"""Per-stage latency measurement (docs/03 §9). Numbers are measured, never invented."""
from __future__ import annotations

import time
from contextlib import contextmanager


class LatencyRecorder:
    def __init__(self) -> None:
        self.stages: dict[str, float] = {}
        self._t0 = time.perf_counter_ns()

    @contextmanager
    def stage(self, name: str):
        t = time.perf_counter_ns()
        try:
            yield
        finally:
            self.stages[name] = round((time.perf_counter_ns() - t) / 1e6, 2)

    def set(self, name: str, ms: float | None) -> None:
        if ms is not None:
            self.stages[name] = round(float(ms), 2)

    def finish(self) -> dict[str, float]:
        self.stages["total_pipeline"] = round((time.perf_counter_ns() - self._t0) / 1e6, 2)
        return dict(self.stages)
