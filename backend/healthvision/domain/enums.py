"""Enumerations (docs/08 §1)."""
from enum import StrEnum


class Role(StrEnum):
    USER = "USER"
    ADMINISTRATOR = "ADMINISTRATOR"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DELETED = "DELETED"


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


class ExpressionStatus(StrEnum):
    ESTIMATED = "ESTIMATED"
    UNCERTAIN = "UNCERTAIN"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ExpressionBand(StrEnum):
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


class ThresholdSource(StrEnum):
    CONFIG = "config"
    CALIBRATION_FILE = "calibration_file"
    DEMO_UNCALIBRATED = "demo_uncalibrated"


class EnrollmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    STALE = "STALE"


class AuditEvent(StrEnum):
    FACE_ENROLLMENT = "FACE_ENROLLMENT"
    CONSENT_CHANGE = "CONSENT_CHANGE"
    RECOGNITION_ATTEMPT = "RECOGNITION_ATTEMPT"
    TEMPLATE_DELETION = "TEMPLATE_DELETION"
    DATA_DELETION = "DATA_DELETION"
    ADMIN_ACCESS = "ADMIN_ACCESS"
    REPORT_GENERATION = "REPORT_GENERATION"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    MODEL_CHANGE = "MODEL_CHANGE"
    MODEL_INTEGRITY_FAILURE = "MODEL_INTEGRITY_FAILURE"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    RATE_LIMITED = "RATE_LIMITED"
    LOCKOUT = "LOCKOUT"
    RETENTION_PURGE = "RETENTION_PURGE"
