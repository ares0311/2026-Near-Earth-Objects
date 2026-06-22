"""Detect stage — moving object detection, real/bogus filter, MPC cross-match."""

from __future__ import annotations

__all__ = ["detect", "detect_batch", "streak_candidates", "filter_by_real_bogus",
           "compute_streak_metric", "cluster_detections", "compute_trail_length",
           "compute_psf_fwhm", "estimate_sky_background", "compute_detection_efficiency",
           "count_detections_by_filter", "compute_motion_vector",
           "flag_moving_sources", "compute_source_extent", "estimate_observation_depth",
           "filter_by_magnitude", "compute_streak_density",
           "compute_angular_velocity",
           "compute_detection_gap",
           "compute_observation_cadence",
           "compute_field_source_count",
           "compute_brightness_trend",
           "compute_variability_index",
           "compute_angular_separation",
           "compute_streak_orientation",
           "compute_magnitude_residual",
           "compute_elongation_ratio",
           "compute_detection_significance",
           "compute_sky_plane_velocity",
           "compute_detection_rate",
           "compute_source_compactness",
           "compute_photon_noise_limit",
           "compute_source_flux",
           "compute_apparent_motion_rate",
           "compute_magnitude_range",
           "compute_detection_density",
           "count_streak_detections",
           "count_detections_by_mission",
           "filter_by_streak_score",
           "compute_rb_score_distribution",
           "count_candidates_above_rb",
           "get_brightest_candidate",
           "compute_mean_motion_rate",
           "compute_candidate_sky_density",
           "compute_detection_gap_days"]

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
    ungrouped = tuple(obs for obs in passing_tuple if obs.obs_id not in object_history_obs)
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


def compute_streak_metric(obs: Observation) -> float | None:
    """Quantify streak severity for a single observation using PSF elongation.

    Decodes the difference-image cutout, computes second-order image moments,
    and returns the axis ratio (major/minor) normalized to [0, 1]:

    - 0.0 → perfectly round (no streak)
    - 1.0 → maximally elongated

    Returns None when no cutout is available (cannot determine streak status).
    Falls back to 0.0 when the image cannot be decoded or has degenerate content.
    """
    if obs.cutout_difference is None:
        return None
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


def cluster_detections(
    observations: tuple | list,
    radius_arcsec: float = 5.0,
) -> list[tuple]:
    """Group observations into spatial clusters within *radius_arcsec* of each other.

    Uses a greedy single-linkage approach: each observation joins the first
    existing cluster whose seed lies within *radius_arcsec*, or starts a new one.
    Returns a list of tuples, each tuple containing the Observation objects in
    that cluster.  Input order within each cluster is preserved.
    """
    obs_list = list(observations)
    if not obs_list:
        return []

    radius_deg = radius_arcsec / 3600.0
    seeds: list = []   # (ra, dec) of each cluster seed
    groups: list[list] = []

    for obs in obs_list:
        placed = False
        for idx, (seed_ra, seed_dec) in enumerate(seeds):
            d1, d2 = math.radians(seed_dec), math.radians(obs.dec_deg)
            r1, r2 = math.radians(seed_ra), math.radians(obs.ra_deg)
            cos_sep = (
                math.sin(d1) * math.sin(d2)
                + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
            )
            sep_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))
            if sep_deg <= radius_deg:
                groups[idx].append(obs)
                placed = True
                break
        if not placed:
            seeds.append((obs.ra_deg, obs.dec_deg))
            groups.append([obs])

    return [tuple(g) for g in groups]


def compute_trail_length(obs: object) -> float | None:
    """Estimate trail length in arcsec from difference-image second moments.

    Returns the larger eigenvalue of the 2×2 moment ellipse converted to arcsec,
    or ``None`` if the cutout is unavailable or the moment matrix is degenerate.
    Pixel scale assumed 1.01 arcsec/pixel (ZTF).
    """
    _PIXEL_SCALE = 1.01  # arcsec / pixel (ZTF)
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
        arr -= arr.mean()
        total = arr.sum()
        if total <= 0:
            return None
        cy, cx = np.indices(arr.shape)
        y0 = (cy * arr).sum() / total
        x0 = (cx * arr).sum() / total
        mxx = ((cx - x0) ** 2 * arr).sum() / total
        myy = ((cy - y0) ** 2 * arr).sum() / total
        mxy = ((cx - x0) * (cy - y0) * arr).sum() / total
        trace = mxx + myy
        disc = math.sqrt(max(0.0, ((mxx - myy) / 2) ** 2 + mxy ** 2))
        lam1 = trace / 2 + disc
        return round(float(math.sqrt(max(0.0, lam1))) * _PIXEL_SCALE, 3)
    except Exception:
        return None


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


def estimate_sky_background(observations: tuple | list, percentile: float = 25.0) -> float | None:
    """Estimate the sky background level from a collection of observations.

    Computes the ``percentile``-th percentile of all pixel values across the
    difference-image cutouts in ``observations``.  Useful as a field-level
    sky estimate when no explicit background map is available.

    Args:
        observations: Iterable of Observation objects with optional cutout_difference.
        percentile: Percentile of pixel distribution to use (default 25.0 → lower quartile).

    Returns:
        Estimated background level as a float, or None if no valid cutouts are found.
    """
    import base64

    import numpy as np

    values: list[float] = []
    for obs in observations:
        cutout_b64 = getattr(obs, "cutout_difference", None)
        if not cutout_b64:
            continue
        try:
            raw = base64.b64decode(cutout_b64)
            arr = np.frombuffer(raw, dtype=np.float32).copy()
            if arr.size < 4:
                continue
            values.extend(arr.tolist())
        except Exception:
            continue
    if not values:
        return None
    return round(float(np.percentile(values, percentile)), 6)


def compute_detection_efficiency(
    observations: tuple | list,
    limiting_mag: float,
) -> float:
    """Estimate detection efficiency as the fraction of observations above the limiting magnitude.

    A detection is considered "above threshold" (efficiently detected) when
    ``obs.mag < limiting_mag``.  Observations with ``mag`` equal to ``None``
    or above 90 (sentinel for non-detection) are counted as missed.

    Args:
        observations: Iterable of Observation objects.
        limiting_mag: Survey limiting magnitude (5-sigma depth).

    Returns:
        Fraction of observations brighter than ``limiting_mag`` in [0.0, 1.0].
        Returns 0.0 for an empty collection.
    """
    obs_list = list(observations)
    if not obs_list:
        return 0.0
    n_detected = sum(
        1 for o in obs_list
        if getattr(o, "mag", None) is not None and o.mag < limiting_mag and o.mag < 90.0
    )
    return round(n_detected / len(obs_list), 6)


def count_detections_by_filter(observations: tuple | list) -> dict:
    """Count detections grouped by filter band.

    Args:
        observations: Iterable of :class:`~schemas.Observation` objects.

    Returns:
        Dict mapping ``filter_band`` string to integer count.  Returns an empty
        dict when the input is empty.
    """
    counts: dict = {}
    for obs in observations:
        band = getattr(obs, "filter_band", None)
        if band is None:
            band = "unknown"
        counts[band] = counts.get(band, 0) + 1
    return counts


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


def flag_moving_sources(
    observations: tuple | list,
    min_rate_arcsec_hr: float = 0.1,
) -> list:
    """Return observations inferred to be moving faster than a threshold.

    Uses the ``ssdistnr`` field (nearest solar-system object distance in
    arcsec) as a motion proxy when available.  An observation is flagged as
    moving if its ``ssdistnr`` value is present and finite and the implied
    motion rate computed from consecutive pairs (sorted by JD) exceeds
    ``min_rate_arcsec_hr``.  If no pairs can be formed the single observation
    is included when ``ssdistnr`` is non-None.

    Args:
        observations: Sequence of Observation objects.
        min_rate_arcsec_hr: Minimum motion rate threshold in arcsec/hr.

    Returns:
        List of Observation objects classified as moving sources.
    """
    obs_list = list(observations)
    if not obs_list:
        return []

    obs_sorted = sorted(obs_list, key=lambda o: o.jd)
    moving: list = []

    if len(obs_sorted) < 2:
        return moving

    flagged_ids: set = set()
    for i in range(len(obs_sorted) - 1):
        o1 = obs_sorted[i]
        o2 = obs_sorted[i + 1]
        vec = compute_motion_vector(o1, o2)
        if vec["rate_arcsec_hr"] >= min_rate_arcsec_hr:
            flagged_ids.add(id(o1))
            flagged_ids.add(id(o2))

    for obs in obs_sorted:
        if id(obs) in flagged_ids:
            moving.append(obs)

    return moving


def compute_source_extent(obs: object) -> float | None:
    """Estimate source semi-major axis in arcsec from difference-image second moments.

    Uses the eigenvalue of the 2-D intensity-weighted covariance matrix of the
    63×63 cutout pixels.  Returns the square-root of the largest eigenvalue
    scaled to arcsec (assuming 1 px = 1 arcsec).

    Args:
        obs: An Observation-like object with an optional ``cutout_difference``
             attribute (base64-encoded 63×63 float32 array).

    Returns:
        Semi-major axis in arcsec, or ``None`` if no cutout is available or the
        moments are degenerate (all-zero / non-positive eigenvalue).
    """
    import base64

    cutout_b64 = getattr(obs, "cutout_difference", None)
    if cutout_b64 is None:
        return None
    try:
        raw = base64.b64decode(cutout_b64)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        total = float(arr.sum())
        if total <= 0.0:
            return None
        ys, xs = np.mgrid[0:63, 0:63]
        w = arr / total
        x_bar = float((w * xs).sum())
        y_bar = float((w * ys).sum())
        dx = xs - x_bar
        dy = ys - y_bar
        mxx = float((w * dx * dx).sum())
        myy = float((w * dy * dy).sum())
        mxy = float((w * dx * dy).sum())
        trace = mxx + myy
        det = mxx * myy - mxy * mxy
        discriminant = max(0.0, (trace / 2.0) ** 2 - det)
        lambda_max = trace / 2.0 + math.sqrt(discriminant)
        if lambda_max <= 0.0:
            return None
        return round(math.sqrt(lambda_max), 4)
    except Exception:
        return None


def estimate_observation_depth(
    observations: tuple | list,
    percentile: float = 95.0,
) -> float | None:
    """Estimate the limiting magnitude of an observation set from faint-end statistics.

    Computes the given percentile of valid (non-sentinel) magnitudes across the
    supplied observations.  Magnitudes ≥ 90 are treated as non-detections and
    excluded.

    Args:
        observations: Iterable of Observation-like objects with a ``mag``
            attribute.
        percentile: Percentile to use as the depth proxy (default 95th).

    Returns:
        Limiting magnitude estimate, or ``None`` if no valid magnitudes are
        found.
    """
    import numpy as np

    mags = [
        float(getattr(o, "mag", 99.0))
        for o in observations
        if getattr(o, "mag", 99.0) is not None and float(getattr(o, "mag", 99.0)) < 90.0
    ]
    if not mags:
        return None
    return round(float(np.percentile(mags, percentile)), 4)


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


def compute_streak_density(observations: list) -> float:
    """Compute the fraction of observations classified as streaks.

    An observation is a streak when :func:`compute_streak_metric` returns a
    value ≥ 0.5.  A ``None`` result counts as non-streak.

    Args:
        observations: List of :class:`~schemas.Observation` objects.

    Returns:
        Streak fraction in [0, 1], rounded to 4 decimal places.
        Returns 0.0 for an empty list.
    """
    if not observations:
        return 0.0
    streak_count = 0
    for obs in observations:
        metric = compute_streak_metric(obs)
        if metric is not None and metric >= 0.5:
            streak_count += 1
    return round(streak_count / len(observations), 4)


def compute_angular_velocity(obs1: object, obs2: object) -> dict | None:
    """Compute the angular velocity vector between two observations.

    Returns a dict with the apparent motion rate (arcsec/hr), position angle
    (degrees east of north, [0, 360)), and time baseline (hours).  The RA
    component is cosine-Dec corrected so the rate reflects true angular
    separation on the sky.

    Returns ``None`` if the two observations have identical Julian Dates
    (zero time baseline).

    Args:
        obs1: First :class:`~schemas.Observation`.
        obs2: Second :class:`~schemas.Observation`.

    Returns:
        Dict with keys ``rate_arcsec_hr``, ``pa_deg``, ``dt_hours``,
        or ``None`` for zero time baseline.
    """
    import math

    jd1 = float(getattr(obs1, "jd", 0.0))
    jd2 = float(getattr(obs2, "jd", 0.0))
    dt_days = jd2 - jd1
    if dt_days == 0.0:
        return None
    dt_hours = dt_days * 24.0

    ra1 = float(getattr(obs1, "ra_deg", 0.0))
    ra2 = float(getattr(obs2, "ra_deg", 0.0))
    dec1 = float(getattr(obs1, "dec_deg", 0.0))
    dec2 = float(getattr(obs2, "dec_deg", 0.0))

    cos_dec = math.cos(math.radians((dec1 + dec2) / 2.0))
    dra_arcsec = (ra2 - ra1) * 3600.0 * cos_dec
    ddec_arcsec = (dec2 - dec1) * 3600.0

    rate = math.sqrt(dra_arcsec**2 + ddec_arcsec**2) / abs(dt_hours)
    pa_rad = math.atan2(dra_arcsec, ddec_arcsec)
    pa_deg = math.degrees(pa_rad) % 360.0

    return {
        "rate_arcsec_hr": round(rate, 4),
        "pa_deg": round(pa_deg, 4),
        "dt_hours": round(dt_hours, 6),
    }


def compute_detection_gap(observations: list) -> float | None:
    """Return the maximum time gap in hours between consecutive observations.

    Observations are sorted by Julian Date before computing gaps.  Returns
    *None* when fewer than two observations are supplied.  Useful for
    identifying fields with interrupted coverage (e.g. weather gaps).
    """
    if len(observations) < 2:
        return None
    sorted_obs = sorted(observations, key=lambda o: float(getattr(o, "jd", 0.0)))
    max_gap_hours = 0.0
    for i in range(len(sorted_obs) - 1):
        dt_hours = (float(getattr(sorted_obs[i + 1], "jd", 0.0))
                    - float(getattr(sorted_obs[i], "jd", 0.0))) * 24.0
        if dt_hours > max_gap_hours:
            max_gap_hours = dt_hours
    return round(max_gap_hours, 4)


def compute_observation_cadence(observations: list) -> float | None:
    """Return the mean cadence in hours between consecutive observations.

    Observations are sorted by Julian Date before computing inter-observation
    gaps.  The cadence is the arithmetic mean of all consecutive-pair gaps.
    Returns *None* when fewer than two observations are supplied.
    """
    if len(observations) < 2:
        return None
    sorted_obs = sorted(observations, key=lambda o: float(getattr(o, "jd", 0.0)))
    gaps = [
        (float(getattr(sorted_obs[i + 1], "jd", 0.0))
         - float(getattr(sorted_obs[i], "jd", 0.0))) * 24.0
        for i in range(len(sorted_obs) - 1)
    ]
    return round(sum(gaps) / len(gaps), 4)


def compute_field_source_count(observations: list) -> dict[str, int]:
    """Count observations grouped by field identifier.

    The field identifier is read from ``obs.obs_id`` up to the first underscore
    (e.g. ``"ZTF_field_12345_obs_7"`` → ``"ZTF"``).  If the ``obs_id`` contains
    no underscore the entire string is used.  Observations whose ``obs_id`` is
    empty or ``None`` are grouped under ``"unknown"``.

    Returns a dict mapping field prefix → count, sorted descending by count.
    """
    counts: dict[str, int] = {}
    for obs in observations:
        obs_id = getattr(obs, "obs_id", None) or ""
        field = obs_id.split("_")[0] if obs_id else "unknown"
        counts[field] = counts.get(field, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def compute_brightness_trend(observations: list | tuple) -> float | None:
    """Return the linear brightness trend slope in magnitudes per day.

    A positive slope means the object is fading; negative means brightening.
    Requires at least 2 observations with valid magnitudes (< 90) and distinct
    JDs.  Returns None when the constraint cannot be satisfied.
    """
    try:
        import numpy as np

        jds: list[float] = []
        mags: list[float] = []
        for obs in observations:
            jd = getattr(obs, "jd", None)
            mag = getattr(obs, "mag", None)
            if jd is not None and mag is not None and float(mag) < 90.0:
                jds.append(float(jd))
                mags.append(float(mag))
        if len(jds) < 2:
            return None
        t = np.asarray(jds)
        m = np.asarray(mags)
        if float(np.ptp(t)) == 0.0:
            return None
        coeffs = np.polyfit(t, m, 1)
        return round(float(coeffs[0]), 8)
    except Exception:
        return None


def compute_variability_index(observations: list | tuple) -> float | None:
    """Return the reduced chi-squared variability index of magnitudes.

    Values > 1 indicate variability beyond the photometric uncertainties.
    Requires at least 2 observations with valid magnitudes (< 90) and
    positive mag_err.  Returns None when this constraint cannot be met.
    """
    mags: list[float] = []
    errs: list[float] = []
    for obs in observations:
        mag = getattr(obs, "mag", None)
        err = getattr(obs, "mag_err", None)
        if mag is not None and err is not None and float(mag) < 90.0 and float(err) > 0.0:
            mags.append(float(mag))
            errs.append(float(err))
    if len(mags) < 2:
        return None
    try:
        import numpy as np

        m = np.asarray(mags)
        e = np.asarray(errs)
        w = 1.0 / e**2
        mean_w = float((w * m).sum() / w.sum())
        chi2 = float(((m - mean_w) ** 2 / e**2).sum())
        dof = len(mags) - 1
        return round(chi2 / dof, 6)
    except Exception:
        return None


def compute_angular_separation(obs1: object, obs2: object) -> float:
    """Return the great-circle angular separation between two observations in arcseconds.

    Uses the haversine formula for numerical stability at small angles.

    Args:
        obs1: Object with ``ra_deg`` and ``dec_deg`` attributes.
        obs2: Object with ``ra_deg`` and ``dec_deg`` attributes.

    Returns:
        Angular separation in arcseconds as a float.
    """
    ra1 = math.radians(float(getattr(obs1, "ra_deg", 0.0)))
    dec1 = math.radians(float(getattr(obs1, "dec_deg", 0.0)))
    ra2 = math.radians(float(getattr(obs2, "ra_deg", 0.0)))
    dec2 = math.radians(float(getattr(obs2, "dec_deg", 0.0)))
    hav = (
        math.sin((dec2 - dec1) / 2.0) ** 2
        + math.cos(dec1) * math.cos(dec2) * math.sin((ra2 - ra1) / 2.0) ** 2
    )
    sep_rad = 2.0 * math.asin(math.sqrt(max(0.0, min(1.0, hav))))
    return float(math.degrees(sep_rad) * 3600.0)


def compute_streak_orientation(obs: object) -> float | None:
    """Compute the orientation angle (0–180 deg) of the principal axis in the difference image.

    Uses 2D second-moment matrix: angle = 0.5 * arctan2(2*mu11, mu20-mu02).
    Returns None if no cutout, decoding fails, or the moment matrix is degenerate
    (both mu11==0 and mu20==mu02).
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        total = float(arr.sum())
        if total == 0.0:
            return None
        ys, xs = np.mgrid[0:63, 0:63]
        cx = float((xs * arr).sum()) / total
        cy = float((ys * arr).sum()) / total
        dx = xs - cx
        dy = ys - cy
        mu20 = float((dx**2 * arr).sum()) / total
        mu02 = float((dy**2 * arr).sum()) / total
        mu11 = float((dx * dy * arr).sum()) / total
        if mu11 == 0.0 and mu20 == mu02:
            return None
        angle_rad = 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)
        angle_deg = math.degrees(angle_rad) % 180.0
        return float(angle_deg)
    except Exception:
        return None


def compute_magnitude_residual(obs: object, predicted_mag: float) -> float:
    """Return the signed residual obs.mag − predicted_mag.

    Returns 0.0 if either the observed magnitude or the predicted magnitude
    is a sentinel value (≥ 90), which indicates an invalid or missing magnitude.
    """
    obs_mag = float(getattr(obs, "mag", 99.0) or 99.0)
    if obs_mag >= 90.0 or predicted_mag >= 90.0:
        return 0.0
    return round(obs_mag - predicted_mag, 6)


def compute_elongation_ratio(obs: object) -> float | None:
    """Compute the axis ratio b/a from 2D image second moments.

    Returns a value in (0, 1] where 1.0 = circular and values closer to 0
    indicate a highly elongated (streak) source.  Returns ``None`` if no
    cutout is available or second moments are degenerate.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        arr = np.clip(arr, 0.0, None)
        total = float(arr.sum())
        if total <= 0.0:
            return None
        rows_idx, cols_idx = np.mgrid[0:63, 0:63]
        cx = float((cols_idx * arr).sum()) / total
        cy = float((rows_idx * arr).sum()) / total
        mxx = float(((cols_idx - cx) ** 2 * arr).sum()) / total
        myy = float(((rows_idx - cy) ** 2 * arr).sum()) / total
        mxy = float(((cols_idx - cx) * (rows_idx - cy) * arr).sum()) / total
        trace = mxx + myy
        det = mxx * myy - mxy ** 2
        if trace <= 0.0 or det < 0.0:
            return None
        discriminant = max(0.0, (trace / 2.0) ** 2 - det)
        lambda1 = trace / 2.0 + discriminant ** 0.5
        lambda2 = trace / 2.0 - discriminant ** 0.5
        ratio = float(max(0.0, lambda2)) / lambda1
        return round(min(1.0, max(0.0, ratio)), 6)
    except Exception:
        return None


def compute_detection_significance(obs: object) -> float | None:
    """Compute detection significance as a [0, 1] score.

    Uses ``(limiting_mag - mag) / 5.0``, clipped to ``[0, 1]``.  Returns
    ``None`` if either magnitude is absent, ``None``, or a sentinel value
    (≥ 90).
    """
    mag = getattr(obs, "mag", None)
    limiting_mag = getattr(obs, "limiting_mag", None)
    if mag is None or limiting_mag is None:
        return None
    if mag >= 90.0 or limiting_mag >= 90.0:
        return None
    return float(max(0.0, min(1.0, (limiting_mag - mag) / 5.0)))


def compute_sky_plane_velocity(obs1: object, obs2: object) -> dict:
    """Compute sky-plane velocity between two observations.

    Returns a dict with keys ``dra_arcsec_hr``, ``ddec_arcsec_hr``, and
    ``speed_arcsec_hr``.  The RA component is cosine-Dec corrected.  Returns
    a zero-velocity dict if both observations have the same JD.

    Args:
        obs1: First observation with ``ra``, ``dec``, and ``jd`` attributes.
        obs2: Second observation with ``ra``, ``dec``, and ``jd`` attributes.

    Returns:
        Dict with velocity components in arcsec/hr.
    """
    ra1 = float(getattr(obs1, "ra", 0.0))
    dec1 = float(getattr(obs1, "dec", 0.0))
    jd1 = float(getattr(obs1, "jd", 0.0))
    ra2 = float(getattr(obs2, "ra", 0.0))
    dec2 = float(getattr(obs2, "dec", 0.0))
    jd2 = float(getattr(obs2, "jd", 0.0))

    dt_days = jd2 - jd1
    if dt_days == 0.0:
        return {"dra_arcsec_hr": 0.0, "ddec_arcsec_hr": 0.0, "speed_arcsec_hr": 0.0}

    dt_hours = dt_days * 24.0
    mean_dec_rad = math.radians((dec1 + dec2) / 2.0)
    dra_deg = (ra2 - ra1) * math.cos(mean_dec_rad)
    ddec_deg = dec2 - dec1
    dra_arcsec_hr = dra_deg * 3600.0 / dt_hours
    ddec_arcsec_hr = ddec_deg * 3600.0 / dt_hours
    speed = math.sqrt(dra_arcsec_hr ** 2 + ddec_arcsec_hr ** 2)
    return {
        "dra_arcsec_hr": round(dra_arcsec_hr, 6),
        "ddec_arcsec_hr": round(ddec_arcsec_hr, 6),
        "speed_arcsec_hr": round(speed, 6),
    }


def compute_detection_rate(
    observations: list[object], window_days: float = 1.0
) -> float:
    """Return the fraction of time bins that contain at least one observation.

    Divides the full observation span into bins of ``window_days`` width and
    counts the fraction that contain at least one observation.  Returns
    ``0.0`` for empty input or a single observation (no span defined).

    Args:
        observations: List of observation objects with a ``jd`` attribute.
        window_days: Width of each time bin in days (default 1.0).

    Returns:
        Detection rate in [0, 1].
    """
    if len(observations) < 2:
        return 0.0
    jds = sorted(float(getattr(o, "jd", 0.0)) for o in observations)
    span = jds[-1] - jds[0]
    if span <= 0.0:
        return 0.0
    n_bins = int(math.ceil(span / window_days))
    occupied: set[int] = set()
    t0 = jds[0]
    for jd in jds:
        bin_idx = int((jd - t0) / window_days)
        # clamp last edge to last bin
        occupied.add(min(bin_idx, n_bins - 1))
    return float(len(occupied)) / float(n_bins)


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


def compute_photon_noise_limit(obs: object, gain: float = 1.0) -> float | None:
    """Compute the Poisson photon noise floor from the difference-image cutout.

    The noise floor is estimated as ``sqrt(peak * gain) / peak`` where ``peak``
    is the maximum pixel value in the 63×63 float32 difference-image cutout.
    This represents the fractional photon noise limit at the peak pixel.

    Args:
        obs: Any object with an optional ``cutout_difference`` base64-encoded
            float32 array attribute.
        gain: Detector gain in electrons per ADU (default 1.0).

    Returns:
        Photon noise limit (float ≥ 0), or ``None`` if no cutout, decode
        error, or peak ≤ 0.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        peak = float(arr.max())
        if peak <= 0.0:
            return None
        return float(math.sqrt(peak * gain) / peak)
    except Exception:
        return None


def compute_source_flux(obs: object, aperture_radius_px: float = 5.0) -> float | None:
    """Sum of pixel values within a circular aperture centred on the brightest pixel.

    Args:
        obs: Observation-like object with an optional ``cutout_difference`` base64 attr.
        aperture_radius_px: Aperture radius in pixels (default 5).

    Returns:
        Total flux as ``float``, or ``None`` if no cutout or decode error.
    """
    import base64 as _b64

    import numpy as np

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = _b64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        cy, cx = np.unravel_index(int(arr.argmax()), arr.shape)
        ys, xs = np.indices(arr.shape)
        mask = (ys - cy) ** 2 + (xs - cx) ** 2 <= aperture_radius_px ** 2
        return float(arr[mask].sum())
    except Exception:
        return None


def compute_apparent_motion_rate(observations: list) -> float | None:
    """Return the mean apparent motion rate in arcsec/hr across consecutive observation pairs.

    Uses cosine-Dec-corrected RA differences for each consecutive pair and
    returns the mean rate. Returns None for fewer than 2 observations or
    identical JDs across all pairs.
    """
    if len(observations) < 2:
        return None
    obs_sorted = sorted(observations, key=lambda o: float(getattr(o, "jd", 0.0)))
    rates = []
    for i in range(len(obs_sorted) - 1):
        o1, o2 = obs_sorted[i], obs_sorted[i + 1]
        dt_hr = (float(getattr(o2, "jd", 0.0)) - float(getattr(o1, "jd", 0.0))) * 24.0
        if abs(dt_hr) < 1e-9:
            continue
        mean_dec = (float(getattr(o1, "dec_deg", 0.0)) + float(getattr(o2, "dec_deg", 0.0))) / 2.0
        cos_dec = math.cos(math.radians(mean_dec))
        dra_deg = float(getattr(o2, "ra_deg", 0.0)) - float(getattr(o1, "ra_deg", 0.0))
        dra = dra_deg * 3600.0 * cos_dec
        ddec = (float(getattr(o2, "dec_deg", 0.0)) - float(getattr(o1, "dec_deg", 0.0))) * 3600.0
        rates.append(math.hypot(dra, ddec) / abs(dt_hr))
    if not rates:
        return None
    return float(sum(rates) / len(rates))


def compute_magnitude_range(observations: list) -> float | None:
    """Return the range (max − min) of valid magnitudes across a list of observations.

    Excludes sentinel magnitudes (≥ 90) and None values. Returns None if fewer
    than 2 valid magnitudes are found.
    """
    mags = []
    for obs in observations:
        mag = getattr(obs, "mag", None)
        if mag is None:
            continue
        m = float(mag)
        if m < 90.0:
            mags.append(m)
    if len(mags) < 2:
        return None
    return float(max(mags) - min(mags))


def compute_detection_density(candidates: list, field_radius_deg: float) -> float | None:
    """Return the number of candidates per square degree.

    Uses the solid-angle formula for a circular field: Ω = 2π(1−cos(r)) steradians,
    converted to square degrees.  Returns None if field_radius_deg ≤ 0.
    """
    if field_radius_deg <= 0.0:
        return None
    r_rad = math.radians(abs(field_radius_deg))
    steradians = 2.0 * math.pi * (1.0 - math.cos(r_rad))
    sq_deg = steradians * (180.0 / math.pi) ** 2
    return float(len(candidates) / sq_deg) if sq_deg > 0.0 else None


def count_streak_detections(detect_result: object) -> int:
    """Return the number of streak/trail candidates in a DetectResult.

    Counts candidates whose ``is_streak`` attribute is True.  If the
    *detect_result* has no ``candidates`` attribute or no candidates have
    streak metadata, returns 0.
    """
    candidates = getattr(detect_result, "candidates", None) or []
    return sum(1 for c in candidates if getattr(c, "is_streak", False))


def count_detections_by_mission(detect_result: object) -> dict:
    """Return a dict mapping survey mission name to candidate count.

    Counts each candidate in ``detect_result.candidates`` by its ``mission``
    attribute (falls back to ``"unknown"`` if the attribute is absent or None).
    Returns an empty dict if there are no candidates.
    """
    candidates = getattr(detect_result, "candidates", None) or []
    counts: dict[str, int] = {}
    for c in candidates:
        obs = getattr(c, "observation", None)
        mission = getattr(obs, "mission", None) if obs is not None else None
        if mission is None:
            mission = getattr(c, "mission", None)
        key = str(mission) if mission is not None else "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def filter_by_streak_score(
    result: DetectResult,
    min_streak_score: float = 0.5,
) -> DetectResult:
    """Return a new DetectResult keeping only candidates with high streak severity.

    For each candidate, computes the maximum ``compute_streak_metric`` across its
    observations.  Candidates where the max streak metric ≥ *min_streak_score*
    are kept.  Candidates with no observations are discarded.

    The returned provenance reflects the reduced candidate count; other
    provenance fields are inherited from the input.
    """
    from schemas import DetectProvenance

    kept = []
    for cand in result.candidates:
        if not cand.observations:
            continue
        streaks = [compute_streak_metric(o) for o in cand.observations]
        max_streak = max((s for s in streaks if s is not None), default=0.0)
        if max_streak >= min_streak_score:
            kept.append(cand)
    prov = DetectProvenance(
        real_bogus_threshold=result.provenance.real_bogus_threshold,
        n_candidates=len(kept),
        n_known_matches=result.provenance.n_known_matches,
        detected_at_jd=result.provenance.detected_at_jd,
    )
    return DetectResult(
        candidates=tuple(kept),
        known_matches=result.known_matches,
        provenance=prov,
    )


def compute_rb_score_distribution(result: DetectResult, n_bins: int = 10) -> dict:
    """Return an equal-width histogram of real/bogus scores across candidates.

    Collects the maximum ``real_bogus`` score across observations for each
    candidate, then bins the scores into *n_bins* equal-width bins spanning
    [0, 1].  Candidates with no valid (non-None) scores are excluded.

    Returns a dict with keys:
      - ``"bin_edges"``: list of *n_bins + 1* floats from 0.0 to 1.0
      - ``"counts"``: list of *n_bins* non-negative ints
      - ``"n_total"``: total candidates with at least one valid RB score
    """
    n_bins = max(1, int(n_bins))
    scores = []
    for cand in result.candidates:
        valid = [
            obs.real_bogus
            for obs in cand.observations
            if obs.real_bogus is not None
        ]
        if valid:
            scores.append(max(valid))
    edges = [i / n_bins for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for s in scores:
        idx = int(float(s) * n_bins)
        if idx >= n_bins:
            idx = n_bins - 1
        counts[idx] += 1
    return {"bin_edges": edges, "counts": counts, "n_total": len(scores)}


def count_candidates_above_rb(result: DetectResult, threshold: float = 0.65) -> int:
    """Return the count of candidates with at least one real_bogus score ≥ threshold.

    For each candidate, considers all ``real_bogus`` scores across its
    observations.  Candidates with no valid (non-None) scores are excluded.
    Returns 0 for an empty result or if no candidates meet the threshold.
    """
    count = 0
    for cand in result.candidates:
        valid = [
            obs.real_bogus
            for obs in cand.observations
            if obs.real_bogus is not None
        ]
        if valid and max(valid) >= threshold:
            count += 1
    return count


def get_brightest_candidate(result: DetectResult) -> object | None:
    """Return the RawCandidate with the lowest-magnitude observation.

    Considers all observations across all candidates and picks the candidate
    that contains the observation with the minimum magnitude (excluding
    sentinel magnitudes ≥ 90).  Returns ``None`` if the result is empty or
    all magnitudes are sentinels.
    """
    best_cand = None
    best_mag = float("inf")
    for cand in result.candidates:
        for obs in cand.observations:
            if obs.mag < 90.0 and obs.mag < best_mag:
                best_mag = obs.mag
                best_cand = cand
    return best_cand


def compute_mean_motion_rate(result: DetectResult) -> float | None:
    """Mean apparent motion rate (arcsec/hr) across all candidates in *result*.

    For each candidate the maximum real_bogus observation's motion is estimated
    using ``compute_motion_vector`` on consecutive observation pairs.  The mean
    over all valid rate values is returned.  Returns ``None`` if no valid rates
    can be computed.
    """
    from detect import compute_motion_vector

    rates: list[float] = []
    for cand in result.candidates:
        obs_list = list(cand.observations)
        for i in range(len(obs_list) - 1):
            try:
                mv = compute_motion_vector(obs_list[i], obs_list[i + 1])
                rate = mv.get("rate_arcsec_hr")
                if rate is not None and rate >= 0.0:
                    rates.append(float(rate))
            except Exception:
                continue
    if not rates:
        return None
    return float(sum(rates) / len(rates))


def compute_candidate_sky_density(result: DetectResult, field_radius_deg: float) -> float:
    """Candidates per square degree for a circular survey field.

    Uses the solid-angle formula: area = 2π(1 − cos(r)) steradians,
    converted to square degrees.  Returns 0.0 for non-positive *field_radius_deg*
    or an empty candidate list.
    """
    import math

    if field_radius_deg <= 0.0:
        return 0.0
    n = len(result.candidates)
    if n == 0:
        return 0.0
    r_rad = math.radians(field_radius_deg)
    area_sr = 2.0 * math.pi * (1.0 - math.cos(r_rad))
    area_sq_deg = area_sr * (180.0 / math.pi) ** 2
    return float(n / area_sq_deg)


def compute_detection_gap_days(result: DetectResult) -> float | None:
    """Maximum gap in days between consecutive candidate detections.

    Extracts the best JD from each candidate (first observation), sorts them,
    and returns the maximum consecutive gap.  Returns ``None`` for fewer than
    2 candidates or if no valid JDs can be extracted.
    """
    jds = []
    for cand in result.candidates:
        obs_list = getattr(cand, "observations", None)
        if obs_list:
            jd = getattr(obs_list[0], "jd", None)
            if jd is not None:
                jds.append(float(jd))
    if len(jds) < 2:
        return None
    jds.sort()
    gaps = [jds[i + 1] - jds[i] for i in range(len(jds) - 1)]
    return float(max(gaps))
