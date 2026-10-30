# PRD — Nadjet (نجاة): AI Road-Incident Detection & Emergency Coordination Platform (Algeria)

| Field | Value |
|---|---|
| Product | **Nadjet** (Arabic: **نجاة**, "survival, being saved"). Final name (D-12). Repo: https://github.com/Nadjeet/nadjet. Domain mapping still open (Q-01) |
| Document status | **DRAFT v0.4, for team review** |
| Owner | Product lead: TBD · Tech lead: TBD |
| Approvers | Whole team (sign-off table in §20) |
| Created / updated | 2026-10-30 |
| Context | SolveX 3.0 hackathon, **Thematic 1: "Road accidents: improving emergency response"** |
| Related docs | This PRD is the **what and why**, and it is technology-neutral (D-13). The **how** (models, frameworks, services, deployment) is in [`docs/11-technical-decisions.md`](docs/11-technical-decisions.md) and supported by `docs/01`–`docs/10`. |

**How to read this document**

- Requirement IDs are stable and are never renumbered:
  - `US-#` user story
  - `FR-<AREA>-###` functional requirement
  - `NFR-<CAT>-###` non-functional requirement
  - `SC-###` success criterion
  - `AC-…` acceptance criterion
  - `Q-##` open question
  - `D-##` product decision
  - `R-##` risk
  - Technical decisions use `TD-##` in doc 11.
- Priority uses **MoSCoW**: `[M]` Must, `[S]` Should, `[C]` Could, `[W]` Won't (this time). Functional requirements use **EARS** syntax and acceptance criteria use **Given/When/Then**.
- `[NEEDS CLARIFICATION: …]` marks open items. Agents must stop and ask; they must not guess.
- **When technology changes, edit doc 11, not this PRD.** Edit the PRD only when the product behaviour, a requirement, a success criterion or a product constraint changes.

---

## 1. Change history

| Version | Date | Author | Change |
|---|---|---|---|
| 0.1 | 2026-10-30 | Team + Claude | First full draft, built from research docs 01–10 |
| 0.2 | 2026-10-30 | Team + Claude | Citizen report raised to Must. Added a one-tap report with an automatic GPS SMS fallback (FR-CIT-006) for roads without cameras (D-11) |
| 0.3 | 2026-10-30 | Team + Claude | PRD made technology-neutral (D-13). Technical choices moved to `docs/11-technical-decisions.md` (TD-01…TD-21). Technical open questions moved there (TQ-01…) |
| 0.4 | 2026-10-30 | Team + Claude | Engineering details moved to doc 11 (§6–§9): AI thresholds and clip sizes, data fields, engineering and traceability rules, reliability timings. The PRD keeps only product-level requirements |

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

The thematic asks for faster, more reliable transmission of geolocation, crash information and available vital signs between the scene, response teams and health facilities. The solution should:

- provide a first assessment and decision support;
- work **alongside existing systems**;
- cope with poor connectivity (**low bandwidth or SMS**).

Source: SolveX 3.0 problem sheet. The organisers scored this thematic highest of all problems: 85.4/100.

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

- **Cameras already exist** and more are being added, but people watch them, not software.
- **Open AI models can now check a crash without being trained on our footage.** In 2026, open-weights vision-language models became good enough for this. The winners of the CVPR 2026 ACCIDENT challenge used one, unmodified.
- **Sovereign hosting is now possible:** the national data centre was inaugurated in July 2026.

---

## 4. Goals and success metrics

### 4.1 Product goals

- **G1:** Reduce the time between a crash on a monitored road and the dispatch of a verified alert.
- **G2:** Give every agency involved **one shared, verified incident picture**: location, severity, evidence, status.
- **G3:** Direct victims to an **appropriate hospital** and warn it before arrival.
- **G4:** Keep working under **poor connectivity**, with an SMS path from end to end.
- **G5:** Prove credibility to Algerian authorities with **genuine, measurable AI**. No faked results.

### 4.2 Success criteria (hackathon demo)

| ID | Criterion | Target | How measured |
|---|---|---|---|
| SC-001 | Time from crash (impact frame) to incident on the operator screen | **≤ 10 s median** on the held-out demo clips | Incident timeline (event time vs creation time) |
| SC-002 | Time from operator confirmation to responder SMS received | **≤ 15 s** | Notification log with delivery report |
| SC-003 | End-to-end demo with **zero manual data edits** and **zero scripted detections** | 2 consecutive clean rehearsals | Rehearsal checklist |
| SC-004 | Event-level recall on the held-out crash clips | **Report it honestly; aim ≥ 0.7** | Evaluation report |
| SC-005 | False alarms per camera-hour on held-out normal and congested footage | **Report it honestly; aim ≤ 1** before human verification | Evaluation report |
| SC-006 | "Try it yourself" upload processed with a verdict | **≤ 60 s** for a 30 s clip | System health page |
| SC-007 | Live camera wall | 4 cameras, ≥ 5 frames/s analysed, ≤ 1.5 s live-video latency in the browser | System health page |
| SC-008 | Responder flow over SMS only (no mobile data) | Acknowledgement, triage and closure all work | Demo step |

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
| NG-05 | Training or fine-tuning AI models during the hackathon | No time. Pretrained open-weights models only (D-03) |
| NG-06 | Edge boxes, model marketplaces, uploadable models | Unnecessary complexity. Inference runs on servers |
| NG-07 | Real integration with government systems during the hackathon | No access. We show **integration-ready** interfaces: standard camera streams in; standard alerts, SMS and webhooks out |
| NG-08 | Native mobile apps | An installable web app plus SMS covers the need |
| NG-09 | Wearables or medical sensors | Vital signs are entered by responders |
| NG-10 | Any paid external service or any service that needs a credit card | Hard constraint C-01 |

---

## 6. Users and stakeholders

| Persona | Context | Primary needs | Surface |
|---|---|---|---|
| **P1 Control-room operator** (wilaya video-surveillance centre / Civil Protection operations room) | Watches many feeds; handles calls | Early, trustworthy alerts; fast verification; one-click dispatch; few false alarms | Operator console |
| **P2 Field responder** (Civil Protection, Gendarmerie, SAMU) | Moving, often weak coverage | Location, severity, evidence, route; fast acknowledgement; triage reporting | Responder phone app + **SMS** |
| **P3 Hospital emergency department** (CHU/EPH) | Busy; needs a heads-up | Victims incoming, triage, vitals, ETA; Ready/Divert | Hospital view + SMS |
| **P4 Citizen / bystander** | At a crash on a road with no camera | Report in seconds with location | Public report page + SMS |
| **P5 Supervisor / road-safety analyst** (DNSR) | Weekly and monthly review | Response-time KPIs, black spots, false-alarm rates | Analytics pages |
| **P6 Auditor / data protection officer (DPO)** | Compliance | Evidence access log, retention, integrity proof | Audit pages |
| **P7 Jury / audience member** (hackathon) | On stage, sceptical | Try it themselves; see that it is real | Public "try it" page, QR code |

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
| US-1 | P1 [M] | As an **operator**, I want crashes on monitored cameras to appear automatically with a video clip and the reasons for the alert, so that I know within seconds without watching every screen. | Play a held-out crash clip on a simulated camera. An incident card appears with the clip, the signals and the AI verdict. |
| US-2 | P1 [M] | As an **operator**, I want to confirm or reject an AI incident, so that only verified incidents trigger dispatch and rejections improve the system. | Confirm moves the incident to *verified*. Reject moves it to *rejected* and stores a label. |
| US-3 | P1 [M] | As an **operator**, I want the system to recommend the nearest suitable unit and hospital by road travel time, so that I dispatch the right resources fast. | Confirming an incident shows a ranked list with ETAs and routes drawn on the map. |
| US-4 | P1 [M] | As a **responder**, I want to receive the alert by push notification **and SMS**, and to acknowledge it in the app or by replying to the SMS, so that dispatch works without mobile data. | An SMS arrives on a real phone. Replying `OK <code>` turns the incident to *acknowledged*. |
| US-5 | P1 [M] | As a **responder**, I want to update the status (en route, on scene, transporting, at hospital, closed), so that everyone sees progress. | Each tap or SMS code updates the timeline on all dashboards in under 2 s. |
| US-6 | P1 [M] | As a **responder**, I want to submit triage and vital signs per victim (or a compact SMS triage), so that the hospital and the dispatcher can adapt. | The form, or SMS `T <code> R1 Y2 G0`, creates casualty records and recomputes priority. |
| US-7 | P1 [M] | As a **hospital**, I want a pre-alert with the number of victims, triage, vitals and ETA, and to answer Ready or Divert, so that we prepare before arrival. | The hospital view shows a pre-alert. READY or DIVERT is reflected on the operator console. |
| US-8 | P1 [M] | As an **operator**, I want a live map and a camera wall showing cameras, incidents, units, hospitals and routes, so that I have one operational picture. | The map shows all entity types live. The camera wall plays 4 streams with AI boxes. |
| US-9 | P1 [M] | As a **citizen**, I want to report a crash on a road without cameras with **one tap**, and have my exact GPS position sent even with no mobile data (by an SMS filled in automatically), so that crashes on those roads get the same response. | Online: one tap creates an *unverified* incident at the phone's GPS position. Offline: one tap opens the SMS app with `ACCIDENT <lat>,<lon>` filled in, and sending it creates the incident at those coordinates. Both cases merge with any nearby incident. |
| US-10 | P2 [S] | As a **jury member**, I want to upload my own traffic video or use my phone as a live camera and watch the AI analyse it, so that I can see the system is real. | Uploading a 30 s clip returns an annotated video and a verdict in ≤ 60 s. The phone stream appears on the wall. |
| US-11 | P2 [S] | As a **supervisor**, I want per-incident timelines and response-time KPIs, so that I can measure performance. | The KPI page shows median detection, verification, acknowledgement and on-scene times. |
| US-12 | P2 [S] | As an **auditor**, I want to verify that evidence was not altered and see who accessed it, so that evidence is legally defensible. | The integrity check returns valid. Tampering with a file makes it return invalid. Access log entries exist. |
| US-13 | P3 [C] | As an **operator**, I want to be alerted when a camera freezes, goes dark or goes offline, so that I know about coverage gaps. | Freezing a simulated camera raises a camera fault within 15 s. |
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

- **FR-CAM-001 [M]** The system shall ingest video from cameras over the standard **RTSP** protocol (H.264/H.265). Cameras are defined in a registry with: id, name, stream URL, coordinates, road, kilometre point (PK), heading, wilaya, zones and calibration.
- **FR-CAM-002 [M]** The simulator shall publish each configured **real video file** as a looping camera stream, without changing any frame content.
- **FR-CAM-003 [M]** The system shall play each camera, raw and AI-annotated, in the browser with low latency (SC-007). A higher-latency fallback is acceptable when the network blocks real-time video.
- **FR-CAM-004 [S]** The simulator shall support `freeze`, `outage`, `restart` and `swap` commands per camera.
- **FR-CAM-005 [S]** WHEN a camera stream stalls for more than 10 s or disconnects, the system shall raise a `camera_fault` event and show the camera as degraded.
- **FR-CAM-006 [C]** The system shall discover ONVIF Profile S cameras on a configured network segment. *(Production only; the demo uses the registry.)*

### 8.2 Vision and AI (VIS)

- **FR-VIS-001 [M]** The vision worker shall decode each camera stream and analyse sampled frames at a configurable rate (default 5 frames/s).
- **FR-VIS-002 [M]** The vision worker shall detect vehicles (car, bus, truck, motorcycle) and persons using a **pretrained open-weights detector with a permissive licence**.
- **FR-VIS-003 [M]** The vision worker shall track detections across frames and estimate each vehicle's speed in m/s using a per-camera ground calibration.
- **FR-VIS-004 [M]** The vision worker shall evaluate **trigger rules** on vehicle and person movements. Thresholds are configurable per camera; default values are in doc 11 §6.

  | Trigger | Situation detected |
  |---|---|
  | `collision_candidate` | Vehicles touch or overlap, then both stay stopped |
  | `hard_stop` | A sudden deceleration not shared by the other traffic |
  | `stalled_vehicle` | A vehicle stopped for a long time in a live lane |
  | `pedestrian_on_road` | A person on the carriageway |
  | `rollover_candidate` | A sudden change in the vehicle's shape, then a stop |
- **FR-VIS-005 [M]** WHEN a trigger fires, the vision worker shall extract a short video clip around the event and a set of keyframes. It shall submit them to a **pretrained vision-language AI verifier**, asked neutrally, which answers in a fixed format and may answer `none`. Clip lengths, frame counts and the answer format are in doc 11 §6.
- **FR-VIS-006 [M]** The vision worker shall publish an incident candidate containing:
  - trigger signals;
  - track ids and boxes;
  - the verifier output;
  - model names and versions;
  - evidence file hashes.
- **FR-VIS-007 [M]** The incident type shall be `collision` **only if** the rule trigger and the AI verifier agree. Otherwise the type shall be `possible_incident`, for human decision.
- **FR-VIS-008 [M]** The vision worker shall produce an **annotated stream** for each camera (boxes, track ids, speeds, zones), kept in sync with the video.
- **FR-VIS-009 [M]** IF the AI verifier is unavailable or too slow (timeout in doc 11 §6), THEN the vision worker shall publish the candidate with `verifier: unavailable` and the rule signals only. It shall never block or drop the candidate.
- **FR-VIS-010 [S]** The vision worker shall suppress repeat triggers at the same location within a configurable cooldown (default in doc 11 §6). This handles video loops and lingering scenes.
- **FR-VIS-011 [S]** The vision worker shall suppress triggers during global camera motion (pan, zoom, shake).
- **FR-VIS-012 [C]** WHERE the smoke/fire module is enabled, the vision worker shall add a `smoke_fire` signal. *(Optional module, licence-isolated: D-06.)*
- **FR-VIS-013 [C]** WHERE the second-opinion module is enabled, the vision worker shall also query a second AI verifier and store both verdicts.
- **FR-VIS-014 [M]** The vision workers shall expose metrics: per-camera frame rate, latency per stage, queue depth, last frame time.

**AI integrity rules.** These are Must requirements, checked in CI and in review.

- **FR-VIS-020 [M]** The system shall never create incidents, detections or confidence values from hardcoded data, timestamps, file names or random values.
- **FR-VIS-021 [M]** Every AI-derived value shown to users shall show its source: the rule name, or the model name and version.
- **FR-VIS-022 [M]** Demo clips shall come from a **held-out list** declared in the repository. No threshold tuning shall use them.

### 8.3 Incidents (INC)

- **FR-INC-001 [M]** WHEN a candidate is received, the system shall create an incident with:
  - a short code;
  - type and priority;
  - location (point, road, PK, wilaya);
  - source (`camera`, `citizen`, `operator`);
  - event time and detection time;
  - evidence references.
- **FR-INC-002 [M]** WHEN a candidate is within 60 s and 50 m of an open incident, the system shall **merge** it into that incident instead of creating a new one.
- **FR-INC-003 [M]** The system shall compute an explainable **priority (P1–P4)** from observable signals and show its reasons:
  - vehicle count;
  - heavy vehicle or bus involved;
  - pre-impact speed;
  - lane blocked;
  - person on the road;
  - smoke or fire;
  - night or highway.
- **FR-INC-004 [M]** WHEN triage data is received, the system shall recompute priority from it. Triage overrides the AI estimate.
- **FR-INC-005 [M]** The system shall enforce this lifecycle:

  `candidate → verified | rejected | merged → dispatched → acknowledged → en_route → on_scene → transporting → at_hospital → closed`

  Every transition is recorded as an append-only event with actor and time.
- **FR-INC-006 [M]** WHEN an operator rejects an incident, the system shall store a reason label: false positive, duplicate, not an emergency, or other.
- **FR-INC-007 [M]** Operators shall be able to create an incident manually from a phone call, with a location picked on the map.
- **FR-INC-008 [S]** The system shall flag an incident as **potential mass-casualty** WHEN a bus is involved OR triage reports ≥ 5 victims.
- **FR-INC-009 [S]** The system shall export each incident in the international **CAP 1.2** alert format (OASIS / ITU-T X.1303), schema-valid, with Arabic and French text.

### 8.4 Dispatch and routing (DSP)

- **FR-DSP-001 [M]** WHEN an incident is verified, the system shall rank candidate units and hospitals by **road ETA**. ETAs are computed on the Algerian road network from OpenStreetMap data, self-hosted with no external routing service.
- **FR-DSP-002 [M]** Hospital ranking shall consider, in this order:
  1. declared capability (e.g. trauma-capable CHU vs EPH);
  2. current Ready/Divert state;
  3. ETA.
- **FR-DSP-003 [M]** The operator shall dispatch one or more units and one hospital in one action. The system shall store the ETA and the route.
- **FR-DSP-004 [S]** The system shall draw the unit-to-scene and scene-to-hospital routes on the map.
- **FR-DSP-005 [C]** The system shall update unit positions from the responder app's GPS when the responder shares it.

### 8.5 Notifications (NTF)

- **FR-NTF-001 [M]** WHEN units are dispatched, the system shall notify each assigned responder by **SMS and push notification**, and optionally by a messaging-app channel.
- **FR-NTF-002 [M]** SMS messages shall:
  - follow one compact, documented message grammar (the codes in FR-NTF-005);
  - fit in **≤ 160 GSM-7 characters**, using Latin text.

  Example: `ACC|P1|36.64800,3.32900|A1 PK42|2V|7F3`.
- **FR-NTF-003 [M]** The system shall send and receive SMS through a **self-operated SMS gateway using the team's own SIM**, with no third-party SMS provider. It shall record delivery status.
- **FR-NTF-004 [M]** IF a notification is not delivered quickly, THEN the system shall retry it automatically and alert the operator if it still fails. Timings are in doc 11 §9.
- **FR-NTF-005 [M]** The system shall parse inbound SMS:

  | Message | Meaning |
  |---|---|
  | `OK`, `ER`, `OS`, `TR`, `AH`, `CL` followed by `<code>` | Status update |
  | `T <code> R# Y# G# B#` | Triage |
  | `H <code> READY` or `H <code> DIVERT` | Hospital response |
  | `ACCIDENT <lat>,<lon> [text]` | Citizen report placed at those coordinates |
  | `ACCIDENT <text>` (no coordinates) | Citizen report with a free-text location, flagged for operator call-back |

  It shall reply with a confirmation or an error.
- **FR-NTF-006 [S]** WHEN a hospital is selected, the system shall send it a pre-alert in its view and by SMS.
- **FR-NTF-007 [S]** Notifications shall not be duplicated per incident and recipient.

### 8.6 Responder app (RSP)

- **FR-RSP-001 [M]** The responder app shall list assigned incidents with location, priority, type, clip or keyframe, AI description, and a navigation link.
- **FR-RSP-002 [M]** The responder app shall let responders acknowledge and update status in one tap each.
- **FR-RSP-003 [M]** The responder app shall provide a triage form per victim:
  - START tag (red / yellow / green / black);
  - AVPU consciousness level;
  - respiratory rate;
  - pulse;
  - SpO₂ (optional);
  - bleeding yes/no;
  - notes.
- **FR-RSP-004 [M]** WHILE offline, the responder app shall queue updates locally and offer **"send via SMS"**, which fills in the compact SMS in the phone's SMS app.
- **FR-RSP-005 [S]** The responder app shall be installable on the phone's home screen and support Arabic (RTL), French and English.

### 8.7 Hospital view (HSP)

- **FR-HSP-001 [M]** The hospital view shall show incoming pre-alerts: victims by triage tag, vitals, ETA and the sending unit.
- **FR-HSP-002 [M]** The hospital shall be able to answer READY or DIVERT, in the view or by SMS. The answer is used in dispatch ranking.

### 8.8 Citizen report and "try it yourself" (CIT)

- **FR-CIT-001 [M]** The public report page shall capture:
  - GPS location, with a map pick as fallback;
  - an optional photo;
  - an optional phone number.

  It shall create an *unverified* incident.
- **FR-CIT-006 [M]** The report page shall offer a **one-tap "Report a crash" button** that reads the phone's GPS position.
  - WHEN the phone is online, the tap shall submit the report directly.
  - IF the submission fails or the phone is offline, THEN the page shall open the phone's SMS app, addressed to the platform's gateway number, with `ACCIDENT <lat>,<lon> <optional text>` filled in. Coordinates use 5 decimals; the message is ≤ 160 GSM-7 characters.
  - The page shall open without connectivity after the first visit.
  - The page shall be reachable from a printed QR code or short link.
- **FR-CIT-002 [S]** The public **try** page shall:
  - accept a video upload of at most 60 s and 100 MB;
  - run the **same pipeline** as the cameras and show progress;
  - return the annotated video, the trigger timeline, the AI verdict and a sandbox incident.
- **FR-CIT-003 [S]** The try page shall let a phone's browser stream its camera as a temporary live camera.
  - While the session lasts, the camera appears on the wall and is analysed.
  - An AI verifier check runs at least every 4 s, even without triggers.
- **FR-CIT-004 [M]** Public endpoints shall:
  - be rate-limited per IP;
  - show a consent notice in Arabic, French and English;
  - store public uploads in an isolated sandbox, deleted after 1 h.
- **FR-CIT-005 [S]** IF the team's AI server is unavailable, THEN the try page shall use a **hosted fallback AI** and display "fallback mode (non-sovereign, demo only)". The fallback may only process public sample clips and user uploads made after consent (NFR-PRIV-002).

### 8.9 Map and operator UI (MAP)

- **FR-MAP-001 [M]** The console shall show an **offline, self-hosted** map of Algeria with cameras, incidents (coloured by priority), units, hospitals and routes. It shall show the "© OpenStreetMap contributors" attribution.
- **FR-MAP-002 [M]** The console shall show an incident queue sorted by priority and time, with live updates in under 2 s.
- **FR-MAP-003 [M]** The incident detail view shall show:
  - clip player and keyframes;
  - trigger signals and AI verdict;
  - priority reasons;
  - timeline;
  - dispatch panel;
  - CAP export.
- **FR-MAP-004 [M]** The camera wall shall show at least 4 live streams, with an annotated/raw toggle.
- **FR-MAP-005 [S]** The UI shall support Arabic (RTL), French and English.
- **FR-MAP-006 [S]** A system health page shall show the pipeline metrics (FR-VIS-014) and the status of each service.

### 8.10 KPIs and analytics (KPI)

- **FR-KPI-001 [S]** The system shall compute per-incident durations: detection delay, verification time, time to acknowledge, time to scene, time to hospital.
- **FR-KPI-002 [S]** The KPI page shall show medians by period, agency and wilaya, and the false-alarm rate by camera.
- **FR-KPI-003 [S]** An **evaluation page** shall show the latest evaluation results on the held-out clips:
  - precision, recall, F1;
  - false alarms per camera-hour;
  - comparison of rules alone vs rules + AI verifier.

### 8.11 Security, privacy and audit (SEC)

- **FR-SEC-001 [M]** Users shall authenticate. Access is role-based:
  - `operator`
  - `supervisor`
  - `responder:<agency>`
  - `hospital:<id>`
  - `auditor`
  - `admin`
- **FR-SEC-002 [M]** Responders shall only see incidents assigned to their agency. Hospital users shall only see pre-alerts addressed to them.
- **FR-SEC-003 [M]** Evidence shall be **tamper-evident**:
  - a cryptographic hash for every evidence file;
  - incident events chained by hash;
  - the chain head digitally signed;
  - an integrity check anyone authorised can run.
- **FR-SEC-004 [M]** The system shall log every evidence view and download, with user, time and IP.
- **FR-SEC-005 [S]** The system shall apply a configurable retention period (default 90 days, maximum 365) and purge expired evidence.
- **FR-SEC-006 [C]** The system shall blur faces and licence plates in exported evidence.
- **FR-SEC-007 [M]** Camera streams shall require authentication, checked against the platform's user roles.

### 8.12 Administration (ADM)

- **FR-ADM-001 [M]** Admins shall manage cameras (registry, zones, calibration), facilities, units, users and contact numbers, using seed files and a minimal admin UI.
- **FR-ADM-002 [S]** A calibration tool shall let an admin, per camera:
  1. click 4 ground points;
  2. enter their real-world distances;
  3. draw the zone polygons.

---

## 9. Acceptance criteria (key, Given/When/Then)

- **AC-VIS-005.1:** **Given** camera `cam-a1-pk42` is playing held-out crash clip X, **when** the impact occurs, **then** an incident candidate with a rule trigger and an AI verdict is published within 10 s (median over 5 runs) and contains no hardcoded values.
- **AC-VIS-007.1:** **Given** the rule fires but the AI verifier answers `none`, **when** the incident is created, **then** its type is `possible_incident` and both signals are visible.
- **AC-VIS-009.1:** **Given** the AI verifier is stopped, **when** a trigger fires, **then** the candidate is still created within 5 s with `verifier: unavailable`.
- **AC-INC-002.1:** **Given** an open incident at point P, **when** a second candidate arrives 30 s later 20 m from P, **then** no new incident is created and the existing one records a merged candidate.
- **AC-DSP-001.1:** **Given** a verified incident near Boumerdès, **when** dispatch opens, **then** at least 3 units and 3 hospitals are listed, ranked by road ETA, in under 2 s.
- **AC-NTF-005.1:** **Given** incident code `7F3` is dispatched to phone N, **when** N replies `OK 7F3`, **then**:
  - the incident becomes `acknowledged` on all dashboards within 5 s;
  - N receives a confirmation SMS.
- **AC-NTF-005.2:** **Given** an inbound SMS `T 7F3 R1 Y2 G0`, **when** it is parsed, **then**:
  - 3 casualty records are created;
  - priority is recomputed;
  - the hospital pre-alert updates.
- **AC-RSP-004.1:** **Given** the responder app is offline, **when** the responder submits triage, **then** the update is queued and a filled-in SMS is offered. **When** connectivity returns, **then** the queue syncs without duplicates.
- **AC-CIT-006.1:** **Given** a phone with data switched off and the report page opened before, **when** the citizen taps "Report a crash", **then** the SMS app opens with `ACCIDENT <lat>,<lon>` filled in. **When** the SMS is sent, **then**:
  - an *unverified* incident appears on the operator map at those coordinates within 10 s of the gateway receiving it;
  - the citizen receives a confirmation SMS.
- **AC-CIT-006.2:** **Given** a phone online, **when** the citizen taps "Report a crash", **then** an *unverified* incident is created at the phone's GPS position within 5 s, with no SMS needed.
- **AC-CIT-002.1:** **Given** a 30 s traffic clip is uploaded, **when** processing completes, **then**:
  - the page shows the annotated video, the triggers and the AI verdict within 60 s;
  - the upload is deleted after 1 h.
- **AC-SEC-003.1:** **Given** an evidence file is modified on disk, **when** the integrity check runs, **then** the result is `invalid` and names the file.
- **AC-SEC-002.1:** **Given** a Gendarmerie responder, **when** they list incidents, **then** incidents assigned only to Civil Protection are not returned.

---

## 10. Edge cases and error handling

| ID | Situation | Required behaviour |
|---|---|---|
| E-01 | Traffic jam (everyone slows down) | No `hard_stop` trigger. Deceleration is compared against the share of other vehicles slowing down too. |
| E-02 | Video loop restarts (simulation) | Tracking resets. The cooldown prevents duplicates. A re-observation is counted, not re-alerted. |
| E-03 | Camera shake or pan | Triggers are suppressed while global motion lasts. |
| E-04 | Vehicle identity switch when hidden behind another vehicle | Require several consecutive confirming frames before a stop counts. |
| E-05 | AI verifier returns invalid output | One retry with the same schema. If still invalid: `verifier: invalid`, rules only. |
| E-06 | Two cameras see the same crash | Spatial merge (FR-INC-002). |
| E-07 | SMS gateway offline | Push and the messaging channel continue. The operator is warned. Messages are queued for retry. |
| E-08 | Inbound SMS with an unknown code or bad syntax | Reply with a short help message. Log it. Do not change state. |
| E-09 | Responder replies for an incident not assigned to them | Reject the reply and notify the operator. |
| E-10 | Hospital answers DIVERT after dispatch | Alert the operator and propose the next-ranked hospital. |
| E-11 | GPS unavailable or denied on the citizen report | The user picks a point on the map. If offline, the filled-in SMS contains only `ACCIDENT` plus any text typed. The free-text location is shown to the operator, flagged for call-back. |
| E-12 | Public upload is not a video, too long or too large | Reject with a clear error before the upload completes (checked on the phone and on the server). |
| E-13 | AI server down during the demo | Switch to the fallback (FR-CIT-005) and show its label. The camera pipeline runs in degraded mode on the laptop. |
| E-14 | Same crash reported by several citizens, or by a citizen and a camera | Merge into one incident (FR-INC-002). Show the report count as a confidence signal. |

---

## 11. Non-functional requirements (ISO/IEC 25010:2023 categories)

| ID | Category | Requirement |
|---|---|---|
| NFR-PERF-001 | Performance | 4 simulated cameras analysed at ≥ 5 frames/s each on **one GPU server**. |
| NFR-PERF-002 | Performance | Incident list and detail responses p95 ≤ 300 ms. Live UI updates ≤ 2 s. |
| NFR-PERF-003 | Performance | AI verification p95 ≤ 6 s per candidate. *(To be measured, doc 11 TQ-02.)* |
| NFR-REL-001 | Reliability | Cameras reconnect automatically after an interruption. Losing one camera never stops the others. |
| NFR-REL-002 | Reliability | No incident candidate is ever lost, even if the backend restarts. |
| NFR-REL-003 | Reliability | A fully offline laptop mode is available as a stage fallback. |
| NFR-SEC-001 | Security | HTTPS on all public endpoints. No secrets in the repository. |
| NFR-SEC-002 | Security | Audit and incident-event records are append-only. The application cannot modify or delete them. |
| NFR-SEC-003 | Security | Public endpoints are rate-limited. Upload type and size are validated server-side. |
| NFR-PRIV-001 | Security / Privacy | Data minimisation: event clips only, no continuous recording stored. Retention ≤ 365 days. Records of processing can be exported for the DPO in production (Law 25-11). |
| NFR-PRIV-002 | Security / Privacy | **No government or real-person footage is ever sent to a hosted third-party AI.** The hosted fallback only processes public sample clips and consented uploads. |
| NFR-COMP-001 | Compatibility | Ingest standard camera streams (RTSP, H.264/H.265; ONVIF in production). Output CAP 1.2 alerts. Integrate through HTTP webhooks and SMS. |
| NFR-INT-001 | Interaction | UIs in Arabic (RTL), French and English. Responder actions reachable in ≤ 2 taps. Usable on a 5-inch phone. |
| NFR-INT-002 | Interaction | WCAG 2.2 AA colour contrast. Priority is never shown by colour alone. |
| NFR-MAINT-001 | Maintainability | Every Must requirement is covered by an automated test or a demo-checklist step (§21). |
| NFR-MAINT-002 | Maintainability | The detector, the AI verifier, the SMS provider and storage can each be replaced without changing product behaviour. The engineering approach is in doc 11 §8. |
| NFR-FLEX-001 | Flexibility | The same deployment bundles run on a laptop, on the hackathon servers, or on government servers (on-premises or national data centre). |
| NFR-SAFE-001 | Safety | Human verification is required before dispatch. The AI is labelled as decision support. Uncertain AI output is shown as uncertain. |
| NFR-LIC-001 | Licensing | The core path uses only permissively licensed software and models (list in doc 11 §3). Copyleft (AGPL) and non-commercial components are optional, isolated and off by default. |

---

## 12. Key entities (data)

What the system keeps track of. Exact fields are in doc 11 §7.

| Entity | What it represents |
|---|---|
| **Camera** | A road camera: where it is (road, kilometre point, wilaya, direction), its watched zones, its calibration and its health |
| **Incident** | One crash or event: type, priority and its reasons, location, source (camera, citizen, operator), times, AI signals and verdict, status |
| **Incident event** | Every change in an incident's life (who, what, when). It can never be edited or deleted, and it is tamper-evident |
| **Evidence** | Video clips, keyframes and photos attached to an incident, each with an integrity fingerprint |
| **Facility** | A hospital, Civil Protection station, Gendarmerie or police post: location, capabilities, Ready/Divert state, SMS contact |
| **Unit** | A rescue or patrol team: agency, call sign, status, position, phone |
| **Dispatch** | Which units and which hospital were sent to an incident, with ETA and route |
| **Casualty** | One victim's triage: colour tag, consciousness, breathing, pulse, oxygen, bleeding, notes |
| **Notification** | Every alert sent (SMS, push, messaging) and whether it was delivered |
| **User** | A person with a role, an agency and, for hospital users, a facility |
| **Audit log** | Who viewed or downloaded what, and when. Append-only |
| **Try job** | A public "try it" upload or live session, isolated and deleted after 1 h |

---

## 13. UX surfaces

| Surface | Users | Main screens |
|---|---|---|
| Operator console | P1, P5, P6 | Map + incident queue · Incident detail (clip, signals, AI verdict, priority reasons, dispatch) · Camera wall · KPIs · Evaluation · System health · Admin |
| Responder app | P2 | My incidents · Incident (route, evidence, status buttons) · Triage form · Offline / SMS fallback |
| Hospital view | P3 | Incoming pre-alerts · Ready / Divert |
| Public pages | P4, P7 | Report a crash (one tap) · Try it (upload) · Live (phone as camera) · About / privacy |

Each surface gets its own subdomain (mapping open: Q-01). Clickable prototype: TBD (Q-08).

---

## 14. Solution concept (non-technical summary)

1. **Detect.** AI watches camera feeds and spots suspicious vehicle behaviour. A second AI check looks at the short clip. Citizens and phone calls cover everything the cameras miss.
2. **Verify.** A human operator confirms or rejects. The AI never dispatches on its own.
3. **Decide.** The system recommends the nearest suitable unit and hospital by real driving time, with an explained priority.
4. **Alert.** Responders get a push notification and an SMS. The hospital gets a pre-alert.
5. **Respond.** Responders acknowledge, update status and send triage, by app or by SMS.
6. **Measure.** Every step is timed and every piece of evidence is tamper-evident.

**Deployment principle:**

- For the hackathon: our own servers and a rented GPU.
- In production: hybrid. AI video nodes run in the wilaya and highway control centres, on government-provided servers. The coordination core runs in the national data centre.

**How each step is built** (models, frameworks, services, deployment): doc 11.

---

## 15. External services and cost constraint

**C-01 (hard constraint):** apart from assets the team already owns (**an NVIDIA Brev account, a VPS with Dokploy, a domain name**), every external service must be **free and must not require a credit card** at signup or use.

Rules that follow from C-01:

- Prefer **self-hosted open-source** components over hosted services.
- The **only accepted running cost** is SMS sent from the team's own SIM, at the operator's tariff (Q-03).
- Any service whose signup asks for a card is excluded, even if it has a free tier.
- The list of services in use, with their free-tier limits and sources, is maintained in **doc 11 §2**.

---

## 16. Assumptions, dependencies and constraints

**Assumptions**

- **A-01:** Public research CCTV crash videos are acceptable as demo footage. We disclose that they were not filmed in Algeria.
- **A-02:** The jury accepts simulated facilities (capabilities and contacts) on real OpenStreetMap locations, labelled as simulated.
- **A-03:** A GPU server is available on demo day. It is started hours before the demo and kept running.
- **A-04:** The venue has mobile coverage for the SMS gateway phone, and the team has its own 4G/5G hotspot.

**Dependencies**

- Open-source software and open-weights models, listed with their licences in doc 11 §3.
- OpenStreetMap data for the map, routing and facility locations.

**Constraints**

- **C-01:** Free, no-card external services only (§15).
- **C-02:** No model training (D-03).
- **C-03:** Sovereignty in production: on-premises or the national data centre; no foreign cloud for video or personal data.
- **C-04:** Law 18-07/25-11 and the ANPDP video-surveillance rules.
- **C-05:** Hackathon duration and team size. `[NEEDS CLARIFICATION: exact hackathon dates/hours and team size → Q-02]`

---

## 17. Risks

| ID | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R-01 | AI misses crashes or raises false alarms on unfamiliar footage | M / H | Rules and AI verifier must agree; human gate; honest metrics; curated held-out clips, including congestion clips |
| R-02 | AI verification too slow | M / M | Benchmark on day 1 (doc 11 TQ-02); fewer frames, smaller inputs; stronger GPU tier |
| R-03 | Venue network blocks real-time video or is unstable | H / H | Own hotspot; network fallback modes; offline laptop mode |
| R-04 | GPU server unavailable or fails to restart | L / H | Start early and never stop it; labelled hosted fallback; laptop mode |
| R-05 | SMS delivery delays at the venue | M / M | Test the SIM in advance; push and messaging channel in parallel |
| R-06 | Overclaiming government integration or facts | L / H | Use only facts marked VERIFIED in doc 02. Say "integration-ready", never "integrated" |
| R-07 | Licence problems (copyleft / non-commercial) in a government pitch | M / M | Core path is permissive only (NFR-LIC-001); optional modules flagged |
| R-08 | Privacy concerns raised by the jury | M / M | Privacy-by-design slide: clips only, retention limits, audit, no third-party AI on government footage |
| R-09 | Public try page abused | M / L | Rate limits, sandbox, deletion after 1 h, size and type checks |

---

## 18. Open questions

Technical questions (GPU tier, measured latency, gateway details, image versions) are in doc 11 §4.

| ID | Question | Owner | Due |
|---|---|---|---|
| Q-01 | ~~Product name and GitHub org~~ → **resolved**: Nadjet (نجاة) (D-12); org `Nadjeet`, repo `Nadjeet/nadjet`. Still open: domain and subdomain mapping | Team | Before deployment |
| Q-02 | Exact hackathon schedule, team size and roles? | Team lead | Now |
| Q-03 | SMS cost: is a prepaid SIM with SMS credit acceptable? It is the only running cost: operator tariff, a few DZD per SMS. | Team | Before P2 |
| Q-04 | *Moved to doc 11 (TQ-01).* | — | — |
| Q-05 | *Moved to doc 11 (TQ-02).* | — | — |
| Q-06 | Which held-out clips? Their licences must allow showing them in the demo. | AI owner | Day 1 |
| Q-07 | Keep the hosted AI fallback at all, or rely only on the laptop offline mode? (Sovereignty story vs demo safety.) | Team | P2 |
| Q-08 | Clickable prototype before building the UI, or build directly? | Designer + frontend owner | Day 1 |
| Q-09 | Demo setting: A1 Boumerdès plus Algiers, or another wilaya? | Team | Day 1 |
| Q-10 | Responder demo phones: whose phones, and which numbers are seeded? Numbers are deleted after the demo. | Team | Before P2 |

---

## 19. Decision log (product decisions)

Technical decisions (models, frameworks, services, repository, deployment, SMS gateway, video handling) are recorded in **doc 11** as `TD-##`. Former product-log entries D-04, D-05, D-07, D-08 and D-09 now live there as TD-02, TD-05, TD-17/18, TD-13 and TD-07.

| ID | Date | Decision | Rationale |
|---|---|---|---|
| D-01 | 2026-10-29 | Reframe from "camera AI" to "incident coordination with camera AI as the flagship sensor" | The thematic covers locate → assess → transmit → orient, plus vital signs and SMS. Camera-only covers one step |
| D-02 | 2026-10-29 | Human verification before dispatch | Accountability; AI is not reliable enough on its own |
| D-03 | 2026-10-30 | No training: pretrained open-weights models only; an AI verifier checks rule-based candidates | No time; evidence that frozen open models work (CVPR 2026 ACCIDENT challenge) |
| D-06 | 2026-10-30 | Copyleft and non-commercial components are optional, isolated and off by default | Keep the product licence-clean for government use |
| D-10 | 2026-10-30 | Free, no-card external services only | Team constraint C-01 |
| D-11 | 2026-10-30 | Citizen report is **Must**, with one-tap reporting and an automatic GPS SMS fallback | Most roads have no cameras. A filled-in SMS gives exact coordinates with no data and no extra cost |
| D-12 | 2026-10-30 | Product name: **Nadjet** (Arabic **نجاة**) | In Arabic it means survival, being saved: the outcome the platform exists for |
| D-13 | 2026-10-30 | The PRD stays technology-neutral; technical choices live in doc 11 | Technology can change without reopening product requirements; the PRD stays readable for the whole team |

---

## 20. Milestones and launch readiness

| Phase | Exit criterion | Requirements covered |
|---|---|---|
| **P0 Foundation** | Shared message formats agreed. Repo and server deployment working. 4 simulated cameras live in the browser. GPU benchmark done (TQ-02) | FR-CAM-001..003 |
| **P1 Vertical slice** | Real clip → trigger → AI verifier → incident on the console with evidence | US-1, FR-VIS-001..009, FR-INC-001..003, FR-MAP-002..003 |
| **P2 Response chain** | Verify → ETA ranking → SMS + push → SMS acknowledgement → triage → hospital pre-alert, on real phones. One-tap citizen report works online and by GPS SMS | US-2..7, US-9, FR-DSP, FR-NTF, FR-RSP, FR-HSP, FR-CIT-001, FR-CIT-006 |
| **P3 Proof and wow** | Try-it upload and live phone camera, KPIs, evaluation page, integrity check, CAP export | US-10..12, FR-CIT, FR-KPI, FR-SEC-003 |
| **P4 Polish** | Arabic/French/English + RTL, camera health, map polish | US-8, US-13 |
| **P5 Freeze** | Release tag `demo-v1`. Two clean rehearsals (SC-003). Backup recording. Fallbacks tested | All `[M]` |

**Launch-readiness checklist (demo day)**

- [ ] `demo-v1` deployed and the GPU server warm.
- [ ] End-to-end test passes against the live URLs.
- [ ] SMS test sent and received.
- [ ] Phone-as-camera tested from 2 phones on 4G.
- [ ] Hotspot charged.
- [ ] Laptop offline mode tested.
- [ ] Evaluation page shows current results.
- [ ] Every slide fact is marked VERIFIED in doc 02.
- [ ] Attributions shown: OpenStreetMap, model licences.

**Sign-off**

| Name | Role | Approved (date) |
|---|---|---|
| | Product | |
| | Tech lead | |
| | Vision / AI | |
| | Backend | |
| | Frontend | |
| | Design | |
| | Film / pitch | |

---

## 21. Traceability

Each `[M]` requirement is covered by at least one automated test or one step in the demo checklist, and its status is visible to the whole team. How tests are linked to requirement IDs is in doc 11 §8.

---

## 22. Glossary

| Term | Meaning |
|---|---|
| AVPU | Consciousness scale: Alert / Voice / Pain / Unresponsive |
| CAP 1.2 | Common Alerting Protocol (OASIS, ITU-T X.1303): international standard format for emergency alerts |
| CHU / EPH | University hospital / public hospital |
| DGPC / DGSN / DNSR | Civil Protection directorate / national police / national road-safety delegation |
| ETA | Estimated time of arrival |
| PK | Point kilométrique: kilometre marker on a road |
| RTSP / ONVIF | Standard protocols used by IP security cameras |
| START | Simple Triage And Rapid Treatment (red / yellow / green / black) |
| Vision-language model (VLM) | An AI that looks at images or video and answers questions about them in text |

---

## 23. References

- **Thematic:** SolveX 3.0 problem sheet, Thematic 1 (PDF provided by the organisers).
- **Research and design:**
  - `docs/01`–`docs/10`. The Algerian sources (R1–R65) are in doc 02.
  - Technical decisions and service sources: doc 11.
- **AI feasibility evidence:**
  - ACCIDENT@CVPR 2026 1st place: https://arxiv.org/abs/2605.29325
  - AI City 2021 Track 4 baseline: https://arxiv.org/abs/2104.06856
- **PRD method:**
  - Atlassian PRD template: https://www.atlassian.com/software/confluence/templates/product-requirements
  - Product School: https://www.productschool.com/blog/product-strategy/product-template-requirements-document-prd
  - GitHub Spec Kit: https://github.com/github/spec-kit
  - Kiro specs (EARS): https://kiro.dev/docs/specs/
  - EARS: https://alistairmavin.com/ears/
  - Given/When/Then: https://martinfowler.com/bliki/GivenWhenThen.html
  - ISO/IEC 25010:2023: https://www.iso.org/standard/78176.html
  - Amazon PR/FAQ: https://www.workingbackwards.com/concepts/working-backwards-pr-faq-process
  - Claude Code best practices: https://code.claude.com/docs/en/best-practices
