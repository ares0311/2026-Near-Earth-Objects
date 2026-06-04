"""Link stage — THOR-inspired tracklet linking across multiple nights."""

from __future__ import annotations

__all__ = ["link", "merge_tracklets", "estimate_motion_uncertainty",
           "filter_high_motion", "deduplicate_tracklets", "_predict_from_arc",
           "split_tracklet", "compute_arc_statistics", "assess_link_confidence",
           "compute_tracklet_grade", "filter_by_arc_length", "summarize_arc_statistics",
           "filter_by_nights_observed", "merge_overlapping_tracklets",
           "validate_tracklet", "compute_great_circle_residual",
           "compute_position_angle_consistency", "score_tracklet_quality",
           "compute_night_span",
           "compute_tracklet_velocity_dispersion",
           "compute_inter_night_gaps",
           "filter_by_motion_rate",
           "compute_tracklet_arc_nights",
           "compute_mean_consecutive_motion",
           "compute_tracklet_sky_density",
           "compute_tracklet_completeness",
           "find_longest_tracklet",
           "compute_tracklet_motion_scatter",
           "compute_great_circle_arc",
           "compute_arc_curvature",
           "compute_tracklet_density",
           "compute_position_residuals",
           "compute_inter_observation_gaps",
           "compute_tracklet_overlap_fraction",
           "compute_velocity_dispersion",
           "compute_tracklet_centroid",
           "compute_along_track_error",
           "compute_observation_rate",
           "compute_tracklet_brightness_trend",
           "compute_arc_endpoint_separation",
           "compute_pa_circular_std",
           "compute_sky_coverage_area",
           "compute_night_gap_statistics",
           "compute_field_tracklet_density",
           "estimate_observation_cadence",
           "compute_tracklet_span_nights"]

import math
import uuid
from collections import defaultdict

import numpy as np

from schemas import (
    LinkProvenance,
    LinkResult,
    Observation,
    RawCandidate,
    Tracklet,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_NIGHTS = 2
_MIN_OBSERVATIONS = 3
_MOTION_MIN_ARCSEC_PER_HR = 0.01
_MOTION_MAX_ARCSEC_PER_HR = 60.0
_POSITION_TOLERANCE_ARCSEC = 10.0  # sky-plane prediction window
_CHI2_DOF_THRESHOLD = 5.0  # max reduced chi² for orbit consistency
# Satellite/debris trail filter: reject seed pairs with motion that is
# >95% along a single axis (nearly pure E-W or N-S) at rate > threshold
_SATELLITE_RATE_MIN_ARCSEC_PER_HR = 30.0
_SATELLITE_AXIS_FRACTION = 0.98  # |dra|/rate or |ddec|/rate must be < this


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = (math.radians(v) for v in (ra1, dec1, ra2, dec2))
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep)) * 3600.0


def _is_satellite_trail(dra: float, ddec: float, rate: float) -> bool:
    """Return True if motion looks like a satellite or debris trail.

    Fast (>30 arcsec/hr) purely E-W or N-S movers are almost certainly
    low-Earth-orbit objects, not solar system bodies.
    """
    if rate < _SATELLITE_RATE_MIN_ARCSEC_PER_HR:
        return False
    return abs(dra) / rate > _SATELLITE_AXIS_FRACTION or abs(ddec) / rate > _SATELLITE_AXIS_FRACTION


def _motion(obs_a: Observation, obs_b: Observation) -> tuple[float, float]:
    """Return (dRA_arcsec/hr, dDec_arcsec/hr)."""
    dt_hr = (obs_b.jd - obs_a.jd) * 24.0
    if abs(dt_hr) < 1e-9:
        return 0.0, 0.0
    cos_dec = math.cos(math.radians((obs_a.dec_deg + obs_b.dec_deg) / 2.0))
    dra = (obs_b.ra_deg - obs_a.ra_deg) * 3600.0 * cos_dec / dt_hr
    ddec = (obs_b.dec_deg - obs_a.dec_deg) * 3600.0 / dt_hr
    return dra, ddec



def _predict_from_arc(
    arc_obs: list[Observation],
    target_jd: float,
) -> tuple[float, float]:
    """Predict RA, Dec at target_jd using observations already in the arc.

    Uses a quadratic polynomial fit when ≥3 observations are available,
    falling back to linear (degree-1) for exactly 2.  This improves
    accuracy over the constant-rate seed-pair extrapolation for arcs
    that already span multiple nights.
    """
    obs_sorted = sorted(arc_obs, key=lambda o: o.jd)
    t0 = obs_sorted[0].jd
    ts = np.array([(o.jd - t0) * 24.0 for o in obs_sorted])  # hours since first obs
    ras = np.array([o.ra_deg for o in obs_sorted])
    decs = np.array([o.dec_deg for o in obs_sorted])

    degree = min(2, len(obs_sorted) - 1)  # quadratic when ≥3 obs, linear for 2
    ra_coeffs = np.polyfit(ts, ras, degree)
    dec_coeffs = np.polyfit(ts, decs, degree)

    dt = (target_jd - t0) * 24.0
    pred_ra = float(np.polyval(ra_coeffs, dt)) % 360.0
    pred_dec = float(np.clip(float(np.polyval(dec_coeffs, dt)), -90.0, 90.0))
    return pred_ra, pred_dec


# ---------------------------------------------------------------------------
# Linear motion model fit
# ---------------------------------------------------------------------------


def _fit_linear_motion(
    observations: list[Observation],
) -> tuple[float, float, float, float, float]:
    """Fit a linear motion model to a sequence of observations.

    Returns (ra0, dec0, dra_arcsec_hr, ddec_arcsec_hr, reduced_chi2)
    where ra0, dec0 are position at the first epoch.
    """
    if len(observations) < 2:
        return observations[0].ra_deg, observations[0].dec_deg, 0.0, 0.0, 0.0

    obs_sorted = sorted(observations, key=lambda o: o.jd)
    t0 = obs_sorted[0].jd
    cos_dec = math.cos(math.radians(np.mean([o.dec_deg for o in obs_sorted])))

    ts = np.array([(o.jd - t0) * 24.0 for o in obs_sorted])  # hours
    ras = np.array([o.ra_deg * 3600.0 * cos_dec for o in obs_sorted])  # arcsec
    decs = np.array([o.dec_deg * 3600.0 for o in obs_sorted])
    # 0.5 arcsec floor ≈ typical ground-based survey astrometric uncertainty
    errs = np.array([max(o.mag_err, 0.5) for o in obs_sorted])

    # Weighted least squares: [1, t] @ [a, b] = y
    A = np.column_stack([np.ones_like(ts), ts])
    W = np.diag(1.0 / errs**2)
    AtW = A.T @ W
    AtWA = AtW @ A
    try:
        coeff_ra = np.linalg.solve(AtWA, AtW @ ras)
        coeff_dec = np.linalg.solve(AtWA, AtW @ decs)
    except np.linalg.LinAlgError:
        coeff_ra = np.polyfit(ts, ras, 1)[::-1]
        coeff_dec = np.polyfit(ts, decs, 1)[::-1]

    ra0_arcsec, dra = float(coeff_ra[0]), float(coeff_ra[1])
    dec0_arcsec, ddec = float(coeff_dec[0]), float(coeff_dec[1])

    # Residuals
    res_ra = ras - (ra0_arcsec + dra * ts)
    res_dec = decs - (dec0_arcsec + ddec * ts)
    chi2 = float(np.sum((res_ra**2 + res_dec**2) / errs**2))
    dof = max(1, 2 * len(ts) - 4)
    reduced_chi2 = chi2 / dof

    ra0_deg = ra0_arcsec / (3600.0 * cos_dec)
    dec0_deg = dec0_arcsec / 3600.0
    return ra0_deg, dec0_deg, dra, ddec, reduced_chi2


# ---------------------------------------------------------------------------
# Tracklet construction
# ---------------------------------------------------------------------------


def _make_tracklet(observations: list[Observation]) -> Tracklet:
    obs_sorted = sorted(observations, key=lambda o: o.jd)
    arc_days = obs_sorted[-1].jd - obs_sorted[0].jd

    if len(obs_sorted) >= 2:
        dra, ddec = _motion(obs_sorted[0], obs_sorted[-1])
        rate = math.hypot(dra, ddec)
        pa = math.degrees(math.atan2(dra, ddec)) % 360.0
    else:
        rate, pa = 0.0, 0.0

    return Tracklet(
        object_id=str(uuid.uuid4()),
        observations=tuple(obs_sorted),
        arc_days=arc_days,
        motion_rate_arcsec_per_hour=rate,
        motion_pa_degrees=pa,
    )


# ---------------------------------------------------------------------------
# Night grouping
# ---------------------------------------------------------------------------


def _obs_by_night(candidates: tuple[RawCandidate, ...]) -> dict[int, list[Observation]]:
    nights: dict[int, list[Observation]] = defaultdict(list)
    for cand in candidates:
        for obs in cand.observations:
            nights[int(obs.jd)].append(obs)
    return dict(nights)


# ---------------------------------------------------------------------------
# Core linker — THOR-inspired pair-and-propagate
# ---------------------------------------------------------------------------


def _link_candidates(
    candidates: tuple[RawCandidate, ...],
    tolerance_arcsec: float = _POSITION_TOLERANCE_ARCSEC,
    chi2_threshold: float = _CHI2_DOF_THRESHOLD,
    min_nights: int = _MIN_NIGHTS,
    min_obs: int = _MIN_OBSERVATIONS,
) -> list[Tracklet]:
    """Link single-night candidates into multi-night tracklets.

    Algorithm (simplified THOR):
    1. Form seed pairs from night N and night N+1 consistent with solar system motion.
    2. For each seed pair, predict position on all subsequent nights and collect
       matching candidates (within tolerance_arcsec).
    3. Fit a linear motion model; accept tracklet if reduced chi² < threshold.
    4. Require ≥min_nights and ≥min_obs observations.
    """
    nights = _obs_by_night(candidates)
    sorted_nights = sorted(nights.keys())

    if len(sorted_nights) < min_nights:
        return []

    tracklets: list[Tracklet] = []
    used_obs_ids: set[str] = set()

    for ni, night_a in enumerate(sorted_nights[:-1]):
        obs_a_list = nights[night_a]

        for night_b in sorted_nights[ni + 1 :]:
            obs_b_list = nights[night_b]
            dt_days = night_b - night_a
            if dt_days > 30:
                break  # too large a gap for seeding

            for obs_a in obs_a_list:
                if obs_a.obs_id in used_obs_ids:
                    continue

                for obs_b in obs_b_list:
                    if obs_b.obs_id in used_obs_ids:
                        continue

                    dra, ddec = _motion(obs_a, obs_b)
                    rate = math.hypot(dra, ddec)
                    if not (_MOTION_MIN_ARCSEC_PER_HR <= rate <= _MOTION_MAX_ARCSEC_PER_HR):
                        continue
                    if _is_satellite_trail(dra, ddec, rate):
                        continue

                    # Seed pair found — propagate to remaining nights
                    arc_obs: list[Observation] = [obs_a, obs_b]

                    for night_c in sorted_nights:
                        if night_c in (night_a, night_b):
                            continue
                        for obs_c in nights[night_c]:
                            if obs_c.obs_id in used_obs_ids:
                                continue
                            # Use arc-based predictor once we have ≥2 obs for better accuracy
                            pred_ra, pred_dec = _predict_from_arc(arc_obs, obs_c.jd)
                            sep = _sep_arcsec(obs_c.ra_deg, obs_c.dec_deg, pred_ra, pred_dec)
                            if sep <= tolerance_arcsec:
                                arc_obs.append(obs_c)
                                break

                    if len(arc_obs) < min_obs:
                        continue

                    nights_covered = len({int(o.jd) for o in arc_obs})
                    if nights_covered < min_nights:
                        continue

                    # Fit linear model and check chi²
                    _, _, _, _, reduced_chi2 = _fit_linear_motion(arc_obs)
                    if reduced_chi2 > chi2_threshold:
                        continue

                    # Accept tracklet
                    tracklet = _make_tracklet(arc_obs)
                    tracklets.append(tracklet)
                    used_obs_ids.update(o.obs_id for o in arc_obs)
                    break  # move on from obs_b once tracklet formed

    return tracklets


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def merge_tracklets(a: Tracklet, b: Tracklet) -> Tracklet:
    """Merge two tracklets covering overlapping or adjacent arcs.

    Combines all observations (deduplicated by ``obs_id``), then recomputes
    arc length, motion rate, and position angle from the merged set.
    Returns a new :class:`Tracklet` with a fresh ``object_id``.
    """
    seen: set[str] = set()
    merged_obs: list[Observation] = []
    for obs in (*a.observations, *b.observations):
        if obs.obs_id not in seen:
            seen.add(obs.obs_id)
            merged_obs.append(obs)
    return _make_tracklet(merged_obs)


def link(
    candidates: tuple[RawCandidate, ...],
    min_nights: int = _MIN_NIGHTS,
    min_observations: int = _MIN_OBSERVATIONS,
    position_tolerance_arcsec: float = _POSITION_TOLERANCE_ARCSEC,
    chi2_threshold: float = _CHI2_DOF_THRESHOLD,
) -> LinkResult:
    """Link single-night moving object candidates into multi-night tracklets.

    Requires ≥min_nights distinct nights and ≥min_observations detections per tracklet.
    """
    tracklets = _link_candidates(
        candidates,
        tolerance_arcsec=position_tolerance_arcsec,
        chi2_threshold=chi2_threshold,
        min_nights=min_nights,
        min_obs=min_observations,
    )
    provenance = LinkProvenance(
        n_tracklets=len(tracklets),
        min_nights=min_nights,
        min_observations=min_observations,
    )
    return LinkResult(tracklets=tuple(tracklets), provenance=provenance)


def estimate_motion_uncertainty(tracklet: Tracklet) -> dict:
    """Estimate uncertainty on motion rate and position angle from fit residuals.

    Fits a linear motion model to the tracklet observations and propagates
    the formal uncertainties on the rate components into rate and PA errors.

    Returns a dict with keys:
      ``rate_arcsec_hr``    — best-fit motion rate (arcsec/hr)
      ``rate_err_arcsec_hr``— 1-σ uncertainty on rate
      ``pa_deg``            — best-fit position angle (deg, N through E)
      ``pa_err_deg``        — 1-σ uncertainty on PA
      ``reduced_chi2``      — goodness-of-fit (1.0 = perfect linear motion)
      ``n_obs``             — number of observations used
    """
    obs = list(tracklet.observations)
    _, _, dra, ddec, reduced_chi2 = _fit_linear_motion(obs)
    rate = math.hypot(dra, ddec)
    pa = math.degrees(math.atan2(dra, ddec)) % 360.0

    # Formal rate uncertainty: propagate from per-observation astrometric noise
    errs = [max(o.mag_err, 0.5) for o in obs]
    median_err = float(np.median(errs)) if errs else 0.5
    n = len(obs)
    # σ_rate ≈ sqrt(2) * σ_pos / (T/2) where T is arc length in hours
    arc_hr = tracklet.arc_days * 24.0
    if arc_hr > 0:
        rate_err = math.sqrt(2.0) * median_err / (arc_hr / 2.0)
    else:
        rate_err = float("inf")

    # σ_PA from error propagation: σ_PA = σ_rate / rate (radians) when rate >> σ
    if rate > 1e-6:
        pa_err = math.degrees(rate_err / rate)
    else:
        pa_err = 180.0

    return {
        "rate_arcsec_hr": round(rate, 4),
        "rate_err_arcsec_hr": round(rate_err, 4),
        "pa_deg": round(pa, 3),
        "pa_err_deg": round(min(pa_err, 180.0), 3),
        "reduced_chi2": round(reduced_chi2, 4),
        "n_obs": n,
    }


def filter_high_motion(
    tracklets: list[Tracklet],
    min_rate_arcsec_hr: float = 10.0,
) -> list[Tracklet]:
    """Return tracklets whose motion rate exceeds *min_rate_arcsec_hr*.

    Useful for isolating fast-moving NEO candidates that are most likely to
    be lost without rapid follow-up (e.g., close-approaching Apollos).

    Args:
        tracklets:          Input list of :class:`Tracklet` objects.
        min_rate_arcsec_hr: Minimum motion rate threshold (arcsec/hr).
                            Defaults to 10.0 arcsec/hr.

    Returns:
        List of tracklets with ``motion_rate_arcsec_per_hour ≥ min_rate_arcsec_hr``,
        in input order.
    """
    return [t for t in tracklets if t.motion_rate_arcsec_per_hour >= min_rate_arcsec_hr]


def deduplicate_tracklets(tracklets: list[Tracklet]) -> list[Tracklet]:
    """Remove tracklets that substantially overlap a longer-arc tracklet.

    Two tracklets overlap when they share ≥ 50 % of obs_ids relative to the
    shorter one.  The longer-arc tracklet is kept; ties are broken by the order
    in the input list (earlier wins).
    """
    sorted_t = sorted(tracklets, key=lambda t: (-t.arc_days, -len(t.observations)))
    kept: list[Tracklet] = []
    kept_ids: list[set[str]] = []
    for tracklet in sorted_t:
        ids = {obs.obs_id for obs in tracklet.observations}
        n = len(ids)
        duplicate = False
        for existing_ids in kept_ids:
            overlap = len(ids & existing_ids)
            if n > 0 and overlap / n >= 0.5:
                duplicate = True
                break
        if not duplicate:
            kept.append(tracklet)
            kept_ids.append(ids)
    return kept


def split_tracklet(tracklet: Tracklet, split_jd: float) -> tuple[Tracklet, Tracklet]:
    """Split a tracklet at *split_jd* into two sub-tracklets.

    Observations with jd < split_jd go into the first tracklet; observations
    with jd >= split_jd go into the second.  Each sub-tracklet recomputes its
    own arc length, motion rate, and position angle from its constituent
    observations.

    Raises :exc:`ValueError` if either side would have fewer than 2 observations.
    """
    before = [obs for obs in tracklet.observations if obs.jd < split_jd]
    after = [obs for obs in tracklet.observations if obs.jd >= split_jd]

    if len(before) < 2:
        raise ValueError(
            f"split_jd={split_jd} leaves fewer than 2 observations in the "
            f"first sub-tracklet ({len(before)} found)"
        )
    if len(after) < 2:
        raise ValueError(
            f"split_jd={split_jd} leaves fewer than 2 observations in the "
            f"second sub-tracklet ({len(after)} found)"
        )

    def _build(obs_list: list[Observation], suffix: str) -> Tracklet:
        sorted_obs = sorted(obs_list, key=lambda o: o.jd)
        arc = sorted_obs[-1].jd - sorted_obs[0].jd
        rate, pa = _motion(*sorted_obs[:2]) if len(sorted_obs) >= 2 else (0.0, 0.0)
        return Tracklet(
            object_id=f"{tracklet.object_id}_{suffix}",
            observations=tuple(sorted_obs),
            arc_days=arc,
            motion_rate_arcsec_per_hour=rate,
            motion_pa_degrees=pa,
        )

    return _build(before, "A"), _build(after, "B")


def compute_arc_statistics(tracklet) -> dict:
    """Compute a summary statistics dict for a tracklet.

    Returns a dict with keys:
      ``n_observations``        — total observation count
      ``n_nights``              — number of distinct integer JD nights
      ``arc_days``              — time span from first to last observation
      ``mean_motion_arcsec_hr`` — mean apparent motion rate in arcsec/hr
      ``motion_pa_std_deg``     — standard deviation of pairwise position angles (deg)
    """
    obs = sorted(tracklet.observations, key=lambda o: o.jd)
    n_obs = len(obs)
    nights = len({int(o.jd) for o in obs})
    arc = obs[-1].jd - obs[0].jd if n_obs >= 2 else 0.0

    rates: list[float] = []
    pas: list[float] = []
    for i in range(len(obs) - 1):
        o1, o2 = obs[i], obs[i + 1]
        dt_hr = (o2.jd - o1.jd) * 24.0
        if dt_hr < 1e-6:
            continue
        cos_dec = math.cos(math.radians((o1.dec_deg + o2.dec_deg) / 2.0))
        d_ra = (o2.ra_deg - o1.ra_deg) * 3600.0 * cos_dec
        d_dec = (o2.dec_deg - o1.dec_deg) * 3600.0
        sep = math.hypot(d_ra, d_dec)
        rates.append(sep / dt_hr)
        pas.append(math.degrees(math.atan2(d_ra, d_dec)) % 360.0)

    mean_rate = float(np.mean(rates)) if rates else 0.0
    pa_std = float(np.std(pas)) if len(pas) >= 2 else 0.0

    return {
        "n_observations": n_obs,
        "n_nights": nights,
        "arc_days": round(arc, 4),
        "mean_motion_arcsec_hr": round(mean_rate, 4),
        "motion_pa_std_deg": round(pa_std, 4),
    }


def assess_link_confidence(tracklet: object) -> float:
    """Confidence score [0, 1] for a linked tracklet based on residual quality.

    Fits a linear model to RA(t) and Dec(t) separately and computes the RMS
    residual in arcsec.  Confidence = max(0, 1 - rms / 10.0), so an RMS of 0
    arcsec → 1.0 and an RMS ≥ 10 arcsec → 0.0.
    Returns 0.0 when the tracklet has fewer than 2 observations.
    """
    obs = list(getattr(tracklet, "observations", []))
    if len(obs) < 2:
        return 0.0

    jds = np.array([o.jd for o in obs], dtype=np.float64)
    ras = np.array([o.ra_deg for o in obs], dtype=np.float64)
    decs = np.array([o.dec_deg for o in obs], dtype=np.float64)

    # Convert RA/Dec residuals to arcsec
    t = jds - jds[0]
    ones = np.ones_like(t)
    A = np.column_stack([ones, t])
    ra_fit = np.linalg.lstsq(A, ras, rcond=None)[0]
    dec_fit = np.linalg.lstsq(A, decs, rcond=None)[0]
    ra_res = (ras - A @ ra_fit) * 3600.0
    dec_res = (decs - A @ dec_fit) * 3600.0
    rms = float(np.sqrt(np.mean(ra_res ** 2 + dec_res ** 2)))
    return round(max(0.0, 1.0 - rms / 10.0), 4)


def compute_tracklet_grade(tracklet: object) -> str:
    """Quality grade for a linked tracklet: 'A', 'B', 'C', or 'D'.

    Grade criteria (all must be satisfied to achieve a given grade):

    =========  ========  =========  ================
    Grade      arc_days  n_nights   rms_arcsec
    =========  ========  =========  ================
    A          ≥ 7       ≥ 3        ≤ 0.5
    B          ≥ 2       ≥ 2        ≤ 2.0
    C          ≥ 0.5     ≥ 2        ≤ 5.0
    D          anything  else       else
    =========  ========  =========  ================

    Uses ``assess_link_confidence`` to derive the RMS residual (rms = (1 - conf) * 10).
    """
    stats = compute_arc_statistics(tracklet)
    arc = stats["arc_days"]
    nights = stats["n_nights"]
    conf = assess_link_confidence(tracklet)
    rms = (1.0 - conf) * 10.0  # inverse of confidence formula

    if arc >= 7.0 and nights >= 3 and rms <= 0.5:
        return "A"
    if arc >= 2.0 and nights >= 2 and rms <= 2.0:
        return "B"
    if arc >= 0.5 and nights >= 2 and rms <= 5.0:
        return "C"
    return "D"


def filter_by_arc_length(tracklets: list, min_arc_days: float = 1.0) -> list:
    """Filter tracklets by minimum arc length.

    Returns a new list containing only tracklets whose ``arc_days`` attribute
    is at least ``min_arc_days``.  The input list is not modified.

    Args:
        tracklets: List of Tracklet objects (or duck-typed equivalents).
        min_arc_days: Minimum arc length in days (inclusive). Default 1.0.

    Returns:
        Filtered list of tracklets satisfying the arc-length criterion.
    """
    return [t for t in tracklets if getattr(t, "arc_days", 0.0) >= min_arc_days]


def summarize_arc_statistics(tracklets: list) -> dict:
    """Aggregate arc-length statistics across a list of tracklets.

    Args:
        tracklets: List of :class:`~schemas.Tracklet` objects.

    Returns:
        Dict with keys:
          - ``"n_tracklets"``: total count.
          - ``"mean_arc_days"``: mean arc length in days (0.0 if empty).
          - ``"max_arc_days"``: maximum arc length in days (0.0 if empty).
          - ``"fraction_multi_night"``: fraction of tracklets spanning >1 night.
    """
    if not tracklets:
        return {
            "n_tracklets": 0,
            "mean_arc_days": 0.0,
            "max_arc_days": 0.0,
            "fraction_multi_night": 0.0,
        }
    arcs = [getattr(t, "arc_days", 0.0) for t in tracklets]
    multi_night = sum(1 for t in tracklets if _count_nights(t) > 1)
    return {
        "n_tracklets": len(tracklets),
        "mean_arc_days": round(float(np.mean(arcs)), 4),
        "max_arc_days": round(float(np.max(arcs)), 4),
        "fraction_multi_night": round(multi_night / len(tracklets), 4),
    }


def _count_nights(tracklet) -> int:
    """Count distinct integer JD nights in a tracklet."""
    return len({int(o.jd) for o in getattr(tracklet, "observations", [])})


def filter_by_nights_observed(tracklets: list, min_nights: int = 2) -> list:
    """Keep only tracklets that span at least *min_nights* distinct calendar nights.

    A "night" is defined as a distinct integer Julian Date (``int(obs.jd)``).
    Tracklets with fewer than *min_nights* distinct nights are discarded.

    Args:
        tracklets: List of :class:`~schemas.Tracklet` objects.
        min_nights: Minimum number of distinct nights required (default 2).

    Returns:
        Filtered list of tracklets.
    """
    return [t for t in tracklets if _count_nights(t) >= min_nights]


def merge_overlapping_tracklets(tracklets: list) -> list:
    """Merge tracklets that share at least one common observation ID.

    Uses a union-find approach: any pair sharing ≥1 ``obs_id`` is merged into
    a single tracklet.  The merged tracklet takes the ``object_id`` of the
    longer-arc member, deduplicates observations (by ``obs_id``), and
    recomputes ``arc_days``, ``motion_rate_arcsec_per_hour``, and
    ``motion_pa_degrees`` from the merged observation set.

    Args:
        tracklets: List of :class:`~schemas.Tracklet` objects.

    Returns:
        New list of tracklets with overlapping ones merged.
    """
    from schemas import Tracklet

    if not tracklets:
        return []

    # Build obs_id → tracklet index map
    obs_to_idx: dict = {}
    for i, t in enumerate(tracklets):
        for o in t.observations:
            if o.obs_id not in obs_to_idx:
                obs_to_idx[o.obs_id] = i

    # Union-Find
    parent = list(range(len(tracklets)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    for i, t in enumerate(tracklets):
        for o in t.observations:
            j = obs_to_idx.get(o.obs_id, i)
            if j != i:
                union(i, j)

    # Group by root
    groups: dict = {}
    for i in range(len(tracklets)):
        root = find(i)
        groups.setdefault(root, []).append(i)

    merged: list = []
    for indices in groups.values():
        if len(indices) == 1:
            merged.append(tracklets[indices[0]])
            continue
        # Pick representative (longest arc)
        rep = max(indices, key=lambda i: tracklets[i].arc_days)
        # Merge observations (deduplicate by obs_id)
        seen_ids: set = set()
        all_obs = []
        for i in sorted(indices, key=lambda i: -tracklets[i].arc_days):
            for o in tracklets[i].observations:
                if o.obs_id not in seen_ids:
                    seen_ids.add(o.obs_id)
                    all_obs.append(o)
        all_obs.sort(key=lambda o: o.jd)
        arc = all_obs[-1].jd - all_obs[0].jd if len(all_obs) >= 2 else 0.0
        rate = tracklets[rep].motion_rate_arcsec_per_hour
        pa = tracklets[rep].motion_pa_degrees
        merged.append(Tracklet(
            object_id=tracklets[rep].object_id,
            observations=tuple(all_obs),
            arc_days=arc,
            motion_rate_arcsec_per_hour=rate,
            motion_pa_degrees=pa,
        ))
    return merged


def validate_tracklet(tracklet: object) -> tuple[bool, list[str]]:
    """Check a tracklet for internal consistency.

    Validates that:
    - There are at least 2 observations.
    - ``arc_days`` is non-negative.
    - ``motion_rate_arcsec_per_hour`` is non-negative.
    - Observations are sorted in ascending JD order.
    - All ``obs_id`` values are unique.

    Args:
        tracklet: A :class:`~schemas.Tracklet` object.

    Returns:
        Tuple of ``(is_valid, reasons)`` where ``is_valid`` is ``True`` when
        all checks pass and ``reasons`` is a list of failure descriptions
        (empty when valid).
    """
    reasons: list[str] = []

    obs = getattr(tracklet, "observations", ())
    if len(obs) < 2:
        reasons.append(f"fewer than 2 observations ({len(obs)} found)")

    arc = getattr(tracklet, "arc_days", None)
    if arc is not None and arc < 0.0:
        reasons.append(f"arc_days is negative ({arc})")

    rate = getattr(tracklet, "motion_rate_arcsec_per_hour", None)
    if rate is not None and rate < 0.0:
        reasons.append(f"motion_rate_arcsec_per_hour is negative ({rate})")

    if len(obs) >= 2:
        jds = [o.jd for o in obs]
        if jds != sorted(jds):
            reasons.append("observations are not sorted by ascending JD")

        obs_ids = [o.obs_id for o in obs]
        if len(obs_ids) != len(set(obs_ids)):
            reasons.append("duplicate obs_id values found")

    return (len(reasons) == 0, reasons)


def compute_great_circle_residual(tracklet: object) -> float | None:
    """Fit a great-circle (linear RA/Dec) model and return RMS positional residual.

    Performs independent linear (polyfit degree-1) fits to (JD, RA) and
    (JD, Dec), then computes the RMS of the vector residuals in arcsec.
    RA residuals are cos-Dec corrected.

    Args:
        tracklet: A :class:`~schemas.Tracklet` object.

    Returns:
        RMS residual in arcsec, or ``None`` for fewer than 2 observations.
    """
    obs = getattr(tracklet, "observations", ())
    if len(obs) < 2:
        return None

    jds = np.array([o.jd for o in obs], dtype=float)
    ras = np.array([o.ra_deg for o in obs], dtype=float)
    decs = np.array([o.dec_deg for o in obs], dtype=float)
    mean_dec_rad = float(np.mean(decs)) * math.pi / 180.0
    cos_dec = math.cos(mean_dec_rad)

    # Linear fits
    ra_coeff = np.polyfit(jds, ras, 1)
    dec_coeff = np.polyfit(jds, decs, 1)

    ra_pred = np.polyval(ra_coeff, jds)
    dec_pred = np.polyval(dec_coeff, jds)

    dra_arcsec = (ras - ra_pred) * 3600.0 * cos_dec
    ddec_arcsec = (decs - dec_pred) * 3600.0

    rms = float(np.sqrt(np.mean(dra_arcsec ** 2 + ddec_arcsec ** 2)))
    return round(rms, 6)


def compute_position_angle_consistency(tracklet: object) -> float | None:
    """Compute the standard deviation of position angles across consecutive observation pairs.

    A low value indicates nearly linear (constant-direction) motion; a high
    value suggests curved motion or measurement scatter.  Useful as a feature
    for artifact rejection and orbit quality estimation.

    Args:
        tracklet: A :class:`~schemas.Tracklet`-like object with an
            ``observations`` attribute containing at least 2 observations.

    Returns:
        Standard deviation of position angles in degrees, or ``None`` if fewer
        than 2 observations are present or all pairs have zero separation.
    """
    import math

    import numpy as np

    obs = list(getattr(tracklet, "observations", ()))
    if len(obs) < 2:
        return None

    pas: list[float] = []
    for i in range(len(obs) - 1):
        o1, o2 = obs[i], obs[i + 1]
        dt = o2.jd - o1.jd
        if dt == 0.0:
            continue
        cos_dec = math.cos(math.radians((o1.dec_deg + o2.dec_deg) / 2.0))
        dra = (o2.ra_deg - o1.ra_deg) * cos_dec * 3600.0
        ddec = (o2.dec_deg - o1.dec_deg) * 3600.0
        if dra == 0.0 and ddec == 0.0:
            continue
        pa = math.degrees(math.atan2(dra, ddec)) % 360.0
        pas.append(pa)

    if len(pas) < 2:
        return None
    return round(float(np.std(pas, ddof=0)), 4)


def score_tracklet_quality(tracklet: object) -> float:
    """Compute a scalar quality score in [0, 1] for a linked tracklet.

    Combines three components:
    - **Grade score**: A=1.0, B=0.75, C=0.5, D=0.25 (weight 0.4)
    - **Arc score**: min(1.0, arc_days / 7.0) (weight 0.3)
    - **Link confidence**: from :func:`assess_link_confidence` (weight 0.3)

    Args:
        tracklet: A :class:`~schemas.Tracklet` object.

    Returns:
        Quality score rounded to 4 decimal places, in [0, 1].
    """
    grade = compute_tracklet_grade(tracklet)
    grade_map = {"A": 1.0, "B": 0.75, "C": 0.5, "D": 0.25}
    grade_score = grade_map.get(grade, 0.25)

    arc_days = float(getattr(tracklet, "arc_days", 0.0))
    arc_score = min(1.0, arc_days / 7.0)

    link_confidence = assess_link_confidence(tracklet)

    quality = 0.4 * grade_score + 0.3 * arc_score + 0.3 * link_confidence
    return round(float(quality), 4)


def compute_night_span(tracklet: object) -> int:
    """Count distinct integer-JD nights covered by a tracklet's observations.

    Args:
        tracklet: A :class:`~schemas.Tracklet` object.

    Returns:
        Number of distinct nights (≥ 0).
    """
    obs = list(getattr(tracklet, "observations", ()))
    if not obs:
        return 0
    return len({int(o.jd) for o in obs})


def compute_tracklet_velocity_dispersion(tracklet: object) -> float | None:
    """Compute the standard deviation of consecutive inter-observation speeds.

    For each consecutive pair of observations in the tracklet the apparent
    motion rate (arcsec/hr, cosine-Dec corrected) is computed.  The standard
    deviation of those rates is returned as a measure of velocity uniformity.

    A low value (near 0) indicates uniform linear motion — consistent with a
    real solar system object.  A high value indicates acceleration or
    inconsistent observations.

    Returns ``None`` when fewer than 3 observations are available (need at
    least 2 consecutive pairs to compute a meaningful dispersion).

    Args:
        tracklet: A :class:`~schemas.Tracklet` object.

    Returns:
        Standard deviation of consecutive speeds in arcsec/hr, rounded to
        4 decimal places, or ``None`` for <3 observations.
    """
    import math

    obs = list(getattr(tracklet, "observations", ()))
    if len(obs) < 3:
        return None

    rates: list[float] = []
    for i in range(len(obs) - 1):
        o1, o2 = obs[i], obs[i + 1]
        dt_days = float(o2.jd) - float(o1.jd)
        if dt_days == 0.0:
            continue
        dt_hours = dt_days * 24.0
        cos_dec = math.cos(math.radians((float(o1.dec_deg) + float(o2.dec_deg)) / 2.0))
        dra = (float(o2.ra_deg) - float(o1.ra_deg)) * 3600.0 * cos_dec
        ddec = (float(o2.dec_deg) - float(o1.dec_deg)) * 3600.0
        rate = math.sqrt(dra**2 + ddec**2) / abs(dt_hours)
        rates.append(rate)

    if len(rates) < 2:
        return None

    mean_rate = sum(rates) / len(rates)
    variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates)
    return round(math.sqrt(variance), 4)


def compute_inter_night_gaps(tracklet: object) -> list[float]:
    """Return the list of inter-night gaps in days between distinct observing nights.

    An observing night is identified by the integer floor of the Julian Date
    (JD) of each observation.  Nights are sorted chronologically and gaps are
    computed between consecutive distinct nights.

    Returns an empty list when the tracklet spans fewer than two distinct
    nights.
    """
    obs = list(getattr(tracklet, "observations", ()))
    nights = sorted({int(float(getattr(o, "jd", 0.0))) for o in obs})
    if len(nights) < 2:
        return []
    return [round(float(nights[i + 1] - nights[i]), 4) for i in range(len(nights) - 1)]


def filter_by_motion_rate(
    tracklets: list,
    min_rate_arcsec_hr: float = 0.0,
    max_rate_arcsec_hr: float = 60.0,
) -> list:
    """Return tracklets whose motion rate is within *[min_rate, max_rate]*.

    Uses the ``motion_rate_arcsec_per_hour`` attribute of each tracklet.
    Tracklets missing this attribute are excluded.  Both bounds are
    inclusive.
    """
    result = []
    for t in tracklets:
        rate = getattr(t, "motion_rate_arcsec_per_hour", None)
        if rate is None:
            continue
        if min_rate_arcsec_hr <= float(rate) <= max_rate_arcsec_hr:
            result.append(t)
    return result


def compute_tracklet_arc_nights(tracklet: object) -> list[int]:
    """Return the sorted list of distinct integer-JD nights in the tracklet.

    Each night is the ``int()`` truncation of the observation JD.  The list
    is sorted in ascending order and contains no duplicates.
    """
    observations = getattr(tracklet, "observations", ()) or ()
    nights: set[int] = set()
    for obs in observations:
        jd = getattr(obs, "jd", None)
        if jd is not None:
            nights.add(int(float(jd)))
    return sorted(nights)


def compute_mean_consecutive_motion(tracklet: object) -> float | None:
    """Return the mean of consecutive pairwise motion rates in arcsec/hr.

    Computes the apparent motion rate between each consecutive pair of
    observations (sorted by JD) and returns the arithmetic mean.  Returns
    None when fewer than two observations are present or all pairs have
    identical JDs.
    """
    observations = sorted(
        getattr(tracklet, "observations", ()) or (),
        key=lambda o: float(getattr(o, "jd", 0.0)),
    )
    if len(observations) < 2:
        return None
    rates: list[float] = []
    for obs1, obs2 in zip(observations, observations[1:]):
        dt_hr = (float(getattr(obs2, "jd", 0.0)) - float(getattr(obs1, "jd", 0.0))) * 24.0
        if dt_hr <= 0.0:
            continue
        dec1 = float(getattr(obs1, "dec_deg", 0.0))
        dec2 = float(getattr(obs2, "dec_deg", 0.0))
        cos_dec = math.cos(math.radians((dec1 + dec2) / 2.0))
        ra1 = float(getattr(obs1, "ra_deg", 0.0))
        ra2 = float(getattr(obs2, "ra_deg", 0.0))
        d_ra = (ra2 - ra1) * 3600.0 * cos_dec
        d_dec = (dec2 - dec1) * 3600.0
        rates.append(math.hypot(d_ra, d_dec) / dt_hr)
    if not rates:
        return None
    return round(sum(rates) / len(rates), 6)


def compute_tracklet_sky_density(
    tracklets: list,
    radius_deg: float = 1.0,
) -> list[dict]:
    """Count how many tracklets have centroids within *radius_deg* of each other.

    Returns a list of dicts with keys ``object_id`` and ``n_neighbors``,
    one per input tracklet, in the same order.
    """
    centroids: list[tuple[float, float, str]] = []
    for t in tracklets:
        obs = getattr(t, "observations", ()) or ()
        if not obs:
            oid = getattr(t, "object_id", "unknown")
            centroids.append((0.0, 0.0, oid))
            continue
        ras = [float(getattr(o, "ra_deg", 0.0)) for o in obs]
        decs = [float(getattr(o, "dec_deg", 0.0)) for o in obs]
        oid = getattr(t, "object_id", "unknown")
        centroids.append((sum(ras) / len(ras), sum(decs) / len(decs), oid))

    results: list[dict] = []
    for i, (ra1, dec1, oid1) in enumerate(centroids):
        count = 0
        for j, (ra2, dec2, _) in enumerate(centroids):
            if i == j:
                continue
            sep = _sep_arcsec(ra1, dec1, ra2, dec2) / 3600.0
            if sep <= radius_deg:
                count += 1
        results.append({"object_id": oid1, "n_neighbors": count})
    return results


def compute_tracklet_completeness(tracklet: object, expected_nights: int) -> float:
    """Return the fraction of expected nights on which the tracklet has observations.

    Counts distinct calendar nights (integer part of JD) covered by the
    tracklet and divides by *expected_nights*.  Returns 0.0 when
    *expected_nights* ≤ 0.

    Args:
        tracklet: Object with an ``observations`` attribute (iterable of obs with ``jd``).
        expected_nights: Total number of nights expected (positive integer).

    Returns:
        Fraction of expected nights covered, in [0, 1].
    """
    if expected_nights <= 0:
        return 0.0
    observations = getattr(tracklet, "observations", ()) or ()
    nights: set[int] = set()
    for obs in observations:
        jd = getattr(obs, "jd", None)
        if jd is not None:
            nights.add(int(float(jd)))
    return round(min(1.0, len(nights) / expected_nights), 6)


def find_longest_tracklet(tracklets: list) -> object | None:
    """Return the tracklet with the largest arc_days.

    Returns None if the list is empty.  If multiple tracklets share the
    maximum arc_days, the first one encountered is returned.
    """
    if not tracklets:
        return None
    return max(tracklets, key=lambda t: float(getattr(t, "arc_days", 0.0) or 0.0))


def compute_tracklet_motion_scatter(tracklet: object) -> float | None:
    """Compute the standard deviation of pairwise motion rates (arcsec/hr).

    Computes the apparent motion rate between each consecutive pair of
    observations (sorted by JD) and returns the standard deviation of those
    rates.  Returns None if fewer than 3 observations are available (need at
    least 2 consecutive pairs) or if all time differences are zero.
    """
    import math

    observations = getattr(tracklet, "observations", ()) or ()
    obs_sorted = sorted(observations, key=lambda o: getattr(o, "jd", 0.0))
    if len(obs_sorted) < 3:
        return None
    rates: list[float] = []
    for i in range(len(obs_sorted) - 1):
        o1, o2 = obs_sorted[i], obs_sorted[i + 1]
        dt_hr = (float(getattr(o2, "jd", 0.0)) - float(getattr(o1, "jd", 0.0))) * 24.0
        if abs(dt_hr) < 1e-9:
            continue
        mid_dec = (
            float(getattr(o1, "dec_deg", 0.0)) + float(getattr(o2, "dec_deg", 0.0))
        ) / 2.0
        cos_dec = math.cos(math.radians(mid_dec))
        dra = (
            (float(getattr(o2, "ra_deg", 0.0)) - float(getattr(o1, "ra_deg", 0.0)))
            * 3600.0
            * cos_dec
        )
        ddec = (float(getattr(o2, "dec_deg", 0.0)) - float(getattr(o1, "dec_deg", 0.0))) * 3600.0
        rates.append(math.hypot(dra, ddec) / abs(dt_hr))
    if len(rates) < 2:
        return None
    mean_rate = sum(rates) / len(rates)
    variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates)
    return round(math.sqrt(variance), 6)


def compute_great_circle_arc(tracklet: object) -> float:
    """Compute the total great-circle arc length of a tracklet in arcseconds.

    Sums the angular separation between each consecutive pair of observations
    (sorted by JD).  Returns 0.0 for fewer than 2 observations.
    """
    import math

    observations = getattr(tracklet, "observations", ()) or ()
    obs_sorted = sorted(observations, key=lambda o: getattr(o, "jd", 0.0))
    if len(obs_sorted) < 2:
        return 0.0
    total_arcsec = 0.0
    for i in range(len(obs_sorted) - 1):
        o1, o2 = obs_sorted[i], obs_sorted[i + 1]
        ra1 = math.radians(float(getattr(o1, "ra_deg", 0.0)))
        dec1 = math.radians(float(getattr(o1, "dec_deg", 0.0)))
        ra2 = math.radians(float(getattr(o2, "ra_deg", 0.0)))
        dec2 = math.radians(float(getattr(o2, "dec_deg", 0.0)))
        cos_angle = (
            math.sin(dec1) * math.sin(dec2)
            + math.cos(dec1) * math.cos(dec2) * math.cos(ra2 - ra1)
        )
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle_rad = math.acos(cos_angle)
        total_arcsec += math.degrees(angle_rad) * 3600.0
    return round(total_arcsec, 6)


def compute_arc_curvature(tracklet: object) -> float:
    """Compute the RMS quadratic residual of the arc in arcsec.

    Fits a quadratic polynomial to RA (cos-Dec-corrected) and Dec vs time,
    then returns the RMS of the residuals from the best-fit *linear* model.
    A value close to 0 indicates straight-line motion; a larger value
    indicates curvature (non-inertial apparent motion).

    Returns ``0.0`` for fewer than 3 observations.
    """
    try:
        import math

        import numpy as np

        obs_list = list(getattr(tracklet, "observations", []))
        obs_list = sorted(obs_list, key=lambda o: o.jd)
        if len(obs_list) < 3:
            return 0.0
        t = np.array([o.jd for o in obs_list], dtype=float)
        ra = np.array([o.ra_deg for o in obs_list], dtype=float)
        dec = np.array([o.dec_deg for o in obs_list], dtype=float)
        mid_dec = float(np.mean(dec))
        cos_dec = math.cos(math.radians(mid_dec))
        ra_corr = ra * cos_dec
        t0 = t[0]
        dt = t - t0
        # Linear fit residuals
        A_lin = np.column_stack([dt, np.ones_like(dt)])
        res_ra = ra_corr - A_lin @ np.linalg.lstsq(A_lin, ra_corr, rcond=None)[0]
        res_dec = dec - A_lin @ np.linalg.lstsq(A_lin, dec, rcond=None)[0]
        rms = float(np.sqrt(np.mean(res_ra**2 + res_dec**2))) * 3600.0
        return round(rms, 6)
    except Exception:
        return 0.0


def compute_tracklet_density(tracklets: list, radius_deg: float = 1.0) -> list[int]:
    """Count how many other tracklets have their first observation within radius_deg.

    For each tracklet, counts how many *other* tracklets have their first
    observation within ``radius_deg`` of this tracklet's first observation
    (great-circle distance, haversine formula).

    Args:
        tracklets: List of Tracklet objects or objects with an ``observations``
            attribute (sequence of observations with ``ra_deg``/``dec_deg`` or
            ``ra``/``dec`` attributes).
        radius_deg: Search radius in degrees (default 1.0).

    Returns:
        List of counts, one per tracklet.  Returns ``[]`` for empty input.
    """
    if not tracklets:
        return []

    def _first_radec(t: object) -> tuple[float, float] | None:
        obs_list = list(getattr(t, "observations", []))
        if not obs_list:
            return None
        obs0 = obs_list[0]
        ra = getattr(obs0, "ra_deg", None)
        if ra is None:
            ra = getattr(obs0, "ra", None)
        dec = getattr(obs0, "dec_deg", None)
        if dec is None:
            dec = getattr(obs0, "dec", None)
        if ra is None or dec is None:
            return None
        return float(ra), float(dec)

    def _haversine_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
        lat1 = math.radians(dec1)
        lat2 = math.radians(dec2)
        dlat = lat2 - lat1
        dlon = math.radians(ra2 - ra1)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return math.degrees(2 * math.asin(math.sqrt(min(1.0, a))))

    positions = [_first_radec(t) for t in tracklets]
    counts: list[int] = []
    n = len(tracklets)
    for i in range(n):
        count = 0
        if positions[i] is not None:
            ra_i, dec_i = positions[i]
            for j in range(n):
                if i == j:
                    continue
                if positions[j] is not None:
                    ra_j, dec_j = positions[j]
                    if _haversine_deg(ra_i, dec_i, ra_j, dec_j) <= radius_deg:
                        count += 1
        counts.append(count)
    return counts


def compute_position_residuals(tracklet: Tracklet) -> list[float]:
    """Compute per-observation position residuals from a linear motion fit.

    Fits linear models RA(t) and Dec(t) using :func:`numpy.polyfit` (degree 1)
    and returns the per-observation residuals in arcseconds as
    ``sqrt(dRA_cos_dec² + dDec²)``.  The RA residual is Dec-corrected by
    multiplying the raw RA difference by ``cos(mean_dec_rad)``.

    Returns an empty list for tracklets with fewer than 2 observations or on
    any error.

    Args:
        tracklet: :class:`~schemas.Tracklet` object.

    Returns:
        List of residuals (arcsec) per observation, or ``[]`` on failure.
    """
    try:
        obs_list = list(tracklet.observations)
        if len(obs_list) < 2:
            return []
        jds = np.array([o.jd for o in obs_list], dtype=float)
        ras = np.array([o.ra_deg for o in obs_list], dtype=float)
        decs = np.array([o.dec_deg for o in obs_list], dtype=float)
        mean_dec_rad = math.radians(float(np.mean(decs)))
        cos_dec = math.cos(mean_dec_rad)
        ra_fit = np.polyfit(jds, ras, 1)
        dec_fit = np.polyfit(jds, decs, 1)
        ra_pred = np.polyval(ra_fit, jds)
        dec_pred = np.polyval(dec_fit, jds)
        dra_arcsec = (ras - ra_pred) * cos_dec * 3600.0
        ddec_arcsec = (decs - dec_pred) * 3600.0
        residuals = np.sqrt(dra_arcsec ** 2 + ddec_arcsec ** 2)
        return [float(r) for r in residuals]
    except Exception:
        return []


def compute_inter_observation_gaps(tracklet: Tracklet) -> list[float]:
    """Return the time gaps in hours between consecutive observations.

    Sorts observations by Julian Date (ascending) and computes the difference
    in hours between each successive pair.

    Args:
        tracklet: :class:`~schemas.Tracklet` object.

    Returns:
        List of time gaps in hours between consecutive observations, sorted by
        observation JD.  Returns an empty list for tracklets with fewer than
        2 observations.
    """
    obs_list = sorted(tracklet.observations, key=lambda o: o.jd)
    if len(obs_list) < 2:
        return []
    gaps: list[float] = []
    for i in range(len(obs_list) - 1):
        gap_hours = (obs_list[i + 1].jd - obs_list[i].jd) * 24.0
        gaps.append(float(gap_hours))
    return gaps


def compute_tracklet_overlap_fraction(t1: Tracklet, t2: Tracklet) -> float:
    """Return the fraction of shared obs_ids between two tracklets.

    The overlap fraction is computed as the number of ``obs_id`` values shared
    by both tracklets divided by the size of the *smaller* tracklet.  Returns
    ``0.0`` if either tracklet has no observations.

    Args:
        t1: First :class:`~schemas.Tracklet`.
        t2: Second :class:`~schemas.Tracklet`.

    Returns:
        Overlap fraction in [0, 1].
    """
    ids1 = {o.obs_id for o in t1.observations}
    ids2 = {o.obs_id for o in t2.observations}
    if not ids1 or not ids2:
        return 0.0
    shared = ids1 & ids2
    smaller = min(len(ids1), len(ids2))
    return float(len(shared)) / float(smaller)


def compute_velocity_dispersion(tracklets: list) -> float:
    """Return the standard deviation of motion rates across tracklets.

    Computes the population standard deviation of
    ``motion_rate_arcsec_per_hour`` over all supplied tracklets.  Returns
    ``0.0`` when fewer than 2 tracklets are provided or when all tracklets
    share the same motion rate.

    Args:
        tracklets: List of :class:`~schemas.Tracklet` objects (or any objects
            with a ``motion_rate_arcsec_per_hour`` attribute).

    Returns:
        Standard deviation of motion rates in arcsec/hour (float ≥ 0).
    """
    rates = [float(getattr(t, "motion_rate_arcsec_per_hour", 0.0)) for t in tracklets]
    if len(rates) < 2:
        return 0.0
    mean = sum(rates) / len(rates)
    variance = sum((r - mean) ** 2 for r in rates) / len(rates)
    return float(math.sqrt(variance))


def compute_tracklet_centroid(tracklet: object) -> dict[str, float] | None:
    """Compute the mean sky position (centroid) of a tracklet.

    Averages the RA and Dec of all observations in the tracklet in
    degree-space and returns a dict with keys ``"ra_deg"`` and ``"dec_deg"``.

    Args:
        tracklet: Object with an ``observations`` attribute (tuple/list of
            observation-like objects each having ``ra`` and ``dec`` in degrees).

    Returns:
        Dict with ``"ra_deg"`` and ``"dec_deg"`` (floats), or ``None`` if the
        tracklet has no observations (empty tuple/list).
    """
    observations = getattr(tracklet, "observations", None) or ()
    if not observations:
        return None
    ras = [float(getattr(obs, "ra", 0.0)) for obs in observations]
    decs = [float(getattr(obs, "dec", 0.0)) for obs in observations]
    return {"ra_deg": float(sum(ras) / len(ras)), "dec_deg": float(sum(decs) / len(decs))}


def compute_along_track_error(tracklet: object) -> float:
    """Compute the RMS of observation residuals projected along the motion PA.

    Fits linear models to RA(t) and Dec(t), computes the residuals for each
    observation, then projects each residual onto the along-track direction
    defined by the tracklet's motion position angle.  Returns the RMS of those
    along-track residuals in arcseconds.

    Args:
        tracklet: Object with ``observations``, ``motion_pa_degrees``, and
            ``motion_rate_arcsec_per_hour`` attributes.  Observations must have
            ``ra``, ``dec``, and ``jd`` attributes (all in degrees / Julian dates).

    Returns:
        Along-track RMS residual in arcseconds (float ≥ 0).  Returns ``0.0``
        for tracklets with fewer than 3 observations or on any exception.
    """
    try:
        import math

        import numpy as np

        observations = getattr(tracklet, "observations", None) or ()
        if len(observations) < 3:
            return 0.0

        pa_deg = getattr(tracklet, "motion_pa_degrees", 0.0) or 0.0
        pa_rad = math.radians(float(pa_deg))

        jds = np.array([float(getattr(obs, "jd", 0.0)) for obs in observations])
        ras = np.array([float(getattr(obs, "ra", 0.0)) for obs in observations])
        decs = np.array([float(getattr(obs, "dec", 0.0)) for obs in observations])

        # Fit linear RA(t) and Dec(t)
        ra_coeffs = np.polyfit(jds, ras, 1)
        dec_coeffs = np.polyfit(jds, decs, 1)

        ra_pred = np.polyval(ra_coeffs, jds)
        dec_pred = np.polyval(dec_coeffs, jds)

        # Residuals in arcsec
        dra_arcsec = (ras - ra_pred) * 3600.0
        ddec_arcsec = (decs - dec_pred) * 3600.0

        # Project onto along-track direction
        along = dra_arcsec * math.cos(pa_rad) + ddec_arcsec * math.sin(pa_rad)

        rms = float(np.sqrt(np.mean(along ** 2)))
        return rms
    except Exception:
        return 0.0


def compute_observation_rate(tracklet: object) -> float | None:
    """Return observations per distinct night for the tracklet.

    Returns None if the tracklet has no observations.
    """
    observations = getattr(tracklet, "observations", None) or ()
    if not observations:
        return None
    nights = {int(getattr(obs, "jd", 0.0)) for obs in observations}
    return float(len(observations)) / float(len(nights))


def compute_tracklet_brightness_trend(tracklet: object) -> float | None:
    """Return the linear slope of magnitude vs JD in mag/day.

    A positive slope means the object is fading; negative means brightening.
    Returns None if fewer than 2 observations have valid (non-sentinel) magnitudes.
    """
    observations = getattr(tracklet, "observations", None) or ()
    jds = []
    mags = []
    for obs in observations:
        mag = getattr(obs, "mag", None)
        if mag is None:
            continue
        m = float(mag)
        if m >= 90.0:
            continue
        jds.append(float(getattr(obs, "jd", 0.0)))
        mags.append(m)
    if len(jds) < 2:
        return None
    coeffs = np.polyfit(jds, mags, 1)
    return float(coeffs[0])


def compute_arc_endpoint_separation(tracklet: object) -> float | None:
    """Return the great-circle separation in arcsec between the first and last observations.

    Returns None if the tracklet has fewer than 2 observations.
    """
    observations = getattr(tracklet, "observations", None) or ()
    if len(observations) < 2:
        return None
    obs_sorted = sorted(observations, key=lambda o: float(getattr(o, "jd", 0.0)))
    o1, o2 = obs_sorted[0], obs_sorted[-1]
    ra1 = math.radians(float(getattr(o1, "ra_deg", 0.0)))
    dec1 = math.radians(float(getattr(o1, "dec_deg", 0.0)))
    ra2 = math.radians(float(getattr(o2, "ra_deg", 0.0)))
    dec2 = math.radians(float(getattr(o2, "dec_deg", 0.0)))
    cos_sep = (
        math.sin(dec1) * math.sin(dec2)
        + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    )
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep)) * 3600.0


def compute_pa_circular_std(tracklets: list) -> float | None:
    """Return the circular standard deviation of motion position angles across tracklets.

    Uses the mean-resultant-vector formula: σ = sqrt(-2 * ln(R̄)) where
    R̄ = |Σ exp(i·θ)| / N.  Angles are taken from tracklet.motion_pa_degrees.
    Returns None if fewer than 2 tracklets have a valid PA.
    """
    pas = []
    for t in tracklets:
        pa = getattr(t, "motion_pa_degrees", None)
        if pa is not None:
            pas.append(math.radians(float(pa)))
    if len(pas) < 2:
        return None
    sin_sum = sum(math.sin(a) for a in pas)
    cos_sum = sum(math.cos(a) for a in pas)
    r_bar = math.hypot(sin_sum, cos_sum) / len(pas)
    r_bar = min(r_bar, 1.0 - 1e-12)
    return float(math.degrees(math.sqrt(-2.0 * math.log(r_bar))))


def compute_sky_coverage_area(tracklets: list) -> float:
    """Return the approximate sky area covered by a list of tracklets in square degrees.

    Computes the bounding box (ΔRA × ΔDec) in degrees multiplied by cos(mean Dec)
    to account for the spherical projection.  Returns 0.0 if fewer than 2 tracklets
    have valid position data or if all positions are identical.

    Positions are taken from each tracklet's first observation (``observations[0]``).
    """
    ras: list[float] = []
    decs: list[float] = []
    for t in tracklets:
        obs_seq = getattr(t, "observations", None) or ()
        if not obs_seq:
            continue
        first = obs_seq[0]
        ra = getattr(first, "ra", None)
        dec = getattr(first, "dec", None)
        if ra is not None and dec is not None:
            ras.append(float(ra))
            decs.append(float(dec))
    if len(ras) < 2:
        return 0.0
    dra = max(ras) - min(ras)
    ddec = max(decs) - min(decs)
    mean_dec_rad = math.radians(sum(decs) / len(decs))
    return float(dra * math.cos(mean_dec_rad) * ddec)


def compute_night_gap_statistics(tracklets: list) -> dict:
    """Return statistics on inter-night gaps across a list of tracklets.

    For each tracklet, computes the gap (in integer nights) between consecutive
    observations.  Aggregates all gaps across all tracklets and returns:

      - ``mean_gap_nights``: mean inter-night gap (float) or ``None`` if no gaps
      - ``max_gap_nights``: maximum inter-night gap (int) or ``None`` if no gaps
      - ``n_tracklets``: number of tracklets examined

    A "night" is defined as the integer part of an observation's JD.
    Single-observation tracklets contribute no gaps.
    """
    all_gaps: list[int] = []
    for t in tracklets:
        obs_seq = getattr(t, "observations", None) or ()
        jds = [getattr(o, "jd", None) for o in obs_seq]
        nights_set = {int(float(j)) for j in jds if j is not None}
        nights = sorted(nights_set)
        for i in range(1, len(nights)):
            all_gaps.append(nights[i] - nights[i - 1])
    return {
        "mean_gap_nights": float(sum(all_gaps) / len(all_gaps)) if all_gaps else None,
        "max_gap_nights": max(all_gaps) if all_gaps else None,
        "n_tracklets": len(tracklets),
    }


def compute_field_tracklet_density(
    tracklets: list,
    field_radius_deg: float,
) -> float | None:
    """Return the number of tracklets per square degree for a circular survey field.

    Uses the solid-angle formula: Ω = 2π(1−cos(r)) steradians, converted to
    square degrees.  Returns ``None`` if *field_radius_deg* ≤ 0.

    Unlike :func:`compute_tracklet_sky_density` (which measures local crowding),
    this function treats *tracklets* as the complete set within the field and
    *field_radius_deg* as the field half-angle.
    """
    if field_radius_deg <= 0.0:
        return None
    r_rad = math.radians(abs(field_radius_deg))
    steradians = 2.0 * math.pi * (1.0 - math.cos(r_rad))
    sq_deg = steradians * (180.0 / math.pi) ** 2
    return float(len(tracklets) / sq_deg) if sq_deg > 0.0 else None


def estimate_observation_cadence(tracklet: object) -> float | None:
    """Return the mean time between consecutive observations in hours.

    Computes the mean of all consecutive observation time-deltas
    ``(jd[i+1] - jd[i]) * 24`` for the sorted observation sequence.
    Returns ``None`` if the tracklet has fewer than 2 observations or if
    observations cannot be accessed.
    """
    obs = getattr(tracklet, "observations", None)
    if not obs or len(obs) < 2:
        return None
    try:
        jds = sorted(float(o.jd) for o in obs)
    except Exception:
        return None
    deltas = [(jds[i + 1] - jds[i]) * 24.0 for i in range(len(jds) - 1)]
    return float(sum(deltas) / len(deltas))


def compute_tracklet_span_nights(tracklet: object) -> int:
    """Return the number of distinct integer nights spanned by a tracklet.

    Counts the number of unique ``int(floor(jd))`` values across all
    observations.  Returns 0 if the tracklet has no observations or if
    observations cannot be accessed.
    """
    import math

    obs = getattr(tracklet, "observations", None)
    if not obs:
        return 0
    try:
        nights = {int(math.floor(float(o.jd))) for o in obs}
    except Exception:
        return 0
    return len(nights)
