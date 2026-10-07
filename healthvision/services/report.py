"""ReportService — builds a report DTO and a PDF. No face images, no medical conclusions (docs/01 FR-REP)."""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from healthvision.domain import new_id, utcnow
from healthvision.services.store import AnalysisSession

DASHBOARD_FOOTER = ("These outputs are separate measurements and should not be interpreted as a medical "
                    "diagnosis or definitive emotional state.")
LIMITATIONS = [
    "BMI is a screening measure and does not constitute a medical diagnosis.",
    "Facial expression is an AI estimate based on visible facial features and should not be interpreted as a "
    "definitive measure of emotional state.",
    "Liveness detection is not implemented in this version; verification can be fooled by photos or screens.",
    "Models have not yet been validated on local data; recognition thresholds are uncalibrated (demo mode) "
    "unless stated otherwise.",
]


def build_report(analysis: AnalysisSession, include_recognition: bool, models: dict[str, str],
                 consent_snapshot: dict[str, Any], config_version: str) -> dict[str, Any]:
    rep: dict[str, Any] = {"report_id": new_id(), "analysis_id": analysis.session_id, "created_at": utcnow(),
                           "config_version": config_version, "model_versions": models,
                           "consent": consent_snapshot, "limitations": LIMITATIONS, "footer": DASHBOARD_FOOTER}
    b = analysis.bmi
    rep["bmi"] = None if b is None else {
        "status": str(b.status), "bmi": b.bmi_display, "category": b.category_label,
        "calculation": b.calculation, "reference": b.reference["short"] if b.reference else None,
        "notes": b.notes, "timestamp": b.timestamp}
    f = analysis.face
    if f is None:
        rep["face"] = None
    else:
        p = f.pipeline
        rep["face"] = {"face_state": str(p.face_state) if p.face_state else None,
                       "image_quality": str(p.quality_grade) if p.quality_grade else None,
                       "expression_status": str(f.status),
                       "expression_estimate": f.expression.capitalize() if f.expression else None,
                       "confidence": None if f.confidence is None else f"{f.confidence:.0%}",
                       "confidence_band": f.confidence_band, "not_available_reason": f.not_available_reason,
                       "timestamp": p.timestamp}
    r = analysis.recognition
    rep["recognition"] = None if (r is None or not include_recognition) else {
        "decision": str(r.decision), "message": r.message, "similarity": r.similarity,
        "thresholds": r.thresholds, "threshold_source": r.threshold_source,
        "liveness": str(r.liveness), "timestamp": r.timestamp}
    return rep


def render_pdf(rep: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm, title="HealthVision AI report")
    ss = getSampleStyleSheet()
    body, small = ss["BodyText"], ss["BodyText"].clone("small", fontSize=8, leading=10)
    story: list[Any] = [Paragraph("HEALTHVISION AI — Analysis report", ss["Title"]),
                        Paragraph(f"Analysis ID: {rep['analysis_id']}<br/>Report ID: {rep['report_id']}<br/>"
                                  f"Generated: {rep['created_at']} (UTC)<br/>Config version: {rep['config_version']}",
                                  small), Spacer(1, 6 * mm)]

    def section(title: str, rows: list[tuple[str, Any]]) -> None:
        story.append(Paragraph(title, ss["Heading2"]))
        data = [[Paragraph(f"<b>{k}</b>", body), Paragraph("—" if v in (None, "") else str(v), body)] for k, v in rows]
        t = Table(data, colWidths=[55 * mm, 115 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
        story.extend([t, Spacer(1, 4 * mm)])

    b = rep["bmi"]
    section("BODY — calculated value", [("BMI", "Not performed")] if b is None else [
        ("Status", b["status"]), ("BMI", b["bmi"]), ("Category", b["category"]),
        ("Calculation", b["calculation"]), ("Reference", b["reference"]), ("Notes", " ".join(b["notes"]))])
    f = rep["face"]
    section("FACE — AI estimates", [("Face analysis", "Not performed")] if f is None else [
        ("Face detection", f["face_state"]), ("Image quality", f["image_quality"]),
        ("Expression status", f["expression_status"]),
        ("Estimated facial expression", f["expression_estimate"]),
        ("Model confidence", f["confidence"] if f["expression_status"] != "NOT_AVAILABLE" else None),
        ("Confidence band", f["confidence_band"]), ("Not available because", f["not_available_reason"])])
    r = rep["recognition"]
    section("IDENTITY", [("Recognition", "Not requested / not included")] if r is None else [
        ("Decision", r["decision"]), ("Result", r["message"]), ("Similarity (cosine)", r["similarity"]),
        ("Thresholds", f"match ≥ {r['thresholds'].get('match')}, no-match < {r['thresholds'].get('no_match')}"),
        ("Threshold source", r["threshold_source"] + (" — DEMO, NOT CALIBRATED" if r["threshold_source"] == "demo_uncalibrated" else "")),
        ("Liveness", r["liveness"])])
    section("Model versions", list(rep["model_versions"].items()))
    section("Privacy / consent status", [(k, v.get("status")) for k, v in rep["consent"].items()])
    story.append(Paragraph("Limitations", ss["Heading2"]))
    for lim in rep["limitations"]:
        story.append(Paragraph(f"• {lim}", body))
    story.extend([Spacer(1, 4 * mm), Paragraph(f"<i>{rep['footer']}</i>", body)])
    doc.build(story)
    return buf.getvalue()
