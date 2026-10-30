# Nadjet (نجاة) — AI Road-Incident Detection & Emergency Coordination for Algeria

These are research and design documents for SolveX 3.0, **Thematic 1: "Road accidents: improving emergency response."** They are current as of 2026-10-29. The product is named **Nadjet** (Arabic **نجاة**, "survival, being saved"). The product requirements (technology-neutral) live in [`../PRD.md`](../PRD.md). The technical choices live in [11-technical-decisions.md](11-technical-decisions.md). The non-technical creative brief for design and film is [`../BRIEF.md`](../BRIEF.md).

## Executive summary

- **The thematic is about the whole response chain, not only detection.** The steps are: locate the accident, assess severity, transmit the information, and direct victims to the right hospital. The thematic names geolocation, vital signs, decision support, complementarity with existing systems, and SMS / low-bandwidth operation.
  - A camera-only system covers only the first step, and only on the small share of roads that have cameras.
  - **We recommend reframing:** an incident-coordination platform with **AI video detection as its fastest sensor**. Citizen and SMS reports cover roads without cameras. Responder triage and hospital pre-alerts complete the chain.
- **Algeria today (verified):**
  - A legal national video-surveillance system run by the DGSN (national police) and the wilaya (province) centres, under Decree 15-228.
  - 1,837+ cameras in Algiers and 387 in Boumerdès (2026).
  - Three separate emergency services: 14/1021 (Civil Protection), 17/1548 (DGSN), 1055 (Gendarmerie).
  - 3,838 road deaths in 2025 (DNSR, the national road-safety delegation).
  - 5G launched in December 2025, but coverage gaps on roads remain.
  - Strict data-protection rules: Law 18-07, amended by Law 25-11, and the 2026 ANPDP rules on video surveillance.
  - **Not found:** automated incident detection in operation, computer-aided dispatch, caller geolocation, published response-time statistics, and any hospital-capacity system. That gap is our opening.
- **AI honesty:**
  - No credible off-the-shelf model detects accidents on CCTV.
  - We build a pipeline:
    1. A COCO object detector and a tracker.
    2. Behaviour triggers. This approach is proven on highway CCTV: AI City 2021 winners reached F1 ≈ 0.95.
    3. A crash verifier that we fine-tune on CCTV accident datasets.
    4. An optional local vision-language model that writes descriptions.
    5. **A human verification step before dispatch.**
  - Evaluation is event-level on held-out videos, including false alarms per camera-hour.
- **Architecture:**
  - A modular monolith: FastAPI with PostGIS and Redis.
  - Vision workers, one per camera.
  - MediaMTX for RTSP in and WebRTC out.
  - OSRM routing on Algeria's OpenStreetMap data, and a MapLibre dashboard with offline tiles.
  - CAP 1.2 alerts, with real two-way SMS through an Android gateway.
  - The production target is hybrid: wilaya video nodes plus central coordination in the national data centre.
- **The demo runs fully locally and end-to-end with genuine inference:** a real video crash is detected, then verified, then units and a hospital are recommended, then real SMS and push alerts go out, the responder acknowledges by SMS, sends triage and vitals, and the hospital receives a pre-alert. KPIs and the evaluation report are shown at the end.

## Documents

| # | Document | Covers deliverable |
|---|---|---|
| 01 | [Thematic analysis](01-thematic-analysis.md) | 1 |
| 02 | [Algeria: infrastructure, emergency chain, legal](02-algeria-research.md) | 2 |
| 03 | [Product vision & prioritized features](03-product-and-features.md) | 3, 4 |
| 04 | [AI & technical feasibility with evidence](04-ai-feasibility.md) | 5 |
| 05 | [Architecture, diagrams & technology stack](05-architecture-and-stack.md) | 6, 7 |
| 06 | [Local simulation strategy](06-local-simulation.md) | 8 |
| 07 | [Roadmap, workstreams & agent workflow](07-roadmap-and-agents.md) | 9, 10 |
| 08 | [Demo scenario, risks & deployment strategy](08-demo-and-risks.md) | 11, 12 |
| 09 | [GitHub org: repositories & per-repo stack](09-repositories-and-stack.md) | repos, CI/CD |
| 10 | [Live stage deployment (Dokploy + Brev) & no-training model stack](10-live-deployment-and-models.md) | deploy, models, "try it" demo |
| 11 | [Technical decisions register (TD-xx)](11-technical-decisions.md) | the canonical "how": wins over docs 04–10 where they differ |

> **Update (doc 10):** there is no time to train, so the crash verifier is now the pretrained open-weights VLM **Qwen3-VL-8B** (Apache-2.0) served by vLLM on a Brev GPU. It replaces the fine-tuned VideoMAE described in docs 04 and 07. The detector is **RF-DETR** (Apache-2.0).

## Evidence labels used throughout

- **VERIFIED**: deployed or in force, with a source.
- **ANNOUNCED**: a plan or contract exists, but operation is unconfirmed.
- **UNKNOWN**: no reliable source was found.
- **[V] / [K] / [E]**: verified on the web this session / established knowledge not re-checked / estimate to be measured.

## Open decisions for the team

1. Confirm the reframing: incident coordination with camera AI as the flagship sensor, versus a camera-only scope.
2. Detector licence: Ultralytics (AGPL, fastest to build) for the hackathon, or RF-DETR (Apache-2.0) from day 1.
3. Hardware: the Mac-only demo, or an NVIDIA laptop/Colab for training the verifier.
4. ~~Product name~~: decided, **Nadjet (نجاة)**. Still open: GitHub org handle and domain mapping.
