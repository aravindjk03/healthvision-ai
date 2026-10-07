# 12 — Testing Strategy

Covers brief §68 and the FR IDs in [01](01_PRODUCT_REQUIREMENTS.md). Model *quality* evaluation lives in [13](13_MODEL_VALIDATION.md); this document covers software correctness.

## 1. Test pyramid

| Level | Tool | Scope | Runs |
|---|---|---|---|
| Unit | pytest, hypothesis, Vitest | BMI math, DecisionEngine, quality metrics, crypto, consent logic, wording | every commit |
| Contract | pytest | Each engine adapter satisfies `engines/base.py` contract on fixture images | every commit |
| Integration | pytest + FastAPI TestClient + temp SQLite | Endpoints → services → real models (CPU) → DB | every commit (models cached in CI) |
| E2E | Playwright (Chromium, fake camera via `--use-file-for-fake-video-capture`) | User journeys, demo script | nightly + before demo |
| Security | bandit, pip-audit, custom tests | §6 | every commit |
| Performance | `tools/benchmark_latency.py` | Latency per stage | on demand; before demo |

Coverage gate: ≥ 90 % lines on `services/`, `domain/`, `storage/`; ≥ 80 % overall backend.

## 2. Test matrices

### 2.1 BMI
| Case | Input | Expected |
|---|---|---|
| Valid metric | 170 cm, 65 kg | VALID, 22.49, NORMAL |
| Valid imperial | 5 ft 7 in, 143.3 lb | VALID, ≈ 22.44 (computed), category per table |
| Metres | 1.70 m, 65 kg | identical to 170 cm |
| Zero height / weight | 0 | INVALID_INPUT, HEIGHT_NOT_POSITIVE / WEIGHT_NOT_POSITIVE |
| Negative | −170 | INVALID_INPUT |
| Non-numeric / NaN / Inf | "abc", NaN | INVALID_INPUT, *_NOT_NUMERIC |
| Out of range | 300 cm, 1000 kg | INVALID_INPUT, *_OUT_OF_RANGE |
| Boundaries | BMI 18.4999 / 18.5 / 24.9999 / 25.0 / 29.9999 / 30 / 35 / 40 | correct half-open categories |
| Adult category | age 30 | VALID |
| Unsupported pediatric | age 12 | NOT_APPLICABLE, category null, pediatric message |
| Age absent | — | VALID + "assume adult" note |
| Plausibility | 200 cm, 20 kg | VALID + warning |
| Property | random valid kg, m | `bmi == kg/m²`; increasing in kg; decreasing in m |
| Reference switch | WHO_ASIAN_2004 | action-point labels appear |

### 2.2 Face pipeline
Fixture set `tests/fixtures/faces/` — **only consented images or synthetic/licensed images** (e.g., generated faces with licence permitting testing; team-member photos with written consent). Each fixture has a JSON sidecar with expected state.

| Case | Expected |
|---|---|
| No face (landscape, blank wall) | NO_FACE, expression NOT_AVAILABLE |
| One face frontal, good light | ONE_FACE, quality GOOD |
| Multiple faces (2, 3, one small in background) | MULTIPLE_FACES, nothing else computed |
| Blur (Gaussian σ = 3, motion blur) | quality POOR (blur), RETAKE |
| Dark image (mean Y < 40) | POOR (brightness) |
| Over-exposed | POOR (brightness) |
| Side profile (yaw ≥ 45°) | POOR (pose) |
| Occlusion (hand over mouth, mask) | POOR or ACCEPTABLE (occlusion) — never ESTIMATED HIGH |
| Glasses (clear / sunglasses) | clear: proceeds; sunglasses: occlusion flagged |
| Different distances (face 60 px, 150 px, 400 px) | <112 px → POOR (face size) |
| Face partially out of frame | visibility check fails |
| EXIF-rotated JPEG | detected correctly after orientation |
| Corrupt / truncated JPEG | 400 IMAGE_DECODE_FAILED |
| PNG with alpha | handled |
| Oversized / pixel bomb | 400 IMAGE_TOO_LARGE before full decode |
| Non-image file renamed .jpg | 400 UNSUPPORTED_MEDIA |

### 2.3 Expression
| Case | Expected |
|---|---|
| Clear smile | ESTIMATED HAPPY (fixture labelled by ≥ 2 annotators) |
| Neutral | ESTIMATED NEUTRAL or UNCERTAIN (never another class with HIGH) |
| Ambiguous | UNCERTAIN accepted |
| Poor image | NOT_AVAILABLE |
| DecisionEngine unit table | probabilities → states at/around each threshold (0.849/0.85, 0.599/0.60, margin 0.149/0.15), excluded-mass rule, ACCEPTABLE caps band |
| Class config | removing a class from `classes` removes it from outputs; mapping change respected |
| Wording | observation/note strings exactly per 01 §6 |

### 2.4 Recognition
| Case | Expected |
|---|---|
| Correct identity | MATCH (on consented fixture pairs) |
| Wrong identity (other enrolled person's image) | NO_MATCH |
| Unknown face (never enrolled) | NO_MATCH |
| Borderline similarity (mocked embedder) | UNCERTAIN for scores in [T_nomatch, T_match) |
| No consent | 403 CONSENT_REQUIRED, no event other than audit DENIED |
| No enrollment | NOT_PERFORMED: NO_ENROLLMENT |
| Revoked enrollment | after revoke → NOT_PERFORMED/403; templates rows gone; wrapped_dek unrecoverable |
| Re-enroll | old enrollment REVOKED, templates replaced atomically |
| Inconsistent enrollment frames (two people) | 409 ENROLLMENT_INCONSISTENT |
| Model change | templates STALE → TEMPLATE_MODEL_MISMATCH |
| Uncalibrated | `demo_uncalibrated: true` in API, UI banner, report |
| Rate limit | 6th verify in a minute → 429; 10 consecutive NO_MATCH → 423 |
| Spoof attempt | **N/A in V1** — test asserts `liveness = NOT_PERFORMED` and disclaimer present. When liveness exists (V2): printed photo / screen replay → NOT_PERFORMED (PRESENTATION_ATTACK_SUSPECTED) |
| Identification | 403 FEATURE_DISABLED |
| Template never in response | schema scan over every route's response model |

### 2.5 Consent & privacy
- Parametrized test over the route table: every route tagged with a consent purpose returns 403 without it and succeeds with it.
- Independence: granting BMI does not grant FACE_ANALYSIS/RECOGNITION (all 8 combinations).
- Revocation deletion effects for each purpose; audit entries present; no biometric content in audit details.
- Retention: freeze time (`time-machine`), advance past `expires_at`, run purge → rows gone, RETENTION_PURGE audited.
- Delete all my data: everything removed except audit + consent history; user tombstoned.
- Export excludes templates.

### 2.6 Security
- Ownership isolation: user B gets 404 for user A's analysis/report/history.
- CSRF required on POST/DELETE.
- Session expiry idle/absolute.
- Audit chain verification detects a manually altered row.
- Model hash mismatch disables model, BMI still works.
- Config threshold change produces new `config_version` and CONFIG_CHANGE.
- Log scan: run full E2E, grep logs for base64 image signatures / float vectors of length 128 → none.

### 2.7 Traceability
For each result type, assert presence and correctness of: input hash, timestamp, model version(s), config_version, thresholds, decision, consent snapshot.

## 3. Engine contract tests
Run for every registered adapter (default + alternates):
- returns bbox within image bounds; scores in [0,1]; deterministic on same input; thread-safe (parallel 8 calls equal results); `info()` matches registry.

## 4. E2E journeys (Playwright)
1. First run → admin setup → login.
2. Consent BMI + Face; decline Recognition → BMI 170/65 → 22.49 → capture smiling fixture → HAPPY estimate → dashboard has no identity panel content → report PDF generated and contains no image.
3. Grant Recognition → enroll (3 frames) → verify → MATCH (demo-uncalibrated banner visible) → revoke → verify blocked.
4. Multiple-face fixture → message shown, no expression.
5. History shows the sessions; retention notice visible.

## 5. Fixture governance
- No scraped images of real people. Store fixture provenance + consent/licence in `tests/fixtures/PROVENANCE.md`.
- Fixtures containing real faces are stored in the repo only if consent allows; otherwise in a private fixture bucket fetched in CI with access control.

## 6. Non-functional checks
- Offline test: run E2E with network disabled (after model fetch) → passes.
- Startup without keystore → recognition disabled, other features OK.
- Windows + macOS + Ubuntu CI matrix for backend unit/integration.

## 7. Wording lint
`tests/wording_lint/test_forbidden_terms.py` scans frontend `src/`, report templates, API message catalog and docs for forbidden phrases from [01](01_PRODUCT_REQUIREMENTS.md) §6 (allow-list for the "never do" sections of docs) and asserts the mandatory notes exist in dashboard and report templates.
