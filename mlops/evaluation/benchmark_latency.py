"""Simple latency harness for edge inference (CPU/GPU)."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--num_samples", type=int, default=20)
    p.add_argument("--output", type=Path, default=Path("latency_report.json"))
    args = p.parse_args()

    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "edge"))
    from clip_inference import ClipInspector  # type: ignore

    root = repo / "edge"
    prompts = root / "prompts.json"
    inspector = ClipInspector(model_name="openai/clip-vit-base-patch32", prompts_path=prompts)
    times_ms: list[float] = []
    frame = np.zeros((224, 224, 3), dtype=np.uint8)
    frame[:] = (90, 90, 90)
    for _ in range(args.num_samples):
        t0 = time.perf_counter()
        inspector.infer(frame)
        times_ms.append((time.perf_counter() - t0) * 1000.0)

    report = {
        "samples": args.num_samples,
        "p50_ms": statistics.median(times_ms),
        "mean_ms": statistics.fmean(times_ms),
        "p95_ms": sorted(times_ms)[int(0.95 * (len(times_ms) - 1))],
    }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
