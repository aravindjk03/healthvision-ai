import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";

interface Item { analysis_id: string; started_at: string; bmi: string | null; bmi_category: string | null; expression: string | null; expression_status: string | null; recognition: string | null }

export default function HistoryPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [notice, setNotice] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    const q = new URLSearchParams();
    if (from) q.set("date_from", from);
    if (to) q.set("date_to", to);
    api.get<{ items: Item[]; retention_notice: string }>(`/history?${q}`).then((r) => { setItems(r.items); setNotice(r.retention_notice); });
  }, [from, to]);

  return (
    <div className="page">
      <h2>History</h2>
      <div className="row">
        <label className="inline-label">From <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="inline-label">To <input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
      </div>
      <p className="muted small">{notice}</p>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Date</th><th>BMI</th><th>Expression estimate</th><th>Identity</th><th /></tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={5} className="muted">No analyses yet.</td></tr>}
            {items.map((i) => (
              <tr key={i.analysis_id}>
                <td>{new Date(i.started_at).toLocaleString()}</td>
                <td>{i.bmi ? `${i.bmi} · ${i.bmi_category}` : "—"}</td>
                <td>{i.expression ? i.expression.charAt(0) + i.expression.slice(1).toLowerCase() : i.expression_status?.replace("_", " ").toLowerCase() ?? "—"}</td>
                <td>{i.recognition?.replace("_", " ") ?? "—"}</td>
                <td><Link to={`/dashboard/${i.analysis_id}`}>Open</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
