import { useEffect, useState } from "react";
import { api, ApiError, type Purpose } from "../api/client";
import { useConsentAction } from "../components/ConsentPrompt";
import { useApp } from "../state";

const NAMES: Record<Purpose, string> = { BMI: "BMI calculation", FACE_ANALYSIS: "Facial expression analysis", RECOGNITION: "Facial recognition" };

interface Retention { retention_period_days: Record<string, number>; face_templates: string; raw_images: string; policy_version: string }
interface Enrollment { enrolled: boolean; created_at?: string; model_version?: string; template_count?: number }

export default function PrivacyPage() {
  const { consent, refreshAuth, setSessionId } = useApp();
  const act = useConsentAction();
  const [ret, setRet] = useState<Retention | null>(null);
  const [enr, setEnr] = useState<Enrollment | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api.get<Retention>("/privacy/retention").then(setRet);
    api.get<Enrollment>("/face/enrollment").then(setEnr);
  };
  useEffect(load, []);

  const change = async (p: Purpose, d: "GRANT" | "REVOKE") => {
    if (d === "REVOKE" && !confirm(`Revoke consent for ${NAMES[p]}? ${p === "RECOGNITION" ? "Your face template will be deleted." : "Related stored results will be deleted."}`)) return;
    setError(null);
    try {
      const r = await act(p, d);
      setMsg(d === "REVOKE" ? `Consent revoked. Deleted: ${JSON.stringify(r?.deletions ?? {})}` : "Consent granted.");
      load();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); }
  };

  const exportData = async () => {
    const data = await api.get<unknown>("/privacy/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "healthvision-export.json";
    a.click();
  };

  const deleteAll = async () => {
    if (!confirm("Delete ALL your data? This removes your BMI records, face analysis results, recognition events, reports, your face template and your account. The audit log keeps a record that a deletion happened (without content). This cannot be undone.")) return;
    await api.del("/privacy/data");
    setSessionId(null);
    await refreshAuth();
  };

  return (
    <div className="page">
      <h2>Privacy &amp; consent</h2>
      {msg && <div className="okbar">{msg}</div>}
      {error && <div className="error">{error}</div>}
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Purpose</th><th>Status</th><th>Since</th><th>Policy version</th><th /></tr></thead>
          <tbody>
            {consent?.consents.map((c) => (
              <tr key={c.purpose}>
                <td>{NAMES[c.purpose]}</td>
                <td>{c.status === "NOT_SET" ? "Not asked yet" : c.status}{c.reprompt ? " (re-confirm)" : ""}</td>
                <td>{c.since ? new Date(c.since).toLocaleString() : "—"}</td>
                <td>{c.policy_version ?? "—"}</td>
                <td>{c.granted ? <button className="btn sm danger" onClick={() => change(c.purpose, "REVOKE")}>Revoke</button>
                  : <button className="btn sm" onClick={() => change(c.purpose, "GRANT")}>Allow</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid2">
        <section className="card">
          <h3>Face enrollment</h3>
          {enr?.enrolled ? (
            <p>Active since {enr.created_at?.slice(0, 10)} · model {enr.model_version} · {enr.template_count} encrypted template(s)</p>
          ) : <p className="muted">No face template stored.</p>}
          <p className="muted small">Templates are encrypted, never shown, never exported and used only to verify you.</p>
        </section>
        <section className="card">
          <h3>Retention</h3>
          {ret && (
            <ul className="plain">
              {Object.entries(ret.retention_period_days).map(([k, v]) => <li key={k}>{k.replace(/_/g, " ")}: {v} days</li>)}
              <li>face templates: {ret.face_templates}</li>
              <li>raw images: {ret.raw_images}</li>
            </ul>
          )}
          <p className="muted small">Policy version {ret?.policy_version}</p>
        </section>
      </div>

      <section className="card row">
        <button className="btn" onClick={exportData}>Export my data (JSON, no biometric templates)</button>
        <button className="btn danger" onClick={deleteAll}>Delete all my data</button>
      </section>
    </div>
  );
}
