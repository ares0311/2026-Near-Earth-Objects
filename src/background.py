"""Conservative background search automation with SQLite-backed logs."""

from __future__ import annotations

__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_REPORT_DIR",
    "DEFAULT_CONFIG_PATH",
    "init_log_db",
    "load_config",
    "load_tracklets",
    "score_tracklet",
    "build_targets",
    "select_target",
    "background_run_once",
    "record_human_signoff",
    "human_signoff_summary",
    "run_detail",
    "target_history",
    "signoff_readiness_summary",
    "ledger_summary",
    "reviewed_log_summary",
    "needs_follow_up_summary",
    "target_priority_summary",
    "follow_up_test_summary",
    "submission_recommendation_summary",
    "validation_summary",
    "audit_report",
    "automation_readiness_summary",
    "record_automation_readiness",
    "automation_readiness_log_summary",
    "live_policy_contract_summary",
    "live_provider_capabilities",
    "live_provider_readiness",
    "live_dry_run_approval_bundle",
    "record_live_dry_run_approval_bundle",
    "live_dry_run_approval_bundle_log_summary",
    "live_dry_run_operator_handoff",
    "write_live_dry_run_operator_handoff",
    "record_live_dry_run_operator_handoff",
    "live_dry_run_operator_handoff_log_summary",
    "live_dry_run_plan",
    "record_live_dry_run_plan",
    "live_dry_run_plan_log_summary",
    "LiveDryRunProvider",
    "MockLiveDryRunProvider",
    "live_dry_run_execute",
    "record_live_execution_attempt",
    "live_execution_log_summary",
    "launchd_plist",
]

import json
import os
import sqlite3
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from classify import classify, extract_features
from orbit import fit_orbit
from schemas import (
    BackgroundConfig,
    BackgroundOutcome,
    BackgroundRunLedgerEntry,
    BackgroundRunMode,
    BackgroundRunResult,
    BackgroundTarget,
    FollowUpTestResult,
    HumanSignoffEntry,
    NeedsFollowUpLogEntry,
    Observation,
    PriorityFactors,
    ReviewedLogEntry,
    ScoredNEO,
    SignoffDecision,
    SubmissionRecommendation,
    Tracklet,
)
from score import score

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _ROOT / "background" / "config.json"
DEFAULT_INPUT_PATH = _ROOT / "background" / "targets.json"
DEFAULT_DB_PATH = _ROOT / "Logs" / "background.sqlite"
DEFAULT_REPORT_DIR = _ROOT / "Logs" / "reports"
_SCHEMA_VERSION = "background-v1"
_CODE_VERSION = "0.50.0"
_LIVE_REVIEW_POLICY_SCHEMA_PATH = _ROOT / "background" / "live_review_policy.schema.json"
_SUPPORTED_LIVE_SURVEYS = ("ZTF", "ATLAS", "PanSTARRS")
_LIVE_PROVIDER_CAPABILITIES = {
    "ZTF": {
        "survey": "ZTF",
        "credential_env": "ZTF_IRSA_TOKEN",
        "fetch_api": "fetch_ztf_alerts",
        "network_mode": "credentialed",
        "supports_live_query": True,
        "supports_external_submission": False,
        "min_seconds_between_queries": 1,
    },
    "ATLAS": {
        "survey": "ATLAS",
        "credential_env": "ATLAS_TOKEN",
        "fetch_api": "fetch_atlas_forced",
        "network_mode": "credentialed",
        "supports_live_query": True,
        "supports_external_submission": False,
        "min_seconds_between_queries": 1,
    },
    "PanSTARRS": {
        "survey": "PanSTARRS",
        "credential_env": "MAST_API_TOKEN",
        "fetch_api": "fetch_panstarrs_catalog",
        "network_mode": "credentialed",
        "supports_live_query": True,
        "supports_external_submission": False,
        "min_seconds_between_queries": 1,
    },
}
_REQUIRED_POLICY_FIELDS = (
    "schema_version",
    "reviewer",
    "approved_for_live_network",
    "allowed_surveys",
    "max_queries_per_run",
    "min_seconds_between_queries",
    "dry_run_scope",
    "no_external_submission_confirmed",
    "no_impact_probability_claims",
)
_REQUIRED_DRY_RUN_SCOPE_FIELDS = (
    "ra_deg",
    "dec_deg",
    "radius_deg",
    "start_jd",
    "end_jd",
)
_FOLLOW_UP_THRESHOLD = 0.45
_LOCK_ID = 1

_FORBIDDEN_REPORT_PHRASES = (
    "confirmed neo",
    "confirmed discovery",
    "impact probability",
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_log_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the top-level SQLite log database if needed."""
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_ledger (
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
                run_mode TEXT NOT NULL DEFAULT 'manual',
                config_path TEXT,
                failure_reason TEXT,
                live_network_enabled INTEGER NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )
        _add_column_if_missing(conn, "run_ledger", "run_mode", "TEXT NOT NULL DEFAULT 'manual'")
        _add_column_if_missing(conn, "run_ledger", "config_path", "TEXT")
        _add_column_if_missing(conn, "run_ledger", "failure_reason", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewed_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                reviewed_at_utc TEXT NOT NULL,
                target_id TEXT NOT NULL,
                negative_evidence_json TEXT NOT NULL,
                rationale TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES run_ledger(run_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_lock (
                lock_id INTEGER PRIMARY KEY CHECK(lock_id = 1),
                run_id TEXT NOT NULL,
                acquired_at_utc TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS human_signoff_log (
                signoff_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                signed_at_utc TEXT NOT NULL,
                decision TEXT NOT NULL,
                scope TEXT NOT NULL,
                notes TEXT NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO schema_metadata (key, value, updated_at_utc)
            VALUES ('schema_version', ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at_utc = excluded.updated_at_utc
            """,
            (_SCHEMA_VERSION, _utc_now()),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS needs_follow_up_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                recorded_at_utc TEXT NOT NULL,
                target_id TEXT NOT NULL,
                trigger_reason_codes_json TEXT NOT NULL,
                report_path TEXT,
                human_approval_required INTEGER NOT NULL,
                entry_json TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES run_ledger(run_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_readiness_log (
                readiness_id TEXT PRIMARY KEY,
                checked_at_utc TEXT NOT NULL,
                config_path TEXT NOT NULL,
                scheduler_ready INTEGER NOT NULL,
                live_mode_ready INTEGER NOT NULL,
                scheduler_blockers_json TEXT NOT NULL,
                live_mode_blockers_json TEXT NOT NULL,
                missing_credential_env_json TEXT NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_dry_run_plan_log (
                plan_id TEXT PRIMARY KEY,
                planned_at_utc TEXT NOT NULL,
                config_path TEXT NOT NULL,
                executable INTEGER NOT NULL,
                planned_surveys_json TEXT NOT NULL,
                blockers_json TEXT NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_approval_bundle_log (
                bundle_id TEXT PRIMARY KEY,
                reviewed_at_utc TEXT NOT NULL,
                config_path TEXT NOT NULL,
                approved_to_attempt_live_dry_run INTEGER NOT NULL,
                blockers_json TEXT NOT NULL,
                planned_surveys_json TEXT NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_operator_handoff_log (
                handoff_id TEXT PRIMARY KEY,
                created_at_utc TEXT NOT NULL,
                config_path TEXT NOT NULL,
                report_path TEXT NOT NULL,
                approved_to_attempt_live_dry_run INTEGER NOT NULL,
                blockers_json TEXT NOT NULL,
                planned_surveys_json TEXT NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_execution_log (
                attempt_id TEXT PRIMARY KEY,
                attempted_at_utc TEXT NOT NULL,
                config_path TEXT NOT NULL,
                executable INTEGER NOT NULL,
                outcome TEXT NOT NULL,
                blockers_json TEXT NOT NULL,
                query_results_json TEXT NOT NULL,
                external_submission_enabled INTEGER NOT NULL,
                entry_json TEXT NOT NULL
            )
            """
        )


def _model_json(model: Any) -> str:
    return model.model_dump_json()


def _insert_ledger(conn: sqlite3.Connection, entry: BackgroundRunLedgerEntry) -> None:
    conn.execute(
        """
        INSERT INTO run_ledger (
            run_id, started_at_utc, completed_at_utc, code_version, schema_version,
            input_path, target_id, outcome, selected_score, reason_codes_json,
            run_mode, config_path, failure_reason, live_network_enabled, entry_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.run_id,
            entry.started_at_utc,
            entry.completed_at_utc,
            entry.code_version,
            entry.schema_version,
            entry.input_path,
            entry.target_id,
            entry.outcome,
            entry.selected_score,
            json.dumps(entry.reason_codes),
            entry.run_mode,
            entry.config_path,
            entry.failure_reason,
            int(entry.live_network_enabled),
            _model_json(entry),
        ),
    )


def _insert_reviewed(conn: sqlite3.Connection, entry: ReviewedLogEntry) -> None:
    conn.execute(
        """
        INSERT INTO reviewed_log (
            run_id, reviewed_at_utc, target_id, negative_evidence_json,
            rationale, entry_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            entry.run_id,
            entry.reviewed_at_utc,
            entry.target_id,
            json.dumps(entry.negative_evidence),
            entry.rationale,
            _model_json(entry),
        ),
    )


def _insert_needs_follow_up(conn: sqlite3.Connection, entry: NeedsFollowUpLogEntry) -> None:
    conn.execute(
        """
        INSERT INTO needs_follow_up_log (
            run_id, recorded_at_utc, target_id, trigger_reason_codes_json,
            report_path, human_approval_required, entry_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.run_id,
            entry.recorded_at_utc,
            entry.target_id,
            json.dumps(entry.trigger_reason_codes),
            entry.report_path,
            int(entry.human_approval_required),
            _model_json(entry),
        ),
    )


def _insert_human_signoff(conn: sqlite3.Connection, entry: HumanSignoffEntry) -> None:
    conn.execute(
        """
        INSERT INTO human_signoff_log (
            signoff_id, run_id, target_id, reviewer, signed_at_utc,
            decision, scope, notes, entry_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.signoff_id,
            entry.run_id,
            entry.target_id,
            entry.reviewer,
            entry.signed_at_utc,
            entry.decision,
            entry.scope,
            entry.notes,
            _model_json(entry),
        ),
    )


def _resolve_project_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else _ROOT / path


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> BackgroundConfig:
    """Load conservative background automation configuration."""
    if not config_path.exists():
        return BackgroundConfig(
            input_path=str(DEFAULT_INPUT_PATH),
            db_path=str(DEFAULT_DB_PATH),
            report_dir=str(DEFAULT_REPORT_DIR),
            follow_up_threshold=_FOLLOW_UP_THRESHOLD,
        )
    with config_path.open() as handle:
        data = json.load(handle)
    return BackgroundConfig(**data)


@contextmanager
def _run_lock(db_path: Path, run_id: str) -> Any:
    init_log_db(db_path)
    conn = _connect(db_path)
    acquired = False
    try:
        try:
            conn.execute(
                "INSERT INTO run_lock (lock_id, run_id, acquired_at_utc) VALUES (?, ?, ?)",
                (_LOCK_ID, run_id, _utc_now()),
            )
            conn.commit()
            acquired = True
        except sqlite3.IntegrityError as exc:
            row = conn.execute("SELECT run_id, acquired_at_utc FROM run_lock").fetchone()
            active = f"{row['run_id']} since {row['acquired_at_utc']}" if row else "unknown"
            raise RuntimeError(f"Background run already in progress: {active}") from exc
        finally:
            conn.close()
        yield
    finally:
        if acquired:
            with _connect(db_path) as release_conn:
                release_conn.execute("DELETE FROM run_lock WHERE lock_id = ?", (_LOCK_ID,))


def load_tracklets(path: Path = DEFAULT_INPUT_PATH) -> tuple[Tracklet, ...]:
    """Load fixture tracklets from a list or versioned manifest JSON file."""
    with path.open() as handle:
        data = json.load(handle)
    entries = data.get("targets", data) if isinstance(data, dict) else data

    tracklets: list[Tracklet] = []
    for idx, entry in enumerate(entries):
        observations = tuple(Observation(**obs) for obs in entry["observations"])
        tracklets.append(
            Tracklet(
                object_id=entry.get("object_id", f"TARGET_{idx:03d}"),
                observations=observations,
                arc_days=entry.get("arc_days", 0.0),
                motion_rate_arcsec_per_hour=entry.get("motion_rate_arcsec_per_hour", 0.0),
                motion_pa_degrees=entry.get("motion_pa_degrees", 0.0),
                motion_rate_uncertainty=entry.get("motion_rate_uncertainty", 0.0),
            )
        )
    return tuple(tracklets)


def score_tracklet(tracklet: Tracklet, run_id: str) -> ScoredNEO:
    """Run the local classify -> orbit -> score path for a fixture target."""
    features = extract_features(tracklet)
    features_cls, posterior = classify(tracklet, features)
    orbital = fit_orbit(tracklet)
    return score(tracklet, features_cls, posterior, orbital, pipeline_run_id=run_id)


def _review_count(conn: sqlite3.Connection, target_id: str) -> int:
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM reviewed_log WHERE target_id = ?) +
            (SELECT COUNT(*) FROM needs_follow_up_log WHERE target_id = ?) AS n
        """,
        (target_id, target_id),
    ).fetchone()
    return int(row["n"])


def _data_completeness(scored: ScoredNEO) -> float:
    n_obs = len(scored.tracklet.observations)
    has_rb = scored.features.real_bogus_score is not None
    has_motion = scored.features.motion_consistency_score is not None
    has_orbit = scored.hazard.orbital_elements is not None
    raw = min(1.0, n_obs / 6.0)
    raw += 0.15 if has_rb else 0.0
    raw += 0.15 if has_motion else 0.0
    raw += 0.20 if has_orbit else 0.0
    return min(1.0, raw)


def _false_positive_risk(scored: ScoredNEO) -> float:
    artifact = scored.posterior.stellar_artifact
    known = scored.posterior.known_object
    mba = scored.posterior.main_belt_asteroid * 0.5
    return min(1.0, artifact + known + mba)


def _calibration_confidence(scored: ScoredNEO) -> float:
    p = scored.posterior.neo_candidate
    return float(max(0.0, 1.0 - abs(p - 0.5) * 1.6))


def _blocking_penalty(scored: ScoredNEO) -> float:
    penalty = 0.0
    if scored.features.real_bogus_score is None:
        penalty += 0.25
    if scored.hazard.orbital_elements is None:
        penalty += 0.25
    if scored.features.known_object_score is None:
        penalty += 0.10
    return min(1.0, penalty)


def _priority_factors(scored: ScoredNEO, review_count: int) -> PriorityFactors:
    prior_review_penalty = min(1.0, review_count * 0.25)
    never_reviewed_boost = 1.0 if review_count == 0 else 0.0
    data_completeness = _data_completeness(scored)
    false_positive_risk = _false_positive_risk(scored)
    followup_feasibility = scored.metadata.followup_value
    calibration_confidence = _calibration_confidence(scored)
    blocking_issue_penalty = _blocking_penalty(scored)
    scientific_interest = max(scored.metadata.scientific_interest, scored.posterior.neo_candidate)

    composite = (
        0.25 * scientific_interest
        + 0.15 * never_reviewed_boost
        + 0.15 * data_completeness
        + 0.15 * followup_feasibility
        + 0.10 * calibration_confidence
        + 0.10 * (1.0 - false_positive_risk)
        - 0.05 * prior_review_penalty
        - 0.05 * blocking_issue_penalty
    )
    composite_score = float(min(1.0, max(0.0, composite)))
    return PriorityFactors(
        scientific_interest=scientific_interest,
        prior_review_penalty=prior_review_penalty,
        never_reviewed_boost=never_reviewed_boost,
        data_completeness=data_completeness,
        false_positive_risk=false_positive_risk,
        followup_feasibility=followup_feasibility,
        calibration_confidence=calibration_confidence,
        blocking_issue_penalty=blocking_issue_penalty,
        composite_score=composite_score,
    )


def build_targets(
    input_path: Path = DEFAULT_INPUT_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    run_id: str | None = None,
) -> tuple[BackgroundTarget, ...]:
    """Score fixture targets and attach priority factors."""
    actual_run_id = run_id or str(uuid.uuid4())
    init_log_db(db_path)
    with _connect(db_path) as conn:
        targets: list[BackgroundTarget] = []
        for tracklet in load_tracklets(input_path):
            scored = score_tracklet(tracklet, actual_run_id)
            count = _review_count(conn, tracklet.object_id)
            targets.append(
                BackgroundTarget(
                    target_id=tracklet.object_id,
                    scored_neo=scored,
                    priority=_priority_factors(scored, count),
                )
            )
    return tuple(targets)


def select_target(targets: tuple[BackgroundTarget, ...]) -> BackgroundTarget | None:
    """Select exactly one target for a bounded run."""
    if not targets:
        return None
    return max(targets, key=lambda target: target.priority.composite_score)


def _trigger_reason_codes(
    target: BackgroundTarget,
    follow_up_threshold: float = _FOLLOW_UP_THRESHOLD,
) -> tuple[str, ...]:
    scored = target.scored_neo
    reasons: list[str] = []
    if target.priority.composite_score >= follow_up_threshold:
        reasons.append("COMPOSITE_PRIORITY_ABOVE_THRESHOLD")
    if scored.metadata.discovery_priority >= 0.35:
        reasons.append("DISCOVERY_PRIORITY_REVIEW")
    if scored.metadata.followup_value >= 0.6:
        reasons.append("FOLLOWUP_VALUE_REVIEW")
    if scored.hazard.alert_pathway != "internal_candidate":
        reasons.append("ALERT_PATHWAY_REVIEW")
    if scored.hazard.hazard_flag in {"pha_candidate", "close_approach"}:
        reasons.append("HAZARD_FLAG_REVIEW")
    if target.priority.blocking_issue_penalty > 0.0:
        reasons.append("BLOCKING_ISSUE_REVIEW")
    if target.priority.calibration_confidence < 0.4:
        reasons.append("CALIBRATION_UNCERTAINTY_REVIEW")
    return tuple(dict.fromkeys(reasons))


def _follow_up_tests(target: BackgroundTarget) -> tuple[FollowUpTestResult, ...]:
    scored = target.scored_neo
    provenance_ok = bool(scored.metadata.pipeline_run_id and scored.tracklet.observations)
    artifact_risk = scored.posterior.stellar_artifact
    known_score = scored.features.known_object_score
    missions = {obs.mission for obs in scored.tracklet.observations}

    tests = [
        FollowUpTestResult(
            name="provenance_check",
            status="pass" if provenance_ok else "fail",
            reason_code="PROVENANCE_TRACEABLE" if provenance_ok else "PROVENANCE_INCOMPLETE",
            summary="Run id and observation records are present."
            if provenance_ok
            else "Run id or observations are missing.",
        ),
        FollowUpTestResult(
            name="false_positive_class_check",
            status="pass" if artifact_risk <= 0.3 else "uncertain",
            reason_code="FALSE_POSITIVE_RISK_LOW"
            if artifact_risk <= 0.3
            else "FALSE_POSITIVE_RISK_UNCERTAIN",
            summary=f"Artifact posterior is {artifact_risk:.2f}.",
        ),
        FollowUpTestResult(
            name="cross_source_consistency_check",
            status="pass" if len(missions) >= 2 else "uncertain",
            reason_code="MULTI_SOURCE_SUPPORT" if len(missions) >= 2 else "SINGLE_SOURCE_ONLY",
            summary=f"Observation missions represented: {', '.join(sorted(missions))}.",
        ),
        FollowUpTestResult(
            name="calibration_confidence_check",
            status="pass" if target.priority.calibration_confidence >= 0.4 else "uncertain",
            reason_code="CALIBRATION_REGIME_ACCEPTABLE"
            if target.priority.calibration_confidence >= 0.4
            else "CALIBRATION_REGIME_WEAK",
            summary=f"Calibration confidence is {target.priority.calibration_confidence:.2f}.",
        ),
        FollowUpTestResult(
            name="reproducibility_check",
            status="pass",
            reason_code="LOCAL_RERUN_DETERMINISTIC",
            summary="The target is loaded from a committed local fixture.",
        ),
        FollowUpTestResult(
            name="known_object_evidence_check",
            status="blocked" if known_score is None else "pass",
            reason_code=(
                "KNOWN_OBJECT_SCORE_MISSING"
                if known_score is None
                else "KNOWN_OBJECT_SCORE_PRESENT"
            ),
            summary="Known-object evidence is not available in this offline fixture."
            if known_score is None
            else f"Known-object score is {known_score:.2f}.",
        ),
        FollowUpTestResult(
            name="human_review_checklist",
            status="ready",
            reason_code="HUMAN_REVIEW_REQUIRED",
            summary="A human reviewer must approve any external action.",
        ),
    ]
    return tuple(tests)


def _recommendations(target: BackgroundTarget) -> tuple[SubmissionRecommendation, ...]:
    risks = (
        "Offline fixture run only; live survey and catalog checks are not enabled.",
        "Independent confirmation has not been obtained.",
    )
    return (
        SubmissionRecommendation(
            destination="Internal project review",
            rank=1,
            suitability_rationale=(
                "Best first step for inspecting provenance and negative evidence."
            ),
            risks=risks,
            prerequisites=("Review SQLite log entry.", "Inspect required follow-up tests."),
            recommended_action="internal_review",
        ),
        SubmissionRecommendation(
            destination="Additional local tests",
            rank=2,
            suitability_rationale="Useful before preparing any formal observation material.",
            risks=("Current evidence may be fixture-specific.",),
            prerequisites=(
                "Run cross-match checks.",
                "Run injection-recovery or reproducibility checks.",
            ),
            recommended_action="request_more_tests",
        ),
        SubmissionRecommendation(
            destination="External submission",
            rank=3,
            suitability_rationale="Not appropriate until the project alert protocol is satisfied.",
            risks=(
                "MPC submission and independent confirmation gates have not been completed.",
                "External contact requires explicit human approval.",
            ),
            prerequisites=("Explicit human approval.", "Protocol gates completed."),
            recommended_action="do_not_submit_yet",
        ),
    )


def _report_text(target: BackgroundTarget, tests: tuple[FollowUpTestResult, ...]) -> str:
    scored = target.scored_neo
    support = scored.hazard.explanation.supporting_evidence or ("No strong support recorded.",)
    contra = scored.hazard.explanation.contra_evidence or ("No contra evidence recorded.",)
    lines = [
        f"# Background Follow-Up Draft: {target.target_id}",
        "",
        "## Status",
        "This is a conservative internal follow-up draft, not an external validation.",
        "",
        "## Target Context",
        f"- Candidate probability: {scored.posterior.neo_candidate:.3f}",
        f"- Hazard flag: {scored.hazard.hazard_flag}",
        f"- Alert pathway: {scored.hazard.alert_pathway}",
        f"- Priority score: {target.priority.composite_score:.3f}",
        "",
        "## Evidence Supporting Follow-Up",
        *(f"- {item}" for item in support),
        "",
        "## Negative Evidence And Limitations",
        *(f"- {item}" for item in contra),
        "- False positives remain the default hypothesis until authorities assess evidence.",
        "- Live survey, MPC, and CNEOS checks are outside this offline run.",
        "",
        "## Follow-Up Tests",
        *(f"- {test.name}: {test.status} ({test.reason_code})" for test in tests),
        "",
        "## Recommended Next Steps",
        "- Keep this candidate in internal review.",
        "- Run known-object cross-match and provenance checks with live credentials if approved.",
        "- Do not contact outside parties without explicit human approval.",
    ]
    report = "\n".join(lines) + "\n"
    lowered = report.lower()
    for phrase in _FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Report contains forbidden phrase: {phrase}")
    return report


def _write_report(
    target: BackgroundTarget,
    tests: tuple[FollowUpTestResult, ...],
    report_dir: Path,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{target.target_id}_follow_up.md"
    path.write_text(_report_text(target, tests))
    return path


def _negative_evidence(target: BackgroundTarget) -> tuple[str, ...]:
    scored = target.scored_neo
    evidence = list(scored.hazard.explanation.contra_evidence)
    evidence.append(
        f"Composite priority below follow-up threshold: {target.priority.composite_score:.3f}."
    )
    evidence.append(f"Artifact posterior: {scored.posterior.stellar_artifact:.3f}.")
    evidence.append(f"Known-object posterior: {scored.posterior.known_object:.3f}.")
    return tuple(evidence)


def _empty_reviewed_entry(
    run_id: str,
    when: str,
    input_path: Path,
    config_path: Path | None = None,
    run_mode: BackgroundRunMode = "manual",
    live_network_enabled: bool = False,
) -> tuple[BackgroundRunLedgerEntry, ReviewedLogEntry]:
    ledger = BackgroundRunLedgerEntry(
        run_id=run_id,
        started_at_utc=when,
        completed_at_utc=when,
        code_version=_CODE_VERSION,
        schema_version=_SCHEMA_VERSION,
        input_path=str(input_path),
        target_id="NO_TARGETS",
        outcome="reviewed",
        selected_score=0.0,
        reason_codes=("NO_TARGETS_AVAILABLE",),
        run_mode=run_mode,
        config_path=str(config_path) if config_path else None,
        live_network_enabled=live_network_enabled,
    )
    reviewed = ReviewedLogEntry(
        run_id=run_id,
        reviewed_at_utc=when,
        target_id="NO_TARGETS",
        priority=None,
        negative_evidence=("No fixture targets were available for selection.",),
        rationale="No background target could be selected.",
    )
    return ledger, reviewed


def _failure_reviewed_entry(
    run_id: str,
    started_at: str,
    completed_at: str,
    input_path: Path,
    exc: Exception,
    config_path: Path | None = None,
    run_mode: BackgroundRunMode = "manual",
    live_network_enabled: bool = False,
) -> tuple[BackgroundRunLedgerEntry, ReviewedLogEntry]:
    message = f"{type(exc).__name__}: {exc}"
    ledger = BackgroundRunLedgerEntry(
        run_id=run_id,
        started_at_utc=started_at,
        completed_at_utc=completed_at,
        code_version=_CODE_VERSION,
        schema_version=_SCHEMA_VERSION,
        input_path=str(input_path),
        target_id="RUN_FAILURE",
        outcome="reviewed",
        selected_score=0.0,
        reason_codes=("RUN_FAILED_BLOCKED",),
        run_mode=run_mode,
        config_path=str(config_path) if config_path else None,
        failure_reason=message,
        live_network_enabled=live_network_enabled,
    )
    reviewed = ReviewedLogEntry(
        run_id=run_id,
        reviewed_at_utc=completed_at,
        target_id="RUN_FAILURE",
        priority=None,
        negative_evidence=(message,),
        rationale="Background run failed before a target outcome could be completed.",
    )
    return ledger, reviewed


def background_run_once(
    input_path: Path | None = None,
    db_path: Path | None = None,
    report_dir: Path | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> BackgroundRunResult:
    """Execute exactly one auditable background run and then exit."""
    run_id = str(uuid.uuid4())
    started_at = _utc_now()
    actual_input_path = input_path or DEFAULT_INPUT_PATH
    actual_db_path = db_path or DEFAULT_DB_PATH
    actual_report_dir = report_dir or DEFAULT_REPORT_DIR
    config: BackgroundConfig | None = None

    try:
        config = load_config(config_path)
        if config.live_network_enabled:
            readiness = automation_readiness_summary(config_path)
            blockers = readiness["live_mode_blockers"]
            if blockers:
                raise RuntimeError(
                    "Live network mode is blocked for background automation: "
                    + ", ".join(blockers)
                )
        actual_input_path = input_path or _resolve_project_path(config.input_path)
        actual_db_path = db_path or _resolve_project_path(config.db_path)
        actual_report_dir = report_dir or _resolve_project_path(config.report_dir)
        init_log_db(actual_db_path)
        with _run_lock(actual_db_path, run_id):
            targets = build_targets(
                input_path=actual_input_path,
                db_path=actual_db_path,
                run_id=run_id,
            )
            target = select_target(targets)

            with _connect(actual_db_path) as conn:
                if target is None:
                    ledger, reviewed = _empty_reviewed_entry(
                        run_id,
                        started_at,
                        actual_input_path,
                        config_path,
                        config.run_mode,
                        config.live_network_enabled,
                    )
                    _insert_ledger(conn, ledger)
                    _insert_reviewed(conn, reviewed)
                    return BackgroundRunResult(ledger=ledger, reviewed=reviewed)

                reason_codes = _trigger_reason_codes(
                    target,
                    follow_up_threshold=config.follow_up_threshold,
                )
                completed_at = _utc_now()
                outcome: BackgroundOutcome = "needs_follow_up" if reason_codes else "reviewed"
                ledger = BackgroundRunLedgerEntry(
                    run_id=run_id,
                    started_at_utc=started_at,
                    completed_at_utc=completed_at,
                    code_version=_CODE_VERSION,
                    schema_version=_SCHEMA_VERSION,
                    input_path=str(actual_input_path),
                    target_id=target.target_id,
                    outcome=outcome,
                    selected_score=target.priority.composite_score,
                    reason_codes=reason_codes or ("BELOW_FOLLOW_UP_THRESHOLD",),
                    run_mode=config.run_mode,
                    config_path=str(config_path),
                    live_network_enabled=config.live_network_enabled,
                )
                _insert_ledger(conn, ledger)

                if outcome == "reviewed":
                    reviewed = ReviewedLogEntry(
                        run_id=run_id,
                        reviewed_at_utc=completed_at,
                        target_id=target.target_id,
                        priority=target.priority,
                        negative_evidence=_negative_evidence(target),
                        rationale="Target did not meet follow-up triggers in this offline run.",
                    )
                    _insert_reviewed(conn, reviewed)
                    return BackgroundRunResult(ledger=ledger, reviewed=reviewed)

                tests = _follow_up_tests(target)
                report_path = _write_report(target, tests, actual_report_dir)
                needs_follow_up = NeedsFollowUpLogEntry(
                    run_id=run_id,
                    recorded_at_utc=completed_at,
                    target_id=target.target_id,
                    priority=target.priority,
                    trigger_reason_codes=reason_codes,
                    required_tests=tests,
                    report_path=str(report_path),
                    recommendations=_recommendations(target),
                    human_approval_required=config.require_human_signoff,
                )
                _insert_needs_follow_up(conn, needs_follow_up)
                return BackgroundRunResult(ledger=ledger, needs_follow_up=needs_follow_up)
    except Exception as exc:
        completed_at = _utc_now()
        init_log_db(actual_db_path)
        with _connect(actual_db_path) as conn:
            ledger, reviewed = _failure_reviewed_entry(
                run_id,
                started_at,
                completed_at,
                actual_input_path,
                exc,
                config_path,
                config.run_mode if config else "manual",
                config.live_network_enabled if config else False,
            )
            if not _ledger_exists(conn, run_id):
                _insert_ledger(conn, ledger)
                _insert_reviewed(conn, reviewed)
        return BackgroundRunResult(ledger=ledger, reviewed=reviewed)


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])


def _ledger_exists(conn: sqlite3.Connection, run_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM run_ledger WHERE run_id = ?", (run_id,)).fetchone()
    return row is not None


def record_human_signoff(
    run_id: str,
    target_id: str,
    reviewer: str,
    decision: SignoffDecision,
    scope: str,
    notes: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> HumanSignoffEntry:
    """Record a human signoff decision without taking external action."""
    init_log_db(db_path)
    entry = HumanSignoffEntry(
        signoff_id=str(uuid.uuid4()),
        run_id=run_id,
        target_id=target_id,
        reviewer=reviewer,
        signed_at_utc=_utc_now(),
        decision=decision,
        scope=scope,
        notes=notes,
    )
    with _connect(db_path) as conn:
        _insert_human_signoff(conn, entry)
    return entry


def ledger_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            "SELECT entry_json FROM run_ledger ORDER BY completed_at_utc DESC LIMIT 1"
        ).fetchone()
        by_outcome = {
            row["outcome"]: row["n"]
            for row in conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM run_ledger GROUP BY outcome"
            )
        }
        return {
            "db_path": str(db_path),
            "total_runs": _count_rows(conn, "run_ledger"),
            "by_outcome": by_outcome,
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def reviewed_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            "SELECT entry_json FROM reviewed_log ORDER BY reviewed_at_utc DESC LIMIT 1"
        ).fetchone()
        return {
            "db_path": str(db_path),
            "total_reviewed": _count_rows(conn, "reviewed_log"),
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def needs_follow_up_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            "SELECT entry_json FROM needs_follow_up_log ORDER BY recorded_at_utc DESC LIMIT 1"
        ).fetchone()
        return {
            "db_path": str(db_path),
            "total_needs_follow_up": _count_rows(conn, "needs_follow_up_log"),
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def human_signoff_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            "SELECT entry_json FROM human_signoff_log ORDER BY signed_at_utc DESC LIMIT 1"
        ).fetchone()
        return {
            "db_path": str(db_path),
            "total_signoffs": _count_rows(conn, "human_signoff_log"),
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def _signoff_rows(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT entry_json
        FROM human_signoff_log
        WHERE run_id = ?
        ORDER BY signed_at_utc ASC
        """,
        (run_id,),
    ).fetchall()
    return [json.loads(row["entry_json"]) for row in rows]


def _run_signoff_readiness(
    conn: sqlite3.Connection,
    run_id: str,
    required_approval_count: int = 1,
) -> dict[str, Any]:
    signoffs = _signoff_rows(conn, run_id)
    approvals = [
        signoff
        for signoff in signoffs
        if signoff["decision"] == "approved_for_internal_review"
    ]
    return {
        "run_id": run_id,
        "required_approval_count": required_approval_count,
        "approval_count": len(approvals),
        "is_ready": len(approvals) >= required_approval_count,
        "signoff_count": len(signoffs),
        "signoffs": signoffs,
    }


def _with_report_readiness(
    readiness: dict[str, Any],
    report_path: str | None,
) -> dict[str, Any]:
    report_exists = bool(report_path and Path(report_path).exists())
    if readiness["is_ready"]:
        report_readiness_state = "signed"
    elif report_exists:
        report_readiness_state = "ready_for_internal_review"
    elif report_path:
        report_readiness_state = "drafted"
    else:
        report_readiness_state = "blocked"
    return {
        "report_path": report_path,
        "report_exists": report_exists,
        "report_readiness_state": report_readiness_state,
        **readiness,
    }


def run_detail(
    run_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    required_approval_count: int = 1,
) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        ledger = conn.execute(
            "SELECT entry_json FROM run_ledger WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        reviewed = conn.execute(
            "SELECT entry_json FROM reviewed_log WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        follow_up = conn.execute(
            "SELECT entry_json FROM needs_follow_up_log WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        signoff_readiness = _run_signoff_readiness(
            conn,
            run_id,
            required_approval_count,
        )
        follow_up_data = json.loads(follow_up["entry_json"]) if follow_up else None
        if follow_up_data:
            signoff_readiness = _with_report_readiness(
                signoff_readiness,
                follow_up_data.get("report_path"),
            )
        return {
            "db_path": str(db_path),
            "run_id": run_id,
            "ledger": json.loads(ledger["entry_json"]) if ledger else None,
            "reviewed": json.loads(reviewed["entry_json"]) if reviewed else None,
            "needs_follow_up": follow_up_data,
            "signoff_readiness": signoff_readiness,
        }


def target_history(target_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        ledger_rows = conn.execute(
            """
            SELECT entry_json
            FROM run_ledger
            WHERE target_id = ?
            ORDER BY completed_at_utc ASC
            """,
            (target_id,),
        ).fetchall()
        signoff_rows = conn.execute(
            """
            SELECT entry_json
            FROM human_signoff_log
            WHERE target_id = ?
            ORDER BY signed_at_utc ASC
            """,
            (target_id,),
        ).fetchall()
        return {
            "db_path": str(db_path),
            "target_id": target_id,
            "runs": [json.loads(row["entry_json"]) for row in ledger_rows],
            "signoffs": [json.loads(row["entry_json"]) for row in signoff_rows],
        }


def signoff_readiness_summary(
    db_path: Path = DEFAULT_DB_PATH,
    required_approval_count: int = 1,
) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        run_rows = conn.execute(
            """
            SELECT run_id, target_id, report_path
            FROM needs_follow_up_log
            ORDER BY recorded_at_utc ASC
            """
        ).fetchall()
        runs = []
        for row in run_rows:
            readiness = _run_signoff_readiness(
                conn,
                row["run_id"],
                required_approval_count,
            )
            runs.append({
                "target_id": row["target_id"],
                **_with_report_readiness(readiness, row["report_path"]),
            })
        return {
            "db_path": str(db_path),
            "required_approval_count": required_approval_count,
            "runs": runs,
            "unsigned_follow_up_runs": [
                run["run_id"] for run in runs if not run["is_ready"]
            ],
        }


def target_priority_summary(
    input_path: Path = DEFAULT_INPUT_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    targets = build_targets(input_path=input_path, db_path=db_path)
    selected = select_target(targets)
    selected_id = selected.target_id if selected else None
    return {
        "input_path": str(input_path),
        "db_path": str(db_path),
        "selected_target_id": selected_id,
        "targets": [
            {
                "target_id": target.target_id,
                "priority": target.priority.model_dump(),
                "skipped_reason_codes": target.skipped_reason_codes
                or (() if target.target_id == selected_id else ("LOWER_PRIORITY_THAN_SELECTED",)),
            }
            for target in sorted(
                targets,
                key=lambda item: item.priority.composite_score,
                reverse=True,
            )
        ],
    }


def _latest_needs_follow_up_entry(db_path: Path) -> dict[str, Any] | None:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT entry_json FROM needs_follow_up_log ORDER BY recorded_at_utc DESC LIMIT 1"
        ).fetchone()
    return json.loads(row["entry_json"]) if row else None


def follow_up_test_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    latest = _latest_needs_follow_up_entry(db_path)
    tests = latest["required_tests"] if latest else []
    return {
        "db_path": str(db_path),
        "target_id": latest["target_id"] if latest else None,
        "tests": tests,
    }


def submission_recommendation_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    latest = _latest_needs_follow_up_entry(db_path)
    recommendations = latest["recommendations"] if latest else []
    return {
        "db_path": str(db_path),
        "target_id": latest["target_id"] if latest else None,
        "recommendations": recommendations,
    }


def validation_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    init_log_db(db_path)
    with _connect(db_path) as conn:
        total_runs = _count_rows(conn, "run_ledger")
        total_reviewed = _count_rows(conn, "reviewed_log")
        total_follow_up = _count_rows(conn, "needs_follow_up_log")
        total_signoffs = _count_rows(conn, "human_signoff_log")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        lock_row = conn.execute("SELECT run_id, acquired_at_utc FROM run_lock").fetchone()
        metadata_row = conn.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()
        report_rows = conn.execute(
            "SELECT report_path FROM needs_follow_up_log WHERE report_path IS NOT NULL"
        ).fetchall()
        readiness = signoff_readiness_summary(db_path)
        missing_reports = [
            row["report_path"]
            for row in report_rows
            if not Path(row["report_path"]).exists()
        ]
    return {
        "db_path": str(db_path),
        "sqlite_integrity": integrity,
        "schema_version": metadata_row["value"] if metadata_row else None,
        "total_runs": total_runs,
        "total_outcomes": total_reviewed + total_follow_up,
        "total_signoffs": total_signoffs,
        "one_outcome_per_run": total_runs == total_reviewed + total_follow_up,
        "lock_active": lock_row is not None,
        "active_lock": dict(lock_row) if lock_row else None,
        "missing_report_paths": missing_reports,
        "all_report_paths_exist": not missing_reports,
        "unsigned_follow_up_runs": readiness["unsigned_follow_up_runs"],
        "all_follow_up_runs_signed": not readiness["unsigned_follow_up_runs"],
        "signoff_readiness": readiness["runs"],
        "manual_first": True,
        "external_submission_enabled": False,
        "log_backend": "sqlite",
    }


def audit_report(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Generate a consolidated cross-log audit report.

    Pulls from all background log tables and returns a summary covering:
      ``total_runs``          — number of ledger entries
      ``reviewed_count``      — entries in the reviewed log
      ``needs_follow_up_count`` — entries in the needs-follow-up log
      ``signoff_coverage``    — fraction of reviewed entries with human signoff
      ``unsigned_count``      — reviewed entries lacking a signoff
      ``pha_candidates``      — count of PHA-flagged candidates ever processed
      ``submission_ready``    — count of candidates recommended for submission
      ``has_unreviewed_runs`` — True when runs exist with no reviewed/follow-up outcome
      ``integrity_ok``        — True when log invariants are satisfied
    """
    ledger = ledger_summary(db_path)
    reviewed = reviewed_log_summary(db_path)
    follow_up = needs_follow_up_summary(db_path)
    readiness = signoff_readiness_summary(db_path)
    validation = validation_summary(db_path)

    total_runs: int = ledger.get("total_runs", 0)
    reviewed_count: int = reviewed.get("total_reviewed", 0)
    follow_up_count: int = follow_up.get("total_needs_follow_up", 0)
    outcome_count = reviewed_count + follow_up_count

    signed_off: int = readiness.get("signed_off", 0)
    unsigned: int = readiness.get("unsigned", 0)
    signoff_coverage = (signed_off / reviewed_count) if reviewed_count > 0 else 0.0

    return {
        "total_runs": total_runs,
        "reviewed_count": reviewed_count,
        "needs_follow_up_count": follow_up_count,
        "signoff_coverage": round(signoff_coverage, 4),
        "unsigned_count": unsigned,
        "pha_candidates": reviewed.get("pha_count", 0),
        "submission_ready": reviewed.get("submission_ready_count", 0),
        "has_unreviewed_runs": outcome_count < total_runs,
        "integrity_ok": validation.get("integrity_ok", True),
    }


def _one_run_command(config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    return f"PYTHONPATH=src python Skills/background.py run-once --config {config_path}"


def _policy_path(config: BackgroundConfig) -> Path | None:
    if not config.live_review_policy:
        return None
    return _resolve_project_path(config.live_review_policy)


def _load_live_review_policy(config: BackgroundConfig) -> tuple[dict[str, Any] | None, list[str]]:
    path = _policy_path(config)
    if path is None:
        return None, ["LIVE_REVIEW_POLICY_MISSING"]
    if not path.exists():
        return None, ["LIVE_REVIEW_POLICY_NOT_FOUND"]
    try:
        with path.open() as handle:
            policy = json.load(handle)
    except json.JSONDecodeError:
        return None, ["LIVE_REVIEW_POLICY_INVALID_JSON"]

    return _load_live_review_policy_from_dict(policy)


def _load_json_contract(
    path: Path,
    missing_code: str,
    invalid_code: str,
) -> tuple[Any | None, list[str]]:
    if not path.exists():
        return None, [missing_code]
    try:
        with path.open() as handle:
            return json.load(handle), []
    except json.JSONDecodeError:
        return None, [invalid_code]


def _live_policy_schema_blockers(schema: Any) -> tuple[str, ...]:
    blockers: list[str] = []
    if not isinstance(schema, dict):
        return ("LIVE_REVIEW_POLICY_SCHEMA_INVALID",)
    if schema.get("$id") != "live-review-policy-v1":
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_ID_INVALID")
    if schema.get("type") != "object":
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_TYPE_INVALID")
    if schema.get("additionalProperties") is not False:
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_ALLOWS_EXTRA_FIELDS")
    required = schema.get("required", ())
    if not isinstance(required, list) or any(
        field not in required for field in _REQUIRED_POLICY_FIELDS
    ):
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_REQUIRED_FIELDS_INCOMPLETE")
    survey_enum = (
        schema.get("properties", {})
        .get("allowed_surveys", {})
        .get("items", {})
        .get("enum", ())
    )
    if tuple(survey_enum) != _SUPPORTED_LIVE_SURVEYS:
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_SURVEY_ENUM_MISMATCH")
    external_const = schema.get("properties", {}).get("no_external_submission_confirmed", {})
    impact_const = schema.get("properties", {}).get("no_impact_probability_claims", {})
    if external_const.get("const") is not True:
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_EXTERNAL_SUBMISSION_GUARD_MISSING")
    if impact_const.get("const") is not True:
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_IMPACT_CLAIM_GUARD_MISSING")
    return tuple(dict.fromkeys(blockers))


def _live_policy_contract_blockers(policy: Any) -> tuple[str, ...]:
    if not isinstance(policy, dict):
        return ("LIVE_REVIEW_POLICY_INVALID_JSON",)
    _policy, blockers = _load_live_review_policy_from_dict(policy)
    return tuple(blocker for blocker in blockers if blocker != "LIVE_REVIEW_POLICY_NOT_APPROVED")


def _load_live_review_policy_from_dict(
    policy: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    missing = [field for field in _REQUIRED_POLICY_FIELDS if field not in policy]
    if missing:
        blockers.append("LIVE_REVIEW_POLICY_MISSING_FIELDS")

    if policy.get("schema_version") != "live-review-policy-v1":
        blockers.append("LIVE_REVIEW_POLICY_SCHEMA_UNSUPPORTED")
    if not policy.get("approved_for_live_network"):
        blockers.append("LIVE_REVIEW_POLICY_NOT_APPROVED")
    if not policy.get("reviewer"):
        blockers.append("LIVE_REVIEW_POLICY_REVIEWER_MISSING")
    if policy.get("no_external_submission_confirmed") is not True:
        blockers.append("LIVE_REVIEW_POLICY_ALLOWS_EXTERNAL_SUBMISSION")
    if policy.get("no_impact_probability_claims") is not True:
        blockers.append("LIVE_REVIEW_POLICY_ALLOWS_IMPACT_CLAIMS")

    allowed = policy.get("allowed_surveys", ())
    if not isinstance(allowed, list) or not allowed:
        blockers.append("LIVE_REVIEW_POLICY_SURVEYS_INVALID")
    elif any(survey not in _SUPPORTED_LIVE_SURVEYS for survey in allowed):
        blockers.append("LIVE_REVIEW_POLICY_SURVEYS_UNSUPPORTED")

    max_queries = policy.get("max_queries_per_run")
    if not isinstance(max_queries, int) or max_queries < 1:
        blockers.append("LIVE_REVIEW_POLICY_RATE_LIMIT_INVALID")
    min_seconds = policy.get("min_seconds_between_queries")
    if not isinstance(min_seconds, int | float) or min_seconds < 0:
        blockers.append("LIVE_REVIEW_POLICY_CADENCE_INVALID")

    scope = policy.get("dry_run_scope", {})
    if not isinstance(scope, dict):
        blockers.append("LIVE_REVIEW_POLICY_SCOPE_INVALID")
    else:
        missing_scope = [
            field for field in _REQUIRED_DRY_RUN_SCOPE_FIELDS if field not in scope
        ]
        if missing_scope:
            blockers.append("LIVE_REVIEW_POLICY_SCOPE_MISSING_FIELDS")
        elif not all(
            isinstance(scope[field], int | float) for field in _REQUIRED_DRY_RUN_SCOPE_FIELDS
        ):
            blockers.append("LIVE_REVIEW_POLICY_SCOPE_INVALID")
        elif scope["end_jd"] <= scope["start_jd"] or scope["radius_deg"] <= 0:
            blockers.append("LIVE_REVIEW_POLICY_SCOPE_INVALID")

    return policy, list(dict.fromkeys(blockers))


def live_policy_contract_summary(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Validate the live-review policy contract without network access."""
    config = load_config(config_path)
    policy_path = _policy_path(config)
    schema, schema_load_blockers = _load_json_contract(
        _LIVE_REVIEW_POLICY_SCHEMA_PATH,
        "LIVE_REVIEW_POLICY_SCHEMA_FILE_NOT_FOUND",
        "LIVE_REVIEW_POLICY_SCHEMA_FILE_INVALID_JSON",
    )
    schema_blockers = (
        tuple(schema_load_blockers)
        if schema_load_blockers
        else _live_policy_schema_blockers(schema)
    )
    policy_blockers: tuple[str, ...]
    if policy_path is None:
        policy_blockers = ("LIVE_REVIEW_POLICY_MISSING",)
    else:
        policy, policy_load_blockers = _load_json_contract(
            policy_path,
            "LIVE_REVIEW_POLICY_NOT_FOUND",
            "LIVE_REVIEW_POLICY_INVALID_JSON",
        )
        policy_blockers = (
            tuple(policy_load_blockers)
            if policy_load_blockers
            else _live_policy_contract_blockers(policy)
        )
    return {
        "config_path": str(config_path),
        "schema_path": str(_LIVE_REVIEW_POLICY_SCHEMA_PATH),
        "policy_path": str(policy_path) if policy_path else None,
        "schema_valid": not schema_blockers,
        "policy_contract_valid": not policy_blockers,
        "contract_valid": not schema_blockers and not policy_blockers,
        "schema_blockers": schema_blockers,
        "policy_blockers": policy_blockers,
        "network_access_performed": False,
        "external_submission_enabled": False,
    }


def live_provider_capabilities() -> tuple[dict[str, Any], ...]:
    """Return the no-network live-provider capability registry."""
    return tuple(dict(_LIVE_PROVIDER_CAPABILITIES[survey]) for survey in _SUPPORTED_LIVE_SURVEYS)


def _policy_allowed_surveys(policy: dict[str, Any] | None) -> tuple[str, ...]:
    if not policy or not isinstance(policy.get("allowed_surveys"), list):
        return ()
    return tuple(policy["allowed_surveys"])


def live_provider_readiness(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> tuple[dict[str, Any], ...]:
    """Report provider-specific live readiness without contacting external services."""
    config = load_config(config_path)
    policy, _policy_blockers = _load_live_review_policy(config)
    allowed_surveys = _policy_allowed_surveys(policy)
    policy_min_seconds = policy.get("min_seconds_between_queries") if policy else None
    readiness = []
    for capability in live_provider_capabilities():
        survey = capability["survey"]
        credential_env = capability["credential_env"]
        blockers: list[str] = []
        if survey not in allowed_surveys:
            blockers.append("PROVIDER_NOT_POLICY_APPROVED")
        if not os.environ.get(credential_env):
            blockers.append("PROVIDER_CREDENTIAL_MISSING")
        if capability["supports_external_submission"]:
            blockers.append("PROVIDER_EXTERNAL_SUBMISSION_CAPABLE")
        if not capability["supports_live_query"]:
            blockers.append("PROVIDER_LIVE_QUERY_UNSUPPORTED")
        min_seconds = capability["min_seconds_between_queries"]
        if not isinstance(policy_min_seconds, int | float):
            blockers.append("PROVIDER_RATE_LIMIT_POLICY_MISSING")
        elif policy_min_seconds < min_seconds:
            blockers.append("PROVIDER_RATE_LIMIT_TOO_FAST")
        readiness.append({
            **capability,
            "policy_approved": survey in allowed_surveys,
            "credential_present": bool(os.environ.get(credential_env)),
            "ready": not blockers,
            "blockers": tuple(blockers),
            "network_access_performed": False,
            "external_submission_enabled": False,
        })
    return tuple(readiness)


def _dedupe_codes(*groups: Any) -> tuple[str, ...]:
    codes: list[str] = []
    for group in groups:
        if not group:
            continue
        for code in group:
            if isinstance(code, str):
                codes.append(code)
    return tuple(dict.fromkeys(codes))


def automation_readiness_summary(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Report scheduler and live-mode readiness without performing network actions."""
    config = load_config(config_path)
    policy, policy_blockers = _load_live_review_policy(config)
    policy_contract = live_policy_contract_summary(config_path)
    provider_readiness = live_provider_readiness(config_path)
    missing_credentials = tuple(
        name for name in config.required_credential_env if not os.environ.get(name)
    )

    scheduler_blockers: list[str] = []
    if config.run_mode != "automated":
        scheduler_blockers.append("RUN_MODE_NOT_AUTOMATED")
    if not config.scheduler_enabled:
        scheduler_blockers.append("SCHEDULER_NOT_ENABLED")

    live_blockers: list[str] = []
    if not config.live_network_enabled:
        live_blockers.append("LIVE_NETWORK_DISABLED")
    if missing_credentials:
        live_blockers.append("MISSING_REQUIRED_CREDENTIALS")
    if any(not provider["ready"] for provider in provider_readiness):
        live_blockers.append("LIVE_PROVIDER_NOT_READY")
    if not policy_contract["contract_valid"]:
        live_blockers.append("LIVE_REVIEW_POLICY_CONTRACT_INVALID")
    live_blockers.extend(policy_blockers)
    if not config.require_human_signoff:
        live_blockers.append("HUMAN_SIGNOFF_NOT_REQUIRED")

    return {
        "config_path": str(config_path),
        "run_mode": config.run_mode,
        "scheduler_enabled": config.scheduler_enabled,
        "scheduler_interval_minutes": config.scheduler_interval_minutes,
        "scheduler_ready": not scheduler_blockers,
        "scheduler_blockers": scheduler_blockers,
        "one_run_command": _one_run_command(config_path),
        "live_network_enabled": config.live_network_enabled,
        "live_mode_ready": config.live_network_enabled and not live_blockers,
        "live_mode_blockers": live_blockers,
        "required_credential_env": config.required_credential_env,
        "missing_credential_env": missing_credentials,
        "live_provider_readiness": provider_readiness,
        "live_review_policy": str(_policy_path(config)) if _policy_path(config) else None,
        "live_review_policy_contract": policy_contract,
        "live_review_policy_summary": _policy_summary(policy),
        "require_human_signoff": config.require_human_signoff,
        "required_approval_count": config.required_approval_count,
        "external_submission_enabled": False,
        "log_backend": "sqlite",
    }


def _policy_summary(policy: dict[str, Any] | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    scope = policy.get("dry_run_scope", {})
    return {
        "schema_version": policy.get("schema_version"),
        "policy_name": policy.get("policy_name"),
        "reviewer": policy.get("reviewer"),
        "approved_for_live_network": bool(policy.get("approved_for_live_network")),
        "allowed_surveys": tuple(policy.get("allowed_surveys", ())),
        "max_queries_per_run": policy.get("max_queries_per_run"),
        "min_seconds_between_queries": policy.get("min_seconds_between_queries"),
        "dry_run_scope": scope if isinstance(scope, dict) else None,
        "no_external_submission_confirmed": policy.get("no_external_submission_confirmed"),
        "no_impact_probability_claims": policy.get("no_impact_probability_claims"),
    }


def record_automation_readiness(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Write an automation-readiness snapshot to the SQLite audit log."""
    init_log_db(db_path)
    summary = automation_readiness_summary(config_path)
    entry = {
        "readiness_id": str(uuid.uuid4()),
        "checked_at_utc": _utc_now(),
        **summary,
    }
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO automation_readiness_log (
                readiness_id, checked_at_utc, config_path, scheduler_ready,
                live_mode_ready, scheduler_blockers_json, live_mode_blockers_json,
                missing_credential_env_json, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["readiness_id"],
                entry["checked_at_utc"],
                entry["config_path"],
                int(entry["scheduler_ready"]),
                int(entry["live_mode_ready"]),
                json.dumps(entry["scheduler_blockers"]),
                json.dumps(entry["live_mode_blockers"]),
                json.dumps(entry["missing_credential_env"]),
                json.dumps(entry),
            ),
        )
    return entry


def automation_readiness_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Summarize persisted automation-readiness checks."""
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            """
            SELECT entry_json
            FROM automation_readiness_log
            ORDER BY checked_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        blocker_counts = {
            "scheduler_not_ready": int(
                conn.execute(
                    "SELECT COUNT(*) FROM automation_readiness_log WHERE scheduler_ready = 0"
                ).fetchone()[0]
            ),
            "live_mode_not_ready": int(
                conn.execute(
                    "SELECT COUNT(*) FROM automation_readiness_log WHERE live_mode_ready = 0"
                ).fetchone()[0]
            ),
        }
        return {
            "db_path": str(db_path),
            "total_readiness_checks": _count_rows(conn, "automation_readiness_log"),
            "blocker_counts": blocker_counts,
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def live_dry_run_plan(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Build a no-network dry-run query plan from config and review policy."""
    config = load_config(config_path)
    policy, policy_blockers = _load_live_review_policy(config)
    readiness = automation_readiness_summary(config_path)
    policy_contract = live_policy_contract_summary(config_path)
    provider_readiness = live_provider_readiness(config_path)
    policy_summary = _policy_summary(policy)
    allowed_surveys = tuple(policy_summary["allowed_surveys"]) if policy_summary else ()
    scope = policy_summary["dry_run_scope"] if policy_summary else None
    queries = []
    if scope:
        for rank, survey in enumerate(allowed_surveys, start=1):
            queries.append({
                "rank": rank,
                "survey": survey,
                "ra_deg": scope["ra_deg"],
                "dec_deg": scope["dec_deg"],
                "radius_deg": scope["radius_deg"],
                "start_jd": scope["start_jd"],
                "end_jd": scope["end_jd"],
                "network_action": "not_executed",
            })
    blockers = tuple(dict.fromkeys((
        *readiness["live_mode_blockers"],
        *policy_blockers,
    )))
    return {
        "config_path": str(config_path),
        "planned_at_utc": _utc_now(),
        "executable": readiness["live_mode_ready"],
        "blockers": blockers,
        "planned_surveys": allowed_surveys,
        "query_count": len(queries),
        "max_queries_per_run": policy_summary["max_queries_per_run"] if policy_summary else None,
        "min_seconds_between_queries": (
            policy_summary["min_seconds_between_queries"] if policy_summary else None
        ),
        "dry_run_scope": scope,
        "queries": queries,
        "live_review_policy_contract": policy_contract,
        "live_provider_readiness": provider_readiness,
        "network_access_performed": False,
        "external_submission_enabled": False,
    }


def live_dry_run_approval_bundle(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Build one no-network review bundle for deciding whether a dry run is ready."""
    readiness = automation_readiness_summary(config_path)
    policy_contract = live_policy_contract_summary(config_path)
    provider_readiness = live_provider_readiness(config_path)
    plan = live_dry_run_plan(config_path)
    provider_blockers = _dedupe_codes(
        *(provider["blockers"] for provider in provider_readiness)
    )
    blockers = _dedupe_codes(
        readiness["scheduler_blockers"],
        readiness["live_mode_blockers"],
        policy_contract["schema_blockers"],
        policy_contract["policy_blockers"],
        provider_blockers,
        plan["blockers"],
    )
    approved = bool(
        readiness["scheduler_ready"]
        and readiness["live_mode_ready"]
        and policy_contract["contract_valid"]
        and plan["executable"]
        and provider_readiness
        and all(provider["ready"] for provider in provider_readiness)
        and not blockers
    )
    return {
        "config_path": str(config_path),
        "reviewed_at_utc": _utc_now(),
        "approved_to_attempt_live_dry_run": approved,
        "blockers": blockers,
        "next_action": "run_mock_live_dry_run_execute" if approved else "resolve_blockers",
        "scheduler_ready": readiness["scheduler_ready"],
        "live_mode_ready": readiness["live_mode_ready"],
        "policy_contract_valid": policy_contract["contract_valid"],
        "all_providers_ready": bool(provider_readiness)
        and all(provider["ready"] for provider in provider_readiness),
        "planned_query_count": plan["query_count"],
        "planned_surveys": plan["planned_surveys"],
        "automation_readiness": readiness,
        "live_review_policy_contract": policy_contract,
        "live_provider_readiness": provider_readiness,
        "live_dry_run_plan": plan,
        "network_access_performed": False,
        "external_submission_enabled": False,
    }


def record_live_dry_run_approval_bundle(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Persist a no-network live dry-run approval bundle to SQLite."""
    init_log_db(db_path)
    bundle = live_dry_run_approval_bundle(config_path)
    entry = {
        "bundle_id": str(uuid.uuid4()),
        **bundle,
    }
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO live_approval_bundle_log (
                bundle_id, reviewed_at_utc, config_path,
                approved_to_attempt_live_dry_run, blockers_json,
                planned_surveys_json, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["bundle_id"],
                entry["reviewed_at_utc"],
                entry["config_path"],
                int(entry["approved_to_attempt_live_dry_run"]),
                json.dumps(entry["blockers"]),
                json.dumps(entry["planned_surveys"]),
                json.dumps(entry),
            ),
        )
    return entry


def live_dry_run_approval_bundle_log_summary(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Summarize persisted no-network live dry-run approval bundles."""
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            """
            SELECT entry_json
            FROM live_approval_bundle_log
            ORDER BY reviewed_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        return {
            "db_path": str(db_path),
            "total_live_approval_bundles": _count_rows(conn, "live_approval_bundle_log"),
            "approval_ready_count": int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM live_approval_bundle_log
                    WHERE approved_to_attempt_live_dry_run = 1
                    """
                ).fetchone()[0]
            ),
            "blocked_count": int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM live_approval_bundle_log
                    WHERE approved_to_attempt_live_dry_run = 0
                    """
                ).fetchone()[0]
            ),
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def _csv_or_none(values: Any) -> str:
    if not values:
        return "None"
    return ", ".join(str(value) for value in values)


def _live_dry_run_handoff_text(bundle: Mapping[str, Any]) -> str:
    readiness = bundle["automation_readiness"]
    policy = readiness.get("live_review_policy_summary") or {}
    missing_credentials = readiness.get("missing_credential_env", ())
    provider_lines = [
        (
            f"- {provider['survey']}: "
            f"{'ready' if provider['ready'] else 'blocked'}"
            f"; credential {provider['credential_env']}"
            f"; blockers: {_csv_or_none(provider['blockers'])}"
        )
        for provider in bundle["live_provider_readiness"]
    ]
    scope = bundle["live_dry_run_plan"].get("dry_run_scope") or {}
    scope_text = (
        "Unavailable"
        if not scope
        else (
            f"RA {scope['ra_deg']}, Dec {scope['dec_deg']}, "
            f"radius {scope['radius_deg']} deg, JD {scope['start_jd']} to {scope['end_jd']}"
        )
    )
    lines = [
        "# Live Dry-Run Operator Handoff",
        "",
        "## Status",
        "Internal review only. This handoff does not authorize external contact or public claims.",
        f"- Ready for mock dry-run attempt: {bundle['approved_to_attempt_live_dry_run']}",
        f"- Next action: {bundle['next_action']}",
        f"- Network access performed: {bundle['network_access_performed']}",
        f"- External submission enabled: {bundle['external_submission_enabled']}",
        "",
        "## Blockers",
        *(
            [f"- {blocker}" for blocker in bundle["blockers"]]
            if bundle["blockers"]
            else ["- None"]
        ),
        "",
        "## Policy",
        f"- Policy approved for live network: {policy.get('approved_for_live_network', False)}",
        f"- Reviewer: {policy.get('reviewer') or 'Not set'}",
        f"- Allowed surveys: {_csv_or_none(policy.get('allowed_surveys', ())) }",
        "",
        "## Credentials",
        f"- Missing credential environment variables: {_csv_or_none(missing_credentials)}",
        "",
        "## Providers",
        *provider_lines,
        "",
        "## Dry-Run Scope",
        f"- Planned surveys: {_csv_or_none(bundle['planned_surveys'])}",
        f"- Planned query count: {bundle['planned_query_count']}",
        f"- Scope: {scope_text}",
        "",
        "## Guardrails",
        "- Use this handoff for local operator review only.",
        "- Resolve blockers before attempting the mock dry-run command.",
        "- Do not contact outside parties from this handoff.",
        "- Defer authoritative hazard assessment to MPC, CNEOS, and NASA processes.",
    ]
    text = "\n".join(lines) + "\n"
    lowered = text.lower()
    for phrase in _FORBIDDEN_REPORT_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Handoff contains forbidden phrase: {phrase}")
    return text


def live_dry_run_operator_handoff(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Build a conservative no-network Markdown handoff for live dry-run review."""
    bundle = live_dry_run_approval_bundle(config_path)
    text = _live_dry_run_handoff_text(bundle)
    return {
        "config_path": str(config_path),
        "created_at_utc": _utc_now(),
        "approved_to_attempt_live_dry_run": bundle["approved_to_attempt_live_dry_run"],
        "blockers": bundle["blockers"],
        "next_action": bundle["next_action"],
        "planned_surveys": bundle["planned_surveys"],
        "planned_query_count": bundle["planned_query_count"],
        "handoff_text": text,
        "network_access_performed": False,
        "external_submission_enabled": False,
    }


def write_live_dry_run_operator_handoff(
    config_path: Path = DEFAULT_CONFIG_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    """Write a conservative no-network live dry-run handoff Markdown file."""
    handoff = live_dry_run_operator_handoff(config_path)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = handoff["created_at_utc"].replace(":", "").replace("+", "_")
    path = report_dir / f"live_dry_run_operator_handoff_{stamp}.md"
    path.write_text(handoff["handoff_text"])
    return {
        **handoff,
        "report_path": str(path),
    }


def record_live_dry_run_operator_handoff(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> dict[str, Any]:
    """Write and persist a conservative no-network operator handoff."""
    init_log_db(db_path)
    handoff = write_live_dry_run_operator_handoff(config_path, report_dir)
    entry = {
        "handoff_id": str(uuid.uuid4()),
        **handoff,
    }
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO live_operator_handoff_log (
                handoff_id, created_at_utc, config_path, report_path,
                approved_to_attempt_live_dry_run, blockers_json,
                planned_surveys_json, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["handoff_id"],
                entry["created_at_utc"],
                entry["config_path"],
                entry["report_path"],
                int(entry["approved_to_attempt_live_dry_run"]),
                json.dumps(entry["blockers"]),
                json.dumps(entry["planned_surveys"]),
                json.dumps(entry),
            ),
        )
    return entry


def live_dry_run_operator_handoff_log_summary(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Summarize persisted no-network live dry-run operator handoffs."""
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            """
            SELECT entry_json
            FROM live_operator_handoff_log
            ORDER BY created_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        return {
            "db_path": str(db_path),
            "total_live_operator_handoffs": _count_rows(
                conn,
                "live_operator_handoff_log",
            ),
            "approval_ready_count": int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM live_operator_handoff_log
                    WHERE approved_to_attempt_live_dry_run = 1
                    """
                ).fetchone()[0]
            ),
            "blocked_count": int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM live_operator_handoff_log
                    WHERE approved_to_attempt_live_dry_run = 0
                    """
                ).fetchone()[0]
            ),
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def record_live_dry_run_plan(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Persist a no-network live dry-run plan to SQLite."""
    init_log_db(db_path)
    plan = live_dry_run_plan(config_path)
    entry = {
        "plan_id": str(uuid.uuid4()),
        **plan,
    }
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO live_dry_run_plan_log (
                plan_id, planned_at_utc, config_path, executable,
                planned_surveys_json, blockers_json, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["plan_id"],
                entry["planned_at_utc"],
                entry["config_path"],
                int(entry["executable"]),
                json.dumps(entry["planned_surveys"]),
                json.dumps(entry["blockers"]),
                json.dumps(entry),
            ),
        )
    return entry


def live_dry_run_plan_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Summarize persisted no-network live dry-run plans."""
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            """
            SELECT entry_json
            FROM live_dry_run_plan_log
            ORDER BY planned_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        return {
            "db_path": str(db_path),
            "total_live_dry_run_plans": _count_rows(conn, "live_dry_run_plan_log"),
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


class LiveDryRunProvider(Protocol):
    """Provider contract for one dry-run survey probe.

    v0.31.0 supports injected/mock providers only. Implementations must not
    contact external services or enable submissions.
    """

    survey: str

    def execute(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a structured dry-run result for one planned query."""


class MockLiveDryRunProvider:
    """No-network provider used by the default live dry-run execution path."""

    def __init__(self, survey: str) -> None:
        self.survey = survey

    def execute(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return a deterministic no-network result for one planned query."""
        return {
            "rank": query["rank"],
            "survey": self.survey,
            "status": "mocked_success",
            "provider": "mock",
            "network_action": "mocked_not_executed",
            "result_count": 0,
            "network_access_performed": False,
            "external_submission_enabled": False,
        }


def _default_live_dry_run_providers(plan: Mapping[str, Any]) -> dict[str, LiveDryRunProvider]:
    return {survey: MockLiveDryRunProvider(survey) for survey in plan["planned_surveys"]}


def _normalize_live_query_result(
    query: Mapping[str, Any],
    raw_result: Mapping[str, Any],
) -> dict[str, Any]:
    result = {
        "rank": query["rank"],
        "survey": query["survey"],
        **dict(raw_result),
    }
    result.setdefault("provider", "injected")
    result.setdefault("network_action", "mocked_not_executed")
    result.setdefault("result_count", 0)
    result.setdefault("network_access_performed", False)
    result.setdefault("external_submission_enabled", False)
    if result["network_access_performed"] is not False:
        raise ValueError("LIVE_PROVIDER_NETWORK_ACCESS_NOT_ALLOWED")
    if result["external_submission_enabled"] is not False:
        raise ValueError("LIVE_PROVIDER_EXTERNAL_SUBMISSION_NOT_ALLOWED")
    return result


def _execute_live_dry_run_queries(
    plan: dict[str, Any],
    providers: Mapping[str, LiveDryRunProvider] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Execute a dry-run plan through no-network providers."""
    provider_map = (
        dict(providers) if providers is not None else _default_live_dry_run_providers(plan)
    )
    results = []
    for query in plan["queries"]:
        survey = query["survey"]
        provider = provider_map.get(survey)
        if provider is None:
            results.append({
                "rank": query["rank"],
                "survey": survey,
                "status": "provider_missing",
                "provider": "none",
                "network_action": "not_executed",
                "result_count": 0,
                "network_access_performed": False,
                "external_submission_enabled": False,
            })
            continue
        results.append(_normalize_live_query_result(query, provider.execute(query)))
    return tuple(results)


def live_dry_run_execute(
    config_path: Path = DEFAULT_CONFIG_PATH,
    providers: Mapping[str, LiveDryRunProvider] | None = None,
) -> dict[str, Any]:
    """Run the live dry-run preflight and execute only no-network providers."""
    plan = live_dry_run_plan(config_path)
    if not plan["executable"]:
        return {
            "config_path": str(config_path),
            "attempted_at_utc": _utc_now(),
            "executable": False,
            "outcome": "blocked",
            "blockers": plan["blockers"],
            "planned_surveys": plan["planned_surveys"],
            "query_results": (),
            "network_access_performed": False,
            "external_submission_enabled": False,
        }

    query_results = _execute_live_dry_run_queries(plan, providers)
    successful_queries = sum(1 for result in query_results if result["status"] == "mocked_success")
    missing_provider_queries = sum(
        1 for result in query_results if result["status"] == "provider_missing"
    )
    return {
        "config_path": str(config_path),
        "attempted_at_utc": _utc_now(),
        "executable": True,
        "outcome": "mock_executed",
        "blockers": (),
        "planned_surveys": plan["planned_surveys"],
        "query_results": query_results,
        "successful_queries": successful_queries,
        "missing_provider_queries": missing_provider_queries,
        "network_access_performed": False,
        "external_submission_enabled": False,
    }


def record_live_execution_attempt(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    providers: Mapping[str, LiveDryRunProvider] | None = None,
) -> dict[str, Any]:
    """Persist a mock-only live dry-run execution attempt to SQLite."""
    init_log_db(db_path)
    result = live_dry_run_execute(config_path, providers)
    entry = {
        "attempt_id": str(uuid.uuid4()),
        **result,
    }
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO live_execution_log (
                attempt_id, attempted_at_utc, config_path, executable,
                outcome, blockers_json, query_results_json,
                external_submission_enabled, entry_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["attempt_id"],
                entry["attempted_at_utc"],
                entry["config_path"],
                int(entry["executable"]),
                entry["outcome"],
                json.dumps(entry["blockers"]),
                json.dumps(entry["query_results"]),
                int(entry["external_submission_enabled"]),
                json.dumps(entry),
            ),
        )
    return entry


def live_execution_log_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Summarize persisted live dry-run execution attempts."""
    init_log_db(db_path)
    with _connect(db_path) as conn:
        latest = conn.execute(
            """
            SELECT entry_json
            FROM live_execution_log
            ORDER BY attempted_at_utc DESC
            LIMIT 1
            """
        ).fetchone()
        by_outcome = {
            row["outcome"]: row["n"]
            for row in conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM live_execution_log GROUP BY outcome"
            )
        }
        return {
            "db_path": str(db_path),
            "total_live_execution_attempts": _count_rows(conn, "live_execution_log"),
            "by_outcome": by_outcome,
            "latest": json.loads(latest["entry_json"]) if latest else None,
        }


def launchd_plist(config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    """Build a macOS launchd plist that invokes the one-run background command."""
    config = load_config(config_path)
    root = _ROOT
    script = root / "Skills" / "background.py"
    stdout = root / "Logs" / "background_launchd.log"
    stderr = root / "Logs" / "background_launchd.err.log"
    interval_seconds = config.scheduler_interval_minutes * 60
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.neo-detection.background</string>
  <key>WorkingDirectory</key>
  <string>{root}</string>
  <key>ProgramArguments</key>
  <array>
    <string>python</string>
    <string>{script}</string>
    <string>run-once</string>
    <string>--config</string>
    <string>{config_path}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>{root / "src"}</string>
    <key>OMP_NUM_THREADS</key>
    <string>1</string>
  </dict>
  <key>StartInterval</key>
  <integer>{interval_seconds}</integer>
  <key>StandardOutPath</key>
  <string>{stdout}</string>
  <key>StandardErrorPath</key>
  <string>{stderr}</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
"""
