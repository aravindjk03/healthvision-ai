# 05 — Face Analysis Architecture

Covers brief §13–19, §36, §45, §57–58: detection, multiple faces, quality, landmarks, pose, expression.

## 1. Diagram 3 — Face pipeline

```
 Camera frame / uploaded file
        │
        ▼
 ConsentService.require(FACE_ANALYSIS) ── no → 403 CONSENT_REQUIRED
        │
        ▼
 ImageIngest
   • MIME sniff (JPEG/PNG only), size ≤ max_upload_bytes
   • decode (OpenCV), apply EXIF orientation (Pillow), convert to RGB
   • reject > max_image_side_px; downscale working copy to ≤ 1280 px long side
   • input_sha256 = sha256(original bytes)   (hash kept; bytes are NOT persisted)
        │
        ▼
 Global quality: resolution, brightness, global blur ── POOR → RETAKE (stop)
        │
        ▼
 [B] FaceDetector.detect()
        │
        ▼
 Face-count gate ── NO_FACE → "No face detected…" (stop)
        │          ── MULTIPLE_FACES → "Multiple faces detected…" (stop)
        ▼ ONE_FACE
 [C] LandmarkEngine.landmarks(crop of the single face, padded 25%)
        │          ── None → quality.visibility = POOR → RETAKE
        ▼
 Face quality: face size, face blur, occlusion/visibility, pose ── POOR → RETAKE
        │
        ▼
 Aligner (5-pt similarity) ── fail → expression NOT_AVAILABLE
        │
        ▼
 [D] ExpressionEngine → DecisionEngine.expression() → ESTIMATED / UNCERTAIN
        │
        ▼
 FaceAnalysisResult (+ traces, latency) → persist expression_result & face_observation
 Image buffers zeroed and released (features.store_raw_images = false)
```

## 2. Face detection (brief §13)

The detector answers only **"Where is the face?"**. Output:

```json
{
  "face_count": 1,
  "face_state": "ONE_FACE",
  "faces": [
    {"face_index": 0, "bbox": {"x": 412, "y": 188, "w": 236, "h": 301}, "detection_confidence": 0.94}
  ],
  "detector": {"model_id": "face_detector.yunet", "version": "2023mar"},
  "threshold": {"face_detection_threshold": 0.80, "source": "config"}
}
```

- Interchangeable via `face_detection.engine` and registry. Adapters required in V1: `yunet` (default). Adapter skeletons for `mediapipe` and `retinaface` must exist and pass the same contract tests (may be marked `experimental`).
- YuNet: call `setInputSize((w, h))` per image; `setScoreThreshold` set to `min_secondary_face_confidence` (the lower value) so weaker secondary faces are still seen by the face-count rule.
- Detector output is never used for identity, expression, or any attribute.

## 3. Multiple faces (brief §14)

| State | Rule (03 §5.3) | Behaviour |
|---|---|---|
| `NO_FACE` | no detection ≥ `face_detection_threshold` | Stop. "No face detected. Please retake the image." |
| `ONE_FACE` | exactly one detection ≥ `min_secondary_face_confidence` | Continue |
| `MULTIPLE_FACES` | > 1 detection ≥ `min_secondary_face_confidence` | Stop. "Multiple faces detected. Please ensure only one person is in frame." Bounding boxes drawn on preview; **no** landmarks/expression/recognition on any face |

- BMI + expression flow **always** requires one face; there is no "pick the largest face" fallback (prevents analyzing a bystander).
- Recognition **enrollment/verification**: also requires ONE_FACE in V1.
- Future (only if `identification_enabled` and explicitly deliberate): API accepts `target_face_index` after the user taps a face in the preview; the service re-runs the pipeline on that face only and records `target_selected_by_user = true` in the trace. Not used in V1.

## 4. Image quality engine (brief §15)

Two phases. Each check yields `GOOD | ACCEPTABLE | POOR` plus a measured value; overall grade = **worst** check (`grade_policy: worst_check`).

| Check | Phase | Metric | GOOD | ACCEPTABLE | POOR |
|---|---|---|---|---|---|
| Resolution | global | short side px | ≥ 720 | ≥ `min_image_short_side_px` (480) | below |
| Brightness | global + face | mean luminance (Y of YCrCb) on face crop | within [min_mean+20, max_mean−20] | within [min_mean, max_mean] | outside |
| Contrast (aux) | face | std of Y on face crop | ≥ 40 | ≥ 25 | < 25 |
| Blur | face | variance of Laplacian on 112×112 aligned gray crop | ≥ `laplacian_var_good` | ≥ `laplacian_var_min` | below |
| Face size | face | min(bbox w, h) px in original image | ≥ 1.5 × `minimum_face_size_px` | ≥ `minimum_face_size_px` | below |
| Face visibility | face | bbox fully inside frame (≥ 95 % area) | inside | 90–95 % | < 90 % |
| Occlusion | face | landmark `visibility` & `region_visibility` (eyes, nose, mouth) | ≥ 0.95 all | ≥ `min_landmark_visibility` | below (e.g., mask, hand over mouth) |
| Pose | face | yaw/pitch/roll from solvePnP | within *_good | within *_max | beyond |

All numeric values come from config `quality.*` (values above are the example config, marked PROVISIONAL until tuned on the validation set — [13](13_MODEL_VALIDATION.md) §2).

Output:

```json
{
  "grade": "GOOD",
  "checks": [
    {"check": "brightness", "value": 128.4, "grade": "GOOD"},
    {"check": "blur", "value": 241.7, "grade": "GOOD"},
    {"check": "pose", "value": {"yaw": 4.1, "pitch": -2.3, "roll": 1.0}, "grade": "GOOD"}
  ],
  "action": "PROCEED"            // PROCEED | PROCEED_WITH_CAUTION | RETAKE
}
```

POOR → `action: RETAKE`, UI shows **"REVIEW / RETAKE IMAGE"** with the failing checks in plain language ("Image is too dark", "Face is turned too far — please look at the camera").

## 5. Landmark engine (brief §16)

- MediaPipe Face Landmarker (IMAGE mode), `num_faces = 1`, run on padded crop; points mapped back to image coordinates.
- Uses: (1) alignment keypoints (eye centres = mean of iris/eye-contour points, nose tip, mouth corners), (2) pose estimation via `cv2.solvePnP` with a 6-point canonical 3D face model (nose tip, chin, eye outer corners, mouth corners), (3) occlusion/visibility via region presence and landmark-confidence heuristics, (4) expression alignment.
- Landmarks are **geometry only**. They are not stored by default (`store_landmarks: false`); the result keeps pose angles and visibility scores only. No facial-geometry "health" interpretation, no facial-symmetry scoring, no attractiveness metrics.

## 6. Expression engine (brief §17–19, §45)

### 6.1 Diagram 4 — Expression pipeline (traceable, brief §73)

```
Image
  ↓
Face detected (ONE_FACE, score 0.94)
  ↓
Face quality acceptable (GOOD)
  ↓
Landmarks detected (visibility 0.98, yaw 4°)
  ↓
Aligned 64×64 grayscale crop
  ↓
Expression model (FER+ ONNX)  → raw probs {happiness .91, neutral .05, …}
  ↓
class_map + renormalize + temperature T
  ↓
Configured thresholds (high .85, moderate .60, margin .15)
  ↓
Expression = HAPPY estimate, band HIGH, status ESTIMATED
```

### 6.2 Classes
Configurable list (`expression.classes`) with a model-label → product-class map. Default: HAPPY, NEUTRAL, SAD, SURPRISED, ANGRY, FEARFUL, DISGUSTED. FER+ `contempt` maps to `null` (excluded, probability mass removed then renormalized; the excluded mass is recorded in the trace — if excluded mass > 0.5 the status is forced to UNCERTAIN).

### 6.3 Confidence policy (brief §19)

| Calibrated top-1 prob | Band | Status | UI |
|---|---|---|---|
| ≥ 0.85 | HIGH | ESTIMATED | "Facial expression estimate: Happy — high-confidence estimate (91%)" |
| 0.60 – 0.84 | MODERATE | ESTIMATED | "Facial expression estimate: Happy — moderate-confidence estimate (72%)" |
| < 0.60 or margin < 0.15 | — | UNCERTAIN | "Expression could not be estimated reliably from this image." + REVIEW |
| pipeline stopped | — | NOT_AVAILABLE | reason (no face / multiple faces / poor quality / alignment failed) |

Quality ACCEPTABLE caps the band at MODERATE.

### 6.4 Three-state result (brief §58)

```json
{
  "status": "ESTIMATED",                 // ESTIMATED | UNCERTAIN | NOT_AVAILABLE
  "expression": "HAPPY",                 // null unless ESTIMATED
  "confidence": 0.91,
  "confidence_band": "HIGH",             // HIGH | MODERATE | null
  "probabilities": {"HAPPY": 0.91, "NEUTRAL": 0.05, "SURPRISED": 0.02, "SAD": 0.01, "ANGRY": 0.005, "FEARFUL": 0.003, "DISGUSTED": 0.002},
  "observation": "Visible facial expression is consistent with a happy-expression classification.",
  "note": "Facial expression is an AI estimate based on visible facial features and should not be interpreted as a definitive measure of emotional state.",
  "not_available_reason": null,
  "model": {"model_id": "expression.ferplus", "version": "onnx-opset8"},
  "trace": { "rule_id": "expression.v1", "thresholds": {"high": 0.85, "moderate": 0.60, "min_top2_margin": 0.15, "temperature": 1.0}, "config_version": "1-3fa9c21b0d4e" }
}
```

### 6.5 Happiness result card (brief §18)

```
FACIAL EXPRESSION
Estimated:   Happy
Confidence:  91%  (high-confidence estimate)
Observation: Visible facial expression is consistent with a
             happy-expression classification.
```
Never: "Person is happy", "This proves…", mood, mental-health or personality language.

### 6.6 Webcam behaviour
- Live preview runs **client-side** only for framing guidance (oval overlay). No continuous server inference in V1.
- User presses CAPTURE → single JPEG (quality 0.92) posted to `/face/expression` (full pipeline) — or `/face/detect` for a quick pre-check.
- V2 option: capture 3 frames over 1 s and report the median-probability result (temporal smoothing) — record frame count in trace.

## 7. Fail-safe matrix (brief §57)

| Condition | Expression | Recognition | User message |
|---|---|---|---|
| No face | NOT_AVAILABLE | not run | "No face detected. Please retake the image." |
| Multiple faces | NOT_AVAILABLE | not run | "Multiple faces detected. Please ensure only one person is in frame." |
| Quality POOR | NOT_AVAILABLE | not run | "Image quality too low: {reasons}. Please retake." |
| Alignment failed | NOT_AVAILABLE | not run | "Could not align the face. Please face the camera." |
| Low confidence / small margin | UNCERTAIN | (independent) | "Expression could not be estimated reliably from this image." |
| Model unavailable | NOT_AVAILABLE | — | "Expression analysis is unavailable on this device." |

## 8. Face Analysis page behaviour (brief §36)

1. Choose Camera or Upload. Guidance text: "Position one face inside the frame."
2. Capture → `POST /face/detect` → shows "Face detected" + box, or the stop message.
3. ANALYZE → `POST /face/expression` → shows Face detected, Quality (grade + checks), Pose, Expression estimate, Confidence + band.
4. RETAKE available at every step. Results are added to the current analysis session.
