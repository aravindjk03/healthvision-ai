"""Request helpers: transactions, authentication, CSRF, roles, rate limits, uploads."""
from __future__ import annotations

import hmac
from contextlib import contextmanager
from typing import Optional

from fastapi import Request, UploadFile
from sqlalchemy.orm import Session

from ..container import Container
from ..core.errors import ApiError
from ..core.util import sha256_hex
from ..domain.enums import AuditEvent
from ..storage.orm import AuthSession, User

SESSION_COOKIE = "hv_session"
CSRF_COOKIE = "hv_csrf"


def C(request: Request) -> Container:
    return request.app.state.container


@contextmanager
def tx(c: Container):
    """One DB transaction per request. Client-side errors (4xx) are business outcomes whose
    audit entries must persist, so they commit; anything else rolls back."""
    s: Session = c.db._factory()
    try:
        yield s
        s.commit()
    except ApiError as e:
        if e.status < 500:
            s.commit()
        else:
            s.rollback()
        raise
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def current_user(request: Request, s: Session, *, csrf: bool = False) -> User:
    c = C(request)
    resolved = c.auth.resolve(s, request.cookies.get(SESSION_COOKIE))
    if resolved is None:
        raise ApiError(401, "UNAUTHENTICATED", "Please sign in.")
    user, sess = resolved
    if csrf:
        check_csrf(request, sess)
    request.state.user = user
    return user


def check_csrf(request: Request, sess: AuthSession) -> None:
    header = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or not hmac.compare_digest(header, cookie) or not hmac.compare_digest(sha256_hex(header), sess.csrf_token_hash):
        raise ApiError(403, "CSRF_FAILED", "Security token missing or invalid. Please reload the page.")


def require_admin(user: User) -> None:
    if user.role != "ADMINISTRATOR":
        raise ApiError(403, "FORBIDDEN", "Administrator role required.")


def rate_limit(request: Request, s: Session, key: str, per_minute: Optional[int], per_hour: Optional[int] = None,
               user_id: Optional[str] = None) -> None:
    c = C(request)
    if not c.limiter.hit(key, per_minute, per_hour):
        c.audit.record(s, AuditEvent.RATE_LIMITED, outcome="DENIED", actor_user_id=user_id,
                       details={"endpoint": request.url.path})
        raise ApiError(429, "RATE_LIMITED", "Too many requests. Please slow down.")


async def read_upload(c: Container, f: UploadFile) -> bytes:
    limit = c.cfg.settings.server.max_upload_bytes
    data = await f.read(limit + 1)
    if len(data) > limit:
        raise ApiError(400, "IMAGE_TOO_LARGE", "Image exceeds the maximum upload size.")
    if not data:
        raise ApiError(400, "VALIDATION_ERROR", "Empty image upload.")
    return data


def client_ms(request: Request) -> Optional[float]:
    v = request.headers.get("X-Client-Capture-Ms")
    try:
        return float(v) if v is not None and 0 <= float(v) < 600000 else None
    except ValueError:
        return None
