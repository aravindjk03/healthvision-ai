"""Shared face pipeline: ingest → global quality → detection → face-count gate → landmarks →
face quality → alignment (docs/02 §5, docs/05). Used by face analysis and recognition."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import Image, ImageOps

from ..config.settings import Settings
from ..core.errors import ApiError
from ..core.latency import LatencyRecorder
from ..core.util import sha256_hex
from ..domain import messages as M
from ..domain.enums import FaceState, QualityGrade
from ..engines.alignment.similarity_transform import align_112
from ..engines.base import FaceDetection, Landmarks
from ..registry.model_registry import ModelRegistry
from . import decision_engine as DE
from .face_quality_service import FaceQualityService, failing, worst


@dataclass
class Ingested:
    image_bgr: np.ndarray
    sha256: str
    width: int
    height: int


def ingest(data: bytes, settings: Settings) -> Ingested:
    if len(data) > settings.server.max_upload_bytes:
        raise ApiError(400, "IMAGE_TOO_LARGE", "Image exceeds the maximum upload size.")
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
        raise ApiError(400, "UNSUPPORTED_MEDIA", "Only JPEG and PNG images are supported.")
    max_side = settings.server.max_image_side_px
    Image.MAX_IMAGE_PIXELS = max_side * max_side
    try:
        im = Image.open(io.BytesIO(data))
        if im.width > max_side or im.height > max_side:
            raise ApiError(400, "IMAGE_TOO_LARGE", f"Image must be at most {max_side}×{max_side} pixels.")
        im = ImageOps.exif_transpose(im).convert("RGB")
    except ApiError:
        raise
    except Exception:
        raise ApiError(400, "IMAGE_DECODE_FAILED", "The image could not be decoded.") from None
    rgb = np.asarray(im)
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    return Ingested(bgr, sha256_hex(data), bgr.shape[1], bgr.shape[0])


@dataclass
class PipelineResult:
    ingested: Ingested
    detections: list[FaceDetection] = field(default_factory=list)
    face_state: Optional[FaceState] = None
    face_trace: Optional[dict] = None
    primary: Optional[FaceDetection] = None
    landmarks: Optional[Landmarks] = None
    global_checks: list[dict] = field(default_factory=list)
    face_checks: list[dict] = field(default_factory=list)
    quality_grade: Optional[QualityGrade] = None
    aligned: Optional[np.ndarray] = None
    stop_reason: Optional[str] = None          # NO_FACE | MULTIPLE_FACES | POOR_QUALITY | ALIGNMENT_FAILED | MODEL_UNAVAILABLE
    message: Optional[str] = None
    models: dict = field(default_factory=dict)

    @property
    def stopped(self) -> bool:
        return self.stop_reason is not None

    def quality_dict(self) -> Optional[dict]:
        if self.quality_grade is None:
            return None
        g = self.quality_grade
        return {"grade": g.value, "action": "RETAKE" if g == QualityGrade.POOR else "PROCEED",
                "checks": self.global_checks + self.face_checks}

    def faces_public(self) -> list[dict]:
        return [{"face_index": i, "bbox": dict(zip("xywh", d.bbox)), "detection_confidence": round(d.score, 4)}
                for i, d in enumerate(self.detections)]


class FacePipeline:
    def __init__(self, settings: Settings, config_version: str, registry: ModelRegistry, quality: FaceQualityService):
        self.s = settings
        self.config_version = config_version
        self.registry = registry
        self.quality = quality

    def run(self, data: bytes, lat: LatencyRecorder, *, full: bool = True, enrollment_profile: bool = False) -> PipelineResult:
        """full=False stops after detection + global quality (POST /face/detect)."""
        det_engine = self.registry.engine("detector")
        if det_engine is None:
            raise ApiError(503, "MODEL_UNAVAILABLE", "Face detection is unavailable on this device.")
        with lat.stage("decode"):
            ing = ingest(data, self.s)
        r = PipelineResult(ing)
        r.models["detector"] = self.registry.entry("detector").key
        with lat.stage("quality_global"):
            r.global_checks = self.quality.global_checks(ing.image_bgr)
        fd = self.s.face_detection
        with lat.stage("detection"):
            dets = det_engine.detect(ing.image_bgr, fd.candidate_floor, fd.nms_threshold, fd.max_faces_considered)
        # Only faces above the secondary threshold are reported/counted.
        r.detections = [d for d in dets if d.score >= min(fd.min_secondary_face_confidence, fd.face_detection_threshold)]
        state, idx, tr = DE.face_count([d.score for d in dets], fd, self.config_version)
        r.face_state, r.face_trace = state, tr.as_dict()
        r.quality_grade = worst(r.global_checks)
        if state == FaceState.NO_FACE:
            r.stop_reason, r.message = "NO_FACE", M.NO_FACE
            return r
        if state == FaceState.MULTIPLE_FACES:
            r.stop_reason, r.message = "MULTIPLE_FACES", M.MULTIPLE_FACES
            return r
        r.primary = dets[idx[0]]
        if not full:
            if r.quality_grade == QualityGrade.POOR:
                r.message = M.POOR_QUALITY.format(reasons=", ".join(failing(r.global_checks)))
            return r

        lm_engine = self.registry.engine("landmarks")
        if lm_engine is not None:
            r.models["landmarks"] = self.registry.entry("landmarks").key
            with lat.stage("landmark"):
                r.landmarks = lm_engine.landmarks(ing.image_bgr, r.primary)
        with lat.stage("quality_face"):
            r.face_checks = self.quality.face_checks(ing.image_bgr, r.primary, r.landmarks)
        r.quality_grade = worst(r.global_checks + r.face_checks)
        if r.quality_grade == QualityGrade.POOR or (enrollment_profile and r.quality_grade != QualityGrade.GOOD):
            r.stop_reason = "POOR_QUALITY"
            reasons = failing(r.global_checks + r.face_checks) or ["quality must be GOOD for enrollment"]
            r.message = M.POOR_QUALITY.format(reasons=", ".join(reasons))
            return r
        with lat.stage("alignment"):
            # Detector keypoints first: SFace/FER+ alignment matches the YuNet 5-point convention.
            for kps in (r.primary.keypoints5, r.landmarks.keypoints5 if r.landmarks else None):
                if kps is not None:
                    r.aligned = align_112(ing.image_bgr, kps)
                    if r.aligned is not None:
                        break
        if r.aligned is None:
            r.stop_reason, r.message = "ALIGNMENT_FAILED", M.ALIGNMENT_FAILED
        return r
