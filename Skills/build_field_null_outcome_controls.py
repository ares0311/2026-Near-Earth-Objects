#!/usr/bin/env python
"""Build additional real searched-field null-outcome control records.

Extends data_selection/calibration/ztf_field_null_outcomes_v1.json's control
set toward PR #264's own "exact next work": a predeclared, stratified
top/middle/bottom/random sample of real searched fields (the existing six
controls are all top-ranked, which the calibration audit itself flags as a
biased, non-random cohort).

Reuses Skills/hunter_cli.py's real coverage-check and per-target execution
machinery (``execute_target``, ``_nights_for_target``) -- this script does
not reimplement acquisition, linking, or adversarial review. Each input
field must already have committed coverage data (run
``create-new-search``/the coverage-expansion path first if not).

A search field counts as a valid "null_result" control under this dataset's
own definition (see ztf_field_null_outcomes_v1.json's ``outcome_definition``)
when it has at least three real populated nights and zero candidates survive
adversarial review -- regardless of how many raw tracklets were linked.

Usage::

    uv run python Skills/build_field_null_outcome_controls.py \\
        --fields-json data_selection/calibration/stratified_control_targets_v1.json \\
        --out Logs/pipeline_runs/field_ranking_calibration/null_outcome_controls_v1.json \\
        --checkpoint-root Logs/pipeline_runs/field_ranking_calibration/checkpoints
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hunter_cli  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "ztf-field-null-outcome-controls-v1"


def _outcome_id(stratum: str, ra_deg: float, dec_deg: float) -> str:
    ra_token = f"{round(ra_deg, 2):07.2f}".replace(".", "p")
    sign = "m" if dec_deg < 0 else "p"
    dec_token = f"{abs(round(dec_deg, 2)):06.2f}".replace(".", "p")
    return f"ztf-null-{stratum}-ra{ra_token}-dec{sign}{dec_token}"


def load_predeclared_fields(path: Path) -> list[dict[str, Any]]:
    """Load and fail-closed validate a predeclared stratified target list.

    Each entry must already specify its stratum and ranking provenance --
    this script only ever executes exactly the fields it is given, never
    a fresh selection, matching this project's predeclare-before-execution
    convention.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload.get("fields") if isinstance(payload, dict) else payload
    if not isinstance(fields, list) or not fields:
        raise ValueError(f"{path} must contain a non-empty list of predeclared fields")
    required = {"stratum", "ra_deg", "dec_deg", "rank", "score", "mode", "ranking_jd"}
    for entry in fields:
        if not isinstance(entry, dict) or not required.issubset(entry):
            raise ValueError(f"predeclared field entry missing required keys {required}: {entry}")
    return fields


def _ensure_coverage_committed(target_id: str, ra_deg: float, dec_deg: float) -> None:
    """Run a real, live coverage-preflight check for this field if no
    committed coverage inventory already covers it.

    ``hunter_cli.execute_target()`` requires a pre-committed coverage
    record (built by ``create-new-search --mode new``'s adaptive expansion
    loop); a predeclared field selected directly from the planning grid,
    as this script's inputs are, has not necessarily been through that
    step yet. Mirrors ``discover_new_targets()``'s own coverage-check call
    rather than duplicating its logic.
    """
    key = hunter_cli.field_selector._coordinate_key(ra_deg, dec_deg)
    if key in hunter_cli._combined_known_coverage():
        return
    hunter_cli._live_coverage_check(
        [(target_id, ra_deg, dec_deg)], "null_control_coverage"
    )


def build_control_record(
    field: dict[str, Any],
    checkpoint_root: Path,
    size_deg: float = hunter_cli._DEFAULT_SIZE_DEG,
    min_observations: int = 3,
) -> dict[str, Any]:
    """Run one real field search and return its null-outcome control record.

    Raises on genuine execution failure -- the caller decides whether to
    skip or abort (this mirrors run-new-search's own per-target failure
    handling rather than silently treating a failure as a null result).
    """
    ra_deg = float(field["ra_deg"])
    dec_deg = float(field["dec_deg"])
    target_id = hunter_cli.hunter_state.target_id_from_radec(ra_deg, dec_deg)
    target = {"target_id": target_id, "ra_deg": ra_deg, "dec_deg": dec_deg}

    _ensure_coverage_committed(target_id, ra_deg, dec_deg)
    result = hunter_cli.execute_target(
        target, checkpoint_root, size_deg, min_observations=min_observations
    )
    production_tracklet_count = len(result["candidate_ids"])
    surviving_review_count = sum(
        1
        for scored in result["scored_candidates"]
        if scored["verdict"].verdict in hunter_cli._FOLLOW_UP_VERDICTS
    )
    outcome = "null_result" if surviving_review_count == 0 else "survivor_found"

    return {
        "outcome_id": _outcome_id(str(field["stratum"]), ra_deg, dec_deg),
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "field_radius_deg": float(field.get("field_radius_deg", 3.5)),
        "observation_nights_yyyymmdd": result["nights_acquired"],
        "outcome": outcome,
        "recorded_rank": int(field["rank"]),
        "recorded_score": float(field["score"]),
        "ranking_mode": str(field["mode"]),
        "ranking_jd": float(field["ranking_jd"]),
        "selection_stratum": str(field["stratum"]),
        "pipeline_path": "motion_product_pixel_extraction",
        "production_tracklet_count": production_tracklet_count,
        "surviving_review_count": surviving_review_count,
        "candidate_ids": result["candidate_ids"],
    }


def build_controls(
    fields: list[dict[str, Any]],
    out: Path,
    checkpoint_root: Path,
    size_deg: float = hunter_cli._DEFAULT_SIZE_DEG,
) -> dict[str, Any]:
    """Execute every predeclared field, checkpointing after each one."""
    envelope: dict[str, Any]
    if out.exists():
        envelope = json.loads(out.read_text(encoding="utf-8"))
        if envelope.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported checkpoint schema: {out}")
    else:
        envelope = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "entries": [],
            "failures": [],
        }

    done = {entry["outcome_id"] for entry in envelope["entries"]}
    total = len(fields)
    for index, field in enumerate(fields, start=1):
        ra_deg, dec_deg = float(field["ra_deg"]), float(field["dec_deg"])
        outcome_id = _outcome_id(str(field["stratum"]), ra_deg, dec_deg)
        if outcome_id in done:
            print(f"[null-controls] {index}/{total} {outcome_id}: checkpointed", flush=True)
            continue
        print(
            f"[null-controls] {index}/{total} {outcome_id}: executing real search "
            f"(stratum={field['stratum']}, rank={field['rank']})",
            flush=True,
        )
        try:
            record = build_control_record(field, checkpoint_root, size_deg)
        except hunter_cli._RUN_TARGET_EXPECTED_EXCEPTIONS as exc:
            print(f"[null-controls] {index}/{total} {outcome_id}: FAILED: {exc}", flush=True)
            envelope["failures"].append({"outcome_id": outcome_id, "error": str(exc)})
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
            continue
        envelope["entries"].append(record)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
        print(
            f"[null-controls] {index}/{total} {outcome_id}: {record['outcome']} "
            f"(tracklets={record['production_tracklet_count']} "
            f"surviving={record['surviving_review_count']})",
            flush=True,
        )
    print(
        f"[null-controls] complete: {len(envelope['entries'])}/{total} recorded, "
        f"{len(envelope['failures'])} failed -> {out}",
        flush=True,
    )
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fields-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--checkpoint-root",
        type=Path,
        default=REPO_ROOT / "Logs" / "pipeline_runs" / "field_ranking_calibration" / "checkpoints",
    )
    parser.add_argument("--size-deg", type=float, default=hunter_cli._DEFAULT_SIZE_DEG)
    args = parser.parse_args()

    fields = load_predeclared_fields(args.fields_json)
    build_controls(fields, args.out, args.checkpoint_root, args.size_deg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
