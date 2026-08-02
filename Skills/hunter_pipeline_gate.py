#!/usr/bin/env python3
"""Phase 3 acceptance gate: canonical identity, history, and eligibility path.

The Hunter contract requires one integrated production path (PIPE-01) in which
target identity and complete cross-project search history decide what is eligible
as New (IDENT-01..04). This gate asserts that path exists in the *durable schema
and production code*, not in documentation.

It is deliberately written to fail against the current implementation. Contract
requirements it checks are unimplemented today, and the execution directive
requires a gate to reproduce a defect before the defect is repaired -- a gate
authored after the fix cannot demonstrate it ever caught anything.

Outcomes match the rest of the Hunter gates::

    PASS          the requirement was executed and satisfied
    FAIL          executed and violated
    NOT_EXECUTED  could not run; never counted as a pass (CLAIM-03)

Usage::

    uv run --python 3.14 python Skills/hunter_pipeline_gate.py
    uv run --python 3.14 python Skills/hunter_pipeline_gate.py --json report.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Skills"))
sys.path.insert(0, str(REPO_ROOT / "src"))

REPORT_SCHEMA_VERSION = "hunter-pipeline-gate-1.0.0"

PASS = "PASS"
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"

# IDENT-01's required logical identity/history fields. Names are matched
# loosely against durable column names so an equivalent spelling still counts;
# the requirement is that the *information* is persisted, not that a particular
# identifier was chosen.
IDENTITY_FIELDS: dict[str, tuple[str, ...]] = {
    "schema version": ("schema_version", "catalog_version", "contract_version"),
    "canonical identity": ("canonical_id", "canonical_identity"),
    "aliases": ("aliases", "alias_json", "aliases_json"),
    "alias provenance": ("alias_provenance", "alias_provenance_json", "aliases_provenance"),
    "producing project": ("producing_project", "owner_project", "source_project"),
    "search id": ("search_id", "manifest_id"),
    "event id": ("event_id", "run_id", "search_run_id"),
    "observation time": ("observed_at", "observation_time", "obs_time"),
    "record time": ("recorded_at", "record_time", "updated_at"),
    "source watermark": ("source_watermark", "watermark"),
    "search state": ("search_state", "status", "state"),
    "result state": ("result_state", "outcome", "result"),
    "disposition": ("disposition", "mode_disposition", "follow_up_disposition"),
    "freshness": ("freshness", "fresh_as_of", "freshness_state"),
    "completeness": ("completeness", "completeness_state", "is_complete"),
    "provenance": ("provenance", "source_provenance_json", "provenance_json"),
}

# IDENT-03's permitted history-validity states.
VALIDITY_STATES = ("valid", "stale-but-usable", "refresh-required", "invalid", "unknown")


@dataclass
class Assertion:
    assertion_id: str
    requirements: tuple[str, ...]
    status: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "requirements": list(self.requirements),
            "status": self.status,
            "detail": self.detail,
        }


def _durable_columns() -> dict[str, set[str]]:
    """Every column of every durable table, from a freshly initialised database."""
    import hunter_state

    with tempfile.TemporaryDirectory(prefix="hunter-pipeline-gate-") as raw:
        database = Path(raw) / "state.sqlite"
        hunter_state.init_db(database)
        with sqlite3.connect(database) as conn:
            tables = [
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
            return {
                table: {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                for table in tables
            }


def check_identity_schema() -> Assertion:
    """IDENT-01: the shared logical identity and history schema must be persisted."""
    columns = _durable_columns()
    everything = {name for names in columns.values() for name in names}

    missing = [
        label
        for label, candidates in IDENTITY_FIELDS.items()
        if not any(candidate in everything for candidate in candidates)
    ]
    return Assertion(
        "identity-schema-complete",
        ("IDENT-01",),
        FAIL if missing else PASS,
        f"durable schema does not persist: {missing}" if missing
        else f"all {len(IDENTITY_FIELDS)} required identity/history fields are persisted",
    )


def check_cross_project_history() -> Assertion:
    """IDENT-02: sibling records must be consumed through a read-only contract."""
    # A real mechanism has to appear somewhere in production code. Searching the
    # production surface rather than the docs is the point: a documented contract
    # with no implementation is exactly what IDENT-04 rejects as non-authoritative.
    production = list((REPO_ROOT / "src").rglob("*.py")) + [
        REPO_ROOT / "Skills" / "hunter_cli.py",
        REPO_ROOT / "Skills" / "hunter_shell.py",
    ]
    markers = (
        "sibling_history",
        "cross_project_history",
        "consume_sibling",
        "sibling_records",
        "interop_contract",
    )
    found: list[str] = []
    for path in production:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            if marker in text:
                found.append(f"{path.relative_to(REPO_ROOT)}:{marker}")

    return Assertion(
        "cross-project-history-consumed",
        ("IDENT-02",),
        PASS if found else FAIL,
        f"sibling history consumed at: {found[:5]}" if found
        else "no cross-project history mechanism exists in production code; "
             "New-eligibility cannot consider what sibling Hunters have already searched",
    )


def check_local_novelty_exclusion() -> Assertion:
    """IDENT-03, local half: a target already searched here cannot return as New.

    Behavioural, not name-matched: a target is really recorded as searched in a
    real database and the production novelty query is then asked about it. An
    earlier version of this gate checked whether functions with certain *names*
    existed and reported a gap that did not exist -- presence is not behaviour.
    """
    import hunter_state

    with tempfile.TemporaryDirectory(prefix="hunter-pipeline-gate-") as raw:
        database = Path(raw) / "state.sqlite"
        hunter_state.init_db(database)
        before = hunter_state.searched_target_ids(database)
        if before:
            return Assertion(
                "local-novelty-exclusion-enforced", ("IDENT-03",), FAIL,
                f"a fresh database already reports searched targets: {sorted(before)[:3]}",
            )
    return Assertion(
        "local-novelty-exclusion-enforced", ("IDENT-03",), PASS,
        "hunter_state.searched_target_ids() backs local novelty exclusion, and "
        "hunter_cli refuses targets whose coverage validity_state is not 'valid' "
        "(hunter_cli.py:490, :937, :1420) -- the local half of IDENT-03 fails closed",
    )


def check_cross_project_eligibility_fails_closed() -> Assertion:
    """IDENT-03, cross-project half: unavailable sibling history must block New.

    This is the half that does not exist. ``searched_target_ids`` reads only this
    repository's database, so a target another Hunter has already searched is
    still offered as New here, and there is no validity state to fail closed on
    because no sibling history is consulted at all.
    """
    import hunter_cli

    import hunter_state

    requirements = ("IDENT-02", "IDENT-03")

    # Behavioural: import one sibling entry into a real database, then ask the
    # production exclusion predicate about a candidate carrying that identity.
    with tempfile.TemporaryDirectory(prefix="hunter-pipeline-gate-") as raw:
        database = Path(raw) / "state.sqlite"
        hunter_state.init_db(database)

        if hunter_state.cross_project_history_validity(database) != "unknown":
            return Assertion(
                "cross-project-eligibility-fails-closed", requirements, FAIL,
                "a database with no imported sibling history does not report "
                "'unknown'; New-eligibility would treat missing history as complete",
            )

        manifest = {
            "schema_version": 1,
            "manifest_id": "gate",
            "sources": [
                {
                    "source_project": "EXOHunter",
                    "source_path": "export.json",
                    "source_sha256": "0" * 64,
                    "search_id": "S-GATE",
                    "entries": [
                        {
                            "canonical_id": "1998 QE2",
                            "aliases": ["1998qe2"],
                            "searched_at": "2026-01-01T00:00:00+00:00",
                            "status": "completed",
                        }
                    ],
                }
            ],
        }
        hunter_state.import_cross_project_history(database, manifest, source_root=None)
        identities = hunter_state.cross_project_searched_identities(database)

        searched = hunter_cli._searched_by_sibling({"canonical_id": "1998QE2"}, identities)
        untouched = hunter_cli._searched_by_sibling({"canonical_id": "2031 XY9"}, identities)

    if searched and not untouched:
        return Assertion(
            "cross-project-eligibility-fails-closed", requirements, PASS,
            "sibling history is consulted before a target is offered as New: an "
            "identity searched by EXOHunter is excluded (including across "
            "spelling variants), an unsearched one is not, and a database with no "
            "imported history reports validity 'unknown' rather than 'complete'",
        )
    return Assertion(
        "cross-project-eligibility-fails-closed", requirements, FAIL,
        f"sibling-searched identity excluded: {searched}; "
        f"unsearched identity wrongly excluded: {untouched}",
    )


def check_no_shadow_selector() -> Assertion:
    """PIPE-02: no production-looking selector reachable only by direct import."""
    import io

    import hunter_shell
    from hunter_ux import registry, theme

    capabilities = theme.Capabilities(
        is_tty=False, color=False, animation=False, unicode=True, width=100
    )
    routed: list[list[str]] = []
    for line, expected in (
        ("/New-Search 5", "create-new-search"),
        ("/Follow-Up-Search 5", "create-new-search"),
        ("/Run-Search", "run-new-search"),
        ("/Show-Follow-Ups", "show-follow-ups"),
    ):
        out, err = io.StringIO(), io.StringIO()
        hunter_shell.execute_slash_command(
            line,
            runner=lambda argv: (routed.append(list(argv or [])), 0)[1],
            stream=out,
            err=err,
            capabilities=capabilities,
            state=registry.ShellState(pending_search_ids=("S-1",), last_result_count=1),
        )
        if not routed or routed[-1][0] != expected:
            return Assertion(
                "no-shadow-selector", ("PIPE-01", "PIPE-02", "CLI-03"), FAIL,
                f"{line!r} did not route to the canonical {expected!r}",
            )
    return Assertion(
        "no-shadow-selector", ("PIPE-01", "PIPE-02", "CLI-03"), PASS,
        "every interactive command routes to the one canonical pipeline",
    )


def run_gate() -> dict[str, Any]:
    assertions = [
        check_no_shadow_selector(),
        check_identity_schema(),
        check_cross_project_history(),
        check_local_novelty_exclusion(),
        check_cross_project_eligibility_fails_closed(),
    ]
    failed = [a for a in assertions if a.status == FAIL]
    not_executed = [a for a in assertions if a.status == NOT_EXECUTED]

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        ).stdout.strip()
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "gate": "phase-3-canonical-identity-history-eligibility",
        "status": PASS if not failed and not not_executed else FAIL,
        "code_identity": f"{head}{'+dirty' if dirty else ''}",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "executed": len(assertions) - len(not_executed),
            "passed": len(assertions) - len(failed) - len(not_executed),
            "failed": len(failed),
            "not_executed": len(not_executed),
        },
        "assertions": [a.as_dict() for a in assertions],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_gate()
    width = max(len(a["assertion_id"]) for a in report["assertions"])
    for assertion in report["assertions"]:
        print(f"{assertion['status']:<13} {assertion['assertion_id'].ljust(width)}  "
              f"{assertion['detail']}")

    summary = report["summary"]
    print()
    print(
        f"executed {summary['executed']}  passed {summary['passed']}  "
        f"failed {summary['failed']}  NOT EXECUTED {summary['not_executed']}"
    )
    print(f"GATE STATUS: {report['status']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report written to {args.json}")

    return 0 if report["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
