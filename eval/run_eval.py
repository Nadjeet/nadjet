"""Honest AI evaluation on the held-out clips (PRD SC-004, SC-005, FR-VIS-022, doc 04 §5).

Run it with ``make eval`` on a machine that has the GPU extra and the Brev tunnel
(``make brev-forward``). It replays every scorable clip of ``eval/heldout.json`` through the
real pipeline (detector, tracker, trigger rules), asks the Brev verifier and sweep about what
the live worker would have asked, matches alerts to the annotated events, and writes
``eval/results/<date>-<git-sha>.json`` (served by ``GET /evaluation/latest``) and a Markdown
summary next to it. ``make eval-compare A=<file> B=<file>`` checks that two runs agree within
their intervals.

This script and the catalogue validators are the only readers of the held-out list; it refuses
to run when a tuning file mentions a clip id or a camera with trigger overrides shows a clip.
The AI is the Brev endpoint only; if it is down the run stops (no silent fallback).
"""

import argparse
import asyncio
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from nadjet_shared.catalogue import Camera, Catalogue, load_catalogue
from nadjet_shared.evaluation import EvaluationResults, SkippedClip
from nadjet_shared.heldout import Heldout, HeldoutClip, load_heldout
from nadjet_vision.config import VisionSettings
from nadjet_vision.evaluation import (
    ClipOutcome,
    build_results,
    compare_runs,
    render_markdown,
    tuned_camera_clips,
    tuning_references,
)

ROOT = Path(__file__).resolve().parents[1]
NEGATIVE_EVENTS = {"normal", "heavy_congestion"}
TUNING_GLOBS = ("data/tuning/**/*", ".env", ".env.example", "eval/tuning/**/*")


@dataclass(frozen=True)
class Plan:
    clip: HeldoutClip
    camera: Camera
    video: Path


def plan_clips(
    heldout: Heldout,
    catalogue: Catalogue,
    videos_dir: Path,
    eval_videos_dir: Path,
    fallback_camera: str | None = None,
) -> tuple[list[Plan], list[SkippedClip]]:
    """Which clips can be scored and why the others cannot (nothing is silently dropped)."""
    cameras = {c.clip_id: c for c in catalogue.cameras}
    by_id = {c.id: c for c in catalogue.cameras}
    plans: list[Plan] = []
    skipped: list[SkippedClip] = []
    for clip in heldout.clips:
        camera = cameras.get(clip.id) or (by_id.get(fallback_camera) if fallback_camera else None)
        if clip.event == "crash" and clip.annotation_status != "annotated":
            skipped.append(SkippedClip(id=clip.id, reason="crash annotation pending"))
        elif camera is None:
            skipped.append(SkippedClip(id=clip.id, reason="no camera zones (pass --camera)"))
        else:
            own = cameras.get(clip.id)
            video = (videos_dir / own.video) if own else (eval_videos_dir / f"{clip.id}.mp4")
            if not video.is_file():
                skipped.append(SkippedClip(id=clip.id, reason=f"video missing: {video}"))
            else:
                plans.append(Plan(clip, camera, video))
    return plans, skipped


def kind_of(clip: HeldoutClip) -> str:
    if clip.event == "crash":
        return "crash"
    return "negative" if clip.event in NEGATIVE_EVENTS else "stalled"


def tuning_violations(heldout: Heldout, root: Path = ROOT) -> list[str]:
    """Tuning configuration that references an evaluation clip (FR-VIS-022): refuse to run."""
    ids = [c.id for c in heldout.clips]
    files = {
        str(p.relative_to(root)): p.read_text()
        for pattern in TUNING_GLOBS
        for p in root.glob(pattern)
        if p.is_file()
    }
    raw = yaml.safe_load((root / "data/cameras.yaml").read_text())
    return [*tuning_references(ids, files), *tuned_camera_clips(raw["cameras"], ids)]


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603, S607
    return out.stdout.strip()


async def run(args: argparse.Namespace) -> int:
    from nadjet_vision.detect import load_detector
    from nadjet_vision.inference import BrevVlmClient
    from nadjet_vision.ingest import FrameSampler, PacketRing, iter_frames
    from nadjet_vision.replay import replay_clip
    from nadjet_vision.track import ByteTrackTracker
    from nadjet_vision.verifier import AiVerifier

    settings = VisionSettings(cameras_file=ROOT / "data/cameras.yaml")
    heldout = load_heldout(ROOT / "eval/heldout.json")
    problems = tuning_violations(heldout)
    if problems:
        print("Refusing to run: tuning configuration references evaluation clips:", file=sys.stderr)
        print(*(f"  {p}" for p in problems), sep="\n", file=sys.stderr)
        return 3
    catalogue = load_catalogue(settings.cameras_file)
    plans, skipped = plan_clips(heldout, catalogue, ROOT / "data/videos", args.videos, args.camera)
    if not plans:
        print("No clip can be scored:", *(f"  {s.id}: {s.reason}" for s in skipped), sep="\n")
        return 2

    client: BrevVlmClient | None = None
    verifier: AiVerifier | None = None
    models = {"detector": settings.detector_model}
    if not args.no_ai:
        client = BrevVlmClient(settings)
        try:
            models["verifier"] = await client.check()
        except Exception as exc:
            print(
                f"AI unavailable ({exc}); run `make brev-forward` or use --no-ai.", file=sys.stderr
            )
            return 4
        # No back-off: in the live worker a down AI is skipped for 30 s, here every answer must
        # come from the model or the run fails (see the check after the replay).
        verifier = AiVerifier(
            client, settings.vlm_model, budget_s=settings.vlm_budget_s, backoff_s=0.0
        )

    detector = load_detector(settings)
    outcomes: list[ClipOutcome] = []
    latency: dict[str, list[float]] = {"frame": [], "verify": [], "sweep": []}
    ai_unavailable = 0
    started_at = datetime.now(UTC)
    dirty = bool(git("status", "--porcelain", "--", ".", ":!eval/results"))
    for plan in plans:
        print(f"replaying {plan.clip.id} ({plan.video.name})", flush=True)
        ring = PacketRing(settings.evidence_buffer_s)
        frames = iter_frames(
            str(plan.video),
            lambda: False,
            sampler=FrameSampler(settings.sample_fps),
            ring=ring,
            options={},
            open_timeout=None,
        )
        replayed = await replay_clip(
            frames,
            camera=plan.camera,
            settings=settings,
            detector=detector,
            tracker=ByteTrackTracker(settings.sample_fps, settings.detector_threshold),
            ring=ring,
            verifier=verifier,
        )
        latency["frame"] += replayed.frame_ms
        latency["verify"] += replayed.verify_ms
        latency["sweep"] += replayed.sweep_ms
        ai_unavailable += replayed.ai_unavailable
        outcomes.append(
            ClipOutcome(
                plan.clip.id,
                kind_of(plan.clip),
                replayed.duration_s,
                plan.clip.impact_time_s,
                tuple(replayed.alerts),
            )
        )
    stats = client.stats if client is not None else None
    if client is not None:
        await client.aclose()
    if ai_unavailable:
        print(
            f"AI unavailable for {ai_unavailable} verification(s) during the run (timeout or "
            "server down): the '+ verifier' / '+ sweep' rows would silently fall back to rules "
            "only. No results written; fix Brev and rerun, or use --no-ai.",
            file=sys.stderr,
        )
        return 4
    now = datetime.now(UTC)
    sha = git("rev-parse", "--short", "HEAD") or "unknown"
    results = build_results(
        outcomes=outcomes,
        skipped=skipped,
        stats=stats,
        latency_ms=latency,
        git_sha=sha,
        dirty=dirty,
        seed=args.seed,
        samples=args.samples,
        models=models,
        generated_at=now,
    )
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    # Time in the name: two runs of one commit (the reproducibility check) must not overwrite.
    stem = f"{started_at:%Y-%m-%d-%H%M%S}-{sha}"
    (out / f"{stem}.json").write_text(results.model_dump_json(indent=2) + "\n")
    (out / f"{stem}.md").write_text(render_markdown(results))
    print(render_markdown(results))
    print(f"wrote {out / stem}.json")
    return 0


def compare(first: Path, second: Path) -> int:
    a = EvaluationResults.model_validate_json(first.read_text())
    b = EvaluationResults.model_validate_json(second.read_text())
    problems = compare_runs(a, b)
    if problems:
        print("Runs disagree:", *problems, sep="\n  ")
        return 1
    print(f"{first.name} and {second.name} agree within their intervals")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--videos", type=Path, default=ROOT / "data/eval", help="Eval-role clips")
    parser.add_argument("--camera", help="Camera id whose zones score clips with no camera")
    parser.add_argument("--out", type=Path, default=ROOT / "eval/results")
    parser.add_argument("--samples", type=int, default=1000, help="Bootstrap resamples")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-ai", action="store_true", help="Rules only (no Brev needed)")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"))
    args = parser.parse_args(argv)
    if args.compare:
        return compare(*args.compare)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
