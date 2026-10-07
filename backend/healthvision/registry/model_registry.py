"""Model registry (docs/03 §7): load registry.yaml, verify SHA-256, enforce licence status,
instantiate adapters, warm up. Failures disable only the dependent features."""
from __future__ import annotations

import hashlib
import importlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from ..engines.base import Engine, EngineInfo

log = logging.getLogger("healthvision.registry")

TYPE_TO_SLOT = {
    "FACE_DETECTOR": "detector",
    "LANDMARKS": "landmarks",
    "EXPRESSION": "expression",
    "EMBEDDING": "embedding",
    "LIVENESS": "liveness",
}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ModelEntry:
    entry: dict
    status: str = "UNAVAILABLE"           # READY | UNAVAILABLE | NOT_IMPLEMENTED | LICENSE_BLOCKED
    reason: Optional[str] = None
    engine: Optional[Engine] = None
    warmup_ms: Optional[float] = None
    events: list = field(default_factory=list)  # (audit_event, details)

    @property
    def model_id(self) -> str:
        return self.entry["model_id"]

    @property
    def version(self) -> str:
        return str(self.entry["version"])

    @property
    def key(self) -> str:
        return f"{self.model_id}@{self.version}"

    def public(self) -> dict:
        e = self.entry
        pm = e.get("performance_metrics") or {}
        return {
            "model_id": e["model_id"],
            "model_type": e["model_type"],
            "name": e.get("name"),
            "version": str(e["version"]),
            "license": e.get("license"),
            "license_status": e.get("license_status"),
            "source": e.get("source"),
            "status": self.status,
            "reason": self.reason,
            "local_validation": "VALIDATED" if pm.get("local_validated") else "NOT_VALIDATED",
            "vendor_reported": pm.get("vendor_reported") or {},
            "known_limitations": e.get("known_limitations", []),
            "warmup_ms": self.warmup_ms,
        }


class ModelRegistry:
    def __init__(self, registry_file: Path, models_dir: Path, selected: dict[str, str], allow_restricted: bool):
        self.registry_file = registry_file
        self.models_dir = models_dir
        self.entries: list[ModelEntry] = []
        self.active: dict[str, ModelEntry] = {}
        raw = yaml.safe_load(registry_file.read_text())
        for e in raw.get("models", []):
            self.entries.append(ModelEntry(e))
        for slot, model_id in selected.items():
            me = next((m for m in self.entries if m.model_id == model_id), None)
            if me is None:
                raise ValueError(f"Configured {slot} model '{model_id}' is not in the registry")
            self._load(me, allow_restricted)
            self.active[slot] = me

    def _load(self, me: ModelEntry, allow_restricted: bool) -> None:
        e = me.entry
        if e.get("license_status") == "REJECTED" or (e.get("license_status") == "REVIEW_REQUIRED" and not allow_restricted):
            me.status, me.reason = "LICENSE_BLOCKED", f"license_status={e.get('license_status')}"
            return
        path = None
        if e.get("file"):
            path = self.models_dir / e["file"]
            if not path.exists():
                me.status, me.reason = "UNAVAILABLE", "model file missing — run tools/fetch_models.py"
                return
            actual = file_sha256(path)
            if e.get("sha256") and actual != e["sha256"]:
                me.status, me.reason = "UNAVAILABLE", "SHA-256 mismatch"
                me.events.append(("MODEL_INTEGRITY_FAILURE", {"model_id": me.model_id}))
                return
        info = EngineInfo(me.model_id, me.version, e.get("sha256"), tuple(e.get("input_size") or ()), e.get("runtime", ""))
        mod_name, cls_name = e["adapter"].split(":")
        try:
            cls = getattr(importlib.import_module(mod_name), cls_name)
            me.engine = cls(info, str(path) if path else None)
            t = time.perf_counter()
            me.engine.warm_up()
            me.warmup_ms = round((time.perf_counter() - t) * 1000, 1)
        except Exception as exc:  # pragma: no cover - environment dependent
            log.exception("failed to load %s", me.key)
            me.status, me.reason, me.engine = "UNAVAILABLE", f"load failed: {type(exc).__name__}", None
            return
        me.status = "NOT_IMPLEMENTED" if e.get("status") == "NOT_IMPLEMENTED" else "READY"

    def engine(self, slot: str):
        me = self.active.get(slot)
        return me.engine if me and me.status in ("READY", "NOT_IMPLEMENTED") else None

    def entry(self, slot: str) -> Optional[ModelEntry]:
        return self.active.get(slot)

    def close(self) -> None:
        for me in self.active.values():
            if me.engine is not None:
                try:
                    me.engine.close()
                except Exception:  # pragma: no cover
                    log.exception("failed to close %s", me.key)
                me.engine = None
                me.status = "UNAVAILABLE"

    def ready(self, slot: str) -> bool:
        me = self.active.get(slot)
        return bool(me and me.status == "READY")
