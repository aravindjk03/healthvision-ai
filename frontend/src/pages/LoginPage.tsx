import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import { useApp } from "../state";

export default function LoginPage({ setup }: { setup: boolean }) {
  const { refreshAuth } = useApp();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (setup && password !== confirm) { setError("Passwords do not match."); return; }
    setBusy(true);
    try {
      if (setup) await api.post("/auth/setup", { username, display_name: displayName || username, password });
      else await api.post("/auth/login", { username, password });
      await refreshAuth();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach the HealthVision service.");
    } finally { setBusy(false); }
  };

  return (
    <div className="auth-wrap">
      <form className="card auth" onSubmit={submit}>
        <h1>HEALTHVISION AI</h1>
        <p className="muted">BMI + Facial Expression + Consent-Based Face Verification</p>
        {setup && <div className="info">First run: create the administrator account for this device. There are no default credentials.</div>}
        <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></label>
        {setup && <label>Display name<input value={displayName} onChange={(e) => setDisplayName(e.target.value)} /></label>}
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete={setup ? "new-password" : "current-password"} required minLength={setup ? 12 : undefined} /></label>
        {setup && <label>Confirm password<input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required /></label>}
        {setup && <p className="hint">At least 12 characters.</p>}
        {error && <div className="error" role="alert">{error}</div>}
        <button className="btn primary" disabled={busy}>{setup ? "Create administrator" : "Sign in"}</button>
        <p className="hint">All processing happens on this device. No face data leaves it.</p>
      </form>
    </div>
  );
}
