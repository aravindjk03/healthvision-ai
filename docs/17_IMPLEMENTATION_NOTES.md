# 17 — Implementation Notes (V1 build)

This file records how the V1 code maps to the plan in docs 01–16, and the places where the build deliberately differs from the plan, with the reason for each.

## 1. Status against the V1 milestones ([14](14_PRODUCTION_ROADMAP.md) §2)

| # | Milestone | Status | Where |
|---|---|---|---|
| M0 | Skeleton & configuration | Done | `backend/healthvision/{main,container}.py`, `config/`, `frontend/` |
| M1 | Storage, auth, audit, crypto | Done | `storage/`, `services/{auth,audit}_service.py` |
| M2 | Consent | Done | `services/consent_service.py` |
| M3 | BMI | Done | `services/bmi_service.py`, `domain/bmi_references.yaml` |
| M4 | Model registry & engine adapters | Done | `registry/`, `engines/`, `models/registry.yaml`, `tools/fetch_models.py` |
| M5 | Face analysis | Done | `services/face_pipeline.py`, `services/face_analysis_service.py` |
| M6 | Recognition (1:1 verify) | Done | `services/recognition_service.py` |
| M7 | Sessions, dashboard, history | Done | `services/session_service.py`, `api/routes.py` |
| M8 | Reports | Done | `services/report_service.py`, `reports/` |
| M9 | Retention & deletion | Done | `services/privacy_service.py` |
| M10 | Tooling | Done (needs datasets to produce results) | `tools/` |
| M11 | Demo hardening | Partly done: offline run verified; rehearsal and the fallback video are tasks for the presenter | [16](16_WEBINAR_DEMO_PLAN.md) |

The readiness gate ([14](14_PRODUCTION_ROADMAP.md) §6) is computed at startup and reports **NOT_MET**. G7 (licences) is the only item that is MET.

## 2. Deviations from the plan

| Plan | Build | Reason |
|---|---|---|
| Alignment keypoints: landmark-derived first, detector second ([03](03_AI_ARCHITECTURE.md) §4) | **Detector (YuNet) keypoints first**, landmark-derived keypoints as the fallback | SFace and OpenCV's reference alignment use YuNet's 5-point convention. MediaPipe's nose-tip index sits lower on turned faces and reduced same-person similarity in testing (0.79 vs 0.93 on a 21°-yaw face). |
| Alembic migration `0001_initial` ([08](08_DATABASE_SCHEMA.md) §5) | `Base.metadata.create_all` + DDL for the audit triggers, plus a `_schema_revision` table recording `0001_initial` | There is a single initial schema. Add Alembic at the first schema change. |
| Schema columns ([08](08_DATABASE_SCHEMA.md)) | Added `user_id` to `face_observations`/`expression_results` (ownership checks and per-user deletion), `result_json` to result tables (the exact DTO shown to the user), `expires_at` to `analysis_sessions`, and an internal `_app_flags` table (the audit-purge permission checked by the trigger) | Traceability and deletion without joins |
| KEK only in the OS keystore ([10](10_SECURITY_ARCHITECTURE.md) §4) | `security.keystore: os` (default) **or** `env`: the key comes from `HEALTHVISION_KEK`, as an explicit opt-in for containers and CI | Headless servers and containers have no OS keystore. There is still never a plaintext-file fallback, and recognition is disabled when no key is available. |
| Breached-password check against a top-10k list | A small bundled list plus the 12-character minimum | A full list is a V2 task |
| Rate limiting via middleware | Per-endpoint checks (`api/deps.py`, `RecognitionService`) using one in-process limiter | Same behaviour, simpler |
| Lockout state persisted | In memory (resets on restart) | V1 single-process. Persist it in V2. |
| Occlusion via landmark visibility | MediaPipe returns no per-point visibility. Region visibility = the fraction of each region's landmarks inside the image | Detects faces cut off by the frame edge. Hand or mask occlusion is **not** reliably detected (added to the limitations). |

## 3. Privacy fix found during the build

ONNX Runtime ≥ 1.2x ships **usage telemetry** that tries to contact `mobile.events.data.microsoft.com`. It was observed while the tests ran. It sends runtime metadata, not images, but it contradicts NFR-1 ("nothing leaves the device"). `healthvision/__init__.py` sets `ORT_DISABLE_TELEMETRY=1` before any import, and the FER+ adapter also calls `onnxruntime.disable_telemetry_events()`. The full test suite was re-run with an egress monitor and made no outbound connections.

## 4. Stability fix found during the build

MediaPipe's `FaceLandmarker.__del__` can deadlock if Python garbage-collects it after the app has shut down. All engines now have `close()`, and `Container.close()` releases them explicitly.

## 5. What the build verified (on the build machine; not a validation)

These checks used public-domain sample photos fetched by `tools/fetch_test_fixtures.py`. They show that the pipeline mechanics work. They are **not** accuracy, fairness or latency claims ([13](13_MODEL_VALIDATION.md)).

- 170 cm / 65 kg returns BMI 22.49, Normal range (WHO adult).
- A two-person photo is stopped with MULTIPLE_FACES, and no expression is produced.
- An enrolled person verified against a different photo of the same person returned MATCH. A different person returned NO_MATCH. Both decisions are labelled demo-uncalibrated.
- Revoking recognition consent crypto-shreds the templates and blocks verification.
- `pytest`: 99 tests (unit, contract, integration, wording lint). A Playwright run of the full UI journey passed with a simulated camera.
