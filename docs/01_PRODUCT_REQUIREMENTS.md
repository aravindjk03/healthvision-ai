# 01 — Product Requirements

## 1. Product objective

HealthVision AI is a **local-first** application that, in one session:

1. Calculates **BMI** from user-entered height and weight and classifies it against a selected, cited reference.
2. Detects **one** face in a captured/uploaded image, assesses **image quality**, extracts **landmarks**, and produces an **estimated visible facial expression** with a confidence band.
3. Optionally, **with separate explicit consent**, enrolls a face template and **verifies** that the person in front of the camera matches their own enrolled identity.
4. Presents these as **three separate results** on a dashboard, with history, a basic report, and privacy controls.

Positioning sentence (use verbatim in UI and webinar):

> "HealthVision AI automates BMI calculation, estimates visible facial expressions, and can verify an enrolled identity — each as a separate, explainable measurement, subject to consent."

## 2. Users and roles

| Role | V1 | Description |
|---|---|---|
| USER | Yes | Person running an analysis on themselves. Sees only their own records. |
| ADMINISTRATOR | Yes (minimal) | Local device admin: configuration, model registry view, retention policy, user management. Cannot view other users' biometric templates (templates are never viewable by anyone). |
| HEALTH/PROGRAM ADMINISTRATOR | No (V3) | Aggregated, consented program-level reporting. |
| AUDITOR | No (V2/V3) | Read-only access to audit logs. In V1 the ADMINISTRATOR can export audit logs. |

## 3. Scope

### 3.1 V1 (prototype) — IN scope

- BMI calculator (metric + imperial input, adult WHO reference, pediatric guard)
- Single-face detection with NO_FACE / ONE_FACE / MULTIPLE_FACES handling
- Image-quality assessment (resolution, brightness, blur, face size, visibility/occlusion, pose)
- Facial landmarks
- Facial-expression estimation (configurable classes, confidence thresholds, three-state result)
- Consent screens with three independent consents (BMI, Face analysis, Recognition)
- Optional face enrollment (template only; no raw image retained by default)
- Basic 1:1 face verification ("Verify my identity")
- Results dashboard (separated: Calculated / AI estimates / Identity)
- History (retention-aware)
- Basic report (HTML view + PDF export)
- Privacy controls (view consents, revoke, delete data)
- Local audit log
- Model registry and model-info endpoint
- Per-stage latency measurement (measured, never invented)

### 3.2 V1 — OUT of scope

- Large-scale cloud deployment, multi-site, PLC/industrial integration
- Medical diagnosis of any kind
- Public face search; 1:N identification across arbitrary images
- Large biometric databases
- Liveness / anti-spoofing (explicitly **not implemented**; documented in UI and report)
- Pediatric BMI-for-age percentiles (returns NOT_APPLICABLE for under-18)
- A combined "health score"

### 3.3 Feature flagged (built but OFF by default)

- `features.identification_enabled = false` — 1:N search within an **authorized enrolled gallery** on the local device. V1 ships the interface and endpoint returning `403 FEATURE_DISABLED`. Implementation deferred to V2.

## 4. Functional requirements

IDs are referenced by tests in [12_TESTING_STRATEGY.md](12_TESTING_STRATEGY.md).

### BMI
- **FR-BMI-1** Accept height in cm, m, or ft+in; weight in kg or lb.
- **FR-BMI-2** Optional age (years) and sex (female / male / prefer not to say). Sex is recorded only for display context; adult BMI categories do not depend on sex.
- **FR-BMI-3** Validate inputs (non-numeric, zero, negative, out of plausible range) → `INVALID_INPUT` with field-level messages.
- **FR-BMI-4** Normalize to metres and kilograms, compute `BMI = kg / m²`, round for display to 2 decimals (store full precision).
- **FR-BMI-5** Classify with the configured reference (default WHO adult). Display category, formula, reference citation, and limitation.
- **FR-BMI-6** If age < 18 (configurable `bmi.adult_min_age`): compute the number but status = `NOT_APPLICABLE` for category; display "Adult BMI categories do not apply under 18. Pediatric assessment uses BMI-for-age percentiles, which this version does not provide."
- **FR-BMI-7** If age not provided: classify as adult but display "Categories assume an adult (18+)."

### Face analysis
- **FR-FACE-1** Webcam capture (browser getUserMedia) or file upload (JPEG/PNG, ≤ 10 MB, ≤ 4096×4096).
- **FR-FACE-2** Pre-capture guidance: "Position one face inside the frame."
- **FR-FACE-3** Detect faces; return bounding boxes, detection confidence, face count.
- **FR-FACE-4** NO_FACE → stop, message "No face detected. Please retake the image."
- **FR-FACE-5** MULTIPLE_FACES → stop, message "Multiple faces detected. Please ensure only one person is in frame." No expression, no recognition on any face.
- **FR-FACE-6** Image quality → GOOD / ACCEPTABLE / POOR with per-check reasons. POOR → `REVIEW / RETAKE IMAGE`, no expression result.
- **FR-FACE-7** Landmarks for alignment, pose and quality. Never presented as medical findings.
- **FR-FACE-8** Expression estimate with status ESTIMATED / UNCERTAIN / NOT_AVAILABLE, confidence, confidence band, full class probability vector stored.
- **FR-FACE-9** UI wording: "Facial expression estimate: Smiling". Never "Person is happy".
- **FR-FACE-10** RETAKE and ANALYZE buttons.

### Recognition
- **FR-REC-1** Recognition page has two modes: VERIFY MY IDENTITY, ENROLL NEW IDENTITY.
- **FR-REC-2** Before either: show biometric notice with ALLOW / DECLINE. DECLINE does not affect BMI or expression features.
- **FR-REC-3** Enrollment: consent → capture (3 frames recommended, min 1) → quality → detect → align → embed → encrypted template storage. Raw images discarded.
- **FR-REC-4** Verification: consent check → capture → quality → detect → align → embed → compare to the **current user's own** template(s) → MATCH / NO_MATCH / UNCERTAIN.
- **FR-REC-5** If thresholds are not calibrated, decisions are labelled `DEMO — UNCALIBRATED THRESHOLD` everywhere they appear.
- **FR-REC-6** UI always shows: "Liveness detection is not implemented in this version. Verification can be fooled by photos or screens."
- **FR-REC-7** Revoking recognition consent deletes templates (crypto-shred) and blocks further recognition.
- **FR-REC-8** Rate limit verification attempts (default 5/min/user, 30/hour/user).

### Results, history, report
- **FR-RES-1** Dashboard with three visually separated panels: CALCULATED (BMI), AI ESTIMATES (face/quality/expression), IDENTITY (recognition, if used).
- **FR-RES-2** Each panel shows model version(s), config version, timestamp.
- **FR-RES-3** Mandatory notes: expression note and BMI note (see section 6).
- **FR-HIS-1** History list: date, BMI, expression estimate, recognition event (if any), link to report.
- **FR-HIS-2** History honors retention; expired records are purged by the retention job.
- **FR-REP-1** Report contains: analysis ID, date/time, BMI & category, face detection, image quality, expression & confidence, recognition result (only if user requested it), model versions, consent status, limitations.
- **FR-REP-2** Report never contains medical conclusions, health scores or face images.

### Privacy
- **FR-PRV-1** Three independent consents; none implies another.
- **FR-PRV-2** Privacy page: view consent states with timestamp and policy version, revoke any, "Delete all my data".
- **FR-PRV-3** All deletions are audited (without biometric content).

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | All AI inference runs locally (CPU baseline). No network call carries face data. |
| NFR-2 | Runs on a laptop (x86-64, 8 GB RAM, no GPU) — Windows 10/11, macOS 13+, Ubuntu 22.04+. |
| NFR-3 | Responsive: per-stage latency measured and displayed; no hard numeric promise until measured (see [03](03_AI_ARCHITECTURE.md) §9). |
| NFR-4 | Every result traceable to input hash, timestamp, model versions, config version, thresholds, decision, consent state. |
| NFR-5 | All thresholds in one config file; none hard-coded. |
| NFR-6 | Each model replaceable via the engine interface + registry without changes to services/UI. |
| NFR-7 | Biometric templates encrypted at rest (AES-256-GCM). |
| NFR-8 | Accessibility: WCAG 2.1 AA for UI text contrast and keyboard navigation. |
| NFR-9 | Backend binds to `127.0.0.1` only in V1. |

## 6. Mandatory wording

| Context | Text |
|---|---|
| Expression label | "Facial expression estimate: {Display label}". Display labels describe visible features in calm wording: Smiling, Calm / neutral, Surprised, Downcast, Frowning, Wide-eyed, Nose wrinkled. Internal classes stay HAPPY, NEUTRAL, SURPRISED, SAD, ANGRY, FEARFUL, DISGUSTED |
| Expression observation (ESTIMATED) | "The face in this photo shows {description}." (e.g. "a warm smile", "a softer, downturned expression") |
| Expression context (ESTIMATED) | Smiling: "A lovely, bright expression in this photo." Calm: "A calm, steady expression in this photo." Downcast / Frowning / Wide-eyed / Nose wrinkled: "Faces change from moment to moment — this captures just one instant, and it says nothing about who you are or how your day is going. Feel free to take another photo anytime." |
| Expression UNCERTAIN | "We need a clearer view to estimate the expression — try facing the camera in soft, even light." |
| Expression system note | "This is an AI estimate of the visible facial expression in one photo. It describes the face at that moment, not how you feel inside." |
| BMI health note | "BMI is a helpful screening number; a healthcare professional can put it in full context for you." |
| BMI guidance | Per WHO category, encouraging and factual, e.g. Normal range: "Great — your BMI is within the WHO adult normal range." Other ranges point to a healthcare professional for the full picture. The category label itself is never changed |
| Multiple faces | "Multiple faces detected. Please make sure only one person is in the frame." |
| Recognition notice | "Facial recognition uses biometric information to verify or identify an enrolled person." |
| Liveness | "Liveness detection is not implemented in this version." |
| Dashboard footer | "These are separate measurements to help you reflect — not a medical diagnosis or a reading of how you feel." |

Tone rule: wording is warm and encouraging, but the **result itself is never changed**. The label shown always corresponds to the model's actual top class, and the BMI category is always the WHO category. A positive tone must not turn into a false reading.

Forbidden strings (CI lint check, see [12](12_TESTING_STRATEGY.md)): "is happy", "definitely", "proves", "health score", "diagnos" (in result text), "100% accurate", "anti-spoof" (unless liveness validated), "mental health".

## 7. UI structure

Navigation: **HOME · BMI ANALYSIS · FACE ANALYSIS · FACE RECOGNITION · HISTORY · REPORTS · PRIVACY · SETTINGS**

| Page | Content |
|---|---|
| HOME | Title "HEALTHVISION AI"; subtitle "BMI + Facial Expression + Consent-Based Face Verification"; primary **START ANALYSIS**; secondary **PRIVACY & CONSENT** |
| BMI ANALYSIS | Height (unit toggle), Weight (unit toggle), optional Age, optional Sex. Output card: BMI, Category, Calculation (`65 ÷ 1.70² = 22.49`), Reference, Limitation. Nothing else. |
| FACE ANALYSIS | Camera/Upload toggle, guidance overlay (oval), capture. After: Face detected / count, Quality (grade + failing checks), Pose (yaw/pitch/roll), Expression estimate, Confidence + band. Buttons RETAKE, ANALYZE. |
| FACE RECOGNITION | Biometric notice (ALLOW/DECLINE) if no consent; then two cards: VERIFY MY IDENTITY, ENROLL NEW IDENTITY. Liveness disclaimer always visible. Identification card hidden unless feature flag on. |
| DASHBOARD | Three separated panels + notes + model versions + timestamp + "Generate report". |
| HISTORY | Table; filter by date; retention notice ("Records older than N days are deleted automatically"). |
| REPORTS | List of generated reports; view/download PDF. |
| PRIVACY | Consent table, revoke buttons, delete enrollment, delete all data, retention policy display, policy version. |
| SETTINGS | Units, language (EN only V1), admin-only: thresholds view (read-only in UI, edited in config file), model registry view, audit log export. |

## 8. User journey

```
START
  │
  ▼
Consent / Privacy Notice ── (BMI consent, Face-analysis consent; Recognition asked later)
  │
  ▼
Enter height ─► Enter weight ─► (optional age/sex)
  │
  ▼
BMI calculation ── INVALID_INPUT → fix fields
  │
  ▼
Capture / upload face ── (skipped if face-analysis consent = NO → dashboard shows BMI only)
  │
  ▼
Image quality check ── POOR → RETAKE
  │
  ▼
Face detection ── NO_FACE / MULTIPLE_FACES → RETAKE
  │
  ▼
Facial landmarks
  │
  ▼
Expression estimation ── UNCERTAIN → shown as UNCERTAIN (not forced)
  │
  ▼
Optional identity verification ── requires Recognition consent + enrollment
  │
  ▼
Results dashboard
  │
  ├─► Optional report
  └─► Optional history
```

Note: the brief lists quality before detection; in implementation, **global** image checks (resolution, brightness, global blur) run before detection and **face-level** checks (face size, face blur, occlusion, pose) run after detection and landmarks. See [05](05_FACE_ANALYSIS_ARCHITECTURE.md) §4.

## 9. Acceptance criteria for V1

V1 is "demo-complete" when:
1. Every FR above has at least one passing automated test.
2. The webinar demo ([16](16_WEBINAR_DEMO_PLAN.md)) runs end-to-end offline on the demo laptop.
3. Forbidden-wording lint passes.
4. Latency numbers on the dashboard are measured values.
5. The production-readiness gate ([14](14_PRODUCTION_ROADMAP.md) §6) is displayed as **NOT MET** in Settings → About.
