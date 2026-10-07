import { useNavigate } from "react-router-dom";
import ConsentPrompt from "../components/ConsentPrompt";
import { useApp } from "../state";

export default function ConsentPage() {
  const { consent } = useApp();
  const nav = useNavigate();
  const decided = (p: string) => {
    const r = consent?.consents.find((c) => c.purpose === p);
    return r && r.status !== "NOT_SET" && !r.reprompt;
  };
  const done = decided("BMI") && decided("FACE_ANALYSIS");

  return (
    <div className="page">
      <h2>Consent &amp; privacy notice</h2>
      <p className="muted">
        Each use has its own consent. Saying no to one does not block the others. Facial recognition is asked
        separately, on the Face Recognition page.
      </p>
      <div className="grid2">
        {(["BMI", "FACE_ANALYSIS"] as const).map((p) => {
          const row = consent?.consents.find((c) => c.purpose === p);
          return decided(p) ? (
            <section className="card" key={p}>
              <h3>{p === "BMI" ? "BMI calculation" : "Facial expression analysis"}</h3>
              <p>Your choice: <strong>{row?.status === "GRANTED" ? "Allowed" : "Declined"}</strong></p>
              <p className="muted small">Change this at any time on the Privacy page.</p>
            </section>
          ) : (
            <ConsentPrompt key={p} purpose={p} />
          );
        })}
      </div>
      <button className="btn primary" disabled={!done} onClick={() => nav("/bmi")}>Continue</button>
    </div>
  );
}
