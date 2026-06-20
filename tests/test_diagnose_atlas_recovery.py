"""Offline tests for Skills/diagnose_atlas_recovery.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _load_skill() -> Any:
    """Load diagnose_atlas_recovery as a module for isolated testing."""
    skill_path = (
        Path(__file__).resolve().parents[1] / "Skills" / "diagnose_atlas_recovery.py"
    )
    spec = importlib.util.spec_from_file_location("diagnose_atlas_recovery", skill_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_checkpoint(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal ATLAS recovery checkpoint for testing."""
    sample_map: dict[str, Any] = {}
    for s in samples:
        key = f"{s['designation']}_{s['sample_index']}"
        sample_map[key] = s
    return {
        "params": {"window_days": 1.0, "min_recovered_samples": 3, "min_nights": 2},
        "last_stage": "done",
        "samples": sample_map,
        "tracklets": [],
    }


def _recovered_sample(
    designation: str,
    idx: int,
    jd: float = 2460001.5,
    ra: float = 180.0,
    dec: float = 10.0,
    n_usable: int = 5,
    n_raw: int = 8,
) -> dict[str, Any]:
    """Build a recovered sample dict."""
    return {
        "designation": designation,
        "sample_index": idx,
        "requested_jd": jd,
        "requested_ra_deg": ra,
        "requested_dec_deg": dec,
        "status": "recovered",
        "n_raw_observations": n_raw,
        "n_usable_observations": n_usable,
        "task_url": f"https://atlas.example.com/task/{idx}",
        "observations": [{"jd": jd + 0.01 * i} for i in range(n_usable)],
    }


def _not_recovered_sample(
    designation: str,
    idx: int,
    jd: float = 2460001.5,
    ra: float = 180.0,
    dec: float = 10.0,
) -> dict[str, Any]:
    """Build a not_recovered sample dict (zero detections from ATLAS)."""
    return {
        "designation": designation,
        "sample_index": idx,
        "requested_jd": jd,
        "requested_ra_deg": ra,
        "requested_dec_deg": dec,
        "status": "not_recovered",
        "n_raw_observations": 0,
        "n_usable_observations": 0,
        "task_url": f"https://atlas.example.com/task/{idx}",
        "observations": [],
    }


def _poll_exhausted_sample(
    designation: str,
    idx: int,
    jd: float = 2460001.5,
    ra: float = 180.0,
    dec: float = 10.0,
) -> dict[str, Any]:
    """Build a poll_exhausted sample dict (ATLAS task still running when polling stopped)."""
    return {
        "designation": designation,
        "sample_index": idx,
        "requested_jd": jd,
        "requested_ra_deg": ra,
        "requested_dec_deg": dec,
        "status": "poll_exhausted",
        "n_raw_observations": 0,
        "n_usable_observations": 0,
        "task_url": f"https://atlas.example.com/task/{idx}",
        "queuepos": 42,
        "observations": [],
    }


class TestLoadCheckpoint:
    """Test _load_checkpoint error handling."""

    def test_missing_checkpoint_raises_file_not_found(self, tmp_path: Path) -> None:
        mod = _load_skill()
        with pytest.raises(FileNotFoundError, match="No checkpoint found"):
            mod._load_checkpoint(tmp_path)

    def test_checkpoint_missing_samples_key_raises_value_error(
        self, tmp_path: Path
    ) -> None:
        mod = _load_skill()
        cp = tmp_path / "checkpoint.json"
        cp.write_text(json.dumps({"params": {}}), encoding="utf-8")
        with pytest.raises(ValueError, match="no 'samples' key"):
            mod._load_checkpoint(tmp_path)

    def test_valid_checkpoint_loads(self, tmp_path: Path) -> None:
        mod = _load_skill()
        cp_data = _make_checkpoint([_recovered_sample("481", 0)])
        (tmp_path / "checkpoint.json").write_text(
            json.dumps(cp_data), encoding="utf-8"
        )
        result = mod._load_checkpoint(tmp_path)
        assert "samples" in result


class TestDiagnoseRun:
    """Test diagnose_run output structure and per-designation stats."""

    def _write_cp(self, tmp_path: Path, samples: list[dict[str, Any]]) -> Path:
        cp = _make_checkpoint(samples)
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        return tmp_path

    def test_recovered_designation_marked_recovered(self, tmp_path: Path) -> None:
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [_recovered_sample("481", i) for i in range(4)],
        )
        result = mod.diagnose_run(tmp_path)
        entries = {e["designation"]: e for e in result["by_designation"]}
        assert entries["481"]["verdict"] == "RECOVERED"
        assert entries["481"]["n_recovered"] == 4

    def test_not_recovered_designation_zero_raw(self, tmp_path: Path) -> None:
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [_not_recovered_sample("2973", i) for i in range(4)],
        )
        result = mod.diagnose_run(tmp_path)
        entries = {e["designation"]: e for e in result["by_designation"]}
        assert entries["2973"]["verdict"] == "NOT_RECOVERED"
        assert entries["2973"]["n_not_recovered"] == 4
        assert entries["2973"]["n_recovered"] == 0

    def test_poll_exhausted_designation_verdict(self, tmp_path: Path) -> None:
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [_poll_exhausted_sample("2973", i) for i in range(3)],
        )
        result = mod.diagnose_run(tmp_path)
        entries = {e["designation"]: e for e in result["by_designation"]}
        assert entries["2973"]["verdict"] == "POLL_EXHAUSTED"
        assert entries["2973"]["n_poll_exhausted"] == 3

    def test_designation_filter(self, tmp_path: Path) -> None:
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [
                _recovered_sample("481", 0),
                _not_recovered_sample("2973", 0),
            ],
        )
        result = mod.diagnose_run(tmp_path, designation_filter="2973")
        assert len(result["by_designation"]) == 1
        assert result["by_designation"][0]["designation"] == "2973"

    def test_status_counts_aggregated(self, tmp_path: Path) -> None:
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [
                _recovered_sample("481", 0),
                _recovered_sample("481", 1),
                _not_recovered_sample("2973", 0),
                _poll_exhausted_sample("1950", 0),
            ],
        )
        result = mod.diagnose_run(tmp_path)
        assert result["status_counts"]["recovered"] == 2
        assert result["status_counts"]["not_recovered"] == 1
        assert result["status_counts"]["poll_exhausted"] == 1

    def test_sample_rows_include_jd_ra_dec(self, tmp_path: Path) -> None:
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [_recovered_sample("481", 0, jd=2460100.5, ra=90.0, dec=-5.0)],
        )
        result = mod.diagnose_run(tmp_path)
        sample = result["by_designation"][0]["samples"][0]
        assert abs(sample["jd"] - 2460100.5) < 0.001
        assert abs(sample["ra_deg"] - 90.0) < 0.001
        assert abs(sample["dec_deg"] - (-5.0)) < 0.001

    def test_mixed_object_run_summary(self, tmp_path: Path) -> None:
        """Simulates the prequalified run where 481/1950/2172 recover but 2973 does not."""
        mod = _load_skill()
        samples = (
            [_recovered_sample("481", i) for i in range(4)]
            + [_recovered_sample("1950", i) for i in range(4)]
            + [_recovered_sample("2172", i) for i in range(4)]
            + [_not_recovered_sample("2973", i) for i in range(3)]
        )
        self._write_cp(tmp_path, samples)
        result = mod.diagnose_run(tmp_path)
        assert result["n_designations"] == 4
        verdicts = {e["designation"]: e["verdict"] for e in result["by_designation"]}
        assert verdicts["481"] == "RECOVERED"
        assert verdicts["1950"] == "RECOVERED"
        assert verdicts["2172"] == "RECOVERED"
        assert verdicts["2973"] == "NOT_RECOVERED"

    def test_check_horizons_adds_position_fields(self, tmp_path: Path) -> None:
        """Horizons query result is attached to sample rows when --check-horizons is given."""
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [_not_recovered_sample("2973", 0, jd=2460001.5, ra=180.0, dec=10.0)],
        )
        fake_horizons = {"ra_deg": 180.5, "dec_deg": 10.2}
        with patch.object(mod, "_query_horizons_position", return_value=fake_horizons):
            result = mod.diagnose_run(tmp_path, check_horizons=True)
        sample = result["by_designation"][0]["samples"][0]
        assert "horizons_ra_deg" in sample
        assert "sep_from_horizons_arcsec" in sample
        assert sample["sep_from_horizons_arcsec"] is not None

    def test_check_horizons_none_on_failure(self, tmp_path: Path) -> None:
        """Horizons failure yields None position fields — diagnostic still completes."""
        mod = _load_skill()
        self._write_cp(
            tmp_path,
            [_not_recovered_sample("2973", 0)],
        )
        with patch.object(mod, "_query_horizons_position", return_value=None):
            result = mod.diagnose_run(tmp_path, check_horizons=True)
        sample = result["by_designation"][0]["samples"][0]
        assert sample["horizons_ra_deg"] is None
        assert sample["sep_from_horizons_arcsec"] is None


class TestSepDistance:
    """Test great-circle separation helper."""

    def test_same_position_zero_separation(self) -> None:
        mod = _load_skill()
        sep = mod._sep_distance_arcsec(90.0, 10.0, 90.0, 10.0)
        assert sep == pytest.approx(0.0, abs=1e-9)

    def test_one_arcsec_in_ra(self) -> None:
        mod = _load_skill()
        # 1 arcsec in RA at declination 0 = 1/3600 degrees / cos(0) = 1/3600 deg
        delta_ra = 1.0 / 3600.0
        sep = mod._sep_distance_arcsec(0.0, 0.0, delta_ra, 0.0)
        assert sep == pytest.approx(1.0, abs=0.01)

    def test_one_arcsec_in_dec(self) -> None:
        mod = _load_skill()
        delta_dec = 1.0 / 3600.0
        sep = mod._sep_distance_arcsec(0.0, 0.0, 0.0, delta_dec)
        assert sep == pytest.approx(1.0, abs=0.01)


class TestSampleStatusSymbol:
    """Test status → symbol mapping."""

    def test_recovered_symbol(self) -> None:
        mod = _load_skill()
        assert mod._sample_status_symbol("recovered") == "✓"

    def test_not_recovered_symbol(self) -> None:
        mod = _load_skill()
        assert mod._sample_status_symbol("not_recovered") == "✗"

    def test_poll_exhausted_symbol(self) -> None:
        mod = _load_skill()
        assert mod._sample_status_symbol("poll_exhausted") == "?"

    def test_unknown_status_returns_string(self) -> None:
        mod = _load_skill()
        # Unknown status passes through as-is
        result = mod._sample_status_symbol("bogus_status")
        assert result == "bogus_status"


class TestPrintHumanReadable:
    """Test that _print_human_readable produces output without errors."""

    def test_prints_without_exception(self, tmp_path: Path, capsys: Any) -> None:
        mod = _load_skill()
        samples = (
            [_recovered_sample("481", i) for i in range(3)]
            + [_not_recovered_sample("2973", i) for i in range(3)]
        )
        cp = _make_checkpoint(samples)
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        result = mod.diagnose_run(tmp_path)
        mod._print_human_readable(result)
        captured = capsys.readouterr()
        assert "481" in captured.out
        assert "2973" in captured.out
        assert "NOT_RECOVERED" in captured.out

    def test_poll_exhausted_diagnosis_message(self, tmp_path: Path, capsys: Any) -> None:
        mod = _load_skill()
        cp = _make_checkpoint([_poll_exhausted_sample("2973", 0)])
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        result = mod.diagnose_run(tmp_path)
        mod._print_human_readable(result)
        captured = capsys.readouterr()
        assert "Poll-exhausted" in captured.out or "poll_exhausted" in captured.out.lower()

    def test_zero_raw_diagnosis_message(self, tmp_path: Path, capsys: Any) -> None:
        mod = _load_skill()
        cp = _make_checkpoint([_not_recovered_sample("2973", 0)])
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        result = mod.diagnose_run(tmp_path)
        mod._print_human_readable(result)
        captured = capsys.readouterr()
        assert "0 raw observations" in captured.out

    def test_all_recovered_no_unrecovered_message(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        mod = _load_skill()
        cp = _make_checkpoint([_recovered_sample("481", 0)])
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        result = mod.diagnose_run(tmp_path)
        mod._print_human_readable(result)
        captured = capsys.readouterr()
        assert "All designations have at least one recovered sample" in captured.out


class TestMainEntrypoint:
    """Smoke test main() with synthetic checkpoint."""

    def test_main_json_output(self, tmp_path: Path, capsys: Any) -> None:
        mod = _load_skill()
        cp = _make_checkpoint(
            [_recovered_sample("481", 0), _not_recovered_sample("2973", 0)]
        )
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        test_argv = ["diagnose_atlas_recovery.py", "--run-dir", str(tmp_path), "--json"]
        with patch("sys.argv", test_argv):
            mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["run_id"] == tmp_path.name
        assert len(parsed["by_designation"]) == 2

    def test_main_human_output(self, tmp_path: Path, capsys: Any) -> None:
        mod = _load_skill()
        cp = _make_checkpoint([_recovered_sample("481", 0)])
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        test_argv = ["diagnose_atlas_recovery.py", "--run-dir", str(tmp_path)]
        with patch("sys.argv", test_argv):
            mod.main()
        captured = capsys.readouterr()
        assert "481" in captured.out

    def test_main_designation_filter(self, tmp_path: Path, capsys: Any) -> None:
        mod = _load_skill()
        cp = _make_checkpoint(
            [_recovered_sample("481", 0), _not_recovered_sample("2973", 0)]
        )
        (tmp_path / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")
        test_argv = [
            "diagnose_atlas_recovery.py",
            "--run-dir", str(tmp_path),
            "--designation", "2973",
            "--json",
        ]
        with patch("sys.argv", test_argv):
            mod.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert len(parsed["by_designation"]) == 1
        assert parsed["by_designation"][0]["designation"] == "2973"
