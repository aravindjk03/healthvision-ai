"""FaceAnalysisService — detection, quality, landmarks, pose and expression estimate (docs/05)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..config.settings import Settings
from ..core.latency import LatencyRecorder
from ..core.util import dumps, iso, iso_in_days, uuid7
from ..domain import messages as M
from ..domain.enums import ExpressionStatus
from ..registry.model_registry import ModelRegistry
from ..storage.orm import ExpressionResult, FaceObservation
from . import decision_engine as DE
from .consent_service import ConsentService
from .face_pipeline import FacePipeline, PipelineResult
from .session_service import AnalysisSessionService


class FaceAnalysisService:
    def __init__(self, settings: Settings, config_version: str, registry: ModelRegistry, pipeline: FacePipeline,
                 consent: ConsentService, sessions: AnalysisSessionService):
        self.s = settings
        self.config_version = config_version
        self.registry = registry
        self.pipeline = pipeline
        self.consent = consent
        self.sessions = sessions

    def _observation(self, s: Session, sess_id: str, user_id: str, r: PipelineResult, purpose: str) -> FaceObservation:
        days = self.s.retention.retention_period_days.get("face_observations", 90)
        q = r.quality_dict()
        obs = FaceObservation(
            observation_id=uuid7(), session_id=sess_id, user_id=user_id, purpose=purpose,
            input_sha256=r.ingested.sha256, image_width=r.ingested.width, image_height=r.ingested.height,
            face_count=len(r.detections), face_state=r.face_state.value, bboxes_json=dumps(r.faces_public()),
            quality_grade=q["grade"] if q else None, quality_checks_json=dumps(q["checks"]) if q else None,
            pose_json=dumps(r.landmarks.pose) if r.landmarks else None, models_json=dumps(r.models),
            config_version=self.config_version, timestamp=iso(), expires_at=iso_in_days(days))
        s.add(obs)
        s.flush()
        return obs

    def detect(self, s: Session, user_id: str, session_id: Optional[str], data: bytes, client_ms: Optional[float]) -> dict:
        self.consent.require(s, user_id, "FACE_ANALYSIS")
        sess = self.sessions.get_or_create(s, user_id, session_id)
        lat = LatencyRecorder()
        lat.set("capture_upload", client_ms)
        r = self.pipeline.run(data, lat, full=False)
        obs = self._observation(s, sess.session_id, user_id, r, "FACE_ANALYSIS_PRECHECK")
        latency = lat.finish()
        self.sessions.add_latency(sess, "face_detect", latency)
        return {"session_id": sess.session_id, "observation_id": obs.observation_id, "face_state": r.face_state.value,
                "face_count": len(r.detections), "faces": r.faces_public(),
                "quality_global": {"grade": r.quality_grade.value, "checks": r.global_checks},
                "message": r.message, "models": r.models, "config_version": self.config_version, "latency_ms": latency}

    def analyze(self, s: Session, user_id: str, session_id: Optional[str], data: bytes, client_ms: Optional[float],
                include_landmarks: bool = False) -> dict:
        self.consent.require(s, user_id, "FACE_ANALYSIS")
        sess = self.sessions.get_or_create(s, user_id, session_id)
        lat = LatencyRecorder()
        lat.set("capture_upload", client_ms)
        r = self.pipeline.run(data, lat, full=True)

        expr_engine = self.registry.engine("expression")
        raw = None
        stop = r.stop_reason
        if not r.stopped and expr_engine is None:
            stop = "MODEL_UNAVAILABLE"
        if not r.stopped and expr_engine is not None:
            with lat.stage("expression"):
                raw = expr_engine.predict(r.aligned)
            r.models["expression"] = self.registry.entry("expression").key
        quality = r.quality_grade.value if r.quality_grade else None
        dec = DE.expression(raw, face_state=r.face_state.value, quality=quality,
                            stop_reason=stop if stop not in ("NO_FACE", "MULTIPLE_FACES", "POOR_QUALITY") else None,
                            cfg=self.s.expression, config_version=self.config_version)
        latency = lat.finish()
        expr_key = self.registry.entry("expression").key if self.registry.entry("expression") else "expression.unavailable"
        result = self._expression_dto(dec, expr_key, r)
        obs = self._observation(s, sess.session_id, user_id, r, "FACE_ANALYSIS")
        days = self.s.retention.retention_period_days.get("expression_results", 90)
        er = ExpressionResult(
            result_id=uuid7(), session_id=sess.session_id, user_id=user_id, observation_id=obs.observation_id,
            status=dec.status.value, expression=dec.label, confidence=dec.confidence,
            confidence_band=dec.band.value if dec.band else None,
            probabilities_json=dumps(dec.probabilities) if dec.probabilities else None,
            not_available_reason=dec.not_available_reason, model_version=expr_key,
            thresholds_json=dumps(dec.trace.thresholds), config_version=self.config_version,
            result_json=dumps(result), trace_json=dumps(dec.trace.as_dict()), timestamp=iso(),
            expires_at=iso_in_days(days))
        s.add(er)
        self.sessions.add_latency(sess, "face_expression", latency)
        out = {
            "session_id": sess.session_id, "observation_id": obs.observation_id, "result_id": er.result_id,
            "face": {"face_state": r.face_state.value, "face_count": len(r.detections), "faces": r.faces_public()},
            "quality": r.quality_dict(),
            "pose": r.landmarks.pose if r.landmarks else None,
            "landmarks": {"detected": r.landmarks is not None,
                          "visibility": round(r.landmarks.visibility, 3) if r.landmarks else None,
                          "scheme": r.landmarks.scheme if r.landmarks else None},
            "expression": result, "message": r.message, "models": r.models,
            "config_version": self.config_version, "latency_ms": latency,
        }
        if include_landmarks and r.landmarks is not None:  # overlay preview only; never persisted
            out["landmarks"]["points"] = r.landmarks.points[:, :2].round(1).tolist()
        return out

    def _expression_dto(self, dec: DE.ExpressionDecision, model_key: str, r: PipelineResult) -> dict:
        model_id, _, version = model_key.partition("@")
        label = dec.label.capitalize() if dec.label else None
        if dec.status == ExpressionStatus.ESTIMATED:
            display = M.EXPRESSION_LABEL.format(label=label)
            observation = M.EXPRESSION_OBSERVATION.format(cls=dec.label.lower())
        elif dec.status == ExpressionStatus.UNCERTAIN:
            display, observation = M.EXPRESSION_UNCERTAIN, None
        else:
            display = r.message or (M.MODEL_UNAVAILABLE if dec.not_available_reason == "MODEL_UNAVAILABLE" else M.EXPRESSION_UNCERTAIN)
            observation = None
        return {
            "status": dec.status.value, "expression": dec.label, "display": display,
            "confidence": dec.confidence, "confidence_label": M.CONFIDENCE_LABEL,
            "confidence_band": dec.band.value if dec.band else None,
            "probabilities": dec.probabilities, "observation": observation, "note": M.EXPRESSION_NOTE,
            "not_available_reason": dec.not_available_reason,
            "model": {"model_id": model_id, "version": version},
            "trace": {"rule_id": dec.trace.rule_id, "thresholds": dec.trace.thresholds,
                      "config_version": dec.trace.config_version, "reasons": dec.trace.reasons},
        }
