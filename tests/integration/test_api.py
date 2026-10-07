"""API integration tests: auth, consent gating, BMI, face pipeline, recognition, privacy,
traceability (docs/12 §2.2–2.7). Face-image tests need the public-domain fixtures fetched by
tools/fetch_test_fixtures.py and are skipped otherwise."""
import numpy as np
import pytest

from conftest import Client, face_fixture, needs_models, png_bytes

pytestmark = needs_models

PROTECTED = [
    ("post", "/api/v1/bmi/calculate", "BMI"),
    ("post", "/api/v1/face/detect", "FACE_ANALYSIS"),
    ("post", "/api/v1/face/expression", "FACE_ANALYSIS"),
    ("post", "/api/v1/face/enroll", "RECOGNITION"),
    ("post", "/api/v1/face/verify", "RECOGNITION"),
]


def _blank():
    return png_bytes(np.full((600, 800, 3), 128, np.uint8))


# ------------------------------------------------------------------ auth
def test_unauthenticated_is_rejected(client):
    assert client.get("/api/v1/consent").status_code == 401
    assert client.get("/api/v1/health").status_code == 200


def test_setup_only_once_and_login(admin):
    r = admin.post("/api/v1/auth/setup", json={"username": "second", "password": "another-long-password"})
    assert r.status_code == 403
    assert admin.get("/api/v1/auth/me").json()["user"]["role"] == "ADMINISTRATOR"


def test_wrong_password(client, admin):
    c = Client(client.app)
    r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "nope-nope-nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"


def test_csrf_required(admin):
    r = admin.c.post("/api/v1/bmi/calculate", json={})  # raw client without header
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"


def test_weak_password_rejected(admin):
    r = admin.post("/api/v1/admin/users", json={"username": "weak", "password": "short"})
    assert r.status_code == 400


# ------------------------------------------------------------------ consent gating
@pytest.mark.parametrize("method,url,purpose", PROTECTED)
def test_every_protected_route_requires_consent(admin, method, url, purpose):
    for p in ("BMI", "FACE_ANALYSIS", "RECOGNITION"):
        state = {c["purpose"]: c for c in admin.get("/api/v1/consent").json()["consents"]}
        if state[p]["granted"]:
            admin.consent(p, "REVOKE")
    if url.startswith("/api/v1/face"):
        r = admin.upload(url, _blank())
    else:
        r = admin.post(url, json={"height": {"value": 170, "unit": "cm"}, "weight": {"value": 65, "unit": "kg"}})
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "CONSENT_REQUIRED"
    assert r.json()["error"]["details"]["purpose"] == purpose


def test_consent_rejects_wrong_notice_hash(admin):
    r = admin.post("/api/v1/consent", json={"purpose": "BMI", "decision": "GRANT", "policy_version": "privacy-1.0",
                                            "notice_sha256": "0" * 64})
    assert r.status_code == 400


def test_consents_are_independent(admin):
    admin.consent("BMI")
    admin.consent("FACE_ANALYSIS", "DECLINE")
    admin.consent("RECOGNITION", "DECLINE")
    r = admin.post("/api/v1/bmi/calculate", json={"height": {"value": 170, "unit": "cm"}, "weight": {"value": 65, "unit": "kg"}})
    assert r.status_code == 200
    assert admin.upload("/api/v1/face/detect", _blank()).status_code == 403


# ------------------------------------------------------------------ BMI
def test_bmi_endpoint_and_traceability(admin):
    admin.consent("BMI")
    r = admin.post("/api/v1/bmi/calculate", json={"height": {"value": 170, "unit": "cm"}, "weight": {"value": 65, "unit": "kg"},
                                                  "age_years": 34})
    j = r.json()
    assert j["result"]["bmi_display"] == "22.49" and j["result"]["category_label"] == "Normal range"
    from healthvision_server.storage.orm import BmiRecord
    with admin.app.state.container.db.session() as s:
        rec = s.get(BmiRecord, j["record_id"])
        assert rec.config_version == admin.app.state.container.cfg.config_version
        assert rec.input_sha256 and rec.trace_json and rec.expires_at


def test_bmi_invalid_is_200_and_not_persisted(admin):
    admin.consent("BMI")
    r = admin.post("/api/v1/bmi/calculate", json={"height": {"value": 0, "unit": "cm"}, "weight": {"value": 65, "unit": "kg"}})
    assert r.status_code == 200
    assert r.json()["result"]["status"] == "INVALID_INPUT" and r.json()["record_id"] is None


# ------------------------------------------------------------------ face pipeline (no real face needed)
def test_no_face(admin):
    admin.consent("FACE_ANALYSIS")
    j = admin.upload("/api/v1/face/expression", _blank()).json()
    assert j["face"]["face_state"] == "NO_FACE"
    assert j["expression"]["status"] == "NOT_AVAILABLE"
    assert j["message"] == "Let's try again — make sure your face is inside the frame."
    assert "latency_ms" in j and j["latency_ms"]["detection"] >= 0


def test_upload_validation(admin):
    admin.consent("FACE_ANALYSIS")
    r = admin.post("/api/v1/face/detect", files={"image": ("x.gif", b"GIF89a....", "image/gif")})
    assert r.json()["error"]["code"] == "UNSUPPORTED_MEDIA"
    r = admin.post("/api/v1/face/detect", files={"image": ("x.png", b"\x89PNG\r\n\x1a\nbroken", "image/png")})
    assert r.json()["error"]["code"] == "IMAGE_DECODE_FAILED"


def test_identify_disabled(admin):
    r = admin.post("/api/v1/face/identify")
    assert r.status_code == 403 and r.json()["error"]["code"] == "FEATURE_DISABLED"


def test_model_info_gate_not_met(admin):
    j = admin.get("/api/v1/model-info").json()
    assert j["production_readiness_gate"] == "NOT_MET"
    assert j["recognition_calibration"]["state"] == "UNCALIBRATED"
    assert j["liveness"]["state"] == "NOT_IMPLEMENTED"
    assert all(m["local_validation"] == "NOT_VALIDATED" for m in j["models"])


# ------------------------------------------------------------------ real-face journeys
def test_expression_on_single_face(admin):
    admin.consent("FACE_ANALYSIS")
    j = admin.upload("/api/v1/face/expression", face_fixture("obama.jpg"), "o.jpg").json()
    assert j["face"]["face_state"] == "ONE_FACE"
    assert j["quality"]["grade"] in ("GOOD", "ACCEPTABLE")
    e = j["expression"]
    assert e["status"] in ("ESTIMATED", "UNCERTAIN")
    if e["status"] == "ESTIMATED":
        assert e["display"].startswith("Facial expression estimate: ")
        assert e["context"] and e["expression_label"] in e["display"]
    assert "points" not in j["landmarks"]


def test_multiple_faces_blocks_everything(admin):
    admin.consent("FACE_ANALYSIS")
    j = admin.upload("/api/v1/face/expression", face_fixture("two_people.jpg"), "t.jpg").json()
    assert j["face"]["face_state"] == "MULTIPLE_FACES"
    assert j["expression"]["status"] == "NOT_AVAILABLE"
    assert j["message"] == "Multiple faces detected. Please make sure only one person is in the frame."


def test_enroll_verify_revoke(admin):
    admin.consent("RECOGNITION")
    admin.delete("/api/v1/face/enrollment")
    r = admin.post("/api/v1/face/enroll", files=[("image", ("a.jpg", face_fixture("obama.jpg"), "image/jpeg"))])
    assert r.status_code == 201, r.text
    assert r.json()["liveness"] == "NOT_PERFORMED"
    # same person
    v = admin.upload("/api/v1/face/verify", face_fixture("obama2.jpg"), "b.jpg").json()
    assert v["decision"] == "MATCH" and v["demo_uncalibrated"] is True and v["demo_banner"]
    # different person
    v = admin.upload("/api/v1/face/verify", face_fixture("biden.jpg"), "c.jpg").json()
    assert v["decision"] == "NO_MATCH"
    # no template or embedding is ever returned
    for body in (v, admin.get("/api/v1/face/enrollment").json(), admin.get("/api/v1/privacy/export").json()):
        text = str(body).lower()
        assert "ciphertext" not in text and "embedding\":" not in text and "wrapped_dek" not in text
    # revoke -> templates shredded, verify blocked
    res = admin.consent("RECOGNITION", "REVOKE")
    assert res["deletions"]["templates_deleted"] >= 1
    r = admin.upload("/api/v1/face/verify", face_fixture("obama2.jpg"), "b.jpg")
    assert r.status_code == 403 and r.json()["error"]["code"] == "CONSENT_REQUIRED"
    from healthvision_server.storage.orm import FaceTemplate
    with admin.app.state.container.db.session() as s:
        assert s.query(FaceTemplate).count() == 0


def test_enroll_inconsistent_frames(admin):
    admin.consent("RECOGNITION")
    r = admin.post("/api/v1/face/enroll", data={"replace": "true"},
                   files=[("image", ("a.jpg", face_fixture("obama.jpg"), "image/jpeg")),
                          ("image", ("b.jpg", face_fixture("biden.jpg"), "image/jpeg"))])
    assert r.status_code == 409 and r.json()["error"]["code"] == "ENROLLMENT_INCONSISTENT"


# ------------------------------------------------------------------ ownership, reports, privacy
def test_ownership_isolation_and_report(admin):
    admin.consent("BMI")
    sid = admin.post("/api/v1/bmi/calculate", json={"height": {"value": 170, "unit": "cm"},
                                                    "weight": {"value": 65, "unit": "kg"}}).json()["session_id"]
    rep = admin.post("/api/v1/reports", json={"session_id": sid}).json()
    html = admin.get(f"/api/v1/reports/{rep['report_id']}").text
    assert "22.49" in html and "<img" not in html and "health score" not in html.lower()
    pdf = admin.get(f"/api/v1/reports/{rep['report_id']}/pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"

    admin.post("/api/v1/admin/users", json={"username": "bob", "password": "bobs-long-password"})
    bob = Client(admin.app)
    bob.login("bob", "bobs-long-password")
    assert bob.get(f"/api/v1/analysis/{sid}").status_code == 404
    assert bob.get(f"/api/v1/reports/{rep['report_id']}").status_code == 404
    assert bob.get("/api/v1/admin/audit").status_code == 403


def test_delete_all_my_data(admin):
    admin.post("/api/v1/admin/users", json={"username": "carol", "password": "carols-long-password"})
    carol = Client(admin.app)
    carol.login("carol", "carols-long-password")
    carol.consent("BMI")
    carol.post("/api/v1/bmi/calculate", json={"height": {"value": 160, "unit": "cm"}, "weight": {"value": 55, "unit": "kg"}})
    r = carol.delete("/api/v1/privacy/data")
    assert r.status_code == 200 and r.json()["deleted"]["bmi_records"] == 1
    assert carol.get("/api/v1/auth/me").status_code == 401
    audit = admin.get("/api/v1/admin/audit").json()
    assert audit["chain"]["valid"]
    assert any(i["event_type"] == "DATA_DELETION" for i in audit["items"])


def test_retention_purge_runs_and_is_audited(admin):
    counts = admin.app.state.container.retention.purge()
    assert "bmi_records" in counts
    assert any(i["event_type"] == "RETENTION_PURGE" for i in admin.get("/api/v1/admin/audit").json()["items"])
