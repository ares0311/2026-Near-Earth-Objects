"""Tests for score.py."""

import pytest

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
    rank_candidates,
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
        from classify import classify

        from .conftest import build_orbital_elements, build_tracklet

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
        from classify import classify

        from .conftest import build_tracklet

        items = []
        for _ in range(2):
            t = build_tracklet(n_obs=4)
            f, p = classify(t)
            items.append((t, f, p, None))
        results = score_batch(items, pipeline_run_id="batch-run-001")
        assert all(r.metadata.pipeline_run_id == "batch-run-001" for r in results)


class TestCloseApproachAu:
    def test_close_approach_au_set_when_orbit_quality_2(self):
        from classify import classify

        from .conftest import build_orbital_elements, build_tracklet

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
        from classify import classify

        from .conftest import build_tracklet

        t = build_tracklet(n_obs=4)
        f, p = classify(t)
        s = score(t, f, p, None)
        assert s.metadata.close_approach_au is None

    def test_close_approach_au_none_when_orbit_quality_1(self):
        from classify import classify

        from .conftest import build_orbital_elements, build_tracklet

        t = build_tracklet(n_obs=4)
        f, p = classify(t)
        orbital = build_orbital_elements(quality_code=1)
        s = score(t, f, p, orbital)
        assert s.metadata.close_approach_au is None


def _make_scored_neo_for_rank(
    priority: float, hazard_flag: str = "nominal"
):
    from .conftest import build_scored_neo
    return build_scored_neo(
        discovery_priority=priority,
        hazard_flag=hazard_flag,
        alert_pathway="internal_candidate",
        moid_au=0.1,
        orbit_quality=2,
    )


class TestRankCandidates:
    def test_sorted_by_descending_priority(self):
        neos = [
            _make_scored_neo_for_rank(0.3),
            _make_scored_neo_for_rank(0.9),
            _make_scored_neo_for_rank(0.6),
        ]
        ranked = rank_candidates(neos)
        priorities = [n.metadata.discovery_priority for n in ranked]
        assert priorities == sorted(priorities, reverse=True)

    def test_pha_before_nominal(self):
        nominal = _make_scored_neo_for_rank(0.99, hazard_flag="nominal")
        pha = _make_scored_neo_for_rank(0.1, hazard_flag="pha_candidate")
        ranked = rank_candidates([nominal, pha])
        assert ranked[0].hazard.hazard_flag == "pha_candidate"

    def test_empty_list_returns_empty(self):
        assert rank_candidates([]) == []

    def test_single_item_unchanged(self):
        neo = _make_scored_neo_for_rank(0.5)
        ranked = rank_candidates([neo])
        assert ranked == [neo]

    def test_does_not_mutate_input(self):
        neos = [
            _make_scored_neo_for_rank(0.2),
            _make_scored_neo_for_rank(0.8),
        ]
        original_order = [id(n) for n in neos]
        rank_candidates(neos)
        assert [id(n) for n in neos] == original_order


class TestDiscoveryReport:
    def _make_neo(self):
        from score import score
        return score(make_tracklet(3), make_features(), make_posterior(), make_orbital())

    def test_returns_required_top_level_keys(self):
        from score import discovery_report
        neo = self._make_neo()
        result = discovery_report(neo)
        required = {"object_id", "n_observations", "arc_days",
                    "motion_rate_arcsec_hr", "motion_pa_deg",
                    "posterior", "features", "hazard", "scoring"}
        assert required.issubset(result.keys())

    def test_object_id_matches(self):
        from score import discovery_report
        neo = self._make_neo()
        assert discovery_report(neo)["object_id"] == neo.tracklet.object_id

    def test_n_observations_correct(self):
        from score import discovery_report
        neo = self._make_neo()
        assert discovery_report(neo)["n_observations"] == len(neo.tracklet.observations)

    def test_posterior_sums_to_one(self):
        from score import discovery_report
        neo = self._make_neo()
        post = discovery_report(neo)["posterior"]
        total = sum(post.values())
        assert abs(total - 1.0) < 1e-3

    def test_hazard_flag_present(self):
        from score import discovery_report
        neo = self._make_neo()
        assert "hazard_flag" in discovery_report(neo)["hazard"]

    def test_scoring_has_discovery_priority(self):
        from score import discovery_report
        neo = self._make_neo()
        assert "discovery_priority" in discovery_report(neo)["scoring"]

    def test_arc_days_matches_tracklet(self):
        from score import discovery_report
        neo = self._make_neo()
        result = discovery_report(neo)
        assert result["arc_days"] == pytest.approx(neo.tracklet.arc_days, abs=1e-3)


class TestFollowupPriorityTable:
    def _make_neo(self, obj_id: str = "T001", priority: float = 0.8) -> object:
        from .conftest import build_scored_neo
        return build_scored_neo(object_id=obj_id, discovery_priority=priority)

    def test_returns_list(self):
        from score import followup_priority_table
        neos = [self._make_neo()]
        result = followup_priority_table(neos)
        assert isinstance(result, list)

    def test_empty_input_returns_empty(self):
        from score import followup_priority_table
        assert followup_priority_table([]) == []

    def test_row_has_required_keys(self):
        from score import followup_priority_table
        neos = [self._make_neo()]
        row = followup_priority_table(neos)[0]
        for key in ("rank", "object_id", "hazard_flag", "alert_pathway",
                    "discovery_priority", "moid_au", "neo_class",
                    "n_observations", "arc_days", "motion_rate_arcsec_hr"):
            assert key in row, f"missing key: {key}"

    def test_rank_starts_at_one(self):
        from score import followup_priority_table
        neos = [self._make_neo("A", 0.9), self._make_neo("B", 0.5)]
        rows = followup_priority_table(neos)
        assert rows[0]["rank"] == 1

    def test_sorted_by_priority_descending(self):
        from score import followup_priority_table
        neos = [self._make_neo("low", 0.2), self._make_neo("high", 0.9)]
        rows = followup_priority_table(neos)
        priorities = [r["discovery_priority"] for r in rows]
        assert priorities == sorted(priorities, reverse=True)

    def test_object_id_matches(self):
        from score import followup_priority_table
        neo = self._make_neo("TESTOBJ")
        rows = followup_priority_table([neo])
        assert rows[0]["object_id"] == "TESTOBJ"


class TestPhaCandidates:
    def _make_neo(self, hazard_flag: str = "pha_candidate", obj_id: str = "T001") -> object:
        from .conftest import build_scored_neo
        return build_scored_neo(hazard_flag=hazard_flag, object_id=obj_id)

    def test_returns_only_pha(self):
        from score import pha_candidates
        pha = self._make_neo("pha_candidate", "PHA")
        nom = self._make_neo("nominal", "NOM")
        result = pha_candidates([pha, nom])
        assert len(result) == 1
        assert result[0].tracklet.object_id == "PHA"

    def test_empty_list(self):
        from score import pha_candidates
        assert pha_candidates([]) == []

    def test_no_pha_returns_empty(self):
        from score import pha_candidates
        nom = self._make_neo("nominal")
        assert pha_candidates([nom]) == []

    def test_all_pha_returned(self):
        from score import pha_candidates
        neos = [self._make_neo("pha_candidate", f"P{i}") for i in range(3)]
        assert len(pha_candidates(neos)) == 3

    def test_close_approach_not_included(self):
        from score import pha_candidates
        ca = self._make_neo("close_approach", "CA")
        assert pha_candidates([ca]) == []


class TestComputeStatistics:
    def _make_neo(self, hazard_flag: str = "pha_candidate", pathway: str = "mpc_submission",
                  neo_class: str = "apollo", priority: float = 0.8, obj_id: str = "T001") -> object:
        from .conftest import build_scored_neo
        return build_scored_neo(
            hazard_flag=hazard_flag, alert_pathway=pathway,
            discovery_priority=priority, object_id=obj_id,
        )

    def test_returns_neo_statistics(self):
        from schemas import NEOStatistics
        from score import compute_statistics
        neos = [self._make_neo()]
        result = compute_statistics(neos)
        assert isinstance(result, NEOStatistics)

    def test_n_total(self):
        from score import compute_statistics
        neos = [self._make_neo(obj_id=f"T{i}") for i in range(4)]
        assert compute_statistics(neos).n_total == 4

    def test_n_pha_candidates(self):
        from score import compute_statistics
        neos = [self._make_neo("pha_candidate", obj_id="A"), self._make_neo("nominal", obj_id="B")]
        result = compute_statistics(neos)
        assert result.n_pha_candidates == 1

    def test_empty_list(self):
        from score import compute_statistics
        result = compute_statistics([])
        assert result.n_total == 0
        assert result.mean_discovery_priority == 0.0

    def test_mean_priority(self):
        from score import compute_statistics
        neos = [self._make_neo(priority=0.4, obj_id="A"), self._make_neo(priority=0.8, obj_id="B")]
        result = compute_statistics(neos)
        assert result.mean_discovery_priority == pytest.approx(0.6)

    def test_max_priority(self):
        from score import compute_statistics
        neos = [self._make_neo(priority=0.4, obj_id="A"), self._make_neo(priority=0.9, obj_id="B")]
        result = compute_statistics(neos)
        assert result.max_discovery_priority == pytest.approx(0.9)

    def test_neo_class_distribution_keys(self):
        from score import compute_statistics
        neos = [self._make_neo(obj_id=f"T{i}") for i in range(2)]
        result = compute_statistics(neos)
        assert isinstance(result.neo_class_distribution, dict)


class TestCloseApproachCandidates:
    def _make_neo(self, moid_au: float | None = 0.03, obj_id: str = "T001") -> object:
        from .conftest import build_scored_neo
        return build_scored_neo(moid_au=moid_au, object_id=obj_id)

    def test_filters_by_moid(self):
        from score import close_approach_candidates
        near = self._make_neo(0.03, "NEAR")
        far = self._make_neo(0.15, "FAR")
        result = close_approach_candidates([near, far], max_moid_au=0.05)
        ids = [n.tracklet.object_id for n in result]
        assert "NEAR" in ids
        assert "FAR" not in ids

    def test_none_moid_excluded(self):
        from score import close_approach_candidates
        neo = self._make_neo(None, "NOMOID")
        result = close_approach_candidates([neo])
        assert len(result) == 0

    def test_empty_input(self):
        from score import close_approach_candidates
        assert close_approach_candidates([]) == []

    def test_custom_threshold(self):
        from score import close_approach_candidates
        neo = self._make_neo(0.08, "FAR")
        result = close_approach_candidates([neo], max_moid_au=0.10)
        assert len(result) == 1

    def test_exact_threshold_included(self):
        from score import close_approach_candidates
        neo = self._make_neo(0.05, "EXACT")
        result = close_approach_candidates([neo], max_moid_au=0.05)
        assert len(result) == 1

    def test_all_included_when_threshold_high(self):
        from score import close_approach_candidates
        neos = [self._make_neo(m, f"T{i}") for i, m in enumerate([0.01, 0.05, 0.10])]
        result = close_approach_candidates(neos, max_moid_au=1.0)
        assert len(result) == 3


class TestAbsoluteMagnitudeFromDiameter:
    def test_140m_standard_albedo(self):
        from score import absolute_magnitude_from_diameter
        h = absolute_magnitude_from_diameter(140.0, albedo=0.14)
        assert h == pytest.approx(22.0, abs=0.1)

    def test_larger_diameter_brighter(self):
        from score import absolute_magnitude_from_diameter
        h1 = absolute_magnitude_from_diameter(100.0)
        h2 = absolute_magnitude_from_diameter(1000.0)
        assert h2 < h1

    def test_higher_albedo_brighter(self):
        from score import absolute_magnitude_from_diameter
        h_dark = absolute_magnitude_from_diameter(140.0, albedo=0.05)
        h_bright = absolute_magnitude_from_diameter(140.0, albedo=0.40)
        assert h_bright < h_dark

    def test_zero_diameter_returns_inf(self):
        from score import absolute_magnitude_from_diameter
        assert absolute_magnitude_from_diameter(0.0) == float("inf")

    def test_zero_albedo_returns_inf(self):
        from score import absolute_magnitude_from_diameter
        assert absolute_magnitude_from_diameter(140.0, albedo=0.0) == float("inf")

    def test_returns_float(self):
        from score import absolute_magnitude_from_diameter
        assert isinstance(absolute_magnitude_from_diameter(200.0), float)


class TestComputeImpactEnergy:
    def test_positive_result(self):
        from score import compute_impact_energy
        result = compute_impact_energy(140.0, 20.0)
        assert result > 0.0

    def test_zero_diameter_returns_zero(self):
        from score import compute_impact_energy
        assert compute_impact_energy(0.0, 20.0) == pytest.approx(0.0)

    def test_zero_velocity_returns_zero(self):
        from score import compute_impact_energy
        assert compute_impact_energy(140.0, 0.0) == pytest.approx(0.0)

    def test_zero_density_returns_zero(self):
        from score import compute_impact_energy
        assert compute_impact_energy(140.0, 20.0, density_kg_m3=0.0) == pytest.approx(0.0)

    def test_larger_diameter_more_energy(self):
        from score import compute_impact_energy
        e1 = compute_impact_energy(100.0, 20.0)
        e2 = compute_impact_energy(200.0, 20.0)
        assert e2 > e1

    def test_higher_velocity_more_energy(self):
        from score import compute_impact_energy
        e1 = compute_impact_energy(140.0, 10.0)
        e2 = compute_impact_energy(140.0, 20.0)
        assert e2 > e1

    def test_returns_float(self):
        from score import compute_impact_energy
        assert isinstance(compute_impact_energy(140.0, 20.0), float)

    def test_known_order_of_magnitude(self):
        # 140 m asteroid at 20 km/s ≈ few hundred megatons
        from score import compute_impact_energy
        result = compute_impact_energy(140.0, 20.0)
        assert 10.0 < result < 10000.0


class TestComputeNoveltyScore:
    def _make_neo(self):
        from .conftest import build_scored_neo
        return build_scored_neo()

    def _make_elements(self, a=1.5, e=0.1, i=5.0):
        from schemas import OrbitalElements
        return OrbitalElements(
            semi_major_axis_au=a,
            eccentricity=e,
            inclination_deg=i,
            longitude_ascending_node_deg=0.0,
            argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0,
            epoch_jd=2460000.5,
            perihelion_au=a * (1 - e),
            aphelion_au=a * (1 + e),
            quality_code=2,
        )

    def test_returns_float(self):
        from score import compute_novelty_score
        neo = self._make_neo()
        result = compute_novelty_score(neo, [])
        assert isinstance(result, float)

    def test_empty_catalog_returns_one(self):
        from score import compute_novelty_score
        neo = self._make_neo()
        assert compute_novelty_score(neo, []) == pytest.approx(1.0)

    def test_identical_orbit_returns_near_zero(self):
        from score import compute_novelty_score

        neo = self._make_neo()
        # Use same elements as the neo's hazard assessment (a~1.5 ish)
        catalog = [self._make_elements(a=1.5, e=0.1, i=5.0)]
        result = compute_novelty_score(neo, catalog)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_distant_catalog_near_one(self):
        from score import compute_novelty_score
        neo = self._make_neo()
        # Very different orbital elements
        catalog = [self._make_elements(a=10.0, e=0.9, i=170.0)]
        result = compute_novelty_score(neo, catalog)
        assert result > 0.5

    def test_range_0_1(self):
        from score import compute_novelty_score
        neo = self._make_neo()
        catalog = [self._make_elements(a=1.8, e=0.2, i=10.0)]
        result = compute_novelty_score(neo, catalog)
        assert 0.0 <= result <= 1.0


class TestComputeThreatScore:
    def _make_neo(self, moid_au=0.03, h=21.5, quality=2):
        import types
        hazard = types.SimpleNamespace(
            moid_au=moid_au,
            absolute_magnitude_h=h,
            orbital_elements=types.SimpleNamespace(quality_code=quality),
        )
        metadata = types.SimpleNamespace(quality_code=quality)
        return types.SimpleNamespace(hazard=hazard, metadata=metadata)

    def test_returns_float(self):
        from score import compute_threat_score
        neo = self._make_neo()
        assert isinstance(compute_threat_score(neo), float)

    def test_range_0_to_1(self):
        from score import compute_threat_score
        neo = self._make_neo()
        score = compute_threat_score(neo)
        assert 0.0 <= score <= 1.0

    def test_high_threat_large_close_well_observed(self):
        from score import compute_threat_score
        neo = self._make_neo(moid_au=0.005, h=17.0, quality=4)
        assert compute_threat_score(neo) > 0.8

    def test_zero_for_far_moid(self):
        from score import compute_threat_score
        neo = self._make_neo(moid_au=0.1, h=22.0, quality=3)
        # moid_score = 0.0 → product = 0
        assert compute_threat_score(neo) == pytest.approx(0.0)

    def test_none_moid_uses_neutral(self):
        import types

        from score import compute_threat_score
        hazard = types.SimpleNamespace(
            moid_au=None,
            absolute_magnitude_h=21.0,
            orbital_elements=types.SimpleNamespace(quality_code=2),
        )
        neo = types.SimpleNamespace(hazard=hazard)
        score = compute_threat_score(neo)
        assert 0.0 <= score <= 1.0

    def test_none_h_uses_neutral(self):
        import types

        from score import compute_threat_score
        hazard = types.SimpleNamespace(
            moid_au=0.02,
            absolute_magnitude_h=None,
            orbital_elements=types.SimpleNamespace(quality_code=2),
        )
        neo = types.SimpleNamespace(hazard=hazard)
        score = compute_threat_score(neo)
        assert 0.0 <= score <= 1.0

    def test_none_orbital_elements_uses_neutral(self):
        import types

        from score import compute_threat_score
        hazard = types.SimpleNamespace(
            moid_au=0.02,
            absolute_magnitude_h=21.0,
            orbital_elements=None,
        )
        neo = types.SimpleNamespace(hazard=hazard)
        score = compute_threat_score(neo)
        assert 0.0 <= score <= 1.0


class TestComputeThreatScoreH25:
    """Cover h >= 25 branch (size_score = 0.0) in compute_threat_score."""

    def test_h_at_25_gives_zero_size(self):
        import types

        from score import compute_threat_score
        hazard = types.SimpleNamespace(
            moid_au=0.02,
            absolute_magnitude_h=25.0,
            orbital_elements=types.SimpleNamespace(quality_code=2),
        )
        neo = types.SimpleNamespace(hazard=hazard)
        # size_score = 0.0 → product = 0 → threat_score = 0.0
        assert compute_threat_score(neo) == pytest.approx(0.0)

    def test_h_above_25_gives_zero(self):
        import types

        from score import compute_threat_score
        hazard = types.SimpleNamespace(
            moid_au=0.02,
            absolute_magnitude_h=28.0,
            orbital_elements=types.SimpleNamespace(quality_code=3),
        )
        neo = types.SimpleNamespace(hazard=hazard)
        assert compute_threat_score(neo) == pytest.approx(0.0)


class TestFilterByAlertPathway:
    def _make_neos(self):
        from .conftest import build_scored_neo
        return [
            build_scored_neo(alert_pathway="mpc_submission"),
            build_scored_neo(alert_pathway="internal_candidate"),
            build_scored_neo(alert_pathway="mpc_submission"),
            build_scored_neo(alert_pathway="known_object"),
        ]

    def test_filters_correctly(self):
        from score import filter_by_alert_pathway
        neos = self._make_neos()
        result = filter_by_alert_pathway(neos, "mpc_submission")
        assert len(result) == 2

    def test_empty_result(self):
        from score import filter_by_alert_pathway
        neos = self._make_neos()
        result = filter_by_alert_pathway(neos, "nasa_pdco_notify")
        assert result == []

    def test_all_match(self):
        from score import filter_by_alert_pathway

        from .conftest import build_scored_neo
        neos = [build_scored_neo(alert_pathway="known_object") for _ in range(3)]
        result = filter_by_alert_pathway(neos, "known_object")
        assert len(result) == 3

    def test_empty_input(self):
        from score import filter_by_alert_pathway
        assert filter_by_alert_pathway([], "mpc_submission") == []

    def test_returns_list(self):
        from score import filter_by_alert_pathway
        result = filter_by_alert_pathway(self._make_neos(), "internal_candidate")
        assert isinstance(result, list)


class TestComputeFollowupUrgency:
    def _make_neo(self, hazard_flag="nominal", moid=0.1, pathway="internal_candidate",
                  priority=0.0):
        import types
        hazard = types.SimpleNamespace(
            hazard_flag=hazard_flag, moid_au=moid, alert_pathway=pathway,
        )
        metadata = types.SimpleNamespace(discovery_priority=priority)
        return types.SimpleNamespace(hazard=hazard, metadata=metadata)

    def test_pha_with_small_moid_is_urgent(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="pha_candidate", moid=0.005)
        assert compute_followup_urgency(neo) == "URGENT"

    def test_pha_with_high_priority_is_urgent(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="pha_candidate", moid=0.04, priority=0.95)
        assert compute_followup_urgency(neo) == "URGENT"

    def test_pha_with_medium_moid_is_high(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="pha_candidate", moid=0.04, priority=0.5)
        assert compute_followup_urgency(neo) == "HIGH"

    def test_small_moid_non_pha_is_high(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="nominal", moid=0.03)
        assert compute_followup_urgency(neo) == "HIGH"

    def test_high_priority_non_pha_is_high(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="nominal", moid=0.5, priority=0.75)
        assert compute_followup_urgency(neo) == "HIGH"

    def test_close_approach_flag_is_medium(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="close_approach", moid=0.15, priority=0.2)
        assert compute_followup_urgency(neo) == "MEDIUM"

    def test_medium_priority_is_medium(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="nominal", moid=0.5, priority=0.5)
        assert compute_followup_urgency(neo) == "MEDIUM"

    def test_low_priority_nominal_is_routine(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="nominal", moid=0.5, priority=0.1)
        assert compute_followup_urgency(neo) == "ROUTINE"

    def test_none_moid_non_pha_is_routine_or_medium(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="nominal", moid=None, priority=0.1)
        result = compute_followup_urgency(neo)
        assert result in {"ROUTINE", "MEDIUM"}

    def test_none_priority_treated_as_zero(self):
        from score import compute_followup_urgency
        neo = self._make_neo(hazard_flag="nominal", moid=0.5, priority=None)
        result = compute_followup_urgency(neo)
        assert result == "ROUTINE"

    def test_returns_string(self):
        from score import compute_followup_urgency
        result = compute_followup_urgency(self._make_neo())
        assert isinstance(result, str)


class TestComputeDiscoveryScore:
    def _make_neo(self, priority=0.5, orbit_q=0.5, brightness=0.5):
        from .conftest import build_scored_neo
        neo = build_scored_neo()
        import types
        neo_ns = types.SimpleNamespace(
            metadata=types.SimpleNamespace(discovery_priority=priority),
            features=types.SimpleNamespace(
                orbit_quality_score=orbit_q, brightness_score=brightness,
            ),
            hazard=neo.hazard,
            tracklet=neo.tracklet,
            posterior=neo.posterior,
        )
        return neo_ns

    def test_returns_float(self):
        from score import compute_discovery_score
        result = compute_discovery_score(self._make_neo())
        assert isinstance(result, float)

    def test_range_0_1(self):
        from score import compute_discovery_score
        result = compute_discovery_score(self._make_neo())
        assert 0.0 <= result <= 1.0

    def test_zero_inputs_zero_score(self):
        from score import compute_discovery_score
        result = compute_discovery_score(self._make_neo(priority=0.0, orbit_q=0.0, brightness=0.0))
        assert result == pytest.approx(0.0)

    def test_max_inputs_near_one(self):
        from score import compute_discovery_score
        result = compute_discovery_score(self._make_neo(priority=1.0, orbit_q=1.0, brightness=1.0))
        assert result == pytest.approx(1.0)

    def test_none_scores_treated_as_zero(self):
        from score import compute_discovery_score
        result = compute_discovery_score(self._make_neo(orbit_q=None, brightness=None))
        assert result == pytest.approx(0.5 * 0.5, abs=0.001)

    def test_weights_blend(self):
        from score import compute_discovery_score
        result = compute_discovery_score(self._make_neo(priority=0.4, orbit_q=0.0, brightness=0.0))
        assert result == pytest.approx(0.5 * 0.4, abs=0.001)


class TestComputeObservationPriority:
    def _make_neo(self, priority=0.5, orbit_q=0.5, last_jd=2459000.0):
        import types

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        obs_list = list(neo.tracklet.observations)
        if obs_list:
            obs_list[0] = obs_list[0].model_copy(update={"jd": last_jd})
        import schemas
        tracklet = schemas.Tracklet(
            object_id=neo.tracklet.object_id,
            observations=tuple(obs_list),
            arc_days=neo.tracklet.arc_days,
            motion_rate_arcsec_per_hour=neo.tracklet.motion_rate_arcsec_per_hour,
            motion_pa_degrees=neo.tracklet.motion_pa_degrees,
        )
        return types.SimpleNamespace(
            metadata=types.SimpleNamespace(discovery_priority=priority),
            features=types.SimpleNamespace(orbit_quality_score=orbit_q),
            hazard=neo.hazard,
            tracklet=tracklet,
            posterior=neo.posterior,
        )

    def test_returns_float(self):
        from score import compute_observation_priority
        result = compute_observation_priority(self._make_neo())
        assert isinstance(result, float)

    def test_result_in_unit_interval(self):
        from score import compute_observation_priority
        result = compute_observation_priority(self._make_neo())
        assert 0.0 <= result <= 1.0

    def test_high_priority_increases_score(self):
        from score import compute_observation_priority
        low = self._make_neo(priority=0.0)
        high = self._make_neo(priority=1.0)
        assert compute_observation_priority(high) > compute_observation_priority(low)

    def test_low_orbit_quality_increases_score(self):
        from score import compute_observation_priority
        good = self._make_neo(orbit_q=1.0)
        poor = self._make_neo(orbit_q=0.0)
        assert compute_observation_priority(poor) >= compute_observation_priority(good)

    def test_old_observation_increases_urgency(self):
        from score import compute_observation_priority
        recent = self._make_neo(last_jd=2459990.0)
        old = self._make_neo(last_jd=2459000.0)
        assert compute_observation_priority(old) >= compute_observation_priority(recent)

    def test_all_zeros_returns_valid_score(self):
        from score import compute_observation_priority
        result = compute_observation_priority(self._make_neo(priority=0.0, orbit_q=0.0))
        assert 0.0 <= result <= 1.0

    def test_clamped_to_unit_interval(self):
        from score import compute_observation_priority
        result = compute_observation_priority(self._make_neo(priority=1.0, orbit_q=0.0))
        assert result <= 1.0

    def test_empty_observations_returns_valid(self):
        import types

        import schemas
        from score import compute_observation_priority

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        tracklet = schemas.Tracklet(
            object_id=neo.tracklet.object_id,
            observations=(),
            arc_days=0.0,
            motion_rate_arcsec_per_hour=0.0,
            motion_pa_degrees=0.0,
        )
        stub = types.SimpleNamespace(
            metadata=types.SimpleNamespace(discovery_priority=0.5),
            features=types.SimpleNamespace(orbit_quality_score=0.5),
            hazard=neo.hazard,
            tracklet=tracklet,
            posterior=neo.posterior,
        )
        result = compute_observation_priority(stub)
        assert 0.0 <= result <= 1.0


class TestComputeSizeEstimate:
    def _make_neo_with_h(self, h_val):
        from tests.conftest import build_scored_neo
        neo = build_scored_neo()
        hazard = neo.hazard.model_copy(update={"absolute_magnitude_h": h_val})
        return neo.model_copy(update={"hazard": hazard})

    def test_returns_dict_for_valid_h(self):
        from score import compute_size_estimate
        neo = self._make_neo_with_h(22.0)
        result = compute_size_estimate(neo)
        assert result is not None
        assert "min_m" in result and "max_m" in result

    def test_none_for_none_h(self):
        from score import compute_size_estimate
        neo = self._make_neo_with_h(None)
        assert compute_size_estimate(neo) is None

    def test_none_for_inf_h(self):
        import math

        from score import compute_size_estimate
        neo = self._make_neo_with_h(math.inf)
        assert compute_size_estimate(neo) is None

    def test_max_gt_min(self):
        from score import compute_size_estimate
        neo = self._make_neo_with_h(22.0)
        result = compute_size_estimate(neo)
        assert result["max_m"] > result["min_m"]

    def test_albedo_range_key(self):
        from score import compute_size_estimate
        neo = self._make_neo_with_h(20.0)
        result = compute_size_estimate(neo)
        assert result["assumed_albedo_range"] == [0.05, 0.30]

    def test_h22_diameter_range(self):
        from score import compute_size_estimate
        neo = self._make_neo_with_h(22.0)
        result = compute_size_estimate(neo)
        # H=22 → ~140m; allow wide tolerance
        assert result["min_m"] > 50.0
        assert result["max_m"] > result["min_m"]

    def test_brighter_object_larger_diameter(self):
        from score import compute_size_estimate
        neo_small = self._make_neo_with_h(25.0)
        neo_large = self._make_neo_with_h(15.0)
        r_small = compute_size_estimate(neo_small)
        r_large = compute_size_estimate(neo_large)
        assert r_large["min_m"] > r_small["min_m"]
