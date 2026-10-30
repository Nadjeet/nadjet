"""``nadjet-vision`` command line."""

import argparse
import asyncio
import sys

import httpx

from nadjet_vision.config import get_settings
from nadjet_vision.inference import BrevVlmClient, InferenceConfigError


async def check_inference() -> int:
    settings = get_settings()
    try:
        client = BrevVlmClient(settings)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nadjet-vision")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-inference", help="verify the Brev vLLM endpoint and served model")
    args = parser.parse_args(argv)
    if args.command == "check-inference":
        return asyncio.run(check_inference())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
