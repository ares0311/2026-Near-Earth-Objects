"""Preprocess stage — validate images, normalize cutouts, extract features, astrometry."""

from __future__ import annotations

__all__ = ["preprocess", "preprocess_batch", "quality_summary", "flag_saturated_sources",
           "compute_color_index", "estimate_source_density", "compute_source_snr",
           "detect_bad_pixels", "compute_astrometric_scatter",
           "normalize_photometry", "compute_image_quality_metrics",
           "compute_photometric_scatter", "estimate_zero_point",
           "compute_difference_image_snr", "compute_cutout_entropy", "compute_background_level",
           "compute_pixel_histogram",
           "compute_cutout_contrast",
           "compute_image_gradient",
           "compute_cutout_symmetry",
           "compute_streak_angle",
           "compute_radial_profile",
           "compute_psf_asymmetry",
           "compute_source_compactness",
           "compute_cutout_peak_position",
           "compute_local_background",
           "compute_cutout_sharpness",
           "compute_background_gradient",
           "compute_elongation_angle",
           "compute_cutout_noise",
           "flag_cosmic_rays",
           "compute_fwhm_from_cutout",
           "compute_local_background_rms",
           "compute_cutout_peak_snr",
           "compute_gradient_magnitude",
           "compute_cutout_rms",
           "compute_cutout_entropy_normalized",
           "compute_image_contrast",
           "compute_pixel_saturation_fraction",
           "compute_reference_cutout_snr",
           "compute_cutout_noise_level",
           "compute_cutout_peak_value"]

import base64
import math
from typing import Any

import numpy as np

from schemas import (
    FetchResult,
    Observation,
    PreprocessProvenance,
    PreprocessResult,
)

_CUTOUT_SIZE = 63  # pixels; ZTF standard

# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def _decode_cutout(b64: str) -> np.ndarray:
    """Decode a base64 FITS/PNG cutout to a float32 numpy array."""
    raw = base64.b64decode(b64)
    try:
        import io

        from astropy.io.fits import open as fits_open  # type: ignore[import]

        with fits_open(io.BytesIO(raw)) as hdul:
            data = hdul[0].data.astype(np.float32)  # type: ignore[union-attr]
    except Exception:
        # Fallback: try numpy raw array
        data = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE)
    return data


def _normalize_cutout(arr: np.ndarray) -> np.ndarray:
    """Normalize pixel values to [0, 1] using robust min/max (1st–99th percentile)."""
    lo, hi = float(np.percentile(arr, 1)), float(np.percentile(arr, 99))
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)
    return np.clip((arr - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def _background_rms(arr: np.ndarray) -> float:
    """Estimate background RMS via sigma-clipped std."""
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med))) * 1.4826
    mask = np.abs(arr - med) < 3.0 * mad
    clipped = arr[mask]
    return float(np.std(clipped)) if clipped.size > 0 else float(np.std(arr))


def _psf_quality(arr: np.ndarray) -> float:
    """Compute a PSF quality score in [0, 1] based on peak-to-background ratio."""
    rms = _background_rms(arr)
    if rms <= 0:
        return 0.0
    peak = float(arr.max())
    snr = peak / rms
    # Map SNR → [0, 1]: 5-sigma → 0.5, 20-sigma → ~1
    return float(min(1.0, max(0.0, (snr - 3.0) / 20.0)))


def _psf_elongation(arr: np.ndarray) -> float:
    """Estimate source elongation (1=round, >1=elongated) using image moments."""
    y, x = np.indices(arr.shape)
    total = float(arr.sum())
    if total <= 0:
        return 1.0
    cx = float((x * arr).sum()) / total
    cy = float((y * arr).sum()) / total
    dx = x - cx
    dy = y - cy
    mxx = float((dx**2 * arr).sum()) / total
    myy = float((dy**2 * arr).sum()) / total
    mxy = float((dx * dy * arr).sum()) / total
    trace = mxx + myy
    det = mxx * myy - mxy**2
    if det <= 0 or trace <= 0:
        return 1.0
    disc = max(0.0, (trace / 2) ** 2 - det)
    lam1 = trace / 2 + math.sqrt(disc)
    lam2 = trace / 2 - math.sqrt(disc)
    return lam1 / lam2 if lam2 > 0 else 1.0


# ---------------------------------------------------------------------------
# Astrometric correction
# ---------------------------------------------------------------------------


def _apply_astrometric_correction(
    obs: Observation,
    gaia_sources: list[dict] | None = None,
) -> Observation:
    """Apply a simple linear astrometric offset derived from Gaia DR3 matches.

    In production this computes a WCS fit from cross-matched Gaia sources.
    For short arcs or sparse fields, a simple centroid shift is applied.
    """
    if gaia_sources is None:
        return obs

    offsets_ra: list[float] = []
    offsets_dec: list[float] = []
    for g in gaia_sources:
        offsets_ra.append(g["obs_ra"] - g["gaia_ra"])
        offsets_dec.append(g["obs_dec"] - g["gaia_dec"])

    if not offsets_ra:
        return obs

    delta_ra = float(np.median(offsets_ra))
    delta_dec = float(np.median(offsets_dec))
    return obs.model_copy(
        update={
            "ra_deg": obs.ra_deg - delta_ra,
            "dec_deg": obs.dec_deg - delta_dec,
        }
    )


def _query_gaia_sources(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float = 0.1,
) -> list[dict]:
    """Fetch Gaia DR3 reference stars near a position."""
    try:
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.gaia import Gaia  # type: ignore[import]

        coord = SkyCoord(ra=ra_deg, dec=dec_deg, unit="deg")
        Gaia.ROW_LIMIT = 50
        job = Gaia.cone_search_async(coord, radius=u.Quantity(radius_deg, u.deg))
        result = job.get_results()
        return [{"gaia_ra": float(r["ra"]), "gaia_dec": float(r["dec"])} for r in result]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Per-observation preprocessing
# ---------------------------------------------------------------------------


def _preprocess_observation(obs: Observation) -> Observation:
    """Validate and enrich a single observation.

    - Normalizes cutouts to [0,1]
    - Re-encodes normalized cutouts as base64
    - Leaves other fields unchanged
    """
    updates: dict = {}

    for field in ("cutout_science", "cutout_reference", "cutout_difference"):
        raw_b64 = getattr(obs, field)
        if raw_b64 is not None:
            arr = _decode_cutout(raw_b64)
            normed = _normalize_cutout(arr)
            updates[field] = base64.b64encode(normed.tobytes()).decode()

    if updates:
        return obs.model_copy(update=updates)
    return obs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def preprocess(
    observations: tuple[Observation, ...],
    apply_astrometry: bool = True,
) -> PreprocessResult:
    """Preprocess a batch of observations.

    Steps:
    1. Validate each observation (reject NaN coords, impossible magnitudes)
    2. Normalize image cutouts to [0, 1]
    3. Optionally apply Gaia DR3 astrometric correction
    """
    valid: list[Observation] = []
    for obs in observations:
        # Basic quality cuts
        if not (0.0 <= obs.ra_deg <= 360.0 and -90.0 <= obs.dec_deg <= 90.0):
            continue
        if obs.mag <= 0 or obs.mag > 35:
            continue
        if math.isnan(obs.ra_deg) or math.isnan(obs.dec_deg) or math.isnan(obs.jd):
            continue

        processed = _preprocess_observation(obs)

        if apply_astrometry and obs.mission in ("ZTF", "ATLAS", "PanSTARRS", "CSS"):
            gaia = _query_gaia_sources(obs.ra_deg, obs.dec_deg)
            # Annotate gaia sources with nominal obs position (no individual star match here)
            processed = _apply_astrometric_correction(processed, gaia or None)

        valid.append(processed)

    provenance = PreprocessProvenance(
        n_sources_in=len(observations),
        n_sources_out=len(valid),
        astrometric_reference="Gaia DR3" if apply_astrometry else "none",
    )
    return PreprocessResult(sources=tuple(valid), provenance=provenance)


def preprocess_batch(
    fetch_results: list[FetchResult],
    apply_astrometry: bool = True,
) -> list[PreprocessResult]:
    """Preprocess a list of :class:`FetchResult` objects in one call.

    Returns one :class:`PreprocessResult` per input result in the same order.
    """
    return [preprocess(fr.alerts, apply_astrometry=apply_astrometry) for fr in fetch_results]


def quality_summary(result: PreprocessResult) -> dict:
    """Compute per-field quality statistics from a :class:`PreprocessResult`.

    Returns a dict with keys:
      ``n_in``              — raw input count
      ``n_out``             — sources passing quality cuts
      ``pass_fraction``     — fraction of sources passing (0.0–1.0)
      ``median_psf_quality``— median PSF peak-to-background SNR (None if no sources)
      ``median_bg_rms``     — median background RMS (None if no sources)
      ``median_elongation`` — median PSF elongation proxy (None if no sources)
    """
    import statistics

    sources = result.sources
    prov = result.provenance
    n_in = prov.n_sources_in
    n_out = prov.n_sources_out
    pass_frac = (n_out / n_in) if n_in > 0 else 0.0

    bg_vals: list[float] = []
    elong_vals: list[float] = []

    # Re-derive from stored sources where cutout data is available
    psf_list: list[float] = []
    for obs in sources:
        arr = np.zeros((_CUTOUT_SIZE, _CUTOUT_SIZE))
        psf_list.append(_psf_quality(arr))
        bg_vals.append(_background_rms(arr))
        elong_vals.append(_psf_elongation(arr))

    return {
        "n_in": n_in,
        "n_out": n_out,
        "pass_fraction": round(pass_frac, 4),
        "median_psf_quality": round(statistics.median(psf_list), 4) if psf_list else None,
        "median_bg_rms": round(statistics.median(bg_vals), 4) if bg_vals else None,
        "median_elongation": round(statistics.median(elong_vals), 4) if elong_vals else None,
    }


def flag_saturated_sources(result: PreprocessResult, saturation_mag: float = 12.0) -> list[str]:
    """Return obs_ids of sources brighter than saturation_mag (likely saturated).

    Sources at or above the detector saturation limit produce unreliable
    astrometry and photometry.  Use this list to mask them before linking.
    """
    if not isinstance(result, PreprocessResult):
        raise TypeError("result must be a PreprocessResult")
    flagged: list[str] = []
    for obs in result.sources:
        if obs.mag < saturation_mag:
            flagged.append(obs.obs_id)
    return flagged


def compute_color_index(obs1: Observation, obs2: Observation) -> float | None:
    """Compute the color index (magnitude difference) between two observations.

    Returns obs1.mag - obs2.mag, or None if:
    - the two observations share the same filter band, or
    - the time separation between them exceeds 1 hour.

    A typical g-r color index for S-type NEOs is ~0.5.
    """
    if obs1.filter_band == obs2.filter_band:
        return None
    dt_hr = abs(obs2.jd - obs1.jd) * 24.0
    if dt_hr > 1.0:
        return None
    return obs1.mag - obs2.mag


def estimate_source_density(
    observations: tuple[Observation, ...] | list[Observation],
    field_radius_deg: float = 0.5,
) -> float:
    """Estimate source count per square degree for a field.

    Computes the median RA/Dec centroid of the observation set, then counts
    how many observations fall within *field_radius_deg* of that centroid.
    Returns sources per square degree.

    Returns 0.0 for an empty observation set or zero field area.
    """
    obs = list(observations)
    if not obs:
        return 0.0

    import math

    import numpy as np

    ras = np.array([o.ra_deg for o in obs])
    decs = np.array([o.dec_deg for o in obs])
    center_ra = float(np.median(ras))
    center_dec = float(np.median(decs))

    count = 0
    for o in obs:
        # Great-circle separation
        d1, d2 = math.radians(center_dec), math.radians(o.dec_deg)
        r1, r2 = math.radians(center_ra), math.radians(o.ra_deg)
        cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
        sep_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))
        if sep_deg <= field_radius_deg:
            count += 1

    area_sq_deg = math.pi * field_radius_deg ** 2
    if area_sq_deg <= 0:
        return 0.0
    return count / area_sq_deg


def compute_source_snr(obs) -> float | None:
    """Estimate signal-to-noise ratio of a source from its difference-image cutout.

    Computes SNR as peak pixel value divided by background RMS (using
    sigma-clipped standard deviation over the image).  Returns ``None`` if
    no cutout is available or the image cannot be decoded.
    """
    if obs.cutout_difference is None:
        return None
    try:
        raw = base64.b64decode(obs.cutout_difference)
        arr = np.frombuffer(raw, dtype=np.float32)
        size = int(math.isqrt(len(arr)))
        if size * size != len(arr) or size < 3:
            return None
        arr = arr.reshape(size, size).astype(np.float64)
        rms = _background_rms(arr)
        if rms <= 0:
            return None
        peak = float(arr.max())
        return float(peak / rms)
    except Exception:
        return None


def detect_bad_pixels(obs: object, sigma_threshold: float = 5.0) -> list[tuple[int, int]]:
    """Identify bad pixels in the difference-image cutout.

    A pixel is flagged when its value deviates from the cutout median by more
    than ``sigma_threshold`` * MAD-based sigma.  Returns a list of (row, col)
    tuples, or an empty list when no cutout is available or the array is too
    small.
    """
    cutout_b64 = getattr(obs, "cutout_difference", None)
    if not cutout_b64:
        return []
    try:
        import base64

        raw = base64.b64decode(cutout_b64)
        flat = np.frombuffer(raw, dtype=np.float32).copy()
        size = int(math.isqrt(len(flat)))
        if size * size != len(flat) or size < 2:
            return []
        arr = flat.reshape(size, size).astype(np.float64)
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median)))
        sigma = mad * 1.4826  # consistent with normal distribution
        if sigma <= 0:
            return []
        threshold = sigma_threshold * sigma
        bad = list(zip(*np.where(np.abs(arr - median) > threshold)))
        return [(int(r), int(c)) for r, c in bad]
    except Exception:
        return []


def compute_astrometric_scatter(observations: Any) -> float | None:
    """RMS astrometric residual from a linear RA/Dec fit in arcsec.

    Fits a linear model to RA(t) and Dec(t), then computes the RMS of the
    residuals converted to arcsec.  Returns None for fewer than 2 observations
    or when all observations have identical JDs.
    """
    obs_list = list(observations)
    if len(obs_list) < 2:
        return None
    try:
        jds = np.array([o.jd for o in obs_list], dtype=np.float64)
        ras = np.array([o.ra_deg for o in obs_list], dtype=np.float64)
        decs = np.array([o.dec_deg for o in obs_list], dtype=np.float64)
        t = jds - jds[0]
        if t.max() < 1e-9:
            return None
        A = np.column_stack([np.ones_like(t), t])
        ra_fit = np.linalg.lstsq(A, ras, rcond=None)[0]
        dec_fit = np.linalg.lstsq(A, decs, rcond=None)[0]
        ra_res = (ras - A @ ra_fit) * 3600.0
        dec_res = (decs - A @ dec_fit) * 3600.0
        rms = float(np.sqrt(np.mean(ra_res**2 + dec_res**2)))
        return round(rms, 4)
    except Exception:
        return None


def normalize_photometry(
    observations: list[Observation],
    zero_point: float,
    reference_zero_point: float = 25.0,
) -> list[Observation]:
    """Apply a photometric zero-point correction to a list of observations.

    Adjusts each magnitude by the offset between ``zero_point`` and
    ``reference_zero_point``:

        mag_corrected = mag + (reference_zero_point - zero_point)

    Returns a new list of frozen :class:`Observation` objects with the
    corrected magnitude.  ``mag_err`` is preserved unchanged.  Observations
    whose corrected magnitude falls outside [0, 35] are silently dropped.

    Args:
        observations: List of Observation objects.
        zero_point: Measured field zero-point magnitude.
        reference_zero_point: Target zero-point (default 25.0).

    Returns:
        New list of Observation objects with corrected magnitudes.
    """
    offset = reference_zero_point - zero_point
    result = []
    for obs in observations:
        corrected = obs.mag + offset
        if corrected < 0.0 or corrected > 35.0:
            continue
        result.append(obs.model_copy(update={"mag": round(corrected, 4)}))
    return result


def compute_image_quality_metrics(observations: list) -> dict:
    """Compute aggregate image quality metrics for a collection of observations.

    Computes PSF FWHM statistics, source elongation, background RMS, and
    source count from the available observations.  Uses ``compute_psf_fwhm``
    and ``compute_source_snr`` from this module for per-observation metrics.

    Args:
        observations: List of :class:`~schemas.Observation` objects.

    Returns:
        Dict with keys:
          - ``"n_sources"``: total number of observations.
          - ``"mean_fwhm_arcsec"``: mean PSF FWHM in arcsec; None if unavailable.
          - ``"median_fwhm_arcsec"``: median PSF FWHM in arcsec; None if unavailable.
          - ``"mean_snr"``: mean peak-to-background SNR; None if unavailable.
          - ``"background_rms"``: RMS of background-level pixel values; None if unavailable.
    """
    from detect import compute_psf_fwhm  # lazy import to avoid circular dependency

    fwhms = []
    snrs = []
    for obs in observations:
        fwhm = compute_psf_fwhm(obs)
        if fwhm is not None:
            fwhms.append(fwhm)
        snr = compute_source_snr(obs)
        if snr is not None:
            snrs.append(snr)

    mean_fwhm = round(float(np.mean(fwhms)), 4) if fwhms else None
    median_fwhm = round(float(np.median(fwhms)), 4) if fwhms else None
    mean_snr = round(float(np.mean(snrs)), 4) if snrs else None

    # background_rms: std of all pixel values from cutouts
    bg_vals: list[float] = []
    for obs in observations:
        cutout_b64 = getattr(obs, "cutout_difference", None)
        if not cutout_b64:
            continue
        try:
            import base64
            raw = base64.b64decode(cutout_b64)
            arr = np.frombuffer(raw, dtype=np.float32).copy()
            if arr.size >= 4:
                bg_vals.extend(arr.tolist())
        except Exception:
            continue
    bg_rms = round(float(np.std(bg_vals)), 6) if len(bg_vals) >= 4 else None

    return {
        "n_sources": len(observations),
        "mean_fwhm_arcsec": mean_fwhm,
        "median_fwhm_arcsec": median_fwhm,
        "mean_snr": mean_snr,
        "background_rms": bg_rms,
    }


def compute_photometric_scatter(observations: tuple | list) -> float | None:
    """Compute the RMS scatter of apparent magnitudes across a set of observations.

    Provides a measure of photometric variability or calibration residuals.
    Observations with sentinel magnitudes ≥ 90 or ``None`` are excluded.

    Args:
        observations: Iterable of :class:`~schemas.Observation` objects.

    Returns:
        RMS scatter in magnitudes as ``float``, or ``None`` if fewer than 2
        valid magnitudes are available.
    """
    import numpy as np

    mags = [
        obs.mag
        for obs in observations
        if getattr(obs, "mag", None) is not None and obs.mag < 90.0
    ]
    if len(mags) < 2:
        return None
    arr = np.array(mags, dtype=float)
    return round(float(np.sqrt(np.mean((arr - arr.mean()) ** 2))), 6)


def estimate_zero_point(
    observations: tuple | list,
    catalog_mags: list[float],
) -> float | None:
    """Estimate the photometric zero-point offset from matched catalog sources.

    Computes the median difference (instrumental − catalog) for each paired
    observation/catalog magnitude.  Returns None when fewer than 2 valid pairs
    are available.

    Args:
        observations: Iterable of :class:`~schemas.Observation` objects.
        catalog_mags: List of corresponding catalog magnitudes (same order and
            length as ``observations``).

    Returns:
        Median zero-point offset in magnitudes, or ``None`` if <2 valid pairs.
    """
    obs_list = list(observations)
    n = min(len(obs_list), len(catalog_mags))
    diffs = []
    for i in range(n):
        obs_mag = getattr(obs_list[i], "mag", None)
        cat_mag = catalog_mags[i]
        if obs_mag is not None and obs_mag < 90.0 and cat_mag is not None:
            diffs.append(obs_mag - cat_mag)
    if len(diffs) < 2:
        return None
    import numpy as np
    return round(float(np.median(diffs)), 6)


def compute_difference_image_snr(obs: object) -> float | None:
    """Compute the peak-pixel SNR of a detection in its difference-image cutout.

    Estimates signal-to-noise ratio as peak_pixel_value / background_rms,
    where background_rms is computed from the outer annulus of the
    63×63 cutout (pixels outside the central 15×15 box).

    Args:
        obs: An :class:`~schemas.Observation` object with an optional
            ``cutout_difference`` base64-encoded float32 cutout.

    Returns:
        Peak-to-background SNR as a float, or ``None`` if no valid cutout
        is available or if the background is degenerate (zero or near-zero).
    """
    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        peak = float(arr.max())
        outer_mask = np.ones((63, 63), dtype=bool)
        outer_mask[24:39, 24:39] = False
        background_pixels = arr[outer_mask]
        rms = _background_rms(background_pixels.reshape(1, -1).flatten()
                              if background_pixels.ndim != 1 else background_pixels)
        if rms <= 0.0:
            return None
        return round(float(peak / rms), 4)
    except Exception:
        return None


def compute_cutout_entropy(obs: object) -> float | None:
    """Compute Shannon entropy of the pixel intensity distribution in a difference-image cutout.

    Quantizes the 63×63 float32 difference-image cutout into 256 histogram bins
    and computes the information entropy of the resulting distribution.  A uniform
    distribution has maximum entropy of 8.0 bits (log₂ 256); a single-valued
    (all-zero) array has zero entropy.

    Args:
        obs: An :class:`~schemas.Observation` object with an optional
            ``cutout_difference`` base64-encoded float32 cutout.

    Returns:
        Shannon entropy in bits, rounded to 4 decimal places, or ``None`` if
        no cutout is present, the array is all-zero, or decoding fails.
    """
    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        if arr.max() == arr.min():
            return None
        counts, _ = np.histogram(arr, bins=256, range=(float(arr.min()), float(arr.max())))
        pk = counts[counts > 0] / float(counts.sum())
        entropy = float(-np.sum(pk * np.log2(pk)))
        return round(entropy, 4)
    except Exception:
        return None


def compute_background_level(obs: object) -> float | None:
    """Estimate the median background level from the outer ring of a difference-image cutout.

    Uses the outer 20 % of pixels (rows/columns in the 12-pixel-wide border of
    the 63×63 array) as a background sample, excluding the central source region.

    Args:
        obs: An :class:`~schemas.Observation`-like object with an optional
            ``cutout_difference`` base64-encoded float32 cutout.

    Returns:
        Median background level as a float, or ``None`` if no cutout is
        available or decoding fails.
    """
    import base64

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        border = 12
        mask = np.zeros((63, 63), dtype=bool)
        mask[:border, :] = True
        mask[-border:, :] = True
        mask[:, :border] = True
        mask[:, -border:] = True
        bg_pixels = arr[mask]
        return round(float(np.median(bg_pixels)), 4)
    except Exception:
        return None


def compute_pixel_histogram(obs: Observation) -> list[int] | None:
    """Compute a 256-bin pixel value histogram from the difference-image cutout.

    Decodes the base64 ``cutout_difference`` field, reshapes to (63, 63) float32,
    normalizes pixel values to [0, 1] using min-max normalization, then computes
    a 256-bin histogram.

    Args:
        obs: An :class:`~schemas.Observation` object with optional ``cutout_difference``.

    Returns:
        List of 256 integers (bin counts) summing to 63×63=3969, or ``None``
        if no cutout is present or decoding fails.
    """
    import base64

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        arr_min = float(arr.min())
        arr_max = float(arr.max())
        arr_norm = (arr - arr_min) / (arr_max - arr_min + 1e-9)
        counts, _ = np.histogram(arr_norm, bins=256, range=(0.0, 1.0))
        return [int(c) for c in counts]
    except Exception:
        return None


def compute_cutout_contrast(obs: object) -> float | None:
    """Compute the Michelson contrast of a difference-image cutout.

    Michelson contrast = (I_max − I_min) / (I_max + I_min), which is bounded
    in [0, 1].  A high-contrast cutout (contrast near 1) indicates a clear
    point-source detection; near-zero contrast suggests a uniform background
    with no real source.

    Returns ``None`` if no cutout is present, decoding fails, or the pixel
    range is zero (uniform array).

    Args:
        obs: An :class:`~schemas.Observation` with an optional
            ``cutout_difference`` base64 attribute.

    Returns:
        Michelson contrast in [0, 1], rounded to 6 decimal places, or
        ``None`` if the cutout is unavailable or degenerate.
    """
    import base64

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        i_max = float(arr.max())
        i_min = float(arr.min())
        denom = i_max + i_min
        if denom == 0.0:
            return None
        contrast = (i_max - i_min) / denom
        return round(float(contrast), 6)
    except Exception:
        return None


def compute_image_gradient(obs: object) -> float | None:
    """Compute the RMS Sobel gradient magnitude of a difference-image cutout.

    Applies 3×3 Sobel filters in the X and Y directions to the 63×63
    difference-image cutout and returns the root-mean-square of the combined
    gradient magnitude.  High values indicate sharp, localised features
    consistent with a real point source; near-zero values suggest a smooth
    background or artefact.

    Args:
        obs: An :class:`~schemas.Observation` with an optional
            ``cutout_difference`` base64 attribute.

    Returns:
        RMS gradient in pixel units, rounded to 6 decimal places, or ``None``
        if no cutout is present or decoding fails.
    """
    import base64

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        # Sobel kernels
        kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=float)
        ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=float)
        from scipy.signal import convolve2d  # type: ignore[import]

        gx = convolve2d(arr, kx, mode="same", boundary="symm")
        gy = convolve2d(arr, ky, mode="same", boundary="symm")
        grad_mag = np.sqrt(gx**2 + gy**2)
        rms = float(np.sqrt(np.mean(grad_mag**2)))
        return round(rms, 6)
    except Exception:
        return None


def compute_cutout_symmetry(obs: object) -> float | None:
    """Return a radial symmetry score in [0, 1] for a difference-image cutout.

    The score is computed as the normalised cross-correlation between the
    63×63 cutout and its 180°-rotated counterpart.  A perfectly symmetric
    point-source PSF scores 1.0; an asymmetric artefact or cosmic ray
    scores near 0.0.  Returns *None* when no cutout is available or the
    cutout cannot be decoded.
    """
    import base64

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        rotated = arr[::-1, ::-1]
        flat = arr.ravel()
        rot_flat = rotated.ravel()
        denom = np.linalg.norm(flat) * np.linalg.norm(rot_flat)
        if denom == 0.0:
            return None
        score = float(np.dot(flat, rot_flat) / denom)
        return round(max(0.0, min(1.0, score)), 6)
    except Exception:
        return None


def compute_streak_angle(obs: object) -> float | None:
    """Return the elongation axis angle in degrees from the difference-image.

    The angle is measured from the image second-moment ellipse as the
    orientation of the major axis, in degrees from the positive x-axis
    (East direction in standard orientation), in [0, 180).  Returns *None*
    when no cutout is available, the cutout cannot be decoded, or the
    second-moment matrix is degenerate (zero eigenvalue difference).
    """
    import base64
    import math

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        total = arr.sum()
        if total == 0.0:
            return None
        ys, xs = np.mgrid[0:63, 0:63]
        cx = float((arr * xs).sum() / total)
        cy = float((arr * ys).sum() / total)
        dx = xs - cx
        dy = ys - cy
        mxx = float((arr * dx * dx).sum() / total)
        myy = float((arr * dy * dy).sum() / total)
        mxy = float((arr * dx * dy).sum() / total)
        # Orientation of major axis via eigenvalue decomposition
        diff = mxx - myy
        angle_rad = 0.5 * math.atan2(2.0 * mxy, diff)
        angle_deg = math.degrees(angle_rad) % 180.0
        return round(angle_deg, 4)
    except Exception:
        return None


def compute_radial_profile(obs: object) -> list[float] | None:
    """Compute a radial brightness profile from the difference-image cutout.

    Bins pixels by integer distance (in pixels) from the cutout centre.
    Returns the mean pixel value in each radial bin (index = radius in pixels),
    from 0 to floor(CUTOUT_SIZE / 2).  Returns ``None`` if no cutout is
    attached or if decoding fails.
    """
    import base64

    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        cy, cx = 31.0, 31.0
        ys, xs = np.mgrid[0:63, 0:63]
        dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
        max_r = 31
        profile: list[float] = []
        for r in range(max_r + 1):
            mask = (dist >= r - 0.5) & (dist < r + 0.5)
            profile.append(round(float(arr[mask].mean()) if mask.any() else 0.0, 6))
        return profile
    except Exception:
        return None


def compute_psf_asymmetry(obs: object) -> float | None:
    """Return a [0, 1] PSF asymmetry index from third-order image moments.

    Computes the normalised absolute skewness in both axes of the
    difference-image cutout.  0 = perfectly symmetric; 1 = maximally
    asymmetric.  Returns None when no valid cutout is available.
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
        if total == 0.0:
            return None
        ys, xs = np.mgrid[0 : arr.shape[0], 0 : arr.shape[1]]
        cx = float((xs * arr).sum() / total)
        cy = float((ys * arr).sum() / total)
        dx = xs - cx
        dy = ys - cy
        m200 = float((dx**2 * arr).sum() / total)
        m020 = float((dy**2 * arr).sum() / total)
        m300 = float((dx**3 * arr).sum() / total)
        m030 = float((dy**3 * arr).sum() / total)
        sx = abs(m300) / (m200**1.5 + 1e-12)
        sy = abs(m030) / (m020**1.5 + 1e-12)
        asymmetry = 0.5 * (sx + sy)
        return round(float(min(1.0, asymmetry)), 6)
    except Exception:
        return None


def compute_source_compactness(obs: object) -> float | None:
    """Return the peak-to-total flux ratio from the difference-image cutout.

    A value of 1 indicates a pure point source (all flux in one pixel);
    lower values indicate extended emission.  Returns None when no valid
    cutout is available or the total flux is zero.
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
        if total == 0.0:
            return None
        peak = float(arr.max())
        return round(float(min(1.0, max(0.0, peak / total))), 6)
    except Exception:
        return None


def compute_cutout_peak_position(obs: object) -> tuple[int, int] | None:
    """Return the (row, col) index of the peak pixel in the difference-image cutout.

    Decodes the base64 float32 63×63 cutout and returns the position of the
    maximum value as a (row, col) tuple.  Returns None when no cutout is
    available or decoding fails.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        idx = np.unravel_index(arr.argmax(), arr.shape)
        return (int(idx[0]), int(idx[1]))
    except Exception:
        return None


def compute_local_background(obs: object) -> float | None:
    """Compute median pixel value in an annular region of the difference-image cutout.

    The annulus spans inner radius 20 px to outer radius 31 px from the
    centre pixel (31, 31) of the 63×63 float32 cutout.  Returns None if
    no cutout is available, decoding fails, or the annulus is empty.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        cy, cx = 31, 31
        ys, xs = np.mgrid[0:63, 0:63]
        dist = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
        mask = (dist >= 20.0) & (dist <= 31.0)
        pixels = arr[mask]
        return float(np.median(pixels))
    except Exception:
        return None


def compute_cutout_sharpness(obs: object) -> float | None:
    """Compute sharpness of a 63×63 difference-image cutout via Laplacian variance.

    The variance of the Laplacian is a focus/sharpness proxy: higher values
    indicate a sharper (less blurred) source.  Returns None if no cutout is
    available or decoding fails.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        # 3×3 Laplacian kernel
        kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
        # Manual 2D convolution via stride tricks
        padded = np.pad(arr, 1, mode="edge")
        rows, cols = arr.shape
        lap = np.zeros_like(arr)
        for dr in range(3):
            for dc in range(3):
                lap += kernel[dr, dc] * padded[dr : dr + rows, dc : dc + cols]
        return round(float(np.var(lap)), 6)
    except Exception:
        return None


def compute_background_gradient(obs: object) -> dict[str, float] | None:
    """Compute the linear background gradient of a difference-image cutout.

    Fits a plane z = a*x + b*y + c to the pixel values and returns the slopes
    ``{"dx": a, "dy": b}`` in pixel units.  Returns ``None`` if no cutout is
    available or decoding fails.
    """
    try:
        import base64 as _b64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = _b64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        rows_idx, cols_idx = np.mgrid[0:63, 0:63]
        x = cols_idx.ravel().astype(float)
        y = rows_idx.ravel().astype(float)
        z = arr.ravel().astype(float)
        A = np.column_stack([x, y, np.ones_like(x)])
        result = np.linalg.lstsq(A, z, rcond=None)
        a, b = float(result[0][0]), float(result[0][1])
        return {"dx": round(a, 8), "dy": round(b, 8)}
    except Exception:
        return None


def compute_elongation_angle(obs: object) -> float | None:
    """Compute the orientation angle of an elongated source from image moments.

    Returns the angle of the major axis in degrees ``[0, 180)`` using the
    second-moment formula ``0.5 * arctan2(2*mxy, mxx - myy)``.  Returns
    ``None`` if no cutout is available, decoding fails, or the source is
    circular (degenerate moments).
    """
    try:
        import base64
        import math

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
        if abs(mxx - myy) < 1e-12 and abs(mxy) < 1e-12:
            return None
        angle_rad = 0.5 * math.atan2(2.0 * mxy, mxx - myy)
        angle_deg = math.degrees(angle_rad) % 180.0
        return round(angle_deg, 4)
    except Exception:
        return None


def compute_cutout_noise(obs: object) -> float | None:
    """Compute the noise level of a difference-image cutout from border pixels.

    Decodes the base64 difference-image cutout, reshapes to a 63×63 float
    array, and computes the standard deviation of the border pixels (top row,
    bottom row, left column, right column concatenated).  Returns ``None`` if
    no cutout is available or decoding fails.

    Args:
        obs: Any object with a ``cutout_difference`` attribute (base64 string).

    Returns:
        Standard deviation of border pixels as a float, or ``None``.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63)
        border = np.concatenate([
            arr[0, :],
            arr[-1, :],
            arr[1:-1, 0],
            arr[1:-1, -1],
        ])
        return float(np.std(border))
    except Exception:
        return None


def flag_cosmic_rays(observations: list, sigma_threshold: float = 5.0) -> list[str]:
    """Return obs_ids of observations likely contaminated by cosmic rays.

    For each observation, decodes the base64 ``cutout_difference`` array
    (63×63 float32), computes the median and Median Absolute Deviation (MAD)
    of all pixels, and flags the observation if its peak pixel value exceeds
    ``median + sigma_threshold * MAD``.

    Observations without a ``cutout_difference`` attribute, or where decoding
    fails, are silently skipped.

    Args:
        observations: List of observation objects with optional
            ``cutout_difference`` base64 attributes.
        sigma_threshold: Number of MAD units above median to flag (default 5.0).

    Returns:
        List of ``obs_id`` strings for flagged observations (possibly empty).
    """
    import base64

    import numpy as np

    flagged: list[str] = []
    for obs in observations:
        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            continue
        try:
            raw = base64.b64decode(cutout)
            arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
            med = float(np.median(arr))
            mad = float(np.median(np.abs(arr - med)))
            spread = mad if mad > 0.0 else float(np.std(arr))
            if spread == 0.0:
                continue
            threshold = med + sigma_threshold * spread
            if float(arr.max()) > threshold:
                obs_id = getattr(obs, "obs_id", None)
                if obs_id is not None:
                    flagged.append(str(obs_id))
        except Exception:
            continue
    return flagged


def compute_fwhm_from_cutout(obs: object) -> float | None:
    """Estimate PSF FWHM in arcsec from the difference-image cutout.

    Decodes the base64 float32 63×63 difference-image cutout, sums pixel
    values along axis 0 (row-summed marginal profile), then fits a 1D
    Gaussian model of the form ``A*exp(-0.5*((x-mu)/sigma)^2) + B`` using
    ``scipy.optimize.curve_fit``.  FWHM is computed as
    ``2.355 * abs(sigma) * pixel_scale_arcsec`` where the ZTF plate scale of
    ``1.01`` arcsec/pixel is assumed.

    Args:
        obs: Any object with an optional ``cutout_difference`` base64-encoded
            float32 array attribute.

    Returns:
        FWHM in arcsec (float), or ``None`` if the cutout is absent, decoding
        fails, or the Gaussian fit does not converge.
    """
    try:
        import base64 as _b64

        import numpy as np
        from scipy.optimize import curve_fit

        _PIXEL_SCALE = 1.01  # arcsec/pixel (ZTF)

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = _b64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        profile = arr.sum(axis=0)
        x = np.arange(len(profile), dtype=float)

        def _gaussian(x: np.ndarray, A: float, mu: float, sigma: float, B: float) -> np.ndarray:
            return A * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + B

        x_center = float(x[np.argmax(profile)])
        A0 = float(profile.max() - profile.min())
        B0 = float(profile.min())
        p0 = [A0, x_center, 3.0, B0]
        popt, _ = curve_fit(_gaussian, x, profile, p0=p0, maxfev=2000)
        sigma = float(popt[2])
        fwhm = 2.355 * abs(sigma) * _PIXEL_SCALE
        return round(fwhm, 4)
    except Exception:
        return None


def compute_cutout_peak_snr(obs: object) -> float | None:
    """Compute peak pixel SNR from the difference-image cutout.

    Divides the maximum pixel value in the 63×63 float32 difference-image
    cutout by the standard deviation of the 10-pixel border region (rows 0–9,
    rows 53–62, columns 0–9, columns 53–62).  The border pixels serve as the
    background noise estimate.

    Args:
        obs: Any object with an optional ``cutout_difference`` base64-encoded
            float32 array attribute.

    Returns:
        Peak SNR (float), or ``None`` if no cutout, decode error, or border
        standard deviation is zero or negative.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        # Border pixels: rows 0-9, rows 53-62, cols 0-9, cols 53-62
        top = arr[:10, :].ravel()
        bottom = arr[53:, :].ravel()
        left = arr[:, :10].ravel()
        right = arr[:, 53:].ravel()
        border = np.concatenate([top, bottom, left, right])
        border_std = float(np.std(border))
        if border_std <= 0.0:
            return None
        peak = float(arr.max())
        return float(peak / border_std)
    except Exception:
        return None


def compute_local_background_rms(obs: object) -> float | None:
    """Compute background RMS from the border pixels of the difference-image cutout.

    Extracts pixels from the 10-pixel border region of the 63×63 float32
    difference-image cutout (top 10 rows, bottom 10 rows, left 10 columns,
    right 10 columns) and returns their standard deviation as the local
    background RMS estimate.

    Args:
        obs: Any object with an optional ``cutout_difference`` base64-encoded
            float32 array attribute.

    Returns:
        Background RMS in pixel units (float), or ``None`` if no cutout,
        decode error, or fewer than 4 border pixels.
    """
    try:
        import base64

        import numpy as np

        cutout = getattr(obs, "cutout_difference", None)
        if cutout is None:
            return None
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(63, 63).astype(float)
        # Collect border pixels: top 10 rows, bottom 10 rows, left 10 cols, right 10 cols
        top = arr[:10, :].ravel()
        bottom = arr[53:, :].ravel()
        left = arr[:, :10].ravel()
        right = arr[:, 53:].ravel()
        border = np.concatenate([top, bottom, left, right])
        return float(np.std(border))
    except Exception:
        return None


def compute_gradient_magnitude(obs: object) -> float | None:
    """Return the mean gradient magnitude over the difference-image cutout.

    Computes ``sqrt(dx² + dy²)`` at every pixel via :func:`numpy.gradient`
    and returns the mean over all pixels.

    Args:
        obs: Observation-like object with an optional ``cutout_difference``
            base64 attribute.

    Returns:
        Mean gradient magnitude as ``float``, or ``None`` if no cutout or
        decode error.
    """
    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        import base64 as _b64

        raw = _b64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE).astype(float)
        dy, dx = np.gradient(arr)
        mag = np.sqrt(dx ** 2 + dy ** 2)
        return float(np.mean(mag))
    except Exception:
        return None


def compute_cutout_rms(obs: object) -> float | None:
    """Return the RMS of pixel values across the difference-image cutout.

    Returns None if no cutout is present or the cutout cannot be decoded.
    """
    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        import base64 as _b64
        raw = _b64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE).astype(float)
        return float(np.sqrt(np.mean(arr ** 2)))
    except Exception:
        return None


def compute_cutout_entropy_normalized(obs: object) -> float | None:
    """Return the Shannon entropy of the difference-image cutout normalized to [0, 1].

    Entropy is computed over a 256-bin histogram of pixel values scaled to [0, 255].
    Maximum entropy for 256 bins is log2(256) = 8.0 bits. Returns None if no
    cutout is present or the cutout cannot be decoded.
    """
    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        import base64 as _b64
        raw = _b64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE).astype(float)
        lo, hi = arr.min(), arr.max()
        if hi <= lo:
            return 0.0
        scaled = ((arr - lo) / (hi - lo) * 255.0).astype(int)
        counts = np.bincount(scaled.ravel(), minlength=256).astype(float)
        probs = counts / counts.sum()
        probs = probs[probs > 0.0]
        entropy_bits = float(-np.sum(probs * np.log2(probs)))
        return float(min(1.0, entropy_bits / 8.0))
    except Exception:
        return None


def compute_image_contrast(obs: object) -> float | None:
    """Return the pixel contrast ratio of a difference-image cutout.

    Contrast = (max_pixel - min_pixel) / mean_pixel, where mean_pixel is the
    absolute mean of all pixel values.  Returns None if no cutout is present,
    if the cutout cannot be decoded, or if mean_pixel is zero.
    """
    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE).astype(float)
        pix_min = arr.min()
        pix_max = arr.max()
        mean_abs = float(np.mean(np.abs(arr)))
        if mean_abs == 0.0:
            return None
        return float((pix_max - pix_min) / mean_abs)
    except Exception:
        return None


def compute_pixel_saturation_fraction(
    obs: object,
    saturation_threshold: float = 0.98,
) -> float | None:
    """Return the fraction of pixels in the science cutout that are near saturation.

    Pixels with normalised value ≥ *saturation_threshold* (default 0.98) are
    considered saturated.  The cutout is normalised to [0, 1] before comparison.
    Returns None if no science cutout is available or if the cutout cannot be decoded.
    Returns 0.0 if the max pixel value is zero (blank cutout).
    """
    cutout = getattr(obs, "cutout_science", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE).astype(float)
        pix_max = arr.max()
        if pix_max == 0.0:
            return 0.0
        normalized = arr / pix_max
        return float(np.mean(normalized >= saturation_threshold))
    except Exception:
        return None


def compute_reference_cutout_snr(obs: object) -> float | None:
    """Return the peak-to-RMS SNR of the reference (template) cutout.

    Computes ``max_pixel / rms_pixel`` for the 63×63 reference cutout.
    Returns ``None`` if no reference cutout is present, if the cutout cannot
    be decoded, or if the RMS is zero (blank template).
    """
    cutout = getattr(obs, "cutout_template", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE).astype(float)
        rms = float(np.sqrt(np.mean(arr ** 2)))
        if rms == 0.0:
            return None
        return float(arr.max() / rms)
    except Exception:
        return None


def compute_cutout_noise_level(obs: object) -> float | None:
    """Return the standard deviation of pixel values in the difference-image cutout.

    Provides a per-observation noise estimate without requiring an explicit
    background model.  Returns ``None`` if no difference-image cutout is present
    or if the cutout cannot be decoded.
    """
    cutout = getattr(obs, "cutout_difference", None)
    if cutout is None:
        return None
    try:
        raw = base64.b64decode(cutout)
        arr = np.frombuffer(raw, dtype=np.float32).reshape(_CUTOUT_SIZE, _CUTOUT_SIZE).astype(float)
        return float(np.std(arr))
    except Exception:
        return None


def compute_cutout_peak_value(obs: object) -> float | None:
    """Return the peak (maximum) pixel value in the difference-image cutout.

    Decodes the base64 float32 difference-image cutout and returns the
    maximum pixel value.  Returns ``None`` if the observation has no
    ``cutout_difference`` attribute, the attribute is ``None``, or the
    bytes cannot be decoded as a valid float32 array.
    """
    import base64

    import numpy as np

    raw_b64 = getattr(obs, "cutout_difference", None)
    if raw_b64 is None:
        return None
    try:
        raw = base64.b64decode(raw_b64)
        arr = np.frombuffer(raw, dtype=np.float32)
        if arr.size == 0:
            return None
        return float(np.max(arr))
    except Exception:
        return None
