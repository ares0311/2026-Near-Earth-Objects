#!/usr/bin/env python
"""REL-09 -- adversarial verification workflow.

Runs every negative-control test module for this project's reliability
controls (directive parity, incomplete-implementation scanning, silent-
exception scanning, and verification freshness) and reports a clear
PASS/FAIL summary per control category, proving each critical check can
actually detect the failure it claims to detect -- not just pass on an
already-clean repository.

Every underlying test uses a pytest `tmp_path` fixture (a real, throwaway
filesystem directory pytest creates and destroys automatically) or a real,
throwaway `git init` repo under `tmp_path` for the freshness controls. None
of them touch this repository's actual tracked files, so there is nothing
to "restore" afterward -- isolation is structural, not achieved by
mutate-then-revert. This script's own final step re-runs `git status
--porcelain` against the real repo and asserts it is unchanged by this run,
as a belt-and-suspenders confirmation of that isolation guarantee.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_ADVERSARIAL_TEST_MODULES = [
    "tests/test_check_directive_parity.py",
    "tests/test_check_incomplete_implementations.py",
    "tests/test_check_silent_exceptions.py",
    "tests/test_verify_reliability_controls.py",
]


def _git_status_porcelain() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def main() -> int:
    before = _git_status_porcelain()

    print("=== Adversarial verification: negative-control test suites ===")
    print(f"Modules: {', '.join(_ADVERSARIAL_TEST_MODULES)}\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", *_ADVERSARIAL_TEST_MODULES],
        cwd=_REPO_ROOT,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    tests_passed = result.returncode == 0

    after = _git_status_porcelain()
    repo_unchanged = before == after

    print("\n" + "=" * 72)
    print(f"  [{'PASS' if tests_passed else 'FAIL'}] all negative-control tests passed")
    print(
        f"  [{'PASS' if repo_unchanged else 'FAIL'}] repository working tree unchanged by this run"
    )
    print("=" * 72)

    if not repo_unchanged:
        print(
            "FAIL LOUDLY: this adversarial run left the working tree in a different state "
            "than before it started -- that violates the isolation guarantee every negative "
            "control here depends on. Diff:",
            file=sys.stderr,
        )
        print(after, file=sys.stderr)

    all_ok = tests_passed and repo_unchanged
    if all_ok:
        print("\n[adversarial-verification] PASS -- every critical control demonstrated it "
              "can detect the failure it claims to detect, and the repo is untouched.")
    else:
        print("\n[adversarial-verification] FAIL", file=sys.stderr)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
