"""Per-field photometric zero-point fit and magnitude correction.

Usage:
    python Skills/photometric_calibration.py <tracklets.json>
        [--band r] [--ref-catalog gaia] [--out PATH] [--json]

Reads a tracklet JSON file, loads reference catalog magnitudes, fits
a photometric zero-point (and optional color term) per field night,
and outputs corrected instrumental magnitudes.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schemas import Observation, Tracklet  # noqa: E402

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class RefStar(NamedTuple):
    ra_deg: float
    dec_deg: float
    mag: float
    mag_err: float


class ZeroPointFit(NamedTuple):
    zero_point: float
    zero_point_err: float
    color_term: float
    n_stars: int
    rms_residual: float


# ---------------------------------------------------------------------------
# Synthetic reference catalog (placeholder for real Gaia/PS1 query)
# ---------------------------------------------------------------------------


def _query_ref_catalog(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float = 0.5,
    band: str = "r",
) -> list[RefStar]:
    """Fetch reference star magnitudes from Gaia DR3 / Pan-STARRS near a position.

    Returns an empty list when astroquery is unavailable (production would require
    network access and Gaia credentials).
    """
    try:
        import astropy.units as u
        from astropy.coordinates import SkyCoord
        from astroquery.gaia import Gaia  # type: ignore[import]

        coord = SkyCoord(ra=ra_deg, dec=dec_deg, unit="deg")
        Gaia.ROW_LIMIT = 100
        job = Gaia.cone_search_async(coord, radius=u.Quantity(radius_deg, u.deg))
        result = job.get_results()
        # Gaia G band as proxy; real implementation maps to survey filter
        stars = []
        for row in result:
            g = float(row.get("phot_g_mean_mag", 0.0) or 0.0)
            if 14.0 <= g <= 20.0:
                stars.append(RefStar(
                    ra_deg=float(row["ra"]),
                    dec_deg=float(row["dec"]),
                    mag=g,
                    mag_err=0.01,
                ))
        return stars
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Angular separation helper
# ---------------------------------------------------------------------------


def _sep_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = (math.radians(x) for x in (ra1, dec1, ra2, dec2))
    cos_sep = (math.sin(d1) * math.sin(d2)
               + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2))
    cos_sep = max(-1.0, min(1.0, cos_sep))
    return math.degrees(math.acos(cos_sep)) * 3600.0


# ---------------------------------------------------------------------------
# Zero-point fitting
# ---------------------------------------------------------------------------


def fit_zero_point(
    obs_mags: list[float],
    ref_mags: list[float],
    weights: list[float] | None = None,
) -> ZeroPointFit:
    """Fit photometric zero-point ZP where mag_ref = mag_inst + ZP.

    Uses weighted mean; optionally includes a first-order color correction term
    (here simplified to the mean offset).

    Args:
        obs_mags: Instrumental (uncalibrated) magnitudes.
        ref_mags: Corresponding reference magnitudes.
        weights:  Per-star weights (e.g., 1/sigma^2). Defaults to uniform.

    Returns:
        :class:`ZeroPointFit` with ``zero_point``, ``zero_point_err``,
        ``color_term`` (set to 0.0 in this simplified implementation),
        ``n_stars``, and ``rms_residual``.
    """
    n = len(obs_mags)
    if n == 0:
        return ZeroPointFit(0.0, 999.0, 0.0, 0, 999.0)

    if weights is None:
        weights = [1.0] * n

    diffs = [r - o for r, o in zip(ref_mags, obs_mags)]
    total_w = sum(weights)
    zp = sum(w * d for w, d in zip(weights, diffs)) / total_w
    residuals = [d - zp for d in diffs]
    rms = math.sqrt(sum(r**2 for r in residuals) / n)

    # Formal error estimate: weighted std / sqrt(n)
    var_w = sum(w * r**2 for w, r in zip(weights, residuals)) / total_w
    zp_err = math.sqrt(var_w / n) if n > 1 else 999.0

    return ZeroPointFit(
        zero_point=round(zp, 4),
        zero_point_err=round(zp_err, 4),
        color_term=0.0,
        n_stars=n,
        rms_residual=round(rms, 4),
    )


# ---------------------------------------------------------------------------
# Per-observation calibration
# ---------------------------------------------------------------------------


def calibrate_observation(obs: Observation, zero_point: float) -> dict:
    """Apply a zero-point correction to a single observation.

    Returns a dict with corrected magnitude and calibration metadata.
    """
    corrected_mag = obs.mag + zero_point
    return {
        "obs_id": obs.obs_id,
        "ra_deg": obs.ra_deg,
        "dec_deg": obs.dec_deg,
        "jd": obs.jd,
        "mag_inst": round(obs.mag, 4),
        "zero_point": zero_point,
        "mag_cal": round(corrected_mag, 4),
        "mag_err": obs.mag_err,
        "band": obs.band,
        "mission": obs.mission,
    }


# ---------------------------------------------------------------------------
# Tracklet-level calibration
# ---------------------------------------------------------------------------


def calibrate_tracklet(
    tracklet: Tracklet,
    band: str = "r",
    match_radius_arcsec: float = 3.0,
) -> dict:
    """Calibrate all observations in a tracklet via a field-level zero-point fit.

    Queries the reference catalog near the first observation, matches reference
    stars to the observation positions, fits the zero-point, and applies it to
    all observations.

    Returns a dict with:
        - ``object_id``
        - ``zero_point_fit`` (a :class:`ZeroPointFit` as dict)
        - ``calibrated_observations`` (list of corrected obs dicts)
        - ``n_obs``
    """
    if not tracklet.observations:
        return {
            "object_id": tracklet.object_id,
            "zero_point_fit": ZeroPointFit(0.0, 999.0, 0.0, 0, 999.0)._asdict(),
            "calibrated_observations": [],
            "n_obs": 0,
        }

    first = tracklet.observations[0]
    ref_stars = _query_ref_catalog(first.ra_deg, first.dec_deg, band=band)

    # Match reference stars to observations (simple nearest-neighbour within radius)
    obs_mags: list[float] = []
    ref_mags: list[float] = []
    ref_weights: list[float] = []

    for obs in tracklet.observations:
        best_sep = match_radius_arcsec + 1.0
        best_ref: RefStar | None = None
        for star in ref_stars:
            sep = _sep_arcsec(obs.ra_deg, obs.dec_deg, star.ra_deg, star.dec_deg)
            if sep < best_sep:
                best_sep = sep
                best_ref = star
        if best_ref is not None:
            obs_mags.append(obs.mag)
            ref_mags.append(best_ref.mag)
            ref_weights.append(1.0 / max(best_ref.mag_err**2, 1e-6))

    zp_fit = fit_zero_point(obs_mags, ref_mags, ref_weights if ref_weights else None)
    zp = zp_fit.zero_point if zp_fit.n_stars > 0 else 0.0

    calibrated = [calibrate_observation(obs, zp) for obs in tracklet.observations]

    return {
        "object_id": tracklet.object_id,
        "zero_point_fit": zp_fit._asdict(),
        "calibrated_observations": calibrated,
        "n_obs": len(calibrated),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Photometric zero-point calibration for NEO tracklets."
    )
    parser.add_argument("input", help="Tracklet JSON file")
    parser.add_argument("--band", default="r", help="Photometric band (default: r)")
    parser.add_argument("--out", default=None, help="Output file path")
    parser.add_argument("--json", dest="json_out", action="store_true",
                        help="Output JSON instead of text table")
    args = parser.parse_args(argv)

    raw = json.loads(Path(args.input).read_text())
    # Support both a list of tracklets and a single tracklet dict
    if isinstance(raw, dict):
        raw = [raw]

    results = []
    for item in raw:
        tracklet = Tracklet(**item)
        result = calibrate_tracklet(tracklet, band=args.band)
        results.append(result)

    if args.json_out:
        content = json.dumps(results, indent=2) + "\n"
    else:
        lines = [
            f"{'Object':<20} {'N_obs':>5} {'ZP':>7} {'ZP_err':>7} {'N_ref':>6} {'RMS':>7}",
            "-" * 55,
        ]
        for r in results:
            zp = r["zero_point_fit"]
            lines.append(
                f"{r['object_id']:<20} {r['n_obs']:>5} "
                f"{zp['zero_point']:>7.3f} {zp['zero_point_err']:>7.3f} "
                f"{zp['n_stars']:>6} {zp['rms_residual']:>7.3f}"
            )
        lines.append(f"\n{len(results)} tracklet(s) calibrated.")
        content = "\n".join(lines) + "\n"

    if args.out:
        Path(args.out).write_text(content)
        print(f"Calibration results written to {args.out}.")
    else:
        sys.stdout.write(content)


if __name__ == "__main__":
    main()
