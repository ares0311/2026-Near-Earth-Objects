"""Detect stage — moving object detection, real/bogus filter, MPC cross-match."""

from __future__ import annotations

__all__ = ["detect", "detect_batch", "streak_candidates", "filter_by_real_bogus",
           "compute_streak_metric"]

import math
import uuid
from collections import defaultdict

import numpy as np

from schemas import (
    DetectProvenance,
    DetectResult,
    KnownMatch,
    Observation,
    PreprocessResult,
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


def detect_batch(
    preprocess_results: list[PreprocessResult],
    real_bogus_threshold: float = _REAL_BOGUS_THRESHOLD,
    mpc_cross_match: bool = True,
) -> list[DetectResult]:
    """Run detection on a list of :class:`PreprocessResult` objects.

    Returns one :class:`DetectResult` per input result in the same order.
    """
    return [
        detect(pr.sources, real_bogus_threshold=real_bogus_threshold,
               mpc_cross_match=mpc_cross_match)
        for pr in preprocess_results
    ]


def streak_candidates(detect_result: DetectResult) -> tuple[RawCandidate, ...]:
    """Filter a :class:`DetectResult` to return only streak/trail detections.

    A streak candidate is one whose constituent observations include at least
    one detection flagged as a streak (``is_streak=True``).  Useful for
    isolating fast-moving NEOs that trail across the focal plane in a single
    exposure.

    Returns a tuple of :class:`RawCandidate` objects from ``detect_result``
    where at least one observation is a streak.
    """
    return tuple(
        cand for cand in detect_result.candidates
        if cand.is_streak
    )


def filter_by_real_bogus(result: DetectResult, threshold: float = 0.65) -> DetectResult:
    """Return a new DetectResult keeping only candidates above a real/bogus threshold.

    Candidates without a real_bogus score on any observation are kept by default
    (conservative: do not discard uncertain sources).
    """
    kept = []
    for cand in result.candidates:
        rbs = [obs.real_bogus for obs in cand.observations if obs.real_bogus is not None]
        if not rbs or max(rbs) >= threshold:
            kept.append(cand)
    from schemas import DetectProvenance
    prov = DetectProvenance(
        real_bogus_threshold=threshold,
        n_candidates=len(kept),
        n_known_matches=result.provenance.n_known_matches,
        detected_at_jd=result.provenance.detected_at_jd,
    )
    return DetectResult(
        candidates=tuple(kept),
        known_matches=result.known_matches,
        provenance=prov,
    )


def compute_streak_metric(obs: Observation) -> float:
    """Quantify streak severity for a single observation using PSF elongation.

    Decodes the difference-image cutout, computes second-order image moments,
    and returns the axis ratio (major/minor) normalized to [0, 1]:

    - 0.0 → perfectly round (no streak)
    - 1.0 → maximally elongated

    Falls back to 0.0 when no cutout is available or the image cannot be
    decoded.
    """
    if obs.cutout_difference is None:
        return 0.0
    try:
        import base64
        import math

        import numpy as np

        raw = base64.b64decode(obs.cutout_difference)
        arr = np.frombuffer(raw, dtype=np.float32)
        size = int(math.isqrt(len(arr)))
        if size * size != len(arr) or size < 3:
            return 0.0
        arr = arr.reshape(size, size).astype(np.float64)
        arr = np.clip(arr, 0.0, None)

        total = float(arr.sum())
        if total <= 0:
            return 0.0

        y, x = np.indices(arr.shape)
        cx = float((x * arr).sum()) / total
        cy = float((y * arr).sum()) / total
        dx = x - cx
        dy = y - cy
        mxx = float((dx ** 2 * arr).sum()) / total
        myy = float((dy ** 2 * arr).sum()) / total
        mxy = float((dx * dy * arr).sum()) / total

        trace = mxx + myy
        if trace <= 0:
            return 0.0
        det = mxx * myy - mxy ** 2
        disc = max(0.0, (trace / 2) ** 2 - det)
        lam1 = trace / 2 + math.sqrt(disc)
        lam2 = trace / 2 - math.sqrt(disc)
        if lam2 <= 1e-12 * lam1:
            # Degenerate: one eigenvalue vanishes → perfectly elongated streak
            return 1.0
        elongation = lam1 / lam2  # ≥ 1

        # Map elongation [1, ∞) → [0, 1]: elongation 5 → ~0.8
        metric = 1.0 - 1.0 / elongation
        return float(min(1.0, max(0.0, metric)))
    except Exception:
        return 0.0
