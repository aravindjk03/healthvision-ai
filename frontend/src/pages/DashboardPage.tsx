import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type Dashboard } from "../api/client";
import { Badge, ExpressionCard, Field, gradeKind } from "../components/bits";
import { useApp } from "../state";

export default function DashboardPage() {
  const { id } = useParams();
  const { sessionId, setSessionId } = useApp();
  const nav = useNavigate();
  const sid = id ?? sessionId;
  const [d, setD] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [incRec, setIncRec] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!sid) return;
    api.get<Dashboard>(`/analysis/${sid}`).then(setD).catch((e) => {
      if (e instanceof ApiError && e.code === "NOT_FOUND" && !id) setSessionId(null);
      setError(e instanceof ApiError ? e.message : "Failed to load");
    });
  }, [sid, id, setSessionId]);

  if (!sid) {
    return (
      <div className="page">
        <h2>Results dashboard</h2>
        <p className="muted">No analysis yet. Start one from <Link to="/">Home</Link>.</p>
      </div>
    );
  }
  if (error) return <div className="page"><h2>Results dashboard</h2><div className="error">{error}</div></div>;
  if (!d) return <div className="page muted">Loading…</div>;

  const bmi = d.calculated.bmi;
  const ai = d.ai_estimates;
  const rec = d.identity.recognition;
  const lat = Object.entries(d.latency_ms).flatMap(([step, v]) =>
    v && v.total_pipeline !== undefined ? [`${step.replace("_", " ")}: ${v.total_pipeline.toFixed(0)} ms`] : []);

  const report = async () => {
    setBusy(true);
    try {
      await api.post("/reports", { session_id: d.analysis_id, include_recognition: incRec });
      nav("/reports");
    } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); } finally { setBusy(false); }
  };

  return (
    <div className="page">
      <div className="titlebar">
        <h2>Results dashboard</h2>
        <span className="muted small">Analysis {d.analysis_id.slice(0, 8)} · {new Date(d.started_at).toLocaleString()}</span>
      </div>
      <div className="three panels">
        <section className="card panel calc">
          <span className="kicker calc">CALCULATED</span>
          <h3>BMI</h3>
          {bmi ? (
            <>
              <div className={`bmi-big ${bmi.status === "NOT_APPLICABLE" ? "grey" : ""}`}>{bmi.bmi_display}<small> kg/m²</small></div>
              {bmi.status === "VALID" ? <Badge kind="info">{bmi.category_label}</Badge> : <p className="info">{bmi.message}</p>}
              <p className="small">{bmi.calculation}</p>
              <p className="muted small">Reference: {bmi.reference.citation}</p>
            </>
          ) : <p className="muted">Not performed. <Link to="/bmi">Calculate BMI</Link></p>}
        </section>

        <section className="card panel ai">
          <span className="kicker ai">AI ESTIMATES</span>
          <h3>Face analysis</h3>
          {ai.face ? (
            <>
              <Field label="Face detection">
                {ai.face.face_state === "ONE_FACE" ? <Badge kind="good">Face detected</Badge> : <Badge kind="bad">{ai.face.face_state.replace("_", " ")}</Badge>}
              </Field>
              {ai.quality?.grade && <Field label="Image quality"><Badge kind={gradeKind(ai.quality.grade)}>{ai.quality.grade}</Badge></Field>}
              {ai.expression && <ExpressionCard e={ai.expression} />}
            </>
          ) : <p className="muted">Not performed. <Link to="/face">Analyse a face</Link></p>}
        </section>

        <section className="card panel id">
          <span className="kicker id">IDENTITY</span>
          <h3>Face verification</h3>
          {rec ? (
            <>
              {rec.demo_banner && <div className="demobar">{rec.demo_banner}</div>}
              <div className="verdict">
                <Badge kind={rec.decision === "MATCH" ? "good" : rec.decision === "NO_MATCH" ? "bad" : "warn"}>{rec.decision.replace("_", " ")}</Badge>
                <span>{rec.message}</span>
              </div>
              {rec.similarity != null && <p className="muted small">Similarity {rec.similarity.toFixed(2)} · threshold {rec.thresholds.match.toFixed(2)} ({rec.thresholds.source})</p>}
              <p className="muted small">Liveness detection is not implemented in this version.</p>
            </>
          ) : <p className="muted">Not used in this analysis (optional).</p>}
        </section>
      </div>

      <section className="card notes">
        {d.notes.map((n) => <p key={n}>{n}</p>)}
        <p className="muted small">
          Models: {Object.values(d.model_versions).join(" · ") || "—"} · Config {d.config_version}
          {lat.length > 0 && <> · Measured: {lat.join(" · ")}</>}
        </p>
      </section>

      <section className="card row">
        <label className="check"><input type="checkbox" checked={incRec} onChange={(e) => setIncRec(e.target.checked)} disabled={!rec} /> Include identity result in report</label>
        <button className="btn primary" onClick={report} disabled={busy}>Generate report</button>
      </section>
    </div>
  );
}
