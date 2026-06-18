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


def test_label_pool_designations_unpack_numeric_labels(tmp_path):
    """Fallback label-pool designations should be usable by Horizons."""
    module = _load_module()
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "designation,neo_class,h_mag,source\n"
        "00433,neo_candidate,10.4,MPC_NEA\n"
        "2014 AA,neo_candidate,20.0,MPC_NEA\n",
        encoding="utf-8",
    )

    assert module._designations_from_label_pool(labels, 10) == ["433", "2014 AA"]


def test_build_manifest_falls_back_when_mpc_region_api_missing(tmp_path, monkeypatch):
    """The live manifest path must survive astroquery MPC region API drift."""
    module = _load_module()
    output = tmp_path / "expected_known.json"
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "designation,neo_class,h_mag,source\n"
        "00433,neo_candidate,10.4,MPC_NEA\n",
        encoding="utf-8",
    )

    def missing_region_api(*_args, **_kwargs):
        """Simulate the installed astroquery version lacking region search."""
        raise AttributeError("'MPCClass' object has no attribute 'query_objects_in_region'")

    monkeypatch.setattr(module, "fetch_mpc_known", missing_region_api)
    monkeypatch.setattr(
        module,
        "fetch_horizons_ephemeris",
        lambda designation, target_jds, force_refresh=False: [
            {"jd": target_jds[0], "ra_deg": 251.66, "dec_deg": -22.5, "mag": 19.8}
        ],
    )

    summary = module.build_recovery_manifest(
        ra_deg=251.66,
        dec_deg=-22.5,
        radius_deg=3.5,
        start_jd=2461206.0,
        end_jd=2461209.0,
        output=output,
        label_pool=labels,
        fallback_scan_limit=10,
        run_root=tmp_path / "runs",
    )

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert summary["candidate_source"] == "committed_training_labels_plus_jpl_horizons"
    assert summary["n_manifest_rows"] == 1
    assert rows[0]["designation"] == "433"
    assert rows[0]["source"] == "committed_training_labels_plus_jpl_horizons"


def test_auto_center_selects_dense_projected_field(monkeypatch):
    """Auto-centering should choose the densest approximate MPC sky cluster."""
    module = _load_module()
    rows = [
        {"number": 1},
        {"number": 2},
        {"number": 3},
        {"number": 4},
    ]
    positions = {
        1: (10.0, 0.0),
        2: (10.5, 0.2),
        3: (11.0, -0.1),
        4: (80.0, 20.0),
    }

    monkeypatch.setattr(module, "_fetch_mpc_orbit_rows", lambda _limit, neo_only=True: rows)
    monkeypatch.setattr(
        module,
        "_rough_ra_dec_from_mpc_orbit",
        lambda row, _jd: positions[row["number"]],
    )

    ra_deg, dec_deg, designations = module._auto_center_designations_from_mpc_list(
        target_jd=2461208.0,
        radius_deg=3.5,
        list_limit=4,
        max_objects=10,
    )

    assert (ra_deg, dec_deg) == (10.0, 0.0)
    assert designations == ["1", "2", "3"]


def test_auto_center_can_include_all_asteroids(monkeypatch):
    """The T1-C recovery selector can opt into dense non-NEO known objects."""
    module = _load_module()
    seen: list[bool] = []
    rows = [{"number": 1}, {"number": 2}]
    positions = {1: (20.0, 5.0), 2: (21.0, 5.0)}

    def fake_rows(_limit, neo_only=True):
        seen.append(neo_only)
        return rows

    monkeypatch.setattr(module, "_fetch_mpc_orbit_rows", fake_rows)
    monkeypatch.setattr(
        module,
        "_rough_ra_dec_from_mpc_orbit",
        lambda row, _jd: positions[row["number"]],
    )

    _ra_deg, _dec_deg, designations = module._auto_center_designations_from_mpc_list(
        target_jd=2461208.0,
        radius_deg=3.5,
        list_limit=2,
        max_objects=10,
        neo_only=False,
    )

    assert seen == [False]
    assert designations == ["1", "2"]


def test_fixed_field_mpc_list_preselection_filters_by_radius(monkeypatch):
    """Fixed-field preselection should preserve a ZTF-available requested field."""
    module = _load_module()
    rows = [{"number": 1}, {"number": 2}, {"number": 3}]
    positions = {
        1: (30.0, 0.0),
        2: (31.0, 0.5),
        3: (80.0, 20.0),
    }
    seen: list[bool] = []

    def fake_rows(_limit, neo_only=True):
        seen.append(neo_only)
        return rows

    monkeypatch.setattr(module, "_fetch_mpc_orbit_rows", fake_rows)
    monkeypatch.setattr(
        module,
        "_rough_ra_dec_from_mpc_orbit",
        lambda row, _jd: positions[row["number"]],
    )

    designations = module._designations_from_mpc_list_field(
        ra_deg=30.0,
        dec_deg=0.0,
        radius_deg=3.5,
        target_jd=2461208.0,
        list_limit=3,
        max_objects=10,
        neo_only=False,
    )

    assert seen == [False]
    assert designations == ["1", "2"]
