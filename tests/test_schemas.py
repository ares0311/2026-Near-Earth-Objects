"""Tests for schemas.py — data model construction and immutability."""

import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, "src")

from schemas import (
    CandidateFeatures,
    DetectProvenance,
    DetectResult,
    FetchProvenance,
    FetchResult,
    LinkProvenance,
    LinkResult,
    NEOPosterior,
    Observation,
    OrbitalElements,
    RawCandidate,
    Tracklet,
)


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="test_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def make_tracklet(n_obs: int = 3) -> Tracklet:
    obs = tuple(
        make_obs(obs_id=f"obs_{i}", jd=2460000.5 + i, ra_deg=180.0 + i * 0.01)
        for i in range(n_obs)
    )
    return Tracklet(
        object_id="T001",
        observations=obs,
        arc_days=float(n_obs - 1),
        motion_rate_arcsec_per_hour=1.2,
        motion_pa_degrees=90.0,
    )


class TestObservation:
    def test_valid(self):
        obs = make_obs()
        assert obs.ra_deg == 180.0

    def test_immutable(self):
        obs = make_obs()
        with pytest.raises(Exception):
            obs.ra_deg = 0.0  # type: ignore[misc]

    def test_ra_bounds(self):
        with pytest.raises(ValidationError):
            make_obs(ra_deg=361.0)
        with pytest.raises(ValidationError):
            make_obs(ra_deg=-1.0)

    def test_dec_bounds(self):
        with pytest.raises(ValidationError):
            make_obs(dec_deg=91.0)

    def test_optional_scores(self):
        obs = make_obs(real_bogus=0.9, deep_real_bogus=0.95)
        assert obs.real_bogus == 0.9
        assert obs.deep_real_bogus == 0.95


class TestTracklet:
    def test_construction(self):
        t = make_tracklet(3)
        assert len(t.observations) == 3
        assert t.arc_days == 2.0

    def test_frozen(self):
        t = make_tracklet()
        with pytest.raises(Exception):
            t.arc_days = 99.0  # type: ignore[misc]


class TestCandidateFeatures:
    def test_all_none(self):
        f = CandidateFeatures()
        assert f.real_bogus_score is None

    def test_with_values(self):
        f = CandidateFeatures(real_bogus_score=0.85, arc_coverage_score=0.5)
        assert f.real_bogus_score == 0.85

    def test_immutable(self):
        f = CandidateFeatures(real_bogus_score=0.8)
        with pytest.raises(Exception):
            f.real_bogus_score = 0.5  # type: ignore[misc]


class TestNEOPosterior:
    def test_valid(self):
        p = NEOPosterior(
            neo_candidate=0.6,
            known_object=0.1,
            main_belt_asteroid=0.1,
            stellar_artifact=0.1,
            other_solar_system=0.1,
        )
        assert p.neo_candidate == 0.6

    def test_bounds(self):
        with pytest.raises(ValidationError):
            NEOPosterior(
                neo_candidate=1.5,
                known_object=0.1,
                main_belt_asteroid=0.1,
                stellar_artifact=0.1,
                other_solar_system=0.1,
            )


class TestRawCandidate:
    def test_construction(self):
        obs = make_obs()
        cand = RawCandidate(
            candidate_id="C001",
            observations=(obs,),
            apparent_motion_arcsec_per_hr=2.5,
            is_streak=False,
        )
        assert cand.candidate_id == "C001"


class TestFetchResult:
    def test_empty(self):
        prov = FetchProvenance(surveys=("ZTF",), start_jd=2460000.0, end_jd=2460001.0)
        result = FetchResult(alerts=(), provenance=prov)
        assert len(result.alerts) == 0


class TestDetectResult:
    def test_construction(self):
        prov = DetectProvenance(real_bogus_threshold=0.65, n_candidates=0, n_known_matches=0)
        result = DetectResult(candidates=(), known_matches=(), provenance=prov)
        assert result.provenance.n_candidates == 0


class TestLinkResult:
    def test_construction(self):
        prov = LinkProvenance(n_tracklets=0, min_nights=2, min_observations=3)
        result = LinkResult(tracklets=(), provenance=prov)
        assert result.provenance.n_tracklets == 0


class TestOrbitalElements:
    def test_construction(self):
        el = OrbitalElements(
            semi_major_axis_au=1.5,
            eccentricity=0.3,
            inclination_deg=15.0,
            longitude_ascending_node_deg=45.0,
            argument_perihelion_deg=90.0,
            mean_anomaly_deg=180.0,
            epoch_jd=2460000.5,
            perihelion_au=1.05,
            aphelion_au=1.95,
        )
        assert el.quality_code == 1
