from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from hunter_state import (
    CatalogTarget,
    ManifestTarget,
    acquired_nights_for_target,
    add_follow_up,
    commit_target_result,
    complete_search_run,
    create_search_manifest,
    create_search_run,
    get_latest_pending_manifest,
    get_latest_run_for_search,
    get_operator_state,
    get_run_targets,
    get_search_manifest,
    get_search_run,
    init_db,
    list_follow_ups,
    list_target_catalog,
    list_target_history,
    mark_manifest_status,
    radec_from_target_id,
    searched_target_ids,
    target_catalog_count,
    target_id_from_radec,
    update_follow_up_status,
    update_search_run_model_versions,
    upsert_run_target,
    upsert_target_catalog,
)


def _targets(n: int) -> list[ManifestTarget]:
    return [
        ManifestTarget(
            target_id=target_id_from_radec(10.0 * i, -5.0 * i),
            ra_deg=10.0 * i,
            dec_deg=-5.0 * i,
            score=1.0 - 0.01 * i,
            selection_reason="top-ranked eligible field",
            coverage_inventory_id="inv-1",
        )
        for i in range(n)
    ]


def _catalog_target(target_id: str = "radec_10.00_5.00") -> CatalogTarget:
    return CatalogTarget(
        target_id=target_id,
        primary_survey_id=f"ztf-dr24-field:{target_id}",
        canonical_id="icrs:10.00:5.00:r3.5deg",
        target_kind="sky_field",
        survey="ZTF DR24 archival science images",
        ra_deg=10.0,
        dec_deg=5.0,
        neo_class="all",
        ranking_score=0.9,
        estimated_storage_mb=60.0,
        estimated_compute_seconds=180.0,
        scientific_metrics={"geometry_score": 0.9},
        source_provenance={"source": "known-ground-truth fixture"},
    )


def test_init_db_records_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"

    init_db(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT value FROM hunter_state_metadata WHERE key = 'schema_version'"
        ).fetchone()
    assert row == ("5",)


def test_operator_state_projects_pending_follow_up_and_latest_results(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    assert get_operator_state(db_path).pending_search_ids == ()

    targets = _targets(1)
    create_search_manifest(
        db_path,
        "search-1",
        "new",
        1,
        "policy.json",
        "digest",
        targets,
        10,
        True,
        {},
    )
    add_follow_up(
        db_path,
        targets[0].target_id,
        "additional evidence warranted",
        0.7,
        "acquire another night",
        "evidence.json",
    )
    create_search_run(db_path, "run-1", "search-1", "abc123", {})
    upsert_run_target(db_path, "run-1", targets[0].target_id, "success")

    state = get_operator_state(db_path)
    assert state.pending_search_ids == ("search-1",)
    assert state.open_follow_up_count == 1
    assert state.last_result_count == 1


def test_target_catalog_is_distinct_versioned_and_upsertable(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter.sqlite"
    target = _catalog_target()

    assert (
        upsert_target_catalog(
            db_path, catalog_version="planning-v1", targets=[target]
        )
        == 1
    )
    stored = list_target_catalog(db_path, catalog_version="planning-v1")
    assert len(stored) == 1
    assert stored[0]["primary_survey_id"] == target.primary_survey_id
    assert stored[0]["scientific_metrics"] == {"geometry_score": 0.9}
    assert stored[0]["source_provenance"] == {
        "source": "known-ground-truth fixture"
    }

    replacement = CatalogTarget(
        **{
            **target.__dict__,
            "ranking_score": 0.8,
            "scientific_metrics": {"geometry_score": 0.8},
        }
    )
    upsert_target_catalog(
        db_path, catalog_version="planning-v2", targets=[replacement]
    )
    all_rows = list_target_catalog(db_path)
    assert len(all_rows) == 2
    v2_rows = list_target_catalog(db_path, catalog_version="planning-v2")
    assert v2_rows[0]["catalog_version"] == "planning-v2"
    assert v2_rows[0]["ranking_score"] == 0.8
    assert len(list_target_catalog(db_path, catalog_version="planning-v1")) == 1
    assert target_catalog_count(db_path, catalog_version="planning-v1") == 1
    assert target_catalog_count(db_path, catalog_version="planning-v2") == 1


def test_target_catalog_rejects_empty_duplicate_and_invalid_records(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter.sqlite"
    target = _catalog_target()
    with pytest.raises(ValueError, match="catalog_version"):
        upsert_target_catalog(db_path, catalog_version="", targets=[target])
    with pytest.raises(ValueError, match="at least one"):
        upsert_target_catalog(db_path, catalog_version="v1", targets=[])
    with pytest.raises(ValueError, match="unique target_id"):
        upsert_target_catalog(
            db_path, catalog_version="v1", targets=[target, target]
        )
    invalid = CatalogTarget(**{**target.__dict__, "canonical_id": ""})
    with pytest.raises(ValueError, match="canonical_id"):
        upsert_target_catalog(
            db_path, catalog_version="v1", targets=[invalid]
        )


def test_init_db_migrates_v1_manifest_targets_and_backfills_history(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE search_manifests (
                search_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, mode TEXT NOT NULL,
                requested_n INTEGER NOT NULL, actual_n_selected INTEGER NOT NULL,
                ranking_policy_path TEXT NOT NULL, ranking_policy_digest TEXT NOT NULL,
                discovery_pool_size_explored INTEGER NOT NULL, sufficiency_met INTEGER NOT NULL,
                config_json TEXT NOT NULL, status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE search_manifest_targets (
                search_id TEXT NOT NULL, rank INTEGER NOT NULL, target_id TEXT NOT NULL,
                ra_deg REAL NOT NULL, dec_deg REAL NOT NULL, score REAL NOT NULL,
                selection_reason TEXT NOT NULL, coverage_inventory_id TEXT,
                PRIMARY KEY (search_id, target_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO search_manifests VALUES "
            "('legacy-search', '2026-07-24T00:00:00Z', 'new', 1, 1, 'p', 'd', "
            "1, 1, '{}', 'executed')"
        )
        conn.execute(
            "INSERT INTO search_manifest_targets VALUES "
            "('legacy-search', 1, 'radec_10.00_5.00', 10.0, 5.0, 0.5, 'legacy', 'field')"
        )
        conn.commit()

    init_db(db_path)

    manifest = get_search_manifest(db_path, "legacy-search")
    assert manifest["targets"][0]["coverage_provenance"] == {}
    assert manifest["targets"][0]["validity_state"] == "unknown"
    history = list_target_history(db_path, "radec_10.00_5.00")
    assert history[0]["status"] == "legacy_manifest_import"
    assert history[0]["contract_version"] == "hunter-identity-history-1.0.0"
    assert history[0]["canonical_id"] == "radec_10.00_5.00"
    assert history[0]["aliases"] == ["radec_10.00_5.00"]
    assert history[0]["alias_provenance"][0]["kind"] == "hunter_target_id"
    assert history[0]["producing_project"] == "NEOHunter"
    assert history[0]["disposition"] == "new"
    assert history[0]["completeness_state"] == "complete"


def test_init_db_migrates_legacy_follow_up_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter.sqlite"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE follow_up_registry (
                follow_up_id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                candidate_id TEXT,
                flagged_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                evidence_ref TEXT NOT NULL,
                priority REAL NOT NULL,
                status TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                originating_run_id TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    init_db(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(follow_up_registry)")
        }
    assert {
        "required_data",
        "estimated_storage_mb",
        "estimated_compute_seconds",
    } <= columns


def test_target_id_from_radec_matches_coordinate_key_rounding() -> None:
    assert target_id_from_radec(251.664, -22.501) == "radec_251.66_-22.50"
    assert target_id_from_radec(0.0, 0.0) == "radec_0.00_0.00"


def test_radec_from_target_id_is_the_inverse_of_target_id_from_radec() -> None:
    assert radec_from_target_id("radec_251.66_-22.50") == (251.66, -22.50)
    assert radec_from_target_id("radec_0.00_0.00") == (0.0, 0.0)


def test_radec_from_target_id_rejects_malformed_input() -> None:
    with pytest.raises(ValueError, match="not a radec_<ra>_<dec> key"):
        radec_from_target_id("not-a-target-id")


def test_create_and_get_search_manifest_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    targets = _targets(3)

    create_search_manifest(
        db_path,
        search_id="search-1",
        mode="new",
        requested_n=3,
        ranking_policy_path="data_selection/ranking_policies/ztf_field_ranking_v2.json",
        ranking_policy_digest="deadbeef",
        targets=targets,
        discovery_pool_size_explored=42,
        sufficiency_met=True,
        config={"survey": "ztf-dr24"},
    )

    manifest = get_search_manifest(db_path, "search-1")
    assert manifest["mode"] == "new"
    assert manifest["requested_n"] == 3
    assert manifest["actual_n_selected"] == 3
    assert manifest["sufficiency_met"] is True
    assert manifest["config"] == {"survey": "ztf-dr24"}
    assert manifest["status"] == "pending"
    assert len(manifest["manifest_sha256"]) == 64
    assert [t["target_id"] for t in manifest["targets"]] == [t.target_id for t in targets]
    assert [t["rank"] for t in manifest["targets"]] == [1, 2, 3]
    assert searched_target_ids(db_path) == {target.target_id for target in targets}
    assert {event["status"] for event in list_target_history(db_path)} == {
        "selected_pending"
    }
    selected = list_target_history(db_path)[0]
    assert selected["canonical_id"] == targets[0].target_id
    assert selected["aliases"] == [targets[0].target_id]
    assert selected["alias_provenance"] == [
        {
            "alias": targets[0].target_id,
            "kind": "hunter_target_id",
            "source": "NEOHunter",
        }
    ]
    assert selected["source_watermark"] == "coverage_inventory_id:inv-1"
    assert selected["search_state"] == "pending"
    assert selected["result_state"] == "not_executed"
    assert selected["freshness_state"] == "unknown"
    assert selected["completeness_state"] == "complete"


def test_manifest_checksum_rejects_target_substitution(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    target = _targets(1)[0]
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", [target], 1, True, {}
    )
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "UPDATE search_manifest_targets SET target_id = 'radec_99.00_5.00' "
            "WHERE search_id = 'search-1'"
        )
        conn.commit()

    with pytest.raises(ValueError, match="checksum mismatch"):
        get_search_manifest(db_path, "search-1")


def test_new_manifest_reservation_blocks_duplicate_but_followup_is_allowed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    target = _targets(1)
    create_search_manifest(
        db_path, "search-new-1", "new", 1, "p", "d", target, 1, True, {}
    )
    with pytest.raises(ValueError, match="governing search history"):
        create_search_manifest(
            db_path, "search-new-2", "new", 1, "p", "d", target, 1, True, {}
        )
    create_search_manifest(
        db_path, "search-followup", "follow_up", 1, "p", "d", target, 1, True, {}
    )


def test_commit_target_result_atomically_records_history_and_nights(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    target = _targets(1)[0]
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", [target], 1, True, {}
    )
    create_search_run(db_path, "run-1", "search-1", "abc", {"score": "v1"})

    commit_target_result(
        db_path,
        run_id="run-1",
        search_id="search-1",
        mode="new",
        target_id=target.target_id,
        execution_status="success",
        candidate_ids=["candidate-1"],
        error_message=None,
        nights_acquired=["20240101", "20240102", "20240103"],
        provenance={"validity_state": "valid"},
    )

    assert get_run_targets(db_path, "run-1")[target.target_id]["candidate_ids"] == [
        "candidate-1"
    ]
    assert acquired_nights_for_target(db_path, target.target_id) == {
        "20240101",
        "20240102",
        "20240103",
    }
    terminal = [
        event
        for event in list_target_history(db_path, target.target_id)
        if event["status"] == "success"
    ]
    assert terminal[0]["provenance"]["validity_state"] == "valid"
    assert terminal[0]["event_id"].startswith("run:run-1:")
    assert terminal[0]["observation_time"] == "20240101"
    assert terminal[0]["search_state"] == "executed"
    assert terminal[0]["result_state"] == "success"
    assert terminal[0]["disposition"] == "new"
    assert terminal[0]["source_watermark"] == "coverage_inventory_id:inv-1"
    assert terminal[0]["completeness_state"] == "complete"


def test_history_rejects_malformed_structured_aliases(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    target = _targets(1)[0]
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", [target], 1, True, {}
    )
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "UPDATE target_search_history SET aliases_json = 'not-json'"
        )
        conn.commit()

    with pytest.raises(ValueError):
        list_target_history(db_path)


@pytest.mark.parametrize(
    ("mode", "status", "message"),
    [
        ("new", "bogus", "execution_status must be one of"),
        ("bogus", "success", "mode must be one of"),
    ],
)
def test_commit_target_result_rejects_invalid_enums(
    tmp_path: Path, mode: str, status: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        commit_target_result(
            tmp_path / "hunter.sqlite",
            run_id="run",
            search_id="search",
            mode=mode,
            target_id="radec_1.00_1.00",
            execution_status=status,
            candidate_ids=[],
            error_message=None,
            nights_acquired=[],
            provenance={},
        )


def test_create_search_manifest_rejects_invalid_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with pytest.raises(ValueError, match="mode must be one of"):
        create_search_manifest(
            db_path,
            search_id="search-1",
            mode="bogus",
            requested_n=1,
            ranking_policy_path="p",
            ranking_policy_digest="d",
            targets=[],
            discovery_pool_size_explored=1,
            sufficiency_met=False,
            config={},
        )


def test_create_search_manifest_rejects_non_positive_requested_n(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with pytest.raises(ValueError, match="requested_n must be positive"):
        create_search_manifest(
            db_path,
            search_id="search-1",
            mode="new",
            requested_n=0,
            ranking_policy_path="p",
            ranking_policy_digest="d",
            targets=[],
            discovery_pool_size_explored=1,
            sufficiency_met=False,
            config={},
        )


def test_create_search_manifest_rejects_false_sufficiency(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires sufficiency_met=true"):
        create_search_manifest(
            tmp_path / "hunter.sqlite",
            search_id="search-1",
            mode="new",
            requested_n=1,
            ranking_policy_path="p",
            ranking_policy_digest="d",
            targets=_targets(1),
            discovery_pool_size_explored=1,
            sufficiency_met=False,
            config={},
        )


def test_create_search_manifest_rejects_non_exact_target_count(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with pytest.raises(ValueError, match="must exactly match requested_n"):
        create_search_manifest(
            db_path,
            search_id="search-1",
            mode="new",
            requested_n=1,
            ranking_policy_path="p",
            ranking_policy_digest="d",
            targets=_targets(2),
            discovery_pool_size_explored=2,
            sufficiency_met=True,
            config={},
        )


def test_create_search_manifest_rejects_duplicate_target_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    dup = _targets(1) * 2
    with pytest.raises(ValueError, match="unique target_id"):
        create_search_manifest(
            db_path,
            search_id="search-1",
            mode="new",
            requested_n=2,
            ranking_policy_path="p",
            ranking_policy_digest="d",
            targets=dup,
            discovery_pool_size_explored=2,
            sufficiency_met=True,
            config={},
        )


def test_create_search_manifest_rejects_invalid_validity_state(tmp_path: Path) -> None:
    target = _targets(1)[0]
    invalid = ManifestTarget(
        target_id=target.target_id,
        ra_deg=target.ra_deg,
        dec_deg=target.dec_deg,
        score=target.score,
        selection_reason=target.selection_reason,
        validity_state="fresh-enough",
    )
    with pytest.raises(ValueError, match="invalid manifest target validity_state"):
        create_search_manifest(
            tmp_path / "hunter.sqlite",
            "search-1",
            "new",
            1,
            "p",
            "d",
            [invalid],
            1,
            True,
            {},
        )


def test_get_search_manifest_missing_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    init_db(db_path)
    with pytest.raises(ValueError, match="no search manifest found"):
        get_search_manifest(db_path, "nope")


def test_get_latest_pending_manifest_filters_by_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-new", "new", 1, "p", "d", _targets(1), 1, True, {}
    )
    create_search_manifest(
        db_path, "search-fu", "follow_up", 1, "p", "d", _targets(1), 1, True, {}
    )

    latest_new = get_latest_pending_manifest(db_path, mode="new")
    assert latest_new["search_id"] == "search-new"

    latest_any = get_latest_pending_manifest(db_path)
    assert latest_any["search_id"] in {"search-new", "search-fu"}


def test_get_latest_pending_manifest_raises_when_none(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    init_db(db_path)
    with pytest.raises(ValueError, match="no pending search manifest"):
        get_latest_pending_manifest(db_path)


def test_mark_manifest_status_updates_and_validates(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", _targets(1), 1, True, {}
    )

    mark_manifest_status(db_path, "search-1", "executed")

    assert get_search_manifest(db_path, "search-1")["status"] == "executed"

    with pytest.raises(ValueError, match="status must be one of"):
        mark_manifest_status(db_path, "search-1", "bogus")

    with pytest.raises(ValueError, match="no search manifest found"):
        mark_manifest_status(db_path, "missing", "expired")


def test_create_search_run_requires_existing_manifest(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    init_db(db_path)
    with pytest.raises(ValueError, match="no search manifest found"):
        create_search_run(db_path, "run-1", "missing-search", "abc123", {})


def test_create_search_run_and_get_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", _targets(1), 1, True, {}
    )

    create_search_run(db_path, "run-1", "search-1", "abc123", {"link": "v1"})

    run = get_search_run(db_path, "run-1")
    assert run["search_id"] == "search-1"
    assert run["status"] == "running"
    assert run["completed_at"] is None
    assert run["model_versions"] == {"link": "v1"}


def test_update_search_run_model_versions_merges_without_discarding_prior_values(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", _targets(1), 1, True, {}
    )
    create_search_run(db_path, "run-1", "search-1", "abc123", {"link": "v1"})

    update_search_run_model_versions(
        db_path, "run-1", {"execution_contract": {"configured_workers": 3}}
    )

    assert get_search_run(db_path, "run-1")["model_versions"] == {
        "link": "v1",
        "execution_contract": {"configured_workers": 3},
    }


def test_update_search_run_model_versions_rejects_empty_or_missing_run(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with pytest.raises(ValueError, match="must not be empty"):
        update_search_run_model_versions(db_path, "run-1", {})
    with pytest.raises(ValueError, match="no search run found"):
        update_search_run_model_versions(db_path, "run-1", {"worker": 3})


def test_get_search_run_missing_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    init_db(db_path)
    with pytest.raises(ValueError, match="no search run found"):
        get_search_run(db_path, "missing")


def test_get_latest_run_for_search_returns_none_when_absent(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", _targets(1), 1, True, {}
    )
    assert get_latest_run_for_search(db_path, "search-1") is None


def test_get_latest_run_for_search_returns_most_recent(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", _targets(1), 1, True, {}
    )
    create_search_run(db_path, "run-1", "search-1", "abc123", {})

    found = get_latest_run_for_search(db_path, "search-1")

    assert found is not None
    assert found["run_id"] == "run-1"


def test_complete_search_run_rejects_running_and_invalid(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", _targets(1), 1, True, {}
    )
    create_search_run(db_path, "run-1", "search-1", "abc123", {})

    with pytest.raises(ValueError, match="terminal status must be one of"):
        complete_search_run(db_path, "run-1", "running")
    with pytest.raises(ValueError, match="terminal status must be one of"):
        complete_search_run(db_path, "run-1", "bogus")

    complete_search_run(db_path, "run-1", "completed")
    run = get_search_run(db_path, "run-1")
    assert run["status"] == "completed"
    assert run["completed_at"] is not None
    assert run["failure_reason"] is None


def test_complete_search_run_missing_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    init_db(db_path)
    with pytest.raises(ValueError, match="no search run found"):
        complete_search_run(db_path, "missing", "failed", failure_reason="boom")


def test_upsert_run_target_insert_then_resume_update(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    create_search_manifest(
        db_path, "search-1", "new", 1, "p", "d", _targets(1), 1, True, {}
    )
    create_search_run(db_path, "run-1", "search-1", "abc123", {})
    target_id = _targets(1)[0].target_id

    upsert_run_target(db_path, "run-1", target_id, "null_result")
    targets = get_run_targets(db_path, "run-1")
    assert targets[target_id]["execution_status"] == "null_result"
    assert targets[target_id]["candidate_ids"] == []
    assert targets[target_id]["nights_acquired"] == []

    upsert_run_target(
        db_path,
        "run-1",
        target_id,
        "success",
        candidate_ids=["cand-1"],
        nights_acquired=["20240101", "20240102", "20240103"],
    )
    targets = get_run_targets(db_path, "run-1")
    assert targets[target_id]["execution_status"] == "success"
    assert targets[target_id]["candidate_ids"] == ["cand-1"]
    assert len(targets[target_id]["nights_acquired"]) == 3


def test_upsert_run_target_rejects_invalid_status(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with pytest.raises(ValueError, match="execution_status must be one of"):
        upsert_run_target(db_path, "run-1", "target-1", "bogus")


def test_get_run_targets_empty_for_unknown_run(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    init_db(db_path)
    assert get_run_targets(db_path, "missing") == {}


def test_add_follow_up_and_list_ordering(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"

    low_id = add_follow_up(
        db_path,
        target_id="radec_10.00_-5.00",
        reason="insufficient coverage, one more night needed",
        priority=0.2,
        recommended_action="acquire one more night",
        evidence_ref="data_selection/target_priority_queue.csv#row-12",
    )
    high_id = add_follow_up(
        db_path,
        target_id="radec_20.00_-10.00",
        reason="borderline candidate needs re-review",
        priority=0.9,
        recommended_action="rerun adversarial review with fresh MPC snapshot",
        evidence_ref="docs/evidence/live/example.md",
        candidate_id="cand-42",
        originating_run_id="run-1",
    )

    open_items = list_follow_ups(db_path)
    assert [item["follow_up_id"] for item in open_items] == [high_id, low_id]
    assert open_items[0]["candidate_id"] == "cand-42"
    assert open_items[0]["originating_run_id"] == "run-1"

    limited = list_follow_ups(db_path, limit=1)
    assert len(limited) == 1
    assert limited[0]["follow_up_id"] == high_id

    all_statuses = list_follow_ups(db_path, status=None)
    assert len(all_statuses) == 2


def test_add_follow_up_is_idempotent_for_same_run_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    first = add_follow_up(
        db_path,
        "radec_1.00_1.00",
        "reason",
        0.5,
        "action",
        "evidence",
        candidate_id="candidate",
        originating_run_id="run",
    )
    second = add_follow_up(
        db_path,
        "radec_1.00_1.00",
        "reason",
        0.5,
        "action",
        "evidence",
        candidate_id="candidate",
        originating_run_id="run",
    )
    assert second == first
    assert len(list_follow_ups(db_path)) == 1


def test_add_follow_up_rejects_empty_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with pytest.raises(ValueError, match="target_id must be a non-empty string"):
        add_follow_up(db_path, "", "reason", 0.5, "action", "evidence")
    with pytest.raises(ValueError, match="reason must be a non-empty string"):
        add_follow_up(db_path, "radec_1.00_1.00", "  ", 0.5, "action", "evidence")
    with pytest.raises(ValueError, match="evidence_ref must be a non-empty string"):
        add_follow_up(db_path, "radec_1.00_1.00", "reason", 0.5, "action", "")
    with pytest.raises(ValueError, match="recommended_action must be a non-empty string"):
        add_follow_up(db_path, "radec_1.00_1.00", "reason", 0.5, "", "evidence")


def test_list_follow_ups_rejects_invalid_status(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    init_db(db_path)
    with pytest.raises(ValueError, match="status must be one of"):
        list_follow_ups(db_path, status="bogus")


def test_update_follow_up_status_transitions_and_validates(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    follow_up_id = add_follow_up(
        db_path, "radec_1.00_1.00", "reason", 0.5, "action", "evidence"
    )

    update_follow_up_status(db_path, follow_up_id, "actioned")
    items = list_follow_ups(db_path, status="actioned")
    assert items[0]["follow_up_id"] == follow_up_id

    with pytest.raises(ValueError, match="status must be one of"):
        update_follow_up_status(db_path, follow_up_id, "bogus")

    with pytest.raises(ValueError, match="no follow-up found"):
        update_follow_up_status(db_path, 99999, "dismissed")
