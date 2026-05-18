"""Score stage — hazard assessment, PHA flag, discovery/followup priority."""

from __future__ import annotations

__all__ = ["score", "score_batch", "rank_candidates", "discovery_report",
           "followup_priority_table", "pha_candidates", "compute_statistics",
           "close_approach_candidates", "absolute_magnitude_from_diameter",
           "compute_impact_energy", "compute_novelty_score",
           "compute_threat_score", "filter_by_alert_pathway"]

import math
import uuid

from orbit import classify_neo, compute_moid
from schemas import (
    AlertPathway,
    CandidateExplanation,
    CandidateFeatures,
    HazardAssessment,
    HazardFlag,
    NEOClass,
    NEOPosterior,
    NEOStatistics,
    OrbitalElements,
    ScoredNEO,
    ScoringMetadata,
    Tracklet,
)

_SCORER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# PHA thresholds
# ---------------------------------------------------------------------------

_PHA_MOID_AU = 0.05
_PHA_H_MAG = 22.0  # absolute magnitude proxy for 140 m diameter
_GEOMETRIC_ALBEDO_DEFAULT = 0.14

# ---------------------------------------------------------------------------
# Absolute magnitude / diameter
# ---------------------------------------------------------------------------


def _absolute_magnitude(mean_mag: float, helio_r_au: float = 1.0, geo_r_au: float = 1.0) -> float:
    """Estimate absolute magnitude H from apparent magnitude, neglecting phase."""
    return mean_mag - 5.0 * math.log10(helio_r_au * geo_r_au)


def _diameter_from_h(h: float, albedo: float = _GEOMETRIC_ALBEDO_DEFAULT) -> float:
    """Estimate diameter in metres from absolute magnitude H and geometric albedo."""
    return 1329e3 * 10 ** (-h / 5.0) / math.sqrt(albedo)


# ---------------------------------------------------------------------------
# Log-score model
# ---------------------------------------------------------------------------

# Log priors (from CLAUDE.md)
_LOG_PRIORS: dict[str, float] = {
    "neo_candidate": math.log(0.05),
    "known_object": math.log(0.30),
    "main_belt_asteroid": math.log(0.35),
    "stellar_artifact": math.log(0.25),
    "other_solar_system": math.log(0.05),
}

# Feature weights for neo_candidate hypothesis
_NEO_WEIGHTS: dict[str, float] = {
    "real_bogus_score": 2.0,
    "arc_coverage_score": 1.5,
    "nights_observed_score": 1.5,
    "motion_consistency_score": 1.2,
    "orbit_quality_score": 1.0,
    "known_object_score": -2.5,      # penalise
    "stellar_artifact_score": -2.0,  # penalise
    "main_belt_consistency_score": -1.5,  # penalise
}


def _compute_log_score_neo(features: CandidateFeatures) -> float:
    score = _LOG_PRIORS["neo_candidate"]
    for attr, w in _NEO_WEIGHTS.items():
        val = getattr(features, attr, None)
        if val is not None:
            score += w * val
    return score


# ---------------------------------------------------------------------------
# Alert pathway gate
# ---------------------------------------------------------------------------


def _determine_alert_pathway(
    posterior: NEOPosterior,
    features: CandidateFeatures,
    moid_au: float | None,
    orbit_quality: int,
) -> AlertPathway:
    """Ordered gate determining the appropriate alert pathway."""
    if features.known_object_score is not None and features.known_object_score > 0.8:
        return "known_object"

    rb = features.real_bogus_score
    if rb is None or rb < 0.90:
        return "internal_candidate"

    if moid_au is None or orbit_quality < 2:
        return "internal_candidate"

    if moid_au > _PHA_MOID_AU:
        return "internal_candidate"

    if posterior.neo_candidate < 0.5:
        return "internal_candidate"

    # MOID ≤ 0.05 AU, quality ≥ 2, rb ≥ 0.90, not known
    # Start with MPC submission; NASA pathway requires external confirmation
    return "mpc_submission"


# ---------------------------------------------------------------------------
# Hazard flag
# ---------------------------------------------------------------------------


def _compute_hazard_flag(
    moid_au: float | None,
    h: float | None,
    neo_class: NEOClass,
    orbit_quality: int,
) -> HazardFlag:
    if moid_au is None or h is None or orbit_quality < 2:
        return "unknown"
    if moid_au <= _PHA_MOID_AU and h <= _PHA_H_MAG:
        return "pha_candidate"
    if moid_au <= 0.2:
        return "close_approach"
    return "nominal"


# ---------------------------------------------------------------------------
# Explanation builder
# ---------------------------------------------------------------------------


def _build_explanation(
    features: CandidateFeatures,
    posterior: NEOPosterior,
    hazard_flag: HazardFlag,
    moid_au: float | None,
) -> CandidateExplanation:
    supporting: list[str] = []
    contra: list[str] = []

    if features.real_bogus_score is not None:
        if features.real_bogus_score >= 0.9:
            supporting.append(f"High real/bogus score: {features.real_bogus_score:.2f}")
        elif features.real_bogus_score < 0.65:
            contra.append(f"Low real/bogus score: {features.real_bogus_score:.2f}")

    if features.nights_observed_score is not None and features.nights_observed_score > 0.3:
        supporting.append(f"Multi-night arc (nights score: {features.nights_observed_score:.2f})")

    if features.motion_consistency_score is not None and features.motion_consistency_score > 0.7:
        mc = features.motion_consistency_score
        supporting.append(f"Consistent linear motion (score: {mc:.2f})")

    if features.orbit_quality_score is not None and features.orbit_quality_score > 0.5:
        oq = features.orbit_quality_score
        supporting.append(f"Reliable orbital solution (quality: {oq:.2f})")

    if moid_au is not None and moid_au <= _PHA_MOID_AU:
        supporting.append(f"MOID ≤ 0.05 AU: {moid_au:.4f} AU")

    if posterior.stellar_artifact > 0.3:
        contra.append(f"Non-negligible artifact probability: {posterior.stellar_artifact:.2f}")

    if posterior.main_belt_asteroid > 0.4:
        contra.append(f"Consistent with main-belt orbit: {posterior.main_belt_asteroid:.2f}")

    if features.known_object_score is not None and features.known_object_score > 0.5:
        contra.append(f"Possible known object match (score: {features.known_object_score:.2f})")

    p = posterior.neo_candidate
    summary = (
        f"NEO candidate probability: {p:.2%}. "
        f"Hazard flag: {hazard_flag}. "
        f"MOID: {moid_au:.4f} AU." if moid_au else f"NEO candidate probability: {p:.2%}. "
        f"Hazard flag: {hazard_flag}. MOID: unknown."
    )

    return CandidateExplanation(
        summary=summary,
        supporting_evidence=tuple(supporting),
        contra_evidence=tuple(contra),
        model_version=_SCORER_VERSION,
    )


# ---------------------------------------------------------------------------
# Discovery/followup/scientific priority
# ---------------------------------------------------------------------------


def _discovery_priority(
    posterior: NEOPosterior,
    features: CandidateFeatures,
    hazard_flag: HazardFlag,
) -> float:
    p = posterior.neo_candidate
    h_bonus = 0.3 if hazard_flag == "pha_candidate" else 0.0
    orbit_bonus = (features.orbit_quality_score or 0.0) * 0.2
    return min(1.0, p * 0.5 + h_bonus + orbit_bonus)


def _followup_value(
    features: CandidateFeatures,
    orbital: OrbitalElements | None,
) -> float:
    brightness = features.brightness_score or 0.5
    arc = features.arc_coverage_score or 0.0
    orbit_q = features.orbit_quality_score or 0.0
    # High value if bright and short arc (needs more observations)
    return min(1.0, brightness * 0.4 + (1.0 - arc) * 0.4 + (1.0 - orbit_q) * 0.2)


def _scientific_interest(
    orbital: OrbitalElements | None,
) -> float:
    if orbital is None:
        return 0.0
    a = orbital.semi_major_axis_au
    e = orbital.eccentricity
    i = orbital.inclination_deg
    # High interest: unusual semi-major axis, high eccentricity, or high inclination
    a_score = min(1.0, abs(a - 1.0) / 2.0)
    e_score = min(1.0, e / 0.9)
    i_score = min(1.0, i / 90.0)
    return float((a_score + e_score + i_score) / 3.0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def score(
    tracklet: Tracklet,
    features: CandidateFeatures,
    posterior: NEOPosterior,
    orbital: OrbitalElements | None,
    pipeline_run_id: str | None = None,
) -> ScoredNEO:
    """Compute full hazard assessment and scoring for a classified tracklet."""
    from astropy.time import Time  # type: ignore[import]

    scored_at_jd = float(Time.now().jd)
    run_id = pipeline_run_id or str(uuid.uuid4())

    # NEO class and MOID
    neo_class: NEOClass = classify_neo(orbital) if orbital else "unknown"
    moid_au = compute_moid(orbital) if orbital else None
    orbit_quality = int(orbital.quality_code) if orbital else 0

    # Absolute magnitude and diameter
    mags = [o.mag for o in tracklet.observations if o.mag < 99]
    mean_mag = sum(mags) / len(mags) if mags else None
    h_mag = _absolute_magnitude(mean_mag) if mean_mag else None
    diam_m = _diameter_from_h(h_mag) if h_mag else None

    hazard_flag = _compute_hazard_flag(moid_au, h_mag, neo_class, orbit_quality)
    alert_pathway = _determine_alert_pathway(posterior, features, moid_au, orbit_quality)
    explanation = _build_explanation(features, posterior, hazard_flag, moid_au)

    hazard = HazardAssessment(
        hazard_flag=hazard_flag,
        moid_au=moid_au,
        estimated_diameter_m=diam_m,
        absolute_magnitude_h=h_mag,
        neo_class=neo_class,
        alert_pathway=alert_pathway,
        explanation=explanation,
        orbital_elements=orbital,
    )

    # Update feature scores from orbit
    moid_score: float | None = None
    if moid_au is not None:
        moid_score = (
            float(max(0.0, 1.0 - moid_au / _PHA_MOID_AU))
            if moid_au <= _PHA_MOID_AU
            else 0.0
        )

    orbit_quality_score: float | None = None
    if orbital:
        orbit_quality_score = float((orbital.quality_code - 1) / 3.0)

    pha_flag_confidence: float | None = None
    if hazard_flag == "pha_candidate":
        pha_flag_confidence = posterior.neo_candidate

    updated_features = features.model_copy(
        update={
            "moid_score": moid_score,
            "orbit_quality_score": orbit_quality_score,
            "pha_flag_confidence": pha_flag_confidence,
            "neo_class_confidence": posterior.neo_candidate,
        }
    )

    dp = _discovery_priority(posterior, updated_features, hazard_flag)
    fv = _followup_value(updated_features, orbital)
    si = _scientific_interest(orbital)

    # Populate close_approach_au: use MOID when orbit quality is sufficient.
    # MOID is the minimum distance between the two orbits; it equals the closest
    # possible approach but not a specific predicted flyby distance.
    close_approach_au: float | None = None
    if moid_au is not None and orbit_quality >= 2:
        close_approach_au = moid_au

    metadata = ScoringMetadata(
        scorer_version=_SCORER_VERSION,
        scored_at_jd=scored_at_jd,
        pipeline_run_id=run_id,
        discovery_priority=dp,
        followup_value=fv,
        scientific_interest=si,
        close_approach_au=close_approach_au,
    )

    return ScoredNEO(
        tracklet=tracklet,
        features=updated_features,
        posterior=posterior,
        hazard=hazard,
        metadata=metadata,
    )


def rank_candidates(neos: list[ScoredNEO]) -> list[ScoredNEO]:
    """Return a copy of ``neos`` sorted by descending discovery priority.

    PHA candidates are always placed above non-PHA candidates of equal
    numerical priority.  Within the same hazard tier, objects are sorted by
    ``metadata.discovery_priority`` (descending).
    """
    def _sort_key(neo: ScoredNEO) -> tuple[int, float]:
        pha_tier = 0 if neo.hazard.hazard_flag == "pha_candidate" else 1
        return (pha_tier, -neo.metadata.discovery_priority)

    return sorted(neos, key=_sort_key)


def score_batch(
    items: list[tuple[Tracklet, CandidateFeatures, NEOPosterior, OrbitalElements | None]],
    pipeline_run_id: str | None = None,
) -> list[ScoredNEO]:
    """Score a list of (tracklet, features, posterior, orbital) tuples.

    Each item is passed to :func:`score` with a shared ``pipeline_run_id``.
    Returns results in the same order as the input list.
    """
    return [score(t, f, p, o, pipeline_run_id=pipeline_run_id) for t, f, p, o in items]


def discovery_report(neo: ScoredNEO) -> dict:
    """Return a comprehensive discovery summary dict for human review or export.

    Combines tracklet geometry, classification posterior, hazard assessment,
    all feature scores, and scoring metadata into a single flat or nested
    structure suitable for JSON serialisation or display.
    """
    f = neo.features
    p = neo.posterior
    h = neo.hazard
    m = neo.metadata
    t = neo.tracklet
    return {
        "object_id": t.object_id,
        "n_observations": len(t.observations),
        "arc_days": round(t.arc_days, 4),
        "motion_rate_arcsec_hr": round(t.motion_rate_arcsec_per_hour, 4),
        "motion_pa_deg": round(t.motion_pa_degrees, 2),
        "posterior": {
            "neo_candidate": round(p.neo_candidate, 4),
            "known_object": round(p.known_object, 4),
            "main_belt_asteroid": round(p.main_belt_asteroid, 4),
            "stellar_artifact": round(p.stellar_artifact, 4),
            "other_solar_system": round(p.other_solar_system, 4),
        },
        "features": {
            "real_bogus_score": f.real_bogus_score,
            "motion_consistency_score": f.motion_consistency_score,
            "arc_coverage_score": f.arc_coverage_score,
            "nights_observed_score": f.nights_observed_score,
            "orbit_quality_score": f.orbit_quality_score,
            "moid_score": f.moid_score,
            "known_object_score": f.known_object_score,
        },
        "hazard": {
            "hazard_flag": h.hazard_flag,
            "alert_pathway": h.alert_pathway,
            "moid_au": h.moid_au,
            "estimated_diameter_m": h.estimated_diameter_m,
            "absolute_magnitude_h": h.absolute_magnitude_h,
            "neo_class": h.neo_class,
        },
        "scoring": {
            "discovery_priority": round(m.discovery_priority, 4),
            "followup_value": round(m.followup_value, 4),
            "scientific_interest": round(m.scientific_interest, 4),
            "close_approach_au": m.close_approach_au,
            "scorer_version": m.scorer_version,
            "pipeline_run_id": m.pipeline_run_id,
        },
    }


def followup_priority_table(neos: list[ScoredNEO]) -> list[dict]:
    """Return a flat table of follow-up priorities for all candidates.

    Combines key fields from :func:`discovery_report` into a flat dict per
    candidate, sorted by descending ``discovery_priority`` with PHA candidates
    first (mirrors :func:`rank_candidates`).

    Suitable for CSV export, dashboard display, or MPC queue generation.

    Returns a list of dicts with keys:
      ``rank``, ``object_id``, ``hazard_flag``, ``alert_pathway``,
      ``discovery_priority``, ``moid_au``, ``neo_class``,
      ``n_observations``, ``arc_days``, ``motion_rate_arcsec_hr``.
    """
    ranked = rank_candidates(neos)
    rows = []
    for i, neo in enumerate(ranked):
        report = discovery_report(neo)
        rows.append({
            "rank": i + 1,
            "object_id": report["object_id"],
            "hazard_flag": report["hazard"]["hazard_flag"],
            "alert_pathway": report["hazard"]["alert_pathway"],
            "discovery_priority": report["scoring"]["discovery_priority"],
            "moid_au": report["hazard"]["moid_au"],
            "neo_class": report["hazard"]["neo_class"],
            "n_observations": report["n_observations"],
            "arc_days": report["arc_days"],
            "motion_rate_arcsec_hr": report["motion_rate_arcsec_hr"],
        })
    return rows


def pha_candidates(neos: list) -> list:
    """Return only ScoredNEO objects with hazard_flag == 'pha_candidate'."""
    return [neo for neo in neos if neo.hazard.hazard_flag == "pha_candidate"]


def compute_statistics(neos: list) -> NEOStatistics:
    """Compute aggregate statistics from a list of ScoredNEO objects.

    Returns a :class:`~schemas.NEOStatistics` instance.
    """
    from collections import Counter

    priorities = [neo.metadata.discovery_priority for neo in neos]
    hazard_flags = [neo.hazard.hazard_flag for neo in neos]
    pathways = [neo.hazard.alert_pathway for neo in neos]
    neo_classes = [neo.hazard.neo_class for neo in neos]

    return NEOStatistics(
        n_total=len(neos),
        n_pha_candidates=hazard_flags.count("pha_candidate"),
        n_mpc_submission=pathways.count("mpc_submission"),
        n_internal_candidate=pathways.count("internal_candidate"),
        n_known_object=pathways.count("known_object"),
        mean_discovery_priority=sum(priorities) / len(priorities) if priorities else 0.0,
        max_discovery_priority=max(priorities) if priorities else 0.0,
        neo_class_distribution=dict(Counter(neo_classes)),
    )


def close_approach_candidates(neos: list, max_moid_au: float = 0.05) -> list:
    """Return ScoredNEO objects with a known MOID at or below *max_moid_au*.

    Unlike :func:`pha_candidates` (which also requires H ≤ 22), this function
    only filters on MOID, letting callers set any threshold — e.g. 0.1 AU for
    enhanced monitoring or 0.002 AU for imminent-flyby follow-up.

    Objects with ``moid_au=None`` (orbit not well-determined) are excluded.
    """
    return [
        neo for neo in neos
        if neo.hazard.moid_au is not None and neo.hazard.moid_au <= max_moid_au
    ]


def absolute_magnitude_from_diameter(diameter_m: float, albedo: float = 0.14) -> float:
    """Compute absolute magnitude H from diameter and geometric albedo.

    Inverse of the standard diameter–albedo relation:
        D = 1329 km / sqrt(p_v) * 10^(-H/5)
    Rearranged:
        H = -5 * log10(D / (1329000 * sqrt(p_v)))

    where D is in metres.  Returns ``float('inf')`` for non-positive inputs.
    """
    if diameter_m <= 0.0 or albedo <= 0.0:
        return float("inf")
    import math as _math
    return -5.0 * _math.log10(diameter_m * _math.sqrt(albedo) / 1_329_000.0)


def compute_impact_energy(
    diameter_m: float,
    velocity_km_s: float,
    density_kg_m3: float = 2500.0,
) -> float:
    """Kinetic impact energy in megatons TNT equivalent.

    E_k = 0.5 * m * v²  with mass from a sphere of given density.
    1 megaton TNT = 4.184e15 J.
    Returns 0.0 for non-positive diameter, velocity, or density.
    """
    if diameter_m <= 0.0 or velocity_km_s <= 0.0 or density_kg_m3 <= 0.0:
        return 0.0
    radius_m = diameter_m / 2.0
    volume_m3 = (4.0 / 3.0) * math.pi * radius_m ** 3
    mass_kg = density_kg_m3 * volume_m3
    velocity_m_s = velocity_km_s * 1_000.0
    joules = 0.5 * mass_kg * velocity_m_s ** 2
    megatons = joules / 4.184e15
    return round(megatons, 6)


def compute_novelty_score(neo: object, catalog_elements: list) -> float:
    """Orbital novelty score in [0, 1] relative to a catalog of known objects.

    Computes a distance metric between the NEO's orbital elements and every
    element in ``catalog_elements`` using a weighted combination of Δa, Δe, Δi.
    Returns 1.0 (maximum novelty) when the catalog is empty or orbital elements
    are unavailable.  Returns 0.0 when an exact match is found.

    Distance metric: d = sqrt((Δa/3)² + (Δe)² + (Δi/180)²)
    Score = min(1, min_distance / reference_distance) where reference_distance = 1.
    """
    el = getattr(getattr(neo, "hazard", None), "orbital_elements", None)
    if el is None or not catalog_elements:
        return 1.0

    a0 = el.semi_major_axis_au
    e0 = el.eccentricity
    i0 = el.inclination_deg

    min_dist = float("inf")
    for cat_el in catalog_elements:
        da = (cat_el.semi_major_axis_au - a0) / 3.0
        de = cat_el.eccentricity - e0
        di = (cat_el.inclination_deg - i0) / 180.0
        d = math.sqrt(da**2 + de**2 + di**2)
        if d < min_dist:
            min_dist = d

    return round(min(1.0, float(min_dist)), 4)


def compute_threat_score(neo: ScoredNEO) -> float:
    """Composite threat score combining MOID, H magnitude, and orbit quality.

    Combines three threat-relevant signals into a single [0, 1] score:

    - **MOID proximity**: 1.0 if MOID ≤ 0.01 AU, linearly decaying to 0 at 0.05 AU;
      0.5 if MOID is unknown.
    - **Size proxy**: 1.0 if H ≤ 18 (>1 km), linearly decaying to 0 at H = 25.
    - **Orbit quality**: quality_code / 4.0 (capped at 1).

    The composite score is the geometric mean of the three components.
    Returns 0.0 if all signals are absent.

    Args:
        neo: A ScoredNEO object.

    Returns:
        Threat score in [0, 1].
    """
    haz = neo.hazard

    # MOID component
    moid = haz.moid_au
    if moid is None:
        moid_score = 0.5
    elif moid <= 0.01:
        moid_score = 1.0
    elif moid >= 0.05:
        moid_score = 0.0
    else:
        moid_score = 1.0 - (moid - 0.01) / 0.04

    # Size component from H magnitude
    h = haz.absolute_magnitude_h
    if h is None:
        size_score = 0.5
    elif h <= 18.0:
        size_score = 1.0
    elif h >= 25.0:
        size_score = 0.0
    else:
        size_score = 1.0 - (h - 18.0) / 7.0

    # Orbit quality component
    quality = None
    if haz.orbital_elements is not None:
        quality = getattr(haz.orbital_elements, "quality_code", None)
    if quality is None:
        orbit_score = 0.5
    else:
        orbit_score = min(1.0, int(quality) / 4.0)

    # Geometric mean of three components
    product = moid_score * size_score * orbit_score
    if product <= 0.0:
        return 0.0
    return round(product ** (1.0 / 3.0), 4)


def filter_by_alert_pathway(neos: list[ScoredNEO], pathway: str) -> list[ScoredNEO]:
    """Filter a list of ScoredNEOs to those with a specific alert pathway.

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.
        pathway: The alert pathway to filter on (e.g. ``"mpc_submission"``,
            ``"nasa_pdco_notify"``, ``"internal_candidate"``).

    Returns:
        Filtered list containing only NEOs whose ``hazard.alert_pathway``
        matches ``pathway`` exactly.
    """
    return [n for n in neos if n.hazard.alert_pathway == pathway]
