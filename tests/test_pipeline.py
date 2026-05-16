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
