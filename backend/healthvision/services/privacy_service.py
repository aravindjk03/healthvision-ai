"""Deletion orchestration, data export and retention purge (docs/09, docs/07 §5, docs/08 §4)."""
from __future__ import annotations

import logging
import threading
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config.settings import Settings
from ..core.util import iso, loads, utcnow
from ..domain.enums import AuditEvent, EnrollmentStatus
from ..storage.orm import (AnalysisSession, AuthSession, BmiRecord, ExpressionResult, FaceEnrollment,
                           FaceObservation, RecognitionEvent, Report, User, UserConsent)
from ..storage.template_store import TemplateStore
from .audit_service import AuditService

log = logging.getLogger("healthvision.privacy")


class PrivacyService:
    def __init__(self, settings: Settings, audit: AuditService, templates: TemplateStore, recognition_revoke):
        self.s = settings
        self.audit = audit
        self.templates = templates
        self._revoke_enrollment = recognition_revoke

    # -------------------------------------------------- revoke hooks
    def on_consent_revoked(self, s: Session, user_id: str, purpose: str) -> dict:
        out: dict = {}
        if purpose == "RECOGNITION":
            out["templates_deleted"] = self._revoke_enrollment(s, user_id, "CONSENT_REVOKED")
        elif self.s.privacy.delete_on_revoke:
            if purpose == "FACE_ANALYSIS":
                out["expression_results"] = s.execute(delete(ExpressionResult).where(ExpressionResult.user_id == user_id)).rowcount
                out["face_observations"] = s.execute(delete(FaceObservation).where(FaceObservation.user_id == user_id)).rowcount
            elif purpose == "BMI":
                out["bmi_records"] = s.execute(delete(BmiRecord).where(BmiRecord.user_id == user_id)).rowcount
            self.audit.record(s, AuditEvent.DATA_DELETION, actor_user_id=user_id,
                              details={"reason": f"{purpose}_CONSENT_REVOKED", "counts": out})
        return out

    # -------------------------------------------------- delete all
    def delete_all(self, s: Session, user_id: str, data_dir: Path) -> dict:
        counts = {"templates": self._revoke_enrollment(s, user_id, "USER_DELETED")}
        for r in s.scalars(select(Report).where(Report.user_id == user_id)).all():
            if r.file_path:
                Path(r.file_path).unlink(missing_ok=True)
        for name, model in (("reports", Report), ("recognition_events", RecognitionEvent),
                            ("expression_results", ExpressionResult), ("face_observations", FaceObservation),
                            ("bmi_records", BmiRecord)):
            counts[name] = s.execute(delete(model).where(model.user_id == user_id)).rowcount
        counts["analysis_sessions"] = s.execute(delete(AnalysisSession).where(AnalysisSession.user_id == user_id)).rowcount
        s.execute(delete(FaceEnrollment).where(FaceEnrollment.user_id == user_id))
        s.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        u = s.get(User, user_id)
        if u is not None:
            u.status, u.deleted_at, u.updated_at = "DELETED", iso(), iso()
            u.display_name, u.username = "deleted user", f"deleted-{user_id}"
            u.password_hash = "!"
        self.audit.record(s, AuditEvent.DATA_DELETION, actor_user_id=user_id,
                          details={"reason": "USER_DELETE_ALL", "counts": counts})
        return counts

    # -------------------------------------------------- export
    def export(self, s: Session, user_id: str) -> dict:
        def rows(model, cols):
            return [{c: getattr(r, c) for c in cols} for r in s.scalars(select(model).where(model.user_id == user_id))]

        return {
            "exported_at": iso(),
            "note": "Biometric templates are never exported.",
            "consents": rows(UserConsent, ["purpose", "consent_status", "timestamp", "policy_version", "revoked_at"]),
            "bmi_records": [{**loads(r.result_json), "timestamp": r.timestamp} | {"trace": None}
                            for r in s.scalars(select(BmiRecord).where(BmiRecord.user_id == user_id))],
            "expression_results": [{"timestamp": r.timestamp, "status": r.status, "expression": r.expression,
                                    "confidence": r.confidence, "confidence_band": r.confidence_band,
                                    "model_version": r.model_version}
                                   for r in s.scalars(select(ExpressionResult).where(ExpressionResult.user_id == user_id))],
            "recognition_events": rows(RecognitionEvent, ["timestamp", "mode", "decision", "similarity",
                                                          "threshold_source", "liveness_status", "model_version"]),
            "enrollments": rows(FaceEnrollment, ["created_at", "status", "model_version", "template_count", "revoked_at"]),
        }


class RetentionService:
    def __init__(self, db, settings: Settings, audit: AuditService, templates: TemplateStore):
        self.db = db
        self.s = settings
        self.audit = audit
        self.templates = templates
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def purge(self) -> dict:
        now = iso()
        counts: dict = {}
        with self.db.session() as s:
            for r in s.scalars(select(Report).where(Report.expires_at < now)).all():
                if r.file_path:
                    Path(r.file_path).unlink(missing_ok=True)
            for name, model in (("reports", Report), ("recognition_events", RecognitionEvent),
                                ("expression_results", ExpressionResult), ("face_observations", FaceObservation),
                                ("bmi_records", BmiRecord)):
                counts[name] = s.execute(delete(model).where(model.expires_at < now)).rowcount
            expired_tpl = self.templates.crypto_shred(s, expired_before=now)
            counts["face_templates"] = expired_tpl
            # enrollments with no templates left are revoked
            for e in s.scalars(select(FaceEnrollment).where(FaceEnrollment.status == EnrollmentStatus.ACTIVE.value)).all():
                if self.templates.count(s, e.enrollment_id) == 0:
                    e.status, e.revoked_at, e.revocation_reason = EnrollmentStatus.REVOKED.value, now, "RETENTION"
            # sessions: expired and childless
            n = 0
            for sess in s.scalars(select(AnalysisSession).where(AnalysisSession.expires_at < now)).all():
                s.delete(sess)
                n += 1
            counts["analysis_sessions"] = n
            counts["auth_sessions"] = s.execute(delete(AuthSession).where(AuthSession.expires_at < now)).rowcount
            days = self.s.retention.retention_period_days.get("audit_logs", 730)
            cutoff = iso(utcnow() - timedelta(days=days))
            counts["audit_logs"] = AuditService.purge_before(s, cutoff)
            self.audit.record(s, AuditEvent.RETENTION_PURGE, details={"counts": counts})
        return counts

    def start(self) -> None:
        def loop():
            while not self._stop.wait(self.s.retention.purge_interval_minutes * 60):
                try:
                    self.purge()
                except Exception:  # pragma: no cover
                    log.exception("retention purge failed")
        self._thread = threading.Thread(target=loop, name="retention", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
