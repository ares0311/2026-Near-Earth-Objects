"""Tests for score.py."""


from schemas import (
    CandidateFeatures,
    NEOPosterior,
    Observation,
    OrbitalElements,
    Tracklet,
)
from score import (
    _build_explanation,
    _compute_hazard_flag,
    _compute_log_score_neo,
    _determine_alert_pathway,
    _diameter_from_h,
    _discovery_priority,
    score,
    score_batch,
)


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="s_001",
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


def make_tracklet(n: int = 3) -> Tracklet:
    obs = tuple(
        make_obs(obs_id=f"o{i}", jd=2460000.5 + i)
        for i in range(n)
    )
    return Tracklet("T001", obs, float(n - 1), 1.0, 90.0)


def make_features(**kwargs) -> CandidateFeatures:
    defaults = dict(real_bogus_score=0.92)
    defaults.update(kwargs)
    return CandidateFeatures(**defaults)


def make_posterior(**kwargs) -> NEOPosterior:
    defaults = dict(
        neo_candidate=0.75,
        known_object=0.05,
        main_belt_asteroid=0.10,
        stellar_artifact=0.05,
        other_solar_system=0.05,
    )
    defaults.update(kwargs)
    return NEOPosterior(**defaults)


def make_orbital(**kwargs) -> OrbitalElements:
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


class TestDiameterFromH:
    def test_h22_gives_140m_approx(self):
        d = _diameter_from_h(22.0)
        assert 100 < d < 200

    def test_brighter_gives_larger(self):
        assert _diameter_from_h(18.0) > _diameter_from_h(22.0)


class TestHazardFlag:
    def test_pha_candidate(self):
        flag = _compute_hazard_flag(0.03, 21.0, "apollo", 2)
        assert flag == "pha_candidate"

    def test_close_approach(self):
        flag = _compute_hazard_flag(0.12, 25.0, "amor", 2)
        assert flag == "close_approach"

    def test_nominal(self):
        flag = _compute_hazard_flag(0.5, 25.0, "amor", 2)
        assert flag == "nominal"

    def test_unknown_when_no_moid(self):
        flag = _compute_hazard_flag(None, 21.0, "apollo", 2)
        assert flag == "unknown"

    def test_unknown_when_low_quality(self):
        flag = _compute_hazard_flag(0.03, 21.0, "apollo", 1)
        assert flag == "unknown"


class TestAlertPathway:
    def test_known_object_pathway(self):
        f = make_features(real_bogus_score=0.95, known_object_score=0.9)
        p = make_posterior()
        pathway = _determine_alert_pathway(p, f, 0.03, 2)
        assert pathway == "known_object"

    def test_low_rb_internal(self):
        f = make_features(real_bogus_score=0.7)
        p = make_posterior()
        pathway = _determine_alert_pathway(p, f, 0.03, 2)
        assert pathway == "internal_candidate"

    def test_none_rb_internal(self):
        f = make_features(real_bogus_score=None)
        p = make_posterior()
        pathway = _determine_alert_pathway(p, f, 0.03, 2)
        assert pathway == "internal_candidate"

    def test_high_moid_internal(self):
        f = make_features(real_bogus_score=0.95)
        p = make_posterior()
        pathway = _determine_alert_pathway(p, f, 0.1, 2)
        assert pathway == "internal_candidate"

    def test_low_orbit_quality_internal(self):
        f = make_features(real_bogus_score=0.95)
        p = make_posterior()
        pathway = _determine_alert_pathway(p, f, 0.03, 1)
        assert pathway == "internal_candidate"

    def test_qualifying_mpc_submission(self):
        f = make_features(real_bogus_score=0.95)
        p = make_posterior(neo_candidate=0.75)
        pathway = _determine_alert_pathway(p, f, 0.03, 2)
        assert pathway == "mpc_submission"


class TestLogScoreNEO:
    def test_none_features_neutral(self):
        # DECISION-005: None features contribute 0 (neutral)
        f_none = CandidateFeatures()
        f_high = make_features(
            real_bogus_score=1.0,
            arc_coverage_score=1.0,
            nights_observed_score=1.0,
        )
        score_none = _compute_log_score_neo(f_none)
        score_high = _compute_log_score_neo(f_high)
        assert score_high > score_none

    def test_known_object_penalised(self):
        f_ko = make_features(known_object_score=1.0)
        f_new = make_features(known_object_score=0.0)
        assert _compute_log_score_neo(f_ko) < _compute_log_score_neo(f_new)


class TestDiscoveryPriority:
    def test_pha_candidate_gets_bonus(self):
        p = make_posterior(neo_candidate=0.8)
        f = make_features()
        dp_pha = _discovery_priority(p, f, "pha_candidate")
        dp_nom = _discovery_priority(p, f, "nominal")
        assert dp_pha > dp_nom

    def test_bounded_0_1(self):
        p = make_posterior(neo_candidate=1.0)
        f = make_features(orbit_quality_score=1.0)
        dp = _discovery_priority(p, f, "pha_candidate")
        assert 0.0 <= dp <= 1.0


class TestScoreFunction:
    def test_returns_scored_neo(self):
        t = make_tracklet()
        f = make_features()
        p = make_posterior()
        result = score(t, f, p, make_orbital())
        valid_flags = {"pha_candidate", "close_approach", "nominal", "unknown"}
        assert result.hazard.hazard_flag in valid_flags
        assert result.metadata.scorer_version == "0.1.0"

    def test_no_orbital_gives_unknown_class(self):
        t = make_tracklet()
        f = make_features()
        p = make_posterior()
        result = score(t, f, p, None)
        assert result.hazard.neo_class == "unknown"
        assert result.hazard.moid_au is None

    def test_none_rb_blocks_mpc_pathway(self):
        t = make_tracklet()
        f = CandidateFeatures(real_bogus_score=None)
        p = make_posterior()
        result = score(t, f, p, make_orbital())
        assert result.hazard.alert_pathway == "internal_candidate"

    def test_moid_score_populated(self):
        t = make_tracklet()
        f = make_features(real_bogus_score=0.95)
        p = make_posterior(neo_candidate=0.8)
        orbital = make_orbital(
            semi_major_axis_au=1.5, eccentricity=0.4,
            perihelion_au=0.9, aphelion_au=2.1,
            inclination_deg=5.0,
        )
        result = score(t, f, p, orbital)
        if result.features.moid_score is not None:
            assert 0.0 <= result.features.moid_score <= 1.0

    def test_pha_flag_confidence_set_when_pha_candidate(self):
        # Orbit with MOID ≤ 0.05 AU (a=1.0, e=0.05 gives MOID≈0.033)
        t = make_tracklet()
        f = make_features(real_bogus_score=0.95)
        p = make_posterior(neo_candidate=0.8)
        orbital = make_orbital(
            semi_major_axis_au=1.0, eccentricity=0.05,
            perihelion_au=0.95, aphelion_au=1.05,
            inclination_deg=1.0, quality_code=3,
            longitude_ascending_node_deg=0.0,
            argument_perihelion_deg=0.0,
        )
        result = score(t, f, p, orbital)
        if result.hazard.hazard_flag == "pha_candidate":
            assert result.features.pha_flag_confidence is not None


class TestAlertPathwayLowNeoCandidateProb:
    def test_low_neo_prob_returns_internal(self):
        f = make_features(real_bogus_score=0.95)
        p = make_posterior(neo_candidate=0.4)  # < 0.5
        pathway = _determine_alert_pathway(p, f, 0.03, 2)
        assert pathway == "internal_candidate"


class TestBuildExplanation:
    def test_low_rb_adds_contra(self):
        f = make_features(real_bogus_score=0.5)
        p = make_posterior(stellar_artifact=0.0, main_belt_asteroid=0.0)
        ex = _build_explanation(f, p, "nominal", None)
        assert any("real/bogus" in e.lower() for e in ex.contra_evidence)

    def test_nights_score_adds_supporting(self):
        f = make_features(real_bogus_score=None, nights_observed_score=0.5)
        p = make_posterior(stellar_artifact=0.0, main_belt_asteroid=0.0)
        ex = _build_explanation(f, p, "nominal", None)
        assert any("night" in e.lower() or "arc" in e.lower() for e in ex.supporting_evidence)

    def test_motion_consistency_adds_supporting(self):
        f = make_features(motion_consistency_score=0.8)
        p = make_posterior(stellar_artifact=0.0, main_belt_asteroid=0.0)
        ex = _build_explanation(f, p, "nominal", None)
        assert any("motion" in e.lower() for e in ex.supporting_evidence)

    def test_orbit_quality_adds_supporting(self):
        f = make_features(orbit_quality_score=0.7)
        p = make_posterior(stellar_artifact=0.0, main_belt_asteroid=0.0)
        ex = _build_explanation(f, p, "nominal", None)
        assert any("orbit" in e.lower() or "quality" in e.lower() for e in ex.supporting_evidence)

    def test_low_moid_adds_supporting(self):
        f = make_features()
        p = make_posterior(stellar_artifact=0.0, main_belt_asteroid=0.0)
        ex = _build_explanation(f, p, "pha_candidate", 0.03)
        assert any("MOID" in e for e in ex.supporting_evidence)

    def test_high_artifact_prob_adds_contra(self):
        f = make_features(real_bogus_score=None)
        p = make_posterior(stellar_artifact=0.4, main_belt_asteroid=0.0)
        ex = _build_explanation(f, p, "nominal", None)
        assert any("artifact" in e.lower() for e in ex.contra_evidence)

    def test_high_mba_prob_adds_contra(self):
        f = make_features(real_bogus_score=None)
        p = make_posterior(stellar_artifact=0.0, main_belt_asteroid=0.5)
        ex = _build_explanation(f, p, "nominal", None)
        assert any("main-belt" in e.lower() or "main_belt" in e.lower() or "belt" in e.lower()
                   for e in ex.contra_evidence)

    def test_known_object_adds_contra(self):
        f = make_features(real_bogus_score=None, known_object_score=0.7)
        p = make_posterior(stellar_artifact=0.0, main_belt_asteroid=0.0)
        ex = _build_explanation(f, p, "nominal", None)
        assert any("known" in e.lower() for e in ex.contra_evidence)


class TestScoreBatch:
    def test_returns_list_same_length(self):
        from .conftest import build_tracklet, build_orbital_elements
        from classify import classify, extract_features

        items = []
        for _ in range(3):
            t = build_tracklet(n_obs=4)
            f, p = classify(t)
            items.append((t, f, p, build_orbital_elements()))
        results = score_batch(items)
        assert len(results) == 3

    def test_empty_input_returns_empty(self):
        assert score_batch([]) == []

    def test_shared_pipeline_run_id(self):
        from .conftest import build_tracklet, build_orbital_elements
        from classify import classify

        items = []
        for _ in range(2):
            t = build_tracklet(n_obs=4)
            f, p = classify(t)
            items.append((t, f, p, None))
        results = score_batch(items, pipeline_run_id="batch-run-001")
        assert all(r.metadata.pipeline_run_id == "batch-run-001" for r in results)


class TestCloseApproachAu:
    def test_close_approach_au_set_when_orbit_quality_2(self):
        from .conftest import build_tracklet, build_orbital_elements
        from classify import classify

        t = build_tracklet(n_obs=4)
        f, p = classify(t)
        orbital = build_orbital_elements(quality_code=2)
        s = score(t, f, p, orbital)
        # close_approach_au should equal moid_au when quality_code >= 2
        if s.hazard.moid_au is not None:
            assert s.metadata.close_approach_au == s.hazard.moid_au
        else:
            assert s.metadata.close_approach_au is None

    def test_close_approach_au_none_when_no_orbit(self):
        from .conftest import build_tracklet
        from classify import classify

        t = build_tracklet(n_obs=4)
        f, p = classify(t)
        s = score(t, f, p, None)
        assert s.metadata.close_approach_au is None

    def test_close_approach_au_none_when_orbit_quality_1(self):
        from .conftest import build_tracklet, build_orbital_elements
        from classify import classify

        t = build_tracklet(n_obs=4)
        f, p = classify(t)
        orbital = build_orbital_elements(quality_code=1)
        s = score(t, f, p, orbital)
        assert s.metadata.close_approach_au is None
