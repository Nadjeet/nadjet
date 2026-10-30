"""Export JSON Schemas of the shared event models to ``contracts/events/``.

Usage: ``uv run nadjet-export-schemas [--check] [--out DIR]``. With ``--check`` the command
writes nothing and exits 1 if any committed schema differs from the models (CI drift check).
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from nadjet_shared.evaluation import EvaluationResults
from nadjet_shared.events import IncidentCandidate
from nadjet_shared.health import CameraHealthReport

MODELS: dict[str, type[BaseModel]] = {
    "incident.candidate": IncidentCandidate,
    "camera.health": CameraHealthReport,
    "evaluation.results": EvaluationResults,
}

DEFAULT_OUT = Path(__file__).resolve().parents[4] / "contracts" / "events"


def render(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


def export(out_dir: Path, *, check: bool) -> list[str]:
    """Write (or compare) every schema. Returns the names of files that differ."""
    drifted: list[str] = []
    if not check:
        out_dir.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        path = out_dir / f"{name}.schema.json"
        content = render(model)
        current = path.read_text() if path.exists() else None
        if current != content:
            drifted.append(path.name)
            if not check:
                path.write_text(content)
    return drifted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if schemas are out of date")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    drifted = export(args.out, check=args.check)
    if args.check and drifted:
        print(f"Out-of-date schemas: {', '.join(drifted)}. Run `make gen`.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
