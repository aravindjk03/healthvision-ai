"""Recognition threshold calibration (docs/13 §4.2) using the PRODUCTION pipeline.

Manifest CSV columns: path,identity,session   (≥ 2 images per identity, ideally from different sessions)

    python tools/calibrate_recognition.py --manifest data/recog_manifest.csv --target-far 0.001

Writes models/calibration/<model>_v1.json (picked up at next start; leaves DEMO-UNCALIBRATED mode)
and reports/validation/<model>_calibration_<date>.json.
"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np

from _common import ROOT, load_registry_and_pipeline, read_manifest, run_metadata, write_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dataset-name", default="local-consented-v1")
    ap.add_argument("--target-far", type=float, default=0.001)
    ap.add_argument("--target-frr-floor", type=float, default=0.01)
    ap.add_argument("--write", action="store_true", help="install the calibration file")
    args = ap.parse_args()
    cfg, reg, pipe = load_registry_and_pipeline()
    from healthvision.core.latency import LatencyRecorder

    rows = read_manifest(args.manifest)
    emb, rejected = [], 0
    for r in rows:
        res = pipe.run(Path(r["path"]).read_bytes(), LatencyRecorder(), full=True)
        if res.stopped:
            rejected += 1
            continue
        emb.append((r["identity"], r.get("session", ""), reg.engine("embedding").embed(res.aligned)))
    genuine, impostor = [], []
    for (ia, sa, a), (ib, sb, b) in itertools.combinations(emb, 2):
        s = float(np.dot(a, b))
        if ia == ib:
            if sa != sb or not sa:
                genuine.append(s)
        else:
            impostor.append(s)
    if not genuine or not impostor:
        raise SystemExit("need genuine and impostor pairs")
    g, im = np.array(genuine), np.array(impostor)
    grid = np.linspace(-1, 1, 2001)
    far = np.array([(im >= t).mean() for t in grid])
    frr = np.array([(g < t).mean() for t in grid])
    ok = np.where(far <= args.target_far)[0]
    t_match = float(grid[ok[0]]) if len(ok) else 1.0
    t_nomatch = float(np.quantile(g, args.target_frr_floor))
    flagged = t_nomatch >= t_match
    t_nomatch = min(t_nomatch, t_match)
    eer_i = int(np.argmin(np.abs(far - frr)))
    measured = {"far_at_threshold": float((im >= t_match).mean()), "frr_at_threshold": float((g < t_match).mean()),
                "eer": float((far[eer_i] + frr[eer_i]) / 2),
                "uncertain_rate_genuine": float(((g >= t_nomatch) & (g < t_match)).mean()),
                "uncertain_rate_impostor": float(((im >= t_nomatch) & (im < t_match)).mean())}
    me = reg.entry("embedding")
    meta = run_metadata(cfg)
    calib = {"model_id": me.model_id, "model_version": me.version,
             "dataset": {"name": args.dataset_name, "identities": len({e[0] for e in emb}),
                         "genuine_pairs": len(g), "impostor_pairs": len(im), "failure_to_enroll": rejected},
             "created_at": meta["created_at"], "git_commit": meta["git_commit"],
             "target_far": args.target_far, "target_frr_floor": args.target_frr_floor,
             "recognition_threshold": round(t_match, 4), "no_match_threshold": round(t_nomatch, 4),
             "no_uncertain_zone_flag": flagged, "measured": measured,
             "statistical_note": f"Claiming FAR ≤ {args.target_far} at 95% confidence (rule of three) needs ≥ "
                                 f"{int(3 / args.target_far)} impostor comparisons; this run has {len(im)}."}
    print(calib)
    write_json(ROOT / "reports" / "validation" / f"{me.model_id}_calibration_{meta['created_at'][:10]}.json", {**meta, **calib})
    if args.write:
        write_json(cfg.resolve(cfg.settings.recognition.calibration_file), calib)


if __name__ == "__main__":
    main()
