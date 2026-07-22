#!/usr/bin/env python3
"""Build a resumable, leakage-safe MPC discovery-field calibration envelope.

The builder queries the current official MPC List API for the complete NEO
candidate universe in each requested discovery year, deterministically selects
a year-stratified sample, and freezes those exact targets before acquiring any
observation histories.  The current MPC Observations API supplies ADES rows;
only an explicitly marked discovery observation can become a positive event.
The replay cutoff is immediately before that observation, so current catalog
identity never enters historical ranking features.

This script creates positive events only. It deliberately does not relabel
unsearched background fields as null outcomes. Real searched nulls are stored
separately in ``data_selection/calibration/ztf_field_null_outcomes_v1.json``.

Usage::

    UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
      Skills/build_field_ranking_calibration.py \
      --out Logs/pipeline_runs/field_ranking_calibration/mpc_discovery_fields.json \
      --years 2018 2019 2020 2021 2022 2023 2024 \
      --per-year 8 --resume
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from astropy.time import Time

SCHEMA_VERSION = "mpc-discovery-field-calibration-v2"
DEFAULT_YEARS = tuple(range(2018, 2025))
REPLAY_EPSILON_DAYS = 1e-6
MPC_LIST_API = "https://data.minorplanetcenter.net/api/list"
MPC_OBSERVATIONS_API = "https://data.minorplanetcenter.net/api/get-obs"
MPC_LIST_CLASSES = {
    "neos": "neo",
    "atens": "aten",
    "atiras": "atira",
    "apollos": "apollo",
    "amors": "amor",
}


@dataclass(frozen=True)
class MpcApiObservation:
    """Normalized subset of one published ADES observation."""

    obs_id: str
    jd: float
    ra_deg: float
    dec_deg: float
    station: str
    discovery: bool


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(encoded)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _payload_shape(payload: Any) -> str:
    if isinstance(payload, dict):
        return f"object keys={sorted(str(key) for key in payload)[:10]}"
    if isinstance(payload, list):
        return f"list length={len(payload)}"
    return type(payload).__name__


def fetch_mpc_neo_list(
    year: int,
    *,
    list_name: str = "neos",
    timeout_seconds: float = 60.0,
    request_get: Callable[..., Any] = requests.get,
) -> list[dict[str, Any]]:
    """Fetch and normalize the complete MPC NEO list for one discovery year."""
    if year < 1800 or year > datetime.now(UTC).year:
        raise ValueError(f"invalid discovery year: {year}")
    if list_name not in MPC_LIST_CLASSES:
        raise ValueError(f"unsupported MPC NEO list: {list_name}")
    request = {
        "list": list_name,
        "like": f"{year}%",
        "limit": 50_000,
        "offset": 0,
        "order": "ASC",
    }
    response = request_get(MPC_LIST_API, json=request, timeout=timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError(f"MPC returned no NEO list items for {year}")

    normalized: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("MPC NEO list item must be an object")
        designation = str(
            item.get("unpacked_primary_provisional_designation", "")
        ).strip()
        if not designation.startswith(f"{year} "):
            raise ValueError(f"MPC NEO list returned an out-of-year designation: {designation}")
        normalized[designation] = {
            "designation": designation,
            "discovery_year": year,
            "neo_class": MPC_LIST_CLASSES[list_name],
            "permanent_id": (
                str(item["permid"]).strip() if item.get("permid") is not None else None
            ),
            "name": str(item["name"]).strip() if item.get("name") is not None else None,
        }
    return [normalized[key] for key in sorted(normalized)]


def fetch_mpc_observations_api(
    designation: str,
    *,
    timeout_seconds: float = 60.0,
    request_get: Callable[..., Any] = requests.get,
) -> list[MpcApiObservation]:
    """Fetch and validate one complete history from the official MPC API."""
    response = request_get(
        MPC_OBSERVATIONS_API,
        json={"desigs": [designation], "output_format": ["ADES_DF"]},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError(
            "MPC observations API must start with one object result; received "
            f"{_payload_shape(payload)}"
        )
    if any(not isinstance(value, int) or value != 200 for value in payload[1:]):
        raise ValueError("MPC observations API returned invalid trailing status metadata")
    rows = payload[0].get("ADES_DF")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"MPC returned no ADES observations for {designation}")

    normalized: list[MpcApiObservation] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("MPC ADES observation row must be an object")
        obs_time = row.get("obsTime", row.get("obstime"))
        if obs_time is None:
            raise ValueError("MPC ADES observation row has no obsTime")
        jd = float(Time(str(obs_time), format="isot", scale="utc").jd)
        ra_deg = float(row["ra"])
        dec_deg = float(row["dec"])
        if not (
            math.isfinite(jd)
            and math.isfinite(ra_deg)
            and math.isfinite(dec_deg)
            and 0.0 <= ra_deg < 360.0
            and -90.0 <= dec_deg <= 90.0
        ):
            raise ValueError("MPC ADES observation has invalid time or coordinates")
        station = str(row.get("stn", "")).strip()
        if not station:
            raise ValueError("MPC ADES observation row has no station code")
        discovery_raw = row.get("disc", row.get("discovery", ""))
        discovery = discovery_raw is True or str(discovery_raw).strip() == "*"
        identity = (
            f"{designation}|{jd:.9f}|{ra_deg:.9f}|{dec_deg:.9f}|{station}|{index}"
        )
        normalized.append(
            MpcApiObservation(
                obs_id=f"MPC_{_sha256_bytes(identity.encode())[:16]}",
                jd=jd,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                station=station,
                discovery=discovery,
            )
        )
    if not any(observation.discovery for observation in normalized):
        raise ValueError(f"MPC history has no explicit discovery observation for {designation}")
    return normalized


def select_year_candidates(
    candidates_by_year: dict[int, list[dict[str, Any]]],
    *,
    years: Sequence[int] = DEFAULT_YEARS,
    per_year: int | None = 8,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Select a deterministic year-stratified sample from the full API universe."""
    if per_year is not None and per_year < 1:
        raise ValueError("per_year must be at least 1")
    normalized_years = tuple(sorted(set(int(year) for year in years)))
    if not normalized_years:
        raise ValueError("at least one calibration year is required")

    selected: list[dict[str, Any]] = []
    for year in normalized_years:
        candidates = candidates_by_year.get(year)
        required = (
            len(candidates)
            if isinstance(candidates, list) and per_year is None
            else per_year
        )
        if not isinstance(candidates, list) or required is None or len(candidates) < required:
            count = len(candidates) if isinstance(candidates, list) else 0
            raise ValueError(
                f"MPC list has only {count} eligible {year} objects; {required} required"
            )
        if any(candidate.get("discovery_year") != year for candidate in candidates):
            raise ValueError(f"MPC candidate universe contains year drift for {year}")
        unique = {str(candidate["designation"]): candidate for candidate in candidates}
        if len(unique) != len(candidates):
            raise ValueError(f"MPC candidate universe contains duplicate {year} designations")
        ordered = sorted(
            candidates,
            key=lambda row: _sha256_bytes(
                f"{seed}|{year}|{row['designation']}".encode()
            ),
        )
        selected.extend(ordered[:required])
    return selected


def _new_envelope(
    candidates_by_year: dict[int, list[dict[str, Any]]],
    selected: list[dict[str, Any]],
    *,
    years: Sequence[int],
    per_year: int | None,
    seed: int,
    list_name: str,
) -> dict[str, Any]:
    now = _utc_now()
    normalized_universe = [
        candidate
        for year in sorted(candidates_by_year)
        for candidate in sorted(
            candidates_by_year[year], key=lambda row: str(row["designation"])
        )
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": now,
        "updated_at_utc": now,
        "status": "running",
        "source": {
            "provider": "Minor Planet Center",
            "candidate_api": MPC_LIST_API,
            "candidate_list": list_name,
            "observation_api": MPC_OBSERVATIONS_API,
            "observation_format": "ADES_DF",
        },
        "selection": {
            "years": list(years),
            "per_year": per_year,
            "all_per_year": per_year is None,
            "seed": seed,
            "method": "sha256_ordered_year_stratified_mpc_neo_list",
            "evaluated_count": len(normalized_universe),
            "evaluated_by_year": {
                str(year): len(candidates_by_year[year]) for year in sorted(candidates_by_year)
            },
            "candidate_universe_sha256": _canonical_sha256(normalized_universe),
            "selected_count": len(selected),
            "selected": selected,
        },
        "leakage_policy": {
            "label_source": "current MPC-confirmed NEO list",
            "feature_cutoff": "discovery_observation_jd_minus_epsilon",
            "replay_epsilon_days": REPLAY_EPSILON_DAYS,
            "future_catalog_identity_allowed_in_features": False,
        },
        "events": [],
        "query_log": [],
        "summary": {},
    }


def _load_checkpoint(
    out: Path,
    *,
    years: Sequence[int],
    per_year: int | None,
    seed: int,
    list_name: str,
    resume: bool,
) -> dict[str, Any] | None:
    if not out.exists():
        return None
    if not resume:
        raise FileExistsError(f"output already exists; use --resume: {out}")
    payload = json.loads(out.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported checkpoint schema: {out}")
    selection = payload.get("selection", {})
    expected = {
        "years": list(years),
        "per_year": per_year,
        "all_per_year": per_year is None,
        "seed": seed,
    }
    if any(selection.get(key) != value for key, value in expected.items()):
        raise ValueError("selection parameters changed since checkpoint creation")
    if payload.get("source", {}).get("candidate_list") != list_name:
        raise ValueError("MPC candidate list changed since checkpoint creation")
    selected = selection.get("selected")
    if not isinstance(selected, list) or len(selected) != selection.get("selected_count"):
        raise ValueError("checkpoint does not contain its exact selected targets")
    return payload


def _event_from_observations(
    candidate: dict[str, Any], observations: Sequence[Any]
) -> dict[str, Any]:
    if len(observations) < 3:
        raise ValueError("fewer than three published observations")
    ordered = sorted(observations, key=lambda observation: float(observation.jd))
    if any(not math.isfinite(float(observation.jd)) for observation in ordered):
        raise ValueError("observation history contains a non-finite JD")
    discoveries = [
        observation
        for observation in ordered
        if bool(getattr(observation, "discovery", False))
    ]
    if not discoveries:
        raise ValueError("published history has no explicit discovery observation")
    discovery = discoveries[0]
    discovery_year = Time(
        float(discovery.jd), format="jd", scale="utc"
    ).to_datetime(timezone=UTC).year
    expected_year = int(candidate["discovery_year"])
    if discovery_year != expected_year:
        raise ValueError(
            f"MPC discovery year {discovery_year} != selected year {expected_year}"
        )
    night_ids = {int(float(observation.jd) + 0.5) for observation in ordered}
    if len(night_ids) < 2:
        raise ValueError("published history spans fewer than two UTC nights")
    return {
        "event_id": f"mpc-discovery-observation:{candidate['designation']}",
        "designation": candidate["designation"],
        "permanent_id": candidate.get("permanent_id"),
        "neo_class": candidate["neo_class"],
        "label": "later_confirmed_neo_discovery_field",
        "discovery_observation": {
            "obs_id": str(discovery.obs_id),
            "jd": float(discovery.jd),
            "ra_deg": float(discovery.ra_deg),
            "dec_deg": float(discovery.dec_deg),
            "station": str(discovery.station),
        },
        "earliest_published_observation_jd": float(ordered[0].jd),
        "replay_cutoff_jd": float(discovery.jd) - REPLAY_EPSILON_DAYS,
        "published_observation_count": len(ordered),
        "published_night_count": len(night_ids),
        "discovery_year": expected_year,
    }


def _fetch_candidate_universe(
    years: Sequence[int],
    *,
    retries: int,
    query_delay_seconds: float,
    fetcher: Callable[[int], list[dict[str, Any]]],
) -> dict[int, list[dict[str, Any]]]:
    universe: dict[int, list[dict[str, Any]]] = {}
    for index, year in enumerate(years, start=1):
        print(f"[calibration] universe {index}/{len(years)} {year}: querying MPC", flush=True)
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                universe[year] = fetcher(year)
                print(
                    f"[calibration] universe {index}/{len(years)} {year}: "
                    f"{len(universe[year])} NEOs",
                    flush=True,
                )
                break
            except Exception as exc:
                last_error = exc
                print(
                    f"[calibration] universe {year}: attempt {attempt + 1}/"
                    f"{retries + 1} failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                if attempt < retries and query_delay_seconds:
                    time.sleep(query_delay_seconds)
        else:
            raise RuntimeError(
                f"MPC candidate-universe acquisition failed for {year}"
            ) from last_error
        if index < len(years) and query_delay_seconds:
            time.sleep(query_delay_seconds)
    return universe


def build_calibration_events(
    out: Path,
    *,
    years: Sequence[int] = DEFAULT_YEARS,
    per_year: int | None = 8,
    seed: int = 42,
    list_name: str = "neos",
    resume: bool = False,
    retries: int = 2,
    query_delay_seconds: float = 1.0,
    list_fetcher: Callable[[int], list[dict[str, Any]]] | None = None,
    observation_fetcher: Callable[[str], Sequence[Any]] | None = None,
) -> dict[str, Any]:
    """Freeze exact targets, acquire histories, and checkpoint every event."""
    if retries < 0 or query_delay_seconds < 0:
        raise ValueError("retries and query_delay_seconds must be non-negative")
    if list_name not in MPC_LIST_CLASSES:
        raise ValueError(f"unsupported MPC NEO list: {list_name}")
    normalized_years = tuple(sorted(set(int(year) for year in years)))
    if not normalized_years:
        raise ValueError("at least one calibration year is required")
    envelope = _load_checkpoint(
        out,
        years=normalized_years,
        per_year=per_year,
        seed=seed,
        list_name=list_name,
        resume=resume,
    )
    if envelope is None:
        universe = _fetch_candidate_universe(
            normalized_years,
            retries=retries,
            query_delay_seconds=query_delay_seconds,
            fetcher=list_fetcher
            or (lambda year: fetch_mpc_neo_list(year, list_name=list_name)),
        )
        selected = select_year_candidates(
            universe,
            years=normalized_years,
            per_year=per_year,
            seed=seed,
        )
        envelope = _new_envelope(
            universe,
            selected,
            years=normalized_years,
            per_year=per_year,
            seed=seed,
            list_name=list_name,
        )
        _atomic_write(out, envelope)
        print(
            f"[calibration] froze {len(selected)} targets from "
            f"{envelope['selection']['evaluated_count']} evaluated NEOs -> {out}",
            flush=True,
        )
    selected = envelope["selection"]["selected"]
    completed = {str(event["designation"]) for event in envelope["events"]}
    fetch = observation_fetcher or fetch_mpc_observations_api

    total = len(selected)
    for index, candidate in enumerate(selected, start=1):
        designation = str(candidate["designation"])
        if designation in completed:
            print(f"[calibration] event {index}/{total} {designation}: checkpointed", flush=True)
            continue
        print(f"[calibration] event {index}/{total} {designation}: querying MPC", flush=True)
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                event = _event_from_observations(candidate, fetch(designation))
                envelope["events"].append(event)
                envelope["query_log"].append(
                    {
                        "designation": designation,
                        "status": "accepted",
                        "attempts": attempt + 1,
                        "event_id": event["event_id"],
                    }
                )
                envelope["updated_at_utc"] = _utc_now()
                envelope["summary"] = {
                    "selected_count": total,
                    "accepted_count": len(envelope["events"]),
                    "complete": len(envelope["events"]) == total,
                }
                _atomic_write(out, envelope)
                print(
                    f"[calibration] event {index}/{total} {designation}: accepted "
                    f"JD {event['discovery_observation']['jd']:.5f}",
                    flush=True,
                )
                break
            except Exception as exc:
                last_error = exc
                print(
                    f"[calibration] event {index}/{total} {designation}: attempt "
                    f"{attempt + 1}/{retries + 1} failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                if attempt < retries and query_delay_seconds:
                    time.sleep(query_delay_seconds)
        else:
            envelope["status"] = "failed"
            envelope["updated_at_utc"] = _utc_now()
            envelope["query_log"].append(
                {
                    "designation": designation,
                    "status": "failed",
                    "attempts": retries + 1,
                    "error_type": type(last_error).__name__,
                    "error": str(last_error),
                }
            )
            envelope["summary"] = {
                "selected_count": total,
                "accepted_count": len(envelope["events"]),
                "complete": False,
            }
            _atomic_write(out, envelope)
            raise RuntimeError(
                f"MPC acquisition failed for {designation}; checkpoint is resumable at {out}"
            ) from last_error
        if index < total and query_delay_seconds:
            time.sleep(query_delay_seconds)

    envelope["status"] = "complete"
    envelope["updated_at_utc"] = _utc_now()
    envelope["summary"] = {
        "selected_count": total,
        "accepted_count": len(envelope["events"]),
        "complete": True,
    }
    _atomic_write(out, envelope)
    print(f"[calibration] complete: {total}/{total} events -> {out}", flush=True)
    return envelope


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a leakage-safe MPC discovery-field calibration envelope"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--years", type=int, nargs="+", default=list(DEFAULT_YEARS))
    parser.add_argument("--per-year", type=int, default=8)
    parser.add_argument(
        "--all-per-year",
        action="store_true",
        help="Select every object returned for each requested year.",
    )
    parser.add_argument(
        "--list-name",
        choices=sorted(MPC_LIST_CLASSES),
        default="neos",
        help="Official MPC dynamical-class list used as the candidate universe.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--query-delay-seconds", type=float, default=1.0)
    args = parser.parse_args()
    build_calibration_events(
        args.out,
        years=args.years,
        per_year=None if args.all_per_year else args.per_year,
        seed=args.seed,
        list_name=args.list_name,
        resume=args.resume,
        retries=args.retries,
        query_delay_seconds=args.query_delay_seconds,
    )


if __name__ == "__main__":
    main()
