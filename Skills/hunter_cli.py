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
    uv run python Skills/hunter_cli.py run-new-search --latest
    uv run python Skills/hunter_cli.py run-new-search --search-id search_new_...
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling Skills/ imports

import adversarial_review  # noqa: E402
import convert_pixel_extraction_to_observations as pixel_convert  # noqa: E402
import inventory_ztf_field_night_coverage as coverage_inventory  # noqa: E402
import run_pixel_extraction_positive_control as positive_control  # noqa: E402
import select_survey_fields as field_selector  # noqa: E402
import ztf_dr24_bounded_ingest as bounded_ingest  # noqa: E402

import candidate_ledger  # noqa: E402
import hunter_state  # noqa: E402
import schemas  # noqa: E402

_NEO_CLASSES = ("aten", "ieo", "all")
_RUN_TARGET_EXPECTED_EXCEPTIONS = (
    KeyError,
    TypeError,
    ValueError,
    RuntimeError,
    OSError,
    json.JSONDecodeError,
)
_DEFAULT_TARGET_QUEUE = REPO_ROOT / "data_selection" / "target_priority_queue.csv"
_DEFAULT_DB = REPO_ROOT / "data_selection" / "hunter_state.sqlite"
_DEFAULT_LEDGER_DB = REPO_ROOT / "data_selection" / "candidate_ledger.sqlite"
_BATCH_MANIFEST_DIR = REPO_ROOT / "data_selection" / "batch_manifests"
_COVERAGE_INVENTORY_DIR = REPO_ROOT / "data_selection" / "coverage_inventories"
_SEARCH_MANIFEST_CSV_DIR = REPO_ROOT / "data_selection" / "search_manifests"
_WORKING_DIR = REPO_ROOT / "Logs" / "pipeline_runs" / "hunter_cli"
_CHECKPOINT_ROOT = _WORKING_DIR / "search_runs"
_MAX_AGGREGATE_IRSA_REQUESTS = 6
# Deliberately small: a wide box (e.g. the coverage-preflight's 2.0deg) spans
# multiple ZTF CCD/quadrant footprints, each producing its own near-identical
# obsjd metadata row -- breaking the single-exposure-per-window assumption
# _single_exposure_window relies on. Matches the box size this project's own
# prior single-exposure pixel-extraction pilots used successfully (e.g.
# docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md).
_DEFAULT_SIZE_DEG = 0.01
_FOLLOW_UP_VERDICTS = ("SURVIVE", "BORDERLINE")

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


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=False
    )
    return result.stdout.strip() or "unknown"


def _day_jd_bounds(night_yyyymmdd: str) -> tuple[float, float]:
    from astropy.time import Time

    year, month, day = night_yyyymmdd[:4], night_yyyymmdd[4:6], night_yyyymmdd[6:8]
    start = Time(f"{year}-{month}-{day}T00:00:00", format="isot", scale="utc")
    return float(start.jd), float(start.jd) + 1.0


def _single_exposure_window(
    ra_deg: float,
    dec_deg: float,
    night_yyyymmdd: str,
    size_deg: float,
    out_dir: Path,
    max_narrowing_attempts: int = 4,
) -> tuple[float, float]:
    """Derive a (start_jd, end_jd) window narrow enough to contain exactly one
    real exposure for this field on this calendar night.

    Queries the real metadata for the full calendar day (one network call),
    then narrows a window around the first chronological exposure using only
    that already-fetched real data -- no guessing, no additional network
    calls, and no dependence on the coverage step's transient (gitignored)
    raw response cache surviving into this process.
    """
    day_start, day_end = _day_jd_bounds(night_yyyymmdd)
    day_report = bounded_ingest.run_bounded_ingest(
        ra=ra_deg, dec=dec_deg, size_deg=size_deg, start_jd=day_start, end_jd=day_end,
        out_dir=out_dir,
    )
    raw_path = Path(day_report["raw_response_path"])
    table = bounded_ingest._parse_ipac_table(raw_path.read_text(encoding="utf-8"))
    if len(table) == 0:
        raise RuntimeError(
            f"no exposure found for RA={ra_deg} Dec={dec_deg} on {night_yyyymmdd}, despite "
            "the coverage inventory recording this as a covered night"
        )
    obsjds = sorted(float(v) for v in table["obsjd"])
    target_jd = obsjds[0]  # first chronological exposure that night -- deterministic
    epsilon = 1.0 / 1440.0  # start at +/- 1 minute
    for _ in range(max_narrowing_attempts):
        start_jd, end_jd = target_jd - epsilon, target_jd + epsilon
        if sum(1 for jd in obsjds if start_jd < jd < end_jd) == 1:
            return start_jd, end_jd
        epsilon /= 2
    raise RuntimeError(
        f"could not isolate a single exposure for RA={ra_deg} Dec={dec_deg} on "
        f"{night_yyyymmdd} after {max_narrowing_attempts} narrowing attempt(s)"
    )


def _nights_for_target(ra_deg: float, dec_deg: float) -> list[str]:
    combined = _combined_known_coverage()
    key = field_selector._coordinate_key(ra_deg, dec_deg)
    field = combined.get(key)
    if field is None:
        raise RuntimeError(
            f"no committed coverage record found for RA={ra_deg} Dec={dec_deg} -- "
            "this target's manifest row does not match any known coverage inventory"
        )
    return list(field["distinct_nights_yyyymmdd"])


def _acquire_and_convert_night(
    ra_deg: float, dec_deg: float, night: str, size_deg: float, target_root: Path
) -> None:
    """Acquire exactly one real exposure for one night and write it as an
    Observation checkpoint, reusing the existing pixel-extraction pilot and
    converter unmodified."""
    start_jd, end_jd = _single_exposure_window(
        ra_deg, dec_deg, night, size_deg, target_root / "day_scan"
    )
    pilot_out_dir = target_root / "pixel_pilot" / night
    report = bounded_ingest.run_bounded_ingest(
        ra=ra_deg, dec=dec_deg, size_deg=size_deg, start_jd=start_jd, end_jd=end_jd,
        out_dir=pilot_out_dir, preflight_motion_products=True, pixel_extraction_pilot=True,
    )
    manifest_path = Path(report["motion_product_manifest_path"])
    pilot_path = manifest_path.parent / "pixel_extraction_pilot.json"
    converted = pixel_convert.convert(pilot_path, manifest_path)
    obs_dir = target_root / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    (obs_dir / f"{night}.json").write_text(json.dumps(converted, indent=2), encoding="utf-8")


def execute_target(
    target: dict[str, Any], checkpoint_root: Path, size_deg: float, min_observations: int = 3
) -> dict[str, Any]:
    """Acquire, link/score, and adversarially review one manifest target.

    Returns {"execution_status", "candidate_ids", "nights_acquired", "scored_candidates"}.
    Raises on genuine failure -- the caller is responsible for catching,
    recording, and continuing to the next target (a per-target failure must
    never silently abort the whole run, per the Hunter directive).
    """
    ra_deg, dec_deg = target["ra_deg"], target["dec_deg"]
    nights_available = _nights_for_target(ra_deg, dec_deg)
    if len(nights_available) < min_observations:
        raise RuntimeError(
            f"target {target['target_id']} has only {len(nights_available)} known covered "
            f"night(s), fewer than min_observations={min_observations}"
        )
    chosen_nights = nights_available[:min_observations]

    target_root = checkpoint_root / target["target_id"]
    obs_dir = target_root / "observations"
    acquired_nights: list[str] = []
    for night in chosen_nights:
        _acquire_and_convert_night(ra_deg, dec_deg, night, size_deg, target_root)
        acquired_nights.append(night)

    control_report = positive_control.run_positive_control(
        nights=acquired_nights,
        checkpoint_dir=obs_dir,
        min_observations=min_observations,
        build_review_packets=True,
    )
    if control_report["n_tracklets_linked"] == 0:
        return {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": acquired_nights,
            "scored_candidates": [],
        }

    scored_candidates = []
    for packet in control_report["review_packets"]:
        neo = schemas.ScoredNEO.model_validate(packet)
        verdict = adversarial_review.run_adversarial_review(neo, offline=True)
        scored_candidates.append({"packet": packet, "verdict": verdict})

    return {
        "execution_status": "success",
        "candidate_ids": [c["packet"]["tracklet"]["object_id"] for c in scored_candidates],
        "nights_acquired": acquired_nights,
        "scored_candidates": scored_candidates,
    }


def _ingest_and_maybe_register_followup(
    db_path: Path,
    ledger_db_path: Path,
    search_id: str,
    run_id: str,
    target: dict[str, Any],
    scored: dict[str, Any],
) -> None:
    packet = scored["packet"]
    verdict = scored["verdict"]
    defaults = candidate_ledger.CandidateLedgerDefaults(
        source_dataset_id=search_id,
        candidate_generator="Skills/hunter_cli.py run-new-search",
        regeneration_command=(
            f"uv run --python 3.14 python Skills/hunter_cli.py run-new-search "
            f"--search-id {search_id}"
        ),
        target_id=target["target_id"],
        review_status=verdict.verdict.lower(),
        review_notes=verdict.summary,
    )
    record = candidate_ledger.record_from_packet(packet, defaults)
    candidate_ledger.upsert_record(ledger_db_path, record)

    if verdict.verdict in _FOLLOW_UP_VERDICTS:
        hunter_state.add_follow_up(
            db_path,
            target_id=target["target_id"],
            reason=f"adversarial review verdict={verdict.verdict}: {verdict.summary}",
            priority=float((packet.get("metadata") or {}).get("discovery_priority") or 0.5),
            recommended_action="operator review before any MPC submission consideration",
            evidence_ref=f"candidate_ledger:{record['candidate_id']}",
            candidate_id=record["candidate_id"],
            originating_run_id=run_id,
        )


def run_search(
    db_path: Path,
    ledger_db_path: Path,
    search_id: str,
    checkpoint_root: Path,
    size_deg: float = _DEFAULT_SIZE_DEG,
) -> dict[str, Any]:
    """Execute the exact persisted manifest for ``search_id``. Never
    regenerates the target selection. Resumes an interrupted OR partially/
    fully failed run in place (retrying only the not-yet-successful targets);
    refuses to silently re-execute a run that fully completed."""
    manifest = hunter_state.get_search_manifest(db_path, search_id)
    if manifest["status"] == "executed":
        existing_run = hunter_state.get_latest_run_for_search(db_path, search_id)
        raise ValueError(
            f"search {search_id} was already executed "
            f"(run_id={existing_run['run_id'] if existing_run else 'unknown'}); "
            "create a new search rather than re-running a completed one"
        )
    if manifest["status"] != "pending":
        raise ValueError(f"search {search_id} has unexpected status {manifest['status']!r}")

    existing_run = hunter_state.get_latest_run_for_search(db_path, search_id)
    if existing_run is not None and existing_run["status"] != "completed":
        # "running" (interrupted mid-execution) or "partial"/"failed" (a prior
        # pass finished but some targets still need retrying) are both resumed
        # into the same run record -- only a fully "completed" run is terminal.
        run_id = existing_run["run_id"]
        print(
            f"[resume] continuing run {run_id} (previous status={existing_run['status']})",
            flush=True,
        )
    else:
        run_id = f"run_{search_id}_{uuid.uuid4().hex[:8]}"
        hunter_state.create_search_run(
            db_path, run_id, search_id, _git_sha(), model_versions={}
        )

    already_done = hunter_state.get_run_targets(db_path, run_id)
    n_failed = 0
    for target in manifest["targets"]:
        target_id = target["target_id"]
        prior = already_done.get(target_id)
        if prior is not None and prior["execution_status"] in {"success", "null_result"}:
            print(
                f"[resume] target {target_id} already {prior['execution_status']}, skipping",
                flush=True,
            )
            continue

        print(
            f"[run-new-search] executing target {target_id} "
            f"({target['ra_deg']}, {target['dec_deg']})",
            flush=True,
        )
        try:
            result = execute_target(target, checkpoint_root, size_deg)
        except _RUN_TARGET_EXPECTED_EXCEPTIONS as exc:
            print(f"[run-new-search] target {target_id} FAILED: {exc}", flush=True)
            hunter_state.upsert_run_target(
                db_path, run_id, target_id, "failed", error_message=str(exc)
            )
            n_failed += 1
            continue

        hunter_state.upsert_run_target(
            db_path,
            run_id,
            target_id,
            result["execution_status"],
            candidate_ids=result["candidate_ids"],
            nights_acquired=result["nights_acquired"],
        )
        for scored in result["scored_candidates"]:
            _ingest_and_maybe_register_followup(
                db_path, ledger_db_path, search_id, run_id, target, scored
            )
        print(
            f"[run-new-search] target {target_id}: {result['execution_status']} "
            f"({len(result['candidate_ids'])} candidate(s))",
            flush=True,
        )

    n_targets = len(manifest["targets"])
    if n_failed == 0:
        final_status = "completed"
    elif n_failed == n_targets:
        final_status = "failed"
    else:
        final_status = "partial"
    hunter_state.complete_search_run(
        db_path,
        run_id,
        final_status,
        failure_reason=(f"{n_failed}/{n_targets} target(s) failed" if n_failed else None),
    )
    # Only a fully successful pass retires the manifest. A "partial"/"failed"
    # pass leaves it "pending" so a future run-new-search invocation resumes
    # this same run and retries just the not-yet-successful targets, rather
    # than being permanently locked out by one bad target.
    if final_status == "completed":
        hunter_state.mark_manifest_status(db_path, search_id, "executed")
    return {"run_id": run_id, "status": final_status, "n_targets": n_targets, "n_failed": n_failed}


def cmd_run_new_search(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    if args.search_id is not None:
        search_id = args.search_id
    else:
        search_id = hunter_state.get_latest_pending_manifest(db_path, mode="new")["search_id"]

    result = run_search(
        db_path=db_path,
        ledger_db_path=Path(args.candidate_ledger_db),
        search_id=search_id,
        checkpoint_root=Path(args.checkpoint_root),
        size_deg=args.size_deg,
    )
    print(
        f"search_id={search_id}  run_id={result['run_id']}  status={result['status']}  "
        f"targets={result['n_targets']}  failed={result['n_failed']}"
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

    run_cmd = sub.add_parser(
        "run-new-search", help="execute the exact targets from a durable pending search"
    )
    run_group = run_cmd.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--search-id")
    run_group.add_argument("--latest", action="store_true")
    run_cmd.add_argument("--db", default=str(_DEFAULT_DB))
    run_cmd.add_argument("--candidate-ledger-db", default=str(_DEFAULT_LEDGER_DB))
    run_cmd.add_argument("--checkpoint-root", default=str(_CHECKPOINT_ROOT))
    run_cmd.add_argument("--size-deg", type=float, default=_DEFAULT_SIZE_DEG)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create-new-search":
            return cmd_create_new_search(args)
        if args.command == "run-new-search":
            return cmd_run_new_search(args)
        raise AssertionError(f"unhandled command {args.command}")  # pragma: no cover
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
