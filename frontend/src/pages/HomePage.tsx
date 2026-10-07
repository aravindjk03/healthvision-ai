import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useApp } from "../state";

export default function HomePage() {
  const { setSessionId, consent } = useApp();
  const nav = useNavigate();

  const start = async () => {
    const r = await api.post<{ analysis_id: string }>("/analysis");
    setSessionId(r.analysis_id);
    const undecided = consent?.consents.filter((c) => c.purpose !== "RECOGNITION" && (c.status === "NOT_SET" || c.reprompt));
    nav(undecided && undecided.length ? "/consent" : "/bmi");
  };

  return (
    <div className="home">
      <section className="hero">
        <h1>HEALTHVISION AI</h1>
        <p className="sub">BMI + Facial Expression + Consent-Based Face Verification</p>
        <p className="lead">
          HealthVision AI automates BMI calculation, estimates visible facial expressions, and can verify an enrolled
          identity — each as a separate, explainable measurement, subject to consent.
        </p>
        <div className="row">
          <button className="btn primary lg" onClick={start}>Start analysis</button>
          <button className="btn lg" onClick={() => nav("/privacy")}>Privacy &amp; consent</button>
        </div>
      </section>
      <section className="three">
        <div className="card">
          <span className="kicker calc">CALCULATED</span>
          <h3>BMI</h3>
          <p>A mathematical calculation from height and weight, classified against the WHO adult reference.</p>
          <p className="muted small">Not a diagnosis. Adult categories do not apply under 18.</p>
        </div>
        <div className="card">
          <span className="kicker ai">AI ESTIMATE</span>
          <h3>Facial expression</h3>
          <p>An estimate of the <em>visible</em> facial expression, with a confidence value — or "uncertain".</p>
          <p className="muted small">Not a reading of emotion, mood or mental state.</p>
        </div>
        <div className="card">
          <span className="kicker id">IDENTITY</span>
          <h3>Face verification</h3>
          <p>With separate biometric consent, checks that you match your own enrollment on this device.</p>
          <p className="muted small">Demo thresholds; no liveness check in this version.</p>
        </div>
      </section>
      <p className="muted small center">All processing runs on this device. No face images are stored. There is no combined health score.</p>
    </div>
  );
}
