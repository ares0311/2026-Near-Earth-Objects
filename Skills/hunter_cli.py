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
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from . import adversarial_review  # noqa: E402
    from . import convert_pixel_extraction_to_observations as pixel_convert  # noqa: E402
    from . import inventory_ztf_field_night_coverage as coverage_inventory  # noqa: E402
    from . import run_pixel_extraction_positive_control as positive_control  # noqa: E402
    from . import select_survey_fields as field_selector  # noqa: E402
    from . import ztf_dr24_bounded_ingest as bounded_ingest  # noqa: E402
    from .hunter_ux import table as ux_table  # noqa: E402
    from .hunter_ux import theme as ux_theme  # noqa: E402
else:
    import adversarial_review  # noqa: E402
    import convert_pixel_extraction_to_observations as pixel_convert  # noqa: E402
    import inventory_ztf_field_night_coverage as coverage_inventory  # noqa: E402
    import run_pixel_extraction_positive_control as positive_control  # noqa: E402
    import select_survey_fields as field_selector  # noqa: E402
    import ztf_dr24_bounded_ingest as bounded_ingest  # noqa: E402
    from hunter_ux import table as ux_table  # noqa: E402
    from hunter_ux import theme as ux_theme  # noqa: E402

import candidate_ledger  # noqa: E402
import hunter_cross_project  # noqa: E402
import hunter_state  # noqa: E402
import schemas  # noqa: E402
from hunter_config import get_hunter_paths  # noqa: E402
from hunter_logging import emit_event  # noqa: E402

_NEO_CLASSES = ("aten", "ieo", "all")
_RUN_TARGET_EXPECTED_EXCEPTIONS = (
    KeyError,
    TypeError,
    ValueError,
    RuntimeError,
    OSError,
    json.JSONDecodeError,
)
_PATHS = get_hunter_paths()
_RESOURCE_ROOT = _PATHS.resource_root
_DEFAULT_TARGET_QUEUE = _PATHS.target_queue
_DEFAULT_DB = _PATHS.hunter_db
_DEFAULT_LEDGER_DB = _PATHS.candidate_ledger_db
_DEFAULT_FOLLOW_UP_POLICY = (
    _PATHS.ranking_policy_dir / "hunter_follow_up_value_v1.json"
)
_BATCH_MANIFEST_DIR = _PATHS.batch_manifest_dir
_RESOURCE_COVERAGE_INVENTORY_DIR = _PATHS.static_coverage_dir
_COVERAGE_INVENTORY_DIR = _PATHS.runtime_coverage_dir
_SEARCH_MANIFEST_CSV_DIR = _PATHS.search_manifest_dir
_WORKING_DIR = _PATHS.work_dir
_CHECKPOINT_ROOT = _PATHS.checkpoint_dir
_EVENT_LOG = _PATHS.event_log
# Deliverable A publish target. Taken from hunter_cross_project rather than
# rebuilt from _PATHS so the CLI default and the module's own WS-01 containment
# check can never point at different roots.
_DEFAULT_CROSS_PROJECT_EXPORT = hunter_cross_project.DEFAULT_PUBLISH_PATH
_MAX_AGGREGATE_IRSA_REQUESTS = 6
_DEFAULT_RUN_WORKERS = 3
_MAX_RUN_WORKERS = 3
# Deliberately small: a wide box (e.g. the coverage-preflight's 2.0deg) spans
# multiple ZTF CCD/quadrant footprints, each producing its own near-identical
# obsjd metadata row -- breaking the single-exposure-per-window assumption
# _single_exposure_window relies on. Matches the box size this project's own
# prior single-exposure pixel-extraction pilots used successfully (e.g.
# docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md).
_DEFAULT_SIZE_DEG = 0.01
_FOLLOW_UP_VERDICTS = ("SURVIVE", "BORDERLINE")
_FOLLOW_UP_POLICY_SCHEMA = "hunter-follow-up-value-policy-v1"
_PLANNING_CATALOG_SCHEMA = "ztf-dr24-planning-catalog-v1"
_LIVE_PREFLIGHT_BYTES_PER_EXPOSURE = 27_311_040
_MINIMUM_EXECUTION_EXPOSURES = 3
_ESTIMATED_TARGET_STORAGE_MB = round(
    _LIVE_PREFLIGHT_BYTES_PER_EXPOSURE
    * _MINIMUM_EXECUTION_EXPOSURES
    / (1024 * 1024),
    1,
)
_UNCALIBRATED_TARGET_COMPUTE_SECONDS = 180.0

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


def _event_path(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "event_log", _EVENT_LOG))


def _content_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_follow_up_policy(path: Path = _DEFAULT_FOLLOW_UP_POLICY) -> dict[str, Any]:
    """Load the canonical follow-up value contract and fail closed on drift."""
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid follow-up policy {path}: {exc}") from exc
    if payload.get("schema_version") != _FOLLOW_UP_POLICY_SCHEMA:
        raise ValueError(f"follow-up policy schema must be {_FOLLOW_UP_POLICY_SCHEMA}")
    if payload.get("model_type") != "deterministic_lexicographic_value":
        raise ValueError("follow-up policy model_type is unsupported")
    expected_bases = {
        "open_review_survivor": 2.0,
        "failed_execution_retry": 1.0,
        "recovered_coverage_retry": 0.0,
    }
    tiers = payload.get("tiers")
    if not isinstance(tiers, dict) or {
        name: tier.get("base") for name, tier in tiers.items()
    } != expected_bases:
        raise ValueError("follow-up policy tiers do not match implementation")
    if not payload.get("exclusions") or not payload.get("limitations"):
        raise ValueError("follow-up policy must document exclusions and limitations")
    return {
        "schema_version": payload["schema_version"],
        "policy_id": payload["policy_id"],
        "path": (
            path.resolve().relative_to(_RESOURCE_ROOT).as_posix()
            if path.resolve().is_relative_to(_RESOURCE_ROOT)
            else str(path)
        ),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "limitations": payload["limitations"],
    }


def _field_id_from_radec(prefix: str, ra_deg: float, dec_deg: float) -> str:
    ra_token = f"{ra_deg:06.2f}".replace(".", "p")
    sign = "m" if dec_deg < 0 else "p"
    dec_token = f"{abs(dec_deg):05.2f}".replace(".", "p")
    return f"{prefix}_{ra_token}_{sign}{dec_token}"


def _combined_known_coverage() -> dict[tuple[float, float], dict[str, Any]]:
    """Merge inventories, preferring current-valid and then newest evidence."""
    combined: dict[tuple[float, float], dict[str, Any]] = {}
    validity_rank = {
        "valid": 4,
        "stale-but-usable": 3,
        "refresh-required": 2,
        "unknown": 1,
        "invalid": 0,
    }
    inventory_dirs = {
        _RESOURCE_COVERAGE_INVENTORY_DIR.resolve(),
        _COVERAGE_INVENTORY_DIR.resolve(),
    }
    for path in sorted(
        candidate
        for directory in inventory_dirs
        if directory.is_dir()
        for candidate in directory.glob("*.json")
    ):
        inventory = field_selector.load_coverage_inventory(path)
        for field in inventory["field_results"]:
            key = field_selector._coordinate_key(field["ra_deg"], field["dec_deg"])
            candidate = {
                **field,
                "coverage_provenance": {
                    **field["coverage_provenance"],
                    "inventory_path": path.relative_to(_RESOURCE_ROOT).as_posix()
                    if path.is_relative_to(_RESOURCE_ROOT)
                    else str(path),
                    "batch_id": inventory["batch_id"],
                    "batch_manifest_sha256": inventory["batch_manifest_sha256"],
                },
            }
            prior = combined.get(key)
            candidate_provenance = candidate["coverage_provenance"]
            prior_provenance = (prior or {}).get("coverage_provenance", {})
            candidate_order = (
                validity_rank.get(candidate_provenance["validity_state"], -1),
                candidate_provenance.get("retrieved_at_utc") or "",
            )
            prior_order = (
                validity_rank.get(prior_provenance.get("validity_state"), -1),
                prior_provenance.get("retrieved_at_utc") or "",
            )
            if prior is None or candidate_order > prior_order:
                combined[key] = candidate
    return combined


def _write_combined_inventory(
    combined: dict[tuple[float, float], dict[str, Any]], out_path: Path
) -> None:
    field_results = list(combined.values())
    payload = {
        "schema_version": "ztf-field-night-coverage-inventory-v1",
        "batch_id": "hunter_cli_combined_working_inventory",
        "batch_manifest_sha256": _content_sha256(field_results),
        "source": "merged validated Hunter coverage inventories",
        "source_version": f"content-sha256:{_content_sha256(field_results)}",
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "transformations": ["coordinate-keyed deterministic inventory merge"],
        "validity_state": "valid",
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


def _materialize_planning_catalog(
    *,
    db_path: Path,
    jd: float,
    neo_class: str,
    ranking_policy_path: Path,
) -> tuple[str, int]:
    """Persist the full explainable pre-selection universe before discovery."""

    rows = field_selector.select_fields(
        jd=jd,
        mode=neo_class,
        top_n=100_000,
        ranking_policy_path=ranking_policy_path,
        deduplicate=False,
    )
    if not rows:
        raise RuntimeError("planning catalog contains no viable candidates")
    policy = rows[0]["ranking_policy"]
    catalog_version = (
        f"{_PLANNING_CATALOG_SCHEMA}:{policy['sha256'][:16]}:"
        f"{neo_class}:{jd:.5f}"
    )
    provenance = {
        "schema_version": _PLANNING_CATALOG_SCHEMA,
        "source": "deterministic ICRS sky mesh ranked for ZTF DR24 historical replay",
        "ranking_policy": policy,
        "jd": jd,
        "grid_step_deg": field_selector._GRID_STEP_DEG,
        "storage_estimate_basis": (
            "3 * 27,311,040-byte live MP1 preflight; exact selected targets "
            "replace this with their summed HEAD content lengths"
        ),
        "storage_estimate_evidence": (
            "docs/evidence/live/2026-07-16-ztf-dr24-motion-product-"
            "preflight-first-live-run.md"
        ),
        "compute_estimate_status": (
            "uncalibrated transparent 180-second operator prior; not used in ranking"
        ),
    }
    targets = [
        _catalog_target_from_row(row, neo_class=neo_class, provenance=provenance)
        for row in rows
    ]
    count = hunter_state.upsert_target_catalog(
        db_path,
        catalog_version=catalog_version,
        targets=targets,
    )
    return catalog_version, count


def _catalog_target_from_row(
    row: dict[str, Any],
    *,
    neo_class: str,
    provenance: dict[str, Any],
) -> hunter_state.CatalogTarget:
    target_id = hunter_state.target_id_from_radec(row["ra_deg"], row["dec_deg"])
    return hunter_state.CatalogTarget(
        target_id=target_id,
        primary_survey_id=f"ztf-dr24-field:{target_id}",
        canonical_id=f"icrs:{row['ra_deg']:.2f}:{row['dec_deg']:.2f}:r3.5deg",
        target_kind="sky_field",
        survey="ZTF DR24 archival science images",
        ra_deg=row["ra_deg"],
        dec_deg=row["dec_deg"],
        neo_class=neo_class,
        ranking_score=row["score"],
        estimated_storage_mb=_estimated_storage_mb(row),
        estimated_compute_seconds=_UNCALIBRATED_TARGET_COMPUTE_SECONDS,
        scientific_metrics={
            "survey_scarcity_score": row.get("survey_scarcity_score"),
            "population_score": row.get("pop_score"),
            "geometry_score": row.get("geom_score"),
            "novelty_score": row.get("novelty_score"),
            "solar_elongation_deg": row.get("elongation_deg"),
            "ecliptic_latitude_deg": row.get("ecl_lat_deg"),
            "hours_visible": row.get("hours_visible"),
            "field_radius_deg": row.get("field_radius_deg", 3.5),
            "n_distinct_nights": len(row.get("coverage_nights", [])),
        },
        source_provenance=provenance,
    )


def _estimated_storage_mb(row: dict[str, Any]) -> float:
    exact = (row.get("coverage_provenance") or {}).get("exact_feasibility") or {}
    measured_bytes = sum(
        int(night.get("required_product_bytes") or 0)
        for night in exact.get("verified_nights", [])
    )
    return (
        round(measured_bytes / (1024 * 1024), 1)
        if measured_bytes > 0
        else _ESTIMATED_TARGET_STORAGE_MB
    )


def _live_coverage_check(
    fields: list[tuple[str, float, float]], batch_id_prefix: str
) -> dict[str, Any]:
    """Run one real, live coverage-preflight batch for the given fields and
    commit the resulting inventory. Shared by ``create-new-search --mode new``'s
    adaptive expansion and ``--mode follow-up``'s insufficient-coverage rechecks."""
    batch_id = f"{batch_id_prefix}_{uuid.uuid4().hex[:8]}"
    manifest_path = _BATCH_MANIFEST_DIR / f"{batch_id}.json"
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
    return merged


def _searched_by_sibling(
    row: dict[str, Any], cross_project_identities: frozenset[str]
) -> bool:
    """True when a sibling Hunter has already searched this candidate (IDENT-02).

    Matching is by *normalized minor-planet identity*, never by sky position: a
    field centre is not an object, and two Hunters agreeing on coordinates would
    be a coincidence rather than a shared target. A candidate carrying no
    interoperable designation cannot be matched and is therefore not excluded --
    that is the correct direction to fail, because excluding on a guess would
    silently discard real work.
    """
    if not cross_project_identities:
        return False
    from hunter_cross_project import normalize_neo_identity

    candidates = (
        row.get("canonical_id"),
        row.get("designation"),
        row.get("primary_survey_id"),
        *(row.get("aliases") or ()),
    )
    for raw in candidates:
        identity = normalize_neo_identity(raw)
        if identity is not None and identity in cross_project_identities:
            return True
    return False


def discover_new_targets(
    jd: float,
    neo_class: str,
    requested_n: int,
    max_pool: int | None,
    out_dir: Path,
    target_queue_path: Path,
    ranking_policy_path: Path,
    db_path: Path,
) -> dict[str, Any]:
    """Adaptive discovery loop for ``create-new-search --mode new``.

    Repeatedly grows the working coverage inventory (real, live IRSA metadata
    checks via inventory_ztf_field_night_coverage.py) for the next batch of
    top-ranked, not-yet-covered planning-grid fields until ``requested_n``
    eligible candidates exist or the reasonably accessible planning universe
    is exhausted. ``max_pool`` is an explicit operator safety limit only; if it
    prevents sufficiency, the caller must fail rather than persist a misleading
    short manifest.
    """
    if requested_n <= 0:
        raise ValueError("requested_n must be positive")
    if max_pool is not None and max_pool <= 0:
        raise ValueError("max_pool must be positive when supplied")
    combined = _combined_known_coverage()
    checked_coords: set[tuple[float, float]] = set(combined.keys())
    # Local search history: targets this Hunter has already searched.
    governing_history = hunter_state.searched_target_ids(db_path)

    # Cross-project search history (IDENT-02/IDENT-03). A target another Hunter
    # has already searched is not New here. The validity state is carried
    # alongside so the caller can disclose incompleteness rather than presenting
    # an unverified novelty decision as authoritative -- IDENT-03 forbids
    # 'stale-but-usable' from justifying a known-incomplete decision, and
    # 'unknown' means no sibling history has been imported at all.
    cross_project_identities = hunter_state.cross_project_searched_identities(db_path)
    cross_project_validity = hunter_state.cross_project_history_validity(db_path)
    eligible: list[dict[str, Any]] = []
    working_inventory_path = out_dir / "working_coverage_inventory.json"
    round_index = 0
    universe_exhausted = False
    exploration_limited = False

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
            eligible = [
                row
                for row in eligible
                if hunter_state.target_id_from_radec(row["ra_deg"], row["dec_deg"])
                not in governing_history
                and not _searched_by_sibling(row, cross_project_identities)
            ]
        if len(eligible) >= requested_n:
            stale_selected = [
                row
                for row in eligible[:requested_n]
                if row["coverage_provenance"]["validity_state"] != "valid"
            ]
            if stale_selected:
                # A legacy inventory may support broad ranking, but exact
                # selected targets are refreshed before durable creation.
                for offset in range(0, len(stale_selected), coverage_inventory.MAX_FIELDS):
                    chunk = stale_selected[offset : offset + coverage_inventory.MAX_FIELDS]
                    fields = [
                        (
                            _field_id_from_radec("refresh", row["ra_deg"], row["dec_deg"]),
                            row["ra_deg"],
                            row["dec_deg"],
                        )
                        for row in chunk
                    ]
                    merged = _live_coverage_check(fields, "hunter_selected_refresh")
                    refreshed = field_selector.load_coverage_inventory(
                        _COVERAGE_INVENTORY_DIR / f"{merged['batch_id']}.json"
                    )
                    for field in refreshed["field_results"]:
                        key = field_selector._coordinate_key(
                            field["ra_deg"], field["dec_deg"]
                        )
                        combined[key] = field
                continue
            break
        if max_pool is not None and len(checked_coords) >= max_pool:
            exploration_limited = True
            break

        batch_size = max(3 * requested_n, 10) * (2**round_index)
        if max_pool is not None:
            batch_size = min(batch_size, max_pool - len(checked_coords))
        candidates = _next_uncovered_planning_candidates(
            jd, neo_class, checked_coords, batch_size, ranking_policy_path
        )
        if not candidates:
            universe_exhausted = True
            break

        round_index += 1
        fields = [
            (_field_id_from_radec(f"hx{round_index}", ra, dec), ra, dec)
            for ra, dec in candidates
        ]
        merged = _live_coverage_check(fields, f"hunter_expand_{neo_class}_r{round_index}")
        for field in merged["field_results"]:
            key = field_selector._coordinate_key(field["ra_deg"], field["dec_deg"])
            combined[key] = field
            checked_coords.add(key)

    return {
        "eligible": eligible,
        "pool_size_explored": len(checked_coords),
        "sufficiency_met": len(eligible) >= requested_n,
        "universe_exhausted": universe_exhausted,
        "exploration_limited": exploration_limited,
        # Cross-project novelty evidence (IDENT-03, IDENT-04, DISC-02). Persisted
        # rather than merely consulted: a novelty decision made against history
        # that was 'unknown' or 'stale-but-usable' is not authoritative, and a
        # reader must be able to see that after the fact rather than assume the
        # exclusion was complete.
        "cross_project_history_validity": cross_project_validity,
        "cross_project_identities_known": len(cross_project_identities),
        "cross_project_limitation": (
            ""
            if cross_project_validity == "valid"
            else (
                "Sibling search history is "
                f"'{cross_project_validity}'. Targets already searched by another "
                "Hunter may not have been excluded."
            )
        ),
    }


def _write_manifest_csv(search_id: str, rows: list[dict[str, Any]]) -> Path:
    _SEARCH_MANIFEST_CSV_DIR.mkdir(parents=True, exist_ok=True)
    path = _SEARCH_MANIFEST_CSV_DIR / f"{search_id}.csv"
    fieldnames = [
        "rank",
        "target_id",
        "primary_survey_id",
        "canonical_id",
        "target_kind",
        "survey",
        "search_mode",
        "ra_deg",
        "dec_deg",
        "distance_ly",
        "estimated_storage_mb",
        "estimated_compute_seconds",
        "prior_search_count",
        "prior_search_provenance",
        "score",
        "selection_reason",
        "scientific_metrics",
        "coverage_inventory_id",
        "validity_state",
        "coverage_source",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            serialized = {
                **row,
                "prior_search_provenance": _json_cell(
                    row["prior_search_provenance"]
                ),
                "scientific_metrics": _json_cell(row["scientific_metrics"]),
            }
            writer.writerow({"rank": i, **serialized})
    return path


def _json_cell(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _print_table(search_id: str, rows: list[dict[str, Any]]) -> None:
    print(f"\nSearch manifest {search_id} -- {len(rows)} target(s) selected (pending):\n")
    header = (
        f"{'rank':>4}  {'target_id':<22}  {'survey':<9}  {'mode':<9}  "
        f"{'prior':>5}  {'MB':>7}  {'CPU-s':>7}  {'score':>7}"
    )
    print(header)
    print("-" * len(header))
    for i, row in enumerate(rows, start=1):
        print(
            f"{i:>4}  {row['target_id']:<22}  {'ZTF DR24':<9}  "
            f"{row['search_mode']:<9}  {row['prior_search_count']:>5}  "
            f"{row['estimated_storage_mb']:>7.1f}  "
            f"{row['estimated_compute_seconds']:>7.1f}  {row['score']:>7.4f}"
        )
        print(
            f"      primary={row['primary_survey_id']}  canonical={row['canonical_id']}  "
            f"type={row['target_kind']}  distance_ly={row['distance_ly']}"
        )
        print(
            f"      metrics={_json_cell(row['scientific_metrics'])}  "
            f"prior={_json_cell(row['prior_search_provenance'])}"
        )
        print(f"      reason={row['selection_reason']}")
    print()


_INSUFFICIENT_COVERAGE_STATUS = "insufficient_coverage"


def _followup_candidates_from_registry(db_path: Path) -> list[dict[str, Any]]:
    """Real, durable follow-up-worthy targets: open registry entries left by a
    prior SURVIVE/BORDERLINE adversarial-review verdict (see run-new-search)."""
    candidates = []
    for entry in hunter_state.list_follow_ups(db_path, status="open"):
        ra_deg, dec_deg = hunter_state.radec_from_target_id(entry["target_id"])
        candidates.append(
            {
                "ra_deg": ra_deg,
                "dec_deg": dec_deg,
                "score": 2.0 + float(entry["priority"]),
                "absolute_quality": float(entry["priority"]),
                "value_tier": "open_review_survivor",
                "reason": (
                    "tier=open_review_survivor; "
                    f"followup_value={float(entry['priority']):.4f}; {entry['reason']}"
                ),
                "field_id": None,
            }
        )
    return candidates


def _followup_candidates_from_insufficient_coverage(
    target_queue_path: Path,
) -> tuple[list[dict[str, Any]], int]:
    """Real target_priority_queue.csv rows marked insufficient_coverage,
    re-checked against this project's *current* coverage window -- a
    genuinely different historical slice of the real ZTF archive than
    whichever window originally found them insufficient -- via one real,
    live IRSA metadata query per not-yet-known field. Returns
    (candidates_now_sufficient, n_still_insufficient)."""
    rows: list[tuple[float, float]] = []
    with target_queue_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") != _INSUFFICIENT_COVERAGE_STATUS:
                continue
            match = field_selector._COORDINATE_PATTERN.search(row.get("notes", ""))
            if match is None:
                continue
            rows.append((float(match.group(1)), float(match.group(2))))
    if not rows:
        return [], 0

    combined = _combined_known_coverage()
    to_check = [
        (ra, dec) for ra, dec in rows if field_selector._coordinate_key(ra, dec) not in combined
    ]
    if to_check:
        fields = [
            (_field_id_from_radec("followup_recheck", ra, dec), ra, dec) for ra, dec in to_check
        ]
        merged = _live_coverage_check(fields, "hunter_followup_recheck")
        for field in merged["field_results"]:
            key = field_selector._coordinate_key(field["ra_deg"], field["dec_deg"])
            combined[key] = field

    candidates: list[dict[str, Any]] = []
    n_still_insufficient = 0
    for ra, dec in rows:
        field = combined.get(field_selector._coordinate_key(ra, dec))
        if field is None or not field["passes_min_distinct_nights"]:
            n_still_insufficient += 1
            continue
        candidates.append(
            {
                "ra_deg": ra,
                "dec_deg": dec,
                "score": min(1.0, field["n_distinct_nights"] / 100.0),
                "absolute_quality": min(1.0, field["n_distinct_nights"] / 100.0),
                "value_tier": "recovered_coverage_retry",
                "reason": (
                    "tier=recovered_coverage_retry; "
                    f"previously {_INSUFFICIENT_COVERAGE_STATUS}; now has "
                    f"{field['n_distinct_nights']} real distinct night(s) under the "
                    "current coverage window"
                ),
                "field_id": field["field_id"],
            }
        )
    return candidates, n_still_insufficient


def _followup_candidates_from_history(db_path: Path) -> list[dict[str, Any]]:
    """Rank only unresolved failed executions by remaining covered nights.

    A success or null result closes the ordinary search obligation. Such a
    target becomes eligible again only through an explicit open follow-up
    registry entry produced by SURVIVE/BORDERLINE adversarial review.
    """
    combined = _combined_known_coverage()
    by_target: dict[str, list[dict[str, Any]]] = {}
    for event in hunter_state.list_target_history(db_path):
        if event["status"] not in {"success", "null_result", "failed"}:
            continue
        by_target.setdefault(event["target_id"], []).append(event)

    candidates: list[dict[str, Any]] = []
    for target_id, events in by_target.items():
        ra_deg, dec_deg = hunter_state.radec_from_target_id(target_id)
        field = combined.get(field_selector._coordinate_key(ra_deg, dec_deg))
        if field is None:
            continue
        acquired = hunter_state.acquired_nights_for_target(db_path, target_id)
        remaining = [
            night for night in field["distinct_nights_yyyymmdd"] if night not in acquired
        ]
        if len(remaining) < int(_DEFAULT_COVERAGE_WINDOW["min_distinct_nights"]):
            continue
        if events[-1]["status"] != "failed":
            continue
        remaining_fraction = min(1.0, len(remaining) / 100.0)
        candidates.append(
            {
                "ra_deg": ra_deg,
                "dec_deg": dec_deg,
                "score": 1.0 + remaining_fraction,
                "absolute_quality": remaining_fraction,
                "value_tier": "failed_execution_retry",
                "reason": (
                    "tier=failed_execution_retry; "
                    f"{len(remaining)} current-valid "
                    f"covered night(s) remain after {len(acquired)} acquired night(s)"
                ),
                "field_id": field["field_id"],
            }
        )
    return candidates


def discover_followup_targets(
    db_path: Path,
    requested_n: int,
    target_queue_path: Path,
    follow_up_policy_path: Path = _DEFAULT_FOLLOW_UP_POLICY,
) -> dict[str, Any]:
    """Follow-up mode selection for ``create-new-search --mode follow-up``.

    Ranks real, existing follow-up-worthy targets from two sources: open
    ``follow_up_registry`` entries (candidates that survived adversarial
    review and await operator attention) and ``target_priority_queue.csv``
    rows marked ``insufficient_coverage`` that have since become sufficient
    under this project's current coverage window (one more real night closes
    the 3-night minimum). No fabricated evidence -- a field that is still
    insufficient after a live recheck is reported, not silently dropped.
    """
    policy = _load_follow_up_policy(follow_up_policy_path)
    registry_candidates = _followup_candidates_from_registry(db_path)
    history_candidates = _followup_candidates_from_history(db_path)
    recovered_candidates, n_still_insufficient = _followup_candidates_from_insufficient_coverage(
        target_queue_path
    )
    # One target may be supported by both a candidate-level registry entry and
    # target-level search history. Keep the strongest explainable reason.
    deduplicated: dict[str, dict[str, Any]] = {}
    for candidate in registry_candidates + history_candidates + recovered_candidates:
        target_id = hunter_state.target_id_from_radec(
            candidate["ra_deg"], candidate["dec_deg"]
        )
        prior = deduplicated.get(target_id)
        if prior is None or candidate["score"] > prior["score"]:
            deduplicated[target_id] = candidate
    all_candidates = sorted(
        deduplicated.values(),
        key=lambda c: (-float(c["score"]), float(c["ra_deg"]), float(c["dec_deg"])),
    )
    return {
        "eligible": all_candidates,
        "pool_size_explored": len(all_candidates) + n_still_insufficient,
        "sufficiency_met": len(all_candidates) >= requested_n,
        "ranking_policy": policy,
    }


def _exact_target_feasibility(
    row: dict[str, Any],
    broad_nights: list[str],
    min_observations: int = 3,
) -> dict[str, Any]:
    """Prove that the exact 0.01-degree target can execute before selection.

    Wide coverage is only a discovery hint. For each candidate night this
    performs an exact-position metadata query, narrows to one exposure, and
    HEAD-checks every product required by pixel extraction. No product body is
    downloaded. Expected exact-footprint misses are recorded as ineligible;
    provider/parse failures still propagate and fail the production request.
    """
    target_id = hunter_state.target_id_from_radec(row["ra_deg"], row["dec_deg"])
    root = _WORKING_DIR / "exact_feasibility" / target_id
    window = _DEFAULT_COVERAGE_WINDOW
    exact_report = bounded_ingest.run_bounded_ingest(
        ra=row["ra_deg"],
        dec=row["dec_deg"],
        size_deg=_DEFAULT_SIZE_DEG,
        start_jd=float(window["start_jd_exclusive"]),
        end_jd=float(window["end_jd_exclusive"]),
        out_dir=root / "exact_inventory",
    )
    exact_table = bounded_ingest._parse_ipac_table(
        Path(exact_report["raw_response_path"]).read_text(encoding="utf-8")
    )
    allowed_nights = set(broad_nights)
    obsjds = sorted(float(value) for value in exact_table["obsjd"])
    from astropy.time import Time

    first_obsjd_by_night: dict[str, float] = {}
    for obsjd in obsjds:
        night = Time(obsjd, format="jd").datetime.strftime("%Y%m%d")
        if night in allowed_nights:
            first_obsjd_by_night.setdefault(night, obsjd)

    verified: list[dict[str, Any]] = []
    misses: list[dict[str, str]] = []
    for night, target_jd in first_obsjd_by_night.items():
        if len(verified) >= min_observations:
            break
        epsilon = 1.0 / 1440.0
        for _ in range(4):
            start_jd, end_jd = target_jd - epsilon, target_jd + epsilon
            if sum(1 for obsjd in obsjds if start_jd < obsjd < end_jd) == 1:
                break
            epsilon /= 10.0
        else:
            raise RuntimeError(
                f"could not isolate one exact exposure at JD={target_jd}"
            )
        try:
            report = bounded_ingest.run_bounded_ingest(
                ra=row["ra_deg"],
                dec=row["dec_deg"],
                size_deg=_DEFAULT_SIZE_DEG,
                start_jd=start_jd,
                end_jd=end_jd,
                out_dir=root / "product_preflight" / night,
                emit_motion_product_manifest=True,
                preflight_motion_products=True,
                max_preflight_exposures=1,
                preflight_workers=1,
            )
        except RuntimeError as exc:
            message = str(exc)
            if not (
                message.startswith("no exposure found")
                or message.startswith("motion-product preflight failed")
            ):
                raise
            misses.append({"night": night, "reason": message})
            continue
        manifest_path = Path(report["motion_product_manifest_path"])
        product_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verified.append(
            {
                "night_yyyymmdd": night,
                "start_jd": start_jd,
                "end_jd": end_jd,
                "metadata_sha256": report["raw_response_sha256"],
                "product_manifest_sha256": hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest(),
                "required_product_bytes": product_manifest["preflight"][
                    "total_content_bytes"
                ],
            }
        )
    return {
        "schema_version": "hunter-exact-target-feasibility-v1",
        "source": "IRSA ZTF science metadata plus required-product HEAD preflight",
        "source_version": (
            f"exact-inventory-sha256:{exact_report['raw_response_sha256']}"
        ),
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "transformations": [
            "exact 0.01-degree metadata query",
            "single-exposure window isolation",
            "difference-image, mask, and PSF HEAD availability preflight",
        ],
        "validity_state": "valid" if len(verified) >= min_observations else "invalid",
        "size_deg": _DEFAULT_SIZE_DEG,
        "exact_inventory_rows": len(exact_table),
        "exact_inventory_distinct_nights": len(first_obsjd_by_night),
        "minimum_nights": min_observations,
        "verified_nights": verified,
        "exact_misses": misses,
        "passes": len(verified) >= min_observations,
    }


def _attach_current_coverage(
    rows: list[dict[str, Any]], requested_n: int | None = None
) -> list[dict[str, Any]]:
    """Return the highest-ranked exact-executable rows with current evidence.

    Candidates that pass the broad 2-degree discovery preflight but fail at
    the exact 0.01-degree execution footprint are rejected here and the next
    ranked candidate is tested. This is selection, not an execution fallback.
    """
    needed = len(rows) if requested_n is None else requested_n
    combined = _combined_known_coverage()
    enriched: list[dict[str, Any]] = []
    # Refresh only the ranked frontier currently needed. If exact footprints
    # fail, advance to the next frontier chunk. This keeps provider work
    # adaptive instead of eagerly refreshing the entire broad eligible set.
    frontier_size = max(needed, min(coverage_inventory.MAX_FIELDS, 3 * needed))
    for frontier_offset in range(0, len(rows), frontier_size):
        frontier = rows[frontier_offset : frontier_offset + frontier_size]
        needs_refresh = [
            row
            for row in frontier
            if (
                (field := combined.get(
                    field_selector._coordinate_key(row["ra_deg"], row["dec_deg"])
                ))
                is None
                or field["coverage_provenance"]["validity_state"] != "valid"
            )
        ]
        for offset in range(0, len(needs_refresh), coverage_inventory.MAX_FIELDS):
            chunk = needs_refresh[offset : offset + coverage_inventory.MAX_FIELDS]
            fields = [
                (
                    _field_id_from_radec("selected", row["ra_deg"], row["dec_deg"]),
                    row["ra_deg"],
                    row["dec_deg"],
                )
                for row in chunk
            ]
            merged = _live_coverage_check(fields, "hunter_exact_target_refresh")
            refreshed = field_selector.load_coverage_inventory(
                _COVERAGE_INVENTORY_DIR / f"{merged['batch_id']}.json"
            )
            for field in refreshed["field_results"]:
                combined[
                    field_selector._coordinate_key(field["ra_deg"], field["dec_deg"])
                ] = field

        for row in frontier:
            if len(enriched) >= needed:
                return enriched
            field = combined.get(
                field_selector._coordinate_key(row["ra_deg"], row["dec_deg"])
            )
            if field is None or not field["passes_min_distinct_nights"]:
                continue
            exact = _exact_target_feasibility(
                row,
                field["distinct_nights_yyyymmdd"],
                int(_DEFAULT_COVERAGE_WINDOW["min_distinct_nights"]),
            )
            if not exact["passes"]:
                print(
                    f"[exact-feasibility] rejected RA={row['ra_deg']} "
                    f"Dec={row['dec_deg']}: {len(exact['verified_nights'])}/"
                    f"{exact['minimum_nights']} exact executable night(s)",
                    flush=True,
                )
                continue
            enriched.append(
                {
                    **row,
                    "field_id": field["field_id"],
                    "coverage_provenance": {
                        **field["coverage_provenance"],
                        "exact_feasibility": exact,
                    },
                    "coverage_nights": [
                        item["night_yyyymmdd"] for item in exact["verified_nights"]
                    ],
                }
            )
    return enriched


def cmd_create_new_search(args: argparse.Namespace) -> int:
    if args.targets <= 0:
        raise ValueError("requested_n must be positive")
    emit_event(
        _event_path(args),
        event="create_search",
        status="started",
        command="Create-New-Search",
        requested_n=args.targets,
        mode=args.mode,
        neo_class=args.neo_class,
    )
    ranking_policy_path = Path(args.ranking_policy)
    target_queue_path = Path(args.target_queue)
    db_path = Path(args.db)

    if args.mode == "new":
        ranking_policy = field_selector.load_ranking_policy(ranking_policy_path)
        if args.jd == "now":
            from astropy.time import Time

            jd = float(Time.now().jd)
        else:
            jd = float(args.jd)

        catalog_version, catalog_size = _materialize_planning_catalog(
            db_path=db_path,
            jd=jd,
            neo_class=args.neo_class,
            ranking_policy_path=ranking_policy_path,
        )
        if args.neo_class == "all" and catalog_size < 10_000:
            raise RuntimeError(
                "all-sky planning catalog must contain at least 10,000 viable "
                f"candidates, found {catalog_size}"
            )
        out_dir = _WORKING_DIR / "coverage_expansion"
        result = discover_new_targets(
            jd=jd,
            neo_class=args.neo_class,
            requested_n=args.targets,
            max_pool=args.max_pool,
            out_dir=out_dir,
            target_queue_path=target_queue_path,
            ranking_policy_path=ranking_policy_path,
            db_path=db_path,
        )
        config: dict[str, Any] = {
            "neo_class": args.neo_class,
            "jd": jd,
            "max_pool": args.max_pool,
            "catalog_version": catalog_version,
            "catalog_size": catalog_size,
        }
    else:
        follow_up_policy_path = Path(
            getattr(args, "follow_up_policy", _DEFAULT_FOLLOW_UP_POLICY)
        )
        result = discover_followup_targets(
            db_path=db_path,
            requested_n=args.targets,
            target_queue_path=target_queue_path,
            follow_up_policy_path=follow_up_policy_path,
        )
        ranking_policy = result["ranking_policy"]
        config = {
            "neo_class": args.neo_class,
            "catalog_version": (
                f"{_PLANNING_CATALOG_SCHEMA}:follow-up:"
                f"{ranking_policy['sha256'][:16]}"
            ),
        }

    if result.get("exploration_limited") and not result["sufficiency_met"]:
        raise RuntimeError(
            f"explicit --max-pool={args.max_pool} stopped discovery after "
            f"{result['pool_size_explored']} field(s) before {args.targets} valid targets "
            "were found; remove or increase the limit"
        )

    selected = _attach_current_coverage(result["eligible"], requested_n=args.targets)
    # Broad coverage can overstate exact executability. If it did, expand the
    # broad universe and keep testing lower-ranked candidates until N exact
    # targets are supported or the accessible universe/operator limit ends.
    while (
        args.mode == "new"
        and len(selected) < args.targets
        and not result.get("universe_exhausted", False)
        and not result.get("exploration_limited", False)
    ):
        prior_eligible_count = len(result["eligible"])
        support_target = prior_eligible_count + max(3 * args.targets, 10)
        result = discover_new_targets(
            jd=config["jd"],
            neo_class=args.neo_class,
            requested_n=support_target,
            max_pool=args.max_pool,
            out_dir=_WORKING_DIR / "coverage_expansion",
            target_queue_path=target_queue_path,
            ranking_policy_path=ranking_policy_path,
            db_path=db_path,
        )
        selected = _attach_current_coverage(
            result["eligible"], requested_n=args.targets
        )
        if len(result["eligible"]) <= prior_eligible_count:
            # Fail closed against a provider/selector implementation that
            # claims expansion but makes no progress.
            if not (
                result.get("universe_exhausted")
                or result.get("exploration_limited")
            ):
                raise RuntimeError(
                    "adaptive exact-feasibility expansion made no progress"
                )
            break
    exact_sufficiency_met = len(selected) >= args.targets
    if result.get("exploration_limited") and not exact_sufficiency_met:
        raise RuntimeError(
            f"explicit --max-pool={args.max_pool} stopped discovery after "
            f"{result['pool_size_explored']} field(s) before {args.targets} exact "
            "executable targets were found; remove or increase the limit"
        )
    if not exact_sufficiency_met:
        exhaustion = (
            "all valid follow-up evidence was exhausted"
            if args.mode == "follow-up"
            else (
                "the full accessible planning universe was exhausted"
                if result.get("universe_exhausted", True)
                else "the currently supported candidate frontier was exhausted"
            )
        )
        raise RuntimeError(
            f"cannot create search: only {len(selected)}/{args.targets} exact eligible "
            f"target(s) were found after exploring {result['pool_size_explored']} "
            f"candidate field(s); {exhaustion}"
        )
    selected_catalog_provenance = {
        "schema_version": _PLANNING_CATALOG_SCHEMA,
        "source": (
            "exact-feasibility-selected ZTF DR24 planning target"
            if args.mode == "new"
            else "durable prior-search/follow-up evidence"
        ),
        "ranking_policy": ranking_policy,
        "search_mode": args.mode,
        "storage_estimate_basis": (
            "selected targets sum exact HEAD content lengths; planning rows use "
            "3 * 27,311,040-byte live MP1 preflight from "
            "docs/evidence/live/2026-07-16-ztf-dr24-motion-product-"
            "preflight-first-live-run.md"
        ),
        "compute_estimate_status": (
            "uncalibrated transparent 180-second operator prior; not used in ranking"
        ),
    }
    hunter_state.upsert_target_catalog(
        db_path,
        catalog_version=config["catalog_version"],
        targets=[
            _catalog_target_from_row(
                row,
                neo_class=args.neo_class,
                provenance=selected_catalog_provenance,
            )
            for row in selected
        ],
    )
    config["catalog_size"] = max(
        int(config.get("catalog_size", 0)),
        hunter_state.target_catalog_count(
            db_path, catalog_version=config["catalog_version"]
        ),
    )
    manifest_targets = []
    for row in selected:
        target_id = hunter_state.target_id_from_radec(row["ra_deg"], row["dec_deg"])
        prior_history = hunter_state.list_target_history(db_path, target_id)
        scientific_metrics = {
            "geometry_score": row.get("geom_score"),
            "population_score": row.get("pop_score"),
            "survey_scarcity_score": row.get("survey_scarcity_score"),
            "novelty_score": row.get("novelty_score"),
            "solar_elongation_deg": row.get("elongation_deg"),
            "ecliptic_latitude_deg": row.get("ecl_lat_deg"),
            "hours_visible": row.get("hours_visible"),
            "n_distinct_nights": len(row.get("coverage_nights", [])),
            "coverage_nights": row.get("coverage_nights", []),
            "neo_class": args.neo_class,
        }
        manifest_targets.append(
            hunter_state.ManifestTarget(
            target_id=target_id,
            ra_deg=row["ra_deg"],
            dec_deg=row["dec_deg"],
            score=row["score"],
            selection_reason=row["reason"],
            coverage_inventory_id=row.get("field_id"),
            coverage_provenance=row["coverage_provenance"],
            validity_state=row["coverage_provenance"]["validity_state"],
            primary_survey_id=f"ztf-dr24-field:{target_id}",
            canonical_id=f"icrs:{row['ra_deg']:.2f}:{row['dec_deg']:.2f}:r3.5deg",
            target_kind="sky_field",
            survey="ZTF DR24 archival science images",
            prior_search_count=len(prior_history),
            prior_search_provenance=[
                {
                    "search_id": event["search_id"],
                    "run_id": event["run_id"],
                    "status": event["status"],
                    "occurred_at": event["occurred_at"],
                    "source": event["source"],
                }
                for event in prior_history
            ],
            estimated_storage_mb=_estimated_storage_mb(row),
            estimated_compute_seconds=_UNCALIBRATED_TARGET_COMPUTE_SECONDS,
            scientific_metrics=scientific_metrics,
        )
        )

    mode_slug = args.mode.replace("-", "_")
    search_id = (
        f"search_{mode_slug}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    hunter_state.create_search_manifest(
        db_path=db_path,
        search_id=search_id,
        mode=mode_slug,
        requested_n=args.targets,
        ranking_policy_path=ranking_policy["path"],
        ranking_policy_digest=ranking_policy["sha256"],
        targets=manifest_targets,
        discovery_pool_size_explored=result["pool_size_explored"],
        sufficiency_met=exact_sufficiency_met,
        config=config,
    )

    manifest_rows = [
        {
            "target_id": t.target_id,
            "primary_survey_id": t.primary_survey_id,
            "canonical_id": t.canonical_id,
            "target_kind": t.target_kind,
            "survey": t.survey,
            "search_mode": args.mode,
            "ra_deg": t.ra_deg,
            "dec_deg": t.dec_deg,
            "distance_ly": "not_applicable_solar_system_sky_field",
            "estimated_storage_mb": t.estimated_storage_mb,
            "estimated_compute_seconds": t.estimated_compute_seconds,
            "prior_search_count": t.prior_search_count,
            "prior_search_provenance": t.prior_search_provenance or [],
            "score": t.score,
            "selection_reason": t.selection_reason,
            "scientific_metrics": t.scientific_metrics or {},
            "coverage_inventory_id": t.coverage_inventory_id,
            "validity_state": t.validity_state,
            "coverage_source": (t.coverage_provenance or {}).get("source", "unknown"),
        }
        for t in manifest_targets
    ]
    if args.targets <= 100:
        _print_table(search_id, manifest_rows)
    else:
        csv_path = _write_manifest_csv(search_id, manifest_rows)
        print(f"Search manifest written: {csv_path}")

    print(
        f"search_id={search_id}  status=pending  requested_n={args.targets}  "
        f"selected_n={len(manifest_targets)}  "
        f"pool_explored={result['pool_size_explored']}  "
        f"sufficiency_met={exact_sufficiency_met}"
    )
    emit_event(
        _event_path(args),
        event="create_search",
        status="completed",
        command="Create-New-Search",
        search_id=search_id,
        requested_n=args.targets,
        selected_n=len(manifest_targets),
        mode=args.mode,
        catalog_size=config.get("catalog_size"),
        state_root=str(_PATHS.state_root),
    )
    return 0


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=False
    )
    return result.stdout.strip() or "unknown"


def _git_provenance() -> dict[str, Any]:
    """Return the exact commit plus whether tracked pipeline code is modified."""
    if not (REPO_ROOT / ".git").exists():
        try:
            version = importlib.metadata.version("neo-detection")
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        return {
            "commit": "installed-distribution",
            "distribution_version": version,
            "tracked_worktree_dirty": False,
        }
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    return {
        "commit": _git_sha(),
        "tracked_worktree_dirty": status.returncode != 0 or bool(status.stdout.strip()),
    }


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
    target: dict[str, Any],
    checkpoint_root: Path,
    size_deg: float,
    min_observations: int = 3,
    previously_acquired_nights: set[str] | None = None,
) -> dict[str, Any]:
    """Acquire, link/score, and adversarially review one manifest target.

    Returns {"execution_status", "candidate_ids", "nights_acquired", "scored_candidates"}.
    Raises on genuine failure -- the caller is responsible for catching,
    recording, and continuing to the next target (a per-target failure must
    never silently abort the whole run, per the Hunter directive).
    """
    ra_deg, dec_deg = target["ra_deg"], target["dec_deg"]
    prior_nights = previously_acquired_nights or set()
    exact = (target.get("coverage_provenance") or {}).get("exact_feasibility")
    if not isinstance(exact, dict) or exact.get("validity_state") != "valid":
        raise RuntimeError(
            f"target {target['target_id']} lacks valid exact-feasibility provenance"
        )
    nights_available = [
        item["night_yyyymmdd"]
        for item in exact.get("verified_nights", [])
        if item["night_yyyymmdd"] not in prior_nights
    ]
    if len(nights_available) < min_observations:
        raise RuntimeError(
            f"target {target['target_id']} has only {len(nights_available)} known covered "
            f"night(s), fewer than min_observations={min_observations}"
        )

    target_root = checkpoint_root / target["target_id"]
    obs_dir = target_root / "observations"
    acquired_nights: list[str] = []
    skipped_nights: list[str] = []
    for night in nights_available:
        if len(acquired_nights) >= min_observations:
            break
        try:
            _acquire_and_convert_night(ra_deg, dec_deg, night, size_deg, target_root)
            acquired_nights.append(night)
        except RuntimeError as exc:
            # Product state may change after manifest creation. Preserve the
            # durable failure and try another preflight-verified night if one
            # exists; never substitute a different target during execution.
            print(
                f"[run-new-search] night {night} did not resolve at the narrow "
                f"acquisition box ({exc}); trying next available night",
                flush=True,
            )
            skipped_nights.append(night)

    if len(acquired_nights) < min_observations:
        raise RuntimeError(
            f"only acquired {len(acquired_nights)}/{min_observations} real exposure(s) for "
            f"target {target['target_id']} after trying "
            f"{len(acquired_nights) + len(skipped_nights)}/{len(nights_available)} "
            "available covered night(s)"
        )

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
        # Cross-survey confirmation is optional, but epoch-specific known-object
        # eligibility is mandatory. Reuse the review module's live, fail-closed
        # SkyBoT/MPC providers while keeping optional enrichment offline.
        verdict = adversarial_review.run_adversarial_review(
            neo,
            offline=True,
            skybot_query=adversarial_review._query_skybot_at_epoch,
            first_observation_query=adversarial_review._query_mpc_first_observation_jd,
        )
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
    git_provenance = _git_provenance()
    known_object_challenge = next(
        (
            {
                "name": challenge.name,
                "outcome": challenge.outcome,
                "reason": challenge.reason,
                "details": challenge.details,
            }
            for challenge in verdict.challenges
            if challenge.name == "known_object_epoch_association"
        ),
        None,
    )
    defaults = candidate_ledger.CandidateLedgerDefaults(
        source_dataset_id=f"hunter-search:{search_id}",
        candidate_generator="Skills/hunter_cli.py run-new-search",
        regeneration_command=(
            f"uv run --python 3.14 python Skills/hunter_cli.py run-new-search "
            f"--search-id {search_id}"
        ),
        target_id=target["target_id"],
        raw_uri=f"hunter-checkpoint:{run_id}/{target['target_id']}",
        preprocess_version=(
            f"git:{git_provenance['commit']}:"
            f"dirty={str(git_provenance['tracked_worktree_dirty']).lower()}:"
            "src/preprocess.py"
        ),
        review_status=verdict.verdict.lower(),
        review_notes=verdict.summary,
        candidate_generator_params={
            "search_id": search_id,
            "run_id": run_id,
            "known_object_association": known_object_challenge,
            "validity_state": (
                "valid"
                if known_object_challenge
                and known_object_challenge["outcome"] in {"PASS", "WARNING", "FAIL"}
                and "error" not in known_object_challenge["details"]
                else "invalid"
            ),
        },
        model_versions={
            "pipeline_git": git_provenance,
            "known_object_policy": adversarial_review._KNOWN_OBJECT_POLICY_VERSION,
        },
    )
    record = candidate_ledger.record_from_packet(packet, defaults)
    candidate_ledger.upsert_record(ledger_db_path, record)

    if verdict.verdict in _FOLLOW_UP_VERDICTS:
        followup_value = float((packet.get("metadata") or {}).get("followup_value") or 0.0)
        hunter_state.add_follow_up(
            db_path,
            target_id=target["target_id"],
            reason=f"adversarial review verdict={verdict.verdict}: {verdict.summary}",
            priority=followup_value,
            recommended_action="operator review before any MPC submission consideration",
            evidence_ref=f"candidate_ledger:{record['candidate_id']}",
            candidate_id=record["candidate_id"],
            originating_run_id=run_id,
            required_data=(
                "operator review packet; if approved, independent follow-up astrometry"
            ),
            estimated_storage_mb=float(target.get("estimated_storage_mb", 0.0)),
            estimated_compute_seconds=float(
                target.get("estimated_compute_seconds", 0.0)
            ),
        )


def _mark_originating_followups_actioned(
    db_path: Path, target_id: str, current_run_id: str
) -> None:
    """After a follow-up-mode target is genuinely executed (success or
    null_result -- not failed), close out any open registry entry that
    selected it, so it is not re-selected by a future follow-up search.
    Matches by target_id rather than a dedicated foreign key -- the registry
    is small and this avoids a schema migration for a one-to-few lookup."""
    for entry in hunter_state.list_follow_ups(db_path, status="open"):
        if (
            entry["target_id"] == target_id
            and entry["originating_run_id"] != current_run_id
        ):
            hunter_state.update_follow_up_status(db_path, entry["follow_up_id"], "actioned")


def _execution_contract(workers: int) -> dict[str, Any]:
    """Validate and provenance-stamp bounded target concurrency.

    Each target owns an isolated checkpoint directory. Only target execution
    runs in worker threads; candidate-ledger, follow-up, history, and run-state
    writes remain serialized in manifest rank order. The three-worker ceiling
    is the repository's documented conservative limit for concurrent IRSA
    pixel-product downloads.
    """
    if workers < 1 or workers > _MAX_RUN_WORKERS:
        raise ValueError(
            f"workers must be between 1 and {_MAX_RUN_WORKERS} "
            "(the documented IRSA pixel-product concurrency limit)"
        )
    return {
        "scheduler": "thread_pool_manifest_order_commit_v1",
        "configured_workers": workers,
        "max_workers": _MAX_RUN_WORKERS,
        "durable_commit_order": "manifest_rank",
    }


def run_search(
    db_path: Path,
    ledger_db_path: Path,
    search_id: str,
    checkpoint_root: Path,
    size_deg: float = _DEFAULT_SIZE_DEG,
    workers: int = _DEFAULT_RUN_WORKERS,
    event_log: Path = _EVENT_LOG,
) -> dict[str, Any]:
    """Execute the exact persisted manifest for ``search_id``. Never
    regenerates the target selection. Resumes an interrupted OR partially/
    fully failed run in place (retrying only the not-yet-successful targets);
    refuses to silently re-execute a run that fully completed."""
    execution_contract = _execution_contract(workers)
    manifest = hunter_state.get_search_manifest(db_path, search_id)
    git_provenance = _git_provenance()
    if manifest["status"] == "executed":
        existing_run = hunter_state.get_latest_run_for_search(db_path, search_id)
        raise ValueError(
            f"search {search_id} was already executed "
            f"(run_id={existing_run['run_id'] if existing_run else 'unknown'}); "
            "create a new search rather than re-running a completed one"
        )
    if manifest["status"] != "pending":
        raise ValueError(f"search {search_id} has unexpected status {manifest['status']!r}")
    if (
        not manifest["sufficiency_met"]
        or manifest["requested_n"] <= 0
        or manifest["actual_n_selected"] != manifest["requested_n"]
        or len(manifest["targets"]) != manifest["requested_n"]
    ):
        raise ValueError(
            f"search {search_id} is incomplete: requested_n={manifest['requested_n']} "
            f"actual_n_selected={manifest['actual_n_selected']} "
            f"sufficiency_met={manifest['sufficiency_met']}; "
            "create a new sufficient search instead of executing partial work"
        )

    existing_run = hunter_state.get_latest_run_for_search(db_path, search_id)
    if existing_run is not None and existing_run["status"] != "completed":
        prior_contract = existing_run["model_versions"].get("execution_contract")
        if prior_contract is not None and prior_contract != execution_contract:
            raise ValueError(
                f"run {existing_run['run_id']} was created with "
                f"workers={prior_contract.get('configured_workers')}; resume with the "
                "same --workers value to preserve its execution contract"
            )
        if prior_contract is None:
            hunter_state.update_search_run_model_versions(
                db_path, existing_run["run_id"], {"execution_contract": execution_contract}
            )
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
            db_path,
            run_id,
            search_id,
            git_provenance["commit"],
            model_versions={
                "ranking_policy_digest": manifest["ranking_policy_digest"],
                "known_object_policy": adversarial_review._KNOWN_OBJECT_POLICY_VERSION,
                "pipeline_git": git_provenance,
                "execution_contract": execution_contract,
            },
        )
    emit_event(
        event_log,
        event="run_search",
        status="started",
        command="Run-New-Search",
        search_id=search_id,
        run_id=run_id,
        requested_n=manifest["requested_n"],
        workers=workers,
    )

    already_done = hunter_state.get_run_targets(db_path, run_id)
    pending_targets: list[dict[str, Any]] = []
    prior_nights_by_target: dict[str, set[str]] = {}
    for target in manifest["targets"]:
        target_id = target["target_id"]
        prior = already_done.get(target_id)
        if prior is not None and prior["execution_status"] in {"success", "null_result"}:
            print(
                f"[resume] target {target_id} already {prior['execution_status']}, skipping",
                flush=True,
            )
            continue

        prior_nights_by_target[target_id] = (
            hunter_state.acquired_nights_for_target(db_path, target_id)
            if manifest["mode"] == "follow_up"
            else set()
        )
        pending_targets.append(target)

    futures: dict[str, Any] = {}
    if pending_targets:
        active_workers = min(workers, len(pending_targets))
        print(
            f"[run-new-search] dispatching {len(pending_targets)} target(s) with "
            f"workers={active_workers}; durable commits remain in manifest rank order",
            flush=True,
        )
        with ThreadPoolExecutor(
            max_workers=active_workers, thread_name_prefix="neo-hunter-target"
        ) as executor:
            for target in pending_targets:
                target_id = target["target_id"]
                print(
                    f"[run-new-search] queued target {target_id} "
                    f"({target['ra_deg']}, {target['dec_deg']})",
                    flush=True,
                )
                futures[target_id] = executor.submit(
                    execute_target,
                    target,
                    checkpoint_root,
                    size_deg,
                    previously_acquired_nights=prior_nights_by_target[target_id],
                )

            for target in pending_targets:
                target_id = target["target_id"]
                try:
                    result = futures[target_id].result()
                    for scored in result["scored_candidates"]:
                        _ingest_and_maybe_register_followup(
                            db_path, ledger_db_path, search_id, run_id, target, scored
                        )
                    if manifest["mode"] == "follow_up":
                        _mark_originating_followups_actioned(db_path, target_id, run_id)
                    # This single transaction is deliberately last. Resume can skip a
                    # terminal target only after every external durable side effect
                    # above has completed successfully.
                    hunter_state.commit_target_result(
                        db_path,
                        run_id=run_id,
                        search_id=search_id,
                        mode=manifest["mode"],
                        target_id=target_id,
                        execution_status=result["execution_status"],
                        candidate_ids=result["candidate_ids"],
                        error_message=None,
                        nights_acquired=result["nights_acquired"],
                        provenance={
                            "coverage_inventory_id": target["coverage_inventory_id"],
                            "coverage": target["coverage_provenance"],
                            "ranking_policy_digest": manifest["ranking_policy_digest"],
                            "pipeline_git": git_provenance,
                            "execution_contract": execution_contract,
                            "validity_state": "valid",
                        },
                    )
                    emit_event(
                        event_log,
                        event="target_execution",
                        status=result["execution_status"],
                        command="Run-New-Search",
                        search_id=search_id,
                        run_id=run_id,
                        target_id=target_id,
                        candidate_count=len(result["candidate_ids"]),
                        nights_acquired=result["nights_acquired"],
                    )
                except _RUN_TARGET_EXPECTED_EXCEPTIONS as exc:
                    print(f"[run-new-search] target {target_id} FAILED: {exc}", flush=True)
                    hunter_state.commit_target_result(
                        db_path,
                        run_id=run_id,
                        search_id=search_id,
                        mode=manifest["mode"],
                        target_id=target_id,
                        execution_status="failed",
                        candidate_ids=[],
                        error_message=str(exc),
                        nights_acquired=[],
                        provenance={
                            "pipeline_git": git_provenance,
                            "execution_contract": execution_contract,
                            "error_type": type(exc).__name__,
                            "validity_state": "invalid",
                        },
                    )
                    emit_event(
                        event_log,
                        event="target_execution",
                        status="failed",
                        command="Run-New-Search",
                        search_id=search_id,
                        run_id=run_id,
                        target_id=target_id,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                    continue

                print(
                    f"[run-new-search] target {target_id}: {result['execution_status']} "
                    f"({len(result['candidate_ids'])} candidate(s))",
                    flush=True,
                )

    target_states = hunter_state.get_run_targets(db_path, run_id)
    n_targets = len(manifest["targets"])
    n_failed = sum(
        1
        for target in manifest["targets"]
        if target_states.get(target["target_id"], {}).get("execution_status") == "failed"
    )
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
    emit_event(
        event_log,
        event="run_search",
        status=final_status,
        command="Run-New-Search",
        search_id=search_id,
        run_id=run_id,
        target_count=n_targets,
        failed_count=n_failed,
    )
    return {"run_id": run_id, "status": final_status, "n_targets": n_targets, "n_failed": n_failed}


def cmd_run_new_search(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    if args.search_id is not None:
        search_id = args.search_id
    else:
        # --latest picks the most recent pending manifest regardless of mode
        # (new or follow-up) -- execution is identical either way.
        search_id = hunter_state.get_latest_pending_manifest(db_path)["search_id"]

    result = run_search(
        db_path=db_path,
        ledger_db_path=Path(args.candidate_ledger_db),
        search_id=search_id,
        checkpoint_root=Path(args.checkpoint_root),
        size_deg=args.size_deg,
        workers=getattr(args, "workers", _DEFAULT_RUN_WORKERS),
        event_log=_event_path(args),
    )
    print(
        f"search_id={search_id}  run_id={result['run_id']}  status={result['status']}  "
        f"targets={result['n_targets']}  failed={result['n_failed']}"
    )
    return 0 if result["status"] == "completed" else 1


def cmd_export_cross_project_history(args: argparse.Namespace) -> int:
    """Publish THIS repository's own prior-search history export (deliverable A).

    The publishing half of the cross-project contract: the two sibling Hunters
    read this file to answer "has NEOHunter already searched this target?"
    without importing anything from this repository at runtime.

    Writes exactly one file, always inside this repository (WS-01). It never
    reads or writes a sibling.
    """
    summary = hunter_cross_project.write_own_history_export(
        Path(args.out),
        target_queue_path=Path(args.target_queue),
        generated_at_utc=args.generated_at,
    )

    print(f"Published cross-project history export -> {summary['output_path']}")
    print(f"  schema_version   : {summary['schema_version']}")
    print(f"  entries          : {summary['entry_count']}")
    print(f"  unique targets   : {summary['unique_target_count']}")
    print(f"  source sha256    : {summary['source_sha256']}")
    print(f"  {summary['disclaimer']}")

    emit_event(
        _event_path(args),
        event="export_cross_project_history",
        status="completed",
        command="Export-Cross-Project-History",
        output_path=summary["output_path"],
        entry_count=summary["entry_count"],
        unique_target_count=summary["unique_target_count"],
    )
    return 0


def cmd_show_follow_ups(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    status = None if args.status == "all" else args.status
    entries = hunter_state.list_follow_ups(db_path, status=status, limit=args.limit)
    ledger_records: dict[str, dict[str, Any]] = {}
    ledger_db_path = Path(args.candidate_ledger_db)
    if ledger_db_path.is_file():
        ledger_records = {
            record["candidate_id"]: record
            for record in candidate_ledger.list_records(ledger_db_path)
        }

    if not entries:
        print(f"No follow-ups with status={status!r}." if status else "No follow-ups.")
        emit_event(
            _event_path(args),
            event="show_follow_ups",
            status="completed",
            command="Show-Follow-Ups",
            requested_status=status,
            result_count=0,
        )
        return 0

    header = (
        f"{'target':<22}  {'priority':>8}  {'status':<10}  {'prior':>5}  "
        f"{'MB':>7}  {'CPU-s':>7}  reason"
    )
    print(header)
    print("-" * len(header))
    for entry in entries:
        review_status = ""
        if entry["candidate_id"] is not None:
            record = ledger_records.get(entry["candidate_id"])
            if record is not None:
                review_status = record["review_status"]
        history = hunter_state.list_target_history(db_path, entry["target_id"])
        print(
            f"{entry['target_id']:<22}  {entry['priority']:>8.3f}  "
            f"{entry['status']:<10}  {len(history):>5}  "
            f"{entry['estimated_storage_mb']:>7.1f}  "
            f"{entry['estimated_compute_seconds']:>7.1f}  {entry['reason']}"
        )
        print(
            f"      flagged_at={entry['flagged_at']}  review={review_status or 'n/a'}  "
            f"originating_run={entry['originating_run_id'] or 'external/unknown'}  "
            f"evidence={entry['evidence_ref']}"
        )
        print(
            f"      required_data={entry['required_data']}  "
            f"recommended_action={entry['recommended_action']}"
        )
        print(
            "      prior_search_provenance="
            + _json_cell(
                [
                    {
                        "search_id": item["search_id"],
                        "run_id": item["run_id"],
                        "status": item["status"],
                        "source": item["source"],
                        "occurred_at": item["occurred_at"],
                    }
                    for item in history
                ]
            )
        )
    emit_event(
        _event_path(args),
        event="show_follow_ups",
        status="completed",
        command="Show-Follow-Ups",
        requested_status=status,
        result_count=len(entries),
    )
    return 0


def _resolve_inspect_manifest(db_path: Path, search_id: str | None) -> dict[str, Any]:
    """Resolve which frozen manifest ``inspect-target`` should read.

    An explicit ``--search-id`` wins. Otherwise the most recent manifest is used,
    preferring a pending one (the search the operator is most likely looking at)
    and falling back to the newest manifest of any status.
    """
    if search_id:
        return hunter_state.get_search_manifest(db_path, search_id)
    try:
        return hunter_state.get_latest_pending_manifest(db_path)
    except ValueError:
        # No pending manifest: fall back to the newest manifest of any status so
        # a completed search remains inspectable.
        hunter_state.init_db(db_path)
        with closing(hunter_state.connect(db_path)) as conn:
            row = conn.execute(
                "SELECT search_id FROM search_manifests ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            raise ValueError(
                "no search manifest exists yet; create one with create-new-search"
            ) from None
        return hunter_state.get_search_manifest(db_path, row["search_id"])


def _select_manifest_target(
    manifest: dict[str, Any], reference: str
) -> dict[str, Any]:
    """Find one frozen target by rank number or by identifier.

    Matching by identifier accepts the canonical ``target_id`` as well as the
    survey-native and canonical identifiers carried alongside it, so an operator
    can paste whichever identity the detail view showed them.
    """
    targets = manifest.get("targets", [])
    if not targets:
        raise ValueError(f"search {manifest['search_id']!r} has no frozen targets")

    if reference.isdigit():
        rank = int(reference)
        for target in targets:
            if int(target.get("rank", -1)) == rank:
                return target
        raise ValueError(
            f"rank {rank} is out of range; search {manifest['search_id']!r} "
            f"froze {len(targets)} target(s)"
        )

    folded = reference.casefold()
    for target in targets:
        candidates = {
            str(target.get("target_id", "")).casefold(),
            str(target.get("canonical_id", "")).casefold(),
            str(target.get("primary_survey_id", "")).casefold(),
        }
        if folded in candidates:
            return target
    raise ValueError(
        f"no target matching {reference!r} in search {manifest['search_id']!r}"
    )


def cmd_inspect_target(args: argparse.Namespace) -> int:
    """Render the full detail view for one frozen target (UX-TABLE-02).

    This is a read-only projection of already-persisted durable state. It runs no
    discovery, performs no acquisition, and mutates nothing.
    """
    db_path = Path(args.db)
    manifest = _resolve_inspect_manifest(db_path, args.search_id)
    target = _select_manifest_target(manifest, str(args.target))
    target_id = str(target.get("target_id", ""))

    # Prior-search evidence comes from the append-only history table rather than
    # the manifest, so the view reflects everything known about the target.
    history = hunter_state.list_target_history(db_path, target_id)

    detail = {
        "target_id": target_id,
        "identity": {
            "target_id": target_id,
            "canonical_id": target.get("canonical_id"),
            "primary_survey_id": target.get("primary_survey_id"),
            "target_kind": target.get("target_kind"),
            "survey": target.get("survey"),
            "search_mode": target.get("search_mode"),
        },
        "metrics": target.get("scientific_metrics") or {},
        "score_components": target.get("score_components") or {},
        "selection_reason": target.get("selection_reason"),
        "provenance": {
            "search_id": manifest.get("search_id"),
            "manifest_status": manifest.get("status"),
            "created_at": manifest.get("created_at"),
            "coverage": target.get("coverage_provenance") or {},
            "prior_search": target.get("prior_search_provenance") or {},
        },
        "prior_search_evidence": [
            f"{item.get('occurred_at')}  {item.get('outcome')}  "
            f"nights={len(item.get('nights') or [])}"
            for item in history
        ],
        "resources": {
            "estimated_storage_mb": target.get("estimated_storage_mb"),
            "rank": target.get("rank"),
        },
        "limitations": target.get("limitations") or [],
    }

    if args.json:
        print(json.dumps(detail, indent=2, sort_keys=True, default=str))
    else:
        capabilities = ux_theme.detect(sys.stdout, no_color=args.no_color)
        for line in ux_table.render_detail(detail, capabilities):
            print(line)

    emit_event(
        _event_path(args),
        event="command",
        status="ok",
        command="inspect-target",
        search_id=manifest.get("search_id"),
        target_id=target_id,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create_cmd = sub.add_parser(
        "create-new-search", help="rank/select targets and create a durable pending search"
    )
    create_cmd.add_argument("--targets", type=int, required=True, help="number of targets (N)")
    create_cmd.add_argument("--mode", choices=["new", "follow-up"], required=True)
    create_cmd.add_argument("--neo-class", choices=_NEO_CLASSES, default="all")
    create_cmd.add_argument("--jd", default="now")
    create_cmd.add_argument(
        "--max-pool",
        type=int,
        default=None,
        help="optional explicit safety limit; normal discovery explores adaptively",
    )
    create_cmd.add_argument("--target-queue", default=str(_DEFAULT_TARGET_QUEUE))
    create_cmd.add_argument(
        "--ranking-policy", default=str(field_selector._DEFAULT_RANKING_POLICY_PATH)
    )
    create_cmd.add_argument(
        "--follow-up-policy", default=str(_DEFAULT_FOLLOW_UP_POLICY)
    )
    create_cmd.add_argument("--db", default=str(_DEFAULT_DB))
    create_cmd.add_argument("--event-log", default=str(_EVENT_LOG))

    run_cmd = sub.add_parser(
        "run-new-search", help="execute the exact targets from a durable pending search"
    )
    run_group = run_cmd.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--search-id")
    run_group.add_argument("--latest", action="store_true")
    run_cmd.add_argument("--db", default=str(_DEFAULT_DB))
    run_cmd.add_argument("--candidate-ledger-db", default=str(_DEFAULT_LEDGER_DB))
    run_cmd.add_argument("--checkpoint-root", default=str(_CHECKPOINT_ROOT))
    run_cmd.add_argument("--event-log", default=str(_EVENT_LOG))
    run_cmd.add_argument("--size-deg", type=float, default=_DEFAULT_SIZE_DEG)
    run_cmd.add_argument(
        "--workers",
        type=int,
        default=_DEFAULT_RUN_WORKERS,
        help=(
            "concurrent target workers "
            f"(1-{_MAX_RUN_WORKERS}; default {_DEFAULT_RUN_WORKERS})"
        ),
    )

    show_cmd = sub.add_parser(
        "show-follow-ups", help="show durable follow-up registry entries"
    )
    show_cmd.add_argument(
        "--status", default="open", choices=["open", "actioned", "dismissed", "expired", "all"]
    )
    show_cmd.add_argument("--limit", type=int, default=None)
    show_cmd.add_argument("--db", default=str(_DEFAULT_DB))
    show_cmd.add_argument("--candidate-ledger-db", default=str(_DEFAULT_LEDGER_DB))
    show_cmd.add_argument("--event-log", default=str(_EVENT_LOG))

    # Deliverable A: publish this repo's own history so the siblings can consume
    # it. Defaults are the shared contract path used identically by all three
    # Hunters, so the normal invocation takes no arguments at all.
    export_cmd = sub.add_parser(
        "export-cross-project-history",
        help="publish this repo's own prior-search history for sibling Hunters",
    )
    export_cmd.add_argument(
        "--out",
        default=str(_DEFAULT_CROSS_PROJECT_EXPORT),
        help="output path (must be inside this repository)",
    )
    export_cmd.add_argument(
        "--target-queue",
        default=str(_DEFAULT_TARGET_QUEUE),
        help="committed target priority queue to derive history from",
    )
    export_cmd.add_argument(
        "--generated-at",
        default=None,
        help="explicit ISO-8601 UTC generation timestamp (for reproducible builds)",
    )
    export_cmd.add_argument("--event-log", default=str(_EVENT_LOG))

    inspect_cmd = sub.add_parser(
        "inspect-target",
        help="show full scientific detail and provenance for one frozen target",
    )
    inspect_cmd.add_argument(
        "--target",
        required=True,
        help="result rank number from the last table, or a target identifier",
    )
    inspect_cmd.add_argument(
        "--search-id",
        default=None,
        help="which frozen search to read; defaults to the most recent",
    )
    inspect_cmd.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON detail"
    )
    inspect_cmd.add_argument("--no-color", action="store_true")
    inspect_cmd.add_argument("--db", default=str(_DEFAULT_DB))
    inspect_cmd.add_argument("--event-log", default=str(_EVENT_LOG))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create-new-search":
            return cmd_create_new_search(args)
        if args.command == "run-new-search":
            return cmd_run_new_search(args)
        if args.command == "show-follow-ups":
            return cmd_show_follow_ups(args)
        if args.command == "inspect-target":
            return cmd_inspect_target(args)
        if args.command == "export-cross-project-history":
            return cmd_export_cross_project_history(args)
        raise AssertionError(f"unhandled command {args.command}")  # pragma: no cover
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        emit_event(
            _event_path(args),
            event="command",
            status="failed",
            command=args.command,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
