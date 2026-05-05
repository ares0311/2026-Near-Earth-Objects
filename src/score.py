"""Score stage — hazard assessment, PHA flag, discovery/followup priority."""

from __future__ import annotations

__all__ = ["score"]

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

    metadata = ScoringMetadata(
        scorer_version=_SCORER_VERSION,
        scored_at_jd=scored_at_jd,
        pipeline_run_id=run_id,
        discovery_priority=dp,
        followup_value=fv,
        scientific_interest=si,
    )

    return ScoredNEO(
        tracklet=tracklet,
        features=updated_features,
        posterior=posterior,
        hazard=hazard,
        metadata=metadata,
    )
