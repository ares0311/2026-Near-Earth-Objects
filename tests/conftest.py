"""Configure sys.path so tests can import src modules without installation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from schemas import (
    CandidateFeatures,
    NEOPosterior,
    Observation,
    OrbitalElements,
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
