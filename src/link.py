"""Link stage — THOR-inspired tracklet linking across multiple nights."""

from __future__ import annotations

__all__ = ["link", "merge_tracklets", "_predict_from_arc"]

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
    pred_dec = float(max(-90.0, min(90.0, np.polyval(dec_coeffs, dt))))
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
