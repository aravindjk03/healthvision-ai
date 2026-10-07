"""Face-count evaluation (docs/13 §2): NO/ONE/MULTIPLE state accuracy and missed-second-face rate.

Manifest CSV columns: path,face_count   (true number of faces in the image)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import ROOT, load_registry_and_pipeline, read_manifest, run_metadata, write_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dataset-name", required=True)
    args = ap.parse_args()
    cfg, reg, pipe = load_registry_and_pipeline()
    from healthvision_server.core.latency import LatencyRecorder

    def truth(n):
        return "NO_FACE" if n == 0 else "ONE_FACE" if n == 1 else "MULTIPLE_FACES"

    rows = read_manifest(args.manifest)
    correct = missed_second = multi = no_face_fp = zero = 0
    for r in rows:
        n = int(r["face_count"])
        state = pipe.run(Path(r["path"]).read_bytes(), LatencyRecorder(), full=False).face_state.value
        correct += state == truth(n)
        if n >= 2:
            multi += 1
            missed_second += state == "ONE_FACE"
        if n >= 1:
            no_face_fp += state == "NO_FACE"
        else:
            zero += 1
    out = {**run_metadata(cfg), "dataset": {"name": args.dataset_name, "size": len(rows)},
           "model": reg.entry("detector").key, "face_count_accuracy": correct / max(1, len(rows)),
           "missed_second_face_rate": missed_second / max(1, multi), "multi_face_images": multi,
           "no_face_false_rate": no_face_fp / max(1, len(rows) - zero)}
    print(out)
    write_json(ROOT / "reports" / "validation" / f"detector_{args.dataset_name}_{out['created_at'][:10]}.json", out)


if __name__ == "__main__":
    main()
