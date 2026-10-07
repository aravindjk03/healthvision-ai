"""Model E — SFace 128-D embedding via cv2.FaceRecognizerSF (input: aligned 112×112 BGR)."""
from __future__ import annotations

import threading

import cv2
import numpy as np

from ..base import EmbeddingModel, EngineInfo


class SFaceEmbedder(EmbeddingModel):
    def __init__(self, info: EngineInfo, model_path: str):
        super().__init__(info)
        self._path = model_path
        self._local = threading.local()

    def _rec(self):
        r = getattr(self._local, "rec", None)
        if r is None:
            r = cv2.FaceRecognizerSF.create(self._path, "")
            self._local.rec = r
        return r

    def embed(self, aligned_face_bgr_112: np.ndarray) -> np.ndarray:
        v = self._rec().feature(aligned_face_bgr_112).reshape(-1).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-12)

    def warm_up(self) -> None:
        self.embed(np.zeros((112, 112, 3), np.uint8))
