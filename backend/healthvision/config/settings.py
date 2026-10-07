"""Typed configuration schema + provider (docs/02 §8).

The YAML file is the single source of every threshold. Its SHA-256 plus the schema
version form ``config_version``, recorded with every result.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MinMax(_Strict):
    min: float
    max: float


class ServerCfg(_Strict):
    host: str = "127.0.0.1"
    port: int = 8600
    max_upload_bytes: int
    max_image_side_px: int


class PathsCfg(_Strict):
    data_dir: str = "data"
    models_dir: str = "models"
    registry_file: str = "models/registry.yaml"


class FeaturesCfg(_Strict):
    recognition_enabled: bool = True
    identification_enabled: bool = False
    liveness_enabled: bool = False
    store_raw_images: bool = False
    allow_restricted_licenses: bool = False

    @model_validator(mode="after")
    def _v1_rules(self):
        if self.store_raw_images:
            raise ValueError("features.store_raw_images must be false in V1")
        if self.liveness_enabled:
            raise ValueError("features.liveness_enabled cannot be true: no validated liveness model in V1")
        return self


class PrivacyCfg(_Strict):
    policy_version: str
    delete_on_revoke: bool = True


class PlausibilityCfg(_Strict):
    bmi_min: float
    bmi_max: float


class BmiCfg(_Strict):
    reference: Literal["WHO_ADULT_2000", "WHO_ASIAN_2004"]
    adult_min_age: int
    height_cm: MinMax
    weight_kg: MinMax
    plausibility_warning: PlausibilityCfg


class FaceDetectionCfg(_Strict):
    engine: str
    face_detection_threshold: float = Field(ge=0, le=1)
    nms_threshold: float = Field(ge=0, le=1)
    max_faces_considered: int
    min_secondary_face_confidence: float = Field(ge=0, le=1)
    candidate_floor: float = Field(ge=0, le=1)


class BrightnessCfg(_Strict):
    min_mean: float
    max_mean: float


class BlurCfg(_Strict):
    laplacian_var_good: float
    laplacian_var_min: float


class PoseCfg(_Strict):
    yaw_good: float
    yaw_max: float
    pitch_good: float
    pitch_max: float
    roll_max: float


class OcclusionCfg(_Strict):
    min_landmark_visibility: float


class QualityCfg(_Strict):
    min_image_short_side_px: int
    minimum_face_size_px: int
    brightness_threshold: BrightnessCfg
    blur_threshold: BlurCfg
    global_blur_min: float
    pose_max_deg: PoseCfg
    occlusion: OcclusionCfg
    grade_policy: Literal["worst_check"]
    store_landmarks: bool = False


class ExprThresholds(_Strict):
    high: float
    moderate: float


class ExpressionCfg(_Strict):
    engine: str
    classes: list[str]
    class_map: dict[str, Optional[str]]
    renormalize_after_exclusion: bool
    max_excluded_mass: float
    expression_confidence_threshold: ExprThresholds
    min_top2_margin: float
    temperature: float = Field(gt=0)


class DemoThresholds(_Strict):
    recognition_threshold: float
    no_match_threshold: float


class FramesCfg(_Strict):
    min: int
    recommended: int
    max: int


class RateCfg(_Strict):
    per_minute: Optional[int] = None
    per_hour: Optional[int] = None


class RecognitionCfg(_Strict):
    engine: str
    calibration_file: str
    demo_uncalibrated_thresholds: DemoThresholds
    enrollment_frames: FramesCfg
    max_templates_per_user: int
    rate_limit: RateCfg
    enroll_rate_limit: RateCfg
    lockout_after_consecutive_no_match: int
    lockout_minutes: int


class RetentionCfg(_Strict):
    retention_period_days: dict[str, int]
    template_max_age_days: int
    purge_interval_minutes: int


class SecurityCfg(_Strict):
    session_idle_minutes: int
    session_absolute_hours: int
    password_min_length: int
    login_rate_limit: RateCfg
    face_rate_limit: RateCfg
    max_sessions_per_user: int
    keystore: Literal["os", "env"] = "os"


class LoggingCfg(_Strict):
    level: str = "INFO"
    log_images: bool = False

    @model_validator(mode="after")
    def _no_images(self):
        if self.log_images:
            raise ValueError("logging.log_images must remain false")
        return self


class Settings(_Strict):
    config_schema_version: Literal[1]
    server: ServerCfg
    paths: PathsCfg = PathsCfg()
    features: FeaturesCfg
    privacy: PrivacyCfg
    bmi: BmiCfg
    face_detection: FaceDetectionCfg
    quality: QualityCfg
    expression: ExpressionCfg
    recognition: RecognitionCfg
    retention: RetentionCfg
    security: SecurityCfg
    logging: LoggingCfg


class LoadedConfig:
    """Immutable loaded config + its version identifiers."""

    def __init__(self, settings: Settings, raw: dict, sha256: str, path: Path, root: Path):
        self.settings = settings
        self.raw = raw
        self.sha256 = sha256
        self.path = path
        self.root = root
        self.config_version = f"{settings.config_schema_version}-{sha256[:12]}"

    def resolve(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (self.root / p)


def repo_root() -> Path:
    env = os.environ.get("HEALTHVISION_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[3]


def load_config(path: str | os.PathLike | None = None, root: Path | None = None) -> LoadedConfig:
    root = root or repo_root()
    if path is None:
        env = os.environ.get("HEALTHVISION_CONFIG")
        if env:
            path = env
        else:
            active = root / "config" / "healthvision.yaml"
            path = active if active.exists() else root / "config" / "healthvision.example.yaml"
    path = Path(path)
    data = path.read_bytes()
    raw = yaml.safe_load(data)
    settings = Settings.model_validate(raw)  # fail fast on missing/invalid keys
    sha = hashlib.sha256(data).hexdigest()
    return LoadedConfig(settings, raw, sha, path, root)


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
