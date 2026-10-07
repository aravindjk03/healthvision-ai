"""Expression evaluation (docs/13 §3) on a labelled manifest, through the production pipeline.

Manifest CSV columns: path,label   (label = product class, e.g. HAPPY, NEUTRAL; AMBIGUOUS allowed)
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np

from _common import ROOT, load_registry_and_pipeline, read_manifest, run_metadata, write_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dataset-name", required=True)
    args = ap.parse_args()
    cfg, reg, pipe = load_registry_and_pipeline()
    from healthvision.core.latency import LatencyRecorder
    from healthvision.services import decision_engine as DE

    classes = cfg.settings.expression.classes
    y_true, y_pred, conf, status = [], [], [], []
    for r in read_manifest(args.manifest):
        res = pipe.run(Path(r["path"]).read_bytes(), LatencyRecorder(), full=True)
        raw = None if res.stopped else reg.engine("expression").predict(res.aligned)
        d = DE.expression(raw, face_state=res.face_state.value, quality=res.quality_grade.value if res.quality_grade else None,
                          stop_reason=None if res.stop_reason in (None, "NO_FACE", "MULTIPLE_FACES", "POOR_QUALITY") else res.stop_reason,
                          cfg=cfg.settings.expression, config_version=cfg.config_version)
        y_true.append(r["label"]); status.append(d.status.value)
        top = max(d.probabilities.items(), key=lambda kv: kv[1])[0] if d.probabilities else None
        y_pred.append(d.label or top); conf.append(d.confidence or 0.0)
    est = [i for i, s in enumerate(status) if s == "ESTIMATED" and y_true[i] in classes]
    per_class = {}
    for c in classes:
        tp = sum(1 for i in est if y_pred[i] == c and y_true[i] == c)
        fp = sum(1 for i in est if y_pred[i] == c and y_true[i] != c)
        fn = sum(1 for i in est if y_pred[i] != c and y_true[i] == c)
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        per_class[c] = {"precision": p, "recall": rc, "f1": 2 * p * rc / (p + rc) if p + rc else 0.0,
                        "support": sum(1 for i in est if y_true[i] == c)}
    acc = float(np.mean([y_pred[i] == y_true[i] for i in est])) if est else None
    bins = np.linspace(0, 1, 16)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        idx = [i for i in est if lo <= conf[i] < hi]
        if idx:
            ece += len(idx) / len(est) * abs(np.mean([y_pred[i] == y_true[i] for i in idx]) - np.mean([conf[i] for i in idx]))
    out = {**run_metadata(cfg), "dataset": {"name": args.dataset_name, "size": len(y_true), "labels": Counter(y_true)},
           "model": reg.entry("expression").key, "coverage": len(est) / max(1, len(y_true)),
           "status_counts": Counter(status), "accuracy_on_estimated": acc,
           "macro_f1": float(np.mean([v["f1"] for v in per_class.values()])), "per_class": per_class, "ece_15": ece}
    print(out)
    write_json(ROOT / "reports" / "validation" / f"expression_{args.dataset_name}_{out['created_at'][:10]}.json", out)


if __name__ == "__main__":
    main()
