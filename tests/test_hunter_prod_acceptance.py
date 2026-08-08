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


def test_entrypoint_loader_resolves_packaged_cli_without_path_mutation() -> None:
    original_path = list(sys.path)
    skills_path = str(ROOT / "Skills")
    sys.path[:] = [entry for entry in sys.path if entry != skills_path]
    try:
        assert hunter_commands._hunter_main().__module__ == "Skills.hunter_cli"
        assert skills_path not in sys.path
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
    packaged_modules = set(pyproject["tool"]["setuptools"]["py-modules"])
    assert {"hunter_commands", "hunter_config", "hunter_state", "hunter_logging"} <= (
        packaged_modules
    )
    # The intent is that no shadow product path is packaged -- not that the list
    # can never grow. Skills.hunter_ux is the CLI/UX interaction layer required
    # by docs/CLI_UX_SPEC.md and must ship; setuptools does not recurse into
    # subpackages of an explicit package list, so it is enumerated explicitly.
    packaged_packages = set(pyproject["tool"]["setuptools"]["packages"])
    assert packaged_packages == {"Skills", "Skills.hunter_ux"}
    # Development-only trees must never be packaged as product.
    assert not any(
        name.split(".")[0] in {"tests", "benchmarks", "docs", "Logs"}
        for name in packaged_packages
    )
    packaged_data = pyproject["tool"]["setuptools"]["data-files"]
    assert "models" in packaged_data
    assert "data_selection/ranking_policies" in packaged_data
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
    from Skills import hunter_shell

    original_path = list(sys.path)
    skills_path = str(ROOT / "Skills")
    sys.path[:] = [entry for entry in sys.path if entry != skills_path]
    seen: list[list[str]] = []
    monkeypatch.setattr(hunter_shell, "main", lambda argv: seen.append(argv) or 0)
    monkeypatch.setattr(sys, "argv", ["NEOHunter", "--command", "/Help"])

    try:
        assert hunter_commands.neo_hunter() == 0
        assert seen == [["--command", "/Help"]]
        assert skills_path not in sys.path
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
    for finding_id in (f"HP-{number:02d}" for number in range(1, 21)):
        assert finding_id in runbook
    assert "Do not restore that claim" in runbook


def test_all_mode_ranks_one_hundred_from_over_ten_thousand_candidates() -> None:
    rows = select_survey_fields.select_fields(
        jd=2461000.5,
        mode="all",
        top_n=100_000,
        deduplicate=False,
    )

    assert len(rows) >= 10_000
    assert len(rows[:100]) == 100
    assert [row["score"] for row in rows[:100]] == sorted(
        (row["score"] for row in rows[:100]), reverse=True
    )
