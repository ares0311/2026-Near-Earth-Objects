from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "Skills")

import hunter_cli  # noqa: E402
import select_survey_fields as field_selector  # noqa: E402

import hunter_state  # noqa: E402

_TARGET_QUEUE_HEADER = [
    "rank",
    "priority",
    "status",
    "data_role",
    "source",
    "selection_rule",
    "evidence_path",
    "notes",
]


def _write_empty_target_queue(path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_TARGET_QUEUE_HEADER)
        writer.writeheader()
    return path


def _coverage_field_result(field_id: str, ra_deg: float, dec_deg: float, n_nights: int = 3) -> dict:
    nights = [f"2024010{i + 1}" for i in range(n_nights)]
    return {
        "field_id": field_id,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "n_distinct_nights": n_nights,
        "distinct_nights_yyyymmdd": nights,
        "passes_min_distinct_nights": n_nights >= 3,
        "raw_response_sha256": "a" * 64,
    }


def _write_coverage_inventory(path: Path, fields: list[dict]) -> None:
    payload = {
        "schema_version": "ztf-field-night-coverage-inventory-v1",
        "batch_id": "test-batch",
        "batch_manifest_sha256": "b" * 64,
        "metadata_only": True,
        "min_distinct_nights": 3,
        "field_results": fields,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _patch_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hunter_cli, "_COVERAGE_INVENTORY_DIR", tmp_path / "coverage_inventories")
    monkeypatch.setattr(hunter_cli, "_BATCH_MANIFEST_DIR", tmp_path / "batch_manifests")
    monkeypatch.setattr(hunter_cli, "_SEARCH_MANIFEST_CSV_DIR", tmp_path / "search_manifests")
    monkeypatch.setattr(hunter_cli, "_WORKING_DIR", tmp_path / "working")
    monkeypatch.setattr(hunter_cli.coverage_inventory, "REPO_ROOT", tmp_path)


def test_field_id_from_radec_format() -> None:
    assert hunter_cli._field_id_from_radec("hx1", 251.664, -22.501) == "hx1_251p66_m22p50"
    assert hunter_cli._field_id_from_radec("hx1", 10.0, 5.0) == "hx1_010p00_p05p00"


def test_content_sha256_is_deterministic_and_order_independent() -> None:
    a = hunter_cli._content_sha256({"x": 1, "y": 2})
    b = hunter_cli._content_sha256({"y": 2, "x": 1})
    assert a == b
    assert len(a) == 64


def test_combined_known_coverage_merges_multiple_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "batch_a.json", [_coverage_field_result("field-a", 10.0, 5.0)]
    )
    _write_coverage_inventory(
        inv_dir / "batch_b.json", [_coverage_field_result("field-b", 20.0, -5.0)]
    )

    combined = hunter_cli._combined_known_coverage()

    assert set(combined.keys()) == {(10.0, 5.0), (20.0, -5.0)}
    assert combined[(10.0, 5.0)]["field_id"] == "field-a"


def test_combined_known_coverage_empty_when_no_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    assert hunter_cli._combined_known_coverage() == {}


def test_write_combined_inventory_round_trips_with_loader(tmp_path: Path) -> None:
    combined = {(10.0, 5.0): _coverage_field_result("field-a", 10.0, 5.0)}
    out_path = tmp_path / "combined.json"

    hunter_cli._write_combined_inventory(combined, out_path)
    loaded = field_selector.load_coverage_inventory(out_path)

    assert loaded["field_results"][0]["field_id"] == "field-a"
    assert loaded["min_distinct_nights"] == 3


def test_write_expansion_batch_manifest_round_trips_with_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hunter_cli.coverage_inventory, "REPO_ROOT", tmp_path)
    out_path = tmp_path / "batch_manifests" / "hunter_expand_test.json"

    hunter_cli._write_expansion_batch_manifest(
        "hunter_expand_test", [("hx1_010p00_p05p00", 10.0, 5.0)], out_path
    )
    batch = hunter_cli.coverage_inventory.load_batch_manifest(out_path)

    assert batch.batch_id == "hunter_expand_test"
    assert batch.fields[0].ra_deg == 10.0
    assert batch.min_distinct_nights == 3


def test_next_uncovered_planning_candidates_excludes_checked(tmp_path: Path) -> None:
    from astropy.time import Time

    jd = float(Time.now().jd)
    ranking_policy_path = field_selector._DEFAULT_RANKING_POLICY_PATH

    first_batch = hunter_cli._next_uncovered_planning_candidates(
        jd, "all", set(), batch_size=5, ranking_policy_path=ranking_policy_path
    )
    assert 0 < len(first_batch) <= 5

    checked = {field_selector._coordinate_key(ra, dec) for ra, dec in first_batch}
    second_batch = hunter_cli._next_uncovered_planning_candidates(
        jd, "all", checked, batch_size=5, ranking_policy_path=ranking_policy_path
    )
    for ra, dec in second_batch:
        assert field_selector._coordinate_key(ra, dec) not in checked


def test_discover_new_targets_sufficient_from_existing_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    from astropy.time import Time

    jd = float(Time.now().jd)
    # Use two real, currently-observable "all"-mode planning candidates so the
    # eligibility/geometry gate genuinely passes, rather than a fabricated
    # coordinate pair that might fall outside tonight's observable window.
    planning = field_selector.select_fields(jd=jd, mode="all", top_n=2)
    fields = [
        _coverage_field_result(f"field-{i}", row["ra_deg"], row["dec_deg"])
        for i, row in enumerate(planning)
    ]
    _write_coverage_inventory(inv_dir / "seed.json", fields)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")

    def _fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("no live expansion should be needed when inventory suffices")

    monkeypatch.setattr(
        hunter_cli.coverage_inventory.bounded_ingest, "run_bounded_ingest", _fail_if_called
    )

    result = hunter_cli.discover_new_targets(
        jd=jd,
        neo_class="all",
        requested_n=2,
        max_pool=50,
        out_dir=tmp_path / "expansion",
        target_queue_path=target_queue_path,
        ranking_policy_path=field_selector._DEFAULT_RANKING_POLICY_PATH,
    )

    assert result["sufficiency_met"] is True
    assert len(result["eligible"]) >= 2
    assert result["pool_size_explored"] == 2


def test_discover_new_targets_expands_when_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    from astropy.time import Time

    jd = float(Time.now().jd)

    def _fake_run_bounded_ingest(*, ra: float, dec: float, size_deg: float, start_jd: float,
                                  end_jd: float, out_dir: Path, **_: object) -> dict:
        return {
            "n_rows": 30,
            "distinct_nights_yyyymmdd": ["20240101", "20240102", "20240103"],
            "raw_response_sha256": "c" * 64,
            "raw_response_path": str(out_dir / "raw.ipac"),
        }

    monkeypatch.setattr(
        hunter_cli.coverage_inventory.bounded_ingest,
        "run_bounded_ingest",
        _fake_run_bounded_ingest,
    )

    result = hunter_cli.discover_new_targets(
        jd=jd,
        neo_class="all",
        requested_n=1,
        max_pool=50,
        out_dir=tmp_path / "expansion",
        target_queue_path=target_queue_path,
        ranking_policy_path=field_selector._DEFAULT_RANKING_POLICY_PATH,
    )

    assert result["sufficiency_met"] is True
    assert len(result["eligible"]) >= 1
    assert result["pool_size_explored"] >= 1
    committed = list(hunter_cli._COVERAGE_INVENTORY_DIR.glob("*.json"))
    assert len(committed) >= 1


def test_discover_new_targets_reports_insufficient_when_pool_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    from astropy.time import Time

    jd = float(Time.now().jd)

    result = hunter_cli.discover_new_targets(
        jd=jd,
        neo_class="all",
        requested_n=5,
        max_pool=0,
        out_dir=tmp_path / "expansion",
        target_queue_path=target_queue_path,
        ranking_policy_path=field_selector._DEFAULT_RANKING_POLICY_PATH,
    )

    assert result["sufficiency_met"] is False
    assert result["eligible"] == []
    assert result["pool_size_explored"] == 0


def test_discover_new_targets_stops_when_planning_grid_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    from astropy.time import Time

    jd = float(Time.now().jd)
    monkeypatch.setattr(hunter_cli, "_next_uncovered_planning_candidates", lambda *a, **k: [])

    result = hunter_cli.discover_new_targets(
        jd=jd,
        neo_class="all",
        requested_n=5,
        max_pool=1000,
        out_dir=tmp_path / "expansion",
        target_queue_path=target_queue_path,
        ranking_policy_path=field_selector._DEFAULT_RANKING_POLICY_PATH,
    )

    assert result["sufficiency_met"] is False
    assert result["eligible"] == []
    assert result["pool_size_explored"] == 0


def test_write_manifest_csv_and_print_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(hunter_cli, "_SEARCH_MANIFEST_CSV_DIR", tmp_path / "search_manifests")
    rows = [
        {
            "target_id": f"radec_{i}.00_0.00",
            "ra_deg": float(i),
            "dec_deg": 0.0,
            "score": 0.9,
            "selection_reason": "test",
            "coverage_inventory_id": "field-x",
        }
        for i in range(3)
    ]

    csv_path = hunter_cli._write_manifest_csv("search-1", rows)
    assert csv_path.is_file()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == 3
    assert written[0]["rank"] == "1"

    hunter_cli._print_table("search-1", rows)
    out = capsys.readouterr().out
    assert "search-1" in out
    assert "3 target(s) selected" in out


def test_cmd_create_new_search_persists_manifest_and_prints_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    from astropy.time import Time

    jd = float(Time.now().jd)
    planning = field_selector.select_fields(jd=jd, mode="all", top_n=2)
    fields = [
        _coverage_field_result(f"field-{i}", row["ra_deg"], row["dec_deg"])
        for i, row in enumerate(planning)
    ]
    _write_coverage_inventory(inv_dir / "seed.json", fields)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    db_path = tmp_path / "hunter_state.sqlite"

    args = argparse.Namespace(
        targets=2,
        mode="new",
        neo_class="all",
        jd="now",
        max_pool=50,
        target_queue=str(target_queue_path),
        ranking_policy=str(field_selector._DEFAULT_RANKING_POLICY_PATH),
        db=str(db_path),
    )

    exit_code = hunter_cli.cmd_create_new_search(args)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "status=pending" in out
    assert "sufficiency_met=True" in out

    manifest = hunter_state.get_latest_pending_manifest(db_path, mode="new")
    assert manifest["requested_n"] == 2
    assert len(manifest["targets"]) == 2
    assert manifest["status"] == "pending"


def test_cmd_create_new_search_accepts_explicit_jd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    db_path = tmp_path / "hunter_state.sqlite"

    args = argparse.Namespace(
        targets=1,
        mode="new",
        neo_class="all",
        jd="2461000.5",
        max_pool=0,
        target_queue=str(target_queue_path),
        ranking_policy=str(field_selector._DEFAULT_RANKING_POLICY_PATH),
        db=str(db_path),
    )

    exit_code = hunter_cli.cmd_create_new_search(args)

    assert exit_code == 0
    manifest = hunter_state.get_latest_pending_manifest(db_path, mode="new")
    assert manifest["config"]["jd"] == 2461000.5


def test_cmd_create_new_search_writes_csv_manifest_over_100_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    db_path = tmp_path / "hunter_state.sqlite"

    fake_eligible = [
        {
            "ra_deg": float(i),
            "dec_deg": 0.0,
            "score": 1.0 - i * 0.001,
            "reason": "synthetic large-batch test row",
            "field_id": f"fake-field-{i}",
        }
        for i in range(150)
    ]
    monkeypatch.setattr(
        hunter_cli,
        "discover_new_targets",
        lambda **kwargs: {
            "eligible": fake_eligible,
            "pool_size_explored": 150,
            "sufficiency_met": True,
        },
    )

    args = argparse.Namespace(
        targets=120,
        mode="new",
        neo_class="all",
        jd="now",
        max_pool=200,
        target_queue=str(target_queue_path),
        ranking_policy=str(field_selector._DEFAULT_RANKING_POLICY_PATH),
        db=str(db_path),
    )

    exit_code = hunter_cli.cmd_create_new_search(args)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Search manifest written:" in out
    csv_files = list(hunter_cli._SEARCH_MANIFEST_CSV_DIR.glob("*.csv"))
    assert len(csv_files) == 1
    with csv_files[0].open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 120


def test_cmd_create_new_search_reports_shortfall_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    db_path = tmp_path / "hunter_state.sqlite"

    args = argparse.Namespace(
        targets=5,
        mode="new",
        neo_class="all",
        jd="now",
        max_pool=0,
        target_queue=str(target_queue_path),
        ranking_policy=str(field_selector._DEFAULT_RANKING_POLICY_PATH),
        db=str(db_path),
    )

    exit_code = hunter_cli.cmd_create_new_search(args)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "WARNING: only 0/5 eligible targets found" in out
    manifest = hunter_state.get_latest_pending_manifest(db_path, mode="new")
    assert manifest["sufficiency_met"] is False
    assert manifest["actual_n_selected"] == 0


def test_main_rejects_non_positive_targets_with_system_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    target_queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")
    db_path = tmp_path / "hunter_state.sqlite"

    with pytest.raises(SystemExit, match="requested_n must be positive"):
        hunter_cli.main(
            [
                "create-new-search",
                "--targets",
                "0",
                "--mode",
                "new",
                "--target-queue",
                str(target_queue_path),
                "--db",
                str(db_path),
                "--max-pool",
                "0",
            ]
        )


def test_build_parser_requires_mode_and_targets() -> None:
    parser = hunter_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["create-new-search"])
