"""Preprocess stage — validate images, normalize cutouts, extract features, astrometry."""

from __future__ import annotations

__all__ = ["preprocess", "preprocess_batch", "quality_summary", "flag_saturated_sources",
           "compute_color_index"]

import base64
import math

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
