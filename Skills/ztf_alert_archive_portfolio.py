#!/usr/bin/env python3
"""Stream one ZTF nightly alert archive once for a multi-field search batch.

This is the native shard target for ``Skills/run_sharded_download.py``.  A
committed batch manifest supplies explicit nights and sky fields.  Each shard
owns ``nights[shard_index::shard_count]`` and each assigned nightly archive is
downloaded once, streamed without a raw on-disk copy, and filtered against all
fields during that pass.  This avoids downloading the same multi-gigabyte
night once per field.

The target intentionally exposes ``--shard-index``, ``--shard-count``, and
``--workers``.  Workers apply only within one shard; provider limits should
normally keep the aggregate number of simultaneous UW archive streams small.
Checkpoints are atomic and bind the batch-manifest SHA-256 to prevent a resume
from silently mixing a changed field definition with old observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import ztf_alert_archive_ingest as single_ingest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = Path("Logs/pipeline_runs/ztf_alert_archive_portfolio")
PROGRESS_EVERY = 5_000
MAX_FIELDS = 20
MAX_NIGHTS = 30


@dataclass(frozen=True)
class SearchField:
    """One immutable sky cone in a portfolio batch."""

    field_id: str
    role: str
    ra_deg: float
    dec_deg: float
    radius_deg: float


@dataclass(frozen=True)
class PortfolioBatch:
    """Validated immutable acquisition definition."""

    batch_id: str
    nights: tuple[str, ...]
    fields: tuple[SearchField, ...]
    manifest_sha256: str
    source_path: Path


def _manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_batch_manifest(path: Path) -> PortfolioBatch:
    """Load and fail-closed validate one committed portfolio definition."""
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("batch manifest must live inside the repository") from exc
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    batch_id = str(payload.get("batch_id", "")).strip()
    if not batch_id or not all(ch.isalnum() or ch in "-_" for ch in batch_id):
        raise ValueError("batch_id must contain only letters, digits, '-' or '_'")

    raw_nights = payload.get("nights")
    if not isinstance(raw_nights, list) or not raw_nights:
        raise ValueError("nights must be a non-empty list")
    nights = tuple(str(night) for night in raw_nights)
    if len(nights) > MAX_NIGHTS or len(set(nights)) != len(nights):
        raise ValueError(f"nights must be unique and contain at most {MAX_NIGHTS} values")
    if any(len(night) != 8 or not night.isdigit() for night in nights):
        raise ValueError("every night must use YYYYMMDD digits")

    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise ValueError("fields must be a non-empty list")
    if len(raw_fields) > MAX_FIELDS:
        raise ValueError(f"fields may contain at most {MAX_FIELDS} entries")
    fields: list[SearchField] = []
    for raw in raw_fields:
        if not isinstance(raw, dict):
            raise ValueError("each field must be an object")
        field = SearchField(
            field_id=str(raw.get("field_id", "")).strip(),
            role=str(raw.get("role", "")).strip(),
            ra_deg=float(raw["ra_deg"]),
            dec_deg=float(raw["dec_deg"]),
            radius_deg=float(raw["radius_deg"]),
        )
        if not field.field_id or not all(
            ch.isalnum() or ch in "-_" for ch in field.field_id
        ):
            raise ValueError("field_id must contain only letters, digits, '-' or '_'")
        if field.role not in {"live_search", "followup_live_search"}:
            raise ValueError(f"unsupported live-search role: {field.role}")
        if not (0.0 <= field.ra_deg < 360.0 and -90.0 <= field.dec_deg <= 90.0):
            raise ValueError(f"invalid coordinates for field {field.field_id}")
        if not (0.0 < field.radius_deg <= 3.5):
            raise ValueError(f"radius_deg must be in (0, 3.5] for field {field.field_id}")
        fields.append(field)
    ids = [field.field_id for field in fields]
    if len(set(ids)) != len(ids):
        raise ValueError("field_id values must be unique")

    role_mix = payload.get("portfolio_role_mix")
    if role_mix != {"new": 6, "followup": 3, "control": 1}:
        raise ValueError("portfolio_role_mix must record the approved 60/30/10 batch")
    controls = payload.get("controls")
    if not isinstance(controls, list) or len(controls) != 1:
        raise ValueError("the approved batch requires exactly one control definition")

    return PortfolioBatch(
        batch_id=batch_id,
        nights=nights,
        fields=tuple(fields),
        manifest_sha256=_manifest_sha256(resolved),
        source_path=resolved,
    )


def assigned_nights(
    nights: tuple[str, ...], shard_index: int, shard_count: int
) -> tuple[str, ...]:
    """Return deterministic, disjoint night ownership for one shard."""
    if shard_count < 1 or not (0 <= shard_index < shard_count):
        raise ValueError("shard_index must be in [0, shard_count)")
    return nights[shard_index::shard_count]


def _angular_separation_deg(field: SearchField, ra_deg: float, dec_deg: float) -> float:
    """Compute great-circle separation using the same geometry as the ingester."""
    ra1, dec1, ra2, dec2 = map(
        math.radians, (field.ra_deg, field.dec_deg, ra_deg, dec_deg)
    )
    d_ra = ra2 - ra1
    d_dec = dec2 - dec1
    value = (
        math.sin(d_dec / 2.0) ** 2
        + math.cos(dec1) * math.cos(dec2) * math.sin(d_ra / 2.0) ** 2
    )
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(value))))


def matching_field_ids(
    fields: tuple[SearchField, ...], ra_deg: float, dec_deg: float
) -> tuple[str, ...]:
    """Return every field cone containing one source position."""
    return tuple(
        field.field_id
        for field in fields
        if _angular_separation_deg(field, ra_deg, dec_deg) <= field.radius_deg
    )


def _checkpoint_path(out_dir: Path, batch: PortfolioBatch, night: str) -> Path:
    return out_dir / batch.batch_id / f"{night}.json"


def resolve_output_dir(path: Path) -> Path:
    """Keep downloaded observations and checkpoints inside this repository."""
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("--out-dir must resolve inside the repository") from exc
    return resolved


def _read_checkpoint(
    path: Path, batch: PortfolioBatch, min_rb: float, max_per_field_night: int
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "batch_id": batch.batch_id,
        "batch_manifest_sha256": batch.manifest_sha256,
        "min_rb": min_rb,
        "max_per_field_night": max_per_field_night,
    }
    actual = {key: state.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(
            f"checkpoint {path} does not match this batch/query; expected "
            f"{expected}, found {actual}"
        )
    return state


def _write_checkpoint(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def ingest_portfolio_night(
    night: str,
    batch: PortfolioBatch,
    out_dir: Path,
    min_rb: float,
    max_per_field_night: int,
) -> dict[str, Any]:
    """Stream one night once and retain bounded observations per field."""
    checkpoint = _checkpoint_path(out_dir, batch, night)
    resumed = _read_checkpoint(checkpoint, batch, min_rb, max_per_field_night)
    if resumed is not None:
        print(f"[resume] {night}: {checkpoint}", flush=True)
        return resumed

    url = f"{single_ingest._ARCHIVE_BASE_URL}ztf_public_{night}.tar.gz"
    head = requests.head(url, timeout=30, allow_redirects=True)
    head.raise_for_status()
    total_bytes = int(head.headers.get("Content-Length", 0))
    print(
        f"[portfolio] {night}: remote size {single_ingest._fmt_bytes(total_bytes)}; "
        f"fields={len(batch.fields)}",
        flush=True,
    )

    import fastavro

    observations: dict[str, list[dict[str, Any]]] = {
        field.field_id: [] for field in batch.fields
    }
    scanned = 0
    started = time.monotonic()
    response = single_ingest._open_stream_with_retry(url)
    try:
        reader = single_ingest._CountingReader(response.raw)
        with tarfile.open(fileobj=reader, mode="r|gz") as archive:
            for member in archive:
                if not member.name.endswith(".avro"):
                    continue
                if all(len(rows) >= max_per_field_night for rows in observations.values()):
                    break
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                for record in fastavro.reader(handle):
                    scanned += 1
                    if scanned % PROGRESS_EVERY == 0:
                        elapsed = time.monotonic() - started
                        fraction = reader.bytes_read / total_bytes if total_bytes else 0.0
                        eta = elapsed / fraction - elapsed if fraction > 0 else 0.0
                        kept = sum(len(rows) for rows in observations.values())
                        print(
                            f"[portfolio] {night}: scanned={scanned} kept={kept} "
                            f"{100.0 * fraction:.1f}% elapsed "
                            f"{single_ingest._fmt_duration(elapsed)} ETA "
                            f"{single_ingest._fmt_duration(eta)}",
                            flush=True,
                        )
                    candidate = record.get("candidate", {})
                    rb = candidate.get("rb")
                    ra = candidate.get("ra")
                    dec = candidate.get("dec")
                    if rb is None or rb < min_rb or ra is None or dec is None:
                        continue
                    matched = matching_field_ids(batch.fields, float(ra), float(dec))
                    if not matched:
                        continue
                    observation = single_ingest._packet_to_observation_dict(candidate, record)
                    if observation is None:
                        continue
                    for field_id in matched:
                        if len(observations[field_id]) < max_per_field_night:
                            observations[field_id].append(observation)
    finally:
        response.close()

    elapsed = time.monotonic() - started
    state: dict[str, Any] = {
        "batch_id": batch.batch_id,
        "batch_manifest": batch.source_path.relative_to(REPO_ROOT).as_posix(),
        "batch_manifest_sha256": batch.manifest_sha256,
        "night": night,
        "source_url": url,
        "source_content_length_bytes": total_bytes,
        "min_rb": min_rb,
        "max_per_field_night": max_per_field_night,
        "scanned_count": scanned,
        "kept_count": sum(len(rows) for rows in observations.values()),
        "field_kept_counts": {
            field_id: len(rows) for field_id, rows in observations.items()
        },
        "observations_by_field": observations,
        "elapsed_seconds": round(elapsed, 2),
    }
    _write_checkpoint(checkpoint, state)
    print(
        f"[portfolio] {night}: complete scanned={scanned} "
        f"kept={state['kept_count']} elapsed={single_ingest._fmt_duration(elapsed)}",
        flush=True,
    )
    return state


def run_shard(
    batch: PortfolioBatch,
    out_dir: Path,
    shard_index: int,
    shard_count: int,
    workers: int,
    min_rb: float,
    max_per_field_night: int,
) -> dict[str, Any]:
    """Run one shard and write its compact local science summary."""
    nights = assigned_nights(batch.nights, shard_index, shard_count)
    if workers < 1:
        raise ValueError("workers must be >= 1")
    print(
        f"[shard] index={shard_index}/{shard_count} workers={workers} "
        f"nights={list(nights)}",
        flush=True,
    )
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(nights)))) as pool:
        futures = {
            pool.submit(
                ingest_portfolio_night,
                night,
                batch,
                out_dir,
                min_rb,
                max_per_field_night,
            ): night
            for night in nights
        }
        for future in as_completed(futures):
            night = futures[future]
            results[night] = future.result()

    summary = {
        "batch_id": batch.batch_id,
        "batch_manifest_sha256": batch.manifest_sha256,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "workers": workers,
        "nights": list(nights),
        "scanned_count": sum(item["scanned_count"] for item in results.values()),
        "kept_count": sum(item["kept_count"] for item in results.values()),
        "status": "succeeded",
    }
    summary_path = out_dir / batch.batch_id / f"shard_{shard_index:02d}_summary.json"
    _write_checkpoint(summary_path, summary)
    print(f"[shard] wrote {summary_path}", flush=True)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-rb", type=float, default=0.5)
    parser.add_argument("--max-per-field-night", type=int, default=5_000)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not (0.0 <= args.min_rb <= 1.0):
        raise SystemExit("--min-rb must be in [0, 1]")
    if args.max_per_field_night < 1:
        raise SystemExit("--max-per-field-night must be >= 1")
    try:
        batch = load_batch_manifest(args.batch_manifest)
        run_shard(
            batch=batch,
            out_dir=resolve_output_dir(args.out_dir),
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            workers=args.workers,
            min_rb=args.min_rb,
            max_per_field_night=args.max_per_field_night,
        )
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
