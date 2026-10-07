"""PDF rendering with ReportLab (pure Python, no external services)."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def pct(x: float) -> str:
    """Model confidence is never displayed as 100 % — it is not a certainty."""
    return ">99%" if x >= 0.995 else f"{x * 100:.0f}%"


def _rows(pairs):
    return [[Paragraph(f"<b>{escape(str(k))}</b>"), Paragraph(escape("—" if v is None else str(v)))] for k, v in pairs]


def _table(pairs):
    t = Table(_rows(pairs), colWidths=[55 * mm, 115 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d0d8")),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f5f8")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def render_pdf(r: dict, path: Path) -> None:
    ss = getSampleStyleSheet()
    h1, h2, body = ss["Title"], ss["Heading2"], ss["BodyText"]
    story = [Paragraph("HealthVision AI — Analysis Report", h1),
             Paragraph(escape(f"Analysis ID {r['analysis_id']} · generated {r['generated_at']}"), body), Spacer(1, 6)]

    story.append(Paragraph("1. Calculated — BMI", h2))
    b = r.get("bmi")
    if b:
        story.append(_table([("BMI", b.get("bmi_display")), ("Category", b.get("category_label") or b.get("message")),
                             ("Status", b.get("status")), ("Context", b.get("guidance")), ("Calculation", b.get("calculation")),
                             ("Reference", (b.get("reference") or {}).get("citation")),
                             ("Limitation", b.get("limitation"))]))
    else:
        story.append(Paragraph("Not performed in this analysis.", body))

    story.append(Paragraph("2. AI estimates — face analysis", h2))
    f, q, e = r.get("face"), r.get("quality"), r.get("expression")
    if f:
        pairs = [("Face detection", f"{f.get('face_state')} ({f.get('face_count')} face(s))"),
                 ("Image quality", (q or {}).get("grade"))]
        if e:
            conf = e.get("confidence")
            pairs += [("Expression", e.get("display")), ("Context", e.get("context")),
                      ("Confidence", f"{pct(conf)} — {e.get('confidence_label')}" if conf is not None else None),
                      ("Confidence band", e.get("confidence_band")), ("Status", e.get("status")),
                      ("Note", e.get("note"))]
        story.append(_table(pairs))
    else:
        story.append(Paragraph("Not performed in this analysis.", body))

    story.append(Paragraph("3. Identity — face verification", h2))
    rec = r.get("recognition")
    if r.get("include_recognition") and rec:
        story.append(_table([("Decision", rec.get("message")), ("Similarity", rec.get("similarity")),
                             ("Threshold", f"{rec['thresholds']['match']} ({rec['thresholds']['source']})"),
                             ("Calibration", rec.get("demo_banner") or "Calibrated thresholds"),
                             ("Liveness", rec.get("liveness_notice"))]))
    else:
        story.append(Paragraph("Not included.", body))

    story.append(Paragraph("4. Traceability", h2))
    story.append(_table([("Model versions", ", ".join(f"{k}: {v}" for k, v in (r.get("model_versions") or {}).items())),
                         ("Config version", r.get("config_version")),
                         ("Consent status", ", ".join(f"{k}: {v.get('status')}" for k, v in (r.get("consent_status") or {}).items())),
                         ("Production readiness gate", r.get("readiness_gate"))]))
    story.append(Paragraph("5. Limitations", h2))
    for lim in r.get("limitations", []):
        story.append(Paragraph("• " + escape(lim), body))
    SimpleDocTemplate(str(path), pagesize=A4, title="HealthVision AI Report", leftMargin=18 * mm,
                      rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm).build(story)
