# 00 — Architecture Summary (Final Planning Output A–S)

Covers brief §77. This is the one-page entry point to the HealthVision AI plan. Each section gives the decisions and links to the detailed document. **Status: planning complete; no application code exists yet.** Implementation starts at milestone M0 ([14](14_PRODUCTION_ROADMAP.md) §2).

---

## A. Product summary
HealthVision AI is a **local-first** application that produces **three separate measurements** in one session: a calculated **BMI**, an AI **estimate of the visible facial expression**, and optional **consent-based 1:1 face verification** against the user's own enrollment. There is **no combined health score**. V1 is a prototype that runs offline on one laptop.
→ [README](../README.md), [01 Product Requirements](01_PRODUCT_REQUIREMENTS.md) §1–3

## B. Core principles
- BMI = calculation; detection = locating the face; landmarks = geometry; expression = estimate; recognition = biometric verification. These are never merged.
- Privacy-first: three independent consents, no raw images retained, templates encrypted.
- Configurable thresholds only (`config/healthvision.yaml`), and every result can be traced.
- No unsupported claims: no figure appears unless it was computed or measured.
→ [01](01_PRODUCT_REQUIREMENTS.md) §5–6, [02](02_SYSTEM_ARCHITECTURE.md) §1

## C. Users, roles & UI
Roles: USER and ADMINISTRATOR (V1); AUDITOR (V2/V3); PROGRAM_ADMINISTRATOR (V3). Pages: HOME · BMI ANALYSIS · FACE ANALYSIS · FACE RECOGNITION · HISTORY · REPORTS · PRIVACY · SETTINGS, plus the DASHBOARD with CALCULATED / AI ESTIMATES / IDENTITY panels. Mandatory wording and forbidden strings are fixed.
→ [01](01_PRODUCT_REQUIREMENTS.md) §2, §6–8, [10](10_SECURITY_ARCHITECTURE.md) §3

## D. System architecture
Modular monolith: React 18 + TypeScript SPA → FastAPI (Python 3.11, bound to 127.0.0.1) → service layer (`AnalysisSessionService`, `BmiService`, `FaceAnalysisService`, `FaceQualityService`, `RecognitionService`, `ConsentService`, `DecisionEngine`, `ResultService`, `HistoryService`, `ReportService`, `RetentionService`, `AuditService`, `AuthService`) → engines / repositories → SQLite + model files. Ports & adapters for every model; one config file versioned by hash.
→ [02](02_SYSTEM_ARCHITECTURE.md) §2–8, §10

## E. AI model architecture
| Model | V1 default | Licence |
|---|---|---|
| A — BMI | Deterministic formula | — |
| B — Face detector | YuNet (OpenCV Zoo) | MIT |
| C — Landmarks | MediaPipe Face Landmarker | Apache-2.0 |
| D — Expression | FER+ ONNX (`emotion-ferplus-8`) | MIT |
| E — Embedding | SFace (128-D) | Apache-2.0 |
| F — Liveness | `NotImplementedLivenessEngine` | — |

Engines return raw scores only, and the `DecisionEngine` applies thresholds and returns a `DecisionTrace`. The model registry verifies SHA-256 and enforces `license_status`.
→ [03](03_AI_ARCHITECTURE.md)

## F. BMI architecture
Validation → unit normalization (cm/m/ft_in, kg/lb) → `kg / m²` → applicability → `WHO_ADULT_2000` (default) or `WHO_ASIAN_2004` classification, using half-open intervals on the unrounded value. States: VALID / INVALID_INPUT / NOT_APPLICABLE. The pediatric rule applies under 18. Example: 170 cm, 65 kg → **22.49, Normal range**.
→ [04](04_BMI_ARCHITECTURE.md)

## G. Face detection, quality & landmarks
Global quality checks → YuNet → face-count gate (NO_FACE / ONE_FACE / MULTIPLE_FACES; a weaker second face still blocks) → MediaPipe landmarks + pose → face-level quality (size, blur, occlusion, pose) → grade GOOD / ACCEPTABLE / POOR (worst check wins). POOR → RETAKE. Landmarks are geometry only and are not stored.
→ [05](05_FACE_ANALYSIS_ARCHITECTURE.md) §1–5

## H. Expression estimation
5-point alignment → 64×64 grayscale → FER+ → class map (contempt excluded and renormalized) → temperature → thresholds (high 0.85, moderate 0.60, margin 0.15, all PROVISIONAL). States: ESTIMATED (HIGH/MODERATE) / UNCERTAIN / NOT_AVAILABLE. The output is worded "Facial expression estimate: {Class}".
→ [05](05_FACE_ANALYSIS_ARCHITECTURE.md) §6–8, [03](03_AI_ARCHITECTURE.md) §5.1

## I. Face recognition
Separate RECOGNITION consent. Enrollment takes 1–5 frames (3 recommended), with GOOD quality, an intra-consistency check and AES-256-GCM templates; raw frames are discarded. Verification compares only against the user's **own** templates (max cosine) → MATCH / NO_MATCH / UNCERTAIN / NOT_PERFORMED. If no calibration file exists → **DEMO-UNCALIBRATED** (0.40 / 0.30) with a banner. Identification (1:N) is behind a flag and returns 403 in V1. Rate limits and lockout apply.
→ [06](06_FACE_RECOGNITION_ARCHITECTURE.md)

## J. Liveness & presentation attacks
Liveness is **not implemented** in V1. `NOT_PERFORMED` is recorded on every event and the absence is disclosed everywhere. Verification is not an authentication method. V2 adds a validated PAD model (ISO/IEC 30107-3).
→ [06](06_FACE_RECOGNITION_ARCHITECTURE.md) §6, [15](15_LIMITATIONS.md) §4

## K. Data architecture & traceability
Every result stores `session_id`, `input_sha256`, timestamp, model ids/versions, `config_version`, thresholds + `threshold_source`, decision, `trace_json` and a consent snapshot. Each data type has its own retention period. Raw images are not retained. Templates are kept until consent is revoked.
→ [07](07_DATA_ARCHITECTURE.md)

## L. Database schema
SQLite (WAL) via SQLAlchemy + Alembic, portable to PostgreSQL. Tables: users, user_consents, analysis_sessions, bmi_records, face_observations, expression_results, face_enrollments, face_templates, recognition_events, reports, audit_logs, config_versions, model_versions, auth_sessions. Enums are fixed in §1.
→ [08](08_DATABASE_SCHEMA.md)

## M. Privacy & consent
Purposes BMI, FACE_ANALYSIS and RECOGNITION are independent (GALLERY_MEMBERSHIP is future). Consent is append-only with policy version and notice hash. Revocation triggers deletion (templates are crypto-shredded). Users can export their data and "Delete all my data". Regulatory review is required before production.
→ [09](09_PRIVACY_ARCHITECTURE.md)

## N. Security
argon2id local accounts, cookie sessions + CSRF, role checks and ownership isolation, envelope encryption with the KEK in the OS keystore, a hash-chained audit log, rate limiting, model SHA-256 verification, and CI security tooling.
→ [10](10_SECURITY_ARCHITECTURE.md)

## O. API
REST at `http://127.0.0.1:8600/api/v1`: `/auth`, `/consent`, `/bmi/calculate`, `/face/detect`, `/face/expression`, `/face/enroll`, `/face/verify`, `/face/identify` (403), `/analysis`, `/history`, `/reports`, `/model-info`, `/privacy`, `/admin`, `/health`. Pipeline stop states return 200 with a body. Errors use a fixed envelope.
→ [11](11_API_ARCHITECTURE.md)

## P. Testing
Unit (BMI property tests, DecisionEngine), engine contract tests, integration with real CPU models, Playwright E2E with a fake camera, security tests, a forbidden-wording lint, offline E2E, and a 3-OS CI matrix. Coverage ≥ 90 % on core packages.
→ [12](12_TESTING_STRATEGY.md)

## Q. Model validation, bias & fairness
Validation protocols per model (detection face-count accuracy, expression macro-F1 + ECE, recognition FAR/FRR/EER + calibration), subgroup fairness with n and CIs, latency benchmarks, and re-validation triggers. **Current status: nothing has been validated locally.**
→ [13](13_MODEL_VALIDATION.md)

## R. Roadmap, deployment & readiness gate
V1 milestones M0–M11; V2 (validation, calibration, PAD, gallery 1:N, GPU/Jetson); V3 (OIDC, central non-biometric aggregates, PostgreSQL, fleet). Diagram 10 shows the production architecture, plus a scalability table. The production-readiness gate (G1–G11) is shown via `/model-info` and is **NOT_MET** in V1.
→ [14](14_PRODUCTION_ROADMAP.md), [02](02_SYSTEM_ARCHITECTURE.md) §9

## S. Limitations, NEVER list & demo
An expression is not an emotion; BMI has limits and adult categories don't apply to children; no liveness; demo-uncalibrated thresholds; models and fairness not validated; research-only licence caveats (InsightFace weights, AffectNet); brief §1–12 missing and to be reconciled. The full NEVER list is in [15](15_LIMITATIONS.md) §10. The webinar is a 1–2 minute offline script: 170 cm / 65 kg → 22.49 → capture → expression estimate (the live value) → optional verify with banner → dashboard → privacy statement.
→ [15](15_LIMITATIONS.md), [16](16_WEBINAR_DEMO_PLAN.md)

---

### Open decisions before implementation
1. Reconcile [04](04_BMI_ARCHITECTURE.md) with the original brief §1–12.
2. Product owner sets the expression accuracy targets per band and the recognition target FAR ([13](13_MODEL_VALIDATION.md) §3.3, §4.2).
3. Confirm the deployment jurisdiction for the privacy/legal review ([09](09_PRIVACY_ARCHITECTURE.md) §7).
