#!/usr/bin/env python3
"""Build a fail-closed audit packet for a real pipeline run.

This tool reads the checkpoint and run summary emitted by ``Skills/run_pipeline.py``
and writes the observation-level evidence needed for T1-C human review. It does
not contact external services, submit observations, or assert impact probability.
The known-object recovery KPI remains blocked unless an expected-known-object
manifest with pipeline IDs or sky/time samples is supplied.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from schemas import Observation, Tracklet

_KNOWN_RECOVERY_THRESHOLD = 0.90
# Match the production adversarial-review hard lower bound. Slower linked arcs
# are treated as near-stationary/artifact-like and cannot advance to operator
# review.
_MIN_SOLAR_SYSTEM_MOTION_ARCSEC_PER_HOUR = 0.05
_LONG_ARC_DAYS = 30.0
_DEFAULT_MATCH_TOLERANCE_ARCSEC = 5.0
_DEFAULT_MATCH_TOLERANCE_DAYS = 0.02
_PASSING_OPERATOR_DECISIONS = {"acceptable"}
_BLOCKING_OPERATOR_DECISIONS = {"false_positive", "suspicious", "needs_followup"}


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _tracklet_from_dict(raw: dict[str, Any]) -> Tracklet:
    return Tracklet(
        object_id=str(raw["object_id"]),
        observations=tuple(Observation(**obs) for obs in raw.get("observations", [])),
        arc_days=float(raw.get("arc_days", 0.0)),
        motion_rate_arcsec_per_hour=float(raw.get("motion_rate_arcsec_per_hour", 0.0)),
        motion_pa_degrees=float(raw.get("motion_pa_degrees", 0.0)),
    )


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _mean(values: list[float]) -> float | None:
    return float(statistics.fmean(values)) if values else None


def _result_by_object_id(partial_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("object_id")): row for row in partial_results if row.get("object_id")}


def _review_flags(tracklet: Tracklet, result: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if tracklet.motion_rate_arcsec_per_hour < _MIN_SOLAR_SYSTEM_MOTION_ARCSEC_PER_HOUR:
        flags.append("below_min_solar_system_motion")
    if (
        tracklet.arc_days > _LONG_ARC_DAYS
        and tracklet.motion_rate_arcsec_per_hour < _MIN_SOLAR_SYSTEM_MOTION_ARCSEC_PER_HOUR
    ):
        flags.append("long_arc_near_stationary")
    if result.get("alert_pathway") not in {None, "internal_candidate", "known_object"}:
        flags.append("external_pathway_requires_protocol_review")
    if result.get("moid_au") is not None:
        flags.append("moid_present_requires_orbit_quality_review")
    return flags


def _tracklet_review_row(tracklet: Tracklet, result: dict[str, Any] | None) -> dict[str, Any]:
    observations = list(tracklet.observations)
    jds = [obs.jd for obs in observations]
    mags = [obs.mag for obs in observations]
    rb_values = [obs.real_bogus for obs in observations if obs.real_bogus is not None]
    drb_values = [obs.deep_real_bogus for obs in observations if obs.deep_real_bogus is not None]
    missions = Counter(obs.mission for obs in observations)
    filters = Counter(obs.filter_band for obs in observations)
    alerce_oids = sorted({obs.field_id for obs in observations if obs.field_id})

    result = result or {}
    review_flags = _review_flags(tracklet, result)
    return {
        "object_id": tracklet.object_id,
        "review_priority": "high" if review_flags else "standard",
        "review_flags": review_flags,
        "n_observations": len(observations),
        "n_nights": len({int(jd) for jd in jds}),
        "start_jd": min(jds) if jds else None,
        "end_jd": max(jds) if jds else None,
        "arc_days": tracklet.arc_days,
        "motion_rate_arcsec_per_hour": tracklet.motion_rate_arcsec_per_hour,
        "motion_pa_degrees": tracklet.motion_pa_degrees,
        "min_mag": min(mags) if mags else None,
        "median_mag": _median(mags),
        "max_mag": max(mags) if mags else None,
        "mean_real_bogus": _mean([float(v) for v in rb_values]),
        "mean_deep_real_bogus": _mean([float(v) for v in drb_values]),
        "missions": dict(missions),
        "filters": dict(filters),
        "alerce_object_ids": alerce_oids,
        "neo_probability": result.get("neo_probability"),
        "hazard_flag": result.get("hazard_flag"),
        "alert_pathway": result.get("alert_pathway"),
        "moid_au": result.get("moid_au"),
        "discovery_priority": result.get("discovery_priority"),
        "human_review_status": "required",
    }


def _load_expected_known(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if path.suffix.lower() == ".json":
        data = _load_json(path)
        if not isinstance(data, list):
            raise ValueError("expected-known JSON must contain a list")
        return [row for row in data if isinstance(row, dict)]
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_table(path: Path | None) -> list[dict[str, Any]]:
    """Load a JSON-list or CSV table; return an empty list when omitted."""
    if path is None:
        return []
    if path.suffix.lower() == ".json":
        data = _load_json(path)
        if not isinstance(data, list):
            raise ValueError(f"{path} JSON must contain a list")
        return [row for row in data if isinstance(row, dict)]
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _angular_sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Return great-circle separation in arcseconds for two sky positions."""
    ra1_rad = math.radians(ra1)
    ra2_rad = math.radians(ra2)
    dec1_rad = math.radians(dec1)
    dec2_rad = math.radians(dec2)
    sin_d_dec = math.sin((dec2_rad - dec1_rad) / 2.0)
    sin_d_ra = math.sin((ra2_rad - ra1_rad) / 2.0)
    hav = sin_d_dec**2 + math.cos(dec1_rad) * math.cos(dec2_rad) * sin_d_ra**2
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(max(0.0, hav))))) * 3600.0


def _coerce_float(value: Any) -> float | None:
    """Convert manifest values to float while treating blanks as missing."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_expected_samples(row: dict[str, Any]) -> list[dict[str, float]]:
    """Return validated RA/Dec/JD samples from a JSON or CSV manifest row."""
    raw_samples = row.get("samples")
    if isinstance(raw_samples, str) and raw_samples.strip():
        try:
            raw_samples = json.loads(raw_samples)
        except json.JSONDecodeError:
            raw_samples = None
    if not raw_samples:
        raw_samples = [row]

    samples: list[dict[str, float]] = []
    if not isinstance(raw_samples, list):
        return samples
    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        ra_value = sample.get("ra_deg") if "ra_deg" in sample else sample.get("ra")
        dec_value = sample.get("dec_deg") if "dec_deg" in sample else sample.get("dec")
        jd_value = sample.get("jd") if "jd" in sample else sample.get("expected_jd")
        ra = _coerce_float(ra_value)
        dec = _coerce_float(dec_value)
        jd = _coerce_float(jd_value)
        if ra is None or dec is None or jd is None:
            continue
        samples.append({"ra_deg": ra, "dec_deg": dec, "jd": jd})
    return samples


def _expected_key(row: dict[str, Any], index: int) -> str:
    """Return a stable expected-object key for audit output."""
    return str(
        row.get("designation")
        or row.get("object_id")
        or row.get("candidate_id")
        or f"expected_{index + 1}"
    )


def _match_expected_row(
    row: dict[str, Any],
    index: int,
    tracklets: list[Tracklet],
    review_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match one expected known object to recovered tracklets by ID or sky/time."""
    expected_id = row.get("object_id") or row.get("candidate_id")
    key = _expected_key(row, index)
    base: dict[str, Any] = {
        "expected_key": key,
        "designation": row.get("designation"),
        "status": "unmatched",
        "matched_object_id": None,
        "candidate_object_ids": [],
        "best_separation_arcsec": None,
        "best_time_delta_days": None,
        "matched_samples": 0,
        "required_samples": 1,
    }

    review_ids = {str(review["object_id"]) for review in review_rows}
    if expected_id:
        expected_id_str = str(expected_id)
        base["candidate_object_ids"] = [expected_id_str]
        if expected_id_str in review_ids:
            base["status"] = "matched"
            base["matched_object_id"] = expected_id_str
            base["matched_by"] = "pipeline_id"
        return base

    samples = _normalise_expected_samples(row)
    if not samples:
        base["status"] = "invalid_expected_row"
        base["error"] = "missing sky/time samples"
        return base

    tolerance_arcsec = (
        _coerce_float(row.get("tolerance_arcsec"))
        or _DEFAULT_MATCH_TOLERANCE_ARCSEC
    )
    tolerance_days = (
        _coerce_float(row.get("tolerance_days"))
        or _DEFAULT_MATCH_TOLERANCE_DAYS
    )
    required_samples = int(_coerce_float(row.get("min_samples")) or 1)
    base["required_samples"] = required_samples
    candidates: dict[str, dict[str, Any]] = {}

    for tracklet in tracklets:
        sample_matches = 0
        best_sep: float | None = None
        best_dt: float | None = None
        for sample in samples:
            sample_matched = False
            for obs in tracklet.observations:
                dt = abs(obs.jd - sample["jd"])
                if dt > tolerance_days:
                    continue
                sep = _angular_sep_arcsec(
                    sample["ra_deg"], sample["dec_deg"], obs.ra_deg, obs.dec_deg
                )
                if sep <= tolerance_arcsec:
                    sample_matched = True
                    best_sep = sep if best_sep is None else min(best_sep, sep)
                    best_dt = dt if best_dt is None else min(best_dt, dt)
            if sample_matched:
                sample_matches += 1
        if sample_matches >= required_samples:
            candidates[tracklet.object_id] = {
                "matched_samples": sample_matches,
                "best_separation_arcsec": best_sep,
                "best_time_delta_days": best_dt,
            }

    if not candidates:
        base["status"] = "unmatched"
        return base
    base["candidate_object_ids"] = sorted(candidates)
    if len(candidates) > 1:
        base["status"] = "ambiguous_match"
        return base

    matched_id, details = next(iter(candidates.items()))
    base["status"] = "matched"
    base["matched_object_id"] = matched_id
    base["matched_by"] = "sky_time"
    base.update(details)
    return base


def _expected_known_matches(
    expected_known: list[dict[str, Any]],
    tracklets: list[Tracklet],
    review_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match all expected known objects against recovered tracklets."""
    return [
        _match_expected_row(row, index, tracklets, review_rows)
        for index, row in enumerate(expected_known)
    ]


def _operator_review_gate(
    review_rows: list[dict[str, Any]],
    operator_review: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate citizen-science operator review rows for recovered candidates."""
    expected_ids = {str(row["object_id"]) for row in review_rows}
    if not review_rows:
        return {
            "status": "blocked_no_candidates_for_review",
            "reviewed": 0,
            "required": 0,
            "passed": False,
        }
    if not operator_review:
        return {
            "status": "blocked_no_operator_review",
            "reviewed": 0,
            "required": len(expected_ids),
            "missing_object_ids": sorted(expected_ids),
            "passed": False,
        }

    decisions: dict[str, str] = {}
    invalid_rows: list[dict[str, Any]] = []
    for row in operator_review:
        object_id = row.get("object_id")
        decision = str(row.get("decision", "")).strip().lower()
        if not object_id or decision not in (
            _PASSING_OPERATOR_DECISIONS | _BLOCKING_OPERATOR_DECISIONS
        ):
            invalid_rows.append(row)
            continue
        decisions[str(object_id)] = decision

    missing = sorted(expected_ids - set(decisions))
    blocking = {
        object_id: decision
        for object_id, decision in decisions.items()
        if object_id in expected_ids and decision in _BLOCKING_OPERATOR_DECISIONS
    }
    if invalid_rows:
        status = "blocked_invalid_operator_review"
    elif missing:
        status = "blocked_incomplete_operator_review"
    elif blocking:
        status = "blocked_operator_review_findings"
    else:
        status = "passed"
    return {
        "status": status,
        "reviewed": len(expected_ids - set(missing)),
        "required": len(expected_ids),
        "missing_object_ids": missing,
        "blocking_decisions": blocking,
        "allowed_decisions": sorted(
            _PASSING_OPERATOR_DECISIONS | _BLOCKING_OPERATOR_DECISIONS
        ),
        "passed": status == "passed",
    }


def _recovery_gate(
    expected_known: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    expected_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not expected_known:
        return {
            "status": "blocked_no_expected_known_manifest",
            "threshold": _KNOWN_RECOVERY_THRESHOLD,
            "recovered": 0,
            "expected": 0,
            "recovery_rate": None,
            "passed": False,
        }

    if expected_matches is None:
        recovered_ids = {str(row["object_id"]) for row in review_rows}
        expected_ids = set()
        designation_only = 0
        for row in expected_known:
            expected_id = row.get("object_id") or row.get("candidate_id")
            if expected_id:
                expected_ids.add(str(expected_id))
            elif row.get("designation"):
                designation_only += 1
        if not expected_ids:
            return {
                "status": "blocked_expected_manifest_missing_sky_time_samples",
                "threshold": _KNOWN_RECOVERY_THRESHOLD,
                "recovered": 0,
                "expected": len(expected_known),
                "recovery_rate": None,
                "designation_only": designation_only,
                "passed": False,
            }
        recovered = len(recovered_ids & expected_ids)
        expected = len(expected_ids)
        rate = recovered / expected if expected else 0.0
        return {
            "status": "evaluated",
            "threshold": _KNOWN_RECOVERY_THRESHOLD,
            "recovered": recovered,
            "expected": expected,
            "recovery_rate": rate,
            "designation_only": designation_only,
            "passed": expected > 0 and rate >= _KNOWN_RECOVERY_THRESHOLD,
        }

    expected = len(expected_matches)
    recovered = sum(1 for match in expected_matches if match["status"] == "matched")
    ambiguous = sum(1 for match in expected_matches if match["status"] == "ambiguous_match")
    invalid = sum(1 for match in expected_matches if match["status"] == "invalid_expected_row")
    rate = recovered / expected if expected else 0.0
    status = "evaluated"
    if invalid:
        status = "blocked_invalid_expected_manifest"
    elif ambiguous:
        status = "evaluated_with_ambiguous_matches"
    reported_rate = None if invalid else rate
    return {
        "status": status,
        "threshold": _KNOWN_RECOVERY_THRESHOLD,
        "recovered": recovered,
        "expected": expected,
        "recovery_rate": reported_rate,
        "ambiguous": ambiguous,
        "invalid": invalid,
        "unmatched": sum(1 for match in expected_matches if match["status"] == "unmatched"),
        "passed": (
            expected > 0
            and invalid == 0
            and ambiguous == 0
            and rate >= _KNOWN_RECOVERY_THRESHOLD
        ),
    }


def _same_night_diagnostic_subgate(
    tracklets: list[Tracklet],
    expected_known_provided: bool,
) -> dict[str, Any]:
    """Return diagnostic statistics about same-night vs multi-night tracklets.

    ALeRCE-backed ZTF pipelines produce only same-night tracklets (arc < 1 night).
    The multi-night production recovery gate requires multi-night arcs, so same-night
    runs cannot satisfy it. This subgate records the same-night evidence as citizen-
    science diagnostic output WITHOUT replacing the production gate.

    It passes only when same-night candidates exist AND no expected-known manifest
    was provided (because if a manifest is provided, the production gate already
    evaluated the evidence and blocking that gate is the correct signal).
    """
    n_same_night = 0
    n_multi_night = 0
    for tracklet in tracklets:
        # Count distinct integer JD nights spanned by this tracklet's observations.
        distinct_nights = len({int(obs.jd) for obs in tracklet.observations})
        if distinct_nights >= 2:
            n_multi_night += 1
        else:
            # Tracklet has all observations on a single calendar night.
            n_same_night += 1

    total = len(tracklets)
    fraction = n_same_night / total if total > 0 else None
    # subgate_applies: evidence is available and it is all same-night (no multi-night).
    subgate_applies = n_same_night > 0 and n_multi_night == 0
    # subgate_passed: applies AND no manifest was provided (so the multi-night
    # production gate hasn't rejected us on evidence — it's simply not run yet).
    subgate_passed = subgate_applies and not expected_known_provided
    return {
        "n_candidates": total,
        "n_same_night": n_same_night,
        "n_multi_night": n_multi_night,
        "fraction_same_night": fraction,
        "subgate_applies": subgate_applies,
        "subgate_passed": subgate_passed,
        "limitations": [
            "Same-night detection evidence only; does not satisfy multi-night "
            "production recovery gate.",
            "This subgate is citizen-science diagnostic evidence.",
            "No external submission authorized. No MPC report generated.",
        ],
    }


def build_audit_packet(
    run_dir: Path,
    expected_known_path: Path | None = None,
    operator_review_path: Path | None = None,
    same_night_ok: bool = False,
) -> dict[str, Any]:
    checkpoint_path = run_dir / "checkpoint.json"
    summary_path = run_dir / "run_summary.json"
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"missing checkpoint: {checkpoint_path}")

    checkpoint = _load_json(checkpoint_path)
    run_summary = _load_json(summary_path) if summary_path.exists() else {}
    tracklets = [_tracklet_from_dict(row) for row in checkpoint.get("tracklets", [])]
    results = _result_by_object_id(checkpoint.get("partial_results", []))
    review_rows = [_tracklet_review_row(tracklet, results.get(tracklet.object_id))
                   for tracklet in tracklets]
    expected_known = _load_expected_known(expected_known_path)
    expected_matches = _expected_known_matches(expected_known, tracklets, review_rows)
    recovery_gate = _recovery_gate(expected_known, review_rows, expected_matches)
    operator_review = _load_table(operator_review_path)
    operator_review_gate = _operator_review_gate(review_rows, operator_review)

    # Compute the same-night diagnostic subgate unconditionally.
    # This records citizen-science evidence for runs that only produce same-night
    # tracklets (e.g. ALeRCE-backed ZTF), without replacing the production gate.
    same_night_subgate = _same_night_diagnostic_subgate(
        tracklets,
        expected_known_provided=bool(expected_known_path),
    )

    promotion_blockers: list[str] = []
    promotion_notes: list[str] = []

    if not recovery_gate["passed"]:
        # Check whether the same-night subgate can stand in for the blocked
        # multi-night production gate. The subgate is accepted only when:
        #  1. same_night_ok=True was explicitly requested by the operator
        #  2. the subgate applies (there are same-night candidates, no multi-night ones)
        #  3. the subgate itself passed (no manifest provided — manifest presence
        #     means the production gate ran and genuinely failed the evidence)
        subgate_accepted = (
            same_night_ok
            and same_night_subgate["subgate_applies"]
            and same_night_subgate["subgate_passed"]
        )
        if not subgate_accepted:
            # Production gate blocked and subgate not accepted: add the blocker.
            promotion_blockers.append("known_object_recovery_gate_not_passed")
        else:
            # Subgate accepted in place of multi-night gate: record as a note,
            # not a blocker, so the operator understands the evidence source.
            promotion_notes.append("same_night_diagnostic_subgate_accepted")

    if not operator_review_gate["passed"]:
        promotion_blockers.append("citizen_science_operator_review_not_passed")

    return {
        "schema_version": "real-run-audit-v2",
        "run_dir": str(run_dir),
        "run_id": run_summary.get("run_id", run_dir.name),
        "run_summary": run_summary,
        "checkpoint_last_stage": checkpoint.get("last_stage"),
        "n_tracklets": len(tracklets),
        "n_review_rows": len(review_rows),
        "review_rows": review_rows,
        "expected_known_matches": expected_matches,
        "known_object_recovery_gate": recovery_gate,
        "same_night_diagnostic_subgate": same_night_subgate,
        "human_false_positive_review": {
            "status": operator_review_gate["status"],
            "n_candidates_for_review": len(review_rows),
            "reviewer": "Jerome W. Lindsey III, citizen-science project operator",
            "decision": None,
            "limitations": (
                "Operator review is citizen-science QA, not professional "
                "planetary-defense validation."
            ),
            "gate": operator_review_gate,
        },
        "citizen_science_limitations": [
            "No professional domain-expert validation is recorded.",
            "This packet does not authorize MPC submission or hazard notification.",
            "All impact-probability statements remain deferred to MPC/CNEOS.",
        ],
        "safety": {
            "no_external_submission": True,
            "no_mpc_submission": True,
            "no_nasa_pdco_notification": True,
            "no_impact_probability_asserted": True,
        },
        "production_promotion_allowed": not promotion_blockers,
        "production_promotion_blockers": promotion_blockers,
        "production_promotion_notes": promotion_notes,
    }


def write_review_csv(review_rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "object_id",
        "review_priority",
        "review_flags",
        "n_observations",
        "n_nights",
        "start_jd",
        "end_jd",
        "arc_days",
        "motion_rate_arcsec_per_hour",
        "motion_pa_degrees",
        "min_mag",
        "median_mag",
        "max_mag",
        "mean_real_bogus",
        "mean_deep_real_bogus",
        "neo_probability",
        "hazard_flag",
        "alert_pathway",
        "moid_au",
        "discovery_priority",
        "alerce_object_ids",
        "human_review_status",
    ]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in review_rows:
            clean_row = {name: row.get(name) for name in fieldnames}
            for name in ("review_flags", "alerce_object_ids"):
                if isinstance(clean_row.get(name), list):
                    clean_row[name] = ";".join(str(value) for value in clean_row[name])
            writer.writerow(clean_row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a real-run T1-C audit packet")
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="Pipeline run directory containing checkpoint.json")
    parser.add_argument("--report-out", type=Path, required=True,
                        help="Output JSON audit report path")
    parser.add_argument("--review-csv", type=Path, default=None,
                        help="Optional human-review CSV output path")
    parser.add_argument("--expected-known", type=Path, default=None,
                        help="Optional expected-known manifest JSON/CSV for recovery KPI")
    parser.add_argument("--operator-review", type=Path, default=None,
                        help="Optional operator review JSON/CSV for candidate QA")
    parser.add_argument(
        "--same-night-ok",
        action="store_true",
        default=False,
        help=(
            "Accept same-night detection evidence as a diagnostic subgate when all "
            "tracklets are single-night (e.g. ALeRCE-backed ZTF runs) and no "
            "expected-known manifest is provided. Does not authorize MPC submission."
        ),
    )
    args = parser.parse_args()

    packet = build_audit_packet(
        args.run_dir,
        args.expected_known,
        args.operator_review,
        same_night_ok=args.same_night_ok,
    )
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    if args.review_csv is not None:
        write_review_csv(packet["review_rows"], args.review_csv)

    gate = packet["known_object_recovery_gate"]
    subgate = packet["same_night_diagnostic_subgate"]
    print(f"Audit packet written: {args.report_out}")
    if args.review_csv is not None:
        print(f"Review CSV written : {args.review_csv}")
    print(f"Tracklets reviewed : {packet['n_review_rows']}")
    print(f"Recovery gate      : {gate['status']} (passed={gate['passed']})")
    print(
        f"Same-night subgate : applies={subgate['subgate_applies']} "
        f"passed={subgate['subgate_passed']} "
        f"(n_same_night={subgate['n_same_night']} n_multi_night={subgate['n_multi_night']})"
    )
    print("No external submission performed.")


if __name__ == "__main__":
    main()
