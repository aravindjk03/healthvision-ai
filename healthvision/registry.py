"""Model registry: loads models/registry.yaml, downloads missing files, verifies SHA-256 (docs/03 §7)."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from healthvision.config import ROOT

MODELS_DIR = ROOT / "models"
REGISTRY_PATH = MODELS_DIR / "registry.yaml"


class ModelUnavailable(RuntimeError):
    pass


@dataclass
class ModelEntry:
    data: dict[str, Any]

    @property
    def model_id(self) -> str:
        return self.data["model_id"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def key(self) -> str:
        return f"{self.model_id}@{self.version}"

    @property
    def path(self) -> Path | None:
        return MODELS_DIR / self.data["file"] if self.data.get("file") else None

    def public_info(self) -> dict[str, Any]:
        hidden = {"file", "url"}
        return {k: v for k, v in self.data.items() if k not in hidden}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ModelRegistry:
    def __init__(self, registry_path: Path = REGISTRY_PATH):
        raw = yaml.safe_load(registry_path.read_text())
        self.entries = {m["model_id"]: ModelEntry(m) for m in raw["models"]}
        self.status: dict[str, str] = {mid: "NOT_LOADED" for mid in self.entries}

    def get(self, model_id: str) -> ModelEntry:
        return self.entries[model_id]

    def ensure_file(self, model_id: str) -> Path:
        """Return a verified local path, downloading the file if needed."""
        entry = self.get(model_id)
        path = entry.path
        if path is None:
            raise ModelUnavailable(f"{model_id} has no model file")
        expected = entry.data.get("sha256")
        if not path.exists():
            url = entry.data.get("url")
            if not url or not url.startswith("https://"):
                self.status[model_id] = "UNAVAILABLE"
                raise ModelUnavailable(f"{model_id}: no HTTPS download URL")
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, dir=path.parent, suffix=".part") as tmp:
                try:
                    with urllib.request.urlopen(url, timeout=120) as resp:
                        shutil.copyfileobj(resp, tmp)
                except Exception as exc:  # network failure
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    self.status[model_id] = "UNAVAILABLE"
                    raise ModelUnavailable(f"{model_id}: download failed ({exc})") from exc
            Path(tmp.name).replace(path)
        if expected and _sha256(path) != expected:
            path.unlink(missing_ok=True)
            self.status[model_id] = "INTEGRITY_FAILURE"
            raise ModelUnavailable(f"{model_id}: SHA-256 mismatch (MODEL_INTEGRITY_FAILURE)")
        self.status[model_id] = "READY"
        return path
