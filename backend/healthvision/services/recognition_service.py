"""RecognitionService — consent-based enrollment and 1:1 verification (docs/06).

Identification (1:N) is a separate method behind ``features.identification_enabled`` and is
disabled in V1. Probe embeddings are held in memory only and never persisted.
"""
from __future__ import annotations

import itertools
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config.settings import LoadedConfig
from ..core.errors import ApiError
from ..core.latency import LatencyRecorder
from ..core.util import dumps, iso, iso_in_days, sha256_hex, uuid7
from ..domain import messages as M
from ..domain.enums import AuditEvent, EnrollmentStatus, RecognitionDecision
from ..registry.model_registry import ModelRegistry
from ..storage.orm import FaceEnrollment, RecognitionEvent
from ..storage.template_store import TemplateStore
from . import decision_engine as DE
from .audit_service import AuditService
from .consent_service import ConsentService
from .face_pipeline import FacePipeline
from .session_service import AnalysisSessionService


class RateLimiter:
    """In-process sliding-window limiter (V1; Redis-backed in V3)."""

    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, per_minute: Optional[int], per_hour: Optional[int]) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 3600:
                q.popleft()
            if per_hour is not None and len(q) >= per_hour:
                return False
            if per_minute is not None and sum(1 for t in q if now - t <= 60) >= per_minute:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RecognitionService:
    def __init__(self, cfg: LoadedConfig, registry: ModelRegistry, pipeline: FacePipeline, consent: ConsentService,
                 sessions: AnalysisSessionService, templates: TemplateStore, audit: AuditService, limiter: RateLimiter):
        self.cfg = cfg
        self.s = cfg.settings
        self.registry = registry
        self.pipeline = pipeline
        self.consent = consent
        self.sessions = sessions
        self.templates = templates
        self.audit = audit
        self.limiter = limiter
        self._no_match_streak: dict[str, int] = defaultdict(int)
        self._locked_until: dict[str, float] = {}
        self.calibration = self._load_calibration()

    # ---------------------------------------------------------------- thresholds
    def _load_calibration(self) -> Optional[dict]:
        p: Path = self.cfg.resolve(self.s.recognition.calibration_file)
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        emb = self.registry.entry("embedding")
        if emb and (data.get("model_id") != emb.model_id or str(data.get("model_version")) != emb.version):
            return None  # calibration for another model is not valid here
        data["_sha256"] = sha256_hex(p.read_bytes())
        return data

    def thresholds(self) -> tuple[float, float, str]:
        if self.calibration:
            t_m = float(self.calibration["recognition_threshold"])
            t_n = min(float(self.calibration["no_match_threshold"]), t_m)
            return t_m, t_n, "calibration_file"
        d = self.s.recognition.demo_uncalibrated_thresholds
        return d.recognition_threshold, min(d.no_match_threshold, d.recognition_threshold), "demo_uncalibrated"

    def calibration_state(self) -> dict:
        if self.calibration:
            return {"state": "CALIBRATED", "file": self.s.recognition.calibration_file,
                    "sha256": self.calibration["_sha256"]}
        return {"state": "UNCALIBRATED", "file": None}

    # ---------------------------------------------------------------- helpers
    def _available(self) -> None:
        if not self.s.features.recognition_enabled:
            raise ApiError(403, "FEATURE_DISABLED", "Face recognition is disabled on this device.")
        if not self.templates.available:
            raise ApiError(503, "KEYSTORE_UNAVAILABLE", "Secure key storage is unavailable; recognition is disabled.")
        if not self.registry.ready("embedding") or not self.registry.ready("detector"):
            raise ApiError(503, "MODEL_UNAVAILABLE", "Face recognition is unavailable on this device.")

    def active_enrollment(self, s: Session, user_id: str) -> Optional[FaceEnrollment]:
        return s.scalars(select(FaceEnrollment).where(FaceEnrollment.user_id == user_id,
                                                      FaceEnrollment.status == EnrollmentStatus.ACTIVE.value)).first()

    def enrollment_status(self, s: Session, user_id: str) -> dict:
        e = self.active_enrollment(s, user_id)
        emb = self.registry.entry("embedding")
        if e is None:
            return {"enrolled": False}
        stale = emb is not None and e.model_version != emb.key
        return {"enrolled": True, "enrollment_id": e.enrollment_id, "status": "STALE" if stale else e.status,
                "created_at": e.created_at, "template_count": e.template_count, "model_version": e.model_version}

    def revoke_enrollment(self, s: Session, user_id: str, reason: str, actor_role: str = "USER") -> int:
        n = 0
        for e in s.scalars(select(FaceEnrollment).where(FaceEnrollment.user_id == user_id,
                                                        FaceEnrollment.status != EnrollmentStatus.REVOKED.value)).all():
            shredded = self.templates.crypto_shred(s, enrollment_id=e.enrollment_id)
            e.status, e.revoked_at, e.revocation_reason = EnrollmentStatus.REVOKED.value, iso(), reason
            s.flush()
            self.audit.record(s, AuditEvent.TEMPLATE_DELETION, actor_user_id=user_id, actor_role=actor_role,
                              target_type="enrollment", target_id=e.enrollment_id,
                              details={"count": shredded, "reason": reason})
            n += shredded
        return n

    # ---------------------------------------------------------------- enrollment
    def enroll(self, s: Session, user_id: str, role: str, session_id: Optional[str], frames: list[bytes], replace: bool) -> dict:
        self._available()
        consent = self.consent.require(s, user_id, "RECOGNITION")
        rf = self.s.recognition
        if not (rf.enrollment_frames.min <= len(frames) <= rf.enrollment_frames.max):
            raise ApiError(400, "VALIDATION_ERROR",
                           f"Provide between {rf.enrollment_frames.min} and {rf.enrollment_frames.max} images.")
        if not self.limiter.hit(f"enroll:{user_id}", None, rf.enroll_rate_limit.per_hour):
            self.audit.record(s, AuditEvent.RATE_LIMITED, outcome="DENIED", actor_user_id=user_id, details={"endpoint": "enroll"})
            raise ApiError(429, "RATE_LIMITED", "Too many enrollment attempts. Please try again later.")
        existing = self.active_enrollment(s, user_id)
        if existing and not replace:
            raise ApiError(409, "ENROLLMENT_EXISTS", "You already have an active enrollment. Use replace to re-enroll.")
        sess = self.sessions.get_or_create(s, user_id, session_id)
        emb_engine = self.registry.engine("embedding")
        liveness = self.registry.engine("liveness")
        lat = LatencyRecorder()
        accepted: list[tuple[int, np.ndarray, dict]] = []
        frame_report = []
        for i, data in enumerate(frames):
            r = self.pipeline.run(data, lat, full=True, enrollment_profile=True)
            if r.stopped:
                frame_report.append({"index": i, "accepted": False, "reason": r.stop_reason, "message": r.message,
                                     "quality": r.quality_grade.value if r.quality_grade else None})
                continue
            with lat.stage("embedding"):
                vec = emb_engine.embed(r.aligned)
            q = {"grade": r.quality_grade.value,
                 "checks": {c["check"]: c["value"] for c in r.face_checks if c["check"] in ("face_blur", "pose")}}
            accepted.append((i, vec, q))
            frame_report.append({"index": i, "accepted": True, "quality": r.quality_grade.value})
            del r  # raw frame no longer referenced
        frames.clear()
        live = liveness.assess([]).status if liveness else "NOT_PERFORMED"
        if not accepted:
            self.audit.record(s, AuditEvent.FACE_ENROLLMENT, outcome="FAILURE", actor_user_id=user_id, actor_role=role,
                              details={"reason": "NO_ACCEPTED_FRAMES", "frames": len(frame_report)})
            raise ApiError(400, "VALIDATION_ERROR", "No frame met the enrollment quality requirements. Please retake.",
                           {"frames": frame_report})
        t_match, _, source = self.thresholds()
        for (ia, a, _), (ib, b, _) in itertools.combinations(accepted, 2):
            if emb_engine.similarity(a, b) < t_match:
                self.audit.record(s, AuditEvent.FACE_ENROLLMENT, outcome="FAILURE", actor_user_id=user_id,
                                  actor_role=role, details={"reason": "ENROLLMENT_INCONSISTENT"})
                raise ApiError(409, "ENROLLMENT_INCONSISTENT",
                               "The captured frames do not appear to show the same person. Please retake.",
                               {"frames": [ia, ib]})
        if existing:
            self.revoke_enrollment(s, user_id, "RE_ENROLLED", role)
        accepted = accepted[: rf.max_templates_per_user]
        emb_entry = self.registry.entry("embedding")
        enr = FaceEnrollment(enrollment_id=uuid7(), user_id=user_id, consent_id=consent.consent_id,
                             template_reference="", model_version=emb_entry.key,
                             embedding_dim=int(accepted[0][1].shape[0]), template_count=len(accepted),
                             status=EnrollmentStatus.ACTIVE.value, created_at=iso())
        enr.template_reference = enr.enrollment_id
        s.add(enr)
        s.flush()
        for _, vec, q in accepted:
            self.templates.store(s, user_id, enr.enrollment_id, vec, q)
        accepted.clear()
        latency = lat.finish()
        self.sessions.add_latency(sess, "face_enroll", latency)
        self.audit.record(s, AuditEvent.FACE_ENROLLMENT, actor_user_id=user_id, actor_role=role,
                          target_type="enrollment", target_id=enr.enrollment_id,
                          details={"template_count": enr.template_count, "model_version": enr.model_version,
                                   "quality_grades": [f.get("quality") for f in frame_report]})
        return {"enrollment_id": enr.enrollment_id, "status": enr.status, "template_count": enr.template_count,
                "frames": frame_report, "model_version": enr.model_version, "liveness": live,
                "threshold_source": source, "notice": M.LIVENESS, "session_id": sess.session_id, "latency_ms": latency}

    # ---------------------------------------------------------------- verification
    def verify(self, s: Session, user_id: str, role: str, session_id: Optional[str], data: bytes,
               client_ms: Optional[float]) -> dict:
        self._available()
        rf = self.s.recognition
        sess = self.sessions.get_or_create(s, user_id, session_id)
        lat = LatencyRecorder()
        lat.set("capture_upload", client_ms)
        t_match, t_nomatch, source = self.thresholds()
        emb_entry = self.registry.entry("embedding")
        liveness = self.registry.engine("liveness")
        live = "NOT_PERFORMED"
        decision, reason, similarity, quality, enr, input_sha = RecognitionDecision.NOT_PERFORMED, None, None, None, None, sha256_hex(data)
        trace: dict = {}

        consent_row = self.consent.current(s, user_id, "RECOGNITION")
        if not self.consent.is_granted(consent_row):
            raise ApiError(403, "CONSENT_REQUIRED", "Recognition consent is required.", {"purpose": "RECOGNITION"})
        locked = self._locked_until.get(user_id, 0)
        if locked > time.monotonic():
            raise ApiError(423, "VERIFICATION_LOCKED", "Verification is temporarily locked after repeated failures.")
        if not self.limiter.hit(f"verify:{user_id}", rf.rate_limit.per_minute, rf.rate_limit.per_hour):
            self.audit.record(s, AuditEvent.RATE_LIMITED, outcome="DENIED", actor_user_id=user_id, details={"endpoint": "verify"})
            raise ApiError(429, "RATE_LIMITED", "Too many verification attempts. Please try again later.")

        enr = self.active_enrollment(s, user_id)
        if enr is None:
            reason = "NO_ENROLLMENT"
        elif enr.model_version != emb_entry.key:
            reason = "TEMPLATE_MODEL_MISMATCH"
        else:
            r = self.pipeline.run(data, lat, full=True)
            input_sha = r.ingested.sha256
            quality = r.quality_grade.value if r.quality_grade else None
            if r.stopped:
                reason = {"POOR_QUALITY": "QUALITY_REJECTED"}.get(r.stop_reason, r.stop_reason)
            else:
                with lat.stage("liveness"):
                    live = liveness.assess([]).status if liveness else "NOT_PERFORMED"
                with lat.stage("embedding"):
                    probe = self.registry.engine("embedding").embed(r.aligned)
                del r
                with lat.stage("comparison"):
                    refs = self.templates.load(s, user_id, enr.enrollment_id)
                    sims = [self.registry.engine("embedding").similarity(probe, t) for t in refs]
                    del probe, refs
                similarity = round(max(sims), 4)
                decision, tr = DE.recognition(similarity, t_match, t_nomatch, source, self.cfg.config_version, len(sims))
                trace = tr.as_dict()
        if decision == RecognitionDecision.NOT_PERFORMED:
            trace = {"rule_id": "recognition.v1", "outcome": "NOT_PERFORMED", "reasons": [reason],
                     "threshold_source": source, "config_version": self.cfg.config_version}
        # lockout bookkeeping
        if decision == RecognitionDecision.NO_MATCH:
            self._no_match_streak[user_id] += 1
            if self._no_match_streak[user_id] >= rf.lockout_after_consecutive_no_match:
                self._locked_until[user_id] = time.monotonic() + rf.lockout_minutes * 60
                self._no_match_streak[user_id] = 0
                self.audit.record(s, AuditEvent.LOCKOUT, outcome="DENIED", actor_user_id=user_id, details={"endpoint": "verify"})
        elif decision == RecognitionDecision.MATCH:
            self._no_match_streak[user_id] = 0

        latency = lat.finish()
        msg = M.VERIFY_MESSAGES[decision.value].format(reason=reason) if decision == RecognitionDecision.NOT_PERFORMED \
            else M.VERIFY_MESSAGES[decision.value]
        result = {"mode": "VERIFY", "decision": decision.value, "not_performed_reason": reason,
                  "similarity": similarity,
                  "thresholds": {"match": t_match, "no_match": t_nomatch, "source": source},
                  "demo_uncalibrated": source == "demo_uncalibrated",
                  "demo_banner": M.DEMO_UNCALIBRATED if source == "demo_uncalibrated" else None,
                  "liveness": live, "liveness_notice": M.LIVENESS_FULL, "quality": quality, "message": msg,
                  "model_version": emb_entry.key, "config_version": self.cfg.config_version}
        days = self.s.retention.retention_period_days.get("recognition_events", 90)
        ev = RecognitionEvent(event_id=uuid7(), session_id=sess.session_id, user_id=user_id, mode="VERIFY",
                              claimed_identity=user_id,
                              matched_identity=user_id if decision == RecognitionDecision.MATCH else None,
                              similarity=similarity, decision=decision.value, not_performed_reason=reason,
                              liveness_status=live, quality_grade=quality, model_version=emb_entry.key,
                              threshold_match=t_match, threshold_no_match=t_nomatch, threshold_source=source,
                              enrollment_id=enr.enrollment_id if enr else None, input_sha256=input_sha,
                              config_version=self.cfg.config_version,
                              consent_snapshot_json=dumps({"RECOGNITION": {"consent_id": consent_row.consent_id,
                                                                           "policy_version": consent_row.policy_version,
                                                                           "status": consent_row.consent_status}}),
                              result_json=dumps(result), trace_json=dumps(trace), timestamp=iso(),
                              expires_at=iso_in_days(days))
        s.add(ev)
        self.sessions.add_latency(sess, "face_verify", latency)
        self.audit.record(s, AuditEvent.RECOGNITION_ATTEMPT, actor_user_id=user_id, actor_role=role,
                          target_type="recognition_event", target_id=ev.event_id,
                          details={"decision": decision.value, "threshold_source": source, "liveness_status": live,
                                   "reason": reason})
        return {"event_id": ev.event_id, "session_id": sess.session_id, **result, "latency_ms": latency}

    def identify(self) -> None:
        if not self.s.features.identification_enabled:
            raise ApiError(403, "FEATURE_DISABLED", "Identification (1:N) is not available in this version.")
        raise ApiError(403, "FEATURE_DISABLED", "Identification (1:N) is not implemented in V1.")  # pragma: no cover
