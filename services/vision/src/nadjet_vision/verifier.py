"""AI verification of a rule candidate and of a sweep window, through the Brev vLLM client.

Builds the numbered, time-stamped video from the packet ring (``clipvideo``) and asks the
neutral question (``inference``). The answer is validated (``verdict``). Nothing here talks to any
provider other than the Brev endpoint (AGENTS.md "AI inference").
"""

import asyncio
import logging
from collections.abc import Sequence

from nadjet_shared import TriggerType, VerifierResult
from nadjet_vision.clipvideo import VerifierVideo, build_sweep_video, build_verifier_video
from nadjet_vision.inference import BrevVlmClient
from nadjet_vision.ingest import Packet, StreamInfo

log = logging.getLogger("nadjet_vision.verifier")


class AiVerifier:
    def __init__(self, client: BrevVlmClient, model: str) -> None:
        self._client = client
        self._model = model

    def _unavailable(self) -> VerifierResult:
        return VerifierResult(available=False, model=self._model)

    async def _ask(self, video: VerifierVideo | None, trigger: TriggerType) -> VerifierResult:
        if video is None:
            log.warning("no frames to verify (ring empty or without keyframe)")
            return self._unavailable()
        return await self._client.verify(
            video.data_url, frame_count=video.frame_count, trigger=trigger
        )

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
        video = await asyncio.to_thread(build_verifier_video, packets, info, centre_s)
        return await self._ask(video, trigger)

    async def sweep(
        self, packets: Sequence[Packet], info: StreamInfo | None, end_s: float
    ) -> VerifierResult:
        """Verdict on the last 8 s before ``end_s`` (no rule fired)."""
        if info is None:
            return self._unavailable()
        video = await asyncio.to_thread(build_sweep_video, packets, info, end_s)
        return await self._ask(video, TriggerType.AI_SWEEP)
