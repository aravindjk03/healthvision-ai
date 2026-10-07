"""FaceAnalysisService — detection → quality → landmarks → alignment → expression (docs/05)."""

from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from healthvision.config import Config
from healthvision.domain import (
    ConsentPurpose, DecisionTrace, ExpressionStatus, FaceState, QualityGrade, QualityResult, new_id, utcnow,
)
from healthvision.runtime import Engines
from healthvision.services import decision
from healthvision.services.consent import ConsentService
from healthvision.services.quality import FaceQualityService

MSG_NO_FACE = "No face detected. Please retake the image."
MSG_MULTIPLE = "Multiple faces detected. Please ensure only one person is in frame."
MSG_UNCERTAIN = "Expression could not be estimated reliably from this image."
EXPRESSION_NOTE = ("Facial expression is an AI estimate based on visible facial features and should not be "
                   "interpreted as a definitive measure of emotional state.")
ALLOWED_FORMATS = {"JPEG", "PNG"}


class ImageRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Timer:
    def __init__(self) -> None:
        self.ms: dict[str, float] = {}
        self._t0 = time.perf_counter()

    def stage(self, name: str):
        timer = self

        class _Ctx:
            def __enter__(self):
                self.t = time.perf_counter()

            def __exit__(self, *exc):
                timer.ms[name] = round((time.perf_counter() - self.t) * 1000, 1)

        return _Ctx()

    def total(self) -> None:
        self.ms["total_pipeline"] = round((time.perf_counter() - self._t0) * 1000, 1)


@dataclass
class FacePipelineOutput:
    purpose: str
    observation_id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=utcnow)
    input_sha256: str = ""
    image_size: tuple[int, int] = (0, 0)
    face_state: FaceState | None = None
    faces: list[dict[str, Any]] = field(default_factory=list)
    detection_trace: DecisionTrace | None = None
    quality_global: QualityResult | None = None
    quality_face: QualityResult | None = None
    landmarks: dict[str, Any] | None = None
    pose: dict[str, float] | None = None
    message: str | None = None
    stopped_reason: str | None = None
    models: dict[str, str] = field(default_factory=dict)
    latency_ms: dict[str, float] = field(default_factory=dict)
    aligned: np.ndarray | None = None          # memory only; never persisted or returned to the UI
    preview: np.ndarray | None = None          # annotated preview for display only; never persisted

    @property
    def quality_grade(self) -> QualityGrade | None:
        grades = [q.grade for q in (self.quality_global, self.quality_face) if q is not None]
        if not grades:
            return None
        if QualityGrade.POOR in grades:
            return QualityGrade.POOR
        return QualityGrade.ACCEPTABLE if QualityGrade.ACCEPTABLE in grades else QualityGrade.GOOD

    @property
    def proceeded(self) -> bool:
        return self.stopped_reason is None


@dataclass
class FaceAnalysisResult:
    pipeline: FacePipelineOutput
    result_id: str = field(default_factory=new_id)
    status: ExpressionStatus = ExpressionStatus.NOT_AVAILABLE
    expression: str | None = None
    confidence: float | None = None
    confidence_band: str | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    observation: str | None = None
    not_available_reason: str | None = None
    note: str = EXPRESSION_NOTE
    trace: DecisionTrace | None = None
    config_version: str = ""


def decode_image(data: bytes, config: Config) -> tuple[np.ndarray, tuple[int, int], float, str]:
    up = config["upload"]
    if len(data) > up["max_upload_bytes"]:
        raise ImageRejected("IMAGE_TOO_LARGE", "Image file is too large (max 10 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        if fmt not in ALLOWED_FORMATS:
            raise ImageRejected("UNSUPPORTED_MEDIA", "Only JPEG and PNG images are supported.")
        w, h = img.size
        if max(w, h) > up["max_image_side_px"]:
            raise ImageRejected("IMAGE_TOO_LARGE", f"Image is larger than {up['max_image_side_px']} px.")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageRejected("IMAGE_DECODE_FAILED", "The image could not be read.") from exc
    rgb = np.asarray(img)
    original = (rgb.shape[1], rgb.shape[0])
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    longest = max(original)
    scale = 1.0
    if longest > up["working_max_side_px"]:
        factor = up["working_max_side_px"] / longest
        bgr = cv2.resize(bgr, (int(original[0] * factor), int(original[1] * factor)), interpolation=cv2.INTER_AREA)
        scale = 1 / factor
    return bgr, original, scale, hashlib.sha256(data).hexdigest()


def _annotate(img: np.ndarray, faces: list[Any], color: tuple[int, int, int]) -> np.ndarray:
    out = img.copy()
    for i, d in enumerate(faces):
        x, y, w, h = d.bbox
        cv2.rectangle(out, (x, y), (x + w, y + h), color, max(2, img.shape[1] // 300))
        cv2.putText(out, f"#{i + 1} {d.score:.2f}", (x, max(15, y - 8)), cv2.FONT_HERSHEY_SIMPLEX,
                    max(0.5, img.shape[1] / 1400), color, 2)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


class FaceAnalysisService:
    def __init__(self, config: Config, engines: Engines, consent: ConsentService):
        self.config = config
        self.engines = engines
        self.consent = consent
        self.quality = FaceQualityService(config)

    def run_pipeline(self, data: bytes, purpose: str) -> FacePipelineOutput:
        """Shared pipeline for analysis, enrollment and verification (no consent check here)."""
        out = FacePipelineOutput(purpose=purpose)
        timer = Timer()
        eng = self.engines
        if eng.detector is None:
            out.stopped_reason, out.message = "MODEL_UNAVAILABLE", "Face detection is unavailable on this device."
            return out
        with timer.stage("decode"):
            img, original, scale, digest = decode_image(data, self.config)
        out.input_sha256, out.image_size = digest, original
        out.models["detector"] = eng.detector.info().key
        out.models["landmarks"] = eng.landmarks.info().key

        with timer.stage("quality_global"):
            out.quality_global = self.quality.global_checks(img, original)

        with timer.stage("detection"):
            detections = eng.detector.detect(img)
        state, faces, out.detection_trace = decision.face_count(detections, self.config)
        out.face_state = state
        out.faces = [{"face_index": i,
                      "bbox": {k: int(round(v * scale)) for k, v in zip("xywh", d.bbox)},
                      "detection_confidence": round(d.score, 3)} for i, d in enumerate(faces)]
        color = (0, 170, 0) if state == FaceState.ONE_FACE else (0, 0, 220)
        out.preview = _annotate(img, faces, color)

        if out.quality_global.grade == QualityGrade.POOR:
            out.stopped_reason = "QUALITY_POOR"
            out.message = "Image quality too low: " + "; ".join(c.message for c in out.quality_global.failing)
        elif state == FaceState.NO_FACE:
            out.stopped_reason, out.message = "NO_FACE", MSG_NO_FACE
        elif state == FaceState.MULTIPLE_FACES:
            out.stopped_reason, out.message = "MULTIPLE_FACES", MSG_MULTIPLE
        if out.stopped_reason:
            timer.total()
            out.latency_ms = timer.ms
            return out

        face = faces[0]
        with timer.stage("landmarks"):
            lms = eng.landmarks.landmarks(img, face)
        if lms is not None:
            out.landmarks = {"detected": True, "scheme": lms.scheme, "visibility": lms.visibility,
                             "points": len(lms.points)}
            out.pose = lms.pose
        else:
            out.landmarks = {"detected": False, "scheme": eng.landmarks.info().model_id}
        with timer.stage("alignment"):
            aligned = eng.embedder.align(img, face, lms.keypoints5 if lms else None) if eng.embedder else None
        with timer.stage("quality_face"):
            out.quality_face = self.quality.face_checks(img, face, lms, aligned, scale)
        out.aligned = aligned
        if out.quality_face.grade == QualityGrade.POOR:
            out.stopped_reason = "QUALITY_POOR"
            out.message = "Image quality too low: " + "; ".join(c.message for c in out.quality_face.failing) + \
                          ". REVIEW / RETAKE IMAGE."
            out.aligned = None
        timer.total()
        out.latency_ms = timer.ms
        return out

    def analyze(self, data: bytes) -> FaceAnalysisResult:
        self.consent.require(ConsentPurpose.FACE_ANALYSIS)
        pipe = self.run_pipeline(data, purpose="FACE_ANALYSIS")
        result = FaceAnalysisResult(pipeline=pipe, config_version=self.config.version)
        eng = self.engines
        if not pipe.proceeded or pipe.aligned is None:
            result.not_available_reason = pipe.stopped_reason or "ALIGNMENT_FAILED"
            pipe.aligned = None
            return result
        if eng.expression is None:
            result.not_available_reason = "MODEL_UNAVAILABLE"
            pipe.aligned = None
            return result
        t0 = time.perf_counter()
        raw = eng.expression.predict(pipe.aligned)
        pipe.latency_ms["expression"] = round((time.perf_counter() - t0) * 1000, 1)
        pipe.latency_ms["total_pipeline"] = round(pipe.latency_ms.get("total_pipeline", 0) +
                                                  pipe.latency_ms["expression"], 1)
        pipe.models["expression"] = eng.expression.info().key
        pipe.aligned = None                                   # release face crop immediately
        d = decision.expression(raw, pipe.quality_grade or QualityGrade.POOR, self.config)
        result.status, result.trace, result.probabilities = d.status, d.trace, d.probabilities
        result.confidence = d.confidence
        if d.status == ExpressionStatus.ESTIMATED:
            result.expression = d.label
            result.confidence_band = str(d.band)
            result.observation = (f"Visible facial expression is consistent with a "
                                  f"{d.label.lower()}-expression classification.")
        else:
            result.observation = MSG_UNCERTAIN
        return result
