#!/usr/bin/env python3
"""Inventory bounded ZTF field/night coverage before an alert-archive transfer.

This is a native target for ``Skills/run_sharded_download.py``. A committed
manifest defines six independent sky fields and one bounded historical window.
Shard ``i`` owns ``fields[i::shard_count]`` and queries only the public IRSA
ZTF science-image metadata endpoint through ``ztf_dr24_bounded_ingest``.

No alert archive, cutout, source photometry, candidate, or catalog is fetched.
The merged result identifies which real UTC nights have science-image coverage
in each central search box, so a later multi-gigabyte transfer can require at
least three populated nights per field instead of guessing dates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ztf_dr24_bounded_ingest as bounded_ingest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = Path("Logs/pipeline_runs/ztf_field_night_coverage")
EXPECTED_DATA_ROLE = "metadata_only_coverage_preflight"
MAX_FIELDS = 20
MAX_AGGREGATE_IRSA_REQUESTS = 6


@dataclass(frozen=True)
class CoverageField:
    """One immutable central search box."""

    field_id: str
    role: str
    ra_deg: float
    dec_deg: float


@dataclass(frozen=True)
class CoverageBatch:
    """Validated query contract loaded from a committed manifest."""

    batch_id: str
    start_jd: float
    end_jd: float
    size_deg: float
    min_distinct_nights: int
    fields: tuple[CoverageField, ...]
    manifest_sha256: str
    source_path: Path


def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_identifier(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text or not all(character.isalnum() or character in "-_" for character in text):
        raise ValueError(f"{name} must contain only letters, digits, '-' or '_'")
    return text


def _resolve_in_repo(path: Path, label: str) -> Path:
    candidate = path if path.is_absolute() else REPO_ROOT / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must resolve inside the repository") from exc
    return resolved


def load_batch_manifest(path: Path) -> CoverageBatch:
    """Load and fail-closed validate a metadata-only coverage batch."""
    resolved = _resolve_in_repo(path, "batch manifest")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("data_role") != EXPECTED_DATA_ROLE:
        raise ValueError(f"data_role must be {EXPECTED_DATA_ROLE}")

    batch_id = _safe_identifier(payload.get("batch_id"), "batch_id")
    start_jd = float(payload["start_jd_exclusive"])
    end_jd = float(payload["end_jd_exclusive"])
    size_deg = float(payload["size_deg"])
    min_distinct_nights = int(payload["min_distinct_nights"])
    if end_jd <= start_jd or end_jd - start_jd > bounded_ingest._MAX_WINDOW_DAYS:
        raise ValueError("manifest time window must be positive and within the bounded ingest cap")
    if not (0.0 < size_deg <= bounded_ingest._MAX_SIZE_DEG):
        raise ValueError("manifest size_deg exceeds the bounded ingest cap")
    if min_distinct_nights < 3:
        raise ValueError("min_distinct_nights must be at least 3")

    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields or len(raw_fields) > MAX_FIELDS:
        raise ValueError(f"fields must be a non-empty list of at most {MAX_FIELDS} entries")
    fields: list[CoverageField] = []
    for raw in raw_fields:
        if not isinstance(raw, dict):
            raise ValueError("each field must be an object")
        field = CoverageField(
            field_id=_safe_identifier(raw.get("field_id"), "field_id"),
            role=str(raw.get("role", "")).strip(),
            ra_deg=float(raw["ra_deg"]),
            dec_deg=float(raw["dec_deg"]),
        )
        if field.role != "live_search":
            raise ValueError(f"unsupported coverage-preflight role: {field.role}")
        if not (0.0 <= field.ra_deg < 360.0 and -90.0 <= field.dec_deg <= 90.0):
            raise ValueError(f"invalid coordinates for field {field.field_id}")
        fields.append(field)
    ids = [field.field_id for field in fields]
    if len(ids) != len(set(ids)):
        raise ValueError("field_id values must be unique")

    safety = payload.get("safety")
    if not isinstance(safety, dict) or safety.get("metadata_only") is not True:
        raise ValueError("safety.metadata_only must be true")
    if safety.get("raw_alert_archives_downloaded") is not False:
        raise ValueError("safety.raw_alert_archives_downloaded must be false")

    return CoverageBatch(
        batch_id=batch_id,
        start_jd=start_jd,
        end_jd=end_jd,
        size_deg=size_deg,
        min_distinct_nights=min_distinct_nights,
        fields=tuple(fields),
        manifest_sha256=_manifest_sha256(resolved),
        source_path=resolved,
    )


def assigned_fields(
    fields: tuple[CoverageField, ...], shard_index: int, shard_count: int
) -> tuple[CoverageField, ...]:
    """Return deterministic, disjoint field ownership for one shard."""
    if shard_count < 1 or not (0 <= shard_index < shard_count):
        raise ValueError("shard_index must be in [0, shard_count)")
    return fields[shard_index::shard_count]


def query_key(batch: CoverageBatch) -> str:
    """Bind shard summaries to the exact manifest and query contract."""
    payload = json.dumps(
        {
            "batch_id": batch.batch_id,
            "manifest_sha256": batch.manifest_sha256,
            "start_jd": batch.start_jd,
            "end_jd": batch.end_jd,
            "size_deg": batch.size_deg,
            "min_distinct_nights": batch.min_distinct_nights,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def resolve_output_dir(path: Path) -> Path:
    return _resolve_in_repo(path, "--out-dir")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_root(batch: CoverageBatch, out_dir: Path) -> Path:
    return out_dir / batch.batch_id / query_key(batch)


def _shard_summary_path(
    batch: CoverageBatch, out_dir: Path, shard_index: int
) -> Path:
    return _run_root(batch, out_dir) / f"shard_{shard_index:02d}_summary.json"


def inventory_field(
    field: CoverageField, batch: CoverageBatch, out_dir: Path
) -> dict[str, Any]:
    """Run one bounded metadata query and return its compact field result."""
    field_out = _run_root(batch, out_dir) / "fields" / field.field_id
    report = bounded_ingest.run_bounded_ingest(
        ra=field.ra_deg,
        dec=field.dec_deg,
        size_deg=batch.size_deg,
        start_jd=batch.start_jd,
        end_jd=batch.end_jd,
        out_dir=field_out,
    )
    nights = list(report["distinct_nights_yyyymmdd"])
    return {
        "field_id": field.field_id,
        "role": field.role,
        "ra_deg": field.ra_deg,
        "dec_deg": field.dec_deg,
        "n_rows": int(report["n_rows"]),
        "n_distinct_nights": len(nights),
        "distinct_nights_yyyymmdd": nights,
        "passes_min_distinct_nights": len(nights) >= batch.min_distinct_nights,
        "raw_response_sha256": report["raw_response_sha256"],
        "raw_response_path": report["raw_response_path"],
    }


def run_shard(
    batch: CoverageBatch,
    out_dir: Path,
    shard_index: int,
    shard_count: int,
    workers: int,
) -> dict[str, Any]:
    """Inventory one disjoint field shard and atomically persist its result."""
    fields = assigned_fields(batch.fields, shard_index, shard_count)
    if workers < 1:
        raise ValueError("workers must be >= 1")
    aggregate_workers = shard_count * workers
    if aggregate_workers > MAX_AGGREGATE_IRSA_REQUESTS:
        raise ValueError(
            f"aggregate IRSA concurrency {aggregate_workers} exceeds the verified ceiling "
            f"of {MAX_AGGREGATE_IRSA_REQUESTS}; lower --workers"
        )
    print(
        f"[coverage] shard={shard_index}/{shard_count} workers={workers} "
        f"fields={[field.field_id for field in fields]}",
        flush=True,
    )
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(fields)))) as pool:
        futures = {pool.submit(inventory_field, field, batch, out_dir): field for field in fields}
        for future in as_completed(futures):
            field = futures[future]
            results[field.field_id] = future.result()

    summary: dict[str, Any] = {
        "batch_id": batch.batch_id,
        "batch_manifest": batch.source_path.relative_to(REPO_ROOT).as_posix(),
        "batch_manifest_sha256": batch.manifest_sha256,
        "query_key": query_key(batch),
        "shard_index": shard_index,
        "shard_count": shard_count,
        "workers": workers,
        "field_ids": [field.field_id for field in fields],
        "field_results": [results[field.field_id] for field in fields],
        "status": "succeeded",
    }
    path = _shard_summary_path(batch, out_dir, shard_index)
    _atomic_write_json(path, summary)
    print(f"[coverage] wrote {path}", flush=True)
    return summary


def _read_matching_shards(
    batch: CoverageBatch, out_dir: Path, shard_count: int
) -> tuple[list[dict[str, Any]], list[int]]:
    summaries: list[dict[str, Any]] = []
    missing: list[int] = []
    for index in range(shard_count):
        path = _shard_summary_path(batch, out_dir, index)
        if not path.exists():
            missing.append(index)
            continue
        summary = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "batch_id": batch.batch_id,
            "batch_manifest_sha256": batch.manifest_sha256,
            "query_key": query_key(batch),
            "shard_index": index,
            "shard_count": shard_count,
            "status": "succeeded",
        }
        if any(summary.get(key) != value for key, value in expected.items()):
            raise RuntimeError(f"shard summary does not match this query: {path}")
        summaries.append(summary)
    return summaries, missing


def report_status(batch: CoverageBatch, out_dir: Path, shard_count: int) -> dict[str, Any]:
    """Report partial progress without failing merely because shards are incomplete."""
    summaries, missing = _read_matching_shards(batch, out_dir, shard_count)
    report = {
        "batch_id": batch.batch_id,
        "query_key": query_key(batch),
        "completed_shards": sorted(summary["shard_index"] for summary in summaries),
        "missing_shards": missing,
        "complete": not missing,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def merge_shards(batch: CoverageBatch, out_dir: Path, shard_count: int) -> dict[str, Any]:
    """Fail closed on missing shards and write the durable coverage inventory."""
    summaries, missing = _read_matching_shards(batch, out_dir, shard_count)
    if missing:
        raise RuntimeError(f"cannot merge; missing shard summaries: {missing}")
    results = [result for summary in summaries for result in summary["field_results"]]
    expected_ids = [field.field_id for field in batch.fields]
    actual_ids = [result["field_id"] for result in results]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise RuntimeError("shard field ownership is incomplete or overlapping")
    by_id = {result["field_id"]: result for result in results}
    ordered = [by_id[field_id] for field_id in expected_ids]
    night_field_counts: dict[str, int] = {}
    for result in ordered:
        for night in result["distinct_nights_yyyymmdd"]:
            night_field_counts[night] = night_field_counts.get(night, 0) + 1
    ranked_nights = sorted(
        night_field_counts, key=lambda night: (-night_field_counts[night], night)
    )
    passing = [result["field_id"] for result in ordered if result["passes_min_distinct_nights"]]
    report: dict[str, Any] = {
        "schema_version": "ztf-field-night-coverage-inventory-v1",
        "batch_id": batch.batch_id,
        "batch_manifest": batch.source_path.relative_to(REPO_ROOT).as_posix(),
        "batch_manifest_sha256": batch.manifest_sha256,
        "query_key": query_key(batch),
        "metadata_only": True,
        "query": {
            "start_jd_exclusive": batch.start_jd,
            "end_jd_exclusive": batch.end_jd,
            "size_deg": batch.size_deg,
        },
        "min_distinct_nights": batch.min_distinct_nights,
        "n_fields": len(ordered),
        "n_fields_passing": len(passing),
        "all_fields_pass": len(passing) == len(ordered),
        "passing_field_ids": passing,
        "field_results": ordered,
        "night_field_counts": {night: night_field_counts[night] for night in ranked_nights},
    }
    path = _run_root(batch, out_dir) / "coverage_inventory.json"
    _atomic_write_json(path, report)
    print(
        f"[coverage] merged {len(ordered)} fields; {len(passing)} pass >= "
        f"{batch.min_distinct_nights} nights; wrote {path}",
        flush=True,
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--workers", type=int, default=1)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--status", action="store_true")
    action.add_argument("--merge", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        batch = load_batch_manifest(args.batch_manifest)
        out_dir = resolve_output_dir(args.out_dir)
        if args.status:
            report_status(batch, out_dir, args.shard_count)
        elif args.merge:
            merge_shards(batch, out_dir, args.shard_count)
        else:
            run_shard(batch, out_dir, args.shard_index, args.shard_count, args.workers)
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
