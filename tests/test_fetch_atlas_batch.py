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
