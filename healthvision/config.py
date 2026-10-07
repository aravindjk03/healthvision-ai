"""Configuration loading. All thresholds come from config/healthvision.yaml (docs/02 §8)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "healthvision.yaml"

REQUIRED_SECTIONS = (
    "privacy", "features", "upload", "bmi", "face_detection", "landmarks",
    "quality", "expression", "recognition",
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    data: dict[str, Any]
    version: str

    def __getitem__(self, key: str) -> Any:
        return self.data[key]


def load_config(path: Path = CONFIG_PATH) -> Config:
    raw = path.read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ConfigError("Config root must be a mapping")
    missing = [s for s in REQUIRED_SECTIONS if s not in data]
    if missing:
        raise ConfigError(f"Config missing sections: {missing}")
    if data["features"].get("store_raw_images"):
        raise ConfigError("store_raw_images must be false in V1")
    exp = data["expression"]["expression_confidence_threshold"]
    if not exp["moderate"] <= exp["high"]:
        raise ConfigError("expression moderate threshold must be <= high threshold")
    demo = data["recognition"]["demo_uncalibrated_thresholds"]
    if not demo["no_match_threshold"] <= demo["recognition_threshold"]:
        raise ConfigError("no_match_threshold must be <= recognition_threshold")
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return Config(data=data, version=f"{data['config_schema_version']}-{digest}")
