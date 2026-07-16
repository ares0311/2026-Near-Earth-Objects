"""Negative controls for Skills/verify_reliability_controls.py's freshness
logic (REL-03/REL-05/REL-09).

This sandboxed environment denies `git init`/`.git/config` writes both
outside the repository root and under pytest's own tmp_path fallback (a
real, confirmed constraint here -- not a design choice), so these tests
cannot spin up a real throwaway git repository. Instead they stub only the
`subprocess.run` I/O boundary inside `_git()` with controlled, exact
`rev-parse HEAD` / `status --porcelain` output, and exercise the REAL
freshness comparison logic in `check_freshness()`/`_current_git_state()`
against that controlled input -- the thing under test (stale/fresh
decision-making) is never mocked, only the external git process is.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_MODULE_PATH = Path(__file__).resolve().parents[1] / "Skills" / "verify_reliability_controls.py"
_spec = importlib.util.spec_from_file_location("verify_reliability_controls", _MODULE_PATH)
verify_reliability_controls = importlib.util.module_from_spec(_spec)
sys.modules["verify_reliability_controls"] = verify_reliability_controls
_spec.loader.exec_module(verify_reliability_controls)


def _fake_completed_process(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _patched_git(commit: str, porcelain: str):
    """Return a `subprocess.run` side_effect that answers `git rev-parse HEAD`
    with `commit` and `git status --porcelain` with `porcelain`, and raises
    for anything else -- so a test can never accidentally rely on an
    unstubbed real git call succeeding by coincidence."""

    def _side_effect(args, **kwargs):
        if args[:2] == ["git", "rev-parse"]:
            return _fake_completed_process(commit + "\n")
        if args[:2] == ["git", "status"]:
            return _fake_completed_process(porcelain)
        raise AssertionError(f"unexpected git invocation in test: {args}")

    return _side_effect


def _write_record(root: Path, *, commit: str, dirty: bool, all_passed: bool) -> Path:
    record_path = root / "reliability_verification.json"
    record_path.write_text(
        json.dumps(
            {
                "schema_version": "reliability-verification-v1",
                "git_commit": commit,
                "git_dirty": dirty,
                "checked_at_utc": "2026-07-16T00:00:00+00:00",
                "checks": {
                    "pytest": {
                        "passed": all_passed,
                        "status": "PASS" if all_passed else "FAIL",
                    }
                },
                "all_passed": all_passed,
            }
        )
    )
    return record_path


_COMMIT_A = "a" * 40
_COMMIT_B = "b" * 40


def test_known_good_matching_clean_commit_is_current(tmp_path, capsys):
    """known-good -> PASS: record's commit matches HEAD exactly, tree is clean, and
    the recorded run itself passed."""
    record_path = _write_record(tmp_path, commit=_COMMIT_A, dirty=False, all_passed=True)
    with patch("subprocess.run", side_effect=_patched_git(_COMMIT_A, "")):
        result = verify_reliability_controls.check_freshness(
            root=tmp_path, record_path=record_path
        )
    assert result is True
    assert "CURRENT AND VERIFIED" in capsys.readouterr().out


def test_no_record_is_not_current(tmp_path, capsys):
    """known-good (for a fresh repo with nothing verified yet) -> the absence of a
    record must read as 'not verified', never as a silent pass. No git call should
    even be needed to reach this conclusion."""
    missing_path = tmp_path / "does_not_exist.json"
    with patch("subprocess.run", side_effect=AssertionError("git should not be called")):
        result = verify_reliability_controls.check_freshness(
            root=tmp_path, record_path=missing_path
        )
    assert result is False
    assert "NO VERIFICATION RECORD" in capsys.readouterr().err


def test_known_bad_commit_changed_after_recording_is_stale(tmp_path, capsys):
    """known-bad -> FAIL: relevant code changed (HEAD moved to a new real commit)
    after the verification record was written -- REL-05's core 'stale result is not
    current evidence' case."""
    record_path = _write_record(tmp_path, commit=_COMMIT_A, dirty=False, all_passed=True)
    with patch("subprocess.run", side_effect=_patched_git(_COMMIT_B, "")):
        result = verify_reliability_controls.check_freshness(
            root=tmp_path, record_path=record_path
        )
    assert result is False
    assert "does not match current" in capsys.readouterr().err


def test_known_bad_uncommitted_changes_now_is_stale(tmp_path, capsys):
    """known-bad -> FAIL: the commit still matches, but the working tree now has
    uncommitted changes -- REL-05's 'account accurately for uncommitted changes'."""
    record_path = _write_record(tmp_path, commit=_COMMIT_A, dirty=False, all_passed=True)
    with patch("subprocess.run", side_effect=_patched_git(_COMMIT_A, " M src/fetch.py\n")):
        result = verify_reliability_controls.check_freshness(
            root=tmp_path, record_path=record_path
        )
    assert result is False
    assert "uncommitted changes right now" in capsys.readouterr().err


def test_known_bad_record_itself_was_dirty_is_stale(tmp_path, capsys):
    """known-bad -> FAIL: even if everything matches now, a record written against a
    dirty tree never represented a real, reproducible, committed state."""
    record_path = _write_record(tmp_path, commit=_COMMIT_A, dirty=True, all_passed=True)
    with patch("subprocess.run", side_effect=_patched_git(_COMMIT_A, "")):
        result = verify_reliability_controls.check_freshness(
            root=tmp_path, record_path=record_path
        )
    assert result is False
    assert "recorded run itself was against a dirty" in capsys.readouterr().err


def test_current_but_failed_is_not_verified(tmp_path, capsys):
    """A fresh, exactly-matching record whose checks did NOT all pass must read as
    'IMPLEMENTED BUT NOT VERIFIED', never as VERIFIED -- REL-03's core distinction."""
    record_path = _write_record(tmp_path, commit=_COMMIT_A, dirty=False, all_passed=False)
    with patch("subprocess.run", side_effect=_patched_git(_COMMIT_A, "")):
        result = verify_reliability_controls.check_freshness(
            root=tmp_path, record_path=record_path
        )
    assert result is False
    assert "NOT VERIFIED" in capsys.readouterr().err


def test_malformed_unsupported_schema_version_is_stale_loudly(tmp_path, capsys):
    """malformed -> FAIL LOUDLY: a record from a future/incompatible schema must
    never be silently accepted as if it were the current format. No git call is
    even needed once the schema check fails."""
    record_path = tmp_path / "reliability_verification.json"
    record_path.write_text(
        json.dumps({"schema_version": "some-other-schema-v99", "git_commit": _COMMIT_A})
    )
    with patch("subprocess.run", side_effect=AssertionError("git should not be called")):
        result = verify_reliability_controls.check_freshness(
            root=tmp_path, record_path=record_path
        )
    assert result is False
    assert "unsupported schema_version" in capsys.readouterr().err


def test_current_git_state_parses_clean_and_dirty_correctly():
    """Independent-oracle check on _current_git_state's own parsing logic: given
    exact, controlled subprocess output, the dirty flag must reflect exactly
    whether `git status --porcelain` produced any output at all."""
    with patch("subprocess.run", side_effect=_patched_git(_COMMIT_A, "")):
        commit, dirty = verify_reliability_controls._current_git_state(Path("/irrelevant"))
    assert commit == _COMMIT_A
    assert dirty is False

    with patch("subprocess.run", side_effect=_patched_git(_COMMIT_A, "?? new_file.py\n")):
        _, dirty_when_untracked_file_present = verify_reliability_controls._current_git_state(
            Path("/irrelevant")
        )
    assert dirty_when_untracked_file_present is True
