"""``nadjet-vision`` command line."""

import argparse
import asyncio
import logging
import signal
import sys

import httpx

from nadjet_vision.config import VisionSettings, get_settings
from nadjet_vision.inference import BrevVlmClient, InferenceConfigError
from nadjet_vision.pipeline import run_worker
from nadjet_vision.supervisor import supervise
from nadjet_vision.worker import camera_ids


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
    *,
    inline: bool = False,
    settings: VisionSettings | None = None,
) -> int:
    """Run cameras: one process each (supervised), or one in this process with ``inline``."""
    settings = settings or get_settings()
    if all_cameras:
        ids = camera_ids(settings.cameras_file)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    if duration_s is not None:
        loop.call_later(duration_s, stop.set)
    if inline:
        if len(ids) != 1:
            print("FAIL --inline runs exactly one camera", file=sys.stderr)
            return 2
        await run_worker(ids[0], settings, stop)
        return 0
    return await supervise(ids, settings, stop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nadjet-vision")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-inference", help="verify the Brev vLLM endpoint and served model")
    cam = sub.add_parser("camera", help="read camera streams and log the frame rate")
    target = cam.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", action="append", default=[], help="camera id (repeatable)")
    target.add_argument("--all", action="store_true", help="every camera in the catalogue")
    cam.add_argument("--duration", type=float, help="stop after this many seconds")
    cam.add_argument("--inline", action="store_true", help="one camera in this process")
    cam.add_argument("--metrics-port", type=int, help="serve /metrics on this port (--inline)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "check-inference":
        return asyncio.run(check_inference())
    if args.command == "camera":
        try:
            settings = get_settings()
            if args.metrics_port is not None:
                settings = settings.model_copy(update={"metrics_port": args.metrics_port})
            return asyncio.run(
                camera(args.id, args.all, args.duration, inline=args.inline, settings=settings)
            )
        except KeyboardInterrupt:
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
