"""Crypto, template store, audit chain and config validation unit tests (docs/10)."""
import os

import numpy as np
import pytest
import yaml
from sqlalchemy import text

from conftest import ROOT
from healthvision.config.settings import Settings
from healthvision.services.audit_service import AuditService
from healthvision.storage.crypto import EnvelopeCipher
from healthvision.storage.db import Database
from healthvision.storage.orm import FaceEnrollment, FaceTemplate, User, UserConsent
from healthvision.storage.template_store import TemplateStore


def test_envelope_roundtrip_and_aad():
    c = EnvelopeCipher(os.urandom(32))
    s = c.seal(b"secret", b"user|enr")
    assert c.open(s, b"user|enr") == b"secret"
    with pytest.raises(Exception):
        c.open(s, b"other|enr")
    with pytest.raises(Exception):
        EnvelopeCipher(os.urandom(32)).open(s, b"user|enr")


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    d.migrate()
    with d.session() as s:
        s.add(User(user_id="u1", display_name="u", username="u", password_hash="x", role="USER", status="ACTIVE",
                   created_at="t", updated_at="t"))
        s.flush()
        s.add(UserConsent(consent_id="c1", user_id="u1", purpose="RECOGNITION", consent_status="GRANTED", timestamp="t",
                          policy_version="privacy-1.0", notice_text_sha256="x"))
        s.flush()
        s.add(FaceEnrollment(enrollment_id="e1", user_id="u1", consent_id="c1", template_reference="e1",
                             model_version="m", embedding_dim=4, template_count=1, status="ACTIVE", created_at="t"))
    return d


def test_template_store_crypto_shred(db):
    ts = TemplateStore(EnvelopeCipher(os.urandom(32)), 730)
    v = np.array([0.1, 0.2, 0.3, 0.4], np.float32)
    with db.session() as s:
        ts.store(s, "u1", "e1", v, {"grade": "GOOD"})
    with db.session() as s:
        row = s.query(FaceTemplate).one()
        assert v.tobytes() not in row.ciphertext          # not stored in plaintext
        np.testing.assert_allclose(ts.load(s, "u1", "e1")[0], v)
        assert ts.crypto_shred(s, enrollment_id="e1") == 1
    with db.session() as s:
        assert s.query(FaceTemplate).count() == 0


def test_one_active_enrollment_per_user(db):
    with pytest.raises(Exception):
        with db.session() as s:
            s.add(FaceEnrollment(enrollment_id="e2", user_id="u1", consent_id="c1", template_reference="e2",
                                 model_version="m", embedding_dim=4, template_count=1, status="ACTIVE", created_at="t"))


def test_audit_chain_detects_tampering(db):
    a = AuditService()
    with db.session() as s:
        for i in range(3):
            a.record(s, "CONSENT_CHANGE", actor_user_id="u1", details={"n": i})
    with db.session() as s:
        assert a.verify_chain(s)["valid"]
    # the append-only trigger blocks updates
    with pytest.raises(Exception):
        with db.session() as s:
            s.execute(text("UPDATE audit_logs SET outcome='DENIED' WHERE audit_id=2"))
    with pytest.raises(Exception):
        with db.session() as s:
            s.execute(text("DELETE FROM audit_logs"))
    # simulate an attacker who bypasses the trigger
    with db.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_no_update"))
        conn.execute(text("UPDATE audit_logs SET details_json = :d WHERE audit_id = 2"), {"d": '{"n":9}'})
    with db.session() as s:
        res = a.verify_chain(s)
        assert not res["valid"] and res["first_break_audit_id"] == 2


def test_audit_rejects_biometric_keys(db):
    with pytest.raises(ValueError):
        with db.session() as s:
            AuditService().record(s, "RECOGNITION_ATTEMPT", details={"embedding": [1, 2]})


def _cfg():
    return yaml.safe_load((ROOT / "config" / "healthvision.example.yaml").read_text())


def test_config_rejects_log_images():
    c = _cfg()
    c["logging"]["log_images"] = True
    with pytest.raises(Exception):
        Settings.model_validate(c)


def test_config_rejects_unknown_and_missing_keys():
    c = _cfg()
    c["quality"]["surprise_key"] = 1
    with pytest.raises(Exception):
        Settings.model_validate(c)
    c = _cfg()
    del c["expression"]["min_top2_margin"]
    with pytest.raises(Exception):
        Settings.model_validate(c)


def test_config_rejects_raw_image_storage_and_liveness():
    for key in ("store_raw_images", "liveness_enabled"):
        c = _cfg()
        c["features"][key] = True
        with pytest.raises(Exception):
            Settings.model_validate(c)
