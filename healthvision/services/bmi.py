"""BMI service — Model A, a deterministic calculation (docs/04)."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import yaml

from healthvision.config import Config
from healthvision.domain import BmiStatus, DecisionTrace, new_id, utcnow

REFERENCES = yaml.safe_load((Path(__file__).resolve().parent.parent / "bmi_references.yaml").read_text())

HEIGHT_UNITS = ("cm", "m", "ft_in")
WEIGHT_UNITS = ("kg", "lb")
SEX_VALUES = ("female", "male", "unspecified")
LB_TO_KG = Decimal("0.45359237")
INCH_TO_M = Decimal("0.0254")

LIMITATION = (
    "BMI is a screening measure and does not constitute a medical diagnosis. It does not distinguish "
    "fat from muscle mass and does not account for body-fat distribution."
)
PEDIATRIC_MESSAGE = (
    "Adult BMI categories do not apply under 18. Pediatric assessment uses BMI-for-age percentiles "
    "(WHO/CDC growth references), which this version does not provide."
)
ASSUME_ADULT_NOTE = "Categories assume an adult (18+)."


@dataclass
class BmiError:
    field: str
    code: str
    message: str


@dataclass
class BmiResult:
    status: BmiStatus
    record_id: str = field(default_factory=new_id)
    timestamp: str = field(default_factory=utcnow)
    bmi: float | None = None
    bmi_display: str | None = None
    category_code: str | None = None
    category_label: str | None = None
    calculation: str | None = None
    reference: dict[str, str] | None = None
    normalized: dict[str, float] | None = None
    inputs: dict[str, Any] | None = None
    input_sha256: str | None = None
    errors: list[BmiError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    limitation: str = LIMITATION
    trace: DecisionTrace | None = None


def _to_decimal(value: Any, name: str, errors: list[BmiError]) -> Decimal | None:
    if value is None or value == "":
        errors.append(BmiError(name, f"{name.upper()}_REQUIRED", f"{name.capitalize()} is required."))
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(BmiError(name, f"{name.upper()}_NOT_NUMERIC", f"{name.capitalize()} must be a number."))
        return None
    if not math.isfinite(number):
        errors.append(BmiError(name, f"{name.upper()}_NOT_NUMERIC", f"{name.capitalize()} must be a number."))
        return None
    if number <= 0:
        errors.append(BmiError(name, f"{name.upper()}_NOT_POSITIVE", f"{name.capitalize()} must be greater than zero."))
        return None
    return Decimal(str(number))


def _round(value: float, places: str) -> str:
    return str(Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


class BmiService:
    def __init__(self, config: Config):
        self.config = config
        self.cfg = config["bmi"]

    def classify(self, bmi: float, reference_code: str) -> dict[str, Any]:
        ref = REFERENCES[reference_code]
        for cat in ref["categories"]:
            lower_ok = cat["lower"] is None or bmi >= cat["lower"]
            upper_ok = cat["upper"] is None or bmi < cat["upper"]
            if lower_ok and upper_ok:
                return cat
        raise ValueError(f"BMI {bmi} not covered by reference {reference_code}")

    def calculate(
        self,
        height: Any,
        height_unit: str,
        weight: Any,
        weight_unit: str,
        age_years: Any = None,
        sex: str | None = None,
        height_inches: Any = None,
    ) -> BmiResult:
        errors: list[BmiError] = []
        inputs = {"height": height, "height_unit": height_unit, "height_inches": height_inches,
                  "weight": weight, "weight_unit": weight_unit, "age_years": age_years, "sex": sex}

        if height_unit not in HEIGHT_UNITS:
            errors.append(BmiError("height", "UNIT_INVALID", "Unsupported height unit."))
        if weight_unit not in WEIGHT_UNITS:
            errors.append(BmiError("weight", "UNIT_INVALID", "Unsupported weight unit."))

        h = _to_decimal(height, "height", errors)
        w = _to_decimal(weight, "weight", errors)

        height_m = weight_kg = None
        if h is not None and height_unit in HEIGHT_UNITS:
            if height_unit == "cm":
                height_m = h / 100
            elif height_unit == "m":
                height_m = h
            else:
                inches = Decimal("0")
                if height_inches not in (None, ""):
                    try:
                        inches = Decimal(str(float(height_inches)))
                    except (TypeError, ValueError):
                        errors.append(BmiError("height", "HEIGHT_NOT_NUMERIC", "Inches must be a number."))
                    if inches < 0 or inches >= 12:
                        errors.append(BmiError("height", "HEIGHT_OUT_OF_RANGE", "Inches must be between 0 and 11.9."))
                height_m = (h * 12 + inches) * INCH_TO_M
        if w is not None and weight_unit in WEIGHT_UNITS:
            weight_kg = w if weight_unit == "kg" else w * LB_TO_KG

        if height_m is not None:
            cm = float(height_m * 100)
            if not self.cfg["height_cm"]["min"] <= cm <= self.cfg["height_cm"]["max"]:
                errors.append(BmiError("height", "HEIGHT_OUT_OF_RANGE",
                                       f"Height must be between {self.cfg['height_cm']['min']} and {self.cfg['height_cm']['max']} cm."))
        if weight_kg is not None:
            kg = float(weight_kg)
            if not self.cfg["weight_kg"]["min"] <= kg <= self.cfg["weight_kg"]["max"]:
                errors.append(BmiError("weight", "WEIGHT_OUT_OF_RANGE",
                                       f"Weight must be between {self.cfg['weight_kg']['min']} and {self.cfg['weight_kg']['max']} kg."))

        age: int | None = None
        if age_years not in (None, ""):
            try:
                age_f = float(age_years)
                if not age_f.is_integer() or not 0 <= age_f <= 120:
                    raise ValueError
                age = int(age_f)
            except (TypeError, ValueError):
                errors.append(BmiError("age", "AGE_INVALID", "Age must be a whole number between 0 and 120."))
        if sex not in (None, "") and sex not in SEX_VALUES:
            errors.append(BmiError("sex", "SEX_INVALID", "Unsupported value for sex."))

        if errors:
            return BmiResult(status=BmiStatus.INVALID_INPUT, errors=errors, inputs=inputs)

        assert height_m is not None and weight_kg is not None
        hm, wk = float(height_m), float(weight_kg)
        bmi = wk / (hm * hm)
        reference_code = self.cfg["reference"]
        ref = REFERENCES[reference_code]
        canonical = json.dumps({"height_m": hm, "weight_kg": wk, "age": age, "sex": sex}, sort_keys=True)
        result = BmiResult(
            status=BmiStatus.VALID,
            bmi=bmi,
            bmi_display=_round(bmi, "0.01"),
            calculation=f"{_round(wk, '0.1')} kg ÷ ({_round(hm, '0.01')} m)² = {_round(bmi, '0.01')} kg/m²",
            reference={"code": reference_code, "citation": ref["citation"], "short": ref["short"], "version": ref["version"]},
            normalized={"height_m": hm, "weight_kg": wk},
            inputs=inputs,
            input_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        )

        reasons: list[str] = []
        if age is not None and age < self.cfg["adult_min_age"]:
            result.status = BmiStatus.NOT_APPLICABLE
            result.notes.append(PEDIATRIC_MESSAGE)
            reasons.append("age below adult_min_age")
        else:
            cat = self.classify(bmi, reference_code)
            result.category_code = cat["code"]
            result.category_label = cat["label"]
            for ap in ref.get("action_points", []):
                if bmi >= ap["value"]:
                    result.notes.append(ap["label"])
            if age is None:
                result.notes.append(ASSUME_ADULT_NOTE)

        plaus = self.cfg["plausibility_warning"]
        if not plaus["bmi_min"] <= bmi <= plaus["bmi_max"]:
            result.warnings.append("This BMI is outside the usual range. Please check the entered values.")

        result.trace = DecisionTrace(
            rule_id="bmi.v1",
            inputs={"height_m": hm, "weight_kg": wk, "age": age},
            thresholds={"adult_min_age": self.cfg["adult_min_age"], "reference": reference_code},
            threshold_source="config",
            config_version=self.config.version,
            outcome=str(result.status) + (f":{result.category_code}" if result.category_code else ""),
            reasons=reasons,
        )
        return result
