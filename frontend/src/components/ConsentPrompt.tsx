import { useState } from "react";
import { api, ApiError, type Purpose } from "../api/client";
import { useApp } from "../state";

const TITLES: Record<Purpose, string> = {
  BMI: "BMI calculation",
  FACE_ANALYSIS: "Facial expression analysis",
  RECOGNITION: "Facial recognition (biometric)",
};

export function useConsentAction() {
  const { consent, refreshConsent } = useApp();
  return async (purpose: Purpose, decision: "GRANT" | "DECLINE" | "REVOKE") => {
    if (!consent) return;
    const n = consent.notices[purpose];
    const res = await api.post<{ deletions: Record<string, number> | null }>("/consent", {
      purpose, decision, policy_version: n.policy_version, notice_sha256: n.sha256,
    });
    await refreshConsent();
    return res;
  };
}

export default function ConsentPrompt({ purpose, compact = false }: { purpose: Purpose; compact?: boolean }) {
  const { consent } = useApp();
  const act = useConsentAction();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!consent) return null;
  const notice = consent.notices[purpose];
  const row = consent.consents.find((c) => c.purpose === purpose);

  const go = async (d: "GRANT" | "DECLINE") => {
    setBusy(true); setError(null);
    try { await act(purpose, d); } catch (e) { setError(e instanceof ApiError ? e.message : "Failed"); }
    finally { setBusy(false); }
  };

  return (
    <section className={`card consent ${compact ? "compact" : ""}`} aria-labelledby={`consent-${purpose}`}>
      <h3 id={`consent-${purpose}`}>{TITLES[purpose]}</h3>
      {row?.reprompt && <div className="info">The privacy policy has changed. Please review and confirm again.</div>}
      <pre className="notice">{notice.text}</pre>
      {row?.status === "DECLINED" && <p className="muted">You previously declined. You can change your mind at any time.</p>}
      {error && <div className="error">{error}</div>}
      <div className="row">
        <button className="btn primary" disabled={busy} onClick={() => go("GRANT")}>Allow</button>
        <button className="btn" disabled={busy} onClick={() => go("DECLINE")}>Decline</button>
        <span className="muted small">Policy version {notice.policy_version}</span>
      </div>
    </section>
  );
}
