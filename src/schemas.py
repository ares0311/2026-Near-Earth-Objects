"""All pipeline data models — immutable Pydantic/dataclass types."""

from __future__ import annotations

__all__ = [
    "Score", "OptScore", "Mission", "NEOClass", "HazardFlag", "AlertPathway", "OrbitQualityCode",
    "Observation", "Tracklet", "CandidateFeatures", "NEOPosterior", "CandidateExplanation",
    "OrbitalElements", "HazardAssessment", "ScoringMetadata", "ScoredNEO",
    "RawCandidate", "KnownMatch",
    "FetchProvenance", "PreprocessProvenance", "DetectProvenance", "LinkProvenance",
    "FetchResult", "PreprocessResult", "DetectResult", "LinkResult",
    "ObservationWindow", "PipelineResult", "CandidateSummary", "NEOStatistics",
    "BackgroundOutcome", "BackgroundRunMode", "FollowUpTestStatus", "HumanReviewStatus",
    "RecommendationAction", "SignoffDecision",
    "PriorityFactors", "BackgroundTarget", "FollowUpTestResult",
    "SubmissionRecommendation", "BackgroundRunLedgerEntry", "ReviewedLogEntry",
    "NeedsFollowUpLogEntry", "BackgroundConfig", "HumanSignoffEntry", "BackgroundRunResult",
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

BackgroundOutcome = Literal["reviewed", "needs_follow_up"]

BackgroundRunMode = Literal["manual"]

FollowUpTestStatus = Literal["pass", "fail", "blocked", "uncertain"]

HumanReviewStatus = Literal["ready", "blocked"]

RecommendationAction = Literal["internal_review", "request_more_tests", "do_not_submit_yet"]

SignoffDecision = Literal["approved_for_internal_review", "needs_more_work", "rejected"]


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
    close_approach_au: float | None = None


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


# ---------------------------------------------------------------------------
# Background search automation models
# ---------------------------------------------------------------------------


class PriorityFactors(BaseModel):
    model_config = ConfigDict(frozen=True)

    scientific_interest: float = Field(ge=0.0, le=1.0)
    prior_review_penalty: float = Field(ge=0.0, le=1.0)
    never_reviewed_boost: float = Field(ge=0.0, le=1.0)
    data_completeness: float = Field(ge=0.0, le=1.0)
    false_positive_risk: float = Field(ge=0.0, le=1.0)
    followup_feasibility: float = Field(ge=0.0, le=1.0)
    calibration_confidence: float = Field(ge=0.0, le=1.0)
    blocking_issue_penalty: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)


class BackgroundTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_id: str
    scored_neo: ScoredNEO
    priority: PriorityFactors
    skipped_reason_codes: tuple[str, ...] = ()


class FollowUpTestResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: FollowUpTestStatus | HumanReviewStatus
    reason_code: str
    summary: str


class SubmissionRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    destination: str
    rank: int = Field(ge=1, le=3)
    suitability_rationale: str
    risks: tuple[str, ...]
    prerequisites: tuple[str, ...]
    recommended_action: RecommendationAction


class BackgroundRunLedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    started_at_utc: str
    completed_at_utc: str
    code_version: str
    schema_version: str
    input_path: str
    target_id: str
    outcome: BackgroundOutcome
    selected_score: float = Field(ge=0.0, le=1.0)
    reason_codes: tuple[str, ...]
    run_mode: BackgroundRunMode = "manual"
    config_path: str | None = None
    failure_reason: str | None = None
    live_network_enabled: bool = False


class ReviewedLogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    reviewed_at_utc: str
    target_id: str
    priority: PriorityFactors | None
    negative_evidence: tuple[str, ...]
    rationale: str


class NeedsFollowUpLogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    recorded_at_utc: str
    target_id: str
    priority: PriorityFactors
    trigger_reason_codes: tuple[str, ...]
    required_tests: tuple[FollowUpTestResult, ...]
    report_path: str | None
    recommendations: tuple[SubmissionRecommendation, ...]
    human_approval_required: bool = True


class BackgroundConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_path: str
    db_path: str
    report_dir: str
    follow_up_threshold: float = Field(ge=0.0, le=1.0)
    run_mode: BackgroundRunMode = "manual"
    live_network_enabled: bool = False
    require_human_signoff: bool = True
    required_approval_count: int = Field(ge=1, default=1)


class HumanSignoffEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    signoff_id: str
    run_id: str
    target_id: str
    reviewer: str
    signed_at_utc: str
    decision: SignoffDecision
    scope: str
    notes: str = ""


class BackgroundRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ledger: BackgroundRunLedgerEntry
    reviewed: ReviewedLogEntry | None = None
    needs_follow_up: NeedsFollowUpLogEntry | None = None


# ---------------------------------------------------------------------------
# Sky/time search query container
# ---------------------------------------------------------------------------


class ObservationWindow(BaseModel):
    """Typed, immutable container for a sky/time search query.

    Used as a self-documenting parameter object for :func:`fetch.fetch` and
    :func:`fetch.fetch_batch`.
    """

    model_config = ConfigDict(frozen=True)

    ra_deg: float
    dec_deg: float
    radius_deg: float
    start_jd: float
    end_jd: float
    surveys: tuple[Mission, ...] = ("ZTF",)
    description: str = ""


# ---------------------------------------------------------------------------
# Top-level pipeline result container
# ---------------------------------------------------------------------------


class PipelineResult(BaseModel):
    """Immutable container for a complete end-to-end pipeline run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    started_at_jd: float
    finished_at_jd: float
    fetch: FetchResult
    preprocess: PreprocessResult
    detect: DetectResult
    link: LinkResult
    scored_neos: tuple[ScoredNEO, ...]
    pipeline_version: str = ""
    n_pha_candidates: int = 0


class CandidateSummary(BaseModel):
    """Lightweight summary of a ScoredNEO for display or export."""

    model_config = ConfigDict(frozen=True)

    object_id: str
    neo_class: NEOClass
    hazard_flag: HazardFlag
    alert_pathway: AlertPathway
    moid_au: float | None = None
    estimated_diameter_m: float | None = None
    absolute_magnitude_h: float | None = None
    arc_days: float
    n_observations: int
    neo_candidate_probability: Score
    discovery_priority: float = 0.0


class NEOStatistics(BaseModel):
    """Aggregate statistics for a pipeline run."""

    model_config = ConfigDict(frozen=True)

    n_total: int
    n_pha_candidates: int
    n_mpc_submission: int
    n_internal_candidate: int
    n_known_object: int
    mean_discovery_priority: float
    max_discovery_priority: float
    neo_class_distribution: dict[str, int] = Field(default_factory=dict)
