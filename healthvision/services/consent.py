"""ConsentService — three independent purposes; revocation triggers deletion (docs/09)."""

from __future__ import annotations

import hashlib
from typing import Any

from healthvision.config import Config
from healthvision.domain import ConsentPurpose, ConsentStatus, new_id, utcnow
from healthvision.services.store import DataStore

NOTICES = {
    ConsentPurpose.BMI: (
        "BMI analysis uses the height, weight and optional age/sex you enter to calculate your Body Mass Index "
        "and classify it against a cited reference. Results are kept only for this browser session."
    ),
    ConsentPurpose.FACE_ANALYSIS: (
        "Facial expression analysis processes a photo of your face to detect the face, check image quality and "
        "estimate the visible facial expression. The photo is processed in memory and not stored. "
        "The result is an estimate of visible expression, not of your emotions."
    ),
    ConsentPurpose.RECOGNITION: (
        "Facial recognition uses biometric information to verify or identify an enrolled person.\n\n"
        "• Purpose: verify that you are the person who enrolled in this session.\n"
        "• What is stored: an encrypted face template (a list of numbers), not your photo.\n"
        "• How long: until you revoke this permission, delete your data, or close this session.\n"
        "• Liveness detection is not implemented in this version.\n"
        "• You can keep using BMI and expression analysis without allowing this."
    ),
}


class ConsentRequired(PermissionError):
    def __init__(self, purpose: ConsentPurpose):
        super().__init__(f"{purpose} consent is required")
        self.purpose = purpose


class ConsentService:
    def __init__(self, config: Config, store: DataStore):
        self.config = config
        self.store = store
        self.policy_version = config["privacy"]["policy_version"]

    def current(self, purpose: ConsentPurpose) -> dict[str, Any] | None:
        rows = [c for c in self.store.consents if c["purpose"] == purpose]
        return rows[-1] if rows else None

    def is_granted(self, purpose: ConsentPurpose) -> bool:
        row = self.current(purpose)
        return bool(row and row["consent_status"] == ConsentStatus.GRANTED
                    and row["policy_version"].split(".")[0] == self.policy_version.split(".")[0])

    def require(self, purpose: ConsentPurpose) -> dict[str, Any]:
        if not self.is_granted(purpose):
            self.store.audit.record("CONSENT_CHECK", outcome="DENIED", purpose=str(purpose))
            raise ConsentRequired(purpose)
        return self.current(purpose)  # type: ignore[return-value]

    def snapshot(self) -> dict[str, Any]:
        out = {}
        for p in ConsentPurpose:
            row = self.current(p)
            out[str(p)] = ({"consent_id": row["consent_id"], "status": str(row["consent_status"]),
                            "policy_version": row["policy_version"]} if row else {"status": "NOT_ASKED"})
        return out

    def record(self, purpose: ConsentPurpose, status: ConsentStatus) -> dict[str, Any]:
        prev = self.current(purpose)
        row = {
            "consent_id": new_id(),
            "user_id": self.store.user_id,
            "purpose": purpose,
            "consent_status": status,
            "timestamp": utcnow(),
            "policy_version": self.policy_version,
            "notice_text_sha256": hashlib.sha256(NOTICES[purpose].encode()).hexdigest(),
            "revoked_at": utcnow() if status == ConsentStatus.REVOKED else None,
            "supersedes_consent_id": prev["consent_id"] if prev else None,
        }
        self.store.consents.append(row)
        self.store.audit.record("CONSENT_CHANGE", target_id=row["consent_id"], purpose=str(purpose),
                                status=str(status), policy_version=self.policy_version)
        if status == ConsentStatus.REVOKED:
            row["deletions"] = self._delete_for(purpose)
        return row

    def _delete_for(self, purpose: ConsentPurpose) -> dict[str, int]:
        store = self.store
        deleted: dict[str, int] = {}
        if purpose == ConsentPurpose.RECOGNITION:
            from healthvision.services.recognition import shred_enrollment
            deleted["face_templates"] = shred_enrollment(store, "CONSENT_REVOKED")
        elif self.config["privacy"]["delete_on_revoke"]:
            attr = "bmi" if purpose == ConsentPurpose.BMI else "face"
            count = 0
            for a in store.analyses.values():
                if getattr(a, attr) is not None:
                    setattr(a, attr, None)
                    count += 1
            deleted["bmi_records" if attr == "bmi" else "expression_results"] = count
            store.audit.record("DATA_DELETION", purpose=str(purpose), counts=deleted)
        return deleted
