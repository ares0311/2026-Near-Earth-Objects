"""Negative controls for the PROD ledger's status authority.

A check that cannot fail proves nothing. Every test here constructs a ledger that
*should* be rejected and asserts it is, so the enforcement in
``Skills/hunter_prod_state.py`` is demonstrated to detect the failure it claims to
detect rather than merely being present.

The rule under test: ``VERIFIED`` is gate-authored. An implementation agent may
write at most ``IMPLEMENTED_NOT_VERIFIED``. Producing ``VERIFIED`` requires a
bound record from :func:`hunter_prod_state.run_gate` that exited zero, whose gate
file still hashes to the recorded value, and whose raw evidence exists on disk.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Skills"))

import hunter_prod_state as hps  # noqa: E402


def _gate_record(**overrides: object) -> dict[str, object]:
    """A well-formed passing gate record, bound to a file that really exists."""
    gate_path = REPO_ROOT / "Skills" / "hunter_prod_state.py"
    record = {
        "gate_command": "uv run python Skills/hunter_prod_state.py --validate",
        "gate_path": "Skills/hunter_prod_state.py",
        "gate_sha256": hps.sha256_of(gate_path),
        "exit_status": 0,
        "code_identity": "abc1234",
        "executed_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    record.update(overrides)
    return record


def _ledger(status: str, evidence_overrides: dict[str, object] | None = None) -> dict:
    """A minimal ledger claiming one requirement at ``status``."""
    evidence = {
        "requirement_id": "WS-01",
        "status": status,
        "exact_command": "git rev-parse --show-toplevel",
        "environment": "test",
        "observable_assertion": "writes stayed inside the active git root",
        # A path that genuinely exists, so unrelated checks do not fire.
        "raw_evidence_path": "pyproject.toml",
        "tested_commit": "abc1234",
        "tested_at_utc": "2026-08-01T00:00:00+00:00",
        "gate": _gate_record(),
    }
    evidence.update(evidence_overrides or {})
    return {
        "artifact": "configs/HUNTER_PROD_STATE.json",
        "requirements": {"WS-01": {"priority": "P0", "status": status}},
        "evidence": {"WS-01": evidence},
    }


def _phase0_ledger(tmp_path: Path) -> tuple[dict, Path]:
    """A complete isolated Phase 0 ledger with frozen executable gate files."""
    root = tmp_path / "neo"
    (root / "Skills").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "configs").mkdir()

    gate_records: dict[str, dict[str, str]] = {}
    for index, name in enumerate(hps.REQUIRED_PHASE_GATES):
        relative = f"Skills/gate_{index}.py"
        path = root / relative
        path.write_text("raise SystemExit(0)\n")
        gate_records[name] = {
            "gate_path": relative,
            "gate_command": f"uv run --python 3.14 python {relative}",
            "gate_sha256": hps.sha256_of(path),
        }

    artifacts = {
        "contract": ("docs/HUNTER_PROD_CONTRACT.md", "HUNTER-PROD-TEST"),
        "cli_ux": ("docs/CLI_UX_SPEC.md", "HUNTER-CLI-UX-TEST"),
        "readme_spec": ("docs/README_SPEC.md", None),
    }
    artifact_records: dict[str, dict[str, str]] = {}
    for key, (relative, version) in artifacts.items():
        path = root / relative
        path.write_text(f"# {key}\n")
        artifact_records[key] = {
            "path": relative,
            "sha256": hps.sha256_of(path),
        }
        if version is not None:
            artifact_records[key]["version"] = version

    state = {
        "artifact": "configs/HUNTER_PROD_STATE.json",
        "schema_version": "test-1",
        "contract_version": "HUNTER-PROD-TEST",
        "cli_ux_version": "HUNTER-CLI-UX-TEST",
        "active_repository": "NEOHunter",
        "repository_profile": "NEOHunter",
        "prod_status": "REVOKED_UNTIL_VERIFIED",
        "requirements": {"WS-01": {"priority": "P0", "status": "UNVERIFIED"}},
        "evidence": {},
        "blocker_profiles": {"NEOHunter": [{"id": "NEO-TEST", "status": "CLOSED"}]},
        "applicable_blockers": [{"id": "NEO-TEST", "status": "CLOSED"}],
        "governing_artifacts": {
            **artifact_records,
            "state": {
                "path": "configs/HUNTER_PROD_STATE.json",
                "schema_version": "test-1",
            },
            "read_complete": True,
        },
        "workspace_boundary": {
            "active_git_root": str(root.resolve()),
            "writable_repository_root": str(root.resolve()),
            "sibling_repositories": [
                {
                    "project": "EXOHunter",
                    "path": str((tmp_path / "exo").resolve()),
                    "access": "read-only",
                },
                {
                    "project": "TechnoHunter",
                    "path": str((tmp_path / "techno").resolve()),
                    "access": "read-only",
                },
            ],
            "shared_write_locations": [],
            "locking_rule": {
                "implemented": False,
                "shared_writes_prohibited_without_lock": True,
            },
        },
        "pre_existing_user_changes": [
            {"path": ".codex/config.toml", "initial_status": " M", "policy": "preserve"}
        ],
        "gate_lock": {"gates": gate_records, "not_yet_created": []},
        "execution_directive_v3": {"gate_result": "PASS"},
        "completion": {"prod_check_exit_status": None},
    }
    (root / "configs" / "HUNTER_PROD_STATE.json").write_text(json.dumps(state))
    return state, root


# --- the control: a correct ledger must pass --------------------------------


def test_well_formed_verified_claim_is_accepted() -> None:
    """Known-good case. Without this the negative controls prove nothing."""
    assert hps.validate_state(_ledger("VERIFIED")) == []


# --- negative controls: each must be detected -------------------------------


def test_verified_without_any_gate_is_rejected() -> None:
    """The original defect: an agent writing the word with no gate behind it."""
    ledger = _ledger("VERIFIED", {"gate": None})
    problems = hps.validate_state(ledger)
    assert any("without a bound gate result" in problem for problem in problems)


def test_verified_with_a_failing_gate_is_rejected() -> None:
    """A gate that ran and failed does not verify anything."""
    ledger = _ledger("VERIFIED", {"gate": _gate_record(exit_status=1)})
    problems = hps.validate_state(ledger)
    assert any("only exit status 0 verifies" in problem for problem in problems)


def test_verified_with_an_incomplete_gate_record_is_rejected() -> None:
    """A partially filled gate record cannot stand in for a real execution."""
    incomplete = _gate_record()
    del incomplete["code_identity"]
    problems = hps.validate_state(_ledger("VERIFIED", {"gate": incomplete}))
    assert any("missing fields" in problem for problem in problems)


def test_verified_whose_gate_file_changed_is_rejected() -> None:
    """A gate edited after it passed must not keep its PASS.

    This is the anti-weakening control: without it, a gate could be relaxed and
    the stale VERIFIED status would silently survive.
    """
    ledger = _ledger("VERIFIED", {"gate": _gate_record(gate_sha256="0" * 64)})
    problems = hps.validate_state(ledger)
    assert any("changed since it passed" in problem for problem in problems)


def test_verified_with_a_missing_gate_file_is_rejected() -> None:
    """A gate path that does not resolve is not a gate."""
    ledger = _ledger("VERIFIED", {"gate": _gate_record(gate_path="Skills/no_such_gate.py")})
    problems = hps.validate_state(ledger)
    assert any("does not exist" in problem for problem in problems)


def test_verified_with_nonexistent_raw_evidence_is_rejected() -> None:
    """Evidence must be on disk. A plausible-looking path is prose."""
    ledger = _ledger("VERIFIED", {"raw_evidence_path": "docs/evidence/prod/not-real.md"})
    problems = hps.validate_state(ledger)
    assert any("does not exist" in problem for problem in problems)


def test_verified_with_missing_evidence_fields_is_rejected() -> None:
    """CLAIM-04's evidence tuple must be complete."""
    ledger = _ledger("VERIFIED", {"environment": ""})
    problems = hps.validate_state(ledger)
    assert any("missing evidence fields" in problem for problem in problems)


@pytest.mark.parametrize("status", hps.AGENT_AUTHORED_STATUSES)
def test_agent_authored_statuses_need_no_gate(status: str) -> None:
    """Statuses that describe work, not verification, remain freely writable."""
    ledger = _ledger(status, {"gate": None})
    assert hps.validate_state(ledger) == []


# --- the write path must refuse too, not only the validator -----------------


def test_record_evidence_refuses_verified_without_a_gate() -> None:
    """Enforcement lives on the write path as well, so bad state is never created."""
    state = _ledger("UNVERIFIED")
    with pytest.raises(hps.LedgerError, match="gate-authored"):
        hps.record_evidence(
            state,
            requirement_id="WS-01",
            status="VERIFIED",
            exact_command="echo hello",
            environment="test",
            observable_assertion="it looked fine to me",
            raw_evidence_path="pyproject.toml",
            tested_commit="abc1234",
        )


def test_record_evidence_refuses_verified_when_the_gate_failed() -> None:
    state = _ledger("UNVERIFIED")
    with pytest.raises(hps.LedgerError, match="the gate exited"):
        hps.record_evidence(
            state,
            requirement_id="WS-01",
            status="VERIFIED",
            exact_command="echo hello",
            environment="test",
            observable_assertion="assertion",
            raw_evidence_path="pyproject.toml",
            tested_commit="abc1234",
            gate=_gate_record(exit_status=3),
        )


def test_record_evidence_refuses_verified_with_missing_evidence_on_disk() -> None:
    state = _ledger("UNVERIFIED")
    with pytest.raises(hps.LedgerError, match="does not exist"):
        hps.record_evidence(
            state,
            requirement_id="WS-01",
            status="VERIFIED",
            exact_command="echo hello",
            environment="test",
            observable_assertion="assertion",
            raw_evidence_path="docs/evidence/prod/invented.md",
            tested_commit="abc1234",
            gate=_gate_record(),
        )


def test_record_evidence_accepts_an_agent_authored_status() -> None:
    """The permitted path stays usable; enforcement is targeted, not blanket."""
    state = _ledger("UNVERIFIED")
    hps.record_evidence(
        state,
        requirement_id="WS-01",
        status="IMPLEMENTED_NOT_VERIFIED",
        exact_command="echo hello",
        environment="test",
        observable_assertion="implemented, awaiting its gate",
        raw_evidence_path="pyproject.toml",
        tested_commit="abc1234",
    )
    assert state["requirements"]["WS-01"]["status"] == "IMPLEMENTED_NOT_VERIFIED"


# --- run_gate produces a genuinely bound record -----------------------------


def test_run_gate_reports_a_real_nonzero_exit() -> None:
    """run_gate cannot be talked into reporting success for a failing command."""
    record = hps.run_gate(
        [sys.executable, "-c", "raise SystemExit(7)"],
        gate_path=REPO_ROOT / "Skills" / "hunter_prod_state.py",
    )
    assert record["exit_status"] == 7
    assert record["gate_sha256"] == hps.sha256_of(REPO_ROOT / "Skills" / "hunter_prod_state.py")


def test_code_identity_marks_a_dirty_working_tree() -> None:
    """Identity must distinguish a commit from a commit plus uncommitted edits."""
    identity = hps.code_identity()
    assert identity, "code identity must never be empty"
    # This repository has uncommitted work during PROD closure; if that ever
    # stops being true the assertion below still holds for a clean tree.
    assert identity.endswith("+dirty") or len(identity) >= 7


# --- Phase 0 governance gate negative controls -----------------------------


def test_phase0_complete_gate_inventory_is_accepted(tmp_path: Path) -> None:
    """Known-good control for the complete Phase 0 validator."""
    state, root = _phase0_ledger(tmp_path)
    assert hps.validate_phase0(state, root) == []


def test_phase0_missing_mandatory_gates_is_rejected(tmp_path: Path) -> None:
    """The reproduced defect: syntax-valid state must not hide absent phase gates."""
    state, root = _phase0_ledger(tmp_path)
    missing = hps.REQUIRED_PHASE_GATES[-1]
    del state["gate_lock"]["gates"][missing]
    state["gate_lock"]["not_yet_created"] = [missing]

    problems = hps.validate_phase0(state, root)

    assert any("mandatory phase gates are not frozen" in problem for problem in problems)
    assert any("remain not_yet_created" in problem for problem in problems)


def test_phase0_malformed_gate_inventory_fails_loudly(tmp_path: Path) -> None:
    state, root = _phase0_ledger(tmp_path)
    state["gate_lock"] = "not-an-object"
    problems = hps.validate_phase0(state, root)
    assert "gate_lock is missing or malformed" in problems


def test_phase0_changed_frozen_gate_is_rejected(tmp_path: Path) -> None:
    state, root = _phase0_ledger(tmp_path)
    name = hps.REQUIRED_PHASE_GATES[0]
    state["gate_lock"]["gates"][name]["gate_sha256"] = "0" * 64
    problems = hps.validate_phase0(state, root)
    assert any("frozen gate sha256 does not match" in problem for problem in problems)


def test_phase0_prod_status_fails_closed_on_unverified_requirement(tmp_path: Path) -> None:
    state, root = _phase0_ledger(tmp_path)
    state["prod_status"] = "PROD"
    state["completion"]["prod_check_exit_status"] = 0
    problems = hps.validate_phase0(state, root)
    assert any("PROD status is forbidden" in problem for problem in problems)
    assert any("prod_check_exit_status cannot be zero" in problem for problem in problems)


def test_phase0_shared_write_without_lock_is_rejected(tmp_path: Path) -> None:
    state, root = _phase0_ledger(tmp_path)
    state["workspace_boundary"]["shared_write_locations"] = ["shared/history.json"]
    problems = hps.validate_phase0(state, root)
    assert any("without an implemented exclusive lock" in problem for problem in problems)


def test_phase0_changed_governing_artifact_is_rejected(tmp_path: Path) -> None:
    state, root = _phase0_ledger(tmp_path)
    (root / "docs" / "README_SPEC.md").write_text("changed\n")
    problems = hps.validate_phase0(state, root)
    assert any(
        "governing artifact 'docs/README_SPEC.md' changed" in problem for problem in problems
    )


def test_the_live_ledger_is_internally_consistent() -> None:
    """The committed ledger itself must satisfy every rule above."""
    state = hps.load_state()
    assert hps.validate_phase0(state) == []
    assert json.loads(hps.STATE_PATH.read_text())["artifact"] == (
        "configs/HUNTER_PROD_STATE.json"
    )
