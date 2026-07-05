"""Repository-level artifact policy checks.

These tests keep the operator's normal ``git add .`` workflow safe by ensuring
local run outputs stay ignored while production model artifacts remain
intentionally visible to future agents through GitHub.
"""

from __future__ import annotations

import subprocess


def _git(*args: str) -> str:
    """Run a read-only git command and return stdout for policy assertions."""
    result = subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def test_only_log_placeholders_are_tracked():
    """Raw operational logs must not be tracked as durable repository state.

    Deliberate exceptions under Logs/reports/ are compact, inert summary
    artifacts -- never raw observation payloads -- that are either
    auto-committed by a script (the ztf_alert_archive_ingest.py git-relay
    manifest; see CLAUDE.md's "shared manifest must live in a committed
    path" rule) or a small evidence JSON promoted by the operator to
    support a specific dated Gate closure (the Gate Z4/Z5 evaluator
    reports; see docs/evidence/live/2026-07-04-gate-z4-z5-closed.md).
    """
    tracked_logs = sorted(_git("ls-files", "Logs").splitlines())

    assert tracked_logs == [
        "Logs/.gitkeep",
        "Logs/reports/.gitkeep",
        "Logs/reports/ranking_baseline.json",
        "Logs/reports/retrospective_validation.json",
        "Logs/reports/ztf_alert_archive_ingest_manifest.jsonl",
    ]


def test_only_allowlisted_model_artifacts_are_tracked():
    """Production model artifacts must be explicit so ad hoc outputs stay local."""
    tracked_models = sorted(_git("ls-files", "models").splitlines())

    assert tracked_models == [
        "models/stacker_coef.json",
        "models/tier1_xgb.json",
        "models/tier2_cnn.pt",
        "models/tier3_transformer.pt",
    ]


def test_generated_log_outputs_are_ignored_for_git_add_dot():
    """Nested Logs outputs and report CSVs should remain ignored when untracked."""
    ignored = _git(
        "check-ignore",
        "-v",
        "--no-index",
        "Logs/pipeline_runs/example/checkpoint.json",
        "Logs/pipeline_runs/example/run_summary.json",
        "Logs/reports/example.csv",
        "Logs/reports/example.json",
        "Logs/background.sqlite",
    )

    for path in [
        "Logs/pipeline_runs/example/checkpoint.json",
        "Logs/pipeline_runs/example/run_summary.json",
        "Logs/reports/example.csv",
        "Logs/reports/example.json",
        "Logs/background.sqlite",
    ]:
        assert path in ignored


def test_unallowlisted_model_outputs_are_ignored_for_git_add_dot():
    """New model files require an explicit policy decision before committing."""
    ignored = _git(
        "check-ignore",
        "-v",
        "--no-index",
        "models/ad_hoc_experiment.pt",
        "models/calibrator_isotonic.pkl",
        "models/local_notes.json",
    )

    for path in [
        "models/ad_hoc_experiment.pt",
        "models/calibrator_isotonic.pkl",
        "models/local_notes.json",
    ]:
        assert path in ignored
