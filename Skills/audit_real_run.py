#!/usr/bin/env python3
"""Build a fail-closed audit packet for a real pipeline run.

This tool reads the checkpoint and run summary emitted by ``Skills/run_pipeline.py``
and writes the observation-level evidence needed for T1-C human review. It does
not contact external services, submit observations, or assert impact probability.
The known-object recovery KPI remains blocked unless an expected-known-object
manifest is supplied by a domain reviewer.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from schemas import Observation, Tracklet

_KNOWN_RECOVERY_THRESHOLD = 0.90
_MIN_SOLAR_SYSTEM_MOTION_ARCSEC_PER_HOUR = 0.01
_LONG_ARC_DAYS = 30.0


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


def _recovery_gate(
    expected_known: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
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
            "status": "blocked_expected_manifest_missing_pipeline_ids",
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


def build_audit_packet(
    run_dir: Path,
    expected_known_path: Path | None = None,
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
    recovery_gate = _recovery_gate(expected_known, review_rows)

    return {
        "schema_version": "real-run-audit-v1",
        "run_dir": str(run_dir),
        "run_id": run_summary.get("run_id", run_dir.name),
        "run_summary": run_summary,
        "checkpoint_last_stage": checkpoint.get("last_stage"),
        "n_tracklets": len(tracklets),
        "n_review_rows": len(review_rows),
        "review_rows": review_rows,
        "known_object_recovery_gate": recovery_gate,
        "human_false_positive_review": {
            "status": "required",
            "n_candidates_for_review": len(review_rows),
            "reviewer": None,
            "decision": None,
        },
        "safety": {
            "no_external_submission": True,
            "no_mpc_submission": True,
            "no_nasa_pdco_notification": True,
            "no_impact_probability_asserted": True,
        },
        "production_promotion_allowed": bool(
            recovery_gate["passed"] and len(review_rows) > 0
        ),
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
    args = parser.parse_args()

    packet = build_audit_packet(args.run_dir, args.expected_known)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    if args.review_csv is not None:
        write_review_csv(packet["review_rows"], args.review_csv)

    gate = packet["known_object_recovery_gate"]
    print(f"Audit packet written: {args.report_out}")
    if args.review_csv is not None:
        print(f"Review CSV written : {args.review_csv}")
    print(f"Tracklets reviewed : {packet['n_review_rows']}")
    print(f"Recovery gate      : {gate['status']} (passed={gate['passed']})")
    print("No external submission performed.")


if __name__ == "__main__":
    main()
