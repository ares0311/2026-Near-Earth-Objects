#!/usr/bin/env python3
"""Build a T1-C expected-known manifest for real-run recovery audits.

The manifest produced here is consumed by ``Skills/audit_real_run.py``.  It is
intentionally conservative: it records predicted sky/time samples for known MPC
objects in a selected recovery field, but it never submits observations, opens
external alert pathways, or asserts impact probability.
"""

from __future__ import annotations

import argparse
import csv
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
_DEFAULT_LABEL_POOL = Path("data/training_labels.csv")
_OBLIQUITY_DEG = 23.439291


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


def _row_float(row: dict[str, Any], key: str) -> float | None:
    """Return a finite float from one MPC orbital row when available."""
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _mpc_row_designation(row: dict[str, Any]) -> str | None:
    """Return the stable MPC number or provisional designation for a row."""
    number = row.get("number")
    if number not in (None, ""):
        try:
            return str(int(number))
        except (TypeError, ValueError):
            return str(number).strip() or None
    designation = str(row.get("designation") or "").strip()
    return designation or None


def _solve_kepler(mean_anomaly_rad: float, eccentricity: float) -> float:
    """Solve Kepler's equation with a fixed small Newton iteration budget."""
    anomaly = mean_anomaly_rad
    for _ in range(12):
        delta = (
            anomaly
            - eccentricity * math.sin(anomaly)
            - mean_anomaly_rad
        ) / max(1e-12, 1.0 - eccentricity * math.cos(anomaly))
        anomaly -= delta
        if abs(delta) < 1e-10:
            break
    return anomaly


def _earth_heliocentric_ecliptic_au(jd: float) -> tuple[float, float, float]:
    """Approximate Earth's heliocentric ecliptic vector in AU for preselection."""
    days = jd - 2451545.0
    mean_long = math.radians((280.460 + 0.9856474 * days) % 360.0)
    anomaly = math.radians((357.528 + 0.9856003 * days) % 360.0)
    sun_lon = (
        mean_long
        + math.radians(1.915) * math.sin(anomaly)
        + math.radians(0.020) * math.sin(2.0 * anomaly)
    )
    earth_lon = sun_lon + math.pi
    radius = (
        1.00014
        - 0.01671 * math.cos(anomaly)
        - 0.00014 * math.cos(2.0 * anomaly)
    )
    return (
        radius * math.cos(earth_lon),
        radius * math.sin(earth_lon),
        0.0,
    )


def _rough_ra_dec_from_mpc_orbit(
    row: dict[str, Any],
    target_jd: float,
) -> tuple[float, float] | None:
    """Approximate geocentric RA/Dec from MPC elements for field preselection."""
    a = _row_float(row, "semimajor_axis")
    e = _row_float(row, "eccentricity")
    inc = _row_float(row, "inclination")
    node = _row_float(row, "ascending_node")
    argp = _row_float(row, "argument_of_perihelion")
    mean_anomaly = _row_float(row, "mean_anomaly")
    daily_motion = _row_float(row, "mean_daily_motion")
    epoch_jd = _row_float(row, "epoch_jd")
    if None in (a, e, inc, node, argp, mean_anomaly, daily_motion, epoch_jd):
        return None
    assert a is not None and e is not None and inc is not None
    assert node is not None and argp is not None and mean_anomaly is not None
    assert daily_motion is not None and epoch_jd is not None
    if a <= 0.0 or not 0.0 <= e < 1.0:
        return None

    mean_rad = math.radians((mean_anomaly + daily_motion * (target_jd - epoch_jd)) % 360.0)
    ecc_anomaly = _solve_kepler(mean_rad, e)
    x_orb = a * (math.cos(ecc_anomaly) - e)
    y_orb = a * math.sqrt(max(0.0, 1.0 - e * e)) * math.sin(ecc_anomaly)

    cos_o, sin_o = math.cos(math.radians(node)), math.sin(math.radians(node))
    cos_i, sin_i = math.cos(math.radians(inc)), math.sin(math.radians(inc))
    cos_w, sin_w = math.cos(math.radians(argp)), math.sin(math.radians(argp))
    x_ecl = (
        (cos_o * cos_w - sin_o * sin_w * cos_i) * x_orb
        + (-cos_o * sin_w - sin_o * cos_w * cos_i) * y_orb
    )
    y_ecl = (
        (sin_o * cos_w + cos_o * sin_w * cos_i) * x_orb
        + (-sin_o * sin_w + cos_o * cos_w * cos_i) * y_orb
    )
    z_ecl = (sin_w * sin_i) * x_orb + (cos_w * sin_i) * y_orb

    earth_x, earth_y, earth_z = _earth_heliocentric_ecliptic_au(target_jd)
    geo_x = x_ecl - earth_x
    geo_y = y_ecl - earth_y
    geo_z = z_ecl - earth_z
    obliquity = math.radians(_OBLIQUITY_DEG)
    equ_x = geo_x
    equ_y = geo_y * math.cos(obliquity) - geo_z * math.sin(obliquity)
    equ_z = geo_y * math.sin(obliquity) + geo_z * math.cos(obliquity)
    distance = math.sqrt(equ_x * equ_x + equ_y * equ_y + equ_z * equ_z)
    if distance <= 0.0:
        return None
    ra = math.degrees(math.atan2(equ_y, equ_x)) % 360.0
    dec = math.degrees(math.asin(max(-1.0, min(1.0, equ_z / distance))))
    return ra, dec


def _designation_from_known_obs(obs: Any) -> str | None:
    """Extract the MPC designation stored by ``fetch_mpc_known`` in ``obs_id``."""
    obs_id = str(getattr(obs, "obs_id", ""))
    if obs_id.startswith("mpc_") and len(obs_id) > 4:
        return obs_id[4:]
    return None


def _designation_from_label_row(row: dict[str, str]) -> str | None:
    """Return a Horizons-compatible designation from one committed label row."""
    designation = str(row.get("designation", "")).strip()
    if not designation:
        return None
    if designation.isdigit():
        return str(int(designation))
    return designation


def _designations_from_label_pool(path: Path, limit: int) -> list[str]:
    """Load a bounded fallback designation pool from committed MPC labels."""
    if limit <= 0 or not path.exists():
        return []
    designations: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            designation = _designation_from_label_row(row)
            if designation and designation not in designations:
                designations.append(designation)
            if len(designations) >= limit:
                break
    return designations


def _designations_from_mpc_region(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    max_objects: int,
) -> list[str]:
    """Return designations from MPC region search when the provider supports it."""
    known_obs = _with_retry(
        "mpc-region",
        lambda: fetch_mpc_known(ra_deg, dec_deg, radius_deg),
    )
    designations: list[str] = []
    for obs in known_obs:
        designation = _designation_from_known_obs(obs)
        if designation and designation not in designations:
            designations.append(designation)
        if len(designations) >= max_objects:
            break
    return designations


def _candidate_designations(
    *,
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    max_objects: int,
    label_pool: Path,
    fallback_scan_limit: int,
) -> tuple[list[str], str]:
    """Get candidate designations, falling back when live MPC lacks region search."""
    try:
        designations = _designations_from_mpc_region(
            ra_deg,
            dec_deg,
            radius_deg,
            max_objects,
        )
    except AttributeError as exc:
        print(
            f"[manifest] MPC region search unavailable ({exc}); "
            f"falling back to {label_pool}",
            flush=True,
        )
        return (
            _designations_from_label_pool(label_pool, fallback_scan_limit),
            "committed_training_labels_plus_jpl_horizons",
        )
    if designations:
        return designations, "mpc_region_plus_jpl_horizons"
    fallback = _designations_from_label_pool(label_pool, fallback_scan_limit)
    return fallback, "committed_training_labels_plus_jpl_horizons"


def _fetch_mpc_orbit_rows(limit: int, neo_only: bool = True) -> list[dict[str, Any]]:
    """Fetch a bounded MPC orbit list for local field preselection."""
    if limit <= 0:
        return []
    from astroquery.mpc import MPC  # type: ignore[import]

    # T1-C recovery is a known-object recovery gate, not a new-NEO discovery gate.
    # Keep NEO-only as the conservative default, but allow all asteroid rows when
    # the operator needs a denser known-moving-object recovery field.
    query_kwargs: dict[str, Any] = {"limit": limit}
    if neo_only:
        query_kwargs["neo"] = 1
    rows = MPC.query_objects("asteroid", **query_kwargs)
    return [dict(row) for row in rows]


def _auto_center_designations_from_mpc_list(
    *,
    target_jd: float,
    radius_deg: float,
    list_limit: int,
    max_objects: int,
    neo_only: bool = True,
) -> tuple[float, float, list[str]]:
    """Choose a dense recovery field from approximate MPC orbit projections."""
    projected: list[tuple[str, float, float]] = []
    for row in _fetch_mpc_orbit_rows(list_limit, neo_only=neo_only):
        designation = _mpc_row_designation(row)
        position = _rough_ra_dec_from_mpc_orbit(row, target_jd)
        if designation is not None and position is not None:
            projected.append((designation, position[0], position[1]))
    if not projected:
        raise RuntimeError("MPC orbit list did not yield any projectable designations")

    best_center = projected[0]
    best_members: list[tuple[str, float, float]] = []
    for candidate in projected:
        _, cand_ra, cand_dec = candidate
        members = [
            row for row in projected
            if _angular_sep_deg(cand_ra, cand_dec, row[1], row[2]) <= radius_deg
        ]
        if len(members) > len(best_members):
            best_center = candidate
            best_members = members

    center_ra = best_center[1]
    center_dec = best_center[2]
    designations = [row[0] for row in best_members[:max_objects]]
    print(
        f"[manifest] auto-centered on RA={center_ra:.4f}, Dec={center_dec:.4f}; "
        f"{len(best_members)} projected object(s) within {radius_deg:.2f} deg",
        flush=True,
    )
    return center_ra, center_dec, designations


def _designations_from_mpc_list_field(
    *,
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    target_jd: float,
    list_limit: int,
    max_objects: int,
    neo_only: bool = True,
) -> list[str]:
    """Preselect MPC orbit-list designations projected into a fixed field."""
    designations: list[str] = []
    for row in _fetch_mpc_orbit_rows(list_limit, neo_only=neo_only):
        designation = _mpc_row_designation(row)
        position = _rough_ra_dec_from_mpc_orbit(row, target_jd)
        if designation is None or position is None:
            continue
        if _angular_sep_deg(ra_deg, dec_deg, position[0], position[1]) <= radius_deg:
            designations.append(designation)
        if len(designations) >= max_objects:
            break
    print(
        f"[manifest] fixed-field MPC orbit preselection found "
        f"{len(designations)} projected object(s)",
        flush=True,
    )
    return designations


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
    label_pool: Path = _DEFAULT_LABEL_POOL,
    fallback_scan_limit: int = 250,
    auto_center_from_mpc_list: bool = False,
    mpc_list_limit: int = 1000,
    auto_center_neo_only: bool = True,
    preselect_from_mpc_list: bool = False,
) -> dict[str, Any]:
    """Build and write the expected-known manifest for one recovery field."""
    sample_jds = _sample_jds(start_jd, end_jd, n_samples)
    requested_ra_deg = ra_deg
    requested_dec_deg = dec_deg
    preselected_designations: list[str] | None = None
    preselection_source: str | None = None
    if auto_center_from_mpc_list:
        ra_deg, dec_deg, preselected_designations = _auto_center_designations_from_mpc_list(
            target_jd=sample_jds[len(sample_jds) // 2],
            radius_deg=radius_deg,
            list_limit=mpc_list_limit,
            max_objects=max_objects,
            neo_only=auto_center_neo_only,
        )
        preselection_source = (
            "mpc_neo_orbit_projection_plus_jpl_horizons"
            if auto_center_neo_only
            else "mpc_asteroid_orbit_projection_plus_jpl_horizons"
        )
    elif preselect_from_mpc_list:
        preselected_designations = _designations_from_mpc_list_field(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            target_jd=sample_jds[len(sample_jds) // 2],
            list_limit=mpc_list_limit,
            max_objects=max_objects,
            neo_only=auto_center_neo_only,
        )
        preselection_source = (
            "mpc_neo_orbit_projection_fixed_field_plus_jpl_horizons"
            if auto_center_neo_only
            else "mpc_asteroid_orbit_projection_fixed_field_plus_jpl_horizons"
        )

    params = {
        "requested_ra_deg": round(requested_ra_deg, 8),
        "requested_dec_deg": round(requested_dec_deg, 8),
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
        "label_pool": str(label_pool),
        "fallback_scan_limit": fallback_scan_limit,
        "auto_center_from_mpc_list": auto_center_from_mpc_list,
        "mpc_list_limit": mpc_list_limit,
        "auto_center_neo_only": auto_center_neo_only,
        "preselect_from_mpc_list": preselect_from_mpc_list,
    }
    checkpoint = _checkpoint_path(params, run_root)
    state = (
        {"params": params, "processed": {}, "rows": []}
        if force_refresh
        else _load_checkpoint(checkpoint, params)
    )
    print(
        f"[manifest] Querying MPC known objects at RA={ra_deg:.4f}, "
        f"Dec={dec_deg:.4f}, r={radius_deg:.2f} deg",
        flush=True,
    )
    if preselected_designations is None:
        designations, source = _candidate_designations(
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            radius_deg=radius_deg,
            max_objects=max_objects,
            label_pool=label_pool,
            fallback_scan_limit=fallback_scan_limit,
        )
    else:
        designations = preselected_designations
        source = str(preselection_source)

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
                "source": source,
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
        "requested_field": {
            "ra_deg": requested_ra_deg,
            "dec_deg": requested_dec_deg,
            "radius_deg": radius_deg,
        },
        "effective_field": {
            "ra_deg": ra_deg,
            "dec_deg": dec_deg,
            "radius_deg": radius_deg,
        },
        "n_region_candidates": total,
        "n_manifest_rows": len(rows),
        "candidate_source": source,
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
    parser.add_argument(
        "--label-pool",
        type=Path,
        default=_DEFAULT_LABEL_POOL,
        help="Committed MPC label CSV used if live MPC region search is unavailable",
    )
    parser.add_argument(
        "--fallback-scan-limit",
        type=int,
        default=250,
        help="Maximum label-pool designations to test with Horizons fallback",
    )
    parser.add_argument(
        "--auto-center-from-mpc-list",
        action="store_true",
        help="Preselect a dense field from a bounded MPC NEO orbit list",
    )
    parser.add_argument(
        "--mpc-list-limit",
        type=int,
        default=1000,
        help="Maximum MPC NEO orbit rows to use for auto-centering",
    )
    parser.add_argument(
        "--auto-center-all-asteroids",
        action="store_false",
        dest="auto_center_neo_only",
        help=(
            "Use the broader MPC asteroid orbit list, not only NEO rows, "
            "when selecting a dense known-object recovery field"
        ),
    )
    parser.add_argument(
        "--preselect-from-mpc-list",
        action="store_true",
        help=(
            "Keep the requested RA/Dec field and preselect projected MPC orbit "
            "rows inside it before authoritative Horizons validation"
        ),
    )
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
        label_pool=args.label_pool,
        fallback_scan_limit=args.fallback_scan_limit,
        auto_center_from_mpc_list=args.auto_center_from_mpc_list,
        mpc_list_limit=args.mpc_list_limit,
        auto_center_neo_only=args.auto_center_neo_only,
        preselect_from_mpc_list=args.preselect_from_mpc_list,
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
