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

# Every executable acceptance surface required by the fixed PROD-closure phase
# sequence. Phase 6 has a dedicated restart/resume gate in addition to the
# repository-native aggregate PROD gate because restart/resume is a mandatory
# black-box stage and cannot be inferred from the aggregate runner's presence.
REQUIRED_PHASE_GATES = (
    "phase-0-governance",
    "phase-1-installed-launch",
    "phase-2-installed-pty-operator",
    "phase-3-canonical-pipeline",
    "phase-4-adaptive-discovery-and-frozen-manifest",
    "phase-5-real-data-new-and-follow-up",
    "phase-6-restart-resume",
    "phase-6-repository-native-prod",
    "phase-7-readme-conformance",
)

GOVERNING_ARTIFACTS = {
    "contract": "docs/HUNTER_PROD_CONTRACT.md",
    "cli_ux": "docs/CLI_UX_SPEC.md",
    "state": "configs/HUNTER_PROD_STATE.json",
    "readme_spec": "docs/README_SPEC.md",
}

PROD_STATUSES = frozenset({"PROD", "PROD_ACCEPTED"})
GATE_RESULTS = frozenset({"PASS", "FAIL", "NOT_EXECUTED", "UNKNOWN"})


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


def _validate_governing_artifacts(
    state: dict[str, Any], repo_root: Path,
) -> list[str]:
    """Validate the four governing artifacts and their frozen identities."""
    problems: list[str] = []
    records = state.get("governing_artifacts")
    if not isinstance(records, dict):
        return ["governing_artifacts must record all four governing files"]

    for key, relative in GOVERNING_ARTIFACTS.items():
        record = records.get(key)
        if not isinstance(record, dict):
            problems.append(f"governing_artifacts.{key} is missing or malformed")
            continue
        if record.get("path") != relative:
            problems.append(
                f"governing_artifacts.{key}.path must be {relative!r}, "
                f"found {record.get('path')!r}"
            )
        path = repo_root / relative
        if not path.is_file():
            problems.append(f"governing artifact is missing: {relative}")
            continue
        if key != "state":
            expected_hash = str(record.get("sha256", "")).strip()
            if not expected_hash:
                problems.append(f"governing_artifacts.{key}.sha256 is missing")
            elif sha256_of(path) != expected_hash:
                problems.append(
                    f"governing artifact {relative!r} changed since startup "
                    "(sha256 mismatch)"
                )
        if key in {"contract", "cli_ux", "readme_spec"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if text.lstrip().startswith("{\\rtf"):
                problems.append(f"governing artifact is RTF content, not Markdown: {relative}")

    if records.get("contract", {}).get("version") != state.get("contract_version"):
        problems.append("governing contract version does not match contract_version")
    if records.get("cli_ux", {}).get("version") != state.get("cli_ux_version"):
        problems.append("CLI/UX specification version does not match cli_ux_version")
    if records.get("state", {}).get("schema_version") != state.get("schema_version"):
        problems.append("state artifact schema version does not match schema_version")
    if records.get("read_complete") is not True:
        problems.append("all four governing artifacts are not recorded as completely read")
    return problems


def _validate_workspace_boundary(state: dict[str, Any], repo_root: Path) -> list[str]:
    """Enforce one writable repository and an explicit shared-write policy."""
    problems: list[str] = []
    boundary = state.get("workspace_boundary")
    if not isinstance(boundary, dict):
        return ["workspace_boundary is missing or malformed"]

    expected_root = str(repo_root.resolve())
    if boundary.get("active_git_root") != expected_root:
        problems.append(
            "workspace_boundary.active_git_root does not match the executing repository"
        )
    if boundary.get("writable_repository_root") != expected_root:
        problems.append("exactly the active Git root must be the writable repository")
    if (
        state.get("active_repository") != "NEOHunter"
        or state.get("repository_profile") != "NEOHunter"
    ):
        problems.append("active repository and blocker profile must both be NEOHunter")

    siblings = boundary.get("sibling_repositories")
    if not isinstance(siblings, list) or len(siblings) != 2:
        problems.append("workspace_boundary must identify exactly two sibling repositories")
    else:
        for sibling in siblings:
            if not isinstance(sibling, dict):
                problems.append("sibling repository records must be objects")
                continue
            path_text = str(sibling.get("path", "")).strip()
            if sibling.get("access") != "read-only":
                problems.append(f"sibling repository is not read-only: {path_text!r}")
            if not path_text:
                problems.append("sibling repository path is missing")
                continue
            path = Path(path_text).resolve()
            try:
                path.relative_to(repo_root.resolve())
            except ValueError:
                pass
            else:
                problems.append(f"sibling repository resolves inside active root: {path}")

    shared_writes = boundary.get("shared_write_locations")
    locking = boundary.get("locking_rule")
    if not isinstance(shared_writes, list):
        problems.append("shared_write_locations must be an explicit list")
    if not isinstance(locking, dict):
        problems.append("locking_rule is missing or malformed")
    elif shared_writes:
        if locking.get("implemented") is not True or not locking.get("lock_path"):
            problems.append(
                "shared writes are configured without an implemented exclusive lock"
            )
    elif locking.get("shared_writes_prohibited_without_lock") is not True:
        problems.append(
            "the no-shared-write state must fail closed until a lock contract exists"
        )

    changes = state.get("pre_existing_user_changes")
    if not isinstance(changes, list) or not changes:
        problems.append("pre_existing_user_changes must preserve the startup worktree snapshot")
    else:
        for entry in changes:
            if not isinstance(entry, dict):
                problems.append("pre-existing change records must be objects")
                continue
            if not str(entry.get("path", "")).strip() or not str(
                entry.get("initial_status", "")
            ).strip():
                problems.append("pre-existing change record lacks path or initial_status")
            if entry.get("policy") != "preserve":
                problems.append(
                    f"pre-existing change is not marked preserve: {entry.get('path')!r}"
                )
    return problems


def _validate_gate_lock(state: dict[str, Any], repo_root: Path) -> list[str]:
    """Require every phase gate to exist and still match its frozen hash."""
    problems: list[str] = []
    lock = state.get("gate_lock")
    if not isinstance(lock, dict):
        return ["gate_lock is missing or malformed"]
    gates = lock.get("gates")
    if not isinstance(gates, dict):
        return ["gate_lock.gates is missing or malformed"]

    missing = [name for name in REQUIRED_PHASE_GATES if name not in gates]
    if missing:
        problems.append(f"mandatory phase gates are not frozen: {missing}")
    not_created = lock.get("not_yet_created")
    if not isinstance(not_created, list):
        problems.append("gate_lock.not_yet_created must be a list")
    elif not_created:
        problems.append(f"mandatory phase gates remain not_yet_created: {not_created}")

    for name in REQUIRED_PHASE_GATES:
        record = gates.get(name)
        if not isinstance(record, dict):
            continue
        gate_path_text = str(record.get("gate_path", "")).strip()
        gate_command = str(record.get("gate_command", "")).strip()
        expected_hash = str(record.get("gate_sha256", "")).strip()
        if not gate_path_text or not gate_command or not expected_hash:
            problems.append(f"{name}: gate path, command, and sha256 are required")
            continue
        gate_path = (repo_root / gate_path_text).resolve()
        try:
            gate_path.relative_to(repo_root.resolve())
        except ValueError:
            problems.append(f"{name}: gate path resolves outside the active repository")
            continue
        if not gate_path.is_file():
            problems.append(f"{name}: gate file does not exist: {gate_path_text}")
        elif sha256_of(gate_path) != expected_hash:
            problems.append(f"{name}: frozen gate sha256 does not match {gate_path_text}")
    return problems


def _validate_prod_fail_closed(state: dict[str, Any]) -> list[str]:
    """A mandatory unknown/failure may never coexist with PROD status."""
    problems: list[str] = []
    requirements = state.get("requirements", {})
    incomplete = sorted(
        requirement_id
        for requirement_id, record in requirements.items()
        if record.get("status") != "VERIFIED"
    )
    blockers = [
        str(record.get("id", "unknown"))
        for record in state.get("applicable_blockers", [])
        if record.get("status") == "BLOCKING"
    ]
    execution = state.get("execution_directive_v3", {})
    gate_result = execution.get("gate_result")
    if gate_result is not None and gate_result not in GATE_RESULTS:
        problems.append(f"execution gate_result is not recognized: {gate_result!r}")

    if state.get("prod_status") in PROD_STATUSES and (incomplete or blockers):
        problems.append(
            "PROD status is forbidden while mandatory requirements or blockers remain: "
            f"requirements={incomplete[:5]}, blockers={blockers}"
        )
    completion = state.get("completion", {})
    if completion.get("prod_check_exit_status") == 0 and (incomplete or blockers):
        problems.append(
            "prod_check_exit_status cannot be zero while mandatory requirements "
            "or blockers remain"
        )
    if gate_result in {"FAIL", "NOT_EXECUTED", "UNKNOWN"} and state.get(
        "prod_status"
    ) in PROD_STATUSES:
        problems.append(f"PROD status is forbidden after mandatory gate result {gate_result}")
    return problems


def validate_phase0(state: dict[str, Any], repo_root: Path = REPO_ROOT) -> list[str]:
    """Validate every Phase 0 pass criterion, not only ledger syntax."""
    problems = validate_state(state)
    problems.extend(_validate_governing_artifacts(state, repo_root))
    problems.extend(_validate_workspace_boundary(state, repo_root))
    problems.extend(_validate_gate_lock(state, repo_root))
    problems.extend(_validate_prod_fail_closed(state))

    profile_ids = {
        str(record.get("id")) for record in state.get("blocker_profiles", {}).get("NEOHunter", [])
    }
    applicable_ids = {str(record.get("id")) for record in state.get("applicable_blockers", [])}
    if not applicable_ids or applicable_ids != profile_ids:
        problems.append(
            "applicable blocker profile does not exactly match blocker_profiles.NEOHunter"
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
        problems = validate_phase0(state)
        if problems:
            print(f"[hunter-prod-state] FAIL -- {len(problems)} Phase 0 violation(s):")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print("[hunter-prod-state] PASS -- ledger structure and evidence completeness")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
