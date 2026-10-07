"""ConsentService — three independent purposes, append-only records (docs/09)."""
from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import ApiError, consent_required
from ..core.util import iso, sha256_hex, uuid7
from ..domain import messages as M
from ..domain.enums import AuditEvent, ConsentPurpose, ConsentStatus
from ..storage.orm import UserConsent
from .audit_service import AuditService

DECISION_TO_STATUS = {"GRANT": ConsentStatus.GRANTED, "DECLINE": ConsentStatus.DECLINED, "REVOKE": ConsentStatus.REVOKED}


def _major(policy_version: str) -> str:
    # "privacy-1.0" -> "privacy-1"
    head, _, ver = policy_version.rpartition("-")
    return f"{head}-{ver.split('.')[0]}"


class ConsentService:
    def __init__(self, policy_version: str, retention_days: dict[str, int], audit: AuditService):
        self.policy_version = policy_version
        self.audit = audit
        self.notices = {
            "BMI": M.CONSENT_NOTICES["BMI"].format(days=retention_days.get("bmi_records")),
            "FACE_ANALYSIS": M.CONSENT_NOTICES["FACE_ANALYSIS"].format(days=retention_days.get("expression_results")),
            "RECOGNITION": M.CONSENT_NOTICES["RECOGNITION"],
        }
        self.on_revoke: Optional[Callable[[Session, str, str], dict]] = None

    def notice_payload(self) -> dict:
        return {p: {"text": t, "sha256": sha256_hex(t), "policy_version": self.policy_version}
                for p, t in self.notices.items()}

    def current(self, s: Session, user_id: str, purpose: str) -> Optional[UserConsent]:
        return s.scalars(select(UserConsent).where(UserConsent.user_id == user_id, UserConsent.purpose == purpose)
                         .order_by(UserConsent.timestamp.desc(), UserConsent.consent_id.desc()).limit(1)).first()

    def is_granted(self, row: Optional[UserConsent]) -> bool:
        return bool(row and row.consent_status == ConsentStatus.GRANTED
                    and _major(row.policy_version) == _major(self.policy_version))

    def require(self, s: Session, user_id: str, purpose: str) -> UserConsent:
        row = self.current(s, user_id, purpose)
        if not self.is_granted(row):
            raise consent_required(purpose)
        return row

    def state(self, s: Session, user_id: str) -> list[dict]:
        out = []
        for p in ConsentPurpose:
            row = self.current(s, user_id, p.value)
            out.append({
                "purpose": p.value,
                "status": row.consent_status if row else "NOT_SET",
                "granted": self.is_granted(row),
                "since": row.timestamp if row else None,
                "policy_version": row.policy_version if row else None,
                "reprompt": bool(row and row.consent_status == ConsentStatus.GRANTED and not self.is_granted(row)),
                "consent_id": row.consent_id if row else None,
            })
        return out

    def snapshot(self, s: Session, user_id: str) -> dict:
        return {c["purpose"]: {"status": c["status"], "consent_id": c["consent_id"], "policy_version": c["policy_version"]}
                for c in self.state(s, user_id)}

    def record(self, s: Session, user_id: str, role: str, purpose: str, decision: str,
               policy_version: str, notice_sha256: str) -> dict:
        if purpose not in ConsentPurpose.__members__:
            raise ApiError(400, "VALIDATION_ERROR", "Unknown consent purpose.", {"purpose": purpose})
        if decision not in DECISION_TO_STATUS:
            raise ApiError(400, "VALIDATION_ERROR", "decision must be GRANT, DECLINE or REVOKE.")
        if policy_version != self.policy_version:
            raise ApiError(400, "VALIDATION_ERROR", "Policy version is out of date; reload the notice.",
                           {"current_policy_version": self.policy_version})
        if notice_sha256 != sha256_hex(self.notices[purpose]):
            raise ApiError(400, "VALIDATION_ERROR", "The notice shown does not match the current notice text.")
        prev = self.current(s, user_id, purpose)
        status = DECISION_TO_STATUS[decision]
        now = iso()
        row = UserConsent(consent_id=uuid7(), user_id=user_id, purpose=purpose, consent_status=status.value,
                          timestamp=now, policy_version=policy_version, notice_text_sha256=notice_sha256,
                          revoked_at=now if status == ConsentStatus.REVOKED else None,
                          supersedes_consent_id=prev.consent_id if prev else None, channel="ui")
        s.add(row)
        s.flush()
        self.audit.record(s, AuditEvent.CONSENT_CHANGE, actor_user_id=user_id, actor_role=role,
                          target_type="consent", target_id=row.consent_id,
                          details={"purpose": purpose, "new_status": status.value, "policy_version": policy_version})
        deletions = None
        if status in (ConsentStatus.REVOKED, ConsentStatus.DECLINED) and self.on_revoke and prev is not None \
                and prev.consent_status == ConsentStatus.GRANTED:
            deletions = self.on_revoke(s, user_id, purpose)
        return {"consent_id": row.consent_id, "purpose": purpose, "status": status.value, "timestamp": now,
                "policy_version": policy_version, "deletions": deletions}
