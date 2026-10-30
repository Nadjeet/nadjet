"""Matching, metrics, bootstrap, ablation and guards on synthetic events (SC-004, SC-005)."""

import pytest

from nadjet_shared.evaluation import AlertRecord, EvaluationResults
from nadjet_vision.evaluation import (
    RULES,
    RULES_VERIFIER,
    RULES_VERIFIER_SWEEP,
    ClipOutcome,
    ai_quality,
    compare_runs,
    counts_in,
    evaluate,
    percentiles,
    score_clip,
    tuned_camera_clips,
    tuning_references,
    vetoed,
    wilson,
)
from nadjet_vision.verdict import VerifyStats


def alert(
    t_fire: float,
    *,
    trigger: str = "collision_candidate",
    source: str = "rule",
    t_peak: float | None = None,
    visible: str | None = None,
    status: str = "probable",
    available: bool = False,
) -> AlertRecord:
    return AlertRecord(
        source=source,  # type: ignore[arg-type]
        trigger=trigger,
        t_fire=t_fire,
        t_peak=t_fire - 3 if t_peak is None else t_peak,
        ai_status=status,
        collision_visible=visible,
        verifier_available=available,
    )


def crash(impact: float, *alerts: AlertRecord, id: str = "c") -> ClipOutcome:
    return ClipOutcome(id, "crash", 60.0, impact, alerts)


def negative(seconds: float, *alerts: AlertRecord, id: str = "n") -> ClipOutcome:
    return ClipOutcome(id, "negative", seconds, None, alerts)


# ---------------------------------------------------------------- matching window


@pytest.mark.parametrize(
    ("t_fire", "hit"),
    [(8.0, True), (20.0, True), (7.9, False), (20.1, False), (14.0, True)],
)
def test_window_is_impact_minus_2_s_to_impact_plus_10_s(t_fire: float, hit: bool) -> None:
    score = score_clip(crash(10.0, alert(t_fire)), RULES)
    assert (score.tp, score.fn) == ((1, 0) if hit else (0, 1))


def test_delay_and_peak_error_are_measured_from_the_annotated_impact() -> None:
    score = score_clip(crash(10.0, alert(14.0, t_peak=11.5)), RULES)
    assert score.delay_s == pytest.approx(4.0)
    assert score.peak_error_s == pytest.approx(1.5)


def test_an_early_peak_estimate_gives_a_negative_error() -> None:
    assert score_clip(crash(10.0, alert(13.0, t_peak=9.0)), RULES).peak_error_s == -1.0


def test_several_alerts_in_the_window_are_one_true_positive_on_the_earliest() -> None:
    score = score_clip(crash(10.0, alert(16.0), alert(12.0, trigger="hard_stop")), RULES)
    assert (score.tp, score.fp, score.delay_s) == (1, 0, 2.0)


def test_alerts_outside_the_window_are_false_positives_even_with_a_hit() -> None:
    score = score_clip(crash(10.0, alert(12.0), alert(50.0)), RULES)
    assert (score.tp, score.fp) == (1, 1)


def test_a_missed_crash_is_a_false_negative_and_its_stray_alerts_false_positives() -> None:
    score = score_clip(crash(10.0, alert(40.0)), RULES)
    assert (score.tp, score.fn, score.fp) == (0, 1, 1)
    assert score.delay_s is None


def test_a_stalled_vehicle_alert_in_a_crash_window_does_not_count_as_the_crash() -> None:
    score = score_clip(crash(10.0, alert(12.0, trigger="stalled_vehicle")), RULES)
    assert (score.tp, score.fn, score.fp) == (0, 1, 1)


def test_a_crash_clip_needs_an_impact_time() -> None:
    with pytest.raises(ValueError, match="no impact time"):
        score_clip(ClipOutcome("x", "crash", 10, None, ()), RULES)


def test_stalled_clip_counts_any_stalled_vehicle_alert() -> None:
    clip = ClipOutcome(
        "s", "stalled", 90.0, None, (alert(30.0, trigger="stalled_vehicle"), alert(5.0))
    )
    score = score_clip(clip, RULES)
    assert (score.tp, score.fp, score.fn, score.gt) == (1, 1, 0, 1)
    assert score.delay_s is None


def test_negative_clip_alerts_are_false_alarms_over_its_duration() -> None:
    score = score_clip(negative(1800.0, alert(10.0), alert(900.0)), RULES)
    assert (score.fp, score.negative_alerts, score.negative_s, score.gt) == (2, 2, 1800.0, 0)


# ---------------------------------------------------------------- ablation configurations


def verified(trigger: str, visible: str, status: str = "possible") -> AlertRecord:
    return alert(12.0, trigger=trigger, visible=visible, status=status, available=True)


def test_verifier_vetoes_a_collision_rule_only_when_it_says_no() -> None:
    assert vetoed(verified("hard_stop", "no"))
    assert not vetoed(verified("hard_stop", "yes"))
    assert not vetoed(verified("hard_stop", "cannot_judge"))
    assert not vetoed(alert(12.0, visible=None, available=False))  # unavailable never vetoes


def test_a_stalled_or_pedestrian_alert_is_not_vetoed_by_a_collision_verdict_of_no_alone() -> None:
    assert not vetoed(verified("stalled_vehicle", "no", status="probable"))
    assert vetoed(verified("stalled_vehicle", "no", status="possible"))


def test_ablation_configs_filter_the_same_alerts() -> None:
    rule_ok = alert(12.0, visible="yes", available=True)
    rule_no = verified("collision_candidate", "no")
    sweep = alert(15.0, trigger="ai_sweep", source="sweep")
    assert [counts_in(RULES, a) for a in (rule_ok, rule_no, sweep)] == [True, True, False]
    assert [counts_in(RULES_VERIFIER, a) for a in (rule_ok, rule_no, sweep)] == [True, False, False]
    assert [counts_in(RULES_VERIFIER_SWEEP, a) for a in (rule_ok, rule_no, sweep)] == [
        True,
        False,
        True,
    ]
    with pytest.raises(ValueError, match="unknown configuration"):
        counts_in("magic", rule_ok)


def test_the_verifier_raises_precision_and_the_sweep_raises_recall() -> None:
    clips = [
        crash(10.0, alert(13.0, visible="yes", available=True), id="a"),
        crash(10.0, id="b-missed-by-rules"),
        negative(3600.0, verified("collision_candidate", "no"), id="jam"),
    ]
    clips[1] = crash(10.0, alert(14.0, trigger="ai_sweep", source="sweep"), id="b")
    rules = evaluate(clips, RULES, samples=50)
    with_ai = evaluate(clips, RULES_VERIFIER, samples=50)
    with_sweep = evaluate(clips, RULES_VERIFIER_SWEEP, samples=50)
    assert (rules.true_positives, rules.false_positives) == (1, 1)
    assert (with_ai.true_positives, with_ai.false_positives) == (1, 0)
    assert with_ai.precision.value == 1.0 and rules.precision.value == 0.5
    assert with_sweep.true_positives == 2
    assert with_sweep.recall.value == 1.0 and with_ai.recall.value == 0.5
    assert rules.false_alarms_per_camera_hour.value == 1.0
    assert with_ai.false_alarms_per_camera_hour.value == 0.0


# ---------------------------------------------------------------- metrics


def test_precision_recall_f1_and_hours() -> None:
    clips = [
        crash(10.0, alert(13.0), id="1"),
        crash(10.0, alert(14.0), alert(45.0), id="2"),
        crash(10.0, id="3"),
        negative(1800.0, alert(100.0), id="n1"),
        negative(5400.0, id="n2"),
    ]
    m = evaluate(clips, RULES, samples=20)
    assert (m.ground_truth, m.true_positives, m.false_negatives, m.false_positives) == (3, 2, 1, 2)
    assert m.precision.value == pytest.approx(0.5)
    assert m.recall.value == pytest.approx(2 / 3)
    assert m.f1.value == pytest.approx(2 * 0.5 * (2 / 3) / (0.5 + 2 / 3))
    assert m.camera_hours == pytest.approx(2.0)
    assert m.false_alarms_per_camera_hour.value == pytest.approx(0.5)
    assert m.median_delay_s.value == pytest.approx(3.5)
    assert m.mean_peak_error_s.value == pytest.approx(0.5)  # errors 0 and +1


def test_undefined_metrics_are_none_not_zero() -> None:
    m = evaluate([negative(600.0)], RULES, samples=10)
    assert m.precision.value is None and m.recall.value is None and m.f1.value is None
    assert m.median_delay_s.value is None
    assert m.false_alarms_per_camera_hour.value == 0.0
    empty = evaluate([], RULES, samples=10)
    assert empty.false_alarms_per_camera_hour.value is None
    assert empty.recall.ci is None


def test_bootstrap_intervals_contain_the_value_and_are_reproducible() -> None:
    clips = [crash(10.0, alert(13.0) if i % 3 else alert(40.0), id=str(i)) for i in range(12)]
    first = evaluate(clips, RULES, samples=300, seed=7)
    second = evaluate(clips, RULES, samples=300, seed=7)
    assert first == second
    assert first.recall.ci is not None and first.recall.value is not None
    assert first.recall.ci.low <= first.recall.value <= first.recall.ci.high
    assert first.recall.ci.high - first.recall.ci.low > 0  # a dozen clips: wide, as documented
    other = evaluate(clips, RULES, samples=300, seed=8)
    assert other.recall.ci != first.recall.ci or other.recall.value == first.recall.value


def test_more_clips_give_narrower_intervals() -> None:
    def clips(n: int) -> list[ClipOutcome]:
        return [crash(10.0, alert(13.0) if i % 2 else alert(40.0), id=str(i)) for i in range(n)]

    small = evaluate(clips(8), RULES, samples=400).recall.ci
    large = evaluate(clips(80), RULES, samples=400).recall.ci
    assert small and large
    assert (large.high - large.low) < (small.high - small.low)


def test_wilson_interval_and_empty_share() -> None:
    share = wilson(9, 10)
    assert share.value == 0.9
    assert share.ci is not None and 0.55 < share.ci.low < 0.9 < share.ci.high <= 1.0
    assert wilson(0, 0) == wilson(0, 0) and wilson(0, 0).value is None
    assert wilson(0, 5).ci is not None and wilson(0, 5).ci.low == 0.0


def test_ai_quality_shares_come_from_the_verifier_counters() -> None:
    stats = VerifyStats(
        answered=18, valid_first_try=15, invalid=2, unavailable=3,
        findings_total=40, findings_dropped=4, cannot_judge=6,
    )  # fmt: skip
    quality = ai_quality(stats)
    assert quality.valid_first_try.value == pytest.approx(15 / 20)  # answered + invalid
    assert quality.dropped_citation_share.value == pytest.approx(0.1)
    assert quality.cannot_judge_share.value == pytest.approx(6 / 18)
    assert (quality.verifications, quality.unavailable) == (18, 3)


def test_percentiles() -> None:
    p = percentiles([1.0, 2.0, 3.0, 4.0, 100.0])
    assert (p.count, p.p50) == (5, 3.0)
    assert p.p95 is not None and p.p95 > 4.0
    assert percentiles([]).p50 is None


# ---------------------------------------------------------------- reproducibility and guard


def results(recall_clips: list[ClipOutcome], seed: int = 0) -> EvaluationResults:
    from datetime import UTC, datetime

    from nadjet_shared.evaluation import AblationRow

    return EvaluationResults(
        generated_at=datetime.now(UTC), git_sha="abc", dirty=False, seed=seed,
        bootstrap_samples=200, window_before_s=2, window_after_s=10, models={}, clips=[],
        camera_hours=0, meets_camera_hour_target=False,
        ablation=[
            AblationRow(name=RULES, description="d", metrics=evaluate(recall_clips, RULES, samples=200)),
            AblationRow(name="boxes on", description="d", not_run_reason="TQ-06 open"),
        ],
    )  # fmt: skip


def test_two_runs_that_agree_within_the_interval_are_reproducible() -> None:
    clips = [crash(10.0, alert(13.0) if i % 4 else alert(40.0), id=str(i)) for i in range(20)]
    assert compare_runs(results(clips), results(clips)) == []
    one_more_hit = [*clips[:-1], crash(10.0, alert(13.0), id="x")]
    assert compare_runs(results(clips), results(one_more_hit)) == []  # within the interval


def test_runs_that_differ_beyond_the_interval_are_reported() -> None:
    good = [crash(10.0, alert(13.0), id=str(i)) for i in range(20)]
    bad = [crash(10.0, alert(50.0), id=str(i)) for i in range(20)]
    problems = compare_runs(results(good), results(bad))
    assert any("recall" in p for p in problems)


def test_tuning_files_may_not_mention_evaluation_clip_ids() -> None:
    files = {
        "tuning/a.yaml": "stalled_s: 30  # chosen watching demo-crash-01",
        "tuning/b.yaml": "stalled_s: 25",
        "tuning/c.yaml": "ids: demo-crash-010",  # a different id sharing a prefix
    }
    assert tuning_references(["demo-crash-01"], files) == ["tuning/a.yaml: demo-crash-01"]
    assert tuning_references([], files) == []


def test_a_camera_with_overrides_on_an_evaluation_clip_is_refused() -> None:
    cameras = [
        {"id": "cam-a", "clip_id": "demo-crash-01", "triggers": {"stalled_s": 30}},
        {"id": "cam-b", "clip_id": "demo-crash-02"},
        {"id": "cam-c", "clip_id": "other", "triggers": {"stalled_s": 30}},
    ]
    assert tuned_camera_clips(cameras, ["demo-crash-01", "demo-crash-02"]) == [
        "camera cam-a (clip demo-crash-01) has trigger overrides"
    ]


# ---------------------------------------------------------------- results file


def assembled(with_ai: bool = True, hours_s: float = 1800.0) -> EvaluationResults:
    from datetime import UTC, datetime

    from nadjet_shared.evaluation import SkippedClip
    from nadjet_vision.evaluation import build_results

    clips = [
        crash(10.0, alert(13.0, visible="yes", available=True), id="c1"),
        negative(hours_s, verified("collision_candidate", "no"), id="n1"),
    ]
    return build_results(
        outcomes=clips,
        skipped=[SkippedClip(id="x", reason="video missing")],
        stats=VerifyStats(answered=2, valid_first_try=2) if with_ai else None,
        latency_ms={"frame": [100.0, 120.0], "verify": [900.0], "sweep": []},
        git_sha="abc1234", dirty=False, seed=3, samples=50, models={"detector": "d"},
        generated_at=datetime(2026, 10, 30, tzinfo=UTC),
    )  # fmt: skip


def test_results_hold_every_configuration_and_say_what_was_not_run() -> None:
    results = assembled()
    assert [r.name for r in results.ablation] == [
        RULES, RULES_VERIFIER, RULES_VERIFIER_SWEEP, "boxes on vs off",
    ]  # fmt: skip
    assert all(r.metrics is not None for r in results.ablation[:3])
    boxes = results.ablation[3]
    assert boxes.metrics is None and "TQ-06" in (boxes.not_run_reason or "")
    assert results.ai_quality is not None and results.ai_quality.verifications == 2
    assert results.latency_ms["frame"].p50 == pytest.approx(110.0)
    assert results.latency_ms["sweep"].count == 0
    assert results.skipped_clips[0].id == "x"
    assert (results.window_before_s, results.window_after_s) == (2.0, 10.0)


def test_without_the_ai_only_the_rules_row_has_numbers() -> None:
    results = assembled(with_ai=False)
    assert results.ablation[0].metrics is not None
    assert [r.not_run_reason for r in results.ablation[1:3]] == ["AI switched off"] * 2
    assert results.ai_quality is None


def test_less_than_one_camera_hour_is_flagged_as_a_limitation() -> None:
    short, long = assembled(hours_s=1800.0), assembled(hours_s=7200.0)
    assert not short.meets_camera_hour_target and short.camera_hours == pytest.approx(0.5)
    assert any("camera-hours" in text for text in short.limitations)
    assert long.meets_camera_hour_target
    assert not any("camera-hours" in text for text in long.limitations)


def test_results_round_trip_and_render_with_intervals_and_the_not_run_rows() -> None:
    from nadjet_vision.evaluation import render_markdown

    results = assembled()
    assert EvaluationResults.model_validate_json(results.model_dump_json()) == results
    text = render_markdown(results)
    assert "rules+verifier+sweep" in text and "not run: TQ-06" in text
    assert "abc1234" in text and "95 % intervals" in text
    assert "Skipped:" in text and "- x: video missing" in text
    assert "valid JSON first try" in text
