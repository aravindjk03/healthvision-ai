# HealthVision AI

**BMI + Facial Expression Estimation + Consent-Based Face Verification**

> **Status: V1 prototype built.** BMI, face analysis (detection, quality, landmarks,
> expression estimate), consent-based 1:1 face verification, dashboard, history, PDF reports,
> privacy controls and the audit log all work end to end, offline, on one computer.
> It is a **prototype**: models are not validated locally, recognition thresholds are
> demo-uncalibrated and there is no liveness check. Its production-readiness gate reports **NOT MET**.

---

## What HealthVision AI is

Three **separate** measurements, presented together on one dashboard:

| Domain | What it is | What it is NOT |
|---|---|---|
| **BMI** | A deterministic mathematical calculation from height and weight, classified against a selected reference table | A diagnosis, a body-fat measurement, or valid for children with adult cut-offs |
| **Facial expression** | An AI *estimate* of the visible facial-expression category | A reading of internal emotion, mood, mental health or personality |
| **Face verification** | Consent-based biometric comparison against a person's *own* enrolled template | Public face search, stranger identification, or guaranteed-correct identity |

There is **no combined "Health Score"**. See [docs/15_LIMITATIONS.md](docs/15_LIMITATIONS.md).

## Quick start

Requirements: **Python 3.11 or 3.12** (recommended on Windows; 3.13 works on Linux), **Node.js 18+**, and about 1 GB of disk space. A webcam is optional; you can upload photos instead.

**Windows (PowerShell)**
```powershell
git clone https://github.com/aravindjk03/healthvision-ai.git
cd healthvision-ai
.\scripts\setup.ps1      # creates .venv, installs packages, downloads + verifies the 4 AI models, builds the UI
.\scripts\run.ps1        # starts the app and opens http://127.0.0.1:8600
```

**macOS / Linux**
```bash
git clone https://github.com/aravindjk03/healthvision-ai.git && cd healthvision-ai
./scripts/setup.sh && ./scripts/run.sh     # then open http://127.0.0.1:8600
```

On first launch, create the administrator account (there are no default credentials). Then
click **Start analysis**. Everything runs locally, and the app listens on 127.0.0.1 only.

| Task | Command |
|---|---|
| Run the tests | `python tools/fetch_test_fixtures.py` then `python -m pytest` |
| Frontend dev server (hot reload) | `cd frontend && npm run dev` (proxies `/api` to :8600) |
| Verify model files | `python tools/fetch_models.py --verify` |
| Verify the audit-log hash chain | `python tools/verify_audit.py` |
| Measure latency on this device | `python tools/benchmark_latency.py --image <photo> --device <name>` |
| Calibrate recognition thresholds | `python tools/calibrate_recognition.py --manifest <csv> --write` |

Configuration: copy `config/healthvision.example.yaml` to `config/healthvision.yaml` and edit it.
Every threshold is set there; restart the app to apply changes.

### Deploying (container)

`docker build -t healthvision .` then
`docker run -p 127.0.0.1:8600:8600 -e HEALTHVISION_KEK=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())") -v hv-data:/app/data healthvision`.
Keep `HEALTHVISION_KEK` stable and secret, because it encrypts the face templates. V1 is designed
for one device. Before exposing it beyond localhost, put it behind HTTPS and access control,
and read [docs/14](docs/14_PRODUCTION_ROADMAP.md) §6 and [docs/09](docs/09_PRIVACY_ARCHITECTURE.md) §7.
Biometric data has legal requirements in most jurisdictions.

### Code layout

```
backend/healthvision/   FastAPI app: api/, services/, engines/ (YuNet, MediaPipe, FER+, SFace), storage/, reports/
frontend/src/           React + TypeScript UI (pages/, components/)
config/                 healthvision.example.yaml — all thresholds
models/registry.yaml    model registry with pinned SHA-256 (model files are downloaded, not committed)
tools/                  fetch_models, benchmark, calibration and evaluation tools
tests/                  unit, integration, engine-contract and wording-lint tests
```

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
| 17 | [Implementation Notes](docs/17_IMPLEMENTATION_NOTES.md) | Build status and deviations from the plan |

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
