"""HealthVision AI — Streamlit UI (V1 hosted demo).

UI → HealthVisionApp (service layer) → engines. The UI never touches models directly (docs/02 §4).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import streamlit as st

from healthvision.app import HealthVisionApp
from healthvision.config import ROOT, load_config
from healthvision.domain import BmiStatus, ConsentPurpose, ConsentStatus, ExpressionStatus, RecognitionDecision
from healthvision.registry import ModelRegistry
from healthvision.runtime import build_engines
from healthvision.services.consent import NOTICES, ConsentRequired
from healthvision.services.face_analysis import EXPRESSION_NOTE, ImageRejected
from healthvision.services.recognition import LIVENESS_NOTICE, EnrollmentError
from healthvision.services.report import DASHBOARD_FOOTER
from healthvision.services.store import DataStore

st.set_page_config(page_title="HealthVision AI", page_icon="🩺", layout="wide")

BMI_NOTE = "BMI is a screening measure and does not constitute a medical diagnosis."
HOSTED_NOTICE = ("Hosted demo: photos are processed in memory on the server running this app and are never stored. "
                 "All results live only in this browser session and disappear when you close the tab.")
PAGES = ["Home", "BMI Analysis", "Face Analysis", "Face Recognition", "Dashboard", "History", "Reports",
         "Privacy", "Settings", "Documentation"]
PURPOSE_LABEL = {ConsentPurpose.BMI: "BMI analysis", ConsentPurpose.FACE_ANALYSIS: "Facial expression analysis",
                 ConsentPurpose.RECOGNITION: "Facial recognition (biometric)"}


# ---------------------------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading AI models (first start downloads ~78 MB)…")
def shared_runtime():
    config = load_config()
    registry = ModelRegistry()
    engines = build_engines(config, registry)
    return config, registry, engines


def get_app() -> HealthVisionApp:
    config, registry, engines = shared_runtime()
    if "store" not in st.session_state:
        st.session_state.store = DataStore()
    return HealthVisionApp(config, registry, engines, st.session_state.store)


def go(page: str) -> None:
    st.session_state.nav = page


def bump(key: str) -> None:
    st.session_state[key] = st.session_state.get(key, 0) + 1


# ---------------------------------------------------------------------------------------------
# Shared widgets
# ---------------------------------------------------------------------------------------------
def consent_gate(app: HealthVisionApp, purpose: ConsentPurpose) -> bool:
    if app.consent.is_granted(purpose):
        return True
    row = app.consent.current(purpose)
    with st.container(border=True):
        st.subheader(f"Permission needed: {PURPOSE_LABEL[purpose]}")
        st.markdown(NOTICES[purpose].replace("\n", "  \n"))
        if row and row["consent_status"] != ConsentStatus.GRANTED:
            st.caption(f"Current status: {row['consent_status']} ({row['timestamp']})")
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("ALLOW", key=f"allow_{purpose}", type="primary"):
            app.consent.record(purpose, ConsentStatus.GRANTED)
            st.rerun()
        if c2.button("DECLINE", key=f"decline_{purpose}"):
            app.consent.record(purpose, ConsentStatus.DECLINED)
            st.rerun()
        st.caption(f"Policy version {app.config['privacy']['policy_version']}. "
                   "Each permission is independent — declining one does not affect the others.")
    return False


def image_input(key: str, label: str = "Position one face inside the frame.") -> bytes | None:
    st.info(label)
    gen = st.session_state.get(f"{key}_gen", 0)
    mode = st.radio("Source", ["Camera", "Upload"], horizontal=True, key=f"{key}_mode")
    if mode == "Camera":
        shot = st.camera_input("Capture", key=f"{key}_cam_{gen}", label_visibility="collapsed")
    else:
        shot = st.file_uploader("Upload a JPEG or PNG", type=["jpg", "jpeg", "png"], key=f"{key}_up_{gen}")
    return shot.getvalue() if shot is not None else None


def quality_table(pipe) -> None:
    rows = []
    for q in (pipe.quality_global, pipe.quality_face):
        if q is None:
            continue
        for c in q.checks:
            rows.append({"Check": c.check, "Value": json.dumps(c.value) if isinstance(c.value, dict) else str(c.value),
                         "Grade": str(c.grade), "Note": c.message})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")


def latency_line(latency: dict[str, float]) -> None:
    if latency:
        parts = [f"{k.replace('_', ' ').capitalize()}: {v:.0f} ms" for k, v in latency.items()]
        st.caption("Measured latency — " + " · ".join(parts))


GRADE_ICON = {"GOOD": "🟢", "ACCEPTABLE": "🟡", "POOR": "🔴"}


# ---------------------------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------------------------
def page_home(app: HealthVisionApp) -> None:
    st.title("HEALTHVISION AI")
    st.subheader("BMI + Facial Expression + Consent-Based Face Verification")
    st.write("Three separate, explainable measurements — a calculated BMI, an AI estimate of the visible facial "
             "expression, and optional verification of your own enrolled identity. They are never merged into a single score.")
    c1, c2, _ = st.columns([1, 1, 3])
    c1.button("START ANALYSIS", type="primary", width="stretch",
              on_click=lambda: (app.start_analysis(), go("BMI Analysis")))
    c2.button("PRIVACY & CONSENT", width="stretch", on_click=go, args=("Privacy",))
    st.divider()
    a, b, c = st.columns(3)
    with a.container(border=True):
        st.markdown("**BMI** — calculated\n\nHeight and weight → BMI → WHO reference category.")
    with b.container(border=True):
        st.markdown("**Facial expression** — AI estimate\n\nDetect one face → quality check → landmarks → "
                    "estimated visible expression with confidence.")
    with c.container(border=True):
        st.markdown("**Identity** — optional, consent-based\n\nEnroll an encrypted template, then verify it is "
                    "you. Liveness detection is not implemented.")


def page_bmi(app: HealthVisionApp) -> None:
    st.header("BMI Analysis")
    if not consent_gate(app, ConsentPurpose.BMI):
        return
    with st.form("bmi"):
        units = st.radio("Units", ["Metric (cm, kg)", "Imperial (ft/in, lb)"], horizontal=True)
        c1, c2 = st.columns(2)
        inches = None
        if units.startswith("Metric"):
            height = c1.number_input("Height (cm)", min_value=0.0, value=170.0, step=0.5)
            weight = c2.number_input("Weight (kg)", min_value=0.0, value=65.0, step=0.5)
            hu, wu = "cm", "kg"
        else:
            f1, f2 = c1.columns(2)
            height = f1.number_input("Height (ft)", min_value=0, value=5, step=1)
            inches = f2.number_input("(in)", min_value=0.0, max_value=11.9, value=7.0, step=0.5)
            weight = c2.number_input("Weight (lb)", min_value=0.0, value=143.0, step=0.5)
            hu, wu = "ft_in", "lb"
        c3, c4 = st.columns(2)
        age = c3.number_input("Age (optional)", min_value=0, max_value=120, value=None, step=1)
        sex = c4.selectbox("Sex (optional)", ["", "female", "male", "unspecified"],
                           format_func=lambda s: s.capitalize() if s else "Prefer not to say")
        submitted = st.form_submit_button("Calculate BMI", type="primary")
    if submitted:
        st.session_state.bmi_last = app.calculate_bmi(height=height, height_unit=hu, weight=weight, weight_unit=wu,
                                                      age_years=age, sex=sex or None, height_inches=inches)
    res = st.session_state.get("bmi_last")
    if res is None:
        return
    if res.status == BmiStatus.INVALID_INPUT:
        for e in res.errors:
            st.error(f"{e.field.capitalize()}: {e.message} ({e.code})")
        return
    with st.container(border=True):
        c1, c2 = st.columns(2)
        c1.metric("BMI", res.bmi_display if res.status == BmiStatus.VALID else f"{res.bmi_display} (not classified)")
        c2.metric("Category", res.category_label or "Not applicable")
        st.markdown(f"**Calculation:** {res.calculation}")
        st.markdown(f"**Reference:** {res.reference['short']}")
        for n in res.notes:
            st.info(n)
        for w in res.warnings:
            st.warning(w)
        st.caption(f"**Limitation:** {res.limitation}")
    st.button("Continue to Face Analysis →", on_click=go, args=("Face Analysis",))


def page_face(app: HealthVisionApp) -> None:
    st.header("Face Analysis")
    if not consent_gate(app, ConsentPurpose.FACE_ANALYSIS):
        return
    data = image_input("face")
    c1, c2, _ = st.columns([1, 1, 4])
    analyze = c1.button("ANALYZE", type="primary", disabled=data is None)
    if c2.button("RETAKE"):
        bump("face_gen")
        st.session_state.pop("face_last", None)
        st.rerun()
    if analyze and data is not None:
        try:
            with st.spinner("Analyzing…"):
                st.session_state.face_last = app.analyze_face(data)
        except ImageRejected as exc:
            st.error(f"{exc} ({exc.code})")
            return
        except ConsentRequired:
            st.rerun()
    res = st.session_state.get("face_last")
    if res is None:
        return
    pipe = res.pipeline
    left, right = st.columns([1, 1])
    with left:
        if pipe.preview is not None:
            st.image(pipe.preview, caption="Detection preview (not stored)", width="stretch")
    with right:
        state = str(pipe.face_state) if pipe.face_state else "—"
        st.markdown(f"**Face:** {'Detected' if state == 'ONE_FACE' else state.replace('_', ' ').title()}"
                    f" ({len(pipe.faces)} counted)")
        for f in pipe.faces:
            st.caption(f"Face #{f['face_index'] + 1}: detection confidence {f['detection_confidence']:.2f}")
        g = str(pipe.quality_grade) if pipe.quality_grade else "—"
        st.markdown(f"**Image quality:** {GRADE_ICON.get(g, '')} {g}")
        if pipe.pose:
            st.markdown(f"**Pose:** yaw {pipe.pose['yaw']}°, pitch {pipe.pose['pitch']}°, roll {pipe.pose['roll']}°")
        if pipe.landmarks:
            st.markdown(f"**Landmarks:** {'detected' if pipe.landmarks.get('detected') else 'not detected'}"
                        f" ({pipe.landmarks.get('scheme')})")
        if pipe.message:
            st.error(pipe.message)
        with st.container(border=True):
            st.markdown("##### FACIAL EXPRESSION")
            if res.status == ExpressionStatus.ESTIMATED:
                band = "high" if res.confidence_band == "HIGH" else "moderate"
                st.markdown(f"Facial expression estimate: **{res.expression.capitalize()}**")
                st.markdown(f"Confidence: **{res.confidence:.0%}** ({band}-confidence estimate)")
                st.markdown(f"Observation: {res.observation}")
            elif res.status == ExpressionStatus.UNCERTAIN:
                st.warning(f"UNCERTAIN — {res.observation} Please REVIEW / RETAKE.")
            else:
                st.markdown(f"NOT AVAILABLE — {res.not_available_reason}")
            st.caption(EXPRESSION_NOTE)
    if res.probabilities:
        with st.expander("Model output by class (model confidence, not probability of emotion)"):
            for k, v in res.probabilities.items():
                st.progress(min(1.0, v), text=f"{k.capitalize()}: {v:.0%}")
    with st.expander("Quality checks and decision trace"):
        quality_table(pipe)
        if res.trace:
            st.json(res.trace.__dict__)
        if pipe.detection_trace:
            st.json(pipe.detection_trace.__dict__)
    latency_line(pipe.latency_ms)
    st.button("View dashboard →", on_click=go, args=("Dashboard",))


def page_recognition(app: HealthVisionApp) -> None:
    st.header("Face Recognition")
    st.warning(LIVENESS_NOTICE, icon="⚠️")
    if not app.config["features"]["recognition_enabled"]:
        st.info("Recognition is disabled by configuration.")
        return
    if not consent_gate(app, ConsentPurpose.RECOGNITION):
        return
    t_match, t_no, source = app.recognition.thresholds()
    if source == "demo_uncalibrated":
        st.info(f"Demo mode — recognition threshold not calibrated on validation data "
                f"(match ≥ {t_match}, no match < {t_no}; vendor reference value).")
    enr = app.store.enrollment
    verify_tab, enroll_tab = st.tabs(["VERIFY MY IDENTITY", "ENROLL NEW IDENTITY"])
    with verify_tab:
        if enr is None:
            st.info("You have not enrolled yet. Use ENROLL NEW IDENTITY first.")
        else:
            data = image_input("verify", "Look straight at the camera, one face in frame.")
            if st.button("VERIFY", type="primary", disabled=data is None) and data is not None:
                try:
                    with st.spinner("Verifying…"):
                        st.session_state.verify_last = app.verify(data)
                except ImageRejected as exc:
                    st.error(f"{exc} ({exc.code})")
            res = st.session_state.get("verify_last")
            if res is not None:
                show_recognition(res)
    with enroll_tab:
        if enr is not None:
            st.success(f"Enrollment active since {enr.created_at} — {len(enr.templates)} encrypted template(s), "
                       f"model {enr.model_version}. Enrolling again replaces it.")
        frames = st.session_state.setdefault("enroll_frames", [])
        limits = app.config["recognition"]["enrollment_frames"]
        st.caption(f"Capture {limits['min']}–{limits['max']} images ({limits['recommended']} recommended, with small "
                   f"head movements). Only an encrypted template is kept — never the photos.")
        mode = st.radio("Source", ["Camera", "Upload"], horizontal=True, key="enroll_mode")
        gen = st.session_state.get("enroll_gen", 0)
        if mode == "Camera":
            shot = st.camera_input("Capture", key=f"enroll_cam_{gen}", label_visibility="collapsed")
            if shot is not None and st.button(f"Add this frame ({len(frames)}/{limits['max']})",
                                              disabled=len(frames) >= limits["max"]):
                frames.append(shot.getvalue())
                bump("enroll_gen")
                st.rerun()
        else:
            ups = st.file_uploader("Upload 1–5 images", type=["jpg", "jpeg", "png"], accept_multiple_files=True,
                                   key=f"enroll_up_{gen}")
            if ups:
                st.session_state.enroll_frames = frames = [u.getvalue() for u in ups][: limits["max"]]
        st.write(f"Frames ready: **{len(frames)}**")
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("ENROLL", type="primary", disabled=not frames):
            try:
                with st.spinner("Creating encrypted template…"):
                    new = app.recognition.enroll(frames)
                st.session_state.enroll_frames = []
                bump("enroll_gen")
                st.session_state.enroll_msg = ("ok", f"Enrollment complete — {len(new.templates)} template(s) stored "
                                                     f"encrypted.", new.frames_report)
            except EnrollmentError as exc:
                st.session_state.enroll_msg = ("err", f"{exc} ({exc.code})", exc.frames)
            except ImageRejected as exc:
                st.session_state.enroll_msg = ("err", f"{exc} ({exc.code})", [])
            st.rerun()
        if c2.button("Clear frames"):
            st.session_state.enroll_frames = []
            bump("enroll_gen")
            st.rerun()
        msg = st.session_state.get("enroll_msg")
        if msg:
            (st.success if msg[0] == "ok" else st.error)(msg[1])
            if msg[2]:
                st.dataframe(msg[2], hide_index=True, width="stretch")
    if app.config["features"]["identification_enabled"]:
        st.button("IDENTIFY FROM ENROLLED GALLERY", disabled=True)


def show_recognition(res) -> None:
    with st.container(border=True):
        icon = {RecognitionDecision.MATCH: "✅", RecognitionDecision.NO_MATCH: "❌",
                RecognitionDecision.UNCERTAIN: "⚠️", RecognitionDecision.NOT_PERFORMED: "⏸️"}[res.decision]
        st.markdown(f"### {icon} {res.message}")
        if res.similarity is not None:
            st.markdown(f"Similarity **{res.similarity:.3f}** (cosine) — match ≥ {res.thresholds['match']}, "
                        f"no match < {res.thresholds['no_match']} · model {res.model_version}")
        if res.demo_uncalibrated:
            st.caption("DEMO — UNCALIBRATED THRESHOLD")
        st.caption(f"Liveness: {res.liveness} · Quality: {res.quality or '—'} · Event {res.event_id[:8]}")
        latency_line(res.latency_ms)


def page_dashboard(app: HealthVisionApp) -> None:
    st.header("Results dashboard")
    a = app.store.current_analysis()
    if a is None or (a.bmi is None and a.face is None and a.recognition is None):
        st.info("No results yet. Start an analysis from Home.")
        return
    st.caption(f"Analysis {a.session_id[:8]} · started {a.started_at} · config {a.config_version}")
    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.markdown("#### BODY — calculated")
        if a.bmi:
            st.metric("BMI", a.bmi.bmi_display)
            st.markdown(f"**Category:** {a.bmi.category_label or 'Not applicable'}")
            st.caption(a.bmi.reference["short"])
        else:
            st.write("Not performed")
    with c2.container(border=True):
        st.markdown("#### FACE — AI estimates")
        if a.face:
            p = a.face.pipeline
            st.markdown(f"**Face:** {'Detected' if str(p.face_state) == 'ONE_FACE' else p.face_state}")
            st.markdown(f"**Image quality:** {p.quality_grade or '—'}")
            if a.face.status == ExpressionStatus.ESTIMATED:
                st.markdown(f"**Expression (estimate):** {a.face.expression.capitalize()}")
                st.markdown(f"**Confidence:** {a.face.confidence:.0%} ({a.face.confidence_band.lower()})")
            else:
                st.markdown(f"**Expression:** {a.face.status}")
        else:
            st.write("Not performed")
    with c3.container(border=True):
        st.markdown("#### IDENTITY")
        r = a.recognition
        if r:
            st.markdown(f"**Recognition:** {r.message}")
            if r.similarity is not None:
                st.markdown(f"**Similarity:** {r.similarity:.3f} (threshold {r.thresholds['match']})")
            if r.demo_uncalibrated:
                st.caption("DEMO — UNCALIBRATED THRESHOLD")
            st.caption(f"Liveness: {r.liveness}")
        else:
            st.write("Not used")
    st.info(EXPRESSION_NOTE)
    st.info(BMI_NOTE)
    st.caption(DASHBOARD_FOOTER)
    with st.expander("Model versions and latency"):
        st.json(app.model_versions())
        if a.face:
            latency_line(a.face.pipeline.latency_ms)
    include = st.checkbox("Include identity result in report", value=False, disabled=a.recognition is None)
    if st.button("Generate report", type="primary"):
        _, pdf = app.report(a, include)
        st.session_state.last_pdf = pdf
    if st.session_state.get("last_pdf"):
        st.download_button("Download PDF report", st.session_state.last_pdf,
                           file_name=f"healthvision_{a.session_id[:8]}.pdf", mime="application/pdf")


def page_history(app: HealthVisionApp) -> None:
    st.header("History")
    st.caption("Retention: records exist only for this browser session and are erased when it ends.")
    rows = []
    for a in sorted(app.store.analyses.values(), key=lambda x: x.started_at, reverse=True):
        rows.append({"Date (UTC)": a.started_at[:19].replace("T", " "),
                     "BMI": a.bmi.bmi_display if a.bmi else "—",
                     "Category": (a.bmi.category_label or "N/A") if a.bmi else "—",
                     "Expression estimate": (a.face.expression.capitalize() if a.face and a.face.expression
                                             else (str(a.face.status) if a.face else "—")),
                     "Recognition": str(a.recognition.decision) if a.recognition else "—",
                     "Reports": sum(1 for r in app.store.reports if r["analysis_id"] == a.session_id),
                     "ID": a.session_id[:8]})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("No analyses yet.")


def page_reports(app: HealthVisionApp) -> None:
    st.header("Reports")
    if not app.store.reports:
        st.info("No reports yet. Generate one from the Dashboard.")
    for r in reversed(app.store.reports):
        c1, c2 = st.columns([3, 1])
        c1.write(f"Report {r['report_id'][:8]} · analysis {r['analysis_id'][:8]} · {r['created_at'][:19]} UTC"
                 f"{' · includes identity' if r['include_recognition'] else ''}")
        c2.download_button("Download PDF", r["pdf"], file_name=f"report_{r['report_id'][:8]}.pdf",
                           mime="application/pdf", key=f"dl_{r['report_id']}")


def page_privacy(app: HealthVisionApp) -> None:
    st.header("Privacy & consent")
    st.write("Each permission is independent. Revoking one stops that feature immediately and deletes its data.")
    for p in ConsentPurpose:
        row = app.consent.current(p)
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"**{PURPOSE_LABEL[p]}**")
            c2.write(f"{row['consent_status']} · {row['timestamp'][:19]} · {row['policy_version']}" if row
                     else "Not asked yet")
            if app.consent.is_granted(p):
                if c3.button("Revoke", key=f"rev_{p}"):
                    out = app.consent.record(p, ConsentStatus.REVOKED)
                    st.session_state.privacy_msg = f"Revoked {PURPOSE_LABEL[p]}. Deleted: {out.get('deletions', {})}"
                    st.session_state.pop("verify_last", None)
                    st.rerun()
            elif c3.button("Allow", key=f"grant_{p}"):
                app.consent.record(p, ConsentStatus.GRANTED)
                st.rerun()
    if st.session_state.get("privacy_msg"):
        st.success(st.session_state.pop("privacy_msg"))
    st.subheader("Face template")
    enr = app.store.enrollment
    if enr:
        st.write(f"Active since {enr.created_at[:19]} UTC · {len(enr.templates)} encrypted template(s) · {enr.model_version}")
        if st.button("Delete my face template"):
            n = app.recognition.delete_enrollment()
            st.success(f"Deleted {n} template(s) (crypto-shredded).")
            st.rerun()
    else:
        st.write("No face template stored.")
    st.subheader("Your data")
    export = {"consents": [{k: str(v) for k, v in c.items() if k != "deletions"} for c in app.store.consents],
              "analyses": [{"id": a.session_id, "started_at": a.started_at,
                            "bmi": a.bmi.bmi_display if a.bmi else None,
                            "expression": a.face.expression if a.face else None,
                            "recognition": str(a.recognition.decision) if a.recognition else None}
                           for a in app.store.analyses.values()],
              "note": "Biometric templates are never exported."}
    st.download_button("Export my data (JSON, no biometric templates)", json.dumps(export, indent=2),
                       file_name="healthvision_export.json", mime="application/json")
    if st.button("Delete all my data", type="secondary"):
        st.session_state.confirm_delete = True
    if st.session_state.get("confirm_delete"):
        st.warning("This deletes all analyses, reports, recognition events and your face template in this session.")
        if st.button("Yes, delete everything", type="primary"):
            counts = app.delete_all()
            for k in ("bmi_last", "face_last", "verify_last", "last_pdf", "confirm_delete"):
                st.session_state.pop(k, None)
            st.success(f"Deleted: {counts}")
    with st.expander("Audit log (no biometric content)"):
        broken = app.store.audit.verify()
        st.caption("Hash chain intact" if broken is None else f"Hash chain broken at entry {broken}")
        st.dataframe([{k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in e.items()
                       if k not in ("prev_hash",)} for e in app.store.audit.entries],
                     hide_index=True, width="stretch")


def page_settings(app: HealthVisionApp) -> None:
    st.header("Settings & model information")
    st.subheader("Production readiness gate: NOT MET")
    for item, ok in app.readiness_gate().items():
        st.write(f"{'✅' if ok else '❌'} {item}")
    st.subheader("Models")
    rows = []
    for mid, entry in app.registry.entries.items():
        d = entry.data
        rows.append({"Model": d["name"], "Type": d["model_type"], "Version": d["version"], "License": d["license"],
                     "Status": app.registry.status.get(mid), "Local validation": "Not validated",
                     "Known limitations": "; ".join(d.get("known_limitations", []))})
    st.dataframe(rows, hide_index=True, width="stretch")
    if app.engines.errors:
        st.warning(app.engines.errors)
    st.caption(f"Warm-up times (ms): {app.engines.warmup_ms}")
    st.subheader("Active configuration (read-only)")
    st.caption(f"config_version {app.config.version} — thresholds are edited in config/healthvision.yaml")
    st.json(app.config.data, expanded=False)


def page_docs() -> None:
    docs = {"README": ROOT / "README.md"} | {p.stem: p for p in sorted((ROOT / "docs").glob("*.md"))}

    def title(p: Path) -> str:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:]
        return p.stem

    key = st.selectbox("Document", list(docs), format_func=lambda k: title(docs[k]))
    text = docs[key].read_text(encoding="utf-8")
    text = re.sub(r"\]\((?!https?://)[^)]+\.md[^)]*\)", "]", text)   # drop relative links (use selector)
    st.markdown(text)


# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------
def main() -> None:
    app = get_app()
    with st.sidebar:
        st.title("🩺 HealthVision AI")
        st.radio("Navigate", PAGES, key="nav", label_visibility="collapsed")
        st.divider()
        st.caption(HOSTED_NOTICE)
        for p in ConsentPurpose:
            st.caption(f"{PURPOSE_LABEL[p]}: {'✅ allowed' if app.consent.is_granted(p) else '—'}")
    page = st.session_state.get("nav", "Home")
    try:
        {"Home": page_home, "BMI Analysis": page_bmi, "Face Analysis": page_face,
         "Face Recognition": page_recognition, "Dashboard": page_dashboard, "History": page_history,
         "Reports": page_reports, "Privacy": page_privacy, "Settings": page_settings,
         "Documentation": lambda _app: page_docs()}[page](app)
    except ConsentRequired as exc:
        st.error(f"{PURPOSE_LABEL[exc.purpose]} permission is required.")


main()
