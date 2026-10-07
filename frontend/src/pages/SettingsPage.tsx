import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError, type ModelInfo } from "../api/client";
import { Badge } from "../components/bits";
import { useApp } from "../state";

interface AuditItem { audit_id: number; timestamp: string; event_type: string; outcome: string; details: Record<string, unknown> }
interface AdminUser { user_id: string; username: string; display_name: string; role: string; status: string }

export default function SettingsPage() {
  const { user } = useApp();
  const isAdmin = user?.role === "ADMINISTRATOR";
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [cfg, setCfg] = useState<{ config_version: string; settings: Record<string, unknown> } | null>(null);
  const [audit, setAudit] = useState<{ items: AuditItem[]; chain: { valid: boolean; checked: number } } | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [nu, setNu] = useState({ username: "", password: "", role: "USER" });
  const [error, setError] = useState<string | null>(null);

  const loadUsers = () => api.get<{ items: AdminUser[] }>("/admin/users").then((r) => setUsers(r.items));
  useEffect(() => {
    api.get<ModelInfo>("/model-info").then(setInfo);
    if (isAdmin) { api.get<typeof cfg>("/admin/config").then(setCfg); loadUsers(); }
  }, [isAdmin]);

  const addUser = async (e: FormEvent) => {
    e.preventDefault(); setError(null);
    try { await api.post("/admin/users", nu); setNu({ username: "", password: "", role: "USER" }); loadUsers(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Failed"); }
  };

  const toggle = async (u: AdminUser) => {
    try { await api.patch(`/admin/users/${u.user_id}`, { status: u.status === "ACTIVE" ? "DISABLED" : "ACTIVE" }); loadUsers(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Failed"); }
  };

  const downloadAudit = () => {
    if (!audit) return;
    const lines = audit.items.map((i) => JSON.stringify(i)).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines], { type: "application/x-ndjson" }));
    a.download = "healthvision-audit.jsonl";
    a.click();
  };

  return (
    <div className="page">
      <h2>Settings · About</h2>
      <section className="card">
        <div className="titlebar">
          <h3>Production readiness gate</h3>
          {info && <Badge kind={info.production_readiness_gate === "MET" ? "good" : "bad"}>{info.production_readiness_gate.replace("_", " ")}</Badge>}
        </div>
        <p className="muted small">This V1 prototype is not production-ready by design. Each item lists what is missing.</p>
        <table>
          <tbody>
            {info?.production_readiness_items.map((i) => (
              <tr key={i.id}><td>{i.id}</td><td>{i.criterion}</td><td><Badge kind={i.status === "MET" ? "good" : "bad"}>{i.status.replace("_", " ")}</Badge></td><td className="muted small">{i.reason}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Model registry</h3>
        <p className="muted small">Recognition calibration: <strong>{info?.recognition_calibration.state}</strong> · Liveness: <strong>{info?.liveness.state.replace("_", " ")}</strong> · Fairness: <strong>{info?.fairness}</strong> · Config {info?.config_version}</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Model</th><th>Version</th><th>License</th><th>Status</th><th>Local validation</th><th>Known limitations</th></tr></thead>
            <tbody>
              {info?.models.map((m) => (
                <tr key={m.model_id}>
                  <td>{m.name}<div className="muted small">{m.model_id}</div></td>
                  <td>{m.version}</td>
                  <td>{m.license}</td>
                  <td><Badge kind={m.status === "READY" ? "good" : m.status === "NOT_IMPLEMENTED" ? "neutral" : "bad"}>{m.status.replace("_", " ")}</Badge></td>
                  <td>{m.status === "NOT_IMPLEMENTED" ? "—" : m.local_validation === "VALIDATED" ? "Validated" : "Not locally validated"}</td>
                  <td className="small">{m.known_limitations.join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {isAdmin && (
        <>
          <section className="card">
            <h3>Users</h3>
            {error && <div className="error">{error}</div>}
            <table>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id}><td>{u.username}</td><td>{u.role}</td><td>{u.status}</td>
                    <td>{u.user_id !== user?.user_id && <button className="btn sm" onClick={() => toggle(u)}>{u.status === "ACTIVE" ? "Disable" : "Enable"}</button>}</td></tr>
                ))}
              </tbody>
            </table>
            <form className="inline" onSubmit={addUser}>
              <input placeholder="username" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} />
              <input placeholder="password (12+ chars)" type="password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} />
              <select value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}><option value="USER">User</option><option value="ADMINISTRATOR">Administrator</option></select>
              <button className="btn">Add user</button>
            </form>
          </section>

          <section className="card">
            <h3>Thresholds (read-only)</h3>
            <p className="muted small">Edit config/server.yaml and restart to change. Active config version {cfg?.config_version}.</p>
            <details><summary>Show active configuration</summary><pre className="code">{JSON.stringify(cfg?.settings, null, 2)}</pre></details>
          </section>

          <section className="card">
            <h3>Audit log</h3>
            <div className="row">
              <button className="btn" onClick={() => api.get<typeof audit>("/admin/audit?limit=500").then(setAudit)}>Load audit log</button>
              {audit && <button className="btn" onClick={downloadAudit}>Export (JSON lines)</button>}
              {audit && <Badge kind={audit.chain.valid ? "good" : "bad"}>Hash chain {audit.chain.valid ? "valid" : "BROKEN"} ({audit.chain.checked} entries)</Badge>}
            </div>
            {audit && (
              <div className="table-wrap audit">
                <table>
                  <tbody>{audit.items.map((a) => (
                    <tr key={a.audit_id}><td>{a.timestamp.replace("T", " ").slice(0, 19)}</td><td>{a.event_type}</td><td>{a.outcome}</td><td className="small muted">{JSON.stringify(a.details)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
