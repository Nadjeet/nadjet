# /// script
# requires-python = ">=3.12"
# dependencies = ["segno==1.6.6"]
# ///
"""Print-ready QR code of the public report page (FR-CIT-001, US-9).

    uv run --script scripts/gen_report_qr.py https://nadjet.example/public/report

Writes ``docs/demo/qr-report.png`` (override with ``--out``) and prints the short URL to print
under the code. Re-run it with the real public address before printing posters.
"""

import argparse
from pathlib import Path

import segno

DEFAULT_URL = "https://nadjet.example/public/report"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "demo" / "qr-report.png"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="public URL of /public/report")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Error level Q survives a scuffed or sun-faded poster; scale 20 is ~700 px, enough for A4.
    segno.make(args.url, error="q").save(args.out, scale=20, border=4)
    print(f"{args.out}\n{args.url}")


if __name__ == "__main__":
    main()
