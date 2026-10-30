# 03 — Product Vision, Value Proposition and Prioritized Features

> Product name: **Nadjet** (Arabic **نجاة**, "survival, being saved"). The product has its own identity and architecture.

## 1. Vision

**Detect road crashes in seconds, put one verified picture of the incident in front of every agency, and get the right unit and the right hospital moving, even over SMS.**

## 2. Users

| User | Where | Need |
|---|---|---|
| **Control-room operator** (wilaya or DGSN video-surveillance centre, Civil Protection operations room) | Desktop dashboard | See AI-detected incidents early, verify them fast, dispatch the right unit, and avoid alarm fatigue. |
| **Responder** (Civil Protection unit, Gendarmerie patrol, SAMU crew) | Smartphone PWA + SMS | Receive location, severity and evidence; acknowledge; navigate; report triage and vitals; update status. |
| **Receiving hospital** (emergency department of a university hospital (CHU) or public hospital (EPH)) | Web view / SMS | Be warned before the patients arrive: number of victims, triage category, vitals, ETA. |
| **Citizen / bystander** | Web form / SMS | Report a crash on a road without cameras, with GPS. |
| **Supervisor / DNSR analyst** | Analytics pages | See response-time KPIs, black spots and false-alarm rates. |
| **Auditor / DPO** | Audit views | Check who accessed evidence, retention and data-protection compliance (Law 18-07 / 25-11). |

## 3. Value proposition

**For authorities**

- Earlier awareness of crashes on monitored roads. The alert does not wait for a phone call.
- One shared incident record across Civil Protection, DGSN, Gendarmerie and SAMU.
- Measurable response times. Today no public response-time statistics exist (see doc 02).
- Uses cameras that are **already deployed**: Algiers (1,837+), Boumerdès (387), and the planned East-West Highway CCTV.

**For victims**

- Faster dispatch.
- The right hospital is chosen from the start.
- The hospital is ready when they arrive.

**For the state**

- Sovereign deployment, on-premises or in the national data centre.
- Standard alert format (CAP 1.2).
- Privacy by design.

## 4. Feature tiers

**Legend.** Feasibility = what an agent-assisted team can deliver for the hackathon:

- **H**: high confidence.
- **M**: doable but needs tuning.
- **L**: stretch.

### Tier 1 — Essential (the demo fails without these)

| # | Feature | What it does | How it works | Requirements | Feas. |
|---|---|---|---|---|---|
| E1 | **Virtual camera network** | Several road cameras streaming real video in a loop. | MediaMTX plus ffmpeg `-stream_loop -1 -re -c copy` per camera, configured from `cameras.yaml` (with coordinates, road, kilometre point and heading). | ffmpeg, MediaMTX | H |
| E2 | **Live camera wall** | The browser shows live streams with an AI overlay. | WebRTC (WHEP) from MediaMTX into a `<video>` element, with detection boxes drawn on a `<canvas>` from a WebSocket feed. | MediaMTX WebRTC, canvas | H |
| E3 | **Real-time vision pipeline** | Detect and track vehicles and people on every camera. | Per-camera worker: decode at 5 fps, then a COCO detector (RF-DETR), then ByteTrack, then speed relative to vehicle size. | GPU (Brev L40S) | H |
| E4 | **Incident triggers** | Turn track behaviour into candidate incidents. | Rules on tracks: two vehicles overlap and then both stop; sudden deceleration that other vehicles do not share; a vehicle stationary in a live lane longer than T seconds; a pedestrian on the carriageway. | supervision zones | H |
| E5 | **AI verifier + AI sweep** | Confirm a candidate is a collision, and catch crashes the rules miss. | A pretrained vision-language model (no training) checks a short clip on each trigger, and checks every camera every few seconds on its own. Graded statuses; a human decides. | 1 GPU (Brev L40S) | M |
| E6 | **Incident record + evidence** | A persistent incident with location, time, type, confidence and evidence. | The worker keeps a ring buffer of encoded packets and writes a 15 s pre-event + 10 s post-event MP4 plus keyframes. A SHA-256 is stored with each file. | PyAV, PostGIS | H |
| E7 | **Operator verification** | A human confirms or rejects the incident before dispatch. | Incident card with clip, keyframes, AI signals and a map. Actions: Confirm / False positive / Duplicate. Rejections are stored as labels. | — | H |
| E8 | **Multi-channel alerting** | Notify the right agencies. | Notifier fans out to web push/SSE, Telegram, and **SMS through an Android SMS gateway**. The canonical alert is a CAP 1.2 XML document. | capcom6 SMS Gateway, Telegram Bot API | H |
| E9 | **Responder interface** | Responders receive, acknowledge and update status. | Mobile PWA with statuses: alerted → acknowledged → en route → on scene → transporting → at hospital → closed. Responders can also reply by SMS (`OK 7F3`). | PWA, inbound SMS webhook | H |
| E10 | **Incident map dashboard** | One shared operational picture. | MapLibre with offline Algeria PMTiles. Shows cameras, incidents, units, hospitals and routes. Arabic and French labels. | MapLibre, Protomaps | H |

### Tier 2 — High-value differentiators (these win the jury)

| # | Feature | What it does | How it works | Feas. |
|---|---|---|---|---|
| D1 | **Nearest-capable unit and hospital recommendation** | Answers "who should go, and where should the victims go". | Facilities from OSM (`amenity=hospital`, `fire_station`, `police`) plus a seeded capability CSV (e.g. CHU = trauma level). A PostGIS KNN search prefilters candidates, then OSRM `/table` ranks them by road ETA. The route is drawn on the map. | H |
| D2 | **Severity and priority score (explainable)** | A first assessment, with its reasons. | Transparent score built from observable signals: number of vehicles, involvement of a heavy vehicle or bus, overturned or stopped in a live lane, people on the road, estimated speed before impact, smoke or fire, time of day, and a **mass-casualty flag** for buses. Shown as "P1–P4 because …". **Not** an injury prediction. | H |
| D3 | **On-scene triage and vitals** | Covers the "vital signs" part of the thematic. | Responder form: victim count and START triage tags (red / yellow / green / black). Per victim: consciousness (AVPU), breathing rate, pulse, SpO₂ if a pulse oximeter is available, bleeding. Data goes straight to the receiving hospital. | H |
| D4 | **SMS-compact protocol** | Works on 2G or with no data. | Alert: `ACC|P1|36.47012,2.82731|A1 PK42|2V|7F3`. Triage reply: `T 7F3 R2 Y1 G3`. Parsed both ways through the Android gateway. | H |
| D5 | **Hospital pre-alert view** | The hospital prepares before arrival. | A per-hospital page and SMS with incoming victims, triage, vitals and ETA. A "Ready / Divert" reply feeds back into recommendation. | H |
| D6 | **Citizen report (no-camera roads)** | Covers roads without cameras. | One-tap web page with GPS, optional photo, and two witness questions (how many people? anyone trapped?). Offline, a pre-filled SMS `ACCIDENT lat,lon P<n> C<0/1>` keeps the exact position. Reports near an existing incident merge into it; standalone reports are marked "unverified". Trapped → P1 + extrication unit. | H |
| D7 | **AI incident description** | A readable summary such as "2 cars, side impact, one stopped across the right lane". | Produced by the same verifier, in Arabic and French. Every finding cites a frame; safety wording (never "dead"/"injured"). **Advisory only**. | M |
| D8 | **Response-time KPIs** | Proves the value. | Each incident records the timeline: event time, detection, verification, alert, acknowledgement, on scene, at hospital. Dashboard shows medians and per-agency breakdowns. | H |
| D9 | **Evidence integrity** | Evidence stands up in court and audit. | SHA-256 per file, a hash chain over incident events, an Ed25519-signed chain head, and a `/verify` endpoint. | H |

### Tier 3 — Advanced (only if Tiers 1–2 are solid)

| # | Feature | Notes | Feas. |
|---|---|---|---|
| A1 | Wrong-way vehicle detection | Track heading against each lane's flow vector. Cheap once tracking works. | H |
| A2 | Smoke / fire detection | A pretrained fire/smoke detector (AGPL-derived, separate process, optional) plus a 10-minute watch after each incident. Many false positives from dust, fog and headlights. Mark it experimental. | M |
| A3 | Secondary-accident warning | Suggest a variable-message-sign text and warn upstream cameras' operators of a queue. Simulated output. | H |
| A4 | Camera health monitoring | Detect a frozen feed, an outage, darkness or a tilted camera. The simulator can trigger these with `SIGSTOP` and kill. | H |
| A5 | Privacy filter | Blur faces and licence plates in exported evidence. | M |
| A6 | Multi-incident correlation | Merge two cameras watching the same crash, or a camera detection and a citizen report, by space-time proximity. | M |
| A7 | Black-spot analytics | Heatmap of incidents by road segment and hour. | H |

### Tier 4 — Future production features (pitch only, do not build)

- ONVIF discovery and onboarding of real DGSN, wilaya and highway CCTV.
- GPU inference servers (NVIDIA DeepStream / Triton) per wilaya centre.
- Integration with Civil Protection, Gendarmerie and SAMU dispatch systems.
- Feed into the national hospital transfer platform announced in December 2025.
- eCall/crash-detection ingestion from vehicles and phones (OS crash detection), and cell broadcast.
- Active-learning loop: operator labels feed periodic retraining on Algerian footage.
- Hospital bed and emergency-capacity integration.

## 5. Features we reject (and why)

- **Licence-plate reading or identity tracking.** Privacy risk, and it does not help the emergency response.
- **Automatic dispatch without a human.** False-positive risk; operators must stay accountable.
- **"Injury severity prediction" from video.** No credible model exists. We score *incident priority* from observable signals instead.
- **Edge boxes, model marketplaces, uploadable models.** Unnecessary. Inference runs on servers in the control room.
- **Microservices per feature.** One API service plus the vision workers is enough.
