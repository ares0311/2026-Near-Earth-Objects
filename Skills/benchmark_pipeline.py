#!/usr/bin/env python3
"""Benchmark link + classify + score on N synthetic tracklets.

Usage:
    PYTHONPATH=src python Skills/benchmark_pipeline.py [--n 100]
"""

from __future__ import annotations

import argparse
import math
import random
import time

from schemas import Observation, Tracklet


def _make_obs(i: int, jd: float, ra: float, dec: float) -> Observation:
    return Observation(
        obs_id=f"bench_{i}",
        ra_deg=ra % 360.0,
        dec_deg=max(-89.0, min(89.0, dec)),
        jd=jd,
        mag=19.0 + random.uniform(-1, 1),
        mag_err=0.05,
        filter_band=random.choice(["g", "r", "i"]),
        mission="ZTF",
        real_bogus=random.uniform(0.7, 1.0),
    )


def _make_tracklet(idx: int, n_obs: int = 4, arc_days: float = 3.0) -> Tracklet:
    ra0 = random.uniform(0, 360)
    dec0 = random.uniform(-30, 30)
    jd0 = 2460000.0 + random.uniform(0, 100)
    rate = random.uniform(0.5, 10.0)  # arcsec/hr
    pa = random.uniform(0, 360)

    obs = tuple(
        _make_obs(
            idx * 100 + i,
            jd0 + i * arc_days / max(n_obs - 1, 1),
            ra0 + i * rate / 3600 * math.cos(math.radians(pa)),
            dec0 + i * rate / 3600 * math.sin(math.radians(pa)),
        )
        for i in range(n_obs)
    )
    return Tracklet(
        object_id=f"T{idx:04d}",
        observations=obs,
        arc_days=arc_days,
        motion_rate_arcsec_per_hour=rate,
        motion_pa_degrees=pa,
    )


def benchmark(n: int) -> None:
    from classify import classify
    from score import score

    random.seed(42)
    tracklets = [_make_tracklet(i) for i in range(n)]

    stages: dict[str, float] = {}

    t0 = time.perf_counter()
    classify_results = [classify(t) for t in tracklets]
    stages["classify"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    _ = [score(t, f, p) for t, (f, p) in zip(tracklets, classify_results)]
    stages["score"] = time.perf_counter() - t0

    total = sum(stages.values())
    print(f"\n{'Stage':<12} {'Total (s)':>10} {'Per tracklet (ms)':>18}")
    print("-" * 42)
    for stage, elapsed in stages.items():
        print(f"{stage:<12} {elapsed:>10.3f} {elapsed / n * 1000:>18.2f}")
    print("-" * 42)
    print(f"{'TOTAL':<12} {total:>10.3f} {total / n * 1000:>18.2f}")
    print(f"\nProcessed {n} tracklets in {total:.3f}s ({n / total:.0f} tracklets/s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="Number of tracklets")
    args = parser.parse_args()
    benchmark(args.n)
