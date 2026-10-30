# AI — Merged AI Solution and Technical Feasibility (with evidence)

> This document has the same structure as `04-ai-feasibility.md`, which it does not modify.
> It describes the AI **after merging** Nadjet (PRD v0.2 + doc 10) with the `brainstorm/` study, and adds the conclusions of the two follow-up investigations:
> - thermal cameras (`ENQUETE-thermique-occupants.md`);
> - occupant count (`ENQUETE-nombre-occupants.md`).
>
> In short:
> - **Nadjet provides the skeleton:** real time, the response chain, human gate, permissive licences.
> - **The brainstorm provides the reasoning layer:** evidence IDs, graded statuses, priority floors, safety filter, fire/smoke mitigations.

**Labels used in this document:**
- **[V]** verified on the web on 2026-10-29/30.
- **[B]** verified in the brainstorm study (`brainstorm/README.md`), not re-checked here.
- **[K]** established knowledge that was not re-checked this session.
- **[E]** an estimate. We must measure these numbers ourselves.

## 1. The core truth: vehicle detection is not accident detection

- A COCO detector (RF-DETR, YOLO) finds *cars, trucks, buses, motorcycles and people*. It has **no idea whether a crash happened**. A crash is an **event in time** between several objects.
- There is **no downloadable, CCTV-specific accident model** that works out of the box [V][B]:
  - Roboflow / Kaggle "accident" detectors have leaky splits.
  - Dashcam datasets have the wrong viewpoint.
  - `OPear/videomae-large-finetuned-UCF-Crime` is CC-BY-NC.
  - ACCIDENT-CVPR-2026 is a notebook with no weights of its own (public score 0.2523) [B].
- **No time to train** (D-03). The best no-training approach published is **hybrid**: tracking-based kinematic triggers propose candidate windows, then a frozen vision-language model (VLM) verifies them on annotated keyframes [V][B]. This is the principle of the ACCIDENT@CVPR 2026 winners (frozen Qwen3-VL + detector + tracker).
- Three things look possible but are **not**:
  - **Counting occupants through intact windows with a thermal camera.** Car glass blocks long-wave IR (8–13 µm). The camera sees a reflection, not the cabin [V].
  - **Counting people in thermal images with a VLM.** Qwen-VL 2.5 (8B) counting MAE is 3.55 on FLIR, against 1.73 for humans (ThermEval) [V].
  - **Predicting injury severity from video.** No credible model exists (NG-04).

So the AI is **a pipeline of proven pieces plus our own rules**, with every output tied to evidence and a human deciding.

## 2. Recommended hybrid pipeline (evidence-based, no training)

```
decode @ 5 fps per camera (RTSP / WHIP / upload)
  → [S1] RF-DETR detector (vehicles, persons)                                proven
  → [S2] tracker by camera_context:                                          proven
           cctv_fixed      → ByteTrack + homography speed (m/s) + lane/zone polygons
           handheld/upload → BoT-SORT (camera-motion compensation), box-normalised speed
  → [S3] behaviour triggers + suppression → AccidentEvent(t_start, t_peak, t_end)  proven on highway CCTV
  → [S4] keyframes around t_peak with track IDs drawn + tracks as text
  → [S5] VLM verifier (Qwen3-VL-8B-FP8, vLLM, guided JSON), findings[] with evidence_ids   strong, zero-shot
  → [S6] validation: schema, evidence_ids exist, FR/AR/EN safety vocabulary,
         1 retry, then template description                                  ours
  → [S7] status (rule × VLM agreement) + priority floors P1–P4 + occupancy range   ours
  → incident candidate → human verification → dispatch → triage overrides AI

parallel side branches (same frames, never block S1–S7):
  [A1] fire/smoke detector @ ~2 fps + 10-min post-incident watch            Should
  [A2] person-exit count around involved vehicles (from S1/S2 tracks)        Could
  [A3] VLM "sentinel" pass every 10–15 s per camera                          Could, gated by ablation
  [A4] image pipeline: citizen photo / photo upload (S1 → S5 → S6)           Could
  [A5] thermal person detection on responder/drone thermal photos            Could, only with real hardware
```

### Evidence per stage

| Stage | Evidence | Limits |
|---|---|---|
| S1 detector | **RF-DETR** N/S/M: 48.4 / 53.0 / 54.7 COCO mAP. T4 TensorRT FP16 runs N in 2.3 ms and M in 4.5 ms per frame. Apache-2.0 [V][B]. | Small or far vehicles, night, rain. Heavier than YOLO on CPU (~30 M parameters even for Nano) [B]. |
| S2 tracking | supervision ByteTrack + PolygonZone + ViewTransformer (MIT) [K]. `trackers` BoT-SORT with camera-motion compensation, HOTA 63.7 vs ByteTrack 60.1 on MOT17 (Apache-2.0) [B]. | Identity switches under occlusion at the exact moment of impact. MOT17 is pedestrians, not traffic. |
| S3 triggers | **AI City 2021 Track 4** (crashes and stalled vehicles on highway CCTV): detection + tracking + rules reached **F1 0.9524** [V]. | They detect *anomalies*, not "crash" specifically. Jams and camera shake are the main false-positive sources. |
| S4 annotated keyframes | Coarse-to-fine VLM + tracking with track IDs drawn on frames (arXiv 2608.08867), reported **0.504** on 2,027 real CCTV clips without training [B]. | IDs drawn at 448 px can become small; measure the trade-off. |
| S5 VLM | ACCIDENT@CVPR 2026 1st place = frozen Qwen3-VL + YOLO + tracking (Apache-2.0 code) [V]. Best zero-shot systems score about 0.50–0.57 on the joint time/location/type metric [V]. | Weak on collision **type** and exact impact time. "Sees" a crash when prompted suggestively. **Never the sole trigger of a `collision`.** |
| S6 validation | Guided JSON (vLLM) + Pydantic; claims without existing `evidence_id` are dropped [B]. | Validation cannot fix a wrong but well-formed answer. That is why the human gate exists. |
| S7 priority | Deterministic floors: a pure function, table-tested [B]. | Thresholds are hand-set until operator labels allow calibration. |
| A1 fire/smoke | `weslleyskah/fire_smoke_box` (YOLO26n on FASDD_CV, mAP50 0.772 on the author's validation set) [B]. D-Fire YOLOv5s (21.5k images; mAP of these weights unverified) [K]. | Smoke is easily confused with fog, dust, exhaust steam and headlight glare. Not road-specific. Both are AGPL-derived (§8). |
| A2 person exits | YOLOv5 + DeepSORT for people entering vehicles in parking video: 58% precision, 100% recall [V]. | Occlusion; bystanders counted as occupants. **Trapped people never exit**, so this is a minimum only. |
| A5 thermal persons | Luxonis `thermal-person-detection`: ONNX, 4.3 M parameters, 88% mAP on its own split, Apache-2.0 [V]. | Trained on standing or walking people. Small silhouettes were filtered out. Partly trained on FLIR data under a non-commercial licence [V]. |

### Why this design is honest

- Every alert traces back to **measurable signals**: tracks, speeds, overlaps, rule names, and VLM findings that each cite an image. The incident card shows "why was this flagged".
- Event types and statuses are named honestly:

| Rule fired | VLM says | Status | Incident type |
|---|---|---|---|
| yes | accident visible | `confirmed_visual` | `collision` (or `rollover`, `fire`) |
| yes | possible / VLM unavailable | `probable` | `possible_incident` |
| yes | no accident visible | `possible` | `possible_incident`, both signals shown |
| yes | insufficient evidence (night, blur, too small) | `insufficient_evidence` | `possible_incident` + quality flag |
| no | accident visible (sentinel / WHIP mode) | `possible` | `possible_incident`, **never** `collision` |

- Contradictions (e.g. smoke detector yes, VLM no) are **listed, never resolved silently**. Failed or disabled modules appear in `degraded_modules`.
- What cannot be seen is said: `not_assessable` always contains "occupant condition", "fuel leak" and "occupants behind intact windows".
- **A human verifies before dispatch.** The AI shortens time-to-awareness; it does not replace judgement.

## 3. S3 trigger definitions (starting values, tune on the non-held-out split)

| Trigger | Signal | Starting threshold |
|---|---|---|
| `collision_candidate` | Two tracks with IoU > 0.05 (or centre distance < 0.6 × mean box width), **then both** have speed < 1.5 m/s for ≥ 3 s | — |
| `hard_stop` | Speed drops by > 6 m/s within ≤ 1.5 s, and < 30% of the other tracks slow down | — |
| `sudden_swerve` (from brainstorm) | Heading change > 35° within ≤ 1 s, then a stop or leaving the lane polygon | — |
| `stalled_vehicle` | Vehicle stationary ≥ 20 s inside a `live_lane` polygon while other tracks still move | — |
| `pedestrian_on_road` | A person inside a `carriageway` polygon for ≥ 2 s on a highway camera | — |
| `rollover_candidate` | Abrupt change of box aspect ratio, then stop | — |
| `wrong_way` (A1) | Heading differs from the lane flow vector by > 120° for ≥ 2 s | — |
| `scene_shock` | Global optical-flow or frame-difference z-score spike, *with no* global camera motion | z > 4 |
| `fire_smoke` (A1) | Fire box on ≥ N consecutive sampled frames, overlapping or adjacent to a tracked vehicle; smoke needs a larger N and a lower priority floor | fire conf ≥ 0.5, N ≥ 4 · smoke conf ≥ 0.4, N ≥ 8 [E] |

**Each trigger outputs an `AccidentEvent`** with:
- `t_start`, `t_peak`, `t_end`;
- `involved_track_ids`;
- the signals that fired and their values.

`t_peak` becomes the incident `event_time` (SC-001).

**Suppression rules:**
- Mute during global camera motion (PTZ / shake).
- Normalise deceleration against the rest of the traffic (jams, E-01).
- Apply a per-camera cooldown per location (also handles video loop restarts).
- Require N consecutive confirmations (identity switches, E-04).

**Fire after impact.** Fire often starts **after** the crash, while the VLM only looks at the scene once, at trigger time. So A1 runs continuously at about 2 fps on every camera. It also watches the zone around the involved vehicles **for 10 minutes after any incident**. A confirmed fire updates the open incident:
- type gets a `fire` flag;
- priority goes to P1;
- dispatch adds a fire-capable Civil Protection unit.

## 4. S5 crash verifier: no-training plan (replaces the VideoMAE training plan)

1. **Model.** `Qwen/Qwen3-VL-8B-Instruct-FP8` served by vLLM (OpenAI-compatible API, guided JSON, temperature 0).
   - Official FP8 build; Apache-2.0; same family as the ACCIDENT 2026 winner [V].
   - **Qwen3.5-9B** is only a **day-1 benchmark candidate**. The brainstorm notes its tooling needs nightly vLLM/transformers [B].
   - **Cosmos-Reason2-8B** stays an optional second opinion on an L40S.
2. **Input.** 8–16 keyframes around `t_peak` (±3 s) at 448 px.
   - Involved tracks have their **boxes and IDs drawn** on the frames.
   - The prompt also lists the tracks as text (class, normalised box, speed).
   - The prompt is neutral, allows `none`, and says "answer only from what is visible".
3. **Output schema** (merged Nadjet + brainstorm):
   - `incident_assessment`: accident visible / possible / not visible / insufficient evidence;
   - `type`: collision | rollover | fire | stalled | pedestrian | none;
   - `involved_track_ids`;
   - `collision_subtype`: indicative only, default `unknown`;
   - `findings[]`, each with `statement`, `observed | inferred` and at least one `evidence_id`;
   - `unknowns[]`;
   - `severity_adjustment`: 0 or +1, with a cited finding;
   - `description_fr`, `description_ar`.
4. **Validation (S6).**
   - Schema check.
   - Every `evidence_id` must exist, otherwise the finding is dropped and logged.
   - Safety vocabulary filter in FR/AR/EN. Words like *dead, injured, unconscious* (and their FR/AR equivalents) are replaced by: *"Person detected lying on the ground — possible emergency requiring human assessment."*
   - One retry with the validation error, then a **template description** built from rule signals only.
5. **Failure handling.** The VLM times out after 15 s or returns invalid output → `vlm: unavailable | invalid`. The candidate is **still published** with the rule signals (FR-VIS-009).
6. **Sentinel pass (A3).** Every 10–15 s per camera, the VLM gets 6 low-resolution frames and one question: "is a collision visible?". It can only create `possible_incident`. **It is enabled only if the ablation (§5) shows a recall gain without exceeding 1 false alarm per camera-hour.**
7. **Mock mode.** `VLM_MODE=mock` (recorded answers) is allowed **only in `tests/`**. The production start-up refuses it (FR-VIS-020).
8. **Compute** [E]. About 1–3 s per check on an L40S and 3–6 s on an L4. **Measure on day 1** (Q-05).

## 5. Honest evaluation protocol (shown in the pitch)

- **Event-level metrics.** A true positive (TP) is an alert within [t_impact − 2 s, t_impact + 10 s] that overlaps the annotated region. Report precision, recall, F1, median detection delay and the **mean error of `t_peak`**.
- **False alarms per camera-hour** on long normal footage that includes congestion, night, rain, **fog and dust** (for A1). This is the number operators care about.
- **Ablation:**
  1. S3 alone;
  2. S3 + S5;
  3. S3 + S5 + sentinel;
  4. A1 with and without its mitigations.
- **VLM quality:**
  - share of valid JSON on the first try;
  - share of findings dropped for invalid evidence;
  - share of `unknown` collision subtypes.
- **Priority:** agreement with human annotation, exact and within ±1 level.
- **Robustness:** fault-injection tests (VLM down, fire module down, camera freeze). The incident must still be produced and the missing module listed.
- **Per-stage latency** and the end-to-end SC-001 budget.
- **Confusion breakdown:** crash vs stall vs jam vs camera motion vs smoke-like fog.
- **Bootstrap 95% confidence intervals.** With about 50–100 test events they will be wide; say so.
- **Held-out rule (FR-VIS-022).** Demo clips come from `eval/heldout.json` and are never used for tuning. `eval/run_eval.py` is published so the jury can rerun it.
- **Dataset licences.** TAD, CADP, TU-DAT and UCF-Crime are research-only. The licence of the real ACCIDENT clips is unspecified [B]. Use them for evaluation only, and disclose that.

## 6. Severity and priority (decision support, not medical prediction)

**Priority floors.** Each rule that fires sets a minimum priority, and the final priority is **the highest floor**. Every fired rule is shown with its evidence IDs.

| Rule (on persistent evidence) | Floor |
|---|---|
| Bus involved (possible mass casualty, FR-INC-008) | P1 |
| Person on the carriageway near an involved vehicle | P1 |
| Visible flames (persistent or confirmed by the VLM) | P1 |
| **Someone reported trapped** (witness question) | P1 + extrication-capable unit |
| ≥ 2 independent P2 indicators | P1 |
| ≥ 3 vehicles involved | P2 |
| Estimated pre-impact speed > 80 km/h (calibrated CCTV only) | P2 |
| Overturned vehicle (rule + VLM) | P2 |
| Persistent smoke associated with a vehicle | P2 |
| Vehicle stopped in a live lane (secondary-crash risk) | P3 |
| Two-vehicle collision, no other indicator | P3 |
| Vehicle stopped off the lane, no hazard | P4 |

- Night or highway: **+1 level at most**, the same cap as the VLM adjustment. Bonuses never add up beyond +1.
- The VLM can **never lower** the priority below the rule floor.
- Not enough evidence → **P2 + "to assess"** (proposal, decision D-15).
- Confidence is shown as `low / medium / high`, from persistence and agreement between sources. No invented probability.
- After responders send triage (START tags), **priority is recomputed from real triage data**, which overrides the AI estimate (FR-INC-004).

**Occupancy (how many people, multi-source).** No single sensor gives a reliable count [V], so the incident carries a range.

| Source | Gives | When |
|---|---|---|
| Witness questions ("how many people?", "is anyone trapped?") on the report page, SMS `ACCIDENT lat,lon P4 C1`, or the operator's call form | Earliest estimate. "Is anyone pinned?" is the key MPDS question for extrication [V] | Must |
| Vehicle class (car ≤ 5, minibus ~30, coach ~50+) | Nominal capacity, labelled **"overload possible"**. The El Harrach bus carried 45 people for 27 seats [V] | Should |
| A2 person-exit count from CCTV | **Minimum** only: "at least N people visible" | Could |
| Triage (R + Y + G + B) | **Found**: the source of truth | Must (exists) |

If found < expected minimum, the operator and the responder get a **"possibly missing person"** alert: search for an ejected occupant (outside) or a trapped one (inside). This is where A5 thermal search helps.

**Rejected for occupancy:**
- thermal through glass;
- near-IR occupancy systems (HOV-lane style, fixed gantries only);
- plate reading (NG-03);
- phone-in-cell counts;
- a VLM count through the windscreen.

**Production / pitch only:**
- eCall `numberOfOccupants` (EN 15722:2020) [V], not deployed in Algeria to our knowledge;
- Sogral coach ticket counts [V], which need a partnership and a data-protection assessment.

## 7. Runtime feasibility

| Hardware | Workload | Expected [E] |
|---|---|---|
| **Brev L40S 48 GB** (recommended) | 4 cameras × RF-DETR-M at 5 fps + tracking + A1 at 2 fps + Qwen3-VL-8B-FP8 (vLLM `--gpu-memory-utilization 0.45`) + optional Cosmos | Comfortable. VLM about 1–3 s per check |
| **Brev L4 24 GB** | Same without Cosmos | VLM about 3–6 s per check. Sentinel probably off |
| Laptop, offline fallback | RF-DETR Nano exported to **ONNX Runtime** (CPU) or CoreML; small local VLM | 2–3 cameras at reduced fps. Hardware to confirm (Mac vs PC) |

**SC-001 latency budget (≤ 10 s median, impact → operator screen)** [E]:
- `collision_candidate` needs both vehicles stopped for ≥ 3 s, so the trigger fires about 3–4 s after impact;
- keyframe extraction takes under 0.5 s;
- the VLM takes 1–3 s on an L40S;
- validation, Redis, API and SSE take under 1 s.

That is about **5–8.5 s in total**. `hard_stop` and `scene_shock` can fire earlier. **Benchmark on day 1.**

Hardware abstraction (from the brainstorm):
- `DeviceSpec` (`cpu | cuda`, `fp32 | fp16`) is resolved once at start-up;
- each adapter picks its own runtime (`torch-cuda`, `onnxruntime-cpu`, `tensorrt`…);
- business logic never contains `if cuda`;
- models load once per worker, never per request.

TensorRT and INT8 are postponed unless measured latency requires them.

## 8. Licensing decisions

- **Core path: permissive only** (NFR-LIC-001). RF-DETR N/S/M, Qwen3-VL and vLLM are Apache-2.0; supervision is MIT; `trackers` is Apache-2.0 [V][B].
- **Optional, isolated, documented** (D-06):
  - **Fire/smoke (A1).** `fire_smoke_box` claims CC-BY-4.0 but is fine-tuned from AGPL `yolo26n`; D-Fire YOLOv5s weights are MIT but the YOLOv5 code is AGPL [B][K]. It runs as a **separate process**, is **enabled for the hackathon** (public repo) and is flagged for replacement by a permissively licensed detector before any production contract.
  - **Thermal persons (A5).** Luxonis model, Apache-2.0, but partly trained on the Teledyne FLIR ADAS dataset, whose licence is **non-commercial** and excludes production systems [V]. Clarify before production.
  - **Cosmos-Reason2-8B.** NVIDIA Open Model License; gated; credit "Built on NVIDIA Cosmos".
- **Rejected:**
  - Ultralytics YOLO11/YOLO26 as default detector (AGPL-3.0, D-04).
  - The vehicle-damage model `car-damage-yolo11m-ft`: CarDD data is non-commercial [B], and it adds little on far CCTV views.
  - `e1250/safety_detection` (indoor fires, no licence) [B].
  - `OPear` VideoMAE (CC-BY-NC); demo-only at most.
- **`models.lock.yaml`.** Every weight is pinned with its source, version, checksum and **licence**. CI fails if an AGPL or non-commercial model is enabled by default in a production profile.
- **Postponed (not in the hackathon):**
  - human pose (RTMPose; weights licence to check, low value on small CCTV silhouettes);
  - vehicle damage;
  - seat-level occupant localisation (not feasible, §1).
- **Datasets:** research / non-commercial. Retrain on Algerian footage under a government agreement for production.

## Key URLs

- AI City 2021 Track 4 strong baseline: https://arxiv.org/abs/2104.06856
- ACCIDENT@CVPR 2026, 1st place: https://arxiv.org/abs/2605.29325 · https://github.com/fuumin621/cvpr2026-accident-1st-place-solution
- Coarse-to-fine VLM + tracking: https://arxiv.org/abs/2608.08867 · zero-shot spatio-temporal grounding: https://arxiv.org/abs/2605.01512
- ACCIDENT-CVPR-2026 baseline: https://arxiv.org/abs/2604.09685 · benchmark: https://accidentbench.github.io
- RF-DETR: https://github.com/roboflow/rf-detr · supervision: https://github.com/roboflow/supervision · trackers: https://github.com/roboflow/trackers
- Qwen3-VL-8B-FP8: https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-FP8 · Qwen3.5-9B: https://huggingface.co/Qwen/Qwen3.5-9B · Cosmos-Reason2-8B: https://huggingface.co/nvidia/Cosmos-Reason2-8B
- Fire/smoke: https://huggingface.co/weslleyskah/fire_smoke_box · https://github.com/pedbrgs/Fire-Detection · https://github.com/gaiasd/DFireDataset
- Thermal: glass vs LWIR https://armasight.com/armasight-university/why-thermal-imaging-devices-dont-see-through-glass-and-other-common-questions-/ · ThermEval https://www.alphaxiv.org/abs/2602.14989.md · Luxonis https://models.luxonis.com/luxonis/thermal-person-detection/aim_6tHaZh3PVbqU4myqxwRDGV · FLIR ADAS licence https://flir.ca/oem/adas/adas-dataset-agree
- Occupancy: eCall EN 15722:2020 https://knowledge.bsigroup.com/products/intelligent-transport-systems-esafety-ecall-minimum-set-of-data-1 · SWOV extrication https://swov.nl/nl/publicatie/predicting-need-extrication-traffic-accidents-reported-911 · El Harrach https://fr.wikipedia.org/wiki/Accident_de_bus_%C3%A0_El-Harrach · person-exit video https://arxiv.org/pdf/1908.00716
- NVIDIA VSS Smart City blueprint (architecture reference): https://docs.nvidia.com/vss/latest/
- Internal (paths relative to this file): `../PRD.md`, `10-live-deployment-and-models.md`, `../../brainstorm/README.md`, `../../FUSION-IA-nadjet-brainstorm.md`, `../../ENQUETE-thermique-occupants.md`, `../../ENQUETE-nombre-occupants.md`
