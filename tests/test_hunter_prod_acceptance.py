"""Independent negative controls for the Hunter PROD closure invariants."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest

import hunter_commands

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Skills"))

import select_survey_fields  # noqa: E402


def test_entrypoint_loader_resolves_repository_cli() -> None:
    original_path = list(sys.path)
    skills_path = str(ROOT / "Skills")
    sys.path[:] = [entry for entry in sys.path if entry != skills_path]
    try:
        assert hunter_commands._hunter_main().__module__ == "hunter_cli"
        assert skills_path in sys.path
    finally:
        sys.path[:] = original_path


@pytest.mark.parametrize(
    ("wrapper", "subcommand"),
    [
        (hunter_commands.create_new_search, "create-new-search"),
        (hunter_commands.run_new_search, "run-new-search"),
        (hunter_commands.show_follow_ups, "show-follow-ups"),
    ],
)
def test_installed_entrypoints_delegate_to_one_canonical_cli(
    monkeypatch: pytest.MonkeyPatch, wrapper, subcommand: str
) -> None:
    seen: list[list[str] | None] = []
    monkeypatch.setattr(hunter_commands, "_hunter_main", lambda: seen.append)
    monkeypatch.setattr(sys, "argv", ["entrypoint", "--sentinel"])

    assert wrapper() is None
    assert seen == [[subcommand, "--sentinel"]]


def test_packaging_and_readme_demote_shadow_product_paths() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"] == {
        "NEO-Hunter": "hunter_commands:neo_hunter",
        "NEOHunter": "hunter_commands:neo_hunter",
        "Create-New-Search": "hunter_commands:create_new_search",
        "Run-New-Search": "hunter_commands:run_new_search",
        "Show-Follow-Ups": "hunter_commands:show_follow_ups",
    }
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Canonical Hunter product workflow" in readme
    assert "`NEO-Hunter` is the persistent product terminal" in readme
    assert "lower-level scientific diagnostics" in readme
    assert "are not alternate product entry points" in readme
    for slash_command in (
        "/New-Search",
        "/Follow-Up-Search",
        "/Run-Search",
        "/Show-Follow-Ups",
        "/Exit",
    ):
        assert slash_command in readme


def test_neohunter_entrypoint_loads_the_thin_persistent_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hunter_shell

    original_path = list(sys.path)
    skills_path = str(ROOT / "Skills")
    sys.path[:] = [entry for entry in sys.path if entry != skills_path]
    seen: list[list[str]] = []
    monkeypatch.setattr(hunter_shell, "main", lambda argv: seen.append(argv) or 0)
    monkeypatch.setattr(sys, "argv", ["NEOHunter", "--command", "/Help"])

    try:
        assert hunter_commands.neo_hunter() == 0
        assert seen == [["--command", "/Help"]]
        assert skills_path in sys.path
    finally:
        sys.path[:] = original_path


def test_coverage_validity_rejects_refresh_required_input(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "ztf-field-night-coverage-inventory-v1",
                "batch_id": "bad",
                "batch_manifest_sha256": "a" * 64,
                "metadata_only": True,
                "min_distinct_nights": 3,
                "validity_state": "refresh-required",
                "field_results": [
                    {
                        "field_id": "field-a",
                        "ra_deg": 10.0,
                        "dec_deg": 5.0,
                        "n_distinct_nights": 3,
                        "distinct_nights_yyyymmdd": [
                            "20240101",
                            "20240102",
                            "20240103",
                        ],
                        "passes_min_distinct_nights": True,
                        "raw_response_sha256": "b" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not usable: validity_state=refresh-required"):
        select_survey_fields.load_coverage_inventory(path)


def test_runbook_contains_fail_closed_acceptance_ledger() -> None:
    runbook = (ROOT / "docs" / "OPERATOR_GO_NO_GO_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    for finding_id in (f"HP-{number:02d}" for number in range(1, 14)):
        assert finding_id in runbook
    assert "Do not restore that claim" in runbook
