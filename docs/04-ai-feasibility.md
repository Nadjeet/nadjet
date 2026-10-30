# 04 — AI and Technical Feasibility (with evidence)

**Labels used in this document:**
- **[V]** verified on the web on 2026-10-29.
- **[K]** established knowledge that was not re-checked this session.
- **[E]** an estimate. We must measure these numbers ourselves.

## 1. The core truth: vehicle detection is not accident detection

- A COCO detector (YOLO, RF-DETR) finds *cars, trucks, buses, motorcycles and people*. It has **no idea whether a crash happened**.
- I found **no credible, downloadable, CCTV-specific accident model** [V]. What exists:
  - **Roboflow Universe "accident" detectors.** Their high mAP is inflated: they are trained on frames from a few videos, with random image splits. The class "accident" is also ill-defined.
  - **Kaggle CCTV accident frame sets.** Papers report heavy near-duplicate leakage between train and test splits [V].
  - **Nexar / CCD / DAD / DoTA / MM-AU.** These are **dashcam** footage, which is the wrong viewpoint for fixed cameras.
  - **`OPear/videomae-large-finetuned-UCF-Crime`.** A real video model with a "Road Accidents" class, but it is multi-class crime, the evaluation split is unclear, and the licence is **CC-BY-NC-4.0** [V].

So accident detection must be **built as a pipeline**, and part of it must be **trained by us**.

## 2. Recommended hybrid pipeline (evidence-based)

```
decode @ 5–10 fps per camera
  → [S1] COCO detector (vehicles, persons)                         proven
  → [S2] tracker + homography speed + lane/zone polygons           proven
  → [S3] behaviour triggers (high recall, cheap)                   proven on highway CCTV
  → [S4] crash verifier on ±2 s clip around involved tracks         trained by us, partially proven
  → [S5] VLM description on 4–8 keyframes (async, advisory)        experimental
  → incident candidate → human verification
```

### Evidence per stage

| Stage | Evidence | Limits |
|---|---|---|
| S1 detector | YOLO11/YOLO26 and RF-DETR are mature. RF-DETR on a T4 with TensorRT FP16 runs N in 2.3 ms and S in 3.5 ms per frame [V]. | Small vehicles far away, night, rain. |
| S2 tracking | ByteTrack, BoT-SORT and OC-SORT are standard (MIT) [K]. `supervision` provides `ByteTrack`, `PolygonZone` and homography-based speed (official example) [K]. | Identity switches under occlusion can look like sudden stops. |
| S3 triggers | **AI City Challenge 2021 Track 4** targeted crashes and stalled vehicles on 100/150 highway CCTV videos. Winners used detection, tracking, background modelling and rules: **F1 0.9524** (Zhao et al.) and 0.9157 (4th place) [V]. | They detect *anomalies*, not "crash" specifically. Traffic jams and camera shake are the main false-positive sources, so normalise against the rest of the traffic and detect global motion. |
| S4 verifier | Transformer video classifiers on CCTV accident clips report about 88–93% clip accuracy (arXiv 2512.11350; OPear model card) [V]. | Small datasets, possible leakage, domain shift to Algerian cameras. **We must evaluate it ourselves** on held-out videos. |
| S5 VLM | ACCIDENT@CVPR 2026 benchmark (2,027 real CCTV clips) [V]. Best baseline 0.412. Qwen3-VL-32B + YOLO11x + BoT-SORT scores 0.504. A two-pass VLM pipeline scores 0.539. | Even 32B VLMs are unreliable on collision type. Small local VLMs hallucinate damage on low-resolution footage. **Description only, never the trigger.** |

### Why this design is honest

- Every alert traces back to **measurable signals**: tracks, speeds, overlaps, a classifier probability. We show them in the incident card ("why was this flagged").
- Event types are named honestly:
  - `stalled_vehicle`, `pedestrian_on_road` and `wrong_way` come from rules, which is proven.
  - `collision` is used **only** when S4 agrees.
- **A human verifies before dispatch.** The AI shortens time-to-awareness; it does not replace judgement.

## 3. S3 trigger definitions (starting values, tune on the training split)

| Trigger | Signal | Starting threshold |
|---|---|---|
| `collision_candidate` | Two tracks with IoU > 0.05 (or centre distance < 0.6 × mean box width), **then both** have speed < 1.5 m/s for ≥ 3 s | — |
| `hard_stop` | Speed drops by > 6 m/s within ≤ 1.5 s, and < 30% of the other tracks slow down | — |
| `stalled_vehicle` | Vehicle stationary ≥ 20 s inside a `live_lane` polygon while other tracks still move | — |
| `pedestrian_on_road` | A person inside a `carriageway` polygon for ≥ 2 s on a highway camera | — |
| `wrong_way` (A1) | Heading differs from the lane flow vector by > 120° for ≥ 2 s | — |
| `scene_shock` | Global optical-flow or frame-difference z-score spike, *with no* global camera motion | z > 4 |

**Suppression rules:**
- Mute during global camera motion (PTZ / shake).
- Apply a per-camera cooldown per location (also handles video loop restarts).
- Require N consecutive confirmations.

## 4. S4 crash verifier: training plan

1. **Data (CCTV only):**
   - **TAD** (333 videos; repo moved to `UnicomAI/UnicomBenchmark/TADBench`)
   - **CADP** (1,416 segments)
   - **TU-DAT** (~210 real videos)
   - **UCF-Crime RoadAccidents** (150) plus UCF-Crime normal videos as negatives
   - AI City Track 4 if access is granted

   All are research or non-commercial use only, which is acceptable for a prototype; flag this for production.
2. **Clips.** 2–4 s windows. Positives are around annotated impact times. Hard negatives: jams, slow traffic, parked vehicles, night glare, normal intersections.
3. **Model.** VideoMAE-B, pretrained on Kinetics (`MCG-NJU/videomae-base-finetuned-kinetics`), fine-tuned with binary output. **Fallback:** an EfficientNet-B0 frame classifier over 3 stacked keyframes, which is faster to train.
4. **Split by source video and camera, never by frame.** Hold out 20–30% of videos. **The demo clips must come from the held-out set.**
5. **Compute.**
   - VideoMAE-B training: a few GPU-hours on one consumer NVIDIA GPU, or a free cloud notebook (Kaggle/Colab) [E].
   - Inference: about 50 ms per clip on Apple MPS and about 10 ms on an RTX GPU [E]. It runs only on triggers.

## 5. Honest evaluation protocol (shown in the pitch)

- **Event-level metrics.** A true positive (TP) is an alert within [t_impact − 2 s, t_impact + 10 s] that overlaps the annotated region. Report precision, recall, F1 and median detection delay.
- **False alarms per camera-hour** on long normal footage that includes congestion, night and rain. This is the number operators care about.
- **Ablation:** S3 alone vs S3 + S4 vs S3 + S4 + S5.
- **Confusion breakdown:** crash vs stall vs jam vs camera motion.
- **Bootstrap 95% confidence intervals.** With about 50–100 test events they will be wide; say so.
- **Publish an evaluation script** (`vision/eval/run_eval.py`) so the jury can rerun it.

## 6. Severity and priority (decision support, not medical prediction)

`priority = f(observable signals)`, displayed with its reasons:

| Signal | Source | Weight idea |
|---|---|---|
| Vehicles involved ≥ 2 | Tracks | + |
| Heavy vehicle or **bus** involved | Detector class | ++ (bus = possible mass casualty) |
| Estimated pre-impact speed > 80 km/h | Homography speed | ++ |
| Vehicle stopped in a live lane (secondary-crash risk) | Zones | + |
| Person on the carriageway | Detector + zone | ++ |
| Overturned / smoke (VLM or fire model, if available) | S5 / A2 | ++ (advisory) |
| Night / highway | Camera metadata + clock | + |

The result is P1–P4 with the reasons shown. After responders send triage (START tags), **priority is recomputed from real triage data**, which overrides the AI estimate.

## 7. Runtime feasibility on a laptop

| Hardware | Detector + tracker | Streams at 5–10 fps [E] |
|---|---|---|
| Apple M2/M3 Pro, CoreML (`format=coreml`) | ~6–15 ms/frame | 4–8 |
| Same, PyTorch MPS | 2–3× slower | 3–4 |
| RTX 4060/4070 laptop, TensorRT FP16 | ~2–4 ms/frame | 10+ (CPU decode becomes the bottleneck) |

**Target demo:** 4 cameras at 5 fps on one MacBook Pro. **Benchmark this on day 1.**

The VLM runs in a separate queue. A 7–8B model at Q4 takes about 3–10 s per query on an M-series Mac [E], which is fine for a few incidents per minute.

## 8. Licensing decisions

- **Ultralytics YOLO11/YOLO26: AGPL-3.0** [V]. Fine for an open hackathon repository. A government product requires an Enterprise licence or a switch of detector.
- **Recommendation:** put the detector behind a `Detector` interface.
  - Hackathon: Ultralytics YOLO11s (one-line CoreML export, built-in tracking).
  - Production: **RF-DETR (Apache-2.0)** or D-FINE/DEIM (Apache-2.0).
- **supervision, ByteTrack, OC-SORT, BoT-SORT:** MIT [K].
- **VLMs:**
  - Qwen2.5-VL-7B and Qwen3-VL: Apache-2.0 [K].
  - **Qwen2.5-VL-3B uses a research licence.**
  - Florence-2: MIT.
  - SmolVLM2 and Moondream2: Apache-2.0.
- **Datasets:** research / non-commercial. Retrain on Algerian footage under a government agreement for production.

## Key URLs

- AI City 2021 Track 4 strong baseline: https://arxiv.org/abs/2104.06856 · https://openaccess.thecvf.com/content/CVPR2021W/AICity/papers/Zhao_Good_Practices_and_a_Strong_Baseline_for_Traffic_Anomaly_Detection_CVPRW_2021_paper.pdf
- ACCIDENT@CVPR 2026 benchmark: https://openaccess.thecvf.com/content/CVPR2026W/AUTOPILOT/supplemental/Picek_ACCIDENT_A_Benchmark_CVPRW_2026_supplemental.pdf · pipelines: https://arxiv.org/abs/2608.08867 · https://arxiv.org/abs/2605.01512
- Zero-shot CCTV accident understanding: https://arxiv.org/abs/2604.09685
- MLLM accident study (infrastructure view): https://arxiv.org/abs/2509.19096
- Transformer CCTV accident study: https://arxiv.org/abs/2512.11350
- TAD: https://arxiv.org/abs/2209.12386 · https://github.com/UnicomAI/UnicomBenchmark/tree/main/TADBench
- CADP: https://ankitshah009.github.io/accident_forecasting_traffic_camera
- TU-DAT: https://github.com/pavana27/TU-DAT
- UCF-Crime: https://www.crcv.ucf.edu/projects/real-world/
- VideoMAE UCF-Crime: https://huggingface.co/OPear/videomae-large-finetuned-UCF-Crime · HF video classification: https://huggingface.co/docs/transformers/tasks/video_classification
- RF-DETR: https://github.com/roboflow/rf-detr · Ultralytics licence: https://www.ultralytics.com/license · CoreML export: https://docs.ultralytics.com/integrations/coreml/
- supervision: https://github.com/roboflow/supervision · ByteTrack: https://github.com/ifzhang/ByteTrack
- Local VLMs: https://ollama.com/library/qwen2.5vl · https://github.com/Blaizzy/mlx-vlm
