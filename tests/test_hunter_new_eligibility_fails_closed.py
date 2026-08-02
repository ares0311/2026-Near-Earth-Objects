"""New eligibility must fail closed on non-decision-grade history (IDENT-03).

Mirrors TechnoHunter's ``tests/test_hunter_new_eligibility_fails_closed.py``.

The defect these guard against is specific: a New search reports its targets as
"not previously searched" while never establishing that across all three
Astrometrics Hunters. Consulting only this repository's own export is a narrower
form of the same thing -- it proves "not searched by NEOHunter" and then presents
it as novelty.

Every test drives the real production entry points. A test that constructed a
validity state by hand and asserted on it would pass against a gate that is
never called.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Skills"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import hunter_cross_project as cxp  # noqa: E402


def _export(tmp_path: Path, *, sha256: str | None = None, schema: int = 1) -> Path:
    """Write a published export with one source whose artifact really exists."""
    repo = tmp_path / "2026 Some Hunter"
    (repo / "data_selection").mkdir(parents=True)
    artifact = repo / "data_selection" / "target_priority_queue.csv"
    artifact.write_text("target_id,status\nX,null_result\n", encoding="utf-8")

    import hashlib

    digest = sha256 or hashlib.sha256(artifact.read_bytes()).hexdigest()
    path = repo / "data_selection" / "hunter_prior_search_history_v1.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": schema,
                "manifest_id": cxp.CROSS_PROJECT_HISTORY_MANIFEST_ID,
                "sources": [
                    {
                        "source_project": "SomeHunter",
                        "source_path": "data_selection/target_priority_queue.csv",
                        "source_sha256": digest,
                        "search_id": "S-1",
                        "entries": [
                            {
                                "canonical_id": "1998 QE2",
                                "searched_at": "2026-01-01T00:00:00+00:00",
                                "status": "no_signal",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


# --- per-export validity ----------------------------------------------------


def test_absent_export_is_unknown(tmp_path: Path) -> None:
    """A sibling that never published is unknown, never 'nothing was searched'."""
    state, detail, payload = cxp.cross_project_history_validity(tmp_path / "missing.json")
    assert state == "unknown"
    assert "absent" in detail
    assert payload is None
    assert state not in cxp.CROSS_PROJECT_DECISION_STATES


def test_malformed_export_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    state, _detail, _ = cxp.cross_project_history_validity(path)
    assert state == "invalid"
    assert state not in cxp.CROSS_PROJECT_DECISION_STATES


def test_wrong_schema_version_is_invalid(tmp_path: Path) -> None:
    """An unversioned or mismatched export is not decision-grade."""
    state, detail, _ = cxp.cross_project_history_validity(_export(tmp_path, schema=99))
    assert state == "invalid"
    assert "schema_version" in detail


def test_verified_source_is_valid(tmp_path: Path) -> None:
    state, _detail, payload = cxp.cross_project_history_validity(_export(tmp_path))
    assert state == "valid"
    assert payload is not None
    assert payload["sources"][0]["validity_state"] == "valid"


def test_hash_mismatch_degrades_whole_export(tmp_path: Path) -> None:
    """One bad source degrades the export; the others cannot average it away."""
    state, _detail, _ = cxp.cross_project_history_validity(_export(tmp_path, sha256="0" * 64))
    assert state == "invalid"
    assert state not in cxp.CROSS_PROJECT_DECISION_STATES


def test_absent_artifact_is_stale_but_usable(tmp_path: Path) -> None:
    """An operator-copied export keeps its entries but is never 'freshly verified'."""
    path = _export(tmp_path)
    (path.parent / "target_priority_queue.csv").unlink()
    state, _detail, _ = cxp.cross_project_history_validity(path)
    assert state == "stale-but-usable"
    assert state in cxp.CROSS_PROJECT_DECISION_STATES


# --- sibling discovery ------------------------------------------------------


def test_sibling_paths_are_repository_relative() -> None:
    """WS-03: discovery is computed from this repo, with no absolute path baked in."""
    for project in cxp.CROSS_PROJECT_ROOT_NAMES:
        path = cxp.sibling_history_export_path(project)
        assert path.name == "hunter_prior_search_history_v1.json"
        assert path.parent.name == "data_selection"
        # A sibling lives beside this repository, never inside it.
        assert cxp.REPOSITORY_ROOT not in path.parents
        assert path.parents[1].parent == cxp.REPOSITORY_ROOT.parent


def test_this_repository_is_never_its_own_sibling() -> None:
    """Listing the active repo as a sibling is the bug that blocks local writes."""
    assert cxp.OWN_PROJECT_KEY not in cxp.CROSS_PROJECT_ROOT_NAMES
    assert cxp.REPOSITORY_ROOT.name not in cxp.CROSS_PROJECT_ROOT_NAMES.values()


def test_unknown_sibling_name_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown sibling project"):
        cxp.sibling_history_export_path("not_a_hunter")


# --- the federated gate -----------------------------------------------------


def test_federation_covers_all_three_projects(tmp_path: Path) -> None:
    _state, _detail, per_project = cxp.cross_project_history_federation_validity(
        _export(tmp_path)
    )
    assert set(per_project) == {cxp.OWN_PROJECT_KEY, *cxp.CROSS_PROJECT_ROOT_NAMES}


def test_one_degraded_project_closes_the_gate(tmp_path: Path, monkeypatch) -> None:
    """Any single non-decision-grade project refuses the New search."""
    good = _export(tmp_path)
    monkeypatch.setattr(
        cxp, "sibling_history_export_path", lambda project: tmp_path / f"{project}.json"
    )
    with pytest.raises(cxp.CrossProjectHistoryError) as excinfo:
        cxp.require_decision_grade_history(good)

    message = str(excinfo.value)
    assert "fails closed" in message
    assert "unknown" in message
    # Actionable: names the blocking projects and what to do about it.
    for project in cxp.CROSS_PROJECT_ROOT_NAMES:
        assert project in message
    assert "hunter_prior_search_history_v1.json" in message


def test_all_three_decision_grade_permits_selection(tmp_path: Path, monkeypatch) -> None:
    """The positive case: a complete federation returns a state and does not raise."""
    good = _export(tmp_path)
    monkeypatch.setattr(cxp, "sibling_history_export_path", lambda project: good)
    state, detail = cxp.require_decision_grade_history(good)
    assert state in cxp.CROSS_PROJECT_DECISION_STATES
    for project in (cxp.OWN_PROJECT_KEY, *cxp.CROSS_PROJECT_ROOT_NAMES):
        assert project in detail


def test_discover_new_targets_refuses_before_writing_state(
    tmp_path: Path, monkeypatch
) -> None:
    """The gate runs before discovery, so a refusal persists nothing.

    The production entry point is called with an output directory that does not
    yet exist; if any state were written before the gate, the directory would be
    created and the assertion below would fail.
    """
    import hunter_cli

    monkeypatch.setattr(
        hunter_cli, "_combined_known_coverage", lambda: pytest.fail("discovery ran")
    )
    monkeypatch.setattr(
        cxp, "sibling_history_export_path", lambda project: tmp_path / "absent.json"
    )

    out_dir = tmp_path / "never-created"
    with pytest.raises(cxp.CrossProjectHistoryError):
        hunter_cli.discover_new_targets(
            jd=2458339.5,
            neo_class="aten",
            requested_n=5,
            max_pool=None,
            out_dir=out_dir,
            target_queue_path=tmp_path / "queue.csv",
            ranking_policy_path=tmp_path / "policy.json",
            db_path=tmp_path / "state.sqlite",
        )

    assert not out_dir.exists(), "state was written before the novelty gate ran"
