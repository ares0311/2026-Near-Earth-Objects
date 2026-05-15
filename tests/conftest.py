"""Configure sys.path so tests can import src modules without installation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from schemas import (
    CandidateExplanation,
    CandidateFeatures,
    HazardAssessment,
    NEOPosterior,
    Observation,
    OrbitalElements,
    RawCandidate,
    ScoredNEO,
    ScoringMetadata,
    Tracklet,
)


def build_observation(**kwargs) -> Observation:
    defaults = dict(
        obs_id="t_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.9,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def build_tracklet(n_obs: int = 4, arc_days: float = 3.0, **obs_kwargs) -> Tracklet:
    obs = tuple(
        build_observation(
            obs_id=f"t_{i}",
            jd=2460000.5 + i * arc_days / max(n_obs - 1, 1),
            ra_deg=180.0 + i * 0.005,
            **obs_kwargs,
        )
        for i in range(n_obs)
    )
    return Tracklet(
        object_id="T001",
        observations=obs,
        arc_days=arc_days,
        motion_rate_arcsec_per_hour=1.2,
        motion_pa_degrees=90.0,
    )


def build_orbital_elements(**kwargs) -> OrbitalElements:
    defaults = dict(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=2,
    )
    defaults.update(kwargs)
    return OrbitalElements(**defaults)


@pytest.fixture
def obs() -> Observation:
    return build_observation()


@pytest.fixture
def tracklet() -> Tracklet:
    return build_tracklet()


@pytest.fixture
def orbital_elements() -> OrbitalElements:
    return build_orbital_elements()


def build_raw_candidate(
    n_obs: int = 2,
    arc_days: float = 0.0,
    rate: float = 1.2,
    **obs_kwargs,
) -> RawCandidate:
    obs = tuple(
        build_observation(
            obs_id=f"rc_{i}",
            jd=2460000.5 + i * max(arc_days, 0.0),
            ra_deg=180.0 + i * 0.001,
            **obs_kwargs,
        )
        for i in range(n_obs)
    )
    return RawCandidate(
        candidate_id="RC001",
        observations=obs,
        apparent_motion_arcsec_per_hr=rate,
    )


def build_scored_neo(
    moid_au: float = 0.03,
    rb: float = 0.95,
    orbit_quality: int = 2,
    hazard_flag: str = "pha_candidate",
    alert_pathway: str = "mpc_submission",
    discovery_priority: float = 0.8,
    object_id: str = "T001",
) -> ScoredNEO:
    obs = tuple(
        build_observation(obs_id=f"sn_{i}", jd=2460000.5 + i)
        for i in range(3)
    )
    tracklet = Tracklet(
        object_id=object_id,
        observations=obs,
        arc_days=2.0,
        motion_rate_arcsec_per_hour=1.2,
        motion_pa_degrees=90.0,
    )
    features = CandidateFeatures(real_bogus_score=rb)
    posterior = NEOPosterior(
        neo_candidate=0.75,
        known_object=0.05,
        main_belt_asteroid=0.1,
        stellar_artifact=0.05,
        other_solar_system=0.05,
    )
    explanation = CandidateExplanation(
        summary="Test candidate",
        supporting_evidence=("High RB score",),
        contra_evidence=(),
        model_version="0.1.0",
    )
    orbital = OrbitalElements(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=orbit_quality,
    )
    hazard = HazardAssessment(
        hazard_flag=hazard_flag,  # type: ignore[arg-type]
        moid_au=moid_au,
        estimated_diameter_m=200.0,
        absolute_magnitude_h=21.5,
        neo_class="apollo",
        alert_pathway=alert_pathway,  # type: ignore[arg-type]
        explanation=explanation,
        orbital_elements=orbital,
    )
    metadata = ScoringMetadata(
        scorer_version="0.1.0",
        scored_at_jd=2460000.5,
        pipeline_run_id="test_run_001",
        discovery_priority=discovery_priority,
        followup_value=0.6,
        scientific_interest=0.5,
    )
    return ScoredNEO(
        tracklet=tracklet,
        features=features,
        posterior=posterior,
        hazard=hazard,
        metadata=metadata,
    )


@pytest.fixture
def candidate_features() -> CandidateFeatures:
    return CandidateFeatures(
        real_bogus_score=0.9,
        motion_consistency_score=0.85,
        arc_coverage_score=0.6,
        nights_observed_score=0.5,
        brightness_score=0.7,
    )


@pytest.fixture
def neo_posterior() -> NEOPosterior:
    return NEOPosterior(
        neo_candidate=0.6,
        known_object=0.1,
        main_belt_asteroid=0.1,
        stellar_artifact=0.1,
        other_solar_system=0.1,
    )


@pytest.fixture
def raw_candidate() -> RawCandidate:
    return build_raw_candidate()


@pytest.fixture
def scored_neo() -> ScoredNEO:
    return build_scored_neo()
