# HealthVision AI — Architecture & Implementation Plan

**BMI + Facial Expression Estimation + Consent-Based Face Verification**

> **Status: V1 prototype implemented as a Streamlit app** (`streamlit_app.py` + `healthvision/` package),
> built from the architecture plan in [docs/](docs/). Not production-ready — see the readiness gate in
> [docs/14_PRODUCTION_ROADMAP.md](docs/14_PRODUCTION_ROADMAP.md) and Settings → readiness in the app.

## Run it

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

On first start the app downloads the four model files listed in [models/registry.yaml](models/registry.yaml)
(~78 MB) and verifies each SHA-256 before loading it. Tests: `pip install -r requirements-dev.txt && pytest`.

### Deploy on Streamlit Community Cloud

1. https://share.streamlit.io → **Create app** → repo `aravindjk03/healthvision-ai`, branch `main`, file `streamlit_app.py`.
2. **Advanced settings → Python 3.12** (the version it was tested on).
3. Deploy. `packages.txt` installs the system libraries OpenCV needs; `requirements.txt` the Python packages.

## What is implemented (V1)

| Component | Implementation |
|---|---|
| UI | Streamlit pages: Home, BMI, Face Analysis, Face Recognition, Dashboard, History, Reports, Privacy, Settings, Documentation |
| Service layer | `healthvision/app.py` facade → `services/` (BMI, consent, face analysis, quality, decision engine, recognition, report, audit) |
| Model A — BMI | Deterministic formula, WHO adult reference (configurable), pediatric guard, unit conversion |
| Model B — detector | YuNet (OpenCV Zoo) |
| Model C — landmarks | MediaPipe Face Landmarker (478 pts, head pose from transform matrix); five-point fallback |
| Model D — expression | FER+ ONNX; configurable classes; HIGH / MODERATE / UNCERTAIN / NOT_AVAILABLE |
| Model E — embedding | SFace (OpenCV Zoo), cosine similarity, MATCH / NO_MATCH / UNCERTAIN |
| Model F — liveness | **Not implemented** — always `NOT_PERFORMED`, disclosed everywhere |
| Thresholds | All in [config/healthvision.yaml](config/healthvision.yaml); every result carries `config_version` + decision trace |
| Privacy | Three independent consents, revocation-triggered deletion, AES-256-GCM envelope-encrypted templates, crypto-shredding, export, delete-all |
| Audit | Hash-chained, rejects biometric fields |

### Deviations from the plan (hosted-demo constraints)

| Plan (docs) | Hosted V1 | Why |
|---|---|---|
| FastAPI backend + React SPA | Streamlit UI calling the same service layer in-process | Single-file deployment on Streamlit Community Cloud |
| SQLite with retention jobs | In-memory store per browser session; nothing written to disk | Public demo should not accumulate biometric or health data |
| KEK in OS keystore | Random KEK per browser session | No OS keystore on the hosting platform |
| Inference on the user's device | Inference on the Streamlit server; images processed in memory and discarded | Hosting model; disclosed in the app sidebar. Run locally for on-device processing |
| Recognition thresholds calibrated | Demo thresholds (vendor reference 0.363 cosine), labelled DEMO — UNCALIBRATED | No local validation set yet (docs/13) |

---

## What HealthVision AI is

Three **separate** measurements, presented together on one dashboard:

| Domain | What it is | What it is NOT |
|---|---|---|
| **BMI** | A deterministic mathematical calculation from height and weight, classified against a selected reference table | A diagnosis, a body-fat measurement, or valid for children with adult cut-offs |
| **Facial expression** | An AI *estimate* of the visible facial-expression category | A reading of internal emotion, mood, mental health or personality |
| **Face verification** | Consent-based biometric comparison against a person's *own* enrolled template | Public face search, stranger identification, or guaranteed-correct identity |

There is **no combined "Health Score"**. See [docs/15_LIMITATIONS.md](docs/15_LIMITATIONS.md).

## Start here

1. [docs/00_ARCHITECTURE_SUMMARY.md](docs/00_ARCHITECTURE_SUMMARY.md) — the final planning output (sections A–S)
2. [docs/02_SYSTEM_ARCHITECTURE.md](docs/02_SYSTEM_ARCHITECTURE.md) — components, layers, repository layout, tech stack
3. [docs/14_PRODUCTION_ROADMAP.md](docs/14_PRODUCTION_ROADMAP.md) — V1 build order (milestones) and V2/V3

## Document index

| # | Document | Purpose |
|---|---|---|
| 00 | [Architecture Summary](docs/00_ARCHITECTURE_SUMMARY.md) | Final planning output A–S |
| 01 | [Product Requirements](docs/01_PRODUCT_REQUIREMENTS.md) | Goals, users, functional & non-functional requirements, UI pages |
| 02 | [System Architecture](docs/02_SYSTEM_ARCHITECTURE.md) | Layers, components, tech stack, repo layout, configuration |
| 03 | [AI Architecture](docs/03_AI_ARCHITECTURE.md) | Model A–F, engine interfaces, model registry, model selection |
| 04 | [BMI Architecture](docs/04_BMI_ARCHITECTURE.md) | Validation, units, formula, references, pediatric rule |
| 05 | [Face Analysis Architecture](docs/05_FACE_ANALYSIS_ARCHITECTURE.md) | Detection, multi-face, quality, landmarks, pose, expression |
| 06 | [Face Recognition Architecture](docs/06_FACE_RECOGNITION_ARCHITECTURE.md) | Enrollment, verification, thresholds, liveness position |
| 07 | [Data Architecture](docs/07_DATA_ARCHITECTURE.md) | Data flows, classification, retention, traceability |
| 08 | [Database Schema](docs/08_DATABASE_SCHEMA.md) | Tables, columns, constraints, indexes |
| 09 | [Privacy Architecture](docs/09_PRIVACY_ARCHITECTURE.md) | Consent model, minimization, deletion, privacy UI |
| 10 | [Security Architecture](docs/10_SECURITY_ARCHITECTURE.md) | AuthN/Z, roles, encryption, audit, rate limiting |
| 11 | [API Architecture](docs/11_API_ARCHITECTURE.md) | Endpoints, request/response contracts, errors |
| 12 | [Testing Strategy](docs/12_TESTING_STRATEGY.md) | Unit, integration, E2E, fixture datasets |
| 13 | [Model Validation](docs/13_MODEL_VALIDATION.md) | Metrics, calibration, bias & fairness validation |
| 14 | [Production Roadmap](docs/14_PRODUCTION_ROADMAP.md) | V1 milestones, V2, V3, readiness gate |
| 15 | [Limitations](docs/15_LIMITATIONS.md) | Known limitations and "never do" list |
| 16 | [Webinar Demo Plan](docs/16_WEBINAR_DEMO_PLAN.md) | 1–2 minute demo script and messaging |

## Note on the source brief

The planning brief supplied for this project began at section 13 (Face Detection).
Sections 1–12 (product introduction and BMI specifics) were not included. The BMI
architecture in [04_BMI_ARCHITECTURE.md](docs/04_BMI_ARCHITECTURE.md) was therefore
reconstructed from the remaining brief (sections 35, 58, 59, 60, 68, 73) and
standard WHO adult BMI practice. **Review section 04 against the original
sections 1–12 before implementation.**

## Core architectural principle

```
BMI                  = mathematical calculation
FACE DETECTION       = locating the face
LANDMARKS            = geometric facial representation
EXPRESSION ANALYSIS  = estimated visible facial expression
FACIAL RECOGNITION   = biometric identity verification/identification
HEALTH INTERPRETATION= only what is scientifically and clinically supported
```

These are never merged into an unexplained "AI health reader".
