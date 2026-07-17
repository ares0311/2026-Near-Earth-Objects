"""Tests for Skills/convert_pixel_extraction_to_observations.py.

Verifies the conversion from a pixel-extraction-pilot checkpoint into the
Observation checkpoint format Skills/run_archive_positive_control.py
already consumes -- an independent-oracle check (real Observation
constructor, not just presence of keys) that the produced dicts actually
build valid Observation objects.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "convert_pixel_extraction_to_observations.py"
)
_spec = importlib.util.spec_from_file_location(
    "convert_pixel_extraction_to_observations", _MODULE_PATH
)
convert_module = importlib.util.module_from_spec(_spec)
sys.modules["convert_pixel_extraction_to_observations"] = convert_module
_spec.loader.exec_module(convert_module)


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    pilot = {
        "pid": 585152193615,
        "sources": [
            {"x": 100, "y": 200, "ra_deg": 232.4, "dec_deg": -8.5, "peak_value": 150.0},
            {"x": 300, "y": 400, "ra_deg": 232.5, "dec_deg": -8.6, "peak_value": 60.0},
        ],
    }
    manifest = {
        "exposures": [
            {"pid": 585152193615, "obsjd": 2458339.6521991, "filtercode": "zr"}
        ]
    }
    pilot_path = tmp_path / "pixel_extraction_pilot.json"
    manifest_path = tmp_path / "motion_product_manifest.json"
    pilot_path.write_text(json.dumps(pilot))
    manifest_path.write_text(json.dumps(manifest))
    return pilot_path, manifest_path


def test_convert_produces_valid_observation_dicts(tmp_path):
    """Independent-oracle check: the produced dicts must actually construct
    real Observation objects, not just look plausible."""
    from schemas import Observation

    pilot_path, manifest_path = _write_fixture(tmp_path)
    result = convert_module.convert(pilot_path, manifest_path)

    assert result["kept_count"] == 2
    assert len(result["observations"]) == 2
    for obs_dict in result["observations"]:
        obs = Observation(**obs_dict)
        assert obs.mission == "ZTF"
        assert obs.filter_band == "r"
        assert obs.jd == 2458339.6521991
        assert obs.real_bogus is None
        assert obs.deep_real_bogus is None


def test_convert_derives_mag_proxy_from_peak_value(tmp_path):
    """The mag proxy must be a real, deterministic function of peak_value
    (brighter peak -> numerically lower/brighter proxy magnitude), not a
    fixed placeholder -- confirms it's actually derived, not fabricated."""
    pilot_path, manifest_path = _write_fixture(tmp_path)
    result = convert_module.convert(pilot_path, manifest_path)

    bright_obs, faint_obs = result["observations"]
    zp = convert_module._PLACEHOLDER_ZEROPOINT
    assert bright_obs["mag"] == zp - 2.5 * math.log10(150.0)
    assert faint_obs["mag"] == zp - 2.5 * math.log10(60.0)
    assert bright_obs["mag"] < faint_obs["mag"]  # brighter peak -> lower mag number
    assert 0 < bright_obs["mag"] <= 35  # must land inside preprocess()'s hard mag gate
    assert 0 < faint_obs["mag"] <= 35


def test_converted_observations_survive_preprocess_mag_gate(tmp_path):
    """Regression test for the real bug found running this converter live:
    the first version's zeropoint-free mag proxy produced negative
    magnitudes for every realistic peak_value, so preprocess()'s hard
    `0 < mag <= 35` gate silently rejected all 471/471 real observations.
    This calls the real preprocess() (not just checks the mag range in
    isolation) so a future regression here would be caught the same way
    this one was."""
    from preprocess import preprocess
    from schemas import Observation

    pilot_path, manifest_path = _write_fixture(tmp_path)
    result = convert_module.convert(pilot_path, manifest_path)
    observations = tuple(Observation(**o) for o in result["observations"])

    prep_result = preprocess(observations, apply_astrometry=False)
    assert prep_result.provenance.n_sources_out == len(observations)


def test_convert_obs_id_is_unique_per_source(tmp_path):
    pilot_path, manifest_path = _write_fixture(tmp_path)
    result = convert_module.convert(pilot_path, manifest_path)
    obs_ids = [o["obs_id"] for o in result["observations"]]
    assert len(obs_ids) == len(set(obs_ids))


def test_convert_handles_zero_or_negative_peak_value_without_math_error(tmp_path):
    """malformed-ish input -> must not crash: a zero/negative peak_value
    (should not occur in practice, but detection noise could in principle
    produce one) must not raise a math domain error from log10."""
    pilot = {
        "pid": 1,
        "sources": [{"x": 0, "y": 0, "ra_deg": 10.0, "dec_deg": 5.0, "peak_value": 0.0}],
    }
    manifest = {"exposures": [{"pid": 1, "obsjd": 2460000.0, "filtercode": "zg"}]}
    pilot_path = tmp_path / "pixel_extraction_pilot.json"
    manifest_path = tmp_path / "motion_product_manifest.json"
    pilot_path.write_text(json.dumps(pilot))
    manifest_path.write_text(json.dumps(manifest))

    result = convert_module.convert(pilot_path, manifest_path)
    assert math.isfinite(result["observations"][0]["mag"])


def test_cli_writes_named_checkpoint_file(tmp_path, monkeypatch, capsys):
    pilot_path, manifest_path = _write_fixture(tmp_path)
    out_dir = tmp_path / "checkpoints"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "convert_pixel_extraction_to_observations.py",
            "--pilot-checkpoint",
            str(pilot_path),
            "--manifest",
            str(manifest_path),
            "--night",
            "20180809",
            "--out-dir",
            str(out_dir),
        ],
    )
    exit_code = convert_module.main()
    assert exit_code == 0
    written = json.loads((out_dir / "20180809.json").read_text())
    assert written["kept_count"] == 2
    assert "wrote 2 observation(s)" in capsys.readouterr().out
