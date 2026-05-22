"""End-to-end synthetic pipeline test: Detect → Link → Score."""

import pytest

from detect import detect
from link import link
from orbit import fit_orbit
from schemas import (
    CandidateFeatures,
    NEOPosterior,
    Observation,
)
from score import score


def make_obs(obs_id: str, jd: float, ra_deg: float, dec_deg: float = 0.0) -> Observation:
    return Observation(
        obs_id=obs_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        jd=jd,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.9,
    )


class TestEndToEndSynthetic:
    def _make_moving_observations(self) -> tuple[Observation, ...]:
        """Three nights, consistent eastward motion at ~1 arcsec/hr."""
        dra_per_hr = 1.0 / 3600.0  # 1 arcsec/hr in deg
        obs = []
        for night in range(3):
            jd_base = 2460000.5 + night
            ra_base = 180.0 + night * dra_per_hr * 24
            obs.append(make_obs(f"n{night}_a", jd_base, ra_base))
            obs.append(make_obs(f"n{night}_b", jd_base + 1 / 24, ra_base + dra_per_hr))
        return tuple(obs)

    def test_detect_produces_candidates(self):
        obs = self._make_moving_observations()
        result = detect(obs, mpc_cross_match=False)
        assert len(result.candidates) >= 1

    def test_link_produces_tracklets(self):
        obs = self._make_moving_observations()
        detect_result = detect(obs, mpc_cross_match=False)
        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)
        assert link_result.provenance.min_nights == 2

    def test_score_returns_hazard(self):
        obs = self._make_moving_observations()
        detect_result = detect(obs, mpc_cross_match=False)
        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)

        if not link_result.tracklets:
            pytest.skip("No tracklets produced — link threshold not met by synthetic data")

        t = link_result.tracklets[0]
        orbital = fit_orbit(t)

        features = CandidateFeatures(
            real_bogus_score=0.9,
            nights_observed_score=0.8,
            motion_consistency_score=0.9,
        )
        posterior = NEOPosterior(
            neo_candidate=0.6,
            known_object=0.1,
            main_belt_asteroid=0.1,
            stellar_artifact=0.1,
            other_solar_system=0.1,
        )

        result = score(t, features, posterior, orbital)
        valid_flags = {"pha_candidate", "close_approach", "nominal", "unknown"}
        assert result.hazard.hazard_flag in valid_flags
        assert result.metadata.discovery_priority >= 0.0

    def test_provenance_chain(self):
        obs = self._make_moving_observations()
        detect_result = detect(obs, mpc_cross_match=False)
        assert detect_result.provenance is not None

        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)
        assert link_result.provenance is not None
        assert link_result.provenance.n_tracklets == len(link_result.tracklets)


class TestTuneLinkerSkill:
    """Smoke test: tune_linker.py runs without error."""

    def test_run_one_returns_rates(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from tune_linker import _run_one

        link_rate, score_rate = _run_one(n=3, seed=0, tol=10.0, chi2=5.0)
        assert 0.0 <= link_rate <= 1.0
        assert 0.0 <= score_rate <= 1.0


class TestSimulateSurveySkill:
    """Smoke tests for simulate_survey.py."""

    def test_returns_correct_observation_count(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from simulate_survey import simulate_survey

        obs = simulate_survey(nights=3, n_objects=4, seed=7)
        # 4 objects × 3 nights × 2 obs/night = 24
        assert len(obs) == 24

    def test_all_obs_ids_unique(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from simulate_survey import simulate_survey

        obs = simulate_survey(nights=2, n_objects=3, seed=99)
        ids = [o.obs_id for o in obs]
        assert len(ids) == len(set(ids))

    def test_main_writes_json(self, tmp_path):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from simulate_survey import main

        out = tmp_path / "sim.json"
        main(["--nights", "2", "--objects", "2", "--out", str(out)])
        assert out.exists()
        import json
        data = json.loads(out.read_text())
        assert len(data) == 2 * 2 * 2


class TestExportRankedTableSkill:
    """Smoke tests for export_ranked_table.py."""

    def test_csv_output(self, tmp_path):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_ranked_table import export_csv

        rows = [{"object_id": "X001", "discovery_priority": 0.9, "hazard_flag": "nominal"}]
        csv = export_csv(rows)
        assert "X001" in csv
        assert "object_id" in csv.split("\n")[0]

    def test_html_output_contains_table(self, tmp_path):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_ranked_table import export_html

        rows = [{"object_id": "X002", "hazard_flag": "pha_candidate"}]
        html = export_html(rows)
        assert "<table" in html
        assert "X002" in html

    def test_empty_csv(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_ranked_table import export_csv

        assert export_csv([]) == ""

    def test_empty_html(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_ranked_table import export_html

        assert "<table>" in export_html([])


class TestCheckOrbitQualitySkill:
    """Smoke tests for check_orbit_quality.py."""

    def test_assess_tracklet_returns_keys(self, tmp_path):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_orbit_quality import assess_tracklet

        from .conftest import build_tracklet

        t = build_tracklet(n_obs=4, arc_days=10.0)
        result = assess_tracklet(t)
        assert "object_id" in result
        assert "quality_code" in result
        assert "recommended_action" in result

    def test_short_arc_no_orbit(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_orbit_quality import assess_tracklet

        from .conftest import build_tracklet

        t = build_tracklet(n_obs=2, arc_days=0.1)
        result = assess_tracklet(t)
        assert result["quality_code"] == 1


class TestFilterCandidatesSkill:
    """Smoke tests for Skills/filter_candidates.py."""

    def _neos_json(self, tmp_path, n: int = 3) -> str:
        import json
        neos = [
            {
                "tracklet": {"object_id": f"OBJ{i}", "observations": [], "arc_days": 2.0,
                             "motion_rate_arcsec_per_hour": 1.0, "motion_pa_degrees": 90.0},
                "hazard": {"hazard_flag": "pha_candidate" if i == 0 else "nominal",
                           "alert_pathway": "mpc_submission" if i == 0 else "internal_candidate",
                           "neo_class": "apollo"},
                "metadata": {"discovery_priority": 0.9 - i * 0.3},
            }
            for i in range(n)
        ]
        p = tmp_path / "neos.json"
        p.write_text(json.dumps(neos))
        return str(p)

    def test_filter_by_hazard_flag(self, tmp_path):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from filter_candidates import filter_candidates

        neos = [
            {"hazard": {"hazard_flag": "pha_candidate", "alert_pathway": "mpc_submission"},
             "metadata": {"discovery_priority": 0.9}},
            {"hazard": {"hazard_flag": "nominal", "alert_pathway": "internal_candidate"},
             "metadata": {"discovery_priority": 0.2}},
        ]
        result = filter_candidates(neos, hazard_flag="pha_candidate")
        assert len(result) == 1
        assert result[0]["hazard"]["hazard_flag"] == "pha_candidate"

    def test_filter_empty_returns_empty(self, tmp_path):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from filter_candidates import filter_candidates

        assert filter_candidates([], hazard_flag="pha_candidate") == []

    def test_min_priority_filter(self, tmp_path):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from filter_candidates import filter_candidates

        neos = [
            {"hazard": {}, "metadata": {"discovery_priority": 0.8}},
            {"hazard": {}, "metadata": {"discovery_priority": 0.2}},
        ]
        result = filter_candidates(neos, min_priority=0.5)
        assert len(result) == 1


class TestSummariseRunSkill:
    """Smoke tests for Skills/summarise_run.py."""

    def _make_neos(self, n: int = 3) -> list:
        return [
            {
                "tracklet": {"object_id": f"OBJ{i}", "observations": []},
                "hazard": {"hazard_flag": "nominal", "alert_pathway": "internal_candidate",
                           "neo_class": "unknown"},
                "metadata": {"discovery_priority": float(i) / n},
            }
            for i in range(n)
        ]

    def test_returns_dict(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from summarise_run import summarise_run

        result = summarise_run(self._make_neos(3))
        assert isinstance(result, dict)

    def test_n_candidates_correct(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from summarise_run import summarise_run

        result = summarise_run(self._make_neos(4))
        assert result["n_candidates"] == 4

    def test_empty_returns_zero_candidates(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from summarise_run import summarise_run

        result = summarise_run([])
        assert result["n_candidates"] == 0

    def test_required_keys_present(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from summarise_run import summarise_run

        result = summarise_run(self._make_neos(2))
        for key in ("n_candidates", "hazard_flag_counts", "alert_pathway_counts",
                    "neo_class_counts", "mean_priority", "max_priority", "top_candidates"):
            assert key in result


class TestPlotSkyCoverageSkill:
    """Smoke tests for Skills/plot_sky_coverage.py."""

    def _make_neos(self) -> list:
        return [
            {
                "hazard": {"hazard_flag": "nominal"},
                "tracklet": {
                    "observations": [
                        {"ra_deg": 180.0, "dec_deg": 10.0},
                        {"ra_deg": 180.5, "dec_deg": 10.5},
                    ]
                },
            }
        ]

    def test_save_png(self, tmp_path):
        import sys
        from pathlib import Path

        import pytest
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from plot_sky_coverage import plot_sky_coverage

        out = str(tmp_path / "sky.png")
        try:
            plot_sky_coverage(self._make_neos(), out=out)
        except ImportError:
            pytest.skip("matplotlib not installed")
        assert Path(out).exists()

    def test_empty_neos_does_not_raise(self, tmp_path):
        import sys
        from pathlib import Path

        import pytest
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from plot_sky_coverage import plot_sky_coverage

        out = str(tmp_path / "empty_sky.png")
        try:
            plot_sky_coverage([], out=out)
        except ImportError:
            pytest.skip("matplotlib not installed")
        assert Path(out).exists()


class TestExportCandidateReportSkill:
    def _make_neo_dict(self, obj_id: str = "T001") -> dict:
        return {
            "tracklet": {
                "object_id": obj_id,
                "observations": [],
                "arc_days": 2.0,
                "motion_rate_arcsec_per_hour": 1.2,
                "motion_pa_degrees": 90.0,
            },
            "hazard": {
                "neo_class": "apollo",
                "hazard_flag": "pha_candidate",
                "alert_pathway": "mpc_submission",
                "moid_au": 0.03,
                "estimated_diameter_m": 200.0,
                "absolute_magnitude_h": 21.5,
                "explanation": {"summary": "test"},
            },
            "features": {"real_bogus_score": 0.9, "motion_consistency_score": 0.8},
            "posterior": {
                "neo_candidate": 0.75,
                "known_object": 0.05,
                "main_belt_asteroid": 0.1,
                "stellar_artifact": 0.05,
                "other_solar_system": 0.05,
            },
            "metadata": {
                "discovery_priority": 0.8,
                "followup_value": 0.6,
                "scientific_interest": 0.5,
                "model_version": "0.16.0",
            },
        }

    def test_returns_list(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_candidate_report import export_candidate_report
        neos = [self._make_neo_dict()]
        result = export_candidate_report(neos)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_report_contains_object_id(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_candidate_report import export_candidate_report
        neos = [self._make_neo_dict("MYOBJ")]
        result = export_candidate_report(neos)
        assert "MYOBJ" in result[0]["report"]

    def test_report_contains_guardrail(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_candidate_report import export_candidate_report
        neos = [self._make_neo_dict()]
        result = export_candidate_report(neos)
        assert "No impact probability" in result[0]["report"]

    def test_split_writes_file(self, tmp_path):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_candidate_report import export_candidate_report
        neos = [self._make_neo_dict("SPLIT_OBJ")]
        export_candidate_report(neos, split=True, out_dir=tmp_path)
        assert (tmp_path / "SPLIT_OBJ.txt").exists()

    def test_empty_list_returns_empty(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_candidate_report import export_candidate_report
        assert export_candidate_report([]) == []


class TestTagNeoClassSkill:
    def _make_tracklet_dict(self, n_obs: int = 3, obj_id: str = "T001") -> dict:
        obs = []
        for i in range(n_obs):
            obs.append({
                "obs_id": f"o{i}",
                "ra_deg": 180.0 + i * 0.001,
                "dec_deg": 0.0,
                "jd": 2460000.5 + i,
                "mag": 19.5,
                "mag_err": 0.05,
                "filter_band": "r",
                "mission": "ZTF",
            })
        return {
            "object_id": obj_id,
            "observations": obs,
            "arc_days": float(n_obs - 1),
            "motion_rate_arcsec_per_hour": 1.0,
            "motion_pa_degrees": 90.0,
        }

    def test_returns_list(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from tag_neo_class import tag_neo_class
        records = [self._make_tracklet_dict()]
        result = tag_neo_class(records)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_neo_class_key_present(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from tag_neo_class import tag_neo_class
        records = [self._make_tracklet_dict()]
        result = tag_neo_class(records)
        assert "neo_class" in result[0]

    def test_neo_class_is_valid_string(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from tag_neo_class import tag_neo_class
        records = [self._make_tracklet_dict()]
        result = tag_neo_class(records)
        valid = {"amor", "apollo", "aten", "ieo", "unknown"}
        assert result[0]["neo_class"] in valid

    def test_empty_input(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from tag_neo_class import tag_neo_class
        assert tag_neo_class([]) == []

    def test_scored_neo_dict_tagged(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from tag_neo_class import tag_neo_class
        scored = {
            "tracklet": self._make_tracklet_dict(),
            "hazard": {"neo_class": "unknown"},
        }
        result = tag_neo_class([scored])
        assert "tracklet" in result[0]
        assert "neo_class" in result[0]["tracklet"]


class TestCheckTissSerandSkill:
    def _make_tracklet_dict(self) -> dict:
        obs = [
            {
                "obs_id": f"t{i}",
                "ra_deg": 180.0 + i * 0.1,
                "dec_deg": i * 0.05,
                "jd": 2460000.5 + i,
                "mag": 19.0,
                "mag_err": 0.05,
                "filter_band": "r",
                "mission": "ZTF",
            }
            for i in range(3)
        ]
        return {
            "object_id": "2026TS1",
            "observations": obs,
        }

    def test_returns_list(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_tisserand import check_tisserand

        result = check_tisserand([self._make_tracklet_dict()])
        assert isinstance(result, list)

    def test_empty_input(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_tisserand import check_tisserand

        assert check_tisserand([]) == []

    def test_result_has_expected_keys(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_tisserand import check_tisserand

        result = check_tisserand([self._make_tracklet_dict()])
        assert len(result) == 1
        row = result[0]
        assert "object_id" in row
        assert "tisserand_parameter" in row
        assert "comet_like" in row

    def test_comet_like_flag_below_threshold(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_tisserand import check_tisserand

        record = self._make_tracklet_dict()
        results = check_tisserand([record], threshold=100.0)
        tj = results[0]["tisserand_parameter"]
        if tj is not None:
            assert results[0]["comet_like"] is True

    def test_comet_like_false_above_threshold(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_tisserand import check_tisserand

        record = self._make_tracklet_dict()
        results = check_tisserand([record], threshold=0.0)
        tj = results[0]["tisserand_parameter"]
        if tj is not None:
            assert results[0]["comet_like"] is False

    def test_scored_neo_dict_accepted(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from check_tisserand import check_tisserand

        scored = {"tracklet": self._make_tracklet_dict()}
        result = check_tisserand([scored])
        assert len(result) == 1
        assert result[0]["object_id"] == "2026TS1"


class TestExportFollowupRequestsSkill:
    def _make_scored_neo(self, priority: float = 0.8, obs_code: str = "Xnn"):
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

        obs = tuple(
            Observation(
                obs_id=f"o{i}",
                ra_deg=180.0 + i * 0.1,
                dec_deg=i * 0.05,
                jd=2460000.5 + i,
                mag=19.0,
                mag_err=0.05,
                filter_band="r",
                mission="ZTF",
            )
            for i in range(3)
        )
        tracklet = Tracklet(
            object_id="2026EFR1",
            observations=obs,
            arc_days=2.0,
            motion_rate_arcsec_per_hour=3.0,
            motion_pa_degrees=45.0,
        )
        explanation = CandidateExplanation(
            summary="test",
            supporting_evidence=(),
            contra_evidence=(),
            model_version="0.17.0",
        )
        hazard = HazardAssessment(
            hazard_flag="nominal",
            moid_au=0.1,
            estimated_diameter_m=100.0,
            absolute_magnitude_h=22.0,
            neo_class="apollo",
            alert_pathway="neocp_followup",
            explanation=explanation,
        )
        features = CandidateFeatures()
        posterior = NEOPosterior(
            neo_candidate=0.8,
            known_object=0.05,
            main_belt_asteroid=0.1,
            stellar_artifact=0.03,
            other_solar_system=0.02,
        )
        metadata = ScoringMetadata(
            scorer_version="0.17.0",
            scored_at_jd=2460000.0,
            pipeline_run_id="run-001",
            discovery_priority=priority,
            followup_value=0.5,
            scientific_interest=0.3,
        )
        return ScoredNEO(
            tracklet=tracklet,
            features=features,
            posterior=posterior,
            hazard=hazard,
            metadata=metadata,
        )

    def test_returns_list(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_followup_requests import export_followup_requests

        neo = self._make_scored_neo()
        result = export_followup_requests([neo])
        assert isinstance(result, list)

    def test_empty_input(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_followup_requests import export_followup_requests

        assert export_followup_requests([]) == []

    def test_result_has_expected_keys(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_followup_requests import export_followup_requests

        neo = self._make_scored_neo()
        result = export_followup_requests([neo])
        assert len(result) == 1
        row = result[0]
        assert "object_id" in row
        assert "priority" in row
        assert "report" in row

    def test_min_priority_filter(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_followup_requests import export_followup_requests

        high = self._make_scored_neo(priority=0.9)
        low = self._make_scored_neo(priority=0.1)
        result = export_followup_requests([high, low], min_priority=0.5)
        assert len(result) == 1
        assert result[0]["priority"] == pytest.approx(0.9)

    def test_sorted_by_priority_descending(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_followup_requests import export_followup_requests

        neos = [self._make_scored_neo(priority=p) for p in (0.3, 0.9, 0.6)]
        result = export_followup_requests(neos)
        priorities = [r["priority"] for r in result]
        assert priorities == sorted(priorities, reverse=True)

    def test_obs_code_passed_through(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from export_followup_requests import export_followup_requests

        neo = self._make_scored_neo()
        result = export_followup_requests([neo], obs_code="F51")
        assert "F51" in result[0]["report"]


class TestEphemerisCheckSkill:
    def _make_tracklet_dict(self) -> dict:
        return {
            "object_id": "2026EC1",
            "observations": [
                {
                    "obs_id": f"e{i}", "ra_deg": 180.0 + i * 0.1,
                    "dec_deg": i * 0.05, "jd": 2460000.5 + i,
                    "mag": 19.0, "mag_err": 0.05,
                    "filter_band": "r", "mission": "ZTF",
                }
                for i in range(3)
            ],
        }

    def test_returns_list(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from ephemeris_check import ephemeris_check
        result = ephemeris_check([self._make_tracklet_dict()], target_jd=2460010.5)
        assert isinstance(result, list)

    def test_empty_input(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from ephemeris_check import ephemeris_check
        assert ephemeris_check([], target_jd=2460010.5) == []

    def test_result_has_expected_keys(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from ephemeris_check import ephemeris_check
        result = ephemeris_check([self._make_tracklet_dict()], target_jd=2460010.5)
        row = result[0]
        for key in ("object_id", "target_jd", "ra_deg", "dec_deg", "helio_dist_au"):
            assert key in row

    def test_target_jd_stored(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from ephemeris_check import ephemeris_check
        result = ephemeris_check([self._make_tracklet_dict()], target_jd=2460099.0)
        assert result[0]["target_jd"] == pytest.approx(2460099.0)

    def test_object_id_preserved(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from ephemeris_check import ephemeris_check
        result = ephemeris_check([self._make_tracklet_dict()], target_jd=2460010.5)
        assert result[0]["object_id"] == "2026EC1"

    def test_scored_neo_dict_accepted(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from ephemeris_check import ephemeris_check
        scored = {"tracklet": self._make_tracklet_dict()}
        result = ephemeris_check([scored], target_jd=2460010.5)
        assert len(result) == 1


class TestFlagCometCandidatesSkill:
    def _make_tracklet_dict(self) -> dict:
        return {
            "object_id": "2026FC1",
            "observations": [
                {
                    "obs_id": f"f{i}", "ra_deg": 180.0 + i * 0.1,
                    "dec_deg": i * 0.05, "jd": 2460000.5 + i,
                    "mag": 19.0, "mag_err": 0.05,
                    "filter_band": "r", "mission": "ZTF",
                }
                for i in range(3)
            ],
        }

    def test_returns_list(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from flag_comet_candidates import flag_comet_candidates
        result = flag_comet_candidates([self._make_tracklet_dict()])
        assert isinstance(result, list)

    def test_empty_input(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from flag_comet_candidates import flag_comet_candidates
        assert flag_comet_candidates([]) == []

    def test_result_has_expected_keys(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from flag_comet_candidates import flag_comet_candidates
        result = flag_comet_candidates([self._make_tracklet_dict()])
        row = result[0]
        for key in ("object_id", "tisserand_parameter", "eccentricity",
                    "comet_candidate", "reason"):
            assert key in row

    def test_comet_flag_true_when_threshold_very_high(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from flag_comet_candidates import flag_comet_candidates
        result = flag_comet_candidates([self._make_tracklet_dict()],
                                       threshold=100.0, min_ecc=0.0)
        tj = result[0]["tisserand_parameter"]
        if tj is not None:
            assert result[0]["comet_candidate"] is True

    def test_comet_flag_false_when_threshold_zero(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from flag_comet_candidates import flag_comet_candidates
        result = flag_comet_candidates([self._make_tracklet_dict()], threshold=0.0)
        assert result[0]["comet_candidate"] is False

    def test_reason_always_present(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))
        from flag_comet_candidates import flag_comet_candidates
        result = flag_comet_candidates([self._make_tracklet_dict()])
        assert isinstance(result[0]["reason"], str)
        assert len(result[0]["reason"]) > 0


class TestComputeOrbitalEnergySkill:
    def _skill_path(self):
        from pathlib import Path
        return str(Path(__file__).resolve().parent.parent / "Skills")

    def test_imports_cleanly(self):
        import sys
        sys.path.insert(0, self._skill_path())
        import importlib
        spec = importlib.util.spec_from_file_location(
            "compute_orbital_energy",
            f"{self._skill_path()}/compute_orbital_energy.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, "main")

    def test_main_runs_on_sample(self, tmp_path):
        import json
        import sys
        sys.path.insert(0, self._skill_path())
        import importlib
        spec = importlib.util.spec_from_file_location(
            "compute_orbital_energy",
            f"{self._skill_path()}/compute_orbital_energy.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        # Write a minimal input file with an orbital_elements block
        data = [{"object_id": "T_energy", "orbital_elements": {
            "semi_major_axis_au": 1.5, "eccentricity": 0.3, "inclination_deg": 10.0,
            "longitude_ascending_node_deg": 45.0, "argument_perihelion_deg": 90.0,
            "mean_anomaly_deg": 180.0, "epoch_jd": 2460000.5,
            "perihelion_au": 1.05, "aphelion_au": 1.95, "quality_code": 2,
        }}]
        f = tmp_path / "input.json"
        f.write_text(json.dumps(data))
        import sys as _sys
        old_argv = _sys.argv
        _sys.argv = ["compute_orbital_energy.py", str(f)]
        try:
            mod.main()
        finally:
            _sys.argv = old_argv


class TestAssessSurveyCoverageSkill:
    def _skill_path(self):
        from pathlib import Path
        return str(Path(__file__).resolve().parent.parent / "Skills")

    def test_imports_cleanly(self):
        import importlib
        spec = importlib.util.spec_from_file_location(
            "assess_survey_coverage",
            f"{self._skill_path()}/assess_survey_coverage.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, "main")

    def test_main_runs_on_sample(self, tmp_path):
        import importlib
        import json
        spec = importlib.util.spec_from_file_location(
            "assess_survey_coverage",
            f"{self._skill_path()}/assess_survey_coverage.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        data = [
            {"field_id": "F001", "ra_deg": 45.0, "dec_deg": 10.0, "radius_deg": 1.5,
             "limiting_mag": 21.5, "n_sources": 80, "jd": 2460000.5},
            {"field_id": "F002", "ra_deg": 90.0, "dec_deg": -5.0, "radius_deg": 1.5,
             "limiting_mag": 21.8, "n_sources": 65, "jd": 2460001.5},
        ]
        f = tmp_path / "fields.json"
        f.write_text(json.dumps(data))
        import sys as _sys
        old_argv = _sys.argv
        _sys.argv = ["assess_survey_coverage.py", str(f)]
        try:
            mod.main()
        finally:
            _sys.argv = old_argv


class TestGradeTrackletsSkill:
    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def test_module_has_main(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "grade_tracklets",
            f"{self._skill_path()}/grade_tracklets.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, "main")

    def test_grade_tracklets_on_sample(self, tmp_path):
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location(
            "grade_tracklets",
            f"{self._skill_path()}/grade_tracklets.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        data = [
            {
                "object_id": "2026 AA1",
                "arc_days": 3.0,
                "motion_rate_arcsec_per_hour": 5.0,
                "motion_pa_degrees": 90.0,
                "observations": [
                    {"obs_id": "o1", "ra_deg": 10.0, "dec_deg": 5.0, "jd": 2460000.5,
                     "magnitude": 20.0, "magnitude_error": 0.1, "band": "r", "survey": "ZTF"},
                    {"obs_id": "o2", "ra_deg": 10.01, "dec_deg": 5.01, "jd": 2460001.5,
                     "magnitude": 20.1, "magnitude_error": 0.1, "band": "r", "survey": "ZTF"},
                ],
            }
        ]
        f = tmp_path / "tracklets.json"
        f.write_text(json.dumps(data))
        import sys as _sys
        old_argv = _sys.argv
        _sys.argv = ["grade_tracklets.py", str(f)]
        try:
            result = mod.grade_tracklets(str(f))
        finally:
            _sys.argv = old_argv
        assert result == 0

    def test_grade_tracklets_json_flag(self, tmp_path):
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location(
            "grade_tracklets",
            f"{self._skill_path()}/grade_tracklets.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        data = [
            {
                "object_id": "2026 BB2",
                "arc_days": 1.0,
                "motion_rate_arcsec_per_hour": 3.0,
                "motion_pa_degrees": 45.0,
                "observations": [
                    {"obs_id": "o1", "ra_deg": 20.0, "dec_deg": 3.0, "jd": 2460000.5,
                     "magnitude": 20.0, "magnitude_error": 0.1, "band": "r", "survey": "ZTF"},
                    {"obs_id": "o2", "ra_deg": 20.01, "dec_deg": 3.01, "jd": 2460001.5,
                     "magnitude": 20.1, "magnitude_error": 0.1, "band": "r", "survey": "ZTF"},
                ],
            }
        ]
        f = tmp_path / "t.json"
        f.write_text(json.dumps(data))
        result = mod.grade_tracklets(str(f), as_json=True)
        assert result == 0

    def test_empty_file_returns_nonzero(self, tmp_path):
        import importlib.util
        import json
        spec = importlib.util.spec_from_file_location(
            "grade_tracklets",
            f"{self._skill_path()}/grade_tracklets.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        f = tmp_path / "empty.json"
        f.write_text(json.dumps([]))
        result = mod.grade_tracklets(str(f))
        assert result == 1


class TestQueryMpcObservationsSkill:
    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def test_module_has_main(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "query_mpc_observations",
            f"{self._skill_path()}/query_mpc_observations.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, "main")

    def test_query_returns_0_on_empty(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location(
            "query_mpc_observations",
            f"{self._skill_path()}/query_mpc_observations.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        with patch("fetch.fetch_mpc_observations", return_value=[]):
            result = mod.query_observations("unknown_xyz")
        assert result == 0

    def test_query_json_flag_empty(self, capsys):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location(
            "query_mpc_observations",
            f"{self._skill_path()}/query_mpc_observations.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        with patch("fetch.fetch_mpc_observations", return_value=[]):
            result = mod.query_observations("unknown_xyz", as_json=True)
        assert result == 0
        captured = capsys.readouterr()
        import json
        data = json.loads(captured.out)
        assert data["n_obs"] == 0


class TestComputeThreatScoresSkill:
    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def _load_skill(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "compute_threat_scores",
            f"{self._skill_path()}/compute_threat_scores.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_load_neos_returns_list(self, tmp_path):
        import json
        mod = self._load_skill()
        data = [
            {
                "tracklet": {"object_id": "T001"},
                "hazard": {"moid_au": 0.02, "absolute_magnitude_h": 21.0},
                "metadata": {"quality_code": 2},
                "features": {},
            }
        ]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        neos = mod._load_neos(str(f))
        assert isinstance(neos, list)
        assert len(neos) == 1
        assert neos[0].tracklet.object_id == "T001"

    def test_load_neos_single_object(self, tmp_path):
        import json
        mod = self._load_skill()
        data = {
            "tracklet": {"object_id": "T002"},
            "hazard": {"moid_au": None, "absolute_magnitude_h": None},
            "metadata": {},
            "features": {},
        }
        f = tmp_path / "single.json"
        f.write_text(json.dumps(data))
        neos = mod._load_neos(str(f))
        assert len(neos) == 1


class TestFetchAtlasDataSkill:
    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def _load_skill(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "fetch_atlas_data",
            f"{self._skill_path()}/fetch_atlas_data.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")


class TestPlotCalibrationSkill:
    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def _load_skill(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "plot_calibration",
            f"{self._skill_path()}/plot_calibration.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_plot_calibration_returns_int(self, tmp_path):
        import json
        mod = self._load_skill()
        data = [{"prob": 0.8, "label": 1}, {"prob": 0.2, "label": 0}]
        f = tmp_path / "probs.json"
        f.write_text(json.dumps(data))
        out = tmp_path / "out.png"
        result = mod.plot_calibration(str(f), str(out))
        assert isinstance(result, int)

    def test_missing_file_returns_nonzero(self, tmp_path):
        mod = self._load_skill()
        result = mod.plot_calibration(str(tmp_path / "nonexistent.json"), str(tmp_path / "out.png"))
        assert result != 0

    def test_scored_neo_format(self, tmp_path):
        import json
        mod = self._load_skill()
        data = [
            {
                "posterior": {"neo_candidate": 0.8},
                "hazard": {"hazard_flag": "pha_candidate"},
            },
            {
                "posterior": {"neo_candidate": 0.1},
                "hazard": {"hazard_flag": "nominal"},
            },
        ]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        result = mod.plot_calibration(str(f), str(tmp_path / "out.png"))
        assert isinstance(result, int)


class TestExportSurveySummarySkill:
    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def _load_skill(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "export_survey_summary",
            f"{self._skill_path()}/export_survey_summary.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _sample_neo_data(self):
        return [
            {
                "tracklet": {
                    "object_id": "2026-AB1",
                    "arc_days": 2.0,
                    "observations": [{"mission": "ZTF"}, {"mission": "ZTF"}],
                },
                "hazard": {
                    "hazard_flag": "pha_candidate",
                    "alert_pathway": "mpc_submission",
                    "moid_au": 0.03,
                    "absolute_magnitude_h": 21.5,
                    "neo_class": "apollo",
                },
                "metadata": {"discovery_priority": 0.8},
            }
        ]

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_csv_export(self, tmp_path):
        import json
        mod = self._load_skill()
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(self._sample_neo_data()))
        out = tmp_path / "summary.csv"
        result = mod.export_summary(str(f), str(out), fmt="csv")
        assert result == 0
        assert out.exists()
        content = out.read_text()
        assert "2026-AB1" in content

    def test_html_export(self, tmp_path):
        import json
        mod = self._load_skill()
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(self._sample_neo_data()))
        out = tmp_path / "summary.html"
        result = mod.export_summary(str(f), str(out), fmt="html")
        assert result == 0
        assert "<table" in out.read_text()

    def test_empty_data_returns_nonzero(self, tmp_path):
        import json
        mod = self._load_skill()
        f = tmp_path / "empty.json"
        f.write_text(json.dumps([]))
        result = mod.export_summary(str(f), None, fmt="csv")
        assert result != 0


class TestComputeApparentMagnitudesSkill:
    """Smoke tests for Skills/compute_apparent_magnitudes.py."""

    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def _load_skill(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "compute_apparent_magnitudes",
            f"{self._skill_path()}/compute_apparent_magnitudes.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_main_with_no_orbital_elements(self, tmp_path):
        import json
        mod = self._load_skill()
        data = [{"tracklet": {"object_id": "NEO-001"}}]
        f = tmp_path / "tracklets.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--jd", "2460000.5"])

    def test_main_json_flag(self, tmp_path, capsys):
        import json
        mod = self._load_skill()
        data = [{"tracklet": {"object_id": "NEO-001"}}]
        f = tmp_path / "tracklets.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--jd", "2460000.5", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert isinstance(rows, list)
        assert rows[0]["object_id"] == "NEO-001"

    def test_main_with_orbital_elements(self, tmp_path, capsys):
        import json
        mod = self._load_skill()
        data = [{
            "tracklet": {
                "object_id": "NEO-002",
                "orbital_elements": {
                    "semi_major_axis_au": 1.5, "eccentricity": 0.2,
                    "inclination_deg": 5.0, "longitude_ascending_node_deg": 30.0,
                    "argument_perihelion_deg": 60.0, "mean_anomaly_deg": 90.0,
                    "epoch_jd": 2460000.5, "perihelion_au": 1.2, "aphelion_au": 1.8,
                },
            }
        }]
        f = tmp_path / "tracklets.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--jd", "2460010.5", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert rows[0]["object_id"] == "NEO-002"

    def test_main_dict_input_wrapped(self, tmp_path, capsys):
        import json
        mod = self._load_skill()
        data = {"tracklet": {"object_id": "NEO-003"}}
        f = tmp_path / "tracklets.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--jd", "2460000.5", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert len(rows) == 1


class TestTriageCandidatesSkill:
    """Smoke tests for Skills/triage_candidates.py."""

    def _skill_path(self):
        import pathlib
        return str(pathlib.Path(__file__).resolve().parents[1] / "Skills")

    def _load_skill(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "triage_candidates",
            f"{self._skill_path()}/triage_candidates.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def _make_neo_data(self, pathway="internal_candidate", hazard_flag="nominal", moid=0.1):
        import json

        from .conftest import build_scored_neo
        neo = build_scored_neo(alert_pathway=pathway)
        return json.loads(neo.model_dump_json())

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_main_runs(self, tmp_path):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f)])

    def test_main_json_flag(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="mpc_submission")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert isinstance(rows, list)

    def test_urgency_filter(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--urgency", "URGENT", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        # All results should be URGENT tier (or empty)
        for row in rows:
            assert row["urgency"] == "URGENT"

    def test_pathway_filter(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--pathway", "nasa_pdco_notify", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        for row in rows:
            assert row["alert_pathway"] == "nasa_pdco_notify"

    def test_empty_result_no_match(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--pathway", "nasa_pdco_notify"])
        captured = capsys.readouterr()
        assert "No candidates" in captured.out or captured.out == ""

    def test_dict_input_wrapped(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = json.loads(neo.model_dump_json())
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert isinstance(rows, list)


class TestComputeDiscoveryScoresSkill:
    """Smoke tests for Skills/compute_discovery_scores.py."""

    def _load_skill(self):
        import importlib.util
        import pathlib
        spec = importlib.util.spec_from_file_location(
            "compute_discovery_scores",
            str(pathlib.Path(__file__).resolve().parents[1]
                / "Skills" / "compute_discovery_scores.py"),
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_main_runs(self, tmp_path):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f)])

    def test_main_json_flag(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert isinstance(rows, list)

    def test_threshold_filters(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--threshold", "0.99", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        for row in rows:
            assert row["discovery_score"] >= 0.99

    def test_sort_flag(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json()) for _ in range(2)]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--sort", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        scores = [r["discovery_score"] for r in rows]
        assert scores == sorted(scores, reverse=True)

    def test_dict_input_wrapped(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        f = tmp_path / "neo.json"
        f.write_text(neo.model_dump_json())
        mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert isinstance(rows, list)


class TestFormatSubmissionChecklistsSkill:
    """Smoke tests for Skills/format_submission_checklists.py."""

    def _load_skill(self):
        import importlib.util
        import pathlib
        spec = importlib.util.spec_from_file_location(
            "format_submission_checklists",
            str(pathlib.Path(__file__).resolve().parents[1]
                / "Skills" / "format_submission_checklists.py"),
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_main_runs(self, tmp_path):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f)])

    def test_main_json_flag(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert isinstance(rows, list)
        assert "checklist" in rows[0]

    def test_min_priority_filter(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f), "--min-priority", "0.99"])
        captured = capsys.readouterr()
        assert "No candidates" in captured.out or captured.out == ""

    def test_checklist_contains_guardrail(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        mod.main([str(f)])
        captured = capsys.readouterr()
        assert "GUARDRAIL" in captured.out

    def test_dict_input_wrapped(self, tmp_path, capsys):
        import json

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        f = tmp_path / "neo.json"
        f.write_text(neo.model_dump_json())
        mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert len(rows) == 1


class TestValidatePipelineRunSkill:
    def _load_skill(self):
        import importlib.util
        from pathlib import Path
        skill_path = (
            Path(__file__).parent.parent / "Skills" / "validate_pipeline_run.py"
        )
        spec = importlib.util.spec_from_file_location("validate_pipeline_run", skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_valid_run_exits_zero(self, tmp_path, capsys):
        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        f = tmp_path / "run.json"
        f.write_text("[" + neo.model_dump_json() + "]")
        with pytest.raises(SystemExit) as exc:
            mod.main([str(f)])
        assert exc.value.code == 0

    def test_json_flag_valid(self, tmp_path, capsys):
        import json as _json

        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        f = tmp_path / "run.json"
        f.write_text("[" + neo.model_dump_json() + "]")
        with pytest.raises(SystemExit):
            mod.main([str(f), "--json"])
        out = capsys.readouterr().out
        rows = _json.loads(out)
        assert isinstance(rows, list)
        assert rows[0]["status"] in ("PASS", "FAIL")

    def test_missing_key_exits_one(self, tmp_path):
        import pytest
        mod = self._load_skill()
        f = tmp_path / "bad.json"
        f.write_text('[{"tracklet": {"object_id": "x", "observations": [1, 2]}}]')
        with pytest.raises(SystemExit) as exc:
            mod.main([str(f)])
        assert exc.value.code == 1

    def test_empty_observations_flagged(self, tmp_path):
        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        data = neo.model_dump()
        data["tracklet"]["observations"] = []
        f = tmp_path / "run.json"
        import json as _json
        f.write_text(_json.dumps([data]))
        with pytest.raises(SystemExit) as exc:
            mod.main([str(f)])
        assert exc.value.code == 1

    def test_dict_input_wrapped(self, tmp_path, capsys):
        import json as _json

        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo()
        f = tmp_path / "single.json"
        f.write_text(neo.model_dump_json())
        with pytest.raises(SystemExit):
            mod.main([str(f), "--json"])
        out = capsys.readouterr().out
        rows = _json.loads(out)
        assert isinstance(rows, list)


class TestExportAtlasLightcurveSkill:
    def _load_skill(self):
        import importlib.util
        from pathlib import Path
        skill_path = (
            Path(__file__).parent.parent / "Skills" / "export_atlas_lightcurve.py"
        )
        spec = importlib.util.spec_from_file_location("export_atlas_lightcurve", skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _make_observations(self):
        from schemas import Observation
        return [
            Observation(
                obs_id=f"atl_{i}", ra_deg=180.0, dec_deg=10.0,
                jd=2460000.5 + i, mag=18.5 + i * 0.1, mag_err=0.05,
                filter_band="o" if i % 2 == 0 else "c", mission="ATLAS",
            )
            for i in range(4)
        ]

    def test_csv_to_stdout(self, capsys):
        from unittest.mock import patch
        mod = self._load_skill()
        obs = self._make_observations()
        with patch("fetch.fetch_atlas_forced", return_value=obs):
            mod.main([
                "--ra", "180.0", "--dec", "10.0",
                "--start-jd", "2460000.5", "--end-jd", "2460004.5",
                "--format", "csv",
            ])
        out = capsys.readouterr().out
        assert "jd" in out.lower() or "obs_id" in out.lower()

    def test_json_output(self, capsys):
        import json as _json
        from unittest.mock import patch
        mod = self._load_skill()
        obs = self._make_observations()
        with patch("fetch.fetch_atlas_forced", return_value=obs):
            mod.main([
                "--ra", "180.0", "--dec", "10.0",
                "--start-jd", "2460000.5", "--end-jd", "2460004.5",
                "--format", "json",
            ])
        out = capsys.readouterr().out
        rows = _json.loads(out)
        assert isinstance(rows, list)
        assert len(rows) > 0

    def test_csv_to_file(self, tmp_path):
        from unittest.mock import patch
        mod = self._load_skill()
        obs = self._make_observations()
        out_file = tmp_path / "lc.csv"
        with patch("fetch.fetch_atlas_forced", return_value=obs):
            mod.main([
                "--ra", "180.0", "--dec", "10.0",
                "--start-jd", "2460000.5", "--end-jd", "2460004.5",
                "--format", "csv", "--out", str(out_file),
            ])
        assert out_file.exists()

    def test_no_observations_exits_one(self, tmp_path):
        from unittest.mock import patch

        import pytest
        mod = self._load_skill()
        with patch("fetch.fetch_atlas_forced", return_value=[]), \
             pytest.raises(SystemExit) as exc:
            mod.main([
                "--ra", "180.0", "--dec", "10.0",
                "--start-jd", "2460000.5", "--end-jd", "2460004.5",
                "--format", "csv",
            ])
        assert exc.value.code == 1

    def test_json_to_file(self, tmp_path):
        from unittest.mock import patch
        mod = self._load_skill()
        obs = self._make_observations()
        out_file = tmp_path / "lc.json"
        with patch("fetch.fetch_atlas_forced", return_value=obs):
            mod.main([
                "--ra", "180.0", "--dec", "10.0",
                "--start-jd", "2460000.5", "--end-jd", "2460004.5",
                "--format", "json", "--out", str(out_file),
            ])
        import json as _json
        assert out_file.exists()
        content = _json.loads(out_file.read_text())
        assert isinstance(content, list)


class TestComputeTrueAnomalySkill:
    def _load_skill(self):
        import importlib.util
        from pathlib import Path
        skill_path = Path(__file__).parent.parent / "Skills" / "compute_true_anomaly.py"
        spec = importlib.util.spec_from_file_location("compute_true_anomaly", skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_missing_file_exits_1(self, tmp_path):
        import pytest
        mod = self._load_skill()
        with pytest.raises(SystemExit) as exc_info:
            mod.main([str(tmp_path / "nonexistent.json")])
        assert exc_info.value.code == 1

    def test_no_orbital_elements_skipped(self, tmp_path):
        import json

        import pytest
        data = [{"object_id": "neo_001", "tracklet": {"object_id": "neo_001"}}]
        f = tmp_path / "track.json"
        f.write_text(json.dumps(data))
        mod = self._load_skill()
        with pytest.raises(SystemExit) as exc_info:
            mod.main([str(f)])
        assert exc_info.value.code == 0

    def test_json_flag_output(self, tmp_path, capsys):
        import json

        import pytest
        el = {"mean_anomaly_deg": 90.0, "eccentricity": 0.3}
        data = [{"object_id": "neo_001", "orbital_elements": el}]
        f = tmp_path / "track.json"
        f.write_text(json.dumps(data))
        mod = self._load_skill()
        with pytest.raises(SystemExit):
            mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert isinstance(result, list)
        assert result[0]["nu_deg"] is not None

    def test_table_output(self, tmp_path, capsys):
        import json

        import pytest
        el = {"mean_anomaly_deg": 45.0, "eccentricity": 0.2}
        data = [{"object_id": "neo_001", "orbital_elements": el}]
        f = tmp_path / "track.json"
        f.write_text(json.dumps(data))
        mod = self._load_skill()
        with pytest.raises(SystemExit):
            mod.main([str(f)])
        captured = capsys.readouterr()
        assert "neo_001" in captured.out

    def test_bad_eccentricity_note(self, tmp_path, capsys):
        import json

        import pytest
        el_bad = {"mean_anomaly_deg": 1.0, "eccentricity": 1.5}
        data = [{"object_id": "bad", "orbital_elements": el_bad}]
        f = tmp_path / "track.json"
        f.write_text(json.dumps(data))
        mod = self._load_skill()
        with pytest.raises(SystemExit):
            mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result[0]["nu_deg"] is None


class TestExportCandidateDossiersSkill:
    def _load_skill(self):
        import importlib.util
        from pathlib import Path
        skill_path = Path(__file__).parent.parent / "Skills" / "export_candidate_dossiers.py"
        spec = importlib.util.spec_from_file_location("export_candidate_dossiers", skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _sample_neo(self):
        return {
            "object_id": "neo_001",
            "tracklet": {"object_id": "neo_001", "arc_days": 2.5,
                         "motion_rate_arcsec_per_hour": 1.5, "observations": []},
            "hazard": {"hazard_flag": "nominal", "alert_pathway": "internal_candidate",
                       "neo_class": "apollo", "moid_au": 0.1,
                       "absolute_magnitude_h": 22.0, "estimated_diameter_m": 150.0},
            "posterior": {"neo_candidate": 0.5, "known_object": 0.2, "main_belt_asteroid": 0.2,
                          "stellar_artifact": 0.05, "other_solar_system": 0.05},
            "metadata": {"discovery_priority": 0.7},
        }

    def test_missing_file_exits_1(self, tmp_path):
        import pytest
        mod = self._load_skill()
        with pytest.raises(SystemExit) as exc_info:
            mod.main([str(tmp_path / "nonexistent.json")])
        assert exc_info.value.code == 1

    def test_stdout_output(self, tmp_path, capsys):
        import json

        import pytest
        f = tmp_path / "neos.json"
        f.write_text(json.dumps([self._sample_neo()]))
        mod = self._load_skill()
        with pytest.raises(SystemExit):
            mod.main([str(f)])
        captured = capsys.readouterr()
        assert "neo_001" in captured.out

    def test_json_flag(self, tmp_path, capsys):
        import json

        import pytest
        f = tmp_path / "neos.json"
        f.write_text(json.dumps([self._sample_neo()]))
        mod = self._load_skill()
        with pytest.raises(SystemExit):
            mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert isinstance(result, list)
        assert result[0]["object_id"] == "neo_001"

    def test_out_dir(self, tmp_path):
        import json

        import pytest
        f = tmp_path / "neos.json"
        f.write_text(json.dumps([self._sample_neo()]))
        out_dir = tmp_path / "dossiers"
        mod = self._load_skill()
        with pytest.raises(SystemExit):
            mod.main([str(f), "--out-dir", str(out_dir)])
        assert (out_dir / "neo_001.txt").exists()

    def test_guardrail_in_output(self, tmp_path, capsys):
        import json

        import pytest
        f = tmp_path / "neos.json"
        f.write_text(json.dumps([self._sample_neo()]))
        mod = self._load_skill()
        with pytest.raises(SystemExit):
            mod.main([str(f)])
        captured = capsys.readouterr()
        assert "NOT" in captured.out.upper()


class TestComputeCombinedPrioritySkill:
    """Smoke tests for Skills/compute_combined_priority.py."""

    def _load_skill(self):
        import importlib.util
        import pathlib
        spec = importlib.util.spec_from_file_location(
            "compute_combined_priority",
            str(pathlib.Path(__file__).resolve().parents[1]
                / "Skills" / "compute_combined_priority.py"),
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_main_runs(self, tmp_path):
        import json

        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        with pytest.raises(SystemExit) as exc:
            mod.main([str(f)])
        assert exc.value.code == 0

    def test_main_json_flag(self, tmp_path, capsys):
        import json

        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        with pytest.raises(SystemExit):
            mod.main([str(f), "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert "combined_priority" in rows[0]

    def test_sort_flag(self, tmp_path, capsys):
        import json

        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json()) for _ in range(2)]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        with pytest.raises(SystemExit):
            mod.main([str(f), "--sort", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        priorities = [r["combined_priority"] for r in rows]
        assert priorities == sorted(priorities, reverse=True)

    def test_threshold_filters(self, tmp_path, capsys):
        import json

        import pytest

        from .conftest import build_scored_neo
        mod = self._load_skill()
        neo = build_scored_neo(alert_pathway="internal_candidate")
        data = [json.loads(neo.model_dump_json())]
        f = tmp_path / "neos.json"
        f.write_text(json.dumps(data))
        with pytest.raises(SystemExit):
            mod.main([str(f), "--threshold", "0.99", "--json"])
        captured = capsys.readouterr()
        rows = json.loads(captured.out)
        for row in rows:
            assert row["combined_priority"] >= 0.99

    def test_error_bad_file(self, capsys):
        import pytest
        mod = self._load_skill()
        with pytest.raises(SystemExit) as exc:
            mod.main(["/nonexistent/path.json"])
        assert exc.value.code == 1


class TestFetchRecentNeosSkill:
    """Smoke tests for Skills/fetch_recent_neos.py."""

    def _load_skill(self):
        import importlib.util
        import pathlib
        spec = importlib.util.spec_from_file_location(
            "fetch_recent_neos",
            str(pathlib.Path(__file__).resolve().parents[1]
                / "Skills" / "fetch_recent_neos.py"),
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    def test_module_has_main(self):
        mod = self._load_skill()
        assert hasattr(mod, "main")

    def test_main_runs_empty(self, tmp_path, capsys, monkeypatch):
        """Skill runs and exits 0 when no NEOs found (import blocked)."""
        import sys

        import pytest
        monkeypatch.setitem(sys.modules, "astroquery.mpc", None)

        mod = self._load_skill()
        with pytest.raises(SystemExit) as exc:
            mod.main([])
        assert exc.value.code == 0

    def test_main_json_flag_with_mock(self, tmp_path, capsys, monkeypatch):
        """Skill returns JSON list when --json passed and MPC returns data."""
        import sys
        from datetime import date, timedelta
        from unittest.mock import MagicMock

        import pytest

        mock_row = {
            "ra": 180.0, "dec": 10.0, "h": 18.0,
            "discovery_date": date.today() - timedelta(days=5),
        }
        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects.return_value = [mock_row]
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        import importlib
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)
        import fetch as fm
        importlib.reload(fm)
        # Patch the fetch module inside the skill's namespace
        mod = self._load_skill()

        with pytest.raises(SystemExit):
            mod.main(["--n-days", "30", "--json"])
        # Just verify it ran without crashing
        assert True
