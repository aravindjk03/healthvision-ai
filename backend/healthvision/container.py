"""Application container: loads config, verifies models, opens the DB, wires services.
Startup order (docs/02 §10): config → validate → models (SHA-256) → DB + migrate → keystore →
warm-up → retention scheduler."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from .config.settings import LoadedConfig, load_config
from .core.util import dumps, iso
from .domain.enums import AuditEvent
from .registry.model_registry import ModelRegistry
from .services.audit_service import AuditService
from .services.auth_service import AuthService
from .services.bmi_service import BmiService
from .services.consent_service import ConsentService
from .services.face_analysis_service import FaceAnalysisService
from .services.face_pipeline import FacePipeline
from .services.face_quality_service import FaceQualityService
from .services.privacy_service import PrivacyService, RetentionService
from .services.recognition_service import RateLimiter, RecognitionService
from .services.report_service import ReportService
from .services.session_service import AnalysisSessionService
from .storage.crypto import EnvelopeCipher, KeystoreUnavailable, load_kek
from .storage.db import Database
from .storage.orm import AuditLog, ConfigVersion, ModelVersion
from .storage.template_store import TemplateStore

log = logging.getLogger("healthvision")

ENGINE_IDS = {
    "detector": {"yunet": "face_detector.yunet"},
    "expression": {"ferplus_onnx": "expression.ferplus"},
    "embedding": {"sface": "embedding.sface"},
}


class Container:
    def __init__(self, config_path: Optional[str] = None, root: Optional[Path] = None, start_scheduler: bool = True):
        self.cfg: LoadedConfig = load_config(config_path, root)
        s = self.cfg.settings
        logging.basicConfig(level=s.logging.level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        self.data_dir = self.cfg.resolve(s.paths.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        selected = {
            "detector": ENGINE_IDS["detector"][s.face_detection.engine],
            "landmarks": "landmarks.mediapipe_face_landmarker",
            "expression": ENGINE_IDS["expression"][s.expression.engine],
            "embedding": ENGINE_IDS["embedding"][s.recognition.engine],
            "liveness": "liveness.none",
        }
        self.registry = ModelRegistry(self.cfg.resolve(s.paths.registry_file), self.cfg.resolve(s.paths.models_dir),
                                      selected, s.features.allow_restricted_licenses)

        self.db = Database(self.data_dir / "healthvision.db")
        self.db.migrate()
        self.audit = AuditService()

        self.keystore_error: Optional[str] = None
        cipher = None
        try:
            cipher = EnvelopeCipher(load_kek(s.security.keystore))
        except KeystoreUnavailable as exc:
            self.keystore_error = str(exc)
            log.warning("Keystore unavailable — recognition disabled: %s", exc)
        self.templates = TemplateStore(cipher, s.retention.template_max_age_days)

        days = s.retention.retention_period_days
        cv = self.cfg.config_version
        self.limiter = RateLimiter()
        self.consent = ConsentService(s.privacy.policy_version, days, self.audit)
        self.sessions = AnalysisSessionService(cv, days.get("analysis_sessions", 365), self.consent)
        self.bmi = BmiService(s.bmi, cv)
        self.quality = FaceQualityService(s.quality)
        self.pipeline = FacePipeline(s, cv, self.registry, self.quality)
        self.face = FaceAnalysisService(s, cv, self.registry, self.pipeline, self.consent, self.sessions)
        self.recognition = RecognitionService(self.cfg, self.registry, self.pipeline, self.consent, self.sessions,
                                              self.templates, self.audit, self.limiter)
        self.privacy = PrivacyService(s, self.audit, self.templates, self.recognition.revoke_enrollment)
        self.consent.on_revoke = self.privacy.on_consent_revoked
        self.auth = AuthService(s.security, self.audit)
        self.reports = ReportService(self.sessions, self.audit, self.data_dir, days.get("reports", 90), self.model_info)
        self.retention = RetentionService(self.db, s, self.audit, self.templates)

        self._record_versions()
        self.retention.purge()
        if start_scheduler:
            self.retention.start()

    # ------------------------------------------------------------------
    def _record_versions(self) -> None:
        s = self.cfg.settings
        with self.db.session() as db:
            if db.get(ConfigVersion, self.cfg.config_version) is None:
                last = db.scalars(select(ConfigVersion).order_by(ConfigVersion.first_seen_at.desc())).first()
                db.add(ConfigVersion(config_version=self.cfg.config_version, schema_version=s.config_schema_version,
                                     sha256=self.cfg.sha256, content_json=dumps(self.cfg.raw), first_seen_at=iso()))
                db.flush()
                if last is not None:
                    self.audit.record(db, AuditEvent.CONFIG_CHANGE, details={"old": last.config_version,
                                                                             "new": self.cfg.config_version})
            for me in self.registry.active.values():
                for ev, details in me.events:
                    self.audit.record(db, ev, outcome="FAILURE", details=details)
                prev = db.scalars(select(ModelVersion).where(ModelVersion.model_id == me.model_id)
                                  .order_by(ModelVersion.first_seen_at.desc())).first()
                row = db.get(ModelVersion, me.key)
                if row is None:
                    db.add(ModelVersion(model_key=me.key, model_id=me.model_id, version=me.version,
                                        sha256=me.entry.get("sha256"), license=me.entry.get("license"),
                                        license_status=me.entry.get("license_status"),
                                        registry_entry_json=json.dumps(me.entry, default=str), first_seen_at=iso(),
                                        status=me.status))
                    if prev is not None:
                        self.audit.record(db, AuditEvent.MODEL_CHANGE, details={"model_id": me.model_id,
                                                                                "old": prev.model_key, "new": me.key})
                else:
                    row.status = me.status

    # ------------------------------------------------------------------
    def readiness_items(self) -> list[dict]:
        def val(slot):
            me = self.registry.entry(slot)
            return bool(me and (me.entry.get("performance_metrics") or {}).get("local_validated"))

        cal = self.recognition.calibration_state()["state"] == "CALIBRATED"
        licences_ok = all(me.entry.get("license_status") == "APPROVED" for me in self.registry.active.values())
        bench = any((self.cfg.root / "reports" / "benchmarks").glob("*.json")) if (self.cfg.root / "reports" / "benchmarks").exists() else False
        items = [
            ("G1", "Detector validated locally", val("detector"), "No local validation report"),
            ("G2", "Expression model validated and calibrated", val("expression"), "No local validation report; temperature = default"),
            ("G3", "Recognition thresholds calibrated", cal, "No calibration file; using demo_uncalibrated thresholds"),
            ("G4", "Fairness evaluated", False, "Subgroup evaluation not yet performed"),
            ("G5", "Liveness / PAD validated", False, "Liveness not implemented"),
            ("G6", "Latency measured on the target hardware", bench, "Run tools/benchmark_latency.py on the deployment device"),
            ("G7", "Licenses approved", licences_ok, "A loaded model is not license-approved"),
            ("G8", "Security review", False, "No external security review"),
            ("G9", "Privacy & legal review", False, "No DPIA / jurisdiction review"),
            ("G10", "Clinical-claim review", False, "Brief §1–12 not reconciled; no qualified clinical review"),
            ("G11", "Operational readiness", False, "No backup/restore or incident-response procedure"),
        ]
        return [{"id": i, "criterion": c, "status": "MET" if ok else "NOT_MET", "reason": None if ok else r}
                for i, c, ok, r in items]

    def model_info(self) -> dict:
        items = self.readiness_items()
        return {
            "models": [me.public() for me in self.registry.active.values()],
            "recognition_calibration": self.recognition.calibration_state(),
            "liveness": {"state": "NOT_IMPLEMENTED"},
            "fairness": "not yet evaluated",
            "keystore": {"available": self.templates.available, "reason": self.keystore_error},
            "config_version": self.cfg.config_version,
            "production_readiness_gate": "MET" if all(i["status"] == "MET" for i in items) else "NOT_MET",
            "production_readiness_items": items,
        }

    def audit_tail(self, n: int = 1) -> list[AuditLog]:
        with self.db.session() as s:
            return list(s.scalars(select(AuditLog).order_by(AuditLog.audit_id.desc()).limit(n)))

    def close(self) -> None:
        self.retention.stop()
        self.registry.close()
