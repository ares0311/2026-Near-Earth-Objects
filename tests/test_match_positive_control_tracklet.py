"""Tests for Skills/match_positive_control_tracklet.py (Gate Z3 tracklet
position-matching diagnostic).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "match_positive_control_tracklet.py"
)
_spec = importlib.util.spec_from_file_location("match_positive_control_tracklet", _MODULE_PATH)
match_positive_control_tracklet = importlib.util.module_from_spec(_spec)
sys.modules["match_positive_control_tracklet"] = match_positive_control_tracklet
_spec.loader.exec_module(match_positive_control_tracklet)


class TestSeparationArcsec:
    def test_zero_separation(self):
        assert match_positive_control_tracklet.separation_arcsec(10.0, 20.0, 10.0, 20.0) == 0.0

    def test_known_dec_only_offset(self):
        # 1 arcsec in Dec at RA offset 0
        sep = match_positive_control_tracklet.separation_arcsec(10.0, 20.0, 10.0, 20.0 + 1 / 3600)
        assert abs(sep - 1.0) < 1e-6


class TestRankTracklets:
    def _report(self):
        return {
            "tracklets": [
                {
                    "object_id": "far",
                    "observations": [
                        {"ra_deg": 100.0, "dec_deg": 0.0, "jd": 2459000.5},
                        {"ra_deg": 100.5, "dec_deg": 0.0, "jd": 2459002.5},
                    ],
                    "motion_rate_arcsec_per_hour": 10.0,
                    "motion_pa_degrees": 90.0,
                },
                {
                    "object_id": "close",
                    "observations": [
                        {"ra_deg": 257.0810, "dec_deg": -10.7455, "jd": 2459000.5},
                        {"ra_deg": 257.5498, "dec_deg": -10.9842, "jd": 2459002.5},
                    ],
                    "motion_rate_arcsec_per_hour": 38.7,
                    "motion_pa_degrees": 117.4,
                },
                {
                    "object_id": "single_obs",
                    "observations": [{"ra_deg": 1.0, "dec_deg": 1.0, "jd": 2459000.5}],
                    "motion_rate_arcsec_per_hour": 5.0,
                    "motion_pa_degrees": 0.0,
                },
            ]
        }

    def test_closest_tracklet_ranked_first(self):
        ranked = match_positive_control_tracklet.rank_tracklets(
            self._report(), (257.0809, -10.7456), (257.5497, -10.9843)
        )
        # single_obs excluded (only 1 observation); "close" ranked before "far"
        assert [r["object_id"] for r in ranked] == ["close", "far"]
        assert ranked[0]["total_offset_arcsec"] < 2.0

    def test_empty_tracklets(self):
        ranked = match_positive_control_tracklet.rank_tracklets(
            {"tracklets": []}, (0.0, 0.0), (0.0, 0.0)
        )
        assert ranked == []


class TestMainCLI:
    def test_main_prints_best_match(self, tmp_path, capsys):
        report = {
            "tracklets": [
                {
                    "object_id": "close",
                    "observations": [
                        {"ra_deg": 257.0810, "dec_deg": -10.7455, "jd": 2459000.5},
                        {"ra_deg": 257.5498, "dec_deg": -10.9842, "jd": 2459002.5},
                    ],
                    "motion_rate_arcsec_per_hour": 38.7,
                    "motion_pa_degrees": 117.4,
                }
            ]
        }
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(report))

        sys.argv = [
            "match_positive_control_tracklet.py",
            str(report_path),
            "--ref1", "257.0809", "-10.7456",
            "--ref2", "257.5497", "-10.9843",
        ]
        match_positive_control_tracklet.main()
        out = capsys.readouterr().out
        assert "Best candidate: close" in out

    def test_main_handles_no_tracklets(self, tmp_path, capsys):
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps({"tracklets": []}))

        sys.argv = [
            "match_positive_control_tracklet.py",
            str(report_path),
            "--ref1", "0", "0",
            "--ref2", "0", "0",
        ]
        match_positive_control_tracklet.main()
        out = capsys.readouterr().out
        assert "nothing to rank" in out
