# 09 — Privacy Architecture

Covers brief §25–26, §28, §50, §54–56. Face recognition creates biometric data; privacy is a first-class component, not a UI afterthought.

## 1. Principles → mechanisms

| Principle | Mechanism in HealthVision AI |
|---|---|
| Data minimization | No raw images stored; no landmarks stored; no probe embeddings stored; only derived results + hashes |
| Purpose limitation | Three separate consent purposes; each service checks only its own purpose; templates used only for the owner's verification |
| Explicit consent | Opt-in ALLOW/DECLINE per purpose; no pre-ticked boxes; consent recorded with notice hash + policy version |
| Limited retention | Per-table `expires_at` + RetentionService ([07](07_DATA_ARCHITECTURE.md) §5) |
| Access control | Users see only their own records; templates readable only by TemplateStore; admin cannot view templates or other users' results in V1 |
| Encryption | Templates AES-256-GCM envelope-encrypted; KEK in OS keystore; optional full-DB encryption via SQLCipher (V2) |
| Audit logging | Consent changes, enrollment, recognition attempts, deletions, admin access ([10](10_SECURITY_ARCHITECTURE.md) §6) |
| Revocation | Any consent revocable from Privacy page; takes effect immediately |
| Deletion | Revocation-triggered deletion; "Delete all my data"; crypto-shredding for templates |
| Local/edge processing | All inference on device; backend bound to 127.0.0.1; no cloud dependency ([02](02_SYSTEM_ARCHITECTURE.md)) |

## 2. Consent modes (brief §56)

| Purpose | Gates | Default | Independent? |
|---|---|---|---|
| `BMI` | `/bmi/calculate`, storing BMI records | not granted | Yes |
| `FACE_ANALYSIS` | `/face/detect`, `/face/expression` | not granted | Yes |
| `RECOGNITION` | `/face/enroll`, `/face/verify`, template storage | not granted | Yes |
| `GALLERY_MEMBERSHIP` (future) | inclusion in a 1:N gallery | not granted | Yes |

No purpose implies another. Valid example state: BMI = YES, Expression analysis = YES, Recognition = NO → BMI + expression fully usable; recognition page shows notice + ALLOW/DECLINE only.

Implementation: `ConsentService.require(purpose, user_id)` is a FastAPI dependency on each endpoint *and* is called again inside the service (defense in depth). Returns the current consent row (for the snapshot) or raises `ConsentRequired(purpose)`.

## 3. Diagram 6 — Consent pipeline

```
               ┌────────────────────────────┐
 First use ──► │ Privacy notice (general)   │  policy_version, data uses, retention, rights
               └─────────────┬──────────────┘
                             ▼
     ┌──────────────── per-purpose prompt ────────────────┐
     │  BMI  [ALLOW] [DECLINE]                              │
     │  Facial expression analysis  [ALLOW] [DECLINE]       │
     │  (Recognition is asked only on the Recognition page) │
     └──────────────────────────┬──────────────────────────┘
                                ▼
                POST /consent {purpose, decision, policy_version, notice_sha256}
                                ▼
            ConsentService.record()  → user_consents (append-only)
                                ▼
                     AuditService CONSENT_CHANGE
                                ▼
               ┌────────────────────────────────────┐
               │ Feature gate checks on every call  │ ── not GRANTED → 403 CONSENT_REQUIRED
               └────────────────────────────────────┘

 Revocation:
 Privacy page [REVOKE] → POST /consent {purpose, decision: REVOKE}
     → new REVOKED row → DeletionOrchestrator(purpose)
         RECOGNITION: enrollment REVOKED + templates crypto-shredded
         FACE_ANALYSIS: delete expression_results + face_observations (if delete_on_revoke)
         BMI: delete bmi_records (if delete_on_revoke)
     → audit CONSENT_CHANGE + TEMPLATE_DELETION / DATA_DELETION
     → future calls blocked immediately
```

Policy version change: when `privacy.policy_version` in config increases, existing GRANTED consents remain recorded but the UI re-prompts; services treat consents with an older **major** policy version as not granted.

## 4. Consent record (brief §25)

Stored per row: `consent_status`, `purpose`, `timestamp`, `policy_version`, `revoked_at` (revocation status), plus `notice_text_sha256` (proves exactly what was shown) and `supersedes_consent_id` (history chain).

## 5. Privacy UI (brief §55)

### Recognition notice (exact text, shown before enrollment/verification)
```
Facial recognition uses biometric information to verify or identify an
enrolled person.

• Purpose: verify that you are the person who enrolled on this device.
• What is stored: an encrypted face template (a list of numbers), not your photo.
• How long: until you revoke this permission or delete your data.
• Liveness detection is not implemented in this version.
• You can keep using BMI and expression analysis without allowing this.

                       [ ALLOW ]     [ DECLINE ]
Policy version privacy-1.0
```

### Privacy page
- Table: Purpose · Status · Since · Policy version · [Revoke]/[Allow]
- Enrollment: Active since … · model SFace 2021dec · [Delete my face template]
- Retention summary per data type
- [Export my data (JSON, no biometric templates)]
- [Delete all my data] (confirm dialog listing what will be deleted)

## 6. Data subject capabilities

| Capability | V1 |
|---|---|
| Access (view own results/history) | Yes |
| Export | Yes (JSON, non-biometric) |
| Rectification | BMI records: delete & recalculate |
| Erasure | Yes (per purpose, per enrollment, all data) |
| Withdraw consent | Yes, immediate |
| Object to automated decisions | No automated decisions with legal effect are made in V1; recognition is user-initiated self-verification |

## 7. Regulatory considerations (for production — not legal advice)

The architecture is designed to make compliance achievable; it is not itself a compliance claim. Before production, legal review should cover, depending on deployment jurisdiction: EU/UK GDPR Art. 9 (biometric data for unique identification = special category; explicit consent), DPIA requirement; EU AI Act (emotion-recognition restrictions in workplace/education contexts; biometric categorisation prohibitions; transparency duties); Illinois BIPA (written release, retention schedule, no sale); Texas CUBI, Washington biometric law; India DPDP Act 2023; HIPAA only if deployed by a covered entity. **Product teams must not deploy expression estimation in workplace or educational settings in the EU without legal review.**

## 8. What the system will not do (privacy)

- No silent enrollment; no background capture; no continuous camera upload.
- No face search of arbitrary images; no stranger identification.
- No sending of face data to third parties or cloud in V1.
- No indefinite biometric storage.
- No use of templates for any purpose other than the owner's verification.
