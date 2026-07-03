#!/usr/bin/env python
"""Gate Z3 -- "known-object positive control": load real per-source alert
archive checkpoints for >=2 real nights and run them through the real
production pipeline (preprocess -> detect -> link) to check whether the
linker recovers a multi-night tracklet from real archived ZTF alerts.

Per docs/ZTF_DR24_PRODUCTION_GATES.md's Gate Z3, this loader must not be
built until a Skills/ztf_alert_archive_ingest.py run has produced real
detections on >=2 real nights in the same sky region -- do not run this
against synthetic or single-night data expecting a real tracklet.

Reads checkpoint JSON files written by Skills/ztf_alert_archive_ingest.py
(<out-dir>/<night>.json, each a dict with a top-level "observations" list
of dicts matching src/schemas.py's Observation constructor kwargs exactly
-- the same format that script writes, not a guessed schema). Builds real
Observation objects, then chains preprocess() -> detect() -> link() using
the exact same call pattern as Skills/run_pipeline.py's production path
(preprocess(..., apply_astrometry=False), detect(prep.sources), then
link(det.candidates)).

This step is diagnostic only: it does not classify, score, or submit
anything, and it must never claim "confirmed NEO" -- it only reports
whether the linker recovered >=1 tracklet, and if so, the tracklet's basic
arc/night statistics for operator review.

Offline verification (using the exact synthetic-tracklet generator already
proven to link in Skills/injection_recovery.py's baseline) found that
`link()`'s default `min_observations=3` can reject a genuine 2-night
tracklet outright when each night contributes only 1-2 observations to the
final linked arc -- this is a real parameter-sensitivity finding, not a
guess: 20/20 synthetic 2-night seeds failed to link at the default
min_observations=3, but 20/20 linked successfully at min_observations=2.
Real archived data has far more observations per night (21 on night
20180809 alone) so the default is likely fine, but `--min-observations` is
exposed here so a zero-tracklet result can be re-checked at a lower
(still principled, not arbitrarily permissive) threshold before concluding
the positive control failed.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \\
        --nights 20180809 20180903 \\
        --checkpoint-dir Logs/pipeline_runs/ztf_alert_archive_ingest
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_DEFAULT_CHECKPOINT_DIR = Path("Logs/pipeline_runs/ztf_alert_archive_ingest")


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def load_observations_from_checkpoints(nights: list[str], checkpoint_dir: Path):
    """Load real Observation objects from Skills/ztf_alert_archive_ingest.py's
    per-night checkpoint files. Fails closed (raises) if a requested night's
    checkpoint is missing, rather than silently proceeding on partial data."""
    from schemas import Observation  # lazy import, matches project convention

    observations = []
    for night in nights:
        path = checkpoint_dir / f"{night}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No checkpoint found for night {night} at {path} -- run "
                "Skills/ztf_alert_archive_ingest.py for this night first."
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
    """Run the real preprocess -> detect -> link chain on real per-source
    observations loaded from >=2 real archived nights, reporting whether
    any multi-night tracklet was recovered. min_observations is link()'s
    own default (3) unless overridden -- see the module docstring for why
    this matters for exactly-2-night arcs."""
    from detect import detect
    from link import link
    from preprocess import preprocess

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

    det_result = detect(prep_result.sources)
    print(
        f"[control] detect: {det_result.provenance.n_candidates} candidate(s), "
        f"{det_result.provenance.n_known_matches} known match(es)  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    link_result = link(det_result.candidates, min_observations=min_observations)
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
        tracklet_summaries.append(
            {
                "object_id": trk.object_id,
                "n_observations": len(trk.observations),
                "n_nights": len(nights_in_trk),
                "arc_days": trk.arc_days,
                "motion_rate_arcsec_per_hour": trk.motion_rate_arcsec_per_hour,
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
        "n_candidates_detected": det_result.provenance.n_candidates,
        "n_known_matches": det_result.provenance.n_known_matches,
        "n_tracklets_linked": n_tracklets,
        "tracklets": tracklet_summaries,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }

    if n_tracklets == 0:
        print(
            "[control] RESULT: no tracklet recovered -- positive control did "
            "not succeed with this night pair/sky region at "
            f"min_observations={min_observations}. If real per-night observation "
            "counts are low, re-run with --min-observations 2 before concluding "
            "failure (see module docstring for why this matters).",
            flush=True,
        )
    else:
        print(
            f"[control] RESULT: {n_tracklets} tracklet(s) recovered from real "
            "archived alerts across >=2 real nights -- Gate Z3 known-object "
            "positive control mechanically exercised. This does NOT confirm "
            "object identity or claim a discovery; it only confirms the "
            "detect->link pipeline recovers a linkable tracklet from real "
            "per-source data.",
            flush=True,
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--nights",
        nargs="+",
        required=True,
        help="Real nights (YYYYMMDD) to load, each must already have a "
        "checkpoint from Skills/ztf_alert_archive_ingest.py.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=_DEFAULT_CHECKPOINT_DIR,
        help=f"Directory containing <night>.json checkpoints (default: "
        f"{_DEFAULT_CHECKPOINT_DIR}).",
    )
    parser.add_argument(
        "--min-observations",
        type=int,
        default=3,
        help="Minimum observations per linked tracklet, passed to link() "
        "(default: 3, link()'s own default). See module docstring: a "
        "genuine 2-night tracklet with few observations per night can be "
        "rejected at the default threshold even when it is real.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write the full JSON report.",
    )
    args = parser.parse_args()

    if len(args.nights) < 2:
        raise SystemExit(
            "--nights requires >=2 nights for a known-object positive control "
            "(a single night cannot form a multi-night tracklet)."
        )

    report = run_positive_control(args.nights, args.checkpoint_dir, args.min_observations)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"[control] Wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
