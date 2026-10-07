# 08 — Database Schema

SQLite 3 (WAL, `foreign_keys=ON`) via SQLAlchemy 2.x + Alembic. Types chosen to port cleanly to PostgreSQL in V3. IDs are UUIDv7 strings (time-ordered). Timestamps are UTC ISO-8601 strings in SQLite (`TIMESTAMPTZ` in Postgres). JSON columns are `TEXT` with JSON validation in the repository layer (`JSONB` in Postgres).

Conceptual entities from brief §29 map 1:1 below; additional columns support traceability, security and retention.

## 1. Enumerations

| Enum | Values |
|---|---|
| `user_status` | ACTIVE, DISABLED, DELETED |
| `role` | USER, ADMINISTRATOR, PROGRAM_ADMINISTRATOR (future), AUDITOR (future) |
| `consent_purpose` | BMI, FACE_ANALYSIS, RECOGNITION, GALLERY_MEMBERSHIP (future) |
| `consent_status` | GRANTED, DECLINED, REVOKED |
| `bmi_status` | VALID, INVALID_INPUT, NOT_APPLICABLE |
| `face_state` | NO_FACE, ONE_FACE, MULTIPLE_FACES |
| `quality_grade` | GOOD, ACCEPTABLE, POOR |
| `expression_status` | ESTIMATED, UNCERTAIN, NOT_AVAILABLE |
| `expression_band` | HIGH, MODERATE |
| `recognition_mode` | VERIFY, IDENTIFY |
| `recognition_decision` | MATCH, NO_MATCH, UNCERTAIN, NOT_PERFORMED |
| `liveness_status` | NOT_PERFORMED, LIVE, SPOOF, UNCERTAIN |
| `threshold_source` | config, calibration_file, demo_uncalibrated |
| `enrollment_status` | ACTIVE, REVOKED, STALE |

## 2. Tables

### users
| Column | Type | Constraints |
|---|---|---|
| user_id | TEXT | PK |
| display_name | TEXT | NOT NULL, 1–80 chars |
| username | TEXT | NOT NULL UNIQUE (lowercase) |
| password_hash | TEXT | NOT NULL (argon2id) |
| role | TEXT | NOT NULL DEFAULT 'USER' |
| status | TEXT | NOT NULL DEFAULT 'ACTIVE' |
| created_at | TEXT | NOT NULL |
| updated_at | TEXT | NOT NULL |
| deleted_at | TEXT | NULL |

### user_consents  (brief: CONSENT)
Append-only: a change inserts a new row; the latest row per (user, purpose) is current.

| Column | Type | Constraints |
|---|---|---|
| consent_id | TEXT | PK |
| user_id | TEXT | FK users, NOT NULL |
| purpose | TEXT | NOT NULL (consent_purpose) |
| consent_status | TEXT | NOT NULL (consent_status) |
| timestamp | TEXT | NOT NULL |
| policy_version | TEXT | NOT NULL (e.g. "privacy-1.0") |
| notice_text_sha256 | TEXT | NOT NULL — hash of the exact notice shown |
| revoked_at | TEXT | NULL (set on the REVOKED row) |
| supersedes_consent_id | TEXT | NULL FK user_consents |
| channel | TEXT | NOT NULL DEFAULT 'ui' |

Index: `(user_id, purpose, timestamp DESC)`.

### analysis_sessions  (brief: INSPECTION/ANALYSIS SESSIONS)
| Column | Type | Constraints |
|---|---|---|
| session_id | TEXT | PK |
| user_id | TEXT | FK users NOT NULL |
| started_at | TEXT | NOT NULL |
| completed_at | TEXT | NULL |
| config_version | TEXT | NOT NULL FK config_versions |
| latency_json | TEXT | NULL (03 §9) |
| consent_snapshot_json | TEXT | NOT NULL |
| status | TEXT | NOT NULL (OPEN, COMPLETED, ABANDONED) |

### bmi_records  (brief: BMI RECORD)
| Column | Type | Constraints |
|---|---|---|
| record_id | TEXT | PK |
| session_id | TEXT | FK analysis_sessions NOT NULL |
| user_id | TEXT | FK users NOT NULL |
| height | REAL | NOT NULL — normalized cm |
| weight | REAL | NOT NULL — normalized kg |
| input_json | TEXT | NOT NULL — original values & units, age, sex |
| age_years | INTEGER | NULL |
| bmi | REAL | NULL (null only if INVALID_INPUT; such rows normally not persisted) |
| status | TEXT | NOT NULL (bmi_status) |
| category | TEXT | NULL (category code) |
| reference | TEXT | NOT NULL (reference code + version) |
| input_sha256 | TEXT | NOT NULL |
| config_version | TEXT | NOT NULL |
| trace_json | TEXT | NOT NULL |
| timestamp | TEXT | NOT NULL |
| expires_at | TEXT | NOT NULL — computed from retention |

### face_observations
| Column | Type | Constraints |
|---|---|---|
| observation_id | TEXT | PK |
| session_id | TEXT | FK NOT NULL |
| purpose | TEXT | NOT NULL (FACE_ANALYSIS, ENROLLMENT, VERIFICATION) |
| input_sha256 | TEXT | NOT NULL |
| image_width / image_height | INTEGER | NOT NULL |
| face_count | INTEGER | NOT NULL |
| face_state | TEXT | NOT NULL |
| bboxes_json | TEXT | NOT NULL (bbox + detection_confidence per face) |
| quality_grade | TEXT | NULL (null if stopped before quality) |
| quality_checks_json | TEXT | NULL |
| pose_json | TEXT | NULL |
| models_json | TEXT | NOT NULL (detector, landmark versions) |
| config_version | TEXT | NOT NULL |
| timestamp | TEXT | NOT NULL |
| expires_at | TEXT | NOT NULL |

### expression_results  (brief: EXPRESSION RESULT)
| Column | Type | Constraints |
|---|---|---|
| result_id | TEXT | PK |
| session_id | TEXT | FK NOT NULL |
| observation_id | TEXT | FK face_observations NOT NULL |
| status | TEXT | NOT NULL (expression_status) |
| expression | TEXT | NULL unless ESTIMATED |
| confidence | REAL | NULL |
| confidence_band | TEXT | NULL |
| probabilities_json | TEXT | NULL |
| not_available_reason | TEXT | NULL |
| model_version | TEXT | NOT NULL ("expression.ferplus@onnx-opset8") |
| thresholds_json | TEXT | NOT NULL |
| config_version | TEXT | NOT NULL |
| trace_json | TEXT | NOT NULL |
| timestamp | TEXT | NOT NULL |
| expires_at | TEXT | NOT NULL |

### face_enrollments  (brief: FACE ENROLLMENT)
| Column | Type | Constraints |
|---|---|---|
| enrollment_id | TEXT | PK |
| user_id | TEXT | FK NOT NULL |
| consent_id | TEXT | FK user_consents NOT NULL (the GRANTED row) |
| template_reference | TEXT | NOT NULL — enrollment-level reference used to look up templates (= enrollment_id; kept for brief compatibility) |
| model_version | TEXT | NOT NULL ("embedding.sface@2021dec") |
| embedding_dim | INTEGER | NOT NULL |
| template_count | INTEGER | NOT NULL |
| status | TEXT | NOT NULL (enrollment_status) |
| created_at | TEXT | NOT NULL |
| revoked_at | TEXT | NULL |
| revocation_reason | TEXT | NULL (CONSENT_REVOKED, RE_ENROLLED, USER_DELETED, RETENTION, MODEL_CHANGED) |

Partial unique index: one `ACTIVE` enrollment per user — `UNIQUE(user_id) WHERE status='ACTIVE'`.

### face_templates  (brief: FACE TEMPLATES)
| Column | Type | Constraints |
|---|---|---|
| template_id | TEXT | PK |
| enrollment_id | TEXT | FK face_enrollments ON DELETE CASCADE |
| user_id | TEXT | FK NOT NULL |
| ciphertext | BLOB | NOT NULL |
| nonce | BLOB | NOT NULL (12 bytes) |
| wrapped_dek | BLOB | NOT NULL |
| kek_id | TEXT | NOT NULL (key version) |
| frame_quality_json | TEXT | NOT NULL (grade + blur/pose values only) |
| created_at | TEXT | NOT NULL |
| expires_at | TEXT | NOT NULL |

Access: only `TemplateStore` (repository) may read this table; enforced by module boundary + test.

### recognition_events  (brief: RECOGNITION EVENT)
| Column | Type | Constraints |
|---|---|---|
| event_id | TEXT | PK |
| session_id | TEXT | FK NOT NULL |
| user_id | TEXT | FK NOT NULL — the requester |
| mode | TEXT | NOT NULL (VERIFY / IDENTIFY) |
| claimed_identity | TEXT | NULL — user_id claimed (VERIFY) |
| matched_identity | TEXT | NULL — user_id matched (MATCH only) |
| similarity | REAL | NULL |
| decision | TEXT | NOT NULL (recognition_decision) |
| not_performed_reason | TEXT | NULL |
| liveness_status | TEXT | NOT NULL |
| quality_grade | TEXT | NULL |
| model_version | TEXT | NOT NULL |
| threshold_match | REAL | NULL |
| threshold_no_match | REAL | NULL |
| threshold_source | TEXT | NOT NULL |
| enrollment_id | TEXT | NULL FK |
| input_sha256 | TEXT | NOT NULL |
| config_version | TEXT | NOT NULL |
| consent_snapshot_json | TEXT | NOT NULL |
| trace_json | TEXT | NOT NULL |
| timestamp | TEXT | NOT NULL |
| expires_at | TEXT | NOT NULL |

Index: `(user_id, timestamp DESC)`.

### reports
| Column | Type | Constraints |
|---|---|---|
| report_id | TEXT | PK |
| session_id | TEXT | FK NOT NULL |
| user_id | TEXT | FK NOT NULL |
| include_recognition | INTEGER | NOT NULL (0/1 — user choice) |
| file_path | TEXT | NULL (PDF) |
| file_sha256 | TEXT | NULL |
| report_json | TEXT | NOT NULL (the DTO snapshot) |
| created_at | TEXT | NOT NULL |
| expires_at | TEXT | NOT NULL |

### audit_logs
| Column | Type | Constraints |
|---|---|---|
| audit_id | INTEGER | PK AUTOINCREMENT |
| timestamp | TEXT | NOT NULL |
| actor_user_id | TEXT | NULL (system) |
| actor_role | TEXT | NULL |
| event_type | TEXT | NOT NULL (see 10 §6) |
| target_type | TEXT | NULL |
| target_id | TEXT | NULL |
| outcome | TEXT | NOT NULL (SUCCESS / DENIED / FAILURE) |
| details_json | TEXT | NOT NULL — no biometric content, no images, no embeddings, no passwords |
| prev_hash | TEXT | NOT NULL |
| entry_hash | TEXT | NOT NULL — sha256(prev_hash ‖ canonical row) |

Triggers: `BEFORE UPDATE` and `BEFORE DELETE` raise unless `PRAGMA` app flag set by RetentionService purge (which itself audits). 

### config_versions
| config_version (PK) | schema_version | sha256 | content_json (thresholds only, no secrets) | first_seen_at |

### model_versions
| model_key (PK, "model_id@version") | model_id | version | sha256 | license | license_status | registry_entry_json | first_seen_at | status |

### auth_sessions
| session_token_hash (PK) | user_id | created_at | last_seen_at | expires_at | csrf_token_hash | user_agent_hash |

## 3. Relationships

```
users 1─* user_consents
users 1─* analysis_sessions 1─* {bmi_records, face_observations, expression_results, recognition_events, reports}
face_observations 1─0..1 expression_results
users 1─* face_enrollments 1─* face_templates
face_enrollments *─1 user_consents (granting consent)
recognition_events *─0..1 face_enrollments
```

## 4. Deletion semantics

| Action | Effect |
|---|---|
| Revoke RECOGNITION consent | new REVOKED consent row; enrollment REVOKED; templates crypto-shredded & deleted |
| Revoke FACE_ANALYSIS consent | future face analysis blocked; existing expression results/observations deleted if `privacy.delete_on_revoke = true` (default true) |
| Revoke BMI consent | future BMI blocked; existing bmi_records deleted if `delete_on_revoke` |
| Delete all my data | all rows for user except audit_logs and consent history (legal record; consent rows retained per retention for audit) deleted; report files removed; user status DELETED, PII fields (display_name, username) replaced with tombstone |
| Retention expiry | rows with `expires_at < now` deleted by RetentionService |

## 5. Migrations

- Alembic revision `0001_initial` creates all tables above, indexes, partial unique index, audit triggers.
- Every schema change → new Alembic revision; `config_versions` and `model_versions` populated at startup.
