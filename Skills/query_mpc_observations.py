"""Query MPC histories or build a resumable Tier 3 raw sequence dataset.

Usage:
    # Inspect one designation without creating a training dataset.
    python Skills/query_mpc_observations.py 2020 XL5
    python Skills/query_mpc_observations.py 433 --json

    # Collect a bounded, resumable raw dataset for offline Tier 3 preparation.
    python Skills/query_mpc_observations.py \
        --labels-csv data/training_labels.csv \
        --output data/sequences/mpc_raw_sequences.json \
        --max-objects 1000 \
        --resume

Exit 0 on success; exit 1 on error.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PYTHONPATH_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PYTHONPATH_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHONPATH_SRC))

from fetch import fetch_mpc_observations  # noqa: E402

SCHEMA_VERSION = "mpc-tracklet-sequences-v2"
LABEL_MAP = {
    "neo_candidate": 0,
    "known_object": 1,
    "main_belt_asteroid": 2,
    "stellar_artifact": 3,
    "other_solar_system": 4,
}


def query_observations(designation: str, as_json: bool = False) -> int:
    """Query and print one MPC designation without writing a dataset."""
    obs_list = fetch_mpc_observations(designation)
    if not obs_list:
        msg = (
            f"No observations returned for '{designation}' "
            "(network unavailable or unknown object)."
        )
        if as_json:
            print(json.dumps({
                "designation": designation,
                "n_obs": 0,
                "observations": [],
                "note": msg,
            }))
        else:
            print(msg, file=sys.stderr)
        return 0  # not a fatal error; could be network unavailable

    if as_json:
        records = []
        for o in obs_list:
            records.append(
                {
                    "obs_id": o.obs_id,
                    "ra_deg": o.ra_deg,
                    "dec_deg": o.dec_deg,
                    "jd": o.jd,
                    "mag": o.mag,
                    "mag_err": o.mag_err,
                    "filter_band": o.filter_band,
                    "mission": o.mission,
                }
            )
        print(
            json.dumps(
                {"designation": designation, "n_obs": len(records), "observations": records},
                indent=2,
            )
        )
    else:
        print(f"MPC observations for '{designation}': {len(obs_list)} records\n")
        hdr = f"{'Obs ID':<20} {'RA (deg)':>10} {'Dec (deg)':>10} {'JD':>14} {'Mag':>6} {'Band':>5}"
        print(hdr)
        print("-" * 70)
        for o in obs_list[:50]:
            print(
                f"{o.obs_id:<20} {o.ra_deg:>10.5f} {o.dec_deg:>10.5f} "
                f"{o.jd:>14.5f} {o.mag:>6.2f} {o.filter_band:>5}"
            )
        if len(obs_list) > 50:
            print(f"  ... ({len(obs_list) - 50} more observations not shown)")
    return 0


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for dataset provenance."""
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    """Return a stable content hash for the input label manifest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest_rows(labels_csv: Path) -> list[dict[str, str]]:
    """Load and validate designation/class rows from a labeled CSV manifest."""
    with labels_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("label manifest is empty")

    required = {"designation", "neo_class"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"label manifest is missing columns: {sorted(missing)}")

    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        designation = str(row.get("designation", "")).strip()
        class_name = str(row.get("neo_class", "")).strip()
        if not designation or designation in seen:
            continue
        if class_name not in LABEL_MAP:
            raise ValueError(f"unsupported neo_class for {designation}: {class_name}")
        seen.add(designation)
        validated.append({key: str(value or "") for key, value in row.items()})
    if not validated:
        raise ValueError("label manifest contains no usable unique designations")
    return validated


def _balanced_selection(rows: list[dict[str, str]], max_objects: int) -> list[dict[str, str]]:
    """Select rows round-robin by class so bounded runs do not bias early classes."""
    if max_objects < 1:
        raise ValueError("max_objects must be at least 1")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["neo_class"]].append(row)

    selected: list[dict[str, str]] = []
    class_names = sorted(grouped, key=lambda name: LABEL_MAP[name])
    while len(selected) < min(max_objects, len(rows)):
        added = False
        for class_name in class_names:
            if grouped[class_name] and len(selected) < max_objects:
                selected.append(grouped[class_name].pop(0))
                added = True
        if not added:
            break
    return selected


def _night_count(observations: list[Any]) -> int:
    """Count distinct UTC observing dates using the Julian-date noon offset."""
    return len({int(float(obs.jd) + 0.5) for obs in observations})


def _select_observation_window(
    observations: list[Any],
    window: str,
    max_observations: int,
    min_nights: int,
) -> list[Any]:
    """Bound a history while retaining temporal coverage for its label policy."""
    if window not in {"early", "late", "full"}:
        raise ValueError(f"unsupported sequence_window: {window}")
    if max_observations < 2:
        raise ValueError("max_observations must be at least 2")

    ordered = sorted(observations, key=lambda observation: observation.jd)
    if len(ordered) <= max_observations:
        return ordered

    # Full histories are sampled across the complete arc instead of truncating it.
    if window == "full":
        denominator = max_observations - 1
        indices = {
            round(index * (len(ordered) - 1) / denominator)
            for index in range(max_observations)
        }
        return [ordered[index] for index in sorted(indices)]

    directed = ordered if window == "early" else list(reversed(ordered))
    selected = directed[:max_observations]
    selected_nights = {int(float(obs.jd) + 0.5) for obs in selected}

    # Replace tail observations when a dense night would otherwise hide other nights.
    for observation in directed[max_observations:]:
        night = int(float(observation.jd) + 0.5)
        if night not in selected_nights:
            selected[-1] = observation
            selected_nights.add(night)
            if len(selected_nights) >= min_nights:
                break
    return sorted(selected, key=lambda observation: observation.jd)


def _serialize_observation(observation: Any) -> dict[str, Any]:
    """Convert one immutable Observation into the Tier 3 raw-data contract."""
    return {
        "obs_id": observation.obs_id,
        "ra_deg": observation.ra_deg,
        "dec_deg": observation.dec_deg,
        "jd": observation.jd,
        "mag": observation.mag,
        "mag_err": observation.mag_err,
        "filter_band": observation.filter_band,
        "mission": observation.mission,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a checkpoint atomically so interrupted downloads remain resumable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _new_dataset(labels_csv: Path, selected: list[dict[str, str]]) -> dict[str, Any]:
    """Create an empty versioned dataset envelope with no credential material."""
    now = _utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": now,
        "updated_at_utc": now,
        "source": {
            "provider": "Minor Planet Center",
            "client": "astroquery.mpc.MPC.get_observations",
            "label_manifest": str(labels_csv),
            "label_manifest_sha256": _sha256_file(labels_csv),
            "selected_object_count": len(selected),
            "label_map": LABEL_MAP,
        },
        "safety": {
            "external_submission_enabled": False,
            "impact_probability_generated": False,
            "secret_values_recorded": False,
        },
        "summary": {},
        "entries": [],
        "query_log": [],
    }


def _update_summary(dataset: dict[str, Any], selected_count: int) -> None:
    """Refresh aggregate counts after each durable checkpoint."""
    entries = dataset["entries"]
    query_log = dataset["query_log"]
    class_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        class_counts[entry["class_name"]] += 1
    dataset["updated_at_utc"] = _utc_now()
    dataset["summary"] = {
        "selected_objects": selected_count,
        "accepted_objects": len(entries),
        "queried_objects": len({item["designation"] for item in query_log}),
        "accepted_class_counts": dict(sorted(class_counts.items())),
        "total_observations": sum(len(entry["observations"]) for entry in entries),
    }


def collect_sequence_dataset(
    labels_csv: Path,
    output_json: Path,
    max_objects: int,
    *,
    min_observations: int = 3,
    min_nights: int = 2,
    max_observations_per_object: int = 20,
    retries: int = 2,
    query_delay_seconds: float = 1.0,
    resume: bool = False,
    fetcher: Callable[..., list[Any]] = fetch_mpc_observations,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Collect a bounded, resumable MPC sequence dataset for Tier 3 training."""
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    if min_nights < 1:
        raise ValueError("min_nights must be at least 1")
    if max_observations_per_object < min_observations:
        raise ValueError("max_observations_per_object cannot be below min_observations")
    if retries < 0:
        raise ValueError("retries cannot be negative")
    if query_delay_seconds < 0:
        raise ValueError("query_delay_seconds cannot be negative")

    rows = _load_manifest_rows(labels_csv)
    selected = _balanced_selection(rows, max_objects)
    if resume and output_json.exists():
        dataset = json.loads(output_json.read_text(encoding="utf-8"))
        if dataset.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("existing output uses an incompatible schema version")
        if dataset.get("source", {}).get("label_manifest_sha256") != _sha256_file(labels_csv):
            raise ValueError("existing output was created from a different label manifest")
    else:
        dataset = _new_dataset(labels_csv, selected)

    accepted = {entry["designation"] for entry in dataset["entries"]}
    for index, row in enumerate(selected):
        designation = row["designation"]
        if designation in accepted:
            continue

        observations: list[Any] = []
        attempts = 0
        for attempt in range(retries + 1):
            attempts = attempt + 1
            observations = fetcher(designation, force_refresh=attempt > 0)
            if observations:
                break
            if attempt < retries and query_delay_seconds:
                sleep_fn(query_delay_seconds)

        raw_observation_count = len(observations)
        sequence_window = row.get("sequence_window", "full") or "full"
        observations = _select_observation_window(
            observations,
            sequence_window,
            max_observations_per_object,
            min_nights,
        )
        n_nights = _night_count(observations)
        status = "accepted"
        if len(observations) < min_observations:
            status = "insufficient_observations"
        elif n_nights < min_nights:
            status = "insufficient_nights"

        dataset["query_log"].append(
            {
                "designation": designation,
                "class_name": row["neo_class"],
                "status": status,
                "attempts": attempts,
                "raw_observation_count": raw_observation_count,
                "observation_count": len(observations),
                "night_count": n_nights,
                "sequence_window": sequence_window,
                "queried_at_utc": _utc_now(),
            }
        )
        if status == "accepted":
            dataset["entries"].append(
                {
                    "designation": designation,
                    "label": LABEL_MAP[row["neo_class"]],
                    "class_name": row["neo_class"],
                    "h_mag": row.get("h_mag", ""),
                    "label_source": row.get("source", ""),
                    "label_basis": row.get("label_basis", ""),
                    "sequence_window": sequence_window,
                    "observation_count": len(observations),
                    "night_count": n_nights,
                    "observations": [
                        _serialize_observation(observation) for observation in observations
                    ],
                    "provenance": {
                        "provider": "Minor Planet Center",
                        "retrieval_client": "astroquery.mpc.MPC.get_observations",
                        "retrieved_at_utc": _utc_now(),
                    },
                }
            )
            accepted.add(designation)

        _update_summary(dataset, len(selected))
        _atomic_write_json(output_json, dataset)
        if index < len(selected) - 1 and query_delay_seconds:
            sleep_fn(query_delay_seconds)

    _update_summary(dataset, len(selected))
    _atomic_write_json(output_json, dataset)
    return dataset


def main() -> None:
    """Parse CLI arguments for either one-object inspection or batch collection."""
    parser = argparse.ArgumentParser(
        description="Query MPC histories or build a Tier 3 raw sequence dataset."
    )
    parser.add_argument(
        "designation",
        nargs="*",
        help="MPC designation for single-object inspection, for example '2020 XL5' or '433'",
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )
    parser.add_argument(
        "--labels-csv",
        type=Path,
        help="Labeled designation manifest for batch mode",
    )
    parser.add_argument("--output", type=Path, help="Versioned raw-sequence JSON output")
    parser.add_argument("--max-objects", type=int, help="Hard cap on queried designations")
    parser.add_argument("--min-observations", type=int, default=3)
    parser.add_argument("--min-nights", type=int, default=2)
    parser.add_argument("--max-observations-per-object", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--query-delay-seconds", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    # Batch collection is deliberately explicit and bounded.
    if args.labels_csv or args.output or args.max_objects is not None:
        if not args.labels_csv or not args.output or args.max_objects is None:
            parser.error("batch mode requires --labels-csv, --output, and --max-objects")
        dataset = collect_sequence_dataset(
            args.labels_csv,
            args.output,
            args.max_objects,
            min_observations=args.min_observations,
            min_nights=args.min_nights,
            max_observations_per_object=args.max_observations_per_object,
            retries=args.retries,
            query_delay_seconds=args.query_delay_seconds,
            resume=args.resume,
        )
        print(json.dumps(dataset["summary"], indent=2, sort_keys=True))
        return

    if not args.designation:
        parser.error("provide a designation or use bounded batch mode")
    designation = " ".join(args.designation)
    sys.exit(query_observations(designation, as_json=args.as_json))


if __name__ == "__main__":
    main()
