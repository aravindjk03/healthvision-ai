"""Assemble the browser-only demo into web-demo/dist/.

Needs: the model files in ../models (python tools/fetch_models.py) and the npm packages
(cd web-demo && npm install). Model files above 14 MB are split into parts because the
artifact host caps each file at 15 MB; the page re-joins them byte-for-byte.
"""
import base64
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIST = HERE / "dist"
NM = HERE / "node_modules"
PART = 11 * 1024 * 1024  # 11 MiB of model bytes -> ~14.7 MB of base64 text per file


def split(src: Path, stem: str) -> list[str]:
    """Write a model as base64 text parts (the artifact host serves text, not raw binaries)."""
    data = src.read_bytes()
    names = []
    for i in range(0, len(data), PART):
        name = f"{stem}.part{i // PART}.txt"
        (DIST / "models" / name).write_text(base64.b64encode(data[i:i + PART]).decode())
        names.append(name)
    return names


def main() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    (DIST / "lib" / "mp").mkdir(parents=True)
    (DIST / "models").mkdir()
    shutil.copy(HERE / "index.html", DIST / "index.html")
    ort = NM / "onnxruntime-web" / "dist"
    for f in ("ort.wasm.min.js", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"):
        shutil.copy(ort / f, DIST / "lib" / f)
    mp = NM / "@mediapipe" / "tasks-vision"
    shutil.copy(mp / "vision_bundle.mjs", DIST / "lib" / "vision_bundle.mjs")
    for f in ("vision_wasm_internal.js", "vision_wasm_internal.wasm"):
        shutil.copy(mp / "wasm" / f, DIST / "lib" / "mp" / f)
    models = ROOT / "models"
    manifest = {
        "yunet": split(models / "face_detection_yunet_2023mar.onnx", "yunet"),
        "landmarker": split(models / "face_landmarker.task", "landmarker"),
        "ferplus": split(models / "emotion-ferplus-8.onnx", "ferplus"),
        "sface": split(models / "face_recognition_sface_2021dec.onnx", "sface"),
    }
    (DIST / "models" / "manifest.json").write_text(json.dumps(manifest))
    for p in sorted(DIST.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size / 1e6:7.2f} MB  {p.relative_to(DIST)}")


if __name__ == "__main__":
    main()
