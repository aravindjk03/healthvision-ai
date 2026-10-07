"""Per-stage latency benchmark (docs/13 §7). These are the only latency numbers allowed in
docs and slides.

    python tools/benchmark_latency.py --image tests/fixtures/local/obama.jpg --device "my-laptop"
"""
from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from _common import ROOT, load_registry_and_pipeline, run_metadata, write_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--device", default="unnamed-device")
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--runs", type=int, default=200)
    args = ap.parse_args()
    cfg, reg, pipe = load_registry_and_pipeline()
    from healthvision_server.core.latency import LatencyRecorder

    data = Path(args.image).read_bytes()
    samples: dict[str, list[float]] = {}
    for i in range(args.warmup + args.runs):
        lat = LatencyRecorder()
        r = pipe.run(data, lat, full=True)
        if not r.stopped:
            with lat.stage("expression"):
                reg.engine("expression").predict(r.aligned)
            with lat.stage("embedding"):
                reg.engine("embedding").embed(r.aligned)
        stages = lat.finish()
        if i >= args.warmup:
            for k, v in stages.items():
                samples.setdefault(k, []).append(v)

    def q(v, p):
        v = sorted(v)
        return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]

    result = {k: {"median_ms": round(statistics.median(v), 2), "p95_ms": round(q(v, 0.95), 2),
                  "max_ms": round(max(v), 2), "n": len(v)} for k, v in samples.items()}
    for k, v in result.items():
        print(f"{k:16s} median {v['median_ms']:8.2f} ms   p95 {v['p95_ms']:8.2f} ms")
    meta = run_metadata(cfg)
    write_json(ROOT / "reports" / "benchmarks" / f"latency_{args.device}_{meta['created_at'][:10]}.json",
               {**meta, "device": args.device, "image": Path(args.image).name, "execution_provider": "CPU",
                "warmup": args.warmup, "runs": args.runs, "stages": result})


if __name__ == "__main__":
    main()
