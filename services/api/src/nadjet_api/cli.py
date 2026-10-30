"""``nadjet-api`` command line: run the server or export the OpenAPI contract."""

import argparse
import asyncio
import json
import logging
import signal
import sys
import uuid
from pathlib import Path

import httpx
import uvicorn
from redis.asyncio import Redis

from nadjet_api.auth.seed import load_seed_file, seed_users
from nadjet_api.cameras.seed import seed_cameras
from nadjet_api.config import get_settings
from nadjet_api.db import create_engine, create_session_factory
from nadjet_api.geo.seed import load_capabilities, load_facilities, load_units, seed_geo
from nadjet_api.incidents.ingest import CandidateConsumer
from nadjet_api.incidents.signing import ChainSigner, generate_seed_hex
from nadjet_api.main import create_app
from nadjet_api.notifications.channels import SMS, DeliveryRequest, build_channels
from nadjet_api.notifications.grammar import normalize_phone
from nadjet_api.notifications.vapid import generate_vapid
from nadjet_shared.catalogue import load_catalogue

GRACEFUL_SHUTDOWN_S = 3
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OPENAPI = ROOT / "contracts" / "openapi.json"
DEFAULT_CAMERAS = ROOT / "data" / "cameras.yaml"
DEFAULT_SEED_DIR = ROOT / "data" / "seed"


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


async def run_seed_cameras(path: Path) -> None:
    catalogue = load_catalogue(path)
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            count = await seed_cameras(session, catalogue)
    finally:
        await engine.dispose()
    print(f"seed-cameras: {count} camera(s) synced from {path}")


async def run_seed_geo(directory: Path) -> None:
    facilities = load_facilities(directory / "facilities.csv")
    capabilities = load_capabilities(directory / "capabilities.csv")
    units = load_units(directory / "units.csv")
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            counts = await seed_geo(session, facilities, capabilities, units)
    finally:
        await engine.dispose()
    print("seed-geo: {} facilities, {} capabilities, {} units upserted".format(*counts))


async def run_send_test_sms(to: str) -> int:
    """Send one SMS through the configured gateway to check the setup (FR-NTF-003)."""
    async with httpx.AsyncClient() as client:
        channel = build_channels(get_settings(), client).get(SMS)
        if channel is None:
            print(
                "send-test-sms: set NADJET_SMS_GATEWAY_URL and NADJET_SMS_GATEWAY_PASSWORD",
                file=sys.stderr,
            )
            return 1
        request = DeliveryRequest(None, normalize_phone(to), "Nadjet: test SMS", str(uuid.uuid4()))
        try:
            await channel.send(request)
        except Exception as exc:
            print(f"send-test-sms: failed: {exc}", file=sys.stderr)
            return 1
    print(f"send-test-sms: accepted by the gateway for {request.recipient}")
    return 0


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

    cameras = sub.add_parser("seed-cameras", help="sync the camera registry from the catalogue")
    cameras.add_argument("--file", type=Path, default=DEFAULT_CAMERAS)
    sub.add_parser("consume", help="persist candidates from the Redis Stream")
    sub.add_parser("gen-signing-key", help="print a new Ed25519 seed for NADJET_SIGNING_KEY")

    geo = sub.add_parser("seed-geo", help="import facilities and units from data/seed CSV files")
    geo.add_argument("--dir", type=Path, default=DEFAULT_SEED_DIR)

    sub.add_parser("gen-vapid", help="print a new Web Push VAPID key pair for NADJET_VAPID_*")
    sub.add_parser("worker", help="run the notification worker (arq)")
    test_sms = sub.add_parser("send-test-sms", help="send a test SMS through the gateway")
    test_sms.add_argument("--to", required=True, help="recipient phone number")

    args = parser.parse_args(argv)
    if args.command == "gen-vapid":
        private, public = generate_vapid()
        print(f"NADJET_VAPID_PRIVATE_KEY={private}\nNADJET_VAPID_PUBLIC_KEY={public}")
        return 0
    if args.command == "send-test-sms":
        return asyncio.run(run_send_test_sms(args.to))
    if args.command == "worker":
        logging.basicConfig(level=logging.INFO)
        from arq.worker import run_worker

        from nadjet_api.notifications.jobs import WorkerSettings

        run_worker(WorkerSettings)  # type: ignore[arg-type]
        return 0
    if args.command == "gen-signing-key":
        print(generate_seed_hex())
        return 0
    if args.command == "consume":
        logging.basicConfig(level=logging.INFO)
        asyncio.run(run_consume())
        return 0
    if args.command == "seed-cameras":
        asyncio.run(run_seed_cameras(args.file))
        return 0
    if args.command == "seed-geo":
        asyncio.run(run_seed_geo(args.dir))
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
            # Open SSE streams (GET /events) never end on their own: do not wait for them forever.
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S,
        )
        return 0
    return export_openapi(args.out, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
