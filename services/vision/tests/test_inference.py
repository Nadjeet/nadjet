import json
import math
from typing import Any

import httpx
import pytest

from nadjet_vision.config import VisionSettings
from nadjet_vision.inference import (
    BrevVlmClient,
    InferenceConfigError,
    assert_brev_endpoint,
    yes_probability,
)

MODEL = "Qwen/Qwen3-VL-8B-Instruct-FP8"


def settings(**overrides: Any) -> VisionSettings:
    return VisionSettings(vlm_model=MODEL, **overrides)


def token(text: str, alts: dict[str, float]) -> dict[str, Any]:
    return {
        "token": text,
        "logprob": alts.get(text, -1.0),
        "top_logprobs": [{"token": t, "logprob": lp} for t, lp in alts.items()],
    }


def completion(content: dict[str, Any], logprobs: dict[str, Any] | None) -> dict[str, Any]:
    return {"choices": [{"message": {"content": json.dumps(content)}, "logprobs": logprobs}]}


ANSWER: dict[str, Any] = {
    "collision_visible": "yes",
    "t_contact": 0.5,
    "type": "collision",
    "vehicles_involved": 2,
    "lanes_blocked": 1,
    "findings": [{"statement": "Two cars touch", "basis": "observed", "frame_ids": [3, 4]}],
    "not_assessable": ["occupants"],
    "priority_raise": 0,
    "description_fr": "Deux voitures.",
    "description_ar": "سيارتان.",
}


def transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/v1", "http://localhost:8000/v1"])
def test_loopback_endpoints_are_allowed(url: str) -> None:
    assert_brev_endpoint(settings(vlm_base_url=url))


def test_non_brev_hosts_are_refused() -> None:
    with pytest.raises(InferenceConfigError, match="Other AI providers are not allowed"):
        assert_brev_endpoint(settings(vlm_base_url="https://api.openai.com/v1"))


def test_explicitly_allowed_brev_host_is_accepted() -> None:
    assert_brev_endpoint(
        settings(vlm_base_url="http://nadjet-gpu:8000/v1", vlm_allowed_hosts=["nadjet-gpu"])
    )


def test_yes_probability_normalises_over_verdict_tokens() -> None:
    lp = {
        "content": [
            token("{", {"{": 0.0}),
            token("yes", {"yes": math.log(0.6), "no": math.log(0.2)}),
        ]
    }
    assert yes_probability(lp) == pytest.approx(0.75)


def test_yes_probability_is_none_without_logprobs() -> None:
    assert yes_probability(None) is None
    assert yes_probability({"content": [token("{", {"{": 0.0})]}) is None


async def test_check_accepts_configured_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": MODEL}]})

    client = BrevVlmClient(settings(), transport=transport(handler))
    assert await client.check() == MODEL
    await client.aclose()


async def test_check_rejects_other_served_model() -> None:
    client = BrevVlmClient(
        settings(), transport=transport(lambda r: httpx.Response(200, json={"data": [{"id": "x"}]}))
    )
    with pytest.raises(InferenceConfigError, match="expected"):
        await client.check()
    await client.aclose()


async def test_verify_sends_structured_request_and_parses_answer() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        lp = {"content": [token("yes", {"yes": math.log(0.9), "no": math.log(0.1)})]}
        return httpx.Response(200, json=completion(ANSWER, lp))

    client = BrevVlmClient(settings(), transport=transport(handler))
    result = await client.verify("file:///clips/a.mp4", frame_count=20)
    await client.aclose()

    assert seen["model"] == MODEL
    assert seen["temperature"] == 0
    assert seen["response_format"]["type"] == "json_schema"
    assert seen["messages"][0]["content"][0]["type"] == "video_url"
    assert result.available is True
    assert result.collision_visible == "yes"
    assert result.yes_probability == pytest.approx(0.9)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="overloaded"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}),
    ],
)
async def test_verify_failures_mean_unavailable_never_another_provider(
    response: httpx.Response,
) -> None:
    client = BrevVlmClient(settings(), transport=transport(lambda r: response))
    result = await client.verify("file:///clips/a.mp4", frame_count=20)
    await client.aclose()
    assert result.available is False
    assert result.collision_visible is None


async def test_verify_timeout_means_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = BrevVlmClient(settings(), transport=transport(handler))
    result = await client.verify("file:///clips/a.mp4", frame_count=20)
    await client.aclose()
    assert result.available is False


def test_FR_VIS_009_default_budget_fits_a_measured_verifier_call() -> None:
    """One verifier call took 6.2-6.7 s on the L40S (TD-50); the old 7 s budget, which also
    covers building the clip, made every live candidate 'unavailable'. The budget stays within
    the doc 11 §6 verifier timeout."""
    settings = VisionSettings()
    assert 10.0 <= settings.vlm_budget_s <= settings.vlm_timeout_s


def test_FR_CIT_002_verifier_default_budget_is_the_configured_one() -> None:
    """The try-it worker built ``AiVerifier`` without a budget and got a hardcoded 7 s, so the
    second (refine) pass always timed out (TD-50)."""
    import inspect

    from nadjet_vision.verifier import AiVerifier

    defaults = inspect.signature(AiVerifier.__init__).parameters
    assert defaults["budget_s"].default == VisionSettings.model_fields["vlm_budget_s"].default
    assert defaults["backoff_s"].default == VisionSettings.model_fields["vlm_backoff_s"].default
