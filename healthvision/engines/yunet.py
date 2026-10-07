"""Model B — YuNet face detector via OpenCV (answers only: where is the face?)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from healthvision.domain import FaceDetection
from healthvision.engines.base import EngineInfo


class YuNetDetector:
    def __init__(self, model_path: Path, version: str, score_floor: float, nms_threshold: float, top_k: int):
        self._info = EngineInfo("face_detector.yunet", version, "opencv-dnn")
        self._model_path = str(model_path)
        self._score_floor = score_floor
        self._nms = nms_threshold
        self._top_k = top_k

    def info(self) -> EngineInfo:
        return self._info

    def detect(self, image_bgr: np.ndarray) -> list[FaceDetection]:
        h, w = image_bgr.shape[:2]
        # A fresh detector per call keeps the engine thread-safe (creation is cheap: ~230 KB model).
        detector = cv2.FaceDetectorYN.create(self._model_path, "", (w, h), self._score_floor, self._nms, self._top_k)
        _, faces = detector.detect(image_bgr)
        results: list[FaceDetection] = []
        if faces is None:
            return results
        for row in faces:
            x, y, bw, bh = row[:4]
            x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
            x1, y1 = min(w, int(round(x + bw))), min(h, int(round(y + bh)))
            kps = [(float(row[4 + 2 * i]), float(row[5 + 2 * i])) for i in range(5)]
            results.append(FaceDetection(bbox=(x0, y0, max(0, x1 - x0), max(0, y1 - y0)),
                                         score=float(row[14]), keypoints5=kps, raw=row.copy()))
        results.sort(key=lambda d: d.score, reverse=True)
        return results
