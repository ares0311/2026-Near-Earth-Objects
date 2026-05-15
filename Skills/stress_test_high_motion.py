#!/usr/bin/env python
"""Stress-test the linker across three motion-rate bins.

Tests 50 synthetic NEOs in each of three bins:
  • 1–10 arcsec/hr   (slow-moving Amors/Apollos)
  • 10–30 arcsec/hr  (typical inner NEOs)
  • 30–60 arcsec/hr  (fast-approaching NEOs)

Asserts ≥60% link rate in the highest-motion bin (30–60 arcsec/hr).
Saves results to data/stress_test_high_motion.json.

Usage:
    PYTHONPATH=src python Skills/stress_test_high_motion.py [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np

from detect import detect
from link import link
from schemas import Observation


def _make_obs(obs_id: str, jd: float, ra_deg: float, dec_deg: float, mag: float) -> Observation:
    return Observation(
        obs_id=obs_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        jd=jd,
        mag=mag,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.92,
    )


def inject_neo(
    seed: int,
    ra0: float,
    dec0: float,
    motion_arcsec_per_hr: float,
) -> tuple[Observation, ...]:
    rng = np.random.default_rng(seed)
    dra_hr = motion_arcsec_per_hr / 3600.0
    obs = []
    for night in range(3):
        jd = 2460000.5 + night
        ra = ra0 + night * dra_hr * 24
        obs.append(_make_obs(f"s{seed}_n{night}a", jd,
                             ra + rng.normal(0, 0.5 / 3600.0),
                             dec0 + rng.normal(0, 0.5 / 3600.0), 19.5))
        obs.append(_make_obs(f"s{seed}_n{night}b", jd + 1 / 24,
                             ra + dra_hr + rng.normal(0, 0.5 / 3600.0),
                             dec0 + rng.normal(0, 0.5 / 3600.0), 19.5))
    return tuple(obs)


def run_bin(rng: np.random.Generator, lo: float, hi: float, n: int = 50) -> dict:
    n_detected = 0
    n_linked = 0
    for i in range(n):
        motion = float(rng.uniform(lo, hi))
        ra0 = float(rng.uniform(0, 359))
        dec0 = float(rng.uniform(-30, 30))
        obs = inject_neo(seed=int(rng.integers(0, 1_000_000)), ra0=ra0, dec0=dec0,
                         motion_arcsec_per_hr=motion)
        dr = detect(obs, mpc_cross_match=False)
        if dr.candidates:
            n_detected += 1
        lr = link(tuple(dr.candidates), min_nights=2, min_observations=3)
        if lr.tracklets:
            n_linked += 1
    return {
        "bin": f"{lo:.0f}-{hi:.0f} arcsec/hr",
        "n_total": n,
        "n_detected": n_detected,
        "n_linked": n_linked,
        "detection_rate": n_detected / max(n, 1),
        "link_rate": n_linked / max(n, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="High-motion linker stress test")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-per-bin", type=int, default=50)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    bins = [(1, 10), (10, 30), (30, 60)]

    print(f"High-motion linker stress test  (seed={args.seed}, n_per_bin={args.n_per_bin})")
    print("-" * 60)

    results = []
    for lo, hi in bins:
        res = run_bin(rng, lo, hi, n=args.n_per_bin)
        results.append(res)
        print(f"  {res['bin']:20s}  det={res['detection_rate']:.0%}  link={res['link_rate']:.0%}")

    print("-" * 60)

    high_motion = results[-1]
    pass_threshold = 0.60
    passed = high_motion["link_rate"] >= pass_threshold
    status = "PASS" if passed else "FAIL"
    print(f"High-motion bin ({high_motion['bin']}): "
          f"link_rate={high_motion['link_rate']:.0%} "
          f"(threshold {pass_threshold:.0%}) → {status}")

    out = {
        "seed": args.seed,
        "n_per_bin": args.n_per_bin,
        "bins": results,
        "high_motion_pass": passed,
        "high_motion_threshold": pass_threshold,
    }
    out_path = Path("data/stress_test_high_motion.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Results saved → {out_path}")

    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
