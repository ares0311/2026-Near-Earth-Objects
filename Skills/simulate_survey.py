"""Simulate a ZTF-like survey over a sky region and generate synthetic observations.

Produces a JSON file of :class:`Observation` dicts that can be fed directly
into the pipeline (preprocess → detect → link → ...).

Usage:
    python Skills/simulate_survey.py [--ra 180.0] [--dec 0.0] [--radius 2.0]
        [--nights 3] [--objects 5] [--seed 42] [--out data/sim_survey.json]

Each simulated NEO moves with a random linear proper motion sampled from the
expected NEO motion distribution (0.5–50 arcsec/hr).  Each night produces 2
observations separated by ~30 minutes.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schemas import Observation  # noqa: E402

_JD_START = 2460000.0  # arbitrary reference epoch
_NIGHT_SPACING_DAYS = 1.0
_INTRA_NIGHT_SPACING_HR = 0.5
_MAG_BASE = 19.5
_MAG_SIGMA = 1.5
_RB_DEFAULT = 0.85


def _simulate_object(
    ra0: float,
    dec0: float,
    radius_deg: float,
    nights: int,
    rng: random.Random,
) -> list[Observation]:
    """Generate observations for one synthetic NEO."""
    # Random starting position within the field
    r_off = radius_deg * math.sqrt(rng.random())
    theta = rng.uniform(0, 2 * math.pi)
    ra = (ra0 + r_off * math.cos(theta)) % 360.0
    dec = max(-90.0, min(90.0, dec0 + r_off * math.sin(theta)))

    # Random proper motion
    motion_rate_arcsec_hr = rng.uniform(0.5, 50.0)
    pa_rad = rng.uniform(0, 2 * math.pi)
    dra_per_hr = motion_rate_arcsec_hr * math.sin(pa_rad) / 3600.0  # deg/hr
    ddec_per_hr = motion_rate_arcsec_hr * math.cos(pa_rad) / 3600.0

    mag = rng.gauss(_MAG_BASE, _MAG_SIGMA)
    mag = max(14.0, min(24.0, mag))
    filter_band = rng.choice(["r", "g", "i"])
    obj_id = str(uuid.uuid4())

    obs_list: list[Observation] = []
    for night in range(nights):
        base_jd = _JD_START + night * _NIGHT_SPACING_DAYS
        for obs_idx in range(2):
            dt_hr = obs_idx * _INTRA_NIGHT_SPACING_HR
            jd = base_jd + dt_hr / 24.0
            elapsed_hr = night * 24.0 + dt_hr
            obs_ra = ra + dra_per_hr * elapsed_hr
            obs_dec = dec + ddec_per_hr * elapsed_hr
            obs_dec = max(-90.0, min(90.0, obs_dec))
            obs_ra = obs_ra % 360.0
            mag_obs = mag + rng.gauss(0, 0.05)
            obs = Observation(
                obs_id=f"sim_{obj_id[:8]}_{night}_{obs_idx}",
                ra_deg=round(obs_ra, 6),
                dec_deg=round(obs_dec, 6),
                jd=round(jd, 6),
                mag=round(mag_obs, 3),
                mag_err=round(rng.uniform(0.02, 0.15), 3),
                filter_band=filter_band,
                mission="ZTF",
                real_bogus=round(rng.uniform(0.70, 0.99), 3),
                deep_real_bogus=round(rng.uniform(0.70, 0.99), 3),
            )
            obs_list.append(obs)
    return obs_list


def simulate_survey(
    ra: float = 180.0,
    dec: float = 0.0,
    radius_deg: float = 2.0,
    nights: int = 3,
    n_objects: int = 5,
    seed: int = 42,
) -> list[Observation]:
    """Generate synthetic observations for a simulated NEO survey.

    Returns a flat list of :class:`Observation` objects from all simulated NEOs,
    shuffled to mimic the order alerts arrive from a real survey stream.
    """
    rng = random.Random(seed)
    all_obs: list[Observation] = []
    for _ in range(n_objects):
        all_obs.extend(_simulate_object(ra, dec, radius_deg, nights, rng))
    rng.shuffle(all_obs)
    return all_obs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Simulate a ZTF-like survey.")
    parser.add_argument("--ra", type=float, default=180.0, help="Field centre RA (deg)")
    parser.add_argument("--dec", type=float, default=0.0, help="Field centre Dec (deg)")
    parser.add_argument("--radius", type=float, default=2.0, help="Field radius (deg)")
    parser.add_argument("--nights", type=int, default=3, help="Number of nights")
    parser.add_argument("--objects", type=int, default=5, help="Number of synthetic NEOs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", default="data/sim_survey.json",
                        help="Output JSON path (default: data/sim_survey.json)")
    args = parser.parse_args(argv)

    observations = simulate_survey(
        ra=args.ra,
        dec=args.dec,
        radius_deg=args.radius,
        nights=args.nights,
        n_objects=args.objects,
        seed=args.seed,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([o.model_dump() for o in observations], indent=2))
    print(f"Wrote {len(observations)} observations ({args.objects} objects × "
          f"{args.nights} nights × 2 obs) to {out_path}")


if __name__ == "__main__":
    main()
