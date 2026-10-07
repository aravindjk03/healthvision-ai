import numpy as np
import pytest

from healthvision.config import load_config
from healthvision.domain import (
    ConfidenceBand, ConsentPurpose, ConsentStatus, ExpressionStatus, FaceDetection, FaceState, QualityGrade,
    RecognitionDecision,
)
from healthvision.services import decision
from healthvision.services.consent import ConsentRequired, ConsentService
from healthvision.services.recognition import decrypt_embedding, encrypt_embedding, shred_enrollment
from healthvision.services.store import AuditLog, DataStore, Enrollment


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def det(score):
    return FaceDetection(bbox=(0, 0, 10, 10), score=score, keypoints5=None)


def test_face_count_states(cfg):
    assert decision.face_count([], cfg)[0] == FaceState.NO_FACE
    assert decision.face_count([det(0.95)], cfg)[0] == FaceState.ONE_FACE
    assert decision.face_count([det(0.95), det(0.9)], cfg)[0] == FaceState.MULTIPLE_FACES
    # a weaker second face above the secondary threshold still blocks analysis (bystander protection)
    assert decision.face_count([det(0.95), det(0.65)], cfg)[0] == FaceState.MULTIPLE_FACES
    assert decision.face_count([det(0.95), det(0.5)], cfg)[0] == FaceState.ONE_FACE
    assert decision.face_count([det(0.7)], cfg)[0] == FaceState.NO_FACE


def probs(happy, neutral, contempt=0.0):
    rest = max(0.0, 1 - happy - neutral - contempt)
    return {"happiness": happy, "neutral": neutral, "contempt": contempt, "surprise": rest, "sadness": 0.0,
            "anger": 0.0, "disgust": 0.0, "fear": 0.0}


def test_expression_high(cfg):
    d = decision.expression(probs(0.91, 0.05), QualityGrade.GOOD, cfg)
    assert d.status == ExpressionStatus.ESTIMATED and d.label == "HAPPY" and d.band == ConfidenceBand.HIGH


def test_expression_moderate_and_quality_cap(cfg):
    assert decision.expression(probs(0.70, 0.10), QualityGrade.GOOD, cfg).band == ConfidenceBand.MODERATE
    assert decision.expression(probs(0.95, 0.03), QualityGrade.ACCEPTABLE, cfg).band == ConfidenceBand.MODERATE


def test_expression_uncertain(cfg):
    assert decision.expression(probs(0.55, 0.30), QualityGrade.GOOD, cfg).status == ExpressionStatus.UNCERTAIN
    assert decision.expression(probs(0.2, 0.1, contempt=0.6), QualityGrade.GOOD, cfg).status == \
        ExpressionStatus.UNCERTAIN


def test_expression_margin_rule(cfg):
    import copy
    from healthvision.config import Config
    data = copy.deepcopy(cfg.data)
    data["expression"]["expression_confidence_threshold"]["moderate"] = 0.4
    loose = Config(data, cfg.version)
    assert decision.expression(probs(0.50, 0.40), QualityGrade.GOOD, loose).status == ExpressionStatus.UNCERTAIN
    assert decision.expression(probs(0.60, 0.30), QualityGrade.GOOD, loose).status == ExpressionStatus.ESTIMATED


def test_expression_excludes_contempt(cfg):
    d = decision.expression(probs(0.8, 0.0, contempt=0.1), QualityGrade.GOOD, cfg)
    assert "CONTEMPT" not in d.probabilities and abs(sum(d.probabilities.values()) - 1) < 1e-9


def test_recognition_three_states(cfg):
    assert decision.recognition(0.5, 0.363, 0.30, "demo_uncalibrated", cfg)[0] == RecognitionDecision.MATCH
    assert decision.recognition(0.33, 0.363, 0.30, "demo_uncalibrated", cfg)[0] == RecognitionDecision.UNCERTAIN
    assert decision.recognition(0.1, 0.363, 0.30, "demo_uncalibrated", cfg)[0] == RecognitionDecision.NO_MATCH


def test_consents_are_independent_and_revocable(cfg):
    store = DataStore()
    c = ConsentService(cfg, store)
    c.record(ConsentPurpose.BMI, ConsentStatus.GRANTED)
    assert c.is_granted(ConsentPurpose.BMI)
    assert not c.is_granted(ConsentPurpose.FACE_ANALYSIS)
    assert not c.is_granted(ConsentPurpose.RECOGNITION)
    with pytest.raises(ConsentRequired):
        c.require(ConsentPurpose.RECOGNITION)
    c.record(ConsentPurpose.BMI, ConsentStatus.REVOKED)
    assert not c.is_granted(ConsentPurpose.BMI)
    assert len(store.consents) == 2   # append-only history


def test_template_encryption_and_shredding(cfg):
    store = DataStore()
    emb = np.random.default_rng(0).standard_normal(128).astype(np.float32)
    tpl = encrypt_embedding(store, emb, "embedding.sface@2021dec", {"grade": "GOOD"})
    assert emb.tobytes() not in tpl.ciphertext
    assert np.allclose(decrypt_embedding(store, tpl, "embedding.sface@2021dec"), emb)
    with pytest.raises(Exception):
        decrypt_embedding(store, tpl, "other-model@1")   # AAD binds template to model
    store.enrollment = Enrollment("e1", "c1", "embedding.sface@2021dec", 128, [tpl])
    assert shred_enrollment(store, "CONSENT_REVOKED") == 1
    assert store.enrollment is None and store.past_enrollments[0].templates == []


def test_audit_chain_and_biometric_guard():
    log = AuditLog()
    log.record("CONSENT_CHANGE", purpose="BMI")
    log.record("RECOGNITION_ATTEMPT", decision="MATCH")
    assert log.verify() is None
    log.entries[0]["details"]["purpose"] = "TAMPERED"
    assert log.verify() == 1
    with pytest.raises(ValueError):
        log.record("X", embedding=[1, 2, 3])
