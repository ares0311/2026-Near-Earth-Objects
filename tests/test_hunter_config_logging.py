from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import hunter_config
import hunter_logging


def test_checkout_defaults_and_all_resolved_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEOHUNTER_HOME", raising=False)
    monkeypatch.delenv("NEOHUNTER_RESOURCE_ROOT", raising=False)
    monkeypatch.delenv("NEOHUNTER_MODEL_ROOT", raising=False)

    paths = hunter_config.get_hunter_paths()

    assert paths.resource_root == paths.state_root
    assert paths.target_queue.name == "target_priority_queue.csv"
    assert paths.ranking_policy_dir.name == "ranking_policies"
    assert paths.static_coverage_dir.name == "coverage_inventories"
    assert paths.model_dir.name == "models"
    assert paths.hunter_db.name == "hunter_state.sqlite"
    assert paths.candidate_ledger_db.name == "candidate_ledger.sqlite"
    assert paths.search_manifest_dir.name == "search_manifests"
    assert paths.batch_manifest_dir.name == "batch_manifests"
    assert paths.runtime_coverage_dir.name == "coverage_inventories"
    assert paths.work_dir.name == "hunter_cli"
    assert paths.checkpoint_dir.name == "search_runs"
    assert paths.event_log.name == "hunter_events.jsonl"
    assert paths.shell_history.name == "neo_hunter_history"


def test_explicit_resource_state_and_model_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resources = tmp_path / "resources"
    state = tmp_path / "state"
    models = tmp_path / "models"
    monkeypatch.setenv("NEOHUNTER_RESOURCE_ROOT", str(resources))
    monkeypatch.setenv("NEOHUNTER_HOME", str(state))
    monkeypatch.setenv("NEOHUNTER_MODEL_ROOT", str(models))

    paths = hunter_config.get_hunter_paths()

    assert paths.resource_root == resources
    assert paths.state_root == state
    assert paths.model_dir == models


def test_installed_defaults_use_prefix_and_platform_state_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_module = tmp_path / "site-packages" / "hunter_config.py"
    fake_module.parent.mkdir()
    fake_module.write_text("", encoding="utf-8")
    monkeypatch.setattr(hunter_config, "__file__", str(fake_module))
    monkeypatch.setattr(hunter_config.sys, "prefix", str(tmp_path / "prefix"))
    monkeypatch.delenv("NEOHUNTER_RESOURCE_ROOT", raising=False)
    monkeypatch.delenv("NEOHUNTER_HOME", raising=False)
    monkeypatch.setattr(hunter_config.sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))

    paths = hunter_config.get_hunter_paths()

    assert paths.resource_root == (tmp_path / "prefix")
    assert paths.state_root == (tmp_path / "xdg" / "neo-hunter")

    assert (
        hunter_config._default_user_state_root(platform="darwin")
        == Path.home() / "Library" / "Application Support" / "NEO-Hunter"
    )

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert hunter_config._default_user_state_root(
        platform="win32", operating_system="nt"
    ) == tmp_path / "local" / "NEO-Hunter"


def test_structured_event_is_valid_append_only_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "events.jsonl"

    hunter_logging.emit_event(
        path, event="create_search", status="started", requested_n=100
    )
    hunter_logging.emit_event(
        path, event="create_search", status="completed", search_id="search-1"
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["status"] for row in rows] == ["started", "completed"]
    assert rows[0]["schema_version"] == 1
    assert rows[0]["requested_n"] == 100
    assert rows[1]["search_id"] == "search-1"


@pytest.mark.parametrize(("event", "status"), [("", "ok"), ("event", "")])
def test_structured_event_rejects_empty_required_fields(
    tmp_path: Path, event: str, status: str
) -> None:
    with pytest.raises(ValueError, match="must be non-empty"):
        hunter_logging.emit_event(tmp_path / "events.jsonl", event=event, status=status)


def test_structured_event_short_write_fails_visibly_and_closes_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path / "events.jsonl", os.O_CREAT | os.O_WRONLY, 0o600)
    closed: list[int] = []
    monkeypatch.setattr(hunter_logging.os, "open", lambda *args: descriptor)
    monkeypatch.setattr(hunter_logging.os, "write", lambda *args: 0)
    monkeypatch.setattr(hunter_logging.os, "close", closed.append)

    with pytest.raises(OSError, match="short structured-log write"):
        hunter_logging.emit_event(
            tmp_path / "events.jsonl", event="test", status="failed"
        )
    assert closed == [descriptor]
    os.close(descriptor)
