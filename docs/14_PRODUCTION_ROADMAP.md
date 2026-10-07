# 14 — Production Roadmap

Covers brief §53, §61–64, §75. This document sets the **build order** for V1 and the scope for V2 and V3. It also defines the **production-readiness gate**. V1 is a prototype, and the gate is expected to show **NOT_MET** for all of V1.

## 1. Phasing overview

| Phase | Purpose | Deployment | Gate status |
|---|---|---|---|
| **V1 — Prototype** | Show three separate, explainable measurements end-to-end on one laptop, offline | Local-first modular monolith ([02](02_SYSTEM_ARCHITECTURE.md) §1) | Readiness gate **NOT_MET** (by design) |
| **V2 — Validated edge product** | Validate models, calibrate thresholds, add liveness, harden for LAN/edge devices | Laptop / GPU desktop / Jetson-class edge ([02](02_SYSTEM_ARCHITECTURE.md) §9) | Gate can become **MET** for named deployments only |
| **V3 — Enterprise / multi-site** | Organisation identity, central non-biometric aggregation, multi-device fleet | Edge inference + central result service (§5) | Gate is re-evaluated per site and per jurisdiction |

Rules that apply to every phase:
- A milestone is done only when its **done-when** criteria pass in CI. Reviewer opinion is not enough.
- No milestone may add a numeric threshold outside `config/` ([02](02_SYSTEM_ARCHITECTURE.md) §8, rule 1).
- No milestone may add wording that fails the forbidden-wording lint ([12](12_TESTING_STRATEGY.md) §7).
- Accuracy, fairness and latency figures appear only after they have been measured ([13](13_MODEL_VALIDATION.md)).

## 2. V1 milestones (M0–M11)

Milestones are listed in dependency order. M3 (BMI) only needs M0–M2, so a BMI-only build can be shown early.

```
M0 ─► M1 ─► M2 ─┬─► M3 (BMI) ───────────────────────────────┐
                │                                           │
                └─► M4 (registry + adapters) ─► M5 (face) ─► M6 (recognition)
                                                            │
                                     M7 (sessions/dashboard/history) ◄─┘
                                                            │
                                     M8 (reports) ─► M9 (retention/deletion)
                                                            │
                                     M10 (tooling) ─► M11 (demo hardening)
```

| # | Milestone | Key deliverables | Done when |
|---|---|---|---|
| **M0** | Skeleton & configuration | Repository layout from [02](02_SYSTEM_ARCHITECTURE.md) §7; `pyproject.toml`; FastAPI app factory; Vite/React shell with the nav from [01](01_PRODUCT_REQUIREMENTS.md) §7; `ConfigProvider` with Pydantic schema, `config_version` hashing, fail-fast validation; `healthvision.example.yaml`; `structlog` setup with `log_images: false` enforced; `LatencyRecorder`; CI (ruff, mypy, pytest, Vitest, bandit, pip-audit, npm audit); the wording-lint and "no threshold literal" tests | `GET /health` returns 200; an invalid config fails startup with a clear error; `log_images: true` refuses to start; CI is green on Windows, macOS and Ubuntu |
| **M1** | Storage, auth, audit, crypto | SQLAlchemy models + Alembic migration for every table in [08](08_DATABASE_SCHEMA.md); repositories with ownership checks; `AuthService` (argon2id, first-run `/auth/setup`, sessions, CSRF, login rate limit); `AuditService` with hash chain + `verify_audit` tool; `crypto.py` (AES-256-GCM envelope, KEK in OS keystore via `keyring`); `TemplateStore` with crypto-shred | Ownership-isolation tests pass; the audit chain verifies and detects a tampered row; the template round-trip encrypts and decrypts, and after crypto-shred decryption is impossible; startup without a keystore disables recognition only |
| **M2** | Consent | `ConsentService` (`record`, `require`, `revoke`); `POST/GET /consent`; `require_consent` dependency on every protected route; notice text + `notice_sha256`; policy-version re-prompt logic; `DeletionOrchestrator` stub wired to revoke | A parametrized test over the route table shows that every protected endpoint returns `403 CONSENT_REQUIRED` without consent; consent rows are append-only; every change writes a `CONSENT_CHANGE` audit entry |
| **M3** | BMI | `BmiService`, `bmi_references.yaml` (`WHO_ADULT_2000`, `WHO_ASIAN_2004`), `DecisionEngine` rule `bmi.v1`, `POST /bmi/calculate`, BMI page | Every case in [12](12_TESTING_STRATEGY.md) §2.1 passes, including boundaries, the pediatric `NOT_APPLICABLE` case, units and hypothesis property tests; 170 cm / 65 kg returns `22.49`, `Normal range` |
| **M4** | Model registry & engine adapters | `engines/base.py` interfaces ([03](03_AI_ARCHITECTURE.md) §3); `ModelRegistry` (YAML load, SHA-256 verify, adapter instantiation, `license_status` enforcement); adapters for YuNet, MediaPipe Face Landmarker, FER+ ONNX, SFace and `NotImplementedLivenessEngine`; `tools/fetch_models.py`; warm-up at startup; `GET /model-info` | Engine contract tests ([12](12_TESTING_STRATEGY.md) §3) pass for every adapter; a hash mismatch disables the model, writes `MODEL_INTEGRITY_FAILURE` and reports `UNAVAILABLE`; a `REVIEW_REQUIRED` model refuses to load unless `allow_restricted_licenses: true` |
| **M5** | Face analysis | ImageIngest; `FaceQualityService` (global + face-level checks, grade policy); face-count rule `face_count.v1`; landmarks + pose; 5-point alignment; expression rule `expression.v1` (class map, renormalization, temperature, margin, ACCEPTABLE cap); `POST /face/detect`, `POST /face/expression`; Face Analysis page with oval overlay, CAPTURE, RETAKE, ANALYZE | Every row of the fail-safe matrix ([05](05_FACE_ANALYSIS_ARCHITECTURE.md) §7) passes on fixtures; the multiple-face fixture returns no expression; the UI shows "Facial expression estimate: …" and never "is happy"; landmarks are not persisted |
| **M6** | Recognition (1:1 verify) | `RecognitionService.enroll/verify`; intra-consistency check; `face_enrollments` / `face_templates` storage; `recognition.v1` with `threshold_source`; DEMO-UNCALIBRATED banner; rate limits + lockout; `/face/enroll`, `/face/verify`, `GET/DELETE /face/enrollment`; `/face/identify` → `403 FEATURE_DISABLED`; Face Recognition page with the recognition notice and liveness disclaimer | Enroll → verify → MATCH works on fixtures; with no calibration file every response has `demo_uncalibrated: true`, and the UI and report show the banner; no response schema contains a template or embedding; revoke → verify returns `NOT_PERFORMED: NO_CONSENT` |
| **M7** | Sessions, dashboard, history | `AnalysisSessionService`; `POST /analysis`, `GET /analysis/{id}`; dashboard with three separate panels (CALCULATED / AI ESTIMATES / IDENTITY), the mandatory notes, model + config versions and measured latency; `GET /history` + History page with the retention notice | E2E journey 2 ([12](12_TESTING_STRATEGY.md) §4) passes; the dashboard shows no combined score; every latency figure shown comes from `LatencyRecorder` |
| **M8** | Reports | `ReportService` (DTO → Jinja2 HTML → ReportLab PDF); `POST /reports`, `GET /reports/{id}`, `/pdf`; Reports page; `REPORT_GENERATION` audit | The report contains every field in FR-REP-1 and no image, landmark, embedding, health score or diagnosis text (template lint); the recognition section appears only if the user ran recognition |
| **M9** | Retention & deletion | `RetentionService` (APScheduler, on startup + every `purge_interval_minutes`); full `DeletionOrchestrator` per purpose; `DELETE /privacy/data`; `GET /privacy/export`; Privacy page | Expired rows are purged and `RETENTION_PURGE` is audited; "Delete all my data" leaves no user rows except the audit trail; the export JSON contains no templates; revoking RECOGNITION crypto-shreds templates in one transaction |
| **M10** | Tooling | `tools/benchmark_latency.py`, `tools/evaluate_detector.py`, `tools/evaluate_expression.py`, `tools/calibrate_recognition.py` writing to `reports/validation/` and `registry.yaml` `local_validated`; `docs/model_cards/` template; admin `GET /admin/audit`, `/admin/config`, user management | Every tool runs end-to-end on a small fixture manifest and writes JSON with the dataset, n, git commit and hardware; `/model-info` reflects `local_validated` and the calibration state |
| **M11** | Demo hardening | Demo profile (seed admin via setup, demo fixtures, offline check); Settings → About shows the readiness gate (§6); pre-recorded fallback video; webinar run-sheet rehearsal ([16](16_WEBINAR_DEMO_PLAN.md)) | E2E journeys 1–5 pass with the network disabled; three full rehearsals finish in ≤ 2 min each; the About page shows `NOT_MET` with the reasons for each failing item |

V1 is **demo-complete** when M0–M11 are done and the acceptance criteria in [01](01_PRODUCT_REQUIREMENTS.md) §9 pass.

## 3. V2 — Validated edge product (brief §62)

| Area | V2 work |
|---|---|
| Model validation | Assemble consented and licensed validation sets; run the full [13](13_MODEL_VALIDATION.md) protocol for the detector, landmarks, expression and recognition; publish model cards |
| Recognition calibration | Produce `models/calibration/sface_v1.json` from the production pipeline; drop DEMO-UNCALIBRATED mode for calibrated deployments |
| Bias & fairness | Complete the subgroup table ([13](13_MODEL_VALIDATION.md) §5); document disparities in [15](15_LIMITATIONS.md); product owner decides mitigations |
| Liveness / PAD | Evaluate and integrate a validated presentation-attack-detection model (ISO/IEC 30107-3: APCER, BPCER); replace `NotImplementedLivenessEngine` |
| Identification (1:N) | Implement `RecognitionService.identify()` behind `features.identification_enabled` for **admin-defined galleries**, with per-member `GALLERY_MEMBERSHIP` consent ([06](06_FACE_RECOGNITION_ARCHITECTURE.md) §9) |
| Model alternatives | Evaluate HSEmotion, ArcFace/AdaFace, RetinaFace/SCRFD with the scorecard ([03](03_AI_ARCHITECTURE.md) §8); adopt a model only if the decision rule passes **and** the license is approved |
| Temporal smoothing | Multi-frame capture (3 frames / 1 s) with median-probability expression; frame count recorded in the trace |
| Hardware acceleration | `inference.execution_providers` (CUDA, DirectML, TensorRT); Jetson Docker image (L4T base) |
| Security | TLS for LAN/kiosk use (mkcert), SQLCipher full-DB encryption option, AUDITOR role |
| Pediatric BMI | Optional WHO 2007 BMI-for-age z-scores (5–19 y) with LMS tables and separate validation |
| Localisation | Message catalogue i18n; wording lint per language |

## 4. V3 — Enterprise / multi-site (brief §63)

| Area | V3 work |
|---|---|
| Identity | OAuth2/OIDC organisation login; PROGRAM_ADMINISTRATOR role; SCIM user provisioning |
| Central result service | Optional central service that receives **non-biometric aggregates only**, and only with consent; templates never leave the edge device |
| Database | PostgreSQL (the schema is already portable, [08](08_DATABASE_SCHEMA.md)); managed backups; row-level security |
| Scale & ops | Fleet management of edge devices, signed model/config bundles, staged rollout, central monitoring (no images or biometrics in telemetry) |
| Rate limiting | Redis-backed limits across instances |
| Compliance | Per-jurisdiction DPIA, BIPA/GDPR Art. 9 consent flows, EU AI Act assessment for expression estimation ([09](09_PRIVACY_ARCHITECTURE.md) §7) |
| API | `/api/v2` alongside `/api/v1` for one release |
| Integrations | Program-level reporting exports (aggregated, consented); no PLC/industrial control coupling without a separate safety assessment |

## 5. Diagram 10 — Production architecture (brief §64)

```
┌──────────────┐     ┌────────────────────┐     ┌─────────────────────────────┐
│   DEVICE     │     │  SECURE CLIENT     │     │   EDGE AI ENGINES           │
│ camera +     │────►│ browser / kiosk UI │────►│ (on-device, ORT CPU/GPU EP) │
│ screen       │ TLS │ OIDC session, CSRF │ TLS │ Detector  (YuNet)           │
└──────────────┘     │ no image caching   │     │ Landmarks (MediaPipe)       │
                     └────────────────────┘     │ Quality                     │
                                                │ Liveness  (validated PAD,V2)│
                                                │ Expression(FER+ / approved) │
                                                │ Embedding (SFace / approved)│
                                                └──────────────┬──────────────┘
                                                               │ scores only
                                                               ▼
                         ┌──────────────────────────────────────────────────────┐
                         │                  RESULT SERVICE                      │
                         │  ┌──────────────┐ ┌──────────────────┐               │
                         │  │ BmiService   │ │ RecognitionSvc   │               │
                         │  └──────────────┘ │ (+DecisionEngine)│               │
                         │  ┌──────────────┐ └──────────────────┘               │
                         │  │ConsentService│ ┌──────────────────┐               │
                         │  └──────────────┘ │ AuditService     │               │
                         │                   └──────────────────┘               │
                         └──────────────────────────┬───────────────────────────┘
                                                    │
                                                    ▼
                         ┌──────────────────────────────────────────────────────┐
                         │                 SECURE DATA STORE                    │
                         │ Edge: SQLite/SQLCipher — results, consents, audit,   │
                         │       encrypted templates (KEK in OS keystore/TPM)   │
                         │ Central (V3, optional): PostgreSQL — NON-biometric   │
                         │       consented aggregates only                      │
                         └──────────────────────────────────────────────────────┘
```

Invariants carried from V1: raw images are not retained; templates never leave the device that enrolled them; engines return scores and the `DecisionEngine` applies thresholds from config or calibration files.

### Scalability (brief §53)

| Dimension | V1 | V2 | V3 |
|---|---|---|---|
| Users per device | A few local accounts | Tens (kiosk / clinic room) | Tens per device × fleet |
| Concurrency | One Uvicorn worker; inference thread pool | Same, plus GPU EP | Horizontal edge devices; central service scales statelessly |
| Inference location | Local CPU | Local CPU/GPU/Jetson | Edge only (no central inference on faces) |
| Database | SQLite (WAL) | SQLite + SQLCipher | Edge SQLite + central PostgreSQL (aggregates) |
| Templates | ≤ 5 per user, local | Same; gallery size bounded by admin | Per-site galleries; never centralised |
| Rate limiting | In-process token bucket | Same | Redis-backed |
| Model distribution | `tools/fetch_models.py` + SHA-256 | Signed bundles | Signed bundles + staged fleet rollout |
| Observability | Local structured logs | Local logs + export | Central metrics (no images or biometrics) |
| Bottleneck to watch | CPU inference latency | Gallery size for 1:N | Fleet config drift; consent synchronisation |

## 6. Production-readiness gate (brief §75)

The gate is computed at startup from the registry, calibration files, validation reports and config. It appears in `GET /model-info` as `production_readiness_gate` ([11](11_API_ARCHITECTURE.md) §4) and in Settings → About with the status of each item. The overall gate is **MET** only when every item is MET. **In V1 it is `NOT_MET` by design.**

| # | Criterion | Evidence required | V1 status |
|---|---|---|---|
| G1 | Detector validated locally | `local_validated` for `face_detector.yunet` with face-count accuracy and missed-second-face rate ≤ 1 % ([13](13_MODEL_VALIDATION.md) §2) | NOT_MET |
| G2 | Expression model validated and calibrated | Validation report + fitted temperature + accuracy targets per band met ([13](13_MODEL_VALIDATION.md) §3) | NOT_MET |
| G3 | Recognition thresholds calibrated | `models/calibration/sface_v1.json` present, produced by the production pipeline, with enough impostor comparisons for the claimed FAR ([13](13_MODEL_VALIDATION.md) §4) | NOT_MET (DEMO-UNCALIBRATED) |
| G4 | Fairness evaluated | Subgroup table complete with n and CIs; disparities documented ([13](13_MODEL_VALIDATION.md) §5) | NOT_MET ("not yet evaluated") |
| G5 | Liveness / PAD validated (required if recognition is used for any access decision) | ISO/IEC 30107-3 report | NOT_MET (not implemented) |
| G6 | Latency measured on the target hardware | `reports/benchmarks/` for the deployment device class | NOT_MET until M10 runs on that hardware |
| G7 | Licenses approved | Every loaded model has `license_status: APPROVED` (code + weights + training data) | MET for defaults; reviewed again if models change |
| G8 | Security review | Threat model reviewed; bandit/pip-audit clean; penetration test for networked deployments | NOT_MET (no external review) |
| G9 | Privacy & legal review | DPIA and jurisdiction review ([09](09_PRIVACY_ARCHITECTURE.md) §7) | NOT_MET |
| G10 | Clinical-claim review | Confirms that no output is presented as a diagnosis; BMI reference approved by a qualified reviewer; brief §1–12 reconciled ([15](15_LIMITATIONS.md) §8) | NOT_MET |
| G11 | Operational readiness | Backup/restore procedure, incident response, model re-validation schedule ([13](13_MODEL_VALIDATION.md) §8) | NOT_MET |

`/model-info` shape (extends [11](11_API_ARCHITECTURE.md) §4):

```json
"production_readiness_gate": "NOT_MET",
"production_readiness_items": [
  {"id": "G3", "criterion": "Recognition thresholds calibrated", "status": "NOT_MET",
   "reason": "No calibration file; using demo_uncalibrated thresholds"}
]
```

Rule: no UI text, report, slide or sales material may describe HealthVision AI as "production-ready", "clinically validated" or "accurate to X %" while the gate is NOT_MET.
