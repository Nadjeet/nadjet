"""AI verification of a rule candidate and of a sweep window, through the Brev vLLM client.

Builds the numbered, time-stamped video from the packet ring (``clipvideo``) and asks the
neutral question (``inference``). The answer is validated (``verdict``). Nothing here talks to any
provider other than the Brev endpoint (AGENTS.md "AI inference").
"""

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Sequence

from nadjet_shared import TriggerType, VerifierResult
from nadjet_vision.clipvideo import (
    VerifierVideo,
    build_scan_video,
    build_sweep_video,
    build_verifier_video,
)
from nadjet_vision.inference import BrevVlmClient
from nadjet_vision.ingest import Packet, StreamInfo

log = logging.getLogger("nadjet_vision.verifier")


class AiVerifier:
    def __init__(
        self,
        client: BrevVlmClient,
        model: str,
        *,
        budget_s: float = 7.0,
        backoff_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._model = model
        self._budget_s = budget_s
        self._backoff_s = backoff_s
        self._clock = clock
        self._down_until = float("-inf")

    def _unavailable(self) -> VerifierResult:
        return VerifierResult(available=False, model=self._model)

    async def _bounded(self, work: Awaitable[VerifierResult]) -> VerifierResult:
        """Run one verification within the budget; a hanging or unreachable AI makes the next
        candidates skip it for ``backoff_s`` so they are not each held for the full budget."""
        if self._clock() < self._down_until:
            if inspect.iscoroutine(work):
                work.close()
            return self._unavailable()
        try:
            result = await asyncio.wait_for(work, timeout=self._budget_s)
        except TimeoutError:
            log.warning("AI verification exceeded %.1fs: unavailable", self._budget_s)
            result = self._unavailable()
        if not result.available:
            self._down_until = self._clock() + self._backoff_s
        return result

    async def _ask(self, video: VerifierVideo | None, trigger: TriggerType) -> VerifierResult:
        if video is None:
            log.warning("no frames to verify (ring empty or without keyframe)")
            return self._unavailable()
        return await self._client.verify(
            video.data_url, frame_count=video.frame_count, trigger=trigger
        )

    async def _video_then_ask(
        self, build: Callable[[], VerifierVideo | None], trigger: TriggerType
    ) -> VerifierResult:
        video = await asyncio.to_thread(build)
        return await self._ask(video, trigger)

    async def verify_event(
        self,
        packets: Sequence[Packet],
        info: StreamInfo | None,
        centre_s: float,
        trigger: TriggerType,
    ) -> VerifierResult:
        """Verdict on the moment ``centre_s`` (stream clock) of a rule candidate."""
        if info is None:
            return self._unavailable()
        return await self._bounded(
            self._video_then_ask(lambda: build_verifier_video(packets, info, centre_s), trigger)
        )

    async def sweep(
        self, packets: Sequence[Packet], info: StreamInfo | None, end_s: float
    ) -> VerifierResult:
        """Verdict on the last 8 s before ``end_s`` (no rule fired)."""
        if info is None:
            return self._unavailable()
        return await self._bounded(
            self._video_then_ask(
                lambda: build_sweep_video(packets, info, end_s), TriggerType.AI_SWEEP
            )
        )

    async def scan(
        self, packets: Sequence[Packet], info: StreamInfo | None, start_s: float, end_s: float
    ) -> VerifierResult:
        """Pass 1 of an upload: the whole clip at 1-2 fps; ``t_contact`` counts from the start."""
        if info is None:
            return self._unavailable()
        video = await asyncio.to_thread(build_scan_video, packets, info, start_s, end_s)
        return await self._ask(video, TriggerType.AI_SWEEP)
