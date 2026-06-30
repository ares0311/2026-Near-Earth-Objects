"""Detect stage — moving object detection, real/bogus filter, MPC cross-match."""

from __future__ import annotations

__all__ = [
    "detect",
    "compute_psf_fwhm",
    "compute_motion_vector",
    "filter_by_magnitude",
    "compute_source_compactness",
]

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
# Keep the discovery-stage floor aligned with adversarial review. Tracklets
# below 0.05 arcsec/hr are rejected as stationary/artifact-like before operator
# review, so admitting them here creates packets that cannot advance D1.
_MOTION_MIN_ARCSEC_PER_HR = 0.05
_MOTION_MAX_ARCSEC_PER_HR = 60.0
_MPC_MATCH_RADIUS_ARCSEC = 5.0
_DISCOVERY_ARCHIVE_MISSIONS = {"WISE", "DECam", "TESS"}


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
        from astropy.coordinates import SkyCoord
        from astropy.time import Time
        from astroquery.mpc import MPC  # type: ignore[import]

        SkyCoord(ra=ra_deg, dec=dec_deg, unit="deg")  # field centre (unused in placeholder)
        epoch = Time(jd, format="jd")
        MPC.get_ephemeris(
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


def _find_object_history_sources(
    observations: tuple[Observation, ...],
    motion_min: float = _MOTION_MIN_ARCSEC_PER_HR,
    motion_max: float = _MOTION_MAX_ARCSEC_PER_HR,
) -> list[RawCandidate]:
    """Preserve broker-provided same-object histories as moving candidates."""
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.field_id:
            grouped[str(obs.field_id)].append(obs)

    candidates: list[RawCandidate] = []
    for oid, history in grouped.items():
        obs_sorted = sorted(history, key=lambda obs: obs.jd)
        if len(obs_sorted) < 2:
            continue
        rate, pa = _motion_rate_and_pa(obs_sorted[0], obs_sorted[-1])
        if motion_min <= rate <= motion_max:
            candidates.append(
                RawCandidate(
                    candidate_id=oid,
                    observations=tuple(obs_sorted),
                    apparent_motion_arcsec_per_hr=rate,
                    motion_pa_deg=pa,
                    is_streak=any(_is_streak(o) for o in obs_sorted),
                )
            )
    return candidates


def _preserve_discovery_archive_singletons(
    observations: tuple[Observation, ...],
) -> list[RawCandidate]:
    """Pass prefiltered discovery archive detections to the multi-night linker.

    WISE/DECam/TESS archive rows are single-epoch detections, not broker object
    histories. Requiring an intra-night pair before linking drops one-visit-per-
    night moving objects, which is exactly the discovery-archive use case.
    """
    candidates: list[RawCandidate] = []
    for obs in observations:
        if obs.mission not in _DISCOVERY_ARCHIVE_MISSIONS:
            continue
        candidates.append(
            RawCandidate(
                candidate_id=obs.obs_id,
                observations=(obs,),
                apparent_motion_arcsec_per_hr=None,
                motion_pa_deg=None,
                is_streak=_is_streak(obs),
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

    # Step 2 & 3: preserve same-object broker histories first, then fall back
    # to night-level pairing for sources that do not carry a stable object id.
    passing_tuple = tuple(passing)
    all_candidates: list[RawCandidate] = _find_object_history_sources(passing_tuple)
    object_history_obs = {
        obs.obs_id
        for cand in all_candidates
        for obs in cand.observations
    }
    ungrouped_tuple = tuple(
        obs for obs in passing_tuple if obs.obs_id not in object_history_obs
    )
    archive_candidates = _preserve_discovery_archive_singletons(ungrouped_tuple)
    all_candidates.extend(archive_candidates)
    archive_obs = {
        obs.obs_id
        for cand in archive_candidates
        for obs in cand.observations
    }
    ungrouped = tuple(obs for obs in ungrouped_tuple if obs.obs_id not in archive_obs)
    nights = _group_by_night(ungrouped)
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














def compute_psf_fwhm(obs: Observation) -> float | None:
    """Estimate PSF FWHM in arcsec from the difference-image cutout.

    Fits a 2D Gaussian to the cutout by computing the RMS radius of the
    light distribution and converting to FWHM (FWHM = 2.355 * sigma).
    Returns None when no cutout is available or the array cannot be decoded.
    Pixel scale: 1.01 arcsec/pixel (ZTF).
    """
    _PIXEL_SCALE = 1.01  # arcsec/pixel
    _FWHM_FACTOR = 2.3548  # 2 * sqrt(2 * ln(2))
    cutout_b64 = getattr(obs, "cutout_difference", None)
    if not cutout_b64:
        return None
    try:
        import base64
        raw = base64.b64decode(cutout_b64)
        arr = np.frombuffer(raw, dtype=np.float32).copy()
        size = int(math.isqrt(len(arr)))
        if size * size != len(arr) or size < 3:
            return None
        arr = arr.reshape(size, size).astype(np.float64)
        arr = np.clip(arr, 0.0, None)
        total = float(arr.sum())
        if total <= 0:
            return None
        y, x = np.indices(arr.shape)
        cx = float((x * arr).sum()) / total
        cy = float((y * arr).sum()) / total
        dx = x - cx
        dy = y - cy
        mxx = float((dx**2 * arr).sum()) / total
        myy = float((dy**2 * arr).sum()) / total
        sigma_px = math.sqrt(max(0.0, (mxx + myy) / 2.0))
        fwhm_arcsec = sigma_px * _FWHM_FACTOR * _PIXEL_SCALE
        return round(fwhm_arcsec, 3)
    except Exception:
        return None








def compute_motion_vector(obs1: Observation, obs2: Observation) -> dict:
    """Compute the apparent motion vector between two observations.

    Returns the RA and Dec components of the motion rate in arcsec/hr,
    the total rate, and the position angle.

    Args:
        obs1: First (earlier) observation.
        obs2: Second (later) observation.

    Returns:
        Dict with keys:
          - ``"dra_arcsec_hr"``: RA motion rate component (arcsec/hr, cos-dec corrected).
          - ``"ddec_arcsec_hr"``: Dec motion rate component (arcsec/hr).
          - ``"rate_arcsec_hr"``: Total apparent motion rate (arcsec/hr).
          - ``"pa_deg"``: Position angle of motion in degrees E of N.
    """
    dt_hr = (obs2.jd - obs1.jd) * 24.0
    if abs(dt_hr) < 1e-9:
        return {"dra_arcsec_hr": 0.0, "ddec_arcsec_hr": 0.0,
                "rate_arcsec_hr": 0.0, "pa_deg": 0.0}
    cos_dec = math.cos(math.radians((obs1.dec_deg + obs2.dec_deg) / 2.0))
    dra = (obs2.ra_deg - obs1.ra_deg) * 3600.0 * cos_dec / dt_hr
    ddec = (obs2.dec_deg - obs1.dec_deg) * 3600.0 / dt_hr
    rate = math.hypot(dra, ddec)
    pa = math.degrees(math.atan2(dra, ddec)) % 360.0
    return {
        "dra_arcsec_hr": round(dra, 6),
        "ddec_arcsec_hr": round(ddec, 6),
        "rate_arcsec_hr": round(rate, 6),
        "pa_deg": round(pa, 4),
    }








def filter_by_magnitude(observations: list[Observation], mag_limit: float) -> list[Observation]:
    """Keep observations brighter than mag_limit (lower magnitude = brighter).

    Excludes observations with None magnitude and sentinel magnitudes ≥ 90.
    Only includes observations where ``obs.mag < mag_limit``.

    Args:
        observations: List of :class:`~schemas.Observation` objects.
        mag_limit: Magnitude limit (exclusive upper bound); brighter objects
            have smaller magnitudes.

    Returns:
        Filtered list of observations with ``mag < mag_limit``.
    """
    result = []
    for obs in observations:
        mag = obs.mag
        if mag is None:
            continue
        if mag >= 90.0:
            continue
        if mag < mag_limit:
            result.append(obs)
    return result






























def compute_source_compactness(obs: object) -> float | None:
    """Return the peak-to-total flux ratio from the difference-image cutout.

    Compactness is defined as the ratio of the peak pixel value to the sum of
    all pixel values in the 63×63 float32 difference-image cutout.  A value
    near 1 indicates a point-like source; lower values indicate extended
    emission.  Returns ``None`` when no cutout is available, base64 decoding
    fails, or the total flux is ≤ 0.

    Args:
        obs: Any object with an optional ``cutout_difference`` base64-encoded
            float32 array attribute.

    Returns:
        Compactness index in [0, 1], or ``None``.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        total = float(arr.sum())
        if total <= 0.0:
            return None
        peak = float(arr.max())
        return round(float(min(1.0, max(0.0, peak / total))), 6)
    except Exception:
        return None


























