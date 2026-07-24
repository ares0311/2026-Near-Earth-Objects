#!/usr/bin/env python3
"""Audit the transparent field-ranking policy against real historical outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import select_survey_fields as selector
from validate_field_null_outcomes import validate_null_outcomes

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "ztf-field-ranking-retrospective-audit-v1"
POSITIVE_SCHEMA_VERSION = "mpc-discovery-field-calibration-v2"
DEFAULT_POSITIVES = (
    ROOT / "data_selection/calibration/mpc_aten_discovery_fields_v2.json",
    ROOT / "data_selection/calibration/mpc_atira_discovery_fields_v2.json",
)
DEFAULT_NULLS = ROOT / "data_selection/calibration/ztf_field_null_outcomes_v1.json"
DEFAULT_POLICY = ROOT / "data_selection/ranking_policies/ztf_field_ranking_v2.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _load_positive_envelope(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != POSITIVE_SCHEMA_VERSION:
        raise ValueError(f"unsupported positive-event schema: {path}")
    if (
        payload.get("status") != "complete"
        or payload.get("summary", {}).get("complete") is not True
    ):
        raise ValueError(f"positive-event envelope is not complete: {path}")
    selected = payload.get("selection", {}).get("selected")
    events = payload.get("events")
    if not isinstance(selected, list) or not isinstance(events, list) or not events:
        raise ValueError(f"positive-event envelope is empty: {path}")
    if len(events) != len(selected) or len(events) != payload["summary"].get("accepted_count"):
        raise ValueError(f"positive-event counts disagree: {path}")
    selected_ids = {str(row.get("designation")) for row in selected}
    event_ids = [str(row.get("designation")) for row in events]
    if len(set(event_ids)) != len(event_ids) or set(event_ids) != selected_ids:
        raise ValueError(f"positive-event identities disagree: {path}")
    return payload


def _score_field(
    ra_deg: float,
    dec_deg: float,
    jd: float,
    mode: str,
    weights: dict[str, float],
) -> dict[str, Any]:
    ra = np.array([ra_deg], dtype=float)
    dec = np.array([dec_deg], dtype=float)
    sun_ra, sun_dec = selector.get_sun_position(jd)
    elongation = selector.elongation_batch(ra, dec, sun_ra, sun_dec)
    ecliptic_latitude = selector.ecliptic_latitude_batch(ra, dec)
    hours = selector.hours_visible_batch(dec, selector._PALOMAR_LAT)
    scarcity = selector.survey_scarcity_score_batch(elongation, mode)
    population = selector.population_score_batch(ecliptic_latitude, elongation, mode)
    geometry = selector.geometry_score_batch(elongation, hours, mode)
    eligible = selector.eligibility_mask_batch(elongation, hours, mode)
    score = (
        weights["scarcity"] * scarcity[0]
        + weights["population"] * population[0]
        + weights["geometry"] * geometry[0]
        + weights["novelty"]
    )
    return {
        "score": round(float(score), 6),
        "eligible": bool(eligible[0]),
        "survey_scarcity_score": round(float(scarcity[0]), 6),
        "population_score": round(float(population[0]), 6),
        "geometry_score": round(float(geometry[0]), 6),
        "novelty_score": 1.0,
        "elongation_deg": round(float(elongation[0]), 6),
        "ecliptic_latitude_deg": round(float(ecliptic_latitude[0]), 6),
        "hours_visible": round(float(hours[0]), 6),
    }


def _pairwise_auc(positives: list[float], negatives: list[float]) -> float | None:
    if not positives or not negatives:
        return None
    wins = sum(
        1.0 if positive > negative else 0.5 if positive == negative else 0.0
        for positive in positives
        for negative in negatives
    )
    return round(wins / (len(positives) * len(negatives)), 6)


def _metric_slice(records: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [row for row in records if row["outcome"] == "positive"]
    negatives = [row for row in records if row["outcome"] == "null_result"]
    eligible_positives = [row for row in positives if row["features"]["eligible"]]
    eligible_negatives = [row for row in negatives if row["features"]["eligible"]]
    return {
        "positive_count": len(positives),
        "positive_eligible_count": len(eligible_positives),
        "positive_eligibility_recall": (
            round(len(eligible_positives) / len(positives), 6) if positives else None
        ),
        "searched_null_count": len(negatives),
        "searched_null_eligible_count": len(eligible_negatives),
        "eligible_pairwise_auc": _pairwise_auc(
            [row["features"]["score"] for row in eligible_positives],
            [row["features"]["score"] for row in eligible_negatives],
        ),
    }


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for mode in ("aten", "ieo"):
        mode_records = [row for row in records if row["ranking_mode"] == mode]
        result[mode] = {
            "all": _metric_slice(mode_records),
            "development_through_2023": _metric_slice(
                [row for row in mode_records if row["cohort_year"] <= 2023]
            ),
            "holdout_2024": _metric_slice(
                [row for row in mode_records if row["cohort_year"] == 2024]
            ),
        }
    return result


def build_policy_audit(
    positive_paths: tuple[Path, ...],
    null_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    """Build an exact, non-promotional retrospective audit."""
    validate_null_outcomes(null_path, repo_root=ROOT)
    policy_raw = json.loads(policy_path.read_text(encoding="utf-8"))
    policy = selector.load_ranking_policy(policy_path)
    weights = policy_raw["discovery_weights"]
    records: list[dict[str, Any]] = []

    for path in positive_paths:
        envelope = _load_positive_envelope(path)
        for event in envelope["events"]:
            neo_class = event.get("neo_class")
            if neo_class not in {"aten", "atira"}:
                raise ValueError(f"unsupported positive NEO class: {neo_class}")
            mode = "aten" if neo_class == "aten" else "ieo"
            observation = event["discovery_observation"]
            features = _score_field(
                float(observation["ra_deg"]),
                float(observation["dec_deg"]),
                float(observation["jd"]),
                mode,
                weights,
            )
            records.append(
                {
                    "record_id": event["event_id"],
                    "outcome": "positive",
                    "ranking_mode": mode,
                    "cohort_year": int(event["discovery_year"]),
                    "source_aligned_ztf_i41": observation["station"] == "I41",
                    "ra_deg": observation["ra_deg"],
                    "dec_deg": observation["dec_deg"],
                    "ranking_jd": observation["jd"],
                    "features": features,
                }
            )

    null_payload = json.loads(null_path.read_text(encoding="utf-8"))
    maximum_score_drift = 0.0
    for entry in null_payload["entries"]:
        features = _score_field(
            float(entry["ra_deg"]),
            float(entry["dec_deg"]),
            float(entry["ranking_jd"]),
            str(entry["ranking_mode"]),
            weights,
        )
        drift = abs(float(entry["recorded_score"]) - features["score"])
        maximum_score_drift = max(maximum_score_drift, drift)
        if drift > 0.0002:
            raise ValueError(
                f"recorded score drift for {entry['outcome_id']}: {drift:.6f}"
            )
        records.append(
            {
                "record_id": entry["outcome_id"],
                "outcome": "null_result",
                "ranking_mode": entry["ranking_mode"],
                "cohort_year": max(
                    int(night[:4]) for night in entry["observation_nights_yyyymmdd"]
                ),
                "source_aligned_ztf_i41": True,
                "ra_deg": entry["ra_deg"],
                "dec_deg": entry["dec_deg"],
                "ranking_jd": entry["ranking_jd"],
                "recorded_score": entry["recorded_score"],
                "features": features,
            }
        )

    source_aligned = [row for row in records if row["source_aligned_ztf_i41"]]
    source_counts = {
        mode: {
            "positive": sum(
                row["outcome"] == "positive" and row["ranking_mode"] == mode
                for row in source_aligned
            ),
            "searched_null": sum(
                row["outcome"] == "null_result" and row["ranking_mode"] == mode
                for row in source_aligned
            ),
        }
        for mode in ("aten", "ieo")
    }
    coefficient_update_authorized = all(
        counts["positive"] >= 20 and counts["searched_null"] >= 20
        for counts in source_counts.values()
    )
    if coefficient_update_authorized:
        raise ValueError("sample gate unexpectedly authorizes an unaudited coefficient fit")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "audit_complete_not_calibrated",
        "policy": policy,
        "sources": {
            "positive_envelopes": [
                {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)}
                for path in positive_paths
            ],
            "searched_nulls": {
                "path": str(null_path.relative_to(ROOT)),
                "sha256": _sha256(null_path),
            },
        },
        "score_reproduction": {
            "searched_null_count": len(null_payload["entries"]),
            "maximum_absolute_drift": round(maximum_score_drift, 8),
            "tolerance": 0.0002,
        },
        "all_source_metrics": _metrics(records),
        "ztf_i41_source_aligned_metrics": _metrics(source_aligned),
        "coefficient_promotion_gate": {
            "minimum_positive_per_mode": 20,
            "minimum_searched_null_per_mode": 20,
            "observed_counts": source_counts,
            "coefficient_update_authorized": coefficient_update_authorized,
            "decision": "retain_transparent_v2_prior",
        },
        "limitations": [
            "Searched nulls are top-selected fields, not random or bottom-ranked controls.",
            "Non-I41 positives establish discovery geometry but are not ZTF source-aligned.",
            "The I41 subset is too small for coefficient fitting or probability calibration.",
            "Pairwise AUC is a diagnostic ordering statistic, not discovery-yield validation.",
        ],
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit field-ranking policy against real positive and null outcomes"
    )
    parser.add_argument("--positive", type=Path, nargs="+", default=list(DEFAULT_POSITIVES))
    parser.add_argument("--nulls", type=Path, default=DEFAULT_NULLS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build_policy_audit(tuple(args.positive), args.nulls, args.policy)
    _atomic_write(args.out, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "score_reproduction": result["score_reproduction"],
                "coefficient_promotion_gate": result["coefficient_promotion_gate"],
                "out": str(args.out),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
