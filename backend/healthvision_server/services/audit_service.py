"""Append-only, hash-chained audit log (docs/10 §6). Never stores biometric content."""
from __future__ import annotations

import hashlib
import re
import threading

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core.util import dumps, iso
from ..storage.orm import AuditLog

GENESIS = "0" * 64
_FORBIDDEN_KEY = re.compile(r"embedding|template_data|image|landmarks|probs_raw|password|ciphertext|similarity_vector", re.I)
_lock = threading.Lock()


def _check_details(details: dict) -> None:
    def walk(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if _FORBIDDEN_KEY.search(str(k)):
                    raise ValueError(f"audit details may not contain '{k}'")
                walk(v)
        elif isinstance(d, list):
            for v in d:
                walk(v)
    walk(details)


def _entry_hash(prev_hash: str, row: dict) -> str:
    return hashlib.sha256((prev_hash + dumps(row)).encode()).hexdigest()


class AuditService:
    def record(self, s: Session, event_type: str, *, outcome: str = "SUCCESS", actor_user_id: str | None = None,
               actor_role: str | None = None, target_type: str | None = None, target_id: str | None = None,
               details: dict | None = None) -> None:
        details = details or {}
        _check_details(details)
        with _lock:
            last = s.scalars(select(AuditLog).order_by(AuditLog.audit_id.desc()).limit(1)).first()
            prev = last.entry_hash if last else GENESIS
            row = {"timestamp": iso(), "actor_user_id": actor_user_id, "actor_role": actor_role,
                   "event_type": str(event_type), "target_type": target_type, "target_id": target_id,
                   "outcome": outcome, "details_json": dumps(details)}
            s.add(AuditLog(**row, prev_hash=prev, entry_hash=_entry_hash(prev, row)))
            s.flush()

    @staticmethod
    def verify_chain(s: Session) -> dict:
        prev = None
        n = 0
        for r in s.scalars(select(AuditLog).order_by(AuditLog.audit_id)):
            row = {"timestamp": r.timestamp, "actor_user_id": r.actor_user_id, "actor_role": r.actor_role,
                   "event_type": r.event_type, "target_type": r.target_type, "target_id": r.target_id,
                   "outcome": r.outcome, "details_json": r.details_json}
            # After a retention purge the first remaining row links to a purged row: accept its prev_hash.
            if prev is not None and r.prev_hash != prev:
                return {"valid": False, "first_break_audit_id": r.audit_id, "checked": n}
            if _entry_hash(r.prev_hash, row) != r.entry_hash:
                return {"valid": False, "first_break_audit_id": r.audit_id, "checked": n}
            prev = r.entry_hash
            n += 1
        return {"valid": True, "first_break_audit_id": None, "checked": n}

    @staticmethod
    def purge_before(s: Session, cutoff_iso: str) -> int:
        s.execute(text("INSERT OR REPLACE INTO _app_flags(name, value) VALUES ('audit_purge', 1)"))
        try:
            res = s.execute(text("DELETE FROM audit_logs WHERE timestamp < :c"), {"c": cutoff_iso})
            return res.rowcount or 0
        finally:
            s.execute(text("UPDATE _app_flags SET value = 0 WHERE name = 'audit_purge'"))
