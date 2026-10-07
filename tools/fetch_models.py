"""Download every model in models/server-registry.yaml and verify its SHA-256 (docs/10 §8).

    python tools/fetch_models.py            # download missing files
    python tools/fetch_models.py --verify   # only verify existing files
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    reg = yaml.safe_load((ROOT / "models" / "registry.yaml").read_text())
    ok = True
    for m in reg["models"]:
        if not m.get("file"):
            continue
        dest = ROOT / "models" / m["file"]
        if not dest.exists() and not args.verify:
            url = m["download_url"]
            if not url.startswith("https://"):
                print(f"refusing non-HTTPS url for {m['model_id']}")
                return 1
            print(f"downloading {m['model_id']} …")
            tmp = dest.with_suffix(dest.suffix + ".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.replace(dest)
        if not dest.exists():
            print(f"MISSING  {m['model_id']}  ({dest.name})")
            ok = False
            continue
        actual = sha256(dest)
        if m.get("sha256") and actual != m["sha256"]:
            print(f"MISMATCH {m['model_id']}  expected {m['sha256'][:12]}… got {actual[:12]}…")
            dest.unlink()
            ok = False
        else:
            print(f"OK       {m['model_id']}@{m['version']}  {actual[:12]}…")
            dest.chmod(0o444)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
