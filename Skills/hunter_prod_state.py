#!/usr/bin/env python3
"""Read/update the Hunter PROD durable state and acceptance ledger.

The ledger at ``configs/HUNTER_PROD_STATE.json`` is the machine-readable record
of which contract requirements are VERIFIED, what evidence supports each, and
what the next executable step is. It must stay valid JSON: the contract treats
it as durable state, and ``Skills/hunter_prod_check.py`` consumes it.

This module exists so requirement closures are recorded through one validated
code path instead of ad hoc hand edits that can silently corrupt the file or
record a VERIFIED status with missing evidence fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "configs" / "HUNTER_PROD_STATE.json"

# Statuses the contract permits for any requirement.
ALLOWED_STATUSES = (
    "UNVERIFIED",
    "BLOCKING",
    "IN_PROGRESS",
    "IMPLEMENTED_NOT_VERIFIED",
    "VERIFIED",
    "NOT_APPLICABLE",
)

# Statuses an implementation agent may assert directly, from its own judgement.
# These describe *work*, and an agent is the authority on its own work.
AGENT_AUTHORED_STATUSES = (
    "UNVERIFIED",
    "BLOCKING",
    "IN_PROGRESS",
    "IMPLEMENTED_NOT_VERIFIED",
    "NOT_APPLICABLE",
)

# Statuses only a deterministic gate execution may produce. These describe
# *verification*, and an agent is never the authority on whether its own work is
# verified. Writing one of these requires a bound gate result: a real command
# that really ran, exited zero, and left raw evidence on disk.
GATE_AUTHORED_STATUSES = ("VERIFIED",)

# Fields that bind a VERIFIED claim to the gate execution that produced it.
# Without these a VERIFIED status is an agent's assertion, which the Hunter
# contract does not accept as evidence of its own claim (CLAIM-04).
REQUIRED_GATE_FIELDS = (
    "gate_command",
    "gate_path",
    "gate_sha256",
    "exit_status",
    "code_identity",
    "executed_at_utc",
)

# Evidence fields that must all be populated before a requirement may be
# VERIFIED. This is the ledger-side enforcement of contract rule CLAIM-04.
REQUIRED_EVIDENCE_FIELDS = (
    "requirement_id",
    "exact_command",
    "environment",
    "observable_assertion",
    "raw_evidence_path",
    "tested_commit",
    "tested_at_utc",
)


class LedgerError(RuntimeError):
    """Raised when the ledger is malformed or an update would violate the contract."""


def sha256_of(path: Path) -> str:
    """Content hash of a gate file, used to detect drift after freezing.

    A frozen gate's hash is recorded alongside every VERIFIED claim it produced.
    If the gate file later changes, the recorded hash no longer matches and the
    claim is reported stale rather than silently inherited -- this is what stops
    a gate from being weakened after the fact while its PASS records survive.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_identity(repo_root: Path = REPO_ROOT) -> str:
    """Identity of the code a gate actually tested: commit plus dirty marker.

    A bare commit SHA is not sufficient identity for a working tree with
    uncommitted changes -- the gate did not test that commit, it tested the
    commit plus whatever is unstaged. Saying so is the difference between
    traceable evidence and a plausible-looking one.
    """
    def _git(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
        )
        return completed.stdout.strip()

    commit = _git("rev-parse", "HEAD") or "unknown"
    dirty = bool(_git("status", "--porcelain"))
    return f"{commit}{'+dirty' if dirty else ''}"


def run_gate(
    command: list[str],
    *,
    gate_path: Path,
    repo_root: Path = REPO_ROOT,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Execute a gate and return its bound, unforgeable result record.

    This is the only supported way to produce the inputs a VERIFIED status
    requires. The record carries what the command was, which file implements it,
    that file's content hash, the real exit status, and the identity of the code
    under test. An agent can call this, but it cannot fabricate a passing result
    without a command that genuinely exits zero.
    """
    completed = subprocess.run(
        command, cwd=repo_root, capture_output=True, text=True, timeout=timeout, check=False
    )
    return {
        "gate_command": " ".join(command),
        "gate_path": str(gate_path.relative_to(repo_root)),
        "gate_sha256": sha256_of(gate_path),
        "exit_status": completed.returncode,
        "code_identity": code_identity(repo_root),
        "executed_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "stdout_tail": completed.stdout.strip().splitlines()[-20:],
        "stderr_tail": completed.stderr.strip().splitlines()[-20:],
    }


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    """Load the ledger, failing loudly rather than silently substituting a default."""
    if not path.is_file():
        raise LedgerError(f"PROD state ledger is missing: {path}")
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise LedgerError(
            f"PROD state ledger is not valid JSON ({path}): {exc}. "
            "The ledger is machine-readable durable state and cannot be a rich-text file."
        ) from exc
    if not isinstance(state, dict):
        raise LedgerError(f"PROD state ledger must be a JSON object, got {type(state).__name__}")
    return state


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    """Write the ledger back as formatted JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def validate_state(state: dict[str, Any]) -> list[str]:
    """Return every contract violation found in the ledger, newest checks first.

    An empty list means the ledger is internally consistent. This does not assert
    that the underlying requirements are actually met -- only that the ledger's
    own claims are well formed and evidence-backed.
    """
    problems: list[str] = []

    if state.get("artifact") != "configs/HUNTER_PROD_STATE.json":
        problems.append(
            "artifact path must be 'configs/HUNTER_PROD_STATE.json', "
            f"found {state.get('artifact')!r}"
        )

    requirements = state.get("requirements", {})
    evidence = state.get("evidence", {})
    for requirement_id, record in sorted(requirements.items()):
        status = record.get("status")
        if status not in ALLOWED_STATUSES:
            problems.append(f"{requirement_id}: status {status!r} is not an allowed status")
            continue
        if status != "VERIFIED":
            continue
        # A VERIFIED requirement must carry complete, populated evidence.
        entry = evidence.get(requirement_id)
        if not isinstance(entry, dict):
            problems.append(f"{requirement_id}: VERIFIED without any evidence entry")
            continue
        missing = [
            field
            for field in REQUIRED_EVIDENCE_FIELDS
            if not str(entry.get(field, "")).strip()
        ]
        if missing:
            problems.append(f"{requirement_id}: VERIFIED with missing evidence fields {missing}")

        # Status authority: VERIFIED must be produced by a deterministic gate,
        # never by an agent writing the word. Everything below checks that the
        # claim is bound to a gate execution that actually happened and passed.
        gate = entry.get("gate")
        if not isinstance(gate, dict):
            problems.append(
                f"{requirement_id}: VERIFIED without a bound gate result. "
                "VERIFIED is gate-authored; an agent may write at most "
                "IMPLEMENTED_NOT_VERIFIED."
            )
            continue

        missing_gate = [f for f in REQUIRED_GATE_FIELDS if not str(gate.get(f, "")).strip()]
        if missing_gate:
            problems.append(f"{requirement_id}: gate result missing fields {missing_gate}")
            continue

        if gate.get("exit_status") != 0:
            problems.append(
                f"{requirement_id}: VERIFIED but its gate exited "
                f"{gate.get('exit_status')!r}; only exit status 0 verifies"
            )

        # The gate file must still be the one that produced this result. A
        # changed hash means the gate was edited after it passed, so the recorded
        # PASS no longer describes the gate that exists now.
        gate_path = REPO_ROOT / str(gate.get("gate_path", ""))
        if not gate_path.is_file():
            problems.append(f"{requirement_id}: gate file {gate.get('gate_path')!r} does not exist")
        elif sha256_of(gate_path) != gate.get("gate_sha256"):
            problems.append(
                f"{requirement_id}: gate {gate.get('gate_path')!r} changed since it passed "
                "(sha256 mismatch); re-run the gate rather than inheriting a stale PASS"
            )

        # Raw evidence must be on disk. A path that does not resolve is prose.
        for raw_path in str(entry.get("raw_evidence_path", "")).split(";"):
            candidate = raw_path.strip()
            if candidate and not (REPO_ROOT / candidate).exists():
                problems.append(
                    f"{requirement_id}: raw evidence path {candidate!r} does not exist"
                )

    return problems


def record_evidence(
    state: dict[str, Any],
    *,
    requirement_id: str,
    status: str,
    exact_command: str,
    environment: str,
    observable_assertion: str,
    raw_evidence_path: str,
    tested_commit: str,
    remaining_risk: str = "",
    implementation_paths: list[str] | None = None,
    gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one requirement closure with its full evidence tuple.

    ``status`` may be any agent-authored status without a gate. ``VERIFIED`` is
    gate-authored: it requires ``gate`` to be a record produced by :func:`run_gate`
    that exited zero, and it requires ``raw_evidence_path`` to exist on disk.
    Passing ``VERIFIED`` without those raises rather than writing the word.
    """
    if status not in ALLOWED_STATUSES:
        raise LedgerError(f"status {status!r} is not one of {ALLOWED_STATUSES}")
    if requirement_id not in state.get("requirements", {}):
        raise LedgerError(f"unknown requirement id {requirement_id!r}")

    if status in GATE_AUTHORED_STATUSES:
        if gate is None:
            raise LedgerError(
                f"{requirement_id}: {status} is gate-authored and requires a gate result "
                f"from run_gate(). An implementation agent may write at most "
                f"IMPLEMENTED_NOT_VERIFIED. Allowed without a gate: {AGENT_AUTHORED_STATUSES}"
            )
        missing_gate = [f for f in REQUIRED_GATE_FIELDS if not str(gate.get(f, "")).strip()]
        if missing_gate:
            raise LedgerError(f"{requirement_id}: gate result is missing fields {missing_gate}")
        if gate.get("exit_status") != 0:
            raise LedgerError(
                f"{requirement_id}: cannot record {status} -- the gate exited "
                f"{gate.get('exit_status')!r}. Only a gate exiting 0 verifies a requirement."
            )
        for raw_path in str(raw_evidence_path).split(";"):
            candidate = raw_path.strip()
            if candidate and not (REPO_ROOT / candidate).exists():
                raise LedgerError(
                    f"{requirement_id}: raw evidence path {candidate!r} does not exist; "
                    "VERIFIED requires evidence on disk, not a path that reads plausibly"
                )

    state["requirements"][requirement_id]["status"] = status
    entry: dict[str, Any] = {
        "requirement_id": requirement_id,
        "status": status,
        "exact_command": exact_command,
        "environment": environment,
        "observable_assertion": observable_assertion,
        "raw_evidence_path": raw_evidence_path,
        "tested_commit": tested_commit,
        "tested_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "remaining_risk": remaining_risk,
        "implementation_paths": implementation_paths or [],
    }
    if gate is not None:
        entry["gate"] = gate
    state.setdefault("evidence", {})[requirement_id] = entry
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="validate ledger structure and evidence completeness; nonzero on any violation",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print a status count summary and the active requirement",
    )
    args = parser.parse_args(argv)

    state = load_state()

    if args.summary:
        counts: dict[str, int] = {}
        for record in state.get("requirements", {}).values():
            counts[record["status"]] = counts.get(record["status"], 0) + 1
        print(f"prod_status:          {state.get('prod_status')}")
        print(f"active_repository:    {state.get('active_repository')}")
        print(f"current_priority:     {state.get('current_priority')}")
        print(f"active_requirement:   {state.get('active_requirement_id')}")
        for status in ALLOWED_STATUSES:
            if counts.get(status):
                print(f"  {status:<26} {counts[status]}")

    if args.validate:
        problems = validate_state(state)
        if problems:
            print(f"[hunter-prod-state] FAIL -- {len(problems)} ledger violation(s):")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("[hunter-prod-state] PASS -- ledger structure and evidence completeness")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
