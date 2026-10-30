"""Client for the AI verifier served by vLLM on NVIDIA Brev.

Rules (AGENTS.md "AI inference"):
- the endpoint must be loopback (``brev port-forward``) or an explicitly allowed Brev host;
- the served model must be the configured one;
- there is no fallback provider: failures surface as ``VerifierResult(available=False)``
  so the candidate is still published with rule signals only (PRD FR-VIS-009).
"""

import ipaddress
import logging
import math
from typing import Any

import httpx
from pydantic import ValidationError

from nadjet_shared import TriggerType, VerifierResult
from nadjet_vision.config import VisionSettings
from nadjet_vision.verdict import (
    VerifierAnswer,
    VerifyStats,
    answer_schema,
    finalize,
    template_result,
)

log = logging.getLogger("nadjet_vision.inference")

VERDICTS = ("yes", "no", "cannot_judge")

NEUTRAL_PROMPT = (
    "You see a road camera video made of numbered frames; each frame shows its number (#n) and "
    "its time in seconds relative to the moment of interest. Describe only what is visible. "
    "Is a collision between road users visible? Answer collision_visible with yes, no, or "
    "cannot_judge (if the image is too dark, blurred or small); no collision is a valid answer. "
    "Give t_contact (seconds on the frame timestamps, null if none), the type of event "
    "(collision, rollover, fire, stalled, pedestrian or none), vehicles_involved, lanes_blocked "
    "and findings. Each finding is one short English statement with basis observed or inferred "
    "and the frame_ids (the #n numbers) it is read from. List in not_assessable what cannot be "
    "seen (occupants, people behind intact windows, fuel leaks). Use priority_raise 1 only when "
    "a finding shows a more serious situation. Write description_fr and description_ar as short "
    "factual descriptions. Never state or guess people's health or death."
)


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
        self.stats = VerifyStats()
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

    async def _ask(self, video_url: str, prompt: str) -> dict[str, Any]:
        payload = {
            "model": self._settings.vlm_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "video_url", "video_url": {"url": video_url}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "verdict", "schema": answer_schema()},
            },
            "temperature": 0,
            "max_tokens": 700,
            "logprobs": True,
            "top_logprobs": 5,
        }
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        choice: dict[str, Any] = response.json()["choices"][0]
        return choice

    async def verify(
        self, video_url: str, *, frame_count: int, trigger: TriggerType = TriggerType.AI_SWEEP
    ) -> VerifierResult:
        """Ask the verifier about one video of ``frame_count`` numbered frames (TD-24).

        Unreachable or timed out: ``available=False`` (FR-VIS-009). An answer that fails the
        schema is asked again once with the validation error; if it fails again the result is
        ``invalid`` with a template description from the rule trigger (FR-VIS-016).
        """
        model = self._settings.vlm_model
        prompt = NEUTRAL_PROMPT
        for attempt in (1, 2):
            try:
                choice = await self._ask(video_url, prompt)
                raw = choice["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
                self.stats.unavailable += 1
                return VerifierResult(available=False, model=model)
            try:
                answer = VerifierAnswer.model_validate_json(raw)
            except ValidationError as exc:
                reason = "; ".join(
                    f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5]
                )
                log.warning("verifier answer invalid (attempt %d): %s", attempt, reason)
                prompt = (
                    f"{NEUTRAL_PROMPT}\nYour previous answer was rejected ({reason}). "
                    "Answer again in the exact format."
                )
                continue
            self.stats.answered += 1
            self.stats.valid_first_try += attempt == 1
            return finalize(
                answer, frame_count, model, yes_probability(choice.get("logprobs")), self.stats
            )
        self.stats.invalid += 1
        return template_result(trigger, model)
