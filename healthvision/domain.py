"""Domain enums and result types (docs/08 §1). Results stay separate — no combined score."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ConsentPurpose(StrEnum):
    BMI = "BMI"
    FACE_ANALYSIS = "FACE_ANALYSIS"
    RECOGNITION = "RECOGNITION"


class ConsentStatus(StrEnum):
    GRANTED = "GRANTED"
    DECLINED = "DECLINED"
    REVOKED = "REVOKED"


class BmiStatus(StrEnum):
    VALID = "VALID"
    INVALID_INPUT = "INVALID_INPUT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FaceState(StrEnum):
    NO_FACE = "NO_FACE"
    ONE_FACE = "ONE_FACE"
    MULTIPLE_FACES = "MULTIPLE_FACES"


class QualityGrade(StrEnum):
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    POOR = "POOR"


GRADE_ORDER = {QualityGrade.GOOD: 0, QualityGrade.ACCEPTABLE: 1, QualityGrade.POOR: 2}


class ExpressionStatus(StrEnum):
    ESTIMATED = "ESTIMATED"
    UNCERTAIN = "UNCERTAIN"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ConfidenceBand(StrEnum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"


class RecognitionDecision(StrEnum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    UNCERTAIN = "UNCERTAIN"
    NOT_PERFORMED = "NOT_PERFORMED"


class LivenessStatus(StrEnum):
    NOT_PERFORMED = "NOT_PERFORMED"
    LIVE = "LIVE"
    SPOOF = "SPOOF"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class DecisionTrace:
    rule_id: str
    inputs: dict[str, Any]
    thresholds: dict[str, Any]
    threshold_source: str
    config_version: str
    outcome: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class FaceDetection:
    bbox: tuple[int, int, int, int]          # x, y, w, h (pixels)
    score: float
    keypoints5: list[tuple[float, float]] | None
    raw: Any = None                           # detector-native row (used for alignment)


@dataclass
class Landmarks:
    scheme: str
    points: Any                               # ndarray[N,2] in image coords (memory only)
    visibility: float
    pose: dict[str, float]                    # yaw, pitch, roll (degrees)
    keypoints5: list[tuple[float, float]]


@dataclass
class QualityCheck:
    check: str
    value: Any
    grade: QualityGrade
    message: str = ""


@dataclass
class QualityResult:
    grade: QualityGrade
    checks: list[QualityCheck]

    @property
    def action(self) -> str:
        return {QualityGrade.GOOD: "PROCEED", QualityGrade.ACCEPTABLE: "PROCEED_WITH_CAUTION",
                QualityGrade.POOR: "RETAKE"}[self.grade]

    @property
    def failing(self) -> list[QualityCheck]:
        return [c for c in self.checks if c.grade == QualityGrade.POOR]
