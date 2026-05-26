#!/usr/bin/env python
"""Unified conservative background automation CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from background import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_INPUT_PATH,
    DEFAULT_REPORT_DIR,
    automation_readiness_log_summary,
    automation_readiness_summary,
    background_blueprint_compliance_summary,
    background_operations_snapshot,
    background_operations_snapshot_log_summary,
    background_run_once,
    background_schema_status_summary,
    blueprint_compliance_log_summary,
    follow_up_test_summary,
    human_signoff_summary,
    latest_undecided_signoff_packet,
    latest_unsigned_signoff_packet,
    launchd_plist,
    ledger_summary,
    live_dry_run_approval_bundle,
    live_dry_run_approval_bundle_log_summary,
    live_dry_run_operator_handoff,
    live_dry_run_operator_handoff_log_summary,
    live_dry_run_plan,
    live_dry_run_plan_log_summary,
    live_execution_log_summary,
    live_policy_contract_summary,
    live_provider_readiness,
    migrate_background_log_db,
    needs_follow_up_summary,
    record_automation_readiness,
    record_background_operations_snapshot,
    record_blueprint_compliance_summary,
    record_human_signoff,
    record_live_dry_run_approval_bundle,
    record_live_dry_run_operator_handoff,
    record_live_dry_run_plan,
    record_live_execution_attempt,
    record_signoff_from_packet,
    record_signoff_packet,
    reviewed_log_summary,
    run_detail,
    signoff_packet,
    signoff_packet_decision_readiness,
    signoff_packet_decision_summary,
    signoff_packet_log_summary,
    signoff_readiness_summary,
    submission_recommendation_summary,
    target_history,
    target_priority_summary,
    validation_summary,
    write_live_dry_run_operator_handoff,
    write_signoff_packet,
)


def _print_json(payload: Any) -> None:
    if hasattr(payload, "model_dump"):
        print(payload.model_dump_json(indent=2))
    else:
        print(json.dumps(payload, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative background automation")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run-once", help="Run one bounded background cycle")
    run.add_argument("--input", type=Path, default=None)
    run.add_argument("--db", type=Path, default=None)
    run.add_argument("--report-dir", type=Path, default=None)
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    priority = sub.add_parser("target-priority-summary", help="Summarize target priorities")
    priority.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    priority.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    readiness = sub.add_parser("automation-readiness", help="Inspect scheduler/live readiness")
    readiness.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    record_readiness = sub.add_parser(
        "record-automation-readiness",
        help="Persist scheduler/live readiness to SQLite",
    )
    record_readiness.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    record_readiness.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    launchd = sub.add_parser("launchd-plist", help="Print a macOS launchd plist template")
    launchd.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    policy_contract = sub.add_parser(
        "live-policy-contract-summary",
        help="Inspect live review policy contract without network access",
    )
    policy_contract.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    provider_readiness = sub.add_parser(
        "live-provider-readiness-summary",
        help="Inspect live provider readiness without network access",
    )
    provider_readiness.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    approval_bundle = sub.add_parser(
        "live-dry-run-approval-bundle",
        help="Inspect all live dry-run approval gates without network access",
    )
    approval_bundle.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    record_approval_bundle = sub.add_parser(
        "record-live-dry-run-approval-bundle",
        help="Persist all live dry-run approval gates to SQLite",
    )
    record_approval_bundle.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    record_approval_bundle.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    operator_handoff = sub.add_parser(
        "live-dry-run-operator-handoff",
        help="Print a conservative live dry-run operator handoff",
    )
    operator_handoff.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    write_operator_handoff = sub.add_parser(
        "write-live-dry-run-operator-handoff",
        help="Write a conservative live dry-run operator handoff Markdown file",
    )
    write_operator_handoff.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    write_operator_handoff.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)

    record_operator_handoff = sub.add_parser(
        "record-live-dry-run-operator-handoff",
        help="Write and persist a conservative live dry-run operator handoff",
    )
    record_operator_handoff.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    record_operator_handoff.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    record_operator_handoff.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)

    dry_run = sub.add_parser("live-dry-run-plan", help="Print a no-network live query plan")
    dry_run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    record_dry_run = sub.add_parser(
        "record-live-dry-run-plan",
        help="Persist a no-network live query plan to SQLite",
    )
    record_dry_run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    record_dry_run.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    execute_dry_run = sub.add_parser(
        "live-dry-run-execute",
        help="Run mock-only live dry-run preflight and persist the attempt",
    )
    execute_dry_run.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    execute_dry_run.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    blueprint = sub.add_parser(
        "blueprint-compliance-summary",
        help="Audit background automation against the implementation blueprint",
    )
    blueprint.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    blueprint.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    record_blueprint = sub.add_parser(
        "record-blueprint-compliance-summary",
        help="Persist a background blueprint compliance audit snapshot",
    )
    record_blueprint.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    record_blueprint.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    operations = sub.add_parser(
        "operations-snapshot",
        help="Aggregate conservative background operations status",
    )
    operations.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    operations.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    operations.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    record_operations = sub.add_parser(
        "record-operations-snapshot",
        help="Persist conservative background operations status to SQLite",
    )
    record_operations.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    record_operations.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    record_operations.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    latest_packet = sub.add_parser(
        "latest-unsigned-signoff-packet",
        help="Build a packet for the oldest unsigned follow-up run",
    )
    latest_packet.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    packet = sub.add_parser("signoff-packet", help="Build an internal signoff packet")
    packet.add_argument("--run-id", required=True)
    packet.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    write_packet = sub.add_parser(
        "write-signoff-packet",
        help="Write an internal signoff packet Markdown file",
    )
    write_packet.add_argument("--run-id", required=True)
    write_packet.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    write_packet.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)

    record_packet = sub.add_parser(
        "record-signoff-packet",
        help="Write and persist internal signoff packet metadata",
    )
    record_packet.add_argument("--run-id", required=True)
    record_packet.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    record_packet.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)

    packet_signoff = sub.add_parser(
        "record-signoff-from-packet",
        help="Record a human signoff decision from an internal packet",
    )
    packet_signoff.add_argument("--packet-id", required=True)
    packet_signoff.add_argument("--reviewer", required=True)
    packet_signoff.add_argument(
        "--decision",
        required=True,
        choices=["approved_for_internal_review", "needs_more_work", "rejected"],
    )
    packet_signoff.add_argument("--scope", required=True)
    packet_signoff.add_argument("--notes", default="")
    packet_signoff.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    for name in (
        "ledger-summary",
        "schema-status-summary",
        "init-log-db",
        "reviewed-summary",
        "needs-follow-up-summary",
        "follow-up-test-summary",
        "submission-recommendation-summary",
        "validation-summary",
        "blueprint-compliance-log-summary",
        "operations-snapshot-log-summary",
        "signoff-packet-log-summary",
        "signoff-packet-decision-summary",
        "signoff-packet-decision-readiness",
        "latest-undecided-signoff-packet",
        "human-signoff-summary",
        "signoff-readiness",
        "automation-readiness-log-summary",
        "live-dry-run-approval-bundle-log-summary",
        "live-dry-run-operator-handoff-log-summary",
        "live-dry-run-plan-log-summary",
        "live-execution-log-summary",
        "unsigned-follow-up",
    ):
        cmd = sub.add_parser(name)
        cmd.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    detail = sub.add_parser("run-detail", help="Inspect one background run")
    detail.add_argument("--run-id", required=True)
    detail.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    history = sub.add_parser("target-history", help="Inspect one target history")
    history.add_argument("--target-id", required=True)
    history.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    signoff = sub.add_parser("record-signoff", help="Record a manual human signoff")
    signoff.add_argument("--run-id", required=True)
    signoff.add_argument("--target-id", required=True)
    signoff.add_argument("--reviewer", required=True)
    signoff.add_argument(
        "--decision",
        required=True,
        choices=["approved_for_internal_review", "needs_more_work", "rejected"],
    )
    signoff.add_argument("--scope", required=True)
    signoff.add_argument("--notes", default="")
    signoff.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    args = parser.parse_args()

    if args.command == "run-once":
        _print_json(background_run_once(args.input, args.db, args.report_dir, args.config))
    elif args.command == "schema-status-summary":
        _print_json(background_schema_status_summary(args.db))
    elif args.command == "init-log-db":
        _print_json(migrate_background_log_db(args.db))
    elif args.command == "target-priority-summary":
        _print_json(target_priority_summary(args.input, args.db))
    elif args.command == "automation-readiness":
        _print_json(automation_readiness_summary(args.config))
    elif args.command == "record-automation-readiness":
        _print_json(record_automation_readiness(args.config, args.db))
    elif args.command == "launchd-plist":
        print(launchd_plist(args.config), end="")
    elif args.command == "live-policy-contract-summary":
        _print_json(live_policy_contract_summary(args.config))
    elif args.command == "live-provider-readiness-summary":
        _print_json(live_provider_readiness(args.config))
    elif args.command == "live-dry-run-approval-bundle":
        _print_json(live_dry_run_approval_bundle(args.config))
    elif args.command == "record-live-dry-run-approval-bundle":
        _print_json(record_live_dry_run_approval_bundle(args.config, args.db))
    elif args.command == "live-dry-run-operator-handoff":
        _print_json(live_dry_run_operator_handoff(args.config))
    elif args.command == "write-live-dry-run-operator-handoff":
        _print_json(write_live_dry_run_operator_handoff(args.config, args.report_dir))
    elif args.command == "record-live-dry-run-operator-handoff":
        _print_json(
            record_live_dry_run_operator_handoff(args.config, args.db, args.report_dir)
        )
    elif args.command == "live-dry-run-plan":
        _print_json(live_dry_run_plan(args.config))
    elif args.command == "record-live-dry-run-plan":
        _print_json(record_live_dry_run_plan(args.config, args.db))
    elif args.command == "live-dry-run-execute":
        _print_json(record_live_execution_attempt(args.config, args.db))
    elif args.command == "blueprint-compliance-summary":
        _print_json(background_blueprint_compliance_summary(args.db, args.input))
    elif args.command == "record-blueprint-compliance-summary":
        _print_json(record_blueprint_compliance_summary(args.db, args.input))
    elif args.command == "operations-snapshot":
        _print_json(background_operations_snapshot(args.config, args.db, args.input))
    elif args.command == "record-operations-snapshot":
        _print_json(record_background_operations_snapshot(args.config, args.db, args.input))
    elif args.command == "latest-unsigned-signoff-packet":
        _print_json(latest_unsigned_signoff_packet(args.db))
    elif args.command == "signoff-packet":
        _print_json(signoff_packet(args.run_id, args.db))
    elif args.command == "write-signoff-packet":
        _print_json(write_signoff_packet(args.run_id, args.db, args.report_dir))
    elif args.command == "record-signoff-packet":
        _print_json(record_signoff_packet(args.run_id, args.db, args.report_dir))
    elif args.command == "record-signoff-from-packet":
        _print_json(
            record_signoff_from_packet(
                packet_id=args.packet_id,
                reviewer=args.reviewer,
                decision=args.decision,
                scope=args.scope,
                notes=args.notes,
                db_path=args.db,
            )
        )
    elif args.command == "ledger-summary":
        _print_json(ledger_summary(args.db))
    elif args.command == "reviewed-summary":
        _print_json(reviewed_log_summary(args.db))
    elif args.command == "needs-follow-up-summary":
        _print_json(needs_follow_up_summary(args.db))
    elif args.command == "follow-up-test-summary":
        _print_json(follow_up_test_summary(args.db))
    elif args.command == "submission-recommendation-summary":
        _print_json(submission_recommendation_summary(args.db))
    elif args.command == "validation-summary":
        _print_json(validation_summary(args.db))
    elif args.command == "blueprint-compliance-log-summary":
        _print_json(blueprint_compliance_log_summary(args.db))
    elif args.command == "operations-snapshot-log-summary":
        _print_json(background_operations_snapshot_log_summary(args.db))
    elif args.command == "signoff-packet-log-summary":
        _print_json(signoff_packet_log_summary(args.db))
    elif args.command == "signoff-packet-decision-summary":
        _print_json(signoff_packet_decision_summary(args.db))
    elif args.command == "signoff-packet-decision-readiness":
        _print_json(signoff_packet_decision_readiness(args.db))
    elif args.command == "latest-undecided-signoff-packet":
        _print_json(latest_undecided_signoff_packet(args.db))
    elif args.command == "human-signoff-summary":
        _print_json(human_signoff_summary(args.db))
    elif args.command == "signoff-readiness":
        _print_json(signoff_readiness_summary(args.db))
    elif args.command == "automation-readiness-log-summary":
        _print_json(automation_readiness_log_summary(args.db))
    elif args.command == "live-dry-run-approval-bundle-log-summary":
        _print_json(live_dry_run_approval_bundle_log_summary(args.db))
    elif args.command == "live-dry-run-operator-handoff-log-summary":
        _print_json(live_dry_run_operator_handoff_log_summary(args.db))
    elif args.command == "live-dry-run-plan-log-summary":
        _print_json(live_dry_run_plan_log_summary(args.db))
    elif args.command == "live-execution-log-summary":
        _print_json(live_execution_log_summary(args.db))
    elif args.command == "unsigned-follow-up":
        readiness = signoff_readiness_summary(args.db)
        _print_json({
            "db_path": readiness["db_path"],
            "unsigned_follow_up_runs": readiness["unsigned_follow_up_runs"],
            "runs": [run for run in readiness["runs"] if not run["is_ready"]],
        })
    elif args.command == "run-detail":
        _print_json(run_detail(args.run_id, args.db))
    elif args.command == "target-history":
        _print_json(target_history(args.target_id, args.db))
    elif args.command == "record-signoff":
        _print_json(
            record_human_signoff(
                run_id=args.run_id,
                target_id=args.target_id,
                reviewer=args.reviewer,
                decision=args.decision,
                scope=args.scope,
                notes=args.notes,
                db_path=args.db,
            )
        )


if __name__ == "__main__":
    main()
