#!/usr/bin/env python
"""Gate Z5 -- "retrospective validation": evaluate historical-replay review
packets against the MPC known-object catalog *as queried today* (i.e.
after the replay window), bucketing each candidate into one of four
outcomes: recovered known object, later-confirmed object, artifact, or
unresolved candidate.

Per docs/ZTF_DR24_PRODUCTION_GATES.md's Gate Z5, this deliberately queries
MPC's *current* catalog -- using data from after the replay window is the
whole point of retrospective validation, and is a different, legitimate
use of "future" data from the no-future-catalog-leakage rule that governs
the replay/exclusion logic itself (src/known_object_exclusion.py). Nothing
here feeds back into replay-time candidate selection.

This intentionally does NOT depend on JPL SBDB's `first_obs` field, which
`src/known_object_exclusion.py` explicitly flags as "NOT YET
LIVE-VERIFIED" -- building a new gate on an unverified mechanism would
compound one guess onto another. Instead it reuses
Skills/check_mpc_known.py's already-real, already-used
`check_candidates_against_mpc` (`astroquery.mpc.MPC.query_objects_in_region`)
live sky-position cross-match, combined with each packet's own
already-computed `known_object_score` (was the object recognized as known
*during* replay) to distinguish the four outcomes:

- recovered_known_object: matches a real MPC object now, AND the pipeline
  already scored it high on known_object_score during replay (correctly
  recognized).
- later_confirmed_object: matches a real MPC object now, but the pipeline
  did NOT recognize it as known during replay (known_object_score low) --
  the single most important retrospective signal: something has since
  been confirmed/designated that this replay run did not already know
  about.
- artifact: no MPC match, and adversarial review REJECTed the candidate.
- unresolved_candidate: no MPC match, and adversarial review did not
  REJECT (SURVIVE/BORDERLINE), or no verdict was supplied.

Usage:
    PYTHONPATH=src uv run --python 3.14 python Skills/evaluate_retrospective_validation.py \\
        --review-packets Logs/pipeline_runs/run_archive_positive_control/report_with_packets.json \\
        --verdicts Logs/reports/adversarial_verdicts.json \\
        --out Logs/reports/retrospective_validation.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_mpc_known import check_candidates_against_mpc  # noqa: E402

from schemas import Observation  # noqa: E402

_KNOWN_SCORE_THRESHOLD = 0.5

_OUTCOMES = (
    "recovered_known_object",
    "later_confirmed_object",
    "artifact",
    "unresolved_candidate",
)

MpcLookupFn = Callable[[list[Observation], float], list[dict]]


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _mean_position_observation(packet: dict) -> Observation:
    """Build a synthetic single Observation at a tracklet's mean sky
    position/time, for feeding into the real MPC region cross-match --
    the same real API `Skills/check_mpc_known.py` already uses elsewhere,
    just called once per tracklet instead of once per raw detection."""
    obs_list = packet["tracklet"]["observations"]
    mean_ra = sum(o["ra_deg"] for o in obs_list) / len(obs_list)
    mean_dec = sum(o["dec_deg"] for o in obs_list) / len(obs_list)
    mean_jd = sum(o["jd"] for o in obs_list) / len(obs_list)
    return Observation(
        obs_id=packet["tracklet"]["object_id"],
        ra_deg=mean_ra,
        dec_deg=mean_dec,
        jd=mean_jd,
        mag=obs_list[0].get("mag", 99.0),
        mag_err=obs_list[0].get("mag_err", 0.1),
        filter_band=obs_list[0].get("filter_band", "r"),
        mission=obs_list[0].get("mission", "ZTF"),
    )


def classify_retrospective_outcome(
    known_object_score: float | None,
    mpc_matched: bool,
    verdict: str | None,
) -> str:
    """Bucket one candidate into one of the four Gate Z5 outcomes. See the
    module docstring for the full rationale behind each rule."""
    if mpc_matched and (known_object_score or 0.0) >= _KNOWN_SCORE_THRESHOLD:
        return "recovered_known_object"
    if mpc_matched:
        return "later_confirmed_object"
    if verdict == "REJECT":
        return "artifact"
    return "unresolved_candidate"


def run_retrospective_validation(
    review_packets: list[dict],
    verdicts_by_object_id: dict[str, str] | None = None,
    radius_deg: float = 0.05,
    mpc_lookup_fn: MpcLookupFn = check_candidates_against_mpc,
) -> dict:
    """Evaluate a list of ScoredNEO review-packet dicts against the current
    MPC catalog, bucketing each into one of the four Gate Z5 outcomes.

    ``verdicts_by_object_id`` should map each tracklet's ``object_id`` to
    an adversarial_review.py verdict string ("SURVIVE"/"BORDERLINE"/
    "REJECT"); candidates with no entry are treated as having no verdict
    (never bucketed as "artifact" purely from a missing verdict).
    """
    verdicts_by_object_id = verdicts_by_object_id or {}
    t0 = time.monotonic()

    outcomes: dict[str, list[str]] = {name: [] for name in _OUTCOMES}
    per_candidate: list[dict[str, Any]] = []

    for i, packet in enumerate(review_packets, start=1):
        object_id = packet["tracklet"]["object_id"]
        known_score = packet.get("features", {}).get("known_object_score")
        verdict = verdicts_by_object_id.get(object_id)

        synthetic_obs = _mean_position_observation(packet)
        mpc_results = mpc_lookup_fn([synthetic_obs], radius_deg)
        mpc_matched = bool(mpc_results) and mpc_results[0].get("mpc_match") is not None

        outcome = classify_retrospective_outcome(known_score, mpc_matched, verdict)
        outcomes[outcome].append(object_id)
        per_candidate.append(
            {
                "object_id": object_id,
                "outcome": outcome,
                "known_object_score": known_score,
                "verdict": verdict,
                "mpc_match": mpc_results[0].get("mpc_match") if mpc_results else None,
            }
        )
        print(
            f"[retro-validation] ({i}/{len(review_packets)}) {object_id}: {outcome}  "
            f"elapsed {_fmt_duration(time.monotonic() - t0)}",
            flush=True,
        )

    report = {
        "n_candidates": len(review_packets),
        "radius_deg": radius_deg,
        "outcome_counts": {name: len(ids) for name, ids in outcomes.items()},
        "outcomes": outcomes,
        "per_candidate": per_candidate,
        "elapsed_s": time.monotonic() - t0,
    }
    print(
        f"[retro-validation] Complete: {report['outcome_counts']}  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    return report


def _load_verdicts(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text())
    return {v["object_id"]: v["verdict"] for v in data if "object_id" in v and "verdict" in v}


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate Z5 retrospective validation")
    parser.add_argument("--review-packets", type=Path, required=True)
    parser.add_argument("--verdicts", type=Path, default=None)
    parser.add_argument("--radius-deg", type=float, default=0.05)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    review_packets = json.loads(args.review_packets.read_text())
    verdicts = _load_verdicts(args.verdicts) if args.verdicts else None

    report = run_retrospective_validation(
        review_packets, verdicts_by_object_id=verdicts, radius_deg=args.radius_deg
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"Report written to {args.out}")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
