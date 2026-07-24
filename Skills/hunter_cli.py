"""Hunter search CLI: create-new-search / run-new-search / show-follow-ups.

Implements the canonical Hunter production pipeline stage this repo is missing:
adaptive candidate discovery -> eligibility -> ranking/selection sufficiency ->
durable search creation, on top of the already-working, already-tested pipeline
stages this repo has (Skills/select_survey_fields.py's scorer,
Skills/inventory_ztf_field_night_coverage.py's live coverage preflight,
src/hunter_state.py's durable state). See docs/HUNTER_PROD_DIRECTIVE.md.

This module composes existing code; it does not reimplement scoring,
eligibility, coverage acquisition, or durable-state schema logic.

Usage::

    uv run python Skills/hunter_cli.py create-new-search --targets 5 --mode new
    uv run python Skills/hunter_cli.py create-new-search --targets 5 --mode new \\
        --neo-class ieo --max-pool 400
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling Skills/ imports

import inventory_ztf_field_night_coverage as coverage_inventory  # noqa: E402
import select_survey_fields as field_selector  # noqa: E402

import hunter_state  # noqa: E402

_NEO_CLASSES = ("aten", "ieo", "all")
_DEFAULT_TARGET_QUEUE = REPO_ROOT / "data_selection" / "target_priority_queue.csv"
_DEFAULT_DB = REPO_ROOT / "data_selection" / "hunter_state.sqlite"
_BATCH_MANIFEST_DIR = REPO_ROOT / "data_selection" / "batch_manifests"
_COVERAGE_INVENTORY_DIR = REPO_ROOT / "data_selection" / "coverage_inventories"
_SEARCH_MANIFEST_CSV_DIR = REPO_ROOT / "data_selection" / "search_manifests"
_WORKING_DIR = REPO_ROOT / "Logs" / "pipeline_runs" / "hunter_cli"
_MAX_AGGREGATE_IRSA_REQUESTS = 6

# Same bounded historical-replay window already established and used by this
# repo's committed coverage batch manifests (data_selection/batch_manifests/
# ztf_dr24_new_field_coverage_preflight_v1.json) -- reused, not reinvented, to
# stay inside the already-authorized no-future-catalog-leakage replay window.
_DEFAULT_COVERAGE_WINDOW: dict[str, Any] = {
    "replay_cutoff_utc": "2024-09-21T00:00:00Z",
    "start_jd_exclusive": 2460209.5,
    "end_jd_exclusive": 2460574.5,
    "size_deg": 2.0,
    "min_distinct_nights": 3,
}


def _content_sha256(payload: Any) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _field_id_from_radec(prefix: str, ra_deg: float, dec_deg: float) -> str:
    ra_token = f"{ra_deg:06.2f}".replace(".", "p")
    sign = "m" if dec_deg < 0 else "p"
    dec_token = f"{abs(dec_deg):05.2f}".replace(".", "p")
    return f"{prefix}_{ra_token}_{sign}{dec_token}"


def _combined_known_coverage() -> dict[tuple[float, float], dict[str, Any]]:
    """Merge every committed coverage inventory into one coordinate-keyed dict."""
    combined: dict[tuple[float, float], dict[str, Any]] = {}
    if not _COVERAGE_INVENTORY_DIR.is_dir():
        return combined
    for path in sorted(_COVERAGE_INVENTORY_DIR.glob("*.json")):
        inventory = field_selector.load_coverage_inventory(path)
        for field in inventory["field_results"]:
            key = field_selector._coordinate_key(field["ra_deg"], field["dec_deg"])
            combined[key] = field
    return combined


def _write_combined_inventory(
    combined: dict[tuple[float, float], dict[str, Any]], out_path: Path
) -> None:
    field_results = list(combined.values())
    payload = {
        "schema_version": "ztf-field-night-coverage-inventory-v1",
        "batch_id": "hunter_cli_combined_working_inventory",
        "batch_manifest_sha256": _content_sha256(field_results),
        "metadata_only": True,
        "min_distinct_nights": _DEFAULT_COVERAGE_WINDOW["min_distinct_nights"],
        "field_results": field_results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_expansion_batch_manifest(
    batch_id: str, fields: list[tuple[str, float, float]], out_path: Path
) -> None:
    window = _DEFAULT_COVERAGE_WINDOW
    payload = {
        "batch_id": batch_id,
        "project": "2026 Near Earth Objects",
        "source": "IRSA ZTF public science-image metadata",
        "source_url": "https://irsa.ipac.caltech.edu/ibe/search/ztf/products/sci",
        "data_role": "metadata_only_coverage_preflight",
        "replay_cutoff_utc": window["replay_cutoff_utc"],
        "start_jd_exclusive": window["start_jd_exclusive"],
        "end_jd_exclusive": window["end_jd_exclusive"],
        "window_days": window["end_jd_exclusive"] - window["start_jd_exclusive"],
        "size_deg": window["size_deg"],
        "footprint_note": (
            "Each query covers the central size_deg x size_deg IRSA search box."
        ),
        "min_distinct_nights": window["min_distinct_nights"],
        "selection_source": "Skills/hunter_cli.py create-new-search adaptive expansion",
        "fields": [
            {"field_id": field_id, "role": "live_search", "ra_deg": ra, "dec_deg": dec}
            for field_id, ra, dec in fields
        ],
        "safety": {
            "metadata_only": True,
            "raw_alert_archives_downloaded": False,
            "candidate_scoring": False,
            "external_submission": False,
            "impact_claims": False,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _next_uncovered_planning_candidates(
    jd: float,
    neo_class: str,
    checked_coords: set[tuple[float, float]],
    batch_size: int,
    ranking_policy_path: Path,
) -> list[tuple[float, float]]:
    """Next top-ranked, not-yet-coverage-checked fields from the full planning grid."""
    planning = field_selector.select_fields(
        jd=jd,
        mode=neo_class,
        top_n=10_000,
        ranking_policy_path=ranking_policy_path,
    )
    candidates: list[tuple[float, float]] = []
    for row in planning:
        key = field_selector._coordinate_key(row["ra_deg"], row["dec_deg"])
        if key in checked_coords:
            continue
        candidates.append((row["ra_deg"], row["dec_deg"]))
        if len(candidates) >= batch_size:
            break
    return candidates


def discover_new_targets(
    jd: float,
    neo_class: str,
    requested_n: int,
    max_pool: int,
    out_dir: Path,
    target_queue_path: Path,
    ranking_policy_path: Path,
) -> dict[str, Any]:
    """Adaptive discovery loop for ``create-new-search --mode new``.

    Repeatedly grows the working coverage inventory (real, live IRSA metadata
    checks via inventory_ztf_field_night_coverage.py) for the next batch of
    top-ranked, not-yet-covered planning-grid fields until either
    ``requested_n`` eligible candidates exist or ``max_pool`` fields have been
    coverage-checked -- whichever comes first. Returns the eligible ranked
    results plus sufficiency/pool-size bookkeeping for the durable manifest.
    """
    combined = _combined_known_coverage()
    checked_coords: set[tuple[float, float]] = set(combined.keys())
    eligible: list[dict[str, Any]] = []
    working_inventory_path = out_dir / "working_coverage_inventory.json"
    round_index = 0

    while True:
        if combined:
            _write_combined_inventory(combined, working_inventory_path)
            eligible = field_selector.select_fields(
                jd=jd,
                mode=neo_class,
                top_n=max(requested_n, len(combined)),
                coverage_inventory_path=working_inventory_path,
                target_queue_path=target_queue_path,
                search_mode="new",
                ranking_policy_path=ranking_policy_path,
            )
        if len(eligible) >= requested_n or len(checked_coords) >= max_pool:
            break

        # max_pool - len(checked_coords) > 0 here: the prior break condition
        # above already ruled out len(checked_coords) >= max_pool.
        batch_size = min(
            max(3 * requested_n, 10) * (2**round_index), max_pool - len(checked_coords)
        )
        candidates = _next_uncovered_planning_candidates(
            jd, neo_class, checked_coords, batch_size, ranking_policy_path
        )
        if not candidates:
            break  # planning grid itself is exhausted for this class/night

        round_index += 1
        batch_id = f"hunter_expand_{neo_class}_r{round_index}_{uuid.uuid4().hex[:8]}"
        manifest_path = _BATCH_MANIFEST_DIR / f"{batch_id}.json"
        fields = [
            (_field_id_from_radec(f"hx{round_index}", ra, dec), ra, dec)
            for ra, dec in candidates
        ]
        _write_expansion_batch_manifest(batch_id, fields, manifest_path)
        batch = coverage_inventory.load_batch_manifest(manifest_path)
        workers = max(1, min(_MAX_AGGREGATE_IRSA_REQUESTS, len(batch.fields)))
        shard_out_dir = _WORKING_DIR / "coverage_shards"
        coverage_inventory.run_shard(batch, shard_out_dir, 0, 1, workers)
        merged = coverage_inventory.merge_shards(batch, shard_out_dir, 1)

        committed_inventory_path = _COVERAGE_INVENTORY_DIR / f"{batch_id}.json"
        committed_inventory_path.parent.mkdir(parents=True, exist_ok=True)
        committed_inventory_path.write_text(
            json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        for field in merged["field_results"]:
            key = field_selector._coordinate_key(field["ra_deg"], field["dec_deg"])
            combined[key] = field
            checked_coords.add(key)

    return {
        "eligible": eligible,
        "pool_size_explored": len(checked_coords),
        "sufficiency_met": len(eligible) >= requested_n,
    }


def _write_manifest_csv(search_id: str, rows: list[dict[str, Any]]) -> Path:
    _SEARCH_MANIFEST_CSV_DIR.mkdir(parents=True, exist_ok=True)
    path = _SEARCH_MANIFEST_CSV_DIR / f"{search_id}.csv"
    fieldnames = [
        "rank",
        "target_id",
        "ra_deg",
        "dec_deg",
        "score",
        "selection_reason",
        "coverage_inventory_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            writer.writerow({"rank": i, **row})
    return path


def _print_table(search_id: str, rows: list[dict[str, Any]]) -> None:
    print(f"\nSearch manifest {search_id} -- {len(rows)} target(s) selected (pending):\n")
    header = f"{'rank':>4}  {'target_id':<22}  {'score':>7}  {'reason'}"
    print(header)
    print("-" * len(header))
    for i, row in enumerate(rows, start=1):
        print(
            f"{i:>4}  {row['target_id']:<22}  {row['score']:>7.4f}  {row['selection_reason']}"
        )
    print()


def cmd_create_new_search(args: argparse.Namespace) -> int:
    ranking_policy_path = Path(args.ranking_policy)
    ranking_policy = field_selector.load_ranking_policy(ranking_policy_path)
    target_queue_path = Path(args.target_queue)

    if args.jd == "now":
        from astropy.time import Time

        jd = float(Time.now().jd)
    else:
        jd = float(args.jd)

    out_dir = _WORKING_DIR / "coverage_expansion"
    result = discover_new_targets(
        jd=jd,
        neo_class=args.neo_class,
        requested_n=args.targets,
        max_pool=args.max_pool,
        out_dir=out_dir,
        target_queue_path=target_queue_path,
        ranking_policy_path=ranking_policy_path,
    )

    selected = result["eligible"][: args.targets]
    manifest_targets = [
        hunter_state.ManifestTarget(
            target_id=hunter_state.target_id_from_radec(row["ra_deg"], row["dec_deg"]),
            ra_deg=row["ra_deg"],
            dec_deg=row["dec_deg"],
            score=row["score"],
            selection_reason=row["reason"],
            coverage_inventory_id=row.get("field_id"),
        )
        for row in selected
    ]

    search_id = f"search_new_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    db_path = Path(args.db)
    hunter_state.create_search_manifest(
        db_path=db_path,
        search_id=search_id,
        mode="new",
        requested_n=args.targets,
        ranking_policy_path=ranking_policy["path"],
        ranking_policy_digest=ranking_policy["sha256"],
        targets=manifest_targets,
        discovery_pool_size_explored=result["pool_size_explored"],
        sufficiency_met=result["sufficiency_met"],
        config={"neo_class": args.neo_class, "jd": jd, "max_pool": args.max_pool},
    )

    manifest_rows = [
        {
            "target_id": t.target_id,
            "ra_deg": t.ra_deg,
            "dec_deg": t.dec_deg,
            "score": t.score,
            "selection_reason": t.selection_reason,
            "coverage_inventory_id": t.coverage_inventory_id,
        }
        for t in manifest_targets
    ]
    if len(manifest_rows) <= 100:
        _print_table(search_id, manifest_rows)
    else:
        csv_path = _write_manifest_csv(search_id, manifest_rows)
        print(f"Search manifest written: {csv_path}")

    print(
        f"search_id={search_id}  status=pending  requested_n={args.targets}  "
        f"selected_n={len(manifest_targets)}  "
        f"pool_explored={result['pool_size_explored']}  "
        f"sufficiency_met={result['sufficiency_met']}"
    )
    if len(manifest_targets) < args.targets:
        print(
            f"WARNING: only {len(manifest_targets)}/{args.targets} eligible targets found "
            f"after exploring {result['pool_size_explored']} candidate field(s) -- the "
            "reachable pool is exhausted for this class/night, not a bug. Use --max-pool "
            "to search further, or retry on a different --jd.",
            flush=True,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create_cmd = sub.add_parser(
        "create-new-search", help="rank/select targets and create a durable pending search"
    )
    create_cmd.add_argument("--targets", type=int, required=True, help="number of targets (N)")
    create_cmd.add_argument("--mode", choices=["new"], required=True)
    create_cmd.add_argument("--neo-class", choices=_NEO_CLASSES, default="all")
    create_cmd.add_argument("--jd", default="now")
    create_cmd.add_argument("--max-pool", type=int, default=200)
    create_cmd.add_argument("--target-queue", default=str(_DEFAULT_TARGET_QUEUE))
    create_cmd.add_argument(
        "--ranking-policy", default=str(field_selector._DEFAULT_RANKING_POLICY_PATH)
    )
    create_cmd.add_argument("--db", default=str(_DEFAULT_DB))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create-new-search":
            return cmd_create_new_search(args)
        raise AssertionError(f"unhandled command {args.command}")  # pragma: no cover
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
