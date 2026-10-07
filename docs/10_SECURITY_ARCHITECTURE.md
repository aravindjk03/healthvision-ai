# 10 — Security Architecture

Covers brief §24, §46–48, §65.

## 1. Threat model (V1, local device)

| Asset | Threats | Primary controls |
|---|---|---|
| Face templates | Theft of DB file; misuse for tracking; replay | Envelope encryption, KEK in OS keystore, no API export, crypto-shred |
| Recognition decision | Presentation attack (photo/screen/video); brute force; threshold tampering | Disclosed absence of liveness; rate limit + lockout; config hash audited; calibration file hash recorded |
| Other users' records | Horizontal privilege escalation | Row-level ownership checks in repositories; tests |
| Model files | Tampering / substitution | SHA-256 verification against registry; `MODEL_INTEGRITY_FAILURE` |
| API | Malicious uploads (decompression bombs, polyglots), CSRF, XSS | Input validation, size/pixel limits, MIME sniffing, CSRF tokens, CSP |
| Audit log | Tampering to hide access | Append-only triggers + hash chain + verification command |
| Logs | Leakage of biometric/PII | Structured logging allow-list; `log_images` must be false |

Out of scope for V1 (documented): a compromised OS/admin account on the device; physical camera attacks; side channels.

## 2. Authentication

- Local accounts: username + password (argon2id, `time_cost=3, memory_cost=64 MiB, parallelism=2`), min length 12, breached-password check against a bundled top-10k list.
- First run: setup wizard creates the ADMINISTRATOR account (no default credentials).
- Session: random 256-bit token in `HttpOnly; SameSite=Strict; Path=/` cookie (`Secure` when TLS enabled), stored hashed in `auth_sessions`; idle timeout 30 min, absolute 8 h (config).
- CSRF: double-submit token (`X-CSRF-Token` header) on all state-changing requests.
- Login rate limit 5/min/username + exponential back-off; audit `LOGIN_FAILURE`.
- Face verification is **not** an authentication method in V1 (no liveness) — it is a demonstration feature performed by an already-authenticated user.

## 3. Authorization & role model (brief §47)

| Permission | USER | ADMINISTRATOR | PROGRAM_ADMIN (V3) | AUDITOR (V2/V3) |
|---|---|---|---|---|
| Own BMI/face/recognition/history/reports | ✔ | ✔ (own) | — | — |
| Other users' results | ✘ | ✘ (V1) | Aggregated, consented only | ✘ |
| Any face template content | ✘ | ✘ | ✘ | ✘ |
| Enrollment metadata of others | ✘ | ✔ (count/status only, audited) | ✘ | ✔ (read-only) |
| Manage users (create/disable) | ✘ | ✔ | — | — |
| View config & thresholds | ✘ | ✔ | — | ✔ |
| Change config | file-system only + restart (audited at startup) | | | |
| Model registry view | ✔ (public info via /model-info) | ✔ | ✔ | ✔ |
| Export audit log | ✘ | ✔ | — | ✔ |
| Identification (1:N) | ✘ | gallery admin (future) | — | — |

Enforcement: FastAPI dependency `require_role(...)` at router; repository methods take `actor` and filter by `user_id` (no unscoped query methods exposed to services handling user data). Every admin access to another user's data writes `ADMIN_ACCESS`.

## 4. Secure storage & encryption

- KEK: 256-bit random, generated at first run, stored via `keyring` (`service="healthvision-ai", username="template-kek-v1"`). If the keystore is unavailable, recognition features are disabled (never fall back to a plaintext key file).
- Templates: per-template DEK, AES-256-GCM, AAD binds to template/user/model; key rotation command re-wraps DEKs under new KEK (`kek_id`).
- DB file permissions: owner-only (0600 / Windows ACL current user).
- V2: SQLCipher for full DB encryption.
- Secure deletion: crypto-shred + row delete + periodic `VACUUM`; report PDFs overwritten once then unlinked (best-effort on SSD — documented limitation; crypto-shredding is the real guarantee for templates).

## 5. Input validation & API hardening

- Pydantic models with strict types, ranges and enums on every endpoint; unknown fields rejected.
- Images: MIME sniff (magic bytes) ∈ {JPEG, PNG}; ≤ 10 MB; decoded pixel count ≤ 4096×4096 checked from header *before* full decode (Pillow `MAX_IMAGE_PIXELS`); reject animated/multi-frame; strip metadata in memory.
- Backend binds `127.0.0.1`; CORS disabled (same-origin static frontend).
- Security headers: `Content-Security-Policy: default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Permissions-Policy: camera=(self)`.
- Errors: uniform JSON (`{"error": {"code", "message", "request_id"}}`); no stack traces to client.
- Dependency pinning with hashes; `pip-audit` and `npm audit` in CI.

## 6. Audit logging (brief §48)

| Event type | Logged when | Details (non-biometric) |
|---|---|---|
| FACE_ENROLLMENT | enroll success/failure | enrollment_id, template_count, model_version, quality grades |
| CONSENT_CHANGE | grant/decline/revoke | purpose, new status, policy_version |
| RECOGNITION_ATTEMPT | every verify (and identify, future) | event_id, decision, threshold_source, liveness_status (NO similarity vector, NO embedding) |
| TEMPLATE_DELETION | revoke, re-enroll, retention, user delete | enrollment_id, count, reason |
| DATA_DELETION | user/purpose deletions | tables + counts |
| ADMIN_ACCESS | admin views user metadata / audit export | target user id, scope |
| REPORT_GENERATION | report created | report_id, include_recognition |
| CONFIG_CHANGE | startup detects new config hash | old/new config_version |
| MODEL_CHANGE | startup detects model version/hash change | model_id, old/new |
| MODEL_INTEGRITY_FAILURE | SHA mismatch | model_id |
| LOGIN_SUCCESS / LOGIN_FAILURE / LOGOUT | auth | username hash on failure |
| RATE_LIMITED / LOCKOUT | limits hit | endpoint |
| RETENTION_PURGE | each purge run | counts per table |

Integrity: each entry stores `prev_hash` and `entry_hash`; `python -m healthvision.tools.verify_audit` recomputes the chain and reports the first break. **Do not log unnecessary biometric content**: logging layer has an allow-list of fields; any key named like `embedding|template|image|landmarks|probs_raw` is rejected by a unit test.

## 7. Rate limiting (recognition APIs)

| Endpoint | Limit (config) | On exceed |
|---|---|---|
| POST /face/verify | 5/min, 30/hour per user | 429 + audit RATE_LIMITED |
| POST /face/enroll | 3/hour per user | 429 |
| POST /face/identify (future) | per-role, per-gallery | 429 |
| POST /auth/login | 5/min per username and per client | 429 + back-off |
| POST /face/expression, /face/detect | 60/min per user | 429 |

In-process token bucket (V1); Redis-backed in V3.

## 8. Model file security

- `tools/fetch_models.py` downloads only from URLs in the registry over HTTPS, verifies SHA-256 (pinned in registry after first verified fetch, committed to repo), stores read-only.
- At startup: re-verify hashes; mismatch disables the model.
- ONNX models loaded with ORT default options; no custom ops; no pickle-based formats (`.pt`/`.pkl`) permitted at runtime.

## 9. Session management

See §2. Logout deletes server-side session; session tokens rotated on login and on role change; concurrent sessions per user limited to 3.

## 10. Secure development checklist (CI)

- `ruff`, `mypy --strict` on `services/`, `engines/base.py`, `storage/`
- `bandit` (no high findings), `pip-audit`, `npm audit --audit-level=high`
- Wording lint ([12](12_TESTING_STRATEGY.md) §7)
- Tests for: ownership isolation, consent gating on every protected endpoint (parametrized over the route table), template never in any response (response-schema scan), audit chain validity.
