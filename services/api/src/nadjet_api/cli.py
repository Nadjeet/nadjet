"""``nadjet-api`` command line: run the server or export the OpenAPI contract."""

import argparse
import json
import sys
from pathlib import Path

import uvicorn

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

    args = parser.parse_args(argv)
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
