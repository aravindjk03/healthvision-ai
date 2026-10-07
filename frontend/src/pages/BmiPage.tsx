import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type BmiResult } from "../api/client";
import { Badge } from "../components/bits";
import ConsentPrompt from "../components/ConsentPrompt";
import { granted, useApp } from "../state";

export default function BmiPage() {
  const { consent, sessionId, setSessionId } = useApp();
  const nav = useNavigate();
  const [hUnit, setHUnit] = useState<"cm" | "ft_in">("cm");
  const [wUnit, setWUnit] = useState<"kg" | "lb">("kg");
  const [height, setHeight] = useState("");
  const [feet, setFeet] = useState("");
  const [inches, setInches] = useState("");
  const [weight, setWeight] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("unspecified");
  const [result, setResult] = useState<BmiResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!granted(consent, "BMI")) {
    return (
      <div className="page">
        <h2>BMI analysis</h2>
        <ConsentPrompt purpose="BMI" />
      </div>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.post<{ session_id: string | null; result: BmiResult }>("/bmi/calculate", {
        session_id: sessionId,
        height: hUnit === "cm" ? { value: height, unit: "cm" } : { feet, inches: inches || "0", unit: "ft_in" },
        weight: { value: weight, unit: wUnit },
        age_years: age || null,
        sex,
      });
      if (r.session_id) setSessionId(r.session_id);
      setResult(r.result);
    } catch (err) {
      if (err instanceof ApiError && err.code === "NOT_FOUND") { setSessionId(null); setError("Your previous analysis expired. Please calculate again."); }
      else setError(err instanceof ApiError ? err.message : "Request failed");
    }
  };

  const fieldErr = (f: string) => result?.errors?.find((x) => x.field === f)?.message;

  return (
    <div className="page">
      <h2>BMI analysis</h2>
      <div className="grid2">
        <form className="card" onSubmit={submit} noValidate>
          <label>Height
            <div className="inline">
              {hUnit === "cm" ? (
                <input inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="170" aria-label="Height in centimetres" />
              ) : (
                <>
                  <input inputMode="numeric" value={feet} onChange={(e) => setFeet(e.target.value)} placeholder="ft" aria-label="Feet" />
                  <input inputMode="decimal" value={inches} onChange={(e) => setInches(e.target.value)} placeholder="in" aria-label="Inches" />
                </>
              )}
              <select value={hUnit} onChange={(e) => setHUnit(e.target.value as "cm" | "ft_in")} aria-label="Height unit">
                <option value="cm">cm</option><option value="ft_in">ft + in</option>
              </select>
            </div>
            {fieldErr("height") && <span className="ferr">{fieldErr("height")}</span>}
          </label>
          <label>Weight
            <div className="inline">
              <input inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="65" aria-label="Weight" />
              <select value={wUnit} onChange={(e) => setWUnit(e.target.value as "kg" | "lb")} aria-label="Weight unit">
                <option value="kg">kg</option><option value="lb">lb</option>
              </select>
            </div>
            {fieldErr("weight") && <span className="ferr">{fieldErr("weight")}</span>}
          </label>
          <div className="inline">
            <label>Age (optional)<input inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value)} placeholder="years" />
              {fieldErr("age_years") && <span className="ferr">{fieldErr("age_years")}</span>}</label>
            <label>Sex (optional)
              <select value={sex} onChange={(e) => setSex(e.target.value)}>
                <option value="unspecified">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option>
              </select>
            </label>
          </div>
          <p className="hint">Adult BMI categories do not depend on sex.</p>
          {error && <div className="error">{error}</div>}
          <button className="btn primary">Calculate BMI</button>
        </form>

        <section className="card result" aria-live="polite">
          <span className="kicker calc">CALCULATED</span>
          {!result && <p className="muted">Enter height and weight to calculate.</p>}
          {result?.status === "INVALID_INPUT" && <p className="error">Please correct the highlighted fields.</p>}
          {result && result.status !== "INVALID_INPUT" && (
            <>
              <div className={`bmi-big ${result.status === "NOT_APPLICABLE" ? "grey" : ""}`}>{result.bmi_display}<small> kg/m²</small></div>
              {result.status === "VALID" ? (
                <>
                  <div><Badge kind={result.category_code === "NORMAL" ? "good" : "info"}>{result.category_label}</Badge></div>
                  {result.guidance && <p className="context">{result.guidance}</p>}
                </>
              ) : (
                <div className="info">{result.message}</div>
              )}
              <dl className="kv">
                <dt>Calculation</dt><dd>{result.calculation}</dd>
                <dt>Reference</dt><dd>{result.reference.citation}</dd>
                <dt>Limitation</dt><dd>{result.limitation}</dd>
              </dl>
              {result.warnings?.map((w) => <p key={w} className="hint">{w}</p>)}
              <div className="row">
                <button className="btn primary" onClick={() => nav("/face")}>Next: face analysis</button>
                <button className="btn" onClick={() => nav("/dashboard")}>View dashboard</button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
