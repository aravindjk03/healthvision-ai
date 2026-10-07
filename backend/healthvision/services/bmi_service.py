"""BMI — Model A, a deterministic calculation (docs/04). No ML."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

import yaml

from ..config.settings import BmiCfg
from ..domain import messages as M
from ..domain.enums import BmiStatus

LB_TO_KG = Decimal("0.45359237")
INCH_TO_M = Decimal("0.0254")
_REF_FILE = Path(__file__).resolve().parents[1] / "domain" / "bmi_references.yaml"


def load_references() -> dict:
    return yaml.safe_load(_REF_FILE.read_text())["references"]


def _num(v: Any) -> Optional[Decimal]:
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _round(x: float, places: str) -> str:
    return str(Decimal(repr(x)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def classify(bmi: float, reference: dict) -> dict:
    for c in reference["categories"]:
        lo, hi = c["lower"], c["upper"]
        if (lo is None or bmi >= lo) and (hi is None or bmi < hi):
            return c
    raise AssertionError("reference table does not cover value")  # pragma: no cover


class BmiService:
    def __init__(self, cfg: BmiCfg, config_version: str):
        self.cfg = cfg
        self.config_version = config_version
        self.refs = load_references()

    def calculate(self, height: dict | None, weight: dict | None, age_years: Any = None, sex: Any = None) -> dict:
        errors: list[dict] = []

        def err(field: str, code: str, msg: str):
            errors.append({"field": field, "code": code, "message": msg})

        # ---- height
        height_m: Optional[Decimal] = None
        h_unit = (height or {}).get("unit", "cm")
        if not height:
            err("height", "HEIGHT_REQUIRED", "Height is required.")
        elif h_unit not in ("cm", "m", "ft_in"):
            err("height", "UNIT_INVALID", "Height unit must be cm, m or ft_in.")
        elif h_unit == "ft_in":
            ft, inch = _num(height.get("feet")), _num(height.get("inches", 0))
            if ft is None or inch is None:
                err("height", "HEIGHT_NOT_NUMERIC", "Height must be a number.")
            elif ft < 0 or inch < 0 or inch >= 12 or (ft * 12 + inch) <= 0:
                err("height", "HEIGHT_NOT_POSITIVE", "Height must be greater than zero (inches 0–11.99).")
            else:
                height_m = (ft * 12 + inch) * INCH_TO_M
        else:
            v = _num(height.get("value"))
            if height.get("value") in (None, ""):
                err("height", "HEIGHT_REQUIRED", "Height is required.")
            elif v is None:
                err("height", "HEIGHT_NOT_NUMERIC", "Height must be a number.")
            elif v <= 0:
                err("height", "HEIGHT_NOT_POSITIVE", "Height must be greater than zero.")
            else:
                height_m = v / 100 if h_unit == "cm" else v
        if height_m is not None:
            cm = float(height_m * 100)
            if not (self.cfg.height_cm.min <= cm <= self.cfg.height_cm.max):
                err("height", "HEIGHT_OUT_OF_RANGE",
                    f"Height must be between {self.cfg.height_cm.min:g} and {self.cfg.height_cm.max:g} cm.")
                height_m = None

        # ---- weight
        weight_kg: Optional[Decimal] = None
        w_unit = (weight or {}).get("unit", "kg")
        if not weight or weight.get("value") in (None, ""):
            err("weight", "WEIGHT_REQUIRED", "Weight is required.")
        elif w_unit not in ("kg", "lb"):
            err("weight", "UNIT_INVALID", "Weight unit must be kg or lb.")
        else:
            v = _num(weight.get("value"))
            if v is None:
                err("weight", "WEIGHT_NOT_NUMERIC", "Weight must be a number.")
            elif v <= 0:
                err("weight", "WEIGHT_NOT_POSITIVE", "Weight must be greater than zero.")
            else:
                weight_kg = v * LB_TO_KG if w_unit == "lb" else v
                if not (self.cfg.weight_kg.min <= float(weight_kg) <= self.cfg.weight_kg.max):
                    err("weight", "WEIGHT_OUT_OF_RANGE",
                        f"Weight must be between {self.cfg.weight_kg.min:g} and {self.cfg.weight_kg.max:g} kg.")
                    weight_kg = None

        # ---- age / sex
        age: Optional[int] = None
        if age_years not in (None, ""):
            a = _num(age_years)
            if a is None or a != a.to_integral_value() or not (0 <= a <= 120):
                err("age_years", "AGE_INVALID", "Age must be a whole number between 0 and 120.")
            else:
                age = int(a)
        sex_val = sex if sex not in (None, "") else "unspecified"
        if sex_val not in ("female", "male", "unspecified"):
            err("sex", "SEX_INVALID", "Sex must be female, male or unspecified.")

        ref_code = self.cfg.reference
        ref = self.refs[ref_code]
        reference = {"code": ref_code, "citation": ref["citation"], "version": ref["version"]}
        if errors:
            return {"status": BmiStatus.INVALID_INPUT.value, "bmi": None, "bmi_display": None, "errors": errors,
                    "reference": reference, "limitation": M.BMI_LIMITATION}

        h, w = float(height_m), float(weight_kg)
        bmi = w / (h * h)
        warnings: list[str] = []
        if not (self.cfg.plausibility_warning.bmi_min <= bmi <= self.cfg.plausibility_warning.bmi_max):
            warnings.append(M.BMI_PLAUSIBILITY)
        if age is None:
            warnings.append(M.BMI_ASSUME_ADULT)

        bmi_display = _round(bmi, "0.01")
        calc = f"{_round(w, '0.1')} kg ÷ ({_round(h, '0.01')} m)² = {bmi_display} kg/m²"
        trace = {"rule_id": "bmi.v1", "config_version": self.config_version, "reference": ref_code,
                 "inputs": {"height_m": h, "weight_kg": w, "age_years": age},
                 "thresholds": {"adult_min_age": self.cfg.adult_min_age,
                                "categories": [[c["code"], c["lower"], c["upper"]] for c in ref["categories"]]}}
        base = {"bmi": bmi, "bmi_display": bmi_display, "calculation": calc, "reference": reference,
                "normalized": {"height_m": round(h, 4), "weight_kg": round(w, 3)}, "warnings": warnings,
                "limitation": M.BMI_LIMITATION, "age_provided": age is not None,
                "action_points": ref.get("action_points", [])}

        if age is not None and age < self.cfg.adult_min_age:
            trace["outcome"] = BmiStatus.NOT_APPLICABLE.value
            return {"status": BmiStatus.NOT_APPLICABLE.value, **base, "category_code": None, "category_label": None,
                    "message": M.BMI_PEDIATRIC, "trace": trace}

        cat = classify(bmi, ref)
        trace["outcome"] = cat["code"]
        return {"status": BmiStatus.VALID.value, **base, "category_code": cat["code"], "category_label": cat["label"],
                "trace": trace}

