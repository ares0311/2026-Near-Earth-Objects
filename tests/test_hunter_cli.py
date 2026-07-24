from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

import pytest
from astropy.io import ascii as ap_ascii
from astropy.table import Table

sys.path.insert(0, "Skills")

import adversarial_review  # noqa: E402
import hunter_cli  # noqa: E402
import select_survey_fields as field_selector  # noqa: E402

import hunter_state  # noqa: E402
import schemas  # noqa: E402

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


def _write_target_queue_with_rows(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_TARGET_QUEUE_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _insufficient_coverage_row(rank: int, ra_deg: float, dec_deg: float) -> dict:
    return {
        "rank": rank,
        "priority": 0.8,
        "status": "insufficient_coverage",
        "data_role": "live_search",
        "source": "sky_field_selector",
        "selection_rule": "test",
        "evidence_path": "",
        "notes": f"ra_deg={ra_deg} dec_deg={dec_deg} field_radius_deg=3.5; test row",
    }


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


# ---------------------------------------------------------------------------
# run-new-search
# ---------------------------------------------------------------------------


def _ipac_text(obsjd_values: list[float]) -> str:
    """Real, library-round-tripped IPAC table text (astropy's own writer),
    matching the format bounded_ingest._parse_ipac_table expects -- not a
    hand-typed guess at the format."""
    n_rows = len(obsjd_values)
    table = Table()
    table["ra"] = [10.0] * n_rows
    table["dec"] = [5.0] * n_rows
    table["field"] = [100] * n_rows
    table["ccdid"] = [1] * n_rows
    table["qid"] = [1] * n_rows
    table["rcid"] = [0] * n_rows
    table["fid"] = [1] * n_rows
    table["filtercode"] = ["zg"] * n_rows
    table["pid"] = [1000 + i for i in range(n_rows)]
    table["obsdate"] = ["2024-01-01 05:00:00"] * n_rows
    table["obsjd"] = obsjd_values
    table["filefracday"] = [20240101000000 + i for i in range(n_rows)]
    table["imgtypecode"] = ["o"] * n_rows
    table["exptime"] = [30.0] * n_rows
    table["seeing"] = [2.1] * n_rows
    table["maglimit"] = [20.5] * n_rows
    table["infobits"] = [0] * n_rows
    table["ipac_pub_date"] = ["2024-01-02 00:00:00"] * n_rows
    buf = io.StringIO()
    ap_ascii.write(table, buf, format="ipac")
    header = f"\\fixlen = T\n\\RowsRetrieved = {n_rows}\n\\QUERY_STATUS = 'OK'\n"
    return header + buf.getvalue()


def _minimal_scored_neo_packet(object_id: str = "hunter-test-T1") -> dict:
    obs = tuple(
        schemas.Observation(
            obs_id=f"o_{i}",
            ra_deg=180.0 + i * 0.01,
            dec_deg=10.0,
            jd=2460000.5 + i,
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            real_bogus=0.95,
        )
        for i in range(3)
    )
    tracklet = schemas.Tracklet(
        object_id=object_id,
        observations=obs,
        arc_days=2.0,
        motion_rate_arcsec_per_hour=5.0,
        motion_pa_degrees=90.0,
    )
    features = schemas.CandidateFeatures(real_bogus_score=0.95)
    posterior = schemas.NEOPosterior(
        neo_candidate=0.75,
        known_object=0.05,
        main_belt_asteroid=0.10,
        stellar_artifact=0.05,
        other_solar_system=0.05,
    )
    explanation = schemas.CandidateExplanation(
        summary="test", supporting_evidence=(), contra_evidence=(), model_version="test"
    )
    elements = schemas.OrbitalElements(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=2,
    )
    hazard = schemas.HazardAssessment(
        hazard_flag="pha_candidate",
        moid_au=0.03,
        estimated_diameter_m=200.0,
        absolute_magnitude_h=21.5,
        neo_class="apollo",
        alert_pathway="mpc_submission",
        explanation=explanation,
        orbital_elements=elements,
    )
    metadata = schemas.ScoringMetadata(
        scorer_version="test",
        scored_at_jd=2460000.5,
        pipeline_run_id="test",
        discovery_priority=0.8,
        followup_value=0.6,
        scientific_interest=0.5,
    )
    scored = schemas.ScoredNEO(
        tracklet=tracklet, features=features, posterior=posterior, hazard=hazard, metadata=metadata
    )
    return scored.model_dump(mode="json")


def test_git_sha_returns_nonempty_string() -> None:
    assert len(hunter_cli._git_sha()) > 0


def test_day_jd_bounds_spans_exactly_one_day() -> None:
    from astropy.time import Time

    start, end = hunter_cli._day_jd_bounds("20240115")
    assert end - start == pytest.approx(1.0)
    assert Time(start, format="jd").datetime.strftime("%Y%m%d") == "20240115"


def test_single_exposure_window_isolates_well_separated_exposures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = 2460315.5
    obsjds = [base + 0.1, base + 0.2]  # ~2.4 hours apart

    def _fake(*, ra, dec, size_deg, start_jd, end_jd, out_dir, **_):
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path = out_dir / "raw.ipac"
        raw_path.write_text(_ipac_text(obsjds), encoding="utf-8")
        return {"raw_response_path": str(raw_path)}

    monkeypatch.setattr(hunter_cli.bounded_ingest, "run_bounded_ingest", _fake)

    start_jd, end_jd = hunter_cli._single_exposure_window(
        10.0, 5.0, "20240115", 2.0, tmp_path / "scan"
    )

    assert start_jd < obsjds[0] < end_jd
    assert not (start_jd < obsjds[1] < end_jd)


def test_single_exposure_window_raises_when_no_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake(*, ra, dec, size_deg, start_jd, end_jd, out_dir, **_):
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path = out_dir / "raw.ipac"
        raw_path.write_text(_ipac_text([]), encoding="utf-8")
        return {"raw_response_path": str(raw_path)}

    monkeypatch.setattr(hunter_cli.bounded_ingest, "run_bounded_ingest", _fake)

    with pytest.raises(RuntimeError, match="no exposure found"):
        hunter_cli._single_exposure_window(10.0, 5.0, "20240115", 2.0, tmp_path / "scan")


def test_single_exposure_window_raises_when_cannot_isolate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = 2460315.5
    obsjds = [base, base + 5.0 / 86400.0]  # 5 seconds apart -- narrower than the tightest attempt

    def _fake(*, ra, dec, size_deg, start_jd, end_jd, out_dir, **_):
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path = out_dir / "raw.ipac"
        raw_path.write_text(_ipac_text(obsjds), encoding="utf-8")
        return {"raw_response_path": str(raw_path)}

    monkeypatch.setattr(hunter_cli.bounded_ingest, "run_bounded_ingest", _fake)

    with pytest.raises(RuntimeError, match="could not isolate"):
        hunter_cli._single_exposure_window(10.0, 5.0, "20240115", 2.0, tmp_path / "scan")


def test_nights_for_target_looks_up_combined_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json",
        [_coverage_field_result("field-a", 10.0, 5.0, n_nights=5)],
    )

    nights = hunter_cli._nights_for_target(10.0, 5.0)

    assert len(nights) == 5


def test_nights_for_target_raises_when_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="no committed coverage record"):
        hunter_cli._nights_for_target(10.0, 5.0)


def test_acquire_and_convert_night_writes_observation_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    obsjd = 2460315.6

    def _fake(*, ra, dec, size_deg, start_jd, end_jd, out_dir, **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        if kwargs.get("pixel_extraction_pilot"):
            manifest_path = out_dir / "motion_product_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {"exposures": [{"pid": 1, "obsjd": obsjd, "filtercode": "zg"}]}
                ),
                encoding="utf-8",
            )
            pilot_path = out_dir / "pixel_extraction_pilot.json"
            pilot_path.write_text(
                json.dumps(
                    {
                        "pid": 1,
                        "sources": [
                            {
                                "x": 1,
                                "y": 1,
                                "ra_deg": 10.0,
                                "dec_deg": 5.0,
                                "peak_value": 500.0,
                                "psf_correlation": 0.9,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return {"motion_product_manifest_path": str(manifest_path)}
        raw_path = out_dir / "raw.ipac"
        raw_path.write_text(_ipac_text([obsjd]), encoding="utf-8")
        return {"raw_response_path": str(raw_path)}

    monkeypatch.setattr(hunter_cli.bounded_ingest, "run_bounded_ingest", _fake)

    target_root = tmp_path / "target-1"
    hunter_cli._acquire_and_convert_night(10.0, 5.0, "20240115", 2.0, target_root)

    written = json.loads((target_root / "observations" / "20240115.json").read_text())
    assert written["kept_count"] == 1
    assert written["observations"][0]["jd"] == obsjd


def test_execute_target_raises_when_insufficient_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=2)]
    )
    target = {"target_id": "radec_10.00_5.00", "ra_deg": 10.0, "dec_deg": 5.0}

    with pytest.raises(RuntimeError, match="fewer than min_observations"):
        hunter_cli.execute_target(target, tmp_path / "checkpoints", 2.0)


def test_execute_target_skips_a_night_that_fails_to_resolve_and_tries_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=4)]
    )

    def _fake_acquire(ra_deg, dec_deg, night, size_deg, target_root):
        if night == "20240101":
            raise RuntimeError("no exposure found for RA=10.0 Dec=5.0 on 20240101")
        return None

    monkeypatch.setattr(hunter_cli, "_acquire_and_convert_night", _fake_acquire)
    monkeypatch.setattr(
        hunter_cli.positive_control,
        "run_positive_control",
        lambda **kwargs: {"n_tracklets_linked": 0, "review_packets": []},
    )
    target = {"target_id": "radec_10.00_5.00", "ra_deg": 10.0, "dec_deg": 5.0}

    result = hunter_cli.execute_target(target, tmp_path / "checkpoints", 2.0)

    # 4 nights available (20240101..20240104); 20240101 fails and is skipped,
    # so the 3 required successes come from the next 3 nights.
    assert result["nights_acquired"] == ["20240102", "20240103", "20240104"]


def test_execute_target_stops_once_min_observations_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=5)]
    )
    attempted: list[str] = []

    def _fake_acquire(ra_deg, dec_deg, night, size_deg, target_root):
        attempted.append(night)

    monkeypatch.setattr(hunter_cli, "_acquire_and_convert_night", _fake_acquire)
    monkeypatch.setattr(
        hunter_cli.positive_control,
        "run_positive_control",
        lambda **kwargs: {"n_tracklets_linked": 0, "review_packets": []},
    )
    target = {"target_id": "radec_10.00_5.00", "ra_deg": 10.0, "dec_deg": 5.0}

    result = hunter_cli.execute_target(target, tmp_path / "checkpoints", 2.0)

    # 5 real covered nights exist, but only the first 3 should ever be
    # attempted once min_observations=3 is satisfied.
    assert attempted == ["20240101", "20240102", "20240103"]
    assert result["nights_acquired"] == ["20240101", "20240102", "20240103"]


def test_execute_target_raises_when_too_few_nights_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=4)]
    )

    def _fake_acquire_always_fails(ra_deg, dec_deg, night, size_deg, target_root):
        raise RuntimeError(f"no exposure found for RA=10.0 Dec=5.0 on {night}")

    monkeypatch.setattr(hunter_cli, "_acquire_and_convert_night", _fake_acquire_always_fails)
    target = {"target_id": "radec_10.00_5.00", "ra_deg": 10.0, "dec_deg": 5.0}

    with pytest.raises(RuntimeError, match="only acquired 0/3 real exposure"):
        hunter_cli.execute_target(target, tmp_path / "checkpoints", 2.0)


def test_execute_target_null_result_when_zero_tracklets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=3)]
    )
    monkeypatch.setattr(hunter_cli, "_acquire_and_convert_night", lambda *a, **k: None)
    monkeypatch.setattr(
        hunter_cli.positive_control,
        "run_positive_control",
        lambda **kwargs: {"n_tracklets_linked": 0, "review_packets": []},
    )
    target = {"target_id": "radec_10.00_5.00", "ra_deg": 10.0, "dec_deg": 5.0}

    result = hunter_cli.execute_target(target, tmp_path / "checkpoints", 2.0)

    assert result == {
        "execution_status": "null_result",
        "candidate_ids": [],
        "nights_acquired": ["20240101", "20240102", "20240103"],
        "scored_candidates": [],
    }


def test_execute_target_success_reviews_real_scored_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=3)]
    )
    monkeypatch.setattr(hunter_cli, "_acquire_and_convert_night", lambda *a, **k: None)
    packet = _minimal_scored_neo_packet()
    monkeypatch.setattr(
        hunter_cli.positive_control,
        "run_positive_control",
        lambda **kwargs: {"n_tracklets_linked": 1, "review_packets": [packet]},
    )
    target = {"target_id": "radec_10.00_5.00", "ra_deg": 10.0, "dec_deg": 5.0}

    result = hunter_cli.execute_target(target, tmp_path / "checkpoints", 2.0)

    assert result["execution_status"] == "success"
    assert result["candidate_ids"] == ["hunter-test-T1"]
    assert len(result["scored_candidates"]) == 1
    verdict = result["scored_candidates"][0]["verdict"]
    # Offline review always fails known-object association (no live evidence
    # available) -- this is the project's own intentional, conservative gate,
    # not a bug in this orchestration.
    assert verdict.verdict == "REJECT"


def test_ingest_and_maybe_register_followup_skips_registry_on_reject(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    packet = _minimal_scored_neo_packet()
    neo = schemas.ScoredNEO.model_validate(packet)
    verdict = adversarial_review.run_adversarial_review(neo, offline=True)
    assert verdict.verdict == "REJECT"
    target = {"target_id": "radec_10.00_5.00"}

    hunter_cli._ingest_and_maybe_register_followup(
        db_path, ledger_db_path, "search-1", "run-1", target, {"packet": packet, "verdict": verdict}
    )

    from candidate_ledger import list_records

    records = list_records(ledger_db_path)
    assert len(records) == 1
    assert records[0]["review_status"] == "reject"
    assert hunter_state.list_follow_ups(db_path, status=None) == []


def test_ingest_and_maybe_register_followup_registers_on_survive(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    packet = _minimal_scored_neo_packet()
    verdict = adversarial_review.ReviewVerdict(
        object_id="hunter-test-T1",
        verdict="SURVIVE",
        challenges=(),
        fail_count=0,
        warning_count=0,
        summary="test forced survive",
        reviewed_at_utc="2024-01-01T00:00:00+00:00",
    )
    target = {"target_id": "radec_10.00_5.00"}

    hunter_cli._ingest_and_maybe_register_followup(
        db_path, ledger_db_path, "search-1", "run-1", target, {"packet": packet, "verdict": verdict}
    )

    follow_ups = hunter_state.list_follow_ups(db_path, status="open")
    assert len(follow_ups) == 1
    assert follow_ups[0]["target_id"] == "radec_10.00_5.00"
    assert follow_ups[0]["priority"] == pytest.approx(0.8)


def _seed_pending_manifest(db_path: Path, search_id: str = "search-1") -> None:
    targets = [
        hunter_state.ManifestTarget(
            target_id="radec_10.00_5.00",
            ra_deg=10.0,
            dec_deg=5.0,
            score=0.9,
            selection_reason="test",
            coverage_inventory_id="field-a",
        )
    ]
    hunter_state.create_search_manifest(
        db_path, search_id, "new", 1, "p", "d", targets, 10, True, {}
    )


def test_run_search_completes_and_marks_manifest_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [],
        },
    )

    result = hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    assert result["status"] == "completed"
    assert result["n_failed"] == 0
    manifest = hunter_state.get_search_manifest(db_path, "search-1")
    assert manifest["status"] == "executed"
    run = hunter_state.get_search_run(db_path, result["run_id"])
    assert run["status"] == "completed"


def test_run_search_rejects_rerun_of_already_executed_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        },
    )
    hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    with pytest.raises(ValueError, match="already executed"):
        hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")


def test_run_search_resumes_interrupted_run_without_reexecuting_completed_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    hunter_state.create_search_run(db_path, "run-existing", "search-1", "abc123", {})
    hunter_state.upsert_run_target(db_path, "run-existing", "radec_10.00_5.00", "success")

    calls: list[str] = []
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda target, *a, **k: calls.append(target["target_id"]),
    )

    result = hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    assert calls == []  # already-successful target was skipped, not re-executed
    assert result["run_id"] == "run-existing"
    assert result["status"] == "completed"


def test_run_search_partial_status_when_some_targets_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    targets = [
        hunter_state.ManifestTarget(
            target_id="radec_10.00_5.00", ra_deg=10.0, dec_deg=5.0, score=0.9,
            selection_reason="test", coverage_inventory_id="field-a",
        ),
        hunter_state.ManifestTarget(
            target_id="radec_20.00_5.00", ra_deg=20.0, dec_deg=5.0, score=0.8,
            selection_reason="test", coverage_inventory_id="field-b",
        ),
    ]
    hunter_state.create_search_manifest(
        db_path, "search-1", "new", 2, "p", "d", targets, 10, True, {}
    )

    def _fake_execute(target, *a, **k):
        if target["target_id"] == "radec_10.00_5.00":
            raise RuntimeError("simulated acquisition failure")
        return {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        }

    monkeypatch.setattr(hunter_cli, "execute_target", _fake_execute)

    result = hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    assert result["status"] == "partial"
    assert result["n_failed"] == 1
    run_targets = hunter_state.get_run_targets(db_path, result["run_id"])
    assert run_targets["radec_10.00_5.00"]["execution_status"] == "failed"
    assert run_targets["radec_20.00_5.00"]["execution_status"] == "null_result"
    # A partial pass must not retire the manifest -- it needs to stay
    # resumable so the failed target can be retried.
    assert hunter_state.get_search_manifest(db_path, "search-1")["status"] == "pending"


def test_run_search_resumes_and_completes_after_a_prior_partial_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)

    def _fake_execute_fails(*a, **k):
        raise RuntimeError("transient network error")

    monkeypatch.setattr(hunter_cli, "execute_target", _fake_execute_fails)
    first = hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")
    assert first["status"] == "failed"
    assert hunter_state.get_search_manifest(db_path, "search-1")["status"] == "pending"

    def _fake_execute_succeeds(*a, **k):
        return {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        }

    monkeypatch.setattr(hunter_cli, "execute_target", _fake_execute_succeeds)
    second = hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    assert second["run_id"] == first["run_id"]  # resumed the same run, not a new one
    assert second["status"] == "completed"
    assert hunter_state.get_search_manifest(db_path, "search-1")["status"] == "executed"


def test_run_search_all_targets_failed_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)

    def _fake_execute(*a, **k):
        raise ValueError("simulated failure")

    monkeypatch.setattr(hunter_cli, "execute_target", _fake_execute)

    result = hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    assert result["status"] == "failed"
    assert result["n_failed"] == 1


def test_run_search_rejects_expired_manifest(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    hunter_state.mark_manifest_status(db_path, "search-1", "expired")

    with pytest.raises(ValueError, match="unexpected status"):
        hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")


def test_run_search_ingests_scored_candidate_and_registers_followup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    packet = _minimal_scored_neo_packet()
    verdict = adversarial_review.ReviewVerdict(
        object_id="hunter-test-T1",
        verdict="SURVIVE",
        challenges=(),
        fail_count=0,
        warning_count=0,
        summary="test forced survive",
        reviewed_at_utc="2024-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "success",
            "candidate_ids": ["hunter-test-T1"],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [{"packet": packet, "verdict": verdict}],
        },
    )

    result = hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    assert result["status"] == "completed"
    from candidate_ledger import list_records

    assert len(list_records(ledger_db_path)) == 1
    follow_ups = hunter_state.list_follow_ups(db_path, status="open")
    assert len(follow_ups) == 1
    assert follow_ups[0]["originating_run_id"] == result["run_id"]


def test_run_search_marks_originating_followup_actioned_after_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    follow_up_id = hunter_state.add_follow_up(
        db_path,
        target_id="radec_10.00_5.00",
        reason="prior borderline candidate",
        priority=0.6,
        recommended_action="operator review",
        evidence_ref="candidate_ledger:cand-1",
    )
    targets = [
        hunter_state.ManifestTarget(
            target_id="radec_10.00_5.00", ra_deg=10.0, dec_deg=5.0, score=0.6,
            selection_reason="open follow-up (registry): prior borderline candidate",
            coverage_inventory_id=None,
        )
    ]
    hunter_state.create_search_manifest(
        db_path, "search-followup-1", "follow_up", 1, "p", "d", targets, 1, True, {}
    )
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        },
    )

    hunter_cli.run_search(db_path, ledger_db_path, "search-followup-1", tmp_path / "checkpoints")

    assert hunter_state.list_follow_ups(db_path, status="open") == []
    actioned = hunter_state.list_follow_ups(db_path, status="actioned")
    assert len(actioned) == 1
    assert actioned[0]["follow_up_id"] == follow_up_id


def test_run_search_does_not_action_followups_for_new_mode_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    hunter_state.add_follow_up(
        db_path,
        target_id="radec_10.00_5.00",
        reason="unrelated open follow-up",
        priority=0.6,
        recommended_action="operator review",
        evidence_ref="candidate_ledger:cand-1",
    )
    _seed_pending_manifest(db_path)  # mode="new", same target_id coincidentally
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        },
    )

    hunter_cli.run_search(db_path, ledger_db_path, "search-1", tmp_path / "checkpoints")

    # A "new"-mode search must never touch the follow-up registry.
    assert len(hunter_state.list_follow_ups(db_path, status="open")) == 1


def test_main_dispatches_run_new_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        },
    )

    exit_code = hunter_cli.main(
        [
            "run-new-search",
            "--search-id",
            "search-1",
            "--db",
            str(db_path),
            "--candidate-ledger-db",
            str(ledger_db_path),
            "--checkpoint-root",
            str(tmp_path / "checkpoints"),
        ]
    )

    assert exit_code == 0
    assert "status=completed" in capsys.readouterr().out


def test_cmd_run_new_search_with_explicit_search_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        },
    )
    args = argparse.Namespace(
        search_id="search-1",
        db=str(db_path),
        candidate_ledger_db=str(ledger_db_path),
        checkpoint_root=str(tmp_path / "checkpoints"),
        size_deg=2.0,
    )

    exit_code = hunter_cli.cmd_run_new_search(args)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "status=completed" in out


def test_cmd_run_new_search_with_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    _seed_pending_manifest(db_path)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        },
    )
    args = argparse.Namespace(
        search_id=None,
        db=str(db_path),
        candidate_ledger_db=str(ledger_db_path),
        checkpoint_root=str(tmp_path / "checkpoints"),
        size_deg=2.0,
    )

    exit_code = hunter_cli.cmd_run_new_search(args)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "status=completed" in out


def test_build_parser_run_new_search_requires_search_id_or_latest() -> None:
    parser = hunter_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run-new-search"])


# ---------------------------------------------------------------------------
# create-new-search --mode follow-up, show-follow-ups
# ---------------------------------------------------------------------------


def test_followup_candidates_from_registry_extracts_radec_and_ranks(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    hunter_state.add_follow_up(
        db_path,
        target_id="radec_10.00_5.00",
        reason="borderline candidate",
        priority=0.4,
        recommended_action="operator review",
        evidence_ref="candidate_ledger:cand-1",
    )
    hunter_state.add_follow_up(
        db_path,
        target_id="radec_20.00_5.00",
        reason="survive candidate",
        priority=0.9,
        recommended_action="operator review",
        evidence_ref="candidate_ledger:cand-2",
    )

    candidates = hunter_cli._followup_candidates_from_registry(db_path)

    # list_follow_ups already orders by priority DESC -- the 0.9-priority
    # entry (ra=20.0) comes first.
    assert [c["ra_deg"] for c in candidates] == [20.0, 10.0]
    assert all(c["field_id"] is None for c in candidates)
    assert "survive candidate" in candidates[0]["reason"]


def test_followup_candidates_from_insufficient_coverage_already_sufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=5)]
    )
    queue_path = _write_target_queue_with_rows(
        tmp_path / "target_priority_queue.csv", [_insufficient_coverage_row(1, 10.0, 5.0)]
    )

    def _fail_if_called(*a, **k):
        raise AssertionError("no live recheck needed -- already covered")

    monkeypatch.setattr(
        hunter_cli.coverage_inventory.bounded_ingest, "run_bounded_ingest", _fail_if_called
    )

    candidates, n_still_insufficient = hunter_cli._followup_candidates_from_insufficient_coverage(
        queue_path
    )

    assert n_still_insufficient == 0
    assert len(candidates) == 1
    assert candidates[0]["field_id"] == "field-a"
    assert "5 real distinct night(s)" in candidates[0]["reason"]


def test_followup_candidates_from_insufficient_coverage_still_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=2)]
    )
    queue_path = _write_target_queue_with_rows(
        tmp_path / "target_priority_queue.csv", [_insufficient_coverage_row(1, 10.0, 5.0)]
    )

    candidates, n_still_insufficient = hunter_cli._followup_candidates_from_insufficient_coverage(
        queue_path
    )

    assert candidates == []
    assert n_still_insufficient == 1


def test_followup_candidates_from_insufficient_coverage_triggers_live_recheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    queue_path = _write_target_queue_with_rows(
        tmp_path / "target_priority_queue.csv", [_insufficient_coverage_row(1, 10.0, 5.0)]
    )

    def _fake_run_bounded_ingest(*, ra, dec, size_deg, start_jd, end_jd, out_dir, **_):
        return {
            "n_rows": 30,
            "distinct_nights_yyyymmdd": ["20240101", "20240102", "20240103", "20240104"],
            "raw_response_sha256": "d" * 64,
            "raw_response_path": str(out_dir / "raw.ipac"),
        }

    monkeypatch.setattr(
        hunter_cli.coverage_inventory.bounded_ingest, "run_bounded_ingest", _fake_run_bounded_ingest
    )

    candidates, n_still_insufficient = hunter_cli._followup_candidates_from_insufficient_coverage(
        queue_path
    )

    assert n_still_insufficient == 0
    assert len(candidates) == 1
    assert candidates[0]["ra_deg"] == 10.0
    committed = list(hunter_cli._COVERAGE_INVENTORY_DIR.glob("*.json"))
    assert len(committed) == 1


def test_followup_candidates_from_insufficient_coverage_no_matching_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")

    candidates, n_still_insufficient = hunter_cli._followup_candidates_from_insufficient_coverage(
        queue_path
    )

    assert candidates == []
    assert n_still_insufficient == 0


def test_followup_candidates_from_insufficient_coverage_skips_other_statuses_and_bad_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=5)]
    )
    rows = [
        {
            "rank": 1,
            "priority": 0.9,
            "status": "null_result",
            "data_role": "live_search",
            "source": "test",
            "selection_rule": "test",
            "evidence_path": "",
            "notes": "ra_deg=99.0 dec_deg=1.0; not insufficient_coverage, must be skipped",
        },
        {
            "rank": 2,
            "priority": 0.8,
            "status": "insufficient_coverage",
            "data_role": "live_search",
            "source": "test",
            "selection_rule": "test",
            "evidence_path": "",
            "notes": "no coordinates in this row at all",
        },
        _insufficient_coverage_row(3, 10.0, 5.0),
    ]
    queue_path = _write_target_queue_with_rows(tmp_path / "target_priority_queue.csv", rows)

    candidates, n_still_insufficient = hunter_cli._followup_candidates_from_insufficient_coverage(
        queue_path
    )

    assert n_still_insufficient == 0
    assert len(candidates) == 1
    assert candidates[0]["ra_deg"] == 10.0


def test_discover_followup_targets_combines_and_ranks_both_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    db_path = tmp_path / "hunter_state.sqlite"
    hunter_state.add_follow_up(
        db_path,
        target_id="radec_30.00_5.00",
        reason="high-priority registry entry",
        priority=0.95,
        recommended_action="operator review",
        evidence_ref="candidate_ledger:cand-1",
    )
    inv_dir = hunter_cli._COVERAGE_INVENTORY_DIR
    _write_coverage_inventory(
        inv_dir / "seed.json", [_coverage_field_result("field-a", 10.0, 5.0, n_nights=5)]
    )
    queue_path = _write_target_queue_with_rows(
        tmp_path / "target_priority_queue.csv", [_insufficient_coverage_row(1, 10.0, 5.0)]
    )

    result = hunter_cli.discover_followup_targets(
        db_path, requested_n=2, target_queue_path=queue_path
    )

    assert result["sufficiency_met"] is True
    assert len(result["eligible"]) == 2
    # Registry entry (priority 0.95) ranks ahead of the recovered-coverage
    # candidate (fixed priority 0.5).
    assert result["eligible"][0]["ra_deg"] == 30.0
    assert result["eligible"][1]["ra_deg"] == 10.0


def test_discover_followup_targets_reports_insufficiency_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    db_path = tmp_path / "hunter_state.sqlite"
    queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")

    result = hunter_cli.discover_followup_targets(
        db_path, requested_n=3, target_queue_path=queue_path
    )

    assert result["sufficiency_met"] is False
    assert result["eligible"] == []


def test_cmd_create_new_search_follow_up_mode_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_dirs(monkeypatch, tmp_path)
    db_path = tmp_path / "hunter_state.sqlite"
    hunter_state.add_follow_up(
        db_path,
        target_id="radec_30.00_5.00",
        reason="high-priority registry entry",
        priority=0.95,
        recommended_action="operator review",
        evidence_ref="candidate_ledger:cand-1",
    )
    queue_path = _write_empty_target_queue(tmp_path / "target_priority_queue.csv")

    args = argparse.Namespace(
        targets=1,
        mode="follow-up",
        neo_class="all",
        jd="now",
        max_pool=200,
        target_queue=str(queue_path),
        ranking_policy=str(field_selector._DEFAULT_RANKING_POLICY_PATH),
        db=str(db_path),
    )

    exit_code = hunter_cli.cmd_create_new_search(args)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "sufficiency_met=True" in out
    manifest = hunter_state.get_latest_pending_manifest(db_path, mode="follow_up")
    assert manifest["targets"][0]["ra_deg"] == 30.0


def test_cmd_show_follow_ups_prints_table_with_review_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    packet = _minimal_scored_neo_packet()
    from candidate_ledger import CandidateLedgerDefaults, record_from_packet, upsert_record

    defaults = CandidateLedgerDefaults(
        source_dataset_id="search-1",
        candidate_generator="test",
        regeneration_command="test",
        review_status="survive",
    )
    record = record_from_packet(packet, defaults)
    upsert_record(ledger_db_path, record)
    hunter_state.add_follow_up(
        db_path,
        target_id="radec_10.00_5.00",
        reason="test reason",
        priority=0.9,
        recommended_action="operator review before submission",
        evidence_ref="candidate_ledger:hunter-test-T1",
        candidate_id="hunter-test-T1",
    )

    args = argparse.Namespace(
        status="open", limit=None, db=str(db_path), candidate_ledger_db=str(ledger_db_path)
    )
    exit_code = hunter_cli.cmd_show_follow_ups(args)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "radec_10.00_5.00" in out
    assert "survive" in out
    assert "operator review before submission" in out


def test_cmd_show_follow_ups_reports_none_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    args = argparse.Namespace(
        status="open",
        limit=None,
        db=str(db_path),
        candidate_ledger_db=str(tmp_path / "missing.sqlite"),
    )

    exit_code = hunter_cli.cmd_show_follow_ups(args)

    assert exit_code == 0
    assert "No follow-ups with status='open'" in capsys.readouterr().out


def test_cmd_show_follow_ups_status_all_shows_every_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    follow_up_id = hunter_state.add_follow_up(
        db_path,
        target_id="radec_10.00_5.00",
        reason="test",
        priority=0.5,
        recommended_action="review",
        evidence_ref="candidate_ledger:x",
    )
    hunter_state.update_follow_up_status(db_path, follow_up_id, "dismissed")

    args = argparse.Namespace(
        status="all",
        limit=None,
        db=str(db_path),
        candidate_ledger_db=str(tmp_path / "missing.sqlite"),
    )
    exit_code = hunter_cli.cmd_show_follow_ups(args)

    assert exit_code == 0
    assert "radec_10.00_5.00" in capsys.readouterr().out


def test_build_parser_create_new_search_accepts_follow_up_mode() -> None:
    parser = hunter_cli.build_parser()
    args = parser.parse_args(["create-new-search", "--targets", "1", "--mode", "follow-up"])
    assert args.mode == "follow-up"


def test_build_parser_show_follow_ups_defaults() -> None:
    parser = hunter_cli.build_parser()
    args = parser.parse_args(["show-follow-ups"])
    assert args.status == "open"
    assert args.limit is None


def test_main_dispatches_show_follow_ups(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    exit_code = hunter_cli.main(["show-follow-ups", "--db", str(db_path)])
    assert exit_code == 0
    assert "No follow-ups" in capsys.readouterr().out


def test_cmd_run_new_search_latest_picks_follow_up_mode_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    ledger_db_path = tmp_path / "candidate_ledger.sqlite"
    targets = [
        hunter_state.ManifestTarget(
            target_id="radec_10.00_5.00", ra_deg=10.0, dec_deg=5.0, score=0.9,
            selection_reason="test", coverage_inventory_id="field-a",
        )
    ]
    hunter_state.create_search_manifest(
        db_path, "search-followup-1", "follow_up", 1, "p", "d", targets, 1, True, {}
    )
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": [],
            "scored_candidates": [],
        },
    )
    args = argparse.Namespace(
        search_id=None,
        db=str(db_path),
        candidate_ledger_db=str(ledger_db_path),
        checkpoint_root=str(tmp_path / "checkpoints"),
        size_deg=2.0,
    )

    exit_code = hunter_cli.cmd_run_new_search(args)

    assert exit_code == 0
    assert "status=completed" in capsys.readouterr().out
