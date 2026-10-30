"""Client for the AI verifier served by vLLM on NVIDIA Brev.

Rules (AGENTS.md "AI inference"):
- the endpoint must be loopback (``brev port-forward``) or an explicitly allowed Brev host;
- the served model must be the configured one;
- there is no fallback provider: failures surface as ``VerifierResult(available=False)``
  so the candidate is still published with rule signals only (PRD FR-VIS-009).
"""

import ipaddress
import math
from typing import Any

import httpx
from pydantic import BaseModel

from nadjet_shared import VerifierResult
from nadjet_vision.config import VisionSettings

VERDICTS = ("yes", "no", "cannot_judge")

VERIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "collision_visible": {"type": "string", "enum": list(VERDICTS)},
        "description_fr": {"type": "string"},
        "description_ar": {"type": "string"},
    },
    "required": ["collision_visible", "description_fr", "description_ar"],
    "additionalProperties": False,
}

NEUTRAL_PROMPT = (
    "Describe only what is visible in this road camera video. Is a collision between road "
    "users visible? Answer collision_visible with yes, no, or cannot_judge (if the image is "
    "too dark, blurred or small). Then give a short factual description in French and Arabic. "
    "Do not guess about people's health."
)


class VerifierAnswer(BaseModel):
    collision_visible: str
    description_fr: str
    description_ar: str


class InferenceConfigError(RuntimeError):
    """The configured endpoint is not an allowed Brev endpoint."""


def assert_brev_endpoint(settings: VisionSettings) -> None:
    host = settings.vlm_base_url.host or ""
    if host in settings.vlm_allowed_hosts or host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise InferenceConfigError(
        f"AI endpoint host {host!r} is not loopback or an allowed Brev host. "
        "Use `make brev-forward`, or add the Brev host to NADJET_VLM_ALLOWED_HOSTS. "
        "Other AI providers are not allowed."
    )


def yes_probability(logprobs: dict[str, Any] | None) -> float | None:
    """Normalised probability of the 'yes' verdict from the first verdict token's top_logprobs."""
    if not logprobs:
        return None
    for token in logprobs.get("content") or []:
        candidates = {
            alt["token"].strip().strip('"').lower(): alt["logprob"]
            for alt in token.get("top_logprobs") or []
        }
        if token.get("token", "").strip().strip('"').lower() not in {"yes", "no", "cannot"}:
            continue
        scores = {
            v: math.exp(candidates[k]) for v in VERDICTS if (k := v.split("_")[0]) in candidates
        }
        total = sum(scores.values())
        return scores.get("yes", 0.0) / total if total > 0 else None
    return None


class BrevVlmClient:
    def __init__(self, settings: VisionSettings, transport: httpx.AsyncBaseTransport | None = None):
        assert_brev_endpoint(settings)
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=str(settings.vlm_base_url).rstrip("/"),
            timeout=settings.vlm_timeout_s,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def served_models(self) -> list[str]:
        response = await self._client.get("/models")
        response.raise_for_status()
        return [m["id"] for m in response.json().get("data", [])]

    async def check(self) -> str:
        """Raise if the Brev endpoint is unreachable or serves another model."""
        models = await self.served_models()
        if self._settings.vlm_model not in models:
            raise InferenceConfigError(
                f"Brev vLLM serves {models}, expected {self._settings.vlm_model!r}"
            )
        return self._settings.vlm_model

    async def verify(self, video_url: str) -> VerifierResult:
        payload = {
            "model": self._settings.vlm_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "video_url", "video_url": {"url": video_url}},
                        {"type": "text", "text": NEUTRAL_PROMPT},
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "verdict", "schema": VERIFIER_SCHEMA},
            },
            "temperature": 0,
            "max_tokens": 256,
            "logprobs": True,
            "top_logprobs": 5,
        }
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            choice = response.json()["choices"][0]
            answer = VerifierAnswer.model_validate_json(choice["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            return VerifierResult(available=False, model=self._settings.vlm_model)
        return VerifierResult(
            available=True,
            model=self._settings.vlm_model,
            collision_visible=answer.collision_visible,
            yes_probability=yes_probability(choice.get("logprobs")),
            description_fr=answer.description_fr,
            description_ar=answer.description_ar,
        )
