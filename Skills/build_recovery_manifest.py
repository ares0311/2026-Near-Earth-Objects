#!/usr/bin/env python3
"""Build a T1-C expected-known manifest for real-run recovery audits.

The manifest produced here is consumed by ``Skills/audit_real_run.py``.  It is
intentionally conservative: it records predicted sky/time samples for known MPC
objects in a selected recovery field, but it never submits observations, opens
external alert pathways, or asserts impact probability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fetch import fetch_horizons_ephemeris, fetch_mpc_known

_DEFAULT_RUN_ROOT = Path("Logs/pipeline_runs")
_DEFAULT_TOLERANCE_ARCSEC = 5.0
_DEFAULT_TOLERANCE_DAYS = 0.02
_DEFAULT_MAX_MAG = 21.5


def _param_key(params: dict[str, Any]) -> str:
    """Return a stable hash for the search parameters that define this work."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _checkpoint_path(params: dict[str, Any], run_root: Path = _DEFAULT_RUN_ROOT) -> Path:
    """Return the stable checkpoint path for this manifest-build request."""
    return run_root / f"recovery_manifest_{_param_key(params)}" / "checkpoint.json"


def _load_checkpoint(path: Path, params: dict[str, Any]) -> dict[str, Any]:
    """Load a matching checkpoint; otherwise return a fresh state object."""
    if not path.exists():
        return {"params": params, "processed": {}, "rows": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"params": params, "processed": {}, "rows": []}
    if data.get("params") != params:
        return {"params": params, "processed": {}, "rows": []}
    if not isinstance(data.get("processed"), dict) or not isinstance(data.get("rows"), list):
        return {"params": params, "processed": {}, "rows": []}
    return data


def _write_checkpoint(path: Path, state: dict[str, Any]) -> None:
    """Persist checkpoint state after each expensive provider query."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _with_retry(label: str, fn: Callable[[], Any], attempts: int = 5) -> Any:
    """Run a provider call with the project-standard exponential backoff."""
    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except (ConnectionError, TimeoutError, OSError) as exc:
            if attempt == attempts:
                raise
            print(
                f"[retry] {label}: {exc} "
                f"(attempt {attempt}/{attempts}; sleeping {delay:.0f}s)",
                flush=True,
            )
            time.sleep(delay)
            delay *= 2.0


def _sample_jds(start_jd: float, end_jd: float, n_samples: int) -> list[float]:
    """Return evenly spaced JD samples across the planned recovery-run window."""
    if end_jd < start_jd:
        raise ValueError("end_jd must be >= start_jd")
    if n_samples <= 1:
        return [round((start_jd + end_jd) / 2.0, 6)]
    step = (end_jd - start_jd) / (n_samples - 1)
    return [round(start_jd + i * step, 6) for i in range(n_samples)]


def _angular_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Return great-circle separation in degrees for two sky positions."""
    ra1_rad = math.radians(ra1)
    ra2_rad = math.radians(ra2)
    dec1_rad = math.radians(dec1)
    dec2_rad = math.radians(dec2)
    sin_d_dec = math.sin((dec2_rad - dec1_rad) / 2.0)
    sin_d_ra = math.sin((ra2_rad - ra1_rad) / 2.0)
    hav = sin_d_dec**2 + math.cos(dec1_rad) * math.cos(dec2_rad) * sin_d_ra**2
    return math.degrees(2.0 * math.asin(min(1.0, math.sqrt(max(0.0, hav)))))


def _designation_from_known_obs(obs: Any) -> str | None:
    """Extract the MPC designation stored by ``fetch_mpc_known`` in ``obs_id``."""
    obs_id = str(getattr(obs, "obs_id", ""))
    if obs_id.startswith("mpc_") and len(obs_id) > 4:
        return obs_id[4:]
    return None


def _format_eta(elapsed: float, done: int, total: int) -> str:
    """Format elapsed and estimated remaining time for live progress output."""
    if done <= 0:
        eta = 0.0
    else:
        eta = max(0.0, (elapsed / done) * (total - done))
    return (
        f"elapsed {int(elapsed // 60)}m{int(elapsed % 60):02d}s  "
        f"ETA {int(eta // 60)}m{int(eta % 60):02d}s"
    )


def _sample_from_ephemeris(row: dict[str, Any]) -> dict[str, float] | None:
    """Normalize one Horizons ephemeris row into audit-manifest sample fields."""
    try:
        sample = {
            "jd": float(row["jd"]),
            "ra_deg": float(row["ra_deg"]),
            "dec_deg": float(row["dec_deg"]),
        }
        if row.get("mag") is not None:
            sample["mag"] = float(row["mag"])
        return sample
    except (KeyError, TypeError, ValueError):
        return None


def _filter_samples(
    samples: list[dict[str, float]],
    *,
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    max_mag: float,
) -> list[dict[str, float]]:
    """Keep samples inside the field and bright enough for a recovery run."""
    kept: list[dict[str, float]] = []
    for sample in samples:
        sep = _angular_sep_deg(ra_deg, dec_deg, sample["ra_deg"], sample["dec_deg"])
        mag = sample.get("mag")
        if sep <= radius_deg and (mag is None or mag <= max_mag):
            kept.append(sample)
    return kept


def build_recovery_manifest(
    *,
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    output: Path,
    max_objects: int = 50,
    n_samples: int = 3,
    min_samples: int = 1,
    tolerance_arcsec: float = _DEFAULT_TOLERANCE_ARCSEC,
    tolerance_days: float = _DEFAULT_TOLERANCE_DAYS,
    max_mag: float = _DEFAULT_MAX_MAG,
    force_refresh: bool = False,
    run_root: Path = _DEFAULT_RUN_ROOT,
) -> dict[str, Any]:
    """Build and write the expected-known manifest for one recovery field."""
    params = {
        "ra_deg": round(ra_deg, 8),
        "dec_deg": round(dec_deg, 8),
        "radius_deg": round(radius_deg, 8),
        "start_jd": round(start_jd, 8),
        "end_jd": round(end_jd, 8),
        "max_objects": max_objects,
        "n_samples": n_samples,
        "min_samples": min_samples,
        "tolerance_arcsec": tolerance_arcsec,
        "tolerance_days": tolerance_days,
        "max_mag": max_mag,
    }
    checkpoint = _checkpoint_path(params, run_root)
    state = (
        {"params": params, "processed": {}, "rows": []}
        if force_refresh
        else _load_checkpoint(checkpoint, params)
    )
    sample_jds = _sample_jds(start_jd, end_jd, n_samples)

    print(
        f"[manifest] Querying MPC known objects at RA={ra_deg:.4f}, "
        f"Dec={dec_deg:.4f}, r={radius_deg:.2f} deg",
        flush=True,
    )
    known_obs = _with_retry(
        "mpc-region",
        lambda: fetch_mpc_known(ra_deg, dec_deg, radius_deg),
    )
    designations = []
    for obs in known_obs:
        designation = _designation_from_known_obs(obs)
        if designation and designation not in designations:
            designations.append(designation)
        if len(designations) >= max_objects:
            break

    total = len(designations)
    print(
        f"[manifest] {total} candidate known object(s); sampling {len(sample_jds)} JD(s)",
        flush=True,
    )

    start_time = time.monotonic()
    rows_by_designation = {
        str(row["designation"]): row
        for row in state.get("rows", [])
        if isinstance(row, dict) and row.get("designation")
    }
    processed: dict[str, Any] = state.get("processed", {})

    for index, designation in enumerate(designations, start=1):
        if processed.get(designation) == "done":
            print(f"[resume] {designation} already sampled", flush=True)
            continue

        elapsed = time.monotonic() - start_time
        print(
            f"[manifest] {index}/{total} {designation}  "
            f"accepted={len(rows_by_designation)}  {_format_eta(elapsed, index - 1, total)}",
            flush=True,
        )
        ephemerides = _with_retry(
            f"horizons-{designation}",
            lambda d=designation: fetch_horizons_ephemeris(
                d,
                sample_jds,
                # The shared Horizons helper caches by designation, while this
                # manifest is defined by a specific JD window. Reuse this
                # script's checkpoint for resume, but fetch fresh ephemerides
                # for any newly sampled object so the manifest cannot inherit
                # stale sky/time samples from another recovery window.
                force_refresh=True,
            ),
        )
        samples = [
            sample for row in ephemerides
            if (sample := _sample_from_ephemeris(row)) is not None
        ]
        kept = _filter_samples(
            samples,
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            max_mag=max_mag,
        )
        if len(kept) >= min_samples:
            rows_by_designation[designation] = {
                "designation": designation,
                "samples": kept,
                "tolerance_arcsec": tolerance_arcsec,
                "tolerance_days": tolerance_days,
                "min_samples": min_samples,
                "source": "mpc_region_plus_jpl_horizons",
            }
        processed[designation] = "done"
        state = {
            "params": params,
            "processed": processed,
            "rows": list(rows_by_designation.values()),
        }
        _write_checkpoint(checkpoint, state)

    rows = list(rows_by_designation.values())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    summary = {
        "output": str(output),
        "checkpoint": str(checkpoint),
        "n_region_candidates": total,
        "n_manifest_rows": len(rows),
        "sample_jds": sample_jds,
        "safety": {
            "no_external_submission": True,
            "no_mpc_submission": True,
            "no_nasa_pdco_notification": True,
            "no_impact_probability_asserted": True,
        },
    }
    print(
        f"[manifest] wrote {len(rows)} expected-known row(s) to {output}",
        flush=True,
    )
    print("[manifest] no external submission performed", flush=True)
    return summary


def main() -> None:
    """Parse CLI arguments and build the recovery manifest."""
    parser = argparse.ArgumentParser(
        description="Build a T1-C expected-known recovery manifest",
    )
    parser.add_argument("--ra", type=float, required=True, help="Field center RA in degrees")
    parser.add_argument("--dec", type=float, required=True, help="Field center Dec in degrees")
    parser.add_argument("--radius", type=float, default=3.5, help="Field radius in degrees")
    parser.add_argument("--start-jd", type=float, required=True, help="Recovery run start JD")
    parser.add_argument("--end-jd", type=float, required=True, help="Recovery run end JD")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON manifest path")
    parser.add_argument("--max-objects", type=int, default=50, help="Maximum regional objects")
    parser.add_argument("--samples", type=int, default=3, help="Ephemeris samples per object")
    parser.add_argument("--min-samples", type=int, default=1, help="Required audit sample matches")
    parser.add_argument("--tolerance-arcsec", type=float, default=_DEFAULT_TOLERANCE_ARCSEC)
    parser.add_argument("--tolerance-days", type=float, default=_DEFAULT_TOLERANCE_DAYS)
    parser.add_argument("--max-mag", type=float, default=_DEFAULT_MAX_MAG)
    parser.add_argument("--force-refresh", action="store_true", help="Ignore cached provider data")
    args = parser.parse_args()

    summary = build_recovery_manifest(
        ra_deg=args.ra,
        dec_deg=args.dec,
        radius_deg=args.radius,
        start_jd=args.start_jd,
        end_jd=args.end_jd,
        output=args.output,
        max_objects=args.max_objects,
        n_samples=args.samples,
        min_samples=args.min_samples,
        tolerance_arcsec=args.tolerance_arcsec,
        tolerance_days=args.tolerance_days,
        max_mag=args.max_mag,
        force_refresh=args.force_refresh,
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
