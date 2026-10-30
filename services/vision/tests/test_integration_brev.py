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
