"""ReportService — report DTO → HTML (Jinja2) and PDF (ReportLab). Never contains images,
landmarks, embeddings, health scores or diagnoses (FR-REP-1/2)."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import not_found
from ..core.util import dumps, iso, iso_in_days, loads, sha256_hex, uuid7
from ..domain import messages as M
from ..domain.enums import AuditEvent
from ..reports.pdf import render_pdf
from ..storage.orm import Report
from .audit_service import AuditService
from .session_service import AnalysisSessionService

_TEMPLATES = Path(__file__).resolve().parents[1] / "reports" / "templates"


class ReportService:
    def __init__(self, sessions: AnalysisSessionService, audit: AuditService, data_dir: Path, retention_days: int,
                 model_info_fn):
        self.sessions = sessions
        self.audit = audit
        self.dir = data_dir / "reports"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.model_info_fn = model_info_fn
        self.env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=select_autoescape(["html", "j2"]))

    def build_dto(self, s: Session, user_id: str, session_id: str, include_recognition: bool) -> dict:
        d = self.sessions.dashboard(s, user_id, session_id)
        consent = self.sessions.consent.snapshot(s, user_id)  # consent state at report time
        return {
            "analysis_id": d["analysis_id"],
            "generated_at": iso(),
            "started_at": d["started_at"],
            "bmi": d["calculated"]["bmi"],
            "face": d["ai_estimates"]["face"],
            "quality": d["ai_estimates"]["quality"],
            "expression": d["ai_estimates"]["expression"],
            "recognition": d["identity"]["recognition"] if include_recognition else None,
            "include_recognition": include_recognition,
            "model_versions": d["model_versions"],
            "config_version": d["config_version"],
            "consent_status": consent,
            "readiness_gate": self.model_info_fn().get("production_readiness_gate"),
            "limitations": [M.BMI_LIMITATION, M.EXPRESSION_NOTE, M.LIVENESS_FULL, M.DASHBOARD_FOOTER,
                            "Models and fairness have not been validated locally; recognition thresholds are "
                            "demo-uncalibrated unless a calibration file is installed."],
        }

    def create(self, s: Session, user_id: str, role: str, session_id: str, include_recognition: bool) -> dict:
        dto = self.build_dto(s, user_id, session_id, include_recognition)
        rid = uuid7()
        dto["report_id"] = rid
        pdf_path = self.dir / f"{rid}.pdf"
        render_pdf(dto, pdf_path)
        row = Report(report_id=rid, session_id=session_id, user_id=user_id, include_recognition=int(include_recognition),
                     file_path=str(pdf_path), file_sha256=sha256_hex(pdf_path.read_bytes()), report_json=dumps(dto),
                     created_at=iso(), expires_at=iso_in_days(self.retention_days))
        s.add(row)
        self.audit.record(s, AuditEvent.REPORT_GENERATION, actor_user_id=user_id, actor_role=role, target_type="report",
                          target_id=rid, details={"include_recognition": include_recognition})
        return {"report_id": rid, "created_at": row.created_at, "session_id": session_id}

    def get(self, s: Session, user_id: str, report_id: str) -> Report:
        r = s.get(Report, report_id)
        if r is None or r.user_id != user_id:
            raise not_found()
        return r

    def html(self, s: Session, user_id: str, report_id: str) -> str:
        r = self.get(s, user_id, report_id)
        return self.env.get_template("report.html.j2").render(r=loads(r.report_json))

    def list(self, s: Session, user_id: str) -> list[dict]:
        return [{"report_id": r.report_id, "session_id": r.session_id, "created_at": r.created_at,
                 "include_recognition": bool(r.include_recognition), "expires_at": r.expires_at}
                for r in s.scalars(select(Report).where(Report.user_id == user_id).order_by(Report.created_at.desc()))]
