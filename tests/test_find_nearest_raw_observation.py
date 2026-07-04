"""Tests for Skills/find_nearest_raw_observation.py (Gate Z3 raw-observation
proximity diagnostic)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "find_nearest_raw_observation.py"
)
_spec = importlib.util.spec_from_file_location("find_nearest_raw_observation", _MODULE_PATH)
find_nearest_raw_observation = importlib.util.module_from_spec(_spec)
sys.modules["find_nearest_raw_observation"] = find_nearest_raw_observation
_spec.loader.exec_module(find_nearest_raw_observation)


class TestSeparationArcsec:
    def test_zero_separation(self):
        assert find_nearest_raw_observation.separation_arcsec(10.0, 20.0, 10.0, 20.0) == 0.0


class TestRankObservations:
    def _checkpoint(self):
        return {
            "observations": [
                {
                    "obs_id": "far",
                    "ra_deg": 100.0,
                    "dec_deg": 0.0,
                    "jd": 2459000.5,
                    "real_bogus": 0.9,
                },
                {
                    "obs_id": "close",
                    "ra_deg": 257.0810,
                    "dec_deg": -10.7455,
                    "jd": 2459000.5,
                    "real_bogus": 0.8,
                },
                {
                    "obs_id": "no_rb",
                    "ra_deg": 200.0,
                    "dec_deg": 5.0,
                    "jd": 2459000.5,
                    "real_bogus": None,
                },
            ]
        }

    def test_closest_ranked_first(self):
        ranked = find_nearest_raw_observation.rank_observations(
            self._checkpoint(), (257.0809, -10.7456)
        )
        assert ranked[0]["obs_id"] == "close"
        assert ranked[0]["offset_arcsec"] < 2.0
        assert ranked[-1]["obs_id"] == "far"

    def test_empty_checkpoint(self):
        ranked = find_nearest_raw_observation.rank_observations({"observations": []}, (0.0, 0.0))
        assert ranked == []


class TestMainCLI:
    def test_main_prints_closest(self, tmp_path, capsys):
        checkpoint = {
            "observations": [
                {
                    "obs_id": "close",
                    "ra_deg": 257.0810,
                    "dec_deg": -10.7455,
                    "jd": 2459000.5,
                    "real_bogus": 0.75,
                }
            ]
        }
        path = tmp_path / "20220817.json"
        path.write_text(json.dumps(checkpoint))

        sys.argv = [
            "find_nearest_raw_observation.py",
            str(path),
            "--ref", "257.0809", "-10.7456",
        ]
        find_nearest_raw_observation.main()
        out = capsys.readouterr().out
        assert "Closest real observation: close" in out

    def test_main_handles_empty(self, tmp_path, capsys):
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"observations": []}))

        sys.argv = [
            "find_nearest_raw_observation.py",
            str(path),
            "--ref", "0", "0",
        ]
        find_nearest_raw_observation.main()
        out = capsys.readouterr().out
        assert "nothing to rank" in out

    def test_main_handles_missing_real_bogus(self, tmp_path, capsys):
        checkpoint = {
            "observations": [
                {
                    "obs_id": "no_rb",
                    "ra_deg": 1.0,
                    "dec_deg": 1.0,
                    "jd": 2459000.5,
                    "real_bogus": None,
                }
            ]
        }
        path = tmp_path / "night.json"
        path.write_text(json.dumps(checkpoint))

        sys.argv = ["find_nearest_raw_observation.py", str(path), "--ref", "1.0", "1.0"]
        find_nearest_raw_observation.main()
        out = capsys.readouterr().out
        assert "real_bogus=None" in out
