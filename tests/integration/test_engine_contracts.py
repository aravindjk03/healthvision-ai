"""Engine contract tests (docs/12 §3): every adapter honours engines/base.py."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from conftest import face_fixture, needs_models

pytestmark = needs_models


@pytest.fixture(scope="module")
def registry(app):
    return app.state.container.registry


def _img():
    import cv2
    data = face_fixture("obama.jpg")
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def test_registry_info_matches(registry):
    for me in registry.active.values():
        if me.engine is not None:
            info = me.engine.info()
            assert info.model_id == me.model_id and info.version == me.version


def test_detector_contract(registry):
    img = _img()
    det = registry.engine("detector")
    out = det.detect(img, 0.5, 0.3, 10)
    h, w = img.shape[:2]
    for d in out:
        x, y, bw, bh = d.bbox
        assert 0 <= x and 0 <= y and x + bw <= w and y + bh <= h
        assert 0.0 <= d.score <= 1.0 and len(d.keypoints5) == 5
    again = det.detect(img, 0.5, 0.3, 10)
    assert [d.bbox for d in out] == [d.bbox for d in again]          # deterministic
    with ThreadPoolExecutor(8) as ex:                                   # thread-safe
        results = list(ex.map(lambda _: [d.bbox for d in det.detect(img, 0.5, 0.3, 10)], range(8)))
    assert all(r == results[0] for r in results)


def test_expression_and_embedding_contract(registry):
    from healthvision_server.engines.alignment.similarity_transform import align_112
    img = _img()
    d = registry.engine("detector").detect(img, 0.5, 0.3, 10)[0]
    aligned = align_112(img, d.keypoints5)
    p = registry.engine("expression").predict(aligned)
    assert set(p) == set(registry.engine("expression").labels())
    assert abs(sum(p.values()) - 1) < 1e-5
    e = registry.engine("embedding").embed(aligned)
    assert e.shape == (128,) and abs(np.linalg.norm(e) - 1) < 1e-4
    lm = registry.engine("landmarks").landmarks(img, d)
    assert lm is not None and lm.points.shape == (478, 2) and set(lm.pose) == {"yaw", "pitch", "roll"}
    assert registry.engine("liveness").assess([]).status == "NOT_PERFORMED"
