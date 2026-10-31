"""Live check against the team's Brev vLLM endpoint (`make test-brev`).

Requires a running Brev instance and `make brev-forward`. Not part of `make test` or CI,
because it consumes GPU credits; it fails (does not skip) when the endpoint is unusable.
"""

import pytest

from nadjet_vision.config import VisionSettings
from nadjet_vision.inference import BrevVlmClient

pytestmark = pytest.mark.brev


async def test_brev_endpoint_serves_configured_model() -> None:
    settings = VisionSettings()
    client = BrevVlmClient(settings)
    try:
        assert await client.check() == settings.vlm_model
    finally:
        await client.aclose()


async def test_brev_verifier_answers_the_full_schema_on_a_synthetic_clip() -> None:
    """A moving-square clip (never a held-out clip, FR-VIS-022) through the real model."""
    from nadjet_vision.verifier import AiVerifier

    from .conftest import make_stream

    settings = VisionSettings()
    client = BrevVlmClient(settings)
    try:
        packets, info = make_stream(seconds=14)
        result = await AiVerifier(client, settings.vlm_model).sweep(packets, info, end_s=12.0)
    finally:
        await client.aclose()
    assert result.available, "the Brev endpoint did not return a valid answer"
    assert result.model == settings.vlm_model
    assert result.collision_visible in {"yes", "no", "cannot_judge"}
    assert result.description_fr and result.description_ar
