"""Regression tests for NEOHunter's own cross-project history export.

Deliverable A is the publishing half of the Hunter interoperability contract:
this repository writes ``data_selection/hunter_prior_search_history_v1.json`` so
the two sibling Hunters can answer "has NEOHunter already searched this?" from
evidence rather than assumption.

These tests are entirely offline and never touch a sibling repository.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import hunter_cross_project as hcp

# The real committed queue's column set; every fixture row must match it so a
# test can never pass against a shape the production reader would reject.
_QUEUE_COLUMNS = [
    "rank",
    "priority",
    "status",
    "data_role",
    "source",
    "selection_rule",
    "evidence_path",
    "notes",
]


def _queue_row(
    *,
    rank: int = 1,
    status: str = "null_result",
    notes: str = "ra_deg=217.41 dec_deg=-15.0; searched 2026-07-17",
    evidence_path: str = "docs/evidence/live/2026-07-17-example.md",
    source: str = "sky_field_selector",
) -> dict[str, str]:
    """Build one target-priority-queue row in the real committed shape."""
    return {
        "rank": str(rank),
        "priority": "0.9308",
        "status": status,
        "data_role": "live_search",
        "source": source,
        "selection_rule": "known-object density 0.93",
        "evidence_path": evidence_path,
        "notes": notes,
    }


def _write_queue(path: Path, rows: list[dict[str, str]]) -> Path:
    """Write a target priority queue CSV the production reader will accept."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_QUEUE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# Positive case: a real publish that a consumer can actually use.
# ---------------------------------------------------------------------------


def test_export_publishes_schema_version_one_with_real_entries(tmp_path: Path) -> None:
    """The published export carries schema_version 1 and real, dated entries."""
    queue = _write_queue(tmp_path / "queue.csv", [_queue_row()])
    out = tmp_path / "data_selection" / "hunter_prior_search_history_v1.json"

    payload = hcp.build_own_history_export(
        target_queue_path=queue, generated_at_utc="2026-08-01T00:00:00+00:00"
    )

    assert payload["schema_version"] == hcp.CROSS_PROJECT_SCHEMA_VERSION == 1
    assert payload["manifest_id"] == hcp.CROSS_PROJECT_HISTORY_MANIFEST_ID
    source = payload["sources"][0]
    assert source["searched_by"] == "NEO-Hunter"
    assert source["source_project"] == "2026 Near Earth Objects"
    # Provenance a consumer re-verifies: repo-relative path plus a real digest.
    assert source["source_path"].startswith("data_selection/") or Path(
        source["source_path"]
    ).name == "queue.csv"
    assert len(source["source_sha256"]) == 64
    entry = source["entries"][0]
    assert entry["target_id"] == "radec_217.41_-15.00"
    assert entry["searched_at"] == "2026-07-17T00:00:00+00:00"
    assert entry["ra_deg"] == pytest.approx(217.41)
    assert entry["dec_deg"] == pytest.approx(-15.0)
    assert out  # path constructed for symmetry with the write test below


def test_export_maps_native_statuses_onto_the_shared_vocabulary(tmp_path: Path) -> None:
    """null_result is real evidence; thin coverage is explicitly not.

    A field that was searched and yielded nothing must count as prior search. A
    field whose coverage was too thin to search must NOT -- no search happened,
    so counting it would let a sibling skip genuinely unsearched sky.
    """
    queue = _write_queue(
        tmp_path / "queue.csv",
        [
            _queue_row(rank=1, status="null_result"),
            _queue_row(rank=2, status="insufficient_coverage"),
            _queue_row(rank=3, status="insufficient_retained_coverage"),
        ],
    )

    entries = hcp.build_own_history_export(target_queue_path=queue)["sources"][0][
        "entries"
    ]

    by_native = {entry["native_status"]: entry["status"] for entry in entries}
    assert by_native == {
        "null_result": "no_signal",
        "insufficient_coverage": "no_data",
        "insufficient_retained_coverage": "no_data",
    }
    # The native status is preserved verbatim, never discarded.
    assert all(entry["native_status"] for entry in entries)


def test_export_excludes_unsearched_rows(tmp_path: Path) -> None:
    """Planning intent is not history and must never be published as searched."""
    queue = _write_queue(
        tmp_path / "queue.csv",
        [
            _queue_row(rank=1, status="null_result"),
            _queue_row(rank=2, status="not_searched"),
        ],
    )

    entries = hcp.build_own_history_export(target_queue_path=queue)["sources"][0][
        "entries"
    ]

    assert len(entries) == 1
    assert entries[0]["native_status"] == "null_result"


def test_written_export_round_trips_through_the_consumer(tmp_path: Path) -> None:
    """What this repo publishes, a contract-compliant consumer can load."""
    repo = tmp_path / "repo"
    (repo / "data_selection").mkdir(parents=True)
    queue = _write_queue(repo / "data_selection" / "target_priority_queue.csv", [_queue_row()])
    out = repo / "data_selection" / "hunter_prior_search_history_v1.json"

    # Point the module's containment check at the fixture repo.
    original_root = hcp.REPOSITORY_ROOT
    hcp.REPOSITORY_ROOT = repo
    try:
        summary = hcp.write_own_history_export(out, target_queue_path=queue)
        assert summary["ok"] is True
        assert summary["entry_count"] == 1
        loaded = hcp.load_cross_project_history(out, source_root=repo)
    finally:
        hcp.REPOSITORY_ROOT = original_root

    # The consumer re-hashed the real source artifact and it matched.
    assert loaded["validity_state"] == "valid"
    assert loaded["source_hashes_verified"] == loaded["source_count"] == 1
    # Sky fields carry no minor-planet identity, so nothing normalizes -- and
    # that is honest disjointness, not a load failure.
    assert loaded["domain_disjoint"] is True
    assert loaded["raw_entry_count"] == 1


# ---------------------------------------------------------------------------
# Fail-closed cases. Each must raise rather than publish something misleading.
# ---------------------------------------------------------------------------


def test_absent_queue_raises(tmp_path: Path) -> None:
    """A missing source of truth cannot be silently published as empty history."""
    with pytest.raises(ValueError, match="target priority queue not found"):
        hcp.build_own_history_export(target_queue_path=tmp_path / "nope.csv")


def test_queue_with_no_searched_rows_raises(tmp_path: Path) -> None:
    """An empty export is not decision-grade for any consumer."""
    queue = _write_queue(tmp_path / "queue.csv", [_queue_row(status="not_searched")])

    with pytest.raises(ValueError, match="no real history"):
        hcp.build_own_history_export(target_queue_path=queue)


def test_unmapped_status_raises_rather_than_guessing(tmp_path: Path) -> None:
    """An unlabelled status must not be published; absence of a label is not evidence."""
    queue = _write_queue(tmp_path / "queue.csv", [_queue_row(status="brand_new_status")])

    with pytest.raises(ValueError, match="no mapping onto the shared"):
        hcp.build_own_history_export(target_queue_path=queue)


def test_row_without_a_date_raises_rather_than_inventing_one(tmp_path: Path) -> None:
    """An invented timestamp would make stale history look freshly verified."""
    queue = _write_queue(
        tmp_path / "queue.csv",
        [_queue_row(notes="ra_deg=10.0 dec_deg=5.0", evidence_path="")],
    )

    with pytest.raises(ValueError, match="names no date"):
        hcp.build_own_history_export(target_queue_path=queue)


def test_row_without_a_position_raises(tmp_path: Path) -> None:
    """A target with no position cannot be matched by anyone and must not ship."""
    queue = _write_queue(tmp_path / "queue.csv", [_queue_row(notes="searched 2026-07-17")])

    with pytest.raises(ValueError, match="no ra_deg/dec_deg"):
        hcp.build_own_history_export(target_queue_path=queue)


def test_publish_refuses_to_write_outside_this_repository(tmp_path: Path) -> None:
    """WS-01: a repository never writes into a sibling, however it is asked.

    REPOSITORY_ROOT is pinned to a fixture root so the assertion tests the
    containment rule itself. Relying on pytest's tmp_path being outside the real
    checkout would be unsound -- under this project's sandbox it is not.
    """
    repo = tmp_path / "2026 Near Earth Objects"
    (repo / "data_selection").mkdir(parents=True)
    queue = _write_queue(repo / "data_selection" / "target_priority_queue.csv", [_queue_row()])
    sibling = tmp_path / "2026 Exoplanet Research" / "data_selection" / "export.json"

    original_root = hcp.REPOSITORY_ROOT
    hcp.REPOSITORY_ROOT = repo
    try:
        with pytest.raises(ValueError, match="refusing to publish outside"):
            hcp.write_own_history_export(sibling, target_queue_path=queue)
        # A permitted path inside the repo still works, so the rule blocks the
        # sibling specifically rather than blocking everything.
        inside = repo / "data_selection" / "hunter_prior_search_history_v1.json"
        assert hcp.write_own_history_export(inside, target_queue_path=queue)["ok"]
    finally:
        hcp.REPOSITORY_ROOT = original_root

    assert not sibling.exists()


# ---------------------------------------------------------------------------
# Consumer-side validity, including the domain-disjointness correction.
# ---------------------------------------------------------------------------


def _manifest(**overrides: object) -> dict[str, object]:
    """A minimal structurally valid sibling manifest."""
    manifest: dict[str, object] = {
        "schema_version": 1,
        "manifest_id": "hunter-prior-search-history-v1",
        "sources": [
            {
                "source_project": "2026 Exoplanet Research",
                "source_path": "results/history.ndjson",
                "source_sha256": "0" * 64,
                "search_id": "S-1",
                "entries": [
                    {
                        "canonical_id": "TIC 123456",
                        "searched_at": "2026-01-01T00:00:00+00:00",
                        "status": "no_signal",
                    }
                ],
            }
        ],
    }
    manifest.update(overrides)
    return manifest


def test_domain_disjoint_sibling_export_is_valid_not_invalid() -> None:
    """A sibling naming only stars is verified evidence of non-overlap.

    Regression guard for a defect that would only have surfaced in production:
    raising here made every sibling export permanently invalid, so a New-search
    gate that fails closed on validity would have deadlocked New searches
    forever rather than transiently.
    """
    loaded = hcp.load_cross_project_history(_manifest(), source_root=None)

    assert loaded["domain_disjoint"] is True
    assert loaded["interoperable_entry_count"] == 0
    assert loaded["raw_entry_count"] == 1
    # Unverified because no source_root was supplied, but never 'invalid'.
    assert loaded["validity_state"] == "stale-but-usable"


def test_matching_identities_are_still_normalized() -> None:
    """The disjointness allowance must not stop real matches from being found."""
    manifest = _manifest()
    manifest["sources"][0]["entries"] = [  # type: ignore[index]
        {
            "canonical_id": "1998 QE2",
            "aliases": ["1998qe2"],
            "searched_at": "2026-01-01T00:00:00+00:00",
            "status": "no_signal",
        }
    ]

    loaded = hcp.load_cross_project_history(manifest, source_root=None)

    assert loaded["domain_disjoint"] is False
    assert loaded["entries"][0]["identities"] == ["1998 QE2"]


def test_source_with_zero_entries_still_raises() -> None:
    """"No entries at all" is structurally wrong and stays fatal."""
    manifest = _manifest()
    manifest["sources"][0]["entries"] = []  # type: ignore[index]

    with pytest.raises(ValueError, match="has no entries"):
        hcp.load_cross_project_history(manifest, source_root=None)


def test_wrong_schema_version_raises() -> None:
    """Schema drift must fail closed, not be best-effort parsed."""
    with pytest.raises(ValueError, match="schema_version"):
        hcp.load_cross_project_history(_manifest(schema_version=2), source_root=None)


def test_malformed_export_file_raises(tmp_path: Path) -> None:
    """A corrupt export is not partial history; it is no history."""
    path = tmp_path / "export.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        hcp.load_cross_project_history(path, source_root=None)


def test_source_hash_mismatch_raises(tmp_path: Path) -> None:
    """A source that changed since publication must not pass as verified."""
    root = tmp_path / "sibling"
    (root / "results").mkdir(parents=True)
    (root / "results" / "history.ndjson").write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        hcp.load_cross_project_history(_manifest(), source_root=root)
