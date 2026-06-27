"""Fetch stage — retrieve alerts from ZTF, ATLAS, MPC, and JPL Horizons."""

from __future__ import annotations

__all__ = [
    "fetch_ztf",
    "fetch_atlas",
    "fetch_mpc_known",
    "fetch_horizons",
    "fetch",
    "fetch_batch",
    "count_known_objects_in_field",
    "fetch_mpc_observations",
    "fetch_atlas_forced",
    "fetch_ztf_alerts",
    "fetch_panstarrs_catalog",
    "fetch_recent_mpc_neos",
    "fetch_known_phas",
    "fetch_horizons_ephemeris",
    "count_observations_by_mission",
    "filter_by_magnitude",
    "compute_observation_rate",
    "fetch_wise_archive",
    "fetch_decam_archive",
    "fetch_tess_ffis",
    "fetch_discovery",
]

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from schemas import (
    FetchProvenance,
    FetchResult,
    Mission,
    Observation,
)

_CACHE_DIR = Path(".neo_cache")


def _cache_path(key: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{key}.json"


def _load_cache(key: str, force_refresh: bool = False) -> list[dict] | dict | None:
    if force_refresh:
        return None
    p = _cache_path(key)
    if p.exists():
        with p.open() as f:
            return json.load(f)  # type: ignore[no-any-return]
    return None


def _save_cache(key: str, data: list[dict] | dict) -> None:
    with _cache_path(key).open("w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# ZTF
# ---------------------------------------------------------------------------


def fetch_ztf(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    force_refresh: bool = False,
) -> list[Observation]:
    """Query public ZTF source detections via ztfquery, ALeRCE, or legacy TAP."""
    import hashlib

    cache_key = hashlib.md5(
        f"ztf_{ra_deg}_{dec_deg}_{radius_deg}_{start_jd}_{end_jd}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        return [Observation(**row) for row in cached]

    observations: list[Observation] = []
    try:
        import ztfquery.query as zq  # type: ignore[import]

        zquery = zq.ZTFQuery()
        zquery.load_metadata(
            kind="sci",
            radec=[ra_deg, dec_deg],
            size=radius_deg,
            start_jd=start_jd,
            end_jd=end_jd,
        )
        meta = zquery.metatable
        observations = _parse_ztf_metatable(meta)
    except Exception:
        # ImportError: ztfquery not installed — use public broker/TAP fallbacks.
        # Any other exception (auth failure, network error, empty metatable)
        # also falls back so live operator runs can still use public ZTF data.
        observations = []

    if not observations:
        observations = _fetch_ztf_alerce_api(ra_deg, dec_deg, radius_deg, start_jd, end_jd)
        if not observations:
            observations = _fetch_ztf_irsa_api(ra_deg, dec_deg, radius_deg, start_jd, end_jd)

    _save_cache(cache_key, [o.model_dump() for o in observations])
    return observations


def _parse_ztf_metatable(meta: object) -> list[Observation]:  # type: ignore[type-arg]
    """Convert ztfquery metatable rows to Observation objects."""
    import pandas as pd  # type: ignore[import]

    df: pd.DataFrame = meta  # type: ignore[assignment]
    obs: list[Observation] = []
    for _, row in df.iterrows():
        obs.append(
            Observation(
                obs_id=str(row.get("pid", row.get("candid", ""))),
                ra_deg=float(row["ra"]),
                dec_deg=float(row["dec"]),
                jd=float(row["obsjd"]),
                mag=float(row.get("magpsf", row.get("mag", 99.0))),
                mag_err=float(row.get("sigmapsf", 0.1)),
                filter_band=_ztf_filter_id(int(row.get("fid", 1))),
                mission="ZTF",
                real_bogus=float(row["rb"]) if "rb" in row else None,
                deep_real_bogus=float(row["drb"]) if "drb" in row else None,
            )
        )
    return obs


def _ztf_filter_id(fid: int) -> str:
    return {1: "g", 2: "r", 3: "i"}.get(fid, "?")


def _jd_to_mjd(jd: float) -> float:
    return jd - 2_400_000.5


def _fetch_ztf_alerce_api(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    *,
    max_objects: int = 200,
) -> list[Observation]:
    """Fetch source-level public ZTF detections through the ALeRCE broker.

    IRSA TAP exposes ZTF object summary and image metadata tables, but not the
    per-alert/source table this pipeline needs.  ALeRCE provides public ZTF
    detections with ``magpsf``, ``sigmapsf``, ``rb``, and ``drb`` fields.

    Key design principle: moving solar system objects appear as a NEW OID each
    night because they move faster than ALeRCE's ~1 arcsec OID-association
    radius (MBAs at opposition move ~700 arcsec/night; NEOs move faster).
    Each nightly detection of the same moving object therefore has its own OID
    with ``ndet=1``.  Persistent sources (stars, AGN) accumulate hundreds of
    detections under one OID.  The ndet cap is what separates transient
    single-sky-position events from stationary background sources.
    """
    try:
        from alerce import Alerce  # type: ignore[import]
    except Exception:
        return []

    try:
        client = Alerce()
    except Exception:
        return []

    # Mode 1: asteroid-classified transients (ndet ≤ 3, single-detection first).
    # The stamp classifier labels detections as "asteroid" when the difference-
    # image cutout looks like a point source appearing at a previously empty sky
    # position — exactly the signature of a moving solar system object.
    # Capping ndet ≤ 3 excludes persistent background sources that happen to
    # have one cutout classified as "asteroid" due to image artifacts.  Ordering
    # ASC surfaces ndet=1 OIDs (the true single-night transients) first.
    asteroid_obs = _fetch_alerce_objects_for_filter(
        client,
        ra_deg,
        dec_deg,
        radius_deg,
        start_jd,
        end_jd,
        max_objects=max_objects,
        query_filter={"classifier": "stamp_classifier", "class_name": "asteroid"},
        order_mode="ASC",   # ndet=1 OIDs first (true single-night transients)
        ndet_max=3,         # exclude persistent sources; moving objects have ndet=1
    )
    if asteroid_obs:
        return asteroid_obs

    # Mode 2: any low-ndet transients (ndet 1–3, generic fallback).
    # When the asteroid classifier returns nothing, fall back to all OIDs that
    # appeared ≤3 times.  Real moving objects are ndet=1 per night; astrometric
    # noise between nights is ~1 arcsec, far smaller than the nightly position
    # shift (~700 arcsec for an MBA), so same-object nightly OIDs never merge.
    return _fetch_alerce_objects_for_filter(
        client,
        ra_deg,
        dec_deg,
        radius_deg,
        start_jd,
        end_jd,
        max_objects=max_objects,
        query_filter={},
        order_mode="ASC",
        ndet_max=3,
    )


def _fetch_alerce_objects_for_filter(
    client: Any,
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    *,
    max_objects: int,
    query_filter: dict[str, str],
    order_mode: str = "ASC",
    ndet_max: int | None = 20,
) -> list[Observation]:
    """Fetch ALeRCE object detections for one object-query filter.

    Moving solar system objects appear as new OIDs at each night's position
    (ndet=1 per OID).  Ordering by ndet ASC and capping at ndet_max ensures
    these low-detection-count objects are returned first instead of persistent
    stars/AGN that dominate an ndet DESC query.  The asteroid-classifier path
    passes order_mode="DESC" (any ndet) since it is already filtered to the
    asteroid class.
    """
    extra: dict[str, Any] = {}
    if ndet_max is not None:
        extra["ndet"] = [1, ndet_max]
    try:
        objects_payload = client.query_objects(
            format="json",
            survey="ztf",
            ra=ra_deg,
            dec=dec_deg,
            radius=max(radius_deg, 0.0) * 3600.0,
            firstmjd=[_jd_to_mjd(start_jd), _jd_to_mjd(end_jd)],
            lastmjd=[_jd_to_mjd(start_jd), _jd_to_mjd(end_jd)],
            page=1,
            page_size=max(1, min(max_objects, 100)),
            order_by="ndet",
            order_mode=order_mode,
            **extra,
            **query_filter,
        )
    except Exception:
        return []

    if isinstance(objects_payload, dict):
        object_rows = objects_payload.get("items", [])
    else:
        object_rows = objects_payload

    observations: list[Observation] = []
    seen: set[str] = set()
    for obj in object_rows[:max_objects]:
        if not isinstance(obj, dict):
            continue
        oid = obj.get("oid")
        if not oid:
            continue
        try:
            detections = client.query_detections(str(oid), format="json", survey="ztf")
        except Exception:
            continue
        for det in detections:
            obs = _parse_alerce_detection(det, str(oid), start_jd, end_jd)
            if obs is None or obs.obs_id in seen:
                continue
            seen.add(obs.obs_id)
            observations.append(obs)
    return observations


def _parse_alerce_detection(
    row: Any,
    oid: str,
    start_jd: float,
    end_jd: float,
) -> Observation | None:
    if not isinstance(row, dict):
        return None
    try:
        jd = float(row["mjd"]) + 2_400_000.5
        if not (start_jd <= jd <= end_jd):
            return None
        mag = row.get("magpsf")
        if mag is None:
            return None
        candid = row.get("candid") or f"{oid}_{row['mjd']}_{row.get('fid', '')}"
        rb = row.get("rb")
        drb = row.get("drb")
        return Observation(
            obs_id=str(candid),
            ra_deg=float(row["ra"]),
            dec_deg=float(row["dec"]),
            jd=jd,
            mag=float(mag),
            mag_err=float(row.get("sigmapsf", 0.1) or 0.1),
            filter_band=_ztf_filter_id(int(row.get("fid", 1) or 1)),
            mission="ZTF",
            real_bogus=float(rb) if rb is not None else None,
            deep_real_bogus=float(drb) if drb is not None else None,
            field_id=oid,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _fetch_ztf_irsa_api(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
) -> list[Observation]:
    """Legacy fallback for source-level ZTF rows from a TAP-like JSON payload.

    Current IRSA TAP exposes ZTF object summaries and image metadata, not the
    per-alert/source table this parser expects. Keep this path fail-closed for
    old deployments or tests, but never query ``ztf.ztf_current_meta_sci`` as if
    it contained source detections.
    """
    import requests

    username = os.environ.get("ZTF_IRSA_USERNAME", "")
    password = os.environ.get("ZTF_IRSA_PASSWORD", "")
    auth = (username, password) if username and password else None

    tap_url = "https://irsa.ipac.caltech.edu/TAP/sync"
    adql = (
        f"SELECT candid, ra, dec, jd, magpsf, sigmapsf, fid, rb, drb "
        f"FROM ztf_alerts "
        f"WHERE CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra_deg}, {dec_deg}, {radius_deg})) = 1 "
        f"AND jd >= {start_jd} AND jd <= {end_jd}"
    )
    try:
        resp = requests.get(
            tap_url,
            params={"QUERY": adql, "FORMAT": "json"},
            auth=auth,
            timeout=60,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []
    # Empty response body (no data for this sky region) must not propagate as
    # a retryable error — treat it as "no observations available" and return [].
    try:
        payload = resp.json()
    except (ValueError, Exception):
        return []
    rows = payload.get("data", [])
    cols = payload.get("metadata", [])
    col_names = [c["name"] for c in cols]
    obs: list[Observation] = []
    for row in rows:
        d = dict(zip(col_names, row))
        obs.append(
            Observation(
                obs_id=str(d.get("candid", "")),
                ra_deg=float(d["ra"]),
                dec_deg=float(d["dec"]),
                jd=float(d["jd"]),
                mag=float(d.get("magpsf", 99.0)),
                mag_err=float(d.get("sigmapsf", 0.1)),
                filter_band=_ztf_filter_id(int(d.get("fid", 1))),
                mission="ZTF",
                real_bogus=float(d["rb"]) if "rb" in d else None,
                deep_real_bogus=float(d["drb"]) if "drb" in d else None,
            )
        )
    return obs


# ---------------------------------------------------------------------------
# ATLAS
# ---------------------------------------------------------------------------


def fetch_atlas(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    atlas_token: str | None = None,
    force_refresh: bool = False,
) -> list[Observation]:
    """Query ATLAS Forced Photometry Server for a sky position.

    ``atlas_token`` may also be supplied via the ``ATLAS_TOKEN`` environment variable.
    An explicit argument takes precedence over the environment variable.
    """
    import hashlib

    import requests

    resolved_token = atlas_token or os.environ.get("ATLAS_TOKEN")

    cache_key = hashlib.md5(
        f"atlas_{ra_deg}_{dec_deg}_{radius_deg}_{start_jd}_{end_jd}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        return [Observation(**row) for row in cached]

    base = "https://fallingstar-data.com/forcedphot"
    # ATLAS API requires form-encoded data (not JSON) and only recognises the
    # standard fields: ra, dec, mjd_min, mjd_max, send_email.
    # Using json= sends Content-Type:application/json which the server rejects
    # with HTTP 400.  Match the working fetch_atlas_forced implementation.
    headers: dict[str, str] = {"Accept": "application/json"}
    if resolved_token:
        headers["Authorization"] = f"Token {resolved_token}"

    payload = {
        "ra": ra_deg,
        "dec": dec_deg,
        "mjd_min": start_jd - 2400000.5,
        "mjd_max": end_jd - 2400000.5,
        "send_email": False,
    }
    resp = requests.post(f"{base}/queue/", data=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    # Empty response body from the ATLAS queue endpoint means the request was
    # not accepted; treat as no data rather than a retryable network error.
    try:
        task_url = resp.json()["url"]
    except (KeyError, ValueError, Exception):
        return []

    # Poll for completion
    for _ in range(60):
        time.sleep(5)
        poll = requests.get(task_url, headers=headers, timeout=30)
        poll.raise_for_status()
        try:
            poll_data = poll.json()
        except (ValueError, Exception):
            continue
        if poll_data.get("finishtimestamp"):
            break

    try:
        result_url = poll.json().get("result_url", "")
    except (ValueError, Exception):
        return []
    if not result_url:
        return []

    data_resp = requests.get(result_url, headers=headers, timeout=60)
    data_resp.raise_for_status()
    lines = data_resp.text.strip().split("\n")
    obs = _parse_atlas_photometry(lines)
    _save_cache(cache_key, [o.model_dump() for o in obs])
    return obs


def _parse_atlas_photometry(lines: list[str]) -> list[Observation]:
    if not lines:
        return []
    if lines[0].startswith("#"):
        header = [h.strip() for h in lines[0].lstrip("#").split()]
        data_lines = lines[1:]
    else:
        header = []
        data_lines = lines

    obs: list[Observation] = []
    for i, line in enumerate(data_lines):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if header:
            d = dict(zip(header, parts))
        else:
            d = {}
        mjd = float(d.get("MJD", parts[0]))
        jd = mjd + 2400000.5
        filt = d.get("F", "o")
        obs.append(
            Observation(
                obs_id=f"atlas_{i}_{mjd}",
                ra_deg=float(d.get("RA", 0.0)),
                dec_deg=float(d.get("Dec", 0.0)),
                jd=jd,
                mag=float(d.get("m", d.get("mag", 99.0))),
                mag_err=float(d.get("dm", 0.1)),
                filter_band=filt,
                mission="ATLAS",
            )
        )
    return obs


# ---------------------------------------------------------------------------
# MPC known objects
# ---------------------------------------------------------------------------


def fetch_mpc_known(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
) -> list[Observation]:
    """Return MPC catalog positions for known objects in a sky region."""
    import hashlib

    cache_key = hashlib.md5(f"mpc_{ra_deg}_{dec_deg}_{radius_deg}".encode()).hexdigest()
    cached = _load_cache(cache_key)
    if cached is not None:
        return [Observation(**row) for row in cached]

    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.mpc import MPC  # type: ignore[import]

    center = SkyCoord(ra=ra_deg, dec=dec_deg, unit="deg")
    result = MPC.query_objects_in_region(center, radius_deg * u.deg)

    obs: list[Observation] = []
    if result is None:
        return obs
    for row in result:
        obs.append(
            Observation(
                obs_id=f"mpc_{row['designation']}",
                ra_deg=float(row["RA"]),
                dec_deg=float(row["Dec"]),
                jd=float(row.get("epoch", 0.0)),
                mag=float(row.get("H", 20.0)),
                mag_err=0.0,
                filter_band="V",
                mission="MPC",
            )
        )
    _save_cache(cache_key, [o.model_dump() for o in obs])
    return obs


# ---------------------------------------------------------------------------
# JPL Horizons ephemerides
# ---------------------------------------------------------------------------


def fetch_horizons(
    target: str,
    ra_deg: float,
    dec_deg: float,
    start_jd: float,
    end_jd: float,
    step: str = "1h",
) -> list[Observation]:
    """Fetch ephemeris from JPL Horizons for a known object."""
    import hashlib

    cache_key = hashlib.md5(
        f"horizons_{target}_{start_jd}_{end_jd}_{step}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key)
    if cached is not None:
        return [Observation(**row) for row in cached]

    from astropy.time import Time
    from astroquery.jplhorizons import Horizons  # type: ignore[import]

    start_iso = Time(start_jd, format="jd").iso
    end_iso = Time(end_jd, format="jd").iso
    obj = Horizons(
        id=target, location="500@399",
        epochs={"start": start_iso, "stop": end_iso, "step": step},
    )
    eph = obj.ephemerides()

    obs: list[Observation] = []
    for row in eph:
        obs.append(
            Observation(
                obs_id=f"horizons_{target}_{row['datetime_jd']:.4f}",
                ra_deg=float(row["RA"]),
                dec_deg=float(row["DEC"]),
                jd=float(row["datetime_jd"]),
                mag=float(row.get("V", 20.0)),
                mag_err=0.0,
                filter_band="V",
                mission="MPC",
            )
        )
    _save_cache(cache_key, [o.model_dump() for o in obs])
    return obs


# ---------------------------------------------------------------------------
# Top-level fetch entry point
# ---------------------------------------------------------------------------


def fetch(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    surveys: tuple[Mission, ...] = ("ZTF",),
    atlas_token: str | None = None,
    force_refresh: bool = False,
) -> FetchResult:
    """Fetch alerts from the requested surveys for a sky position and time range."""
    from astropy.time import Time

    fetched_at_jd = Time.now().jd
    all_alerts: list[Observation] = []

    for survey in surveys:
        if survey == "ZTF":
            all_alerts.extend(
                fetch_ztf(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                          force_refresh=force_refresh)
            )
        elif survey == "ATLAS":
            all_alerts.extend(
                fetch_atlas(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                            atlas_token=atlas_token, force_refresh=force_refresh)
            )
        elif survey == "MPC":
            all_alerts.extend(fetch_mpc_known(ra_deg, dec_deg, radius_deg))
        elif survey == "TESS":
            # Route to TESS FFI archive fetch for discovery runs
            all_alerts.extend(
                fetch_tess_ffis(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                                force_refresh=force_refresh)
            )
        elif survey == "DECam":
            # Route to DECam/NOIRLab NSC DR2 archive fetch for discovery runs
            all_alerts.extend(
                fetch_decam_archive(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                                    force_refresh=force_refresh)
            )
        elif survey == "WISE":
            # Route to WISE/NEOWISE archive fetch for discovery runs
            all_alerts.extend(
                fetch_wise_archive(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                                   force_refresh=force_refresh)
            )

    provenance = FetchProvenance(
        surveys=surveys,
        start_jd=start_jd,
        end_jd=end_jd,
        search_ra_deg=ra_deg,
        search_dec_deg=dec_deg,
        search_radius_deg=radius_deg,
        fetched_at_jd=fetched_at_jd,
        cached=False,
    )
    return FetchResult(alerts=tuple(all_alerts), provenance=provenance)


def fetch_batch(
    targets: list[tuple[float, float]],
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    surveys: tuple[Mission, ...] = ("ZTF",),
    atlas_token: str | None = None,
    force_refresh: bool = False,
) -> list[FetchResult]:
    """Fetch alerts for multiple (RA, Dec) targets in one call.

    Each element of ``targets`` is a ``(ra_deg, dec_deg)`` pair.  Returns one
    :class:`FetchResult` per target in the same order.
    """
    return [
        fetch(
            ra_deg=ra,
            dec_deg=dec,
            radius_deg=radius_deg,
            start_jd=start_jd,
            end_jd=end_jd,
            surveys=surveys,
            atlas_token=atlas_token,
            force_refresh=force_refresh,
        )
        for ra, dec in targets
    ]












def count_known_objects_in_field(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float = 1.0,
) -> int:
    """Count MPC known objects within a circular field.

    Queries ``fetch_mpc_known`` and returns the number of observations returned.
    Returns 0 on any error (network or parse failure).
    """
    try:
        observations = fetch_mpc_known(ra_deg, dec_deg, radius_deg)
        return len(observations)
    except Exception:
        return 0


def _mpc_to_float(val: Any) -> float:
    """Convert an MPC column value that may be an astropy Quantity or Time to float.

    astroquery 0.4.11+ converts the observation table to a QTable and assigns
    units to all numeric columns (epoch→d, RA→deg, DEC→deg, mag→mag).
    Accessing a single row element then yields an astropy Quantity, and
    float(dimensioned_Quantity) raises TypeError.  Extract the numeric value via
    .jd (astropy Time), .value (astropy Quantity), or plain float().
    """
    if hasattr(val, "jd"):
        return float(val.jd)
    if hasattr(val, "value"):
        return float(val.value)
    return float(val)


def _mpc_row_value(row: object, *names: str, default: Any = None) -> Any:
    """Read the first available MPC column from Astropy rows or test fixtures."""
    colnames = getattr(row, "colnames", None)
    known_columns = set(colnames) if isinstance(colnames, (list, tuple)) else None
    for name in names:
        if known_columns is not None and name not in known_columns:
            continue
        try:
            value = row[name]  # type: ignore[index]
        except (KeyError, TypeError, IndexError):
            continue
        if value is not None:
            return value
    return default


def fetch_mpc_observations(
    designation: str,
    force_refresh: bool = False,
    *,
    raise_on_error: bool = False,
) -> list:
    """Fetch MPC observation history for a known-object designation.

    Queries ``astroquery.mpc`` for all observations of the given designation
    and returns a list of :class:`schemas.Observation` objects.
    Returns an empty list on any error (network failure, unknown designation).

    Args:
        designation: Official MPC number or unpacked provisional designation.
        force_refresh: Bypass both the project cache and astroquery cache.
        raise_on_error: Re-raise provider failures for audited acquisition workflows.
    """
    import hashlib

    cache_key = hashlib.md5(f"mpc_obs_{designation}".encode()).hexdigest()
    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        obs_list = []
        for d in cached:
            try:
                obs_list.append(Observation(**d))
            except Exception:
                pass
        return obs_list

    # Exceptions that indicate a transient infrastructure failure and should be
    # re-raised when raise_on_error=True so the caller's circuit breaker can
    # detect a genuinely unavailable provider.
    _INFRA_ERRORS = (
        ConnectionError,
        TimeoutError,
        OSError,  # includes socket.timeout via inheritance on CPython
    )

    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        # astroquery exposes the authoritative MPC observation-history query.
        table = MPC.get_observations(designation, cache=not force_refresh)

        # MPC returns None for unknown or malformed designations rather than
        # raising; treat this as an empty result, not a provider failure.
        if table is None:
            _save_cache(cache_key, [])
            return []

        obs_list = []
        for row_index, row in enumerate(table):
            try:
                # Current astroquery columns use ``epoch``, ``RA``, and ``DEC``.
                # The fallbacks preserve compatibility with older cached fixtures.
                # astroquery 0.4.11+ converts the table to QTable and assigns
                # units to all numeric columns (epoch→d, RA→deg, DEC→deg, mag→mag).
                # All scalar extractions use _mpc_to_float() so that dimensioned
                # Quantities are handled without TypeError.
                jd = _mpc_to_float(_mpc_row_value(row, "epoch", "JD"))
                dec = _mpc_to_float(_mpc_row_value(row, "DEC", "Dec"))
                ra = _mpc_to_float(_mpc_row_value(row, "RA"))
                mag_value = _mpc_row_value(row, "mag", default=99.0)
                band_value = _mpc_row_value(row, "band", default="?")
                observatory = str(_mpc_row_value(row, "observatory", default="UNK"))
                mag = _mpc_to_float(mag_value) if not getattr(mag_value, "mask", False) else 99.0
                band = str(band_value) if not getattr(band_value, "mask", False) else "?"

                # Hash stable observation fields so every historical record has
                # a deterministic unique identifier across retries and caches.
                identity = (
                    f"{designation}|{jd:.8f}|{ra:.8f}|{dec:.8f}|"
                    f"{observatory}|{row_index}"
                )
                obs_hash = hashlib.sha256(identity.encode()).hexdigest()[:16]
                obs = Observation(
                    obs_id=f"MPC_{obs_hash}",
                    ra_deg=ra,
                    dec_deg=dec,
                    jd=jd,
                    mag=mag,
                    mag_err=0.1,
                    filter_band=band,
                    mission="MPC",
                    real_bogus=1.0,
                )
                obs_list.append(obs)
            except Exception:
                pass
        _save_cache(cache_key, [o.model_dump() for o in obs_list])
        return obs_list
    except _INFRA_ERRORS:
        # Infrastructure failures (network down, timeout, socket error): re-raise
        # when requested so the caller's circuit breaker can detect a provider outage.
        if raise_on_error:
            raise
        return []
    except Exception as _exc:
        # Query-level failures (invalid designation format, API rejection,
        # astroquery parse errors): not an infrastructure outage.  Never feed
        # the circuit breaker — treat as an empty result regardless of
        # raise_on_error so the caller records insufficient_observations instead.
        # Emit a warning so silent failures are visible in operator console output.
        import sys
        print(
            f"  [fetch_mpc_observations] query-level error for {designation!r}: "
            f"{type(_exc).__name__}: {_exc}",
            file=sys.stderr,
            flush=True,
        )
        return []


def fetch_atlas_forced(
    ra_deg: float,
    dec_deg: float,
    start_jd: float,
    end_jd: float,
    atlas_token: str | None = None,
    force_refresh: bool = False,
    max_polls: int = 60,
    poll_interval_seconds: float = 0.0,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    task_url: str | None = None,
) -> list:
    """Fetch ATLAS forced photometry at a given sky position.

    Queries the ATLAS Forced Photometry Server REST API for orange (o) and
    cyan (c) band photometry at (ra_deg, dec_deg) over the requested time
    window.  Results are disk-cached.

    Args:
        ra_deg: Right ascension in degrees [0, 360).
        dec_deg: Declination in degrees [-90, 90].
        start_jd: Start of the search window as Julian Date.
        end_jd: End of the search window as Julian Date.
        atlas_token: ATLAS API token.  Falls back to ``ATLAS_TOKEN`` env var.
        force_refresh: If True, bypass the on-disk cache.
        max_polls: Maximum task-status polls before returning no data.
        poll_interval_seconds: Delay between unfinished task polls. The default
            is zero for fast unit tests; operator scripts should pass a
            positive value for live ATLAS jobs.
        progress_callback: Optional callable receiving each task-status JSON
            payload after a successful poll.
        task_url: Existing ATLAS queue task URL to resume polling. When set,
            no new ATLAS queue request is submitted.

    Returns:
        List of :class:`~schemas.Observation` objects.  Returns an empty list
        on network failure or authentication error.
    """
    import hashlib
    import os

    token = atlas_token or os.environ.get("ATLAS_TOKEN", "")
    cache_key = hashlib.md5(
        f"atlas_forced_{ra_deg:.5f}_{dec_deg:.5f}_{start_jd:.3f}_{end_jd:.3f}".encode()
    ).hexdigest()

    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        obs_list = []
        for d in cached:
            try:
                obs_list.append(Observation(**d))
            except Exception:
                pass
        return obs_list

    if not token:
        return []

    try:
        import requests  # type: ignore[import]

        # Convert JD to MJD for ATLAS API
        start_mjd = start_jd - 2400000.5
        end_mjd = end_jd - 2400000.5

        if task_url is None:
            resp = requests.post(
                "https://fallingstar-data.com/forcedphot/queue/",
                headers={
                    "Authorization": f"Token {token}",
                    "Accept": "application/json",
                },
                data={
                    "ra": ra_deg,
                    "dec": dec_deg,
                    "mjd_min": start_mjd,
                    "mjd_max": end_mjd,
                    "send_email": False,
                },
                timeout=30,
            )
            resp.raise_for_status()
            queued = resp.json()
            task_url = queued.get("url", "")
            if progress_callback is not None:
                progress_callback({"event": "queued", **queued})
        elif progress_callback is not None:
            progress_callback({"event": "resume_existing_task", "url": task_url})
        if not task_url:
            return []

        for poll_index in range(max(1, max_polls)):
            result_resp = requests.get(
                task_url,
                headers={
                    "Authorization": f"Token {token}",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            result_resp.raise_for_status()
            data = result_resp.json()
            if progress_callback is not None:
                progress_callback(data)
            if data.get("result_url"):
                text_resp = requests.get(
                    data["result_url"],
                    headers={
                        "Authorization": f"Token {token}",
                        "Accept": "text/plain, */*",
                    },
                    timeout=30,
                )
                text_resp.raise_for_status()
                lines = text_resp.text.splitlines()
                obs_list = _parse_atlas_photometry(lines)
                _save_cache(cache_key, [o.model_dump() for o in obs_list])
                return obs_list
            if data.get("finishtimestamp"):
                return []
            if poll_interval_seconds > 0 and poll_index < max_polls - 1:
                time.sleep(poll_interval_seconds)
        return []
    except Exception:
        return []


def fetch_ztf_alerts(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    force_refresh: bool = False,
) -> list:
    """Fetch public ZTF source detections.

    Queries the public ALeRCE ZTF broker for detections within ``radius_deg``
    of (``ra_deg``, ``dec_deg``) in the time window [``start_jd``, ``end_jd``].
    Results are disk-cached; subsequent calls with the same parameters return
    immediately from cache unless ``force_refresh=True``.

    Args:
        ra_deg: Right ascension of the search centre in degrees.
        dec_deg: Declination of the search centre in degrees.
        radius_deg: Search radius in degrees.
        start_jd: Start of the search window as Julian Date.
        end_jd: End of the search window as Julian Date.
        force_refresh: Bypass on-disk cache if True.

    Returns:
        List of :class:`~schemas.Observation` objects.  Returns an empty list
        on network failure or missing dependency.
    """
    import hashlib

    cache_key = hashlib.md5(
        f"ztf_irsa_{ra_deg:.5f}_{dec_deg:.5f}_{radius_deg:.4f}"
        f"_{start_jd:.3f}_{end_jd:.3f}".encode()
    ).hexdigest()

    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        obs_list = []
        for d in cached:
            try:
                obs_list.append(Observation(**d))
            except Exception:
                pass
        return obs_list

    ztf_obs = _fetch_ztf_alerce_api(ra_deg, dec_deg, radius_deg, start_jd, end_jd)
    if not ztf_obs:
        ztf_obs = _fetch_ztf_irsa_api(ra_deg, dec_deg, radius_deg, start_jd, end_jd)
    _save_cache(cache_key, [o.model_dump() for o in ztf_obs])
    return ztf_obs






def fetch_panstarrs_catalog(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    epoch_jd: float = 2460000.5,
    force_refresh: bool = False,
) -> list:
    """Fetch Pan-STARRS DR2 catalog sources in a cone search.

    Queries the Pan-STARRS PS1 catalog via ``astroquery.mast`` for
    point-source detections around the target position.  Results are
    cached to ``.neo_cache/`` by query parameters.

    Args:
        ra_deg: Right ascension of search centre in degrees [0, 360).
        dec_deg: Declination of search centre in degrees [-90, 90].
        radius_deg: Search radius in degrees.
        epoch_jd: Reference epoch as Julian Date (default 2460000.5).
        force_refresh: If ``True``, bypass the on-disk cache.

    Returns:
        List of :class:`~schemas.Observation` objects from Pan-STARRS.
        Returns an empty list on network failure or when no sources are found.
    """
    import hashlib

    cache_key = hashlib.md5(
        f"panstarrs:{ra_deg:.6f}:{dec_deg:.6f}:{radius_deg:.6f}:{epoch_jd:.2f}".encode()
    ).hexdigest()
    cache_path = _CACHE_DIR / f"{cache_key}.json"

    if not force_refresh and cache_path.exists():
        try:
            with cache_path.open() as f:
                raw = json.load(f)
            return [Observation(**item) for item in raw]
        except Exception:
            pass

    observations: list = []
    try:
        from astroquery.mast import Catalogs  # type: ignore[import]

        results = Catalogs.query_region(  # type: ignore[no-untyped-call]
            f"{ra_deg} {dec_deg}",
            radius=radius_deg,
            catalog="PanSTARRS",
            data_release="dr2",
            table="mean",
        )
        for row in results:
            try:
                obs = Observation(
                    obs_id=f"ps1_{row['objID']}",
                    jd=float(epoch_jd),
                    ra_deg=float(row["raMean"]),
                    dec_deg=float(row["decMean"]),
                    mag=float(row["rMeanPSFMag"]) if row["rMeanPSFMag"] else 99.0,
                    mag_err=float(row["rMeanPSFMagErr"]) if row["rMeanPSFMagErr"] else 0.0,
                    filter_band="r",
                    mission="PanSTARRS",
                )
                observations.append(obs)
            except Exception:
                continue
    except Exception:
        pass

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w") as f:
            json.dump([o.model_dump() for o in observations], f)
    except Exception:
        pass

    return observations






def fetch_recent_mpc_neos(n_days: int = 30, force_refresh: bool = False) -> list[Observation]:
    """Fetch recently announced NEOs from the MPC catalog.

    Queries ``astroquery.mpc.MPC`` for NEO asteroids and filters to objects
    discovered within the last ``n_days`` days based on the ``discovery_date``
    column.  Results are disk-cached per ``n_days`` value.

    Args:
        n_days: Number of days to look back for recent discoveries (default 30).
        force_refresh: If True, bypass the on-disk cache.

    Returns:
        List of :class:`~schemas.Observation` objects, one per result row.
        Returns an empty list if the import or query fails.
    """
    import hashlib

    cache_key = hashlib.md5(f"mpc_recent_neos:{n_days}".encode()).hexdigest()
    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        obs_list: list[Observation] = []
        for d in cached:
            try:
                obs_list.append(Observation(**d))
            except Exception:
                pass
        return obs_list

    try:
        from astroquery.mpc import MPC  # type: ignore[import]
    except ImportError:
        return []

    try:
        from datetime import date, timedelta

        table = MPC.query_objects("asteroid", is_neo=True)
        cutoff = date.today() - timedelta(days=n_days)
        result_list: list[Observation] = []
        for i, row in enumerate(table):
            try:
                disc_raw = row.get("discovery_date") or row.get("disc_date")
                if disc_raw is not None:
                    if hasattr(disc_raw, "isoformat"):
                        disc_date = disc_raw
                    else:
                        from datetime import datetime as _dt
                        disc_date = _dt.strptime(str(disc_raw)[:10], "%Y-%m-%d").date()
                    if disc_date < cutoff:
                        continue
                ra_val = row.get("ra") or row.get("RA") or 0.0
                dec_val = row.get("dec") or row.get("Dec") or 0.0
                h_val = row.get("h") or row.get("H") or 99.0
                obs = Observation(
                    obs_id=f"mpc_recent_{i}",
                    ra_deg=float(ra_val),
                    dec_deg=float(dec_val),
                    jd=2460000.5,
                    mag=float(h_val) if h_val is not None else 99.0,
                    mag_err=0.1,
                    filter_band="V",
                    mission="MPC",
                    real_bogus=1.0,
                )
                result_list.append(obs)
            except Exception:
                pass
        _save_cache(cache_key, [o.model_dump() for o in result_list])
        return result_list
    except Exception:
        return []


















def fetch_known_phas(force_refresh: bool = False) -> list[dict]:
    """Fetch the MPC list of known Potentially Hazardous Asteroids.

    Queries the MPC PHA catalog via ``astroquery.mpc`` and returns a list
    of dicts with keys: ``designation``, ``absolute_magnitude_h``,
    ``moid_au``, ``neo_class``.  Results are disk-cached under the key
    ``"known_phas"``.  Returns an empty list on failure.
    """
    cache_key = "known_phas"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, list):
            return cached
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        tbl = MPC.query_objects("pha")
        rows: list[dict] = []
        for row in tbl:
            desig = str(row.get("designation") or row.get("name") or "unknown")
            h = float(row["absolute_magnitude"]) if "absolute_magnitude" in tbl.colnames else None
            moid = float(row["moid"]) if "moid" in tbl.colnames else None
            a = float(row["semimajor_axis"]) if "semimajor_axis" in tbl.colnames else None
            e = float(row["eccentricity"]) if "eccentricity" in tbl.colnames else None
            q = (a * (1.0 - e)) if (a is not None and e is not None) else None
            Q = (a * (1.0 + e)) if (a is not None and e is not None) else None
            neo_class: str = "unknown"
            if q is not None and a is not None and Q is not None:
                if Q < 0.983:
                    neo_class = "ieo"
                elif a < 1.0:
                    neo_class = "aten"
                elif q < 1.017:
                    neo_class = "apollo"
                elif q < 1.3:
                    neo_class = "amor"
            rows.append({
                "designation": desig,
                "absolute_magnitude_h": h,
                "moid_au": moid,
                "neo_class": neo_class,
            })
        _save_cache(cache_key, rows)
        return rows
    except Exception:
        return []




def fetch_horizons_ephemeris(
    designation: str,
    target_jds: list[float],
    force_refresh: bool = False,
) -> list[dict]:
    """Fetch JPL Horizons ephemeris for a named object at specific JDs.

    Returns a list of dicts with keys ``"jd"``, ``"ra_deg"``, ``"dec_deg"``,
    ``"delta_au"`` (geocentric distance), and ``"mag"``.  Results are
    disk-cached under ``"horizons_<designation>"``.  Returns an empty list on
    failure.
    """
    cache_key = f"horizons_{designation.replace(' ', '_')}"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, list):
            return cached
    try:
        from astroquery.jplhorizons import Horizons  # type: ignore[import]

        results: list[dict] = []
        for jd in target_jds:
            obj = Horizons(
                id=designation,
                location="500@399",
                epochs=jd,
            )
            eph = obj.ephemerides()
            if len(eph) == 0:
                continue
            row = eph[0]
            results.append({
                "jd": float(jd),
                "ra_deg": float(row["RA"]),
                "dec_deg": float(row["DEC"]),
                "delta_au": float(row.get("delta", 1.0) or 1.0),
                "mag": float(row.get("V", 99.0) or 99.0),
            })
        _save_cache(cache_key, results)
        return results
    except Exception:
        return []






def count_observations_by_mission(fetch_result: FetchResult) -> dict[str, int]:
    """Return a dict mapping mission name to observation count.

    Iterates over ``fetch_result.alerts``, groups by ``obs.mission`` (string),
    and returns the count per mission.  Returns an empty dict for an empty
    ``FetchResult``.

    Args:
        fetch_result: :class:`~schemas.FetchResult` object.

    Returns:
        Dict mapping mission name (str) to count (int).
    """
    counts: dict[str, int] = {}
    for obs in fetch_result.alerts:
        mission = str(getattr(obs, "mission", "unknown"))
        counts[mission] = counts.get(mission, 0) + 1
    return counts










def filter_by_magnitude(observations: list, min_mag: float, max_mag: float) -> list:
    """Filter observations to those with magnitude in [min_mag, max_mag].

    Sentinel magnitudes (≥ 90) are always excluded.

    Args:
        observations: List of observation-like objects with a ``mag`` attribute.
        min_mag: Minimum magnitude (inclusive).
        max_mag: Maximum magnitude (inclusive).

    Returns:
        Filtered list of observations.
    """
    result = []
    for obs in observations:
        mag = getattr(obs, "mag", None)
        if mag is None:
            continue
        if float(mag) >= 90.0:
            continue
        if min_mag <= float(mag) <= max_mag:
            result.append(obs)
    return result










def compute_observation_rate(fetch_result: object) -> float | None:
    """Return the mean number of observations per night in a FetchResult.

    Night boundaries are determined by flooring each observation's JD to an
    integer.  Returns ``None`` if fewer than 2 distinct nights are present
    (rate is undefined for a single-night dataset).
    Returns ``None`` if the FetchResult has no alerts.
    """
    alerts = getattr(fetch_result, "alerts", None) or []
    nights: dict[int, int] = {}
    for obs in alerts:
        jd = getattr(obs, "jd", None)
        if jd is None:
            continue
        night = int(float(jd))
        nights[night] = nights.get(night, 0) + 1
    if len(nights) < 2:
        return None
    return float(sum(nights.values()) / len(nights))















# ---------------------------------------------------------------------------
# Discovery archives (unreviewed): WISE/NEOWISE, DECam/NOIRLab, TESS FFIs
# ---------------------------------------------------------------------------


def fetch_wise_archive(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    force_refresh: bool = False,
) -> list[Observation]:
    """Query NASA IRSA for WISE/NEOWISE single-exposure source detections.

    Targets the NEOWISE single-epoch photometry catalog (neowiser_p1bs_psd),
    which covers 2013-2024 with infrared detections of 158,000+ minor planets.
    Infrared sensitivity finds low-albedo NEOs that optical surveys miss.
    Each row is one single-exposure detection at a unique epoch — exactly the
    format the linker needs to identify multi-night moving sources.

    Returns Observation objects with mission='WISE'.
    """
    import hashlib
    # Stable cache key derived from all query parameters
    cache_key = hashlib.md5(
        f"wise_{ra_deg}_{dec_deg}_{radius_deg}_{start_jd}_{end_jd}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        # Reconstruct Observation objects from cached dicts
        return [Observation(**row) for row in cached]

    try:
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.ipac.irsa import Irsa  # type: ignore[import]
    except ImportError:
        # Return empty list when astroquery is not installed
        return []

    # Build sky coordinate for the cone search centre
    coord = SkyCoord(ra=ra_deg, dec=dec_deg, unit="deg")
    try:
        # Request only the columns we need: reduces payload vs the default '*'
        # which can time out for dense fields (e.g. Taurus/Pleiades).
        table = Irsa.query_region(
            coord,
            catalog="neowiser_p1bs_psd",
            spatial="Cone",
            radius=radius_deg * u.deg,
            columns="ra,dec,mjd_obs,w1mpro,w1sigmpro",
        )
    except Exception as exc:
        # Print to stderr so operators can diagnose IRSA network/catalog issues.
        import sys
        print(
            f"[fetch] WISE IRSA query FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr, flush=True,
        )
        return []

    if table is None or len(table) == 0:
        import sys
        print(
            f"[fetch] WISE IRSA returned 0 rows for "
            f"RA={ra_deg:.2f} Dec={dec_deg:.2f} r={radius_deg:.2f}°",
            file=sys.stderr, flush=True,
        )
        return []

    # Convert JD time window to MJD for comparison with table values
    start_mjd = start_jd - 2_400_000.5
    end_mjd = end_jd - 2_400_000.5
    obs: list[Observation] = []
    for i, row in enumerate(table):
        try:
            # NEOWISE neowiser_p1bs_psd uses mjd_obs (not mjd) for epoch
            mjd = float(row["mjd_obs"])
            # Skip rows outside the requested time window
            if not (start_mjd <= mjd <= end_mjd):
                continue
            jd = mjd + 2_400_000.5
            # Use sentinel 99.0 for missing magnitudes
            w1_raw = row["w1mpro"]
            w1 = float(w1_raw) if w1_raw is not None else 99.0
            w1err_raw = row["w1sigmpro"]
            w1_err = float(w1err_raw) if w1err_raw is not None else 0.1
            obs.append(
                Observation(
                    obs_id=f"wise_{i}_{mjd:.5f}",
                    ra_deg=float(row["ra"]),
                    dec_deg=float(row["dec"]),
                    jd=jd,
                    mag=w1,
                    mag_err=w1_err or 0.1,
                    filter_band="W1",
                    mission="WISE",
                )
            )
        except Exception:
            continue

    _save_cache(cache_key, [o.model_dump() for o in obs])
    return obs


def fetch_decam_archive(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    force_refresh: bool = False,
) -> list[Observation]:
    """Query NOIRLab Astro Data Lab for DECam per-epoch source detections.

    Queries the NOIRLab Source Catalog DR2 (NSC DR2) via the Data Lab TAP
    service. NSC DR2 contains 3.9 billion individual source measurements from
    DECam and other instruments with per-epoch MJD timestamps, enabling
    multi-night moving-object linking.

    Requires the pyvo package (pip install pyvo).
    Returns Observation objects with mission='DECam'.
    """
    import hashlib
    # Stable cache key derived from all query parameters
    cache_key = hashlib.md5(
        f"decam_{ra_deg}_{dec_deg}_{radius_deg}_{start_jd}_{end_jd}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        # Reconstruct Observation objects from cached dicts
        return [Observation(**row) for row in cached]

    try:
        import pyvo  # type: ignore[import]
    except ImportError:
        # Return empty list when pyvo is not installed
        return []

    # Convert JD time window to MJD for the TAP query
    start_mjd = start_jd - 2_400_000.5
    end_mjd = end_jd - 2_400_000.5
    # ADQL cone query using q3c spatial indexing function for efficiency
    adql = (
        f"SELECT ra, dec, mjd, mag_auto, magerr_auto, filter "
        f"FROM nsc_dr2.meas "
        f"WHERE q3c_radial_query(ra, dec, {ra_deg}, {dec_deg}, {radius_deg}) "
        f"AND mjd BETWEEN {start_mjd} AND {end_mjd} "
        f"LIMIT 2000"
    )
    try:
        service = pyvo.dal.TAPService("https://datalab.noirlab.edu/tap")
        result = service.search(adql)
        table = result.to_table()
    except Exception:
        return []

    if table is None or len(table) == 0:
        return []

    obs: list[Observation] = []
    for i, row in enumerate(table):
        try:
            mjd = float(row["mjd"])
            jd = mjd + 2_400_000.5
            # Use sentinel 99.0 for missing magnitudes
            mag_raw = row["mag_auto"]
            mag = float(mag_raw) if mag_raw is not None else 99.0
            magerr_raw = row["magerr_auto"]
            mag_err = float(magerr_raw) if magerr_raw is not None else 0.1
            filt_raw = row["filter"]
            filt = str(filt_raw) if filt_raw is not None else "?"
            obs.append(
                Observation(
                    obs_id=f"decam_{i}_{mjd:.5f}",
                    ra_deg=float(row["ra"]),
                    dec_deg=float(row["dec"]),
                    jd=jd,
                    mag=mag,
                    mag_err=mag_err or 0.1,
                    filter_band=filt,
                    mission="DECam",
                )
            )
        except Exception:
            continue

    _save_cache(cache_key, [o.model_dump() for o in obs])
    return obs


def fetch_tess_ffis(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    force_refresh: bool = False,
) -> list[Observation]:
    """Query MAST for TESS FFI source detections in a sky region.

    Queries the MAST observations service for TESS sectors covering the field
    during the requested time window, then retrieves TIC catalog sources in
    the field for each sector epoch. Each returned Observation carries the
    sector midpoint JD and a TIC source position, giving the linker multi-epoch
    coverage across the 27-day sector windows.

    Note: The TIC catalog contains static stellar sources used as the reference
    background. Moving NEO candidates appear as sources present in FFI images
    but absent from the TIC; full FFI-level source detection is performed by
    preprocess.py. This fetch layer provides sector coverage metadata and static
    reference positions.

    JD conversion: TESS uses BTJD (Barycentric TESS Julian Date);
    BTJD = JD - 2457000.0 (exact offset defined by the TESS mission).

    Returns Observation objects with mission='TESS'.
    """
    import hashlib
    # Stable cache key derived from all query parameters
    cache_key = hashlib.md5(
        f"tess_{ra_deg}_{dec_deg}_{radius_deg}_{start_jd}_{end_jd}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key, force_refresh=force_refresh)
    if cached is not None:
        # Reconstruct Observation objects from cached dicts
        return [Observation(**row) for row in cached]

    try:
        from astroquery.mast import Catalogs, Observations  # type: ignore[import]
    except ImportError:
        # Return empty list when astroquery.mast is not installed
        return []

    # BTJD = JD - 2457000.0 (exact TESS mission epoch offset)
    _BTJD_OFFSET = 2_457_000.0
    start_btjd = start_jd - _BTJD_OFFSET
    end_btjd = end_jd - _BTJD_OFFSET

    try:
        # Query MAST for TESS image observations covering the field
        tess_obs = Observations.query_criteria(
            coordinates=f"{ra_deg} {dec_deg}",
            radius=f"{radius_deg * 3600:.1f} arcsec",
            obs_collection="TESS",
            dataproduct_type="image",
            t_min=[start_btjd - 14, end_btjd + 14],  # sector overlap margin
        )
    except Exception:
        return []

    if tess_obs is None or len(tess_obs) == 0:
        return []

    try:
        # Retrieve TIC catalog sources as reference positions for the field
        tic = Catalogs.query_region(
            f"{ra_deg} {dec_deg}", radius=radius_deg, catalog="TIC"
        )
    except Exception:
        tic = None

    if tic is None or len(tic) == 0:
        return []

    obs: list[Observation] = []
    seen: set[str] = set()
    for sector_row in tess_obs:
        try:
            # Convert sector time range to JD for epoch assignment
            t_min = float(sector_row["t_min"]) if sector_row["t_min"] is not None else start_btjd
            t_max = float(sector_row["t_max"]) if sector_row["t_max"] is not None else end_btjd
            epoch_jd = (t_min + t_max) / 2.0 + _BTJD_OFFSET
            if not (start_jd - 14 <= epoch_jd <= end_jd + 14):
                continue
            seq = sector_row["sequence_number"]
            sec_id = str(seq) if seq is not None else "0"
        except Exception:
            continue

        # Limit TIC sources per sector to avoid observation explosion
        for src in tic[:50]:
            try:
                src_key = f"{src['ID']}_{sec_id}"
                if src_key in seen:
                    continue
                seen.add(src_key)
                tmag_raw = src["Tmag"]
                tmag = float(tmag_raw) if tmag_raw is not None else 20.0
                tmag_err_raw = src.get("e_Tmag")
                tmag_err = float(tmag_err_raw) if tmag_err_raw is not None else 0.1
                obs.append(
                    Observation(
                        obs_id=f"tess_s{sec_id}_t{src['ID']}",
                        ra_deg=float(src["ra"]),
                        dec_deg=float(src["dec"]),
                        jd=epoch_jd,
                        mag=tmag,
                        mag_err=tmag_err or 0.1,
                        filter_band="T",
                        mission="TESS",
                    )
                )
            except Exception:
                continue

    _save_cache(cache_key, [o.model_dump() for o in obs])
    return obs


def fetch_discovery(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    sources: tuple[str, ...] = ("WISE", "DECam", "TESS"),
    force_refresh: bool = False,
) -> FetchResult:
    """Fetch from unreviewed discovery archives for NEO candidate detection.

    Routes to fetch_wise_archive, fetch_decam_archive, and/or fetch_tess_ffis
    depending on the requested sources. ZTF and ATLAS are NOT valid discovery
    sources — they are training data only (ZTF ZAPS and ATLAS pipeline already
    process those streams and submit to MPC). See docs/MISSION.md.

    Args:
        sources: Which unreviewed archives to query. Subset of
                 ("WISE", "DECam", "TESS"). Default: all three.

    Returns:
        FetchResult with observations from the requested archives.
    """
    from astropy.time import Time

    # Record the wall-clock time this function was called
    fetched_at_jd = Time.now().jd
    all_alerts: list[Observation] = []

    for src in sources:
        if src == "WISE":
            # Query NEOWISE single-epoch catalog via IRSA
            all_alerts.extend(
                fetch_wise_archive(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                                   force_refresh=force_refresh)
            )
        elif src == "DECam":
            # Query NOIRLab NSC DR2 via Data Lab TAP
            all_alerts.extend(
                fetch_decam_archive(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                                    force_refresh=force_refresh)
            )
        elif src == "TESS":
            # Query MAST for TESS FFI sector coverage and TIC reference positions
            all_alerts.extend(
                fetch_tess_ffis(ra_deg, dec_deg, radius_deg, start_jd, end_jd,
                                force_refresh=force_refresh)
            )

    provenance = FetchProvenance(
        surveys=tuple(sources),  # type: ignore[arg-type]
        start_jd=start_jd,
        end_jd=end_jd,
        search_ra_deg=ra_deg,
        search_dec_deg=dec_deg,
        search_radius_deg=radius_deg,
        fetched_at_jd=fetched_at_jd,
        cached=False,
    )
    return FetchResult(alerts=tuple(all_alerts), provenance=provenance)
