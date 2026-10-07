import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type VerifyResult } from "../api/client";
import { Badge, Latency, LivenessBanner } from "../components/bits";
import CameraCapture, { type Captured } from "../components/CameraCapture";
import ConsentPrompt from "../components/ConsentPrompt";
import { granted, useApp } from "../state";

interface Enrollment {
  enrolled: boolean; status?: string; created_at?: string; template_count?: number; model_version?: string;
  recognition_available: boolean; demo_banner: string | null; frames: { min: number; recommended: number; max: number };
}

const PROMPTS = ["Look straight at the camera", "Turn your head slightly left", "Turn your head slightly right", "Tilt your chin slightly up", "Neutral expression"];

export default function RecognitionPage() {
  const { consent, sessionId, setSessionId } = useApp();
  const nav = useNavigate();
  const [enr, setEnr] = useState<Enrollment | null>(null);
  const [mode, setMode] = useState<"menu" | "verify" | "enroll">("menu");
  const [frames, setFrames] = useState<Captured[]>([]);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setEnr(await api.get<Enrollment>("/face/enrollment")); } catch { /* ignore */ }
  }, []);
  useEffect(() => { load(); }, [load]);

  const hasConsent = granted(consent, "RECOGNITION");

  const run = async <T,>(fn: () => Promise<T>) => {
    setBusy(true); setError(null); setMsg(null);
    try { return await fn(); } catch (e) {
      if (e instanceof ApiError) {
        const fr = (e.details as { frames?: { index: number; accepted: boolean; message?: string }[] }).frames;
        setError(e.message + (Array.isArray(fr) ? " " + fr.filter((f) => !f.accepted).map((f) => `Frame ${f.index + 1}: ${f.message ?? "rejected"}`).join(" ") : ""));
      } else setError("Request failed");
      return null;
    } finally { setBusy(false); }
  };

  const doVerify = async (c: Captured) => {
    const fd = new FormData();
    fd.append("image", c.blob, "verify.jpg");
    if (sessionId) fd.append("session_id", sessionId);
    const r = await run(() => api.post<VerifyResult>("/face/verify", fd, { "X-Client-Capture-Ms": String(c.captureMs) }));
    if (r) { setVerify(r); setSessionId(r.session_id); }
  };

  const doEnroll = async () => {
    const fd = new FormData();
    frames.forEach((f, i) => fd.append("image", f.blob, `frame${i}.jpg`));
    fd.append("replace", String(!!enr?.enrolled));
    if (sessionId) fd.append("session_id", sessionId);
    const r = await run(() => api.post<{ template_count: number; frames: { accepted: boolean }[] }>("/face/enroll", fd));
    if (r) {
      setMsg(`Enrollment complete — ${r.template_count} template(s) stored (encrypted). Your photos were discarded.`);
      setFrames([]); setMode("menu"); load();
    }
  };

  const deleteEnrollment = async () => {
    if (!confirm("Delete your face template? You can enroll again later.")) return;
    const r = await run(() => api.del<{ templates_deleted: number }>("/face/enrollment"));
    if (r) { setMsg("Face template deleted."); load(); }
  };

  return (
    <div className="page">
      <h2>Face recognition</h2>
      <LivenessBanner />
      {enr?.demo_banner && <div className="demobar">{enr.demo_banner}</div>}
      {enr && !enr.recognition_available && <div className="error">Secure key storage is unavailable on this device, so recognition is disabled.</div>}

      {!hasConsent ? (
        <ConsentPrompt purpose="RECOGNITION" />
      ) : mode === "menu" ? (
        <>
          {msg && <div className="okbar">{msg}</div>}
          {error && <div className="error">{error}</div>}
          <div className="grid2">
            <section className="card">
              <h3>Verify my identity</h3>
              <p className="muted">Compares a new photo with <strong>your own</strong> enrollment on this device.</p>
              {enr?.enrolled ? (
                <button className="btn primary" onClick={() => { setVerify(null); setMode("verify"); }}>Verify my identity</button>
              ) : <p className="hint">Requires an enrollment first.</p>}
            </section>
            <section className="card">
              <h3>{enr?.enrolled ? "Re-enroll" : "Enroll new identity"}</h3>
              {enr?.enrolled ? (
                <p className="muted">Enrolled {enr.created_at?.slice(0, 10)} · {enr.template_count} template(s) · {enr.model_version}{enr.status === "STALE" ? " · STALE (model changed — please re-enroll)" : ""}</p>
              ) : <p className="muted">Capture {enr?.frames.recommended ?? 3} photos. Only an encrypted face template is stored — never the photos.</p>}
              <div className="row">
                <button className="btn primary" onClick={() => { setFrames([]); setMode("enroll"); }}>{enr?.enrolled ? "Re-enroll" : "Enroll new identity"}</button>
                {enr?.enrolled && <button className="btn danger" onClick={deleteEnrollment}>Delete my face template</button>}
              </div>
            </section>
          </div>
        </>
      ) : mode === "enroll" ? (
        <div className="grid2">
          <section className="card">
            <h3>Enrollment — frame {Math.min(frames.length + 1, enr?.frames.max ?? 5)} of {enr?.frames.recommended ?? 3}</h3>
            <p className="info">{PROMPTS[frames.length % PROMPTS.length]}</p>
            {frames.length < (enr?.frames.max ?? 5) && (
              <CameraCapture onCapture={(c) => setFrames((f) => [...f, c])} captureLabel={`Capture frame ${frames.length + 1}`} disabled={busy} />
            )}
          </section>
          <section className="card">
            <h3>Captured frames</h3>
            <div className="thumbs">{frames.map((f, i) => <img key={i} src={f.url} alt={`Frame ${i + 1}`} />)}</div>
            {error && <div className="error">{error}</div>}
            <div className="row">
              <button className="btn" onClick={() => { setFrames([]); setMode("menu"); }}>Cancel</button>
              <button className="btn" onClick={() => setFrames([])} disabled={!frames.length}>Clear</button>
              <button className="btn primary" disabled={busy || frames.length < (enr?.frames.min ?? 1)} onClick={doEnroll}>
                {busy ? "Enrolling…" : `Enroll with ${frames.length} frame(s)`}
              </button>
            </div>
            <p className="hint">Frames must be GOOD quality with one face. Frames that do not show the same person are rejected.</p>
          </section>
        </div>
      ) : (
        <div className="grid2">
          <section className="card">
            <h3>Verify my identity</h3>
            <CameraCapture onCapture={doVerify} captureLabel={busy ? "Verifying…" : "Capture & verify"} disabled={busy} />
            <button className="btn ghost" onClick={() => setMode("menu")}>Back</button>
          </section>
          <section className="card result" aria-live="polite">
            <span className="kicker id">IDENTITY</span>
            {error && <div className="error">{error}</div>}
            {!verify && !error && <p className="muted">Capture a photo to verify.</p>}
            {verify && (
              <>
                {verify.demo_banner && <div className="demobar">{verify.demo_banner}</div>}
                <div className="verdict">
                  <Badge kind={verify.decision === "MATCH" ? "good" : verify.decision === "NO_MATCH" ? "bad" : "warn"}>{verify.decision.replace("_", " ")}</Badge>
                  <span>{verify.message}</span>
                </div>
                {verify.similarity != null && (
                  <p className="muted">Similarity {verify.similarity.toFixed(2)} (threshold {verify.thresholds.match.toFixed(2)}, model {verify.model_version}). This is a similarity score — not a percentage of certainty.</p>
                )}
                <p className="muted small">Liveness: {verify.liveness.replace("_", " ").toLowerCase()} · quality {verify.quality ?? "—"}</p>
                <Latency ms={verify.latency_ms} />
                <div className="row">
                  <button className="btn primary" onClick={() => nav("/dashboard")}>View dashboard</button>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
