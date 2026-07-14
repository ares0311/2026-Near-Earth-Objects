#!/usr/bin/env python3
"""Safely associate multi-night detections from a ZTF portfolio ingest.

The portfolio checkpoints retain ZTF's survey field number in
``Observation.field_id``.  That value is not an object identity, so this
analyzer clears it on an in-memory copy before calling ``detect()``.  This
forces the real within-night motion-pairing path instead of incorrectly
grouping every alert from the same survey field as one object history.

Multiple ``--batch-manifest`` arguments may be supplied when a bounded
expansion supplements an earlier batch. Observations are merged by field/night
and deduplicated by ``obs_id`` while every source checkpoint remains bound to
its own manifest hash. This prevents a supplemental run from being analyzed in
isolation and silently discarding useful earlier nights.

This stage stops after linking. It deliberately disables the current-catalog
MPC shortcut and marks every result ineligible for candidate review until a
separate time-aware historical known-object exclusion audit is complete.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ztf_alert_archive_portfolio as portfolio

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT_ROOT = Path("Logs/pipeline_runs/ztf_alert_archive_portfolio")


def _fmt_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def _load_states(
    batch: portfolio.PortfolioBatch, checkpoint_root: Path
) -> dict[str, dict[str, Any]]:
    batch_dir = checkpoint_root / batch.batch_id
    states: dict[str, dict[str, Any]] = {}
    for night in batch.nights:
        path = batch_dir / f"{night}.json"
        if not path.is_file():
            raise FileNotFoundError(f"missing portfolio checkpoint: {path}")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("batch_id") != batch.batch_id:
            raise ValueError(f"checkpoint batch_id mismatch: {path}")
        if state.get("batch_manifest_sha256") != batch.manifest_sha256:
            raise ValueError(f"checkpoint manifest SHA-256 mismatch: {path}")
        observations = state.get("observations_by_field")
        if not isinstance(observations, dict):
            raise ValueError(f"checkpoint lacks observations_by_field: {path}")
        states[night] = state
    return states


def eligible_field_nights(
    batch: portfolio.PortfolioBatch, states: dict[str, dict[str, Any]]
) -> dict[str, tuple[str, ...]]:
    """Return fields with retained observations on at least two real nights."""
    return eligible_field_nights_for_fields(batch.fields, states)


def eligible_field_nights_for_fields(
    fields: tuple[portfolio.SearchField, ...], states: dict[str, dict[str, Any]]
) -> dict[str, tuple[str, ...]]:
    """Return multi-night coverage for an explicit, possibly cross-batch field set."""
    result: dict[str, tuple[str, ...]] = {}
    for field in fields:
        nights = tuple(
            night
            for night in sorted(states)
            if states[night]["observations_by_field"].get(field.field_id)
        )
        if len(nights) >= 2:
            result[field.field_id] = nights
    return result


def _field_signature(field: portfolio.SearchField) -> tuple[str, float, float, float]:
    """Return the immutable search geometry used to detect manifest drift."""
    return (field.role, field.ra_deg, field.dec_deg, field.radius_deg)


def _merge_batch_states(
    batches: tuple[portfolio.PortfolioBatch, ...], checkpoint_root: Path
) -> tuple[tuple[portfolio.SearchField, ...], dict[str, dict[str, Any]]]:
    """Merge query-bound checkpoints without losing or double-counting observations."""
    fields_by_id: dict[str, portfolio.SearchField] = {}
    states_by_batch = [(batch, _load_states(batch, checkpoint_root)) for batch in batches]
    for batch in batches:
        for field in batch.fields:
            existing = fields_by_id.get(field.field_id)
            if existing is not None and _field_signature(existing) != _field_signature(field):
                raise ValueError(
                    f"field definition mismatch across batches for {field.field_id}"
                )
            fields_by_id.setdefault(field.field_id, field)

    merged: dict[str, dict[str, Any]] = {}
    seen: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for batch, states in states_by_batch:
        for night in batch.nights:
            target = merged.setdefault(
                night,
                {
                    "observations_by_field": {
                        field_id: [] for field_id in fields_by_id
                    },
                    "source_batch_ids": [],
                },
            )
            target["source_batch_ids"].append(batch.batch_id)
            for field_id in fields_by_id:
                rows = states[night]["observations_by_field"].get(field_id, [])
                key = (night, field_id)
                indexed = seen.setdefault(key, {})
                for row in rows:
                    obs_id = str(row.get("obs_id", "")).strip()
                    if not obs_id:
                        raise ValueError(
                            f"observation without obs_id in {batch.batch_id}/{night}/{field_id}"
                        )
                    existing = indexed.get(obs_id)
                    if existing is not None:
                        if existing != row:
                            raise ValueError(
                                f"conflicting duplicate observation {obs_id} in "
                                f"{night}/{field_id}"
                            )
                        continue
                    indexed[obs_id] = row
                    target["observations_by_field"][field_id].append(row)
    return tuple(fields_by_id.values()), merged


def _tracklet_summary(tracklet: Any) -> dict[str, Any]:
    observations = sorted(tracklet.observations, key=lambda item: item.jd)
    return {
        "object_id": tracklet.object_id,
        "n_observations": len(observations),
        "n_nights": len({int(item.jd) for item in observations}),
        "arc_days": tracklet.arc_days,
        "motion_rate_arcsec_per_hour": tracklet.motion_rate_arcsec_per_hour,
        "motion_pa_degrees": tracklet.motion_pa_degrees,
        "observations": [
            {
                "obs_id": item.obs_id,
                "ra_deg": item.ra_deg,
                "dec_deg": item.dec_deg,
                "jd": item.jd,
                "survey_field_id": item.field_id,
            }
            for item in observations
        ],
    }


def analyze_field(
    field_id: str,
    nights: tuple[str, ...],
    states: dict[str, dict[str, Any]],
    min_observations: int = 3,
) -> dict[str, Any]:
    """Run preprocess, real motion pairing, and linking for one field."""
    from detect import detect
    from link import link
    from preprocess import preprocess
    from schemas import Observation

    raw_rows = [
        row
        for night in nights
        for row in states[night]["observations_by_field"][field_id]
    ]
    observations = tuple(Observation(**row) for row in raw_rows)
    prep = preprocess(observations, apply_astrometry=False)

    # A ZTF survey field number identifies a telescope pointing, not a source.
    # Keep the original value in checkpoint provenance and clear it only on the
    # association copy so detect() uses spatial/temporal motion pairing.
    association_sources = tuple(
        source.model_copy(update={"field_id": None}) for source in prep.sources
    )
    detection = detect(association_sources, mpc_cross_match=False)

    started = time.monotonic()

    def progress(done: int, total: int, formed: int) -> None:
        print(
            f"[associate] {field_id}: seed_pairs={done}/{total} "
            f"tracklets={formed} elapsed={_fmt_duration(time.monotonic() - started)}",
            flush=True,
        )

    linked = link(
        detection.candidates,
        min_observations=min_observations,
        progress_callback=progress,
    )
    summaries = [_tracklet_summary(item) for item in linked.tracklets]
    return {
        "field_id": field_id,
        "nights": list(nights),
        "n_observations_loaded": len(observations),
        "n_sources_preprocessed": prep.provenance.n_sources_out,
        "n_motion_candidates_detected": detection.provenance.n_candidates,
        "n_tracklets_linked": linked.provenance.n_tracklets,
        "link_diagnostics": linked.provenance.model_dump(mode="json"),
        "tracklets": summaries,
        "known_object_exclusion_status": "pending_time_aware_audit",
        "candidate_review_allowed": False,
    }


def analyze_batch(
    batch_manifest: Path,
    checkpoint_root: Path,
    min_observations: int = 3,
) -> dict[str, Any]:
    """Analyze every portfolio field that has at least two populated nights."""
    batch = portfolio.load_batch_manifest(batch_manifest)
    states = _load_states(batch, checkpoint_root)
    eligible = eligible_field_nights(batch, states)
    fields = [
        analyze_field(field_id, nights, states, min_observations)
        for field_id, nights in eligible.items()
    ]
    return {
        "schema_version": "ztf-portfolio-association-v1",
        "batch_id": batch.batch_id,
        "batch_manifest": batch.source_path.relative_to(REPO_ROOT).as_posix(),
        "batch_manifest_sha256": batch.manifest_sha256,
        "min_observations": min_observations,
        "eligible_fields": {key: list(value) for key, value in eligible.items()},
        "n_eligible_fields": len(eligible),
        "n_tracklets_linked": sum(item["n_tracklets_linked"] for item in fields),
        "fields": fields,
        "known_object_exclusion_status": "pending_time_aware_audit",
        "candidate_review_allowed": False,
        "external_submission_allowed": False,
    }


def analyze_batches(
    batch_manifests: tuple[Path, ...],
    checkpoint_root: Path,
    min_observations: int = 3,
    field_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Associate a provenance-bound union of one or more portfolio batches."""
    if not batch_manifests:
        raise ValueError("at least one batch manifest is required")
    batches = tuple(portfolio.load_batch_manifest(path) for path in batch_manifests)
    batch_ids = [batch.batch_id for batch in batches]
    if len(batch_ids) != len(set(batch_ids)):
        raise ValueError("batch_id values must be unique across --batch-manifest inputs")
    fields, states = _merge_batch_states(batches, checkpoint_root)
    known_ids = {field.field_id for field in fields}
    if len(field_ids) != len(set(field_ids)):
        raise ValueError("--field-id values must be unique")
    unknown = sorted(set(field_ids) - known_ids)
    if unknown:
        raise ValueError(f"unknown --field-id values: {unknown}")
    selected_fields = (
        tuple(field for field in fields if field.field_id in field_ids)
        if field_ids
        else fields
    )
    eligible = eligible_field_nights_for_fields(selected_fields, states)
    field_reports = [
        analyze_field(field_id, nights, states, min_observations)
        for field_id, nights in eligible.items()
    ]
    return {
        "schema_version": "ztf-portfolio-cross-batch-association-v1",
        "batch_ids": [batch.batch_id for batch in batches],
        "batch_manifests": [
            batch.source_path.relative_to(REPO_ROOT).as_posix() for batch in batches
        ],
        "batch_manifest_sha256s": {
            batch.batch_id: batch.manifest_sha256 for batch in batches
        },
        "n_input_batches": len(batches),
        "selected_field_ids": [field.field_id for field in selected_fields],
        "min_observations": min_observations,
        "eligible_fields": {key: list(value) for key, value in eligible.items()},
        "n_eligible_fields": len(eligible),
        "n_tracklets_linked": sum(item["n_tracklets_linked"] for item in field_reports),
        "fields": field_reports,
        "known_object_exclusion_status": "pending_time_aware_audit",
        "candidate_review_allowed": False,
        "external_submission_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-manifest",
        type=Path,
        action="append",
        required=True,
        help="Repeat to combine a supplemental batch with prior retained nights.",
    )
    parser.add_argument(
        "--field-id",
        action="append",
        default=[],
        help="Optional field allowlist; repeat for multiple fields.",
    )
    parser.add_argument("--checkpoint-root", type=Path, default=DEFAULT_CHECKPOINT_ROOT)
    parser.add_argument("--min-observations", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.min_observations < 2:
        raise SystemExit("--min-observations must be >= 2")
    report = analyze_batches(
        tuple(args.batch_manifest),
        args.checkpoint_root,
        args.min_observations,
        tuple(args.field_id),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        f"[associate] fields={report['n_eligible_fields']} "
        f"tracklets={report['n_tracklets_linked']} -> {args.out}",
        flush=True,
    )


if __name__ == "__main__":
    main()
