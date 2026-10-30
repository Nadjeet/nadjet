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


ANSWER = {
    "collision_visible": "yes",
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
    result = await client.verify("file:///clips/a.mp4")
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
    result = await client.verify("file:///clips/a.mp4")
    await client.aclose()
    assert result.available is False
    assert result.collision_visible is None


async def test_verify_timeout_means_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = BrevVlmClient(settings(), transport=transport(handler))
    result = await client.verify("file:///clips/a.mp4")
    await client.aclose()
    assert result.available is False
