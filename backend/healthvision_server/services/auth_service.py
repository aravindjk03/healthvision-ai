"""Local accounts, sessions and CSRF (docs/10 §2)."""
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config.settings import SecurityCfg
from ..core.errors import ApiError
from ..core.util import iso, parse_iso, sha256_hex, utcnow, uuid7
from ..domain.enums import AuditEvent, Role
from ..storage.orm import AuthSession, User
from .audit_service import AuditService

_PH = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)
# Small bundled list of the most common passwords (V1). Replace with a full top-10k list for production.
COMMON_PASSWORDS = {
    "123456789012", "password1234", "passwordpassword", "qwertyuiop12", "111111111111", "123123123123",
    "iloveyou1234", "adminadmin12", "welcome12345", "letmein12345", "abc123abc123", "000000000000",
    "qwerty123456", "password123!", "1q2w3e4r5t6y", "healthvision", "healthvision1",
}


class AuthService:
    def __init__(self, cfg: SecurityCfg, audit: AuditService):
        self.cfg = cfg
        self.audit = audit

    def needs_setup(self, s: Session) -> bool:
        return (s.scalar(select(func.count()).select_from(User)) or 0) == 0

    def validate_password(self, password: str) -> None:
        if len(password) < self.cfg.password_min_length:
            raise ApiError(400, "VALIDATION_ERROR", f"Password must be at least {self.cfg.password_min_length} characters.",
                           {"field": "password"})
        if password.lower() in COMMON_PASSWORDS:
            raise ApiError(400, "VALIDATION_ERROR", "This password is too common.", {"field": "password"})

    def create_user(self, s: Session, username: str, display_name: str, password: str, role: Role) -> User:
        username = (username or "").strip().lower()
        if not (3 <= len(username) <= 40) or not username.replace("_", "").replace(".", "").replace("-", "").isalnum():
            raise ApiError(400, "VALIDATION_ERROR", "Username must be 3–40 letters, digits, '.', '-' or '_'.", {"field": "username"})
        display_name = (display_name or username).strip()[:80] or username
        self.validate_password(password)
        if s.scalar(select(User).where(User.username == username)):
            raise ApiError(400, "VALIDATION_ERROR", "That username is taken.", {"field": "username"})
        now = iso()
        u = User(user_id=uuid7(), username=username, display_name=display_name, password_hash=_PH.hash(password),
                 role=role.value, status="ACTIVE", created_at=now, updated_at=now)
        s.add(u)
        s.flush()
        return u

    def login(self, s: Session, username: str, password: str, user_agent: str) -> tuple[User, str, str]:
        username = (username or "").strip().lower()
        u = s.scalar(select(User).where(User.username == username))
        ok = False
        if u is not None and u.status == "ACTIVE":
            try:
                ok = _PH.verify(u.password_hash, password or "")
            except (VerifyMismatchError, InvalidHashError):
                ok = False
        if not ok:
            self.audit.record(s, AuditEvent.LOGIN_FAILURE, outcome="FAILURE",
                              details={"username_hash": sha256_hex(username)[:16]})
            raise ApiError(401, "UNAUTHENTICATED", "Invalid username or password.")
        if _PH.check_needs_rehash(u.password_hash):
            u.password_hash = _PH.hash(password)
        # cap concurrent sessions
        sessions = s.scalars(select(AuthSession).where(AuthSession.user_id == u.user_id)
                             .order_by(AuthSession.created_at)).all()
        for old in sessions[: max(0, len(sessions) - self.cfg.max_sessions_per_user + 1)]:
            s.delete(old)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = utcnow()
        s.add(AuthSession(session_token_hash=sha256_hex(token), user_id=u.user_id, created_at=iso(now),
                          last_seen_at=iso(now), expires_at=iso(now + timedelta(hours=self.cfg.session_absolute_hours)),
                          csrf_token_hash=sha256_hex(csrf), user_agent_hash=sha256_hex(user_agent or "")))
        self.audit.record(s, AuditEvent.LOGIN_SUCCESS, actor_user_id=u.user_id, actor_role=u.role)
        return u, token, csrf

    def resolve(self, s: Session, token: Optional[str]) -> Optional[tuple[User, AuthSession]]:
        if not token:
            return None
        sess = s.get(AuthSession, sha256_hex(token))
        if sess is None:
            return None
        now = utcnow()
        if parse_iso(sess.expires_at) < now or parse_iso(sess.last_seen_at) + timedelta(minutes=self.cfg.session_idle_minutes) < now:
            s.delete(sess)
            return None
        u = s.get(User, sess.user_id)
        if u is None or u.status != "ACTIVE":
            return None
        sess.last_seen_at = iso(now)
        return u, sess

    def logout(self, s: Session, token: str, user: User) -> None:
        s.execute(delete(AuthSession).where(AuthSession.session_token_hash == sha256_hex(token)))
        self.audit.record(s, AuditEvent.LOGOUT, actor_user_id=user.user_id, actor_role=user.role)
