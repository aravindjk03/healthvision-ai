"""BMI unit tests (docs/12 §2.1, FR-BMI-1..7)."""
import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from conftest import ROOT
from healthvision.config.settings import BmiCfg
from healthvision.services.bmi_service import BmiService

CFG = BmiCfg.model_validate(yaml.safe_load((ROOT / "config" / "healthvision.example.yaml").read_text())["bmi"])
svc = BmiService(CFG, "test")


def calc(h, w, age=None, sex=None, hu="cm", wu="kg"):
    height = {"value": h, "unit": hu} if hu != "ft_in" else {"feet": h[0], "inches": h[1], "unit": "ft_in"}
    return svc.calculate(height, {"value": w, "unit": wu}, age, sex)


def test_demo_value():
    r = calc(170, 65, 34)
    assert r["status"] == "VALID"
    assert r["bmi_display"] == "22.49"
    assert r["category_code"] == "NORMAL"
    assert r["category_label"] == "Normal range"
    assert r["calculation"] == "65.0 kg ÷ (1.70 m)² = 22.49 kg/m²"
    assert r["reference"]["code"] == "WHO_ADULT_2000"
    assert r["guidance"].startswith("Great")


@pytest.mark.parametrize("bmi,code", [(18.4999, "UNDERWEIGHT"), (18.5, "NORMAL"), (24.9999, "NORMAL"), (25.0, "OVERWEIGHT"),
                                      (29.9999, "OVERWEIGHT"), (30.0, "OBESE_I"), (35.0, "OBESE_II"), (40.0, "OBESE_III")])
def test_boundaries_half_open(bmi, code):
    # height 1 m => BMI == weight
    r = calc(100, bmi, 30)
    assert r["category_code"] == code


def test_units_imperial():
    r = calc((5, 7), 143.3, 30, hu="ft_in", wu="lb")
    assert r["status"] == "VALID"
    assert abs(r["normalized"]["height_m"] - 1.7018) < 1e-4
    assert abs(r["normalized"]["weight_kg"] - 143.3 * 0.45359237) < 1e-3


def test_metres():
    r = svc.calculate({"value": 1.7, "unit": "m"}, {"value": 65, "unit": "kg"}, 40, None)
    assert r["bmi_display"] == "22.49"


@pytest.mark.parametrize("h,w,field,code", [
    (0, 65, "height", "HEIGHT_NOT_POSITIVE"), (-170, 65, "height", "HEIGHT_NOT_POSITIVE"),
    ("abc", 65, "height", "HEIGHT_NOT_NUMERIC"), (170, 0, "weight", "WEIGHT_NOT_POSITIVE"),
    (170, -5, "weight", "WEIGHT_NOT_POSITIVE"), (170, "x", "weight", "WEIGHT_NOT_NUMERIC"),
    (20, 65, "height", "HEIGHT_OUT_OF_RANGE"), (170, 900, "weight", "WEIGHT_OUT_OF_RANGE"),
    ("", 65, "height", "HEIGHT_REQUIRED"), (170, "", "weight", "WEIGHT_REQUIRED"),
    ("nan", 65, "height", "HEIGHT_NOT_NUMERIC"), ("inf", 65, "height", "HEIGHT_NOT_NUMERIC"),
])
def test_invalid(h, w, field, code):
    r = calc(h, w, 30)
    assert r["status"] == "INVALID_INPUT"
    assert r["bmi"] is None
    assert any(e["field"] == field and e["code"] == code for e in r["errors"])


def test_invalid_age_and_sex():
    r = calc(170, 65, 200, "robot")
    codes = {e["code"] for e in r["errors"]}
    assert {"AGE_INVALID", "SEX_INVALID"} <= codes


def test_pediatric_not_applicable():
    r = calc(150, 40, 12)
    assert r["status"] == "NOT_APPLICABLE"
    assert r["category_code"] is None
    assert r["bmi_display"] is not None
    assert "under 18" in r["message"] and "growth charts" in r["message"]


def test_age_missing_assumes_adult():
    r = calc(170, 65)
    assert r["status"] == "VALID"
    assert "Categories assume an adult (18+)." in r["warnings"]
    assert r["age_provided"] is False


def test_plausibility_warning():
    r = calc(100, 9, 30)
    assert "Please double-check the entered values." in r["warnings"]


@given(st.floats(min_value=0.5, max_value=2.72), st.floats(min_value=2, max_value=635))
def test_property_formula(h_m, kg):
    r = svc.calculate({"value": h_m, "unit": "m"}, {"value": kg, "unit": "kg"}, 30, None)
    if r["status"] == "VALID":
        assert abs(r["bmi"] - kg / h_m ** 2) <= 1e-9 * max(1, r["bmi"])


@given(st.floats(min_value=1.0, max_value=2.5), st.floats(min_value=20, max_value=200), st.floats(min_value=0.1, max_value=50))
def test_property_monotonic_in_weight(h_m, kg, delta):
    a = svc.calculate({"value": h_m, "unit": "m"}, {"value": kg, "unit": "kg"}, 30, None)
    b = svc.calculate({"value": h_m, "unit": "m"}, {"value": kg + delta, "unit": "kg"}, 30, None)
    if a["status"] == b["status"] == "VALID":
        assert b["bmi"] > a["bmi"]
