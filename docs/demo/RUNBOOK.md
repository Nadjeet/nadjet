# Demo runbook (demo-v1)

Stage procedure for the live demo. Scenario and timing: `docs/08-demo-and-risks.md` section 1.
Deployment: `docs/DEPLOYMENT.md`. Brev: `docs/ONBOARDING.md` section 3. Fallback design:
`docs/10-live-deployment-and-models.md` section 6. Measurements: `docs/demo/RESULTS.md`.

Rules that hold all day (AGENTS.md):
- No manual database edits and no scripted detections. Every incident comes from a real clip through
  the live pipeline (PRD SC-003, FR-VIS-020).
- AI runs only on the team's Brev instance. There is no other provider and no silent fallback.
- Only clips from `eval/heldout.json` play on the demo cameras. Nobody tunes on them.

## Roles and phones

| Who | Device | Account | Does |
|---|---|---|---|
| Presenter | Laptop on the projector | `operator` | Camera wall, confirm, dispatch |
| Responder 1 | Phone 1 (installed PWA) | `civil_protection` | Push alert, status, triage |
| Responder 2 | Phone 2 (SMS only, data off) | `gendarmerie` (phone set in `users.yaml`) | SMS alert, replies `OK <code>`, `T <code> ...` |
| Hospital | Tablet | `hospital` | Pre-alert, READY or DIVERT |
| Citizen | Any phone | none | One-tap report, `try.<domain>/live`, upload |
| Gateway | Android phone with a SIM | SMS gateway app | Sends and receives the real SMS |

Passwords and phone numbers live in `data/seed/users.yaml` and the Dokploy environment, never in git.
Facilities, units and capabilities are simulated and labelled so in the UI (PRD A-02). The demo
footage is research footage and is disclosed as such on the slide (PRD A-01).

## T-1 day

- [ ] CI green on `main`; the maintainer tags `demo-v1` and the `app-images` job finishes.
- [ ] VPS: `NADJET_TAG=demo-v1`, Deploy. `https://api.<domain>/ready` reports PostGIS and Redis.
- [ ] `nadjet-api seed-demo --users data/seed/users.yaml` run in the API container; the output has
      no `WARNING` about responders without a phone.
- [ ] Demo clips and the offline basemap are in the volumes (`docs/DEPLOYMENT.md` section 3).
- [ ] Brev instance is up and warm (see the Brev policy below). `make brev-check` passes.
- [ ] Workers on Brev run `make brev-deploy-workers`; `/system` shows 4 cameras with FPS and latency.
- [ ] `make eval` has been run on the held-out clips; the Evaluation page shows the latest file
      (SC-004, SC-005).
- [ ] Rehearsal 1 and rehearsal 2 passed back to back (checklist below), results in `RESULTS.md`.
- [ ] Backup recording of a full real run saved outside git (see below).
- [ ] Laptop mode tested: `make dev` runs everything locally with the Brev forward
      (`make brev-forward`) as the only remote part.
- [ ] Postgres backup taken (`docs/DEPLOYMENT.md` section 6).

## T-2 h

- [ ] Hotspot (dedicated 4G/5G) charged and tested. Never rely on the venue Wi-Fi.
- [ ] Gateway phone charged, SIM has credit, one test SMS sent and received
      (`nadjet-api send-test-sms --to <number>`).
- [ ] Camera loops running: `/system` shows FPS, per-stage latency and last frame time for each camera.
- [ ] `make brev-check` passes; the vLLM tunnel or forward is up.
- [ ] Phone-as-camera tested from 2 phones over 4G on `https://try.<domain>/live` (HTTPS is required
      for the camera); the phone shows on the camera wall tagged "live demo".
- [ ] Try-it upload of a 30 s clip returns a verdict (SC-006).
- [ ] Both responder phones receive a test alert (push on phone 1, SMS on phone 2).
- [ ] Browser tabs ready: operator console, `/system`, Evaluation page, hospital view, responder PWA.
- [ ] Attribution visible: OpenStreetMap contributors (basemap and facilities, ODbL) and the model
      licences (Qwen3-VL-8B Apache-2.0, RF-DETR Apache-2.0; check `models.lock.yaml`).

## Brev policy and budget

- Start the instance hours before the stage slot and **do not stop it** during the event: a restart
  can fail if that GPU type is unavailable.
- Nobody creates, starts, stops or deletes an instance without the team lead's explicit approval.
  Never paste Brev tokens in chat, tickets or slides.
- Budget and hours: `docs/10-live-deployment-and-models.md` section 4 ("$90 Brev budget plan").
  Verify the live price in the Brev console and the remaining credit before the T-1 day rehearsal.
- Production workers connect outbound only; no inbound port is opened on Brev (`docs/DEPLOYMENT.md`
  section 5).

## Rehearsal checklist (SC-003)

A rehearsal is clean only if every box holds. Record date, tag, who ran it and the timings in
`RESULTS.md`. Two clean rehearsals in a row are required.

1. [ ] Camera wall shows 4 live streams with an annotated and raw toggle. FR-CAM-003, FR-MAP-004
2. [ ] No camera raises an alert during the normal traffic before its impact (false-positive control).
3. [ ] The crash clip on A1 PK42 creates an incident by itself with clip, signals and AI verdict;
       the AI status is shown with its source. FR-VIS-005, FR-VIS-007, FR-INC-001
4. [ ] Operator confirms; unit and hospital recommendations appear with ETAs and routes. FR-DSP-001
5. [ ] Dispatch sends push to phone 1 and SMS to phone 2; the CAP XML is shown. FR-NTF-001
6. [ ] Phone 2 replies `OK <code>` over SMS only; the incident becomes acknowledged. FR-NTF-005, SC-008
7. [ ] Phone 1 taps On scene and sends triage; with data off, `T <code> R1 Y2 G0` by SMS works. SC-008
8. [ ] Hospital tablet shows the pre-alert and READY is visible on the console. FR-HSP-001
9. [ ] Citizen report on a road with no camera creates an unverified incident. FR-CIT-001
10. [ ] Phone-as-camera appears on the wall and gets AI checks. FR-CIT-003
11. [ ] KPI page shows detection and acknowledgement times of this incident. FR-KPI-001
12. [ ] No database edit and no scripted detection happened (check the audit log).

## Fallback ladder

| Problem | Do this |
|---|---|
| Brev or vLLM down | Incidents continue from rules with `verifier: unavailable`; the UI says "AI unavailable". Say so out loud. No other AI provider. |
| One camera or stream fails | Drop to 3 cameras; use `make camsim-restart CAM=<id>` for a stuck clip. |
| UDP blocked | WebRTC falls back to TCP on 8189; last resort HLS (2 to 6 s latency). |
| SMS not delivered | Push and the PWA continue the flow; show the SMS from the gateway log. |
| VPS or internet down | Laptop mode: `make dev` locally, AI through the Brev forward on the hotspot. |
| Everything down | Play the recorded real run and say that it is a recording. |

## Backup recording

A screen recording of a full real run (all 12 rehearsal steps) is made during the second rehearsal
and stored **outside git** (media never goes in the repository).

- Location: _to be filled in by the team after the recording (shared drive link)._
- Recorded by / date / tag: _to be filled in._

## Slides

Every fact on a slide comes from a row marked VERIFIED in `docs/02-algeria-research.md`. ANNOUNCED
and UNKNOWN items are never presented as facts; the list of claims to avoid is in
`docs/08-demo-and-risks.md` section 2. State plainly: integration-ready (RTSP/ONVIF, CAP 1.2, SMS),
not integrated, no partnerships.

## After the event

Delete the demo phone numbers entered on the spot, let the try-it sandbox expire (1 h), keep the
Brev instance only as long as the team decides, and archive the recording and `RESULTS.md`.
