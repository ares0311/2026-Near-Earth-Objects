#!/usr/bin/env python
"""Validate alert-protocol gate logic on ≥10 diverse synthetic scored NEOs.

Exercises every combination of gate pass/fail for ready_for_submission() to
confirm that the alert-protocol decision tree is conservative and correct.
Exits 0 if all assertions pass; exits 1 with a summary of failures.

Usage:
    PYTHONPATH=src uv run python Skills/validate_alert_protocol.py
    PYTHONPATH=src uv run python Skills/validate_alert_protocol.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Ensure src/ is on the path regardless of how the script is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _make_elements(quality_code: int = 2) -> Any:
    """Return a minimal orbital elements namespace with the given quality code."""
    return SimpleNamespace(quality_code=quality_code)


def _make_neo(
    moid_au: float | None = 0.03,
    quality_code: int = 2,
    rb: float | None = 0.95,
    pathway: str = "internal_candidate",
) -> Any:
    """Build a minimal ScoredNEO-like namespace for gate testing.

    Uses SimpleNamespace so the test has no dependency on model weights or
    full pipeline state — only the fields read by ready_for_submission() are
    populated.
    """
    hazard = SimpleNamespace(
        moid_au=moid_au,
        orbital_elements=_make_elements(quality_code),
        alert_pathway=pathway,
    )
    features = SimpleNamespace(real_bogus_score=rb)
    return SimpleNamespace(hazard=hazard, features=features)


# Each scenario: (description, neo kwargs, expected_ready)
_SCENARIOS: list[tuple[str, dict, bool]] = [
    # --- Should PASS (all gates met) ---
    (
        "all gates pass: MOID=0.01, quality=2, rb=0.95, not known",
        dict(moid_au=0.01, quality_code=2, rb=0.95, pathway="internal_candidate"),
        True,
    ),
    (
        "all gates pass: MOID=0.05 (boundary), quality=3, rb=0.90 (boundary)",
        dict(moid_au=0.05, quality_code=3, rb=0.90, pathway="internal_candidate"),
        True,
    ),
    (
        "all gates pass: PHA pathway with high quality and rb",
        dict(moid_au=0.02, quality_code=4, rb=0.99, pathway="mpc_submission"),
        True,
    ),
    # --- Should FAIL: MOID gate ---
    (
        "MOID=None blocks submission",
        dict(moid_au=None, quality_code=2, rb=0.95, pathway="internal_candidate"),
        False,
    ),
    (
        "MOID=0.06 (above 0.05) blocks submission",
        dict(moid_au=0.06, quality_code=2, rb=0.95, pathway="internal_candidate"),
        False,
    ),
    (
        "MOID=1.0 (main-belt distance) blocks submission",
        dict(moid_au=1.0, quality_code=3, rb=0.98, pathway="internal_candidate"),
        False,
    ),
    # --- Should FAIL: orbit quality gate ---
    (
        "quality_code=1 (single-night) blocks submission",
        dict(moid_au=0.03, quality_code=1, rb=0.95, pathway="internal_candidate"),
        False,
    ),
    (
        "quality_code=0 (no orbit) blocks submission",
        dict(moid_au=0.03, quality_code=0, rb=0.95, pathway="internal_candidate"),
        False,
    ),
    # --- Should FAIL: real_bogus gate ---
    (
        "rb=0.89 (below 0.90 threshold) blocks submission",
        dict(moid_au=0.03, quality_code=2, rb=0.89, pathway="internal_candidate"),
        False,
    ),
    (
        "rb=None (missing score) blocks submission",
        dict(moid_au=0.03, quality_code=2, rb=None, pathway="internal_candidate"),
        False,
    ),
    (
        "rb=0.0 (artifact) blocks submission",
        dict(moid_au=0.01, quality_code=3, rb=0.0, pathway="internal_candidate"),
        False,
    ),
    # --- Should FAIL: known-object gate ---
    (
        "pathway=known_object blocks submission regardless of other gates",
        dict(moid_au=0.01, quality_code=4, rb=0.99, pathway="known_object"),
        False,
    ),
    # --- Multi-gate failures ---
    (
        "MOID=None AND quality=0: both gates fail",
        dict(moid_au=None, quality_code=0, rb=0.95, pathway="internal_candidate"),
        False,
    ),
    (
        "all gates fail: None MOID, quality=0, rb=None, known_object",
        dict(moid_au=None, quality_code=0, rb=None, pathway="known_object"),
        False,
    ),
]


def run_validation(json_output: bool = False) -> int:
    """Run all scenarios and return exit code (0=all pass, 1=failures found)."""
    from alert import ready_for_submission

    results = []
    failures = 0

    for description, kwargs, expected_ready in _SCENARIOS:
        neo = _make_neo(**kwargs)
        ready, unmet = ready_for_submission(neo)

        passed = ready == expected_ready
        if not passed:
            failures += 1

        results.append(
            {
                "scenario": description,
                "expected_ready": expected_ready,
                "actual_ready": ready,
                "unmet_conditions": unmet,
                "assertion": "PASS" if passed else "FAIL",
            }
        )

        if not json_output:
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] {description}", flush=True)
            if not passed:
                print(
                    f"       expected ready={expected_ready}, got ready={ready},"
                    f" unmet={unmet}",
                    flush=True,
                )

    summary = {
        "total": len(_SCENARIOS),
        "passed": len(_SCENARIOS) - failures,
        "failed": failures,
        "results": results,
    }

    if json_output:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"\nAlert protocol validation: {summary['passed']}/{summary['total']} passed",
            flush=True,
        )
        if failures:
            print(f"FAILURES: {failures} scenario(s) failed.", flush=True)
        else:
            print("All gate assertions correct. ready_for_submission() is conservative.", flush=True)

    return 1 if failures else 0


def main() -> None:
    """Parse CLI args and run validation."""
    parser = argparse.ArgumentParser(
        description="Validate ready_for_submission() on diverse synthetic NEOs."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON result instead of human-readable output.",
    )
    args = parser.parse_args()
    sys.exit(run_validation(json_output=args.json))


if __name__ == "__main__":
    main()
