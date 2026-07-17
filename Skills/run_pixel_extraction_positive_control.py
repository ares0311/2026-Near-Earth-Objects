#!/usr/bin/env python
"""Motion-product-pivot cross-night linking test: load real Observation
checkpoints written by Skills/convert_pixel_extraction_to_observations.py
and run them through preprocess() -> link(), reporting whether the linker
recovers any real multi-night tracklet from source-native pixel-extracted
candidates.

Why this does not reuse Skills/run_archive_positive_control.py's
preprocess() -> detect() -> link() chain verbatim: detect.py's ZTF path
(`_find_moving_sources`) pairs observations WITHIN a single night by
computing a motion rate between two same-night detections -- structurally
impossible here, because each "night" from the pixel-extraction pilot is
exactly one exposure (one JD), not the multiple same-night ZTF alert-broker
exposures that path was designed for. detect.py's other path
(`_preserve_discovery_archive_singletons`, which preserves each detection
as its own 1-observation candidate for the *cross-night* linker to handle)
is exactly the right shape for this data, but is gated to
`mission in {"WISE", "DECam", "TESS"}` -- extending that gate to include
"ZTF" would change detect.py's behavior for the entire existing ZTF
alert-broker code path (real observations without `field_id` set would
newly take a different route through detect()), a real regression risk
across 2000+ existing tests for a change out of scope for this diagnostic
run. Root-caused live: the first attempt at this positive control got
0/471 candidates from detect() for exactly this mission-gating reason, not
because nothing in the data was candidate-worthy.

This script performs the same singleton-wrapping `_preserve_discovery_
archive_singletons` already does (one candidate per surviving observation,
no motion rate computed yet -- link() computes that across nights), just
without gating on mission, and calls the same `link()` function
run_archive_positive_control.py uses. It does not modify detect.py.

This step is diagnostic only: it does not classify, score, or submit
anything, and it must never claim "confirmed NEO" -- it only reports
whether the linker recovered >=1 tracklet.

Usage:
    caffeinate -i uv run --python 3.14 python \\
        Skills/run_pixel_extraction_positive_control.py \\
        --nights 20180802 20180806 20180809 \\
        --checkpoint-dir Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_DEFAULT_CHECKPOINT_DIR = Path("Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control")


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def load_observations_from_checkpoints(nights: list[str], checkpoint_dir: Path):
    """Same checkpoint format/loading contract as
    Skills/run_archive_positive_control.py's identically-named function."""
    from schemas import Observation

    observations = []
    for night in nights:
        path = checkpoint_dir / f"{night}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No checkpoint found for night {night} at {path} -- run "
                "Skills/convert_pixel_extraction_to_observations.py for this night first."
            )
        state = json.loads(path.read_text())
        n_kept = state.get("kept_count", 0)
        print(f"[control] {night}: loading {n_kept} real observation(s) from {path}", flush=True)
        for obs_dict in state.get("observations", []):
            observations.append(Observation(**obs_dict))
    return observations


def run_positive_control(
    nights: list[str], checkpoint_dir: Path, min_observations: int = 3
) -> dict:
    """preprocess() every real observation, wrap each surviving one as its
    own 1-observation RawCandidate (mission-agnostic version of detect.py's
    `_preserve_discovery_archive_singletons`), then run the real link()."""
    from link import link
    from preprocess import preprocess
    from schemas import RawCandidate

    t0 = time.monotonic()
    observations = load_observations_from_checkpoints(nights, checkpoint_dir)
    print(
        f"[control] Loaded {len(observations)} real observation(s) across "
        f"{len(nights)} real night(s)  elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    if not observations:
        raise ValueError(
            "No real observations loaded -- cannot run a positive control "
            "with zero input observations."
        )

    prep_result = preprocess(tuple(observations), apply_astrometry=False)
    print(
        f"[control] preprocess: {prep_result.provenance.n_sources_out}/"
        f"{prep_result.provenance.n_sources_in} sources passed  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    candidates = tuple(
        RawCandidate(
            candidate_id=str(uuid.uuid4()),
            observations=(obs,),
            apparent_motion_arcsec_per_hr=None,
            motion_pa_deg=None,
            is_streak=False,
        )
        for obs in prep_result.sources
    )
    print(
        f"[control] wrapped {len(candidates)} candidate(s) for cross-night linking  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    link_result = link(candidates, min_observations=min_observations)
    n_tracklets = link_result.provenance.n_tracklets
    print(
        f"[control] link: {n_tracklets} tracklet(s) formed "
        f"(min_observations={min_observations})  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    tracklet_summaries = []
    for trk in link_result.tracklets:
        nights_in_trk = sorted({int(o.jd - 0.5) for o in trk.observations})
        obs_sorted = sorted(trk.observations, key=lambda o: o.jd)
        tracklet_summaries.append(
            {
                "object_id": trk.object_id,
                "n_observations": len(trk.observations),
                "n_nights": len(nights_in_trk),
                "arc_days": trk.arc_days,
                "motion_rate_arcsec_per_hour": trk.motion_rate_arcsec_per_hour,
                "motion_pa_degrees": trk.motion_pa_degrees,
                "observations": [
                    {"ra_deg": o.ra_deg, "dec_deg": o.dec_deg, "jd": o.jd} for o in obs_sorted
                ],
            }
        )
        print(
            f"[control]   tracklet {trk.object_id}: {len(trk.observations)} obs across "
            f"{len(nights_in_trk)} night(s), arc={trk.arc_days:.2f}d, "
            f"rate={trk.motion_rate_arcsec_per_hour:.2f} arcsec/hr",
            flush=True,
        )

    report = {
        "nights": nights,
        "min_observations": min_observations,
        "n_observations_loaded": len(observations),
        "n_sources_preprocessed": prep_result.provenance.n_sources_out,
        "n_candidates_wrapped": len(candidates),
        "n_tracklets_linked": n_tracklets,
        "tracklets": tracklet_summaries,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }

    if n_tracklets == 0:
        print(
            "[control] RESULT: no tracklet recovered from source-native pixel-extracted "
            "candidates across these nights.",
            flush=True,
        )
    else:
        print(
            f"[control] RESULT: {n_tracklets} tracklet(s) recovered from real "
            "pixel-extracted candidates across >=2 real nights. This does NOT confirm "
            "object identity or claim a discovery; it only confirms the linker recovers "
            "a linkable tracklet from this source-native candidate set.",
            flush=True,
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--nights", nargs="+", required=True)
    parser.add_argument("--checkpoint-dir", type=Path, default=_DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--min-observations", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = run_positive_control(args.nights, args.checkpoint_dir, args.min_observations)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"[control] Wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
