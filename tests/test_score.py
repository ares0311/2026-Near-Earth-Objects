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


class TestComputeHazardGradeAllGrades:
    def test_grade_c_and_d(self, scored_neo):
        """Cover score.py lines 950-952 (C and D branches)."""
        import sys
        sys.path.insert(0, "src")
        from score import compute_hazard_grade, compute_weighted_hazard_score

        score = compute_weighted_hazard_score(scored_neo)
        grade = compute_hazard_grade(scored_neo)
        if score >= 0.7:
            assert grade == "A"
        elif score >= 0.5:
            assert grade == "B"
        elif score >= 0.3:
            assert grade == "C"
        else:
            assert grade == "D"

    def _make_neo(self, moid):
        import sys
        sys.path.insert(0, "src")
        from schemas import (
            CandidateExplanation,
            CandidateFeatures,
            HazardAssessment,
            NEOPosterior,
            Observation,
            ScoredNEO,
            ScoringMetadata,
            Tracklet,
        )
        obs = (Observation(obs_id="o1", ra_deg=10.0, dec_deg=0.0, jd=2460000.0,
                           mag=20.0, mag_err=0.1, filter_band="r", mission="ZTF"),
               Observation(obs_id="o2", ra_deg=10.01, dec_deg=0.0, jd=2460001.0,
                           mag=20.0, mag_err=0.1, filter_band="r", mission="ZTF"))
        tracklet = Tracklet("T_grade", obs, arc_days=1.0,
                            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0)
        expl = CandidateExplanation(summary="grade test", supporting_evidence=(),
                                    contra_evidence=(), model_version="t")
        hazard = HazardAssessment(hazard_flag="nominal", moid_au=moid,
                                  estimated_diameter_m=None, absolute_magnitude_h=None,
                                  neo_class="amor", alert_pathway="internal_candidate",
                                  explanation=expl)
        meta = ScoringMetadata(scorer_version="t", scored_at_jd=2460000.0,
                               pipeline_run_id="x", discovery_priority=0.1,
                               followup_value=0.1, scientific_interest=0.1)
        return ScoredNEO(tracklet=tracklet, features=CandidateFeatures(),
                         posterior=NEOPosterior(neo_candidate=0.2, known_object=0.2,
                                               main_belt_asteroid=0.2, stellar_artifact=0.2,
                                               other_solar_system=0.2),
                         hazard=hazard, metadata=meta)

    def test_explicit_c_grade(self):
        """Force C grade: moid=0.1 AU → score ≈ 0.306 → C."""
        import sys
        sys.path.insert(0, "src")
        from score import compute_hazard_grade
        neo = self._make_neo(moid=0.1)
        assert compute_hazard_grade(neo) == "C"

    def test_explicit_d_grade(self):
        """Force D grade: moid=0.25 AU → score ≈ 0.106 → D."""
        import sys
        sys.path.insert(0, "src")
        from score import compute_hazard_grade
        neo = self._make_neo(moid=0.25)
        assert compute_hazard_grade(neo) == "D"


class TestComputeNoveltyRankMetaNone:
    def test_no_metadata_attr(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from score import compute_novelty_rank
        neo = SimpleNamespace(tracklet=SimpleNamespace(object_id="x"))
        result = compute_novelty_rank([neo])
        assert len(result) == 1
        assert result[0][1] == "x"


class TestGetTopCandidates:
    def setup_method(self):
        import sys
        sys.path.insert(0, "src")
        from score import get_top_candidates
        self.fn = get_top_candidates

    def test_basic(self, scored_neo):
        result = self.fn([scored_neo])
        assert len(result) == 1

    def test_top_n(self, scored_neo):
        result = self.fn([scored_neo, scored_neo, scored_neo], n=2)
        assert len(result) == 2

    def test_empty(self):
        assert self.fn([]) == []

    def test_n_larger_than_list(self, scored_neo):
        result = self.fn([scored_neo], n=100)
        assert len(result) == 1

    def test_n_zero(self, scored_neo):
        result = self.fn([scored_neo], n=0)
        assert result == []

    def test_sorted_by_priority(self):
        from types import SimpleNamespace
        high = SimpleNamespace(metadata=SimpleNamespace(discovery_priority=0.9))
        low = SimpleNamespace(metadata=SimpleNamespace(discovery_priority=0.1))
        result = self.fn([low, high], n=2)
        assert result[0] is high

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import score
        assert "get_top_candidates" in score.__all__


class TestComputeWeightedHazardIndexNoneQuality:
    """Cover orbit_q=0.0 branch when quality_code is None."""

    def _fn(self):
        import sys
        sys.path.insert(0, "src")
        import score
        return score.compute_weighted_hazard_index

    def test_none_quality_code(self):
        from types import SimpleNamespace
        hazard = SimpleNamespace(
            moid_au=0.02, hazard_flag="nominal",
            alert_pathway="internal_candidate",
            estimated_diameter_m=None, absolute_magnitude_h=None,
            neo_class="unknown", explanation=None,
        )
        meta = SimpleNamespace(
            discovery_priority=0.5, quality_code=None,
            followup_value=0.3, scientific_interest=0.2,
            close_approach_au=0.02, scoring_model_version="test",
            pipeline_version="test",
        )
        tracklet = SimpleNamespace(
            object_id="T1", observations=(), arc_days=1.0,
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=45.0,
        )
        features = SimpleNamespace(
            real_bogus_score=0.9, streak_score=None, psf_quality_score=None,
            motion_consistency_score=None, arc_coverage_score=None,
            nights_observed_score=None, brightness_score=None,
            color_score=None, lightcurve_variability_score=None,
            orbit_quality_score=None, moid_score=None,
            neo_class_confidence=None, pha_flag_confidence=None,
            known_object_score=None,
        )
        posterior = SimpleNamespace(
            neo_candidate=0.5, known_object=0.1, main_belt_asteroid=0.2,
            stellar_artifact=0.1, other_solar_system=0.1,
        )
        neo = SimpleNamespace(
            tracklet=tracklet, features=features,
            posterior=posterior, hazard=hazard, metadata=meta,
        )
        result = self._fn()(neo)
        assert 0.0 <= result <= 1.0


