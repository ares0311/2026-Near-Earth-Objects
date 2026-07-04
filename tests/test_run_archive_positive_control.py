"""Tests for Skills/run_archive_positive_control.py (Gate Z3 known-object
positive control loader/runner).

Checkpoint fixtures reuse the exact synthetic-tracklet construction already
proven to link successfully in Skills/injection_recovery.py's baseline
(2 observations/night, 1 hour apart, small Gaussian astrometric jitter,
consistent solar-system motion rate) -- not a hand-guessed observation set.
No network calls are made anywhere in this script; these tests exercise the
real production preprocess()/detect()/link() chain end-to-end.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "run_archive_positive_control.py"
)
_spec = importlib.util.spec_from_file_location("run_archive_positive_control", _MODULE_PATH)
run_archive_positive_control = importlib.util.module_from_spec(_spec)
sys.modules["run_archive_positive_control"] = run_archive_positive_control
_spec.loader.exec_module(run_archive_positive_control)


def _make_obs_dict(obs_id, jd, ra_deg, dec_deg, mag, real_bogus=0.92):
    return {
        "obs_id": obs_id,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "jd": jd,
        "mag": mag,
        "mag_err": 0.05,
        "filter_band": "r",
        "mission": "ZTF",
        "real_bogus": real_bogus,
        "field_id": "377",
        "limiting_mag": 20.0,
    }


def _write_two_night_checkpoints(out_dir: Path, seed: int = 42):
    """Two real-schema checkpoint files (matching exactly what
    Skills/ztf_alert_archive_ingest.py writes) built from the same
    synthetic-NEO generator already validated to link in
    Skills/injection_recovery.py's baseline (n=200 -> 100% link rate)."""
    rng = np.random.default_rng(seed)
    motion_arcsec_per_hr = 1.0
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    ra0, dec0 = 180.0, 0.0
    nights = ["20180809", "20180903"]

    for night_idx, night in enumerate(nights):
        jd_base = 2460000.5 + night_idx
        ra_base = ra0 + night_idx * dra_per_hr * 24
        obs_a = _make_obs_dict(
            f"n{night_idx}a", jd_base,
            ra_base + rng.normal(0, 0.5 / 3600.0), dec0 + rng.normal(0, 0.5 / 3600.0), 19.5,
        )
        obs_b = _make_obs_dict(
            f"n{night_idx}b", jd_base + 1 / 24,
            ra_base + dra_per_hr + rng.normal(0, 0.5 / 3600.0),
            dec0 + rng.normal(0, 0.5 / 3600.0), 19.5,
        )
        state = {
            "night": night,
            "filename": f"ztf_public_{night}.tar.gz",
            "scanned_count": 100,
            "kept_count": 2,
            "observations": [obs_a, obs_b],
        }
        (out_dir / f"{night}.json").write_text(json.dumps(state, indent=2))
    return nights


class TestLoadObservationsFromCheckpoints:
    def test_loads_real_observations(self, tmp_path):
        nights = _write_two_night_checkpoints(tmp_path)
        obs = run_archive_positive_control.load_observations_from_checkpoints(nights, tmp_path)
        assert len(obs) == 4
        assert all(o.mission == "ZTF" for o in obs)

    def test_missing_checkpoint_fails_closed(self, tmp_path):
        _write_two_night_checkpoints(tmp_path)  # only 20180809/20180903 exist
        try:
            run_archive_positive_control.load_observations_from_checkpoints(
                ["20180809", "99999999"], tmp_path
            )
            raise AssertionError("expected FileNotFoundError")
        except FileNotFoundError as exc:
            assert "99999999" in str(exc)


class TestRunPositiveControl:
    def test_full_chain_runs_and_reports(self, tmp_path):
        nights = _write_two_night_checkpoints(tmp_path)
        report = run_archive_positive_control.run_positive_control(nights, tmp_path)
        assert report["nights"] == nights
        assert report["n_observations_loaded"] == 4
        assert "n_tracklets_linked" in report
        assert isinstance(report["tracklets"], list)

    def test_min_observations_override_affects_linking(self, tmp_path):
        """Regression coverage for the real finding: link()'s default
        min_observations=3 can reject a genuine 2-night tracklet with only
        1-2 observations contributed per night; --min-observations 2 must
        be able to recover it."""
        nights = _write_two_night_checkpoints(tmp_path)
        default_report = run_archive_positive_control.run_positive_control(nights, tmp_path)
        relaxed_report = run_archive_positive_control.run_positive_control(
            nights, tmp_path, min_observations=2
        )
        assert default_report["n_tracklets_linked"] == 0
        assert relaxed_report["n_tracklets_linked"] > 0

    def test_build_review_packets_produces_real_scored_neo_dicts(self, tmp_path):
        """Gate Z6 no-submission package drill: build_review_packets=True
        must run every linked tracklet through the real
        classify -> fit_orbit -> score -> process_alert(dry_run=True) chain
        and include the resulting ScoredNEO dicts in the report. Never
        submits externally (process_alert is always called with
        dry_run=True in this path)."""
        nights = _write_two_night_checkpoints(tmp_path)
        report = run_archive_positive_control.run_positive_control(
            nights, tmp_path, min_observations=2, build_review_packets=True
        )
        assert report["n_tracklets_linked"] > 0
        assert "review_packets" in report
        assert len(report["review_packets"]) == report["n_tracklets_linked"]
        packet = report["review_packets"][0]
        assert "hazard" in packet
        assert "posterior" in packet
        assert "metadata" in packet

    def test_build_review_packets_false_omits_key_by_default(self, tmp_path):
        nights = _write_two_night_checkpoints(tmp_path)
        report = run_archive_positive_control.run_positive_control(nights, tmp_path)
        assert "review_packets" not in report

    def test_empty_night_raises(self, tmp_path):
        (tmp_path / "20180809.json").write_text(
            json.dumps({"night": "20180809", "kept_count": 0, "observations": []})
        )
        (tmp_path / "20180903.json").write_text(
            json.dumps({"night": "20180903", "kept_count": 0, "observations": []})
        )
        try:
            run_archive_positive_control.run_positive_control(
                ["20180809", "20180903"], tmp_path
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "zero input observations" in str(exc)
