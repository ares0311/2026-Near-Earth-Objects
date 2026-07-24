from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from hunter_state import (
    ManifestTarget,
    add_follow_up,
    complete_search_run,
    create_search_manifest,
    create_search_run,
    get_latest_pending_manifest,
    get_latest_run_for_search,
    get_run_targets,
    get_search_manifest,
    get_search_run,
    init_db,
    list_follow_ups,
    mark_manifest_status,
    target_id_from_radec,
    update_follow_up_status,
    upsert_run_target,
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


def test_init_db_records_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"

    init_db(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT value FROM hunter_state_metadata WHERE key = 'schema_version'"
        ).fetchone()
    assert row == ("1",)


def test_target_id_from_radec_matches_coordinate_key_rounding() -> None:
    assert target_id_from_radec(251.664, -22.501) == "radec_251.66_-22.50"
    assert target_id_from_radec(0.0, 0.0) == "radec_0.00_0.00"


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
    assert [t["target_id"] for t in manifest["targets"]] == [t.target_id for t in targets]
    assert [t["rank"] for t in manifest["targets"]] == [1, 2, 3]


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


def test_create_search_manifest_rejects_too_many_targets(tmp_path: Path) -> None:
    db_path = tmp_path / "hunter_state.sqlite"
    with pytest.raises(ValueError, match="must not exceed requested_n"):
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
