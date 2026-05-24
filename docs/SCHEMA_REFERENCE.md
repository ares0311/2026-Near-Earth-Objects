# Schema Reference

All models in `src/schemas.py` use `ConfigDict(frozen=True)` — they are immutable after construction.

---

## Primitive Aliases

| Type | Description |
|------|-------------|
| `Score` | `float` bounded [0, 1] |
| `OptScore` | `float \| None` bounded [0, 1] |
| `Mission` | Literal: `"ZTF"`, `"ATLAS"`, `"PanSTARRS"`, `"CSS"`, `"MPC"` |
| `NEOClass` | Literal: `"amor"`, `"apollo"`, `"aten"`, `"ieo"`, `"unknown"` |
| `HazardFlag` | Literal: `"pha_candidate"`, `"close_approach"`, `"nominal"`, `"unknown"` |
| `AlertPathway` | Literal: `"mpc_submission"`, `"neocp_followup"`, `"nasa_pdco_notify"`, `"internal_candidate"`, `"known_object"` |
| `OrbitQualityCode` | Literal: 1, 2, 3, 4 |

---

## Core Detection Models

### `Observation`
A single photometric detection.

| Field | Type | Description |
|-------|------|-------------|
| `obs_id` | `str` | Unique observation identifier |
| `ra_deg` | `float` | Right ascension (degrees) |
| `dec_deg` | `float` | Declination (degrees) |
| `jd` | `float` | Julian date of observation |
| `mag` | `float` | Apparent magnitude |
| `mag_err` | `float` | Magnitude uncertainty |
| `filter_band` | `str \| None` | Filter name (g, r, i, o, c, …) |
| `mission` | `Mission` | Survey that produced this observation |
| `real_bogus` | `float \| None` | Classical real/bogus score [0, 1] |
| `deep_real_bogus` | `float \| None` | Deep-learning real/bogus score [0, 1] |
| `cutout_science` | `str \| None` | Base64 63×63 float32 science cutout |
| `cutout_reference` | `str \| None` | Base64 63×63 float32 reference cutout |
| `cutout_difference` | `str \| None` | Base64 63×63 float32 difference cutout |

### `Tracklet`
A linked sequence of observations consistent with solar system motion.

| Field | Type | Description |
|-------|------|-------------|
| `object_id` | `str` | Pipeline-assigned identifier |
| `observations` | `tuple[Observation, ...]` | ≥2 observations |
| `arc_days` | `float` | Time span of observations in days |
| `motion_rate_arcsec_per_hour` | `float` | Apparent angular speed |
| `motion_pa_degrees` | `float` | Position angle of motion (degrees) |

### `RawCandidate`
A single-night moving-object candidate before multi-night linking.

### `KnownMatch`
A candidate matched to a known MPC object.

---

## Feature and Classification Models

### `CandidateFeatures`
Feature vector for ML classification. All `OptScore` fields are `float | None` in [0, 1].

| Field | Description |
|-------|-------------|
| `real_bogus_score` | Real/bogus classifier output |
| `streak_score` | Streak/trail severity |
| `psf_quality_score` | PSF quality |
| `motion_consistency_score` | Linear motion fit quality |
| `arc_coverage_score` | Arc length normalized to 30 days |
| `nights_observed_score` | Number of nights normalized |
| `brightness_score` | Proxy for size (lower mag → higher score) |
| `color_score` | g-r color index normalized |
| `lightcurve_variability_score` | Magnitude scatter |
| `orbit_quality_score` | Orbit quality code normalized |
| `moid_score` | 1 = MOID ≤ 0.05 AU |
| `neo_class_confidence` | Confidence in NEO classification |
| `pha_flag_confidence` | Confidence in PHA flag |
| `known_object_score` | 0 = new, 1 = known MPC object |

### `NEOPosterior`
Posterior probability distribution over classification hypotheses.

| Field | Prior | Description |
|-------|-------|-------------|
| `neo_candidate` | 0.05 | Genuine new NEO |
| `known_object` | 0.30 | Matches MPC catalog |
| `main_belt_asteroid` | 0.35 | MBA on unusual orbit |
| `stellar_artifact` | 0.25 | Cosmic ray/satellite/artifact |
| `other_solar_system` | 0.05 | Comet, TNO, etc. |

### `CandidateExplanation`
Human-readable explanation of the classification decision.

| Field | Type | Description |
|-------|------|-------------|
| `summary` | `str` | One-sentence summary |
| `supporting_evidence` | `tuple[str, ...]` | Features supporting NEO hypothesis |
| `contra_evidence` | `tuple[str, ...]` | Features against NEO hypothesis |
| `model_version` | `str` | Scorer version string |

---

## Orbit and Hazard Models

### `OrbitalElements`
Keplerian orbital elements from `orbit.py`.

| Field | Description |
|-------|-------------|
| `semi_major_axis_au` | Semi-major axis a (AU) |
| `eccentricity` | Eccentricity e |
| `inclination_deg` | Inclination i (degrees) |
| `longitude_ascending_node_deg` | Ω (degrees) |
| `argument_of_perihelion_deg` | ω (degrees) |
| `mean_anomaly_deg` | M₀ (degrees) at epoch |
| `epoch_jd` | Reference epoch (JD) |
| `quality_code` | `OrbitQualityCode` 1–4 |

### `HazardAssessment`
Result of the scoring and hazard evaluation stage.

| Field | Type | Description |
|-------|------|-------------|
| `hazard_flag` | `HazardFlag` | PHA/close-approach/nominal/unknown |
| `moid_au` | `float \| None` | Minimum Orbit Intersection Distance |
| `estimated_diameter_m` | `float \| None` | Diameter estimate in metres |
| `absolute_magnitude_h` | `float \| None` | H magnitude |
| `neo_class` | `NEOClass` | Dynamical class |
| `alert_pathway` | `AlertPathway` | Recommended reporting pathway |
| `explanation` | `CandidateExplanation` | Scoring rationale |

### `ScoringMetadata`
Provenance for a scoring run.

| Field | Type | Description |
|-------|------|-------------|
| `scorer_version` | `str` | Version string |
| `pipeline_run_id` | `str` | UUID for the run |
| `discovery_priority` | `float` | Combined priority score [0, 1] |
| `followup_value` | `float` | Follow-up urgency score [0, 1] |
| `scientific_interest` | `float` | Novelty/scientific value [0, 1] |
| `close_approach_au` | `float \| None` | Closest approach distance |

### `ScoredNEO`
Top-level container for a fully scored NEO candidate.

| Field | Type |
|-------|------|
| `tracklet` | `Tracklet` |
| `features` | `CandidateFeatures` |
| `posterior` | `NEOPosterior` |
| `hazard` | `HazardAssessment` |
| `metadata` | `ScoringMetadata` |

---

## Pipeline Containers

### `FetchResult`
Output of `fetch.py`. Contains `alerts: tuple[Observation, ...]` and `provenance: FetchProvenance`.

### `PreprocessResult`
Output of `preprocess.py`. Contains `sources: tuple[Observation, ...]` and `provenance: PreprocessProvenance`.

### `DetectResult`
Output of `detect.py`. Contains `candidates: list[RawCandidate]` and `known_matches: list[KnownMatch]`.

### `LinkResult`
Output of `link.py`. Contains `tracklets: list[Tracklet]`.

### `PipelineResult`
Top-level immutable container for a complete pipeline run.

| Field | Type |
|-------|------|
| `run_id` | `str` |
| `config` | `PipelineConfig` |
| `fetch` | `FetchResult` |
| `preprocess` | `PreprocessResult` |
| `detect` | `DetectResult` |
| `link` | `LinkResult` |
| `scored_neos` | `tuple[ScoredNEO, ...]` |

---

## Query and Configuration Models

### `ObservationWindow`
Sky/time search query parameters.

| Field | Type |
|-------|------|
| `ra_deg` | `float` |
| `dec_deg` | `float` |
| `radius_deg` | `float` |
| `start_jd` | `float` |
| `end_jd` | `float` |
| `surveys` | `tuple[Mission, ...]` |

### `PipelineConfig`
Frozen configuration for a pipeline run.

| Field | Type |
|-------|------|
| `observation_window` | `ObservationWindow` |
| `real_bogus_threshold` | `float` |
| `min_nights` | `int` |
| `min_arc_days` | `float` |
| `max_moid_au` | `float` |

---

## Survey and Observation Statistics

### `ObservationBatch`
Batch of observations from the same survey field and night.

| Field | Type |
|-------|------|
| `batch_id` | `str` |
| `field_id` | `str` |
| `night_jd` | `float` |
| `mission` | `Mission` |
| `observations` | `tuple[Observation, ...]` |
| `limiting_mag` | `float \| None` |

### `SurveyField`
Metadata for a single survey field.

| Field | Type |
|-------|------|
| `field_id` | `str` |
| `ra_deg` | `float` |
| `dec_deg` | `float` |
| `radius_deg` | `float` |
| `limiting_mag` | `float \| None` |
| `n_sources` | `int` |
| `jd` | `float` |

### `DetectionSummary`
Per-field detection summary.

| Field | Type |
|-------|------|
| `field_id` | `str` |
| `epoch_jd` | `float` |
| `survey` | `Mission` |
| `n_candidates` | `int` |
| `n_known_matches` | `int` |
| `n_new` | `int` |
| `limiting_mag` | `float \| None` |

### `ObservationStatistics`
Aggregate statistics over a set of observations.

| Field | Type |
|-------|------|
| `n_obs` | `int` |
| `mean_mag` | `float \| None` |
| `mag_range` | `float \| None` |
| `mean_real_bogus` | `float \| None` |
| `n_filters` | `int` |
| `arc_days` | `float` |

### `PhotometricSolution`
Zero-point and calibration coefficients for a field.

| Field | Type |
|-------|------|
| `zero_point` | `float` |
| `color_coeff` | `float \| None` |
| `extinction_coeff` | `float \| None` |
| `rms_scatter` | `float \| None` |
| `n_stars` | `int` |
| `filter_band` | `str` |
| `epoch_jd` | `float` |

### `NightSummary`
Per-night pipeline summary.

| Field | Type |
|-------|------|
| `night_jd` | `float` |
| `survey` | `Mission` |
| `n_tracklets` | `int` |
| `n_new` | `int` |
| `n_known` | `int` |
| `n_pha_candidates` | `int` |
| `fields_covered` | `tuple[str, ...]` |
| `limiting_mag` | `float \| None` |

### `SurveyStatistics`
Aggregate statistics across a survey or run.

### `TrackletCluster`
A group of spatially or temporally nearby tracklets.

| Field | Type |
|-------|------|
| `cluster_id` | `str` |
| `tracklet_ids` | `tuple[str, ...]` |
| `centroid_ra_deg` | `float` |
| `centroid_dec_deg` | `float` |
| `n_tracklets` | `int` |
| `arc_span_days` | `float` |

### `CampaignSummary`
Summary of a multi-night observing campaign.

| Field | Type |
|-------|------|
| `campaign_id` | `str` |
| `start_jd` | `float` |
| `end_jd` | `float` |
| `n_nights` | `int` |
| `n_tracklets` | `int` |
| `n_pha_candidates` | `int` |
| `surveys_used` | `tuple[str, ...]` |
| `sky_area_deg2` | `float \| None` |

---

## Alert Models

### `AlertPackage`
Immutable bundle for an alert submission.

| Field | Type |
|-------|------|
| `neo_id` | `str` |
| `alert_pathway` | `AlertPathway` |
| `moid_au` | `float \| None` |
| `observations` | `tuple[Observation, ...]` |
| `submission_timestamp_jd` | `float` |
| `guardrail_statement` | `str` |

### `CloseApproachEvent`
A single close-approach event record.

---

## Lightweight Display Models

### `CandidateSummary`
Lightweight summary for display/export. Contains object_id, neo_class, hazard_flag, alert_pathway, and priority.

### `TrackletSummary`
Lightweight tracklet display model with object_id, arc_days, n_obs, and motion_rate.

### `CandidateReport`
Frozen report model: object_id, neo_class, hazard_flag, alert_pathway, moid_au, H, diameter, priority, prob, n_obs, arc_days, generated_jd.

### `OrbitalElementsSummary`
Frozen summary of orbital elements: object_id, neo_class, a/e/i/q/Q, moid_au, quality_code, epoch_jd.

### `NEOStatistics`
Aggregate pipeline statistics: counts by class, hazard flag, and pathway.

---

## Astrometric Models

### `AstrometricResidual`
Single astrometric residual (obs_id, dra_arcsec, ddec_arcsec, epoch_jd).

### `ResidualSummary`
Summary of residuals: n_obs, rms_arcsec, max_arcsec, mean_dra, mean_ddec.

### `ObservationCoverage`
Sky coverage record: field_id, ra_deg, dec_deg, radius_deg, jd, n_observations, limiting_mag.
