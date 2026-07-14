"""Safety and orchestration tests for the one-command download launcher."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

import run_sharded_download as runner  # noqa: E402


def _native_target(repo_root: Path, name: str = "native_fetch.py") -> Path:
    """Create a minimal target advertising the three required native flags."""
    skills = repo_root / "Skills"
    skills.mkdir(parents=True)
    target = skills / name
    target.write_text(
        '"""fixture"""\nFLAGS = ("--shard-index", "--shard-count", "--workers")\n',
        encoding="utf-8",
    )
    return target


def _config(script: Path, **overrides) -> runner.LaunchConfig:
    """Build a compact validated config for command and budget tests."""
    values = {
        "script": script,
        "child_args": ("--resume",),
        "shard_count": 6,
        "workers": 6,
        "estimated_download_gb": 2.0,
        "max_project_data_gb": 100.0,
        "min_free_gb": 10.0,
        "manifest_path": Path("Logs/reports/test.jsonl"),
        "run_root": Path("Logs/pipeline_runs/test"),
        "resume": False,
    }
    values.update(overrides)
    return runner.LaunchConfig(**values)


def test_validate_target_requires_repo_native_flags(tmp_path):
    """A valid target stays under Skills and declares all shard/worker flags."""
    target = _native_target(tmp_path)
    assert runner.validate_target_script(target.relative_to(tmp_path), tmp_path) == Path(
        "Skills/native_fetch.py"
    )

    target.write_text('FLAGS = ("--shard-index", "--shard-count")\n', encoding="utf-8")
    with pytest.raises(ValueError, match="--workers"):
        runner.validate_target_script(target.relative_to(tmp_path), tmp_path)


def test_validate_target_rejects_paths_outside_skills(tmp_path):
    """The generic process launcher cannot escape the active repo's Skills tree."""
    outside = tmp_path / "outside.py"
    outside.write_text('FLAGS = ("--shard-index", "--shard-count", "--workers")\n')
    with pytest.raises(ValueError, match="Skills"):
        runner.validate_target_script(outside, tmp_path)


@pytest.mark.parametrize(
    "args, message",
    [
        (("--workers", "2"), "controlled"),
        (("--shard-count=4",), "controlled"),
        (("--api-token", "plaintext"), "Secret-bearing"),
    ],
)
def test_child_args_fail_closed_on_controlled_or_secret_options(args, message):
    """Shard layout and credentials cannot be overridden through passthrough args."""
    with pytest.raises(ValueError, match=message):
        runner._validate_child_args(args)


def test_build_command_uses_six_by_six_defaults_without_shell():
    """Every child receives one index, the shared count, and six workers."""
    config = _config(Path("Skills/native_fetch.py"))
    command = runner.build_shard_command(config, 3)
    assert command[:9] == [
        "caffeinate",
        "-i",
        "uv",
        "run",
        "--no-sync",
        "--python",
        "3.14",
        "python",
        "Skills/native_fetch.py",
    ]
    assert command[-6:] == [
        "--shard-index",
        "3",
        "--shard-count",
        "6",
        "--workers",
        "6",
    ]


def test_run_id_is_stable_and_parameter_sensitive():
    """Identical commands resume the same batch while changed scope gets a new key."""
    first = runner.compute_run_id(Path("Skills/a.py"), ("--resume",), 6, 6)
    assert first == runner.compute_run_id(Path("Skills/a.py"), ("--resume",), 6, 6)
    assert first != runner.compute_run_id(Path("Skills/a.py"), ("--resume",), 5, 6)


def test_storage_budget_accepts_safe_batch_and_rejects_ceiling(monkeypatch, tmp_path):
    """The launcher checks both project-data and free-space projections."""
    config = _config(Path("Skills/a.py"), estimated_download_gb=20.0)
    monkeypatch.setattr(runner, "project_data_size_gb", lambda _root: 10.0)
    usage = type("Usage", (), {"free": 200_000_000_000})()
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _root: usage)
    result = runner.check_storage_budget(config, tmp_path)
    assert result["projected_project_data_gb"] == 30.0

    too_large = _config(Path("Skills/a.py"), estimated_download_gb=95.0)
    with pytest.raises(RuntimeError, match="ceiling"):
        runner.check_storage_budget(too_large, tmp_path)


def test_manifest_status_and_merge_use_latest_record_per_shard(tmp_path):
    """Rerunning a shard replaces its logical record and merge fails closed."""
    manifest = tmp_path / "manifest.jsonl"
    runner.append_manifest_record(
        manifest, {"record_type": "run_started", "run_id": "run-a"}
    )
    for index in range(2):
        runner.append_manifest_record(
            manifest,
            {
                "record_type": "shard_completed",
                "run_id": "run-a",
                "shard_index": index,
                "status": "succeeded",
            },
        )
    runner.append_manifest_record(
        manifest,
        {
            "record_type": "shard_completed",
            "run_id": "run-a",
            "shard_index": 1,
            "status": "failed",
        },
    )
    status = runner.report_status(manifest, "run-a", shard_count=2)
    assert status["shards_failed"] == [1]
    with pytest.raises(RuntimeError, match="failed shards"):
        runner.merge_run(manifest, "run-a", 2, tmp_path / "summary.json")


def test_merge_writes_summary_only_after_all_shards_succeed(tmp_path):
    """A complete successful manifest produces one deterministic summary."""
    manifest = tmp_path / "manifest.jsonl"
    for index in range(2):
        runner.append_manifest_record(
            manifest,
            {
                "record_type": "shard_completed",
                "run_id": "run-b",
                "shard_index": index,
                "status": "succeeded",
            },
        )
    output = tmp_path / "summary.json"
    merged = runner.merge_run(manifest, "run-b", 2, output)
    assert merged["status"] == "succeeded"
    assert json.loads(output.read_text())["shard_count"] == 2


def test_status_and_merge_infer_nondefault_shard_count_from_run(tmp_path):
    """Inspection reuses recorded topology instead of assuming six shards."""
    manifest = tmp_path / "manifest.jsonl"
    runner.append_manifest_record(
        manifest,
        {
            "record_type": "run_started",
            "run_id": "run-four",
            "shard_count": 4,
        },
    )
    for index in range(4):
        runner.append_manifest_record(
            manifest,
            {
                "record_type": "shard_completed",
                "run_id": "run-four",
                "shard_count": 4,
                "shard_index": index,
                "status": "succeeded",
            },
        )

    status = runner.report_status(manifest, "run-four", shard_count=None)
    assert status["shard_count"] == 4
    assert status["shards_missing"] == []

    output = tmp_path / "summary.json"
    merged = runner.merge_run(manifest, "run-four", shard_count=None, out_path=output)
    assert merged["shard_count"] == 4


def test_manifest_relay_scopes_commit_and_retries_push(monkeypatch, tmp_path):
    """Only the manifest is committed, with a bounded concurrent-push retry."""
    manifest = tmp_path / "Logs/reports/manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}\n", encoding="utf-8")
    calls: list[list[str]] = []
    outcomes = iter(
        [
            (0, "", ""),  # add
            (1, "", ""),  # path has a staged change
            (0, "", ""),  # commit --only
            (1, "", "non-fast-forward"),
            (0, "", ""),  # pull --rebase
            (0, "", ""),  # retry push
        ]
    )

    def fake_git(args, repo_root):
        assert repo_root == tmp_path
        calls.append(args)
        return next(outcomes)

    monkeypatch.setattr(runner, "_run_git", fake_git)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

    assert runner.commit_and_push_manifest(manifest, tmp_path)
    relative = "Logs/reports/manifest.jsonl"
    assert ["diff", "--cached", "--quiet", "--", relative] in calls
    commit = next(call for call in calls if call[0] == "commit")
    assert "--only" in commit
    assert commit[-2:] == ["--", relative]
    assert calls.count(["push"]) == 2
    assert ["pull", "--rebase"] in calls


def test_parser_exposes_manifest_sync_without_a_download_target():
    """A prior local manifest can be relayed again without restarting data work."""
    args = runner._build_parser().parse_args(["--sync"])
    assert args.sync
    assert args.script is None
