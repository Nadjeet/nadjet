# PRD — Nadjet (نجاة): AI Road-Incident Detection & Emergency Coordination Platform (Algeria)

| Field | Value |
|---|---|
| Product | **Nadjet** (Arabic: **نجاة**, "survival, being saved"). Final name (D-12). Repo: https://github.com/Nadjeet/nadjet. Domain mapping still open (Q-01) |
| Document status | **DRAFT v0.2, for team review** |
| Owner | Product lead: TBD · Tech lead: TBD |
| Approvers | Whole team (sign-off table in §20) |
| Created / updated | 2026-10-30 |
| Context | SolveX 3.0 hackathon, **Thematic 1: "Road accidents: improving emergency response"** |
| Related docs | `docs/01`–`docs/10` (research, architecture, simulation, deployment). This PRD is the **what and why**. The `docs/` files and the future `plan.md` are the **how**. |

**How to read this document**

- Requirement IDs are stable and are never renumbered:
  - `US-#` user story
  - `FR-<AREA>-###` functional requirement
  - `NFR-<CAT>-###` non-functional requirement
  - `SC-###` success criterion
  - `AC-…` acceptance criterion
  - `Q-##` open question
  - `D-##` decision
  - `R-##` risk
- Priority uses **MoSCoW**: `[M]` Must, `[S]` Should, `[C]` Could, `[W]` Won't (this time). Functional requirements use **EARS** syntax and acceptance criteria use **Given/When/Then**.
- `[NEEDS CLARIFICATION: …]` marks open items. Agents must stop and ask; they must not guess.

---

## 1. Change history

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-10-30 | Team + Claude | First full draft, built from research docs 01–10 |
| 0.2 | 2026-10-30 | Team + Claude | Citizen report raised to Must. Added a one-tap report with an automatic GPS SMS fallback (FR-CIT-006) for roads without cameras (D-11) |

---

## 2. Summary (press-release style)

> **Algiers, [demo day]:** Nadjet (نجاة) turns Algeria's existing road cameras into an early-warning network for crashes.
>
> When a collision happens in front of a monitored camera, Nadjet does the following:
> 1. Detects it in seconds.
> 2. Shows the operator a short verified video clip.
> 3. Recommends the nearest Civil Protection unit and the most suitable hospital, ranked by real road travel time.
> 4. Alerts responders by app and **by SMS, even without mobile data**.
>
> Responders acknowledge by replying to the SMS and send the victims' triage and vital signs from the scene. The hospital is warned before the ambulance leaves.
>
> On roads without cameras, citizens can report a crash with one tap or one SMS.
>
> Everything runs on-premises or in Algeria's national data centre, and uses open international alert standards.

---

## 3. Problem and context

### 3.1 Problem statement (from the thematic)

The first steps after a road crash are often slowed by missing information at the moment of intervention:

- **locating** the crash,
- **assessing severity**,
- **transmitting** information,
- **directing victims** to an appropriate facility.

The thematic asks for faster, more reliable transmission of geolocation, crash information and available vital signs between the scene, response teams and health facilities. The solution should provide a first assessment and decision support, work **alongside existing systems**, and cope with poor connectivity (**low bandwidth or SMS**). Source: SolveX 3.0 problem sheet. The thematic was the organisers' top-scored problem at 85.4/100.

### 3.2 Evidence (Algeria, 2025–2026)

All facts below are sourced in `docs/02-algeria-research.md`.

| Fact | Status |
|---|---|
| 26,976 accidents, **3,838 deaths**, 37,020 injured in 2025 (DNSR); human factor in more than 96% of them | VERIFIED |
| Mass-casualty bus crashes, e.g. Boumerdès on 31 July 2026: 25 dead, 44 injured | VERIFIED |
| Three separate emergency services: **14/1021** Civil Protection, **17/1548** DGSN (national police), **1055** Gendarmerie | VERIFIED |
| National video-surveillance system (Decree 15-228), run by the DGSN with wilaya (province) centres; traffic regulation is a stated purpose | VERIFIED |
| Cameras: **1,837** operational in Algiers (2024); **387** in Boumerdès (centre opened July 2026) | VERIFIED |
| East-West Highway: CCTV and automatic incident detection contracted in 2014 | ANNOUNCED (operation unconfirmed) |
| Computer-aided dispatch, caller geolocation, published response times, hospital-capacity visibility | **NOT FOUND**. This is the gap we address |
| Rural and road mobile-coverage gaps are officially acknowledged; emergency roaming on the A1 highway since May 2025 | VERIFIED |
| Law 18-07 on personal data, amended by Law 25-11 (2025); the data-protection authority's (ANPDP) 2026 video-surveillance rules (no internet connection, restricted access, ≤ 1 year retention) | VERIFIED |

### 3.3 Why now and why us

- **Cameras already exist** and are being added, but they are watched by people.
- **Open-weights vision-language models (VLMs)** became good enough in 2026 to *verify* crash candidates without training. The CVPR 2026 ACCIDENT challenge winners used frozen Qwen3-VL.
- **Sovereign hosting is now possible:** the national data centre was inaugurated in July 2026.

---

## 4. Goals and success metrics

### 4.1 Product goals

- **G1:** Reduce the time between a crash on a monitored road and the dispatch of a verified alert.
- **G2:** Give every agency involved **one shared, verified incident picture**: location, severity, evidence, status.
- **G3:** Direct victims to an **appropriate hospital** and warn it before arrival.
- **G4:** Keep working under **poor connectivity** (SMS path end to end).
- **G5:** Prove credibility to Algerian authorities with **genuine, measurable AI**. No faked results.

### 4.2 Success criteria (hackathon demo)

| ID | Criterion | Target | How measured |
|---|---|---|---|
| SC-001 | Time from crash (impact frame) to incident on the operator screen | **≤ 10 s median** on the held-out demo clips | `event_time` vs `created_at` in the incident timeline |
| SC-002 | Time from operator confirmation to responder SMS received | **≤ 15 s** | Notification log with gateway delivery report |
| SC-003 | End-to-end demo with **zero manual DB edits** and **zero scripted detections** | 2 consecutive clean rehearsals | Rehearsal checklist |
| SC-004 | Event-level recall on the held-out crash clips | **Report it honestly; aim ≥ 0.7** | `eval/run_eval.py` |
| SC-005 | False alarms per camera-hour on held-out normal and congested footage | **Report it honestly; aim ≤ 1** before human verification | `eval/run_eval.py` |
| SC-006 | "Try it yourself" upload processed with a verdict | **≤ 60 s** for a 30 s clip | Job timing in `/system` |
| SC-007 | Live camera wall | 4 cameras, ≥ 5 fps analysed, ≤ 1.5 s glass-to-glass latency on WebRTC | `/system` metrics |
| SC-008 | Responder flow over SMS only (no mobile data) | Acknowledge, triage, close all work | Demo step |

### 4.3 Production success metrics (post-hackathon pilot, informative)

- Median detection-to-dispatch time.
- Share of verified incidents detected before the first phone call.
- Operator false-alarm burden per shift.
- Hospital pre-alert rate.

---

## 5. Non-goals (Won't, this time)

| ID | Non-goal | Why |
|---|---|---|
| NG-01 | Replacing 14 / 17 / 1055 or the existing control rooms | We complement existing systems, as the thematic explicitly asks |
| NG-02 | **Automatic dispatch without a human decision** | Accountability and false-positive risk |
| NG-03 | Licence-plate reading, face recognition, identity tracking, traffic fines | Privacy (Law 18-07/25-11); does not help the emergency response |
| NG-04 | Predicting medical injury severity from video | No credible model exists. We score *incident priority* from observable signals |
| NG-05 | Training or fine-tuning AI models during the hackathon | No time. Pretrained open weights only (D-03) |
| NG-06 | Edge boxes, model marketplaces, uploadable models | Unnecessary complexity. Inference runs on servers |
| NG-07 | Real integration with government systems during the hackathon | No access. We show **integration-ready** interfaces (RTSP/ONVIF in; CAP 1.2, SMS and webhooks out) |
| NG-08 | Native mobile apps | A PWA plus SMS covers the need |
| NG-09 | Wearables or medical sensors | Vital signs are entered by responders |
| NG-10 | Any paid external service or any service that needs a credit card | Hard constraint C-01 |

---

## 6. Users and stakeholders

| Persona | Context | Primary needs | Surface |
|---|---|---|---|
| **P1 Control-room operator** (wilaya video-surveillance centre / Civil Protection operations room) | Watches many feeds; handles calls | Early, trustworthy alerts; fast verification; one-click dispatch; low false alarms | `app.` operator console |
| **P2 Field responder** (Civil Protection, Gendarmerie, SAMU) | Moving, often weak coverage | Location, severity, evidence, route; acknowledge fast; report triage | `respond.` PWA + **SMS** |
| **P3 Hospital emergency department** (CHU/EPH) | Busy; needs a heads-up | Victims incoming, triage, vitals, ETA; Ready/Divert | `hospital.` view + SMS |
| **P4 Citizen / bystander** | At a crash on a road with no camera | Report in seconds with location | `try.`/report page + SMS keyword |
| **P5 Supervisor / road-safety analyst** (DNSR) | Weekly and monthly review | Response-time KPIs, black spots, false-alarm rates | Analytics pages |
| **P6 Auditor / data protection officer (DPO)** | Compliance | Evidence access log, retention, integrity proof | Audit pages |
| **P7 Jury / audience member** (hackathon) | On stage, sceptical | Try it themselves; see it is real | `try.` public page, QR code |

**Institutional stakeholders** (for the pitch, not for integration now):

- DGSN, Gendarmerie and DGPC (Civil Protection)
- Ministry of Health (SAMU, hospitals)
- DNSR
- High Commission for Digitalization
- ANPDP (data protection)
- The wilayas

---

## 7. User stories (prioritized, each independently testable)

| ID | Priority | Story | Independent test |
|---|---|---|---|
| US-1 | P1 [M] | As an **operator**, I want crashes on monitored cameras to appear automatically with a video clip and the reasons for the alert, so that I know within seconds without watching every screen. | Play a held-out crash clip on a simulated camera. An incident card appears with the clip, signals and VLM verdict. |
| US-2 | P1 [M] | As an **operator**, I want to confirm or reject an AI incident, so that only verified incidents trigger dispatch and rejections improve the system. | Confirm moves the incident to *verified*. Reject moves it to *rejected* and stores a label. |
| US-3 | P1 [M] | As an **operator**, I want the system to recommend the nearest suitable unit and hospital by road travel time, so that I dispatch the right resources fast. | Confirming an incident shows a ranked list with ETAs and routes drawn on the map. |
| US-4 | P1 [M] | As a **responder**, I want to receive the alert by push **and SMS**, and to acknowledge it by app or by replying to the SMS, so that dispatch works without mobile data. | An SMS arrives on a real phone. Replying `OK <code>` turns the incident to *acknowledged*. |
| US-5 | P1 [M] | As a **responder**, I want to update the status (en route, on scene, transporting, at hospital, closed), so that everyone sees progress. | Each tap or SMS code updates the timeline on all dashboards in under 2 s. |
| US-6 | P1 [M] | As a **responder**, I want to submit triage and vital signs per victim (or a compact SMS triage), so that the hospital and the dispatch can adapt. | The form or SMS `T <code> R1 Y2 G0` creates casualty records and recomputes priority. |
| US-7 | P1 [M] | As a **hospital**, I want a pre-alert with the number of victims, triage, vitals and ETA, and to answer Ready or Divert, so that we prepare before arrival. | The hospital view shows a pre-alert. READY or DIVERT is reflected on the operator console. |
| US-8 | P1 [M] | As an **operator**, I want a live map and a camera wall showing cameras, incidents, units, hospitals and routes, so that I have one operational picture. | The map shows all entity types live. The camera wall plays 4 streams with AI boxes. |
| US-9 | P1 [M] | As a **citizen**, I want to report a crash on a road without cameras with **one tap**, and have my exact GPS position sent even when I have no mobile data (by an SMS that is filled in automatically), so that crashes on roads without cameras get the same response. | Online: one tap creates an *unverified* incident at the phone's GPS position. Offline: one tap opens the SMS app with `ACCIDENT <lat>,<lon>` already filled in, and sending it creates the incident at those coordinates. In both cases the incident merges with any nearby incident. |
| US-10 | P2 [S] | As a **jury member**, I want to upload my own traffic video or use my phone as a live camera and watch the AI analyse it, so that I can see the system is real. | Uploading a 30 s clip returns an annotated video and a verdict in ≤ 60 s. The phone stream appears on the wall. |
| US-11 | P2 [S] | As a **supervisor**, I want per-incident timelines and response-time KPIs, so that I can measure performance. | The KPI page shows median detection, verification, ack and on-scene times. |
| US-12 | P2 [S] | As an **auditor**, I want to verify that evidence was not altered and see who accessed it, so that evidence is legally defensible. | `/incidents/{id}/verify` returns valid. Tampering with a file returns invalid. Access log entries exist. |
| US-13 | P3 [C] | As an **operator**, I want to be alerted when a camera freezes, goes dark or goes offline, so that I know about coverage gaps. | `camctl freeze cam-x` raises a `camera_fault` within 15 s. |
| US-14 | P3 [C] | As an **operator**, I want wrong-way vehicles, pedestrians on the highway and smoke or fire flagged, so that other dangerous events are covered. | A clip with each event raises the matching incident type. |
| US-15 | P3 [C] | As an **analyst**, I want a black-spot heatmap by road segment and hour, so that prevention can be targeted. | The heatmap renders from incident data. |

---

## 8. Functional requirements

Areas:

- `CAM` cameras and simulation
- `VIS` vision and AI
- `INC` incidents
- `DSP` dispatch and routing
- `NTF` notifications
- `RSP` responder
- `HSP` hospital
- `CIT` citizen and try-it
- `MAP` maps and UI
- `KPI` analytics
- `SEC` security and audit
- `ADM` administration

### 8.1 Cameras and simulation (CAM)

- **FR-CAM-001 [M]** The system shall ingest video from cameras over **RTSP** (H.264/H.265) defined in a camera registry with: id, name, RTSP URL, coordinates, road, kilometre point (PK), heading, wilaya, zones and calibration.
- **FR-CAM-002 [M]** The simulator shall publish each configured **real video file** as a looping RTSP camera via MediaMTX, with no modification of frame content.
- **FR-CAM-003 [M]** The system shall serve each camera, raw and AI-annotated, to browsers over **WebRTC (WHEP)**, with **LL-HLS** as fallback.
- **FR-CAM-004 [S]** The simulator shall support `freeze`, `outage`, `restart` and `swap` commands per camera.
- **FR-CAM-005 [S]** WHEN a camera stream stalls for more than 10 s or disconnects, the system shall raise a `camera_fault` event and show the camera as degraded.
- **FR-CAM-006 [C]** The system shall discover ONVIF Profile S cameras on a configured network segment. *(Production only; demo uses the registry.)*

### 8.2 Vision and AI (VIS)

- **FR-VIS-001 [M]** The vision worker shall decode each camera stream and analyse sampled frames at a configurable rate (default 5 fps).
- **FR-VIS-002 [M]** The vision worker shall detect vehicles (car, bus, truck, motorcycle) and persons using a **pretrained open-weights detector** (default RF-DETR, Apache-2.0).
- **FR-VIS-003 [M]** The vision worker shall track detections across frames and estimate per-track speed in m/s using a per-camera homography.
- **FR-VIS-004 [M]** The vision worker shall evaluate **trigger rules** on tracks:
  - `collision_candidate`: overlap, then both vehicles stopped ≥ 3 s
  - `hard_stop`: sudden deceleration not shared by the other traffic
  - `stalled_vehicle`: stopped ≥ 20 s in a live lane
  - `pedestrian_on_road`: a person ≥ 2 s on the carriageway
  - `rollover_candidate`: abrupt change in box aspect ratio, then stop

  Thresholds are configurable per camera.
- **FR-VIS-005 [M]** WHEN a trigger fires, the vision worker shall extract a clip (≥ 10 s before, ≥ 5 s after) and 8–16 keyframes. It shall submit them to the **VLM verifier** (default Qwen3-VL-8B-Instruct-FP8 via vLLM) with a neutral prompt and a fixed JSON schema that allows `none`.
- **FR-VIS-006 [M]** The vision worker shall publish an `incident.candidate` event containing: trigger signals, track ids, boxes, VLM output, model names and versions, and evidence file hashes.
- **FR-VIS-007 [M]** The incident type shall be `collision` **only if** the rule trigger and the VLM agree. Otherwise the type shall be `possible_incident`, for human decision.
- **FR-VIS-008 [M]** The vision worker shall republish an **annotated stream** (boxes, track ids, speeds, zones) for each camera.
- **FR-VIS-009 [M]** IF the VLM is unavailable or times out (> 15 s), THEN the vision worker shall publish the candidate with `vlm: unavailable` and the rule signals only. It shall never block or drop the candidate.
- **FR-VIS-010 [S]** The vision worker shall suppress repeat triggers for the same location within a configurable cooldown (default 120 s). This handles video loops and lingering scenes.
- **FR-VIS-011 [S]** The vision worker shall suppress triggers during global camera motion (pan, zoom, shake).
- **FR-VIS-012 [C]** WHERE the smoke/fire module is enabled, the vision worker shall add a `smoke_fire` signal from the D-Fire detector. *(Isolated: AGPL code, see D-06.)*
- **FR-VIS-013 [C]** WHERE the second-opinion module is enabled, the vision worker shall also query Cosmos-Reason2-8B and store both verdicts.
- **FR-VIS-014 [M]** The vision workers shall expose metrics: per-camera fps, per-stage latency, queue depth, last frame time.

**AI integrity rules.** These are Must requirements and are checked in CI and review.

- **FR-VIS-020 [M]** The system shall never create incidents, detections or confidence values from hardcoded data, timestamps, file names or random values.
- **FR-VIS-021 [M]** Every AI-derived value shown to users shall show its source: the rule name, or the model name and version.
- **FR-VIS-022 [M]** Demo clips shall come from a declared **held-out list** (`eval/heldout.json`). No threshold tuning shall use them.

### 8.3 Incidents (INC)

- **FR-INC-001 [M]** WHEN a candidate is received, the system shall create an incident with:
  - a short code
  - type and priority
  - location (point, road, PK, wilaya)
  - source (`camera`, `citizen`, `operator`)
  - event time and detection time
  - evidence references
- **FR-INC-002 [M]** WHEN a candidate is within 60 s and 50 m of an open incident, the system shall **merge** it into that incident instead of creating a new one.
- **FR-INC-003 [M]** The system shall compute an explainable **priority (P1–P4)** from observable signals and show its reasons:
  - vehicle count
  - heavy vehicle or bus involved
  - pre-impact speed
  - lane blocked
  - person on the road
  - smoke or fire
  - night or highway
- **FR-INC-004 [M]** WHEN triage data is received, the system shall recompute priority from triage. Triage overrides the AI estimate.
- **FR-INC-005 [M]** The system shall enforce the lifecycle `candidate → verified | rejected | merged → dispatched → acknowledged → en_route → on_scene → transporting → at_hospital → closed`. Every transition is recorded as an append-only event with actor and time.
- **FR-INC-006 [M]** WHEN an operator rejects an incident, the system shall store a reason label: false positive, duplicate, not an emergency or other.
- **FR-INC-007 [M]** Operators shall be able to create an incident manually from a phone call, with a location picked on the map.
- **FR-INC-008 [S]** The system shall flag an incident as **potential mass-casualty** WHEN a bus is involved OR triage reports ≥ 5 victims.
- **FR-INC-009 [S]** The system shall export each incident as **CAP 1.2 XML** (`/incidents/{id}.cap.xml`), valid against the OASIS schema, with Arabic and French info blocks.

### 8.4 Dispatch and routing (DSP)

- **FR-DSP-001 [M]** WHEN an incident is verified, the system shall rank candidate units and hospitals by **road ETA**. It shall prefilter by straight-line distance (PostGIS) and then use OSRM on the Algeria road graph.
- **FR-DSP-002 [M]** Hospital ranking shall consider declared capability (e.g. trauma-capable CHU vs EPH) and current Ready/Divert state, then ETA.
- **FR-DSP-003 [M]** The operator shall dispatch one or more units and one hospital in one action. The system shall store the ETA and route.
- **FR-DSP-004 [S]** The system shall draw the unit-to-scene and scene-to-hospital routes on the map.
- **FR-DSP-005 [C]** The system shall update unit positions from responder PWA GPS when shared.

### 8.5 Notifications (NTF)

- **FR-NTF-001 [M]** WHEN units are dispatched, the system shall notify each assigned responder by **SMS and Web Push**, and optionally by Telegram.
- **FR-NTF-002 [M]** SMS messages shall follow the compact grammar in `contracts/sms-grammar.md` and fit in **≤ 160 GSM-7 characters**, using Latin text. Example: `ACC|P1|36.64800,3.32900|A1 PK42|2V|7F3`.
- **FR-NTF-003 [M]** The system shall send SMS through a **self-operated Android SMS gateway** (capcom6, local or private-server mode). It shall record delivery status.
- **FR-NTF-004 [M]** IF a notification is not delivered within 30 s, THEN the system shall retry up to 3 times with backoff and alert the operator on failure.
- **FR-NTF-005 [M]** The system shall parse inbound SMS:
  - `OK`, `ER`, `OS`, `TR`, `AH`, `CL` followed by `<code>`: status updates
  - `T <code> R# Y# G# B#`: triage
  - `H <code> READY|DIVERT`: hospital response
  - `ACCIDENT <lat>,<lon> [text]`: citizen report placed at those coordinates
  - `ACCIDENT <text>` (no coordinates): citizen report with a free-text location, flagged for operator call-back

  It shall reply with a confirmation or an error.
- **FR-NTF-006 [S]** WHEN a hospital is selected, the system shall send it a pre-alert via its view and SMS.
- **FR-NTF-007 [S]** Notifications shall be idempotent per incident and recipient.

### 8.6 Responder PWA (RSP)

- **FR-RSP-001 [M]** The PWA shall list assigned incidents with location, priority, type, clip/keyframe, AI description and the route deep link.
- **FR-RSP-002 [M]** The PWA shall let responders acknowledge and update status in one tap each.
- **FR-RSP-003 [M]** The PWA shall provide a triage form per victim:
  - START tag (red / yellow / green / black)
  - AVPU consciousness level
  - respiratory rate
  - pulse
  - SpO₂ (optional)
  - bleeding yes/no
  - notes
- **FR-RSP-004 [M]** WHILE offline, the PWA shall queue updates locally and offer **"send via SMS"**, which pre-fills the compact SMS in the phone's SMS app.
- **FR-RSP-005 [S]** The PWA shall be installable (manifest + service worker) and support ar/fr/en with RTL.

### 8.7 Hospital view (HSP)

- **FR-HSP-001 [M]** The hospital view shall show incoming pre-alerts: victims by triage tag, vitals, ETA and the sending unit.
- **FR-HSP-002 [M]** The hospital shall be able to answer READY or DIVERT, by view or SMS. The answer is reflected in dispatch ranking.

### 8.8 Citizen report and "try it yourself" (CIT)

- **FR-CIT-001 [M]** The public report page shall capture GPS location (with a map pick as fallback), an optional photo and an optional phone number. It shall create an *unverified* incident.
- **FR-CIT-006 [M]** The report page shall offer a **one-tap "Report a crash" button** that reads the phone's GPS position.
  - WHEN the phone is online, the tap shall submit the report directly.
  - IF the submission fails or the phone is offline, THEN the page shall open the phone's SMS app (`sms:` link) addressed to the platform's gateway number, with the message `ACCIDENT <lat>,<lon> <optional text>` already filled in. Coordinates use 5 decimals, and the whole message is ≤ 160 GSM-7 characters.
  - The page shall be cached by a service worker after the first visit, so it opens without connectivity. It shall also be reachable by a printed QR code / short link.
- **FR-CIT-002 [S]** The public **try** page shall accept a video upload of at most 60 s and 100 MB. It shall run the **same pipeline** as cameras and stream progress. It shall return the annotated video, the trigger timeline, the VLM verdict and a sandbox incident.
- **FR-CIT-003 [S]** The try page shall let a phone publish its camera via **WHIP** as a temporary live camera. While the session lasts, the camera appears on the wall and is analysed. A VLM check runs at least every 4 s even without triggers.
- **FR-CIT-004 [M]** Public endpoints shall be rate-limited per IP, show a consent notice in ar/fr/en, and store public uploads in an isolated sandbox. Sandbox uploads are deleted after 1 h.
- **FR-CIT-005 [S]** IF the GPU host is unavailable, THEN the try page shall use the **hosted fallback VLM** and display "fallback mode (non-sovereign, demo only)". The fallback may only be used for public sample clips and user uploads made after consent.

### 8.9 Map and operator UI (MAP)

- **FR-MAP-001 [M]** The console shall show an offline vector map of Algeria (self-hosted PMTiles) with cameras, incidents (coloured by priority), units, hospitals and routes. It shall show OSM attribution.
- **FR-MAP-002 [M]** The console shall show an incident queue sorted by priority and time, with live updates (SSE) in under 2 s.
- **FR-MAP-003 [M]** The incident detail view shall show: the clip player, keyframes, trigger signals, VLM output, priority reasons, timeline, dispatch panel and CAP export.
- **FR-MAP-004 [M]** The camera wall shall show at least 4 live streams, with an annotated/raw toggle.
- **FR-MAP-005 [S]** The UI shall support Arabic (RTL), French and English.
- **FR-MAP-006 [S]** A `/system` page shall display pipeline health metrics (FR-VIS-014) and service status.

### 8.10 KPIs and analytics (KPI)

- **FR-KPI-001 [S]** The system shall compute per-incident durations: detection delay, verification time, time to acknowledge, time to scene, time to hospital.
- **FR-KPI-002 [S]** The KPI page shall show medians by period, agency and wilaya, and the false-alarm rate by camera.
- **FR-KPI-003 [S]** An **evaluation page** shall show the latest `eval/run_eval.py` results on held-out clips:
  - precision, recall, F1
  - false alarms per camera-hour
  - ablation: rules / rules+VLM

### 8.11 Security, privacy and audit (SEC)

- **FR-SEC-001 [M]** Users shall authenticate. Access is role-based: `operator`, `supervisor`, `responder:<agency>`, `hospital:<id>`, `auditor`, `admin`.
- **FR-SEC-002 [M]** Responders shall only see incidents assigned to their agency. Hospital users shall only see pre-alerts addressed to them.
- **FR-SEC-003 [M]** The system shall store SHA-256 hashes of every evidence file. It shall chain incident events in a hash chain whose head is signed with Ed25519. It shall expose integrity verification.
- **FR-SEC-004 [M]** The system shall log every evidence view and download, with user, time and IP.
- **FR-SEC-005 [S]** The system shall apply a configurable retention period (default 90 days, maximum 365) and purge expired evidence.
- **FR-SEC-006 [C]** The system shall blur faces and licence plates in exported evidence.
- **FR-SEC-007 [M]** Camera streams shall require authentication. MediaMTX delegates auth to the API.

### 8.12 Administration (ADM)

- **FR-ADM-001 [M]** Admins shall manage cameras (registry, zones, calibration), facilities, units, users and contact numbers via seed files and a minimal admin UI.
- **FR-ADM-002 [S]** A calibration tool shall let an admin click 4 ground points, enter metric distances, and draw zone polygons per camera.

---

## 9. Acceptance criteria (key, Given/When/Then)

- **AC-VIS-005.1:** **Given** camera `cam-a1-pk42` is playing held-out crash clip X, **when** the impact occurs, **then** an `incident.candidate` with a rule trigger and a VLM verdict is published within 10 s (median over 5 runs) and contains no hardcoded values.
- **AC-VIS-007.1:** **Given** the rule fires but the VLM answers `none`, **when** the incident is created, **then** its type is `possible_incident` and both signals are visible.
- **AC-VIS-009.1:** **Given** vLLM is stopped, **when** a trigger fires, **then** the candidate is still created within 5 s with `vlm: unavailable`.
- **AC-INC-002.1:** **Given** an open incident at point P, **when** a second candidate arrives 30 s later at 20 m from P, **then** no new incident is created and the existing one gets a `merged_candidate` event.
- **AC-DSP-001.1:** **Given** a verified incident near Boumerdès, **when** dispatch opens, **then** at least 3 units and 3 hospitals are listed, ranked by OSRM ETA, in under 2 s.
- **AC-NTF-005.1:** **Given** incident code `7F3` is dispatched to phone N, **when** N replies `OK 7F3`, **then** the incident becomes `acknowledged` on all dashboards within 5 s, and N receives a confirmation SMS.
- **AC-NTF-005.2:** **Given** an inbound SMS `T 7F3 R1 Y2 G0`, **when** it is parsed, **then** 3 casualty records are created, priority is recomputed, and the hospital pre-alert updates.
- **AC-RSP-004.1:** **Given** the PWA is offline, **when** the responder submits triage, **then** the update is queued and a pre-filled SMS is offered. **When** connectivity returns, **then** the queue syncs without duplicates.
- **AC-CIT-006.1:** **Given** a phone with data switched off and the report page already cached, **when** the citizen taps "Report a crash", **then** the SMS app opens with `ACCIDENT <lat>,<lon>` filled in. **When** the SMS is sent, **then** an *unverified* incident appears on the operator map at those coordinates within 10 s of the gateway receiving it, and the citizen receives a confirmation SMS.
- **AC-CIT-006.2:** **Given** a phone online, **when** the citizen taps "Report a crash", **then** an *unverified* incident is created at the phone's GPS position within 5 s. No SMS is needed.
- **AC-CIT-002.1:** **Given** a 30 s traffic clip is uploaded, **when** processing completes, **then** the page shows the annotated video, the triggers and the VLM verdict within 60 s, and the upload is deleted after 1 h.
- **AC-SEC-003.1:** **Given** an evidence file is modified on disk, **when** `/incidents/{id}/verify` is called, **then** the result is `invalid` and names the file.
- **AC-SEC-002.1:** **Given** a Gendarmerie responder, **when** they list incidents, **then** incidents assigned only to Civil Protection are not returned.

---

## 10. Edge cases and error handling

| ID | Situation | Required behaviour |
|---|---|---|
| E-01 | Traffic jam (everyone slows down) | No `hard_stop` trigger. Deceleration is normalised against the share of other tracks that slow down too. |
| E-02 | Video loop restarts (simulation) | Tracker resets. The cooldown prevents duplicates. A re-observation is counted, not re-alerted. |
| E-03 | Camera shake or pan | Triggers are suppressed while global motion lasts. |
| E-04 | Track id switch under occlusion | Require N consecutive confirming frames before a stop counts. |
| E-05 | VLM returns invalid JSON | One retry with the same schema, then `vlm: invalid`, then rules only. |
| E-06 | Two cameras see the same crash | Spatial merge (FR-INC-002). |
| E-07 | SMS gateway phone offline | Push and Telegram continue. The operator is warned. Messages are queued for retry. |
| E-08 | Inbound SMS with an unknown code or bad syntax | Reply with a short help message. Log it. Do not change state. |
| E-09 | Responder replies for an incident not assigned to them | Reject the reply and notify the operator. |
| E-10 | Hospital answers DIVERT after dispatch | The operator gets an alert and the next-ranked hospital is proposed. |
| E-11 | GPS unavailable or denied on the citizen report | The user picks a point on the map. If the user is offline, the pre-filled SMS contains only `ACCIDENT` plus any text they typed. The free-text location is shown to the operator, flagged for call-back. |
| E-14 | Same crash reported by several citizens, or by a citizen and a camera | Merge into one incident (FR-INC-002). Show the report count as a confidence signal. |
| E-12 | Public upload is not a video, too long or too large | Reject with a clear error before upload completes, using a client-side check plus a server check. |
| E-13 | GPU host down during demo | VLM switches to the fallback (FR-CIT-005) and the label is shown. The camera pipeline runs in degraded mode on the laptop. |

---

## 11. Non-functional requirements (ISO/IEC 25010:2023 categories)

| ID | Category | Requirement |
|---|---|---|
| NFR-PERF-001 | Performance | 4 simulated cameras analysed at ≥ 5 fps each on one GPU host (L4 or L40S). |
| NFR-PERF-002 | Performance | Incident list and detail API p95 ≤ 300 ms. SSE update ≤ 2 s. |
| NFR-PERF-003 | Performance | VLM verification p95 ≤ 6 s per candidate on an L40S. *(To be measured, Q-05.)* |
| NFR-REL-001 | Reliability | Vision workers reconnect to streams with exponential backoff (1 s to 30 s) and survive the loss of a single camera. |
| NFR-REL-002 | Reliability | Candidates are persisted in Redis Streams with consumer groups. No candidate is lost on an API restart. |
| NFR-REL-003 | Reliability | Fully offline laptop mode (`deploy/local`) is available as a stage fallback. |
| NFR-SEC-001 | Security | TLS on all public endpoints (Let's Encrypt via Traefik). No secrets in git. |
| NFR-SEC-002 | Security | Append-only audit and incident-event tables. The app DB role has no UPDATE or DELETE on them. |
| NFR-SEC-003 | Security | Public endpoints are rate-limited. Upload type and size are validated server-side. |
| NFR-PRIV-001 | Security / Privacy | Data minimisation: event clips only, no continuous recording stored. Retention ≤ 365 days. Production processing records can be exported for the DPO (Law 25-11). |
| NFR-PRIV-002 | Security / Privacy | **No government or real-person footage is ever sent to a hosted third-party AI.** The hosted fallback is restricted to public sample clips and consented uploads. |
| NFR-COMP-001 | Compatibility | Ingest standard RTSP H.264/H.265. Output CAP 1.2 XML. Integrate through HTTP webhooks and SMS. |
| NFR-INT-001 | Interaction | Arabic (RTL), French and English UIs. Responder actions are reachable in ≤ 2 taps. Usable on a 5-inch phone. |
| NFR-INT-002 | Interaction | WCAG 2.2 AA colour contrast. Priority is never encoded by colour only. |
| NFR-MAINT-001 | Maintainability | Contracts-first: the OpenAPI spec and event JSON Schemas are the source of truth, clients are generated, and CI fails on drift. |
| NFR-MAINT-002 | Maintainability | Detector, VLM, SMS provider and storage sit behind interfaces, so they can be swapped without touching business logic. |
| NFR-FLEX-001 | Flexibility | The same container bundles run on a laptop, the VPS + GPU host, or government servers on-premises or in the national data centre. |
| NFR-SAFE-001 | Safety | Human verification is required before dispatch. The AI is labelled as decision support. Uncertain AI output is shown as uncertain. |
| NFR-LIC-001 | Licensing | The core path uses only permissive licences: RF-DETR (Apache-2.0), supervision (MIT), Qwen3-VL (Apache-2.0), vLLM (Apache-2.0), MediaMTX (MIT). AGPL and non-commercial components are optional, isolated, and off by default. |

---

## 12. Key entities (data)

- **Camera:** id, name, rtsp_url, location, road, pk, heading, wilaya, zones, homography, status.
- **Incident:** id, short_code, type, status, priority, priority_reasons, location, road, pk, wilaya, source, camera_id, event_time, detected_at, ai_signals, vlm_result, merged_into.
- **IncidentEvent** (append-only): incident_id, kind, actor, payload, ts, prev_hash, hash.
- **Evidence:** incident_id, kind (clip, keyframe, photo), path, sha256, time range.
- **Facility:** kind (hospital, civil_protection, gendarmerie, police), name, location, wilaya, capabilities, ready_state, contact_sms.
- **Unit:** facility_id, agency, callsign, status, location, phone.
- **Dispatch:** incident_id, unit_id, hospital_id, eta_s, route, status.
- **Casualty:** incident_id, triage_tag, avpu, resp_rate, pulse, spo2, bleeding, notes, reported_by, ts.
- **Notification:** incident_id, channel, recipient, payload, status, attempts, provider_ref.
- **User:** role, agency, facility_id.
- **AuditLog** (append-only).
- **TryJob:** sandbox, status, input, outputs, expires_at.

---

## 13. UX surfaces

| Surface | Domain | Main screens |
|---|---|---|
| Operator console | `app.<domain>` | Map + incident queue · Incident detail (clip, signals, VLM, priority reasons, dispatch) · Camera wall · KPIs · Evaluation · System health · Admin |
| Responder PWA | `respond.<domain>` | My incidents · Incident (route, evidence, status buttons) · Triage form · Offline / SMS fallback |
| Hospital view | `hospital.<domain>` | Incoming pre-alerts · Ready / Divert |
| Public | `try.<domain>` | Try it (upload) · Live (phone as camera) · Report a crash · About / privacy |

The design system is shadcn/ui on Tailwind. Clickable prototype: TBD (Q-08).

---

## 14. Solution overview (summary; details in docs 05, 09 and 10)

- **Repos:**
  - `Nadjeet/nadjet`: monorepo with `contracts/`, `packages/`, `services/{api,vision,camsim}`, `apps/web`, `deploy/`, `eval/`, `docs/`
  - `Nadjeet/.github`: org profile
- **Pipeline:**
  1. RTSP feed.
  2. RF-DETR detection, then ByteTrack tracking, homography speed and zone tests.
  3. Trigger rules.
  4. Qwen3-VL verifier with JSON output.
  5. Candidate published to Redis.
  6. FastAPI processes it and stores it in PostGIS.
  7. SSE updates the console; operator verifies.
  8. OSRM ranks units and hospitals by ETA.
  9. CAP + SMS (Android gateway) + Web Push + Telegram go out.
  10. Responder PWA or SMS sends acknowledgement, triage and the hospital pre-alert.
- **Stage deployment:**
  - **VPS + Dokploy** (Docker Compose mode, Traefik + Let's Encrypt): web, api, worker, PostGIS, Redis, OSRM, MediaMTX. The WebRTC ports are published directly.
  - **NVIDIA Brev GPU** (L40S, or L4 without Cosmos): vLLM and the vision workers, outbound-only connections.
  - **Laptop offline fallback.**
- **Production target:** hybrid.
  - Vision nodes in wilaya and highway control centres, on GPU servers provided by the government.
  - Coordination core in the national data centre.

---

## 15. External services and cost constraint

**C-01 (hard constraint):** apart from assets the team already owns (**NVIDIA Brev account, VPS with Dokploy, domain name**), every external service must be **free and must not require a credit card** at signup or use. All of the following were verified on 2026-10-30; sources are in §23.

| Need | Service | Free / card | Limits and caveats | Status |
|---|---|---|---|---|
| Code, CI, images | **GitHub Free org**, Actions, GHCR | Free · no card | Unlimited standard runners and free GHCR for **public** repos | VERIFIED |
| Model weights | **Hugging Face Hub** (free token) | Free · no card | 5,000 file requests per 5 min with a token. Cosmos-Reason2 is gated (accept the licence; credit "Built on NVIDIA Cosmos") | VERIFIED |
| TLS | **Let's Encrypt** (Traefik in Dokploy) | Free · no card | 50 certs per domain per week. Use the staging server for tests | VERIFIED |
| Responder push | **Web Push (VAPID)** | Free · no account | Keys generated locally. iOS needs the PWA added to the home screen (iOS 16.4+) | VERIFIED |
| Chat alerts | **Telegram Bot API** | Free · no card | About 20 messages/min per group | VERIFIED |
| SMS | **SMS Gateway for Android (capcom6)**, local or private-server mode | Free, open source · no account | **Uses our own SIM: SMS cost is the operator tariff** (see Q-03) | VERIFIED |
| Basemap | **Protomaps daily build → self-hosted PMTiles** | Free · no account | ODbL: show "© OpenStreetMap contributors". Do not use the hosted Tile API (non-commercial) | VERIFIED |
| Routing data | **Geofabrik Algeria extract** (287 MB) → self-hosted OSRM | Free · no account | ODbL attribution | VERIFIED |
| Facility seed | **Overpass API**, one-off export at build time only | Free · no account | Not used at runtime (usage policy) | VERIFIED |
| Uptime monitoring (optional) | **UptimeRobot Free** | Free · "no credit card" | 50 monitors at 5-minute interval | VERIFIED |
| Metrics and logs (optional) | **Grafana Cloud Free** | Free · "no credit card required" | 14-day retention | VERIFIED |
| Hosted VLM fallback (optional) | **Gemini API via Google AI Studio** (free tier) | Free · no card | **Algeria is a supported region.** Free-tier prompts may be used to improve Google products and reviewed by humans, so only public sample clips and consented uploads are allowed (NFR-PRIV-002). Rate limits are only visible in AI Studio | VERIFIED (card, region, terms) |
| Email (optional) | Self-hosted **Mailpit** (dev); **Brevo Free** if needed | Free · "no credit card needed" | 300 emails/day after account approval | VERIFIED |

**Explicitly excluded:**

- **Twilio.** It needs a card. In Algeria it also has no two-way SMS, and Mobilis rejects numeric sender IDs.
- **Hosted map tile APIs.**
- **NVIDIA build.nvidia.com as a critical path.** The terms limit it to trial or prototype use, and the rate limit is unofficial.
- **Paid GPU clouds** other than Brev.
- Sentry, Resend and Better Stack are not needed. Their official pages do not confirm "no card".

---

## 16. Assumptions, dependencies and constraints

**Assumptions**

- **A-01:** Public research CCTV crash videos are acceptable as demo footage. We disclose that they were not filmed in Algeria.
- **A-02:** The jury accepts simulated facilities (capabilities and contacts) on real OSM locations, labelled as simulated.
- **A-03:** A Brev L40S (or L4) is available on demo day. The instance is started hours before the demo and kept running.
- **A-04:** The venue has mobile coverage for the SMS gateway phone and a team 4G/5G hotspot.

**Dependencies**

- MediaMTX, ffmpeg, PyAV, RF-DETR, supervision, vLLM, Qwen3-VL weights, OSRM, PostGIS, Redis, MapLibre, Protomaps, and the capcom6 APK.

**Constraints**

- **C-01:** Free, no-card external services only (§15).
- **C-02:** No model training (D-03).
- **C-03:** Sovereignty in production: on-premises or the national data centre; no foreign cloud for video or personal data.
- **C-04:** Law 18-07/25-11 and the ANPDP rules on video surveillance.
- **C-05:** Hackathon duration and team size. `[NEEDS CLARIFICATION: exact hackathon dates/hours and team size → Q-02]`

---

## 17. Risks

| ID | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R-01 | Zero-shot detection misses crashes or raises false alarms on unfamiliar footage | M / H | Rules + VLM agreement, human gate, honest metrics, curated held-out clips plus congestion clips |
| R-02 | VLM latency too high on the chosen GPU | M / M | Benchmark on day 1. Use the FP8 model, fewer frames and 448 px input. Prefer L40S |
| R-03 | Venue network blocks UDP or is unstable | H / H | Own hotspot, WebRTC TCP fallback on 8189/tcp, HLS fallback, offline laptop mode |
| R-04 | Brev GPU unavailable or fails to restart | L / H | Start early and never stop. Gemini fallback (labelled). Laptop mode |
| R-05 | SMS delivery delays at the venue | M / M | Test the SIM in advance; Push and Telegram in parallel |
| R-06 | Overclaiming government integration or facts | L / H | Use only facts marked VERIFIED in doc 02. Say "integration-ready", never "integrated" |
| R-07 | Licence misuse (AGPL / non-commercial) in a B2G pitch | M / M | Core path is permissive only (NFR-LIC-001). Optional modules are flagged |
| R-08 | Privacy concerns raised by the jury | M / M | Privacy-by-design slide: clips only, retention, audit, no third-party AI on government footage |
| R-09 | Public try page abused | M / L | Rate limits, sandbox, 1 h deletion, size and type checks |

---

## 18. Open questions

| ID | Question | Owner | Due |
|---|---|---|---|
| Q-01 | ~~Product name and GitHub org~~ → **resolved**: Nadjet (نجاة) (D-12); org `Nadjeet`, repo `Nadjeet/nadjet`. Still open: domain/subdomain mapping | Team | Before repo creation |
| Q-02 | Exact hackathon schedule, team size and roles? | Team lead | Now |
| Q-03 | SMS cost: is a prepaid SIM with SMS credit acceptable? It is the only non-zero cost: operator tariff, a few DZD per SMS. | Team | Before P2 |
| Q-04 | GPU tier: L40S (with Cosmos second opinion) or L4 (Qwen only)? Check Brev prices and credits in the console. | Tech lead | Day 1 |
| Q-05 | Measured latency of RF-DETR + Qwen3-VL-8B-FP8 on the chosen GPU (validates NFR-PERF-003). | Vision owner | Day 1 |
| Q-06 | Which held-out clips? Their licences (TAD, UCF-Crime, CADP, AI City 2026 TAR) must allow demo display. | ML owner | Day 1 |
| Q-07 | Use the Gemini fallback at all, or only the laptop offline mode? (Sovereignty narrative vs demo safety.) | Team | P2 |
| Q-08 | Clickable prototype (Figma) before building the UI, or build directly? | Frontend owner | Day 1 |
| Q-09 | Demo setting: A1 Boumerdès plus Algiers, or another wilaya? | Team | Day 1 |
| Q-10 | Responder demo phones: whose phones, and which numbers are seeded? Numbers are deleted after the demo. | Team | Before P2 |

---

## 19. Decision log

| ID | Date | Decision | Rationale | Supersedes |
|---|---|---|---|---|
| D-01 | 2026-10-29 | Reframe from "camera AI" to "incident coordination with camera AI as the flagship sensor" | The thematic covers locate → assess → transmit → orient, plus vital signs and SMS; camera-only covers one step | — |
| D-02 | 2026-10-29 | Human verification before dispatch | Accountability; AI is not reliable enough | — |
| D-03 | 2026-10-30 | No training. Crash verifier = pretrained **Qwen3-VL-8B** (vLLM) on rule candidates | No time; ACCIDENT 2026 winners used frozen Qwen3-VL; Apache-2.0 | Fine-tuned VideoMAE (docs 04/07) |
| D-04 | 2026-10-30 | Detector = **RF-DETR** (Apache-2.0) | Permissive licence for B2G; real-time on GPU | Ultralytics YOLO (AGPL) default |
| D-05 | 2026-10-30 | **One monorepo** `Nadjeet/nadjet` + `Nadjeet/.github` | Atomic contract changes; easier for agents; Dokploy watch paths | Polyrepo |
| D-06 | 2026-10-30 | AGPL and non-commercial models are optional, isolated and off by default | Keep the core path licence-clean | — |
| D-07 | 2026-10-30 | VPS (Dokploy, Compose mode) + Brev GPU (plain compose, outbound only) | Dokploy Traefik only proxies HTTP; Brev tunnels require browser auth | — |
| D-08 | 2026-10-30 | SMS through a self-operated Android gateway | Free, no card, two-way; Twilio needs a card and has no two-way SMS in Algeria | Twilio |
| D-09 | 2026-10-30 | Annotated video re-encoded on the GPU (NVENC) and republished to MediaMTX | Perfect box/video sync on stage; simple browser player | Canvas overlay |
| D-10 | 2026-10-30 | Free, no-card external services only | Team constraint C-01 | — |
| D-12 | 2026-10-30 | Product name: **Nadjet** (Arabic **نجاة**) | Team decision. In Arabic it means survival, being saved, which is the outcome the platform exists for | — |
| D-11 | 2026-10-30 | Citizen report is **Must**. One-tap report with an automatic GPS SMS fallback | Most roads have no cameras. Without this, detection on those roads depends on vague phone calls. A pre-filled `sms:` link gives exact coordinates with no data connection and no extra cost to us | US-9 as Should |

---

## 20. Milestones and launch readiness

| Phase | Exit criterion | Requirements covered |
|---|---|---|
| **P0 Foundation** | Contracts v0 frozen. Repo, CI and Dokploy deploy working. 4 simulated cameras live in the browser. GPU benchmark done (Q-05) | FR-CAM-001..003 |
| **P1 Vertical slice** | Real clip → trigger → VLM → incident on the console with evidence | US-1, FR-VIS-001..009, FR-INC-001..003, FR-MAP-002..003 |
| **P2 Response chain** | Verify → OSRM ranking → SMS + push → SMS ACK → triage → hospital pre-alert, on real phones. One-tap citizen report works online and by GPS SMS | US-2..7, US-9, FR-DSP, FR-NTF, FR-RSP, FR-HSP, FR-CIT-001, FR-CIT-006 |
| **P3 Proof and wow** | Try-it upload and live phone camera, KPIs, evaluation page, integrity verification, CAP export | US-10..12, FR-CIT, FR-KPI, FR-SEC-003 |
| **P4 Polish** | ar/fr/en + RTL, camera health, map polish | US-8, 13 |
| **P5 Freeze** | Tag `demo-v1`. Two clean rehearsals (SC-003). Backup recording. Fallbacks tested | All `[M]` |

**Launch-readiness checklist (demo day)**

- [ ] `demo-v1` deployed on the VPS and the GPU host is warm.
- [ ] `just e2e` passes against production URLs.
- [ ] SMS test is sent and received.
- [ ] WHIP test passes from 2 phones on 4G.
- [ ] Hotspot is charged.
- [ ] Laptop offline mode is tested.
- [ ] The evaluation page shows current results.
- [ ] Every slide fact is marked VERIFIED in doc 02.
- [ ] Attribution is shown: OSM, "Built on NVIDIA Cosmos" (if used), model licences.

**Sign-off**

| Name | Role | Approved (date) |
|---|---|---|
| | Product | |
| | Tech lead | |
| | Vision / AI | |
| | Backend | |
| | Frontend | |

---

## 21. Traceability

Each `[M]` requirement maps to at least one automated test, named with its ID (e.g. `test_FR_NTF_005_parses_triage`), or to a demo-checklist step. CI generates `docs/traceability.md` (ID → test files → status) from test names. PR titles reference requirement IDs.

---

## 22. Glossary

| Term | Meaning |
|---|---|
| AVPU | Consciousness scale: Alert / Voice / Pain / Unresponsive |
| CAP 1.2 | OASIS Common Alerting Protocol (also ITU-T X.1303), an XML standard for emergency alerts |
| CHU / EPH | University hospital / public hospital |
| DGPC / DGSN / DNSR | Civil Protection directorate / national police / national road-safety delegation |
| PK | Point kilométrique: kilometre marker on a road |
| START | Simple Triage And Rapid Treatment (red / yellow / green / black) |
| VLM | Vision-language model |
| WHEP / WHIP | WebRTC HTTP egress / ingest protocols (play / publish) |

---

## 23. References

- Thematic: SolveX 3.0 problem sheet, Thematic 1 (PDF provided by the organisers).
- Research and design: `docs/01-thematic-analysis.md` … `docs/10-live-deployment-and-models.md`. Algerian sources (R1–R65) are in doc 02.
- AI evidence:
  - ACCIDENT@CVPR 2026, 1st place: https://arxiv.org/abs/2605.29325 · https://github.com/fuumin621/cvpr2026-accident-1st-place-solution
  - AI City 2021 Track 4 baseline: https://arxiv.org/abs/2104.06856
  - Qwen3-VL-8B-FP8: https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-FP8
  - Cosmos-Reason2-8B: https://huggingface.co/nvidia/Cosmos-Reason2-8B
  - RF-DETR: https://github.com/roboflow/rf-detr
  - NVIDIA VSS Smart City blueprint: https://docs.nvidia.com/vss/latest/
- Deployment:
  - Dokploy compose, domains and installation: https://docs.dokploy.com/docs/core/docker-compose · https://docs.dokploy.com/docs/core/domains · https://docs.dokploy.com/docs/core/manual-installation
  - Brev: https://docs.nvidia.com/brev/latest/guides/console-reference.md
  - MediaMTX WebRTC: https://mediamtx.org/docs/usage/webrtc-specific-features
- Free services (§15):
  - GitHub Actions: https://docs.github.com/en/billing/concepts/product-billing/github-actions
  - GitHub Packages: https://docs.github.com/en/billing/concepts/product-billing/github-packages
  - Hugging Face rate limits: https://huggingface.co/docs/hub/rate-limits
  - Let's Encrypt rate limits: https://letsencrypt.org/docs/rate-limits/
  - Web Push: https://webkit.org/blog/12945/meet-web-push/
  - Telegram bots: https://core.telegram.org/bots/faq
  - SMS Gateway for Android: https://docs.sms-gate.app/pricing/
  - Protomaps downloads: https://docs.protomaps.com/basemaps/downloads
  - Geofabrik Algeria: https://download.geofabrik.de/africa/algeria.html
  - Overpass API: https://wiki.openstreetmap.org/wiki/Overpass_API
  - UptimeRobot: https://uptimerobot.com/pricing/
  - Grafana Cloud: https://grafana.com/pricing/
  - Gemini available regions: https://ai.google.dev/gemini-api/docs/available-regions
  - Gemini terms: https://ai.google.dev/gemini-api/terms
  - Brevo: https://www.brevo.com/pricing/
- PRD method:
  - Atlassian PRD template: https://www.atlassian.com/software/confluence/templates/product-requirements
  - Product School: https://www.productschool.com/blog/product-strategy/product-template-requirements-document-prd
  - GitHub Spec Kit: https://github.com/github/spec-kit
  - Kiro specs (EARS): https://kiro.dev/docs/specs/
  - EARS: https://alistairmavin.com/ears/
  - Given/When/Then: https://martinfowler.com/bliki/GivenWhenThen.html
  - ISO/IEC 25010:2023: https://www.iso.org/standard/78176.html
  - Amazon PR/FAQ: https://www.workingbackwards.com/concepts/working-backwards-pr-faq-process
  - Claude Code best practices: https://code.claude.com/docs/en/best-practices
