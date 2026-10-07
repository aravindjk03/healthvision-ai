"""Model D — FER+ expression classifier (ONNX Runtime). Returns raw probabilities only."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from healthvision.engines.base import EngineInfo

FERPLUS_LABELS = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]


class FerPlusExpression:
    def __init__(self, model_path: Path, version: str):
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input = self._session.get_inputs()[0].name
        self._info = EngineInfo("expression.ferplus", version, "onnxruntime")

    def info(self) -> EngineInfo:
        return self._info

    def labels(self) -> list[str]:
        return list(FERPLUS_LABELS)

    def predict(self, aligned_face_bgr: np.ndarray) -> dict[str, float]:
        gray = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2GRAY)
        tensor = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32).reshape(1, 1, 64, 64)
        logits = self._session.run(None, {self._input: tensor})[0].flatten().astype(np.float64)
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        return {label: float(p) for label, p in zip(FERPLUS_LABELS, probs)}
