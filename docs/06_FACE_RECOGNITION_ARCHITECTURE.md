# 06 — Face Recognition Architecture

Covers brief §20–25, §37, §55–58, §60.

## 1. Concepts — never blurred (brief §20)

| Concept | Question | V1 | Endpoint |
|---|---|---|---|
| **Detection** | Where is a face? | Yes | `POST /face/detect` |
| **Recognition** (umbrella) | Producing and comparing biometric templates | — | — |
| **Verification (1:1)** | Is this the *claimed* person (the logged-in user)? | **Yes** | `POST /face/verify` |
| **Identification (1:N)** | Who, among an *authorized enrolled gallery*, is this? | **No** (flag off) | `POST /face/identify` → 403 |

Code-level separation: `FaceDetector` (engine) ≠ `EmbeddingModel` (engine) ≠ `RecognitionService.verify()` ≠ `RecognitionService.identify()`. Identification lives in a separate method guarded by `features.identification_enabled`, a separate consent check (gallery-membership consent per person), an ADMIN-defined gallery, and separate audit event types.

## 2. Diagram 5 — Recognition pipeline

```
Face image
    │
ConsentService.require(RECOGNITION, user)   ── no → 403 CONSENT_REQUIRED
    │
Rate limiter (per user)                      ── exceeded → 429
    │
Face detection (Model B) → ONE_FACE gate
    │
Landmarks (Model C) → face quality gate (stricter profile: ACCEPTABLE minimum, GOOD for enrollment)
    │
Liveness (Model F) — V1: NOT_PERFORMED (recorded, disclaimed)
    │
Alignment → 112×112 RGB crop
    │
Recognition model (Model E: SFace) → embedding (128-D, L2-normalized)
    │
Comparison against the user's own templates (cosine similarity, max over templates)
    │
Similarity score
    │
Calibrated thresholds (T_match, T_nomatch)  — or DEMO-UNCALIBRATED
    │
MATCH / NO MATCH / UNCERTAIN
    │
recognition_event persisted (no embedding of probe stored) + audit
```

## 3. Enrollment (brief §22)

```
USER CONSENT (RECOGNITION, policy vX)          — must be GRANTED, recorded first
     │
Capture face: 1–5 frames (3 recommended; small head movements prompted)
     │
Quality check per frame: overall GOOD required (enrollment profile)
     │
Face detection: ONE_FACE per frame
     │
Alignment
     │
Embedding generation per accepted frame
     │
Intra-consistency check: pairwise cosine ≥ T_match for all accepted frames
     │   (prevents enrolling two different people / bad frames) — else ENROLLMENT_INCONSISTENT
     │
Template = per-frame embeddings (≤ max_templates_per_user), each AES-256-GCM encrypted
     │
Encrypted/protected template storage (face_template rows) + face_enrollment row
     │
Raw frames zeroed & discarded
     │
Audit FACE_ENROLLMENT → "Enrollment complete"
```

- A user has at most one **active** enrollment. Re-enrolling revokes the old one (templates crypto-shredded) inside the same transaction.
- Enrollment records `model_id`, `model_version`, `embedding_dim`. If the embedding model changes, existing templates become `STALE` (cannot be compared across models) and the user is prompted to re-enroll; verification against stale templates returns `NOT_PERFORMED: TEMPLATE_MODEL_MISMATCH`.
- No silent enrollment (brief §60): enrollment is only reachable from the explicit ENROLL button after consent; no other code path writes `face_template`.

## 4. Verification

- Claimed identity = the authenticated user (V1 does not allow claiming someone else's identity).
- Probe embedding compared to **only** that user's active templates. Score = max cosine similarity.
- Probe embedding held in memory only; it is not persisted. `recognition_event` stores similarity, decision, thresholds, versions, quality grade, liveness status.
- Output wording:

| Decision | UI |
|---|---|
| MATCH | "Verified — matches your enrolled identity" |
| NO_MATCH | "Not verified — does not match your enrolled identity" |
| UNCERTAIN | "Uncertain — the result is borderline. Please retry with better lighting, facing the camera." |
| NOT_PERFORMED | reason: NO_CONSENT / NO_ENROLLMENT / QUALITY_REJECTED / MULTIPLE_FACES / NO_FACE / TEMPLATE_MODEL_MISMATCH / RATE_LIMITED |

- Similarity display: "Similarity 0.52 (threshold 0.40, model SFace 2021dec)". Never displayed as "% certainty" or "% accurate".
- After `lockout_after_consecutive_no_match` consecutive NO_MATCH, verification for that user is locked for 15 min and audited.

## 5. Thresholds (brief §23)

- **No universal threshold in code.** Two thresholds, both from calibration:
  - `T_match` (`recognition_threshold`): chosen at the target FAR on the validation set (default target FAR = 0.1 % for demo-grade, policy-set for production).
  - `T_nomatch`: chosen at a target FRR margin (e.g., the similarity below which < 1 % of genuine pairs fall).
  - Scores in `[T_nomatch, T_match)` → UNCERTAIN.
- Calibration file `models/calibration/<model_id>_<version>.json` produced by `tools/calibrate_recognition.py` ([13](13_MODEL_VALIDATION.md) §4):

```json
{
  "model_id": "embedding.sface", "model_version": "2021dec",
  "dataset": {"name": "local-consented-v1", "identities": 0, "genuine_pairs": 0, "impostor_pairs": 0},
  "created_at": "…", "git_commit": "…",
  "target_far": 0.001, "target_frr_floor": 0.01,
  "recognition_threshold": 0.0, "no_match_threshold": 0.0,
  "measured": {"far_at_threshold": 0.0, "frr_at_threshold": 0.0, "eer": 0.0},
  "subgroup_metrics_ref": "reports/validation/sface_v1_subgroups.json"
}
```

- If the calibration file is absent → **DEMO-UNCALIBRATED mode**: uses `recognition.demo_uncalibrated_thresholds`, every result carries `threshold_source: demo_uncalibrated`, UI banner "Demo mode — recognition threshold not calibrated on validation data", report repeats this. The production-readiness gate fails.

## 6. Security of recognition (brief §24)

Presentation attacks: printed photo, phone/tablet screen, video replay, mask.

- **V1: liveness is NOT implemented.** `LivenessEngine` = `NotImplementedLivenessEngine` returning `NOT_PERFORMED`. Recorded on every event. Disclaimer shown on recognition page, dashboard identity panel, and report: *"Liveness detection is not implemented in this version. Verification can be fooled by photos or screens. Do not use for security decisions."*
- The words "anti-spoofing", "secure biometric login", "liveness-checked" must not appear anywhere in V1 UI/docs except to state absence.
- V2 pipeline:
```
Camera → Face detection → Liveness (PAD) → Face embedding → Recognition
```
  PAD candidates evaluated per ISO/IEC 30107-3 (APCER/BPCER). A liveness result of SPOOF → decision NOT_PERFORMED (`PRESENTATION_ATTACK_SUSPECTED`); UNCERTAIN → recognition UNCERTAIN.

Other controls: rate limiting, consecutive-failure lockout, templates encrypted, templates never returned by any API, no export of templates, audit on every attempt.

## 7. Consent dependency (brief §25, §55–56)

- Recognition consent is **separate** from BMI and face-analysis consent. Declining it never blocks BMI/expression.
- Before ALLOW/DECLINE, show: "Facial recognition uses biometric information to verify or identify an enrolled person." plus purpose, retention ("kept until you revoke consent"), liveness disclaimer, and policy version.
- Revocation → `ConsentService.revoke(RECOGNITION)` → in one transaction: mark consent REVOKED, set `face_enrollment.revoked_at`, crypto-shred templates (delete per-template data keys, then delete ciphertext rows), audit `CONSENT_CHANGE` + `TEMPLATE_DELETION`. Any in-flight verify after revocation fails with NO_CONSENT.

## 8. Face Recognition page (brief §37)

```
┌────────────────────────── FACE RECOGNITION ──────────────────────────┐
│ ⚠ Liveness detection is not implemented in this version.            │
│                                                                      │
│ [ VERIFY MY IDENTITY ]          [ ENROLL NEW IDENTITY ]              │
│  Requires an enrollment          Requires recognition consent        │
│                                                                      │
│ (IDENTIFY FROM ENROLLED GALLERY — hidden; future, admin-authorized)  │
└──────────────────────────────────────────────────────────────────────┘
```
Never exposed as a generic public face search. No "upload any photo to find who this is" capability exists in any version.

## 9. Identification (future, V2+) design constraints

- Gallery = explicit, named, admin-created set; each member has an individual GRANTED `GALLERY_MEMBERSHIP` consent.
- Requester must hold a role authorized for that gallery; purpose recorded per request.
- Result returns top-1 only if above `T_match` with a margin over top-2; else UNCERTAIN. Never returns a ranked candidate list to end users.
- Separate rate limits and audit type `IDENTIFICATION_ATTEMPT`.

## 10. Diagram — decision trace example (brief §73)

```
Image → Face detected (ONE_FACE) → Quality accepted (GOOD) → Consent validated (RECOGNITION v1.0, granted 2026-10-07T10:02Z)
 → Liveness NOT_PERFORMED → Embedding generated (SFace 2021dec) → Template comparison (3 templates)
 → Similarity 0.52 (max) → Calibrated threshold 0.40 / no-match 0.30 (calibration sface_v1.json)
 → MATCH ("Verified")
```
