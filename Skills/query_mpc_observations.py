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
        --resume \
        --workers 4

Exit 0 on success; exit 1 on error.

Threading notes
---------------
--workers controls how many designations are fetched concurrently.  Request
*starts* are staggered globally by --query-delay-seconds regardless of worker
count: only one thread may start a new request per interval.  Workers still
pipeline (multiple requests are in-flight simultaneously), so --workers 4 with
a 1 s delay gives ~4× throughput while the aggregate request-start rate stays
at 1/s — well within MPC's guidance of ~2 req/s.  The default is --workers 1
(sequential), which preserves the original behaviour exactly.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PYTHONPATH_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PYTHONPATH_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHONPATH_SRC))

from fetch import fetch_mpc_observations  # noqa: E402

SCHEMA_VERSION = "mpc-tracklet-sequences-v3"
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
        if not designation:
            continue
        if designation in seen:
            raise ValueError(f"duplicate designation in label manifest: {designation}")
        if class_name not in LABEL_MAP:
            raise ValueError(f"unsupported neo_class for {designation}: {class_name}")
        seen.add(designation)
        validated.append({key: str(value or "") for key, value in row.items()})
    if not validated:
        raise ValueError("label manifest contains no usable unique designations")
    return validated


def _strict_fetcher(designation: str, force_refresh: bool = False) -> list[Any]:
    """Fetch one MPC history while preserving provider failures for audit logs."""
    return fetch_mpc_observations(
        designation,
        force_refresh=force_refresh,
        raise_on_error=True,
    )


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


def _new_dataset(
    labels_csv: Path,
    selected: list[dict[str, str]],
    target_per_class: int | None,
) -> dict[str, Any]:
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
            "target_accepted_per_class": target_per_class,
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


def _update_summary(
    dataset: dict[str, Any],
    selected_count: int,
    target_per_class: int | None,
) -> None:
    """Refresh aggregate counts after each durable checkpoint."""
    entries = dataset["entries"]
    query_log = dataset["query_log"]
    class_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        class_counts[entry["class_name"]] += 1
    dataset["updated_at_utc"] = _utc_now()
    summary: dict[str, Any] = {
        "selected_objects": selected_count,
        "accepted_objects": len(entries),
        "queried_objects": len({item["designation"] for item in query_log}),
        "accepted_class_counts": dict(sorted(class_counts.items())),
        "total_observations": sum(len(entry["observations"]) for entry in entries),
    }
    if target_per_class is not None:
        target_classes = sorted(
            {entry["class_name"] for entry in entries}
            | {item["class_name"] for item in query_log}
        )
        summary["target_accepted_per_class"] = target_per_class
        summary["target_met"] = all(
            class_counts[class_name] >= target_per_class
            for class_name in target_classes
        )
    dataset["summary"] = summary


class _RateLimiter:
    """Stagger request starts across threads: one slot per min_interval seconds.

    Each thread atomically reserves a time slot while holding the lock, then
    releases the lock and sleeps only for its own slot's wait time.  This means
    N threads are always pipelined (their requests overlap in flight) while the
    aggregate request-start rate never exceeds 1 / min_interval per second.

    With min_interval=0 the limiter is a no-op (used by tests with delay=0).
    """

    def __init__(self, min_interval: float, sleep_fn: Callable[[float], None]) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_slot = 0.0
        self._sleep_fn = sleep_fn

    def acquire(self) -> None:
        """Block until this thread's reserved time slot arrives."""
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now >= self._next_slot:
                # Take the slot immediately and set the next one.
                self._next_slot = now + self._min_interval
                return
            # Reserve the next available slot before releasing the lock so
            # other threads get their own distinct slots, not the same one.
            wait = self._next_slot - now
            self._next_slot += self._min_interval
        self._sleep_fn(wait)


def _fetch_designation_result(
    row: dict[str, str],
    fetcher: Callable[..., list[Any]],
    retries: int,
    retry_delay_seconds: float,
    max_observations_per_object: int,
    min_observations: int,
    min_nights: int,
    sleep_fn: Callable[[float], None],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Fetch and process one designation; return (log_item, entry_item | None).

    Designed to be called from a worker thread: all inputs are immutable or
    thread-local, and the function never touches shared dataset state.
    Pacing (inter-designation delay) is the caller's responsibility.
    """
    designation = row["designation"]
    class_name = row["neo_class"]
    sequence_window = row.get("sequence_window", "full") or "full"

    observations: list[Any] = []
    attempts = 0
    provider_error: Exception | None = None

    for attempt in range(retries + 1):
        attempts = attempt + 1
        try:
            observations = fetcher(designation, force_refresh=attempt > 0)
            provider_error = None
        except Exception as exc:
            provider_error = exc
            observations = []
        if observations:
            break
        if attempt < retries and retry_delay_seconds:
            sleep_fn(retry_delay_seconds)

    raw_observation_count = len(observations)
    observations = _select_observation_window(
        observations,
        sequence_window,
        max_observations_per_object,
        min_nights,
    )
    n_nights = _night_count(observations)

    status = "accepted"
    if provider_error is not None:
        status = "query_error"
    elif len(observations) < min_observations:
        status = "insufficient_observations"
    elif n_nights < min_nights:
        status = "insufficient_nights"

    log_item: dict[str, Any] = {
        "designation": designation,
        "class_name": class_name,
        "status": status,
        "attempts": attempts,
        "raw_observation_count": raw_observation_count,
        "observation_count": len(observations),
        "night_count": n_nights,
        "sequence_window": sequence_window,
        "queried_at_utc": _utc_now(),
        "error_type": type(provider_error).__name__ if provider_error else None,
    }

    entry_item: dict[str, Any] | None = None
    if status == "accepted":
        entry_item = {
            "designation": designation,
            "label": LABEL_MAP[class_name],
            "class_name": class_name,
            "h_mag": row.get("h_mag", ""),
            "label_source": row.get("source", ""),
            "label_basis": row.get("label_basis", ""),
            "sequence_window": sequence_window,
            "observation_count": len(observations),
            "night_count": n_nights,
            "observations": [_serialize_observation(obs) for obs in observations],
            "provenance": {
                "provider": "Minor Planet Center",
                "retrieval_client": "astroquery.mpc.MPC.get_observations",
                "retrieved_at_utc": _utc_now(),
            },
        }

    return log_item, entry_item


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
    max_consecutive_query_errors: int = 3,
    target_per_class: int | None = None,
    resume: bool = False,
    workers: int = 1,
    fetcher: Callable[..., list[Any]] = _strict_fetcher,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Collect a bounded, resumable MPC sequence dataset for Tier 3 training.

    Args:
        workers: Number of parallel fetch threads.  Default 1 (sequential).
            Increase to speed up large runs; see module docstring for MPC
            rate-limit guidance.  A global rate limiter staggers request starts
            by query_delay_seconds regardless of worker count, so throughput
            scales with workers while the request-start rate stays bounded.
    """
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
    if max_consecutive_query_errors < 1:
        raise ValueError("max_consecutive_query_errors must be at least 1")
    if target_per_class is not None and target_per_class < 1:
        raise ValueError("target_per_class must be at least 1")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    rows = _load_manifest_rows(labels_csv)
    selected = _balanced_selection(rows, max_objects)
    if resume and output_json.exists():
        dataset = json.loads(output_json.read_text(encoding="utf-8"))
        if dataset.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("existing output uses an incompatible schema version")
        if dataset.get("source", {}).get("label_manifest_sha256") != _sha256_file(labels_csv):
            raise ValueError("existing output was created from a different label manifest")
        if dataset.get("source", {}).get("target_accepted_per_class") != target_per_class:
            raise ValueError("existing output uses a different per-class acceptance target")
    else:
        dataset = _new_dataset(labels_csv, selected, target_per_class)

    accepted: set[str] = {entry["designation"] for entry in dataset["entries"]}
    accepted_counts: dict[str, int] = defaultdict(int)
    for entry in dataset["entries"]:
        accepted_counts[entry["class_name"]] += 1
    completed: set[str] = {
        item["designation"]
        for item in dataset["query_log"]
        if item.get("status") != "query_error"
    }

    # Build the list of designations that still need fetching.
    todo = [
        row for row in selected
        if row["designation"] not in completed and row["designation"] not in accepted
        and (
            target_per_class is None
            or accepted_counts[row["neo_class"]] < target_per_class
        )
    ]

    if workers == 1:
        _collect_sequential(
            todo,
            dataset,
            output_json,
            selected,
            accepted,
            accepted_counts,
            fetcher=fetcher,
            retries=retries,
            query_delay_seconds=query_delay_seconds,
            max_observations_per_object=max_observations_per_object,
            min_observations=min_observations,
            min_nights=min_nights,
            max_consecutive_query_errors=max_consecutive_query_errors,
            target_per_class=target_per_class,
            sleep_fn=sleep_fn,
        )
    else:
        _collect_parallel(
            todo,
            dataset,
            output_json,
            selected,
            accepted,
            accepted_counts,
            fetcher=fetcher,
            retries=retries,
            query_delay_seconds=query_delay_seconds,
            max_observations_per_object=max_observations_per_object,
            min_observations=min_observations,
            min_nights=min_nights,
            max_consecutive_query_errors=max_consecutive_query_errors,
            target_per_class=target_per_class,
            sleep_fn=sleep_fn,
            workers=workers,
        )

    _update_summary(dataset, len(selected), target_per_class)
    _atomic_write_json(output_json, dataset)

    if target_per_class is not None:
        class_counts: dict[str, int] = defaultdict(int)
        for entry in dataset["entries"]:
            class_counts[entry["class_name"]] += 1
        missing = {
            class_name: class_counts[class_name]
            for class_name in sorted({row["neo_class"] for row in selected})
            if class_counts[class_name] < target_per_class
        }
        if missing:
            raise RuntimeError(
                "MPC candidate pool exhausted before acceptance targets were met: "
                f"{missing}; inspect {output_json}"
            )
    return dataset


def _collect_sequential(
    todo: list[dict[str, str]],
    dataset: dict[str, Any],
    output_json: Path,
    selected: list[dict[str, str]],
    accepted: set[str],
    accepted_counts: dict[str, int],
    *,
    fetcher: Callable[..., list[Any]],
    retries: int,
    query_delay_seconds: float,
    max_observations_per_object: int,
    min_observations: int,
    min_nights: int,
    max_consecutive_query_errors: int,
    target_per_class: int | None,
    sleep_fn: Callable[[float], None],
) -> None:
    """Process designations one at a time (workers=1).  Exact original semantics."""
    consecutive_query_errors = 0

    for row in todo:
        if target_per_class is not None and accepted_counts[row["neo_class"]] >= target_per_class:
            continue

        log_item, entry_item = _fetch_designation_result(
            row,
            fetcher,
            retries,
            query_delay_seconds,
            max_observations_per_object,
            min_observations,
            min_nights,
            sleep_fn,
        )
        # Sequential mode: pace requests with an explicit post-fetch delay.
        if query_delay_seconds:
            sleep_fn(query_delay_seconds)

        dataset["query_log"].append(log_item)
        if entry_item is not None:
            dataset["entries"].append(entry_item)
            accepted.add(entry_item["designation"])
            accepted_counts[entry_item["class_name"]] += 1

        _update_summary(dataset, len(selected), target_per_class)
        _atomic_write_json(output_json, dataset)

        if log_item["status"] == "query_error":
            consecutive_query_errors += 1
            if consecutive_query_errors >= max_consecutive_query_errors:
                raise RuntimeError(
                    "MPC acquisition stopped after "
                    f"{consecutive_query_errors} consecutive provider errors; "
                    f"inspect {output_json}"
                ) from None
        else:
            consecutive_query_errors = 0

        if target_per_class is not None and all(
            accepted_counts[class_name] >= target_per_class
            for class_name in sorted({row["neo_class"] for row in todo})
        ):
            break


def _collect_parallel(
    todo: list[dict[str, str]],
    dataset: dict[str, Any],
    output_json: Path,
    selected: list[dict[str, str]],
    accepted: set[str],
    accepted_counts: dict[str, int],
    *,
    fetcher: Callable[..., list[Any]],
    retries: int,
    query_delay_seconds: float,
    max_observations_per_object: int,
    min_observations: int,
    min_nights: int,
    max_consecutive_query_errors: int,
    target_per_class: int | None,
    sleep_fn: Callable[[float], None],
    workers: int,
) -> None:
    """Process designations in parallel using a thread pool.

    Thread safety: all mutations to dataset, accepted, and accepted_counts are
    serialised through _lock.  The circuit breaker counter is also lock-protected.
    When the error threshold is exceeded, _abort is set so in-flight futures
    drain without updating shared state.
    """
    _lock = threading.Lock()
    _abort = threading.Event()
    consecutive_query_errors = 0
    circuit_break_error: RuntimeError | None = None
    # One global rate limiter staggered request *starts* across all threads so
    # they never pile up simultaneously.  Workers remain pipelined (their
    # in-flight requests overlap) but each new request start waits its turn.
    _rate_limiter = _RateLimiter(query_delay_seconds, sleep_fn)

    def _submit(row: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        """Worker target: acquire rate-limit slot, then fetch (skip if aborted)."""
        if _abort.is_set():
            return None
        # Stagger this request start; blocks here until the slot is available.
        _rate_limiter.acquire()
        if _abort.is_set():
            return None
        return _fetch_designation_result(
            row,
            fetcher,
            retries,
            retry_delay_seconds=query_delay_seconds,
            max_observations_per_object=max_observations_per_object,
            min_observations=min_observations,
            min_nights=min_nights,
            sleep_fn=sleep_fn,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_row = {executor.submit(_submit, row): row for row in todo}

        for future in as_completed(future_to_row):
            result = future.result()
            if result is None:
                # Aborted before fetch started.
                continue
            log_item, entry_item = result

            with _lock:
                if _abort.is_set():
                    continue  # discard result after abort

                dataset["query_log"].append(log_item)

                # Respect target_per_class even in parallel mode: extra accepted
                # futures are discarded so counts never exceed the target.
                if entry_item is not None and (
                    target_per_class is None
                    or accepted_counts[entry_item["class_name"]] < target_per_class
                ):
                    dataset["entries"].append(entry_item)
                    accepted.add(entry_item["designation"])
                    accepted_counts[entry_item["class_name"]] += 1

                _update_summary(dataset, len(selected), target_per_class)
                _atomic_write_json(output_json, dataset)

                if log_item["status"] == "query_error":
                    consecutive_query_errors += 1
                    if consecutive_query_errors >= max_consecutive_query_errors:
                        circuit_break_error = RuntimeError(
                            "MPC acquisition stopped after "
                            f"{consecutive_query_errors} consecutive provider errors; "
                            f"inspect {output_json}"
                        )
                        _abort.set()
                else:
                    consecutive_query_errors = 0

    if circuit_break_error is not None:
        raise circuit_break_error


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
    parser.add_argument("--max-consecutive-query-errors", type=int, default=3)
    parser.add_argument(
        "--target-per-class",
        type=int,
        help="Stop only after this many accepted sequences per represented class",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel fetch threads (default 1).  See module docstring for rate-limit guidance.",
    )
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
            max_consecutive_query_errors=args.max_consecutive_query_errors,
            target_per_class=args.target_per_class,
            resume=args.resume,
            workers=args.workers,
        )
        print(json.dumps(dataset["summary"], indent=2, sort_keys=True))
        return

    if not args.designation:
        parser.error("provide a designation or use bounded batch mode")
    designation = " ".join(args.designation)
    sys.exit(query_observations(designation, as_json=args.as_json))


if __name__ == "__main__":
    main()
