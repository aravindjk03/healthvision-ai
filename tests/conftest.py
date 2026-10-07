"""Shared fixtures: an isolated app per test module (temp data dir, env keystore)."""
from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
FIXTURES = ROOT / "tests" / "fixtures" / "local"

os.environ.setdefault("HEALTHVISION_KEK", base64.b64encode(b"k" * 32).decode())

MODELS_PRESENT = all((ROOT / "models" / f).exists() for f in (
    "face_detection_yunet_2023mar.onnx", "face_landmarker.task", "emotion-ferplus-8.onnx",
    "face_recognition_sface_2021dec.onnx"))
needs_models = pytest.mark.skipif(not MODELS_PRESENT, reason="model files missing — run tools/fetch_models.py")


def face_fixture(name: str) -> bytes:
    p = FIXTURES / name
    if not p.exists():
        pytest.skip(f"face fixture {name} missing — run tools/fetch_test_fixtures.py")
    return p.read_bytes()


def make_config(tmp: Path, **overrides) -> Path:
    cfg = yaml.safe_load((ROOT / "config" / "healthvision.example.yaml").read_text())
    cfg["paths"]["data_dir"] = str(tmp / "data")
    cfg["security"]["keystore"] = "env"
    for dotted, value in overrides.items():
        node = cfg
        keys = dotted.split("__")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    path = tmp / "healthvision.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


def png_bytes(arr: np.ndarray) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


class Client:
    """TestClient wrapper that signs in and sends the CSRF header automatically."""

    def __init__(self, app):
        from fastapi.testclient import TestClient
        self.app = app
        self.c = TestClient(app)

    def _h(self, headers=None):
        h = {"X-CSRF-Token": self.c.cookies.get("hv_csrf", "")}
        h.update(headers or {})
        return h

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **kw):
        kw["headers"] = self._h(kw.get("headers"))
        return self.c.post(url, **kw)

    def patch(self, url, **kw):
        kw["headers"] = self._h(kw.get("headers"))
        return self.c.patch(url, **kw)

    def delete(self, url, **kw):
        kw["headers"] = self._h(kw.get("headers"))
        return self.c.delete(url, **kw)

    def setup_admin(self, username="admin", password="a-long-test-password"):
        r = self.post("/api/v1/auth/setup", json={"username": username, "password": password})
        assert r.status_code == 201, r.text
        return r

    def login(self, username, password):
        self.c.cookies.clear()
        r = self.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return r

    def consent(self, purpose, decision="GRANT"):
        n = self.get("/api/v1/consent").json()["notices"][purpose]
        r = self.post("/api/v1/consent", json={"purpose": purpose, "decision": decision,
                                               "policy_version": n["policy_version"], "notice_sha256": n["sha256"]})
        assert r.status_code == 200, r.text
        return r.json()

    def upload(self, url, data: bytes, name="img.png", extra=None):
        return self.post(url, files={"image": (name, data, "image/png")}, data=extra or {})


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    from healthvision.main import create_app
    tmp = tmp_path_factory.mktemp("hv")
    application = create_app(str(make_config(tmp)), start_scheduler=False)
    yield application
    application.state.container.close()


@pytest.fixture()
def client(app):
    c = app.state.container
    c.limiter.reset()
    cl = Client(app)
    return cl


@pytest.fixture()
def admin(client):
    with client.app.state.container.db.session() as s:
        from healthvision.storage.orm import User
        exists = s.query(User).filter_by(username="admin").first() is not None
    if exists:
        client.login("admin", "a-long-test-password")
    else:
        client.setup_admin()
    return client
