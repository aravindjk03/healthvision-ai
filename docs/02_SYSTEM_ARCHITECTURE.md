# 02 — System Architecture

## 1. Architectural style

- **Local-first modular monolith** for V1: one Python backend process + one browser frontend, both on the same machine.
- **Strict layering**: `UI → API → Service layer → Engines / Repositories → Database / Model files`. The UI never touches models; engines never touch the database; services orchestrate.
- **Ports & adapters** for every AI model: services depend on abstract engine interfaces; concrete adapters (YuNet, MediaPipe, SFace, …) are selected by configuration through the model registry.
- **Separate result types**: `BmiResult`, `FaceAnalysisResult` (detection + quality + landmarks + expression), `RecognitionResult`. Never merged into a score.

## 2. Diagram 1 — Overall system (V1)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          USER DEVICE (laptop)                            │
│                                                                          │
│  ┌──────────────────────────────┐        HTTP (127.0.0.1 only)           │
│  │  Browser — React SPA         │  ───────────────────────────────┐      │
│  │  • Pages (Home, BMI, Face…)  │  JSON + multipart image          │      │
│  │  • getUserMedia camera       │                                  ▼      │
│  └──────────────────────────────┘   ┌──────────────────────────────────┐ │
│                                     │ FastAPI backend (Python 3.11)    │ │
│                                     │                                  │ │
│                                     │  API layer (routers, validation, │ │
│                                     │   auth, rate limit, errors)      │ │
│                                     │            │                     │ │
│                                     │  ┌─────────▼──────────────────┐  │ │
│                                     │  │ SERVICE LAYER              │  │ │
│                                     │  │ AnalysisSessionService     │  │ │
│                                     │  │ BmiService                 │  │ │
│                                     │  │ FaceAnalysisService        │  │ │
│                                     │  │ RecognitionService         │  │ │
│                                     │  │ ConsentService             │  │ │
│                                     │  │ FaceQualityService         │  │ │
│                                     │  │ DecisionEngine             │  │ │
│                                     │  │ ResultService / Report /   │  │ │
│                                     │  │ History / Retention / Audit│  │ │
│                                     │  └───┬───────────────┬────────┘  │ │
│                                     │      │               │           │ │
│                                     │  ┌───▼─────────┐ ┌───▼────────┐  │ │
│                                     │  │ AI ENGINES  │ │ STORAGE    │  │ │
│                                     │  │ Detector    │ │ Repos      │  │ │
│                                     │  │ Landmarks   │ │ TemplateStore│ │ │
│                                     │  │ Quality     │ │ Crypto     │  │ │
│                                     │  │ Expression  │ └───┬────────┘  │ │
│                                     │  │ Embedding   │     │           │ │
│                                     │  │ (Liveness*) │     │           │ │
│                                     │  └───┬─────────┘     │           │ │
│                                     └──────┼───────────────┼───────────┘ │
│                                            │               │             │
│                         ┌──────────────────▼──┐   ┌────────▼──────────┐  │
│                         │ models/ (ONNX/TFLite│   │ data/healthvision │  │
│                         │ + registry.yaml,    │   │ .db (SQLite)      │  │
│                         │ SHA-256 verified)   │   │ + keystore (OS)   │  │
│                         └─────────────────────┘   └───────────────────┘  │
│                                                                          │
│   * Liveness = interface only in V1 (NotImplementedLivenessEngine)       │
│   No outbound network calls carry face data. Cloud is optional (V3).     │
└──────────────────────────────────────────────────────────────────────────┘
```

## 3. Technology stack (decided)

| Concern | Choice | Reason |
|---|---|---|
| Backend language | Python 3.11 | Mature CV/ML ecosystem |
| Web framework | FastAPI + Uvicorn | Typed request/response (Pydantic v2), OpenAPI generation |
| Inference runtime | ONNX Runtime (CPU EP default; CUDA/TensorRT/DirectML EP optional) + OpenCV 4.9+ DNN + MediaPipe Tasks | Vendor-neutral, CPU-capable, edge-portable |
| Image processing | OpenCV (`opencv-python-headless`), NumPy, Pillow (EXIF orientation) | |
| DB | SQLite 3 (WAL mode) via SQLAlchemy 2.x; migrations via Alembic | Zero-ops local DB; Postgres-compatible schema for V3 |
| Crypto | `cryptography` (AES-256-GCM), `argon2-cffi` (passwords), `keyring` (OS key store: Windows DPAPI/Credential Manager, macOS Keychain, Linux Secret Service) | |
| Config | YAML file + Pydantic Settings, versioned & hashed | Single source of thresholds |
| Reports | Jinja2 HTML template → PDF via ReportLab | No external services; pure Python on Windows |
| Frontend | React 18 + TypeScript + Vite; React Router; TanStack Query; plain CSS modules | |
| Testing | pytest, pytest-cov, hypothesis (BMI property tests), Playwright (E2E), Vitest (frontend units) | |
| Packaging | `uv`/pip `pyproject.toml`; frontend built to static files served by FastAPI at `/` | Single process to launch for demo |
| Logging | `structlog` JSON logs (no images, no embeddings) | |

## 4. Layer responsibilities

| Layer | May call | Must not |
|---|---|---|
| UI (React) | API only | Load models, compute BMI categories, decide thresholds, hold templates |
| API (routers) | Services; auth & rate-limit dependencies | Contain business logic or call engines directly |
| Services | Engines, repositories, ConsentService, AuditService, ConfigProvider | Know concrete model vendors |
| Engines | Model runtime, NumPy/OpenCV | Touch DB, consent, users, or decide final user-facing wording |
| DecisionEngine | Config thresholds | Run models |
| Repositories | SQLAlchemy session | Apply business rules |

## 5. Service pipelines (from brief §65)

Face analysis:
```
UI
 ↓
FaceAnalysisService
 ↓  (ConsentService.require(FACE_ANALYSIS))
ImageIngest (decode, EXIF orient, size checks, input hash)
 ↓
FaceQualityService.global_checks
 ↓
FaceDetector            (Model B)
 ↓  face-count gate
LandmarkEngine          (Model C)
 ↓
FaceQualityService.face_checks (+ pose)
 ↓  quality gate
Aligner → ExpressionEngine (Model D)
 ↓
DecisionEngine.expression()
 ↓
ResultService.persist + AuditService (if applicable)
```

Recognition:
```
UI
 ↓
RecognitionService
 ↓
ConsentService.require(RECOGNITION)
 ↓
FaceQualityService  (+ FaceDetector, LandmarkEngine via shared pipeline)
 ↓
LivenessEngine      (Model F — V1: NotImplemented → status NOT_PERFORMED)
 ↓
EmbeddingModel      (Model E)
 ↓
TemplateStore       (decrypt user's own templates in memory)
 ↓
DecisionEngine.recognition()
 ↓
RecognitionEvent persisted + AuditService
```

## 6. Component catalogue

| Component | Module | Responsibility |
|---|---|---|
| `AnalysisSessionService` | `services/session_service.py` | Creates `analysis_session`, ties BMI/face/recognition results together, finalizes dashboard view |
| `BmiService` | `services/bmi_service.py` | Validation, normalization, formula, classification ([04](04_BMI_ARCHITECTURE.md)) |
| `FaceAnalysisService` | `services/face_analysis_service.py` | Orchestrates face pipeline ([05](05_FACE_ANALYSIS_ARCHITECTURE.md)) |
| `FaceQualityService` | `services/face_quality_service.py` | Global + face-level quality checks, grade |
| `RecognitionService` | `services/recognition_service.py` | Enroll / verify / (identify, flagged) ([06](06_FACE_RECOGNITION_ARCHITECTURE.md)) |
| `ConsentService` | `services/consent_service.py` | Grant/decline/revoke, `require(purpose)`; triggers deletion on revoke ([09](09_PRIVACY_ARCHITECTURE.md)) |
| `DecisionEngine` | `services/decision_engine.py` | Pure functions converting scores + config thresholds into states; returns a `DecisionTrace` |
| `ResultService` | `services/result_service.py` | Persists results with traceability fields |
| `HistoryService` | `services/history_service.py` | Lists user's sessions (retention-filtered) |
| `ReportService` | `services/report_service.py` | Builds report DTO, HTML, PDF |
| `RetentionService` | `services/retention_service.py` | Scheduled purge (APScheduler in-process, hourly + on startup) |
| `AuditService` | `services/audit_service.py` | Append-only, hash-chained audit entries ([10](10_SECURITY_ARCHITECTURE.md)) |
| `AuthService` | `services/auth_service.py` | Local accounts, sessions, roles |
| `ModelRegistry` | `registry/model_registry.py` | Loads `models/registry.yaml`, verifies SHA-256, instantiates adapters |
| `ConfigProvider` | `config/provider.py` | Loads, validates, hashes config → `config_version` |
| `TemplateStore` | `storage/template_store.py` | Encrypt/decrypt templates, crypto-shred |
| `LatencyRecorder` | `core/latency.py` | Context manager timing each stage (perf_counter_ns) |

## 7. Repository layout (to be created by the coding agent)

```
healthvision-ai/
├── README.md
├── docs/                         # this plan
├── config/
│   ├── healthvision.yaml         # active config (gitignored copy of example)
│   └── healthvision.example.yaml
├── models/
│   ├── registry.yaml             # model registry (see 03 §7)
│   └── *.onnx / *.task           # downloaded by tools/fetch_models.py (gitignored)
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                  # migrations
│   └── healthvision/
│       ├── main.py               # FastAPI app factory, static frontend mount
│       ├── api/                  # routers: bmi, face, recognition, consent, analysis,
│       │                         #   history, reports, model_info, auth, admin
│       ├── core/                 # errors, latency, ids, hashing, time
│       ├── config/               # settings schema, provider
│       ├── domain/               # enums, dataclasses (results, traces)
│       ├── services/             # see §6
│       ├── engines/
│       │   ├── base.py           # abstract interfaces (03 §3)
│       │   ├── detection/        # yunet.py, mediapipe_detector.py, retinaface.py
│       │   ├── landmarks/        # mediapipe_landmarker.py
│       │   ├── quality/          # metrics.py (blur, brightness, pose)
│       │   ├── alignment/        # similarity_transform.py
│       │   ├── expression/       # ferplus_onnx.py, (hsemotion_onnx.py candidate)
│       │   ├── recognition/      # sface.py, (arcface_onnx.py candidate)
│       │   └── liveness/         # not_implemented.py
│       ├── registry/
│       ├── storage/              # db.py, models_orm.py, repositories/, crypto.py, template_store.py
│       └── reports/              # templates/report.html.j2, pdf.py
├── frontend/
│   ├── package.json
│   └── src/ (pages/, components/, api/, hooks/, styles/)
├── tools/
│   ├── fetch_models.py           # downloads + verifies SHA-256 from registry
│   ├── calibrate_recognition.py  # threshold calibration (13 §4)
│   ├── evaluate_expression.py
│   ├── evaluate_detector.py
│   └── benchmark_latency.py
└── tests/
    ├── unit/  integration/  e2e/  fixtures/  wording_lint/
```

## 8. Configuration (single source of thresholds)

All thresholds live in `config/healthvision.yaml`. The file's SHA-256 (first 12 hex chars) plus `config_schema_version` form the `config_version` recorded with every result. Changing the file is an audited `CONFIG_CHANGE` event at next startup (hash differs from last recorded).

Reference `healthvision.example.yaml` (values marked `# PROVISIONAL` must be tuned per [13](13_MODEL_VALIDATION.md)):

```yaml
config_schema_version: 1

server:
  host: 127.0.0.1
  port: 8600
  max_upload_bytes: 10485760
  max_image_side_px: 4096

features:
  recognition_enabled: true
  identification_enabled: false        # 1:N gallery search (V2)
  liveness_enabled: false              # no validated liveness model in V1
  store_raw_images: false

bmi:
  reference: WHO_ADULT_2000            # WHO_ADULT_2000 | WHO_ASIAN_2004
  adult_min_age: 18
  height_cm: {min: 50, max: 272}
  weight_kg: {min: 2, max: 635}
  plausibility_warning: {bmi_min: 10, bmi_max: 80}

face_detection:
  engine: yunet                         # yunet | mediapipe | retinaface
  face_detection_threshold: 0.80        # PROVISIONAL
  nms_threshold: 0.30
  max_faces_considered: 10
  min_secondary_face_confidence: 0.60   # faces above this count toward MULTIPLE_FACES

quality:
  min_image_short_side_px: 480
  minimum_face_size_px: 112             # inter-ocular-independent face box short side
  brightness_threshold: {min_mean: 60, max_mean: 200}   # 0–255 luminance, PROVISIONAL
  blur_threshold: {laplacian_var_good: 120, laplacian_var_min: 60}  # face crop, PROVISIONAL
  pose_max_deg: {yaw_good: 15, yaw_max: 30, pitch_good: 15, pitch_max: 25, roll_max: 25}
  occlusion: {min_landmark_visibility: 0.80}
  grade_policy: worst_check             # overall grade = worst individual check

expression:
  engine: ferplus_onnx
  classes: [HAPPY, NEUTRAL, SAD, SURPRISED, ANGRY, FEARFUL, DISGUSTED]
  class_map:                            # model label -> product class (null = excluded)
    happiness: HAPPY
    neutral: NEUTRAL
    sadness: SAD
    surprise: SURPRISED
    anger: ANGRY
    fear: FEARFUL
    disgust: DISGUSTED
    contempt: null
  renormalize_after_exclusion: true
  expression_confidence_threshold:
    high: 0.85
    moderate: 0.60                      # below this => UNCERTAIN
  min_top2_margin: 0.15                 # top1 - top2 below this => UNCERTAIN, PROVISIONAL
  temperature: 1.0                      # set by calibration (13 §3.3)

recognition:
  engine: sface
  calibration_file: models/calibration/sface_v1.json   # absent => DEMO-UNCALIBRATED mode
  demo_uncalibrated_thresholds:         # used ONLY when calibration file absent; labelled in UI
    recognition_threshold: 0.40         # cosine similarity
    no_match_threshold: 0.30
  enrollment_frames: {min: 1, recommended: 3, max: 5}
  max_templates_per_user: 5
  rate_limit: {per_minute: 5, per_hour: 30}
  lockout_after_consecutive_no_match: 10

retention:
  retention_period_days:
    bmi_records: 365
    expression_results: 90
    recognition_events: 90
    analysis_sessions: 365
    reports: 90
    audit_logs: 730
  face_templates: until_consent_revoked
  raw_images: not_retained
  purge_interval_minutes: 60

security:
  session_idle_minutes: 30
  session_absolute_hours: 8
  password_min_length: 12
  login_rate_limit: {per_minute: 5}

logging:
  level: INFO
  log_images: false                     # must remain false; startup refuses true
```

Rules for the coding agent:
1. No numeric threshold literal may appear outside `config/` and tests. Enforced by a test that greps `engines/` and `services/` for float literals in comparison expressions (allow-list for math constants).
2. Config is immutable at runtime; reload requires restart (keeps `config_version` coherent).
3. Startup validation fails fast on missing/invalid keys.

## 9. Diagram 9 — Edge deployment options

```
                    ┌────────────────────────────────────────┐
                    │  Same codebase, different EP / package │
                    └────────────────────────────────────────┘
   V1                       V2                               V2/V3
┌───────────────┐   ┌─────────────────────┐   ┌──────────────────────────────┐
│ Laptop / PC   │   │ Desktop with GPU    │   │ NVIDIA Jetson Orin / Mini PC │
│ CPU only      │   │ ONNX Runtime CUDA / │   │ / Industrial edge computer   │
│ ORT CPU EP    │   │ DirectML EP         │   │ ORT TensorRT EP, Docker      │
│ Browser UI on │   │ Browser UI on same  │   │ (L4T base image), kiosk UI   │
│ same machine  │   │ machine or LAN(TLS) │   │ over LAN with TLS + auth     │
└───────┬───────┘   └──────────┬──────────┘   └──────────────┬───────────────┘
        │                      │                             │
        └──────── All inference local; DB local; ────────────┘
                  optional sync of NON-biometric aggregates to a
                  central service only in V3 and only with consent
```

Hardware abstraction: `inference.execution_providers` (config, V2) is an ordered list passed to ONNX Runtime; engines never reference a provider directly.

## 10. Runtime & process model

- One Uvicorn worker (models loaded once into memory; SQLite single-writer). Inference executed in a bounded `ThreadPoolExecutor` (size = physical cores − 1, min 1) to keep the event loop responsive.
- Model warm-up at startup (one dummy inference per engine) so first-request latency is not misreported; warm-up times are logged separately.
- Startup sequence: load config → validate → verify model files (SHA-256) → open DB + migrate → load keystore key → warm-up → start retention scheduler → serve.
- If any required model fails verification, dependent features are disabled and `/model-info` reports `status: UNAVAILABLE`; BMI remains usable.
