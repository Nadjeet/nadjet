# 08 — Hackathon Demonstration Scenario, Risks and Government Deployment Strategy

## 1. Demo scenario (about 7 minutes, everything live)

**Setup**
- Laptop on the projector shows the operator dashboard.
- Phone 1 runs the Civil Protection responder PWA.
- Phone 2 is a "Gendarmerie patrol" phone that receives SMS only.
- A tablet shows the hospital view, "EPH Rouiba (simulated)".
- An Android SMS-gateway phone runs on the side.
- The `/system` page is visible in a second tab.

| t | What the jury sees | What is really happening |
|---|---|---|
| 0:00 | **The problem in one slide.** 3,838 road deaths in 2025 (DNSR). Three separate emergency numbers. No public response-time data. Cameras exist but people watch them. | Sourced figures from doc 02 |
| 0:45 | **Camera wall.** Four A1 / Algiers cameras live with AI boxes and speed labels. `/system` shows FPS and per-stage latency. | MediaMTX → vision workers → WebRTC + canvas overlay |
| 1:30 | **Congestion camera.** Heavy, slow traffic. **No alert.** | The triggers' jam normalisation and the verifier both reject it, which demonstrates false-positive control |
| 2:00 | **Crash on A1 PK42.** Within seconds an incident card appears: *Possible collision, P1*. Reasons shown: "2 vehicles · stop in live lane · p(crash)=0.9x · pre-impact ~85 km/h". Clip and keyframes attached. The map pin is in Boumerdès. | Real trigger, then the verifier, then a Redis candidate, then the API, then SSE |
| 2:30 | A few seconds later the AI description arrives: "Two cars, side impact, one stopped across the right lane". | Local VLM, async, labelled *advisory* |
| 2:45 | **Operator confirms.** The system recommends the nearest Civil Protection unit (ETA 9 min) and the hospital, CHU or EPH by capability (ETA 14 min), and draws the routes. | PostGIS KNN, then the OSRM `/table` and `/route` calls |
| 3:15 | **Dispatch.** Phone 1 gets a push notification. Phone 2 gets an SMS: `ACC|P1|36.64800,3.32900|A1 PK42|2V|7F3`. The CAP 1.2 XML is shown. | Real SMS via the gateway; real web push |
| 3:45 | Phone 2 replies **`OK 7F3`** by SMS. The dashboard flips to *Acknowledged* and the timeline records the acknowledgement time. | Inbound SMS webhook, parser, state transition |
| 4:15 | **On scene.** On Phone 1 the responder taps *On scene* and fills in triage: 1 red (AVPU=V, RR 28, pulse 120, SpO₂ 91), 2 yellow. With data switched off on the phone, it **falls back to SMS**: `T 7F3 R1 Y2 G0`. | PWA offline queue, then the SMS path |
| 5:00 | **Hospital pre-alert.** The tablet shows 3 incoming patients, 1 red with vitals, ETA 12 min. The hospital taps **READY**. | Hospital view + SSE |
| 5:30 | **Citizen report on a road with no camera.** A phone sends SMS `ACCIDENT RN24 Dellys` (or uses the web form with GPS). An *unverified* incident appears and the operator calls back. | Covers the 90% of roads without cameras |
| 6:00 | **Proof page.** KPI timeline for the incident: detection 3 s after impact, acknowledgement +40 s. Evaluation report on held-out videos: event-level precision, recall, F1, false alarms per camera-hour, and the ablation. Evidence integrity check ✓. | `vision/eval/run_eval.py` output; hash-chain verification |
| 6:40 | **Deployment slide.** Hybrid architecture: wilaya / highway nodes plus the national data centre, CAP interoperability, Law 18-07/25-11 compliance. | Doc 05 §7 |

**Backup**
- A screen recording of a full real run, made during rehearsal.
- If live SMS fails because of venue coverage, Telegram and the PWA continue the flow.

## 2. Risks and limitations

| Risk | Impact | Mitigation |
|---|---|---|
| **Verifier generalisation.** Research clips differ from Algerian CCTV (resolution, angle, vehicle types). | Missed crashes or false alarms in the field | Human verification. Report metrics honestly. Retrain on Algerian footage under a pilot agreement. Rules provide a baseline that does not depend on the domain. |
| **Small or low-quality datasets, possible leakage** | Overstated accuracy | Split by video, keep held-out demo clips, publish the evaluation script, report confidence intervals |
| **Night, rain, glare, small far-away vehicles** | Lower recall | Per-camera zones, minimum object size, camera-health flags; state these limits |
| **Traffic jams and camera motion → false positives** | Alarm fatigue | Normalise against the rest of the traffic, detect global motion, cooldowns, human gate, track false alarms per camera-hour |
| **Laptop performance with 4 streams** | Laggy demo | Benchmark at hour 0; 5 fps sampling; CoreML; drop to 3 cameras if needed |
| **SMS delivery at the venue** | A broken demo step | Test the SIM beforehand; Telegram/PWA fallback; recorded backup |
| **AGPL (Ultralytics)** | Licensing for a government product | Detector interface; RF-DETR / D-FINE (Apache-2.0) or an Enterprise licence for production |
| **Research-only datasets** | Cannot ship as-is | Production retraining on government footage |
| **VLM hallucination** | Misleading descriptions | Advisory only, constrained JSON, "uncertain" allowed, never triggers alerts |
| **Overclaiming government integration** | Loss of credibility with the jury | State plainly: "integration-ready (RTSP/ONVIF, CAP 1.2, SMS), not integrated". No claimed partnerships. |
| **Privacy (Law 18-07/25-11, ANPDP 2026 video rules)** | Legal blocker | Closed-network deployment, clips not continuous recording, retention limits, blur on export, audit log, DPO exports |

**Facts we must not claim** (see doc 02):
- That the East-West Highway incident-detection cameras are operational (unconfirmed).
- Huawei "Safe City" (allegation only).
- "115 = SAMU" or "112" in Algeria (unconfirmed).
- Moroccan emergency statistics.

## 3. Path to government deployment

1. **Pilot proposal (months 0–3).** One wilaya centre, for example **Boumerdès**: it has 387 cameras, the deadly A1 section and a new centre opened in 2026.
   - Partners: the DGSN wilaya centre, the Civil Protection wilaya directorate, the regional Gendarmerie group, one CHU or EPH.
   - Run read-only on RTSP feeds in **shadow mode**: alerts go to an evaluation console, not to dispatch.
2. **Shadow-mode evaluation (months 3–6).**
   - Collect operator labels and measure precision, recall and false alarms per camera-hour on Algerian footage.
   - Retrain the verifier.
   - Measure the time saved compared with the time the first call came in.
3. **Controlled go-live (months 6–12).**
   - Dispatch alerts to Civil Protection with operator confirmation.
   - Offer SMS and CAP integration to the existing operations rooms.
   - Hospital pre-alerts in pilot hospitals.
4. **Scale (year 2+).**
   - Wilaya nodes with GPU servers.
   - Central coordination in the national data centre.
   - East-West Highway control centres, if operational.
   - Link to the Ministry of Health's transfer platform and the electronic medical record (DME).
   - Contribute data to DNSR road-safety analytics.
5. **Governance.**
   - DPO and an impact assessment before go-live (Law 25-11).
   - ANPDP consultation.
   - Cybersecurity unit review (Decree 26-07).
   - Procurement as sovereign software, with source escrow.

**Cost profile (indicative, to be validated).** Software on commodity servers. One GPU server per ~30–60 cameras at a 5 fps analysis rate, depending on the GPU. No new cameras required.
