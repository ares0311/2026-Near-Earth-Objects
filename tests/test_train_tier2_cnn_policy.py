"""Tests for A4 production-candidate policy gates in train_tier2_cnn.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_skill():
    path = Path(__file__).resolve().parents[1] / "Skills" / "train_tier2_cnn.py"
    spec = importlib.util.spec_from_file_location("train_tier2_cnn", path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _write_report(path: Path, *, passed: bool) -> Path:
    path.write_text(
        json.dumps({
            "schema_version": "grouped-split-leakage-v1",
            "passed": passed,
            "hard_leakage": {},
            "missing_required_splits": [],
        }),
        encoding="utf-8",
    )
    return path


def test_main_production_candidate_requires_passing_grouped_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    failing = _write_report(tmp_path / "failing.json", passed=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier2_cnn.py",
            "--labels", str(tmp_path / "nonexistent.csv"),
            "--grouped-split-report", str(failing),
            "--production-candidate",
            "--dry-run",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        mod.main()

    assert exc.value.code == 1


def test_main_production_candidate_accepts_passing_grouped_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    passing = _write_report(tmp_path / "passing.json", passed=True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier2_cnn.py",
            "--labels", str(tmp_path / "nonexistent.csv"),
            "--grouped-split-report", str(passing),
            "--production-candidate",
            "--dry-run",
        ],
    )

    mod.main()


def test_main_without_production_candidate_ignores_missing_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier2_cnn.py",
            "--labels", str(tmp_path / "nonexistent.csv"),
            "--dry-run",
        ],
    )

    mod.main()


def _row(object_id: str, label: int = 0, jd: float = 2459000.5,
         ra: float = 100.0, dec: float = 5.0) -> dict:
    return {
        "cutout_path": f"cutout_{object_id}.npz",
        "label": str(label),
        "candidate_id": f"cand_{object_id}",
        "object_id": object_id,
        "jd": str(jd),
        "ra_deg": str(ra),
        "dec_deg": str(dec),
        "source_key": "ZTF:P48",
    }


def test_assign_grouped_split_keeps_same_object_id_in_one_split() -> None:
    mod = _load_skill()
    # Object "A" has 3 alerts across nights -- all must land in the same split.
    rows = (
        [_row("A", jd=2459000.5), _row("A", jd=2459003.5), _row("A", jd=2459006.5)]
        + [_row(f"solo{i}") for i in range(20)]
    )

    assignments, n_missing = mod.assign_grouped_split(
        rows, val_fraction=0.2, test_fraction=0.15, seed=42
    )

    assert n_missing == 0
    a_indices = [i for i, r in enumerate(rows) if r["object_id"] == "A"]
    a_splits = {assignments[i] for i in a_indices}
    assert len(a_splits) == 1, f"object A leaked across splits: {a_splits}"
    assert set(assignments) <= {"train", "validation", "test"}
    assert "train" in assignments
    assert "validation" in assignments
    assert "test" in assignments


def test_assign_grouped_split_flags_missing_object_id() -> None:
    mod = _load_skill()
    rows = [_row(f"obj{i}") for i in range(5)]
    for r in rows[:2]:
        r["object_id"] = ""

    _assignments, n_missing = mod.assign_grouped_split(
        rows, val_fraction=0.2, test_fraction=0.2, seed=1
    )

    assert n_missing == 2


def test_assign_grouped_split_is_deterministic_for_same_seed() -> None:
    mod = _load_skill()
    rows = [_row(f"obj{i}") for i in range(30)]

    a1, _ = mod.assign_grouped_split(rows, val_fraction=0.2, test_fraction=0.15, seed=7)
    a2, _ = mod.assign_grouped_split(rows, val_fraction=0.2, test_fraction=0.15, seed=7)

    assert a1 == a2


def test_write_grouped_split_csv_is_consumable_by_validator(tmp_path: Path) -> None:
    mod = _load_skill()
    # Spread each object across a distinct sky cell and night (the real
    # download script gives every object a real, distinct sky position and
    # observation time; night_key and sky_cell are both A4 hard-leakage
    # groups, so a synthetic fixture that shares either across objects would
    # trip the checker for reasons unrelated to what this test verifies).
    rows = [_row(f"obj{i}", jd=2459000.5 + i, ra=100.0 + i * 5.0) for i in range(20)]
    assignments, _ = mod.assign_grouped_split(rows, val_fraction=0.2, test_fraction=0.15, seed=3)
    out_path = tmp_path / "split.csv"

    mod.write_grouped_split_csv(rows, assignments, out_path)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from grouped_splits import leakage_report, records_from_csv

    records = records_from_csv(out_path)
    report = leakage_report(records)
    assert report["schema_version"] == "grouped-split-leakage-v1"
    assert report["passed"] is True


def test_emit_split_csv_cli_writes_file_and_exits_without_training(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    labels_csv = tmp_path / "index.csv"
    rows = [_row(f"obj{i}") for i in range(20)]
    with labels_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    out_csv = tmp_path / "grouped_split.csv"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier2_cnn.py",
            "--labels", str(labels_csv),
            "--emit-split-csv", str(out_csv),
        ],
    )

    mod.main()

    assert out_csv.exists()
    with out_csv.open() as f:
        written_rows = list(csv.DictReader(f))
    assert len(written_rows) == 20


def test_assign_night_based_split_keeps_every_night_in_one_split() -> None:
    """Regression for the real A4 night_key leakage found running this
    script against genuine 3-night ZTF data: object_id-only splitting lets
    one night's alerts scatter across all three splits. See
    docs/evidence/a7/2026-07-10-second-attempt-object-id-split-still-leaks-night-and-sky.md."""
    mod = _load_skill()
    rows = []
    for night_offset in range(6):  # 6 distinct nights, spaced >1 day apart
        jd = 2459000.5 + night_offset * 3
        for obj_idx in range(10):
            rows.append(_row(f"n{night_offset}o{obj_idx}", jd=jd, ra=10.0 * night_offset))

    assignments, diagnostics = mod.assign_night_based_split(
        rows, val_fraction=0.2, test_fraction=0.15
    )

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from grouped_splits import _night_key

    night_to_splits: dict[str, set[str]] = {}
    for row, split in zip(rows, assignments, strict=True):
        night_to_splits.setdefault(_night_key(row), set()).add(split)

    for night, splits in night_to_splits.items():
        assert len(splits) == 1, f"night {night} leaked across splits: {splits}"
    assert diagnostics["n_nights"] == 6
    assert set(assignments) <= {"train", "validation", "test"}


def test_assign_night_based_split_resolves_object_id_conflicts() -> None:
    """An object observed on two nights assigned to different splits must
    still end up entirely in one split (object_id purity), with the
    reassignment counted in diagnostics rather than silently dropped."""
    mod = _load_skill()
    rows = [
        _row("cross_night_obj", jd=2459000.5, ra=10.0),   # night 0
        _row("cross_night_obj", jd=2459010.5, ra=10.0),   # night 10 (different split)
    ] + [_row(f"filler{i}", jd=2459000.5 + i, ra=50.0 + i) for i in range(20)]

    assignments, diagnostics = mod.assign_night_based_split(
        rows, val_fraction=0.2, test_fraction=0.15
    )

    obj_indices = [i for i, r in enumerate(rows) if r["object_id"] == "cross_night_obj"]
    obj_splits = {assignments[i] for i in obj_indices}
    assert len(obj_splits) == 1, f"cross_night_obj leaked across splits: {obj_splits}"
    assert diagnostics["n_reassigned_for_object_conflict"] >= 1


def test_split_strategy_night_cli_produces_night_pure_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    labels_csv = tmp_path / "index.csv"
    rows = []
    for night_offset in range(6):
        jd = 2459000.5 + night_offset * 3
        for obj_idx in range(10):
            rows.append(_row(f"n{night_offset}o{obj_idx}", jd=jd, ra=10.0 * night_offset))
    with labels_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    out_csv = tmp_path / "grouped_split.csv"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier2_cnn.py",
            "--labels", str(labels_csv),
            "--emit-split-csv", str(out_csv),
            "--split-strategy", "night",
        ],
    )

    mod.main()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from grouped_splits import leakage_report, records_from_csv

    records = records_from_csv(out_csv)
    report = leakage_report(records)
    assert report["hard_leakage"].get("night_key", {}) == {}
    assert report["hard_leakage"].get("object_id", {}) == {}


def test_emit_split_csv_cli_fails_closed_on_legacy_csv_without_object_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_skill()
    labels_csv = tmp_path / "index.csv"
    with labels_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cutout_path", "label"])
        writer.writeheader()
        writer.writerow({"cutout_path": "cutout_0.npz", "label": "0"})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_tier2_cnn.py",
            "--labels", str(labels_csv),
            "--emit-split-csv", str(tmp_path / "out.csv"),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        mod.main()

    assert exc.value.code == 1
