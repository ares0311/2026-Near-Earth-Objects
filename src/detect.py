"""Detect stage — moving object detection, real/bogus filter, MPC cross-match."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict

import numpy as np

from schemas import (
    DetectProvenance,
    DetectResult,
    KnownMatch,
    Observation,
    RawCandidate,
)

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

_REAL_BOGUS_THRESHOLD = 0.65  # ZTF rb score; configurable
_MOTION_MIN_ARCSEC_PER_HR = 0.01
_MOTION_MAX_ARCSEC_PER_HR = 60.0
_MPC_MATCH_RADIUS_ARCSEC = 5.0


# ---------------------------------------------------------------------------
# Angular distance helpers
# ---------------------------------------------------------------------------


def _angular_sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle separation in arcseconds."""
    r1, d1, r2, d2 = (math.radians(x) for x in (ra1, dec1, ra2, dec2))
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep)) * 3600.0


def _motion_rate_and_pa(
    obs1: Observation,
    obs2: Observation,
) -> tuple[float, float]:
    """Compute apparent motion rate (arcsec/hr) and position angle (deg)."""
    dt_hr = (obs2.jd - obs1.jd) * 24.0
    if abs(dt_hr) < 1e-6:
        return 0.0, 0.0
    cos_dec = math.cos(math.radians((obs1.dec_deg + obs2.dec_deg) / 2.0))
    d_ra_arcsec = (obs2.ra_deg - obs1.ra_deg) * 3600.0 * cos_dec
    d_dec_arcsec = (obs2.dec_deg - obs1.dec_deg) * 3600.0
    sep_arcsec = math.hypot(d_ra_arcsec, d_dec_arcsec)
    rate = sep_arcsec / abs(dt_hr)
    pa = math.degrees(math.atan2(d_ra_arcsec, d_dec_arcsec)) % 360.0
    return rate, pa


# ---------------------------------------------------------------------------
# Real/bogus filter
# ---------------------------------------------------------------------------


def _passes_real_bogus(obs: Observation, threshold: float) -> bool:
    """Return True if the observation passes the real/bogus threshold."""
    rb = obs.deep_real_bogus if obs.deep_real_bogus is not None else obs.real_bogus
    if rb is None:
        # No score available — pass conservatively (let downstream filters decide)
        return True
    return rb >= threshold


# ---------------------------------------------------------------------------
# Streak detection
# ---------------------------------------------------------------------------


def _is_streak(obs: Observation) -> bool:
    """Heuristic: a very elongated PSF in the difference cutout suggests a streak."""
    if obs.cutout_difference is None:
        return False
    try:
        import base64

        raw = base64.b64decode(obs.cutout_difference)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        # Compute elongation via image moments
        y, x = np.indices(arr.shape)
        total = float(arr.sum())
        if total <= 0:
            return False
        cx = float((x * arr).sum()) / total
        cy = float((y * arr).sum()) / total
        dx, dy = x - cx, y - cy
        mxx = float((dx**2 * arr).sum()) / total
        myy = float((dy**2 * arr).sum()) / total
        mxy = float((dx * dy * arr).sum()) / total
        trace = mxx + myy
        det = mxx * myy - mxy**2
        if det <= 0 or trace <= 0:
            return False
        disc = max(0.0, (trace / 2) ** 2 - det)
        lam1 = trace / 2 + math.sqrt(disc)
        lam2 = trace / 2 - math.sqrt(disc)
        elongation = lam1 / lam2 if lam2 > 0 else 1.0
        return elongation > 3.0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# MPC cross-match
# ---------------------------------------------------------------------------


def _load_mpc_ephemerides(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    jd: float,
) -> list[dict]:
    """Query MPC for known object ephemerides at a given epoch near a sky position."""
    try:
        from astroquery.mpc import MPC  # type: ignore[import]
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astropy.time import Time

        coord = SkyCoord(ra=ra_deg, dec=dec_deg, unit="deg")
        epoch = Time(jd, format="jd")
        result = MPC.get_ephemeris(
            target="Ceres",  # placeholder — real impl queries the region
            location="500",
            start=epoch,
            number=1,
            step="1h",
        )
        # Real implementation would iterate over all known NEOs/MBAs in field
        return []
    except Exception:
        return []


def _cross_match_mpc(
    obs: Observation,
    mpc_ephemerides: list[dict],
    match_radius_arcsec: float = _MPC_MATCH_RADIUS_ARCSEC,
) -> KnownMatch | None:
    """Return a KnownMatch if the observation is within radius of a known object."""
    for ephem in mpc_ephemerides:
        sep = _angular_sep_arcsec(obs.ra_deg, obs.dec_deg, ephem["ra"], ephem["dec"])
        if sep <= match_radius_arcsec:
            return KnownMatch(
                observation=obs,
                mpc_designation=ephem["designation"],
                separation_arcsec=sep,
                ephemeris_ra_deg=ephem["ra"],
                ephemeris_dec_deg=ephem["dec"],
            )
    return None


# ---------------------------------------------------------------------------
# Single-night candidate grouping
# ---------------------------------------------------------------------------


def _group_by_night(observations: tuple[Observation, ...]) -> dict[int, list[Observation]]:
    """Group observations by integer Julian Date night."""
    nights: dict[int, list[Observation]] = defaultdict(list)
    for obs in observations:
        night = int(obs.jd)
        nights[night].append(obs)
    return dict(nights)


def _find_moving_sources(
    night_obs: list[Observation],
    motion_min: float = _MOTION_MIN_ARCSEC_PER_HR,
    motion_max: float = _MOTION_MAX_ARCSEC_PER_HR,
) -> list[RawCandidate]:
    """Within a single night, pair observations that show solar-system-like motion."""
    candidates: list[RawCandidate] = []
    used: set[int] = set()

    for i, obs1 in enumerate(night_obs):
        if i in used:
            continue
        best_pair: list[Observation] = [obs1]
        best_rate: float | None = None
        best_pa: float | None = None

        for j, obs2 in enumerate(night_obs):
            if j <= i or j in used:
                continue
            rate, pa = _motion_rate_and_pa(obs1, obs2)
            if motion_min <= rate <= motion_max:
                best_pair.append(obs2)
                best_rate = rate
                best_pa = pa
                used.add(j)
                break  # simplification: take first valid pair per source

        if len(best_pair) >= 2:
            used.add(i)
            candidates.append(
                RawCandidate(
                    candidate_id=str(uuid.uuid4()),
                    observations=tuple(best_pair),
                    apparent_motion_arcsec_per_hr=best_rate,
                    motion_pa_deg=best_pa,
                    is_streak=any(_is_streak(o) for o in best_pair),
                )
            )

    return candidates


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def detect(
    sources: tuple[Observation, ...],
    real_bogus_threshold: float = _REAL_BOGUS_THRESHOLD,
    mpc_cross_match: bool = True,
) -> DetectResult:
    """Detect moving object candidates from a preprocessed source catalog.

    Steps:
    1. Apply real/bogus threshold filter
    2. Find pairs of observations with solar-system-compatible motion
    3. Flag streaks
    4. Cross-match against MPC known object ephemerides
    """
    # Step 1: real/bogus filter
    passing = [obs for obs in sources if _passes_real_bogus(obs, real_bogus_threshold)]

    # Step 2 & 3: find moving sources night by night
    all_candidates: list[RawCandidate] = []
    nights = _group_by_night(tuple(passing))
    for night_obs in nights.values():
        all_candidates.extend(_find_moving_sources(night_obs))

    # Step 4: MPC cross-match
    known_matches: list[KnownMatch] = []
    surviving_candidates: list[RawCandidate] = []

    if mpc_cross_match and all_candidates:
        # Use the centroid of the first candidate to query MPC for the field
        first_obs = all_candidates[0].observations[0]
        mpc_ephem = _load_mpc_ephemerides(
            first_obs.ra_deg, first_obs.dec_deg, radius_deg=1.0, jd=first_obs.jd
        )
    else:
        mpc_ephem = []

    for cand in all_candidates:
        matched = False
        for obs in cand.observations:
            km = _cross_match_mpc(obs, mpc_ephem)
            if km is not None:
                known_matches.append(km)
                matched = True
                break
        if not matched:
            surviving_candidates.append(cand)

    provenance = DetectProvenance(
        real_bogus_threshold=real_bogus_threshold,
        n_candidates=len(surviving_candidates),
        n_known_matches=len(known_matches),
    )
    return DetectResult(
        candidates=tuple(surviving_candidates),
        known_matches=tuple(known_matches),
        provenance=provenance,
    )
