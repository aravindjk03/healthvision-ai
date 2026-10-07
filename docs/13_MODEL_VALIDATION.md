# 13 — Model Validation

Covers brief §43–45, §60, §67, §75. **No accuracy, fairness or latency claim may be made from demo images.** Every number shown in UI, reports, or presentations must trace to an evaluation run recorded here.

## 1. Validation framework

```
validation dataset (consented / licensed, documented)
        │
tools/evaluate_<model>.py --dataset <manifest> --model <registry id>
        │
reports/validation/<model_id>_<version>_<date>.json   (metrics, per-subgroup, CIs, git commit)
        │
registry.yaml performance_metrics.local_validated  ← written by the tool, not by hand
        │
docs/model_cards/<model_id>.md  (human summary, limitations)
```

Each run records: dataset name/version/size, subgroup counts, model hash, config_version, code commit, hardware, date, metrics with 95 % bootstrap confidence intervals (1,000 resamples).

### Datasets (to be assembled; licence review required for each)

| Purpose | Candidate sources | Notes |
|---|---|---|
| Detection | WIDER FACE val (research licence); local consented capture set | Local set must include lighting/pose/distance variation |
| Expression | FER+ test, RAF-DB (research), AffectNet val (research licence); local consented posed set | Public sets are research-only — results usable internally, not for training a commercial model without licence |
| Recognition | LFW, CALFW/CPLFW (pose/age), RFW (research); local consented set (≥ 50 identities × ≥ 5 images, multiple sessions) | Local set is the calibration source for thresholds |
| Fairness | Annotated subgroup labels: Monk Skin Tone (MST) 10-point scale (annotated, not inferred), age band, gender presentation (self-reported only), facial hair, glasses, head covering, camera type | Labels collected with consent; never inferred by the system |
| Liveness (V2) | Consented attack set: prints, screens, replays | ISO/IEC 30107-3 protocol |

## 2. Face detector evaluation (Model B)

| Metric | Definition |
|---|---|
| Precision / Recall | IoU ≥ 0.5 matching, at operating threshold |
| AP / PR curve | over thresholds |
| Face-count accuracy | NO/ONE/MULTIPLE state correctness on the local set — **primary product metric** |
| Missed-second-face rate | multi-person images classified ONE_FACE — safety-critical (bystander analysis risk); target ≤ 1 % |
| Performance under lighting/pose | recall per lighting bucket (dark/normal/bright/backlit) and yaw bucket (0–15/15–30/30–45/>45°) |
| Latency | median, p95 |

Threshold tuning: choose `face_detection_threshold` and `min_secondary_face_confidence` to minimize missed-second-face rate subject to NO_FACE false-positive rate ≤ 2 %.

### Quality thresholds
Tune `quality.*` on the local set by correlating each metric with downstream errors (expression accuracy drop, recognition FRR increase). Document chosen cut-offs and the data that justified them.

## 3. Expression evaluation (Model D)

### 3.1 Metrics (brief §43)
- Accuracy, macro-precision, macro-recall, macro-F1
- **Per-class** precision/recall/F1 and support
- Confusion matrix (normalized by true class)
- Coverage vs. accuracy: fraction ESTIMATED vs. accuracy on ESTIMATED (selective-prediction curve) — determines how often UNCERTAIN is returned
- Calibration: Expected Calibration Error (ECE, 15 bins), reliability diagram

### 3.2 Protocol
- Ground truth = consensus of ≥ 2 human annotators labelling **visible expression** (not felt emotion). Disagreements labelled AMBIGUOUS (expected output: UNCERTAIN).
- Evaluate on the product class set after `class_map`.

### 3.3 Threshold & calibration
- Fit temperature `T` on a held-out calibration split (minimize NLL). Store in config `expression.temperature`.
- Choose `high`, `moderate`, `min_top2_margin` so that accuracy on HIGH ≥ target (e.g., 90 %) and on MODERATE ≥ target (e.g., 75 %) — targets set by the product owner and recorded in the validation report. If targets cannot be met, raise thresholds (more UNCERTAIN) rather than lower targets.

## 4. Recognition evaluation (Model E)

### 4.1 Metrics
- **FAR / FMR** (false acceptance) and **FRR / FNMR** (false rejection) at thresholds
- ROC / DET curve; EER; TAR @ FAR = 1e-2, 1e-3, 1e-4
- **UNCERTAIN rate** for genuine and impostor pairs (between thresholds)
- Failure-to-enroll rate (quality rejection)
- Threshold analysis table: threshold → FAR, FRR, UNCERTAIN %

### 4.2 Calibration procedure (`tools/calibrate_recognition.py`)
1. Build genuine pairs (same identity, different sessions) and impostor pairs (all cross-identity, plus look-alike hard negatives where available).
2. Run the **production pipeline** (same detector, quality gate, alignment, model) — not a research shortcut.
3. `T_match` = smallest threshold with FAR ≤ target_far (upper 95 % CI ≤ 2 × target).
4. `T_nomatch` = threshold below which ≤ 1 % of genuine scores fall.
5. If `T_nomatch ≥ T_match`, set `T_nomatch = T_match` (no uncertain zone) and flag it in the report.
6. Write calibration JSON ([06](06_FACE_RECOGNITION_ARCHITECTURE.md) §5) + validation report.
7. Statistical sufficiency: to claim FAR ≤ 1e-3 at 95 % confidence by the rule of three, ≥ 3,000 impostor comparisons with zero false accepts are needed; claims scale accordingly. Report actual comparison counts.

## 5. Bias & fairness validation (brief §44)

Measured **per subgroup** for each model:

| Variation | Annotation | Detector | Expression | Recognition |
|---|---|---|---|---|
| Skin tone | MST 1–10 (grouped 1–3, 4–7, 8–10) | recall | macro-F1, per-class recall | FAR, FRR at global threshold |
| Lighting | dark / normal / bright / backlit | recall | F1 | FRR |
| Age range | 18–29, 30–44, 45–64, 65+ (adults only) | recall | F1 | FAR/FRR |
| Gender presentation | self-reported, where supported | recall | F1 | FAR/FRR |
| Facial hair | none / partial / full | recall | F1 | FRR |
| Glasses | none / clear / tinted | recall | F1 | FRR |
| Head coverings | none / hijab / turban / cap / other | recall | F1 | FRR |
| Camera quality | laptop 720p / 1080p / phone / low-light webcam | recall | F1 | FRR |
| Face angle | yaw buckets | recall | F1 | FRR |

Reporting rules:
- Report each subgroup's metric with CI and **n**; subgroups with n < 30 are reported as "insufficient data", not omitted.
- Disparity metrics: max/min ratio of FRR and FAR across subgroups; max difference in expression macro-F1.
- Flag threshold (initial policy): FAR or FRR ratio > 2.0, or F1 gap > 10 points → documented in [15](15_LIMITATIONS.md) and the model card; the product owner decides mitigation (different model, threshold policy, scope restriction). **Never** silently adjust thresholds per demographic group.
- "Do not claim fairness without measuring it": until this table is complete, UI/model-info shows "Fairness: not yet evaluated".

## 6. Liveness (Model F, V2)
- APCER per attack type, BPCER, ACER per ISO/IEC 30107-3; attack types: print, screen replay, video replay, paper mask.
- Only after this validation may the UI state that liveness is performed — and never as "100 %".

## 7. Latency validation
`tools/benchmark_latency.py --device <name>`: 20 warm-up + 200 timed runs per stage on fixed fixtures; outputs median/p95/max per stage and total, CPU model, RAM, OS, execution provider. Results stored in `reports/benchmarks/`. These are the only latency numbers allowed in docs and slides.

## 8. Re-validation triggers
- Any model version/hash change
- Any change to alignment, quality thresholds or preprocessing
- New deployment hardware class (for latency)
- Every 12 months in production

## 9. Validation status (current)

| Model | Local accuracy | Fairness | Calibration | Latency |
|---|---|---|---|---|
| YuNet | NOT VALIDATED | NOT EVALUATED | n/a | NOT MEASURED |
| MediaPipe landmarks | NOT VALIDATED | NOT EVALUATED | n/a | NOT MEASURED |
| FER+ | NOT VALIDATED | NOT EVALUATED | T = 1.0 (default) | NOT MEASURED |
| SFace | NOT VALIDATED | NOT EVALUATED | UNCALIBRATED (demo thresholds) | NOT MEASURED |
| Liveness | NOT IMPLEMENTED | — | — | — |
