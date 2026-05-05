"""Fetch stage — retrieve alerts from ZTF, ATLAS, MPC, and JPL Horizons."""

from __future__ import annotations

import json
import time
from pathlib import Path

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


def _load_cache(key: str) -> list[dict] | None:
    p = _cache_path(key)
    if p.exists():
        with p.open() as f:
            return json.load(f)  # type: ignore[no-any-return]
    return None


def _save_cache(key: str, data: list[dict]) -> None:
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
) -> list[Observation]:
    """Query ZTF alert stream via IRSA.  Requires ``ztfquery`` or requests."""
    import hashlib

    cache_key = hashlib.md5(
        f"ztf_{ra_deg}_{dec_deg}_{radius_deg}_{start_jd}_{end_jd}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key)
    if cached is not None:
        return [Observation(**row) for row in cached]

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
    except ImportError:
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


def _fetch_ztf_irsa_api(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
) -> list[Observation]:
    """Fallback: query IRSA TAP for ZTF source catalog."""
    import requests

    tap_url = "https://irsa.ipac.caltech.edu/TAP/sync"
    adql = (
        f"SELECT candid, ra, dec, jd, magpsf, sigmapsf, fid, rb, drb "
        f"FROM ztf.ztf_current_meta_sci "
        f"WHERE CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra_deg}, {dec_deg}, {radius_deg})) = 1 "
        f"AND jd >= {start_jd} AND jd <= {end_jd}"
    )
    resp = requests.get(tap_url, params={"QUERY": adql, "FORMAT": "json"}, timeout=60)
    resp.raise_for_status()
    rows = resp.json().get("data", [])
    cols = resp.json().get("metadata", [])
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
) -> list[Observation]:
    """Query ATLAS Forced Photometry Server for a sky position."""
    import hashlib

    import requests

    cache_key = hashlib.md5(
        f"atlas_{ra_deg}_{dec_deg}_{radius_deg}_{start_jd}_{end_jd}".encode()
    ).hexdigest()
    cached = _load_cache(cache_key)
    if cached is not None:
        return [Observation(**row) for row in cached]

    base = "https://fallingstar-data.com/forcedphot"
    headers: dict[str, str] = {}
    if atlas_token:
        headers["Authorization"] = f"Token {atlas_token}"

    payload = {
        "ra": ra_deg,
        "dec": dec_deg,
        "mjd_min": start_jd - 2400000.5,
        "mjd_max": end_jd - 2400000.5,
        "radius": radius_deg * 3600,  # arcsec
        "use_reduced": False,
    }
    resp = requests.post(f"{base}/queue/", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    task_url = resp.json()["url"]

    # Poll for completion
    for _ in range(60):
        time.sleep(5)
        poll = requests.get(task_url, headers=headers, timeout=30)
        poll.raise_for_status()
        if poll.json().get("finishtimestamp"):
            break

    result_url = poll.json().get("result_url", "")
    if not result_url:
        return []

    data_resp = requests.get(result_url, headers=headers, timeout=60)
    data_resp.raise_for_status()
    lines = data_resp.text.strip().split("\n")
    obs = _parse_atlas_photometry(lines)
    _save_cache(cache_key, [o.model_dump() for o in obs])
    return obs


def _parse_atlas_photometry(lines: list[str]) -> list[Observation]:
    if not lines or lines[0].startswith("#"):
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

    from astroquery.mpc import MPC  # type: ignore[import]
    import astropy.units as u
    from astropy.coordinates import SkyCoord

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

    from astroquery.jplhorizons import Horizons  # type: ignore[import]
    from astropy.time import Time

    start_iso = Time(start_jd, format="jd").iso
    end_iso = Time(end_jd, format="jd").iso
    obj = Horizons(id=target, location="500@399", epochs={"start": start_iso, "stop": end_iso, "step": step})
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
) -> FetchResult:
    """Fetch alerts from the requested surveys for a sky position and time range."""
    from astropy.time import Time

    fetched_at_jd = Time.now().jd
    all_alerts: list[Observation] = []

    for survey in surveys:
        if survey == "ZTF":
            all_alerts.extend(fetch_ztf(ra_deg, dec_deg, radius_deg, start_jd, end_jd))
        elif survey == "ATLAS":
            all_alerts.extend(
                fetch_atlas(ra_deg, dec_deg, radius_deg, start_jd, end_jd, atlas_token)
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
