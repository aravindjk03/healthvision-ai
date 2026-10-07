# 03 — AI Architecture

## 1. Model inventory (brief §41)

| ID | Model | Type | V1 default | Replaceable by |
|---|---|---|---|---|
| A | BMI calculation | Deterministic formula (no ML) | `BmiService` | Another reference table (config) |
| B | Face detector | CNN detector | **YuNet** (OpenCV Zoo, `face_detection_yunet_2023mar.onnx`) | MediaPipe BlazeFace, RetinaFace (ONNX), SCRFD |
| C | Face landmarks | Landmark regressor | **MediaPipe Face Landmarker** (478 pts + blendshapes, `face_landmarker.task`) run on detector crop | dlib-free 68-pt ONNX, InsightFace 2d106 (license review) |
| D | Expression classifier | Image classifier | **FER+ (ONNX Model Zoo `emotion-ferplus-8`)** | HSEmotion EfficientNet (AffectNet — license review), custom fine-tuned model |
| E | Recognition embedding | Metric-learning embedder | **SFace** (OpenCV Zoo, `face_recognition_sface_2021dec.onnx`, 128-D) | ArcFace R100/R50 ONNX (license review), AdaFace, MagFace |
| F | Liveness | Presentation-attack detector | **Not implemented** (`NotImplementedLivenessEngine`) | Validated PAD model (V2) |

### Why these defaults (brief §13, §21, §67)

| Criterion | YuNet | FER+ ONNX | SFace | MediaPipe Landmarker |
|---|---|---|---|---|
| License | MIT (OpenCV Zoo) | MIT (ONNX Model Zoo) | Apache-2.0 (OpenCV Zoo) | Apache-2.0 |
| CPU suitability | Very high (~75k params) | High (64×64 grayscale input) | High (MobileFaceNet-class) | High (designed for mobile) |
| GPU required | No | No | No | No |
| Deployment | `cv2.FaceDetectorYN` — no extra runtime | ONNX Runtime | `cv2.FaceRecognizerSF` or ORT | `mediapipe` wheel |
| Edge portability | Excellent | Excellent | Excellent | Good (Jetson via CPU) |
| Known weakness | Small/very angled faces | Low-res grayscale input; modest accuracy; FER+ demographic skew | Lower accuracy than large ArcFace models | Heavy occlusion |

These are **chosen for license clarity and CPU deployment, not for top benchmark scores** (brief §67). Before any production claim, each must pass [13_MODEL_VALIDATION.md](13_MODEL_VALIDATION.md). Candidates with stronger accuracy but restrictive licenses (InsightFace `buffalo_l` model weights: non-commercial research; AffectNet-trained weights: dataset terms restrict commercial use) are listed in the registry with `license_status: REVIEW_REQUIRED` and are not loadable unless `allow_restricted_licenses: true` is set by an administrator.

## 2. AI pipeline overview

```
image bytes
   │  ImageIngest: decode, EXIF orient, RGB, size check, sha256(input)
   ▼
global quality (resolution, brightness, global blur) ──► POOR → RETAKE
   ▼
[B] FaceDetector.detect(img) → [FaceDetection(bbox, score, kps5)]
   ▼  count gate (NO_FACE / ONE_FACE / MULTIPLE_FACES)
[C] LandmarkEngine.landmarks(img, bbox) → Landmarks(points, visibility, pose)
   ▼
face quality (face size, face blur, occlusion, pose) ──► POOR → RETAKE
   ▼
Aligner.align(img, kps5) ──► aligned crops (expression: 64×64 gray; recognition: 112×112 RGB)
   ├──► [D] ExpressionEngine.predict(crop) → probs[] → DecisionEngine.expression()
   └──► [F] Liveness (NOT_PERFORMED) → [E] EmbeddingModel.embed(crop) → vec
                                         → TemplateStore compare → DecisionEngine.recognition()
```

## 3. Engine interfaces (contract for every adapter)

Defined in `engines/base.py`. All engines are **stateless after load**, thread-safe for inference, and return plain dataclasses (no framework objects).

```text
class EngineInfo:            # returned by every engine, fed from registry
    model_id: str            # e.g. "face_detector.yunet"
    version: str             # e.g. "2023mar"
    sha256: str
    input_size: tuple
    runtime: str             # "opencv-dnn" | "onnxruntime" | "mediapipe"

interface FaceDetector:
    info() -> EngineInfo
    detect(image_rgb: ndarray[H,W,3] uint8) -> list[FaceDetection]
        FaceDetection:
            bbox: (x, y, w, h) in pixels, clipped to image
            score: float in [0,1]      # raw detector confidence
            keypoints5: [(x,y)]*5 | None   # R-eye, L-eye, nose, R-mouth, L-mouth

interface LandmarkEngine:
    info() -> EngineInfo
    landmarks(image_rgb, detection: FaceDetection) -> Landmarks | None
        Landmarks:
            points: ndarray[N,2] float (image coords)
            scheme: str                 # "mediapipe_478"
            visibility: float in [0,1]  # fraction of key regions judged visible
            region_visibility: {eyes, nose, mouth, jaw: float}
            pose: {yaw, pitch, roll} degrees (solvePnP on canonical 3D model)
            keypoints5: [(x,y)]*5       # derived, for alignment

interface ExpressionEngine:
    info() -> EngineInfo
    labels() -> list[str]               # model-native labels
    predict(aligned_face) -> dict[label, prob]   # softmax, sums to 1

interface EmbeddingModel:
    info() -> EngineInfo
    embed(aligned_face_112) -> ndarray[D] float32, L2-normalized
    similarity(a, b) -> float           # cosine; defined by model family

interface LivenessEngine:
    info() -> EngineInfo
    assess(frames) -> LivenessResult(status: NOT_PERFORMED|LIVE|SPOOF|UNCERTAIN, score|None)
    # V1 implementation always returns NOT_PERFORMED, score None
```

Rules:
- Engines **never** apply product thresholds or produce user-facing text. They return raw scores; `DecisionEngine` applies config.
- The only threshold an engine may receive is a **pre-filter** passed explicitly by the service (e.g., detector score floor) — sourced from config.
- Adapters register via an entry in `models/registry.yaml` with `adapter: healthvision.engines.detection.yunet:YuNetDetector`.

## 4. Alignment

- Use the 5-point similarity transform (`cv2.estimateAffinePartial2D`) to the ArcFace canonical 112×112 template:
  `[(38.2946,51.6963),(73.5318,51.5014),(56.0252,71.7366),(41.5493,92.3655),(70.7299,92.2041)]`.
- Expression crop: from aligned 112×112 take centre crop, convert to grayscale, resize to 64×64 (FER+ input), no normalization beyond what the model card specifies (FER+ expects raw 0–255 float).
- Keypoint source priority: landmark-derived 5 points (more stable) → detector keypoints → fail with `ALIGNMENT_FAILED` (expression NOT_AVAILABLE).

## 5. DecisionEngine (score → state)

Pure, deterministic, unit-tested. Every call returns `(state, DecisionTrace)`:

```text
DecisionTrace:
  rule_id: str                # e.g. "expression.v1"
  inputs: {raw scores}
  thresholds: {name: value}   # values actually used
  threshold_source: "config" | "calibration_file" | "demo_uncalibrated"
  config_version: str
  outcome: str
  reasons: [str]
```

### 5.1 Expression decision (rule `expression.v1`)
```
if face_state != ONE_FACE or quality == POOR or alignment failed:
    status = NOT_AVAILABLE
else:
    p = map model labels -> product classes via class_map; drop null; renormalize if configured
    p = temperature_scale(p, T)            # T from calibration (default 1.0)
    top1, top2 = two highest
    if top1.prob < moderate_threshold or (top1.prob - top2.prob) < min_top2_margin:
        status = UNCERTAIN; label = None
    else:
        status = ESTIMATED; label = top1.class
        band = HIGH if top1.prob >= high_threshold else MODERATE
    if quality == ACCEPTABLE and band == HIGH: band = MODERATE   # quality caps confidence band
```
Displayed confidence = calibrated `top1.prob` as a percentage, labelled "model confidence (not a probability of emotion)".

### 5.2 Recognition decision (rule `recognition.v1`)
```
inputs: best_similarity over user's templates (max), thresholds T_match, T_nomatch (T_nomatch < T_match)
if best >= T_match:   MATCH
elif best < T_nomatch: NO_MATCH
else:                 UNCERTAIN
if threshold_source == demo_uncalibrated: flag DEMO_UNCALIBRATED on result
```
Never output "identified as X" in verification mode; output "Matches your enrolled identity" / "Does not match" / "Uncertain — please retry".

### 5.3 Face-count decision (rule `face_count.v1`)
```
faces = [d for d in detections if d.score >= face_detection_threshold]
secondary = [d for d in detections if d.score >= min_secondary_face_confidence]
if len(faces) == 0: NO_FACE
elif len(secondary) > 1: MULTIPLE_FACES      # conservative: a weaker 2nd face still blocks
else: ONE_FACE
```

## 6. Explicit non-goals of the AI layer

The AI layer does **not** output: identity from detection, age, gender, ethnicity, attractiveness, health, disease risk, mental state, personality, honesty, or any derived "score". Blendshapes from MediaPipe are used **only** as optional auxiliary features for occlusion/visibility checks — never displayed as emotions.

## 7. Model registry (brief §42)

`models/registry.yaml` — one entry per model artifact. Loaded and validated at startup; exposed (minus file paths) by `GET /model-info`.

```yaml
models:
  - model_id: face_detector.yunet
    model_type: FACE_DETECTOR            # FACE_DETECTOR|LANDMARKS|EXPRESSION|EMBEDDING|LIVENESS
    name: YuNet
    version: "2023mar"
    source: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
    license: MIT
    license_status: APPROVED             # APPROVED | REVIEW_REQUIRED | REJECTED
    file: models/face_detection_yunet_2023mar.onnx
    sha256: "<fill on fetch>"
    adapter: healthvision.engines.detection.yunet:YuNetDetector
    deployment_format: onnx
    runtime: opencv-dnn
    input_size: [320, 320]               # dynamic; set per image
    training_validation_date: "vendor: 2023-03; local validation: PENDING"
    performance_metrics:                 # filled ONLY from tools/evaluate_* outputs
      vendor_reported: {widerface_ap: "copy from OpenCV Zoo model card at fetch time"}
      local_validated: null
    thresholds_ref: config.face_detection
    known_limitations:
      - "Reduced recall on faces < 30 px and extreme profiles"
      - "Not validated locally for skin-tone / lighting subgroups (PENDING)"

  - model_id: landmarks.mediapipe_face_landmarker
    model_type: LANDMARKS
    version: "float16/1"
    license: Apache-2.0
    deployment_format: task
    # ...

  - model_id: expression.ferplus
    model_type: EXPRESSION
    version: "onnx-opset8"
    source: https://github.com/onnx/models/tree/main/validated/vision/body_analysis/emotion_ferplus
    license: MIT
    input_size: [64, 64, 1]
    labels: [neutral, happiness, surprise, sadness, anger, disgust, fear, contempt]
    performance_metrics: {vendor_reported: {fer_plus_test_accuracy: "see model card"}, local_validated: null}
    known_limitations:
      - "Trained on low-resolution grayscale web images; posed expressions over-represented"
      - "Disgust and fear classes have low support"
      - "Not an emotion detector"

  - model_id: embedding.sface
    model_type: EMBEDDING
    version: "2021dec"
    license: Apache-2.0
    input_size: [112, 112, 3]
    embedding_dim: 128
    similarity: cosine
    performance_metrics: {vendor_reported: {lfw_accuracy: "see model card"}, local_validated: null}
    known_limitations: ["No liveness", "Accuracy below large ArcFace models", "Threshold must be calibrated locally"]

  - model_id: liveness.none
    model_type: LIVENESS
    version: "none"
    status: NOT_IMPLEMENTED
```

Rules:
- `performance_metrics.local_validated` is written **only** by evaluation tools from real runs, with dataset name, size, date and git commit. UI shows "Not locally validated" when null.
- `vendor_reported` metrics are shown as "vendor-reported", never as HealthVision accuracy.
- SHA-256 mismatch → model disabled, audit `MODEL_INTEGRITY_FAILURE`.
- Any change in a model's `version` or `sha256` versus the last start → audit `MODEL_CHANGE`.

## 8. Model selection criteria template (brief §67)

Every candidate model gets a scorecard in `docs/model_cards/<model_id>.md` (created when evaluated):

| Criterion | How measured |
|---|---|
| Accuracy | Task metrics in [13](13_MODEL_VALIDATION.md) on the local validation set |
| Latency | `tools/benchmark_latency.py`, median & p95 over 200 runs, after warm-up |
| CPU performance | Same, on reference laptop |
| GPU performance | Same, with CUDA/DirectML EP (V2) |
| Memory usage | Peak RSS delta on load + inference |
| License | Code license AND weights license AND training-data terms |
| Privacy implications | Does it need network? Telemetry? Does it output protected attributes? |
| Model size | File size MB |
| Deployment difficulty | Extra native deps? Windows/macOS/Linux/Jetson support |
| Supported platforms | Tested matrix |
| Subgroup performance | Bias metrics per [13](13_MODEL_VALIDATION.md) §5 |

Decision rule: a candidate replaces the default only if it is **license-approved**, meets latency budget on the reference laptop, and improves the primary metric without worsening the worst-subgroup metric.

## 9. Performance measurement (brief §51)

`LatencyRecorder` records per request (ms, from `time.perf_counter_ns`):

```
capture_upload_ms   (client-measured, sent as header X-Client-Capture-Ms)
decode_ms
quality_global_ms
detection_ms
landmark_ms
quality_face_ms
alignment_ms
expression_ms
liveness_ms         (0 / "not performed")
embedding_ms
comparison_ms
total_pipeline_ms   (server side, ingest → decision)
```

- Stored in `analysis_session.latency_json`; shown on dashboard as "Detection: 14 ms" etc.
- **No latency number may appear in docs, UI copy or webinar slides unless it came from this recorder or `tools/benchmark_latency.py`.**
- Provisional budget (to be confirmed by benchmark, not promised): total face analysis "responsive" = under ~1 s on the reference laptop CPU.
