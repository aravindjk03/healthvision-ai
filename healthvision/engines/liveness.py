"""Model F — liveness. NOT IMPLEMENTED in V1 (docs/06 §6). Always reports NOT_PERFORMED."""

from __future__ import annotations

import numpy as np

from healthvision.domain import LivenessStatus
from healthvision.engines.base import EngineInfo, LivenessResult


class NotImplementedLivenessEngine:
    def info(self) -> EngineInfo:
        return EngineInfo("liveness.none", "none", "none")

    def assess(self, frames: list[np.ndarray]) -> LivenessResult:
        return LivenessResult(status=LivenessStatus.NOT_PERFORMED, score=None)
