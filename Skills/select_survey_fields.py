"""Select optimal sky fields for NEO discovery, targeting Aten and IEO/Atira classes.

Scientific basis
----------------
Aten/IEO classes have the highest fraction of undiscovered objects:

  IEO (Atira, Q < 0.983 AU) — ~97% undiscovered. Only ~30 known. Population
    models (Granvik et al. 2018) predict thousands. Accessible only in
    twilight at elongation 20-45° from the Sun.

  Aten (a < 1 AU, Q > 0.983 AU) — ~85% undiscovered for H < 20. Best found
    at quadrature (elongation 60-100°) where standard opposition surveys do
    not focus.

  Apollo/Amor — comparatively well-surveyed near opposition; lower marginal
    discovery value per field.

Scoring formula (Granvik 2018, Ye et al. 2020, Harris & D'Abramo 2015):

    S = 0.35 * CoverageGap  +  0.30 * PopulationDensity
      + 0.20 * Geometry      +  0.15 * Novelty

  CoverageGap   — proxy for time since last survey visit; twilight and
                  quadrature fields are rarely pointed at by standard cadences.
  PopulationDensity — expected undiscovered object density from debiased
                  population model, weighted by ecliptic latitude and
                  catalog incompleteness fraction.
  Geometry      — elongation match for the target class + hours observable
                  tonight (analytic hour-angle formula).
  Novelty       — penalises fields already processed by this pipeline
                  (read from Logs/pipeline_runs/ audit log).

The algorithm autonomously selects the best fields from a tessellated grid
of the entire observable sky for tonight, then outputs a ranked list ready
to feed into Skills/run_pipeline.py.

ML hook (Phase 2)
-----------------
After ~20 pipeline runs are logged, run::

    uv run python Skills/train_field_selector.py

to fit an XGBoost regressor on (gap, pop, geom, novelty, moon_phase,
limiting_mag, run_yield) to replace the analytic weights with learned ones.
Pass --model path/to/field_selector.json to use the trained model.

Usage::

    uv run python Skills/select_survey_fields.py --jd now --mode aten --top-n 20
    uv run python Skills/select_survey_fields.py --jd now --mode ieo  --top-n 10
    uv run python Skills/select_survey_fields.py --jd now --mode recovery --top-n 15 --json
    uv run python Skills/select_survey_fields.py --jd 2461000.5 --history-dir Logs/pipeline_runs
    uv run python Skills/select_survey_fields.py --jd 2459065.5 --mode aten \
        --top-n 3 --wise-archive-probes --start-jd 2458880.5 --end-jd 2459250.5 --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

# ── Constants ──────────────────────────────────────────────────────────────────

# Default observer: Palomar Mountain (ZTF primary site, latitude +33.36°)
_PALOMAR_LAT = 33.3563   # degrees North
_PALOMAR_LON = -116.8650  # degrees East (unused in Phase 1 analytic scoring)

# Candidate field grid resolution and ZTF field radius
_GRID_STEP_DEG = 7.5   # degrees between field centres (balances coverage vs. speed)
_FIELD_RADIUS_DEG = 3.5  # degrees — ZTF focal plane inscribed radius ≈ 3.8°

# Mean obliquity of the ecliptic (J2000); constant is accurate to ~0.01° over decades
_ECL_OBLIQUITY_RAD = math.radians(23.4393)

# Minimum altitude for practical observability
_MIN_ALT_DEG = 25.0

# Scoring weights (Aten/IEO priority mode)
_WEIGHTS: dict[str, float] = {
    "gap": 0.35,
    "population": 0.30,
    "geometry": 0.20,
    "novelty": 0.15,
}

# Elongation windows (min, max, peak) per mode, in degrees
_ELONG_WINDOWS: dict[str, tuple[float, float, float]] = {
    "aten": (60.0, 100.0, 80.0),   # dawn/dusk quadrature sector
    "ieo":  (20.0,  45.0, 32.5),   # twilight zone (civil to nautical twilight)
    "all":  (60.0, 160.0, 110.0),  # general NEO (broad anti-helion sector)
    "recovery": (120.0, 180.0, 165.0),  # opposition-side fields rich in known objects
}

# Approximate catalog completeness fraction at the optimal elongation per mode.
# Derived from Harris & D'Abramo (2015) census and Granvik et al. (2018) model.
# 1 - completeness = undiscovered fraction used in population score.
_COMPLETENESS: dict[str, float] = {
    "aten": 0.15,  # ~85% of Atens H<20 still undiscovered
    "ieo":  0.03,  # ~97% of IEOs undiscovered (fewest known of any NEO class)
    "all":  0.45,  # mixed population; ~55% of H<20 NEOs still undiscovered
    "recovery": 0.95,  # known-object recovery wants catalog-rich fields, not discovery gap
}

# Overlap radius for deduplication of selected fields
_DEDUP_RADIUS_DEG = _FIELD_RADIUS_DEG  # skip fields within one FoV of selected

# Overlap radius for novelty comparison against run history
_HISTORY_OVERLAP_DEG = 5.0

# WISE/NEOWISE diagnostic defaults: small parent cones are scale-plan probes,
# not complete discovery tiles. The linker may recommend smaller subfields.
_WISE_PARENT_RADIUS_DEG = 0.2


# ── Vectorised geometry helpers ───────────────────────────────────────────────

def ecliptic_latitude_batch(ra_deg: np.ndarray, dec_deg: np.ndarray) -> np.ndarray:
    """Ecliptic latitude in degrees using mean obliquity (no per-field SkyCoord call).

    Formula: sin(β) = sin(δ)·cos(ε) - cos(δ)·sin(ε)·sin(α)
    where ε is the obliquity of the ecliptic, α=RA, δ=Dec.
    """
    ra  = np.radians(ra_deg)
    dec = np.radians(dec_deg)
    sin_b = (np.sin(dec) * math.cos(_ECL_OBLIQUITY_RAD)
             - np.cos(dec) * math.sin(_ECL_OBLIQUITY_RAD) * np.sin(ra))
    return np.degrees(np.arcsin(np.clip(sin_b, -1.0, 1.0)))


def elongation_batch(ra_field: np.ndarray, dec_field: np.ndarray,
                     ra_sun: float, dec_sun: float) -> np.ndarray:
    """Sun-to-field angular separation in degrees (vectorised spherical law of cosines)."""
    rs = math.radians(ra_sun)
    ds = math.radians(dec_sun)
    rf = np.radians(ra_field)
    df = np.radians(dec_field)
    cos_sep = (math.sin(ds) * np.sin(df)
               + math.cos(ds) * np.cos(df) * np.cos(rf - rs))
    return np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0)))


def hours_visible_batch(dec_deg: np.ndarray, lat_deg: float,
                         min_alt_deg: float = _MIN_ALT_DEG) -> np.ndarray:
    """Hours per night a field is above min_alt_deg (analytic hour-angle formula).

    H_rise such that cos(H) = (sin(alt_min) - sin(lat)·sin(dec)) / (cos(lat)·cos(dec))
    Hours observable = 2·H_rise / 15  (15°/hour sidereal rate).
    Night window capped at 10 hours (conservative mid-latitude dark time).
    """
    lat = math.radians(lat_deg)
    alt = math.radians(min_alt_deg)
    dec = np.radians(dec_deg)
    denom = math.cos(lat) * np.cos(dec)
    # Avoid division by zero near poles
    safe_denom = np.where(np.abs(denom) < 1e-9, 1e-9, denom)
    cos_H = (math.sin(alt) - math.sin(lat) * np.sin(dec)) / safe_denom
    # 2 * arccos (degrees) / 15 = hours; arccos degrees = degrees of half-arc
    half_arc_deg = np.degrees(np.arccos(np.clip(cos_H, -1.0, 1.0)))
    hours = (2.0 * half_arc_deg) / 15.0
    # cos_H < -1: circumpolar (always visible) → 10h cap
    # cos_H > 1: never rises above min_alt → 0h
    return np.where(cos_H < -1.0, 10.0,
           np.where(cos_H >  1.0, 0.0,
                    np.minimum(hours, 10.0)))


# ── Scoring components ─────────────────────────────────────────────────────────

def gap_score_batch(elong: np.ndarray, mode: str) -> np.ndarray:
    """Coverage gap proxy score based on elongation and survey mode.

    Twilight and quadrature fields are visited far less frequently than the
    opposition region. In Phase 2, replace with actual per-field last-visit
    JD from the ZTF IRSA ztf.field_coverage table.

    Empirical basis (Ye et al. 2020): discovery rate rises sharply for fields
    with cadence gaps > 5 days; opposition fields average < 3-day gaps in ZTF;
    quadrature fields average 7-15 day gaps; twilight fields are rarely touched.
    """
    if mode == "ieo":
        # Twilight zone: virtually never visited by standard surveys
        return np.full(elong.shape, 0.95, dtype=float)
    elif mode == "aten":
        # Quadrature: visited ~1/4 as often as opposition; Gaussian peak at 80°
        base = 0.70 + 0.25 * np.exp(-((elong - 80.0) ** 2) / (20.0 ** 2))
        return np.clip(base, 0.0, 1.0)
    else:
        # General: survey cadence thins rapidly away from opposition
        base = 0.35 + 0.50 * np.exp(-((elong - 90.0) ** 2) / (50.0 ** 2))
        return np.clip(base, 0.0, 1.0)


def population_score_batch(ecl_lat: np.ndarray, elong: np.ndarray, mode: str) -> np.ndarray:
    """Undiscovered NEO density proxy (Granvik et al. 2018 debiased sky density).

    Combines ecliptic latitude factor (NEOs cluster near ecliptic) with the
    undiscovered fraction = 1 - catalog_completeness for the mode's class.

    Bimodal latitude weighting gives 60% weight to the ecliptic core
    (exp scale 20°) and 40% to a broad tail (scale 60°) to capture
    high-inclination objects missed by purely ecliptic surveys.
    """
    lat_score = (0.6 * np.exp(-np.abs(ecl_lat) / 20.0)
                 + 0.4 * np.exp(-np.abs(ecl_lat) / 60.0))
    undiscovered_fraction = 1.0 - _COMPLETENESS.get(mode, 0.45)
    return np.clip(lat_score * undiscovered_fraction, 0.0, 1.0)


def known_object_density_score_batch(ecl_lat: np.ndarray, elong: np.ndarray) -> np.ndarray:
    """Known-moving-object density proxy for production recovery tests.

    Known minor planets concentrate near the ecliptic and are easiest to
    recover near opposition, where sky-plane density is high and observing
    geometry is favorable. This score intentionally differs from the discovery
    population score: it seeks many expected recoveries, not rare new objects.
    """
    lat_score = np.exp(-np.abs(ecl_lat) / 12.0)
    opposition_score = np.exp(-((180.0 - elong) ** 2) / (45.0 ** 2))
    return np.clip(0.70 * lat_score + 0.30 * opposition_score, 0.0, 1.0)


def geometry_score_batch(elong: np.ndarray, hours: np.ndarray, mode: str) -> np.ndarray:
    """Geometry score: elongation match for the target class + observable hours tonight.

    Elongation score is a Gaussian centred on the mode's optimal elongation,
    with sigma = 1/3 of the window width. Fields outside the window get 0.
    Hours score is linear up to 6 hours (0.35 weight).
    """
    e_min, e_max, e_peak = _ELONG_WINDOWS.get(mode, _ELONG_WINDOWS["all"])
    sigma = (e_max - e_min) / 3.0
    elong_score = np.exp(-((elong - e_peak) ** 2) / (2.0 * sigma ** 2))
    in_window  = (elong >= e_min) & (elong <= e_max)
    hour_score = np.minimum(hours / 6.0, 1.0)
    combined   = np.clip(0.65 * elong_score + 0.35 * hour_score, 0.0, 1.0)
    # Fields outside the mode's elongation window are entirely unsuitable.
    return np.where(in_window, combined, 0.0)


# ── Run history / novelty ─────────────────────────────────────────────────────

def load_run_history(history_dir: Path) -> list[tuple[float, float]]:
    """Load (ra_deg, dec_deg) of fields previously processed from the audit log.

    Reads all run_summary.json files under history_dir (written by run_pipeline.py
    after each pipeline run). Returns empty list if directory does not exist.
    """
    seen: list[tuple[float, float]] = []
    if not history_dir or not history_dir.exists():
        return seen
    for summary_file in sorted(history_dir.rglob("run_summary.json")):
        try:
            data = json.loads(summary_file.read_text())
            ra  = data.get("ra_deg")
            dec = data.get("dec_deg")
            if ra is not None and dec is not None:
                seen.append((float(ra), float(dec)))
        except Exception:
            # Malformed or partial files are silently skipped
            pass
    return seen


def novelty_scores_batch(ra: np.ndarray, dec: np.ndarray,
                          history: list[tuple[float, float]],
                          overlap_deg: float = _HISTORY_OVERLAP_DEG) -> np.ndarray:
    """Novelty score: 1.0 = never processed; 0.0 = within overlap_deg of a prior run.

    Computed by comparing each candidate field against the history list.
    O(N * len(history)) — fast for history sizes < 500.
    """
    scores = np.ones(len(ra), dtype=float)
    if not history:
        return scores
    ra_r  = np.radians(ra)
    dec_r = np.radians(dec)
    for h_ra, h_dec in history:
        cos_sep = (math.sin(math.radians(h_dec)) * np.sin(dec_r)
                   + math.cos(math.radians(h_dec)) * np.cos(dec_r)
                   * np.cos(ra_r - math.radians(h_ra)))
        sep_deg = np.degrees(np.arccos(np.clip(cos_sep, -1.0, 1.0)))
        scores  = np.where(sep_deg < overlap_deg, 0.0, scores)
    return scores


# ── ML model hook (Phase 2 stub) ──────────────────────────────────────────────

def load_field_selector_model(model_path: Path) -> object | None:
    """Load a trained field-selector model from JSON (Phase 2 hook).

    The model replaces the analytic _WEIGHTS with learned coefficients trained
    on pipeline run history via Skills/train_field_selector.py.  Returns None
    if the file does not exist or is malformed; the caller falls back to
    analytic scoring.

    Expected JSON schema::
        {
          "version": "1.0",
          "feature_names": ["gap", "population", "geometry", "novelty", ...],
          "coef": [0.35, 0.30, 0.20, 0.15, ...],
          "intercept": 0.0
        }
    """
    if not model_path or not model_path.exists():
        return None
    try:
        data = json.loads(model_path.read_text())
        coef = np.array(data["coef"], dtype=float)
        intercept = float(data.get("intercept", 0.0))
        names = data.get("feature_names", [])
        return {"coef": coef, "intercept": intercept, "feature_names": names}
    except Exception as exc:
        print(f"Warning: could not load field selector model: {exc}", file=sys.stderr)
        return None


def apply_model_score(features: np.ndarray, model: dict) -> np.ndarray:
    """Apply a learned linear model to the feature matrix.

    features: shape (N, K) where K matches len(model['coef']).
    Returns scores in [0, 1] via sigmoid.
    """
    raw = features @ model["coef"] + model["intercept"]
    return 1.0 / (1.0 + np.exp(-raw))  # sigmoid to [0, 1]


# ── Sun position ──────────────────────────────────────────────────────────────

def get_sun_position(jd: float) -> tuple[float, float]:
    """Return Sun's (RA, Dec) in degrees at the given Julian Date.

    Uses astropy.coordinates.get_sun (called once per run, not per field).
    """
    from astropy.coordinates import get_sun  # lazy import
    from astropy.time import Time  # lazy import
    t = Time(jd, format="jd")
    sun = get_sun(t)
    return float(sun.ra.deg), float(sun.dec.deg)


# ── Grid generation ───────────────────────────────────────────────────────────

def generate_sky_grid(dec_min: float = -30.0,
                       dec_max: float = 87.0,
                       grid_step: float = _GRID_STEP_DEG) -> tuple[np.ndarray, np.ndarray]:
    """Generate a tessellated RA/Dec grid adjusted for cos(Dec) projection.

    RA spacing is widened at high Dec to keep field centres roughly equidistant
    on the sky. Returns (ra_array, dec_array) in degrees.
    """
    ra_list:  list[float] = []
    dec_list: list[float] = []
    dec = dec_min
    while dec <= dec_max:
        cos_dec = max(math.cos(math.radians(dec)), 0.05)
        ra_step = grid_step / cos_dec
        ra = 0.0
        while ra < 360.0:
            ra_list.append(ra)
            dec_list.append(dec)
            ra += ra_step
        dec += grid_step
    return np.array(ra_list, dtype=float), np.array(dec_list, dtype=float)


# ── Main selection routine ─────────────────────────────────────────────────────

def select_fields(jd: float,
                  mode: str = "aten",
                  top_n: int = 20,
                  history_dir: Path | None = None,
                  lat: float = _PALOMAR_LAT,
                  model_path: Path | None = None) -> list[dict]:
    """Score all candidate sky fields and return the top-N for the current night.

    All geometry is computed analytically over a vectorised NumPy array for
    the entire sky grid in a single pass (~1-2 seconds for 1,200 fields).

    Parameters
    ----------
    jd:           Julian Date of the observation window to score.
    mode:         "aten" | "ieo" | "all" | "recovery" — controls elongation
                  window and the population score used in scoring.
    top_n:        Number of top fields to return after deduplication.
    history_dir:  Path to Logs/pipeline_runs/ directory; if given, fields
                  already processed are penalised via the Novelty score.
    lat:          Observer latitude in degrees North (default: Palomar +33.36°).
    model_path:   Optional path to a trained field-selector model JSON file
                  (Phase 2 ML hook). Falls back to analytic scoring if None
                  or if the file does not exist.

    Returns
    -------
    List of dicts with keys: rank, ra_deg, dec_deg, score, gap_score,
    pop_score, geom_score, novelty_score, elongation_deg, ecl_lat_deg,
    hours_visible, field_radius_deg, reason.
    """
    t_start = time.monotonic()

    ra_sun, dec_sun = get_sun_position(jd)
    print(
        f"JD {jd:.2f}  |  Sun: RA={ra_sun:.1f}° Dec={dec_sun:.1f}°",
        file=sys.stderr, flush=True,
    )
    print(
        f"Mode: {mode}  |  Observer lat: {lat:.2f}°N  |  Top-N: {top_n}",
        file=sys.stderr, flush=True,
    )

    # Build sky grid
    ra_arr, dec_arr = generate_sky_grid()
    n_fields = len(ra_arr)
    print(f"Scoring {n_fields} candidate fields...", file=sys.stderr, flush=True)

    # Vectorised geometry
    elong   = elongation_batch(ra_arr, dec_arr, ra_sun, dec_sun)
    ecl_lat = ecliptic_latitude_batch(ra_arr, dec_arr)
    hours   = hours_visible_batch(dec_arr, lat)

    # Vectorised scoring components
    gap_s   = gap_score_batch(elong, mode)
    pop_s   = (
        known_object_density_score_batch(ecl_lat, elong)
        if mode == "recovery"
        else population_score_batch(ecl_lat, elong, mode)
    )
    geom_s  = geometry_score_batch(elong, hours, mode)
    history = load_run_history(history_dir) if history_dir else []
    novel_s = novelty_scores_batch(ra_arr, dec_arr, history)

    # Composite score: analytic weights or learned model
    ml_model = load_field_selector_model(model_path) if model_path else None
    if ml_model is not None:
        # Phase 2: learned linear model over component features
        feature_matrix = np.column_stack([gap_s, pop_s, geom_s, novel_s])
        total = apply_model_score(feature_matrix, ml_model)
        print(f"Using ML model: {model_path}", file=sys.stderr, flush=True)
    else:
        w = _WEIGHTS
        if mode == "recovery":
            total = 0.45 * pop_s + 0.35 * geom_s + 0.20 * novel_s
        else:
            total = (w["gap"] * gap_s + w["population"] * pop_s
                     + w["geometry"] * geom_s + w["novelty"] * novel_s)

    # Mask non-observable fields (below horizon or outside elongation window)
    observable = (geom_s > 0.01) & (hours > 0.5)
    total      = np.where(observable, total, -1.0)

    # Sort descending; grab extra candidates to absorb deduplication losses
    order   = np.argsort(-total)
    results: list[dict] = []
    selected_positions: list[tuple[float, float]] = []  # (ra, dec) of chosen fields

    elapsed_score = time.monotonic() - t_start
    print(f"Scored {n_fields} fields in {elapsed_score:.2f}s  |  "
          f"Observable: {int(observable.sum())}  |  Ranking...",
          file=sys.stderr, flush=True)

    for idx in order:
        if total[idx] < 0.0:
            break  # all remaining fields are non-observable

        ra_i  = float(ra_arr[idx])
        dec_i = float(dec_arr[idx])

        # Deduplicate: reject fields within one FoV of an already-selected field
        too_close = False
        for s_ra, s_dec in selected_positions:
            cos_sep = (math.sin(math.radians(s_dec)) * math.sin(math.radians(dec_i))
                       + math.cos(math.radians(s_dec)) * math.cos(math.radians(dec_i))
                       * math.cos(math.radians(ra_i) - math.radians(s_ra)))
            if math.degrees(math.acos(max(-1.0, min(1.0, cos_sep)))) < _DEDUP_RADIUS_DEG:
                too_close = True
                break
        if too_close:
            continue

        selected_positions.append((ra_i, dec_i))

        # Human-readable reason string
        parts: list[str] = []
        if gap_s[idx] > 0.7:
            parts.append(f"coverage gap {gap_s[idx]:.2f}")
        if pop_s[idx] > 0.4:
            label = "known-object density" if mode == "recovery" else "pop density"
            parts.append(f"{label} {pop_s[idx]:.2f}")
        if geom_s[idx] > 0.4:
            parts.append(f"geometry {geom_s[idx]:.2f} ({hours[idx]:.1f}h vis)")
        if novel_s[idx] == 0.0:
            parts.append("WARNING: recently processed")
        reason = "; ".join(parts) or f"elong {elong[idx]:.1f}°"

        results.append({
            "rank":             len(results) + 1,
            "ra_deg":           round(ra_i, 2),
            "dec_deg":          round(dec_i, 2),
            "score":            round(float(total[idx]), 4),
            "gap_score":        round(float(gap_s[idx]),   4),
            "pop_score":        round(float(pop_s[idx]),   4),
            "geom_score":       round(float(geom_s[idx]),  4),
            "novelty_score":    round(float(novel_s[idx]), 4),
            "elongation_deg":   round(float(elong[idx]),   1),
            "ecl_lat_deg":      round(float(ecl_lat[idx]), 1),
            "hours_visible":    round(float(hours[idx]),   1),
            "field_radius_deg": _FIELD_RADIUS_DEG,
            "reason":           reason,
        })

        if len(results) >= top_n:
            break

    elapsed_total = time.monotonic() - t_start
    print(f"Done. {len(results)} fields selected in {elapsed_total:.1f}s total.",
          file=sys.stderr, flush=True)
    return results


def probe_ztf_object_count(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    *,
    page_size: int = 100,
) -> int:
    """Return a bounded live ALeRCE/ZTF object count for one candidate field."""
    try:
        from alerce import Alerce  # type: ignore[import]
    except Exception:
        return 0

    try:
        client = Alerce()
        payload = client.query_objects(
            format="json",
            survey="ztf",
            ra=ra_deg,
            dec=dec_deg,
            radius=max(radius_deg, 0.0) * 3600.0,
            firstmjd=[start_jd - 2_400_000.5, end_jd - 2_400_000.5],
            lastmjd=[start_jd - 2_400_000.5, end_jd - 2_400_000.5],
            page=1,
            page_size=max(1, min(page_size, 100)),
            order_by="ndet",
            order_mode="DESC",
        )
    except Exception:
        return 0
    rows = payload.get("items", []) if isinstance(payload, dict) else payload
    return len(rows) if isinstance(rows, list) else 0


def filter_fields_by_ztf_availability(
    fields: list[dict],
    *,
    start_jd: float,
    end_jd: float,
    min_objects: int,
    top_n: int,
    probe_fn=probe_ztf_object_count,
) -> list[dict]:
    """Keep only candidate fields with live ZTF/ALeRCE objects in the window."""
    accepted: list[dict] = []
    total = len(fields)
    t_start = time.monotonic()
    for idx, field in enumerate(fields, start=1):
        count = int(
            probe_fn(
                float(field["ra_deg"]),
                float(field["dec_deg"]),
                float(field["field_radius_deg"]),
                start_jd,
                end_jd,
            )
        )
        elapsed = time.monotonic() - t_start
        eta = (elapsed / idx) * (total - idx) if idx else 0.0
        print(
            f"[ztf-probe] {idx}/{total} RA={field['ra_deg']:.2f} "
            f"Dec={field['dec_deg']:.2f} objects={count} "
            f"elapsed {elapsed:.0f}s ETA {eta:.0f}s",
            file=sys.stderr,
            flush=True,
        )
        enriched = dict(field)
        enriched["ztf_object_count"] = count
        if count >= min_objects:
            enriched["rank"] = len(accepted) + 1
            enriched["reason"] = f"{enriched['reason']}; ZTF objects {count}"
            accepted.append(enriched)
        if len(accepted) >= top_n:
            break
    return accepted


def wise_scale_probe_outputs(
    field: dict,
    *,
    start_jd: float,
    end_jd: float,
    radius_deg: float = _WISE_PARENT_RADIUS_DEG,
) -> dict:
    """Return directive-compliant WISE scale-plan outputs for a selected field.

    This does not claim the field is productive. It produces the first live
    measurement command for a candidate parent field: a dry-run WISE scale plan
    that can rank support-positive diagnostic subfields before any full run.
    """
    ra = float(field["ra_deg"])
    dec = float(field["dec_deg"])
    label = f"ra{ra:.2f}_dec{dec:.2f}".replace("-", "m").replace(".", "p")
    scale_plan = f"Logs/reports/wise_scale_plan_{label}_{start_jd:.1f}_{end_jd:.1f}.json"
    probe_out = f"Logs/reports/wise_scale_probe_{label}_{start_jd:.1f}_{end_jd:.1f}.json"
    args = [
        "caffeinate",
        "-i",
        "uv",
        "run",
        "--python",
        "3.14",
        "python",
        "Skills/run_pipeline.py",
        "--ra",
        f"{ra:.4f}",
        "--dec",
        f"{dec:.4f}",
        "--radius",
        f"{radius_deg:.4f}",
        "--start-jd",
        f"{start_jd:.1f}",
        "--end-jd",
        f"{end_jd:.1f}",
        "--surveys",
        "WISE",
        "--no-resume",
        "--force-refresh",
        "--link-scale-plan-out",
        scale_plan,
        "--output",
        probe_out,
    ]
    command = (
        "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 "
        "NUMEXPR_MAX_THREADS=1 PYTHONPATH=src "
        + " ".join(args)
    )
    return {
        "wise_parent_radius_deg": round(radius_deg, 4),
        "wise_start_jd": round(start_jd, 1),
        "wise_end_jd": round(end_jd, 1),
        "wise_scale_plan_out": scale_plan,
        "wise_probe_out": probe_out,
        "wise_scale_probe_command": command,
        "wise_safety": (
            "dry-run scale-plan probe only; no external submission; "
            "do not run adversarial review unless non-zero ScoredNEO packets are written"
        ),
    }


def add_wise_archive_probe_commands(
    fields: list[dict],
    *,
    start_jd: float,
    end_jd: float,
    radius_deg: float = _WISE_PARENT_RADIUS_DEG,
) -> list[dict]:
    """Add WISE archive scale-plan probe commands to selected field rows."""
    enriched: list[dict] = []
    for field in fields:
        row = dict(field)
        row.update(
            wise_scale_probe_outputs(
                field,
                start_jd=start_jd,
                end_jd=end_jd,
                radius_deg=radius_deg,
            )
        )
        enriched.append(row)
    return enriched


# ── CLI ────────────────────────────────────────────────────────────────────────

def append_fields_to_target_queue(
    fields: list[dict], queue_path: Path, *, data_role: str
) -> int:
    """Append ranked field-selection results to the target-priority-queue CSV.

    Matches the committed `data_selection/target_priority_queue.csv` schema
    exactly (rank,priority,status,data_role,source,selection_rule,
    evidence_path,notes) rather than the more elaborate generic schema in
    `docs/astrometrics_data_selection_policy.md` -- this repo already
    committed the simplified version, and this function conforms to what is
    actually on disk. Writes the header only if the file does not yet exist.
    Every value is derived directly from the selector's own computed score
    and reason; nothing is invented. Returns the number of rows appended.
    """
    import csv

    fieldnames = [
        "rank", "priority", "status", "data_role", "source",
        "selection_rule", "evidence_path", "notes",
    ]
    file_exists = queue_path.exists()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        n_written = 0
        for field in fields:
            source = "WISE" if "wise_scale_probe_command" in field else "sky_field_selector"
            evidence_path = field.get("wise_scale_plan_out", "")
            notes = (
                f"ra_deg={field['ra_deg']} dec_deg={field['dec_deg']} "
                f"field_radius_deg={field.get('field_radius_deg', _FIELD_RADIUS_DEG)}"
            )
            if "wise_scale_probe_command" in field:
                notes += f"; wise_scale_probe_command={field['wise_scale_probe_command']}"
            writer.writerow({
                "rank": field["rank"],
                "priority": f"{field['score']:.4f}",
                "status": "not_searched",
                "data_role": data_role,
                "source": source,
                "selection_rule": field["reason"],
                "evidence_path": evidence_path,
                "notes": notes,
            })
            n_written += 1
    return n_written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Select optimal sky fields for NEO discovery or recovery tests. "
            "Scores the entire observable sky tonight and returns a ranked list "
            "of (RA, Dec) cones to feed into Skills/run_pipeline.py."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run python Skills/select_survey_fields.py --jd now --mode aten --top-n 20\n"
            "  uv run python Skills/select_survey_fields.py --jd now --mode ieo --top-n 10 --json\n"
            "  uv run python Skills/select_survey_fields.py --jd now --mode recovery --top-n 10\n"
            "  uv run python Skills/select_survey_fields.py --jd now "
            "--history-dir Logs/pipeline_runs\n"
            "  uv run python Skills/select_survey_fields.py --jd 2459065.5 --mode aten "
            "--wise-archive-probes --start-jd 2458880.5 --end-jd 2459250.5 --json\n"
        ),
    )
    parser.add_argument(
        "--jd", default="now",
        help="Julian Date for scoring (e.g. 2461000.5) or 'now'. Default: now.",
    )
    parser.add_argument(
        "--mode", choices=["aten", "ieo", "all", "recovery"], default="aten",
        help=(
            "Discovery mode. 'aten': quadrature/dawn-dusk (elong 60-100°, ~85%% undiscovered). "
            "'ieo': twilight Atira (elong 20-45°, ~97%% undiscovered). "
            "'all': general NEO. 'recovery': opposition-side known-object-rich "
            "fields for the T1-C recovery benchmark. Default: aten."
        ),
    )
    parser.add_argument(
        "--top-n", type=int, default=20,
        help="Number of top ranked fields to output. Default: 20.",
    )
    parser.add_argument(
        "--obs-lat", type=float, default=_PALOMAR_LAT,
        help=f"Observer latitude degrees N. Default: {_PALOMAR_LAT} (Palomar).",
    )
    parser.add_argument(
        "--history-dir", type=Path, default=None,
        help="Path to Logs/pipeline_runs/ for novelty scoring (skip recently processed fields).",
    )
    parser.add_argument(
        "--model", type=Path, default=None,
        help="Path to trained field-selector model JSON (Phase 2 ML hook). "
             "Falls back to analytic scoring if not provided.",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_out",
        help="Output JSON list instead of ASCII table.",
    )
    parser.add_argument(
        "--require-ztf-alerts",
        action="store_true",
        help="Probe live ALeRCE/ZTF availability and keep only fields with objects.",
    )
    parser.add_argument(
        "--ztf-start-jd",
        type=float,
        default=None,
        help="Start JD for the live ZTF availability probe. Default: jd - 4.",
    )
    parser.add_argument(
        "--ztf-end-jd",
        type=float,
        default=None,
        help="End JD for the live ZTF availability probe. Default: jd.",
    )
    parser.add_argument(
        "--ztf-min-objects",
        type=int,
        default=1,
        help="Minimum ALeRCE/ZTF objects required for a selected field.",
    )
    parser.add_argument(
        "--ztf-probe-top-k",
        type=int,
        default=40,
        help="Number of analytically ranked fields to live-probe before filtering.",
    )
    parser.add_argument(
        "--wise-archive-probes",
        action="store_true",
        help=(
            "Add dry-run WISE/NEOWISE scale-plan probe commands to each selected "
            "field. Requires --start-jd and --end-jd."
        ),
    )
    parser.add_argument(
        "--start-jd",
        type=float,
        default=None,
        help="Start JD for WISE/NEOWISE archive scale-plan probe commands.",
    )
    parser.add_argument(
        "--end-jd",
        type=float,
        default=None,
        help="End JD for WISE/NEOWISE archive scale-plan probe commands.",
    )
    parser.add_argument(
        "--wise-parent-radius",
        type=float,
        default=_WISE_PARENT_RADIUS_DEG,
        help=(
            "Parent cone radius, in degrees, for WISE scale-plan probes. "
            f"Default: {_WISE_PARENT_RADIUS_DEG}."
        ),
    )
    parser.add_argument(
        "--write-target-queue",
        type=Path,
        default=None,
        help=(
            "Append the ranked field list to this target-priority-queue CSV, "
            "matching data_selection/target_priority_queue.csv's committed "
            "schema (rank,priority,status,data_role,source,selection_rule,"
            "evidence_path,notes) per docs/astrometrics_data_selection_policy.md's "
            "'every live-search batch needs a documented selection rule before "
            "execution' requirement. Previously this tool only printed 'copy to "
            "run_pipeline.py' with no persisted, inspectable selection record."
        ),
    )
    parser.add_argument(
        "--target-queue-data-role",
        default="live_search",
        help="data_role value recorded for appended target-queue rows (default: live_search).",
    )
    args = parser.parse_args(argv)

    if args.jd == "now":
        from astropy.time import Time
        jd = float(Time.now().jd)
    else:
        jd = float(args.jd)

    initial_top_n = max(args.top_n, args.ztf_probe_top_k) if args.require_ztf_alerts else args.top_n
    fields = select_fields(
        jd=jd,
        mode=args.mode,
        top_n=initial_top_n,
        history_dir=args.history_dir,
        lat=args.obs_lat,
        model_path=args.model,
    )
    if args.require_ztf_alerts:
        fields = filter_fields_by_ztf_availability(
            fields,
            start_jd=args.ztf_start_jd if args.ztf_start_jd is not None else jd - 4.0,
            end_jd=args.ztf_end_jd if args.ztf_end_jd is not None else jd,
            min_objects=args.ztf_min_objects,
            top_n=args.top_n,
        )
    if args.wise_archive_probes:
        if args.start_jd is None or args.end_jd is None:
            parser.error("--wise-archive-probes requires --start-jd and --end-jd")
        if args.end_jd <= args.start_jd:
            parser.error("--end-jd must be greater than --start-jd")
        fields = fields[: args.top_n]
        fields = add_wise_archive_probe_commands(
            fields,
            start_jd=args.start_jd,
            end_jd=args.end_jd,
            radius_deg=args.wise_parent_radius,
        )

    if args.write_target_queue is not None:
        n_written = append_fields_to_target_queue(
            fields, args.write_target_queue, data_role=args.target_queue_data_role
        )
        print(
            f"Appended {n_written} field(s) to {args.write_target_queue}",
            file=sys.stderr,
        )

    if args.json_out:
        print(json.dumps(fields, indent=2))
        return

    # ASCII ranked table
    col = "  "
    hdr = (f"{'Rank':>4}{col}{'RA':>8}{col}{'Dec':>7}{col}{'Score':>6}{col}"
           f"{'Gap':>5}{col}{'Pop':>5}{col}{'Geom':>5}{col}"
           f"{'Elong':>6}{col}{'EclLat':>7}{col}{'Vis_h':>5}{col}Reason")
    print()
    print(hdr)
    print("-" * len(hdr))
    for f in fields:
        print(
            f"{f['rank']:>4}{col}{f['ra_deg']:>8.2f}{col}{f['dec_deg']:>7.2f}{col}"
            f"{f['score']:>6.4f}{col}{f['gap_score']:>5.3f}{col}{f['pop_score']:>5.3f}{col}"
            f"{f['geom_score']:>5.3f}{col}{f['elongation_deg']:>6.1f}{col}"
            f"{f['ecl_lat_deg']:>7.1f}{col}{f['hours_visible']:>5.1f}{col}{f['reason']}"
        )

    if fields:
        top = fields[0]
        print()
        print("Top field — copy to run_pipeline.py:")
        print(f"  --ra {top['ra_deg']} --dec {top['dec_deg']} "
              f"--radius {_FIELD_RADIUS_DEG}")
        print(f"  (score={top['score']:.4f}  elong={top['elongation_deg']:.1f}°  "
              f"ecl_lat={top['ecl_lat_deg']:.1f}°  {top['hours_visible']:.1f}h visible)")
        if args.wise_archive_probes:
            print()
            print("Top WISE scale-plan probe — copy exactly:")
            print(top["wise_scale_probe_command"])


if __name__ == "__main__":
    main()
