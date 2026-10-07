"""Abstract engine interfaces (docs/03 §3).

Engines are stateless after load, thread-safe for inference, return plain dataclasses and
NEVER apply product thresholds or produce user-facing text. The only threshold an engine
may receive is an explicit pre-filter passed by the service (sourced from config).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class EngineInfo:
    model_id: str
    version: str
    sha256: Optional[str]
    input_size: tuple
    runtime: str

    @property
    def key(self) -> str:
        return f"{self.model_id}@{self.version}"


@dataclass
class FaceDetection:
    bbox: tuple[int, int, int, int]          # x, y, w, h (clipped to image)
    score: float                             # raw detector confidence [0,1]
    keypoints5: Optional[list[tuple[float, float]]] = None  # R-eye, L-eye, nose, R-mouth, L-mouth
    raw: Optional[np.ndarray] = field(default=None, repr=False)


@dataclass
class Landmarks:
    points: np.ndarray                       # [N,2] image coords
    scheme: str
    visibility: float
    region_visibility: dict[str, float]
    pose: dict[str, float]                   # yaw, pitch, roll (degrees)
    keypoints5: list[tuple[float, float]]


@dataclass
class LivenessResult:
    status: str                              # NOT_PERFORMED | LIVE | SPOOF | UNCERTAIN
    score: Optional[float] = None


class Engine(ABC):
    def __init__(self, info: EngineInfo):
        self._info = info

    def info(self) -> EngineInfo:
        return self._info

    def warm_up(self) -> None:  # pragma: no cover - overridden
        pass

    def close(self) -> None:
        """Release native resources. Called explicitly at shutdown."""


class FaceDetector(Engine):
    @abstractmethod
    def detect(self, image_bgr: np.ndarray, score_floor: float, nms_threshold: float, top_k: int) -> list[FaceDetection]: ...


class LandmarkEngine(Engine):
    @abstractmethod
    def landmarks(self, image_bgr: np.ndarray, detection: FaceDetection) -> Optional[Landmarks]: ...


class ExpressionEngine(Engine):
    @abstractmethod
    def labels(self) -> list[str]: ...

    @abstractmethod
    def predict(self, aligned_face_bgr_112: np.ndarray) -> dict[str, float]: ...


class EmbeddingModel(Engine):
    @abstractmethod
    def embed(self, aligned_face_bgr_112: np.ndarray) -> np.ndarray: ...

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


class LivenessEngine(Engine):
    @abstractmethod
    def assess(self, frames: list[np.ndarray]) -> LivenessResult: ...
