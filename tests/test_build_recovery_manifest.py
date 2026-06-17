"""Tests for the T1-C recovery manifest builder Skill."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _load_module():
    """Load the Skill as a module so tests exercise the shipped script."""
    path = Path(__file__).resolve().parents[1] / "Skills" / "build_recovery_manifest.py"
    spec = importlib.util.spec_from_file_location("build_recovery_manifest", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sample_jds_are_evenly_spaced():
    """The manifest should sample the full planned run window."""
    module = _load_module()

    assert module._sample_jds(10.0, 14.0, 3) == [10.0, 12.0, 14.0]
    assert module._sample_jds(10.0, 14.0, 1) == [12.0]


def test_angular_sep_handles_identical_points():
    """A same-position sample should have zero angular separation."""
    module = _load_module()

    assert module._angular_sep_deg(251.0, -22.0, 251.0, -22.0) == 0.0


def test_build_manifest_filters_and_writes_expected_rows(tmp_path, monkeypatch):
    """Mocked providers should produce an audit-compatible expected-known JSON."""
    module = _load_module()
    output = tmp_path / "expected_known.json"

    monkeypatch.setattr(
        module,
        "fetch_mpc_known",
        lambda *_args, **_kwargs: [
            SimpleNamespace(obs_id="mpc_100001"),
            SimpleNamespace(obs_id="mpc_TOO_FAINT"),
        ],
    )

    def fake_horizons(designation, target_jds, force_refresh=False):
        """Return one recoverable object and one filtered-out faint object."""
        if designation == "100001":
            return [
                {"jd": target_jds[0], "ra_deg": 251.66, "dec_deg": -22.5, "mag": 19.8},
                {"jd": target_jds[-1], "ra_deg": 251.67, "dec_deg": -22.49, "mag": 20.1},
            ]
        return [
            {"jd": target_jds[0], "ra_deg": 251.66, "dec_deg": -22.5, "mag": 24.0}
        ]

    monkeypatch.setattr(module, "fetch_horizons_ephemeris", fake_horizons)

    summary = module.build_recovery_manifest(
        ra_deg=251.66,
        dec_deg=-22.5,
        radius_deg=3.5,
        start_jd=2461206.0,
        end_jd=2461209.0,
        output=output,
        max_objects=10,
        n_samples=2,
        min_samples=1,
        run_root=tmp_path / "runs",
    )

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert summary["n_region_candidates"] == 2
    assert summary["n_manifest_rows"] == 1
    assert rows[0]["designation"] == "100001"
    assert rows[0]["samples"][0]["ra_deg"] == 251.66
    assert rows[0]["source"] == "mpc_region_plus_jpl_horizons"
    assert summary["safety"]["no_external_submission"] is True
    assert Path(summary["checkpoint"]).exists()


def test_build_manifest_resumes_processed_designations(tmp_path, monkeypatch):
    """A second identical run should reuse checkpointed rows and skip Horizons."""
    module = _load_module()
    output = tmp_path / "expected_known.json"
    calls = {"horizons": 0}

    monkeypatch.setattr(
        module,
        "fetch_mpc_known",
        lambda *_args, **_kwargs: [SimpleNamespace(obs_id="mpc_100001")],
    )

    def fake_horizons(designation, target_jds, force_refresh=False):
        """Count provider calls so resume behavior is observable."""
        calls["horizons"] += 1
        return [{"jd": target_jds[0], "ra_deg": 251.66, "dec_deg": -22.5, "mag": 19.8}]

    monkeypatch.setattr(module, "fetch_horizons_ephemeris", fake_horizons)
    kwargs = {
        "ra_deg": 251.66,
        "dec_deg": -22.5,
        "radius_deg": 3.5,
        "start_jd": 2461206.0,
        "end_jd": 2461209.0,
        "output": output,
        "run_root": tmp_path / "runs",
    }

    module.build_recovery_manifest(**kwargs)
    module.build_recovery_manifest(**kwargs)

    assert calls["horizons"] == 1
    rows = json.loads(output.read_text(encoding="utf-8"))
    assert rows[0]["designation"] == "100001"
