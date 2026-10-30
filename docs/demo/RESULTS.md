# Success-criteria results (PRD section 4.2)

Status of every success criterion on the **production setup** (VPS + Brev, tag `demo-v1`).

> **No measurement has been recorded yet.** This file is the sheet to fill in during the T-1 day
> rehearsals; nothing below is an estimate. A value is entered only with the date, the tag, who
> measured it and the source (file, page or log). A miss stays in the table with its mitigation;
> it is never removed or rounded. Integrity rules apply (AGENTS.md): no value comes from a
> hardcoded, scripted or random detection.

| Field | Value |
|---|---|
| Release tag measured | _not yet tagged_ |
| Brev instance and GPU | _to fill in_ |
| Date and team members present | _to fill in_ |

## Summary

| SC | Target | Measured | Status | Evidence |
|---|---|---|---|---|
| SC-001 impact to screen | ≤ 10 s median on held-out demo clips | — | pending | |
| SC-002 confirm to SMS received | ≤ 15 s | — | pending | |
| SC-003 clean rehearsals | 2 consecutive | 0 | pending | |
| SC-004 event-level recall | report honestly; aim ≥ 0.7 | — | pending | |
| SC-005 false alarms per camera-hour | report honestly; aim ≤ 1 | — | pending | |
| SC-006 try-it, 30 s clip | ≤ 60 s | — | pending | |
| SC-007 live camera wall | 4 cameras, ≥ 5 fps, ≤ 1.5 s latency | — | pending | |
| SC-008 responder over SMS only | acknowledge, triage, close all work | — | pending | |

## How each one is measured

**SC-001.** Play each held-out demo crash clip on its simulated camera. For each, read the incident
timeline: event time (impact frame, stream time) against incident creation time. Report the median
and the individual values of at least the demo clips. Source: incident timeline and the KPI page
(FR-KPI-001). The worker's own stage latencies on `/system` explain a miss.

**SC-002.** From the operator's *Confirm* click to the SMS arriving on phone 2. Source: the
notification log (sent time, delivery report) plus a stopwatch on the phone for the last hop.
Report at least five runs. A slow gateway phone or SIM is the usual cause: say so in the mitigation.

**SC-003.** Run the rehearsal checklist in `docs/demo/RUNBOOK.md` twice in a row on production.
Each run is clean only if all 12 steps pass with no manual database edit and no scripted detection.
Record both runs (date, tag, people, result, any step that failed and what changed afterwards). A
failed run resets the count to zero.

**SC-004 and SC-005.** `make eval` (needs `make brev-forward`, GPU extra) writes
`eval/results/<date>-<git-sha>.json` and a Markdown summary; copy the headline numbers with their
confidence intervals and link the file. Check reproducibility with `make eval-compare`. Report the
numbers honestly even when below the aim. Clips without an annotated impact time are listed under
`skipped_clips`; count them in the denominator discussion.

**SC-006.** On `https://try.<domain>`, upload a 30 s clip over the demo network and time from the
upload to the verdict (the page shows the stages). Repeat three times. Source: the System health page.

**SC-007.** With 4 cameras live, read FPS per camera and stage latency from `/system`. Measure the
live-video latency in the browser (burned-in timestamp on a simulated camera versus the wall clock,
or the WebRTC stats) over at least one minute, on the demo network and on a phone hotspot.

**SC-008.** On phone 2 with mobile data off: acknowledge by SMS (`OK <code>`), send triage
(`T <code> R1 Y2 G0`) and close, and confirm every step is reflected on the console.

## Rehearsal log

| # | Date | Tag | Run by | Result | Notes |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |

## Misses and mitigations

_None recorded yet. Each miss is listed here with its cause and the mitigation used on stage (see
the fallback ladder in the runbook)._

## Other launch-readiness items

Tracked in PRD section 20. Not yet verified on production: `demo-v1` deployed, SMS test received,
phone-as-camera on 4G from 2 phones, laptop mode, evaluation page with current results. The
traceability report is `docs/traceability.md` (generated, `make traceability`).
