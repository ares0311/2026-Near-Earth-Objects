#!/usr/bin/env python3
"""Fetch ATLAS forced photometry for one sky position or a batch of positions.

Single-position mode (original):
    python Skills/fetch_atlas_data.py <ra> <dec> <start_jd> <end_jd> [--token T]

Batch mode (new): reads a CSV with columns ra,dec,start_jd,end_jd[,label],
fetches each position (optionally in parallel), and writes per-position JSON
files to --out-dir.  Supports --resume to skip positions already fetched.

    python Skills/fetch_atlas_data.py \\
        --positions-csv targets.csv \\
        --out-dir data/atlas_batch/ \\
        --workers 8 \\
        --resume \\
        --token "$ATLAS_TOKEN"

Batch CSV format (header required):
    ra,dec,start_jd,end_jd[,label]
    10.5,-5.2,2460000,2460030,target_A
    22.1,+3.7,2460000,2460030

The optional label column becomes the output filename stem; without it the
row index is used.  Existing output files are skipped when --resume is given.
Output files are written as <out-dir>/<label_or_index>.json.

Threading notes
---------------
ATLAS forced photometry requests involve server-side task queuing and a polling
loop; each request may take 10–120 s.  --workers controls how many positions
are fetched concurrently.  Default is 1 (sequential).  With gigabit connectivity
and an ATLAS token, 4–8 workers saturate the practical throughput.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PYTHONPATH_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PYTHONPATH_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHONPATH_SRC))

_DEFAULT_RUN_ROOT = Path("Logs/pipeline_runs")
_DEFAULT_WINDOW_DAYS = 1.0  # Widened from 0.05: ATLAS has ~2-day cadence; a ±72-minute
# window (0.05 d) misses ~95% of observations. 1.0 d ensures at least one
# cadence cycle is always included in the search window.
_DEFAULT_MIN_RECOVERED_SAMPLES = 3
_DEFAULT_MIN_NIGHTS = 2
_DEFAULT_MAX_MAG = 21.5
_DEFAULT_MAX_POLLS = 60
_DEFAULT_POLL_INTERVAL_SECONDS = 5.0
_TERMINAL_SAMPLE_STATUSES = {"recovered", "not_recovered", "failed"}


def _param_key(params: dict[str, Any]) -> str:
    """Return a stable key for a recovery request."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _load_positions_csv(path: Path) -> list[dict[str, Any]]:
    """Load and validate the batch positions CSV; return a list of position dicts."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("positions CSV is empty")

    required = {"ra", "dec", "start_jd", "end_jd"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"positions CSV is missing columns: {sorted(missing)}")

    positions = []
    for index, row in enumerate(rows):
        try:
            positions.append(
                {
                    "index": index,
                    "label": str(row.get("label", "") or index).strip() or str(index),
                    "ra": float(row["ra"]),
                    "dec": float(row["dec"]),
                    "start_jd": float(row["start_jd"]),
                    "end_jd": float(row["end_jd"]),
                }
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid row {index}: {exc}") from exc
    return positions


def _fetch_position(
    pos: dict[str, Any],
    atlas_token: str | None,
    force_refresh: bool,
    fetcher: Callable[..., list[Any]],
) -> tuple[dict[str, Any], list[Any]]:
    """Fetch one sky position; return (pos, observations).  Thread-safe."""
    observations = fetcher(
        ra_deg=pos["ra"],
        dec_deg=pos["dec"],
        start_jd=pos["start_jd"],
        end_jd=pos["end_jd"],
        atlas_token=atlas_token,
        force_refresh=force_refresh,
    )
    return pos, observations


def _observations_to_json(observations: list[Any]) -> list[dict[str, Any]]:
    """Serialise Observation objects into dicts for JSON output."""
    return [
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
        for o in observations
    ]


def _load_expected_known_manifest(path: Path) -> list[dict[str, Any]]:
    """Load the JSON expected-known manifest produced by build_recovery_manifest.py."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("expected-known manifest must be a JSON list")
    rows = [row for row in data if isinstance(row, dict)]
    if not rows:
        raise ValueError("expected-known manifest contains no object rows")
    return rows


def _coerce_float(value: Any) -> float | None:
    """Return a finite float or None for malformed manifest/provider values."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _manifest_samples(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized sky/time samples for one expected-known row."""
    designation = str(row.get("designation") or row.get("object_id") or "").strip()
    if not designation:
        return []
    raw_samples = row.get("samples")
    if not isinstance(raw_samples, list):
        raw_samples = [row]
    samples: list[dict[str, Any]] = []
    for index, sample in enumerate(raw_samples):
        if not isinstance(sample, dict):
            continue
        ra = _coerce_float(sample.get("ra_deg", sample.get("ra")))
        dec = _coerce_float(sample.get("dec_deg", sample.get("dec")))
        jd = _coerce_float(sample.get("jd", sample.get("expected_jd")))
        if ra is None or dec is None or jd is None:
            continue
        samples.append(
            {
                "designation": designation,
                "sample_index": index,
                "ra_deg": ra,
                "dec_deg": dec,
                "jd": jd,
                "mag": _coerce_float(sample.get("mag")),
                "source": row.get("source"),
                "tolerance_arcsec": _coerce_float(row.get("tolerance_arcsec")),
                "tolerance_days": _coerce_float(row.get("tolerance_days")),
                "min_samples": int(_coerce_float(row.get("min_samples")) or 1),
            }
        )
    return samples


def _recovery_sample_key(sample: dict[str, Any]) -> str:
    """Return a stable per-sample checkpoint key."""
    return (
        f"{sample['designation']}:{sample['sample_index']}:"
        f"{sample['ra_deg']:.8f}:{sample['dec_deg']:.8f}:{sample['jd']:.6f}"
    )


def _format_eta(elapsed: float, done: int, total: int) -> str:
    """Format progress for live operator runs."""
    eta = 0.0 if done <= 0 else max(0.0, (elapsed / done) * (total - done))
    return (
        f"elapsed {int(elapsed // 60)}m{int(elapsed % 60):02d}s "
        f"ETA {int(eta // 60)}m{int(eta % 60):02d}s"
    )


def _load_recovery_checkpoint(path: Path, params: dict[str, Any]) -> dict[str, Any]:
    """Load a matching ATLAS recovery checkpoint or return fresh state."""
    if not path.exists():
        return {"params": params, "samples": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"params": params, "samples": {}}
    if data.get("params") != params or not isinstance(data.get("samples"), dict):
        return {"params": params, "samples": {}}
    return data


def _write_json(path: Path, payload: Any) -> None:
    """Write pretty JSON with parent-directory creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _is_usable_atlas_observation(obs: Any, *, sample: dict[str, Any], max_mag: float) -> bool:
    """Return True when an ATLAS forced-photometry row is usable for recovery evidence."""
    jd = _coerce_float(getattr(obs, "jd", None))
    mag = _coerce_float(getattr(obs, "mag", None))
    mag_err = _coerce_float(getattr(obs, "mag_err", None))
    if jd is None or mag is None or mag_err is None:
        return False
    if abs(jd - float(sample["jd"])) > float(sample["window_days"]):
        return False
    return 0.0 < mag <= max_mag and 0.0 <= mag_err <= 1.0


def _atlas_obs_to_audit_dict(obs: Any, sample: dict[str, Any]) -> dict[str, Any]:
    """Serialize one ATLAS observation for audit checkpoints.

    ATLAS forced-photometry products may omit per-measurement RA/Dec. In that
    case the requested sky position is the only valid audit coordinate, so the
    generated run summary records that this is targeted forced photometry.
    """
    ra = _coerce_float(getattr(obs, "ra_deg", None))
    dec = _coerce_float(getattr(obs, "dec_deg", None))
    if ra is None or dec is None or (ra == 0.0 and dec == 0.0):
        ra = float(sample["ra_deg"])
        dec = float(sample["dec_deg"])
    fallback_id = f"atlas_{sample['designation']}_{sample['sample_index']}"
    return {
        "obs_id": str(getattr(obs, "obs_id", fallback_id)),
        "ra_deg": ra,
        "dec_deg": dec,
        "jd": float(getattr(obs, "jd")),
        "mag": float(getattr(obs, "mag")),
        "mag_err": float(getattr(obs, "mag_err")),
        "filter_band": str(getattr(obs, "filter_band", "o") or "o"),
        "mission": "ATLAS",
        "field_id": f"ATLAS_FORCED:{sample['designation']}",
    }


def _angular_sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Return great-circle separation in arcseconds."""
    ra1_rad = math.radians(ra1)
    ra2_rad = math.radians(ra2)
    dec1_rad = math.radians(dec1)
    dec2_rad = math.radians(dec2)
    sin_d_dec = math.sin((dec2_rad - dec1_rad) / 2.0)
    sin_d_ra = math.sin((ra2_rad - ra1_rad) / 2.0)
    hav = sin_d_dec**2 + math.cos(dec1_rad) * math.cos(dec2_rad) * sin_d_ra**2
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(max(0.0, hav))))) * 3600.0


def _tracklet_from_observations(
    designation: str,
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an audit-compatible Tracklet dict from recovered ATLAS observations."""
    ordered = sorted(observations, key=lambda row: float(row["jd"]))
    first = ordered[0]
    last = ordered[-1]
    arc_days = max(0.0, float(last["jd"]) - float(first["jd"]))
    sep_arcsec = _angular_sep_arcsec(
        float(first["ra_deg"]),
        float(first["dec_deg"]),
        float(last["ra_deg"]),
        float(last["dec_deg"]),
    )
    motion_rate = sep_arcsec / max(arc_days * 24.0, 1e-9)
    delta_ra = (float(last["ra_deg"]) - float(first["ra_deg"])) * math.cos(
        math.radians((float(first["dec_deg"]) + float(last["dec_deg"])) / 2.0)
    )
    delta_dec = float(last["dec_deg"]) - float(first["dec_deg"])
    pa = math.degrees(math.atan2(delta_ra, delta_dec)) % 360.0
    return {
        "object_id": f"atlas_recovery:{designation}",
        "observations": ordered,
        "arc_days": arc_days,
        "motion_rate_arcsec_per_hour": motion_rate,
        "motion_pa_degrees": pa,
        "motion_rate_uncertainty": 0.0,
    }


def _tracklets_from_recovery_state(
    state: dict[str, Any],
    *,
    min_recovered_samples: int,
    min_nights: int,
) -> list[dict[str, Any]]:
    """Create multi-night recovery tracklets from checkpointed sample results."""
    by_designation: dict[str, list[dict[str, Any]]] = {}
    seen_sample: set[tuple[str, int]] = set()
    for sample_result in state.get("samples", {}).values():
        if not isinstance(sample_result, dict) or sample_result.get("status") != "recovered":
            continue
        designation = str(sample_result.get("designation"))
        sample_index = int(sample_result.get("sample_index", -1))
        if (designation, sample_index) in seen_sample:
            continue
        observations = sample_result.get("observations")
        if not isinstance(observations, list) or not observations:
            continue
        by_designation.setdefault(designation, []).append(observations[0])
        seen_sample.add((designation, sample_index))

    tracklets: list[dict[str, Any]] = []
    for designation, observations in sorted(by_designation.items()):
        nights = {int(float(obs["jd"])) for obs in observations}
        if len(observations) >= min_recovered_samples and len(nights) >= min_nights:
            tracklets.append(_tracklet_from_observations(designation, observations))
    return tracklets


def _recovery_partial_results(tracklets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return conservative partial results for audit review rows."""
    return [
        {
            "object_id": str(tracklet["object_id"]),
            "neo_probability": None,
            "hazard_flag": "unknown",
            "alert_pathway": "known_object",
            "moid_au": None,
            "discovery_priority": 0.0,
        }
        for tracklet in tracklets
    ]


def _audit_manifest_rows(
    original_rows: list[dict[str, Any]],
    *,
    tolerance_days: float,
) -> list[dict[str, Any]]:
    """Return an audit manifest aligned with the ATLAS forced-photometry window."""
    rows: list[dict[str, Any]] = []
    for row in original_rows:
        samples = _manifest_samples(row)
        if not samples:
            continue
        rows.append(
            {
                "designation": str(row.get("designation") or row.get("object_id")),
                "samples": [
                    {
                        "ra_deg": sample["ra_deg"],
                        "dec_deg": sample["dec_deg"],
                        "jd": sample["jd"],
                    }
                    for sample in samples
                ],
                "tolerance_arcsec": row.get("tolerance_arcsec", 5.0),
                "tolerance_days": max(
                    float(row.get("tolerance_days") or 0.0),
                    tolerance_days,
                ),
                "min_samples": row.get("min_samples", 1),
                "source": "atlas_forced_photometry_fallback",
            }
        )
    return rows


def _fetch_recovery_sample(
    sample: dict[str, Any],
    *,
    atlas_token: str | None,
    force_refresh: bool,
    window_days: float,
    max_mag: float,
    max_polls: int,
    poll_interval_seconds: float,
    print_fn: Callable[[str], None],
    task_progress_callback: Callable[[dict[str, Any], dict[str, Any]], None] | None,
    fetcher: Callable[..., list[Any]],
) -> dict[str, Any]:
    """Fetch one manifest sample from ATLAS and normalize the result."""
    sample = dict(sample)
    sample["window_days"] = window_days
    last_task: dict[str, Any] = {}

    def _progress(task: dict[str, Any]) -> None:
        nonlocal last_task
        last_task = task
        queuepos = task.get("queuepos")
        started = bool(task.get("starttimestamp"))
        finished = bool(task.get("finishtimestamp") or task.get("finished"))
        result_ready = bool(task.get("result_url"))
        if task_progress_callback is not None:
            task_progress_callback(sample, task)
        print_fn(
            f"[atlas-recovery] poll {sample['designation']} "
            f"sample={sample['sample_index']} queuepos={queuepos} "
            f"started={started} finished={finished} result={result_ready}"
        )

    observations = fetcher(
        ra_deg=float(sample["ra_deg"]),
        dec_deg=float(sample["dec_deg"]),
        start_jd=float(sample["jd"]) - window_days,
        end_jd=float(sample["jd"]) + window_days,
        atlas_token=atlas_token,
        force_refresh=force_refresh,
        max_polls=max_polls,
        poll_interval_seconds=poll_interval_seconds,
        progress_callback=_progress,
        task_url=sample.get("task_url"),
    )
    # Emit a diagnostic message when ATLAS returns zero raw observations so the
    # operator can distinguish genuine non-detection from a network or window problem.
    if len(observations) == 0:
        print_fn(
            f"[atlas-recovery] {sample['designation']} sample={sample['sample_index']}: "
            f"ATLAS returned 0 raw observations "
            f"(object may be too faint or outside ATLAS footprint at this JD)"
        )
    usable = [
        _atlas_obs_to_audit_dict(obs, sample)
        for obs in observations
        if _is_usable_atlas_observation(obs, sample=sample, max_mag=max_mag)
    ]
    task_url_value = last_task.get("url") or sample.get("task_url")
    task_unfinished = bool(task_url_value) and not bool(
        last_task.get("result_url")
        or last_task.get("finishtimestamp")
        or last_task.get("finished")
    )
    status = "recovered" if usable else "not_recovered"
    if not usable and task_unfinished:
        status = "poll_exhausted"
    return {
        "designation": sample["designation"],
        "sample_index": sample["sample_index"],
        "requested_ra_deg": sample["ra_deg"],
        "requested_dec_deg": sample["dec_deg"],
        "requested_jd": sample["jd"],
        "window_days": window_days,
        "status": status,
        "task_url": task_url_value,
        "queuepos": last_task.get("queuepos"),
        "poll_count": last_task.get("poll_count"),
        "n_raw_observations": len(observations),
        "n_usable_observations": len(usable),
        "observations": usable,
    }


def run_atlas_recovery(
    *,
    expected_known: Path,
    run_root: Path,
    atlas_token: str | None,
    force_refresh: bool,
    resume: bool,
    workers: int,
    window_days: float = _DEFAULT_WINDOW_DAYS,
    min_recovered_samples: int = _DEFAULT_MIN_RECOVERED_SAMPLES,
    min_nights: int = _DEFAULT_MIN_NIGHTS,
    max_mag: float = _DEFAULT_MAX_MAG,
    max_polls: int = _DEFAULT_MAX_POLLS,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    max_objects: int | None = None,
    fetcher: Callable[..., list[Any]],
    print_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Run ATLAS forced-photometry fallback recovery and write audit artifacts."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if window_days <= 0.0:
        raise ValueError("window_days must be positive")
    if window_days < _DEFAULT_WINDOW_DAYS:
        print_fn(
            "[atlas-recovery] WARNING: --window-days is narrower than the "
            f"{_DEFAULT_WINDOW_DAYS:.1f} day default. ATLAS has an approximately "
            "2-day cadence, so narrow windows can fail the T1-C recovery KPI "
            "even when the target is recoverable."
        )
    if min_recovered_samples < 1 or min_nights < 1:
        raise ValueError("minimum recovery thresholds must be positive")
    if max_polls < 1 or poll_interval_seconds < 0.0:
        raise ValueError("polling controls must be non-negative with at least one poll")

    manifest_rows = _load_expected_known_manifest(expected_known)
    if max_objects is not None:
        manifest_rows = manifest_rows[:max_objects]
    samples = [
        sample
        for row in manifest_rows
        for sample in _manifest_samples(row)
    ]
    if not samples:
        raise ValueError("expected-known manifest contains no usable sky/time samples")

    params = {
        "expected_known": str(expected_known),
        "n_manifest_rows": len(manifest_rows),
        "n_samples": len(samples),
        "window_days": window_days,
        "min_recovered_samples": min_recovered_samples,
        "min_nights": min_nights,
        "max_mag": max_mag,
        "max_polls": max_polls,
        "poll_interval_seconds": poll_interval_seconds,
        "max_objects": max_objects,
    }
    run_id = f"atlas_recovery_{_param_key(params)}"
    run_dir = run_root / run_id
    checkpoint_path = run_dir / "checkpoint.json"
    state = (
        _load_recovery_checkpoint(checkpoint_path, params)
        if resume
        else {"params": params, "samples": {}}
    )
    todo = []
    for sample in samples:
        key = _recovery_sample_key(sample)
        existing = state.get("samples", {}).get(key)
        existing_status = existing.get("status") if isinstance(existing, dict) else None
        if existing_status == "recovered":
            print_fn(
                f"[resume] {sample['designation']} sample={sample['sample_index']} "
                "already recovered"
            )
            continue
        if (
            isinstance(existing, dict)
            and existing_status in {"not_recovered", "failed"}
            and not force_refresh
        ):
            print_fn(
                f"[resume] {sample['designation']} sample={sample['sample_index']} "
                f"already {existing_status}"
            )
            continue
        sample_for_run = dict(sample)
        if isinstance(existing, dict) and existing.get("task_url"):
            sample_for_run["task_url"] = existing["task_url"]
            print_fn(
                f"[resume] {sample['designation']} sample={sample['sample_index']} "
                "polling existing ATLAS task"
            )
        elif isinstance(existing, dict) and existing_status in {"not_recovered", "failed"}:
            print_fn(
                f"[resume] {sample['designation']} sample={sample['sample_index']} "
                f"refreshing prior {existing_status}"
            )
        todo.append(sample_for_run)
    start_time = time.monotonic()
    print_fn(
        f"[atlas-recovery] run_id={run_id} objects={len(manifest_rows)} "
        f"samples={len(samples)} todo={len(todo)} workers={workers}"
    )

    lock = threading.Lock()

    def _checkpoint_payload(last_stage: str, tracklets: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the audit-compatible checkpoint payload from current state."""
        return {
            "params": params,
            "last_stage": last_stage,
            "tracklets": tracklets,
            "partial_results": _recovery_partial_results(tracklets),
            "samples": state["samples"],
        }

    def _record_pending(sample: dict[str, Any], task: dict[str, Any]) -> None:
        """Persist in-flight ATLAS task status so interrupted runs can resume polling."""
        key = _recovery_sample_key(sample)
        with lock:
            previous = state["samples"].get(key, {})
            poll_count = int(previous.get("poll_count", 0)) + 1 if isinstance(previous, dict) else 1
            task["poll_count"] = poll_count
            task_url_value = task.get("url") or sample.get("task_url")
            state["samples"][key] = {
                "designation": sample["designation"],
                "sample_index": sample["sample_index"],
                "requested_ra_deg": sample["ra_deg"],
                "requested_dec_deg": sample["dec_deg"],
                "requested_jd": sample["jd"],
                "window_days": window_days,
                "status": "polling",
                "task_url": task_url_value,
                "queuepos": task.get("queuepos"),
                "started": bool(task.get("starttimestamp")),
                "finished": bool(task.get("finishtimestamp") or task.get("finished")),
                "result_ready": bool(task.get("result_url")),
                "poll_count": poll_count,
                "n_raw_observations": 0,
                "n_usable_observations": 0,
                "observations": [],
            }
            tracklets = _tracklets_from_recovery_state(
                state,
                min_recovered_samples=min_recovered_samples,
                min_nights=min_nights,
            )
            _write_json(
                checkpoint_path,
                _checkpoint_payload("atlas_forced_recovery_polling", tracklets),
            )

    def _record(sample: dict[str, Any], result: dict[str, Any], done_count: int) -> None:
        key = _recovery_sample_key(sample)
        with lock:
            state["samples"][key] = result
            tracklets = _tracklets_from_recovery_state(
                state,
                min_recovered_samples=min_recovered_samples,
                min_nights=min_nights,
            )
            _write_json(
                checkpoint_path,
                _checkpoint_payload("atlas_forced_recovery", tracklets),
            )
            elapsed = time.monotonic() - start_time
            print_fn(
                f"[atlas-recovery] {done_count}/{len(todo)} "
                f"{result['designation']} sample={result['sample_index']} "
                f"status={result['status']} usable={result['n_usable_observations']} "
                f"{_format_eta(elapsed, done_count, len(todo))}"
            )

    def _do_one(sample: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        try:
            return sample, _fetch_recovery_sample(
                sample,
                atlas_token=atlas_token,
                force_refresh=force_refresh,
                window_days=window_days,
                max_mag=max_mag,
                max_polls=max_polls,
                poll_interval_seconds=poll_interval_seconds,
                print_fn=print_fn,
                task_progress_callback=_record_pending,
                fetcher=fetcher,
            ), None
        except Exception as exc:
            return sample, None, str(exc)

    done = 0
    failures: list[dict[str, Any]] = []
    if workers == 1:
        for sample in todo:
            done += 1
            sample, result, error = _do_one(sample)
            if error:
                failures.append({"sample": sample, "error": error})
                result = {
                    "designation": sample["designation"],
                    "sample_index": sample["sample_index"],
                    "requested_ra_deg": sample["ra_deg"],
                    "requested_dec_deg": sample["dec_deg"],
                    "requested_jd": sample["jd"],
                    "window_days": window_days,
                    "status": "failed",
                    "error": error,
                    "n_raw_observations": 0,
                    "n_usable_observations": 0,
                    "observations": [],
                }
            _record(sample, result, done)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_do_one, sample): sample for sample in todo}
            for future in as_completed(futures):
                done += 1
                sample, result, error = future.result()
                if error:
                    failures.append({"sample": sample, "error": error})
                    result = {
                        "designation": sample["designation"],
                        "sample_index": sample["sample_index"],
                        "requested_ra_deg": sample["ra_deg"],
                        "requested_dec_deg": sample["dec_deg"],
                        "requested_jd": sample["jd"],
                        "window_days": window_days,
                        "status": "failed",
                        "error": error,
                        "n_raw_observations": 0,
                        "n_usable_observations": 0,
                        "observations": [],
                    }
                _record(sample, result, done)

    tracklets = _tracklets_from_recovery_state(
        state,
        min_recovered_samples=min_recovered_samples,
        min_nights=min_nights,
    )
    audit_manifest = run_dir / "expected_known_atlas_forced.json"
    _write_json(audit_manifest, _audit_manifest_rows(manifest_rows, tolerance_days=window_days))
    summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "expected_known": str(expected_known),
        "atlas_audit_expected_known": str(audit_manifest),
        "n_manifest_rows": len(manifest_rows),
        "n_samples": len(samples),
        "n_recovered_samples": sum(
            1 for result in state["samples"].values()
            if isinstance(result, dict) and result.get("status") == "recovered"
        ),
        "n_tracklets": len(tracklets),
        "n_failures": len(failures),
        "n_pending_samples": sum(
            1 for result in state["samples"].values()
            if isinstance(result, dict)
            and result.get("status") not in _TERMINAL_SAMPLE_STATUSES
        ),
        "fallback_type": "atlas_forced_photometry_targeted_known_object_recovery",
        "limitations": [
            "Targeted forced photometry is supporting recovery evidence, not blind discovery.",
            "This tool performs no external submission and makes no impact claim.",
            "Promotion remains controlled by audit_real_run.py and operator review.",
        ],
        "safety": {
            "no_external_submission": True,
            "no_impact_probability_claim": True,
            "mpc_nasa_alert_pathway_triggered": False,
        },
    }
    _write_json(run_dir / "run_summary.json", summary)
    print_fn(
        f"[atlas-recovery] wrote run_dir={run_dir} tracklets={len(tracklets)} "
        f"recovered_samples={summary['n_recovered_samples']}/{len(samples)}"
    )
    return summary


def _output_path(out_dir: Path, label: str) -> Path:
    """Derive the per-position output file path from the label."""
    safe_label = str(label).replace("/", "_").replace(" ", "_")
    return out_dir / f"{safe_label}.json"


def run_batch(
    positions_csv: Path,
    out_dir: Path,
    atlas_token: str | None,
    force_refresh: bool,
    resume: bool,
    workers: int,
    fetcher: Callable[..., list[Any]],
    print_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch all positions in the CSV and write per-position JSON output.

    Returns a summary dict with counts: total, skipped, fetched, failed.
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")

    positions = _load_positions_csv(positions_csv)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resume: skip positions where the output file already exists.
    todo = []
    skipped = 0
    for pos in positions:
        out_path = _output_path(out_dir, pos["label"])
        if resume and out_path.exists():
            skipped += 1
        else:
            todo.append(pos)

    fetched = 0
    failed = 0
    _print_lock = threading.Lock()

    def _do_one(pos: dict[str, Any]) -> tuple[dict[str, Any], list[Any] | None, str | None]:
        """Fetch one position; return (pos, observations | None, error_msg | None)."""
        try:
            _, obs = _fetch_position(pos, atlas_token, force_refresh, fetcher)
            return pos, obs, None
        except Exception as exc:
            return pos, None, str(exc)

    if workers == 1:
        results = [_do_one(pos) for pos in todo]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(_do_one, pos): pos for pos in todo}
            for future in as_completed(future_map):
                results.append(future.result())

    for pos, obs, err in results:
        out_path = _output_path(out_dir, pos["label"])
        if err is not None:
            failed += 1
            with _print_lock:
                print_fn(
                    f"FAILED ra={pos['ra']} dec={pos['dec']}: {err}",
                    file=sys.stderr,
                )
            continue
        payload = {
            "ra_deg": pos["ra"],
            "dec_deg": pos["dec"],
            "start_jd": pos["start_jd"],
            "end_jd": pos["end_jd"],
            "label": pos["label"],
            "n_obs": len(obs or []),
            "observations": _observations_to_json(obs or []),
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        fetched += 1
        with _print_lock:
            print_fn(f"OK  {pos['label']:30s} n_obs={len(obs or [])}")

    summary = {
        "total": len(positions),
        "skipped": skipped,
        "fetched": fetched,
        "failed": failed,
    }
    return summary


def main() -> None:
    """Parse CLI for single-position or batch mode."""
    parser = argparse.ArgumentParser(
        description="Fetch ATLAS forced photometry for one or many sky positions."
    )

    # --- Single-position positional args (preserved from original) ---
    parser.add_argument(
        "ra", nargs="?", type=float, help="Right ascension in degrees (single-position mode)"
    )
    parser.add_argument(
        "dec", nargs="?", type=float, help="Declination in degrees (single-position mode)"
    )
    parser.add_argument(
        "start_jd", nargs="?", type=float, help="Start Julian date (single-position mode)"
    )
    parser.add_argument(
        "end_jd", nargs="?", type=float, help="End Julian date (single-position mode)"
    )

    # --- Batch mode args ---
    parser.add_argument(
        "--positions-csv",
        type=Path,
        help="CSV with columns ra,dec,start_jd,end_jd[,label] for batch mode",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Output directory for per-position JSON files (batch mode)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip positions whose output file already exists (batch mode)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel fetch threads for batch mode (default 1)",
    )
    parser.add_argument(
        "--expected-known",
        type=Path,
        help=(
            "Expected-known JSON manifest for ATLAS forced-photometry recovery "
            "(writes an audit-compatible Logs/pipeline_runs packet)"
        ),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=_DEFAULT_RUN_ROOT,
        help="Root directory for ATLAS recovery run packets",
    )
    parser.add_argument(
        "--window-days",
        type=float,
        default=_DEFAULT_WINDOW_DAYS,
        help=(
            "Half-window around each expected sample JD for forced photometry "
            f"(default {_DEFAULT_WINDOW_DAYS:.1f}; keep the default for T1-C "
            "because ATLAS cadence is approximately 2 days)"
        ),
    )
    parser.add_argument(
        "--min-recovered-samples",
        type=int,
        default=_DEFAULT_MIN_RECOVERED_SAMPLES,
        help="Minimum recovered samples required to emit an audit tracklet",
    )
    parser.add_argument(
        "--min-nights",
        type=int,
        default=_DEFAULT_MIN_NIGHTS,
        help="Minimum distinct nights required to emit an audit tracklet",
    )
    parser.add_argument(
        "--max-mag",
        type=float,
        default=_DEFAULT_MAX_MAG,
        help="Faint limit for usable ATLAS recovery observations",
    )
    parser.add_argument(
        "--max-objects",
        type=int,
        default=None,
        help="Limit expected-known object rows for bounded pilot runs",
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=_DEFAULT_MAX_POLLS,
        help="Maximum ATLAS task polls per forced-photometry sample",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=_DEFAULT_POLL_INTERVAL_SECONDS,
        help="Delay between unfinished ATLAS task polls",
    )

    # --- Shared args ---
    parser.add_argument(
        "--token",
        default=None,
        help="ATLAS API token (or set ATLAS_TOKEN environment variable)",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Bypass on-disk cache")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (single mode only)")
    args = parser.parse_args()

    from fetch import fetch_atlas_forced  # type: ignore[import]

    # Expected-known recovery mode.
    if args.expected_known:
        summary = run_atlas_recovery(
            expected_known=args.expected_known,
            run_root=args.run_root,
            atlas_token=args.token,
            force_refresh=args.force_refresh,
            resume=args.resume,
            workers=args.workers,
            window_days=args.window_days,
            min_recovered_samples=args.min_recovered_samples,
            min_nights=args.min_nights,
            max_mag=args.max_mag,
            max_polls=args.max_polls,
            poll_interval_seconds=args.poll_interval_seconds,
            max_objects=args.max_objects,
            fetcher=fetch_atlas_forced,
        )
        print(json.dumps(summary, indent=2))
        return

    # Batch mode.
    if args.positions_csv:
        if not args.out_dir:
            parser.error("--out-dir is required with --positions-csv")
        summary = run_batch(
            args.positions_csv,
            args.out_dir,
            atlas_token=args.token,
            force_refresh=args.force_refresh,
            resume=args.resume,
            workers=args.workers,
            fetcher=fetch_atlas_forced,
        )
        print(json.dumps(summary, indent=2))
        return

    # Single-position mode (original behaviour).
    if args.ra is None or args.dec is None or args.start_jd is None or args.end_jd is None:
        parser.error("provide ra dec start_jd end_jd or use --positions-csv for batch mode")

    observations = fetch_atlas_forced(
        ra_deg=args.ra,
        dec_deg=args.dec,
        start_jd=args.start_jd,
        end_jd=args.end_jd,
        atlas_token=args.token,
        force_refresh=args.force_refresh,
        max_polls=args.max_polls,
        poll_interval_seconds=args.poll_interval_seconds,
    )

    if args.json:
        print(json.dumps(_observations_to_json(observations), indent=2))
        return

    if not observations:
        print("No ATLAS observations returned (check token, coordinates, or date range).")
        return

    hdr = f"{'obs_id':<24} {'JD':>13} {'RA':>10} {'Dec':>10} {'mag':>7} {'err':>6} {'band':>5}"
    print(hdr)
    print("-" * len(hdr))
    for o in observations:
        print(
            f"{o.obs_id:<24} {o.jd:>13.5f} {o.ra_deg:>10.5f} {o.dec_deg:>10.5f}"
            f" {o.mag:>7.3f} {o.mag_err:>6.3f} {o.filter_band:>5}"
        )


if __name__ == "__main__":
    main()
