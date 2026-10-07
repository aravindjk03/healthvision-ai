# 04 — BMI Architecture

> Source note: brief sections 1–12 were not supplied. This design follows the BMI
> requirements stated elsewhere in the brief (§35, §58, §59, §60, §68, §70, §73)
> and WHO adult BMI practice. Review before implementation.

## 1. Principle

BMI is **Model A — a mathematical calculation**. No ML. The product statement is:

> "AI automates BMI calculation and presents the result using the selected reference."

## 2. Diagram 2 — BMI pipeline

```
Height (value, unit) + Weight (value, unit) + optional Age + optional Sex
   │
   ▼
ConsentService.require(BMI)  ── not granted → 403 CONSENT_REQUIRED
   │
   ▼
Validation  ── fail → status INVALID_INPUT (field errors)
   │   • numeric, finite, > 0
   │   • unit in allowed set
   │   • within configured min/max after normalization
   │   • age integer 0–120 if present
   ▼
Unit normalization → height_m (float64), weight_kg (float64)
   │
   ▼
BMI formula: bmi = weight_kg / height_m²
   │
   ▼
Applicability ── age < adult_min_age → status NOT_APPLICABLE (category = null)
   │
   ▼
Reference classification (configured table) → category
   │
   ▼
Plausibility flag (bmi outside [10, 80]) → warning "Please check the entered values"
   │
   ▼
BmiResult (status VALID) + DecisionTrace → persisted bmi_record
```

## 3. Units and normalization

| Input unit | Conversion | Notes |
|---|---|---|
| `cm` | m = cm / 100 | default |
| `m` | m | |
| `ft_in` | m = (ft × 12 + in) × 0.0254 | `in` may be decimal, 0 ≤ in < 12 |
| `kg` | kg | default |
| `lb` | kg = lb × 0.45359237 | exact definition |

- Use `decimal.Decimal` for conversion, then `float` for the formula; store `height_cm` and `weight_kg` normalized with original input preserved in `input_json`.
- Display rounding: BMI to 2 decimals (`ROUND_HALF_UP`), height to 1 decimal cm, weight to 1 decimal kg.
- Example (demo): 170 cm, 65 kg → 65 / 1.70² = 65 / 2.89 = **22.49** → Normal range.

## 4. Validation rules

| Field | Rule | Error code |
|---|---|---|
| height | present, numeric, finite | `HEIGHT_REQUIRED`, `HEIGHT_NOT_NUMERIC` |
| height | > 0 | `HEIGHT_NOT_POSITIVE` |
| height | 50 ≤ cm ≤ 272 (config) | `HEIGHT_OUT_OF_RANGE` |
| weight | present, numeric, finite | `WEIGHT_REQUIRED`, `WEIGHT_NOT_NUMERIC` |
| weight | > 0 | `WEIGHT_NOT_POSITIVE` |
| weight | 2 ≤ kg ≤ 635 (config) | `WEIGHT_OUT_OF_RANGE` |
| age | optional; integer 0–120 | `AGE_INVALID` |
| sex | optional; `female`/`male`/`unspecified` | `SEX_INVALID` |
| units | in allowed enum | `UNIT_INVALID` |

Any validation error → `status = INVALID_INPUT`, `bmi = null`, no record persisted except an `analysis_session` step status.

## 5. Reference tables (configurable, versioned)

Stored as data in `backend/healthvision/domain/bmi_references.yaml` (not code), each with citation and version.

### `WHO_ADULT_2000` (default)
Citation: WHO. *Obesity: preventing and managing the global epidemic.* WHO Technical Report Series 894, 2000.

| BMI (kg/m²) | Category label (display) |
|---|---|
| < 18.5 | Underweight |
| 18.5 – < 25.0 | Normal range |
| 25.0 – < 30.0 | Overweight (pre-obese) |
| 30.0 – < 35.0 | Obese class I |
| 35.0 – < 40.0 | Obese class II |
| ≥ 40.0 | Obese class III |

Boundaries use half-open intervals `[lower, upper)` on the **unrounded** value.

### `WHO_ASIAN_2004` (optional, selectable by admin)
Citation: WHO Expert Consultation. *Appropriate body-mass index for Asian populations and its implications for policy and intervention strategies.* Lancet 2004;363:157–163. Public-health action points 23.0 and 27.5 kg/m² displayed as additional reference lines; category labels remain the WHO labels plus "Increased risk (action point 23)" / "High risk (action point 27.5)". Only enabled when an administrator selects it; label it clearly as a population-level public-health reference.

## 6. Pediatric rule (brief §60: never use adult categories for children)

- `age < bmi.adult_min_age (18)` → compute BMI value for transparency **but** `status = NOT_APPLICABLE`, `category = null`, message:
  "Adult BMI categories do not apply under 18. Pediatric assessment uses BMI-for-age percentiles (WHO/CDC growth references), which this version does not provide."
- Age not provided → classify as adult and display "Categories assume an adult (18+)." Store `age_provided = false`.
- V2 option: WHO 2007 BMI-for-age z-scores (5–19 y) — requires LMS tables, separate validation.

## 7. Three-state BMI result (brief §58)

| Status | When | UI |
|---|---|---|
| `VALID` | Inputs valid, adult or age unknown | BMI, category, calculation, reference, limitation |
| `INVALID_INPUT` | Any validation failure | Field-level errors, no BMI |
| `NOT_APPLICABLE` | Under adult_min_age | BMI number greyed + pediatric message, no category |

## 8. Output contract

```json
{
  "status": "VALID",
  "bmi": 22.491349480968857,
  "bmi_display": "22.49",
  "category_code": "NORMAL",
  "category_label": "Normal range",
  "calculation": "65.0 kg ÷ (1.70 m)² = 22.49 kg/m²",
  "reference": {"code": "WHO_ADULT_2000", "citation": "WHO TRS 894, 2000", "version": "1"},
  "normalized": {"height_m": 1.70, "weight_kg": 65.0},
  "warnings": [],
  "limitation": "BMI is a screening measure and does not constitute a medical diagnosis. It does not distinguish fat from muscle mass and does not account for body-fat distribution.",
  "trace": {"rule_id": "bmi.v1", "config_version": "1-3fa9c21b0d4e", "reference": "WHO_ADULT_2000"}
}
```

## 9. Limitations to display (BMI page + report)

- BMI is a screening measure, not a diagnosis.
- Does not distinguish muscle from fat; may misclassify athletes, older adults, pregnant people.
- Population cut-offs may differ by ethnicity; the selected reference is shown.
- Adult categories are not valid for under-18s.

## 10. Test hooks

See [12](12_TESTING_STRATEGY.md) §2.1: valid, invalid, zero, negative, unit conversion, boundary values (18.4999/18.5/24.9999/25.0/29.9999/30.0), pediatric, plausibility, property test `bmi(kg, m) == kg / m**2` and monotonicity.
