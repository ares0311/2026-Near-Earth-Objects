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
    PipelineResult,
    PreprocessProvenance,
    PreprocessResult,
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


def _make_pipeline_result(**kwargs):
    obs = (Observation(
        obs_id="pr1", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
        mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF",
    ),)
    fetch = FetchResult(
        alerts=obs,
        provenance=FetchProvenance(surveys=("ZTF",), start_jd=2460000.0, end_jd=2460001.0),
    )
    preprocess = PreprocessResult(
        sources=obs,
        provenance=PreprocessProvenance(n_sources_in=1, n_sources_out=1),
    )
    detect = DetectResult(
        candidates=(),
        known_matches=(),
        provenance=DetectProvenance(real_bogus_threshold=0.65, n_candidates=0, n_known_matches=0),
    )
    link = LinkResult(
        tracklets=(),
        provenance=LinkProvenance(n_tracklets=0, min_nights=3, min_observations=6),
    )
    defaults = dict(
        run_id="test_run_001",
        started_at_jd=2460000.0,
        finished_at_jd=2460000.1,
        fetch=fetch,
        preprocess=preprocess,
        detect=detect,
        link=link,
        scored_neos=(),
    )
    defaults.update(kwargs)
    return PipelineResult(**defaults)


class TestPipelineResult:
    def test_constructs_successfully(self):
        pr = _make_pipeline_result()
        assert pr.run_id == "test_run_001"

    def test_is_frozen(self):
        pr = _make_pipeline_result()
        with pytest.raises(Exception):
            pr.run_id = "modified"  # type: ignore[misc]

    def test_default_n_pha_candidates_zero(self):
        pr = _make_pipeline_result()
        assert pr.n_pha_candidates == 0

    def test_custom_n_pha_candidates(self):
        pr = _make_pipeline_result(n_pha_candidates=3)
        assert pr.n_pha_candidates == 3

    def test_scored_neos_empty_tuple_default(self):
        pr = _make_pipeline_result()
        assert pr.scored_neos == ()

    def test_pipeline_version_default_empty(self):
        pr = _make_pipeline_result()
        assert pr.pipeline_version == ""


class TestObservationWindow:
    def test_constructs_successfully(self):
        from schemas import ObservationWindow
        w = ObservationWindow(
            ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
            start_jd=2460000.0, end_jd=2460001.0,
        )
        assert w.ra_deg == 180.0

    def test_is_frozen(self):
        from schemas import ObservationWindow
        w = ObservationWindow(
            ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
            start_jd=2460000.0, end_jd=2460001.0,
        )
        with pytest.raises(Exception):
            w.ra_deg = 0.0  # type: ignore[misc]

    def test_default_surveys_is_ztf(self):
        from schemas import ObservationWindow
        w = ObservationWindow(
            ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
            start_jd=2460000.0, end_jd=2460001.0,
        )
        assert "ZTF" in w.surveys

    def test_custom_surveys(self):
        from schemas import ObservationWindow
        w = ObservationWindow(
            ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
            start_jd=2460000.0, end_jd=2460001.0,
            surveys=("ATLAS", "PanSTARRS"),
        )
        assert "ATLAS" in w.surveys

    def test_description_default_empty(self):
        from schemas import ObservationWindow
        w = ObservationWindow(
            ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
            start_jd=2460000.0, end_jd=2460001.0,
        )
        assert w.description == ""

    def test_custom_description(self):
        from schemas import ObservationWindow
        w = ObservationWindow(
            ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
            start_jd=2460000.0, end_jd=2460001.0,
            description="Test field",
        )
        assert w.description == "Test field"


class TestCandidateSummary:
    def _make_summary(self, **kwargs) -> object:
        from schemas import CandidateSummary
        defaults = dict(
            object_id="T001",
            neo_class="apollo",
            hazard_flag="pha_candidate",
            alert_pathway="mpc_submission",
            arc_days=3.0,
            n_observations=5,
            neo_candidate_probability=0.8,
        )
        defaults.update(kwargs)
        return CandidateSummary(**defaults)

    def test_instantiation(self):
        s = self._make_summary()
        assert s.object_id == "T001"

    def test_frozen(self):
        import pytest
        s = self._make_summary()
        with pytest.raises(Exception):
            s.object_id = "X"  # type: ignore[misc]

    def test_optional_fields_default_none(self):
        s = self._make_summary()
        assert s.moid_au is None
        assert s.estimated_diameter_m is None
        assert s.absolute_magnitude_h is None

    def test_discovery_priority_default_zero(self):
        s = self._make_summary()
        assert s.discovery_priority == 0.0

    def test_custom_moid(self):
        s = self._make_summary(moid_au=0.03)
        assert s.moid_au == pytest.approx(0.03)

    def test_neo_class_field(self):
        s = self._make_summary(neo_class="aten")
        assert s.neo_class == "aten"


class TestNEOStatistics:
    def _make_stats(self, **kwargs) -> object:
        from schemas import NEOStatistics
        defaults = dict(
            n_total=10,
            n_pha_candidates=2,
            n_mpc_submission=3,
            n_internal_candidate=5,
            n_known_object=1,
            mean_discovery_priority=0.6,
            max_discovery_priority=0.95,
        )
        defaults.update(kwargs)
        return NEOStatistics(**defaults)

    def test_instantiation(self):
        s = self._make_stats()
        assert s.n_total == 10

    def test_frozen(self):
        import pytest
        s = self._make_stats()
        with pytest.raises(Exception):
            s.n_total = 99  # type: ignore[misc]

    def test_default_neo_class_distribution_empty(self):
        s = self._make_stats()
        assert s.neo_class_distribution == {}

    def test_custom_distribution(self):
        s = self._make_stats(neo_class_distribution={"apollo": 5, "amor": 3})
        assert s.neo_class_distribution["apollo"] == 5

    def test_mean_priority_stored(self):
        s = self._make_stats(mean_discovery_priority=0.42)
        assert s.mean_discovery_priority == pytest.approx(0.42)

    def test_max_priority_stored(self):
        s = self._make_stats(max_discovery_priority=0.99)
        assert s.max_discovery_priority == pytest.approx(0.99)


class TestTrackletSummary:
    def _make_summary(self, **kwargs) -> object:
        from schemas import TrackletSummary

        defaults = dict(
            object_id="2026 AA1",
            arc_days=2.5,
            n_observations=6,
            motion_rate_arcsec_per_hour=3.2,
            motion_pa_degrees=45.0,
        )
        defaults.update(kwargs)
        return TrackletSummary(**defaults)

    def test_basic_construction(self):
        s = self._make_summary()
        assert s.object_id == "2026 AA1"
        assert s.arc_days == pytest.approx(2.5)
        assert s.n_observations == 6

    def test_default_neo_class(self):
        s = self._make_summary()
        assert s.neo_class == "unknown"

    def test_custom_neo_class(self):
        s = self._make_summary(neo_class="apollo")
        assert s.neo_class == "apollo"

    def test_default_discovery_priority(self):
        s = self._make_summary()
        assert s.discovery_priority == pytest.approx(0.0)

    def test_custom_discovery_priority(self):
        s = self._make_summary(discovery_priority=0.87)
        assert s.discovery_priority == pytest.approx(0.87)

    def test_immutable(self):
        import pytest as pt
        s = self._make_summary()
        with pt.raises(Exception):
            s.object_id = "changed"  # type: ignore[misc]

    def test_motion_pa_stored(self):
        s = self._make_summary(motion_pa_degrees=123.4)
        assert s.motion_pa_degrees == pytest.approx(123.4)


class TestCloseApproachEvent:
    def _make_event(self, **kwargs) -> object:
        from schemas import CloseApproachEvent
        defaults = dict(
            object_id="2026 AA1",
            jd=2460100.5,
            geocentric_dist_au=0.031,
        )
        defaults.update(kwargs)
        return CloseApproachEvent(**defaults)

    def test_basic_construction(self):
        ev = self._make_event()
        assert ev.object_id == "2026 AA1"
        assert ev.geocentric_dist_au == pytest.approx(0.031)

    def test_optional_fields_default_none(self):
        ev = self._make_event()
        assert ev.relative_velocity_km_s is None
        assert ev.warning_time_days is None

    def test_optional_fields_stored(self):
        ev = self._make_event(relative_velocity_km_s=12.5, warning_time_days=30.0)
        assert ev.relative_velocity_km_s == pytest.approx(12.5)
        assert ev.warning_time_days == pytest.approx(30.0)

    def test_jd_stored(self):
        ev = self._make_event(jd=2460200.0)
        assert ev.jd == pytest.approx(2460200.0)

    def test_immutable(self):
        import pytest as pt
        ev = self._make_event()
        with pt.raises(Exception):
            ev.object_id = "changed"  # type: ignore[misc]

    def test_zero_dist_allowed(self):
        ev = self._make_event(geocentric_dist_au=0.0)
        assert ev.geocentric_dist_au == pytest.approx(0.0)


class TestSurveyField:
    def _make_field(self, **kwargs):
        from schemas import SurveyField
        defaults = dict(
            field_id="F001",
            ra_deg=180.0,
            dec_deg=0.0,
            radius_deg=1.5,
            limiting_mag=21.5,
            n_sources=120,
            jd=2460000.5,
        )
        defaults.update(kwargs)
        return SurveyField(**defaults)

    def test_construction(self):
        f = self._make_field()
        assert f.field_id == "F001"
        assert f.ra_deg == pytest.approx(180.0)

    def test_immutable(self):
        import pytest as pt
        f = self._make_field()
        with pt.raises(Exception):
            f.field_id = "changed"  # type: ignore[misc]

    def test_n_sources_stored(self):
        f = self._make_field(n_sources=42)
        assert f.n_sources == 42

    def test_limiting_mag_stored(self):
        f = self._make_field(limiting_mag=22.0)
        assert f.limiting_mag == pytest.approx(22.0)

    def test_jd_stored(self):
        f = self._make_field(jd=2461000.5)
        assert f.jd == pytest.approx(2461000.5)


class TestPipelineConfig:
    def _make_config(self, **kwargs):
        from schemas import PipelineConfig
        defaults = dict(ra_deg=180.0, dec_deg=0.0)
        defaults.update(kwargs)
        return PipelineConfig(**defaults)

    def test_construction(self):
        cfg = self._make_config()
        assert cfg.ra_deg == pytest.approx(180.0)
        assert cfg.dec_deg == pytest.approx(0.0)

    def test_defaults(self):
        cfg = self._make_config()
        assert cfg.radius_deg == pytest.approx(1.0)
        assert cfg.real_bogus_threshold == pytest.approx(0.65)
        assert cfg.surveys == ("ZTF",)
        assert cfg.end_jd is None

    def test_immutable(self):
        import pytest as pt
        cfg = self._make_config()
        with pt.raises(Exception):
            cfg.ra_deg = 0.0  # type: ignore[misc]

    def test_custom_values(self):
        cfg = self._make_config(
            radius_deg=2.0,
            real_bogus_threshold=0.80,
            surveys=("ZTF", "ATLAS"),
            end_jd=2460100.5,
        )
        assert cfg.radius_deg == pytest.approx(2.0)
        assert cfg.real_bogus_threshold == pytest.approx(0.80)
        assert "ATLAS" in cfg.surveys
        assert cfg.end_jd == pytest.approx(2460100.5)

    def test_surveys_is_tuple(self):
        cfg = self._make_config(surveys=("ZTF", "Pan-STARRS"))
        assert isinstance(cfg.surveys, tuple)


class TestObservationBatch:
    def _make_obs(self, obs_id="b_001"):
        from .conftest import build_observation
        return build_observation(obs_id=obs_id, mission="ZTF")

    def _make_batch(self, **kwargs):
        from schemas import ObservationBatch
        defaults = dict(
            batch_id="batch_001",
            field_id="ZTF_F001",
            night_jd=2460000,
            mission="ZTF",
            observations=(self._make_obs("b_001"), self._make_obs("b_002")),
            limiting_mag=20.5,
        )
        defaults.update(kwargs)
        return ObservationBatch(**defaults)

    def test_construction(self):
        batch = self._make_batch()
        assert batch.batch_id == "batch_001"
        assert batch.field_id == "ZTF_F001"
        assert batch.night_jd == 2460000
        assert batch.mission == "ZTF"
        assert len(batch.observations) == 2
        assert batch.limiting_mag == pytest.approx(20.5)

    def test_limiting_mag_optional(self):
        from schemas import ObservationBatch
        batch = ObservationBatch(
            batch_id="b", field_id="f", night_jd=2460000, mission="ZTF",
            observations=(self._make_obs(),),
        )
        assert batch.limiting_mag is None

    def test_frozen(self):
        import pytest as pt
        batch = self._make_batch()
        with pt.raises(Exception):
            batch.batch_id = "other"  # type: ignore[misc]

    def test_observations_is_tuple(self):
        batch = self._make_batch()
        assert isinstance(batch.observations, tuple)

    def test_different_missions(self):
        from schemas import ObservationBatch

        from .conftest import build_observation
        obs = build_observation(mission="ATLAS")
        batch = ObservationBatch(
            batch_id="b2", field_id="ATLAS_F001", night_jd=2460001,
            mission="ATLAS", observations=(obs,),
        )
        assert batch.mission == "ATLAS"


class TestDetectionSummary:
    def _make_summary(self, **kwargs):
        from schemas import DetectionSummary
        defaults = dict(
            field_id="ZTF_F001", epoch_jd=2460000.5, survey="ZTF",
            n_candidates=10, n_known_matches=8, n_new=2, limiting_mag=20.5,
        )
        defaults.update(kwargs)
        return DetectionSummary(**defaults)

    def test_construction(self):
        s = self._make_summary()
        assert s.field_id == "ZTF_F001"
        assert s.n_candidates == 10
        assert s.n_new == 2
        assert s.limiting_mag == pytest.approx(20.5)

    def test_limiting_mag_optional(self):
        from schemas import DetectionSummary
        s = DetectionSummary(field_id="F", epoch_jd=2460000.5, survey="ZTF",
                             n_candidates=5, n_known_matches=3, n_new=2)
        assert s.limiting_mag is None

    def test_frozen(self):
        import pytest as pt
        s = self._make_summary()
        with pt.raises(Exception):
            s.field_id = "other"  # type: ignore[misc]

    def test_zero_candidates(self):
        s = self._make_summary(n_candidates=0, n_known_matches=0, n_new=0)
        assert s.n_candidates == 0

    def test_different_surveys(self):
        for survey in ("ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"):
            s = self._make_summary(survey=survey)
            assert s.survey == survey


class TestPhotometricSolution:
    def test_instantiation(self):
        from schemas import PhotometricSolution
        sol = PhotometricSolution(zero_point=25.0, filter_band="r", epoch_jd=2460000.5)
        assert sol.zero_point == 25.0

    def test_defaults(self):
        from schemas import PhotometricSolution
        sol = PhotometricSolution(zero_point=25.0)
        assert sol.color_coeff == 0.0
        assert sol.extinction_coeff == 0.0
        assert sol.rms_scatter is None
        assert sol.n_stars == 0
        assert sol.filter_band == "r"
        assert sol.epoch_jd is None

    def test_frozen(self):
        from schemas import PhotometricSolution
        sol = PhotometricSolution(zero_point=25.0)
        with pytest.raises(Exception):
            sol.zero_point = 26.0  # type: ignore[misc]

    def test_all_fields(self):
        from schemas import PhotometricSolution
        sol = PhotometricSolution(
            zero_point=25.5, color_coeff=0.05, extinction_coeff=0.12,
            rms_scatter=0.02, n_stars=150, filter_band="g", epoch_jd=2460000.5,
        )
        assert sol.rms_scatter == pytest.approx(0.02)
        assert sol.n_stars == 150
        assert sol.filter_band == "g"

    def test_n_stars_nonnegative(self):
        import pytest

        from schemas import PhotometricSolution
        with pytest.raises(Exception):
            PhotometricSolution(zero_point=25.0, n_stars=-1)


class TestObservationStatistics:
    def test_instantiation_minimal(self):
        from schemas import ObservationStatistics
        s = ObservationStatistics(n_obs=5)
        assert s.n_obs == 5

    def test_defaults(self):
        from schemas import ObservationStatistics
        s = ObservationStatistics(n_obs=0)
        assert s.mean_mag is None
        assert s.mag_range is None
        assert s.mean_real_bogus is None
        assert s.n_filters == 0
        assert s.arc_days == 0.0

    def test_frozen(self):
        from schemas import ObservationStatistics
        s = ObservationStatistics(n_obs=3)
        with pytest.raises(Exception):
            s.n_obs = 4  # type: ignore[misc]

    def test_all_fields(self):
        from schemas import ObservationStatistics
        s = ObservationStatistics(
            n_obs=10, mean_mag=19.5, mag_range=1.2,
            mean_real_bogus=0.85, n_filters=2, arc_days=3.5,
        )
        assert s.mean_mag == pytest.approx(19.5)
        assert s.n_filters == 2

    def test_n_obs_nonnegative(self):
        from schemas import ObservationStatistics
        with pytest.raises(Exception):
            ObservationStatistics(n_obs=-1)


class TestAlertPackage:
    def _make_obs(self):
        from schemas import Observation
        return Observation(
            obs_id="o1", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )

    def test_basic_construction(self):
        from schemas import AlertPackage
        pkg = AlertPackage(
            neo_id="NEO-001",
            alert_pathway="mpc_submission",
            submission_timestamp_jd=2460001.0,
        )
        assert pkg.neo_id == "NEO-001"
        assert pkg.alert_pathway == "mpc_submission"

    def test_default_guardrail_contains_not(self):
        from schemas import AlertPackage
        pkg = AlertPackage(
            neo_id="NEO-002",
            alert_pathway="internal_candidate",
            submission_timestamp_jd=2460001.0,
        )
        assert "NOT" in pkg.guardrail_statement.upper()

    def test_with_observations(self):
        from schemas import AlertPackage
        obs = self._make_obs()
        pkg = AlertPackage(
            neo_id="NEO-003",
            alert_pathway="mpc_submission",
            moid_au=0.04,
            observations=(obs,),
            submission_timestamp_jd=2460001.0,
        )
        assert len(pkg.observations) == 1
        assert pkg.moid_au == 0.04

    def test_frozen(self):
        import pytest

        from schemas import AlertPackage
        pkg = AlertPackage(
            neo_id="NEO-004",
            alert_pathway="mpc_submission",
            submission_timestamp_jd=2460001.0,
        )
        with pytest.raises(Exception):
            pkg.neo_id = "CHANGED"

    def test_none_moid_allowed(self):
        from schemas import AlertPackage
        pkg = AlertPackage(
            neo_id="NEO-005",
            alert_pathway="internal_candidate",
            moid_au=None,
            submission_timestamp_jd=2460001.0,
        )
        assert pkg.moid_au is None

    def test_in_all(self):
        from schemas import __all__
        assert "AlertPackage" in __all__


class TestOrbitalElementsSummary:
    def _make_summary(self, **kwargs):
        from schemas import OrbitalElementsSummary
        defaults = dict(
            object_id="test_neo",
            neo_class="apollo",
            semi_major_axis_au=1.5,
            eccentricity=0.3,
            inclination_deg=15.0,
            perihelion_au=1.05,
            aphelion_au=1.95,
            moid_au=0.02,
            quality_code=2,
            epoch_jd=2460000.5,
        )
        defaults.update(kwargs)
        return OrbitalElementsSummary(**defaults)

    def test_basic_construction(self):
        s = self._make_summary()
        assert s.object_id == "test_neo"
        assert s.neo_class == "apollo"

    def test_frozen(self):
        import pytest
        s = self._make_summary()
        with pytest.raises(Exception):
            s.object_id = "other"

    def test_moid_none_allowed(self):
        s = self._make_summary(moid_au=None)
        assert s.moid_au is None

    def test_default_quality_code(self):
        from schemas import OrbitalElementsSummary
        s = OrbitalElementsSummary(
            object_id="x", neo_class="amor",
            semi_major_axis_au=1.2, eccentricity=0.1,
            inclination_deg=5.0, perihelion_au=1.1, aphelion_au=1.3,
            epoch_jd=2460000.5,
        )
        assert s.quality_code == 1

    def test_in_all(self):
        from schemas import __all__
        assert "OrbitalElementsSummary" in __all__

    def test_model_copy(self):
        s = self._make_summary()
        s2 = s.model_copy(update={"quality_code": 3})
        assert s2.quality_code == 3
        assert s.quality_code == 2


class TestCandidateReport:
    def _make_report(self, **kwargs):
        from schemas import CandidateReport
        defaults = dict(
            object_id="test_neo_001",
            neo_class="apollo",
            hazard_flag="pha_candidate",
            alert_pathway="mpc_submission",
            moid_au=0.02,
            absolute_magnitude_h=21.5,
            estimated_diameter_m=180.0,
            discovery_priority=0.85,
            neo_candidate_prob=0.78,
            n_observations=6,
            arc_days=3.2,
            generated_jd=2460100.0,
        )
        defaults.update(kwargs)
        return CandidateReport(**defaults)

    def test_basic_construction(self):
        r = self._make_report()
        assert r.object_id == "test_neo_001"
        assert r.neo_class == "apollo"

    def test_frozen(self):
        import pytest
        r = self._make_report()
        with pytest.raises(Exception):
            r.object_id = "other"

    def test_optional_moid(self):
        r = self._make_report(moid_au=None)
        assert r.moid_au is None

    def test_defaults(self):
        from schemas import CandidateReport
        r = CandidateReport(
            object_id="x", neo_class="amor", hazard_flag="nominal",
            alert_pathway="internal_candidate",
        )
        assert r.discovery_priority == 0.0
        assert r.n_observations == 0

    def test_model_copy(self):
        r = self._make_report()
        r2 = r.model_copy(update={"n_observations": 10})
        assert r2.n_observations == 10
        assert r.n_observations == 6

    def test_in_all(self):
        from schemas import __all__
        assert "CandidateReport" in __all__


class TestSurveyStatistics:
    """Tests for SurveyStatistics schema."""

    def _make(self, **kwargs):
        from schemas import SurveyStatistics
        defaults = dict(survey="ZTF")
        defaults.update(kwargs)
        return SurveyStatistics(**defaults)

    def test_construction_defaults(self):
        ss = self._make()
        assert ss.survey == "ZTF"
        assert ss.n_fields == 0
        assert ss.n_observations == 0
        assert ss.n_candidates == 0
        assert ss.n_tracklets == 0
        assert ss.mean_limiting_mag is None
        assert ss.epoch_start_jd == 0.0
        assert ss.epoch_end_jd == 0.0

    def test_construction_with_values(self):
        ss = self._make(
            survey="ATLAS",
            n_fields=50,
            n_observations=200,
            n_candidates=20,
            n_tracklets=10,
            mean_limiting_mag=19.5,
            epoch_start_jd=2460000.0,
            epoch_end_jd=2460100.0,
        )
        assert ss.survey == "ATLAS"
        assert ss.n_fields == 50
        assert ss.n_observations == 200
        assert ss.n_candidates == 20
        assert ss.n_tracklets == 10
        assert ss.mean_limiting_mag == 19.5
        assert ss.epoch_start_jd == 2460000.0
        assert ss.epoch_end_jd == 2460100.0

    def test_frozen_cannot_mutate(self):
        from pydantic import ValidationError
        ss = self._make(survey="ZTF", n_fields=10)
        with pytest.raises((ValidationError, TypeError)):
            ss.n_fields = 99  # type: ignore[misc]

    def test_model_copy(self):
        ss = self._make(n_fields=50)
        ss2 = ss.model_copy(update={"n_fields": 100})
        assert ss2.n_fields == 100
        assert ss.n_fields == 50

    def test_in_all(self):
        from schemas import __all__
        assert "SurveyStatistics" in __all__


class TestEphemerisPoint:
    """Tests for EphemerisPoint schema."""

    def test_basic_construction(self):
        from schemas import EphemerisPoint
        ep = EphemerisPoint(
            object_id="NEO001",
            jd=2460000.5,
            ra_deg=180.0,
            dec_deg=10.0,
        )
        assert ep.object_id == "NEO001"
        assert ep.jd == 2460000.5
        assert ep.ra_deg == 180.0
        assert ep.dec_deg == 10.0

    def test_defaults(self):
        from schemas import EphemerisPoint
        ep = EphemerisPoint(object_id="X", jd=2460000.5, ra_deg=0.0, dec_deg=0.0)
        assert ep.delta_au == 1.0
        assert ep.r_au == 1.0
        assert ep.phase_deg is None
        assert ep.mag is None

    def test_with_all_fields(self):
        from schemas import EphemerisPoint
        ep = EphemerisPoint(
            object_id="NEO002",
            jd=2460010.0,
            ra_deg=90.0,
            dec_deg=-15.0,
            delta_au=0.8,
            r_au=1.1,
            phase_deg=35.0,
            mag=18.5,
        )
        assert ep.delta_au == 0.8
        assert ep.r_au == 1.1
        assert ep.phase_deg == 35.0
        assert ep.mag == 18.5

    def test_is_frozen(self):
        import pytest

        from schemas import EphemerisPoint
        ep = EphemerisPoint(object_id="Y", jd=2460000.5, ra_deg=0.0, dec_deg=0.0)
        with pytest.raises(Exception):
            ep.ra_deg = 99.0  # type: ignore[misc]

    def test_in_all(self):
        from schemas import __all__
        assert "EphemerisPoint" in __all__


class TestObservationClusterLegacy:
    """Legacy tests for ObservationCluster schema (updated for v0.62.0 fields)."""

    def test_basic_construction(self):
        from schemas import ObservationCluster
        oc = ObservationCluster(
            cluster_id="CL001",
            center_ra_deg=180.0,
            center_dec_deg=10.0,
            radius_arcsec=0.0,
            epoch_jd=2460000.5,
        )
        assert oc.cluster_id == "CL001"
        assert oc.center_ra_deg == 180.0
        assert oc.observations == ()
        assert oc.radius_arcsec == 0.0

    def test_with_observations(self):
        from schemas import Observation, ObservationCluster
        obs = (Observation(
            obs_id="o1", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        ),)
        oc = ObservationCluster(
            cluster_id="CL002", center_ra_deg=180.0, center_dec_deg=10.0,
            observations=obs, radius_arcsec=5.0, epoch_jd=2460000.5,
        )
        assert len(oc.observations) == 1
        assert oc.radius_arcsec == 5.0

    def test_is_frozen(self):
        import pytest

        from schemas import ObservationCluster
        oc = ObservationCluster(
            cluster_id="X", center_ra_deg=0.0, center_dec_deg=0.0,
            radius_arcsec=0.0, epoch_jd=2460000.5,
        )
        with pytest.raises(Exception):
            oc.cluster_id = "Y"  # type: ignore[misc]

    def test_in_all(self):
        from schemas import __all__
        assert "ObservationCluster" in __all__


class TestAstrometricResidual:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import AstrometricResidual
        r = AstrometricResidual(obs_id="obs1", ra_residual_arcsec=0.2,
                                dec_residual_arcsec=-0.1, total_arcsec=0.22,
                                jd=2460000.5)
        assert r.obs_id == "obs1"
        assert r.total_arcsec == 0.22

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import AstrometricResidual
        r = AstrometricResidual(obs_id="x", ra_residual_arcsec=0.0,
                                dec_residual_arcsec=0.0, total_arcsec=0.0, jd=0.0)
        with pytest.raises(Exception):
            r.obs_id = "y"

    def test_negative_residuals(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import AstrometricResidual
        r = AstrometricResidual(obs_id="x", ra_residual_arcsec=-1.5,
                                dec_residual_arcsec=-0.5, total_arcsec=1.58, jd=2460001.0)
        assert r.ra_residual_arcsec == -1.5

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "AstrometricResidual" in schemas.__all__


class TestResidualSummary:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ResidualSummary
        r = ResidualSummary(object_id="T1", n_obs=3, rms_arcsec=0.25,
                            max_residual_arcsec=0.45, mean_ra_residual_arcsec=0.01,
                            mean_dec_residual_arcsec=-0.02)
        assert r.object_id == "T1"
        assert r.n_obs == 3

    def test_frozen(self):
        import sys

        import pytest
        sys.path.insert(0, "src")
        from schemas import ResidualSummary
        r = ResidualSummary(object_id="x", n_obs=1, rms_arcsec=0.0,
                            max_residual_arcsec=0.0, mean_ra_residual_arcsec=0.0,
                            mean_dec_residual_arcsec=0.0)
        with pytest.raises(Exception):
            r.n_obs = 2

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "ResidualSummary" in schemas.__all__

    def test_zero_residuals(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ResidualSummary
        r = ResidualSummary(object_id="T2", n_obs=5, rms_arcsec=0.0,
                            max_residual_arcsec=0.0, mean_ra_residual_arcsec=0.0,
                            mean_dec_residual_arcsec=0.0)
        assert r.rms_arcsec == 0.0


class TestObservationCoverage:
    def test_basic(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(night_jd=2460000.5, mission="ZTF",
                                 n_fields=5, total_area_deg2=100.0,
                                 limiting_mag=21.5,
                                 field_ids=("ZTF01", "ZTF02"))
        assert oc.n_fields == 5
        assert oc.mission == "ZTF"
        assert oc.limiting_mag == 21.5
        assert oc.field_ids == ("ZTF01", "ZTF02")

    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(night_jd=2460000.5, mission="ATLAS",
                                 n_fields=1, total_area_deg2=10.0)
        assert oc.limiting_mag is None
        assert oc.field_ids == ()

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(night_jd=2460000.5, mission="ZTF",
                                 n_fields=1, total_area_deg2=5.0)
        with pytest.raises(Exception):
            oc.n_fields = 2

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "ObservationCoverage" in schemas.__all__


class TestNightSummary:
    def test_basic(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import NightSummary
        ns = NightSummary(night_jd=2460000.5, survey="ZTF",
                          n_tracklets=10, n_new=3, n_known=7, n_pha_candidates=1)
        assert ns.n_tracklets == 10
        assert ns.survey == "ZTF"
        assert ns.n_pha_candidates == 1

    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import NightSummary
        ns = NightSummary(night_jd=2460000.5, survey="ATLAS",
                          n_tracklets=5, n_new=2, n_known=3, n_pha_candidates=0)
        assert ns.fields_covered == ()
        assert ns.limiting_mag is None

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import NightSummary
        ns = NightSummary(night_jd=2460000.5, survey="ZTF",
                          n_tracklets=1, n_new=1, n_known=0, n_pha_candidates=0)
        with pytest.raises(Exception):
            ns.n_tracklets = 99

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "NightSummary" in schemas.__all__


class TestTrackletCluster:
    def test_basic(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import TrackletCluster
        tc = TrackletCluster(cluster_id="C1", tracklet_ids=("A", "B"),
                             centroid_ra_deg=15.0, centroid_dec_deg=-5.0,
                             n_tracklets=2)
        assert tc.n_tracklets == 2
        assert tc.cluster_id == "C1"

    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import TrackletCluster
        tc = TrackletCluster(cluster_id="C2", centroid_ra_deg=0.0,
                             centroid_dec_deg=0.0, n_tracklets=1)
        assert tc.tracklet_ids == ()
        assert tc.arc_span_days == 0.0

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import TrackletCluster
        tc = TrackletCluster(cluster_id="C3", centroid_ra_deg=0.0,
                             centroid_dec_deg=0.0, n_tracklets=1)
        with pytest.raises(Exception):
            tc.n_tracklets = 5

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "TrackletCluster" in schemas.__all__


class TestCampaignSummary:
    def test_basic(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CampaignSummary
        cs = CampaignSummary(
            campaign_id="camp001",
            start_jd=2460000.0,
            end_jd=2460010.0,
            n_nights=5,
            n_tracklets=20,
            n_pha_candidates=1,
            surveys_used=("ZTF", "ATLAS"),
            sky_area_deg2=100.0,
        )
        assert cs.campaign_id == "camp001"
        assert cs.n_nights == 5
        assert cs.surveys_used == ("ZTF", "ATLAS")
        assert cs.sky_area_deg2 == 100.0

    def test_optional_sky_area(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CampaignSummary
        cs = CampaignSummary(
            campaign_id="c2",
            start_jd=2460000.0,
            end_jd=2460003.0,
            n_nights=3,
            n_tracklets=5,
            n_pha_candidates=0,
        )
        assert cs.sky_area_deg2 is None

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import CampaignSummary
        cs = CampaignSummary(
            campaign_id="c3",
            start_jd=2460000.0,
            end_jd=2460005.0,
            n_nights=2,
            n_tracklets=3,
            n_pha_candidates=0,
        )
        with pytest.raises(Exception):
            cs.campaign_id = "changed"  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "CampaignSummary" in schemas.__all__


class TestFieldObservationSummary:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldObservationSummary
        fos = FieldObservationSummary(
            field_id="F001",
            epoch_jd=2460000.0,
            survey="ZTF",
            n_sources=150,
            n_moving=5,
            n_known=3,
            n_new=2,
            limiting_mag=21.5,
        )
        assert fos.field_id == "F001"
        assert fos.n_sources == 150
        assert fos.limiting_mag == 21.5

    def test_default_values(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldObservationSummary
        fos = FieldObservationSummary(field_id="F002", epoch_jd=2460001.0, survey="ATLAS")
        assert fos.n_sources == 0
        assert fos.n_moving == 0
        assert fos.n_known == 0
        assert fos.n_new == 0
        assert fos.limiting_mag is None

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldObservationSummary
        fos = FieldObservationSummary(field_id="F003", epoch_jd=2460002.0, survey="ZTF")
        with pytest.raises(Exception):
            fos.n_sources = 99

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "FieldObservationSummary" in schemas.__all__


class TestObservationCluster:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCluster
        oc = ObservationCluster(
            cluster_id="C001",
            center_ra_deg=180.0,
            center_dec_deg=5.0,
            radius_arcsec=30.0,
            epoch_jd=2460000.0,
            n_observations=3,
        )
        assert oc.cluster_id == "C001"
        assert oc.n_observations == 3
        assert oc.observations == ()

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCluster
        oc = ObservationCluster(
            cluster_id="C002",
            center_ra_deg=10.0,
            center_dec_deg=0.0,
            radius_arcsec=10.0,
            epoch_jd=2460001.0,
        )
        with pytest.raises(Exception):
            oc.cluster_id = "X"

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "ObservationCluster" in schemas.__all__


class TestSurveyRun:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import SurveyRun
        r = SurveyRun(run_id="r1", survey="ZTF", epoch_jd=2460000.0, field_id="f1")
        assert r.run_id == "r1"
        assert r.n_candidates == 0
        assert r.limiting_mag is None

    def test_with_all_fields(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import SurveyRun
        r = SurveyRun(run_id="r2", survey="ATLAS", epoch_jd=2460001.0, field_id="f2",
                      n_candidates=5, sky_coverage_deg2=3.14, limiting_mag=21.5)
        assert r.n_candidates == 5
        assert r.limiting_mag == 21.5

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import SurveyRun
        r = SurveyRun(run_id="r3", survey="ZTF", epoch_jd=2460000.0, field_id="f3")
        with pytest.raises(Exception):
            r.run_id = "x"  # type: ignore

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "SurveyRun" in schemas.__all__


class TestCandidateCluster:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CandidateCluster
        cc = CandidateCluster(
            cluster_id="cluster-001",
            run_id="run-42",
            center_ra_deg=120.5,
            center_dec_deg=-10.0,
            n_candidates=3,
            candidate_ids=("a", "b", "c"),
        )
        assert cc.cluster_id == "cluster-001"
        assert cc.n_candidates == 3
        assert cc.mean_priority == 0.0

    def test_with_mean_priority(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CandidateCluster
        cc = CandidateCluster(
            cluster_id="c2",
            run_id="r2",
            center_ra_deg=0.0,
            center_dec_deg=0.0,
            n_candidates=2,
            candidate_ids=("x", "y"),
            mean_priority=0.75,
        )
        assert cc.mean_priority == 0.75
        assert cc.candidate_ids == ("x", "y")

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import CandidateCluster
        cc = CandidateCluster(
            cluster_id="c3",
            run_id="r3",
            center_ra_deg=5.0,
            center_dec_deg=5.0,
            n_candidates=1,
            candidate_ids=("z",),
        )
        with pytest.raises(Exception):
            cc.cluster_id = "changed"  # type: ignore

    def test_empty_candidate_ids(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CandidateCluster
        cc = CandidateCluster(
            cluster_id="c4",
            run_id="r4",
            center_ra_deg=180.0,
            center_dec_deg=45.0,
            n_candidates=0,
            candidate_ids=(),
        )
        assert cc.candidate_ids == ()
        assert cc.n_candidates == 0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "CandidateCluster" in schemas.__all__


class TestObservationCoverageRunId:
    """Tests for the new run_id / mean_limiting_mag / epoch_jd fields."""

    def test_run_id_field(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(
            night_jd=2460000.5, mission="ZTF",
            n_fields=3, total_area_deg2=50.0,
            run_id="run-001",
        )
        assert oc.run_id == "run-001"

    def test_mean_limiting_mag_field(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(
            night_jd=2460000.5, mission="ATLAS",
            n_fields=2, total_area_deg2=30.0,
            mean_limiting_mag=21.0,
        )
        assert oc.mean_limiting_mag == 21.0

    def test_epoch_jd_field(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(
            night_jd=2460000.5, mission="ZTF",
            n_fields=1, total_area_deg2=10.0,
            epoch_jd=2460001.0,
        )
        assert oc.epoch_jd == 2460001.0

    def test_all_new_fields_together(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(
            night_jd=2460000.5, mission="PanSTARRS",
            n_fields=5, total_area_deg2=100.0,
            run_id="run-xyz",
            mean_limiting_mag=22.5,
            epoch_jd=2460000.75,
        )
        assert oc.run_id == "run-xyz"
        assert oc.mean_limiting_mag == 22.5
        assert oc.epoch_jd == 2460000.75

    def test_new_fields_default_to_none(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationCoverage
        oc = ObservationCoverage(
            night_jd=2460000.5, mission="ZTF",
            n_fields=1, total_area_deg2=5.0,
        )
        assert oc.run_id is None
        assert oc.mean_limiting_mag is None
        assert oc.epoch_jd is None


class TestPipelineRunSummary:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import PipelineRunSummary
        prs = PipelineRunSummary(run_id="run-001", epoch_jd=2460000.5)
        assert prs.run_id == "run-001"
        assert prs.epoch_jd == 2460000.5

    def test_default_values(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import PipelineRunSummary
        prs = PipelineRunSummary(run_id="r", epoch_jd=2460000.0)
        assert prs.n_tracklets == 0
        assert prs.n_pha_candidates == 0
        assert prs.n_new_candidates == 0
        assert prs.top_priority == 0.0
        assert prs.alert_pathways == ()

    def test_full_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import PipelineRunSummary
        prs = PipelineRunSummary(
            run_id="run-full",
            epoch_jd=2460100.0,
            n_tracklets=42,
            n_pha_candidates=3,
            n_new_candidates=10,
            top_priority=0.97,
            alert_pathways=("mpc_submission", "nasa_pdco_notify"),
        )
        assert prs.n_tracklets == 42
        assert prs.n_pha_candidates == 3
        assert prs.n_new_candidates == 10
        assert prs.top_priority == 0.97
        assert "mpc_submission" in prs.alert_pathways

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import PipelineRunSummary
        prs = PipelineRunSummary(run_id="r", epoch_jd=2460000.0)
        with pytest.raises(Exception):
            prs.run_id = "changed"  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "PipelineRunSummary" in schemas.__all__

    def test_alert_pathways_tuple(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import PipelineRunSummary
        prs = PipelineRunSummary(
            run_id="r", epoch_jd=2460000.0,
            alert_pathways=("mpc_submission",),
        )
        assert isinstance(prs.alert_pathways, tuple)


class TestTrackletBatch:
    """Tests for TrackletBatch schema model."""

    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import TrackletBatch
        tb = TrackletBatch(batch_id="b1", run_id="r1", tracklets=("obj1", "obj2"))
        assert tb.batch_id == "b1"
        assert tb.run_id == "r1"
        assert tb.tracklets == ("obj1", "obj2")

    def test_default_n_tracklets(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import TrackletBatch
        tb = TrackletBatch(batch_id="b1", run_id="r1", tracklets=())
        assert tb.n_tracklets == 0

    def test_epoch_jd_none_by_default(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import TrackletBatch
        tb = TrackletBatch(batch_id="b1", run_id="r1", tracklets=())
        assert tb.epoch_jd is None

    def test_with_epoch_jd(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import TrackletBatch
        tb = TrackletBatch(
            batch_id="b1", run_id="r1", tracklets=("x",), n_tracklets=1, epoch_jd=2460000.0
        )
        assert tb.epoch_jd == 2460000.0
        assert tb.n_tracklets == 1

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import TrackletBatch
        tb = TrackletBatch(batch_id="b1", run_id="r1", tracklets=())
        with pytest.raises(Exception):
            tb.batch_id = "changed"  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "TrackletBatch" in schemas.__all__


class TestFieldObservation:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldObservation
        fo = FieldObservation(
            field_id="f1", ra_deg=45.0, dec_deg=-10.0, epoch_jd=2460000.0, survey="ZTF"
        )
        assert fo.field_id == "f1"
        assert fo.ra_deg == 45.0
        assert fo.survey == "ZTF"

    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldObservation
        fo = FieldObservation(
            field_id="f2", ra_deg=0.0, dec_deg=0.0, epoch_jd=2460001.0, survey="ATLAS"
        )
        assert fo.limiting_mag is None
        assert fo.n_sources == 0
        assert fo.filter_band is None

    def test_with_optional_fields(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldObservation
        fo = FieldObservation(
            field_id="f3", ra_deg=120.0, dec_deg=30.0, epoch_jd=2460002.0,
            survey="PanSTARRS", limiting_mag=22.5, n_sources=150, filter_band="g"
        )
        assert fo.limiting_mag == 22.5
        assert fo.n_sources == 150
        assert fo.filter_band == "g"

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import FieldObservation
        fo = FieldObservation(
            field_id="f4", ra_deg=0.0, dec_deg=0.0, epoch_jd=2460000.0, survey="ZTF"
        )
        with pytest.raises(Exception):
            fo.field_id = "changed"  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "FieldObservation" in schemas.__all__

    def test_epoch_jd_stored(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldObservation
        fo = FieldObservation(
            field_id="f5", ra_deg=200.0, dec_deg=-30.0, epoch_jd=2460999.5, survey="CSS"
        )
        assert fo.epoch_jd == 2460999.5


class TestScoringRun:
    def test_default_values(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ScoringRun
        run = ScoringRun(run_id="run-001")
        assert run.n_scored == 0
        assert run.n_pha == 0
        assert run.mean_priority == 0.0
        assert run.top_object_id is None
        assert run.epoch_jd is None

    def test_custom_values(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ScoringRun
        run = ScoringRun(
            run_id="run-002",
            n_scored=10,
            n_pha=2,
            mean_priority=0.75,
            top_object_id="NEO-001",
            epoch_jd=2460000.5,
        )
        assert run.n_scored == 10
        assert run.n_pha == 2
        assert run.mean_priority == 0.75
        assert run.top_object_id == "NEO-001"
        assert run.epoch_jd == 2460000.5

    def test_is_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import ScoringRun
        run = ScoringRun(run_id="run-003")
        with pytest.raises(Exception):
            run.n_scored = 5  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "ScoringRun" in schemas.__all__

    def test_run_id_stored(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ScoringRun
        run = ScoringRun(run_id="my-run-id")
        assert run.run_id == "my-run-id"

    def test_mean_priority_float(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ScoringRun
        run = ScoringRun(run_id="r", mean_priority=0.5)
        assert isinstance(run.mean_priority, float)


class TestAlertBatch:
    def test_default_values(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import AlertBatch

        batch = AlertBatch(batch_id="b1", run_id="r1")
        assert batch.n_alerts == 0
        assert batch.pathways == ()
        assert batch.epoch_jd is None
        assert "NOT" in batch.guardrail_statement

    def test_custom_values(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import AlertBatch

        batch = AlertBatch(
            batch_id="b2",
            run_id="r2",
            n_alerts=5,
            pathways=("mpc_submission", "neocp_followup"),
            epoch_jd=2460000.5,
        )
        assert batch.n_alerts == 5
        assert batch.pathways == ("mpc_submission", "neocp_followup")
        assert batch.epoch_jd == 2460000.5

    def test_is_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import AlertBatch

        batch = AlertBatch(batch_id="b3", run_id="r3")
        with pytest.raises(Exception):
            batch.n_alerts = 10  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas

        assert "AlertBatch" in schemas.__all__

    def test_guardrail_contains_not(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import AlertBatch

        batch = AlertBatch(batch_id="b4", run_id="r4")
        assert "NOT" in batch.guardrail_statement

    def test_batch_id_stored(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import AlertBatch

        batch = AlertBatch(batch_id="my-batch-id", run_id="my-run")
        assert batch.batch_id == "my-batch-id"
        assert batch.run_id == "my-run"


class TestObservationFilter:
    def test_default_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationFilter
        f = ObservationFilter()
        assert f.min_rb_score is None
        assert f.max_mag is None
        assert f.surveys == ()

    def test_with_values(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationFilter
        f = ObservationFilter(min_rb_score=0.65, max_mag=21.0, surveys=("ZTF",))
        assert f.min_rb_score == 0.65
        assert f.max_mag == 21.0
        assert "ZTF" in f.surveys

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import ObservationFilter
        f = ObservationFilter(min_rb_score=0.5)
        with pytest.raises(Exception):
            f.min_rb_score = 0.9  # type: ignore[misc]

    def test_filter_bands(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationFilter
        f = ObservationFilter(filter_bands=("g", "r"))
        assert "g" in f.filter_bands

    def test_jd_bounds(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import ObservationFilter
        f = ObservationFilter(min_jd=2460000.0, max_jd=2460010.0)
        assert f.min_jd == 2460000.0
        assert f.max_jd == 2460010.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "ObservationFilter" in schemas.__all__


class TestFieldStatistics:
    def test_basic_construction(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldStatistics
        fs = FieldStatistics(field_id="F001", n_sources=150, limiting_mag=21.5)
        assert fs.field_id == "F001"
        assert fs.n_sources == 150
        assert fs.limiting_mag == 21.5

    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldStatistics
        fs = FieldStatistics(field_id="F002", n_sources=0)
        assert fs.sky_area_sq_deg is None
        assert fs.epoch_jd is None
        assert fs.mission is None

    def test_all_fields(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import FieldStatistics
        fs = FieldStatistics(
            field_id="F003", n_sources=200, limiting_mag=22.0,
            sky_area_sq_deg=1.0, epoch_jd=2460000.5, mission="ZTF",
        )
        assert fs.mission == "ZTF"
        assert fs.sky_area_sq_deg == 1.0

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import FieldStatistics
        fs = FieldStatistics(field_id="F004", n_sources=10)
        with pytest.raises(Exception):
            fs.n_sources = 20  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "FieldStatistics" in schemas.__all__


class TestCandidateGrouping:
    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CandidateGrouping
        cg = CandidateGrouping(group_id="G001")
        assert cg.group_id == "G001"
        assert cg.field_id is None
        assert cg.night_jd is None
        assert cg.candidate_ids == ()
        assert cg.n_candidates == 0
        assert cg.dominant_hazard_flag == "unknown"

    def test_with_fields(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CandidateGrouping
        cg = CandidateGrouping(
            group_id="G002",
            field_id="F001",
            night_jd=2460000.5,
            candidate_ids=("A", "B"),
            n_candidates=2,
            dominant_hazard_flag="pha_candidate",
        )
        assert cg.field_id == "F001"
        assert cg.night_jd == 2460000.5
        assert cg.candidate_ids == ("A", "B")
        assert cg.n_candidates == 2
        assert cg.dominant_hazard_flag == "pha_candidate"

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import CandidateGrouping
        cg = CandidateGrouping(group_id="G003")
        with pytest.raises(Exception):
            cg.n_candidates = 5  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "CandidateGrouping" in schemas.__all__

    def test_candidate_ids_tuple(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import CandidateGrouping
        cg = CandidateGrouping(group_id="G004", candidate_ids=("X", "Y", "Z"))
        assert len(cg.candidate_ids) == 3
        assert "Z" in cg.candidate_ids


class TestMCPServerStatus:
    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import MCPServerStatus
        s = MCPServerStatus(server_name="neo-project_files")
        assert s.is_healthy is False
        assert s.tool_count == 0
        assert s.offline_mode is True

    def test_healthy(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import MCPServerStatus
        s = MCPServerStatus(server_name="neo-git_read", is_healthy=True, tool_count=5)
        assert s.is_healthy is True
        assert s.tool_count == 5

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import MCPServerStatus
        s = MCPServerStatus(server_name="test")
        with pytest.raises(Exception):
            s.is_healthy = True  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "MCPServerStatus" in schemas.__all__


class TestBatchProcessingResult:
    def test_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import BatchProcessingResult

        r = BatchProcessingResult(batch_id="run-001")
        assert r.batch_id == "run-001"
        assert r.n_input == 0
        assert r.n_pha_candidates == 0
        assert r.pipeline_version == "unknown"

    def test_custom_fields(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import BatchProcessingResult

        r = BatchProcessingResult(
            batch_id="test",
            n_input=100,
            n_detected=90,
            n_linked=70,
            n_scored=65,
            n_pha_candidates=2,
            elapsed_seconds=12.5,
            pipeline_version="0.79.0",
        )
        assert r.n_detected == 90
        assert r.elapsed_seconds == 12.5
        assert r.pipeline_version == "0.79.0"

    def test_frozen(self):
        import sys
        sys.path.insert(0, "src")
        import pytest

        from schemas import BatchProcessingResult

        r = BatchProcessingResult(batch_id="x")
        with pytest.raises(Exception):
            r.n_input = 5  # type: ignore[misc]

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import schemas
        assert "BatchProcessingResult" in schemas.__all__
