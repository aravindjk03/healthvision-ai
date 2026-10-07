"""Wording lint (docs/12 §7): forbidden claims must not appear in user-facing code."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = [r"\bis happy\b", r"\bdefinitely\b", r"\bproves\b", r"health score", r"100% accurate", r"anti-spoof",
             r"mental health", r"\bdiagnos(e|is) (you|your)"]
USER_FACING = [ROOT / "streamlit_app.py", *(ROOT / "healthvision").rglob("*.py")]


def test_no_forbidden_wording():
    for path in USER_FACING:
        text = path.read_text(encoding="utf-8").lower()
        for pattern in FORBIDDEN:
            assert not re.search(pattern, text), f"{pattern!r} found in {path.name}"


def test_mandatory_notes_present():
    app = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    face = (ROOT / "healthvision/services/face_analysis.py").read_text(encoding="utf-8")
    from healthvision.services.face_analysis import EXPRESSION_NOTE
    assert "should not be interpreted as a definitive measure of emotional state" in EXPRESSION_NOTE
    assert "does not constitute a medical diagnosis" in app
    assert "Multiple faces detected. Please ensure only one person is in frame." in face
    assert "LIVENESS_NOTICE" in app
