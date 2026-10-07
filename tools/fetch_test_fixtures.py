"""Fetch face test fixtures into tests/fixtures/local/ (gitignored — never committed).

Source: example images shipped with the open-source `face_recognition` project
(github.com/ageitgey/face_recognition, MIT). They are official U.S. government (White House)
photographs, which are in the public domain. Provenance: tests/fixtures/PROVENANCE.md.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/ageitgey/face_recognition/master/examples/"
FILES = ["obama.jpg", "obama2.jpg", "biden.jpg", "two_people.jpg"]


def main() -> None:
    out = ROOT / "tests" / "fixtures" / "local"
    out.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        dest = out / f
        if not dest.exists():
            print("downloading", f)
            urllib.request.urlretrieve(BASE + f, dest)
        print("OK", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
