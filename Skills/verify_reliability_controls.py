#!/usr/bin/env python
"""REL-10 -- the one canonical verification entry point.

Normal usage (run all mandatory checks against the current repository):

    UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \\
        Skills/verify_reliability_controls.py

Runs, in order: directive parity + Claude/Codex exposure (REL-04), the
new-silent-exception gate (REL-01), the incomplete-implementation scan
(REL-02/REL-08), `ruff check .` (REL-07), `mypy src` (REL-07), and the full
`pytest` suite with the existing 100%-coverage gate (REL-06/REL-07). Exits
non-zero if ANY mandatory check fails -- this script is itself the concrete
enforcement of "mandatory failures propagate to a non-zero final status."

On a fully clean run it writes a freshness record
(Logs/reports/reliability_verification.json) binding the PASS result to the
exact git commit and working-tree cleanliness it was run against (REL-05).

    --check-freshness   Don't run anything; just report whether the last
                         recorded verification result is still current for
                         the repository's present git state (REL-03/REL-05).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FRESHNESS_RECORD_PATH = _REPO_ROOT / "Logs" / "reports" / "reliability_verification.json"
_SCHEMA_VERSION = "reliability-verification-v1"

# Native-library thread isolation for the pytest stage: this project's own
# CLAUDE.md/SYSTEM_PROFILE.md document that XGBoost/OpenMP can crash
# (segfault) on macOS local runs without single-threaded native libraries
# and PYTHONPATH=src set explicitly. Root-caused live during this file's own
# first dogfooding run (plain `pytest` segfaulted at ~10% here) -- this is
# the fix, not a workaround.
_PYTEST_ENV_OVERRIDES = {
    "PYTHONPATH": "src",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_MAX_THREADS": "1",
}


def _git(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _current_git_state(root: Path) -> tuple[str, bool]:
    """Return (HEAD commit sha, is_dirty). is_dirty is True if `git status
    --porcelain` reports anything at all -- any uncommitted change, not just
    changes to files a specific check happens to touch, per REL-05's
    "Account accurately for uncommitted changes." Parameterized by `root`
    (rather than hardcoded to this repo) so freshness logic can be exercised
    against a real, throwaway git fixture in tests."""
    commit = _git(root, ["rev-parse", "HEAD"])
    dirty = bool(_git(root, ["status", "--porcelain"]))
    return commit, dirty


def _run_check(
    name: str, command: list[str], extra_env: dict[str, str] | None = None
) -> tuple[bool, str]:
    """Run one subprocess check, printing its output live (fail loudly: the
    operator sees exactly what failed, not just a pass/fail bit)."""
    print(f"\n=== [{name}] {' '.join(command)} ===", flush=True)
    env = {**os.environ, **extra_env} if extra_env else None
    result = subprocess.run(command, cwd=_REPO_ROOT, env=env)
    passed = result.returncode == 0
    status = "PASS" if passed else f"FAIL (exit {result.returncode})"
    print(f"=== [{name}] {status} ===", flush=True)
    return passed, status


def run_normal_verification() -> bool:
    checks: list[tuple[str, list[str], dict[str, str] | None]] = [
        ("directive_parity", [sys.executable, "Skills/check_directive_parity.py"], None),
        ("silent_exceptions", [sys.executable, "Skills/check_silent_exceptions.py"], None),
        (
            "incomplete_implementations",
            [sys.executable, "Skills/check_incomplete_implementations.py"],
            None,
        ),
        ("ruff", [sys.executable, "-m", "ruff", "check", "."], None),
        ("mypy", [sys.executable, "-m", "mypy", "src"], None),
        (
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--cov=src",
                "--cov-report=term-missing",
                "--cov-fail-under=100",
            ],
            _PYTEST_ENV_OVERRIDES,
        ),
    ]

    results: dict[str, dict] = {}
    all_passed = True
    for name, command, extra_env in checks:
        passed, status = _run_check(name, command, extra_env)
        results[name] = {"passed": passed, "status": status}
        all_passed = all_passed and passed

    print("\n" + "=" * 72)
    for name, result in results.items():
        marker = "PASS" if result["passed"] else "FAIL"
        print(f"  [{marker}] {name}")
    print("=" * 72)

    commit, dirty = _current_git_state(_REPO_ROOT)
    record = {
        "schema_version": _SCHEMA_VERSION,
        "git_commit": commit,
        "git_dirty": dirty,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "checks": results,
        "all_passed": all_passed,
    }
    _FRESHNESS_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    _FRESHNESS_RECORD_PATH.write_text(json.dumps(record, indent=2))
    print(f"\nFreshness record written: {_FRESHNESS_RECORD_PATH}")
    if dirty:
        print(
            "WARNING: working tree has uncommitted changes -- this result will read as "
            "STALE the moment it is checked again, per REL-05.",
            flush=True,
        )

    if all_passed:
        print(f"\n[verify-reliability-controls] PASS -- all {len(checks)} checks passed.")
    else:
        failed = [name for name, r in results.items() if not r["passed"]]
        print(
            f"\n[verify-reliability-controls] FAIL -- {len(failed)} check(s) failed: "
            f"{', '.join(failed)}",
            file=sys.stderr,
        )
    return all_passed


def check_freshness(root: Path | None = None, record_path: Path | None = None) -> bool:
    """REL-03/REL-05: report whether the last recorded verification result
    is still current. Returns True only if a record exists, matches the
    current commit exactly, the tree was (and still would need to be)
    clean, and every check in that record passed. `root`/`record_path`
    default to this repository but are parameterized so tests can exercise
    the logic against a real, throwaway git fixture instead."""
    root = root if root is not None else _REPO_ROOT
    record_path = record_path if record_path is not None else _FRESHNESS_RECORD_PATH

    if not record_path.exists():
        print(
            "[freshness] NO VERIFICATION RECORD -- run Skills/verify_reliability_controls.py "
            "before claiming VERIFIED status.",
            file=sys.stderr,
        )
        return False

    record = json.loads(record_path.read_text())
    if record.get("schema_version") != _SCHEMA_VERSION:
        print(
            f"[freshness] STALE -- record has unsupported schema_version "
            f"{record.get('schema_version')!r}",
            file=sys.stderr,
        )
        return False

    current_commit, current_dirty = _current_git_state(root)
    recorded_commit = record.get("git_commit")

    if current_dirty:
        print(
            "[freshness] STALE -- working tree has uncommitted changes right now; no "
            "recorded result can be current against a moving target.",
            file=sys.stderr,
        )
        return False

    if recorded_commit != current_commit:
        print(
            f"[freshness] STALE -- recorded commit {recorded_commit} does not match current "
            f"HEAD {current_commit}.",
            file=sys.stderr,
        )
        return False

    if record.get("git_dirty"):
        print(
            "[freshness] STALE -- the recorded run itself was against a dirty working tree, "
            "so it never represented a committed, reproducible state.",
            file=sys.stderr,
        )
        return False

    if not record.get("all_passed"):
        failed = [name for name, r in record.get("checks", {}).items() if not r.get("passed")]
        print(
            f"[freshness] CURRENT but NOT PASSING -- last verification at {current_commit} "
            f"failed: {', '.join(failed)}. This is IMPLEMENTED BUT NOT VERIFIED, not VERIFIED.",
            file=sys.stderr,
        )
        return False

    print(
        f"[freshness] CURRENT AND VERIFIED -- commit {current_commit}, "
        f"checked at {record.get('checked_at_utc')}."
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check-freshness",
        action="store_true",
        help="Only check whether the last recorded verification is still current; run nothing.",
    )
    args = parser.parse_args()

    if args.check_freshness:
        return 0 if check_freshness() else 1
    return 0 if run_normal_verification() else 1


if __name__ == "__main__":
    sys.exit(main())
