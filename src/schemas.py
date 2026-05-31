"""All pipeline data models — immutable Pydantic/dataclass types."""

from __future__ import annotations

__all__ = [
    "Score", "OptScore", "Mission", "NEOClass", "HazardFlag", "AlertPathway", "OrbitQualityCode",
    "Observation", "Tracklet", "CandidateFeatures", "NEOPosterior", "CandidateExplanation",
    "OrbitalElements", "HazardAssessment", "ScoringMetadata", "ScoredNEO",
    "RawCandidate", "KnownMatch",
    "FetchProvenance", "PreprocessProvenance", "DetectProvenance", "LinkProvenance",
    "FetchResult", "PreprocessResult", "DetectResult", "LinkResult",
    "ObservationWindow", "PipelineResult", "CandidateSummary", "NEOStatistics", "TrackletSummary",
    "CloseApproachEvent", "SurveyField", "PipelineConfig", "ObservationBatch", "DetectionSummary",
    "PhotometricSolution",
    "ObservationStatistics",
    "AlertPackage",
    "OrbitalElementsSummary", "CandidateReport",
    "EphemerisPoint",
    "SurveyStatistics",
    "ObservationCluster",
    "BackgroundOutcome", "BackgroundRunMode", "FollowUpTestStatus", "HumanReviewStatus",
    "RecommendationAction", "SignoffDecision",
    "PriorityFactors", "BackgroundTarget", "FollowUpTestResult",
    "SubmissionRecommendation", "BackgroundRunLedgerEntry", "ReviewedLogEntry",
    "NeedsFollowUpLogEntry", "BackgroundConfig", "HumanSignoffEntry", "BackgroundRunResult",
    "AstrometricResidual",
    "ResidualSummary",
    "ObservationCoverage",
    "NightSummary",
    "TrackletCluster",
    "CampaignSummary",
    "FieldObservationSummary",
    "ObservationCluster",
    "SurveyRun",
    "CandidateCluster",
    "PipelineRunSummary",
    "TrackletBatch",
    "FieldObservation",
    "ScoringRun",
    "AlertBatch",
    "ObservationFilter",
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

BackgroundRunMode = Literal["manual", "automated"]

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
    # Survey field metadata
    field_id: str | None = None
    limiting_mag: float | None = None


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
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = Field(ge=15, default=60)
    live_review_policy: str | None = None
    required_credential_env: tuple[str, ...] = ()


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


class TrackletSummary(BaseModel):
    """Lightweight summary of a Tracklet for display or export.

    Avoids carrying the full observation list while preserving the key
    properties needed for candidate tables and follow-up scheduling.
    """

    model_config = ConfigDict(frozen=True)

    object_id: str
    arc_days: float
    n_observations: int
    motion_rate_arcsec_per_hour: float
    motion_pa_degrees: float
    neo_class: NEOClass = "unknown"
    discovery_priority: float = 0.0


class CloseApproachEvent(BaseModel):
    """Record of a single close approach between an NEO and Earth.

    Produced by ``orbit.close_approach_table`` and used in alert workflows.
    All distances in AU; velocities in km/s.
    """

    model_config = ConfigDict(frozen=True)

    object_id: str
    jd: float
    geocentric_dist_au: float
    relative_velocity_km_s: float | None = None
    warning_time_days: float | None = None


class SurveyField(BaseModel):
    """Metadata for a single survey field pointing.

    Captures the sky position, search radius, limiting magnitude, source count,
    and observation epoch for one field visited by a survey.
    """

    model_config = ConfigDict(frozen=True)

    field_id: str
    ra_deg: float
    dec_deg: float
    radius_deg: float
    limiting_mag: float
    n_sources: int
    jd: float


class PipelineConfig(BaseModel):
    """Configuration for a single pipeline run.

    Captures the sky search parameters, time window, survey selection, and
    key detection thresholds for a repeatable pipeline execution.
    """

    model_config = ConfigDict(frozen=True)

    ra_deg: float
    dec_deg: float
    radius_deg: float = 1.0
    start_jd: float = 2460000.5
    end_jd: float | None = None
    real_bogus_threshold: float = 0.65
    surveys: tuple[str, ...] = ("ZTF",)


class ObservationBatch(BaseModel):
    """A named batch of observations from the same survey field and night.

    Groups related :class:`Observation` objects for efficient processing and
    provenance tracking.  Immutable after construction.

    Attributes:
        batch_id: Unique identifier for this batch (e.g. field+night hash).
        field_id: Survey field identifier.
        night_jd: Integer Julian Date of the observation night.
        mission: Survey that produced this batch.
        observations: Tuple of Observation objects in this batch.
        limiting_mag: Estimated 5-sigma limiting magnitude for this batch.
    """

    model_config = ConfigDict(frozen=True)

    batch_id: str
    field_id: str
    night_jd: int
    mission: Mission
    observations: tuple[Observation, ...]
    limiting_mag: float | None = None


class DetectionSummary(BaseModel):
    """Summary statistics for a single detection run on a survey field.

    Groups key outcomes from a detection pass: candidate count, known-object
    matches, genuinely new detections, and field metadata.  Immutable after
    construction.

    Attributes:
        field_id: Survey field identifier.
        epoch_jd: Julian Date of the observation epoch.
        survey: Survey that produced this detection run.
        n_candidates: Total number of raw candidates extracted.
        n_known_matches: Candidates matched to MPC known objects.
        n_new: Candidates not matched to any known object (n_candidates - n_known_matches).
        limiting_mag: Estimated 5-sigma limiting magnitude; None if unknown.
    """

    model_config = ConfigDict(frozen=True)

    field_id: str
    epoch_jd: float
    survey: Mission
    n_candidates: int = Field(ge=0)
    n_known_matches: int = Field(ge=0)
    n_new: int = Field(ge=0)
    limiting_mag: float | None = None


class PhotometricSolution(BaseModel):
    """Photometric calibration solution for a survey field.

    Captures the zero-point and colour-term coefficients derived from a
    catalogue cross-match (e.g. Gaia DR3 or Pan-STARRS).  Immutable after
    construction.

    Attributes:
        zero_point: Instrumental zero-point magnitude (mag).
        color_coeff: First-order colour coefficient (mag/mag).
        extinction_coeff: Atmospheric extinction coefficient (mag/airmass).
        rms_scatter: RMS residual of the photometric fit in magnitudes.
        n_stars: Number of reference stars used in the fit.
        filter_band: Photometric band (e.g. ``"g"``, ``"r"``, ``"i"``).
        epoch_jd: Julian Date of the calibration observation.
    """

    model_config = ConfigDict(frozen=True)

    zero_point: float
    color_coeff: float = 0.0
    extinction_coeff: float = 0.0
    rms_scatter: float | None = None
    n_stars: int = Field(ge=0, default=0)
    filter_band: str = "r"
    epoch_jd: float | None = None


class ObservationStatistics(BaseModel):
    """Aggregate statistics computed over a set of observations.

    Provides a compact summary of observation quality and coverage for use in
    scoring, reporting, and scheduling tools.  Immutable after construction.

    Attributes:
        n_obs: Total number of observations.
        mean_mag: Mean apparent magnitude; None if no valid magnitudes.
        mag_range: Max − min apparent magnitude; None if <2 valid magnitudes.
        mean_real_bogus: Mean real/bogus score; None if no scored observations.
        n_filters: Number of distinct filter bands observed.
        arc_days: Temporal arc from first to last observation in days.
    """

    model_config = ConfigDict(frozen=True)

    n_obs: int = Field(ge=0)
    mean_mag: float | None = None
    mag_range: float | None = None
    mean_real_bogus: float | None = None
    n_filters: int = Field(ge=0, default=0)
    arc_days: float = 0.0


class AlertPackage(BaseModel):
    """Immutable container for a complete external alert submission package.

    Bundles all artefacts required for MPC submission or NASA PDCO notification
    into a single, auditable object.  Always includes a mandatory guardrail
    statement.

    Attributes:
        neo_id: Object identifier from the pipeline (tracklet ``object_id``).
        alert_pathway: The determined alert pathway for this candidate.
        moid_au: Minimum Orbit Intersection Distance in AU; None if unknown.
        observations: Tuple of observations supporting this alert.
        submission_timestamp_jd: Julian Date at which the package was created.
        guardrail_statement: Mandatory non-impact-claim statement.  Must
            contain "NOT" to confirm compliance with the no-impact-probability
            guardrail.
    """

    model_config = ConfigDict(frozen=True)

    neo_id: str
    alert_pathway: AlertPathway
    moid_au: float | None = None
    observations: tuple[Observation, ...] = Field(default_factory=tuple)
    submission_timestamp_jd: float
    guardrail_statement: str = (
        "Do NOT publicly announce any impact probability. "
        "Defer all public communication to NASA/CNEOS."
    )


class OrbitalElementsSummary(BaseModel):
    """Compact orbital elements summary for display and export.

    Captures the key orbital parameters for a NEO candidate in a single
    frozen model suitable for ranking, reporting, and cross-matching.
    Includes optional MOID and quality annotation fields.

    Attributes:
        object_id: Pipeline object identifier.
        neo_class: Dynamical class: amor, apollo, aten, ieo, or unknown.
        semi_major_axis_au: Semi-major axis in AU.
        eccentricity: Orbital eccentricity (0 ≤ e < 1 for bound orbits).
        inclination_deg: Orbital inclination in degrees.
        perihelion_au: Perihelion distance q = a(1-e) in AU.
        aphelion_au: Aphelion distance Q = a(1+e) in AU.
        moid_au: Minimum Orbit Intersection Distance in AU; None if unknown.
        quality_code: Orbit quality code 1–4 (1=arc<1day, 4=opposition).
        epoch_jd: Reference epoch as Julian Date.
    """

    model_config = ConfigDict(frozen=True)

    object_id: str
    neo_class: NEOClass
    semi_major_axis_au: float
    eccentricity: float
    inclination_deg: float
    perihelion_au: float
    aphelion_au: float
    moid_au: float | None = None
    quality_code: int = 1
    epoch_jd: float


class EphemerisPoint(BaseModel):
    """A single predicted sky position from an ephemeris computation.

    Represents one time-step in an ephemeris table produced by
    :func:`~orbit.predict_ephemeris` or similar routines.

    Attributes:
        object_id: Pipeline object identifier.
        jd: Julian Date for this prediction.
        ra_deg: Predicted right ascension in degrees [0, 360).
        dec_deg: Predicted declination in degrees (−90, +90].
        delta_au: Geocentric distance in AU at the prediction epoch.
        r_au: Heliocentric distance in AU at the prediction epoch.
        phase_deg: Sun–target–observer phase angle in degrees; None if unknown.
        mag: Predicted apparent magnitude; None if unknown.
    """

    model_config = ConfigDict(frozen=True)

    object_id: str
    jd: float
    ra_deg: float
    dec_deg: float
    delta_au: float = 1.0
    r_au: float = 1.0
    phase_deg: float | None = None
    mag: float | None = None


class CandidateReport(BaseModel):
    """Complete per-candidate export summary for operator review and filing.

    Aggregates the key outputs of all pipeline stages for a single NEO
    candidate into one frozen, serialisable model.

    Attributes:
        object_id: Pipeline object identifier.
        neo_class: Dynamical classification result.
        hazard_flag: Hazard assessment flag.
        alert_pathway: Recommended alert pathway.
        moid_au: Minimum Orbit Intersection Distance in AU; None if unknown.
        absolute_magnitude_h: Absolute magnitude; None if unknown.
        estimated_diameter_m: Estimated diameter in metres; None if unknown.
        discovery_priority: Discovery priority score [0, 1].
        neo_candidate_prob: Posterior probability of being a new NEO.
        n_observations: Number of observations in the tracklet.
        arc_days: Tracklet arc length in days.
        generated_jd: Julian Date when this report was generated.
    """

    model_config = ConfigDict(frozen=True)

    object_id: str
    neo_class: NEOClass
    hazard_flag: HazardFlag
    alert_pathway: AlertPathway
    moid_au: float | None = None
    absolute_magnitude_h: float | None = None
    estimated_diameter_m: float | None = None
    discovery_priority: float = 0.0
    neo_candidate_prob: float = 0.0
    n_observations: int = 0
    arc_days: float = 0.0
    generated_jd: float = 2460000.5


class SurveyStatistics(BaseModel):
    """Aggregate statistics for a single survey over one pipeline run.

    Captures headline numbers for a survey provider (ZTF, ATLAS, etc.) in
    a single pipeline execution: total fields visited, observations, candidates,
    and tracklets formed, along with optional quality indicators.

    Attributes:
        survey: Survey identifier (e.g. ``"ZTF"``, ``"ATLAS"``).
        n_fields: Number of survey fields visited.
        n_observations: Total number of observations collected.
        n_candidates: Candidates passing detection thresholds.
        n_tracklets: Number of linked tracklets formed.
        mean_limiting_mag: Mean limiting magnitude across all fields; None if unknown.
        epoch_start_jd: Start of the survey epoch as Julian Date.
        epoch_end_jd: End of the survey epoch as Julian Date.
    """

    model_config = ConfigDict(frozen=True)

    survey: Mission
    n_fields: int = 0
    n_observations: int = 0
    n_candidates: int = 0
    n_tracklets: int = 0
    mean_limiting_mag: float | None = None
    epoch_start_jd: float = 0.0
    epoch_end_jd: float = 0.0


class ObservationCluster(BaseModel):
    """A spatial cluster of co-located observations from a single pipeline epoch."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    center_ra_deg: float
    center_dec_deg: float
    radius_arcsec: float
    epoch_jd: float
    observations: tuple[Observation, ...] = ()
    n_observations: int = 0


class AstrometricResidual(BaseModel):
    """Per-observation astrometric residual from an orbit fit."""

    model_config = ConfigDict(frozen=True)

    obs_id: str
    ra_residual_arcsec: float
    dec_residual_arcsec: float
    total_arcsec: float
    jd: float


class ResidualSummary(BaseModel):
    """Aggregate astrometric residual statistics for a set of observations."""

    model_config = ConfigDict(frozen=True)

    object_id: str
    n_obs: int
    rms_arcsec: float
    max_residual_arcsec: float
    mean_ra_residual_arcsec: float
    mean_dec_residual_arcsec: float


class ObservationCoverage(BaseModel):
    """Sky coverage metadata for a single pipeline run or survey night."""

    model_config = ConfigDict(frozen=True)

    night_jd: float
    mission: Mission
    n_fields: int
    total_area_deg2: float
    limiting_mag: float | None = None
    field_ids: tuple[str, ...] = ()
    run_id: str | None = None
    mean_limiting_mag: float | None = None
    epoch_jd: float | None = None


class NightSummary(BaseModel):
    """Summary statistics for a single survey night."""

    model_config = ConfigDict(frozen=True)

    night_jd: float
    survey: Mission
    n_tracklets: int
    n_new: int
    n_known: int
    n_pha_candidates: int
    fields_covered: tuple[str, ...] = ()
    limiting_mag: float | None = None


class TrackletCluster(BaseModel):
    """A group of spatially or temporally nearby tracklets."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    tracklet_ids: tuple[str, ...] = ()
    centroid_ra_deg: float
    centroid_dec_deg: float
    n_tracklets: int
    arc_span_days: float = 0.0


class CampaignSummary(BaseModel):
    """Summary of a multi-night observing campaign."""

    model_config = ConfigDict(frozen=True)

    campaign_id: str
    start_jd: float
    end_jd: float
    n_nights: int
    n_tracklets: int
    n_pha_candidates: int
    surveys_used: tuple[str, ...] = ()
    sky_area_deg2: float | None = None


class FieldObservationSummary(BaseModel):
    """Per-field observation summary from a single pipeline run epoch."""

    model_config = ConfigDict(frozen=True)

    field_id: str
    epoch_jd: float
    survey: Mission
    n_sources: int = 0
    n_moving: int = 0
    n_known: int = 0
    n_new: int = 0
    limiting_mag: float | None = None


class SurveyRun(BaseModel):
    """A single survey field epoch produced by the pipeline."""
    model_config = ConfigDict(frozen=True)
    run_id: str
    survey: Mission
    epoch_jd: float
    field_id: str
    n_candidates: int = 0
    sky_coverage_deg2: float = 0.0
    limiting_mag: float | None = None


class CandidateCluster(BaseModel):
    """A spatial cluster of NEO candidates from a single pipeline run."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    run_id: str
    center_ra_deg: float
    center_dec_deg: float
    n_candidates: int
    candidate_ids: tuple[str, ...]
    mean_priority: float = 0.0


class PipelineRunSummary(BaseModel):
    """High-level summary of a single pipeline run for reporting and auditing.

    Aggregates the key headline numbers from a complete pipeline execution
    into a single frozen model suitable for dashboards, logs, and operator
    review.

    Attributes:
        run_id: Unique identifier for this pipeline run.
        epoch_jd: Julian Date of the observation epoch.
        n_tracklets: Total number of linked tracklets produced.
        n_pha_candidates: Number of PHA-candidate tracklets.
        n_new_candidates: Number of candidates not matched to known objects.
        top_priority: Highest discovery_priority score among all candidates.
        alert_pathways: Tuple of distinct alert pathway values seen this run.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    epoch_jd: float
    n_tracklets: int = 0
    n_pha_candidates: int = 0
    n_new_candidates: int = 0
    top_priority: float = 0.0
    alert_pathways: tuple[str, ...] = ()


class TrackletBatch(BaseModel):
    """A batch of tracklets from a single pipeline run for bulk processing."""

    model_config = ConfigDict(frozen=True)

    batch_id: str
    run_id: str
    tracklets: tuple[str, ...]  # object_ids
    n_tracklets: int = 0
    epoch_jd: float | None = None


class FieldObservation(BaseModel):
    """A single survey field pointing with metadata."""

    model_config = ConfigDict(frozen=True)

    field_id: str
    ra_deg: float
    dec_deg: float
    epoch_jd: float
    survey: str
    limiting_mag: float | None = None
    n_sources: int = 0
    filter_band: str | None = None


class ScoringRun(BaseModel):
    """Summary of a single scoring batch run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    n_scored: int = 0
    n_pha: int = 0
    mean_priority: float = 0.0
    top_object_id: str | None = None
    epoch_jd: float | None = None


class AlertBatch(BaseModel):
    """A batch of alert packages from a single pipeline run."""

    model_config = ConfigDict(frozen=True)

    batch_id: str
    run_id: str
    n_alerts: int = 0
    pathways: tuple[str, ...] = ()
    epoch_jd: float | None = None
    guardrail_statement: str = "These alerts do NOT constitute confirmed detections."


class ObservationFilter(BaseModel):
    """Configurable criteria for filtering pipeline observations."""

    model_config = ConfigDict(frozen=True)

    min_rb_score: float | None = None
    max_mag: float | None = None
    min_mag: float | None = None
    surveys: tuple[str, ...] = ()
    filter_bands: tuple[str, ...] = ()
    min_jd: float | None = None
    max_jd: float | None = None
