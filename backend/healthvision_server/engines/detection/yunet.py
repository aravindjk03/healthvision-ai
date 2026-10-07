"""Model B — YuNet face detector via cv2.FaceDetectorYN."""
from __future__ import annotations

import threading

import cv2
import numpy as np

from ..base import EngineInfo, FaceDetection, FaceDetector


class YuNetDetector(FaceDetector):
    def __init__(self, info: EngineInfo, model_path: str):
        super().__init__(info)
        self._path = model_path
        self._local = threading.local()

    def _det(self, w: int, h: int, score_floor: float, nms: float, top_k: int):
        d = getattr(self._local, "det", None)
        if d is None:
            d = cv2.FaceDetectorYN.create(self._path, "", (w, h), score_floor, nms, top_k)
            self._local.det = d
        d.setInputSize((w, h))
        d.setScoreThreshold(score_floor)
        d.setNMSThreshold(nms)
        d.setTopK(top_k)
        return d

    def detect(self, image_bgr, score_floor, nms_threshold, top_k):
        h, w = image_bgr.shape[:2]
        _, faces = self._det(w, h, score_floor, nms_threshold, max(top_k, 1)).detect(image_bgr)
        out: list[FaceDetection] = []
        if faces is None:
            return out
        for f in faces:
            x, y, bw, bh = f[:4]
            x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
            x1, y1 = min(w, int(round(x + bw))), min(h, int(round(y + bh)))
            kps = [(float(f[4 + 2 * i]), float(f[5 + 2 * i])) for i in range(5)]
            out.append(FaceDetection(bbox=(x0, y0, max(0, x1 - x0), max(0, y1 - y0)),
                                     score=float(np.clip(f[14], 0, 1)), keypoints5=kps, raw=f.copy()))
        out.sort(key=lambda d: d.score, reverse=True)
        return out

    def warm_up(self) -> None:
        self.detect(np.zeros((320, 320, 3), np.uint8), 0.5, 0.3, 5)
