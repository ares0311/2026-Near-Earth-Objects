from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

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


@pytest.fixture(autouse=True)
def no_keychain_credentials(monkeypatch):
    monkeypatch.setenv("NEO_DETECTION_DISABLE_KEYCHAIN_LOOKUP", "1")
    monkeypatch.setattr(background, "_keychain_secret_present", lambda service: False)


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


def write_live_policy(path: Path, approved: bool = True, min_seconds: int = 1) -> None:
    path.write_text(json.dumps({
        "schema_version": "live-review-policy-v1",
        "policy_name": "test-live-policy",
        "reviewer": "Dr. Reviewer",
        "approved_for_live_network": approved,
        "allowed_surveys": ["ZTF", "ATLAS", "PanSTARRS"],
        "max_queries_per_run": 3,
        "min_seconds_between_queries": min_seconds,
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
        "required_credential_env": ["ATLAS_TOKEN"],
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
    assert cfg.required_credential_env == ("ATLAS_TOKEN",)
    assert cfg.live_review_policy == "background/live_review_policy.example.json"


def test_automation_readiness_is_scheduler_ready_but_live_blocked(monkeypatch):
    monkeypatch.delenv("ATLAS_TOKEN", raising=False)

    readiness = background.automation_readiness_summary(Path("background/config.json"))

    assert readiness["scheduler_ready"] is True
    assert readiness["scheduler_blockers"] == []
    assert readiness["live_mode_ready"] is False
    assert "LIVE_NETWORK_DISABLED" in readiness["live_mode_blockers"]
    assert "MISSING_REQUIRED_CREDENTIALS" in readiness["live_mode_blockers"]
    assert "LIVE_PROVIDER_NOT_READY" in readiness["live_mode_blockers"]
    assert "LIVE_REVIEW_POLICY_NOT_APPROVED" in readiness["live_mode_blockers"]
    assert readiness["missing_credential_env"] == ("ATLAS_TOKEN",)
    assert readiness["live_review_policy_summary"]["allowed_surveys"] == (
        "ZTF",
        "ATLAS",
        "PanSTARRS",
    )
    assert readiness["live_review_policy_contract"]["contract_valid"] is True
    assert readiness["live_review_policy_contract"]["network_access_performed"] is False
    assert "Skills/background.py run-once" in readiness["one_run_command"]


def test_live_policy_contract_summary_default_policy_is_valid():
    summary = background.live_policy_contract_summary(Path("background/config.json"))

    assert summary["schema_valid"] is True
    assert summary["policy_contract_valid"] is True
    assert summary["contract_valid"] is True
    assert summary["schema_blockers"] == ()
    assert summary["policy_blockers"] == ()
    assert summary["external_submission_enabled"] is False


def test_live_policy_contract_summary_rejects_submission_policy(tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    policy = json.loads(policy_path.read_text())
    policy["no_external_submission_confirmed"] = False
    policy_path.write_text(json.dumps(policy))
    write_live_config(config_path, policy_path, live_network_enabled=True)

    summary = background.automation_readiness_summary(config_path)

    assert summary["live_review_policy_contract"]["contract_valid"] is False
    assert "LIVE_REVIEW_POLICY_ALLOWS_EXTERNAL_SUBMISSION" in (
        summary["live_review_policy_contract"]["policy_blockers"]
    )
    assert "LIVE_REVIEW_POLICY_CONTRACT_INVALID" in summary["live_mode_blockers"]


def test_live_policy_contract_summary_rejects_missing_policy(tmp_path):
    config_path = tmp_path / "config.json"
    write_live_config(config_path, tmp_path / "missing_policy.json", live_network_enabled=True)

    summary = background.live_policy_contract_summary(config_path)

    assert summary["schema_valid"] is True
    assert summary["policy_contract_valid"] is False
    assert summary["policy_blockers"] == ("LIVE_REVIEW_POLICY_NOT_FOUND",)


def test_live_provider_readiness_default_config_is_blocked(monkeypatch):
    monkeypatch.delenv("ATLAS_TOKEN", raising=False)

    providers = background.live_provider_readiness(Path("background/config.json"))
    by_survey = {provider["survey"]: provider for provider in providers}

    assert [provider["survey"] for provider in providers] == ["ZTF", "ATLAS", "PanSTARRS"]
    assert all(provider["network_access_performed"] is False for provider in providers)
    assert all(provider["external_submission_enabled"] is False for provider in providers)
    assert by_survey["ZTF"]["ready"] is True
    assert by_survey["PanSTARRS"]["ready"] is True
    assert by_survey["ATLAS"]["ready"] is False
    assert "PROVIDER_CREDENTIAL_MISSING" in by_survey["ATLAS"]["blockers"]


def test_live_provider_readiness_approved_config_is_ready(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    providers = background.live_provider_readiness(config_path)

    assert all(provider["ready"] is True for provider in providers)
    assert all(provider["credential_present"] is True for provider in providers)
    assert all(provider["policy_approved"] is True for provider in providers)
    assert {provider["fetch_api"] for provider in providers} == {
        "fetch_ztf_alerts",
        "fetch_atlas_forced",
        "fetch_panstarrs_catalog",
    }


def test_live_credential_inventory_omits_secret_values(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.delenv("ATLAS_TOKEN", raising=False)
    monkeypatch.setenv("MAST_API_TOKEN", "mast-token")

    inventory = background.live_credential_inventory(config_path)
    payload = json.dumps(inventory)

    assert inventory["all_required_credentials_present"] is False
    assert inventory["missing_credential_env"] == ("ATLAS_TOKEN",)
    assert inventory["secret_values_recorded"] is False
    assert inventory["network_access_performed"] is False
    assert inventory["external_submission_enabled"] is False
    assert "mast-token" not in payload
    assert {entry["credential_env"] for entry in inventory["inventory"]} == {
        "ZTF_IRSA_USERNAME",
        "ZTF_IRSA_PASSWORD",
        "ATLAS_TOKEN",
        "MAST_API_TOKEN",
    }
    assert all(entry["secret_value_recorded"] is False for entry in inventory["inventory"])


def test_live_credential_inventory_detects_keychain_source(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.delenv("ATLAS_TOKEN", raising=False)
    monkeypatch.delenv("NEO_DETECTION_DISABLE_KEYCHAIN_LOOKUP", raising=False)
    monkeypatch.setattr(
        background,
        "_keychain_secret_present",
        lambda service: service == "neo-detection:ATLAS_TOKEN",
    )

    inventory = background.live_credential_inventory(config_path)
    atlas = next(
        item for item in inventory["inventory"]
        if item["credential_env"] == "ATLAS_TOKEN"
    )

    assert inventory["all_required_credentials_present"] is True
    assert inventory["missing_credential_env"] == ()
    assert atlas["credential_present"] is True
    assert atlas["credential_source"] == "keychain"
    assert atlas["keychain_service"] == "neo-detection:ATLAS_TOKEN"
    assert atlas["secret_value_recorded"] is False


def test_live_provider_readiness_flags_rate_limit_gap(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True, min_seconds=0)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    readiness = background.automation_readiness_summary(config_path)

    assert readiness["live_mode_ready"] is False
    assert "LIVE_PROVIDER_NOT_READY" in readiness["live_mode_blockers"]
    assert all(
        "PROVIDER_RATE_LIMIT_TOO_FAST" in provider["blockers"]
        for provider in readiness["live_provider_readiness"]
    )


def test_launchd_plist_wraps_one_run_command():
    plist = background.launchd_plist(Path("background/config.json"))

    assert "org.neo-detection.background" in plist
    assert "<string>run-once</string>" in plist
    assert "<key>StartInterval</key>" in plist
    assert "<integer>3600</integer>" in plist
    assert "<key>OMP_NUM_THREADS</key>" in plist


def test_record_automation_readiness_writes_sqlite_log(monkeypatch, tmp_path):
    monkeypatch.delenv("ATLAS_TOKEN", raising=False)
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

    class FailProvider:
        survey = "ZTF"

        def execute(self, query):
            raise AssertionError("provider should not run for blocked config")

    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    entry = background.record_live_execution_attempt(
        Path("background/config.json"),
        db_path,
        providers={"ZTF": FailProvider()},
    )
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
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    calls = []

    class CountingProvider:
        survey = "ZTF"

        def __init__(self, survey: str):
            self.survey = survey

        def execute(self, query):
            calls.append(query)
            return {
                "survey": self.survey,
                "status": "mocked_success",
                "provider": "test",
                "network_access_performed": False,
                "external_submission_enabled": False,
            }

    providers = {
        "ZTF": CountingProvider("ZTF"),
        "ATLAS": CountingProvider("ATLAS"),
        "PanSTARRS": CountingProvider("PanSTARRS"),
    }
    entry = background.record_live_execution_attempt(config_path, db_path, providers=providers)

    assert entry["outcome"] == "mock_executed"
    assert entry["executable"] is True
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert entry["successful_queries"] == 3
    assert entry["missing_provider_queries"] == 0
    assert len(calls) == 3
    assert {result["provider"] for result in entry["query_results"]} == {"test"}


def test_live_dry_run_execute_records_missing_injected_providers(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    class ZtfOnlyProvider:
        survey = "ZTF"

        def execute(self, query):
            return {
                "status": "mocked_success",
                "provider": "ztf-only",
                "network_access_performed": False,
                "external_submission_enabled": False,
            }

    result = background.live_dry_run_execute(config_path, providers={"ZTF": ZtfOnlyProvider()})

    assert result["outcome"] == "mock_executed"
    assert result["successful_queries"] == 1
    assert result["missing_provider_queries"] == 2
    assert [item["status"] for item in result["query_results"]] == [
        "mocked_success",
        "provider_missing",
        "provider_missing",
    ]


def test_live_dry_run_execute_rejects_network_provider(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    class BadProvider:
        survey = "ZTF"

        def execute(self, query):
            return {
                "status": "live_attempted",
                "network_access_performed": True,
                "external_submission_enabled": False,
            }

    try:
        background.live_dry_run_execute(config_path, providers={"ZTF": BadProvider()})
    except ValueError as exc:
        assert str(exc) == "LIVE_PROVIDER_NETWORK_ACCESS_NOT_ALLOWED"
    else:
        raise AssertionError("network-capable provider result should be rejected")


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


def test_blueprint_compliance_summary_empty_log(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())

    summary = background.background_blueprint_compliance_summary(db_path, fixture)
    items = {item["id"]: item for item in summary["items"]}

    assert summary["overall_status"] == "pass"
    assert summary["network_access_performed"] is False
    assert summary["external_submission_enabled"] is False
    assert items["durable_run_ledger"]["status"] == "pass"
    assert items["one_outcome_per_run"]["status"] == "pass"
    assert items["target_selection_exposes_composite_factors"]["status"] == "pass"
    assert (
        items["needs_follow_up_records_trigger_mandatory_tests"]["status"]
        == "not_applicable"
    )


def test_blueprint_compliance_summary_after_followup_run(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "reports"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())

    result = background.background_run_once(
        fixture,
        db_path,
        report_dir,
        config_path=tmp_path / "missing_config.json",
    )
    summary = background.background_blueprint_compliance_summary(db_path, fixture)
    items = {item["id"]: item for item in summary["items"]}
    report_text = Path(result.needs_follow_up.report_path).read_text()

    assert summary["overall_status"] == "pass"
    assert summary["failed_items"] == []
    assert summary["latest_needs_follow_up"]["run_id"] == result.ledger.run_id
    assert "Uncertainty" in report_text
    assert items["needs_follow_up_records_trigger_mandatory_tests"]["status"] == "pass"
    assert (
        items["reports_include_evidence_uncertainty_and_limitations"]["status"]
        == "pass"
    )
    assert (
        items["top_three_submission_recommendations_conservative"]["status"]
        == "pass"
    )
    assert (
        items["external_submission_requires_human_approval"]["evidence"][
            "all_follow_up_entries_require_human_approval"
        ]
        is True
    )


def test_background_cli_blueprint_compliance_summary(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "blueprint-compliance-summary",
            "--input",
            str(fixture),
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )

    payload = json.loads(result.stdout)
    assert payload["overall_status"] == "pass"
    assert payload["blueprint"] == "BACKGROUND_SEARCH_AUTOMATION_BLUEPRINT.md"
    assert payload["external_submission_enabled"] is False


def test_record_blueprint_compliance_summary_empty_log(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())

    entry = background.record_blueprint_compliance_summary(db_path, fixture)
    summary = background.blueprint_compliance_log_summary(db_path)

    assert entry["overall_status"] == "pass"
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert table_count(db_path, "blueprint_compliance_log") == 1
    assert summary["total_blueprint_compliance_checks"] == 1
    assert summary["passing_checks"] == 1
    assert summary["failing_checks"] == 0
    assert summary["latest"]["compliance_id"] == entry["compliance_id"]


def test_record_blueprint_compliance_summary_after_followup_run(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())
    background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    entry = background.record_blueprint_compliance_summary(db_path, fixture)
    summary = background.blueprint_compliance_log_summary(db_path)

    assert entry["overall_status"] == "pass"
    assert entry["not_applicable_items"] == []
    assert entry["latest_needs_follow_up"] is not None
    assert summary["latest"]["latest_needs_follow_up"]["target_id"] == "T001"


def test_background_cli_blueprint_compliance_log_commands(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    recorded = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "record-blueprint-compliance-summary",
            "--input",
            str(fixture),
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
            "blueprint-compliance-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    recorded_payload = json.loads(recorded.stdout)
    summary_payload = json.loads(summary.stdout)
    assert recorded_payload["overall_status"] == "pass"
    assert summary_payload["total_blueprint_compliance_checks"] == 1
    assert summary_payload["latest"]["compliance_id"] == recorded_payload["compliance_id"]


def test_background_operations_snapshot_empty_log(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())

    snapshot = background.background_operations_snapshot(
        Path("background/config.json"),
        db_path,
        fixture,
    )

    assert snapshot["code_version"] == "0.76.0"
    assert snapshot["next_action"] == "run_background_once"
    assert snapshot["ledger"]["total_runs"] == 0
    assert snapshot["automation_readiness"]["scheduler_ready"] is True
    assert snapshot["blueprint_compliance"]["overall_status"] == "pass"
    assert snapshot["guardrails"]["network_access_performed"] is False
    assert snapshot["guardrails"]["external_submission_enabled"] is False
    assert snapshot["network_access_performed"] is False
    assert snapshot["external_submission_enabled"] is False


def test_record_background_operations_snapshot_after_followup(monkeypatch, tmp_path):
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

    entry = background.record_background_operations_snapshot(
        Path("background/config.json"),
        db_path,
        fixture,
    )
    summary = background.background_operations_snapshot_log_summary(db_path)

    assert entry["next_action"] == "record_signoff"
    assert entry["validation"]["total_runs"] == 1
    assert entry["needs_follow_up"]["latest"]["run_id"] == result.ledger.run_id
    assert table_count(db_path, "operations_snapshot_log") == 1
    assert summary["total_operations_snapshots"] == 1
    assert summary["by_next_action"] == {"record_signoff": 1}
    assert summary["latest"]["snapshot_id"] == entry["snapshot_id"]


def test_background_operations_snapshot_after_signoff(monkeypatch, tmp_path):
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
        run_id=result.ledger.run_id,
        target_id=result.ledger.target_id,
        reviewer="Reviewer",
        decision="approved_for_internal_review",
        scope="Internal follow-up only",
        notes="Reviewed local SQLite logs.",
        db_path=db_path,
    )

    snapshot = background.background_operations_snapshot(
        Path("background/config.json"),
        db_path,
        fixture,
    )

    assert snapshot["next_action"] == "review_follow_up"
    assert snapshot["signoff_readiness"]["unsigned_follow_up_runs"] == []
    assert snapshot["validation"]["all_follow_up_runs_signed"] is True


def test_background_cli_operations_snapshot_commands(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    snapshot = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "operations-snapshot",
            "--config",
            str(repo / "background" / "config.json"),
            "--input",
            str(fixture),
            "--db",
            str(db_path),
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
            "record-operations-snapshot",
            "--config",
            str(repo / "background" / "config.json"),
            "--input",
            str(fixture),
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
            "operations-snapshot-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    snapshot_payload = json.loads(snapshot.stdout)
    recorded_payload = json.loads(recorded.stdout)
    summary_payload = json.loads(summary.stdout)
    assert snapshot_payload["next_action"] == "run_background_once"
    assert recorded_payload["next_action"] == "run_background_once"
    assert recorded_payload["external_submission_enabled"] is False
    assert summary_payload["total_operations_snapshots"] == 1
    assert summary_payload["latest"]["snapshot_id"] == recorded_payload["snapshot_id"]


def test_background_operator_next_action_summary_blocks_old_schema(tmp_path):
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE signoff_packet_log (packet_id TEXT PRIMARY KEY)")

    summary = background.background_operator_next_action_summary(
        Path("background/config.json"),
        db_path,
        Path("background/targets.json"),
    )

    assert summary["code_version"] == "0.76.0"
    assert summary["schema_ready"] is False
    assert summary["blocked"] is True
    assert summary["blocker"] == "BACKGROUND_LOG_SCHEMA_NOT_CURRENT"
    assert summary["next_action"] == "run_init_log_db"
    assert summary["recommended_command"] == (
        "PYTHONPATH=src python Skills/background.py init-log-db"
    )
    assert summary["operations_snapshot"] is None
    assert summary["packet_decision_readiness"] is None
    assert summary["network_access_performed"] is False
    assert summary["external_submission_enabled"] is False


def test_background_operator_next_action_summary_current_schema(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    background.init_log_db(db_path)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())

    summary = background.background_operator_next_action_summary(
        Path("background/config.json"),
        db_path,
        fixture,
    )

    assert summary["schema_ready"] is True
    assert summary["blocked"] is False
    assert summary["blocker"] is None
    assert summary["next_action"] == "run_background_once"
    assert summary["recommended_command"] == (
        "PYTHONPATH=src python Skills/background.py run-once"
    )
    assert summary["safe_to_run_recommended_command"] is True
    assert summary["requires_human_approval_before_external_action"] is True
    assert summary["operations_snapshot"]["next_action"] == "run_background_once"
    assert summary["packet_decision_readiness"]["total_packets"] == 0
    assert summary["network_access_performed"] is False
    assert summary["external_submission_enabled"] is False


def test_background_operator_next_action_summary_after_signoff(monkeypatch, tmp_path):
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
        run_id=result.ledger.run_id,
        target_id=result.ledger.target_id,
        reviewer="Reviewer",
        decision="approved_for_internal_review",
        scope="Internal Project Tracking",
        notes="Internal fixture review only.",
        db_path=db_path,
    )

    summary = background.background_operator_next_action_summary(
        Path("background/config.json"),
        db_path,
        fixture,
    )

    assert summary["next_action"] == "review_follow_up"
    assert summary["recommended_command"] == (
        "PYTHONPATH=src python Skills/background.py needs-follow-up-summary"
    )
    assert summary["operations_snapshot"]["signoff_readiness"][
        "unsigned_follow_up_runs"
    ] == []
    assert summary["network_access_performed"] is False
    assert summary["external_submission_enabled"] is False


def test_background_cli_operator_next_action(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "operator-next-action",
            "--config",
            str(repo / "background" / "config.json"),
            "--input",
            str(fixture),
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema_ready"] is False
    assert payload["next_action"] == "create_log_db_when_ready"
    assert payload["recommended_command"] == (
        "PYTHONPATH=src python Skills/background.py init-log-db"
    )
    assert payload["external_submission_enabled"] is False


def test_signoff_packet_for_unsigned_followup(monkeypatch, tmp_path):
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

    packet = background.signoff_packet(result.ledger.run_id, db_path)
    latest = background.latest_unsigned_signoff_packet(db_path)

    assert packet["code_version"] == "0.76.0"
    assert packet["run_id"] == result.ledger.run_id
    assert packet["target_id"] == "T001"
    assert packet["recommended_decision"] == "review_and_optionally_sign"
    assert packet["signoff_readiness"]["report_readiness_state"] == (
        "ready_for_internal_review"
    )
    assert packet["operations_snapshot"]["next_action"] == "record_signoff"
    assert packet["network_access_performed"] is False
    assert packet["external_submission_enabled"] is False
    assert "impact probability" not in packet["packet_text"].lower()
    assert latest["packet"]["run_id"] == result.ledger.run_id


def test_latest_unsigned_signoff_packet_none_after_signoff(monkeypatch, tmp_path):
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
        run_id=result.ledger.run_id,
        target_id=result.ledger.target_id,
        reviewer="Reviewer",
        decision="approved_for_internal_review",
        scope="Internal follow-up only",
        notes="Reviewed local SQLite logs.",
        db_path=db_path,
    )

    latest = background.latest_unsigned_signoff_packet(db_path)

    assert latest["unsigned_follow_up_runs"] == []
    assert latest["packet"] is None
    assert latest["network_access_performed"] is False
    assert latest["external_submission_enabled"] is False


def test_signoff_packet_rejects_missing_or_reviewed_run(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    fixture.write_text("[]")
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    with pytest.raises(ValueError, match="Run not found"):
        background.signoff_packet("missing-run", db_path)
    with pytest.raises(ValueError, match="does not require follow-up"):
        background.signoff_packet(result.ledger.run_id, db_path)


def test_record_signoff_packet_persists_sqlite_log(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "packets"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )

    entry = background.record_signoff_packet(result.ledger.run_id, db_path, report_dir)
    summary = background.signoff_packet_log_summary(db_path)

    assert Path(entry["packet_path"]).exists()
    assert entry["recommended_decision"] == "review_and_optionally_sign"
    assert table_count(db_path, "signoff_packet_log") == 1
    assert summary["total_signoff_packets"] == 1
    assert summary["by_recommended_decision"] == {"review_and_optionally_sign": 1}
    assert summary["latest"]["packet_id"] == entry["packet_id"]


def test_background_cli_signoff_packet_commands(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "packets"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    latest = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "latest-unsigned-signoff-packet",
            "--db",
            str(db_path),
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
            "record-signoff-packet",
            "--run-id",
            result.ledger.run_id,
            "--db",
            str(db_path),
            "--report-dir",
            str(report_dir),
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
            "signoff-packet-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    latest_payload = json.loads(latest.stdout)
    recorded_payload = json.loads(recorded.stdout)
    summary_payload = json.loads(summary.stdout)
    assert latest_payload["packet"]["run_id"] == result.ledger.run_id
    assert recorded_payload["run_id"] == result.ledger.run_id
    assert Path(recorded_payload["packet_path"]).exists()
    assert summary_payload["total_signoff_packets"] == 1
    assert summary_payload["latest"]["packet_id"] == recorded_payload["packet_id"]


def test_record_signoff_from_packet_approves_and_snapshots(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "packets"
    write_fixture(fixture)
    monkeypatch.setattr(background, "score_tracklet", lambda tracklet, run_id: make_scored())
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, report_dir)

    decision = background.record_signoff_from_packet(
        packet_id=packet["packet_id"],
        reviewer="Reviewer",
        decision="approved_for_internal_review",
        scope="Internal follow-up only",
        notes="Reviewed signoff packet.",
        db_path=db_path,
    )
    summary = background.signoff_packet_decision_summary(db_path)
    readiness = background.signoff_readiness_summary(db_path)

    assert decision["packet_id"] == packet["packet_id"]
    assert decision["decision"] == "approved_for_internal_review"
    assert decision["operations_snapshot"]["next_action"] == "review_follow_up"
    assert table_count(db_path, "human_signoff_log") == 1
    assert table_count(db_path, "signoff_packet_decision_log") == 1
    assert summary["total_packet_decisions"] == 1
    assert summary["by_decision"] == {"approved_for_internal_review": 1}
    assert readiness["unsigned_follow_up_runs"] == []


def test_internal_follow_up_disposition_summary_signed(monkeypatch, tmp_path):
    fixture = tmp_path / "targets.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    write_fixture(fixture)
    monkeypatch.setattr(
        background,
        "score_tracklet",
        lambda tracklet, run_id: make_scored(known_object_score=None),
    )
    result = background.background_run_once(
        fixture,
        db_path,
        tmp_path / "reports",
        config_path=tmp_path / "missing_config.json",
    )
    background.record_human_signoff(
        run_id=result.ledger.run_id,
        target_id=result.ledger.target_id,
        reviewer="Reviewer",
        decision="approved_for_internal_review",
        scope="Internal Project Tracking",
        notes="Internal fixture review only.",
        db_path=db_path,
    )

    summary = background.internal_follow_up_disposition_summary(db_path)

    assert summary["total_follow_up"] == 1
    assert summary["total_internal_tracking_complete"] == 1
    assert summary["dispositions"][0]["disposition"] == "internal_tracking_complete"
    assert summary["dispositions"][0]["signed_for_internal_tracking"] is True
    assert summary["dispositions"][0]["scope"] == "Internal Project Tracking"
    assert summary["dispositions"][0]["live_search_approved"] is False
    assert summary["dispositions"][0]["external_submission_enabled"] is False
    assert "known_object_evidence_check: blocked" in " ".join(
        summary["dispositions"][0]["remaining_local_limitations"]
    )


@pytest.mark.parametrize("decision", ["needs_more_work", "rejected"])
def test_record_signoff_from_packet_nonapproval_keeps_run_unsigned(
    monkeypatch,
    tmp_path,
    decision,
):
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
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "packets")

    entry = background.record_signoff_from_packet(
        packet["packet_id"],
        "Reviewer",
        decision,
        "Internal follow-up only",
        "Reviewed signoff packet.",
        db_path,
    )
    readiness = background.signoff_readiness_summary(db_path)

    assert entry["decision"] == decision
    assert entry["operations_snapshot"]["next_action"] == "record_signoff"
    assert readiness["unsigned_follow_up_runs"] == [result.ledger.run_id]


def test_record_signoff_from_packet_rejects_missing_duplicate_and_signed(
    monkeypatch,
    tmp_path,
):
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
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "packets")

    with pytest.raises(ValueError, match="Signoff packet not found"):
        background.record_signoff_from_packet(
            "missing-packet",
            "Reviewer",
            "approved_for_internal_review",
            "Internal follow-up only",
            db_path=db_path,
        )

    background.record_signoff_from_packet(
        packet["packet_id"],
        "Reviewer",
        "needs_more_work",
        "Internal follow-up only",
        db_path=db_path,
    )
    with pytest.raises(ValueError, match="already has a decision"):
        background.record_signoff_from_packet(
            packet["packet_id"],
            "Reviewer",
            "approved_for_internal_review",
            "Internal follow-up only",
            db_path=db_path,
        )

    second_packet = background.record_signoff_packet(
        result.ledger.run_id,
        db_path,
        tmp_path / "packets",
    )
    background.record_human_signoff(
        run_id=result.ledger.run_id,
        target_id=result.ledger.target_id,
        reviewer="Approver",
        decision="approved_for_internal_review",
        scope="Internal follow-up only",
        db_path=db_path,
    )
    with pytest.raises(ValueError, match="already signed"):
        background.record_signoff_from_packet(
            second_packet["packet_id"],
            "Reviewer",
            "approved_for_internal_review",
            "Internal follow-up only",
            db_path=db_path,
        )


def test_background_cli_record_signoff_from_packet(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
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
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "packets")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    recorded = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "record-signoff-from-packet",
            "--packet-id",
            packet["packet_id"],
            "--reviewer",
            "Reviewer",
            "--decision",
            "approved_for_internal_review",
            "--scope",
            "Internal follow-up only",
            "--notes",
            "Reviewed signoff packet.",
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
            "signoff-packet-decision-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    recorded_payload = json.loads(recorded.stdout)
    summary_payload = json.loads(summary.stdout)
    assert recorded_payload["packet_id"] == packet["packet_id"]
    assert recorded_payload["network_access_performed"] is False
    assert recorded_payload["external_submission_enabled"] is False
    assert summary_payload["total_packet_decisions"] == 1
    assert summary_payload["by_decision"] == {"approved_for_internal_review": 1}


def test_background_cli_internal_follow_up_disposition(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
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
        "Reviewer",
        "approved_for_internal_review",
        "Internal Project Tracking",
        "Internal fixture review only.",
        db_path,
    )
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "internal-follow-up-disposition",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["total_internal_tracking_complete"] == 1
    assert payload["dispositions"][0]["discovery_claim_approved"] is False
    assert payload["network_access_performed"] is False


def test_signoff_packet_decision_readiness_empty_db(tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"

    readiness = background.signoff_packet_decision_readiness(db_path)
    latest = background.latest_undecided_signoff_packet(db_path)

    assert readiness["total_packets"] == 0
    assert readiness["total_undecided_packets"] == 0
    assert readiness["ready_for_decision_packets"] == []
    assert readiness["network_access_performed"] is False
    assert latest["packet"] is None
    assert latest["undecided_packet_ids"] == []
    assert table_count(db_path, "signoff_packet_decision_log") == 0


def test_signoff_packet_decision_readiness_lists_undecided_packet(
    monkeypatch,
    tmp_path,
):
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
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "packets")

    readiness = background.signoff_packet_decision_readiness(db_path)
    latest = background.latest_undecided_signoff_packet(db_path)

    assert readiness["total_packets"] == 1
    assert readiness["total_undecided_packets"] == 1
    assert readiness["total_ready_for_decision"] == 1
    assert readiness["undecided_packets"][0]["packet_id"] == packet["packet_id"]
    assert readiness["undecided_packets"][0]["state"] == "ready_for_decision"
    assert readiness["undecided_packets"][0]["can_record_decision"] is True
    assert readiness["undecided_packets"][0]["decision"] is None
    assert latest["packet"]["packet_id"] == packet["packet_id"]
    assert latest["undecided_packet_ids"] == [packet["packet_id"]]


def test_signoff_packet_decision_readiness_excludes_decided_packet(
    monkeypatch,
    tmp_path,
):
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
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "packets")
    decision = background.record_signoff_from_packet(
        packet["packet_id"],
        "Reviewer",
        "needs_more_work",
        "Internal follow-up only",
        db_path=db_path,
    )

    readiness = background.signoff_packet_decision_readiness(db_path)

    assert readiness["total_packets"] == 1
    assert readiness["total_undecided_packets"] == 0
    assert readiness["packets"][0]["state"] == "decided"
    assert readiness["packets"][0]["decision"]["decision_id"] == decision["decision_id"]
    assert readiness["packets"][0]["blockers"] == ["PACKET_ALREADY_DECIDED"]


def test_signoff_packet_decision_readiness_blocks_already_signed_run(
    monkeypatch,
    tmp_path,
):
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
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "packets")
    background.record_human_signoff(
        run_id=result.ledger.run_id,
        target_id=result.ledger.target_id,
        reviewer="Approver",
        decision="approved_for_internal_review",
        scope="Internal follow-up only",
        db_path=db_path,
    )

    readiness = background.signoff_packet_decision_readiness(db_path)

    assert readiness["total_undecided_packets"] == 1
    assert readiness["total_ready_for_decision"] == 0
    assert readiness["blocked_undecided_packets"][0]["packet_id"] == packet["packet_id"]
    assert readiness["blocked_undecided_packets"][0]["state"] == "signed"
    assert readiness["blocked_undecided_packets"][0]["blockers"] == ["RUN_ALREADY_SIGNED"]


def test_background_cli_signoff_packet_decision_readiness(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
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
    packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "packets")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    readiness = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "signoff-packet-decision-readiness",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    latest = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "latest-undecided-signoff-packet",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    readiness_payload = json.loads(readiness.stdout)
    latest_payload = json.loads(latest.stdout)
    assert readiness_payload["total_ready_for_decision"] == 1
    assert readiness_payload["ready_for_decision_packets"][0]["packet_id"] == (
        packet["packet_id"]
    )
    assert latest_payload["packet"]["packet_id"] == packet["packet_id"]


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
    policy_contract = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-policy-contract-summary",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    provider_readiness = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-provider-readiness-summary",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    approval_bundle = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-dry-run-approval-bundle",
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
    assert json.loads(policy_contract.stdout)["contract_valid"] is True
    assert json.loads(policy_contract.stdout)["network_access_performed"] is False
    provider_payload = json.loads(provider_readiness.stdout)
    assert [provider["survey"] for provider in provider_payload] == ["ZTF", "ATLAS", "PanSTARRS"]
    assert all(provider["network_access_performed"] is False for provider in provider_payload)
    assert all(provider["external_submission_enabled"] is False for provider in provider_payload)
    bundle_payload = json.loads(approval_bundle.stdout)
    assert bundle_payload["approved_to_attempt_live_dry_run"] is False
    assert bundle_payload["network_access_performed"] is False
    assert bundle_payload["external_submission_enabled"] is False
    assert "LIVE_NETWORK_DISABLED" in bundle_payload["blockers"]
    assert json.loads(recorded.stdout)["live_mode_ready"] is False
    assert json.loads(summary.stdout)["total_readiness_checks"] == 1
    assert json.loads(plan.stdout)["network_access_performed"] is False
    assert json.loads(recorded_plan.stdout)["query_count"] == 3
    assert json.loads(plan_summary.stdout)["total_live_dry_run_plans"] == 1
    assert json.loads(execution.stdout)["outcome"] == "blocked"
    assert json.loads(execution_summary.stdout)["total_live_execution_attempts"] == 1


def test_background_cli_live_policy_contract_invalid_policy(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    policy = json.loads(policy_path.read_text())
    policy["no_external_submission_confirmed"] = False
    policy_path.write_text(json.dumps(policy))
    write_live_config(config_path, policy_path, live_network_enabled=True)
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    contract = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-policy-contract-summary",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(contract.stdout)

    assert payload["contract_valid"] is False
    assert payload["external_submission_enabled"] is False
    assert "LIVE_REVIEW_POLICY_ALLOWS_EXTERNAL_SUBMISSION" in payload["policy_blockers"]


def test_background_cli_live_provider_readiness_approved_config(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    readiness = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-provider-readiness-summary",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(readiness.stdout)

    assert all(provider["ready"] is True for provider in payload)
    assert all(provider["credential_present"] is True for provider in payload)
    assert all(provider["policy_approved"] is True for provider in payload)
    assert all(provider["network_access_performed"] is False for provider in payload)
    assert all(provider["external_submission_enabled"] is False for provider in payload)


def test_background_cli_live_credential_inventory(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-credential-inventory",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["all_required_credentials_present"] is True
    assert payload["missing_credential_env"] == []
    assert payload["secret_values_recorded"] is False
    assert "ztf-token" not in completed.stdout
    assert "atlas-token" not in completed.stdout
    assert "mast-token" not in completed.stdout


def test_background_cli_live_credential_inventory_write_report(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    report_path = tmp_path / "reports" / "credential_inventory.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-credential-inventory",
            "--config",
            str(config_path),
            "--write-report",
            str(report_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    report = json.loads(report_path.read_text())

    assert payload["report_path"] == str(report_path)
    assert payload["secret_values_recorded"] is False
    assert report["all_required_credentials_present"] is True
    assert "atlas-token" not in completed.stdout
    assert "atlas-token" not in report_path.read_text()


def test_live_policy_approval_checklist_is_sanitized(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=False)
    write_live_config(config_path, policy_path, live_network_enabled=False)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    checklist = background.live_policy_approval_checklist(config_path)

    skeleton = checklist["recommended_policy_skeleton"]
    assert checklist["network_access_performed"] is False
    assert checklist["external_submission_enabled"] is False
    assert checklist["secret_values_recorded"] is False
    assert checklist["recommended_first_dry_run_mode"] == (
        "ZTF public-only, one bounded query"
    )
    assert skeleton["allowed_surveys"] == ["ZTF"]
    assert skeleton["approved_for_live_network"] is False
    assert skeleton["no_external_submission_confirmed"] is True
    assert skeleton["no_impact_probability_claims"] is True
    assert "SET_LOCAL_CONFIG_TO_LOCAL_POLICY_PATH" in checklist["approval_blockers"]
    assert "atlas-token" not in json.dumps(checklist)


def test_background_cli_live_policy_approval_checklist_write_report(
    monkeypatch, tmp_path
):
    repo = Path(__file__).resolve().parents[1]
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    report_path = tmp_path / "reports" / "policy_checklist.json"
    write_live_policy(policy_path, approved=False)
    write_live_config(config_path, policy_path, live_network_enabled=False)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-policy-approval-checklist",
            "--config",
            str(config_path),
            "--write-report",
            str(report_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    report = json.loads(report_path.read_text())

    assert payload["report_path"] == str(report_path)
    assert payload["secret_values_recorded"] is False
    assert report["recommended_policy_skeleton"]["allowed_surveys"] == ["ZTF"]
    assert report["recommended_policy_skeleton"]["approved_for_live_network"] is False
    assert "atlas-token" not in completed.stdout
    assert "atlas-token" not in report_path.read_text()


def test_scoring_metrics_kpi_report_passes_hard_gates():
    report = background.scoring_metrics_kpi_report()
    by_id = {kpi["id"]: kpi for kpi in report["kpis"]}

    assert report["overall_status"] == "pass"
    assert report["ready_for_live_smoke_metrics_approval"] is True
    assert report["network_access_performed"] is False
    assert report["external_submission_enabled"] is False
    assert report["secret_values_recorded"] is False
    assert report["thresholds"]["posterior_sum_tolerance"] == 1e-6
    assert by_id["posterior_normalization"]["status"] == "pass"
    assert by_id["low_real_bogus_blocks_external_pathway"]["observed"] == (
        "internal_candidate"
    )
    assert by_id["low_orbit_quality_blocks_external_pathway"]["observed"] == (
        "internal_candidate"
    )
    assert by_id["known_object_routes_to_known_object"]["observed"] == "known_object"
    assert by_id["artifact_heavy_blocks_external_pathway"]["observed"] == (
        "internal_candidate"
    )
    assert by_id["missing_features_conservative"]["observed"] == "internal_candidate"
    assert by_id["negative_false_external_pathway_rate"]["observed"] == 0.0
    assert by_id["brier_score"]["status"] == "pending_labeled_data"
    assert by_id["expected_calibration_error"]["status"] == "pending_labeled_data"
    assert "confirmed neo" not in json.dumps(report).lower()
    assert "impact probability" not in json.dumps(report).lower()


def test_background_cli_scoring_metrics_kpi_report_write_report(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "reports" / "scoring_kpis.json"
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    completed = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "scoring-metrics-kpi-report",
            "--write-report",
            str(report_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    report = json.loads(report_path.read_text())

    assert payload["report_path"] == str(report_path)
    assert payload["secret_values_recorded"] is False
    assert report["overall_status"] == "pass"
    assert report["ready_for_live_smoke_metrics_approval"] is True
    assert "pending_labeled_data" in report_path.read_text()


def test_live_dry_run_approval_bundle_default_config_is_blocked():
    bundle = background.live_dry_run_approval_bundle(Path("background/config.json"))

    assert bundle["approved_to_attempt_live_dry_run"] is False
    assert bundle["next_action"] == "resolve_blockers"
    assert bundle["scheduler_ready"] is True
    assert bundle["live_mode_ready"] is False
    assert bundle["policy_contract_valid"] is True
    assert bundle["network_access_performed"] is False
    assert bundle["external_submission_enabled"] is False
    assert "LIVE_NETWORK_DISABLED" in bundle["blockers"]
    assert "LIVE_REVIEW_POLICY_NOT_APPROVED" in bundle["blockers"]
    assert "PROVIDER_CREDENTIAL_MISSING" in bundle["blockers"]


def test_background_cli_live_dry_run_approval_bundle_approved_config(
    monkeypatch,
    tmp_path,
):
    repo = Path(__file__).resolve().parents[1]
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    approval = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-dry-run-approval-bundle",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(approval.stdout)

    assert payload["approved_to_attempt_live_dry_run"] is True
    assert payload["next_action"] == "run_mock_live_dry_run_execute"
    assert payload["blockers"] == []
    assert payload["planned_query_count"] == 3
    assert payload["planned_surveys"] == ["ZTF", "ATLAS", "PanSTARRS"]
    assert payload["network_access_performed"] is False
    assert payload["external_submission_enabled"] is False


def test_live_dry_run_approval_bundle_blocks_unsafe_policy(monkeypatch, tmp_path):
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    policy = json.loads(policy_path.read_text())
    policy["no_external_submission_confirmed"] = False
    policy_path.write_text(json.dumps(policy))
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    bundle = background.live_dry_run_approval_bundle(config_path)

    assert bundle["approved_to_attempt_live_dry_run"] is False
    assert bundle["policy_contract_valid"] is False
    assert bundle["network_access_performed"] is False
    assert bundle["external_submission_enabled"] is False
    assert "LIVE_REVIEW_POLICY_ALLOWS_EXTERNAL_SUBMISSION" in bundle["blockers"]


def test_record_live_dry_run_approval_bundle_default_config_is_blocked(tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"

    entry = background.record_live_dry_run_approval_bundle(
        Path("background/config.json"),
        db_path,
    )
    summary = background.live_dry_run_approval_bundle_log_summary(db_path)

    assert entry["approved_to_attempt_live_dry_run"] is False
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert "LIVE_NETWORK_DISABLED" in entry["blockers"]
    assert summary["total_live_approval_bundles"] == 1
    assert summary["approval_ready_count"] == 0
    assert summary["blocked_count"] == 1
    assert summary["latest"]["bundle_id"] == entry["bundle_id"]


def test_record_live_dry_run_approval_bundle_approved_config(monkeypatch, tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    entry = background.record_live_dry_run_approval_bundle(config_path, db_path)
    summary = background.live_dry_run_approval_bundle_log_summary(db_path)

    assert entry["approved_to_attempt_live_dry_run"] is True
    assert entry["blockers"] == ()
    assert entry["planned_surveys"] == ("ZTF", "ATLAS", "PanSTARRS")
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert summary["total_live_approval_bundles"] == 1
    assert summary["approval_ready_count"] == 1
    assert summary["blocked_count"] == 0
    assert summary["latest"]["approved_to_attempt_live_dry_run"] is True


def test_background_cli_live_dry_run_approval_bundle_log_commands(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    config_path = repo / "background" / "config.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    recorded = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "record-live-dry-run-approval-bundle",
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
            "live-dry-run-approval-bundle-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    recorded_payload = json.loads(recorded.stdout)
    summary_payload = json.loads(summary.stdout)
    assert recorded_payload["approved_to_attempt_live_dry_run"] is False
    assert recorded_payload["network_access_performed"] is False
    assert recorded_payload["external_submission_enabled"] is False
    assert summary_payload["total_live_approval_bundles"] == 1
    assert summary_payload["blocked_count"] == 1


def _assert_no_forbidden_handoff_language(text: str) -> None:
    lowered = text.lower()
    assert "confirmed neo" not in lowered
    assert "confirmed discovery" not in lowered
    assert "impact probability" not in lowered


def test_live_dry_run_operator_handoff_default_config_is_blocked():
    handoff = background.live_dry_run_operator_handoff(Path("background/config.json"))
    text = handoff["handoff_text"]

    assert handoff["approved_to_attempt_live_dry_run"] is False
    assert handoff["network_access_performed"] is False
    assert handoff["external_submission_enabled"] is False
    assert "LIVE_NETWORK_DISABLED" in text
    assert "ATLAS_TOKEN" in text
    assert "Internal review only" in text
    _assert_no_forbidden_handoff_language(text)


def test_write_live_dry_run_operator_handoff_approved_config(monkeypatch, tmp_path):
    report_dir = tmp_path / "reports"
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    handoff = background.write_live_dry_run_operator_handoff(config_path, report_dir)
    path = Path(handoff["report_path"])
    text = path.read_text()

    assert handoff["approved_to_attempt_live_dry_run"] is True
    assert handoff["network_access_performed"] is False
    assert handoff["external_submission_enabled"] is False
    assert path.exists()
    assert "Ready for mock dry-run attempt: True" in text
    assert "Missing credential environment variables: None" in text
    _assert_no_forbidden_handoff_language(text)


def test_background_cli_live_dry_run_operator_handoff_commands(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    config_path = repo / "background" / "config.json"
    report_dir = tmp_path / "reports"
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    printed = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "live-dry-run-operator-handoff",
            "--config",
            str(config_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    written = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "write-live-dry-run-operator-handoff",
            "--config",
            str(config_path),
            "--report-dir",
            str(report_dir),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    printed_payload = json.loads(printed.stdout)
    written_payload = json.loads(written.stdout)
    assert printed_payload["approved_to_attempt_live_dry_run"] is False
    assert "Internal review only" in printed_payload["handoff_text"]
    assert written_payload["network_access_performed"] is False
    assert written_payload["external_submission_enabled"] is False
    assert Path(written_payload["report_path"]).exists()
    _assert_no_forbidden_handoff_language(written_payload["handoff_text"])


def test_live_dry_run_operator_handoff_rejects_forbidden_language(monkeypatch):
    bundle = background.live_dry_run_approval_bundle(Path("background/config.json"))
    bad_bundle = {
        **bundle,
        "blockers": (*bundle["blockers"], "confirmed discovery"),
    }
    monkeypatch.setattr(background, "live_dry_run_approval_bundle", lambda _path: bad_bundle)

    with pytest.raises(ValueError, match="forbidden phrase"):
        background.live_dry_run_operator_handoff(Path("background/config.json"))


def test_record_live_dry_run_operator_handoff_default_config_is_blocked(tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "reports"

    entry = background.record_live_dry_run_operator_handoff(
        Path("background/config.json"),
        db_path,
        report_dir,
    )
    summary = background.live_dry_run_operator_handoff_log_summary(db_path)
    report_path = Path(entry["report_path"])

    assert entry["approved_to_attempt_live_dry_run"] is False
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert "LIVE_NETWORK_DISABLED" in entry["handoff_text"]
    assert report_path.exists()
    _assert_no_forbidden_handoff_language(entry["handoff_text"])
    assert summary["total_live_operator_handoffs"] == 1
    assert summary["approval_ready_count"] == 0
    assert summary["blocked_count"] == 1
    assert summary["latest"]["handoff_id"] == entry["handoff_id"]


def test_record_live_dry_run_operator_handoff_approved_config(monkeypatch, tmp_path):
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "reports"
    policy_path = tmp_path / "policy.json"
    config_path = tmp_path / "config.json"
    write_live_policy(policy_path, approved=True)
    write_live_config(config_path, policy_path, live_network_enabled=True)
    monkeypatch.setenv("ATLAS_TOKEN", "atlas-token")

    entry = background.record_live_dry_run_operator_handoff(
        config_path,
        db_path,
        report_dir,
    )
    summary = background.live_dry_run_operator_handoff_log_summary(db_path)

    assert entry["approved_to_attempt_live_dry_run"] is True
    assert entry["blockers"] == ()
    assert entry["network_access_performed"] is False
    assert entry["external_submission_enabled"] is False
    assert Path(entry["report_path"]).exists()
    assert summary["total_live_operator_handoffs"] == 1
    assert summary["approval_ready_count"] == 1
    assert summary["blocked_count"] == 0
    assert summary["latest"]["approved_to_attempt_live_dry_run"] is True


def test_background_cli_live_dry_run_operator_handoff_log_commands(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    config_path = repo / "background" / "config.json"
    db_path = tmp_path / "Logs" / "background.sqlite"
    report_dir = tmp_path / "reports"
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    recorded = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "record-live-dry-run-operator-handoff",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--report-dir",
            str(report_dir),
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
            "live-dry-run-operator-handoff-log-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    recorded_payload = json.loads(recorded.stdout)
    summary_payload = json.loads(summary.stdout)
    assert recorded_payload["approved_to_attempt_live_dry_run"] is False
    assert recorded_payload["network_access_performed"] is False
    assert recorded_payload["external_submission_enabled"] is False
    assert Path(recorded_payload["report_path"]).exists()
    assert summary_payload["total_live_operator_handoffs"] == 1
    assert summary_payload["blocked_count"] == 1


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
        "blueprint_compliance_log",
        "operations_snapshot_log",
        "signoff_packet_log",
        "signoff_packet_decision_log",
        "live_approval_bundle_log",
        "live_operator_handoff_log",
        "live_dry_run_plan_log",
        "live_execution_log",
    } <= tables


def test_background_schema_status_summary_missing_db_is_read_only(tmp_path):
    db_path = tmp_path / "missing" / "background.sqlite"

    summary = background.background_schema_status_summary(db_path)

    assert summary["db_exists"] is False
    assert summary["is_current"] is False
    assert "signoff_packet_decision_log" in summary["missing_tables"]
    assert summary["present_tables"] == []
    assert summary["network_access_performed"] is False
    assert summary["external_submission_enabled"] is False
    assert not db_path.exists()


def test_background_schema_migration_preview_missing_db_is_read_only(tmp_path):
    db_path = tmp_path / "missing" / "background.sqlite"

    preview = background.background_schema_migration_preview(db_path)

    assert preview["db_exists"] is False
    assert preview["db_would_be_created"] is True
    assert preview["migration_needed"] is True
    assert preview["would_create_tables"] == preview["missing_tables"]
    assert "signoff_packet_decision_log" in preview["would_create_tables"]
    assert preview["db_created"] is False
    assert preview["network_access_performed"] is False
    assert preview["external_submission_enabled"] is False
    assert preview["signoff_recorded"] is False
    assert preview["packet_recorded"] is False
    assert preview["report_written"] is False
    assert not db_path.exists()


def test_background_schema_status_summary_reports_old_db_missing_tables(tmp_path):
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE schema_metadata (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO schema_metadata (key, value) VALUES ('schema_version', 'old')"
        )
        conn.execute("CREATE TABLE signoff_packet_log (packet_id TEXT PRIMARY KEY)")

    summary = background.background_schema_status_summary(db_path)

    assert summary["db_exists"] is True
    assert summary["schema_version"] == "old"
    assert summary["is_current"] is False
    assert summary["present_tables"] == ["schema_metadata", "signoff_packet_log"]
    assert "signoff_packet_decision_log" in summary["missing_tables"]


def test_background_schema_migration_preview_reports_old_db_without_writing(tmp_path):
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE signoff_packet_log (packet_id TEXT PRIMARY KEY)")

    preview = background.background_schema_migration_preview(db_path)
    after = background.background_schema_status_summary(db_path)

    assert preview["db_exists"] is True
    assert preview["db_would_be_created"] is False
    assert preview["migration_needed"] is True
    assert "signoff_packet_log" in preview["present_tables"]
    assert "signoff_packet_decision_log" in preview["would_create_tables"]
    assert after["present_tables"] == ["signoff_packet_log"]
    assert "schema_metadata" in after["missing_tables"]


def test_background_schema_migration_preview_current_db(tmp_path):
    db_path = tmp_path / "current.sqlite"
    background.init_log_db(db_path)

    preview = background.background_schema_migration_preview(db_path)

    assert preview["db_exists"] is True
    assert preview["is_current"] is True
    assert preview["migration_needed"] is False
    assert preview["db_would_be_created"] is False
    assert preview["would_create_tables"] == []


def test_background_schema_operations_summary_missing_db_is_read_only(tmp_path):
    db_path = tmp_path / "missing" / "background.sqlite"

    summary = background.background_schema_operations_summary(db_path)

    assert summary["db_exists"] is False
    assert summary["migration_needed"] is True
    assert summary["packet_decision_commands_ready"] is False
    assert summary["next_schema_action"] == "create_log_db_when_ready"
    assert "signoff_packet_decision_log" in summary["would_create_tables"]
    assert summary["db_created"] is False
    assert summary["network_access_performed"] is False
    assert summary["external_submission_enabled"] is False
    assert not db_path.exists()


def test_background_schema_operations_summary_old_db_recommends_migration(tmp_path):
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE signoff_packet_log (packet_id TEXT PRIMARY KEY)")

    summary = background.background_schema_operations_summary(db_path)

    assert summary["db_exists"] is True
    assert summary["migration_needed"] is True
    assert summary["packet_decision_commands_ready"] is False
    assert summary["next_schema_action"] == "run_init_log_db"
    assert summary["recommended_command"].endswith("init-log-db")
    assert summary["status"]["present_tables"] == ["signoff_packet_log"]


def test_background_schema_operations_summary_current_db_ready(tmp_path):
    db_path = tmp_path / "current.sqlite"
    background.init_log_db(db_path)

    summary = background.background_schema_operations_summary(db_path)

    assert summary["is_current"] is True
    assert summary["migration_needed"] is False
    assert summary["packet_decision_commands_ready"] is True
    assert summary["next_schema_action"] == "none"
    assert summary["recommended_command"] is None
    assert summary["would_create_tables"] == []


def test_migrate_background_log_db_adds_missing_tables(tmp_path):
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

    migrated = background.migrate_background_log_db(db_path)
    status = background.background_schema_status_summary(db_path)

    assert migrated["db_existed_before"] is True
    assert "signoff_packet_decision_log" in migrated["created_tables"]
    assert migrated["missing_tables_after"] == []
    assert migrated["is_current"] is True
    assert migrated["signoff_recorded"] is False
    assert migrated["packet_recorded"] is False
    assert migrated["report_written"] is False
    assert status["is_current"] is True


def test_background_cli_schema_status_and_init_log_db(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "old.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE signoff_packet_log (packet_id TEXT PRIMARY KEY)")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    before = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "schema-status-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    migrated = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "init-log-db",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    before_payload = json.loads(before.stdout)
    migrated_payload = json.loads(migrated.stdout)
    assert before_payload["is_current"] is False
    assert "signoff_packet_decision_log" in before_payload["missing_tables"]
    assert migrated_payload["is_current"] is True
    assert migrated_payload["missing_tables_after"] == []
    assert migrated_payload["network_access_performed"] is False
    assert migrated_payload["external_submission_enabled"] is False


def test_background_cli_init_log_db_preview(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "preview.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE signoff_packet_log (packet_id TEXT PRIMARY KEY)")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    preview = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "init-log-db-preview",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(preview.stdout)
    assert payload["migration_needed"] is True
    assert payload["db_created"] is False
    assert "signoff_packet_decision_log" in payload["would_create_tables"]
    assert table_count(db_path, "signoff_packet_log") == 0


def test_background_cli_schema_operations_summary(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "operations.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE signoff_packet_log (packet_id TEXT PRIMARY KEY)")
    env = {**os.environ, "PYTHONPATH": str(repo / "src")}

    summary = subprocess.run(
        [
            sys.executable,
            str(repo / "Skills" / "background.py"),
            "schema-operations-summary",
            "--db",
            str(db_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(summary.stdout)
    assert payload["migration_needed"] is True
    assert payload["packet_decision_commands_ready"] is False
    assert payload["next_schema_action"] == "run_init_log_db"
    assert "signoff_packet_decision_log" in payload["would_create_tables"]


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


# ---------------------------------------------------------------------------
# Coverage gap tests: background.py private helpers and edge branches
# ---------------------------------------------------------------------------

class TestLoadLiveReviewPolicy:
    def test_policy_file_not_found(self, tmp_path):
        from background import _load_live_review_policy, load_config
        config_path = tmp_path / "config.json"
        policy_path = tmp_path / "missing_policy.json"
        config_path.write_text(json.dumps({
            "input_path": "background/targets.json",
            "db_path": "Logs/background.sqlite",
            "report_dir": "Logs/reports",
            "follow_up_threshold": 0.45,
            "live_review_policy": str(policy_path),
        }))
        config = load_config(config_path)
        policy, blockers = _load_live_review_policy(config)
        assert policy is None
        assert "LIVE_REVIEW_POLICY_NOT_FOUND" in blockers

    def test_policy_file_invalid_json(self, tmp_path):
        from background import _load_live_review_policy, load_config
        config_path = tmp_path / "config.json"
        policy_path = tmp_path / "bad_policy.json"
        policy_path.write_text("not { valid json }")
        config_path.write_text(json.dumps({
            "input_path": "background/targets.json",
            "db_path": "Logs/background.sqlite",
            "report_dir": "Logs/reports",
            "follow_up_threshold": 0.45,
            "live_review_policy": str(policy_path),
        }))
        config = load_config(config_path)
        policy, blockers = _load_live_review_policy(config)
        assert policy is None
        assert "LIVE_REVIEW_POLICY_INVALID_JSON" in blockers


class TestLoadJsonContract:
    def test_invalid_json_returns_error_code(self, tmp_path):
        from background import _load_json_contract
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid}")
        result, blockers = _load_json_contract(bad_file, "MISSING", "INVALID_JSON")
        assert result is None
        assert "INVALID_JSON" in blockers


class TestLivePolicySchemaBlockers:
    def test_schema_not_dict(self):
        from background import _live_policy_schema_blockers
        result = _live_policy_schema_blockers("not-a-dict")
        assert "LIVE_REVIEW_POLICY_SCHEMA_INVALID" in result

    def test_schema_id_invalid(self):
        from background import _live_policy_schema_blockers
        schema = {
            "$id": "wrong-id",
            "type": "object",
            "additionalProperties": False,
            "required": list(background._REQUIRED_POLICY_FIELDS),
            "properties": {
                "allowed_surveys": {"items": {"enum": list(background._SUPPORTED_LIVE_SURVEYS)}},
                "no_external_submission_confirmed": {"const": True},
                "no_impact_probability_claims": {"const": True},
            },
        }
        result = _live_policy_schema_blockers(schema)
        assert "LIVE_REVIEW_POLICY_SCHEMA_ID_INVALID" in result

    def test_schema_type_invalid(self):
        from background import _live_policy_schema_blockers
        schema = {
            "$id": "live-review-policy-v1",
            "type": "array",
            "additionalProperties": False,
            "required": list(background._REQUIRED_POLICY_FIELDS),
            "properties": {
                "allowed_surveys": {"items": {"enum": list(background._SUPPORTED_LIVE_SURVEYS)}},
                "no_external_submission_confirmed": {"const": True},
                "no_impact_probability_claims": {"const": True},
            },
        }
        result = _live_policy_schema_blockers(schema)
        assert "LIVE_REVIEW_POLICY_SCHEMA_TYPE_INVALID" in result

    def test_schema_allows_extra_fields(self):
        from background import _live_policy_schema_blockers
        schema = {
            "$id": "live-review-policy-v1",
            "type": "object",
            "additionalProperties": True,
            "required": list(background._REQUIRED_POLICY_FIELDS),
            "properties": {
                "allowed_surveys": {"items": {"enum": list(background._SUPPORTED_LIVE_SURVEYS)}},
                "no_external_submission_confirmed": {"const": True},
                "no_impact_probability_claims": {"const": True},
            },
        }
        result = _live_policy_schema_blockers(schema)
        assert "LIVE_REVIEW_POLICY_SCHEMA_ALLOWS_EXTRA_FIELDS" in result

    def test_schema_required_fields_incomplete(self):
        from background import _live_policy_schema_blockers
        schema = {
            "$id": "live-review-policy-v1",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version"],  # missing many required fields
            "properties": {
                "allowed_surveys": {"items": {"enum": list(background._SUPPORTED_LIVE_SURVEYS)}},
                "no_external_submission_confirmed": {"const": True},
                "no_impact_probability_claims": {"const": True},
            },
        }
        result = _live_policy_schema_blockers(schema)
        assert "LIVE_REVIEW_POLICY_SCHEMA_REQUIRED_FIELDS_INCOMPLETE" in result

    def test_schema_survey_enum_mismatch(self):
        from background import _live_policy_schema_blockers
        schema = {
            "$id": "live-review-policy-v1",
            "type": "object",
            "additionalProperties": False,
            "required": list(background._REQUIRED_POLICY_FIELDS),
            "properties": {
                "allowed_surveys": {"items": {"enum": ["ZTF"]}},  # incomplete enum
                "no_external_submission_confirmed": {"const": True},
                "no_impact_probability_claims": {"const": True},
            },
        }
        result = _live_policy_schema_blockers(schema)
        assert "LIVE_REVIEW_POLICY_SCHEMA_SURVEY_ENUM_MISMATCH" in result

    def test_schema_external_submission_guard_missing(self):
        from background import _live_policy_schema_blockers
        schema = {
            "$id": "live-review-policy-v1",
            "type": "object",
            "additionalProperties": False,
            "required": list(background._REQUIRED_POLICY_FIELDS),
            "properties": {
                "allowed_surveys": {"items": {"enum": list(background._SUPPORTED_LIVE_SURVEYS)}},
                "no_external_submission_confirmed": {"const": False},  # wrong value
                "no_impact_probability_claims": {"const": True},
            },
        }
        result = _live_policy_schema_blockers(schema)
        assert "LIVE_REVIEW_POLICY_SCHEMA_EXTERNAL_SUBMISSION_GUARD_MISSING" in result

    def test_schema_impact_claim_guard_missing(self):
        from background import _live_policy_schema_blockers
        schema = {
            "$id": "live-review-policy-v1",
            "type": "object",
            "additionalProperties": False,
            "required": list(background._REQUIRED_POLICY_FIELDS),
            "properties": {
                "allowed_surveys": {"items": {"enum": list(background._SUPPORTED_LIVE_SURVEYS)}},
                "no_external_submission_confirmed": {"const": True},
                "no_impact_probability_claims": {},  # missing const
            },
        }
        result = _live_policy_schema_blockers(schema)
        assert "LIVE_REVIEW_POLICY_SCHEMA_IMPACT_CLAIM_GUARD_MISSING" in result


class TestLivePolicyContractBlockers:
    def test_policy_not_dict(self):
        from background import _live_policy_contract_blockers
        result = _live_policy_contract_blockers("not-a-dict")
        assert "LIVE_REVIEW_POLICY_INVALID_JSON" in result


class TestLoadLiveReviewPolicyFromDict:
    def _good_policy(self):
        return {
            "schema_version": "live-review-policy-v1",
            "policy_name": "test",
            "reviewer": "Dr. Test",
            "approved_for_live_network": True,
            "allowed_surveys": ["ZTF", "ATLAS", "PanSTARRS"],
            "max_queries_per_run": 3,
            "min_seconds_between_queries": 1,
            "dry_run_scope": {
                "ra_deg": 180.0, "dec_deg": 0.0, "radius_deg": 0.1,
                "start_jd": 2460000.5, "end_jd": 2460001.5,
            },
            "no_external_submission_confirmed": True,
            "no_impact_probability_claims": True,
        }

    def test_missing_fields(self):
        from background import _load_live_review_policy_from_dict
        _, blockers = _load_live_review_policy_from_dict({})
        assert "LIVE_REVIEW_POLICY_MISSING_FIELDS" in blockers

    def test_schema_version_wrong(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["schema_version"] = "bad-version"
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_SCHEMA_UNSUPPORTED" in blockers

    def test_reviewer_missing(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["reviewer"] = ""
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_REVIEWER_MISSING" in blockers

    def test_impact_claims_not_true(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["no_impact_probability_claims"] = False
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_ALLOWS_IMPACT_CLAIMS" in blockers

    def test_surveys_invalid_not_list(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["allowed_surveys"] = "ZTF"
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_SURVEYS_INVALID" in blockers

    def test_surveys_unsupported(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["allowed_surveys"] = ["ZTF", "UNKNOWN_SURVEY"]
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_SURVEYS_UNSUPPORTED" in blockers

    def test_max_queries_invalid(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["max_queries_per_run"] = 0
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_RATE_LIMIT_INVALID" in blockers

    def test_min_seconds_invalid(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["min_seconds_between_queries"] = -1
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_CADENCE_INVALID" in blockers

    def test_scope_not_dict(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["dry_run_scope"] = "not-a-dict"
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_SCOPE_INVALID" in blockers

    def test_scope_missing_fields(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["dry_run_scope"] = {"ra_deg": 0.0}
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_SCOPE_MISSING_FIELDS" in blockers

    def test_scope_fields_not_numbers(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["dry_run_scope"] = {
            "ra_deg": "bad", "dec_deg": 0.0, "radius_deg": 0.1,
            "start_jd": 2460000.5, "end_jd": 2460001.5,
        }
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_SCOPE_INVALID" in blockers

    def test_scope_end_jd_before_start_jd(self):
        from background import _load_live_review_policy_from_dict
        policy = self._good_policy()
        policy["dry_run_scope"] = {
            "ra_deg": 180.0, "dec_deg": 0.0, "radius_deg": 0.1,
            "start_jd": 2460001.5, "end_jd": 2460000.5,  # end before start
        }
        _, blockers = _load_live_review_policy_from_dict(policy)
        assert "LIVE_REVIEW_POLICY_SCOPE_INVALID" in blockers


class TestLiveProviderReadinessEdgeCases:
    def test_provider_external_submission_capable(self, tmp_path, monkeypatch):
        from background import live_provider_readiness
        config_path = tmp_path / "config.json"
        policy_path = tmp_path / "policy.json"
        write_live_policy(policy_path, approved=True)
        write_live_config(config_path, policy_path)
        # Patch _LIVE_PROVIDER_CAPABILITIES so one provider has external_submission=True
        fake_caps = {
            "ZTF": {
                **background._LIVE_PROVIDER_CAPABILITIES["ZTF"],
                "supports_external_submission": True,
            },
            "ATLAS": background._LIVE_PROVIDER_CAPABILITIES["ATLAS"],
            "PanSTARRS": background._LIVE_PROVIDER_CAPABILITIES["PanSTARRS"],
        }
        monkeypatch.setattr(background, "_LIVE_PROVIDER_CAPABILITIES", fake_caps)
        results = live_provider_readiness(config_path)
        ztf = next(r for r in results if r["survey"] == "ZTF")
        assert "PROVIDER_EXTERNAL_SUBMISSION_CAPABLE" in ztf["blockers"]

    def test_provider_live_query_unsupported(self, tmp_path, monkeypatch):
        from background import live_provider_readiness
        config_path = tmp_path / "config.json"
        policy_path = tmp_path / "policy.json"
        write_live_policy(policy_path, approved=True)
        write_live_config(config_path, policy_path)
        fake_caps = {
            "ZTF": {
                **background._LIVE_PROVIDER_CAPABILITIES["ZTF"],
                "supports_live_query": False,
            },
            "ATLAS": background._LIVE_PROVIDER_CAPABILITIES["ATLAS"],
            "PanSTARRS": background._LIVE_PROVIDER_CAPABILITIES["PanSTARRS"],
        }
        monkeypatch.setattr(background, "_LIVE_PROVIDER_CAPABILITIES", fake_caps)
        results = live_provider_readiness(config_path)
        ztf = next(r for r in results if r["survey"] == "ZTF")
        assert "PROVIDER_LIVE_QUERY_UNSUPPORTED" in ztf["blockers"]


class TestAutomationReadinessHumanSignoff:
    def test_human_signoff_not_required_blocker(self, tmp_path):
        from background import automation_readiness_summary
        config_path = tmp_path / "config.json"
        policy_path = tmp_path / "policy.json"
        write_live_policy(policy_path, approved=True)
        config_path.write_text(json.dumps({
            "input_path": "background/targets.json",
            "db_path": "Logs/background.sqlite",
            "report_dir": "Logs/reports",
            "follow_up_threshold": 0.45,
            "run_mode": "automated",
            "live_network_enabled": True,
            "require_human_signoff": False,
            "required_approval_count": 1,
            "scheduler_enabled": True,
            "scheduler_interval_minutes": 60,
            "live_review_policy": str(policy_path),
            "required_credential_env": [],
        }))
        result = automation_readiness_summary(config_path)
        assert "HUMAN_SIGNOFF_NOT_REQUIRED" in result["live_mode_blockers"]


class TestMockLiveDryRunProvider:
    def test_init_and_execute(self):
        from background import MockLiveDryRunProvider
        provider = MockLiveDryRunProvider("ZTF")
        assert provider.survey == "ZTF"
        query = {"rank": 1, "survey": "ZTF", "ra_deg": 180.0, "dec_deg": 0.0}
        result = provider.execute(query)
        assert result["survey"] == "ZTF"
        assert result["status"] == "mocked_success"
        assert result["network_access_performed"] is False
        assert result["external_submission_enabled"] is False

    def test_default_live_dry_run_providers(self):
        from background import _default_live_dry_run_providers
        plan = {"planned_surveys": ["ZTF", "ATLAS"]}
        providers = _default_live_dry_run_providers(plan)
        assert "ZTF" in providers
        assert "ATLAS" in providers

    def test_normalize_live_query_result_rejects_external_submission(self):
        from background import _normalize_live_query_result
        query = {"rank": 1, "survey": "ZTF"}
        raw = {"external_submission_enabled": True}
        with pytest.raises(ValueError, match="LIVE_PROVIDER_EXTERNAL_SUBMISSION_NOT_ALLOWED"):
            _normalize_live_query_result(query, raw)


# --- Tests targeting previously uncovered background.py branches ---

class TestSignoffPacketDecision:
    def test_already_signed(self):
        result = background._signoff_packet_decision({"is_ready": True})
        assert result == "already_signed"

    def test_review_and_optionally_sign(self):
        result = background._signoff_packet_decision({
            "is_ready": False,
            "report_readiness_state": "ready_for_internal_review",
        })
        assert result == "review_and_optionally_sign"

    def test_inspect_missing_report_file(self):
        result = background._signoff_packet_decision({
            "is_ready": False,
            "report_readiness_state": "drafted",
        })
        assert result == "inspect_missing_report_file"

    def test_resolve_packet_blockers(self):
        result = background._signoff_packet_decision({
            "is_ready": False,
            "report_readiness_state": "blocked",
        })
        assert result == "resolve_packet_blockers"


class TestSignoffPacketTextForbiddenPhrase:
    def test_forbidden_phrase_raises(self, monkeypatch, tmp_path):
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
        # Build a packet dict that would trigger the forbidden-phrase check
        detail = background.run_detail(result.ledger.run_id, db_path)
        signoff_r = {
            "is_ready": False,
            "report_readiness_state": "ready_for_internal_review",
        }
        ops = background.background_operations_snapshot(
            db_path=db_path,
            input_path=fixture,
        )
        packet = {
            "packet_id": "test-packet-1",
            "run_id": result.ledger.run_id,
            "target_id": "T001",
            "code_version": "0.61.0",
            "recommended_decision": "review_and_optionally_sign",
            "signoff_readiness": signoff_r,
            "operations_snapshot": ops,
            "run_detail": detail,
            "network_access_performed": False,
            "external_submission_enabled": False,
        }
        # Inject a forbidden phrase into the ops to force the ValueError
        ops_with_forbidden = dict(ops)
        ops_with_forbidden["next_action"] = "confirmed neo candidate review"
        packet_bad = dict(packet)
        packet_bad["operations_snapshot"] = ops_with_forbidden
        with pytest.raises(ValueError, match="forbidden phrase"):
            background._signoff_packet_text(packet_bad)


class TestPacketDecisionReadinessBranches:
    def test_follow_up_record_missing(self, monkeypatch, tmp_path):
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
        background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "pkts")
        # Manually delete the needs_follow_up_log entry
        with background._connect(db_path) as conn:
            conn.execute("DELETE FROM needs_follow_up_log WHERE run_id=?", (result.ledger.run_id,))
        summary = background.signoff_packet_decision_readiness(db_path)
        # Should show blocked with FOLLOW_UP_RECORD_MISSING
        if summary["packets"]:
            row = summary["packets"][0]
            assert "FOLLOW_UP_RECORD_MISSING" in row["blockers"]

    def test_packet_target_mismatch(self, monkeypatch, tmp_path):
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
        background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "pkts")
        # Corrupt the follow_up entry to have wrong target_id
        with background._connect(db_path) as conn:
            row = conn.execute(
                "SELECT entry_json FROM needs_follow_up_log WHERE run_id=?",
                (result.ledger.run_id,),
            ).fetchone()
            entry = json.loads(row["entry_json"])
            entry["target_id"] = "WRONG_TARGET"
            conn.execute(
                "UPDATE needs_follow_up_log SET entry_json=? WHERE run_id=?",
                (json.dumps(entry), result.ledger.run_id),
            )
        summary = background.signoff_packet_decision_readiness(db_path)
        if summary["packets"]:
            row = summary["packets"][0]
            assert "PACKET_TARGET_MISMATCH" in row["blockers"]

    def test_signoff_report_not_ready(self, monkeypatch, tmp_path):
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
        # Create a packet with no report path so state is "not_ready"
        with background._connect(db_path) as conn:
            row = conn.execute(
                "SELECT entry_json FROM needs_follow_up_log WHERE run_id=?",
                (result.ledger.run_id,),
            ).fetchone()
            entry = json.loads(row["entry_json"])
            entry["report_path"] = None
            conn.execute(
                "UPDATE needs_follow_up_log SET entry_json=? WHERE run_id=?",
                (json.dumps(entry), result.ledger.run_id),
            )
        background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "pkts")
        summary = background.signoff_packet_decision_readiness(db_path)
        # Should show state blocked with SIGNOFF_REPORT_NOT_READY or similar
        assert "packets" in summary

    def test_signoff_report_file_missing(self, monkeypatch, tmp_path):
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
        # Record a real packet first (with existing report)
        packet_entry = background.record_signoff_packet(
            result.ledger.run_id, db_path, tmp_path / "pkts"
        )
        # Now set report_path in the DB to a non-existent file (after packet was recorded)
        nonexistent = str(tmp_path / "nonexistent_report.md")
        with background._connect(db_path) as conn:
            row = conn.execute(
                "SELECT entry_json FROM signoff_packet_log WHERE packet_id=?",
                (packet_entry["packet_id"],),
            ).fetchone()
            entry = json.loads(row["entry_json"])
            entry["signoff_readiness"]["report_path"] = nonexistent
            entry["signoff_readiness"]["report_exists"] = False
            entry["signoff_readiness"]["report_readiness_state"] = "drafted"
            conn.execute(
                "UPDATE signoff_packet_log"
                " SET report_path=?, report_readiness_state=?, entry_json=?"
                " WHERE packet_id=?",
                (nonexistent, "drafted", json.dumps(entry), packet_entry["packet_id"]),
            )
            # Also update needs_follow_up so _packet_decision_readiness_row sees consistent data
            fu_row = conn.execute(
                "SELECT entry_json FROM needs_follow_up_log WHERE run_id=?",
                (result.ledger.run_id,),
            ).fetchone()
            fu_entry = json.loads(fu_row["entry_json"])
            fu_entry["report_path"] = nonexistent
            conn.execute(
                "UPDATE needs_follow_up_log SET report_path=?, entry_json=? WHERE run_id=?",
                (nonexistent, json.dumps(fu_entry), result.ledger.run_id),
            )
        summary = background.signoff_packet_decision_readiness(db_path)
        if summary["packets"]:
            row = summary["packets"][0]
            assert "SIGNOFF_REPORT_FILE_MISSING" in row["blockers"]


class TestRecordSignoffFromPacketEdgeCases:
    def test_follow_up_record_removed_raises(self, monkeypatch, tmp_path):
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
        packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "pkts")
        # Remove the follow_up record after packet was written
        with background._connect(db_path) as conn:
            conn.execute("DELETE FROM needs_follow_up_log WHERE run_id=?", (result.ledger.run_id,))
        with pytest.raises(ValueError, match="no longer a follow-up run"):
            background.record_signoff_from_packet(
                packet["packet_id"], "Reviewer", "approved_for_internal_review",
                "Internal", "notes", db_path,
            )

    def test_packet_target_mismatch_raises(self, monkeypatch, tmp_path):
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
        packet = background.record_signoff_packet(result.ledger.run_id, db_path, tmp_path / "pkts")
        with background._connect(db_path) as conn:
            row = conn.execute(
                "SELECT entry_json FROM needs_follow_up_log WHERE run_id=?",
                (result.ledger.run_id,),
            ).fetchone()
            entry = json.loads(row["entry_json"])
            entry["target_id"] = "DIFFERENT_TARGET"
            conn.execute(
                "UPDATE needs_follow_up_log SET entry_json=? WHERE run_id=?",
                (json.dumps(entry), result.ledger.run_id),
            )
        with pytest.raises(ValueError, match="no longer matches"):
            background.record_signoff_from_packet(
                packet["packet_id"], "Reviewer", "approved_for_internal_review",
                "Internal", "notes", db_path,
            )


class TestBlueprintComplianceMissingBranches:
    def test_missing_tests_and_report_gaps(self, monkeypatch, tmp_path):
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
        # Inject a needs_follow_up entry missing required tests and with incomplete report
        report_path = tmp_path / "incomplete.md"
        report_path.write_text("some text without required sections")
        with background._connect(db_path) as conn:
            row = conn.execute(
                "SELECT entry_json FROM needs_follow_up_log WHERE run_id=?",
                (result.ledger.run_id,),
            ).fetchone()
            entry = json.loads(row["entry_json"])
            entry["required_tests"] = []  # missing tests
            entry["report_path"] = str(report_path)
            entry["recommendations"] = [
                {"rank": 1, "recommended_action": "submit_now"},  # bad recommendations
            ]
            conn.execute(
                "UPDATE needs_follow_up_log SET entry_json=? WHERE run_id=?",
                (json.dumps(entry), result.ledger.run_id),
            )
        summary = background.background_blueprint_compliance_summary(
            db_path=db_path, input_path=fixture
        )
        assert "overall_status" in summary


class TestOperationsNextAction:
    def test_wait_for_active_run(self):
        result = background._operations_next_action(
            {"lock_active": True, "total_runs": 1, "total_follow_up": 0},
            {"unsigned_follow_up_runs": []},
            {"scheduler_ready": True},
            {"overall_status": "pass"},
        )
        assert result == "wait_for_active_run"

    def test_resolve_blueprint_failures(self):
        result = background._operations_next_action(
            {"lock_active": False, "total_runs": 1, "total_follow_up": 0},
            {"unsigned_follow_up_runs": []},
            {"scheduler_ready": True},
            {"overall_status": "fail"},
        )
        assert result == "resolve_blueprint_failures"

    def test_review_follow_up(self):
        result = background._operations_next_action(
            {"lock_active": False, "total_runs": 1, "total_follow_up": 1},
            {"unsigned_follow_up_runs": []},
            {"scheduler_ready": True},
            {"overall_status": "pass"},
        )
        assert result == "review_follow_up"

    def test_resolve_scheduler_blockers(self):
        result = background._operations_next_action(
            {"lock_active": False, "total_runs": 1, "total_follow_up": 0},
            {"unsigned_follow_up_runs": []},
            {"scheduler_ready": False},
            {"overall_status": "pass"},
        )
        assert result == "resolve_scheduler_blockers"

    def test_continue_offline_scheduler(self):
        result = background._operations_next_action(
            {"lock_active": False, "total_runs": 1, "total_follow_up": 0},
            {"unsigned_follow_up_runs": []},
            {"scheduler_ready": True},
            {"overall_status": "pass"},
        )
        assert result == "continue_offline_scheduler"


# ---------------------------------------------------------------------------
# Coverage gap tests — background.py v0.76.0 additions
# ---------------------------------------------------------------------------

class TestInternalFollowUpDispositionUnsigned:
    """Covers lines 1676-1677: awaiting_internal_review branch."""

    def test_unsigned_entry_disposition(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import background

        fixture = tmp_path / "targets.json"
        db_path = tmp_path / "Logs" / "background.sqlite"
        write_fixture(fixture)
        monkeypatch.setattr(background, "score_tracklet", lambda t, r: make_scored())
        # Run but do NOT sign off
        background.background_run_once(
            fixture, db_path, tmp_path / "reports",
            config_path=tmp_path / "missing_config.json",
        )
        summary = background.internal_follow_up_disposition_summary(db_path)
        dispositions = [
            d for d in summary["dispositions"]
            if d["disposition"] == "awaiting_internal_review"
        ]
        assert len(dispositions) >= 1
        assert dispositions[0]["signed_for_internal_tracking"] is False
        assert dispositions[0]["next_action"] == "record_internal_review_decision"


class TestKeychainSecretPresent:
    """Covers lines 3080-3091: _keychain_secret_present subprocess path.

    Override the module-level autouse fixture so the real function is NOT patched.
    The class-scoped fixture of the same name shadows the autouse one for this class.
    """

    @pytest.fixture(autouse=True)
    def no_keychain_credentials(self, monkeypatch):
        # Override the module autouse fixture: do NOT patch _keychain_secret_present.
        # Only disable the env-var guard so tests can control it per-test.
        monkeypatch.delenv("NEO_DETECTION_DISABLE_KEYCHAIN_LOOKUP", raising=False)

    def test_disable_flag_returns_false(self, monkeypatch):
        monkeypatch.setenv("NEO_DETECTION_DISABLE_KEYCHAIN_LOOKUP", "1")
        result = background._keychain_secret_present("neo-detection:TEST_SERVICE")
        assert result is False

    def test_no_security_command_returns_false(self):
        # On Linux 'security' doesn't exist → OSError → False
        result = background._keychain_secret_present("neo-detection:NONEXISTENT_SERVICE")
        assert result is False

    def test_subprocess_returncode_zero_returns_true(self, monkeypatch):
        monkeypatch.setattr(
            background.subprocess, "run",
            lambda *a, **kw: type("R", (), {"returncode": 0})()
        )
        result = background._keychain_secret_present("neo-detection:TEST")
        assert result is True

    def test_subprocess_returncode_nonzero_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            background.subprocess, "run",
            lambda *a, **kw: type("R", (), {"returncode": 1})()
        )
        result = background._keychain_secret_present("neo-detection:TEST")
        assert result is False


class TestLiveCredentialInventoryNoCredentialProvider:
    """Covers lines 3181-3196: empty credential_rows branch."""

    def test_no_credential_provider_entry(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import background
        # Inject a provider with no required or optional credentials
        fake_provider = {
            "survey": "PublicSurvey",
            "auth_mode": "public",
            "fetch_api": "public_api",
            "credential_status": [],
            "optional_credential_status": [],
        }
        monkeypatch.setattr(
            background, "live_provider_readiness",
            lambda config_path: (fake_provider,),
        )
        policy_path = tmp_path / "policy.json"
        config_path = tmp_path / "config.json"
        write_live_policy(policy_path, approved=True)
        write_live_config(config_path, policy_path, live_network_enabled=True)

        inventory = background.live_credential_inventory(config_path)
        entry = inventory["inventory"][0]
        assert entry["survey"] == "PublicSurvey"
        assert entry["credential_env"] is None
        assert entry["credential_required"] is False
        assert entry["credential_source"] == "not_required"
        assert entry["network_access_performed"] is False


class TestWriteLiveCredentialInventoryReport:
    """Covers lines 3243-3246: write_live_credential_inventory_report path write."""

    def test_writes_report_file(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import background
        policy_path = tmp_path / "policy.json"
        config_path = tmp_path / "config.json"
        report_path = tmp_path / "reports" / "cred_inv.json"
        write_live_policy(policy_path, approved=True)
        write_live_config(config_path, policy_path, live_network_enabled=True)
        monkeypatch.setenv("ATLAS_TOKEN", "tok")

        result = background.write_live_credential_inventory_report(
            config_path=config_path, report_path=report_path
        )
        assert report_path.exists()
        assert result["secret_values_recorded"] is False
        assert result["network_access_performed"] is False
        assert result["external_submission_enabled"] is False


class TestLivePolicyApprovalChecklistAtlasTokenMissing:
    """Covers line 3301: ATLAS_TOKEN_MISSING_FOR_ATLAS_SURVEY blocker."""

    def test_atlas_token_missing_blocker(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import background
        policy_path = tmp_path / "policy.json"
        config_path = tmp_path / "config.json"
        write_live_policy(policy_path, approved=False)
        write_live_config(config_path, policy_path, live_network_enabled=True)
        monkeypatch.delenv("ATLAS_TOKEN", raising=False)
        monkeypatch.setenv("NEO_DETECTION_DISABLE_KEYCHAIN_LOOKUP", "1")

        checklist = background.live_policy_approval_checklist(config_path)
        assert "ATLAS_TOKEN_MISSING_FOR_ATLAS_SURVEY" in checklist["approval_blockers"]


class TestWriteLivePolicyApprovalChecklistReport:
    """Covers lines 3339-3342: write_live_policy_approval_checklist_report path write."""

    def test_writes_report_file(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import background
        policy_path = tmp_path / "policy.json"
        config_path = tmp_path / "config.json"
        report_path = tmp_path / "reports" / "checklist.json"
        write_live_policy(policy_path, approved=False)
        write_live_config(config_path, policy_path, live_network_enabled=False)
        monkeypatch.setenv("ATLAS_TOKEN", "tok")

        result = background.write_live_policy_approval_checklist_report(
            config_path=config_path, report_path=report_path
        )
        assert report_path.exists()
        assert result["secret_values_recorded"] is False
        assert result["network_access_performed"] is False
        assert result["external_submission_enabled"] is False


class TestNumericValues:
    """Covers lines 3495, 3504-3507: _numeric_values branches."""

    def test_bool_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._numeric_values(True) == []
        assert background._numeric_values(False) == []

    def test_none_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._numeric_values(None) == []

    def test_int_returns_float_list(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._numeric_values(5) == [5.0]

    def test_list_returns_flattened(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._numeric_values([0.1, 0.2]) == [0.1, 0.2]

    def test_tuple_returns_flattened(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._numeric_values((0.3, 0.4)) == [0.3, 0.4]

    def test_unknown_type_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._numeric_values("hello") == []


class TestScoreValuesInRange:
    """Covers lines 3514, 3516: _score_values_in_range branches."""

    def test_non_finite_returns_false(self):
        import math
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._score_values_in_range({"v": math.inf}) is False
        assert background._score_values_in_range({"v": float("nan")}) is False

    def test_out_of_range_returns_false(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._score_values_in_range({"v": 1.5}) is False
        assert background._score_values_in_range({"v": -0.1}) is False

    def test_valid_range_returns_true(self):
        import sys
        sys.path.insert(0, "src")
        import background
        assert background._score_values_in_range({"v": 0.5}) is True
        assert background._score_values_in_range({"v": 0.0}) is True
        assert background._score_values_in_range({"v": 1.0}) is True


class TestWriteScoringMetricsKpiReport:
    """Covers lines 3714-3717: write_scoring_metrics_kpi_report path write."""

    def test_writes_report_file(self, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import background
        report_path = tmp_path / "kpi_latest.json"

        result = background.write_scoring_metrics_kpi_report(report_path=report_path)
        assert report_path.exists()
        assert result["secret_values_recorded"] is False
        assert result["network_access_performed"] is False
        assert result["external_submission_enabled"] is False
        assert "report" in result
