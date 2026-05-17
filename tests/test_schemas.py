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
