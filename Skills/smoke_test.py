#!/usr/bin/env python
"""Smoke test — verify all pipeline modules import and run minimal happy-path checks.

Usage:
    PYTHONPATH=src python Skills/smoke_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


import numpy as np

from detect import detect
from link import link
from orbit import classify_neo, compute_moid
from preprocess import _normalize_cutout, preprocess
from schemas import (
    CandidateFeatures,
    NEOPosterior,
    Observation,
    OrbitalElements,
    Tracklet,
)
from score import score


def _obs(obs_id: str, jd: float, ra: float, rb: float = 0.9) -> Observation:
    return Observation(
        obs_id=obs_id,
        ra_deg=ra,
        dec_deg=0.0,
        jd=jd,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=rb,
    )


def smoke_preprocess() -> None:
    from schemas import Observation

    obs = Observation(
        obs_id="p1",
        ra_deg=180.0,
        dec_deg=0.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
    )
    result = preprocess((obs,), apply_astrometry=False)
    assert len(result.sources) == 1, "Preprocess: expected 1 source"
    arr = np.random.default_rng(0).uniform(0, 100, (63, 63)).astype(np.float32)
    norm = _normalize_cutout(arr)
    assert norm.min() >= 0.0 and norm.max() <= 1.0
    print("  preprocess  ✓")


def smoke_detect() -> None:
    obs1 = _obs("a", 2460000.5, 180.00)
    obs2 = _obs("b", 2460000.5 + 1 / 24, 180.01)
    result = detect((obs1, obs2), mpc_cross_match=False)
    assert len(result.candidates) >= 1, "Detect: expected ≥1 candidate"
    print("  detect      ✓")


def smoke_link() -> None:
    dra = 1.0 / 3600.0
    candidates = []
    from detect import detect as _detect

    for night in range(3):
        jd = 2460000.5 + night
        ra = 180.0 + night * dra * 24
        o1 = _obs(f"n{night}a", jd, ra)
        o2 = _obs(f"n{night}b", jd + 1 / 24, ra + dra)
        det = _detect((o1, o2), mpc_cross_match=False)
        candidates.extend(det.candidates)

    result = link(tuple(candidates), min_nights=2, min_observations=3)
    print(f"  link        ✓  ({len(result.tracklets)} tracklets)")


def smoke_orbit() -> None:
    el = OrbitalElements(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=2,
    )
    cls = classify_neo(el)
    assert cls in ("amor", "apollo", "aten", "ieo", "unknown")
    moid = compute_moid(el)
    print(f"  orbit       ✓  (class={cls}, moid={moid})")


def smoke_score() -> None:
    obs = tuple(_obs(f"o{i}", 2460000.5 + i, 180.0 + i * 0.001) for i in range(3))
    t = Tracklet("T001", obs, 2.0, 1.0, 90.0)
    el = OrbitalElements(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=2,
    )
    f = CandidateFeatures(real_bogus_score=0.92)
    p = NEOPosterior(
        neo_candidate=0.6,
        known_object=0.1,
        main_belt_asteroid=0.1,
        stellar_artifact=0.1,
        other_solar_system=0.1,
    )
    result = score(t, f, p, el)
    assert result.hazard.hazard_flag in ("pha_candidate", "close_approach", "nominal", "unknown")
    print(f"  score       ✓  (pathway={result.hazard.alert_pathway})")


def main() -> None:
    print("NEO pipeline smoke test")
    print("-" * 40)
    smoke_preprocess()
    smoke_detect()
    smoke_link()
    smoke_orbit()
    smoke_score()
    print("-" * 40)
    print("All checks passed.")


if __name__ == "__main__":
    main()
