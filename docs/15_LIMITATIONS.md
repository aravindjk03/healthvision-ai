# 15 — Limitations

Covers brief §45, §59–60, §67, §75. This document is the **single register of known limitations** for HealthVision AI V1. Each limitation is repeated wherever it matters: in the UI, the report, `/model-info` and the webinar. It is not repeated in marketing copy only. Its "never do" sections are allow-listed by the wording lint ([12](12_TESTING_STRATEGY.md) §7) because they quote forbidden phrases in order to forbid them.

## 1. Summary

| # | Limitation | Where the user sees it |
|---|---|---|
| L1 | A facial expression is not an internal emotion | Expression card note, dashboard footer, report |
| L2 | BMI is a screening measure with known limits; adult categories do not apply to children | BMI card limitation, pediatric message, report |
| L3 | Liveness / anti-spoofing is **not implemented** in V1 | Recognition page banner, identity panel, report |
| L4 | Recognition thresholds are **demo-uncalibrated** | "Demo mode" banner on every recognition result, report |
| L5 | No model and no fairness property has been validated locally | `/model-info` ("Not locally validated", "Fairness: not yet evaluated"), Settings → About |
| L6 | Some candidate models have research-only licences | Registry `license_status`; admin view |
| L7 | Brief sections 1–12 were not supplied | README, [04](04_BMI_ARCHITECTURE.md), readiness gate G10 |
| L8 | Prototype engineering limits (single device, no backups, no liveness, CPU-only) | [14](14_PRODUCTION_ROADMAP.md) §6 |

## 2. Facial expression is not internal emotion (brief §45)

The expression engine classifies the **visible configuration of the face** in one still image. It does not and cannot measure what a person feels. Factors that break the link between a visible expression and an internal state:

| Factor | Effect |
|---|---|
| Posed vs. spontaneous expressions | People smile for cameras. FER+ training data over-represents posed expressions |
| Social display rules & culture | When and how strongly expressions are shown varies across cultures and settings |
| Masking / suppression | People routinely hide or perform expressions |
| Context missing | One frame has no situation, speech, body posture or history |
| Individual differences | Resting facial features can look like an expression (for example, "resting" faces read as SAD or ANGRY) |
| Neurodiversity & medical conditions | Autism, facial paralysis (for example, Bell's palsy), Parkinson's, stroke, botulinum toxin and other factors change facial movement |
| Same expression, different meanings | A smile can signal embarrassment, politeness or discomfort |
| Image conditions | Lighting, pose, occlusion (glasses, masks, beards, hands, head coverings) and resolution change the predictions |
| Training-data limits | Low-resolution grayscale web images, small DISGUSTED/FEARFUL classes, labels from annotators who judged what they *saw*, not what was felt |
| Demographic skew | Expression models can perform differently across skin tones, ages and genders. **Not yet measured** for this system (L5) |

Consequences in the product:
- Output wording is always "Facial expression estimate: {Class}". Confidence is labelled "model confidence (not a probability of emotion)" ([03](03_AI_ARCHITECTURE.md) §5.1).
- Low confidence or a small top-2 margin returns **UNCERTAIN** instead of forcing a label.
- No mood tracking, no mental-health inference, no use for hiring, education, workplace monitoring, lie detection or law enforcement. The EU AI Act restricts emotion recognition in workplace and education settings ([09](09_PRIVACY_ARCHITECTURE.md) §7).

## 3. BMI limitations (brief §59)

- BMI = weight / height². It is a **population screening measure**, not a diagnosis, and not a measure of body fat or health.
- It does not distinguish muscle from fat, or capture fat distribution (waist circumference, visceral fat). It may misclassify athletes, older adults, people with low muscle mass, pregnant people, and people with amputations or oedema.
- The relationship between BMI and health risk differs between populations. `WHO_ASIAN_2004` action points exist for that reason, and the selected reference is always displayed.
- **Pediatric rule:** under `bmi.adult_min_age` (18) the value is shown greyed and the status is `NOT_APPLICABLE`. Adult categories are **never** applied to children. BMI-for-age percentiles are not provided in V1 ([04](04_BMI_ARCHITECTURE.md) §6).
- If age is not provided, an adult is assumed and the UI says "Categories assume an adult (18+)."
- Accuracy depends on what the user enters. Values are self-reported and not measured by the system.

## 4. No liveness in V1 (brief §24)

- `NotImplementedLivenessEngine` returns `NOT_PERFORMED` on every enrollment and verification.
- **Verification can be fooled by a printed photo, a phone or tablet screen, a video replay or a mask.**
- Face verification is therefore a **demonstration feature for an already-authenticated user**. It is not an authentication method, an access-control mechanism or evidence of identity ([10](10_SECURITY_ARCHITECTURE.md) §2).
- Required text: "Liveness detection is not implemented in this version. Verification can be fooled by photos or screens. Do not use for security decisions."

## 5. Recognition thresholds are demo-uncalibrated

- V1 ships **without** `models/calibration/sface_v1.json`. Decisions use `recognition.demo_uncalibrated_thresholds` (0.40 / 0.30 cosine), which are placeholders and not measured operating points.
- FAR and FRR at these thresholds are **unknown** for this pipeline, these cameras and these users.
- Every result carries `threshold_source: demo_uncalibrated` and `demo_uncalibrated: true`, and the UI and report show "Demo mode — recognition threshold not calibrated on validation data".
- Thresholds do not transfer between models. Changing the embedding model marks templates `STALE` ([06](06_FACE_RECOGNITION_ARCHITECTURE.md) §3).
- SFace is less accurate than large ArcFace-class models. It was chosen for its licence and CPU cost ([03](03_AI_ARCHITECTURE.md) §1).
- 1:N identification is disabled (`403 FEATURE_DISABLED`).

## 6. Models and fairness not yet validated locally

| Model | Local accuracy | Fairness | Calibration | Latency |
|---|---|---|---|---|
| YuNet | NOT VALIDATED | NOT EVALUATED | n/a | NOT MEASURED |
| MediaPipe Face Landmarker | NOT VALIDATED | NOT EVALUATED | n/a | NOT MEASURED |
| FER+ ONNX | NOT VALIDATED | NOT EVALUATED | T = 1.0 (default) | NOT MEASURED |
| SFace | NOT VALIDATED | NOT EVALUATED | UNCALIBRATED | NOT MEASURED |
| Liveness | NOT IMPLEMENTED | — | — | — |

- Vendor-reported numbers (WIDER FACE, FER+ test, LFW) come from other data and other pipelines. They are shown only as "vendor-reported" and never as HealthVision accuracy.
- Known risks that have not been measured yet: lower detector recall on small or angled faces, and on darker skin in poor lighting; expression skew from FER+ training demographics; recognition FAR/FRR differences across skin tone, age and gender ([13](13_MODEL_VALIDATION.md) §5).
- Until [13](13_MODEL_VALIDATION.md) is run: "Fairness: not yet evaluated" is displayed, and **no fairness claim** is made.
- Disparities found later are recorded in §11 of this document. Thresholds are **never** adjusted per demographic group without anyone being told.

## 7. Licence caveats (brief §67)

| Item | Status |
|---|---|
| YuNet (MIT), FER+ ONNX (MIT), SFace (Apache-2.0), MediaPipe Face Landmarker (Apache-2.0) | `APPROVED` defaults |
| **InsightFace model weights** (for example, `buffalo_l`, ArcFace R100, 2d106 landmarks) | Code is MIT but the **pretrained weights are for non-commercial research only** → `REVIEW_REQUIRED`, not loadable by default |
| **AffectNet-trained models** (for example, HSEmotion) | AffectNet dataset terms restrict commercial use → `REVIEW_REQUIRED` |
| Public validation datasets (WIDER FACE, RAF-DB, AffectNet, LFW, RFW…) | Research licences. Results may be used internally to evaluate models, but not to train a commercial model without a licence |
| Licences in general | Code licence ≠ weights licence ≠ training-data terms. All three are reviewed before a model is `APPROVED`. This is not legal advice |

## 8. Gap left by the missing brief sections 1–12

The planning brief started at §13. Sections 1–12 (product introduction and BMI specifics) were **not supplied**. As a result:
- The BMI design ([04](04_BMI_ARCHITECTURE.md)) was reconstructed from §35, §58–60, §68, §70, §73 and WHO adult practice. Reference choice, age handling, units and wording **must be reconciled** with the original §1–12 before implementation.
- Product goals, target users, deployment setting and any stated health claims in §1–12 may add requirements or constraints that this plan does not cover.
- Readiness-gate item **G10** ([14](14_PRODUCTION_ROADMAP.md) §6) stays NOT_MET until that reconciliation is done.

## 9. Other prototype limitations

- Single device, local accounts only. No backups. Templates cannot be decrypted on another machine (by design).
- CPU baseline. Latency is reported only from measurement. No latency promise is made.
- Still-image analysis only. There is no temporal smoothing (V2), so a single blink or mid-speech frame can change the expression estimate.
- English UI only.
- The wording lint catches listed phrases only. It does not replace human review of copy.
- Security assumes the OS account and device are not compromised ([10](10_SECURITY_ARCHITECTURE.md) §1).

## 10. The NEVER list (brief §60)

> Reconstructed from the brief requirements cited throughout docs 01–13. The original brief text is not in this repository. If the original §60 differs, the stricter rule applies.

HealthVision AI must **never**:

1. Present BMI, landmarks, expression or recognition as a **medical diagnosis**, or infer disease, disease risk or a health condition from a face.
2. Produce a combined **"health score"** or any invented health metric that merges BMI, expression and identity.
3. Claim a facial expression **is** an emotion ("Person is happy"), or infer mood, mental health, personality, honesty, intelligence or attractiveness.
4. Apply **adult BMI categories to children**.
5. Infer **age, gender, ethnicity or other protected attributes** from the face.
6. **Enroll a face silently**, capture in the background or upload continuously without the user acting.
7. Run recognition **without separate, explicit recognition consent**, or treat BMI/expression consent as recognition consent.
8. Offer **public face search**, identify strangers or search arbitrary uploaded photos for identities.
9. Store **raw face images** by default, store probe embeddings, or return, log, export or report **templates**.
10. Keep biometric data **indefinitely**, or after consent is revoked.
11. Claim **liveness / anti-spoofing** or "secure biometric login" while liveness is not implemented and validated.
12. Use a **hard-coded or uncalibrated threshold** without labelling it as such. Never adjust thresholds per demographic group without telling anyone.
13. Show **invented numbers**: accuracy, fairness or latency figures that were not measured ([13](13_MODEL_VALIDATION.md)), or "100 % accurate" claims.
14. Show recognition **similarity as "% certainty"** or "% accurate".
15. Analyse expression or recognise anyone when **multiple faces** are detected, or force a label when the result is UNCERTAIN.
16. Send face data to a **cloud or third party** in V1.
17. Load a model whose **licence** is not approved, or whose SHA-256 does not match.
18. Use outputs for **employment, education, insurance, credit, law-enforcement or access-control decisions**.

## 11. Disparity & incident register

Empty in V1 (no validation has been run). The format for entries added by [13](13_MODEL_VALIDATION.md) runs:

| Date | Model@version | Metric | Subgroup(s) | Value (CI, n) | Flag rule | Decision & owner |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |
