# HealthVision AI

**BMI + Facial Expression Estimation + Consent-Based Face Verification**

> **Status: V1 prototype built, in three versions** (below). BMI, face analysis (detection, quality,
> landmarks, expression estimate) and consent-based 1:1 face verification work end to end.
> It is a **prototype**: models are not validated locally, recognition thresholds are
> demo-uncalibrated and there is no liveness check. The production-readiness gate reports **NOT MET**.

## Three ways to run it

| Version | Best for | Where the photo is processed | Start |
|---|---|---|---|
| **Streamlit app** (`streamlit_app.py`, `healthvision/`) | A hosted link for a remote team | On the Streamlit server, in memory, then discarded | [Streamlit](#streamlit-app) |
| **Full app** (`backend/healthvision_server/` + `frontend/`) | Full features on one computer: logins, history, PDF reports, audit log, camera | On that computer only | [Full app](#full-app-fastapi--react) |
| **Browser-only demo** (`web-demo/`) | A static website or offline demo; no server | Inside each visitor's browser | [web-demo/README.md](web-demo/README.md) |

All three use the same four model files (YuNet, MediaPipe Face Landmarker, FER+, SFace). Each version has its own settings file, so some demo thresholds differ (for example the Streamlit app uses a 0.363 recognition threshold, the others 0.40).

---

## What HealthVision AI is

Three **separate** measurements, presented together on one dashboard:

| Domain | What it is | What it is NOT |
|---|---|---|
| **BMI** | A deterministic mathematical calculation from height and weight, classified against a selected reference table | A diagnosis, a body-fat measurement, or valid for children with adult cut-offs |
| **Facial expression** | An AI *estimate* of the visible facial-expression category | A reading of internal emotion, mood, mental health or personality |
| **Face verification** | Consent-based biometric comparison against a person's *own* enrolled template | Public face search, stranger identification, or guaranteed-correct identity |

There is **no combined "Health Score"**. See [docs/15_LIMITATIONS.md](docs/15_LIMITATIONS.md).

## Streamlit app

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

On first start the app downloads the four model files listed in [models/registry.yaml](models/registry.yaml)
(~78 MB) and verifies each SHA-256 before loading it. Tests: `pip install -r requirements-dev.txt && pytest tests/test_*.py`.

### Deploy on Streamlit Community Cloud (live link for the team)

1. https://share.streamlit.io → **Create app** → repo `aravindjk03/healthvision-ai`, branch `main`, file `streamlit_app.py`.
2. **Advanced settings → Python 3.12** (the version it was tested on).
3. Deploy. `packages.txt` installs the system libraries OpenCV needs; `requirements.txt` the Python packages.

### What the Streamlit app implements

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

#### Deviations from the plan (hosted-demo constraints)

| Plan (docs) | Hosted V1 | Why |
|---|---|---|
| FastAPI backend + React SPA | Streamlit UI calling the same service layer in-process | Single-file deployment on Streamlit Community Cloud |
| SQLite with retention jobs | In-memory store per browser session; nothing written to disk | Public demo should not accumulate biometric or health data |
| KEK in OS keystore | Random KEK per browser session | No OS keystore on the hosting platform |
| Inference on the user's device | Inference on the Streamlit server; images processed in memory and discarded | Hosting model; disclosed in the app sidebar. Run locally for on-device processing |
| Recognition thresholds calibrated | Demo thresholds (vendor reference 0.363 cosine), labelled DEMO — UNCALIBRATED | No local validation set yet (docs/13) |

## Full app (FastAPI + React)

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

Configuration: copy `config/server.example.yaml` to `config/server.yaml` and edit it. (`config/healthvision.yaml` is the Streamlit app's settings file.)
Every threshold is set there; restart the app to apply changes.

### Deploying (container)

`docker build -t healthvision .` then
`docker run -p 127.0.0.1:8600:8600 -e HEALTHVISION_KEK=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())") -v hv-data:/app/data healthvision`.
Keep `HEALTHVISION_KEK` stable and secret, because it encrypts the face templates. V1 is designed
for one device. Before exposing it beyond localhost, put it behind HTTPS and access control,
and read [docs/14](docs/14_PRODUCTION_ROADMAP.md) §6 and [docs/09](docs/09_PRIVACY_ARCHITECTURE.md) §7.
Biometric data has legal requirements in most jurisdictions.

### Sharing with your team

| Option | What the team gets | How |
|---|---|---|
| **GitHub Pages** (recommended for testing) | The browser-only version at `https://<owner>.github.io/healthvision-ai/`, with camera, BMI, face analysis and verification. Photos never leave each person's browser | 1. Merge to `main`. 2. Repo **Settings → Pages → Source: GitHub Actions**. 3. The workflow `.github/workflows/pages.yml` builds and deploys on every push to `main` (or run it manually from the **Actions** tab). Pages on a private repo needs a paid GitHub plan; on a free plan the repo must be public. The site is reachable by anyone with the URL |
| **Streamlit Community Cloud** (simplest hosted link) | The Streamlit app at `https://<name>.streamlit.app` | See [Deploy on Streamlit Community Cloud](#deploy-on-streamlit-community-cloud-live-link-for-the-team). Photos are processed on Streamlit's server in memory, not stored |
| **Shared claude.ai link** | The same browser version (photo upload only, the camera is blocked inside that viewer) | Open the link → **Share** → add teammates |
| **Full app on a server** | Logins, history, PDF reports, audit log | Deploy the `Dockerfile` to a cloud host (Cloud Run, Render, Azure, …). Admins add users under **Settings → Users**. Needs HTTPS for the camera and a privacy review before real biometric data is used |
| **Full app on each laptop** | Everything, offline | Each person runs `scripts/setup.ps1` + `scripts/run.ps1` |

GitHub itself only stores the code. It cannot run a Python server, so the Streamlit app needs Streamlit Cloud and the full app needs a server or each laptop.

### Code layout

```
streamlit_app.py, healthvision/   Streamlit app and its service layer (config/healthvision.yaml, models/registry.yaml)
backend/healthvision_server/      FastAPI app: api/, services/, engines/, storage/, reports/
frontend/src/                     React + TypeScript UI for the FastAPI app
web-demo/                         Browser-only single page (ONNX Runtime Web + MediaPipe)
config/server.example.yaml        FastAPI app thresholds        models/server-registry.yaml  its model registry
tools/                            fetch_models, benchmark, calibration and evaluation tools (FastAPI app)
tests/                            test_*.py: Streamlit app · unit/ integration/ wording_lint/: FastAPI app
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
