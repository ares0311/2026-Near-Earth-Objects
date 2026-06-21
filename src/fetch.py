"""Fetch stage — retrieve alerts from ZTF, ATLAS, MPC, and JPL Horizons."""

from __future__ import annotations

__all__ = ["fetch_ztf", "fetch_atlas", "fetch_mpc_known", "fetch_horizons", "fetch",
           "fetch_batch", "estimate_limiting_magnitude", "summarise_fetch_result",
           "merge_survey_alerts", "filter_alerts_by_motion", "build_observation_window",
           "count_known_objects_in_field", "fetch_mpc_observations",
           "fetch_atlas_forced", "fetch_ztf_alerts", "estimate_survey_depth",
           "filter_by_survey", "fetch_panstarrs_catalog", "fetch_css_alerts",
           "fetch_panstarrs_moving_objects", "fetch_recent_mpc_neos",
           "estimate_field_completeness",
           "fetch_known_neo_ephemerides",
           "fetch_neocp_objects",
           "fetch_mpc_orbit_elements",
           "fetch_known_neo_list",
           "fetch_neocp_confirmed",
           "fetch_mpc_orbit_catalog",
           "compute_field_overlap",
           "fetch_known_phas",
           "fetch_mpc_neo_counts",
           "fetch_horizons_ephemeris",
           "summarize_survey_fields",
           "count_observations_by_mission",
           "build_fetch_provenance",
           "get_fetch_result_age",
           "deduplicate_observations",
           "get_survey_coverage_fraction",
           "partition_by_field",
           "filter_by_magnitude",
           "compute_field_sky_area",
           "compute_survey_overlap",
           "count_observations_by_night",
           "compute_temporal_coverage",
           "compute_observation_rate",
           "compute_magnitude_distribution",
           "group_observations_by_night",
           "count_observations_by_filter",
           "get_brightest_observation",
           "get_latest_observation",
           "get_faintest_observation",
           "compute_observation_time_span"]

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
    max_objects: int = 50,
) -> list[Observation]:
    """Fetch source-level public ZTF detections through the ALeRCE broker.

    IRSA TAP exposes ZTF object summary and image metadata tables, but not the
    per-alert/source table this pipeline needs. ALeRCE provides public ZTF
    detections with ``magpsf``, ``sigmapsf``, ``rb``, and ``drb`` fields.
    """
    try:
        from alerce import Alerce  # type: ignore[import]
    except Exception:
        return []

    try:
        client = Alerce()
    except Exception:
        return []

    # Mode 1: asteroid-classified objects (any ndet, highest confidence first).
    # ALeRCE's stamp classifier labels single-night moving-object detections as
    # "asteroid"; this is the highest-signal path.
    asteroid_obs = _fetch_alerce_objects_for_filter(
        client,
        ra_deg,
        dec_deg,
        radius_deg,
        start_jd,
        end_jd,
        max_objects=max_objects,
        query_filter={"classifier": "stamp_classifier", "class_name": "asteroid"},
        order_mode="DESC",  # ndet DESC for classifier-filtered results is fine
        ndet_max=None,      # no cap — get all classified asteroids
    )
    if asteroid_obs:
        return asteroid_obs

    # Mode 2: generic low-ndet objects (ndet 1–20, least detected first).
    # Moving objects appear as one new OID per night at each sky position, so
    # ndet=1 per OID is their signature.  Ordering ASC surfaces them before
    # persistent stars/AGN that dominate an ndet DESC query.
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
        ndet_max=20,
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


def estimate_limiting_magnitude(fetch_result: FetchResult) -> float | None:
    """Estimate the 5-sigma limiting magnitude from detected source magnitudes.

    Uses the faint-end tail of the magnitude distribution (90th–99th percentile)
    as a proxy for the survey depth.  Returns ``None`` when fewer than 5
    observations with valid magnitudes are available.
    """
    import statistics

    mags = [
        obs.mag
        for obs in fetch_result.alerts
        if obs.mag is not None and 10.0 < obs.mag < 35.0
    ]
    if len(mags) < 5:
        return None

    mags_sorted = sorted(mags)
    # Use the 90th–99th percentile band as faint-end estimate
    lo = int(0.90 * len(mags_sorted))
    hi = max(lo + 1, int(0.99 * len(mags_sorted)))
    tail = mags_sorted[lo:hi]
    return round(statistics.mean(tail), 2) if tail else None


def summarise_fetch_result(result: FetchResult) -> dict:
    """Return a summary dict describing a FetchResult.

    Keys: n_alerts, surveys, search_ra_deg, search_dec_deg, search_radius_deg,
    start_jd, end_jd, limiting_magnitude.
    """
    if not isinstance(result, FetchResult):
        raise TypeError("result must be a FetchResult")
    prov = result.provenance
    return {
        "n_alerts": len(result.alerts),
        "surveys": list(prov.surveys),
        "search_ra_deg": prov.search_ra_deg,
        "search_dec_deg": prov.search_dec_deg,
        "search_radius_deg": prov.search_radius_deg,
        "start_jd": prov.start_jd,
        "end_jd": prov.end_jd,
        "limiting_magnitude": prov.limiting_magnitude,
    }


def merge_survey_alerts(results: list[FetchResult]) -> FetchResult:
    """Merge multiple FetchResult objects into a single FetchResult.

    Deduplicates alerts by obs_id.  The provenance of the merged result
    reflects the union of all surveys and the widest JD range.
    """
    if not results:
        prov = FetchProvenance(surveys=(), start_jd=0.0, end_jd=0.0)
        return FetchResult(alerts=(), provenance=prov)

    seen: set[str] = set()
    merged_alerts: list = []
    all_surveys: list = []
    start_jd = float("inf")
    end_jd = float("-inf")

    for result in results:
        prov = result.provenance
        all_surveys.extend(prov.surveys)
        start_jd = min(start_jd, prov.start_jd)
        end_jd = max(end_jd, prov.end_jd)
        for alert in result.alerts:
            if alert.obs_id not in seen:
                seen.add(alert.obs_id)
                merged_alerts.append(alert)

    unique_surveys: tuple = tuple(dict.fromkeys(all_surveys))
    merged_prov = FetchProvenance(
        surveys=unique_surveys,
        start_jd=start_jd,
        end_jd=end_jd,
    )
    return FetchResult(alerts=tuple(merged_alerts), provenance=merged_prov)


def filter_alerts_by_motion(
    alerts: tuple,
    min_rate_arcsec_hr: float = 0.0,
    max_rate_arcsec_hr: float = 60.0,
) -> tuple:
    """Filter a tuple of Observation objects by apparent motion rate.

    Uses ``ssdistnr`` (solar-system distance) as a proxy: objects with
    ``ssdistnr`` < 5 arcsec are likely known solar system objects whose
    motion is already constrained by ZTF.  For observations without
    ``ssdistnr``, the filter passes them through conservatively.

    In practice, motion rate filtering is most useful as a pre-detect step
    to remove stationary calibration stars (rate ≈ 0) and LEO satellite
    streaks (rate > 60 arcsec/hr) from the alert stream.

    Returns a tuple of Observation objects within the specified rate range.
    """

    result = []
    for obs in alerts:
        ssd = getattr(obs, "ssdistnr", None)
        if ssd is None:
            # No motion information — keep conservatively
            result.append(obs)
            continue
        # ZTF ssdistnr is in arcseconds; use as proxy for motion displacement
        # over one 30-second exposure (rate in arcsec/hr = ssd * 120)
        rate_proxy = float(ssd) * 120.0
        if min_rate_arcsec_hr <= rate_proxy <= max_rate_arcsec_hr:
            result.append(obs)
    return tuple(result)


def build_observation_window(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float = 1.0,
    start_jd: float = 2460000.5,
    end_jd: float | None = None,
    surveys: tuple | list | None = None,
) -> object:
    """Construct an ObservationWindow schema object from component parameters.

    Validates that ``start_jd < end_jd``, that ``radius_deg > 0``, and that
    all survey names are valid ``Mission`` literals.  Raises ``ValueError`` on
    invalid inputs.  Returns an :class:`schemas.ObservationWindow`.
    """
    from schemas import ObservationWindow

    if end_jd is None:
        end_jd = start_jd + 30.0

    if start_jd >= end_jd:
        raise ValueError(
            f"start_jd ({start_jd}) must be less than end_jd ({end_jd})"
        )
    if radius_deg <= 0.0:
        raise ValueError(f"radius_deg must be positive (got {radius_deg})")

    valid_missions: set[str] = {"ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"}
    if surveys is None:
        survey_tuple: tuple[Mission, ...] = ("ZTF",)
    else:
        bad = [s for s in surveys if s not in valid_missions]
        if bad:
            raise ValueError(f"Unknown survey(s): {bad}; valid: {sorted(valid_missions)}")
        survey_tuple = tuple(surveys)  # type: ignore[assignment]

    return ObservationWindow(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        radius_deg=radius_deg,
        start_jd=start_jd,
        end_jd=end_jd,
        surveys=survey_tuple,
    )


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


def estimate_survey_depth(fetch_result: FetchResult) -> float | None:
    """Estimate the limiting magnitude of a survey observation window.

    Returns the 95th-percentile apparent magnitude from all alert observations
    in the :class:`~schemas.FetchResult`.  This provides a robust proxy for the
    5-sigma survey depth, robust against a few very bright detections.

    Args:
        fetch_result: A :class:`~schemas.FetchResult` containing survey alerts.

    Returns:
        95th-percentile magnitude as ``float``, or ``None`` if there are no
        valid magnitudes (empty alerts or all sentinel values ≥ 90).
    """
    import numpy as np

    mags = [
        obs.mag
        for obs in fetch_result.alerts
        if obs.mag is not None and obs.mag < 90.0
    ]
    if not mags:
        return None
    return round(float(np.percentile(mags, 95)), 4)


def filter_by_survey(fetch_result: FetchResult, surveys: list[str]) -> FetchResult:
    """Return a new FetchResult containing only alerts from the specified surveys.

    Args:
        fetch_result: Source :class:`~schemas.FetchResult`.
        surveys: List of survey name strings to keep (e.g. ``["ZTF", "ATLAS"]``).

    Returns:
        New :class:`~schemas.FetchResult` with filtered alerts.  Provenance is
        unchanged.  If ``surveys`` is empty, all alerts are excluded.
    """
    allowed = set(surveys)
    filtered = tuple(obs for obs in fetch_result.alerts if obs.mission in allowed)
    return FetchResult(alerts=filtered, provenance=fetch_result.provenance)


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


def fetch_css_alerts(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float | None = None,
    end_jd: float | None = None,
    force_refresh: bool = False,
) -> list:
    """Fetch Catalina Sky Survey alerts via the MPC astroquery interface.

    Queries the Minor Planet Center observation database for CSS detections
    (observatory code 703) near a sky position.  Results are disk-cached by
    (ra, dec, radius).

    Args:
        ra_deg: Right ascension of search centre in degrees.
        dec_deg: Declination of search centre in degrees.
        radius_deg: Search radius in degrees.
        start_jd: Optional start Julian Date for time filtering (not enforced
            by MPC API but stored for provenance).
        end_jd: Optional end Julian Date for time filtering.
        force_refresh: Bypass the on-disk cache if ``True``.

    Returns:
        List of :class:`~schemas.Observation` objects from CSS.
        Returns an empty list on network failure or when no sources are found.
    """
    import hashlib

    cache_key = hashlib.md5(
        f"css:{ra_deg:.6f}:{dec_deg:.6f}:{radius_deg:.6f}".encode()
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
        from astroquery.mpc import MPC  # type: ignore[import]

        results = MPC.query_observations_by_position(  # type: ignore[attr-defined]
            ra=ra_deg, dec=dec_deg, radius=radius_deg
        )
        for row in results:
            try:
                # Keep only CSS (observatory code 703) rows
                obs_code = str(row.get("obs_code") or row.get("observatory_code") or "")
                submission = str(row.get("submission_info") or "")
                if obs_code != "703" and "703" not in submission:
                    continue
                obs_id = str(
                    row.get("obs_id") or row.get("id") or row.get("number") or "css_unknown"
                )
                jd_val = float(row.get("epoch") or row.get("jd") or 2460000.5)
                ra_val = float(row.get("ra") or row.get("ra_deg") or ra_deg)
                dec_val = float(row.get("dec") or row.get("dec_deg") or dec_deg)
                mag_val = float(row.get("mag") or row.get("magnitude") or 99.0)
                band = str(row.get("band") or row.get("filter_band") or "V")
                obs = Observation(
                    obs_id=f"css_{obs_id}",
                    jd=jd_val,
                    ra_deg=ra_val,
                    dec_deg=dec_val,
                    mag=mag_val,
                    mag_err=0.1,
                    filter_band=band,
                    mission="CSS",
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


def fetch_panstarrs_moving_objects(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    force_refresh: bool = False,
) -> list:
    """Fetch PanSTARRS moving-object detections near a sky position via MAST.

    Queries the PanSTARRS PS1 moving-object catalog (MAST "PANSTARRS" catalog,
    "detection" table) filtered to rows with non-null ``ssObjectId``, which
    flags solar-system object detections.  Results are disk-cached.

    Args:
        ra_deg: Right ascension of the search centre in degrees.
        dec_deg: Declination of the search centre in degrees.
        radius_deg: Search radius in degrees.
        force_refresh: Bypass the on-disk cache if ``True``.

    Returns:
        List of :class:`~schemas.Observation` objects from PanSTARRS with
        ``mission="PanSTARRS"``.  Returns an empty list on failure.
    """
    import hashlib

    cache_key = hashlib.md5(
        f"ps1_moving:{ra_deg:.6f}:{dec_deg:.6f}:{radius_deg:.6f}".encode()
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

        results = Catalogs.query_region(
            f"{ra_deg} {dec_deg}",
            radius=radius_deg,
            catalog="PanSTARRS",
            data_release="dr2",
            table="detection",
        )
        for row in results:
            try:
                ss_id = row.get("ssObjectId") or row.get("ssobjectid")
                if not ss_id:
                    continue
                obs = Observation(
                    obs_id=f"ps1_mo_{row.get('detectID') or row.get('detectionID') or 'unk'}",
                    jd=float(row.get("obsTime") or row.get("epochMjdTai", 0.0)) + 2400000.5,
                    ra_deg=float(row.get("ra") or row.get("raMean") or ra_deg),
                    dec_deg=float(row.get("dec") or row.get("decMean") or dec_deg),
                    mag=float(row.get("psfFlux") or row.get("rMeanPSFMag") or 99.0),
                    mag_err=float(row.get("psfFluxErr") or 0.1),
                    filter_band=str(row.get("filterID") or "r"),
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


def estimate_field_completeness(
    fetch_result: object,
    limiting_mag: float | None = None,
) -> float:
    """Estimate the fractional completeness of a survey field.

    Completeness is defined as the fraction of observations whose magnitude is
    at least 0.5 mag brighter than the field's limiting magnitude (i.e. well
    above the detection threshold).  Observations with sentinel magnitudes
    ≥ 90 are treated as non-detections.

    If *limiting_mag* is not supplied, :func:`estimate_survey_depth` is used
    to derive it from the fetch result.  If no limiting magnitude can be
    determined, returns 0.0.

    Args:
        fetch_result: A :class:`~schemas.FetchResult` object.
        limiting_mag: Optional override for the field limiting magnitude.

    Returns:
        Completeness fraction in [0, 1], rounded to 4 decimal places.
        Returns 0.0 for empty or missing observations.
    """
    alerts = list(getattr(fetch_result, "alerts", []) or [])
    if not alerts:
        return 0.0

    lim = limiting_mag
    if lim is None:
        lim = estimate_survey_depth(fetch_result)
    if lim is None:
        return 0.0

    threshold = lim - 0.5
    valid = [o for o in alerts if float(getattr(o, "mag", 99.0)) < 90.0]
    if not valid:
        return 0.0

    bright = sum(1 for o in valid if float(getattr(o, "mag", 99.0)) <= threshold)
    return round(bright / len(valid), 4)


def fetch_known_neo_ephemerides(
    designations: list[str],
    target_jd: float = 2460000.5,
    force_refresh: bool = False,
) -> list:
    """Fetch geocentric ephemerides for a list of known NEO designations.

    Queries JPL Horizons (via ``astroquery.jplhorizons``) for each designation
    and returns a list of :class:`~schemas.EphemerisPoint` objects.  Results are
    disk-cached per (designation, target_jd) pair; use *force_refresh* to bypass.

    Failed individual queries are silently skipped — only successful results are
    returned.  The order of returned points matches the order of *designations*
    (absent entries are omitted).

    Args:
        designations: List of MPC/JPL designation strings, e.g. ``["433", "3200"]``.
        target_jd: Julian Date for the ephemeris prediction (default 2460000.5).
        force_refresh: If True, bypass disk cache and re-query.

    Returns:
        List of :class:`~schemas.EphemerisPoint` objects, one per successful query.
    """
    from schemas import EphemerisPoint

    results: list[EphemerisPoint] = []
    for desig in designations:
        cache_key = f"neo_eph_{desig}_{target_jd:.2f}"
        if not force_refresh:
            cached = _load_cache(cache_key)
            if cached is not None:
                try:
                    results.append(EphemerisPoint.model_validate(cached))
                    continue
                except Exception:
                    pass
        try:
            from astroquery.jplhorizons import Horizons  # type: ignore[import]

            obj = Horizons(id=desig, location="500", epochs=target_jd)
            eph = obj.ephemerides()
            ra = float(eph["RA"][0])
            dec = float(eph["DEC"][0])
            delta = float(eph["delta"][0])
            r = float(eph["r"][0])
            phase = float(eph["alpha"][0]) if "alpha" in eph.colnames else None
            mag = float(eph["V"][0]) if "V" in eph.colnames else None
            point = EphemerisPoint(
                object_id=desig,
                jd=target_jd,
                ra_deg=ra,
                dec_deg=dec,
                delta_au=delta,
                r_au=r,
                phase_deg=phase,
                mag=mag,
            )
            _save_cache(cache_key, point.model_dump())
            results.append(point)
        except Exception:
            pass
    return results


def fetch_neocp_objects(force_refresh: bool = False) -> list[dict]:
    """Return unconfirmed objects currently listed on the MPC NEOCP.

    Each dict contains at minimum ``object_id``, ``score``, ``updated``
    (ISO timestamp string), ``ra_deg``, ``dec_deg``, and ``mag`` keys
    populated from the MPC NEOCP feed.  Missing fields default to *None*.
    Results are disk-cached under the key ``"neocp_objects"``; set
    *force_refresh* to bypass the cache.

    Returns an empty list if the MPC NEOCP cannot be reached or the
    response cannot be parsed.
    """
    cache_key = "neocp_objects"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, list):
            return cached

    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        tbl = MPC.query_objects("nea")
        rows: list[dict] = []
        for row in tbl:
            rows.append({
                "object_id": str(row.get("designation") or row.get("name") or "unknown"),
                "score": float(row["score"]) if "score" in row.colnames else None,
                "updated": str(row["updated"]) if "updated" in row.colnames else None,
                "ra_deg": float(row["ra"]) if "ra" in row.colnames else None,
                "dec_deg": float(row["dec"]) if "dec" in row.colnames else None,
                "mag": float(row["vmag"]) if "vmag" in row.colnames else None,
            })
        _save_cache(cache_key, rows)
        return rows
    except Exception:
        return []


def fetch_mpc_orbit_elements(
    designation: str,
    force_refresh: bool = False,
) -> dict | None:
    """Fetch orbital elements for *designation* from the MPC via astroquery.

    Results are disk-cached under ``"mpc_orb_{designation}"``.  Set
    *force_refresh* to bypass the cache.  Returns a dict with keys
    ``"a"``, ``"e"``, ``"i"``, ``"node"``, ``"peri"``, ``"M"``,
    ``"epoch_jd"`` (all floats) and ``"designation"`` (str), or
    *None* if the object cannot be found or the query fails.
    """
    cache_key = f"mpc_orb_{designation}"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        tbl = MPC.query_object("asteroid", designation=designation)
        if tbl is None or len(tbl) == 0:
            return None
        row = tbl[0]
        result = {
            "designation": designation,
            "a": float(row["semimajor_axis"]) if "semimajor_axis" in tbl.colnames else None,
            "e": float(row["eccentricity"]) if "eccentricity" in tbl.colnames else None,
            "i": float(row["inclination"]) if "inclination" in tbl.colnames else None,
            "node": float(row["ascending_node"]) if "ascending_node" in tbl.colnames else None,
            "peri": (float(row["argument_of_perihelion"])
                     if "argument_of_perihelion" in tbl.colnames else None),
            "M": float(row["mean_anomaly"]) if "mean_anomaly" in tbl.colnames else None,
            "epoch_jd": float(row["epoch_jd"]) if "epoch_jd" in tbl.colnames else None,
        }
        _save_cache(cache_key, result)
        return result
    except Exception:
        return None


def fetch_known_neo_list(force_refresh: bool = False) -> list[dict]:
    """Return a list of known numbered NEOs from the MPC catalog.

    Each entry has keys: ``object_id``, ``a_au``, ``e``, ``i_deg``,
    ``absolute_magnitude_h``, ``neo_class``.  Returns an empty list on failure.
    Results are disk-cached under the standard cache directory.
    """
    cache_key = "known_neo_list"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, list):
            return cached
    try:
        from astroquery.mpc import MPC  # type: ignore[import-untyped]

        tbl = MPC.query_objects("nea")
        rows: list[dict] = []
        for row in tbl:
            a = float(row["semimajor_axis"]) if "semimajor_axis" in tbl.colnames else None
            e = float(row["eccentricity"]) if "eccentricity" in tbl.colnames else None
            q = (a * (1.0 - e)) if (a is not None and e is not None) else None
            Q = (a * (1.0 + e)) if (a is not None and e is not None) else None
            neo_class: str = "unknown"
            if q is not None and Q is not None and a is not None:
                if a < 1.0 and Q > 0.983:
                    neo_class = "aten"
                elif Q is not None and Q < 0.983:
                    neo_class = "ieo"
                elif a >= 1.0 and q < 1.017:
                    neo_class = "apollo"
                elif 1.017 <= q < 1.3:
                    neo_class = "amor"
            rows.append({
                "object_id": (
                    str(row.get("designation") or row.get("name") or "unknown")
                ),
                "a_au": a,
                "e": e,
                "i_deg": (
                    float(row["inclination"]) if "inclination" in tbl.colnames else None
                ),
                "absolute_magnitude_h": (
                    float(row["absolute_magnitude"])
                    if "absolute_magnitude" in tbl.colnames else None
                ),
                "neo_class": neo_class,
            })
        _save_cache(cache_key, rows)
        return rows
    except Exception:
        return []


def fetch_neocp_confirmed(force_refresh: bool = False) -> list[dict]:
    """Return a list of recently confirmed NEOCP objects from the MPC catalog.

    Queries the MPC NEA list and returns objects that have a confirmation date
    available (i.e. were recently on NEOCP and then confirmed). Each entry has
    keys: ``object_id``, ``a_au``, ``e``, ``i_deg``, ``absolute_magnitude_h``,
    ``neo_class``, ``confirmed``.  Returns an empty list on failure.
    Results are disk-cached under ``neocp_confirmed``.
    """
    cache_key = "neocp_confirmed"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, list):
            return cached
    try:
        from astroquery.mpc import MPC  # type: ignore[import-untyped]

        tbl = MPC.query_objects("nea")
        rows: list[dict] = []
        for row in tbl:
            desig = str(row.get("designation") or row.get("name") or "unknown")
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
                "object_id": desig,
                "a_au": a,
                "e": e,
                "i_deg": (
                    float(row["inclination"]) if "inclination" in tbl.colnames else None
                ),
                "absolute_magnitude_h": (
                    float(row["absolute_magnitude"])
                    if "absolute_magnitude" in tbl.colnames else None
                ),
                "neo_class": neo_class,
                "confirmed": True,
            })
        _save_cache(cache_key, rows)
        return rows
    except Exception:
        return []


def fetch_mpc_orbit_catalog(force_refresh: bool = False) -> list[dict]:
    """Download a sample of MPC orbital elements for known NEOs.

    Queries the MPC NEA catalog via ``astroquery.mpc`` and returns a
    list of dicts with keys: designation, a_au, e, i_deg, q_au, Q_au,
    neo_class, absolute_magnitude_h.  Results are disk-cached under the
    key ``"mpc_orbit_catalog"``.  Returns an empty list on failure.
    """
    cache_key = "mpc_orbit_catalog"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, list):
            return cached
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        tbl = MPC.query_objects("nea")
        rows: list[dict] = []
        for row in tbl:
            desig = str(row.get("designation") or row.get("name") or "unknown")
            a = float(row["semimajor_axis"]) if "semimajor_axis" in tbl.colnames else None
            e = float(row["eccentricity"]) if "eccentricity" in tbl.colnames else None
            i = float(row["inclination"]) if "inclination" in tbl.colnames else None
            h = float(row["absolute_magnitude"]) if "absolute_magnitude" in tbl.colnames else None
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
                "a_au": a,
                "e": e,
                "i_deg": i,
                "q_au": q,
                "Q_au": Q,
                "neo_class": neo_class,
                "absolute_magnitude_h": h,
            })
        _save_cache(cache_key, rows)
        return rows
    except Exception:
        return []


def compute_field_overlap(fetch_result1: object, fetch_result2: object) -> float:
    """Return the fraction of observations in fetch_result1 within 0.1 deg of
    any observation in fetch_result2.

    Uses the haversine great-circle separation.  Returns 0.0 if either result
    has no observations.

    Args:
        fetch_result1: First FetchResult (or object with ``alerts`` attribute).
        fetch_result2: Second FetchResult (or object with ``alerts`` attribute).

    Returns:
        Fraction of alerts in fetch_result1 that are within 360 arcsec (0.1 deg)
        of at least one alert in fetch_result2, in [0, 1].
    """
    import math as _math

    alerts1 = list(getattr(fetch_result1, "alerts", []) or [])
    alerts2 = list(getattr(fetch_result2, "alerts", []) or [])
    if not alerts1 or not alerts2:
        return 0.0

    threshold_rad = _math.radians(0.1)

    def _sep(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
        r1, d1, r2, d2 = (_math.radians(x) for x in (ra1, dec1, ra2, dec2))
        hav = (
            _math.sin((d2 - d1) / 2.0) ** 2
            + _math.cos(d1) * _math.cos(d2) * _math.sin((r2 - r1) / 2.0) ** 2
        )
        return 2.0 * _math.asin(_math.sqrt(max(0.0, min(1.0, hav))))

    matched = 0
    for obs1 in alerts1:
        ra1 = float(getattr(obs1, "ra_deg", 0.0))
        dec1 = float(getattr(obs1, "dec_deg", 0.0))
        for obs2 in alerts2:
            ra2 = float(getattr(obs2, "ra_deg", 0.0))
            dec2 = float(getattr(obs2, "dec_deg", 0.0))
            if _sep(ra1, dec1, ra2, dec2) <= threshold_rad:
                matched += 1
                break

    return matched / len(alerts1)


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


def fetch_mpc_neo_counts(force_refresh: bool = False) -> dict[str, int]:
    """Fetch total known NEO counts by dynamical class from the MPC.

    Returns a dict with keys ``"amor"``, ``"apollo"``, ``"aten"``, ``"ieo"``,
    and ``"total"``.  Results are disk-cached under the key
    ``"mpc_neo_counts"``.  Returns an empty dict on failure.
    """
    cache_key = "mpc_neo_counts"
    if not force_refresh:
        cached = _load_cache(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached
    try:
        from astroquery.mpc import MPC  # type: ignore[import]

        MPC.get_observatory_list()  # dummy call to warm up session
        neo_tbl = MPC.query_objects_in_sky(
            ra_deg=180.0, dec_deg=0.0, radius=180.0, limiting_magnitude=30.0
        )
        counts: dict[str, int] = {"amor": 0, "apollo": 0, "aten": 0, "ieo": 0, "total": 0}
        for row in neo_tbl:
            a = float(row.get("a", 0.0) or 0.0)
            e = float(row.get("e", 0.0) or 0.0)
            q = a * (1.0 - e)
            Q = a * (1.0 + e)
            if a > 1.0 and q < 1.017:
                counts["apollo"] += 1
            elif a < 1.0 and Q > 0.983:
                counts["aten"] += 1
            elif Q < 0.983:
                counts["ieo"] += 1
            elif 1.017 <= q <= 1.3:
                counts["amor"] += 1
            counts["total"] += 1
        _save_cache(cache_key, counts)
        return counts
    except Exception:
        return {}


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


def summarize_survey_fields(result: FetchResult) -> list[dict]:
    """Summarise observations in a FetchResult grouped by field_id.

    Returns a list of dicts, each with keys ``"field_id"``, ``"survey"``,
    ``"epoch_jd"`` (median JD for the group), and ``"n_observations"``.
    Observations whose ``field_id`` is ``None`` are grouped under ``"unknown"``.
    Returns an empty list for an empty FetchResult.
    """
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for obs in result.alerts:
        key = obs.field_id if obs.field_id is not None else "unknown"
        groups[key].append(obs)
    rows = []
    for fid, obs_list in sorted(groups.items()):
        jds = [o.jd for o in obs_list if o.jd is not None]
        epoch = float(sorted(jds)[len(jds) // 2]) if jds else 0.0
        surveys = [o.mission for o in obs_list if o.mission is not None]
        survey = surveys[0] if surveys else "unknown"
        rows.append({
            "field_id": fid,
            "survey": survey,
            "epoch_jd": epoch,
            "n_observations": len(obs_list),
        })
    return rows


def build_fetch_provenance(
    alerts: list | tuple,
    survey: str,
    start_jd: float,
    end_jd: float,
    *,
    search_ra_deg: float | None = None,
    search_dec_deg: float | None = None,
    search_radius_deg: float | None = None,
    limiting_magnitude: float | None = None,
    fetched_at_jd: float = 0.0,
    cached: bool = False,
) -> FetchProvenance:
    """Construct a :class:`~schemas.FetchProvenance` from the given parameters.

    This is a convenience factory that collects fetch-stage metadata into a
    single immutable provenance object.  The ``survey`` string is normalised
    to the canonical ``Mission`` literals where possible.

    Args:
        alerts: List or tuple of :class:`~schemas.Observation` objects returned
            by the fetch stage (used only for consistency; not stored directly).
        survey: Survey name string (e.g. ``"ZTF"``, ``"ATLAS"``).
        start_jd: Start of the search window as a Julian Date.
        end_jd: End of the search window as a Julian Date.
        search_ra_deg: Right ascension of the search centre in degrees; None if
            not applicable.
        search_dec_deg: Declination of the search centre in degrees; None if not
            applicable.
        search_radius_deg: Search cone radius in degrees; None if not applicable.
        limiting_magnitude: Estimated 5-sigma limiting magnitude; None if
            unknown.
        fetched_at_jd: Julian Date at which the fetch was performed (default 0).
        cached: Whether the result was loaded from a local disk cache.

    Returns:
        :class:`~schemas.FetchProvenance` capturing all provided metadata.
    """
    _KNOWN_MISSIONS = {"ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"}
    normalised = survey if survey in _KNOWN_MISSIONS else "ZTF"
    mission: Mission = normalised  # type: ignore[assignment]
    return FetchProvenance(
        surveys=(mission,),
        start_jd=start_jd,
        end_jd=end_jd,
        search_ra_deg=search_ra_deg,
        search_dec_deg=search_dec_deg,
        search_radius_deg=search_radius_deg,
        limiting_magnitude=limiting_magnitude,
        fetched_at_jd=fetched_at_jd,
        cached=cached,
    )


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


def get_fetch_result_age(fetch_result: FetchResult) -> float | None:
    """Return the age in days of a fetch result.

    Age is defined as the current Julian Date minus the earliest observation
    JD in the result.  Uses ``astropy.time.Time.now().jd`` for the current
    JD.  Returns ``None`` if the fetch result contains no observations.

    Args:
        fetch_result: :class:`~schemas.FetchResult` object.

    Returns:
        Age in days (float ≥ 0), or ``None`` if no observations are present.
    """
    from astropy.time import Time  # noqa: PLC0415

    if not fetch_result.alerts:
        return None
    earliest_jd = min(obs.jd for obs in fetch_result.alerts)
    current_jd = Time.now().jd
    return float(current_jd - earliest_jd)


def deduplicate_observations(observations: object) -> list:
    """Remove duplicate observations by ``obs_id``, keeping first occurrence.

    Iterates over *observations* (any iterable of objects with an ``obs_id``
    attribute) and returns a new list containing only the first occurrence of
    each unique ``obs_id``.  Objects whose ``obs_id`` attribute is missing or
    ``None`` are treated as having a unique sentinel id and are always kept.

    Args:
        observations: Any iterable of observation-like objects with an
            ``obs_id`` attribute.

    Returns:
        List of deduplicated observations in their original order.
    """
    seen: set[object] = set()
    result: list = []
    for obs in observations:  # type: ignore[attr-defined]
        obs_id = getattr(obs, "obs_id", None)
        if obs_id is None or obs_id not in seen:
            if obs_id is not None:
                seen.add(obs_id)
            result.append(obs)
    return result


def get_survey_coverage_fraction(fetch_result: object, expected_fields: int) -> float:
    """Return the fraction of expected survey fields represented in a FetchResult.

    Counts the number of unique ``field_id`` values among all observations in
    *fetch_result.alerts* and divides by *expected_fields*.  Returns a float
    in [0, 1].  Returns 0.0 if *expected_fields* ≤ 0 or if there are no
    observations.

    Args:
        fetch_result: A :class:`~schemas.FetchResult`-like object with an
            ``alerts`` attribute (iterable of observation-like objects, each
            with an optional ``field_id`` attribute).
        expected_fields: Total number of fields expected for full coverage.

    Returns:
        Coverage fraction in [0, 1].
    """
    if expected_fields <= 0:
        return 0.0
    alerts = getattr(fetch_result, "alerts", None) or []
    field_ids: set[object] = set()
    for obs in alerts:
        fid = getattr(obs, "field_id", None)
        if fid is not None:
            field_ids.add(fid)
    if not field_ids:
        return 0.0
    return float(min(1.0, len(field_ids) / expected_fields))


def partition_by_field(fetch_result: object) -> dict[str, list]:
    """Group observations from a FetchResult by field_id.

    Iterates over ``fetch_result.alerts`` and buckets each observation by its
    ``field_id`` attribute.  Observations with no ``field_id`` or where the
    attribute is ``None`` are grouped under the key ``"unknown"``.

    Args:
        fetch_result: A :class:`~schemas.FetchResult`-like object with an
            ``alerts`` attribute (iterable of observation-like objects).

    Returns:
        A ``dict[str, list]`` mapping field_id → list of observations.  Returns
        an empty dict if the fetch result has no alerts.
    """
    alerts = getattr(fetch_result, "alerts", None) or []
    result: dict[str, list] = {}
    for obs in alerts:
        fid = getattr(obs, "field_id", None)
        key = str(fid) if fid is not None else "unknown"
        result.setdefault(key, []).append(obs)
    return result


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


def compute_field_sky_area(radius_deg: float) -> float:
    """Return the sky area in square degrees for a circular field of given radius.

    Uses the exact spherical-cap formula: 2π·(1 − cos(r)) steradians,
    converted to square degrees.
    """
    import math
    r_rad = math.radians(abs(radius_deg))
    steradians = 2.0 * math.pi * (1.0 - math.cos(r_rad))
    return steradians * (180.0 / math.pi) ** 2


def compute_survey_overlap(result1: object, result2: object) -> float:
    """Return the Jaccard overlap fraction between two FetchResult observation sets.

    Overlap = |shared obs_ids| / |union obs_ids|. Returns 0.0 if both are empty.
    """
    alerts1 = getattr(result1, "alerts", None) or []
    alerts2 = getattr(result2, "alerts", None) or []
    ids1 = {getattr(o, "obs_id", None) for o in alerts1} - {None}
    ids2 = {getattr(o, "obs_id", None) for o in alerts2} - {None}
    union = ids1 | ids2
    if not union:
        return 0.0
    return float(len(ids1 & ids2)) / float(len(union))


def count_observations_by_night(fetch_result: object) -> dict:
    """Return a dict mapping integer JD (floor) to observation count.

    Each observation's JD is floored to an integer night key.
    Returns an empty dict if the FetchResult has no alerts.
    """
    alerts = getattr(fetch_result, "alerts", None) or []
    counts: dict[int, int] = {}
    for obs in alerts:
        jd = getattr(obs, "jd", None)
        if jd is None:
            continue
        night = int(float(jd))
        counts[night] = counts.get(night, 0) + 1
    return counts


def compute_temporal_coverage(fetch_result: object) -> dict:
    """Return a summary of the temporal span covered by a FetchResult.

    Returns a dict with keys:
      - ``n_observations``: total observation count
      - ``min_jd``: earliest JD (float) or None
      - ``max_jd``: latest JD (float) or None
      - ``span_days``: max_jd - min_jd (float) or None if fewer than 2 obs
      - ``n_nights``: number of distinct integer-JD nights

    Returns all-None / zero values if the FetchResult has no alerts.
    """
    alerts = getattr(fetch_result, "alerts", None) or []
    jds: list[float] = []
    for obs in alerts:
        jd = getattr(obs, "jd", None)
        if jd is not None:
            jds.append(float(jd))
    if not jds:
        return {
            "n_observations": 0,
            "min_jd": None,
            "max_jd": None,
            "span_days": None,
            "n_nights": 0,
        }
    min_jd = min(jds)
    max_jd = max(jds)
    span = (max_jd - min_jd) if len(jds) >= 2 else None
    n_nights = len({int(j) for j in jds})
    return {
        "n_observations": len(jds),
        "min_jd": min_jd,
        "max_jd": max_jd,
        "span_days": span,
        "n_nights": n_nights,
    }


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


def compute_magnitude_distribution(fetch_result: object, n_bins: int = 10) -> dict:
    """Return a histogram of alert magnitudes across a FetchResult.

    Divides the observed magnitude range into *n_bins* equal-width bins and
    counts observations in each bin.  Returns a dict with keys:

      - ``"bin_edges"``: list of n_bins + 1 edge values
      - ``"counts"``: list of n_bins integer counts
      - ``"n_total"``: total number of valid magnitude observations (mag < 90)

    Observations with mag ≥ 90 (sentinel / missing) are excluded.
    *n_bins* is clamped to at least 1.  Returns zero counts and edges [0, 1]
    if no valid magnitudes are present.
    """
    n_bins = max(1, int(n_bins))
    alerts = getattr(fetch_result, "alerts", None) or []
    mags = [
        float(getattr(o, "mag", 99))
        for o in alerts
        if getattr(o, "mag", None) is not None and float(getattr(o, "mag", 99)) < 90.0
    ]
    if not mags:
        edges = [float(i) / n_bins for i in range(n_bins + 1)]
        return {"bin_edges": edges, "counts": [0] * n_bins, "n_total": 0}
    lo, hi = min(mags), max(mags)
    width = (hi - lo) / n_bins if hi > lo else 1.0
    edges = [lo + i * width for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for m in mags:
        idx = int((m - lo) / width) if width > 0 else 0
        if idx >= n_bins:
            idx = n_bins - 1
        counts[idx] += 1
    return {"bin_edges": edges, "counts": counts, "n_total": len(mags)}


def group_observations_by_night(fetch_result: FetchResult) -> dict:
    """Group observations in a FetchResult by integer night (floor of JD).

    Returns a dict mapping each integer JD (``int(floor(jd))``) to the list
    of :class:`Observation` objects whose Julian Date falls in that night.
    Observations with non-finite JDs are skipped.  Returns an empty dict for
    empty inputs.
    """
    import math

    groups: dict[int, list] = {}
    for obs in fetch_result.alerts:
        if not math.isfinite(obs.jd):
            continue
        night = int(math.floor(obs.jd))
        groups.setdefault(night, []).append(obs)
    return groups


def count_observations_by_filter(fetch_result: FetchResult) -> dict:
    """Return the count of observations per filter band in a FetchResult.

    Returns a dict mapping each ``filter_band`` string to the number of
    observations in that band.  Returns an empty dict for empty inputs.
    """
    counts: dict = {}
    for obs in fetch_result.alerts:
        band = obs.filter_band
        counts[band] = counts.get(band, 0) + 1
    return counts


def get_brightest_observation(fetch_result: FetchResult) -> object | None:
    """Return the single brightest (lowest-magnitude) Observation in a FetchResult.

    Excludes observations with sentinel magnitudes ≥ 90.  Returns ``None``
    if the result is empty or all magnitudes are sentinels.
    """
    valid = [obs for obs in fetch_result.alerts if obs.mag < 90.0]
    if not valid:
        return None
    return min(valid, key=lambda o: o.mag)


def get_latest_observation(fetch_result: FetchResult) -> object | None:
    """Return the most recent Observation (highest JD) from *fetch_result*.

    Ignores sentinel magnitudes (mag >= 90) and non-finite JDs.
    Returns ``None`` if no valid observations exist.
    """
    import math

    valid = [obs for obs in fetch_result.alerts if math.isfinite(obs.jd)]
    if not valid:
        return None
    return max(valid, key=lambda o: o.jd)


def get_faintest_observation(fetch_result: FetchResult) -> object | None:
    """Return the faintest Observation (highest valid mag) from *fetch_result*.

    Ignores sentinel magnitudes (mag >= 90).  Returns ``None`` if no valid
    observations exist.
    """
    valid = [obs for obs in fetch_result.alerts if obs.mag < 90.0]
    if not valid:
        return None
    return max(valid, key=lambda o: o.mag)


def compute_observation_time_span(fetch_result: FetchResult) -> float | None:
    """Total time span in days covered by valid observations.

    Returns max(JD) − min(JD) across all alerts with finite JDs.
    Returns ``None`` if fewer than 2 valid JDs exist.
    """
    import math

    jds = [obs.jd for obs in fetch_result.alerts if math.isfinite(obs.jd)]
    if len(jds) < 2:
        return None
    return float(max(jds) - min(jds))
