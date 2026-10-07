"""Engine interfaces (docs/03 §3). Every adapter implements one of these protocols."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from healthvision.domain import FaceDetection, Landmarks, LivenessStatus


@dataclass(frozen=True)
class EngineInfo:
    model_id: str
    version: str
    runtime: str

    @property
    def key(self) -> str:
        return f"{self.model_id}@{self.version}"


class FaceDetector(Protocol):
    def info(self) -> EngineInfo: ...
    def detect(self, image_bgr: np.ndarray) -> list[FaceDetection]: ...


class LandmarkEngine(Protocol):
    def info(self) -> EngineInfo: ...
    def landmarks(self, image_bgr: np.ndarray, detection: FaceDetection) -> Landmarks | None: ...


class Aligner(Protocol):
    def align(self, image_bgr: np.ndarray, detection: FaceDetection,
              keypoints5: list[tuple[float, float]] | None) -> np.ndarray | None: ...


class ExpressionEngine(Protocol):
    def info(self) -> EngineInfo: ...
    def labels(self) -> list[str]: ...
    def predict(self, aligned_face_bgr: np.ndarray) -> dict[str, float]: ...


class EmbeddingModel(Protocol):
    def info(self) -> EngineInfo: ...
    def embed(self, aligned_face_bgr: np.ndarray) -> np.ndarray: ...
    def similarity(self, a: np.ndarray, b: np.ndarray) -> float: ...


@dataclass
class LivenessResult:
    status: LivenessStatus
    score: float | None = None


class LivenessEngine(Protocol):
    def info(self) -> EngineInfo: ...
    def assess(self, frames: list[np.ndarray]) -> LivenessResult: ...
