"""Offline tests for fetch_atlas_data.py batch mode and input validation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_skill() -> Any:
    """Load the fetch_atlas_data Skill directly for isolated testing."""
    skill_path = Path(__file__).resolve().parents[1] / "Skills" / "fetch_atlas_data.py"
    spec = importlib.util.spec_from_file_location("fetch_atlas_data", skill_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_audit_skill() -> Any:
    """Load the audit_real_run Skill directly for contract testing."""
    skill_path = Path(__file__).resolve().parents[1] / "Skills" / "audit_real_run.py"
    spec = importlib.util.spec_from_file_location("audit_real_run", skill_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_positions_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a minimal positions CSV for batch tests."""
    import csv

    fieldnames = list(rows[0]) if rows else ["ra", "dec", "start_jd", "end_jd"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fake_observation(ra: float, dec: float) -> SimpleNamespace:
    """Create a minimal fake ATLAS observation."""
    return SimpleNamespace(
        obs_id=f"ATLAS:{ra:.1f}:{dec:.1f}",
        ra_deg=ra,
        dec_deg=dec,
        jd=2460000.0,
        mag=18.5,
        mag_err=0.05,
        filter_band="o",
        mission="ATLAS",
    )


def _fake_observation_at(ra: float, dec: float, jd: float, mag: float = 18.5) -> SimpleNamespace:
    """Create a fake ATLAS observation at a requested JD."""
    return SimpleNamespace(
        obs_id=f"ATLAS:{ra:.3f}:{dec:.3f}:{jd:.3f}",
        ra_deg=ra,
        dec_deg=dec,
        jd=jd,
        mag=mag,
        mag_err=0.05,
        filter_band="o",
        mission="ATLAS",
    )


def _fake_fetcher(
    ra_deg: float,
    dec_deg: float,
    start_jd: float,
    end_jd: float,
    atlas_token: str | None = None,
    force_refresh: bool = False,
) -> list[SimpleNamespace]:
    """Return one synthetic observation per position without network access."""
    return [_fake_observation(ra_deg, dec_deg)]


def _write_expected_manifest(path: Path) -> None:
    """Write a small expected-known manifest with multi-night samples."""
    path.write_text(
        json.dumps(
            [
                {
                    "designation": "100001",
                    "samples": [
                        {"ra_deg": 10.0, "dec_deg": 5.0, "jd": 2460000.0},
                        {"ra_deg": 10.1, "dec_deg": 5.1, "jd": 2460002.0},
                        {"ra_deg": 10.2, "dec_deg": 5.2, "jd": 2460004.0},
                    ],
                    "tolerance_arcsec": 5.0,
                    "tolerance_days": 0.02,
                    "min_samples": 3,
                }
            ]
        ),
        encoding="utf-8",
    )


def test_load_positions_csv_accepts_minimal_csv(tmp_path: Path) -> None:
    """A CSV with the four required columns must load without error."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    _write_positions_csv(
        csv_path,
        [{"ra": 10.5, "dec": -5.2, "start_jd": 2460000, "end_jd": 2460030}],
    )

    positions = module._load_positions_csv(csv_path)

    assert len(positions) == 1
    assert positions[0]["ra"] == pytest.approx(10.5)
    assert positions[0]["label"] == "0"


def test_load_positions_csv_uses_label_column(tmp_path: Path) -> None:
    """An optional label column must become the output filename stem."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    _write_positions_csv(
        csv_path,
        [{"ra": 10.5, "dec": -5.2, "start_jd": 2460000, "end_jd": 2460030, "label": "target_A"}],
    )

    positions = module._load_positions_csv(csv_path)

    assert positions[0]["label"] == "target_A"


def test_load_positions_csv_rejects_empty_file(tmp_path: Path) -> None:
    """An empty CSV must be rejected before any fetch is attempted."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    csv_path.write_text("ra,dec,start_jd,end_jd\n", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        module._load_positions_csv(csv_path)


def test_load_positions_csv_rejects_missing_columns(tmp_path: Path) -> None:
    """Missing required columns must fail with a clear message."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    csv_path.write_text("ra,dec\n10.0,-5.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns"):
        module._load_positions_csv(csv_path)


def test_run_batch_sequential_writes_per_position_json(tmp_path: Path) -> None:
    """Sequential batch run must write one JSON file per position."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    out_dir = tmp_path / "out"
    _write_positions_csv(
        csv_path,
        [
            {"ra": 10.0, "dec": -5.0, "start_jd": 2460000, "end_jd": 2460030, "label": "pos_A"},
            {"ra": 20.0, "dec": +3.0, "start_jd": 2460000, "end_jd": 2460030, "label": "pos_B"},
        ],
    )

    summary = module.run_batch(
        csv_path,
        out_dir,
        atlas_token=None,
        force_refresh=False,
        resume=False,
        workers=1,
        fetcher=_fake_fetcher,
        print_fn=lambda *a, **kw: None,
    )

    assert summary["total"] == 2
    assert summary["fetched"] == 2
    assert summary["failed"] == 0
    assert (out_dir / "pos_A.json").exists()
    assert (out_dir / "pos_B.json").exists()
    data = json.loads((out_dir / "pos_A.json").read_text(encoding="utf-8"))
    assert data["n_obs"] == 1
    assert data["ra_deg"] == pytest.approx(10.0)


def test_run_batch_parallel_writes_all_positions(tmp_path: Path) -> None:
    """Parallel batch run must write the same output as sequential mode."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    out_dir = tmp_path / "out"
    rows = [
        {"ra": float(i), "dec": 0.0, "start_jd": 2460000, "end_jd": 2460030, "label": f"p{i}"}
        for i in range(6)
    ]
    _write_positions_csv(csv_path, rows)

    summary = module.run_batch(
        csv_path,
        out_dir,
        atlas_token=None,
        force_refresh=False,
        resume=False,
        workers=4,
        fetcher=_fake_fetcher,
        print_fn=lambda *a, **kw: None,
    )

    assert summary["total"] == 6
    assert summary["fetched"] == 6
    assert summary["failed"] == 0
    for i in range(6):
        assert (out_dir / f"p{i}.json").exists()


def test_run_batch_resume_skips_existing_output(tmp_path: Path) -> None:
    """Resume must skip positions whose output file already exists."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _write_positions_csv(
        csv_path,
        [
            {"ra": 10.0, "dec": -5.0, "start_jd": 2460000, "end_jd": 2460030, "label": "done"},
            {"ra": 20.0, "dec": +3.0, "start_jd": 2460000, "end_jd": 2460030, "label": "todo"},
        ],
    )
    # Pre-create the first position's output so resume skips it.
    (out_dir / "done.json").write_text('{"n_obs": 99}', encoding="utf-8")
    calls: list[float] = []

    def tracking_fetcher(**kwargs: Any) -> list[SimpleNamespace]:
        calls.append(kwargs["ra_deg"])
        return [_fake_observation(kwargs["ra_deg"], kwargs["dec_deg"])]

    summary = module.run_batch(
        csv_path,
        out_dir,
        atlas_token=None,
        force_refresh=False,
        resume=True,
        workers=1,
        fetcher=tracking_fetcher,
        print_fn=lambda *a, **kw: None,
    )

    assert summary["skipped"] == 1
    assert summary["fetched"] == 1
    assert calls == [pytest.approx(20.0)]
    # The pre-existing file must not be overwritten.
    assert json.loads((out_dir / "done.json").read_text())["n_obs"] == 99


def test_run_batch_records_failed_positions(tmp_path: Path) -> None:
    """Fetch failures must be counted in the summary without halting the batch."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    out_dir = tmp_path / "out"
    _write_positions_csv(
        csv_path,
        [
            {"ra": 10.0, "dec": -5.0, "start_jd": 2460000, "end_jd": 2460030, "label": "ok"},
            {"ra": 99.0, "dec": +0.0, "start_jd": 2460000, "end_jd": 2460030, "label": "bad"},
        ],
    )

    def partial_fetcher(
        ra_deg: float, dec_deg: float, **kwargs: Any
    ) -> list[SimpleNamespace]:
        if ra_deg == pytest.approx(99.0):
            raise ConnectionError("simulated ATLAS timeout")
        return [_fake_observation(ra_deg, dec_deg)]

    summary = module.run_batch(
        csv_path,
        out_dir,
        atlas_token=None,
        force_refresh=False,
        resume=False,
        workers=1,
        fetcher=partial_fetcher,
        print_fn=lambda *a, **kw: None,
    )

    assert summary["fetched"] == 1
    assert summary["failed"] == 1
    assert (out_dir / "ok.json").exists()
    assert not (out_dir / "bad.json").exists()


def test_run_batch_workers_validation_rejects_zero(tmp_path: Path) -> None:
    """workers=0 must be rejected before touching the CSV."""
    module = _load_skill()
    csv_path = tmp_path / "positions.csv"
    out_dir = tmp_path / "out"
    _write_positions_csv(
        csv_path,
        [{"ra": 10.0, "dec": -5.0, "start_jd": 2460000, "end_jd": 2460030}],
    )

    with pytest.raises(ValueError, match="workers"):
        module.run_batch(
            csv_path,
            out_dir,
            atlas_token=None,
            force_refresh=False,
            resume=False,
            workers=0,
            fetcher=_fake_fetcher,
        )


def test_run_atlas_recovery_writes_audit_compatible_packet(tmp_path: Path) -> None:
    """ATLAS recovery mode must write checkpoint, run summary, and audit manifest."""
    module = _load_skill()
    expected = tmp_path / "expected_known.json"
    _write_expected_manifest(expected)
    run_root = tmp_path / "runs"
    calls: list[tuple[float, float, float, float]] = []

    def recovery_fetcher(
        ra_deg: float,
        dec_deg: float,
        start_jd: float,
        end_jd: float,
        **kwargs: Any,
    ) -> list[SimpleNamespace]:
        calls.append((ra_deg, dec_deg, start_jd, end_jd))
        center_jd = (start_jd + end_jd) / 2.0
        # Return zero coordinates to verify forced-position substitution.
        return [_fake_observation_at(0.0, 0.0, center_jd)]

    summary = module.run_atlas_recovery(
        expected_known=expected,
        run_root=run_root,
        atlas_token=None,
        force_refresh=False,
        resume=False,
        workers=1,
        window_days=0.05,
        min_recovered_samples=3,
        min_nights=2,
        max_mag=21.5,
        max_objects=None,
        fetcher=recovery_fetcher,
        print_fn=lambda *a, **kw: None,
    )

    run_dir = Path(summary["run_dir"])
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    audit_manifest = json.loads(
        (run_dir / "expected_known_atlas_forced.json").read_text(encoding="utf-8")
    )

    assert len(calls) == 3
    assert summary["n_tracklets"] == 1
    assert summary["n_recovered_samples"] == 3
    assert checkpoint["last_stage"] == "atlas_forced_recovery"
    assert checkpoint["partial_results"][0]["alert_pathway"] == "known_object"
    assert checkpoint["tracklets"][0]["object_id"] == "atlas_recovery:100001"
    assert checkpoint["tracklets"][0]["observations"][0]["ra_deg"] == pytest.approx(10.0)
    assert audit_manifest[0]["source"] == "atlas_forced_photometry_fallback"
    assert audit_manifest[0]["tolerance_days"] == pytest.approx(0.05)
    assert summary["safety"]["no_external_submission"] is True

    audit = _load_audit_skill().build_audit_packet(
        run_dir,
        run_dir / "expected_known_atlas_forced.json",
    )
    assert audit["known_object_recovery_gate"]["status"] == "evaluated"
    assert audit["known_object_recovery_gate"]["passed"] is True
    assert audit["production_promotion_allowed"] is False


def test_run_atlas_recovery_fails_closed_on_sparse_samples(tmp_path: Path) -> None:
    """Sparse ATLAS evidence must not emit a recovery tracklet."""
    module = _load_skill()
    expected = tmp_path / "expected_known.json"
    _write_expected_manifest(expected)
    calls = 0

    def sparse_fetcher(
        ra_deg: float,
        dec_deg: float,
        start_jd: float,
        end_jd: float,
        **kwargs: Any,
    ) -> list[SimpleNamespace]:
        nonlocal calls
        calls += 1
        center_jd = (start_jd + end_jd) / 2.0
        if calls == 1:
            return [_fake_observation_at(ra_deg, dec_deg, center_jd)]
        return []

    summary = module.run_atlas_recovery(
        expected_known=expected,
        run_root=tmp_path / "runs",
        atlas_token=None,
        force_refresh=False,
        resume=False,
        workers=1,
        window_days=0.05,
        min_recovered_samples=3,
        min_nights=2,
        max_mag=21.5,
        max_objects=None,
        fetcher=sparse_fetcher,
        print_fn=lambda *a, **kw: None,
    )

    checkpoint = json.loads((Path(summary["run_dir"]) / "checkpoint.json").read_text())
    assert summary["n_recovered_samples"] == 1
    assert summary["n_tracklets"] == 0
    assert checkpoint["tracklets"] == []


def test_run_atlas_recovery_checkpoints_polling_task_before_interrupt(tmp_path: Path) -> None:
    """A killed ATLAS queue wait must leave a resumable task URL in the checkpoint."""
    module = _load_skill()
    expected = tmp_path / "expected_known.json"
    _write_expected_manifest(expected)

    def interrupted_fetcher(
        ra_deg: float,
        dec_deg: float,
        start_jd: float,
        end_jd: float,
        **kwargs: Any,
    ) -> list[SimpleNamespace]:
        kwargs["progress_callback"](
            {
                "event": "queued",
                "url": "https://fake-atlas/task/queued/",
                "queuepos": 42,
            }
        )
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        module.run_atlas_recovery(
            expected_known=expected,
            run_root=tmp_path / "runs",
            atlas_token=None,
            force_refresh=True,
            resume=True,
            workers=1,
            window_days=0.05,
            min_recovered_samples=3,
            min_nights=2,
            max_mag=21.5,
            max_objects=None,
            max_polls=2,
            poll_interval_seconds=0.0,
            fetcher=interrupted_fetcher,
            print_fn=lambda *a, **kw: None,
        )

    checkpoints = list((tmp_path / "runs").glob("atlas_recovery_*/checkpoint.json"))
    assert len(checkpoints) == 1
    checkpoint = json.loads(checkpoints[0].read_text(encoding="utf-8"))
    sample_state = next(iter(checkpoint["samples"].values()))
    assert sample_state["status"] == "polling"
    assert sample_state["task_url"] == "https://fake-atlas/task/queued/"
    assert sample_state["queuepos"] == 42


def test_run_atlas_recovery_resumes_existing_task_url_with_force_refresh(tmp_path: Path) -> None:
    """resume + force_refresh must reuse queued ATLAS tasks instead of starting over."""
    module = _load_skill()
    expected = tmp_path / "expected_known.json"
    _write_expected_manifest(expected)
    rows = module._load_expected_known_manifest(expected)
    samples = [sample for row in rows for sample in module._manifest_samples(row)]
    params = {
        "expected_known": str(expected),
        "n_manifest_rows": 1,
        "n_samples": 3,
        "window_days": 0.05,
        "min_recovered_samples": 3,
        "min_nights": 2,
        "max_mag": 21.5,
        "max_polls": 2,
        "poll_interval_seconds": 0.0,
        "max_objects": None,
    }
    run_dir = tmp_path / "runs" / f"atlas_recovery_{module._param_key(params)}"
    first_key = module._recovery_sample_key(samples[0])
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "params": params,
                "last_stage": "atlas_forced_recovery_polling",
                "tracklets": [],
                "partial_results": [],
                "samples": {
                    first_key: {
                        "designation": "100001",
                        "sample_index": 0,
                        "requested_ra_deg": 10.0,
                        "requested_dec_deg": 5.0,
                        "requested_jd": 2460000.0,
                        "window_days": 0.05,
                        "status": "polling",
                        "task_url": "https://fake-atlas/task/existing/",
                        "queuepos": 9,
                        "n_raw_observations": 0,
                        "n_usable_observations": 0,
                        "observations": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    task_urls: list[str | None] = []

    def recovery_fetcher(
        ra_deg: float,
        dec_deg: float,
        start_jd: float,
        end_jd: float,
        **kwargs: Any,
    ) -> list[SimpleNamespace]:
        task_urls.append(kwargs.get("task_url"))
        center_jd = (start_jd + end_jd) / 2.0
        return [_fake_observation_at(ra_deg, dec_deg, center_jd)]

    messages: list[str] = []
    summary = module.run_atlas_recovery(
        expected_known=expected,
        run_root=tmp_path / "runs",
        atlas_token=None,
        force_refresh=True,
        resume=True,
        workers=1,
        window_days=0.05,
        min_recovered_samples=3,
        min_nights=2,
        max_mag=21.5,
        max_objects=None,
        max_polls=2,
        poll_interval_seconds=0.0,
        fetcher=recovery_fetcher,
        print_fn=messages.append,
    )

    assert task_urls[0] == "https://fake-atlas/task/existing/"
    assert task_urls[1:] == [None, None]
    assert summary["n_tracklets"] == 1
    assert any("polling existing ATLAS task" in message for message in messages)


def test_run_atlas_recovery_resume_skips_prior_not_recovered_without_refresh(
    tmp_path: Path,
) -> None:
    """resume without force_refresh must preserve prior negative sample evidence."""
    module = _load_skill()
    expected = tmp_path / "expected_known.json"
    _write_expected_manifest(expected)
    rows = module._load_expected_known_manifest(expected)
    samples = [sample for row in rows for sample in module._manifest_samples(row)]
    params = {
        "expected_known": str(expected),
        "n_manifest_rows": 1,
        "n_samples": 3,
        "window_days": 1.0,
        "min_recovered_samples": 3,
        "min_nights": 2,
        "max_mag": 21.5,
        "max_polls": 2,
        "poll_interval_seconds": 0.0,
        "max_objects": None,
    }
    run_dir = tmp_path / "runs" / f"atlas_recovery_{module._param_key(params)}"
    first_key = module._recovery_sample_key(samples[0])
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "params": params,
                "last_stage": "atlas_forced_recovery",
                "tracklets": [],
                "partial_results": [],
                "samples": {
                    first_key: {
                        "designation": "100001",
                        "sample_index": 0,
                        "requested_ra_deg": 10.0,
                        "requested_dec_deg": 5.0,
                        "requested_jd": 2460000.0,
                        "window_days": 1.0,
                        "status": "not_recovered",
                        "n_raw_observations": 0,
                        "n_usable_observations": 0,
                        "observations": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[float] = []

    def recovery_fetcher(
        ra_deg: float,
        dec_deg: float,
        start_jd: float,
        end_jd: float,
        **kwargs: Any,
    ) -> list[SimpleNamespace]:
        calls.append(ra_deg)
        center_jd = (start_jd + end_jd) / 2.0
        return [_fake_observation_at(ra_deg, dec_deg, center_jd)]

    messages: list[str] = []
    summary = module.run_atlas_recovery(
        expected_known=expected,
        run_root=tmp_path / "runs",
        atlas_token=None,
        force_refresh=False,
        resume=True,
        workers=1,
        window_days=1.0,
        min_recovered_samples=3,
        min_nights=2,
        max_mag=21.5,
        max_objects=None,
        max_polls=2,
        poll_interval_seconds=0.0,
        fetcher=recovery_fetcher,
        print_fn=messages.append,
    )

    assert len(calls) == 2
    assert summary["n_recovered_samples"] == 2
    assert any("already not_recovered" in message for message in messages)


def test_run_atlas_recovery_force_refresh_retries_prior_not_recovered(
    tmp_path: Path,
) -> None:
    """force_refresh must re-query stale negative rows from older recovery windows."""
    module = _load_skill()
    expected = tmp_path / "expected_known.json"
    _write_expected_manifest(expected)
    rows = module._load_expected_known_manifest(expected)
    samples = [sample for row in rows for sample in module._manifest_samples(row)]
    params = {
        "expected_known": str(expected),
        "n_manifest_rows": 1,
        "n_samples": 3,
        "window_days": 1.0,
        "min_recovered_samples": 3,
        "min_nights": 2,
        "max_mag": 21.5,
        "max_polls": 2,
        "poll_interval_seconds": 0.0,
        "max_objects": None,
    }
    run_dir = tmp_path / "runs" / f"atlas_recovery_{module._param_key(params)}"
    first_key = module._recovery_sample_key(samples[0])
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(
            {
                "params": params,
                "last_stage": "atlas_forced_recovery",
                "tracklets": [],
                "partial_results": [],
                "samples": {
                    first_key: {
                        "designation": "100001",
                        "sample_index": 0,
                        "requested_ra_deg": 10.0,
                        "requested_dec_deg": 5.0,
                        "requested_jd": 2460000.0,
                        "window_days": 1.0,
                        "status": "not_recovered",
                        "n_raw_observations": 0,
                        "n_usable_observations": 0,
                        "observations": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    calls: list[float] = []

    def recovery_fetcher(
        ra_deg: float,
        dec_deg: float,
        start_jd: float,
        end_jd: float,
        **kwargs: Any,
    ) -> list[SimpleNamespace]:
        calls.append(ra_deg)
        center_jd = (start_jd + end_jd) / 2.0
        return [_fake_observation_at(ra_deg, dec_deg, center_jd)]

    messages: list[str] = []
    summary = module.run_atlas_recovery(
        expected_known=expected,
        run_root=tmp_path / "runs",
        atlas_token=None,
        force_refresh=True,
        resume=True,
        workers=1,
        window_days=1.0,
        min_recovered_samples=3,
        min_nights=2,
        max_mag=21.5,
        max_objects=None,
        max_polls=2,
        poll_interval_seconds=0.0,
        fetcher=recovery_fetcher,
        print_fn=messages.append,
    )

    assert len(calls) == 3
    assert summary["n_recovered_samples"] == 3
    assert summary["n_tracklets"] == 1
    assert any("refreshing prior not_recovered" in message for message in messages)


def test_run_atlas_recovery_marks_poll_exhaustion_as_pending(tmp_path: Path) -> None:
    """A queued task that outlives max_polls must stay resumable, not unrecovered."""
    module = _load_skill()
    expected = tmp_path / "expected_known.json"
    _write_expected_manifest(expected)

    def queued_fetcher(
        ra_deg: float,
        dec_deg: float,
        start_jd: float,
        end_jd: float,
        **kwargs: Any,
    ) -> list[SimpleNamespace]:
        kwargs["progress_callback"](
            {
                "url": "https://fake-atlas/task/still-queued/",
                "queuepos": 123,
                "finished": False,
                "result_url": None,
            }
        )
        return []

    summary = module.run_atlas_recovery(
        expected_known=expected,
        run_root=tmp_path / "runs",
        atlas_token=None,
        force_refresh=False,
        resume=False,
        workers=1,
        window_days=0.05,
        min_recovered_samples=3,
        min_nights=2,
        max_mag=21.5,
        max_objects=1,
        max_polls=1,
        poll_interval_seconds=0.0,
        fetcher=queued_fetcher,
        print_fn=lambda *a, **kw: None,
    )

    checkpoint = json.loads((Path(summary["run_dir"]) / "checkpoint.json").read_text())
    sample_states = list(checkpoint["samples"].values())
    assert summary["n_pending_samples"] == 3
    assert sample_states[0]["status"] == "poll_exhausted"
    assert sample_states[0]["task_url"] == "https://fake-atlas/task/still-queued/"
    assert sample_states[0]["queuepos"] == 123
    assert sample_states[0]["poll_count"] == 1


# ---------------------------------------------------------------------------
# Tests for Change 1: _DEFAULT_WINDOW_DAYS value and zero-obs diagnostic print
# ---------------------------------------------------------------------------


def test_default_window_days_is_one_day() -> None:
    """_DEFAULT_WINDOW_DAYS must be 1.0 to cover at least one ATLAS cadence cycle."""
    module = _load_skill()
    # ATLAS cadence is ~2 days; 0.05 d (72 min) was too narrow to catch observations.
    # The widened default of 1.0 d ensures a ±1 day window around each expected JD.
    assert module._DEFAULT_WINDOW_DAYS == 1.0, (
        f"_DEFAULT_WINDOW_DAYS is {module._DEFAULT_WINDOW_DAYS!r}; "
        "expected 1.0 to cover ATLAS 2-day cadence"
    )


def test_fetch_recovery_sample_prints_diagnostic_when_zero_observations(tmp_path: Path) -> None:
    """_fetch_recovery_sample must emit a diagnostic line when ATLAS returns 0 observations."""
    module = _load_skill()
    # Build the minimal sample dict that _fetch_recovery_sample expects.
    sample: dict[str, Any] = {
        "designation": "Ceres",
        "sample_index": 0,
        "ra_deg": 10.0,
        "dec_deg": 5.0,
        "jd": 2460000.0,
    }

    # Fetcher that always returns an empty list — simulates object outside footprint.
    def empty_fetcher(**kwargs: Any) -> list[Any]:
        return []

    printed: list[str] = []

    module._fetch_recovery_sample(
        sample=sample,
        atlas_token=None,
        force_refresh=False,
        window_days=1.0,
        max_mag=21.5,
        max_polls=1,
        poll_interval_seconds=0.0,
        fetcher=empty_fetcher,
        print_fn=printed.append,
        task_progress_callback=None,
    )

    # At least one message must contain the diagnostic text.
    diagnostic_msgs = [
        m for m in printed
        if "ATLAS returned 0 raw observations" in m and "Ceres" in m and "sample=0" in m
    ]
    assert diagnostic_msgs, (
        f"Expected diagnostic message about 0 raw observations but got: {printed}"
    )
