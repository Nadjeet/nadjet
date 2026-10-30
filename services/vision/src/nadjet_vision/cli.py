"""``nadjet-vision`` command line."""

import argparse
import asyncio
import logging
import sys

import httpx

from nadjet_vision.config import VisionSettings, get_settings
from nadjet_vision.inference import BrevVlmClient, InferenceConfigError
from nadjet_vision.worker import camera_ids, run_cameras


async def check_inference(
    settings: VisionSettings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> int:
    settings = settings or get_settings()
    try:
        client = BrevVlmClient(settings, transport=transport)
    except InferenceConfigError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    try:
        model = await client.check()
    except (httpx.HTTPError, InferenceConfigError) as exc:
        print(
            f"FAIL Brev AI endpoint {settings.vlm_base_url} not usable: {exc}\n"
            "     Start the instance and run `make brev-forward` (see docs/ONBOARDING.md).",
            file=sys.stderr,
        )
        return 1
    finally:
        await client.aclose()
    print(f"OK   Brev AI endpoint {settings.vlm_base_url} serves {model}")
    return 0


async def camera(
    ids: list[str],
    all_cameras: bool,
    duration_s: float | None,
    settings: VisionSettings | None = None,
) -> int:
    settings = settings or get_settings()
    if all_cameras:
        ids = camera_ids(settings.cameras_file)
    return await run_cameras(ids, settings, duration_s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nadjet-vision")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-inference", help="verify the Brev vLLM endpoint and served model")
    cam = sub.add_parser("camera", help="read camera streams and log the frame rate")
    target = cam.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", action="append", default=[], help="camera id (repeatable)")
    target.add_argument("--all", action="store_true", help="every camera in the catalogue")
    cam.add_argument("--duration", type=float, help="stop after this many seconds")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "check-inference":
        return asyncio.run(check_inference())
    if args.command == "camera":
        try:
            return asyncio.run(camera(args.id, args.all, args.duration))
        except KeyboardInterrupt:
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
