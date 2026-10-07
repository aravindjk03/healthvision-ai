# 16 — Webinar Demo Plan

Covers brief §69–70. This is a 1–2 minute live demonstration of V1 running **offline on one laptop**. The demo shows three separate measurements, each with its limitations stated. Every number on screen is either computed (BMI) or measured live (expression confidence, latency). Nothing is pre-filled for show.

## 1. Demo objective

The audience should leave knowing three things:
1. BMI is **calculated**, with the formula and the reference shown.
2. The facial expression is an **estimate** of what is visible, with a confidence value, and it is not an emotion.
3. Identity verification is **consent-based**, compares only against the user's own enrollment, and in V1 is **demo-uncalibrated with no liveness check**.

Positioning sentence (verbatim, from [01](01_PRODUCT_REQUIREMENTS.md) §1):

> "HealthVision AI automates BMI calculation, estimates visible facial expressions, and can verify an enrolled identity — each as a separate, explainable measurement, subject to consent."

## 2. Script (brief §69)

| Step | Screen | Presenter action | Presenter says (suggested) |
|---|---|---|---|
| 1 | HOME | Click **START ANALYSIS** | "Everything runs on this laptop. No face data leaves it." |
| 2 | Consent | ALLOW BMI and Facial expression analysis. Recognition is asked later | "Each use has its own consent. Saying no to one doesn't block the others." |
| 3 | BMI ANALYSIS | Enter **170 cm**, **65 kg** → Calculate | "BMI is a calculation: 65 ÷ 1.70² = **22.49**, which is in the WHO adult **Normal range**. It's a screening measure, not a diagnosis." |
| 4 | FACE ANALYSIS | Camera on, face inside the oval, **CAPTURE** | "One face in frame. The image is checked for quality first." |
| 5 | Result | Point at **Face detected**, then Quality GOOD/ACCEPTABLE, then pose | "It found one face, and the image is good enough to analyse." |
| 6 | Expression | Smile naturally, then **ANALYZE** | "Facial expression estimate: Happy, at **{the confidence actually shown}**. That's the model's confidence about the visible expression. It doesn't tell us how I feel." |
| 7 | *(optional)* FACE RECOGNITION | ALLOW the recognition notice → **VERIFY MY IDENTITY** (enrolled before the webinar) | "With separate biometric consent, it can check that I match my own enrollment. Note the banner: thresholds are demo-uncalibrated and there's no liveness check, so this isn't a security feature yet." |
| 8 | DASHBOARD | Show the three panels: CALCULATED / AI ESTIMATES / IDENTITY | "Three separate results, never merged into a score. Each one shows the model version, config version and measured latency." |
| 9 | Close | Point at the footer note, then the Privacy page | "These are separate measurements, not a medical diagnosis or a definitive emotional state. You can revoke consent and delete your data at any time." |

**Do not quote a fixed confidence such as "91 %".** Read out the number on screen. If the result is **UNCERTAIN**, say so. That shows the system declines to guess: "It wasn't confident enough, so it says *uncertain* rather than guessing. Let me retake it." Then retake once.

## 3. Timed run-sheet

| Time (mm:ss) | Segment | Hard cut-off |
|---|---|---|
| 00:00–00:10 | Intro + positioning sentence (HOME) | 00:12 |
| 00:10–00:20 | Consent (BMI + Face) | 00:25 |
| 00:20–00:35 | BMI 170 / 65 → 22.49 Normal range | 00:40 |
| 00:35–01:00 | Capture → Face detected → quality → expression estimate | 01:05 |
| 01:00–01:25 | *(optional)* Verify with demo-uncalibrated banner | skip if past 01:05 |
| 01:25–01:45 | Dashboard (three panels) | 01:50 |
| 01:45–02:00 | Privacy + limitation statement; close | 02:00 |

The short version (≈ 1:15) skips step 7 and goes straight from the expression result to the dashboard.

## 4. Messaging do / don't (brief §70)

The "Don't say" column quotes forbidden phrases in order to forbid them. It is allow-listed by the wording lint in the same way as the "never do" sections.

| Do say | Don't say |
|---|---|
| "BMI is calculated from height and weight." | "AI measures your health." |
| "Facial expression estimate: Happy." | "It knows you're happy." / "It reads your emotions." |
| "Model confidence: {value}." | "{value} accurate." / "100 % accurate." |
| "Verifies against your own enrollment, with your consent." | "Recognises anyone." / "Facial search." |
| "Demo thresholds, not yet calibrated. No liveness check yet." | "Secure biometric login." / "Spoof-proof." |
| "Latency measured on this laptop: {value from dashboard}." | Latency figures from slides or memory |
| "Separate measurements. No combined score." | "Health score." / "Wellness index." |
| "Not a medical diagnosis." | Any disease, risk or mental-health language |
| "Validation and fairness testing come before production." | "Unbiased." / "Clinically validated." / "Production-ready." |

Slides follow the same rules and are put through the wording lint ([12](12_TESTING_STRATEGY.md) §7) before the event.

## 5. Fallbacks

| Failure | Fallback | Say |
|---|---|---|
| Camera unavailable or permission denied | Switch to **Upload** and use the consented demo fixture `tests/fixtures/demo/presenter_smile.jpg` | "Same pipeline, using a saved photo." |
| NO_FACE / POOR quality | RETAKE once with better lighting. Then use the upload fixture | "It refuses to analyse a poor image. That's on purpose." |
| UNCERTAIN expression | Retake once. If it is still UNCERTAIN, move on | "It says uncertain rather than guessing." |
| Someone walks into frame (MULTIPLE_FACES) | Show the message, then retake | "With two faces, it stops." |
| Verify returns NO_MATCH / UNCERTAIN | Show it honestly. Do not retry more than once | "Borderline lighting. And remember these thresholds aren't calibrated yet." |
| Backend crash / app frozen | Switch to the **pre-recorded screen video** (same script, recorded on the demo laptop at the final rehearsal) | "Let me show the recorded run." |
| Venue network down | No effect: the demo is fully **offline** after the model fetch | — |
| Laptop failure | Backup laptop with the same build, models and enrollment, or the pre-recorded video | — |

The pre-recorded video must be labelled "Recorded run" on screen and must show the real values from that run.

## 6. Pre-demo checklist

**T − 1 week**
- [ ] V1 milestones M0–M11 complete ([14](14_PRODUCTION_ROADMAP.md) §2). E2E journeys 1–5 pass with the network disabled
- [ ] Wording lint passes on the app, report template **and slides**
- [ ] `tools/benchmark_latency.py` run on the demo laptop. Only these numbers, if any, are mentioned
- [ ] Demo fixture photo has written consent from the presenter and is recorded in `tests/fixtures/PROVENANCE.md`

**T − 1 day**
- [ ] Fresh demo profile: admin set up; presenter account created; **enrolled** (3 frames, venue-like lighting) if step 7 is planned
- [ ] Three full rehearsals ≤ 2:00 each; record the final one as the fallback video
- [ ] Settings → About shows readiness gate `NOT_MET`; the demo-uncalibrated banner is visible on verify
- [ ] Backup laptop prepared and checked

**T − 30 min**
- [ ] Wi-Fi **off**; app started; `GET /health` all models READY; warm-up completed
- [ ] Camera tested in venue lighting; ring light / front light positioned; background clear of other faces
- [ ] OS notifications, screen savers and auto-updates disabled; display scaling readable at the back of the room
- [ ] Browser at HOME, zoom 125 %, other tabs closed; fallback video and upload fixture open in the background
- [ ] Consents reset so step 2 can be shown live (recognition consent left GRANTED only if step 7 is planned)

**After the demo**
- [ ] "Delete all my data" for any audience volunteer (avoid volunteers in V1)
- [ ] Export the audit log if required; confirm `RETENTION_PURGE` is scheduled
