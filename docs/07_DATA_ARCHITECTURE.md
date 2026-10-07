# 07 — Data Architecture

Covers brief §27–28, §54, §74.

## 1. Logical entities (brief §27)

| Entity | Table | Classification | Contains biometric data? |
|---|---|---|---|
| Users | `users` | Personal | No |
| User consents | `user_consents` | Personal / legal record | No |
| Analysis/inspection sessions | `analysis_sessions` | Personal | No |
| BMI records | `bmi_records` | Personal health-adjacent | No |
| Face observations (detection + quality summary) | `face_observations` | Personal, derived | No (no image, no landmarks, no embedding) |
| Expression results | `expression_results` | Sensitive inference | No |
| Face enrollments | `face_enrollments` | Personal | No (metadata only) |
| Face templates | `face_templates` | **Special category — biometric** | **Yes (encrypted)** |
| Recognition events | `recognition_events` | Sensitive | No (similarity score only) |
| Reports | `reports` | Personal | No (no face image) |
| Audit logs | `audit_logs` | Security record | No |
| Config versions | `config_versions` | System | No |
| Model versions | `model_versions` | System | No |
| Auth sessions | `auth_sessions` | Security | No |

## 2. Diagram 7 — Data storage

```
┌───────────────────────────────── data/ (local disk) ─────────────────────────────────┐
│                                                                                      │
│  healthvision.db (SQLite, WAL)                                                       │
│  ┌──────────────┐   ┌───────────────┐   ┌──────────────────┐   ┌─────────────────┐   │
│  │ users        │──<│ user_consents │   │ analysis_sessions│──<│ bmi_records     │   │
│  │              │   └───────────────┘   │  (latency, cfg   │   └─────────────────┘   │
│  │              │──────────────────────<│   version)       │──<│ face_observations│  │
│  │              │                       │                  │──<│ expression_results│ │
│  │              │                       │                  │──<│ recognition_events│ │
│  │              │                       │                  │──<│ reports          │  │
│  │              │──<┌────────────────┐  └──────────────────┘                         │
│  │              │   │face_enrollments│──<┌──────────────────────────────────────┐    │
│  └──────────────┘   └────────────────┘   │ face_templates                        │    │
│                                          │  ciphertext (AES-256-GCM)             │    │
│                                          │  wrapped_dek (per-template data key)  │    │
│                                          └──────────────────────────────────────┘    │
│  audit_logs (append-only, hash-chained)   config_versions   model_versions          │
│                                                                                      │
│  reports/  (generated PDFs, retention-managed)                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
        ▲
        │ Key-encryption key (KEK, 256-bit) — never in DB/disk files
┌───────┴────────────────────────┐
│ OS keystore via `keyring`      │  Windows Credential Manager (DPAPI) /
│ service "healthvision-ai"      │  macOS Keychain / Linux Secret Service
└────────────────────────────────┘

NOT STORED: raw images, video, landmarks, probe embeddings, face crops.
```

## 3. Data flows

### 3.1 BMI
`UI form → POST /bmi/calculate → BmiService → bmi_records (inputs normalized, result, reference, trace)`.

### 3.2 Face analysis
`image bytes (memory) → pipeline → face_observations (face_count, state, bbox, det. confidence, quality grade+checks, pose angles) + expression_results (status, label, confidence, probabilities, trace) → bytes discarded`. Only `input_sha256` remains to prove which input produced the result without retaining it.

### 3.3 Enrollment
`frames (memory) → embeddings (memory) → encrypt → face_templates → frames & plaintext embeddings zeroed`.

### 3.4 Verification
`frame (memory) → probe embedding (memory) → decrypt user's templates (memory) → similarity → recognition_events → all buffers zeroed`.

### 3.5 Report
`analysis_session + linked results → Report DTO → HTML (on demand) / PDF file in data/reports/ → reports row (path, sha256)`.

## 4. Face template storage (brief §28)

- Preferred artifact = **protected template** (embedding), never raw photos.
- Envelope encryption: per-template random 256-bit DEK → AES-256-GCM(embedding bytes, AAD = `template_id|user_id|model_id|model_version`) → DEK wrapped with KEK (AES-KW or AES-GCM) → store `ciphertext, nonce, wrapped_dek`.
- Crypto-shred on delete: overwrite `wrapped_dek` with random bytes, commit, then delete row; run `VACUUM` in the retention job when deletions occurred (SQLite free-page reuse).
- Templates are **never** returned by the API, logged, exported, or included in reports or backups that leave the device.
- Raw images: `features.store_raw_images = false` (V1 fixed). If a future deployment enables it, it must define in config: `raw_image.purpose`, `raw_image.retention_days` (max 30), `raw_image.access_roles`, and deletion job — and startup refuses to enable it without all four.

## 5. Retention (brief §54)

| Data type | Default retention | Configurable | Deletion trigger |
|---|---|---|---|
| BMI records | 365 days | yes | retention job; user "delete all"; account deletion |
| Expression results | 90 days | yes | same |
| Face observations | 90 days (follows expression) | yes | same |
| Recognition events | 90 days | yes | same; enrollment revocation does **not** delete past events (they contain no biometric data) unless user deletes all data |
| Analysis sessions | 365 days (deleted when all children gone) | yes | same |
| Reports (files + rows) | 90 days | yes | same |
| Face templates | until recognition consent revoked, re-enrollment, account deletion, or `template_max_age_days` (default 730) | yes | ConsentService.revoke; RetentionService |
| Raw face images | not retained | V1 fixed | n/a |
| Audit logs | 730 days | yes | RetentionService (audit entry recorded for purge itself) |
| Auth sessions | expire per security config; purged daily | yes | RetentionService |

`RetentionService` runs on startup and every `purge_interval_minutes`; each run writes one `RETENTION_PURGE` audit entry with counts per table (no content). History UI states the retention window.

## 6. Traceability (brief §74)

Every result row carries:

| Field | Meaning |
|---|---|
| `session_id` | Parent analysis session |
| `input_sha256` | Hash of image bytes (face/recognition) or canonical JSON of inputs (BMI) |
| `created_at` | UTC timestamp (ISO-8601, ms) |
| `model_id`, `model_version` | Engine(s) used (detector, landmark, expression/embedding) — JSON `models_json` for multi-model results |
| `config_version` | `<schema>-<sha256[:12]>` of the config file |
| `thresholds_json` | The exact threshold values applied + `threshold_source` |
| `decision` / `status` | Outcome state |
| `trace_json` | Full `DecisionTrace` |
| `consent_snapshot_json` | Consent IDs + statuses + policy versions in force at decision time (where applicable) |

With these, any historical result can be re-explained ("why did it say UNCERTAIN on 7 Oct?") without the original image.

## 7. Backups & export

- V1: no automatic backups. "Export my data" (user) produces a JSON of their non-biometric records (BMI, expression, recognition events, consents) — **excluding templates**.
- Admin backup (manual) copies the DB file; templates remain encrypted under the device KEK, so a backup restored on another machine cannot decrypt templates (by design → users re-enroll).
