#!/usr/bin/env python3
"""Phase 4 gate: adaptive discovery, sufficiency, exact manifests, and resume.

The discovery control supplies a deterministic accessible universe at the
external-source boundary. A valid high-value target is deliberately placed
outside the initial segment. Production discovery must continue far enough to
reach it, rank it into the final top-N, and persist the complete DISC-02 audit.

The lifecycle control uses real SQLite state and the real run orchestrator. It
injects one deterministic target-execution failure at the acquisition boundary,
then verifies resume retains the original target order and checksum and does not
re-execute completed work.
"""

from __future__ import annotations

import argparse
import json
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

import hunter_cli  # noqa: E402

import hunter_state  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"
REPORT_SCHEMA_VERSION = "hunter-adaptive-manifest-gate-1.0.0"

# At the gate's fixed JD and ranking-policy fixture, RA=24 degrees scores
# 1.0000 while every RA=1..10 initial-segment candidate scores below it. The
# earlier RA=126 oracle scored only 0.6355 and could not validly assert that a
# higher-value target lay outside the initial segment.
OUTSIDE_HIGH_VALUE_RA_DEG = 24.0


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


def _coverage_field(field_id: str, ra: float) -> dict[str, Any]:
    return {
        "field_id": field_id,
        "ra_deg": ra,
        "dec_deg": 5.0,
        "n_distinct_nights": 3,
        "distinct_nights_yyyymmdd": ["20240101", "20240102", "20240103"],
        "passes_min_distinct_nights": True,
        "raw_response_sha256": f"{int(ra):064x}",
        "coverage_provenance": {
            "validity_state": "valid",
            "source": "phase-4-independent-oracle",
            "retrieved_at_utc": "2026-01-01T00:00:00+00:00",
        },
    }


def check_adaptive_expansion() -> Assertion:
    """DISC-01..03: high value beyond the initial segment must be reached."""
    original_combined = hunter_cli._combined_known_coverage
    original_next = hunter_cli._next_uncovered_planning_candidates
    original_live = hunter_cli._live_coverage_check
    calls = 0

    def next_candidates(*args: object, **kwargs: object) -> list[tuple[float, float]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return [(float(index), 5.0) for index in range(1, 11)]
        if calls == 2:
            return [(OUTSIDE_HIGH_VALUE_RA_DEG, 5.0)]
        return []

    def live(fields: list[tuple[str, float, float]], prefix: str) -> dict[str, Any]:
        del prefix
        return {
            "batch_id": f"gate-round-{calls}",
            "field_results": [_coverage_field(field_id, ra) for field_id, ra, _dec in fields],
        }

    try:
        hunter_cli._combined_known_coverage = lambda: {}
        hunter_cli._next_uncovered_planning_candidates = next_candidates
        hunter_cli._live_coverage_check = live
        with tempfile.TemporaryDirectory(prefix="hunter-phase4-") as raw:
            from astropy.config import set_temp_cache, set_temp_config

            root = Path(raw)
            cache_dir = root / "cache"
            config_dir = root / "config"
            cache_dir.mkdir()
            config_dir.mkdir()
            queue = root / "queue.csv"
            queue.write_text(
                "rank,priority,status,data_role,source,selection_rule,evidence_path,notes\n"
            )
            with set_temp_cache(cache_dir), set_temp_config(config_dir):
                result = hunter_cli.discover_new_targets(
                    jd=2461000.5,
                    neo_class="all",
                    requested_n=1,
                    max_pool=None,
                    out_dir=root / "working",
                    target_queue_path=queue,
                    ranking_policy_path=REPO_ROOT
                    / "data_selection/ranking_policies/ztf_field_ranking_v4.json",
                    db_path=root / "state.sqlite",
                )
    finally:
        hunter_cli._combined_known_coverage = original_combined
        hunter_cli._next_uncovered_planning_candidates = original_next
        hunter_cli._live_coverage_check = original_live

    selected = [float(row["ra_deg"]) for row in result.get("eligible", [])[:1]]
    required_evidence = {
        "requested_n",
        "discovered_count",
        "eligible_count",
        "rejection_counts",
        "source_watermarks",
        "expansion_rounds",
        "top_n_membership_churn",
        "rank_stability",
        "exhausted_sources",
        "remaining_unexplored_universe",
        "termination_reason",
        "quality_distribution",
        "limitations",
    }
    missing = sorted(required_evidence - result.keys())
    passed = calls >= 2 and selected == [OUTSIDE_HIGH_VALUE_RA_DEG] and not missing
    return Assertion(
        "adaptive-expansion-outside-initial-segment",
        ("DISC-01", "DISC-02", "DISC-03"),
        PASS if passed else FAIL,
        f"rounds_requested={calls}; final_top_n={selected}; missing_DISC_02={missing}",
    )


def check_exact_manifest_resume() -> Assertion:
    """DUR-02/DUR-04: resume must keep exact order/checksum and skip success."""
    with tempfile.TemporaryDirectory(prefix="hunter-phase4-") as raw:
        root = Path(raw)
        database = root / "state.sqlite"
        ledger = root / "ledger.sqlite"
        targets = [
            hunter_state.ManifestTarget(
                target_id=f"radec_{ra:.2f}_5.00",
                ra_deg=ra,
                dec_deg=5.0,
                score=score,
                selection_reason="phase-4 oracle",
                coverage_inventory_id=f"field-{index}",
            )
            for index, (ra, score) in enumerate(((10.0, 0.9), (20.0, 0.8)), 1)
        ]
        hunter_state.create_search_manifest(
            database, "search-gate", "new", 2, "policy", "d" * 64,
            targets, 100, True, {"oracle": "phase-4"},
        )
        frozen = hunter_state.get_search_manifest(database, "search-gate")
        calls: list[str] = []
        failed_once = False
        original_execute = hunter_cli.execute_target

        def execute(target: dict[str, Any], *args: object, **kwargs: object) -> dict[str, Any]:
            nonlocal failed_once
            del args, kwargs
            calls.append(target["target_id"])
            if target["target_id"] == targets[1].target_id and not failed_once:
                failed_once = True
                raise RuntimeError("independent one-shot acquisition failure")
            return {
                "execution_status": "null_result",
                "candidate_ids": [],
                "nights_acquired": ["20240101", "20240102", "20240103"],
                "scored_candidates": [],
            }

        try:
            hunter_cli.execute_target = execute
            first = hunter_cli.run_search(
                database, ledger, "search-gate", root / "checkpoints", workers=1
            )
            second = hunter_cli.run_search(
                database, ledger, "search-gate", root / "checkpoints", workers=1
            )
        finally:
            hunter_cli.execute_target = original_execute

        final = hunter_state.get_search_manifest(database, "search-gate")
        frozen_checksum = frozen.get("manifest_sha256")
        final_ids = [row["target_id"] for row in final["targets"]]
        expected_ids = [target.target_id for target in targets]
        passed = (
            first["status"] == "partial"
            and second["status"] == "completed"
            and second["run_id"] == first["run_id"]
            and calls.count(targets[0].target_id) == 1
            and calls.count(targets[1].target_id) == 2
            and final_ids == expected_ids
            and isinstance(frozen_checksum, str)
            and len(frozen_checksum) == 64
            and final.get("manifest_sha256") == frozen_checksum
        )
    return Assertion(
        "exact-manifest-retry-resume",
        ("DUR-02", "DUR-03", "DUR-04"),
        PASS if passed else FAIL,
        "same run resumed; completed target skipped; persisted ordering/checksum unchanged"
        if passed else "resume regenerated/reordered work or lost exact-manifest identity",
    )


def run_gate() -> dict[str, Any]:
    assertions: list[Assertion] = []
    try:
        assertions.append(check_adaptive_expansion())
        assertions.append(check_exact_manifest_resume())
    except Exception as exc:  # fail loudly with an operator-actionable gate result
        assertions.append(
            Assertion("phase-4-gate-execution", ("DISC-01", "DUR-02"), FAIL, repr(exc))
        )
    failed = [item for item in assertions if item.status != PASS]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "gate": "phase-4-adaptive-discovery-and-frozen-manifest",
        "status": PASS if not failed else FAIL,
        "code_identity": head,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "assertions": [item.as_dict() for item in assertions],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    report = run_gate()
    for assertion in report["assertions"]:
        print(f"{assertion['status']:<13} {assertion['assertion_id']}  {assertion['detail']}")
    print(f"GATE STATUS: {report['status']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report written to {args.json}")
    return 0 if report["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
