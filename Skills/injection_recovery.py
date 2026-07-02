#!/usr/bin/env python
"""Injection-recovery test for the NEO detection pipeline.

Injects synthetic moving objects into a background of real observations and
measures how many are successfully detected, linked, classified, and scored.

Usage:
    PYTHONPATH=src python Skills/injection_recovery.py [--n-inject 50] [--seed 42]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np

from classify import classify, extract_features
from detect import detect
from link import link
from orbit import fit_orbit
from schemas import Observation
from score import score


def _make_obs(
    obs_id: str,
    jd: float,
    ra_deg: float,
    dec_deg: float,
    mag: float,
    mission: str = "ZTF",
    filter_band: str = "r",
    mag_err: float = 0.05,
    real_bogus: float | None = 0.92,
) -> Observation:
    return Observation(
        obs_id=obs_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        jd=jd,
        mag=mag,
        mag_err=mag_err,
        filter_band=filter_band,
        mission=mission,
        real_bogus=real_bogus,
    )


def inject_synthetic_neo(
    seed: int,
    n_nights: int = 3,
    ra0: float = 180.0,
    dec0: float = 0.0,
    motion_arcsec_per_hr: float = 1.0,
    mag: float = 19.5,
) -> tuple[Observation, ...]:
    """Generate a synthetic ZTF-cadence NEO tracklet as a sequence of observations."""
    rng = np.random.default_rng(seed)
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    obs = []
    for night in range(n_nights):
        jd_base = 2460000.5 + night
        ra_base = ra0 + night * dra_per_hr * 24
        # Two observations per night separated by 1 hr
        obs.append(
            _make_obs(
                f"inj_{seed}_n{night}a",
                jd_base,
                ra_base + rng.normal(0, 0.5 / 3600.0),
                dec0 + rng.normal(0, 0.5 / 3600.0),
                mag + rng.normal(0, 0.05),
            )
        )
        obs.append(
            _make_obs(
                f"inj_{seed}_n{night}b",
                jd_base + 1 / 24,
                ra_base + dra_per_hr + rng.normal(0, 0.5 / 3600.0),
                dec0 + rng.normal(0, 0.5 / 3600.0),
                mag + rng.normal(0, 0.05),
            )
        )
    return tuple(obs)


def inject_synthetic_neo_wise(
    seed: int,
    ra0: float = 180.0,
    dec0: float = 0.0,
    motion_arcsec_per_hr: float = 1.0,
    mag: float = 12.0,
    n_exposures: int = 6,
    visit_span_hours: float = 54.0,
) -> tuple[Observation, ...]:
    """Generate a synthetic WISE/NEOWISE-cadence NEO tracklet.

    Source-specific cadence assumption (see docs/PRODUCTION_READINESS.md Gate
    P1 and Mainzer et al. 2014): a single NEOWISE "visit" consists of several
    single-epoch W1 exposures as the spacecraft's overlapping orbit tracks
    re-cross the same sky patch, not a paired same-night detection like ZTF.
    Visit duration depends on ecliptic latitude: near the ecliptic poles,
    continuous orbit-track overlap gives multi-day (~2-3 UTC calendar day)
    visit coverage rather than the ~1-day baseline at low ecliptic latitude
    (Mainzer et al. 2014). link.py buckets nights by `int(obs.jd)`, and a
    single seed pair can only extend to a tracklet if a third night's
    observation falls within its predicted position — so a >=3-distinct-night
    visit is used here to satisfy link.py's >=3-observation, >=2-night
    structural requirement without inventing an unphysical inter-visit (~6
    month) linear-motion assumption. Unlike ZTF, NEOWISE single-epoch
    photometry (`neowiser_p1bs_psd`) carries no real/bogus score, so
    `real_bogus` is left `None` — the pipeline's scoring model treats a
    missing score as neutral (contributes 0), not as a fabricated ZTF-style
    confidence. W1 photometric uncertainty
    (`w1sigmpro`) is typically 0.03-0.2 mag at the depths NEOs are detected;
    astrometric scatter reflects the ~1 arcsec position-fit sky in
    Mainzer et al. (2014).
    """
    rng = np.random.default_rng(seed)
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    obs = []
    exposure_hours = np.linspace(0.0, visit_span_hours, n_exposures)
    # Start mid-day (2460000.6) so the multi-day visit crosses integer-JD
    # night boundaries link.py uses for night bucketing (int(obs.jd)); a
    # visit starting at midnight would shift bucket boundaries unnecessarily.
    for idx, dt_hr in enumerate(exposure_hours):
        jd = 2460000.6 + dt_hr / 24.0
        ra = ra0 + dt_hr * dra_per_hr + rng.normal(0, 1.0 / 3600.0)
        dec = dec0 + rng.normal(0, 1.0 / 3600.0)
        obs.append(
            _make_obs(
                f"inj_wise_{seed}_e{idx}",
                jd,
                ra,
                dec,
                mag + rng.normal(0, 0.08),
                mission="WISE",
                filter_band="W1",
                mag_err=0.08,
                real_bogus=None,
            )
        )
    return tuple(obs)


def run_injection_recovery(n_inject: int = 20, seed: int = 0, mission: str = "ZTF") -> dict:
    """Run the injection-recovery test and return summary statistics.

    ``mission="ZTF"`` uses the original two-obs-per-night ZTF cadence.
    ``mission="WISE"`` uses the single-visit, multi-exposure NEOWISE cadence
    (Gate P1 discovery-source positive control) with no native real/bogus
    score, routed through detect.py's discovery-archive singleton path.
    """
    rng = np.random.default_rng(seed)

    n_detected = 0
    n_linked = 0
    n_scored = 0
    hazard_flags: list[str] = []

    for i in range(n_inject):
        motion = rng.uniform(0.1, 10.0)
        ra0 = rng.uniform(0.0, 359.0)
        dec0 = rng.uniform(-30.0, 30.0)

        if mission == "WISE":
            mag = rng.uniform(10.0, 14.0)
            obs = inject_synthetic_neo_wise(
                seed=seed * 1000 + i,
                ra0=ra0,
                dec0=dec0,
                motion_arcsec_per_hr=float(motion),
                mag=float(mag),
            )
        else:
            mag = rng.uniform(18.0, 21.0)
            obs = inject_synthetic_neo(
                seed=seed * 1000 + i,
                ra0=ra0,
                dec0=dec0,
                motion_arcsec_per_hr=float(motion),
                mag=float(mag),
            )

        detect_result = detect(obs, mpc_cross_match=False)
        if detect_result.candidates:
            n_detected += 1

        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)
        if link_result.tracklets:
            n_linked += 1

            t = link_result.tracklets[0]
            features = extract_features(t)
            orbital = fit_orbit(t)
            features_cls, posterior = classify(t, features)
            scored = score(t, features_cls, posterior, orbital)
            n_scored += 1
            hazard_flags.append(scored.hazard.hazard_flag)

    return {
        "n_injected": n_inject,
        "mission": mission,
        "n_detected": n_detected,
        "n_linked": n_linked,
        "n_scored": n_scored,
        "detection_rate": n_detected / max(n_inject, 1),
        "link_rate": n_linked / max(n_inject, 1),
        "score_rate": n_scored / max(n_inject, 1),
        "hazard_flag_counts": {
            flag: hazard_flags.count(flag)
            for flag in {"pha_candidate", "close_approach", "nominal", "unknown"}
        },
    }


def main() -> None:
    import json

    parser = argparse.ArgumentParser(description="NEO injection-recovery test")
    parser.add_argument("--n-inject", type=int, default=20, help="Number of NEOs to inject")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--survey",
        choices=["ZTF", "WISE"],
        default="ZTF",
        help="Source-native cadence to simulate. WISE uses the single-visit "
        "NEOWISE cadence for Gate P1 discovery-source positive control.",
    )
    parser.add_argument("--json", metavar="PATH", help="Save results as JSON to this path")
    args = parser.parse_args()

    print(
        f"Injection-recovery test: {args.n_inject} synthetic {args.survey} NEOs "
        f"(seed={args.seed})"
    )
    print("-" * 50)

    results = run_injection_recovery(n_inject=args.n_inject, seed=args.seed, mission=args.survey)

    n = results["n_injected"]
    print(f"Detection rate:  {results['detection_rate']:.1%}  ({results['n_detected']}/{n})")
    print(f"Link rate:       {results['link_rate']:.1%}  ({results['n_linked']}/{n})")
    print(f"Score rate:      {results['score_rate']:.1%}  ({results['n_scored']}/{n})")
    print()
    print("Hazard flag distribution (scored objects):")
    for flag, count in sorted(results["hazard_flag_counts"].items()):
        if count > 0:
            print(f"  {flag}: {count}")

    print("-" * 50)
    print("Done.")

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved → {args.json}")


if __name__ == "__main__":
    main()
