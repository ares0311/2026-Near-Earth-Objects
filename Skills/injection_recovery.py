#!/usr/bin/env python
"""Injection-recovery test for the NEO detection pipeline.

Injects synthetic moving objects into a background of real observations and
measures how many are successfully detected, linked, classified, and scored.

Usage:
    PYTHONPATH=src python Skills/injection_recovery.py [--n-inject 50] [--seed 42]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
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


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


_CHECKPOINT_ROOT = Path("Logs/pipeline_runs/injection_recovery")


def _checkpoint_key(n_inject: int, seed: int, mission: str) -> str:
    """Stable checkpoint key from the exact run parameters, so re-running the
    identical command finds and resumes the existing checkpoint instead of
    starting over (checkpoint/resume standing rule)."""
    payload = json.dumps({"n_inject": n_inject, "seed": seed, "mission": mission}, sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write a checkpoint atomically (write-then-rename) so a kill mid-write
    never leaves a corrupt/unparseable checkpoint file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


def run_injection_recovery(
    n_inject: int = 20,
    seed: int = 0,
    mission: str = "ZTF",
    review_packet_out: Path | None = None,
    checkpoint_root: Path | None = None,
) -> dict:
    """Run the injection-recovery test and return summary statistics.

    ``mission="ZTF"`` uses the original two-obs-per-night ZTF cadence.
    ``mission="WISE"`` uses the single-visit, multi-exposure NEOWISE cadence
    (Gate P1 discovery-source positive control) with no native real/bogus
    score, routed through detect.py's discovery-archive singleton path.

    If ``review_packet_out`` is given, every recovered candidate's full
    ``ScoredNEO`` packet is written to that path as a JSON list — the same
    format ``Skills/run_pipeline.py --review-packet-out`` produces, so the
    output can feed ``Skills/adversarial_review.py`` and
    ``Skills/export_ades_report.py`` for the Gate P3 no-submission drill.

    Checkpoints after every item to ``<checkpoint_root>/<key>/checkpoint.json``
    (key derived from n_inject/seed/mission), including the RNG's own
    serializable bit-generator state, so a kill/sleep mid-run and re-running
    the identical command resumes from the next un-completed item instead of
    losing prior work or silently diverging from a from-scratch run.
    """
    root = checkpoint_root if checkpoint_root is not None else _CHECKPOINT_ROOT
    key = _checkpoint_key(n_inject, seed, mission)
    checkpoint_path = root / key / "checkpoint.json"

    rng = np.random.default_rng(seed)

    n_detected = 0
    n_linked = 0
    n_scored = 0
    hazard_flags: list[str] = []
    review_packets: list[dict] = []
    start_i = 0

    if checkpoint_path.exists():
        state = json.loads(checkpoint_path.read_text())
        start_i = state["completed"]
        n_detected = state["n_detected"]
        n_linked = state["n_linked"]
        n_scored = state["n_scored"]
        hazard_flags = state["hazard_flags"]
        review_packets = state["review_packets"]
        rng.bit_generator.state = state["rng_state"]
        print(
            f"[resume] loaded checkpoint: {start_i}/{n_inject} items already "
            f"completed, continuing from item {start_i + 1}",
            flush=True,
        )

    t0 = time.monotonic()

    for i in range(start_i, n_inject):
        elapsed = time.monotonic() - t0
        # Use items completed in THIS run (not the absolute index) for the
        # rate estimate -- after a resume, i starts far above 0 while
        # elapsed restarts at 0, so dividing by i would produce a wildly
        # wrong near-zero ETA immediately after resuming.
        items_done_this_run = i - start_i
        per_item = elapsed / max(items_done_this_run, 1)
        eta = per_item * (n_inject - i)
        print(
            f"[injection] ({i + 1}/{n_inject}) mission={mission}  "
            f"detected={n_detected} linked={n_linked} scored={n_scored}  "
            f"elapsed {_fmt_duration(elapsed)}  ETA {_fmt_duration(eta)}",
            flush=True,
        )
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
            # Always accumulate internally (not gated on review_packet_out)
            # so a checkpoint saved on a run without --review-packet-out can
            # still be resumed correctly by a later run that requests it.
            review_packets.append(scored.model_dump(mode="json"))

        _atomic_write_json(
            checkpoint_path,
            {
                "n_inject": n_inject,
                "seed": seed,
                "mission": mission,
                "completed": i + 1,
                "n_detected": n_detected,
                "n_linked": n_linked,
                "n_scored": n_scored,
                "hazard_flags": hazard_flags,
                "review_packets": review_packets,
                "rng_state": rng.bit_generator.state,
            },
        )

    print(
        f"[injection] Complete: {n_inject} injected  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    if review_packet_out is not None:
        review_packet_out.parent.mkdir(parents=True, exist_ok=True)
        review_packet_out.write_text(json.dumps(review_packets, indent=2))
        print(
            f"Review packets written to {review_packet_out} "
            f"({len(review_packets)} packet(s))"
        )

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
    parser.add_argument(
        "--review-packet-out",
        metavar="PATH",
        help="Write full ScoredNEO review packets (JSON list) to this path, "
        "consumable by Skills/adversarial_review.py and "
        "Skills/export_ades_report.py for a Gate P3 no-submission drill.",
    )
    args = parser.parse_args()

    print(
        f"Injection-recovery test: {args.n_inject} synthetic {args.survey} NEOs "
        f"(seed={args.seed})"
    )
    print("-" * 50)

    results = run_injection_recovery(
        n_inject=args.n_inject,
        seed=args.seed,
        mission=args.survey,
        review_packet_out=Path(args.review_packet_out) if args.review_packet_out else None,
    )

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
