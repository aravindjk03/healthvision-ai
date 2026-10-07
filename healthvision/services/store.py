"""In-memory data store for one browser session (hosted-demo retention mode).

Mirrors the logical entities in docs/08 but keeps everything in memory: nothing is
written to disk, and all data disappears when the browser session ends.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

from healthvision.domain import new_id, utcnow


@dataclass
class AnalysisSession:
    session_id: str = field(default_factory=new_id)
    started_at: str = field(default_factory=utcnow)
    config_version: str = ""
    bmi: Any = None                      # BmiResult
    face: Any = None                     # FaceAnalysisResult
    recognition: Any = None              # RecognitionResult
    consent_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class EncryptedTemplate:
    template_id: str
    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes
    dek_nonce: bytes
    frame_quality: dict[str, Any]
    created_at: str


@dataclass
class Enrollment:
    enrollment_id: str
    consent_id: str
    model_version: str
    embedding_dim: int
    templates: list[EncryptedTemplate]
    status: str = "ACTIVE"
    created_at: str = field(default_factory=utcnow)
    revoked_at: str | None = None
    revocation_reason: str | None = None


class AuditLog:
    """Append-only, hash-chained audit log (docs/10 §6). Never stores biometric content."""

    FORBIDDEN_KEYS = ("embedding", "template", "image", "landmarks", "probs_raw", "feature")

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, event_type: str, outcome: str = "SUCCESS", target_id: str | None = None,
               **details: Any) -> None:
        for key in details:
            if any(f in key.lower() for f in self.FORBIDDEN_KEYS):
                raise ValueError(f"Refusing to audit biometric field '{key}'")
        prev = self.entries[-1]["entry_hash"] if self.entries else "0" * 64
        row = {"audit_id": len(self.entries) + 1, "timestamp": utcnow(), "event_type": event_type,
               "outcome": outcome, "target_id": target_id, "details": details, "prev_hash": prev}
        row["entry_hash"] = hashlib.sha256((prev + json.dumps(row, sort_keys=True, default=str)).encode()).hexdigest()
        self.entries.append(row)

    def verify(self) -> int | None:
        """Return the audit_id of the first broken entry, or None if the chain is intact."""
        prev = "0" * 64
        for row in self.entries:
            body = {k: v for k, v in row.items() if k != "entry_hash"}
            if body["prev_hash"] != prev:
                return row["audit_id"]
            digest = hashlib.sha256((prev + json.dumps(body, sort_keys=True, default=str)).encode()).hexdigest()
            if digest != row["entry_hash"]:
                return row["audit_id"]
            prev = row["entry_hash"]
        return None


class DataStore:
    def __init__(self) -> None:
        self.user_id = new_id()
        self.consents: list[dict[str, Any]] = []          # append-only consent rows
        self.analyses: dict[str, AnalysisSession] = {}
        self.current_analysis_id: str | None = None
        self.enrollment: Enrollment | None = None
        self.past_enrollments: list[Enrollment] = []
        self.recognition_events: list[Any] = []
        self.reports: list[dict[str, Any]] = []
        self.verify_attempts: list[float] = []
        self.consecutive_no_match = 0
        self.locked_until: float = 0.0
        self.audit = AuditLog()
        self.kek = os.urandom(32)                         # session-scoped key-encryption key

    def current_analysis(self) -> AnalysisSession | None:
        return self.analyses.get(self.current_analysis_id or "")
