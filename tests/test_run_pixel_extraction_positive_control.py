"""Tests for Skills/run_pixel_extraction_positive_control.py.

Checkpoint fixtures reuse the same synthetic-tracklet construction already
proven to link in tests/test_run_archive_positive_control.py (consistent
solar-system motion rate, small Gaussian astrometric jitter) -- not a
hand-guessed observation set. No network calls anywhere here; these tests
exercise the real production preprocess()/link() chain end-to-end,
confirming the mission-gating bypass this script exists for actually
recovers a genuine tracklet when fed motion-consistent candidates.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "run_pixel_extraction_positive_control.py"
)
_spec = importlib.util.spec_from_file_location(
    "run_pixel_extraction_positive_control", _MODULE_PATH
)
run_pixel_extraction_positive_control = importlib.util.module_from_spec(_spec)
sys.modules["run_pixel_extraction_positive_control"] = run_pixel_extraction_positive_control
_spec.loader.exec_module(run_pixel_extraction_positive_control)


def _make_obs_dict(obs_id, jd, ra_deg, dec_deg, mag):
    """Deliberately mirrors Skills/convert_pixel_extraction_to_observations.py's
    real output shape: mission="ZTF", no field_id, no real_bogus -- this is
    exactly the "detect.py's ZTF path does not fit" case this script exists
    to handle."""
    return {
        "obs_id": obs_id,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "jd": jd,
        "mag": mag,
        "mag_err": 0.5,
        "filter_band": "r",
        "mission": "ZTF",
    }


def _write_two_night_checkpoints(out_dir: Path, seed: int = 42):
    """Two nights, one real motion-consistent moving-source pair plus noise
    singletons on each night -- the same synthetic-NEO generator pattern
    validated to link in Skills/injection_recovery.py's baseline."""
    rng = np.random.default_rng(seed)
    motion_arcsec_per_hr = 1.0
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    ra0, dec0 = 180.0, 0.0
    nights = ["20180809", "20180903"]

    for night_idx, night in enumerate(nights):
        jd_base = 2460000.5 + night_idx
        ra_base = ra0 + night_idx * dra_per_hr * 24
        real_obs = _make_obs_dict(
            f"n{night_idx}_real",
            jd_base,
            ra_base + rng.normal(0, 0.5 / 3600.0),
            dec0 + rng.normal(0, 0.5 / 3600.0),
            19.5,
        )
        # A handful of unrelated noise singletons scattered elsewhere in the
        # field, matching the real pixel-extraction pilot's output shape
        # (many candidates per night, only some of which are consistent).
        noise_obs = [
            _make_obs_dict(
                f"n{night_idx}_noise{i}",
                jd_base,
                ra0 + rng.uniform(-0.01, 0.01),
                dec0 + rng.uniform(-0.01, 0.01),
                20.0,
            )
            for i in range(5)
        ]
        state = {"kept_count": 1 + len(noise_obs), "observations": [real_obs, *noise_obs]}
        (out_dir / f"{night}.json").write_text(json.dumps(state, indent=2))
    return nights


def test_known_good_recovers_tracklet_from_motion_consistent_candidates(tmp_path):
    """known-good -> a real motion-consistent pair across 2 nights, mixed in
    with noise singletons, must still be recovered as a tracklet -- this is
    the actual thing this script's mission-gating bypass exists to enable."""
    nights = _write_two_night_checkpoints(tmp_path)
    report = run_pixel_extraction_positive_control.run_positive_control(
        nights, tmp_path, min_observations=2
    )
    assert report["n_tracklets_linked"] >= 1
    assert report["n_sources_preprocessed"] == 12  # 2 nights x 6 observations


def test_known_bad_pure_noise_forms_no_tracklet(tmp_path):
    """known-bad -> unrelated positions across 2 nights must not spuriously
    link into a tracklet. The two nights' clusters are placed several
    degrees apart (each internally jittered by only ~1 arcsec) so EVERY
    possible cross-night pair's separation is guaranteed, deterministically
    (not just by chance with this seed), to exceed link()'s 60 arcsec/hr x
    24h = 0.4 deg maximum tolerance -- this is exactly the combinatorial-
    pairing risk this project's own Gate Z3/Z6 evidence documents, made
    deterministic rather than seed-dependent."""
    rng = np.random.default_rng(7)
    nights = ["20180809", "20180903"]
    night_centers = [(180.0, 0.0), (190.0, 5.0)]  # several degrees apart
    for night_idx, (night, (ra_center, dec_center)) in enumerate(zip(nights, night_centers)):
        jd_base = 2460000.5 + night_idx
        obs = [
            _make_obs_dict(
                f"n{night_idx}_{i}",
                jd_base,
                ra_center + rng.normal(0, 1.0 / 3600.0),
                dec_center + rng.normal(0, 1.0 / 3600.0),
                20.0,
            )
            for i in range(5)
        ]
        (tmp_path / f"{night}.json").write_text(
            json.dumps({"kept_count": len(obs), "observations": obs})
        )
    report = run_pixel_extraction_positive_control.run_positive_control(
        nights, tmp_path, min_observations=2
    )
    assert report["n_tracklets_linked"] == 0


def test_missing_checkpoint_fails_loudly(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError, match="No checkpoint found"):
        run_pixel_extraction_positive_control.load_observations_from_checkpoints(
            ["20990101"], tmp_path
        )


def test_empty_observations_fails_loudly(tmp_path):
    import pytest

    (tmp_path / "20180809.json").write_text(json.dumps({"kept_count": 0, "observations": []}))
    with pytest.raises(ValueError, match="zero input observations"):
        run_pixel_extraction_positive_control.run_positive_control(
            ["20180809"], tmp_path, min_observations=2
        )


def test_cli_writes_report_when_out_given(tmp_path, monkeypatch, capsys):
    nights = _write_two_night_checkpoints(tmp_path)
    out_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pixel_extraction_positive_control.py",
            "--nights",
            *nights,
            "--checkpoint-dir",
            str(tmp_path),
            "--min-observations",
            "2",
            "--out",
            str(out_path),
        ],
    )
    run_pixel_extraction_positive_control.main()
    written = json.loads(out_path.read_text())
    assert written["n_tracklets_linked"] >= 1
    assert "Wrote" in capsys.readouterr().out
