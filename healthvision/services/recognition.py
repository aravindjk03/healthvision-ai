"""RecognitionService — consent-gated enrollment and 1:1 verification (docs/06).

Templates are envelope-encrypted (AES-256-GCM per-template key, wrapped by a session KEK).
Probe embeddings and face images are held in memory only. Identification (1:N) is disabled.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from healthvision.config import ROOT, Config
from healthvision.domain import (
    GRADE_ORDER, ConsentPurpose, DecisionTrace, LivenessStatus, QualityGrade, RecognitionDecision, new_id, utcnow,
)
from healthvision.runtime import Engines
from healthvision.services import decision
from healthvision.services.consent import ConsentService
from healthvision.services.face_analysis import FaceAnalysisService
from healthvision.services.store import DataStore, EncryptedTemplate, Enrollment

LIVENESS_NOTICE = ("Liveness detection is not implemented in this version. Verification can be fooled by "
                   "photos or screens. Do not use for security decisions.")
MESSAGES = {
    RecognitionDecision.MATCH: "Verified — matches your enrolled identity",
    RecognitionDecision.NO_MATCH: "Not verified — does not match your enrolled identity",
    RecognitionDecision.UNCERTAIN: ("Uncertain — the result is borderline. Please retry with better lighting, "
                                    "facing the camera."),
}
NOT_PERFORMED_MESSAGES = {
    "NO_CONSENT": "Recognition consent is required.",
    "NO_ENROLLMENT": "You have not enrolled a face template yet.",
    "QUALITY_REJECTED": "Image quality too low for verification. Please retake.",
    "NO_FACE": "No face detected. Please retake the image.",
    "MULTIPLE_FACES": "Multiple faces detected. Please ensure only one person is in frame.",
    "TEMPLATE_MODEL_MISMATCH": "Your template was created with a different model. Please re-enroll.",
    "RATE_LIMITED": "Too many verification attempts. Please wait a minute.",
    "LOCKED": "Verification is temporarily locked after repeated non-matches.",
    "MODEL_UNAVAILABLE": "Recognition is unavailable on this device.",
}


class FeatureDisabled(RuntimeError):
    pass


class EnrollmentError(ValueError):
    def __init__(self, code: str, message: str, frames: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.frames = frames or []


@dataclass
class RecognitionResult:
    mode: str
    decision: RecognitionDecision
    event_id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=utcnow)
    not_performed_reason: str | None = None
    similarity: float | None = None
    thresholds: dict[str, float] = field(default_factory=dict)
    threshold_source: str = ""
    liveness: LivenessStatus = LivenessStatus.NOT_PERFORMED
    quality: str | None = None
    face_state: str | None = None
    message: str = ""
    model_version: str | None = None
    config_version: str = ""
    consent_snapshot: dict[str, Any] = field(default_factory=dict)
    trace: DecisionTrace | None = None
    input_sha256: str | None = None
    latency_ms: dict[str, float] = field(default_factory=dict)
    enrollment_id: str | None = None

    @property
    def demo_uncalibrated(self) -> bool:
        return self.threshold_source == "demo_uncalibrated"


def _aad(template_id: str, user_id: str, model_key: str) -> bytes:
    return f"{template_id}|{user_id}|{model_key}".encode()


def encrypt_embedding(store: DataStore, embedding: np.ndarray, model_key: str,
                      frame_quality: dict[str, Any]) -> EncryptedTemplate:
    template_id = new_id()
    dek = AESGCM.generate_key(bit_length=256)
    nonce, dek_nonce = os.urandom(12), os.urandom(12)
    aad = _aad(template_id, store.user_id, model_key)
    ciphertext = AESGCM(dek).encrypt(nonce, embedding.astype(np.float32).tobytes(), aad)
    wrapped = AESGCM(store.kek).encrypt(dek_nonce, dek, aad)
    return EncryptedTemplate(template_id, ciphertext, nonce, wrapped, dek_nonce, frame_quality, utcnow())


def decrypt_embedding(store: DataStore, tpl: EncryptedTemplate, model_key: str) -> np.ndarray:
    aad = _aad(tpl.template_id, store.user_id, model_key)
    dek = AESGCM(store.kek).decrypt(tpl.dek_nonce, tpl.wrapped_dek, aad)
    return np.frombuffer(AESGCM(dek).decrypt(tpl.nonce, tpl.ciphertext, aad), dtype=np.float32)


def shred_enrollment(store: DataStore, reason: str) -> int:
    """Crypto-shred: destroy wrapped keys, then drop ciphertext. Returns number of templates destroyed."""
    enr = store.enrollment
    if enr is None:
        return 0
    count = len(enr.templates)
    for tpl in enr.templates:
        tpl.wrapped_dek = os.urandom(len(tpl.wrapped_dek))
        tpl.ciphertext = b""
    enr.templates = []
    enr.status, enr.revoked_at, enr.revocation_reason = "REVOKED", utcnow(), reason
    store.past_enrollments.append(enr)
    store.enrollment = None
    store.audit.record("TEMPLATE_DELETION", target_id=enr.enrollment_id, count=count, reason=reason)
    return count


class RecognitionService:
    def __init__(self, config: Config, engines: Engines, consent: ConsentService, faces: FaceAnalysisService,
                 store: DataStore):
        self.config = config
        self.cfg = config["recognition"]
        self.engines = engines
        self.consent = consent
        self.faces = faces
        self.store = store

    # ---- thresholds -------------------------------------------------------------------------
    def thresholds(self) -> tuple[float, float, str]:
        path = ROOT / self.cfg["calibration_file"]
        if path.exists():
            cal = json.loads(Path(path).read_text())
            return float(cal["recognition_threshold"]), float(cal["no_match_threshold"]), "calibration_file"
        demo = self.cfg["demo_uncalibrated_thresholds"]
        return float(demo["recognition_threshold"]), float(demo["no_match_threshold"]), "demo_uncalibrated"

    def _model_key(self) -> str:
        return self.engines.embedder.info().key

    # ---- enrollment -------------------------------------------------------------------------
    def enroll(self, frames: list[bytes]) -> Enrollment:
        consent_row = self.consent.require(ConsentPurpose.RECOGNITION)
        if self.engines.embedder is None:
            raise EnrollmentError("MODEL_UNAVAILABLE", NOT_PERFORMED_MESSAGES["MODEL_UNAVAILABLE"])
        limits = self.cfg["enrollment_frames"]
        if not limits["min"] <= len(frames) <= limits["max"]:
            raise EnrollmentError("VALIDATION_ERROR", f"Provide between {limits['min']} and {limits['max']} images.")
        accepted: list[tuple[np.ndarray, dict[str, Any]]] = []
        report: list[dict[str, Any]] = []
        for i, data in enumerate(frames):
            pipe = self.faces.run_pipeline(data, purpose="ENROLLMENT")
            ok = (pipe.proceeded and pipe.aligned is not None and pipe.quality_grade is not None
                  and GRADE_ORDER[pipe.quality_grade] <= GRADE_ORDER[QualityGrade(self.cfg["enrollment_min_quality"])])
            reason = None if ok else (pipe.stopped_reason or f"QUALITY_{pipe.quality_grade}")
            if ok:
                emb = self.engines.embedder.embed(pipe.aligned)
                accepted.append((emb, {"grade": str(pipe.quality_grade)}))
            pipe.aligned = None
            report.append({"index": i + 1, "accepted": ok, "reason": reason, "message": pipe.message,
                           "quality": str(pipe.quality_grade) if pipe.quality_grade else None})
        if not accepted:
            self.store.audit.record("FACE_ENROLLMENT", outcome="FAILURE", reason="NO_ACCEPTED_FRAMES")
            raise EnrollmentError("QUALITY_REJECTED",
                                  f"No image passed the enrollment quality check ({self.cfg['enrollment_min_quality']} quality and one face required).",
                                  report)
        t_match, _, _ = self.thresholds()
        for a in range(len(accepted)):
            for b in range(a + 1, len(accepted)):
                if self.engines.embedder.similarity(accepted[a][0], accepted[b][0]) < t_match:
                    self.store.audit.record("FACE_ENROLLMENT", outcome="FAILURE", reason="ENROLLMENT_INCONSISTENT")
                    raise EnrollmentError("ENROLLMENT_INCONSISTENT",
                                          "The enrollment images do not appear to show the same person.", report)
        if self.store.enrollment is not None:
            shred_enrollment(self.store, "RE_ENROLLED")
        model_key = self._model_key()
        templates = [encrypt_embedding(self.store, emb, model_key, q) for emb, q in accepted]
        for emb, _ in accepted:
            emb.fill(0)
        enr = Enrollment(enrollment_id=new_id(), consent_id=consent_row["consent_id"], model_version=model_key,
                         embedding_dim=int(accepted[0][0].shape[0]), templates=templates)
        enr.frames_report = report  # type: ignore[attr-defined]
        self.store.enrollment = enr
        self.store.audit.record("FACE_ENROLLMENT", target_id=enr.enrollment_id, count=len(templates),
                                model_version=model_key)
        return enr

    def delete_enrollment(self) -> int:
        return shred_enrollment(self.store, "USER_DELETED")

    # ---- verification -----------------------------------------------------------------------
    def _not_performed(self, reason: str, **kw: Any) -> RecognitionResult:
        res = RecognitionResult(mode="VERIFY", decision=RecognitionDecision.NOT_PERFORMED,
                                not_performed_reason=reason, message=NOT_PERFORMED_MESSAGES.get(reason, reason),
                                config_version=self.config.version, consent_snapshot=self.consent.snapshot(), **kw)
        self._log(res)
        return res

    def _log(self, res: RecognitionResult) -> None:
        self.store.recognition_events.append(res)
        self.store.audit.record("RECOGNITION_ATTEMPT", target_id=res.event_id, decision=str(res.decision),
                                reason=res.not_performed_reason, threshold_source=res.threshold_source,
                                liveness=str(res.liveness))

    def verify(self, data: bytes) -> RecognitionResult:
        if not self.consent.is_granted(ConsentPurpose.RECOGNITION):
            self.store.audit.record("CONSENT_CHECK", outcome="DENIED", purpose="RECOGNITION")
            return self._not_performed("NO_CONSENT")
        if self.engines.embedder is None:
            return self._not_performed("MODEL_UNAVAILABLE")
        now = time.time()
        if now < self.store.locked_until:
            return self._not_performed("LOCKED")
        rl = self.cfg["rate_limit"]
        self.store.verify_attempts = [t for t in self.store.verify_attempts if now - t < 3600]
        if (sum(1 for t in self.store.verify_attempts if now - t < 60) >= rl["per_minute"]
                or len(self.store.verify_attempts) >= rl["per_hour"]):
            self.store.audit.record("RATE_LIMITED", outcome="DENIED", endpoint="verify")
            return self._not_performed("RATE_LIMITED")
        self.store.verify_attempts.append(now)

        enr = self.store.enrollment
        if enr is None or not enr.templates:
            return self._not_performed("NO_ENROLLMENT")
        model_key = self._model_key()
        if enr.model_version != model_key:
            enr.status = "STALE"
            return self._not_performed("TEMPLATE_MODEL_MISMATCH")

        pipe = self.faces.run_pipeline(data, purpose="VERIFICATION")
        common = dict(input_sha256=pipe.input_sha256, face_state=str(pipe.face_state) if pipe.face_state else None,
                      quality=str(pipe.quality_grade) if pipe.quality_grade else None, latency_ms=pipe.latency_ms,
                      enrollment_id=enr.enrollment_id, model_version=model_key)
        if pipe.stopped_reason in ("NO_FACE", "MULTIPLE_FACES"):
            return self._not_performed(pipe.stopped_reason, **common)
        min_q = QualityGrade(self.cfg["verification_min_quality"])
        if (not pipe.proceeded or pipe.aligned is None or pipe.quality_grade is None
                or GRADE_ORDER[pipe.quality_grade] > GRADE_ORDER[min_q]):
            return self._not_performed("QUALITY_REJECTED", **common)

        liveness = self.engines.liveness.assess([])
        t0 = time.perf_counter()
        probe = self.engines.embedder.embed(pipe.aligned)
        pipe.aligned = None
        pipe.latency_ms["embedding"] = round((time.perf_counter() - t0) * 1000, 1)
        t0 = time.perf_counter()
        sims = []
        for tpl in enr.templates:
            ref = decrypt_embedding(self.store, tpl, model_key)
            sims.append(self.engines.embedder.similarity(probe, ref))
        probe.fill(0)
        best = max(sims)
        pipe.latency_ms["comparison"] = round((time.perf_counter() - t0) * 1000, 1)
        pipe.latency_ms["total_pipeline"] = round(sum(v for k, v in pipe.latency_ms.items()
                                                      if k != "total_pipeline"), 1)
        t_match, t_no, source = self.thresholds()
        dec, trace = decision.recognition(best, t_match, t_no, source, self.config)
        res = RecognitionResult(
            mode="VERIFY", decision=dec, similarity=round(best, 4),
            thresholds={"match": t_match, "no_match": t_no}, threshold_source=source,
            liveness=liveness.status, message=MESSAGES[dec], config_version=self.config.version,
            consent_snapshot=self.consent.snapshot(), trace=trace, **common,
        )
        if dec == RecognitionDecision.NO_MATCH:
            self.store.consecutive_no_match += 1
            if self.store.consecutive_no_match >= self.cfg["lockout_after_consecutive_no_match"]:
                self.store.locked_until = time.time() + 60 * self.cfg["lockout_minutes"]
                self.store.consecutive_no_match = 0
                self.store.audit.record("LOCKOUT", outcome="DENIED", endpoint="verify")
        else:
            self.store.consecutive_no_match = 0
        self._log(res)
        return res

    def identify(self, data: bytes) -> RecognitionResult:
        if not self.config["features"]["identification_enabled"]:
            raise FeatureDisabled("Identification (1:N) is disabled in this version.")
        raise NotImplementedError
