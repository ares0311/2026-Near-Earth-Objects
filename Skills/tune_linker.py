#!/usr/bin/env python3
"""Parametric sweep of link.py tolerance and chi² threshold vs link/score rate.

Usage:
    PYTHONPATH=src uv run python Skills/tune_linker.py [--n 50] [--seed 42]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np

from classify import extract_features
from detect import detect
from link import link
from orbit import fit_orbit
from schemas import NEOPosterior, Observation
from score import score

_SYNTHETIC_SWEEP_POSTERIOR = NEOPosterior(
    # The linker sweep measures link/orbit/score plumbing, not ML inference.
    # Use a deterministic posterior so this utility does not load Tier 3
    # Transformer weights or initialize PyTorch during lightweight smoke tests.
    neo_candidate=0.6,
    known_object=0.1,
    main_belt_asteroid=0.1,
    stellar_artifact=0.1,
    other_solar_system=0.1,
)


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


def _inject(
    seed: int, ra0: float, dec0: float, motion: float, mag: float
) -> tuple[Observation, ...]:
    rng = np.random.default_rng(seed)
    dra = motion / 3600.0
    obs = []
    for night in range(3):
        jd_base = 2460000.5 + night
        ra_base = ra0 + night * dra * 24
        obs.append(_make_obs(f"t_{seed}_n{night}a", jd_base,
                              ra_base + rng.normal(0, 0.3 / 3600),
                              dec0 + rng.normal(0, 0.3 / 3600), mag))
        obs.append(_make_obs(f"t_{seed}_n{night}b", jd_base + 1 / 24,
                              ra_base + dra + rng.normal(0, 0.3 / 3600),
                              dec0 + rng.normal(0, 0.3 / 3600), mag))
    return tuple(obs)


def _run_one(n: int, seed: int, tol: float, chi2: float) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n_linked = 0
    n_scored = 0
    for i in range(n):
        motion = float(rng.uniform(0.1, 10.0))
        mag = float(rng.uniform(18.0, 21.0))
        ra0 = float(rng.uniform(0.0, 359.0))
        dec0 = float(rng.uniform(-30.0, 30.0))
        obs = _inject(seed * 1000 + i, ra0, dec0, motion, mag)
        dr = detect(obs, mpc_cross_match=False)
        lr = link(tuple(dr.candidates), min_nights=2, min_observations=3,
                  position_tolerance_arcsec=tol, chi2_threshold=chi2)
        if lr.tracklets:
            n_linked += 1
            t = lr.tracklets[0]
            feats = extract_features(t)
            orb = fit_orbit(t)
            score(t, feats, _SYNTHETIC_SWEEP_POSTERIOR, orb)
            n_scored += 1
    return n_linked / max(n, 1), n_scored / max(n, 1)


def sweep(n: int, seed: int) -> None:  # noqa: ANN201
    tolerances = [5.0, 10.0, 20.0, 30.0]
    chi2s = [2.0, 5.0, 10.0, 20.0]

    print(f"Linker parameter sweep (n={n}, seed={seed})")
    print(f"{'Tol(″)':>8} {'χ²max':>8} {'Link%':>8} {'Score%':>8}")
    print("-" * 36)
    for tol in tolerances:
        for chi2 in chi2s:
            link_rate, score_rate = _run_one(n, seed, tol, chi2)
            print(f"{tol:>8.1f} {chi2:>8.1f} {link_rate:>7.1%} {score_rate:>7.1%}")
    print("-" * 36)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20, help="Tracklets per config")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    sweep(args.n, args.seed)
