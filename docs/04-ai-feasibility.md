# 04 — AI Design and Technical Feasibility (with evidence)

This is the AI design for Nadjet. It is built **without any model training**. Exact parameters and technical decisions are in [doc 11](11-technical-decisions.md): TD-01, TD-03, TD-22 to TD-25, and §6. Where they differ, doc 11 wins.

**Labels used in this document:**
- **[V]** verified on the web on 2026-10-29/30.
- **[K]** established knowledge, not re-checked this session.
- **[E]** an estimate that we must measure ourselves.

## 1. The core truth: vehicle detection is not accident detection

- A COCO detector (RF-DETR) finds *cars, trucks, buses, motorcycles and people*. It has **no idea whether a crash happened**. A crash is an **event in time** between several objects.
- There is **no downloadable, CCTV-specific accident model** that works out of the box [V]:
  - Roboflow and Kaggle "accident" detectors have leaky splits.
  - Dashcam models and datasets have the wrong viewpoint for fixed cameras.
  - `OPear/videomae-large-finetuned-UCF-Crime` is CC-BY-NC, with an unclear evaluation split.
- **No time to train** (PRD D-03). The best published no-training approach combines two things [V]:
  - a frozen vision-language model (VLM);
  - detection and tracking.

  This is how the **CVPR 2026 ACCIDENT** winners worked (frozen Qwen3-VL).
- Three things look possible but are **not**:
  - **Counting occupants through intact windows with a thermal camera.** Car glass blocks long-wave infrared, so the camera sees a reflection, not the cabin [V].
  - **Counting people with a VLM through a windscreen.** VLM counting error is about twice a human's on thermal images (ThermEval) [V].
  - **Predicting injury severity from video.** No credible model exists (PRD NG-04).

## 2. Pipeline (no training)

```
decode @ 5 fps per camera (RTSP / phone WHIP / upload)
  → [S1] RF-DETR detector (vehicles, persons)                              proven
  → [S2] ByteTrack + zones + speed relative to box size (no calibration)   proven
  → [S3] trigger rules (4) + suppression ──────┐                          proven on highway CCTV
  → [S3b] AI sweep: every 5 s, last 8 s ───────┤                          strong cost evidence, gain inferred
                                               ▼
  → [S4] verifier input: one video, 16 dense frames @4 fps ±2 s + 4 context frames, 768 px, timestamps drawn
  → [S5] Qwen3-VL-8B-FP8 on vLLM, structured JSON, temperature 0, no thinking, yes-token probability
  → [S6] validation: schema, every finding cites a frame, AR/FR/EN safety wording, 1 retry, else template text
  → [S7] AI status + priority minimums
  → incident candidate → human verification → dispatch → triage overrides the AI

uploads ("try it"): two-pass AI-first (scan whole clip → refine ±2–3 s); RF-DETR only snaps the result onto vehicles
optional side branch: smoke/fire detector @ ~2 fps + 10-min watch after an incident (separate process, AGPL-derived)
```

### Evidence per stage

| Stage | Evidence | Limits |
|---|---|---|
| S1 detector | RF-DETR N/S/M: 48.4 / 53.0 / 54.7 COCO mAP; N runs in 2.3 ms on a T4 with TensorRT FP16; Apache-2.0 [V] | Small or far vehicles, night, rain |
| S2 tracking | `supervision` ByteTrack + PolygonZone (MIT) [K] | Identity switches under occlusion at the moment of impact. Speed is **relative**: per-camera metric calibration is impractical on public clips, and speed is very sensitive to calibration errors (Revaud et al., ICCV 2021) [V] |
| S3 rules | AI City 2021 Track 4 (highway crashes and stalls): detection, tracking and rules reached **F1 0.9524** [V] | Rules alone **miss many real crashes**: 71% detection rate (Ijjina et al., arXiv 1911.10037). Rule-based timing error was 6.63 s vs 3.20 s for a VLM (Huang, arXiv 2605.01512) [V] |
| S3b sweep | NVIDIA RT-VLM benchmark: an L40S-class GPU checks dozens of streams in 10 s chunks [V]. 4 cameras every 5 s ≈ 0.8 calls/s | No paper measures sweep vs rules-only recall. The gain is our inference, so it is **measured in the ablation** (§5) |
| S4–S5 verifier | ACCIDENT@CVPR 2026 1st place (frozen Qwen3-VL, arXiv 2605.29325) [V]: 4 fps beat 10 fps; **thinking mode collapsed timing** (0.42 → 0.06); **drawn tracking trails hurt**; self-consistency changed < 10 of 2,027 clips; timestamps drawn on frames worked; Cosmos-Reason2-8B, InternVL3.5 and Gemma-3 lost to Qwen3-VL | Benchmark clips **always contain a crash**: it shows the VLM locates crashes, not how often it wrongly says "crash" on normal traffic. The VLM tends to pick the wreckage frame (≈ +1.5 s late) and to guess the clip's middle when unsure |
| Confidence | Self-reported VLM confidence is overconfident; the probability of the yes/no answer token separates right from wrong better [V] | Medium-to-weak evidence for video. Thresholds are tuned per TQ-07 |
| S6 validation | Structured output + Pydantic; claims without a valid frame citation are dropped | Validation cannot fix a well-formed but wrong answer. That is why the human gate exists |
| Uploads | All three top ACCIDENT 2026 papers scan first, then refine around the moment (2605.29325, 2608.08867, 2605.01512) [V] | Open-world detection (clips without a crash) is unproven, so "no collision" must always be an allowed answer |
| Production pattern | NVIDIA VSS alert verification: rules → VLM yes/no → confirmed / rejected / failed; a 5 s timeout; NVIDIA warns of backlogs and occasional hallucinated verdicts [V] | NVIDIA publishes no false-positive-reduction numbers |

## 3. Trigger rules and AI statuses

**Trigger rules** (thresholds in doc 11 §6):

| Trigger | Signal |
|---|---|
| `collision_candidate` | Two tracks overlap, **then both** stay almost still for ≥ 3 s |
| `hard_stop` | Relative speed drops by > 70% within 1 s, then stays near zero, while most other vehicles keep moving |
| `stalled_vehicle` | A vehicle stationary ≥ 20 s in a live lane while other tracks move |
| `pedestrian_on_road` | A person on the carriageway ≥ 2 s (highway cameras) |
| *(optional)* `wrong_way` | Heading against the lane flow for ≥ 2 s (PRD US-14, Could) |

**Suppression:**
- mute during global camera motion;
- normalise against the rest of the traffic (jams);
- per-location cooldown (also handles looped demo clips);
- several confirming frames before a stop counts.

**AI statuses** (PRD FR-VIS-007; the AI alone never confirms a collision):

| Rule fired | AI verifier says | Status |
|---|---|---|
| yes | collision visible, high yes-probability | `confirmed` → `collision` |
| yes | possible, or verifier unavailable | `probable` |
| yes | no collision visible | `possible` (both signals shown) |
| yes | cannot judge (night, blur, too small) | `insufficient_evidence` + quality flag |
| no (sweep only) | collision visible | `possible`, or `probable` on 2 consecutive sweeps |

- Contradictions are **listed, never hidden**.
- Disabled or failed modules are shown as degraded.
- The output always lists what cannot be seen: occupants' condition, people behind intact windows, fuel leaks.

## 4. Verifier prompt and output (no training)

- **Model:** `Qwen/Qwen3-VL-8B-Instruct-FP8` on vLLM, one server for the verifier and the sweep. Apache-2.0.
- **Input:** one video per call (half the visual tokens of an image list). Timestamps drawn on frames. 768 px for verification, 640 px for the sweep.
- **Question:** neutral. It never presupposes a crash, and always allows "no collision" and "cannot judge".
- **Output:** fixed JSON (doc 11 §6), with:
  - `collision_visible`, `t_contact`, `type`, `vehicles_involved`, `lanes_blocked`;
  - `findings[]`, each citing `frame_ids`;
  - `not_assessable[]`;
  - `priority_raise` (0 or 1);
  - `description_fr`, `description_ar`.
- **Safety wording:** "dead", "injured" and their Arabic and French equivalents are replaced by "person lying on the ground — needs human assessment".
- **Failure:** verifier timeout or invalid output → one retry, then `verifier: unavailable / invalid` and a template description from rule signals. The candidate is still published.
- **Mock mode:** recorded answers are allowed **only in `tests/`**. Production start-up refuses them.

## 5. Honest evaluation protocol (shown in the pitch)

- **Event-level metrics.** A true positive is an alert within [t_impact − 2 s, t_impact + 10 s]. Report:
  - precision, recall and F1;
  - median detection delay;
  - mean error of the detected crash time.
- **False alarms per camera-hour** on long normal footage: congestion, night, rain, fog and dust. Count sweep alerts too.
- **Ablation:**
  1. rules alone;
  2. rules + verifier;
  3. rules + verifier + sweep;
  4. drawn boxes on vs off (TQ-06).
- **AI quality:**
  - share of valid JSON on the first try;
  - share of findings dropped for invalid citations;
  - share of "cannot judge".
- **Priority:** agreement with human annotation, exact and within ±1 level.
- **Robustness:** fault injection (verifier down, camera freeze). The incident must still be produced, with the missing module listed.
- **Bootstrap 95% confidence intervals.** With about 50–100 test events they will be wide; say so.
- **Held-out rule.** Demo clips come from `eval/heldout.json` and are never used for tuning. `eval/run_eval.py` is published so the jury can rerun it.
- **Dataset licences.** TAD, CADP, TU-DAT, UCF-Crime and the ACCIDENT clips are research-only. Use them for evaluation and demo only, and disclose that.

### Status of the evaluation (issue #19)

The harness exists (`make eval`, TD-42) and every metric above is computed by tested functions, but **no real run has been made yet**: the annotated crash clips, the held-out video files and at least one camera-hour of normal and congested footage are not in the repository, and a run needs the Brev GPU. Until `make eval` has written a file to `eval/results/`, there are no measured numbers in this document: the targets in the success criteria (recall ≥ 0.7, at most 1 false alarm per camera-hour) are goals, not results.

What a results file reports: precision, recall, F1, median detection delay and mean crash-time error with bootstrap 95 % intervals; false alarms per camera-hour; the ablation table (rules, + verifier, + sweep; the boxes on/off comparison is listed as not run because drawn boxes are not implemented, TQ-06); AI quality (valid JSON on the first try, findings dropped for invalid citations, share of "cannot judge"); per-stage latency p50/p95; the clips that were skipped and why; and the limitations of the run. Known limits of the method: intervals over a few dozen clips are wide; delay is stream time without network and queue time; the priority-agreement metric and the robustness (fault-injection) runs of this protocol are not part of the harness yet.

## 6. Priority (decision support, not medical prediction)

**Priority minimums** (PRD FR-INC-003). Each rule sets a minimum; the final priority is the highest minimum. Every fired rule is shown with its evidence.

| Rule | Minimum |
|---|---|
| Bus involved (possible mass casualty) | P1 |
| Person on the carriageway near an involved vehicle | P1 |
| Visible flames (persistent, or confirmed by the AI) | P1 |
| **Someone reported trapped** (witness question) | P1 + extrication-capable unit |
| ≥ 3 vehicles involved | P2 |
| Overturned vehicle (AI finding) | P2 |
| Persistent smoke near a vehicle | P2 |
| Not enough evidence | P2 "to assess" (D-15) |
| Vehicle stopped in a live lane | P3 |
| Two-vehicle collision, no other indicator | P3 |
| Vehicle stopped off the lane, no hazard | P4 |

- Night or highway, or an AI `priority_raise`: **+1 level at most** in total.
- The AI **never lowers** a priority.
- Confidence is shown as low / medium / high, from the yes-probability and the agreement between sources.
- Triage from responders (START tags) **overrides** the AI estimate (FR-INC-004).

**Occupancy (MVP).** No sensor gives a reliable count, so the incident carries what is known:
- **witness answers** (how many people? anyone trapped?);
- the **vehicle class** (car ≤ 5, minibus ~30, coach ~50+), labelled "overload possible". The El Harrach bus carried 45 people for 27 seats [V];
- **triage**, which is the source of truth.

Counting from CCTV and thermal search are out of scope (D-16).

## 7. Runtime and budget

| Hardware | Workload | Expected [E] |
|---|---|---|
| **Brev L40S 48 GB** (recommended) | 4 cameras × RF-DETR at 5 fps + tracking + sweep (0.8 calls/s) + verifications + uploads + optional fire detector, with Qwen3-VL-8B-FP8 on vLLM | ≈ 2–3 s per AI call; comfortable |
| Brev L4 24 GB (fallback) | Same | Slower; sweep at 8–10 s |
| Laptop | Everything except AI; AI through `make brev-forward` | Brev only (TD-27) |

- **Budget:** $90 of Brev credits. Plan ≈ 28 h (≈ $30–52); see doc 10 §4.
- **SC-001 (≤ 10 s):**
  - Rule path: the trigger fires ≈ 3–4 s after impact, the context window adds ≈ 1 s, the verifier takes 2–3 s, and the backend under 1 s. That is ≈ **7–9 s**.
  - Sweep path: ≤ 5 s wait + 2–3 s ≈ **≤ 8 s**.
  - **Measure on day 1** (TQ-02). If the verifier p95 is above 6 s, slow the sweep or use Qwen3-VL-4B for the sweep.

## 8. Licensing

- **Core path: permissive only** (NFR-LIC-001):
  - RF-DETR, Qwen3-VL and vLLM: Apache-2.0;
  - supervision: MIT.
- **Optional, isolated:** the smoke/fire detector (`fire_smoke_box` YOLO26n or D-Fire YOLOv5s; AGPL-derived).
  - Runs as a separate process.
  - Off by default in production; may be enabled for the public hackathon demo (D-06, D-16).
  - Must be replaced by a permissively licensed detector before any production contract.
- **`models.lock.yaml`** (TD-25): every weight is pinned with its licence. CI blocks AGPL or non-commercial models from being on by default in production.
- **Dropped:**
  - Cosmos-Reason2 (lost to Qwen3-VL; slow);
  - VideoMAE UCF-Crime (non-commercial);
  - Ultralytics YOLO as the main detector (AGPL);
  - vehicle-damage models (non-commercial data);
  - thermal and person-exit modules (D-16).

## Key URLs

- ACCIDENT@CVPR 2026 1st place: https://arxiv.org/abs/2605.29325 · https://github.com/fuumin621/cvpr2026-accident-1st-place-solution
- Coarse-to-fine VLM + tracking: https://arxiv.org/abs/2608.08867 · Two-pass: https://arxiv.org/abs/2605.01512 · Baseline: https://arxiv.org/abs/2604.09685
- AI City 2021 Track 4 baseline: https://arxiv.org/abs/2104.06856 · Rule-based detection rate: https://arxiv.org/abs/1911.10037
- NVIDIA VSS alert verification: https://docs.nvidia.com/vss/vision-agent/agent-workflows/alert-verification.md · RT-VLM performance: https://docs.nvidia.com/vss/3.2.0/performance-rt-vlm.html
- Speed calibration sensitivity (Revaud et al., ICCV 2021): https://openaccess.thecvf.com/content/ICCV2021/papers/Revaud_Robust_Automatic_Monocular_Vehicle_Speed_Estimation_for_Traffic_Surveillance_ICCV_2021_paper.pdf
- Qwen3-VL-8B-FP8: https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-FP8 · vLLM Qwen3-VL recipe: https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html
- RF-DETR: https://github.com/roboflow/rf-detr · supervision: https://github.com/roboflow/supervision
- Fire/smoke: https://huggingface.co/weslleyskah/fire_smoke_box · https://github.com/pedbrgs/Fire-Detection
- Datasets: TAD https://arxiv.org/abs/2209.12386 · CADP https://ankitshah009.github.io/accident_forecasting_traffic_camera · TU-DAT https://github.com/pavana27/TU-DAT · UCF-Crime https://www.crcv.ucf.edu/projects/real-world/
- Thermal through glass: https://armasight.com/armasight-university/why-thermal-imaging-devices-dont-see-through-glass-and-other-common-questions-/ · ThermEval: https://www.alphaxiv.org/abs/2602.14989.md
