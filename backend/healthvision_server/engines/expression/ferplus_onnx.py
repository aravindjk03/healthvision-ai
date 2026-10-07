"""Model D — FER+ (ONNX Model Zoo emotion-ferplus-8). Returns model-native label → softmax prob."""
from __future__ import annotations

import numpy as np
import onnxruntime as ort

from ...engines.alignment.similarity_transform import expression_crop
from ..base import EngineInfo, ExpressionEngine

if hasattr(ort, "disable_telemetry_events"):
    ort.disable_telemetry_events()

_LABELS = ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]


class FerPlusExpressionEngine(ExpressionEngine):
    def __init__(self, info: EngineInfo, model_path: str):
        super().__init__(info)
        so = ort.SessionOptions()
        so.log_severity_level = 3
        self._sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
        self._input = self._sess.get_inputs()[0].name

    def labels(self) -> list[str]:
        return list(_LABELS)

    def predict(self, aligned_face_bgr_112: np.ndarray) -> dict[str, float]:
        x = expression_crop(aligned_face_bgr_112)[None, None]
        logits = self._sess.run(None, {self._input: x})[0][0].astype(np.float64)
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return {lbl: float(v) for lbl, v in zip(_LABELS, p)}

    def warm_up(self) -> None:
        self.predict(np.zeros((112, 112, 3), np.uint8))
