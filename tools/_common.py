"""Shared helpers for evaluation tools: load the production pipeline exactly as the app does."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def load_registry_and_pipeline(config: str | None = None):
    from healthvision.config.settings import load_config
    from healthvision.container import ENGINE_IDS
    from healthvision.registry.model_registry import ModelRegistry
    from healthvision.services.face_pipeline import FacePipeline
    from healthvision.services.face_quality_service import FaceQualityService

    cfg = load_config(config)
    s = cfg.settings
    selected = {"detector": ENGINE_IDS["detector"][s.face_detection.engine],
                "landmarks": "landmarks.mediapipe_face_landmarker",
                "expression": ENGINE_IDS["expression"][s.expression.engine],
                "embedding": ENGINE_IDS["embedding"][s.recognition.engine],
                "liveness": "liveness.none"}
    reg = ModelRegistry(cfg.resolve(s.paths.registry_file), cfg.resolve(s.paths.models_dir), selected,
                        s.features.allow_restricted_licenses)
    pipe = FacePipeline(s, cfg.config_version, reg, FaceQualityService(s.quality))
    return cfg, reg, pipe


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def run_metadata(cfg) -> dict:
    return {"created_at": datetime.now(timezone.utc).isoformat(), "git_commit": git_commit(),
            "config_version": cfg.config_version, "hardware": {"cpu": platform.processor() or platform.machine(),
            "os": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
            "cpus": os.cpu_count()}}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
    print("wrote", path.relative_to(ROOT) if ROOT in path.parents else path)


def read_manifest(path: str) -> list[dict]:
    """CSV manifest with a header row; image paths relative to the manifest file."""
    import csv
    base = Path(path).resolve().parent
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            r["path"] = str((base / r["path"]).resolve())
            rows.append(r)
    return rows
