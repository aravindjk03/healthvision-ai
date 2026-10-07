"""REST API v1 (docs/11). Pipeline stop states (NO_FACE, MULTIPLE_FACES, POOR quality) are
valid results returned with HTTP 200, not errors."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from ..core.errors import ApiError
from ..core.util import dumps, iso, loads, uuid7
from ..domain import messages as M
from ..domain.enums import AuditEvent, Role
from ..storage.orm import (AnalysisSession, AuditLog, BmiRecord, ExpressionResult, RecognitionEvent, User)
from ..core.util import iso_in_days, sha256_hex
from .deps import (C, CSRF_COOKIE, SESSION_COOKIE, client_ms, current_user, rate_limit, read_upload,
                   require_admin, tx)

router = APIRouter(prefix="/api/v1")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ============================================================== health & model info
@router.get("/health")
def health(request: Request):
    c = C(request)
    return {"status": "ok", "models": {me.model_id: me.status for me in c.registry.active.values()},
            "recognition_available": c.templates.available and c.registry.ready("embedding")}


@router.get("/model-info")
def model_info(request: Request):
    c = C(request)
    with tx(c) as s:
        current_user(request, s)
    return c.model_info()


# ============================================================== auth
class SetupIn(_In):
    username: str
    display_name: Optional[str] = None
    password: str


class LoginIn(_In):
    username: str
    password: str


def _set_session_cookies(response: Response, token: str, csrf: str, secure: bool) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", secure=secure, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="strict", secure=secure, path="/")


def _user_dto(u: User) -> dict:
    return {"user_id": u.user_id, "username": u.username, "display_name": u.display_name, "role": u.role}


@router.get("/auth/status")
def auth_status(request: Request):
    c = C(request)
    with tx(c) as s:
        needs = c.auth.needs_setup(s)
        r = c.auth.resolve(s, request.cookies.get(SESSION_COOKIE))
        return {"needs_setup": needs, "user": _user_dto(r[0]) if r else None}


@router.post("/auth/setup", status_code=201)
def auth_setup(body: SetupIn, request: Request, response: Response):
    c = C(request)
    with tx(c) as s:
        if not c.auth.needs_setup(s):
            raise ApiError(403, "FORBIDDEN", "Setup has already been completed.")
        u = c.auth.create_user(s, body.username, body.display_name or body.username, body.password, Role.ADMINISTRATOR)
        _, token, csrf = c.auth.login(s, body.username, body.password, request.headers.get("user-agent", ""))
        _set_session_cookies(response, token, csrf, request.url.scheme == "https")
        return {"user": _user_dto(u)}


@router.post("/auth/login")
def auth_login(body: LoginIn, request: Request, response: Response):
    c = C(request)
    lim = c.cfg.settings.security.login_rate_limit
    with tx(c) as s:
        rate_limit(request, s, f"login:{body.username.lower()}", lim.per_minute)
        rate_limit(request, s, f"login-client:{request.client.host if request.client else '-'}", lim.per_minute)
        u, token, csrf = c.auth.login(s, body.username, body.password, request.headers.get("user-agent", ""))
        _set_session_cookies(response, token, csrf, request.url.scheme == "https")
        return {"user": _user_dto(u)}


@router.post("/auth/logout")
def auth_logout(request: Request, response: Response):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        c.auth.logout(s, request.cookies.get(SESSION_COOKIE), u)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def auth_me(request: Request):
    c = C(request)
    with tx(c) as s:
        return {"user": _user_dto(current_user(request, s))}


# ============================================================== consent
class ConsentIn(_In):
    purpose: Literal["BMI", "FACE_ANALYSIS", "RECOGNITION"]
    decision: Literal["GRANT", "DECLINE", "REVOKE"]
    policy_version: str
    notice_sha256: str


@router.get("/consent")
def consent_get(request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        return {"consents": c.consent.state(s, u.user_id), "notices": c.consent.notice_payload(),
                "policy_version": c.consent.policy_version}


@router.post("/consent")
def consent_post(body: ConsentIn, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        return c.consent.record(s, u.user_id, u.role, body.purpose, body.decision, body.policy_version, body.notice_sha256)


# ============================================================== BMI
class HeightIn(_In):
    value: Optional[float | str] = None
    unit: str = "cm"
    feet: Optional[float | str] = None
    inches: Optional[float | str] = None


class WeightIn(_In):
    value: Optional[float | str] = None
    unit: str = "kg"


class BmiIn(_In):
    session_id: Optional[str] = None
    height: Optional[HeightIn] = None
    weight: Optional[WeightIn] = None
    age_years: Optional[int | float | str] = None
    sex: Optional[str] = None


@router.post("/bmi/calculate")
def bmi_calculate(body: BmiIn, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        c.consent.require(s, u.user_id, "BMI")
        h = body.height.model_dump(exclude_none=True) if body.height else None
        w = body.weight.model_dump(exclude_none=True) if body.weight else None
        res = c.bmi.calculate(h, w, body.age_years, body.sex)
        if res["status"] == "INVALID_INPUT":
            return {"session_id": body.session_id, "record_id": None, "result": res}
        sess = c.sessions.get_or_create(s, u.user_id, body.session_id)
        input_json = {"height": h, "weight": w, "age_years": body.age_years, "sex": body.sex or "unspecified"}
        trace = res.pop("trace")
        rec = BmiRecord(record_id=uuid7(), session_id=sess.session_id, user_id=u.user_id,
                        height=res["normalized"]["height_m"] * 100, weight=res["normalized"]["weight_kg"],
                        input_json=dumps(input_json), age_years=int(float(body.age_years)) if body.age_years not in (None, "") else None,
                        bmi=res["bmi"], status=res["status"], category=res.get("category_code"),
                        reference=f"{res['reference']['code']}@{res['reference']['version']}",
                        input_sha256=sha256_hex(dumps(input_json)), config_version=c.cfg.config_version,
                        result_json="", trace_json=dumps(trace), timestamp=iso(),
                        expires_at=iso_in_days(c.cfg.settings.retention.retention_period_days.get("bmi_records", 365)))
        res["trace"] = {"rule_id": trace["rule_id"], "config_version": trace["config_version"], "reference": trace["reference"]}
        rec.result_json = dumps(res)
        s.add(rec)
        c.sessions.add_latency(sess, "bmi", {})
        return {"session_id": sess.session_id, "record_id": rec.record_id, "result": res}


# ============================================================== face analysis
def _face_limit(request, s, u):
    lim = C(request).cfg.settings.security.face_rate_limit
    rate_limit(request, s, f"face:{u.user_id}", lim.per_minute, user_id=u.user_id)


@router.post("/face/detect")
async def face_detect(request: Request, image: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    c = C(request)
    data = await read_upload(c, image)
    cms = client_ms(request)

    def work():
        with tx(c) as s:
            u = current_user(request, s, csrf=True)
            _face_limit(request, s, u)
            return c.face.detect(s, u.user_id, session_id or None, data, cms)
    return await run_in_threadpool(work)


@router.post("/face/expression")
async def face_expression(request: Request, image: UploadFile = File(...), session_id: Optional[str] = Form(None),
                          include_landmarks: bool = False):
    c = C(request)
    data = await read_upload(c, image)
    cms = client_ms(request)

    def work():
        with tx(c) as s:
            u = current_user(request, s, csrf=True)
            _face_limit(request, s, u)
            return c.face.analyze(s, u.user_id, session_id or None, data, cms, include_landmarks)
    return await run_in_threadpool(work)


# ============================================================== recognition
@router.post("/face/enroll", status_code=201)
async def face_enroll(request: Request, image: list[UploadFile] = File(...), replace: bool = Form(False),
                      session_id: Optional[str] = Form(None)):
    c = C(request)
    frames = [await read_upload(c, f) for f in image]

    def work():
        with tx(c) as s:
            u = current_user(request, s, csrf=True)
            return c.recognition.enroll(s, u.user_id, u.role, session_id or None, frames, replace)
    return await run_in_threadpool(work)


@router.post("/face/verify")
async def face_verify(request: Request, image: UploadFile = File(...), session_id: Optional[str] = Form(None)):
    c = C(request)
    data = await read_upload(c, image)
    cms = client_ms(request)

    def work():
        with tx(c) as s:
            u = current_user(request, s, csrf=True)
            return c.recognition.verify(s, u.user_id, u.role, session_id or None, data, cms)
    return await run_in_threadpool(work)


@router.post("/face/identify")
def face_identify(request: Request):
    c = C(request)
    with tx(c) as s:
        current_user(request, s, csrf=True)
        c.recognition.identify()


@router.get("/face/enrollment")
def enrollment_get(request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        return {**c.recognition.enrollment_status(s, u.user_id), "recognition_available": c.templates.available,
                "notice": M.RECOGNITION_NOTICE, "liveness_notice": M.LIVENESS_FULL,
                "calibration": c.recognition.calibration_state(),
                "demo_banner": M.DEMO_UNCALIBRATED if c.recognition.thresholds()[2] == "demo_uncalibrated" else None,
                "frames": c.cfg.settings.recognition.enrollment_frames.model_dump(),
                "identification_enabled": c.cfg.settings.features.identification_enabled}


@router.delete("/face/enrollment")
def enrollment_delete(request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        n = c.recognition.revoke_enrollment(s, u.user_id, "USER_DELETED", u.role)
        return {"templates_deleted": n}


# ============================================================== sessions, dashboard, history
@router.post("/analysis", status_code=201)
def analysis_start(request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        row = c.sessions.create(s, u.user_id)
        return {"analysis_id": row.session_id, "started_at": row.started_at}


@router.get("/analysis/{analysis_id}")
def analysis_get(analysis_id: str, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        return c.sessions.dashboard(s, u.user_id, analysis_id)


@router.get("/history")
def history(request: Request, page: int = 1, page_size: int = 20, date_from: Optional[str] = None,
            date_to: Optional[str] = None):
    c = C(request)
    page_size = max(1, min(page_size, 100))
    with tx(c) as s:
        u = current_user(request, s)
        q = select(AnalysisSession).where(AnalysisSession.user_id == u.user_id)
        if date_from:
            q = q.where(AnalysisSession.started_at >= date_from)
        if date_to:
            q = q.where(AnalysisSession.started_at <= date_to + "T23:59:59.999Z")
        total = s.scalar(select(func.count()).select_from(q.subquery()))
        rows = s.scalars(q.order_by(AnalysisSession.started_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        items = []
        for r in rows:
            bmi = s.scalars(select(BmiRecord).where(BmiRecord.session_id == r.session_id).order_by(BmiRecord.timestamp.desc())).first()
            ex = s.scalars(select(ExpressionResult).where(ExpressionResult.session_id == r.session_id)
                           .order_by(ExpressionResult.timestamp.desc())).first()
            rec = s.scalars(select(RecognitionEvent).where(RecognitionEvent.session_id == r.session_id)
                            .order_by(RecognitionEvent.timestamp.desc())).first()
            if not (bmi or ex or rec):
                continue
            bres = loads(bmi.result_json) if bmi else None
            items.append({"analysis_id": r.session_id, "started_at": r.started_at,
                          "bmi": bres.get("bmi_display") if bres else None,
                          "bmi_category": (bres.get("category_label") or bres.get("status")) if bres else None,
                          "expression": ex.expression if ex else None, "expression_status": ex.status if ex else None,
                          "recognition": rec.decision if rec else None})
        days = c.cfg.settings.retention.retention_period_days
        return {"items": items, "page": page, "page_size": page_size, "total": total,
                "retention_notice": f"Records older than {days.get('expression_results')}–{days.get('bmi_records')} days "
                                    f"(depending on type) are deleted automatically."}


# ============================================================== reports
class ReportIn(_In):
    session_id: str
    include_recognition: bool = False


@router.post("/reports", status_code=201)
def report_create(body: ReportIn, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        return c.reports.create(s, u.user_id, u.role, body.session_id, body.include_recognition)


@router.get("/reports")
def report_list(request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        return {"items": c.reports.list(s, u.user_id)}


@router.get("/reports/{report_id}", response_class=HTMLResponse)
def report_view(report_id: str, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        return HTMLResponse(c.reports.html(s, u.user_id, report_id))


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: str, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        r = c.reports.get(s, u.user_id, report_id)
        path = r.file_path
    return FileResponse(path, media_type="application/pdf", filename=f"healthvision-report-{report_id[:8]}.pdf")


# ============================================================== privacy
@router.get("/privacy/export")
def privacy_export(request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        return c.privacy.export(s, u.user_id)


@router.get("/privacy/retention")
def privacy_retention(request: Request):
    c = C(request)
    with tx(c) as s:
        current_user(request, s)
    r = c.cfg.settings.retention
    return {"retention_period_days": r.retention_period_days, "face_templates": "until consent is revoked "
            f"(max {r.template_max_age_days} days)", "raw_images": "not retained",
            "policy_version": c.cfg.settings.privacy.policy_version}


@router.delete("/privacy/data")
def privacy_delete(request: Request, response: Response):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        counts = c.privacy.delete_all(s, u.user_id, c.data_dir)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"deleted": counts}


# ============================================================== admin
class NewUserIn(_In):
    username: str
    display_name: Optional[str] = None
    password: str
    role: Literal["USER", "ADMINISTRATOR"] = "USER"


class PatchUserIn(_In):
    status: Optional[Literal["ACTIVE", "DISABLED"]] = None
    role: Optional[Literal["USER", "ADMINISTRATOR"]] = None


@router.get("/admin/audit")
def admin_audit(request: Request, date_from: Optional[str] = None, date_to: Optional[str] = None,
                limit: int = 500):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        require_admin(u)
        q = select(AuditLog)
        if date_from:
            q = q.where(AuditLog.timestamp >= date_from)
        if date_to:
            q = q.where(AuditLog.timestamp <= date_to + "T23:59:59.999Z")
        rows = s.scalars(q.order_by(AuditLog.audit_id.desc()).limit(min(int(limit), 5000))).all()
        out = [{"audit_id": r.audit_id, "timestamp": r.timestamp, "event_type": r.event_type, "outcome": r.outcome,
                "actor_user_id": r.actor_user_id, "actor_role": r.actor_role, "target_type": r.target_type,
                "target_id": r.target_id, "details": loads(r.details_json), "entry_hash": r.entry_hash}
               for r in rows]
        chain = c.audit.verify_chain(s)
        c.audit.record(s, AuditEvent.ADMIN_ACCESS, actor_user_id=u.user_id, actor_role=u.role,
                       details={"scope": "audit_export", "rows": len(out)})
        return {"items": out, "chain": chain}


@router.get("/admin/config")
def admin_config(request: Request):
    c = C(request)
    with tx(c) as s:
        require_admin(current_user(request, s))
    return {"config_version": c.cfg.config_version, "config_file": str(c.cfg.path.name), "settings": c.cfg.raw}


@router.get("/admin/users")
def admin_users(request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s)
        require_admin(u)
        c.audit.record(s, AuditEvent.ADMIN_ACCESS, actor_user_id=u.user_id, actor_role=u.role, details={"scope": "user_list"})
        return {"items": [{**_user_dto(x), "status": x.status, "created_at": x.created_at}
                          for x in s.scalars(select(User).where(User.status != "DELETED").order_by(User.created_at))]}


@router.post("/admin/users", status_code=201)
def admin_users_create(body: NewUserIn, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        require_admin(u)
        nu = c.auth.create_user(s, body.username, body.display_name or body.username, body.password, Role(body.role))
        c.audit.record(s, AuditEvent.ADMIN_ACCESS, actor_user_id=u.user_id, actor_role=u.role, target_type="user",
                       target_id=nu.user_id, details={"scope": "user_create", "role": body.role})
        return {"user": _user_dto(nu)}


@router.patch("/admin/users/{user_id}")
def admin_users_patch(user_id: str, body: PatchUserIn, request: Request):
    c = C(request)
    with tx(c) as s:
        u = current_user(request, s, csrf=True)
        require_admin(u)
        t = s.get(User, user_id)
        if t is None or t.status == "DELETED":
            raise ApiError(404, "NOT_FOUND", "Not found.")
        if t.user_id == u.user_id and (body.status == "DISABLED" or body.role == "USER"):
            raise ApiError(400, "VALIDATION_ERROR", "You cannot disable or demote your own account.")
        if body.status:
            t.status = body.status
        if body.role:
            t.role = body.role
        t.updated_at = iso()
        c.audit.record(s, AuditEvent.ADMIN_ACCESS, actor_user_id=u.user_id, actor_role=u.role, target_type="user",
                       target_id=t.user_id, details={"scope": "user_update", "status": body.status, "role": body.role})
        return {"user": {**_user_dto(t), "status": t.status}}


# ============================================================== about
@router.get("/about")
def about():
    return {"name": "HealthVision AI", "version": "0.1.0 (V1 prototype)", "positioning": M.POSITIONING,
            "footer": M.DASHBOARD_FOOTER}
