from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import background
from schemas import (
    BackgroundConfig,
    CandidateExplanation,
    CandidateFeatures,
    HazardAssessment,
    NEOPosterior,
    ScoredNEO,
    ScoringMetadata,
)
from score import score

from .conftest import build_orbital_elements, build_tracklet


def write_fixture(path: Path, object_ids: tuple[str, ...] = ("T001",)) -> None:
    rows = []
    for object_id in object_ids:
        tracklet = build_tracklet(n_obs=3, arc_days=2.0)
        rows.append({
            "object_id": object_id,
            "arc_days": tracklet.arc_days,
            "motion_rate_arcsec_per_hour": tracklet.motion_rate_arcsec_per_hour,
            "motion_pa_degrees": tracklet.motion_pa_degrees,
            "observations": [obs.model_dump() for obs in tracklet.observations],
        })
    path.write_text(json.dumps(rows))


def write_manifest_fixture(path: Path, object_ids: tuple[str, ...] = ("T001",)) -> None:
    rows = []
    for object_id in object_ids:
        tracklet = build_tracklet(n_obs=3, arc_days=2.0)
        rows.append({
            "object_id": object_id,
            "arc_days": tracklet.arc_days,
            "motion_rate_arcsec_per_hour": tracklet.motion_rate_arcsec_per_hour,
            "motion_pa_degrees": tracklet.motion_pa_degrees,
            "observations": [obs.model_dump() for obs in tracklet.observations],
        })
    path.write_text(json.dumps({"schema_version": "background-targets-v1", "targets": rows}))


def write_live_policy(path: Path, approved: bool = True) -> None:
    path.write_text(json.dumps({
        "schema_version": "live-review-policy-v1",
        "policy_name": "test-live-policy",
        "reviewer": "Dr. Reviewer",
        "approved_for_live_network": approved,
        "allowed_surveys": ["ZTF", "ATLAS", "PanSTARRS"],
        "max_queries_per_run": 3,
        "min_seconds_between_queries": 0,
        "dry_run_scope": {
            "ra_deg": 180.0,
            "dec_deg": 0.0,
            "radius_deg": 0.1,
            "start_jd": 2460000.5,
            "end_jd": 2460001.5,
        },
        "no_external_submission_confirmed": True,
        "no_impact_probability_claims": True,
    }))


def write_live_config(path: Path, policy_path: Path, live_network_enabled: bool = True) -> None:
    path.write_text(json.dumps({
        "input_path": "background/targets.json",
        "db_path": "Logs/background.sqlite",
        "report_dir": "Logs/reports",
        "follow_up_threshold": 0.45,
        "run_mode": "automated",
        "live_network_enabled": live_network_enabled,
        "require_human_signoff": True,
        "required_approval_count": 1,
        "scheduler_enabled": True,
        "scheduler_interval_minutes": 60,
        "live_review_policy": str(policy_path),
        "required_credential_env": ["ZTF_IRSA_TOKEN", "ATLAS_TOKEN", "MAST_API_TOKEN"],
    }))


def make_scored(
    object_id: str = "T001",
    neo_prob: float = 0.65,
    artifact_prob: float = 0.05,
    known_object_score: float | None = 0.0,
    followup_value: float = 0.8,
    discovery_priority: float = 0.4,
) -> ScoredNEO:
    tracklet = build_tracklet(n_obs=4, arc_days=3.0)
    tracklet = type(tracklet)(
        object_id=object_id,
        observations=tracklet.observations,
        arc_days=tracklet.arc_days,
        motion_rate_arcsec_per_hour=tracklet.motion_rate_arcsec_per_hour,
        motion_pa_degrees=tracklet.motion_pa_degrees,
    )
    features = CandidateFeatures(
        real_bogus_score=0.92,
        motion_consistency_score=0.9,
        arc_coverage_score=0.2,
        nights_observed_score=0.4,
        brightness_score=0.6,
        known_object_score=known_object_score,
    )
    posterior = NEOPosterior(
        neo_candidate=neo_prob,
        known_object=0.05,
        main_belt_asteroid=0.2,
        stellar_artifact=artifact_prob,
        other_solar_system=0.05,
    )
    scored = score(tracklet, features, posterior, build_orbital_elements(), pipeline_run_id="run")
    return scored.model_copy(
        update={
            "metadata": ScoringMetadata(
                scorer_version="test",
                scored_at_jd=2460000.5,
                pipeline_run_id="run",
                discovery_priority=discovery_priority,
                followup_value=followup_value,
                scientific_interest=0.3,
            )
        }
    )


def table_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_background_run_once_writes_one_ledger_and_followup(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "Logs" / "reports"
    write_fixture(fixture)

    def fake_score(tracklet, run_id):
        return make_scored(tracklet.object_id)

    monkeypatch.setattr(background, "score_tracklet", fake_score)
    result = background.background_run_once(fixture, db_path, report_dir)

    assert result.ledger.outcome == "needs_follow_up"
    assert result.needs_follow_up is not None
    assert result.reviewed is None
    assert table_count(db_path, "run_ledger") == 1
    assert table_count(db_path, "needs_follow_up_log") == 1
    assert table_count(db_path, "reviewed_log") == 0
    assert result.needs_follow_up.human_approval_required is True
    assert result.needs_follow_up.report_path is not None

    report = Path(result.needs_follow_up.report_path).read_text().lower()
    assert "confirmed neo" not in report
    assert "impact probability" not in report
    assert "explicit human approval" in report


def test_load_config_defaults_to_manual_and_one_approval(tmp_path):
    cfg = background.load_config(tmp_path / "missing.json")

    assert isinstance(cfg, BackgroundConfig)
    assert cfg.run_mode == "manual"
    assert cfg.live_network_enabled is False
    assert cfg.required_approval_count == 1
    assert cfg.scheduler_enabled is False


def test_project_config_is_automated_offline():
    cfg = background.load_config(Path("background/config.json"))

    assert cfg.run_mode == "automated"
    assert cfg.scheduler_enabled is True
    assert cfg.live_network_enabled is False
    assert cfg.required_credential_env == ("ZTF_IRSA_TOKEN", "ATLAS_TOKEN", "MAST_API_TOKEN")
    assert cfg.live_review_policy == "background/live_review_policy.example.json"


def test_automation_readiness_is_scheduler_ready_but_live_blocked(monkeypatch):
    monkeypatch.delenv("ZTF_IRSA_TOKEN", raising=False)
    monkeypatch.delenv("ATLAS_TOKEN", raising=False)
    monkeypatch.delenv("MAST_API_TOKEN", raising=False)

    readiness = background.automation_readiness_summary(Path("background/config.json"))

    assert readiness["scheduler_ready"] is True
    assert readiness["scheduler_blockers"] == []
    assert readiness["live_mode_ready"] is False
    assert "LIVE_NETWORK_DISABLED" in readiness["live_mode_blockers"]
    assert "MISSING_REQUIRED_CREDENTIALS" in readiness["live_mode_blockers"]
    assert "LIVE_REVIEW_POLICY_NOT_APPROVED" in readiness["live_mode_blockers"]
    assert readiness["missing_credential_env"] == (
        "ZTF_IRSA_TOKEN",
        "ATLAS_TOKEN",
        "MAST_API_TOKEN",
    )
    assert readiness["live_review_policy_summary"]["allowed_surveys"] == (
        "ZTF",
        "ATLAS",
        "PanSTARRS",
    )
    assert "Skills/background.py run-once" in readiness["one_run_command"]


def test_launchd_plist_wraps_one_run_command():
    plist = background.launchd_plist(Path("background/config.json"))

    assert "org.neo-detection.background" in plist
    assert "<string>run-once</string>" in plist
    assert "<key>StartInterval</key>" in plist
    assert "<integer>3600</integer>" in plist
    assert "<key>OMP_NUM_THREADS</key>" in plist


def test_record_automation_readiness_writes_sqlite_log(monkeypatch, tmp_path):
    monkeypatch.delenv("ZTF_IRSA_TOKEN", raising=False)
    monkeypatch.delenv("ATLAS_TOKEN", raising=False)
    monkeypatch.delenv("MAST_API_TOKEN", raising=False)
    db_path = tmp_path / "Logs" / "background.sqlite"

    entry = background.record_automation_readiness(Path("background/config.json"), db_path)
    summary = background.automation_readiness_log_summary(db_path)

    assert table_count(db_path, "automation_readiness_log") == 1
    assert entry["scheduler_ready"] is True
    assert entry["live_mode_ready"] is False
    assert "MISSING_REQUIRED_CREDENTIALS" in entry["live_mode_blockers"]
    assert summary["total_readiness_checks"] == 1
    assert summary["blocker_counts"]["scheduler_not_ready"] == 0
    assert summary["blocker_counts"]["live_mode_not_ready"] == 1
    assert summary["latest"]["readiness_id"] == entry["readiness_id"]


def test_live_dry_run_plan_is_no_network_and_persisted(tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"

    plan = background.live_dry_run_plan(Path("background/config.json"))
    entry = background.record_live_dry_run_plan(Path("background/config.json"), db_path)
    summary = background.live_dry_run_plan_log_summary(db_path)

    assert plan["network_access_performed"] is False
    assert plan["external_submission_enabled"] is False
    assert plan["executable"] is False
    assert plan["planned_surveys"] == ("ZTF", "ATLAS", "PanSTARRS")
    assert plan["query_count"] == 3
    assert all(query["network_action"] == "not_executed" for query in plan["queries"])
    assert "LIVE_REVIEW_POLICY_NOT_APPROVED" in plan["blockers"]
    assert table_count(db_path, "live_dry_run_plan_log") == 1
    assert summary["total_live_dry_run_plans"] == 1
    assert summary["latest"]["plan_id"] == entry["plan_id"]


def test_live_dry_run_execute_blocked_by_default(monkeypatch, tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"

    def fail_if_called(plan):
        raise AssertionError("network execution hook should not run")

    monkeypatch.setattr(background, "_execute_live_dry_run_queries", fail_if_called)
    entry = background.record_live_execution_attempt(Path("background/config.json"), db_path)
    summary = background.live_execution_log_summary(db_path)

    assert entry["outcome"] == "blocked"
    assert entry["executable"] is False
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert "LIVE_NETWORK_DISABLED" in entry["blockers"]
    assert table_count(db_path, "live_execution_log") == 1
    assert summary["by_outcome"] == {"blocked": 1}


def test_live_dry_run_execute_approved_config_uses_mock_hook(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ZTF_IRSA_TOKEN", "ztf-token")
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    monkeypatch.setenv("MAST_API_TOKEN", "mast-token")
    calls = []

    def fake_execute(plan):
        calls.append(plan)
        return ({"survey": "ZTF", "status": "mocked_success"},)

    monkeypatch.setattr(background, "_execute_live_dry_run_queries", fake_execute)
    entry = background.record_live_execution_attempt(config_path, db_path)

    assert entry["outcome"] == "mock_executed"
    assert entry["executable"] is True
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert len(calls) == 1
    assert calls[0]["executable"] is True


def test_automation_readiness_log_summary_empty(tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"

    summary = background.automation_readiness_log_summary(db_path)

    assert summary["total_readiness_checks"] == 0
    assert summary["latest"] is None


def test_gitignore_excludes_generated_background_artifacts():
    text = Path(".gitignore").read_text()

    assert ".venv/" in text
    assert "Logs/*.sqlite" in text
    assert "Logs/*.sqlite-*" in text
    assert "Logs/*.log" in text
    assert "Logs/reports/*.md" in text


def test_background_run_once_empty_fixture_is_reviewed(tmp_path):
    fixture = tmp_path / "empty.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    fixture.write_text("[]")

    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    assert result.ledger.target_id == "NO_TARGETS"
    assert result.ledger.outcome == "reviewed"
    assert result.reviewed is not None
    assert result.needs_follow_up is None
    assert table_count(db_path, "run_ledger") == 1
    assert table_count(db_path, "reviewed_log") == 1


def test_load_tracklets_supports_versioned_manifest(tmp_path):
    fixture = tmp_path / "targets.json"
    write_manifest_fixture(fixture, ("M001", "M002"))

    tracklets = background.load_tracklets(fixture)

    assert [tracklet.object_id for tracklet in tracklets] == ["M001", "M002"]


def test_summaries_return_latest_entries(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())

    background.background_run_once(fixture, db_path, tmp_path / "reports")

    ledger = background.ledger_summary(db_path)
    followup = background.needs_follow_up_summary(db_path)
    reviewed = background.reviewed_log_summary(db_path)
    tests = background.follow_up_test_summary(db_path)
    recommendations = background.submission_recommendation_summary(db_path)
    validation = background.validation_summary(db_path)

    assert ledger["total_runs"] == 1
    assert ledger["by_outcome"] == {"needs_follow_up": 1}
    assert ledger["latest"]["target_id"] == "T001"
    assert followup["total_needs_follow_up"] == 1
    assert reviewed["total_reviewed"] == 0
    assert tests["target_id"] == "T001"
    assert recommendations["recommendations"][-1]["recommended_action"] == "do_not_submit_yet"
    assert validation["one_outcome_per_run"] is True


def test_select_target_uses_highest_composite():
    scored_low = make_scored("LOW", neo_prob=0.1, followup_value=0.1)
    scored_high = make_scored("HIGH", neo_prob=0.8, followup_value=0.9)
    low = background.BackgroundTarget(
        target_id="LOW",
        scored_neo=scored_low,
        priority=background._priority_factors(scored_low, review_count=1),
    )
    high = background.BackgroundTarget(
        target_id="HIGH",
        scored_neo=scored_high,
        priority=background._priority_factors(scored_high, review_count=0),
    )

    assert background.select_target((low, high)) == high


def test_target_priority_summary(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture, ("LOW", "HIGH"))

    def fake_score(tracklet, run_id):
        if tracklet.object_id == "HIGH":
            return make_scored("HIGH", neo_prob=0.8, followup_value=0.9)
        return make_scored("LOW", neo_prob=0.1, followup_value=0.1)

    monkeypatch.setattr(background, "score_tracklet", fake_score)
    summary = background.target_priority_summary(fixture, db_path)

    assert summary["selected_target_id"] == "HIGH"
    assert [target["target_id"] for target in summary["targets"]] == ["HIGH", "LOW"]
    low_summary = summary["targets"][1]
    assert low_summary["skipped_reason_codes"] == ("LOWER_PRIORITY_THAN_SELECTED",)


def test_reviewed_path_for_low_priority(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)

    def fake_score(tracklet, run_id):
        return make_scored(
            tracklet.object_id,
            neo_prob=0.05,
            artifact_prob=0.7,
            known_object_score=0.8,
            followup_value=0.0,
            discovery_priority=0.0,
        )

    monkeypatch.setattr(background, "score_tracklet", fake_score)
    monkeypatch.setattr(background, "_FOLLOW_UP_THRESHOLD", 0.95)
    monkeypatch.setattr(background, "_trigger_reason_codes", lambda target, follow_up_threshold: ())

    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    assert result.ledger.outcome == "reviewed"
    assert result.reviewed is not None
    assert result.needs_follow_up is None
    assert result.reviewed.priority is not None
    assert result.reviewed.negative_evidence


def test_failure_path_writes_reviewed_audit_record(tmp_path):
    fixture = tmp_path / "missing_targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"

    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    assert result.ledger.target_id == "RUN_FAILURE"
    assert result.ledger.outcome == "reviewed"
    assert result.ledger.failure_reason is not None
    assert result.reviewed is not None
    assert table_count(db_path, "run_ledger") == 1
    assert table_count(db_path, "reviewed_log") == 1


def test_lock_conflict_is_logged_as_failure(tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    background.init_log_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO run_lock (lock_id, run_id, acquired_at_utc) VALUES (1, 'busy', 'now')"
        )

    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    assert result.ledger.target_id == "RUN_FAILURE"
    assert "already in progress" in (result.ledger.failure_reason or "")


def test_record_human_signoff_and_validation(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    entry = background.record_human_signoff(
        run_id=result.ledger.run_id,
        target_id=result.ledger.target_id,
        reviewer="Dr. Reviewer",
        decision="approved_for_internal_review",
        scope="Internal follow-up only",
        notes="Looks ready for local review.",
        db_path=db_path,
    )
    summary = background.human_signoff_summary(db_path)
    validation = background.validation_summary(db_path)

    assert entry.reviewer == "Dr. Reviewer"
    assert summary["total_signoffs"] == 1
    assert summary["latest"]["decision"] == "approved_for_internal_review"
    assert validation["total_signoffs"] == 1
    assert validation["lock_active"] is False
    assert validation["sqlite_integrity"] == "ok"
    assert validation["all_follow_up_runs_signed"] is True


def test_multiple_signoffs_and_readiness(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    background.record_human_signoff(
        result.ledger.run_id,
        result.ledger.target_id,
        "Reviewer A",
        "needs_more_work",
        "Internal review",
        db_path=db_path,
    )
    not_ready = background.signoff_readiness_summary(db_path)
    background.record_human_signoff(
        result.ledger.run_id,
        result.ledger.target_id,
        "Reviewer B",
        "approved_for_internal_review",
        "Internal review",
        db_path=db_path,
    )
    ready = background.signoff_readiness_summary(db_path)

    assert not_ready["runs"][0]["is_ready"] is False
    assert not_ready["runs"][0]["report_readiness_state"] == "ready_for_internal_review"
    assert ready["runs"][0]["is_ready"] is True
    assert ready["runs"][0]["report_readiness_state"] == "signed"
    assert ready["runs"][0]["signoff_count"] == 2
    assert ready["runs"][0]["approval_count"] == 1


def test_run_detail_and_target_history(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    detail = background.run_detail(result.ledger.run_id, db_path)
    history = background.target_history(result.ledger.target_id, db_path)

    assert detail["ledger"]["run_id"] == result.ledger.run_id
    assert detail["needs_follow_up"]["target_id"] == result.ledger.target_id
    assert detail["signoff_readiness"]["report_readiness_state"] == "ready_for_internal_review"
    assert history["runs"][0]["target_id"] == result.ledger.target_id


def test_background_cli_subcommands(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "empty.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "reports"
    fixture.write_text("[]")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    run = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "run-once",
            "--input",
            str(fixture),
            "--db",
            str(db_path),
            "--report-dir",
            str(report_dir),
            "--config",
            str(tmp_path / "missing_config.json"),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    run_id = json.loads(run.stdout)["ledger"]["run_id"]

    detail = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "run-detail",
            "--run-id",
            run_id,
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    unsigned = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "unsigned-follow-up",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert json.loads(detail.stdout)["run_id"] == run_id
    assert json.loads(unsigned.stdout)["unsigned_follow_up_runs"] == []


def test_background_cli_automation_commands(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    config_path = repo / "background" / "config.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    readiness = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "automation-readiness",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    plist = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "launchd-plist",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    recorded = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "record-automation-readiness",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    summary = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "automation-readiness-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    plan = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-dry-run-plan",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    recorded_plan = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "record-live-dry-run-plan",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    plan_summary = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-dry-run-plan-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    execution = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-dry-run-execute",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    execution_summary = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-execution-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert json.loads(readiness.stdout)["scheduler_ready"] is True
    assert "org.neo-detection.background" in plist.stdout
    assert json.loads(recorded.stdout)["live_mode_ready"] is False
    assert json.loads(summary.stdout)["total_readiness_checks"] == 1
    assert json.loads(plan.stdout)["network_access_performed"] is False
    assert json.loads(recorded_plan.stdout)["query_count"] == 3
    assert json.loads(plan_summary.stdout)["total_live_dry_run_plans"] == 1
    assert json.loads(execution.stdout)["outcome"] == "blocked"
    assert json.loads(execution_summary.stdout)["total_live_execution_attempts"] == 1


def test_deprecated_background_wrappers_are_removed():
    repo = Path(__file__).resolve().parents[1]

    deprecated = [
        "background_run_once.py",
        "background_ledger_summary.py",
        "background_reviewed_summary.py",
        "background_needs_follow_up_summary.py",
        "background_target_priority_summary.py",
        "background_follow_up_test_summary.py",
        "background_submission_recommendation_summary.py",
        "background_validation_summary.py",
        "background_record_signoff.py",
        "background_human_signoff_summary.py",
    ]

    assert not any((repo / "Skills" / name).exists() for name in deprecated)
    assert (repo / "Skills" / "background.py").exists()


def test_init_log_db_migrates_existing_ledger(tmp_path):
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE run_ledger (
                run_id TEXT PRIMARY KEY,
                started_at_utc TEXT NOT NULL,
                completed_at_utc TEXT NOT NULL,
                code_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                input_path TEXT NOT NULL,
                target_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                selected_score REAL NOT NULL,
                reason_codes_json TEXT NOT NULL,
                live_network_enabled INTEGER NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )

    background.init_log_db(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(run_ledger)")}
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"run_mode", "config_path", "failure_reason"} <= columns
    assert {
        "schema_metadata",
        "run_lock",
        "human_signoff_log",
        "automation_readiness_log",
        "live_dry_run_plan_log",
        "live_execution_log",
    } <= tables


def test_report_text_rejects_forbidden_language():
    scored = make_scored()
    explanation = CandidateExplanation(
        summary="bad",
        supporting_evidence=("confirmed discovery wording",),
        contra_evidence=(),
        model_version="test",
    )
    scored = scored.model_copy(
        update={
            "hazard": HazardAssessment(
                hazard_flag=scored.hazard.hazard_flag,
                moid_au=scored.hazard.moid_au,
                estimated_diameter_m=scored.hazard.estimated_diameter_m,
                absolute_magnitude_h=scored.hazard.absolute_magnitude_h,
                neo_class=scored.hazard.neo_class,
                alert_pathway=scored.hazard.alert_pathway,
                explanation=explanation,
                orbital_elements=scored.hazard.orbital_elements,
            )
        }
    )
    target = background.BackgroundTarget(
        target_id="T001",
        scored_neo=scored,
        priority=background._priority_factors(scored, review_count=0),
    )

    try:
        background._report_text(target, ())
    except ValueError as exc:
        assert "forbidden phrase" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("forbidden report language was accepted")


def test_resolve_project_path_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(background, "_ROOT", tmp_path)
    result = background._resolve_project_path("subdir/file.json")
    assert result == tmp_path / "subdir" / "file.json"


def test_score_tracklet_direct():
    from .conftest import build_tracklet
    tracklet = build_tracklet(n_obs=4, arc_days=3.0)
    scored = background.score_tracklet(tracklet, "run-direct")
    assert scored.tracklet.object_id == tracklet.object_id


def test_blocking_penalty_all_none_features():
    scored = make_scored()
    # Build a scored with None blocking fields
    features_none = CandidateFeatures(
        real_bogus_score=None,
        known_object_score=None,
    )
    # score_tracklet returns a ScoredNEO; use model_copy to patch features + hazard orbital_elements
    scored_none = scored.model_copy(
        update={
            "features": features_none,
            "hazard": HazardAssessment(
                hazard_flag=scored.hazard.hazard_flag,
                moid_au=scored.hazard.moid_au,
                estimated_diameter_m=scored.hazard.estimated_diameter_m,
                absolute_magnitude_h=scored.hazard.absolute_magnitude_h,
                neo_class=scored.hazard.neo_class,
                alert_pathway=scored.hazard.alert_pathway,
                explanation=scored.hazard.explanation,
                orbital_elements=None,
            ),
        }
    )
    penalty = background._blocking_penalty(scored_none)
    assert penalty == min(1.0, 0.25 + 0.25 + 0.10)


def test_review_reasons_alert_pathway_and_hazard_flag(monkeypatch, tmp_path):

    scored = make_scored(neo_prob=0.7, followup_value=0.7, discovery_priority=0.4)
    scored_mpc = scored.model_copy(
        update={
            "hazard": HazardAssessment(
                hazard_flag="pha_candidate",
                moid_au=0.03,
                estimated_diameter_m=200.0,
                absolute_magnitude_h=20.0,
                neo_class=scored.hazard.neo_class,
                alert_pathway="mpc_submission",
                explanation=scored.hazard.explanation,
                orbital_elements=scored.hazard.orbital_elements,
            ),
            "metadata": ScoringMetadata(
                scorer_version="test",
                scored_at_jd=2460000.5,
                pipeline_run_id="run",
                discovery_priority=0.4,
                followup_value=0.7,
                scientific_interest=0.3,
            ),
        }
    )
    # Give it low calibration_confidence and blocking penalty
    features_none = CandidateFeatures(
        real_bogus_score=None,
        known_object_score=None,
    )
    scored_full = scored_mpc.model_copy(
        update={
            "features": features_none,
            "hazard": HazardAssessment(
                hazard_flag="pha_candidate",
                moid_au=0.03,
                estimated_diameter_m=200.0,
                absolute_magnitude_h=20.0,
                neo_class=scored.hazard.neo_class,
                alert_pathway="mpc_submission",
                explanation=scored.hazard.explanation,
                orbital_elements=None,
            ),
        }
    )
    priority = background._priority_factors(scored_full, review_count=0)
    # Manually adjust calibration_confidence to < 0.4
    priority_low_cal = type(priority)(
        composite_score=priority.composite_score,
        scientific_interest=priority.scientific_interest,
        never_reviewed_boost=priority.never_reviewed_boost,
        prior_review_penalty=priority.prior_review_penalty,
        data_completeness=priority.data_completeness,
        false_positive_risk=priority.false_positive_risk,
        followup_feasibility=priority.followup_feasibility,
        calibration_confidence=0.2,
        blocking_issue_penalty=0.5,
    )
    target = background.BackgroundTarget(
        target_id="T_REASONS",
        scored_neo=scored_full,
        priority=priority_low_cal,
    )
    reasons = background._trigger_reason_codes(target)
    assert "ALERT_PATHWAY_REVIEW" in reasons
    assert "HAZARD_FLAG_REVIEW" in reasons
    assert "BLOCKING_ISSUE_REVIEW" in reasons
    assert "CALIBRATION_UNCERTAINTY_REVIEW" in reasons


def test_with_report_readiness_drafted_and_blocked():
    readiness = {"is_ready": False, "signoff_count": 0, "approval_count": 0}
    # "drafted": report_path given but file does not exist
    result = background._with_report_readiness(readiness, "/nonexistent/report.md")
    assert result["report_readiness_state"] == "drafted"
    # "blocked": no report_path
    result2 = background._with_report_readiness(readiness, None)
    assert result2["report_readiness_state"] == "blocked"


def test_background_run_once_raises_on_live_network(tmp_path):
    import json as _json

    fixture = tmp_path / "targets.json"
    fixture.write_text("[]")
    db_path = tmp_path / "bg.sqlite"
    config_path = tmp_path / "config.json"
    config_path.write_text(_json.dumps({
        "live_network_enabled": True,
        "input_path": str(fixture),
        "db_path": str(db_path),
        "report_dir": str(tmp_path / "reports"),
        "follow_up_threshold": 0.5,
    }))

    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=config_path,
    )
    # RuntimeError is caught internally and logged as a run failure
    assert result.ledger.target_id == "RUN_FAILURE"
    assert result.ledger.failure_reason is not None
    assert "blocked" in result.ledger.failure_reason
    assert "LIVE_REVIEW_POLICY_MISSING" in result.ledger.failure_reason


def test_audit_report_returns_required_keys(tmp_path):
    db = tmp_path / "neo.db"
    from background import audit_report, init_log_db
    init_log_db(db)
    result = audit_report(db)
    expected = {
        "total_runs", "reviewed_count", "needs_follow_up_count",
        "signoff_coverage", "unsigned_count", "pha_candidates",
        "submission_ready", "has_unreviewed_runs", "integrity_ok",
    }
    assert expected == set(result.keys())


def test_audit_report_empty_db_all_zeros(tmp_path):
    db = tmp_path / "neo.db"
    from background import audit_report, init_log_db
    init_log_db(db)
    result = audit_report(db)
    assert result["total_runs"] == 0
    assert result["reviewed_count"] == 0
    assert result["needs_follow_up_count"] == 0
    assert result["pha_candidates"] == 0
    assert result["submission_ready"] == 0
    assert result["has_unreviewed_runs"] is False
    assert result["integrity_ok"] is True


def test_audit_report_signoff_coverage_zero_no_reviewed(tmp_path):
    db = tmp_path / "neo.db"
    from background import audit_report, init_log_db
    init_log_db(db)
    result = audit_report(db)
    assert result["signoff_coverage"] == 0.0


def test_audit_report_has_unreviewed_when_runs_present(tmp_path):
    import sqlite3
    db = tmp_path / "neo.db"
    from background import audit_report, init_log_db
    init_log_db(db)
    # Directly insert a minimal ledger row to simulate a completed run
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO run_ledger (
                run_id, started_at_utc, completed_at_utc, code_version, schema_version,
                input_path, target_id, outcome, selected_score, reason_codes_json,
                run_mode, config_path, failure_reason, live_network_enabled, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("r001", "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z",
             "0.14.0", "1", "targets.json", "AU001", "completed",
             0.3, "[]", "manual", "config.json", None, 0, "{}"),
        )
    result = audit_report(db)
    assert result["total_runs"] >= 1
    assert result["has_unreviewed_runs"] is True
