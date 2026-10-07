import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Face, type FaceAnalysis } from "../api/client";
import { Badge, ExpressionCard, Field, gradeKind, Latency, QualityList } from "../components/bits";
import CameraCapture, { type Captured } from "../components/CameraCapture";
import ConsentPrompt from "../components/ConsentPrompt";
import { granted, useApp } from "../state";

interface DetectResult {
  session_id: string; face_state: string; face_count: number; faces: Face[];
  quality_global: { grade: string; checks: { check: string; grade: "GOOD" | "ACCEPTABLE" | "POOR"; value: unknown; detail: string }[] };
  message: string | null; latency_ms: Record<string, number>;
}

function Preview({ url, faces, dims }: { url: string; faces: Face[]; dims: { w: number; h: number } | null }) {
  return (
    <div className="preview">
      <img src={url} alt="Captured" />
      {dims && (
        <svg viewBox={`0 0 ${dims.w} ${dims.h}`} preserveAspectRatio="none" aria-hidden>
          {faces.map((f) => (
            <rect key={f.face_index} x={f.bbox.x} y={f.bbox.y} width={f.bbox.w} height={f.bbox.h} />
          ))}
        </svg>
      )}
    </div>
  );
}

export default function FaceAnalysisPage() {
  const { consent, sessionId, setSessionId } = useApp();
  const nav = useNavigate();
  const [shot, setShot] = useState<Captured | null>(null);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const [det, setDet] = useState<DetectResult | null>(null);
  const [res, setRes] = useState<FaceAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!granted(consent, "FACE_ANALYSIS")) {
    return (
      <div className="page">
        <h2>Face analysis</h2>
        <ConsentPrompt purpose="FACE_ANALYSIS" />
      </div>
    );
  }

  const form = (c: Captured) => {
    const fd = new FormData();
    fd.append("image", c.blob, "capture.jpg");
    if (sessionId) fd.append("session_id", sessionId);
    return fd;
  };

  const handle = async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) {
      if (e instanceof ApiError && e.code === "NOT_FOUND") setSessionId(null);
      setError(e instanceof ApiError ? e.message : "Request failed");
      return null;
    } finally { setBusy(false); }
  };

  const onCapture = async (c: Captured) => {
    setShot(c); setRes(null); setDet(null);
    const img = new Image();
    img.onload = () => setDims({ w: img.naturalWidth, h: img.naturalHeight });
    img.src = c.url;
    const r = await handle(() => api.post<DetectResult>("/face/detect", form(c), { "X-Client-Capture-Ms": String(c.captureMs) }));
    if (r) { setDet(r); setSessionId(r.session_id); }
  };

  const analyze = async () => {
    if (!shot) return;
    const r = await handle(() => api.post<FaceAnalysis>("/face/expression", form(shot), { "X-Client-Capture-Ms": String(shot.captureMs) }));
    if (r) { setRes(r); setSessionId(r.session_id); }
  };

  const retake = () => { setShot(null); setDet(null); setRes(null); setError(null); };
  const faces = res?.face.faces ?? det?.faces ?? [];
  const blocked = det && det.face_state !== "ONE_FACE";

  return (
    <div className="page">
      <h2>Face analysis</h2>
      <div className="grid2">
        <section className="card">
          {!shot ? (
            <CameraCapture onCapture={onCapture} captureLabel="Capture" disabled={busy} />
          ) : (
            <>
              <Preview url={shot.url} faces={faces} dims={dims} />
              <div className="row">
                <button className="btn" onClick={retake}>Retake</button>
                <button className="btn primary" onClick={analyze} disabled={busy || !!blocked || !!res}>
                  {busy ? "Analysing…" : "Analyze"}
                </button>
              </div>
            </>
          )}
        </section>

        <section className="card result" aria-live="polite">
          <span className="kicker ai">AI ESTIMATES</span>
          {error && <div className="error">{error}</div>}
          {!det && !res && !error && <p className="muted">Capture or upload a photo with one face.</p>}
          {det && !res && (
            <>
              <Field label="Face detection">
                {det.face_state === "ONE_FACE" ? <Badge kind="good">Face detected</Badge> : <Badge kind="bad">{det.face_state.replace("_", " ")}</Badge>}
                {det.faces[0] && <span className="muted small"> detection confidence {(det.faces[0].detection_confidence * 100).toFixed(0)}%</span>}
              </Field>
              {det.message && <div className="warnbar">{det.message}</div>}
              {det.face_state === "ONE_FACE" && <p className="muted">Press <strong>Analyze</strong> to check quality and estimate the facial expression.</p>}
              <Latency ms={det.latency_ms} />
            </>
          )}
          {res && (
            <>
              <Field label="Face detection">
                {res.face.face_state === "ONE_FACE" ? <Badge kind="good">Face detected</Badge> : <Badge kind="bad">{res.face.face_state.replace("_", " ")}</Badge>}
              </Field>
              {res.quality && (
                <Field label="Image quality">
                  <Badge kind={gradeKind(res.quality.grade)}>{res.quality.grade}</Badge>
                  <QualityList checks={res.quality.checks} />
                </Field>
              )}
              {res.pose && (
                <Field label="Head pose">
                  <span className="muted">yaw {res.pose.yaw.toFixed(0)}° · pitch {res.pose.pitch.toFixed(0)}° · roll {res.pose.roll.toFixed(0)}°</span>
                </Field>
              )}
              {res.message && res.expression.status === "NOT_AVAILABLE" && <div className="warnbar">{res.message}</div>}
              <ExpressionCard e={res.expression} />
              <Latency ms={res.latency_ms} />
              <p className="muted small">Models: {Object.values(res.models).join(" · ")} · config {res.config_version}</p>
              <div className="row">
                <button className="btn" onClick={retake}>Retake</button>
                <button className="btn primary" onClick={() => nav("/dashboard")}>View dashboard</button>
                <button className="btn" onClick={() => nav("/recognition")}>Optional: verify identity</button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
