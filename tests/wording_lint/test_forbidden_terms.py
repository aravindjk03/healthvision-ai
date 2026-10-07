"""Wording lint (docs/12 §7, docs/01 §6): forbidden phrases must not appear in user-facing
text; mandatory notes must exist. "Never do" sections of the docs are allow-listed."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = [r"\bis happy\b", r"\bdefinitely\b", r"\bproves\b", r"health score", r"100\s?% accurate",
             r"anti-spoof", r"mental health", r"secure biometric login", r"\bdiagnos(e|ed|es|ing)\b(?! )",
             r"emotion detector(?! —)"]
# Phrases that are fine only when negated / disclaiming (checked by surrounding text).
NEGATION = re.compile(r"(no|not|never|does not|cannot|isn't|is not|without|n't)\b[^.\n]{0,60}$", re.I)

SCAN = [
    *(ROOT / "frontend" / "src").rglob("*.tsx"),
    *(ROOT / "frontend" / "src").rglob("*.ts"),
    ROOT / "backend" / "healthvision" / "domain" / "messages.py",
    *(ROOT / "backend" / "healthvision" / "reports").rglob("*.*"),
]


def _violations(text: str):
    out = []
    for pat in FORBIDDEN:
        for m in re.finditer(pat, text, re.I):
            prefix = text[max(0, m.start() - 80):m.start()]
            if NEGATION.search(prefix):
                continue
            out.append((pat, text[max(0, m.start() - 40):m.end() + 20].replace("\n", " ")))
    return out


@pytest.mark.parametrize("path", [p for p in SCAN if p.is_file() and p.suffix in {".ts", ".tsx", ".py", ".j2"}],
                         ids=lambda p: str(p.relative_to(ROOT)))
def test_no_forbidden_wording(path):
    assert _violations(path.read_text(encoding="utf-8")) == []


def test_mandatory_notes_present():
    from healthvision.domain import messages as M
    msgs = " ".join(v if isinstance(v, str) else " ".join(map(str, v.values())) for k, v in vars(M).items()
                    if k.isupper())
    for needle in ["It describes the face at that moment, not how you feel inside.",
                   "BMI is a screening measure, not a medical diagnosis",
                   "Multiple faces detected. Please make sure only one person is in the frame.",
                   "Liveness detection is not implemented in this version.",
                   "These are separate measurements"]:
        assert needle in msgs
    dash = (ROOT / "frontend" / "src" / "App.tsx").read_text()
    assert "These are separate measurements" in dash


def test_expression_display_is_positive_and_complete():
    """Every product class has calm, descriptive display wording and a supportive context line."""
    from healthvision.domain import messages as M
    classes = ["HAPPY", "NEUTRAL", "SAD", "SURPRISED", "ANGRY", "FEARFUL", "DISGUSTED"]
    for c in classes:
        assert M.EXPRESSION_DISPLAY[c] and M.EXPRESSION_DESCRIPTION[c] and M.EXPRESSION_CONTEXT[c]
    shown = " ".join(M.EXPRESSION_DISPLAY.values()).lower()
    for harsh in ("angry", "sad", "fear", "disgust"):
        assert harsh not in shown
    pdf = (ROOT / "backend" / "healthvision" / "reports" / "pdf.py").read_text()
    assert "limitations" in pdf


def test_no_threshold_literals_in_services_and_engines():
    """docs/02 §8 rule 1: no numeric threshold literal in comparisons outside config/tests."""
    pat = re.compile(r"(>=|<=|<|>)\s*0\.\d+")
    allowed = {"bmi_service.py", "pdf.py"}  # pdf: display rounding of >99%
    for p in list((ROOT / "backend" / "healthvision" / "services").rglob("*.py")) + \
             list((ROOT / "backend" / "healthvision" / "engines").rglob("*.py")):
        if p.name in allowed:
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            assert not pat.search(line), f"{p.name}:{i}: {line.strip()}"
