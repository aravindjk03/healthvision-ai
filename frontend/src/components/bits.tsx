import type { ReactNode } from "react";
import type { ExpressionResult, QualityCheck } from "../api/client";

export function Badge({ kind, children }: { kind: "good" | "warn" | "bad" | "info" | "neutral"; children: ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function gradeKind(g?: string | null): "good" | "warn" | "bad" | "neutral" {
  return g === "GOOD" ? "good" : g === "ACCEPTABLE" ? "warn" : g === "POOR" ? "bad" : "neutral";
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <div className="field-label">{label}</div>
      <div className="field-value">{children}</div>
    </div>
  );
}

export function QualityList({ checks }: { checks: QualityCheck[] }) {
  return (
    <ul className="checks">
      {checks.map((c) => (
        <li key={c.check}>
          <Badge kind={gradeKind(c.grade)}>{c.grade}</Badge>
          <span>{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}

// Model confidence is never shown as 100% (it is not a certainty).
export const pct = (x: number) => (x >= 0.995 ? ">99%" : x > 0 && x < 0.005 ? "<1%" : `${Math.round(x * 100)}%`);

export function ExpressionCard({ e }: { e: ExpressionResult }) {
  return (
    <div className="expr">
      <div className="expr-head">
        <span className="kicker">FACIAL EXPRESSION</span>
        <Badge kind={e.status === "ESTIMATED" ? "info" : e.status === "UNCERTAIN" ? "warn" : "neutral"}>{e.status}</Badge>
      </div>
      <div className="expr-main">{e.display}</div>
      {e.status === "ESTIMATED" && e.confidence != null && (
        <div className="muted">
          Confidence: <strong>{pct(e.confidence)}</strong> ({e.confidence_band === "HIGH" ? "high" : "moderate"}-confidence estimate) — {e.confidence_label}
        </div>
      )}
      {e.observation && <p className="obs">{e.observation}</p>}
      {e.context && <p className="context">{e.context}</p>}
      {e.probabilities && (
        <div className="bars" aria-label="Class probabilities">
          {Object.entries(e.probabilities).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
            <div className="bar-row" key={k}>
              <span className="bar-label">{e.probability_labels?.[k] ?? k.charAt(0) + k.slice(1).toLowerCase()}</span>
              <span className="bar"><span style={{ width: `${(v * 100).toFixed(1)}%` }} /></span>
              <span className="bar-val">{pct(v)}</span>
            </div>
          ))}
        </div>
      )}
      <p className="note">{e.note}</p>
    </div>
  );
}

export function Latency({ ms }: { ms: Record<string, number> | undefined }) {
  if (!ms) return null;
  const order = ["capture_upload", "decode", "quality_global", "detection", "landmark", "quality_face", "alignment",
    "expression", "liveness", "embedding", "comparison", "total_pipeline"];
  const items = order.filter((k) => ms[k] !== undefined);
  return (
    <div className="latency">
      <span className="muted small">Measured latency:</span>{" "}
      {items.map((k) => (
        <span key={k} className="lat">{k.replace(/_/g, " ")}: {ms[k].toFixed(0)} ms</span>
      ))}
    </div>
  );
}

export function LivenessBanner() {
  return (
    <div className="warnbar" role="note">
      ⚠ Liveness detection is not implemented in this version. Verification can be fooled by photos or screens. Do not use for security decisions.
    </div>
  );
}
