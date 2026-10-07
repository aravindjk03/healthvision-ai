import math

import pytest

from healthvision.config import load_config
from healthvision.domain import BmiStatus
from healthvision.services.bmi import BmiService


@pytest.fixture(scope="module")
def svc():
    return BmiService(load_config())


def test_demo_values(svc):
    r = svc.calculate(170, "cm", 65, "kg")
    assert r.status == BmiStatus.VALID
    assert r.bmi_display == "22.49"
    assert r.category_code == "NORMAL"
    assert r.trace.config_version


def test_metres_equal_cm(svc):
    assert svc.calculate(1.70, "m", 65, "kg").bmi == pytest.approx(svc.calculate(170, "cm", 65, "kg").bmi)


def test_imperial(svc):
    r = svc.calculate(5, "ft_in", 143.3, "lb", height_inches=7)
    expected = (143.3 * 0.45359237) / (67 * 0.0254) ** 2
    assert r.bmi == pytest.approx(expected)


@pytest.mark.parametrize("h,w,code", [
    (0, 65, "HEIGHT_NOT_POSITIVE"), (-170, 65, "HEIGHT_NOT_POSITIVE"), (170, 0, "WEIGHT_NOT_POSITIVE"),
    ("abc", 65, "HEIGHT_NOT_NUMERIC"), (float("nan"), 65, "HEIGHT_NOT_NUMERIC"), (None, 65, "HEIGHT_REQUIRED"),
    (300, 65, "HEIGHT_OUT_OF_RANGE"), (170, 1000, "WEIGHT_OUT_OF_RANGE"),
])
def test_invalid(svc, h, w, code):
    r = svc.calculate(h, "cm", w, "kg")
    assert r.status == BmiStatus.INVALID_INPUT
    assert code in [e.code for e in r.errors]
    assert r.bmi is None


@pytest.mark.parametrize("bmi,code", [
    (18.4999, "UNDERWEIGHT"), (18.5, "NORMAL"), (24.9999, "NORMAL"), (25.0, "OVERWEIGHT"),
    (29.9999, "OVERWEIGHT"), (30.0, "OBESE_I"), (35.0, "OBESE_II"), (40.0, "OBESE_III"),
])
def test_boundaries(svc, bmi, code):
    assert svc.classify(bmi, "WHO_ADULT_2000")["code"] == code


def test_pediatric_not_applicable(svc):
    r = svc.calculate(150, "cm", 40, "kg", age_years=12)
    assert r.status == BmiStatus.NOT_APPLICABLE
    assert r.category_code is None
    assert any("under 18" in n for n in r.notes)


def test_adult_with_age(svc):
    r = svc.calculate(170, "cm", 65, "kg", age_years=30)
    assert r.status == BmiStatus.VALID and not any("assume" in n for n in r.notes)


def test_plausibility_warning(svc):
    assert svc.calculate(200, "cm", 20, "kg").warnings


def test_invalid_unit(svc):
    assert svc.calculate(170, "inch", 65, "kg").status == BmiStatus.INVALID_INPUT


@pytest.mark.parametrize("kg,m", [(50, 1.5), (80, 1.8), (120.5, 1.93), (45.2, 1.55)])
def test_formula_and_monotonic(svc, kg, m):
    r = svc.calculate(m, "m", kg, "kg")
    assert math.isclose(r.bmi, kg / m ** 2)
    assert svc.calculate(m, "m", kg + 1, "kg").bmi > r.bmi
    assert svc.calculate(m + 0.01, "m", kg, "kg").bmi < r.bmi
