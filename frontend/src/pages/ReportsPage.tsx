import { useEffect, useState } from "react";
import { api } from "../api/client";

interface Item { report_id: string; session_id: string; created_at: string; include_recognition: boolean; expires_at: string }

export default function ReportsPage() {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => { api.get<{ items: Item[] }>("/reports").then((r) => setItems(r.items)); }, []);
  return (
    <div className="page">
      <h2>Reports</h2>
      <p className="muted small">Reports never contain face images, medical conclusions or health scores. They are deleted automatically when they expire.</p>
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Created</th><th>Analysis</th><th>Identity included</th><th>Expires</th><th /></tr></thead>
          <tbody>
            {items.length === 0 && <tr><td colSpan={5} className="muted">No reports yet. Generate one from the dashboard.</td></tr>}
            {items.map((r) => (
              <tr key={r.report_id}>
                <td>{new Date(r.created_at).toLocaleString()}</td>
                <td>{r.session_id.slice(0, 8)}</td>
                <td>{r.include_recognition ? "Yes" : "No"}</td>
                <td>{r.expires_at.slice(0, 10)}</td>
                <td className="row">
                  <a href={`/api/v1/reports/${r.report_id}`} target="_blank" rel="noreferrer">View</a>
                  <a href={`/api/v1/reports/${r.report_id}/pdf`}>Download PDF</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
