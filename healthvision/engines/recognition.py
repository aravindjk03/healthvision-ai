"""Model E — SFace embedding model (OpenCV Zoo), plus the shared 5-point aligner (docs/03 §4)."""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

from healthvision.domain import FaceDetection
from healthvision.engines.base import EngineInfo


class SFaceEmbedder:
    def __init__(self, model_path: Path, version: str):
        self._model_path = str(model_path)
        self._recognizer = cv2.FaceRecognizerSF.create(self._model_path, "")
        self._lock = threading.Lock()   # cv2 DNN nets are not safe for concurrent use
        self._info = EngineInfo("embedding.sface", version, "opencv-dnn")

    def info(self) -> EngineInfo:
        return self._info

    def align(self, image_bgr: np.ndarray, detection: FaceDetection,
              keypoints5: list[tuple[float, float]] | None) -> np.ndarray | None:
        """Similarity-transform alignment to the ArcFace 112x112 template."""
        kps = keypoints5 or detection.keypoints5
        if not kps or len(kps) != 5:
            return None
        x, y, w, h = detection.bbox
        row = np.array([x, y, w, h, *[c for p in kps for c in p], detection.score], dtype=np.float32)
        try:
            with self._lock:
                aligned = self._recognizer.alignCrop(image_bgr, row.reshape(1, -1))
        except cv2.error:
            return None
        return aligned if aligned is not None and aligned.size else None

    def embed(self, aligned_face_bgr: np.ndarray) -> np.ndarray:
        with self._lock:
            feature = self._recognizer.feature(aligned_face_bgr).flatten().astype(np.float32)
        norm = float(np.linalg.norm(feature))
        return feature / norm if norm > 0 else feature

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
