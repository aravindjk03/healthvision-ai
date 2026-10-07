"""AnalysisSessionService — ties BMI / face / recognition results of one analysis together."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import not_found
from ..core.util import dumps, iso, iso_in_days, loads, uuid7
from ..domain import messages as M
from ..storage.orm import (AnalysisSession, BmiRecord, ExpressionResult, FaceObservation, RecognitionEvent)
from .consent_service import ConsentService


class AnalysisSessionService:
    def __init__(self, config_version: str, retention_days: int, consent: ConsentService):
        self.config_version = config_version
        self.retention_days = retention_days
        self.consent = consent

    def create(self, s: Session, user_id: str) -> AnalysisSession:
        row = AnalysisSession(session_id=uuid7(), user_id=user_id, started_at=iso(), config_version=self.config_version,
                              latency_json=dumps({}), consent_snapshot_json=dumps(self.consent.snapshot(s, user_id)),
                              status="OPEN", expires_at=iso_in_days(self.retention_days))
        s.add(row)
        s.flush()
        return row

    def get_owned(self, s: Session, user_id: str, session_id: str) -> AnalysisSession:
        row = s.get(AnalysisSession, session_id)
        if row is None or row.user_id != user_id:
            raise not_found()
        return row

    def get_or_create(self, s: Session, user_id: str, session_id: Optional[str]) -> AnalysisSession:
        return self.get_owned(s, user_id, session_id) if session_id else self.create(s, user_id)

    def add_latency(self, row: AnalysisSession, step: str, latency: dict) -> None:
        cur = loads(row.latency_json) or {}
        cur[step] = latency
        row.latency_json = dumps(cur)
        row.completed_at = iso()
        row.status = "COMPLETED"

    def dashboard(self, s: Session, user_id: str, session_id: str) -> dict:
        sess = self.get_owned(s, user_id, session_id)
        bmi = s.scalars(select(BmiRecord).where(BmiRecord.session_id == session_id)
                        .order_by(BmiRecord.timestamp.desc())).first()
        obs = s.scalars(select(FaceObservation).where(FaceObservation.session_id == session_id,
                                                      FaceObservation.purpose == "FACE_ANALYSIS")
                        .order_by(FaceObservation.timestamp.desc())).first()
        expr = None
        if obs is not None:
            expr = s.scalars(select(ExpressionResult).where(ExpressionResult.observation_id == obs.observation_id)).first()
        rec = s.scalars(select(RecognitionEvent).where(RecognitionEvent.session_id == session_id)
                        .order_by(RecognitionEvent.timestamp.desc())).first()
        models: dict = {}
        if obs is not None:
            models.update(loads(obs.models_json))
        if expr is not None:
            models["expression"] = expr.model_version
        if rec is not None:
            models["embedding"] = rec.model_version
        return {
            "analysis_id": sess.session_id,
            "started_at": sess.started_at,
            "completed_at": sess.completed_at,
            "calculated": {"bmi": loads(bmi.result_json) if bmi else None},
            "ai_estimates": {
                "face": ({"face_state": obs.face_state, "face_count": obs.face_count, "faces": loads(obs.bboxes_json),
                          "pose": loads(obs.pose_json)} if obs else None),
                "quality": ({"grade": obs.quality_grade, "checks": loads(obs.quality_checks_json)} if obs else None),
                "expression": loads(expr.result_json) if expr else None,
            },
            "identity": {"recognition": loads(rec.result_json) if rec else None},
            "model_versions": models,
            "config_version": sess.config_version,
            "latency_ms": loads(sess.latency_json) or {},
            "notes": [M.EXPRESSION_NOTE, M.BMI_NOTE, M.DASHBOARD_FOOTER],
        }
