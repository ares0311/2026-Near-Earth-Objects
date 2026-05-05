"""All pipeline data models — immutable Pydantic/dataclass types."""

from __future__ import annotations

__all__ = [
    "Score", "OptScore", "Mission", "NEOClass", "HazardFlag", "AlertPathway", "OrbitQualityCode",
    "Observation", "Tracklet", "CandidateFeatures", "NEOPosterior", "CandidateExplanation",
    "OrbitalElements", "HazardAssessment", "ScoringMetadata", "ScoredNEO",
    "RawCandidate", "KnownMatch",
    "FetchProvenance", "PreprocessProvenance", "DetectProvenance", "LinkProvenance",
    "FetchResult", "PreprocessResult", "DetectResult", "LinkResult",
]

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Primitive aliases
# ---------------------------------------------------------------------------

Score = float  # bounded [0, 1]
OptScore = float | None  # optional [0, 1]

# ---------------------------------------------------------------------------
# Enumerations (Literal unions)
# ---------------------------------------------------------------------------

Mission = Literal["ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"]

NEOClass = Literal["amor", "apollo", "aten", "ieo", "unknown"]

HazardFlag = Literal["pha_candidate", "close_approach", "nominal", "unknown"]

AlertPathway = Literal[
    "mpc_submission",
    "neocp_followup",
    "nasa_pdco_notify",
    "internal_candidate",
    "known_object",
]

OrbitQualityCode = Literal[1, 2, 3, 4]
# 1=arc<1day, 2=multi-night, 3=multi-week, 4=opposition


# ---------------------------------------------------------------------------
# Observation — a single photometric detection
# ---------------------------------------------------------------------------


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    obs_id: str
    ra_deg: float = Field(ge=0.0, le=360.0)
    dec_deg: float = Field(ge=-90.0, le=90.0)
    jd: float  # Julian Date
    mag: float
    mag_err: float = Field(ge=0.0)
    filter_band: str  # "g", "r", "i", "o", "c", …
    mission: Mission
    # ZTF-specific optional fields
    real_bogus: OptScore = None
    deep_real_bogus: OptScore = None
    # image cutouts as base64 strings (science / reference / difference)
    cutout_science: str | None = None
    cutout_reference: str | None = None
    cutout_difference: str | None = None


# ---------------------------------------------------------------------------
# Tracklet — linked set of observations for one moving object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tracklet:
    object_id: str
    observations: tuple[Observation, ...]  # ≥2 obs per tracklet
    arc_days: float
    motion_rate_arcsec_per_hour: float
    motion_pa_degrees: float  # position angle of motion, degrees E of N
    motion_rate_uncertainty: float = 0.0  # arcsec/hr


# ---------------------------------------------------------------------------
# Feature vector — all scores bounded [0, 1] or None
# ---------------------------------------------------------------------------


class CandidateFeatures(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Detection quality
    real_bogus_score: OptScore = None
    streak_score: OptScore = None
    psf_quality_score: OptScore = None
    # Motion
    motion_consistency_score: OptScore = None
    arc_coverage_score: OptScore = None
    nights_observed_score: OptScore = None
    # Photometry
    brightness_score: OptScore = None
    color_score: OptScore = None
    lightcurve_variability_score: OptScore = None
    # Orbit (populated after orbit.py)
    orbit_quality_score: OptScore = None
    moid_score: OptScore = None
    neo_class_confidence: OptScore = None
    pha_flag_confidence: OptScore = None
    # Catalog
    known_object_score: OptScore = None
    # Classifier auxiliary
    main_belt_consistency_score: OptScore = None
    stellar_artifact_score: OptScore = None


# ---------------------------------------------------------------------------
# NEO posterior — probabilities over five hypotheses
# ---------------------------------------------------------------------------


class NEOPosterior(BaseModel):
    model_config = ConfigDict(frozen=True)

    neo_candidate: Score = Field(ge=0.0, le=1.0)
    known_object: Score = Field(ge=0.0, le=1.0)
    main_belt_asteroid: Score = Field(ge=0.0, le=1.0)
    stellar_artifact: Score = Field(ge=0.0, le=1.0)
    other_solar_system: Score = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Candidate explanation — human-readable evidence
# ---------------------------------------------------------------------------


class CandidateExplanation(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str
    supporting_evidence: tuple[str, ...]
    contra_evidence: tuple[str, ...]
    model_version: str


# ---------------------------------------------------------------------------
# Orbital elements
# ---------------------------------------------------------------------------


class OrbitalElements(BaseModel):
    model_config = ConfigDict(frozen=True)

    semi_major_axis_au: float  # a
    eccentricity: float  # e
    inclination_deg: float  # i
    longitude_ascending_node_deg: float  # Ω
    argument_perihelion_deg: float  # ω
    mean_anomaly_deg: float  # M₀
    epoch_jd: float
    perihelion_au: float  # q = a(1-e)
    aphelion_au: float  # Q = a(1+e)
    quality_code: OrbitQualityCode = 1
    fit_residual_arcsec: float | None = None


# ---------------------------------------------------------------------------
# Hazard assessment
# ---------------------------------------------------------------------------


class HazardAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    hazard_flag: HazardFlag
    moid_au: float | None
    estimated_diameter_m: float | None
    absolute_magnitude_h: float | None
    neo_class: NEOClass
    alert_pathway: AlertPathway
    explanation: CandidateExplanation
    orbital_elements: OrbitalElements | None = None


# ---------------------------------------------------------------------------
# Scoring metadata
# ---------------------------------------------------------------------------


class ScoringMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    scorer_version: str
    scored_at_jd: float
    pipeline_run_id: str
    discovery_priority: float = Field(ge=0.0, le=1.0, default=0.0)
    followup_value: float = Field(ge=0.0, le=1.0, default=0.0)
    scientific_interest: float = Field(ge=0.0, le=1.0, default=0.0)


# ---------------------------------------------------------------------------
# Top-level scored result
# ---------------------------------------------------------------------------


class ScoredNEO(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    tracklet: Tracklet
    features: CandidateFeatures
    posterior: NEOPosterior
    hazard: HazardAssessment
    metadata: ScoringMetadata


# ---------------------------------------------------------------------------
# Raw candidate — output of detect.py before linking
# ---------------------------------------------------------------------------


class RawCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    observations: tuple[Observation, ...]
    apparent_motion_arcsec_per_hr: float | None = None
    motion_pa_deg: float | None = None
    is_streak: bool = False


# ---------------------------------------------------------------------------
# Known match — object cross-identified in MPC catalog
# ---------------------------------------------------------------------------


class KnownMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation: Observation
    mpc_designation: str
    separation_arcsec: float
    ephemeris_ra_deg: float
    ephemeris_dec_deg: float


# ---------------------------------------------------------------------------
# Provenance models for each pipeline stage
# ---------------------------------------------------------------------------


class FetchProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    surveys: tuple[Mission, ...]
    start_jd: float
    end_jd: float
    search_ra_deg: float | None = None
    search_dec_deg: float | None = None
    search_radius_deg: float | None = None
    limiting_magnitude: float | None = None
    fetched_at_jd: float = 0.0
    cached: bool = False


class PreprocessProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    n_sources_in: int
    n_sources_out: int
    astrometric_reference: str = "Gaia DR3"
    processed_at_jd: float = 0.0


class DetectProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    real_bogus_threshold: float
    n_candidates: int
    n_known_matches: int
    detected_at_jd: float = 0.0


class LinkProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    n_tracklets: int
    min_nights: int
    min_observations: int
    linked_at_jd: float = 0.0


# ---------------------------------------------------------------------------
# Stage result containers
# ---------------------------------------------------------------------------


class FetchResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    alerts: tuple[Observation, ...]
    provenance: FetchProvenance


class PreprocessResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    sources: tuple[Observation, ...]
    provenance: PreprocessProvenance


class DetectResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    candidates: tuple[RawCandidate, ...]
    known_matches: tuple[KnownMatch, ...]
    provenance: DetectProvenance


class LinkResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    tracklets: tuple[Tracklet, ...]
    provenance: LinkProvenance
