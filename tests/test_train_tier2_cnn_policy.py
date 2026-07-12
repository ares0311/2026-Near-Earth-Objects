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


def test_assign_night_based_split_uses_chronological_order_not_row_order() -> None:
    """Regression: download_ztf_training_alerts.py iterates nights
    most-recent-first, so row order in a real labels CSV is the REVERSE of
    chronological order. An earlier implementation used row-encounter order
    to pick each object's "canonical" split, which silently picked the
    LATEST night instead of the earliest for real data, concentrating all
    leakage onto the earliest (test/validation) nights instead of resolving
    symmetrically. See
    docs/evidence/a7/2026-07-10-fourth-attempt-object-conflict-resolution-used-file-order-not-chronological-order.md."""
    mod = _load_skill()
    # Row order deliberately reversed: the LATER night (jd=2459010.5) comes
    # first in the list, exactly like a real download's most-recent-first CSV.
    rows = [
        _row("cross_night_obj", jd=2459010.5, ra=10.0),   # later night, first in file
        _row("cross_night_obj", jd=2459000.5, ra=10.0),   # earlier night, later in file
    ] + [_row(f"filler{i}", jd=2459000.5 + i, ra=50.0 + i) for i in range(20)]

    assignments, _ = mod.assign_night_based_split(rows, val_fraction=0.2, test_fraction=0.15)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from grouped_splits import _night_key

    # Whichever split the object's chronologically-earliest night (jd=2459000.5)
    # landed in must be the split for BOTH of its rows, regardless of file order.
    earliest_night_row = next(r for r in rows if float(r["jd"]) == 2459000.5)
    earliest_night_split = None
    for idx, row in enumerate(rows):
        same_night = _night_key(row) == _night_key(earliest_night_row)
        if same_night and row["object_id"] != "cross_night_obj":
            earliest_night_split = assignments[idx]
            break
    assert earliest_night_split is not None, "test fixture needs a same-night filler row"

    obj_indices = [i for i, r in enumerate(rows) if r["object_id"] == "cross_night_obj"]
    obj_splits = {assignments[i] for i in obj_indices}
    assert obj_splits == {earliest_night_split}, (
        f"cross_night_obj should land entirely in {earliest_night_split!r} "
        f"(its earliest night's split), got {obj_splits}"
    )


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


class TestSyntheticArtifactDataset:
    """Regression tests for the 2026-07-12 hard-negative augmentation added
    after tier2_cnn_v3 was rejected for 100% false-discovery on
    Skills/evaluate_cnn_false_discovery.py's adversarial test."""

    def test_len_matches_n_samples(self) -> None:
        mod = _load_skill()
        ds = mod.SyntheticArtifactDataset(7, seed=1)
        assert len(ds) == 7

    def test_every_sample_labeled_stellar_artifact(self) -> None:
        mod = _load_skill()
        ds = mod.SyntheticArtifactDataset(5, seed=2)
        for idx in range(len(ds)):
            sci, ref, diff, label = ds[idx]
            assert label.item() == mod._STELLAR_ARTIFACT_LABEL
            assert sci.shape == ref.shape == diff.shape == (1, 63, 63)

    def test_same_seed_and_index_is_deterministic(self) -> None:
        mod = _load_skill()
        ds_a = mod.SyntheticArtifactDataset(3, seed=42)
        ds_b = mod.SyntheticArtifactDataset(3, seed=42)
        sci_a, ref_a, diff_a, _ = ds_a[1]
        sci_b, ref_b, diff_b, _ = ds_b[1]
        assert (sci_a == sci_b).all()
        assert (ref_a == ref_b).all()
        assert (diff_a == diff_b).all()

    def test_different_indices_produce_different_samples(self) -> None:
        mod = _load_skill()
        ds = mod.SyntheticArtifactDataset(3, seed=42)
        sci_0, _, _, _ = ds[0]
        sci_1, _, _, _ = ds[1]
        assert not (sci_0 == sci_1).all()

    def test_respects_sigma_range(self) -> None:
        """Every generated sample's sigma must stay within the requested
        range -- otherwise the "kept below real seeing-limited PSF width"
        safety property documented on --hard-negative-sigma-max would not
        actually hold at the given CLI settings."""
        mod = _load_skill()
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Skills"))
        import numpy as np
        from evaluate_cnn_false_discovery import _synthesize_artifact_cutout_arrays

        sigma_min, sigma_max = 0.05, 0.35
        ds = mod.SyntheticArtifactDataset(1, seed=99, sigma_range=(sigma_min, sigma_max))
        # Reproduce the internal draw exactly to confirm it's bounded (the
        # dataset doesn't expose sigma directly, so this checks the same
        # rng-derivation formula __getitem__ uses).
        rng = np.random.default_rng(ds.seed + 0)
        sigma_px = float(rng.uniform(ds.sigma_min, ds.sigma_max))
        assert sigma_min <= sigma_px <= sigma_max
        # Sanity: the underlying synthesis function accepts this sigma and
        # produces a valid triplet without raising.
        rng2 = np.random.default_rng(ds.seed + 0)
        sci_arr, ref_arr, diff_arr, real_bogus = _synthesize_artifact_cutout_arrays(
            rng2, 19.5, 10.0, sigma_px=sigma_px
        )
        assert sci_arr.shape == (63, 63)
        assert 0.0 <= real_bogus <= 1.0


class TestComputeClassWeightsExtraCounts:
    def test_extra_label_counts_shift_weights(self) -> None:
        mod = _load_skill()
        rows = [_row(f"o{i}", label=0) for i in range(80)] + [
            _row(f"o{i}", label=3) for i in range(80, 100)
        ]
        base_weights = mod._compute_class_weights(rows)
        # Add 1000 more label=3 examples outside `rows` (as the synthetic
        # hard negatives are, since they never have a CSV row) -- class 3's
        # weight must drop (it's no longer as rare) relative to the
        # no-extra-counts baseline.
        boosted_weights = mod._compute_class_weights(rows, extra_label_counts={3: 1000})
        assert boosted_weights[3].item() < base_weights[3].item()

    def test_extra_label_counts_none_matches_prior_behavior(self) -> None:
        mod = _load_skill()
        rows = [_row(f"o{i}", label=0) for i in range(10)] + [_row("b", label=3)]
        assert (
            mod._compute_class_weights(rows).tolist()
            == mod._compute_class_weights(rows, extra_label_counts=None).tolist()
        )


class TestHardNegativeCliWiring:
    """Verify main() parses the new flags and passes them through to
    train() unchanged -- by monkeypatching train() to capture its kwargs
    rather than running a real (torch-dependent, slow) training loop."""

    def _capture_train_kwargs(self, mod, monkeypatch: pytest.MonkeyPatch) -> dict:
        captured: dict = {}

        def _fake_train(*args, **kwargs) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

        monkeypatch.setattr(mod, "train", _fake_train)
        return captured

    def test_n_hard_negatives_defaults_to_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--n-hard-negatives must default to 0 (opt-in only) so existing
        invocation commands from before this feature existed are unaffected."""
        mod = _load_skill()
        captured = self._capture_train_kwargs(mod, monkeypatch)
        monkeypatch.setattr(
            sys, "argv", ["train_tier2_cnn.py", "--labels", str(tmp_path / "nonexistent.csv")]
        )
        mod.main()
        assert captured["kwargs"]["n_hard_negatives"] == 0

    def test_hard_negative_flags_reach_train(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _load_skill()
        captured = self._capture_train_kwargs(mod, monkeypatch)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "train_tier2_cnn.py",
                "--labels", str(tmp_path / "nonexistent.csv"),
                "--n-hard-negatives", "500",
                "--hard-negative-sigma-min", "0.05",
                "--hard-negative-sigma-max", "0.35",
                "--hard-negative-seed", "7",
            ],
        )
        mod.main()
        kwargs = captured["kwargs"]
        assert kwargs["n_hard_negatives"] == 500
        assert kwargs["hard_negative_sigma_range"] == (0.05, 0.35)
        assert kwargs["hard_negative_seed"] == 7
