import httpx
import pytest

from nadjet_vision.cli import check_inference
from nadjet_vision.config import VisionSettings

MODEL = "Qwen/Qwen3-VL-8B-Instruct-FP8"


def models(*ids: str) -> httpx.MockTransport:
    body = {"data": [{"id": i} for i in ids]}
    return httpx.MockTransport(lambda r: httpx.Response(200, json=body))


async def test_check_inference_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert await check_inference(VisionSettings(vlm_model=MODEL), transport=models(MODEL)) == 0
    assert "serves Qwen/Qwen3-VL-8B-Instruct-FP8" in capsys.readouterr().out


async def test_check_inference_wrong_model(capsys: pytest.CaptureFixture[str]) -> None:
    assert await check_inference(VisionSettings(vlm_model=MODEL), transport=models("other")) == 1
    assert "make brev-forward" in capsys.readouterr().err


async def test_check_inference_unreachable(capsys: pytest.CaptureFixture[str]) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert await check_inference(VisionSettings(), transport=httpx.MockTransport(down)) == 1
    assert "not usable" in capsys.readouterr().err


async def test_check_inference_refuses_non_brev_host(capsys: pytest.CaptureFixture[str]) -> None:
    settings = VisionSettings(vlm_base_url="https://api.openai.com/v1")  # type: ignore[arg-type]
    assert await check_inference(settings) == 1
    assert "not allowed" in capsys.readouterr().err
