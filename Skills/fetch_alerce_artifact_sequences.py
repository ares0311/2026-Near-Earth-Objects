#!/usr/bin/env python3
"""Acquire bounded ALeRCE bogus-object histories for the Tier 3 artifact class.

The ALeRCE public broker supplies ZTF object identities and detection histories
that are absent from the repository's single-alert Tier 2 download. This Skill
performs read-only queries, records provenance, checkpoints after every object,
and never accesses credentials or submits observations.

Usage:
    caffeinate -i .venv/bin/python Skills/fetch_alerce_artifact_sequences.py \
        --output data/sequences/alerce_artifact_pilot.json \
        --max-objects 50 --resume --workers 8

Threading notes
---------------
--workers controls how many detection-fetch requests are issued concurrently
within each candidate page.  Candidate-page iteration (query_objects) is
always sequential because paging requires ordered results.  Each detection
worker sleeps query_delay_seconds after its own request.  With 8 workers and a
0.25 s delay the peak detection-fetch rate is approximately 32 req/s; the
public ALeRCE API tolerates bursts of this size but may throttle at sustained
high rates.  Default is --workers 1 (sequential), which preserves the original
behaviour exactly.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "alerce-artifact-sequences-v2"
ARTIFACT_LABEL = 3
FILTER_MAP = {1: "g", 2: "r", 3: "i"}


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for acquisition provenance."""
    return datetime.now(UTC).isoformat()


def _new_client() -> Any:
    """Create the optional public ALeRCE client only when live acquisition runs."""
    try:
        from alerce.core import Alerce  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "ALeRCE client is required; install the training extras with "
            '`python -m pip install -e ".[training]"`'
        ) from exc
    return Alerce()


def _configure_client_network(client: Any, request_timeout_seconds: float) -> None:
    """Normalize the legacy ZTF endpoint and enforce a timeout on every request."""
    if request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be positive")
    legacy_client = getattr(client, "legacy_ztf_client", None)
    if legacy_client is None:
        return

    # ALeRCE 2.3.0 combines a slash-terminated base with slash-prefixed routes.
    # Removing the trailing slash avoids an unnecessary redirect on every call.
    config = getattr(legacy_client, "config", None)
    if isinstance(config, dict) and isinstance(config.get("ZTF_API_URL"), str):
        config["ZTF_API_URL"] = config["ZTF_API_URL"].rstrip("/")

    session = getattr(legacy_client, "session", None)
    if session is None or not callable(getattr(session, "request", None)):
        return
    original_request = session.request

    def request_with_timeout(method: str, url: str, **kwargs: Any) -> Any:
        """Delegate to Requests while supplying the timeout omitted by ALeRCE."""
        kwargs.setdefault("timeout", request_timeout_seconds)
        return original_request(method, url, **kwargs)

    session.request = request_with_timeout


def _request_with_retries(
    operation: Callable[..., Any],
    *,
    operation_name: str,
    attempts: int,
    retry_delay_seconds: float,
    sleep_fn: Callable[[float], None],
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
) -> Any:
    """Run one broker request with bounded retries and a useful final error."""
    if attempts < 1:
        raise ValueError("request attempts must be at least 1")
    request_kwargs = kwargs or {}
    for attempt in range(1, attempts + 1):
        try:
            return operation(*args, **request_kwargs)
        except Exception as exc:
            if attempt == attempts:
                raise RuntimeError(
                    f"{operation_name} failed after {attempts} attempts"
                ) from exc
            if retry_delay_seconds:
                sleep_fn(min(retry_delay_seconds * (2 ** (attempt - 1)), 60.0))
    raise AssertionError("bounded retry loop exited unexpectedly")


def _records(payload: Any) -> list[dict[str, Any]]:
    """Normalize ALeRCE list and paginated JSON response shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "objects"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _night_count(observations: list[dict[str, Any]]) -> int:
    """Count UTC observing dates from Julian dates."""
    return len({int(float(observation["jd"]) + 0.5) for observation in observations})


def _sample_full_arc(
    observations: list[dict[str, Any]],
    max_observations: int,
) -> list[dict[str, Any]]:
    """Bound a ZTF history while retaining detections across its complete arc."""
    ordered = sorted(observations, key=lambda observation: observation["jd"])
    if len(ordered) <= max_observations:
        return ordered
    denominator = max_observations - 1
    indices = {
        round(index * (len(ordered) - 1) / denominator)
        for index in range(max_observations)
    }
    return [ordered[index] for index in sorted(indices)]


def _serialize_detection(oid: str, detection: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one ALeRCE ZTF detection into the common Tier 3 observation contract."""
    required = ("mjd", "ra", "dec")
    if any(detection.get(name) is None for name in required):
        return None
    try:
        mjd = float(detection["mjd"])
        ra_deg = float(detection["ra"])
        dec_deg = float(detection["dec"])
        magnitude = float(detection.get("magpsf", 20.0))
        magnitude_error = float(detection.get("sigmapsf", 0.0))
        filter_id = int(detection.get("fid", 2))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= ra_deg < 360.0 and -90.0 <= dec_deg <= 90.0):
        return None

    candid = detection.get("candid", detection.get("measurement_id", "unknown"))
    return {
        "obs_id": f"{oid}:{candid}",
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "jd": mjd + 2400000.5,
        "mag": magnitude,
        "mag_err": magnitude_error,
        "filter_band": FILTER_MAP.get(filter_id, "r"),
        "mission": "ZTF",
        "rb": detection.get("rb"),
        "drb": detection.get("drb"),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Checkpoint an acquisition atomically so interrupted runs remain resumable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _new_dataset(
    max_objects: int,
    probability: float,
    class_name: str,
    request_timeout_seconds: float,
    request_attempts: int,
    candidate_page_size: int,
) -> dict[str, Any]:
    """Create the versioned, secret-free ALeRCE acquisition envelope."""
    now = _utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": now,
        "updated_at_utc": now,
        "source": {
            "provider": "ALeRCE public ZTF broker",
            "client": "alerce.core.Alerce",
            "classifier": "stamp_classifier",
            "class_name": class_name,
            "minimum_probability": probability,
            "requested_object_count": max_objects,
            "request_timeout_seconds": request_timeout_seconds,
            "request_attempts": request_attempts,
            "candidate_page_size": candidate_page_size,
        },
        "safety": {
            "external_submission_enabled": False,
            "impact_probability_generated": False,
            "secret_values_recorded": False,
        },
        "summary": {},
        "entries": [],
        "query_log": [],
        "candidate_pages": [],
        "acquisition_errors": [],
    }


def _update_summary(dataset: dict[str, Any], max_objects: int) -> None:
    """Refresh aggregate evidence after each durable checkpoint."""
    entries = dataset["entries"]
    dataset["updated_at_utc"] = _utc_now()
    dataset["summary"] = {
        "requested_objects": max_objects,
        "queried_objects": len(dataset["query_log"]),
        "accepted_objects": len(entries),
        "accepted_class_counts": {"stellar_artifact": len(entries)},
        "total_observations": sum(len(entry["observations"]) for entry in entries),
    }


def _fetch_detections_for_oid(
    oid: str,
    client: Any,
    request_attempts: int,
    retry_delay_seconds: float,
    max_observations_per_object: int,
    min_observations: int,
    min_nights: int,
    query_delay_seconds: float,
    sleep_fn: Callable[[float], None],
) -> tuple[str, list[dict[str, Any]], int, str, dict[str, Any] | None]:
    """Fetch and process detections for one ALeRCE OID.

    Returns (oid, observations, night_count, status, acquisition_error | None).
    Safe to call from a worker thread: uses no shared mutable state.
    """
    acquisition_error: dict[str, Any] | None = None
    observations: list[dict[str, Any]] = []
    night_count = 0
    status = "accepted"

    try:
        detection_payload = _request_with_retries(
            client.query_detections,
            operation_name=f"ALeRCE detections for {oid}",
            attempts=request_attempts,
            retry_delay_seconds=retry_delay_seconds,
            sleep_fn=sleep_fn,
            args=(oid,),
            kwargs={"survey": "ztf", "format": "json"},
        )
        detections = _records(detection_payload)
        observations = [
            obs
            for det in detections
            if (obs := _serialize_detection(oid, det)) is not None
        ]
        observations = _sample_full_arc(observations, max_observations_per_object)
        night_count = _night_count(observations)
        if len(observations) < min_observations:
            status = "insufficient_observations"
        elif night_count < min_nights:
            status = "insufficient_nights"
    except RuntimeError as exc:
        observations = []
        night_count = 0
        status = "query_error"
        acquisition_error = {
            "operation": "query_detections",
            "oid": oid,
            "error_type": type(exc.__cause__).__name__,
            "failed_at_utc": _utc_now(),
        }

    # Per-worker inter-request courtesy delay.
    if query_delay_seconds:
        sleep_fn(query_delay_seconds)

    return oid, observations, night_count, status, acquisition_error


def collect_artifact_sequences(
    output_json: Path,
    max_objects: int,
    *,
    probability: float = 0.9,
    class_name: str = "bogus",
    min_observations: int = 3,
    min_nights: int = 2,
    max_observations_per_object: int = 20,
    query_delay_seconds: float = 0.25,
    request_timeout_seconds: float = 30.0,
    request_attempts: int = 3,
    retry_delay_seconds: float = 5.0,
    candidate_page_size: int = 25,
    max_candidate_pages: int = 40,
    resume: bool = False,
    workers: int = 1,
    client_factory: Callable[[], Any] = _new_client,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Collect public broker-labeled multi-epoch artifact sequences.

    Args:
        workers: Number of parallel detection-fetch threads per candidate page.
            Default 1 (sequential).  Candidate-page queries (query_objects) are
            always sequential; only detection fetches are parallelised.
    """
    if max_objects < 1:
        raise ValueError("max_objects must be at least 1")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    if min_observations < 2 or min_nights < 1:
        raise ValueError("minimum observations/nights are invalid")
    if max_observations_per_object < min_observations:
        raise ValueError("max_observations_per_object cannot be below min_observations")
    if query_delay_seconds < 0:
        raise ValueError("query_delay_seconds cannot be negative")
    if request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be positive")
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds cannot be negative")
    if not 1 <= candidate_page_size <= 250:
        raise ValueError("candidate_page_size must be between 1 and 250")
    if request_attempts < 1 or max_candidate_pages < 1:
        raise ValueError("request attempts and candidate pages must be at least 1")
    if workers < 1:
        raise ValueError("workers must be at least 1")

    if resume and output_json.exists():
        dataset = json.loads(output_json.read_text(encoding="utf-8"))
        if dataset.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("existing output uses an incompatible schema version")
        source = dataset.get("source", {})
        if (
            source.get("class_name") != class_name
            or source.get("minimum_probability") != probability
            or source.get("requested_object_count") != max_objects
            or source.get("candidate_page_size") != candidate_page_size
        ):
            raise ValueError("existing output uses different ALeRCE label criteria")
        dataset.setdefault("candidate_pages", [])
        dataset.setdefault("acquisition_errors", [])
    else:
        dataset = _new_dataset(
            max_objects,
            probability,
            class_name,
            request_timeout_seconds,
            request_attempts,
            candidate_page_size,
        )

    client = client_factory()
    _configure_client_network(client, request_timeout_seconds)
    completed: set[str] = {
        item["oid"]
        for item in dataset["query_log"]
        if item.get("status") != "query_error"
    }
    accepted: set[str] = {entry["designation"] for entry in dataset["entries"]}
    _update_summary(dataset, max_objects)
    # Write the envelope before the first request so even connection failures
    # leave durable, secret-free evidence for diagnosis and a subsequent resume.
    _atomic_write_json(output_json, dataset)

    # Small, oid-ordered pages avoid the expensive detection-count sort that can
    # time out on the public classifier join.
    for page in range(1, max_candidate_pages + 1):
        if len(accepted) >= max_objects:
            break
        try:
            payload = _request_with_retries(
                client.query_objects,
                operation_name=f"ALeRCE object page {page}",
                attempts=request_attempts,
                retry_delay_seconds=retry_delay_seconds,
                sleep_fn=sleep_fn,
                kwargs={
                    "survey": "ztf",
                    "classifier": "stamp_classifier",
                    "class_name": class_name,
                    "probability": probability,
                    "order_by": "oid",
                    "order_mode": "ASC",
                    "page": page,
                    "page_size": candidate_page_size,
                    "format": "json",
                },
            )
        except RuntimeError as exc:
            dataset["acquisition_errors"].append(
                {
                    "operation": "query_objects",
                    "page": page,
                    "error_type": type(exc.__cause__).__name__,
                    "failed_at_utc": _utc_now(),
                }
            )
            _update_summary(dataset, max_objects)
            _atomic_write_json(output_json, dataset)
            raise

        objects = _records(payload)
        dataset["candidate_pages"].append(
            {
                "page": page,
                "returned_objects": len(objects),
                "queried_at_utc": _utc_now(),
            }
        )
        _atomic_write_json(output_json, dataset)
        if not objects:
            break

        # Filter the page to OIDs that still need detection fetching.
        pending = [
            str(item.get("oid", "")).strip()
            for item in objects
            if str(item.get("oid", "")).strip()
            and str(item.get("oid", "")).strip() not in completed
        ]

        if workers == 1:
            # Sequential: process one OID at a time.
            for oid in pending:
                if len(accepted) >= max_objects:
                    break
                _process_oid_result(
                    *_fetch_detections_for_oid(
                        oid,
                        client,
                        request_attempts,
                        retry_delay_seconds,
                        max_observations_per_object,
                        min_observations,
                        min_nights,
                        query_delay_seconds,
                        sleep_fn,
                    ),
                    dataset=dataset,
                    accepted=accepted,
                    completed=completed,
                    max_objects=max_objects,
                    output_json=output_json,
                )
        else:
            # Parallel: fan out detection fetches for all OIDs on the page.
            _process_page_parallel(
                [oid for oid in pending if len(accepted) < max_objects],
                client=client,
                dataset=dataset,
                accepted=accepted,
                completed=completed,
                max_objects=max_objects,
                output_json=output_json,
                request_attempts=request_attempts,
                retry_delay_seconds=retry_delay_seconds,
                max_observations_per_object=max_observations_per_object,
                min_observations=min_observations,
                min_nights=min_nights,
                query_delay_seconds=query_delay_seconds,
                sleep_fn=sleep_fn,
                workers=workers,
            )

    _update_summary(dataset, max_objects)
    _atomic_write_json(output_json, dataset)
    if len(accepted) < max_objects:
        raise RuntimeError(
            f"ALeRCE returned only {len(accepted)} accepted artifact sequences; "
            f"{max_objects} required"
        )
    return dataset


def _process_oid_result(
    oid: str,
    observations: list[dict[str, Any]],
    night_count: int,
    status: str,
    acquisition_error: dict[str, Any] | None,
    *,
    dataset: dict[str, Any],
    accepted: set[str],
    completed: set[str],
    max_objects: int,
    output_json: Path,
) -> None:
    """Apply one OID's fetch result to the shared dataset and checkpoint."""
    if acquisition_error is not None:
        dataset["acquisition_errors"].append(acquisition_error)

    dataset["query_log"].append(
        {
            "oid": oid,
            "status": status,
            "observation_count": len(observations),
            "night_count": night_count,
            "queried_at_utc": _utc_now(),
        }
    )
    completed.add(oid)
    if status == "accepted" and len(accepted) < max_objects:
        dataset["entries"].append(
            {
                "designation": oid,
                "label": ARTIFACT_LABEL,
                "class_name": "stellar_artifact",
                "label_source": "ALeRCE_stamp_classifier",
                "label_basis": (
                    f"ALeRCE stamp_classifier, "
                    f"probability>={dataset['source']['minimum_probability']}"
                ),
                "sequence_window": "full",
                "observation_count": len(observations),
                "night_count": night_count,
                "observations": observations,
                "provenance": {
                    "provider": "ALeRCE public ZTF broker",
                    "retrieval_client": "alerce.core.Alerce",
                    "retrieved_at_utc": _utc_now(),
                },
            }
        )
        accepted.add(oid)

    _update_summary(dataset, max_objects)
    _atomic_write_json(output_json, dataset)


def _process_page_parallel(
    pending: list[str],
    *,
    client: Any,
    dataset: dict[str, Any],
    accepted: set[str],
    completed: set[str],
    max_objects: int,
    output_json: Path,
    request_attempts: int,
    retry_delay_seconds: float,
    max_observations_per_object: int,
    min_observations: int,
    min_nights: int,
    query_delay_seconds: float,
    sleep_fn: Callable[[float], None],
    workers: int,
) -> None:
    """Fan out detection fetches for all OIDs on one page and merge results."""
    _lock = threading.Lock()

    def _submit(oid: str) -> tuple[str, list[dict[str, Any]], int, str, dict[str, Any] | None]:
        return _fetch_detections_for_oid(
            oid,
            client,
            request_attempts,
            retry_delay_seconds,
            max_observations_per_object,
            min_observations,
            min_nights,
            query_delay_seconds,
            sleep_fn,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_submit, oid): oid for oid in pending}
        for future in as_completed(futures):
            oid_r, obs, nc, st, err = future.result()
            with _lock:
                _process_oid_result(
                    oid_r,
                    obs,
                    nc,
                    st,
                    err,
                    dataset=dataset,
                    accepted=accepted,
                    completed=completed,
                    max_objects=max_objects,
                    output_json=output_json,
                )


def main() -> None:
    """Parse the bounded operator-facing acquisition command."""
    parser = argparse.ArgumentParser(
        description="Acquire public ALeRCE bogus-object histories for Tier 3."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-objects", type=int, default=50)
    parser.add_argument("--probability", type=float, default=0.9)
    parser.add_argument("--class-name", default="bogus")
    parser.add_argument("--min-observations", type=int, default=3)
    parser.add_argument("--min-nights", type=int, default=2)
    parser.add_argument("--max-observations-per-object", type=int, default=20)
    parser.add_argument("--query-delay-seconds", type=float, default=0.25)
    parser.add_argument("--request-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--request-attempts", type=int, default=3)
    parser.add_argument("--retry-delay-seconds", type=float, default=5.0)
    parser.add_argument("--candidate-page-size", type=int, default=25)
    parser.add_argument("--max-candidate-pages", type=int, default=40)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel detection-fetch threads per page (default 1).",
    )
    args = parser.parse_args()
    dataset = collect_artifact_sequences(
        args.output,
        args.max_objects,
        probability=args.probability,
        class_name=args.class_name,
        min_observations=args.min_observations,
        min_nights=args.min_nights,
        max_observations_per_object=args.max_observations_per_object,
        query_delay_seconds=args.query_delay_seconds,
        request_timeout_seconds=args.request_timeout_seconds,
        request_attempts=args.request_attempts,
        retry_delay_seconds=args.retry_delay_seconds,
        candidate_page_size=args.candidate_page_size,
        max_candidate_pages=args.max_candidate_pages,
        resume=args.resume,
        workers=args.workers,
    )
    print(json.dumps(dataset["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
