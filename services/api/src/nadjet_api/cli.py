"""``nadjet-api`` command line: run the server or export the OpenAPI contract."""

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

import uvicorn
from redis.asyncio import Redis

from nadjet_api.auth.seed import load_seed_file, seed_users
from nadjet_api.config import get_settings
from nadjet_api.db import create_engine, create_session_factory
from nadjet_api.incidents.ingest import CandidateConsumer
from nadjet_api.incidents.signing import ChainSigner, generate_seed_hex
from nadjet_api.main import create_app

DEFAULT_OPENAPI = Path(__file__).resolve().parents[4] / "contracts" / "openapi.json"


def render_openapi() -> str:
    schema = create_app(probes={}).openapi()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def export_openapi(path: Path, *, check: bool) -> int:
    content = render_openapi()
    current = path.read_text() if path.exists() else None
    if current == content:
        return 0
    if check:
        print(f"{path.name} is out of date. Run `make gen`.", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return 0


async def run_seed_users(path: Path) -> None:
    users = load_seed_file(path)
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            created, skipped = await seed_users(session, users)
    finally:
        await engine.dispose()
    print(f"seed-users: {created} created, {skipped} already existed")


async def run_consume() -> None:
    """Persist candidates from the Redis Stream until SIGINT/SIGTERM."""
    settings = get_settings()
    engine = create_engine(settings)
    redis: Redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    consumer = CandidateConsumer(
        redis,
        create_session_factory(engine),
        ChainSigner(settings.signing_seed),
        claim_idle_ms=settings.candidate_claim_idle_ms,
    )
    try:
        await consumer.run(stop)
    finally:
        await redis.aclose()
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nadjet-api")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    serve.add_argument("--reload", action="store_true")

    openapi = sub.add_parser("export-openapi", help="write contracts/openapi.json")
    openapi.add_argument("--check", action="store_true", help="fail if the file is out of date")
    openapi.add_argument("--out", type=Path, default=DEFAULT_OPENAPI)

    seed = sub.add_parser("seed-users", help="create dev/demo users from a YAML file")
    seed.add_argument("--file", type=Path, required=True)

    sub.add_parser("consume", help="persist candidates from the Redis Stream")
    sub.add_parser("gen-signing-key", help="print a new Ed25519 seed for NADJET_SIGNING_KEY")

    args = parser.parse_args(argv)
    if args.command == "gen-signing-key":
        print(generate_seed_hex())
        return 0
    if args.command == "consume":
        logging.basicConfig(level=logging.INFO)
        asyncio.run(run_consume())
        return 0
    if args.command == "seed-users":
        asyncio.run(run_seed_users(args.file))
        return 0
    if args.command == "serve":
        uvicorn.run(
            "nadjet_api.main:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0
    return export_openapi(args.out, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
