"""Verifier answer validation, safety wording and retry (FR-VIS-016/017, AC-VIS-017.1, TD-24)."""

import json
from typing import Any

import httpx
import pytest

from nadjet_shared import TriggerType
from nadjet_vision.config import VisionSettings
from nadjet_vision.inference import BrevVlmClient
from nadjet_vision.verdict import VerifierAnswer, answer_schema, finalize, template_result

from .test_inference import ANSWER, MODEL, token


def answer(**overrides: Any) -> VerifierAnswer:
    return VerifierAnswer.model_validate({**ANSWER, **overrides})


def finding(statement: str, frames: list[int], basis: str = "observed") -> dict[str, Any]:
    return {"statement": statement, "basis": basis, "frame_ids": frames}


def test_schema_asks_for_the_verdict_first_and_every_field_of_doc_11() -> None:
    schema = answer_schema()
    assert next(iter(schema["properties"])) == "collision_visible"
    assert set(schema["required"]) == {
        "collision_visible", "t_contact", "type", "vehicles_involved", "lanes_blocked",
        "findings", "not_assessable", "priority_raise", "description_fr", "description_ar",
    }  # fmt: skip


def test_every_finding_keeps_only_frames_that_exist() -> None:
    raw = answer(
        findings=[finding("Cars touch", [3, 99]), finding("Ghost", [50]), finding("Two", [0])]
    )
    result = finalize(raw, frame_count=20, model=MODEL, yes_probability=0.9)
    assert [(f.statement, f.frame_ids) for f in result.findings] == [
        ("Cars touch", [3]),
        ("Two", [0]),
    ]


def test_dropped_findings_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")
    finalize(answer(findings=[finding("Ghost", [50])]), 20, MODEL, 0.9)
    assert "Ghost" in caplog.text


def test_negative_frame_ids_are_invalid() -> None:
    result = finalize(answer(findings=[finding("x", [-1])]), 20, MODEL, None)
    assert result.findings == []


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("The driver is dead.", "en"),
        ("Un blessé est au sol.", "fr"),
        ("يوجد شخص مصاب.", "ar"),
    ],
)
def test_AC_VIS_017_1_health_words_are_replaced_before_storage(text: str, lang: str) -> None:
    raw = answer(
        description_fr=text if lang == "fr" else "Deux voitures.",
        description_ar=text if lang == "ar" else "سيارتان.",
        findings=[finding(text if lang == "en" else "Cars touch", [1])],
        not_assessable=[text] if lang == "en" else [],
    )
    result = finalize(raw, 20, MODEL, 0.9)
    stored = " ".join(
        [
            result.description_fr or "",
            result.description_ar or "",
            *(f.statement for f in result.findings),
            *result.not_assessable,
        ]
    )
    for word in ("dead", "blessé", "مصاب"):
        assert word not in stored
    assert "needs human assessment" in stored or "humaine" in stored or "تقييم بشري" in stored


def test_priority_raise_needs_a_surviving_finding() -> None:
    cited = finalize(answer(priority_raise=1, findings=[finding("Overturned", [2])]), 20, MODEL, 1)
    uncited = finalize(
        answer(priority_raise=1, findings=[finding("Overturned", [77])]), 20, MODEL, 1
    )
    assert cited.priority_raise == 1
    assert uncited.priority_raise == 0


def test_template_description_comes_from_the_rule_and_marks_the_result_invalid() -> None:
    result = template_result(TriggerType.HARD_STOP, MODEL)
    assert (result.available, result.invalid) == (False, True)
    assert "arrêt brutal" in (result.description_fr or "")
    assert result.description_ar
    assert result.collision_visible is None


class Server:
    """A fake vLLM returning scripted contents."""

    def __init__(self, *contents: str) -> None:
        self.contents = list(contents)
        self.prompts: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.prompts.append(body["messages"][0]["content"][1]["text"])
        content = self.contents.pop(0) if len(self.contents) > 1 else self.contents[0]
        lp = {"content": [token("yes", {"yes": -0.1, "no": -2.5})]}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}, "logprobs": lp}]},
        )


async def ask(server: Server) -> Any:
    client = BrevVlmClient(VisionSettings(vlm_model=MODEL), transport=httpx.MockTransport(server))
    try:
        return await client.verify(
            "data:video/mp4;base64,AAA", frame_count=20, trigger=TriggerType.HARD_STOP
        )
    finally:
        await client.aclose()


async def test_valid_answer_is_finalised_with_the_yes_probability() -> None:
    server = Server(json.dumps(ANSWER))
    result = await ask(server)
    assert result.available and not result.invalid
    assert result.findings[0].frame_ids == [3, 4]
    assert result.yes_probability == pytest.approx(0.9, abs=0.05)
    assert len(server.prompts) == 1


async def test_invalid_answer_is_retried_once_with_the_validation_error() -> None:
    server = Server(json.dumps({"collision_visible": "maybe"}), json.dumps(ANSWER))
    result = await ask(server)
    assert result.available and result.collision_visible == "yes"
    assert len(server.prompts) == 2
    assert "rejected" in server.prompts[1] and "collision_visible" in server.prompts[1]


async def test_answer_invalid_twice_gives_the_template_never_an_error() -> None:
    server = Server("not json")
    result = await ask(server)
    assert (result.available, result.invalid) == (False, True)
    assert "arrêt brutal" in (result.description_fr or "")
    assert len(server.prompts) == 2


async def test_an_unreachable_server_is_not_retried_and_is_unavailable() -> None:
    calls = {"n": 0}

    def down(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("refused", request=request)

    client = BrevVlmClient(VisionSettings(vlm_model=MODEL), transport=httpx.MockTransport(down))
    result = await client.verify("data:video/mp4;base64,AAA", frame_count=20)
    await client.aclose()
    assert (result.available, result.invalid) == (False, False)
    assert calls["n"] == 1
