"""DecisionEngine unit tests (docs/03 §5)."""
import yaml

from conftest import ROOT
from healthvision_server.config.settings import Settings
from healthvision_server.services import decision_engine as DE

S = Settings.model_validate(yaml.safe_load((ROOT / "config" / "server.example.yaml").read_text()))
E, FD = S.expression, S.face_detection


def probs(**kw):
    base = {k: 0.0 for k in ["neutral", "happiness", "surprise", "sadness", "anger", "disgust", "fear", "contempt"]}
    base.update(kw)
    return base


def expr(p, quality="GOOD", face_state="ONE_FACE", stop=None):
    return DE.expression(p, face_state=face_state, quality=quality, stop_reason=stop, cfg=E, config_version="t")


def test_high_confidence():
    d = expr(probs(happiness=0.93, neutral=0.05, surprise=0.02))
    assert d.status == "ESTIMATED" and d.label == "HAPPY" and d.band == "HIGH"
    assert d.trace.rule_id == "expression.v1" and d.trace.thresholds["high"] == 0.85


def test_moderate_confidence():
    d = expr(probs(happiness=0.72, neutral=0.28))
    assert d.status == "ESTIMATED" and d.band == "MODERATE"


def test_low_confidence_uncertain():
    d = expr(probs(happiness=0.5, neutral=0.3, sadness=0.2))
    assert d.status == "UNCERTAIN" and d.label is None and "LOW_CONFIDENCE" in d.trace.reasons


def test_small_margin_uncertain():
    d = expr(probs(happiness=0.5, neutral=0.5))
    assert d.status == "UNCERTAIN" and "SMALL_MARGIN" in d.trace.reasons


def test_acceptable_quality_caps_band():
    d = expr(probs(happiness=0.95, neutral=0.05), quality="ACCEPTABLE")
    assert d.band == "MODERATE" and "BAND_CAPPED_BY_ACCEPTABLE_QUALITY" in d.trace.reasons


def test_contempt_excluded_and_renormalized():
    d = expr(probs(happiness=0.6, contempt=0.3, neutral=0.1))
    assert d.status == "ESTIMATED"
    assert abs(sum(d.probabilities.values()) - 1) < 1e-3
    assert "CONTEMPT" not in d.probabilities


def test_excluded_mass_forces_uncertain():
    d = expr(probs(contempt=0.7, happiness=0.3))
    assert d.status == "UNCERTAIN" and "EXCLUDED_MASS_TOO_HIGH" in d.trace.reasons


def test_not_available_states():
    assert expr(None, face_state="NO_FACE").status == "NOT_AVAILABLE"
    assert expr(probs(happiness=1.0), face_state="MULTIPLE_FACES").status == "NOT_AVAILABLE"
    assert expr(probs(happiness=1.0), quality="POOR").status == "NOT_AVAILABLE"
    assert expr(probs(happiness=1.0), stop="ALIGNMENT_FAILED").not_available_reason == "ALIGNMENT_FAILED"
    assert expr(None).not_available_reason == "MODEL_UNAVAILABLE"


def test_face_count_rules():
    assert DE.face_count([], FD, "t")[0] == "NO_FACE"
    assert DE.face_count([0.7], FD, "t")[0] == "NO_FACE"          # below detection threshold
    assert DE.face_count([0.95], FD, "t")[0] == "ONE_FACE"
    assert DE.face_count([0.95, 0.9], FD, "t")[0] == "MULTIPLE_FACES"
    assert DE.face_count([0.95, 0.65], FD, "t")[0] == "MULTIPLE_FACES"  # weaker 2nd face still blocks
    assert DE.face_count([0.95, 0.55], FD, "t")[0] == "ONE_FACE"


def test_recognition_rule():
    assert DE.recognition(0.5, 0.4, 0.3, "demo_uncalibrated", "t", 3)[0] == "MATCH"
    assert DE.recognition(0.35, 0.4, 0.3, "demo_uncalibrated", "t", 3)[0] == "UNCERTAIN"
    assert DE.recognition(0.1, 0.4, 0.3, "demo_uncalibrated", "t", 3)[0] == "NO_MATCH"
    d, tr = DE.recognition(0.4, 0.4, 0.3, "calibration_file", "t", 1)
    assert d == "MATCH" and tr.threshold_source == "calibration_file" and tr.reasons == []
    assert "DEMO_UNCALIBRATED" in DE.recognition(0.9, 0.4, 0.3, "demo_uncalibrated", "t", 1)[1].reasons
