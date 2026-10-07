"""Builds engines from config + registry. The UI never touches this directly — only services do."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from healthvision.config import Config
from healthvision.engines.expression import FerPlusExpression
from healthvision.engines.landmarks import FivePointLandmarker, MediaPipeLandmarker
from healthvision.engines.liveness import NotImplementedLivenessEngine
from healthvision.engines.recognition import SFaceEmbedder
from healthvision.engines.yunet import YuNetDetector
from healthvision.registry import ModelRegistry, ModelUnavailable


@dataclass
class Engines:
    detector: Any = None
    landmarks: Any = None
    expression: Any = None
    embedder: Any = None
    liveness: Any = None
    errors: dict[str, str] = field(default_factory=dict)
    warmup_ms: dict[str, float] = field(default_factory=dict)


def build_engines(config: Config, registry: ModelRegistry) -> Engines:
    eng = Engines(liveness=NotImplementedLivenessEngine())
    fd = config["face_detection"]
    try:
        entry = registry.get("face_detector.yunet")
        eng.detector = YuNetDetector(registry.ensure_file(entry.model_id), entry.version,
                                     score_floor=fd["min_secondary_face_confidence"],
                                     nms_threshold=fd["nms_threshold"], top_k=fd["max_faces_considered"])
    except ModelUnavailable as exc:
        eng.errors["face_detector"] = str(exc)

    lm_cfg = config["landmarks"]
    if lm_cfg["engine"] == "mediapipe":
        try:
            entry = registry.get("landmarks.mediapipe_face_landmarker")
            eng.landmarks = MediaPipeLandmarker(registry.ensure_file(entry.model_id), entry.version,
                                                lm_cfg["crop_padding"])
        except Exception as exc:  # MediaPipe import or model failure -> documented fallback
            eng.errors["landmarks"] = f"MediaPipe unavailable, using five-point fallback ({exc})"
    if eng.landmarks is None:
        eng.landmarks = FivePointLandmarker()
        registry.status["landmarks.fivepoint"] = "READY"

    try:
        entry = registry.get("embedding.sface")
        eng.embedder = SFaceEmbedder(registry.ensure_file(entry.model_id), entry.version)
    except ModelUnavailable as exc:
        eng.errors["embedder"] = str(exc)

    try:
        entry = registry.get("expression.ferplus")
        eng.expression = FerPlusExpression(registry.ensure_file(entry.model_id), entry.version)
    except ModelUnavailable as exc:
        eng.errors["expression"] = str(exc)

    registry.status["liveness.none"] = "NOT_IMPLEMENTED"

    # Warm-up so the first user request is not misreported as slow (docs/02 §10).
    dummy = np.full((240, 320, 3), 127, dtype=np.uint8)
    for name, fn in (("detector", lambda: eng.detector and eng.detector.detect(dummy)),
                     ("expression", lambda: eng.expression and eng.expression.predict(np.full((112, 112, 3), 127, np.uint8))),
                     ("embedder", lambda: eng.embedder and eng.embedder.embed(np.full((112, 112, 3), 127, np.uint8)))):
        t0 = time.perf_counter()
        fn()
        eng.warmup_ms[name] = round((time.perf_counter() - t0) * 1000, 1)
    return eng
