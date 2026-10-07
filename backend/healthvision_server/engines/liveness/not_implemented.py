"""Model F — liveness is NOT implemented in V1. Always returns NOT_PERFORMED."""
from ..base import LivenessEngine, LivenessResult


class NotImplementedLivenessEngine(LivenessEngine):
    def __init__(self, info, model_path=None):
        super().__init__(info)

    def assess(self, frames) -> LivenessResult:
        return LivenessResult(status="NOT_PERFORMED", score=None)
