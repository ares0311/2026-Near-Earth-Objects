#!/usr/bin/env python3
"""Skills/run_pipeline.py — End-to-end NEO pipeline runner.

Checkpoint/resume: after each major stage the pipeline writes
Logs/pipeline_runs/<param_key>/checkpoint.json.  Re-running the same
command after a network drop, machine sleep, or process kill automatically
resumes from the last completed stage — no data is re-fetched or
re-processed.

Console output conforms to docs/CONSOLE_OUTPUT_SPEC.md.

Usage:
    uv run python Skills/run_pipeline.py \\
        --ra 180.0 --dec 10.0 --radius 1.0 \\
        --start-jd 2460000.0 --end-jd 2460010.0 \\
        [--surveys WISE] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alert import monitor_neocp, process_alert, ready_for_submission, summarise
from classify import classify
from detect import detect
from fetch import fetch
from link import link
from orbit import fit_orbit
from preprocess import preprocess
from schemas import Observation, Tracklet
from score import score

# Cache directory used by fetch.py
_CACHE_DIR = Path(".neo_cache")

# Root directory for pipeline run audit logs and checkpoints
_LOG_ROOT = Path("Logs") / "pipeline_runs"

# Network errors that warrant a retry
_INFRA_ERRORS = (ConnectionError, TimeoutError, OSError)

# Guardrail for all-pairs linking. Override with --max-link-seed-pairs for
# intentionally larger diagnostics after a tiling/scale plan is documented.
_DEFAULT_MAX_LINK_SEED_PAIRS = 1_000_000


class LinkSeedBudgetExceeded(RuntimeError):
    """Expected fail-closed stop when broad-field linking exceeds budget."""


# ── Console output helpers ────────────────────────────────────────────────────

_LINE = "═" * 65
_DASH = "─" * 65


def _print_run_header(
    run_id: str,
    ra: float,
    dec: float,
    radius: float,
    start_jd: float,
    end_jd: float,
    surveys: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Print the CONSOLE_OUTPUT_SPEC.md run header block."""
    mode = (
        "DRY RUN  (no external submissions will be made)"
        if dry_run
        else "LIVE RUN  ⚠  alerts enabled"
    )
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    n_days = round(end_jd - start_jd, 2)
    surveys_str = " ".join(surveys)
    print(_LINE, flush=True)
    print(f"  NEO Detection Pipeline — {mode}", flush=True)
    print(f"  Run ID  : {run_id}", flush=True)
    print(f"  Field   : RA={ra}°  Dec={dec}°  r={radius}°", flush=True)
    print(
        f"  Window  : JD {start_jd} – {end_jd}  ({n_days} days)",
        flush=True,
    )
    print(f"  Surveys : {surveys_str}", flush=True)
    print(f"  Started : {timestamp}", flush=True)
    print(_LINE, flush=True)


def _print_run_footer(n_processed: int, n_ready: int, elapsed_s: float) -> None:
    """Print the CONSOLE_OUTPUT_SPEC.md run footer block."""
    print(_DASH, flush=True)
    print("  Pipeline complete.", flush=True)
    print(f"  Candidates processed : {n_processed}", flush=True)
    print(f"  Submission-ready     : {n_ready}", flush=True)
    print(f"  Elapsed              : {_format_duration(elapsed_s)}", flush=True)
    print(_DASH, flush=True)


def _print_escalation_notice(
    object_id: str,
    moid_au: float | None,
    rb: float | None,
    pathway: str,
    priority: float,
    dry_run: bool,
) -> None:
    """Print the candidate escalation notice per CONSOLE_OUTPUT_SPEC.md."""
    moid_str = f"{moid_au:.4f}" if moid_au is not None else "N/A"
    rb_str = f"{rb:.3f}" if rb is not None else "N/A"
    print("┌─────────────────────────────────────────────────────────────────┐", flush=True)
    print(f"│  ⚠  SUBMISSION CANDIDATE: {object_id}", flush=True)
    print(f"│     MOID    : {moid_str} AU", flush=True)
    print(f"│     RB score: {rb_str}", flush=True)
    print(f"│     Pathway : {pathway}", flush=True)
    print(f"│     Priority: {priority:.4f}", flush=True)
    print("│     TODO: MPC archival-submission authority unresolved — see", flush=True)
    print("│           docs/MPC_SUBMISSION_POLICY.md", flush=True)
    print("│           §Archival WISE Submission Authority", flush=True)
    print("└─────────────────────────────────────────────────────────────────┘", flush=True)
    if dry_run:
        print("[alert] DRY RUN — no external submission performed.", flush=True)


def _estimate_link_seed_pairs(candidates: tuple) -> int:
    """Estimate linker seed pairs using the same 30-day night-pair window."""
    counts_by_night: dict[int, int] = {}
    for cand in candidates:
        for obs in getattr(cand, "observations", ()):
            night = int(obs.jd)
            counts_by_night[night] = counts_by_night.get(night, 0) + 1

    total = 0
    nights = sorted(counts_by_night)
    for idx, night_a in enumerate(nights[:-1]):
        for night_b in nights[idx + 1 :]:
            if night_b - night_a > 30:
                break
            total += counts_by_night[night_a] * counts_by_night[night_b]
    return total


def _build_link_scale_plan(
    candidates: tuple,
    max_link_seed_pairs: int,
    *,
    sky_cell_deg: float = 0.2,
    top_n: int = 12,
) -> dict:
    """Build an operator scale plan before fail-closed broad-field linking.

    The plan is diagnostic only. It does not authorize an all-pairs override and
    does not partition candidates for science processing; it shows which nights
    and approximate sky cells dominate seed-pair work so the next run can use a
    smaller field/window or documented pilot cap.
    """
    counts_by_night: dict[int, int] = {}
    cell_counts: dict[tuple[int, int], int] = {}
    for cand in candidates:
        for obs in getattr(cand, "observations", ()):
            night = int(obs.jd)
            counts_by_night[night] = counts_by_night.get(night, 0) + 1
            ra = float(getattr(obs, "ra_deg", 0.0))
            dec = float(getattr(obs, "dec_deg", 0.0))
            cell = (int(ra // sky_cell_deg), int((dec + 90.0) // sky_cell_deg))
            cell_counts[cell] = cell_counts.get(cell, 0) + 1

    night_pairs: list[dict[str, int]] = []
    nights = sorted(counts_by_night)
    for idx, night_a in enumerate(nights[:-1]):
        for night_b in nights[idx + 1 :]:
            if night_b - night_a > 30:
                break
            seed_pairs = counts_by_night[night_a] * counts_by_night[night_b]
            night_pairs.append({
                "night_a": night_a,
                "night_b": night_b,
                "seed_pairs": seed_pairs,
            })

    sky_cells = []
    for (ra_idx, dec_idx), n_obs in sorted(
        cell_counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:top_n]:
        sky_cells.append({
            "center_ra_deg": round((ra_idx + 0.5) * sky_cell_deg, 6),
            "center_dec_deg": round((dec_idx + 0.5) * sky_cell_deg - 90.0, 6),
            "cell_size_deg": sky_cell_deg,
            "n_observations": n_obs,
        })

    total_seed_pairs = sum(pair["seed_pairs"] for pair in night_pairs)
    return {
        "status": "blocked_seed_pair_budget",
        "max_link_seed_pairs": max_link_seed_pairs,
        "estimated_seed_pairs": total_seed_pairs,
        "n_candidates": len(candidates),
        "n_observations": sum(counts_by_night.values()),
        "n_nights": len(nights),
        "nights": [
            {"night": night, "n_observations": counts_by_night[night]}
            for night in nights
        ],
        "top_night_pairs": sorted(
            night_pairs,
            key=lambda pair: pair["seed_pairs"],
            reverse=True,
        )[:top_n],
        "top_sky_cells": sky_cells,
        "recommended_next_actions": [
            "Run a smaller field or shorter window selected from top_night_pairs.",
            "Use --max-candidates only for bounded diagnostics, not promotion.",
            "Override --max-link-seed-pairs only after documenting a scale plan.",
        ],
        "safety": {
            "no_external_submission": True,
            "no_impact_probability_claim": True,
        },
    }


def _write_link_scale_plan(
    path: Path,
    candidates: tuple,
    max_link_seed_pairs: int,
) -> None:
    """Write a JSON scale plan for a fail-closed link budget stop."""
    path.parent.mkdir(parents=True, exist_ok=True)
    plan = _build_link_scale_plan(candidates, max_link_seed_pairs)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")


# ── Checkpoint helpers ────────────────────────────────────────────────────────

def _param_key(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    surveys: tuple[str, ...],
) -> str:
    """Return a stable 12-char key derived from search parameters.

    Same parameters always produce the same key so that re-running the same
    command finds the existing checkpoint directory.
    """
    raw = (
        f"{ra_deg:.3f}|{dec_deg:.3f}|{radius_deg:.3f}"
        f"|{start_jd:.2f}|{end_jd:.2f}|{'|'.join(sorted(surveys))}"
    )
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _format_duration(seconds: float) -> str:
    seconds_int = max(0, int(seconds))
    minutes, secs = divmod(seconds_int, 60)
    return f"{minutes}m{secs:02d}s"


def _tracklet_to_dict(t: Tracklet) -> dict:
    """Serialize a Tracklet to a plain dict for JSON checkpoint storage."""
    return {
        "object_id": t.object_id,
        "arc_days": t.arc_days,
        "motion_rate_arcsec_per_hour": t.motion_rate_arcsec_per_hour,
        "motion_pa_degrees": t.motion_pa_degrees,
        "observations": [o.model_dump() for o in t.observations],
    }


def _tracklet_from_dict(d: dict) -> Tracklet:
    """Reconstruct a Tracklet from a checkpoint dict."""
    obs = tuple(Observation(**o) for o in d["observations"])
    return Tracklet(
        object_id=d["object_id"],
        observations=obs,
        arc_days=d["arc_days"],
        motion_rate_arcsec_per_hour=d["motion_rate_arcsec_per_hour"],
        motion_pa_degrees=d["motion_pa_degrees"],
    )


def _load_checkpoint(run_dir: Path) -> dict:
    """Return the checkpoint dict from run_dir, or {} if none exists."""
    cp_file = run_dir / "checkpoint.json"
    return json.loads(cp_file.read_text()) if cp_file.exists() else {}


def _save_checkpoint(run_dir: Path, data: dict) -> None:
    """Write data to run_dir/checkpoint.json, creating directories as needed."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoint.json").write_text(json.dumps(data, indent=2))


# ── Fetch with retry ──────────────────────────────────────────────────────────

def _fetch_with_retry(
    max_attempts: int = 5,
    _sleep_fn=time.sleep,  # injectable for tests
    **kwargs,
):
    """Call fetch() retrying on network errors with exponential backoff.

    Waits 2, 4, 8, 16, 32 seconds between attempts.  Raises the last
    exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fetch(**kwargs)
        except _INFRA_ERRORS as exc:
            # json.JSONDecodeError inherits from ValueError and (via
            # requests.exceptions.JSONDecodeError) from OSError, so it would
            # otherwise be caught here.  An empty API response body is "no data
            # for this region" — not a transient network failure — so we must
            # not retry it.  Re-raise immediately so the pipeline sees 0 alerts
            # rather than sleeping through 5 useless retries.
            if isinstance(exc, (json.JSONDecodeError, ValueError)):
                raise
            last_exc = exc
            if attempt == max_attempts - 1:
                break
            wait = 2 ** (attempt + 1)
            print(
                f"[fetch] Network error: {exc}  "
                f"(attempt {attempt + 1}/{max_attempts}; retry in {wait}s...)",
                flush=True,
            )
            _sleep_fn(wait)
    raise last_exc  # type: ignore[misc]


# ── Cache / audit-log helpers ─────────────────────────────────────────────────

def delete_cache_files(cache_dir: Path = _CACHE_DIR) -> list[str]:
    """Delete all .json files in cache_dir and return the list of deleted names."""
    deleted: list[str] = []
    if not cache_dir.is_dir():
        return deleted
    for f in sorted(cache_dir.glob("*.json")):
        try:
            f.unlink()
            deleted.append(f.name)
        except OSError:
            pass
    return deleted


def write_run_summary(log_dir: Path, summary: dict) -> None:
    """Create log_dir if needed and write summary as run_summary.json."""
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "run_summary.json").write_text(json.dumps(summary, indent=2))


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(
    ra_deg: float,
    dec_deg: float,
    radius_deg: float,
    start_jd: float,
    end_jd: float,
    surveys: tuple[str, ...] = ("ZTF",),
    max_candidates: int | None = None,
    dry_run: bool = True,
    atlas_token: str | None = None,
    force_refresh: bool = False,
    neocp_timeout_hours: float = 0.0,
    neocp_poll_interval_hours: float = 1.0,
    run_dir: Path | None = None,
    resume: bool = True,
    run_id: str = "unknown",
    review_packet_out: Path | None = None,
    max_link_seed_pairs: int | None = _DEFAULT_MAX_LINK_SEED_PAIRS,
    link_scale_plan_out: Path | None = None,
) -> list[dict]:
    _t_pipeline_start = time.monotonic()

    # Print the spec-compliant run header
    _print_run_header(
        run_id=run_id,
        ra=ra_deg,
        dec=dec_deg,
        radius=radius_deg,
        start_jd=start_jd,
        end_jd=end_jd,
        surveys=surveys,
        dry_run=dry_run,
    )

    # Warn the operator that live alert mode was requested while preserving the
    # independent MPC submission fail-closed gate in alert.py.
    if not dry_run:
        print(
            "[alert] LIVE ALERT MODE REQUESTED — MPC submission remains fail-closed "
            "unless NEO_MPC_SUBMISSION_APPROVED=1 and a real observatory code are set.",
            flush=True,
        )
        print("[alert]    Guardrails: no impact-probability claims; no direct PDCO contact.",
              flush=True)
        print("[alert]    Quality gates still apply before any report is drafted.",
              flush=True)

    # Load any existing checkpoint for this parameter set
    cp: dict = {}
    if run_dir is not None and resume:
        cp = _load_checkpoint(run_dir)
        if cp:
            print(
                f"[resume] Checkpoint found (last stage: {cp.get('last_stage', '?')}); "
                "resuming from last completed stage.",
                flush=True,
            )

    # ── Stage 1: Fetch → Preprocess → Detect → Link ──────────────────────────
    if "tracklets" in cp:
        # These stages already finished; reload tracklets from the checkpoint.
        n_trk = len(cp["tracklets"])
        print(
            f"[resume] Reloading {n_trk} tracklets from checkpoint "
            "(skipping fetch / preprocess / detect / link).",
            flush=True,
        )
        tracklets: list[Tracklet] = [_tracklet_from_dict(d) for d in cp["tracklets"]]
    else:
        # Fetch each survey separately so we can emit per-survey progress with ETA.
        # Measurable quantity: surveys completed / total surveys.
        _fetch_start = time.monotonic()
        _n_surveys = len(surveys)
        print(
            f"[fetch] Querying {_n_surveys} survey(s): {surveys}  "
            f"RA={ra_deg}, Dec={dec_deg}, r={radius_deg}°  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        all_alerts: list = []
        for _i_srv, _srv in enumerate(surveys):
            _srv_done = _i_srv + 1
            print(
                f"[fetch] ({_srv_done}/{_n_surveys}) Starting {_srv}  "
                f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
                flush=True,
            )
            _partial = _fetch_with_retry(
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                radius_deg=radius_deg,
                start_jd=start_jd,
                end_jd=end_jd,
                surveys=(_srv,),  # type: ignore[arg-type]
                atlas_token=atlas_token,
                force_refresh=force_refresh,
            )
            all_alerts.extend(_partial.alerts)
            _srv_elapsed = time.monotonic() - _fetch_start
            _per_srv = _srv_elapsed / _srv_done
            _srv_eta = _per_srv * (_n_surveys - _srv_done)
            print(
                f"[fetch] ({_srv_done}/{_n_surveys}) {_srv}: "
                f"{len(_partial.alerts)} alerts  "
                f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}  "
                f"ETA {_format_duration(_srv_eta)}",
                flush=True,
            )
        print(
            f"[fetch] Complete: {len(all_alerts)} alerts total  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )

        print(
            f"[preprocess] Validating and normalising {len(all_alerts)} sources  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        prep_result = preprocess(tuple(all_alerts), apply_astrometry=False)
        n_out = prep_result.provenance.n_sources_out
        n_in = prep_result.provenance.n_sources_in
        print(
            f"[preprocess] {n_out}/{n_in} sources passed  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )

        print(
            f"[detect] Identifying moving object candidates  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        det_result = detect(prep_result.sources)
        n_cands = det_result.provenance.n_candidates
        n_known = det_result.provenance.n_known_matches
        print(
            f"[detect] {n_cands} candidates, {n_known} known matches  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        link_candidates = det_result.candidates
        if max_candidates is not None and len(link_candidates) > max_candidates:
            print(
                f"[detect] Pilot cap active: linking first {max_candidates}/"
                f"{len(det_result.candidates)} candidates  "
                f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
                flush=True,
            )
            link_candidates = link_candidates[:max_candidates]

        estimated_seed_pairs = _estimate_link_seed_pairs(link_candidates)
        if max_link_seed_pairs is not None and estimated_seed_pairs > max_link_seed_pairs:
            if link_scale_plan_out is not None:
                _write_link_scale_plan(
                    link_scale_plan_out,
                    link_candidates,
                    max_link_seed_pairs,
                )
                print(
                    f"[link] Scale plan written to {link_scale_plan_out}",
                    flush=True,
                )
            message = (
                "Link seed-pair budget exceeded: "
                f"{estimated_seed_pairs} estimated seed pairs > {max_link_seed_pairs}. "
                "Use --max-candidates, a smaller field/window, or an explicit "
                "--max-link-seed-pairs override after documenting the scale plan."
            )
            print(f"[link] {message}", flush=True)
            raise LinkSeedBudgetExceeded(message)

        print(
            f"[link] Linking {len(link_candidates)} candidates across nights  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        link_start = time.monotonic()

        def _link_progress(done: int, total: int, n_tracklets: int) -> None:
            elapsed = time.monotonic() - link_start
            eta = 0.0 if done <= 0 else (elapsed / done) * max(0, total - done)
            print(
                f"[link] progress {done}/{total} seed pairs; "
                f"tracklets={n_tracklets}; elapsed {_format_duration(elapsed)} "
                f"ETA {_format_duration(eta)}",
                flush=True,
            )

        link_result = link(link_candidates, progress_callback=_link_progress)
        n_trk = link_result.provenance.n_tracklets
        print(
            f"[link] {n_trk} tracklets formed  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        link_diag = link_result.provenance
        if n_trk == 0 and link_diag.n_seed_pairs_total > 0:
            print(
                "[link] diagnostics "
                f"nights={link_diag.n_nights}; "
                f"observations={link_diag.n_observations}; "
                f"seed_pairs={link_diag.n_seed_pairs_total}; "
                f"rate_ok={link_diag.n_seed_pairs_rate_window}; "
                f"satellite_rejected={link_diag.n_seed_pairs_satellite_rejected}; "
                f"below_min_obs={link_diag.n_arcs_below_min_observations}; "
                f"below_min_nights={link_diag.n_arcs_below_min_nights}; "
                f"chi2_rejected={link_diag.n_arcs_chi2_rejected}; "
                f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
                flush=True,
            )

        tracklets = list(link_result.tracklets)

        # Checkpoint: expensive network + detection stages are done.
        # A kill/sleep after this point will resume the per-tracklet loop.
        if run_dir is not None:
            _save_checkpoint(run_dir, {
                "last_stage": "link",
                "tracklets": [_tracklet_to_dict(t) for t in tracklets],
                "link_provenance": link_result.provenance.model_dump(),
                "partial_results": [],
            })

    # ── Stage 2: Per-tracklet classify → orbit → score → alert ───────────────
    completed_ids = {r["object_id"] for r in cp.get("partial_results", [])}
    results: list[dict] = list(cp.get("partial_results", []))
    review_packets: list[dict] = list(cp.get("review_packets", []))

    # Track per-tracklet timing for ETA.  Only count tracklets processed this
    # session (not ones reloaded from checkpoint) so ETA reflects real work.
    _n_tracklets = len(tracklets)
    _trk_session_start = time.monotonic()
    _trk_done_this_session = 0

    for _trk_idx, tracklet in enumerate(tracklets):
        if tracklet.object_id in completed_ids:
            # Already scored in a previous (interrupted) run; skip it.
            print(
                f"[resume] Skipping already-processed {tracklet.object_id}  "
                f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
                flush=True,
            )
            continue

        _trk_done_this_session += 1
        _trk_elapsed_session = time.monotonic() - _trk_session_start
        _trk_per_item = _trk_elapsed_session / _trk_done_this_session
        _trk_remaining = _n_tracklets - _trk_idx - 1
        _trk_eta = _trk_per_item * _trk_remaining

        print(
            f"[classify] ({_trk_idx + 1}/{_n_tracklets}) {tracklet.object_id}  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}  "
            f"ETA {_format_duration(_trk_eta)}",
            flush=True,
        )
        features, posterior = classify(tracklet)

        print(
            f"[orbit] ({_trk_idx + 1}/{_n_tracklets}) {tracklet.object_id}  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        orbital = fit_orbit(tracklet)

        print(
            f"[score] ({_trk_idx + 1}/{_n_tracklets}) {tracklet.object_id}  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        scored = score(tracklet, features, posterior, orbital)

        print(
            f"[alert] ({_trk_idx + 1}/{_n_tracklets}) {tracklet.object_id}  "
            f"elapsed {_format_duration(time.monotonic() - _t_pipeline_start)}",
            flush=True,
        )
        alert_result = process_alert(scored, dry_run=dry_run)

        # Check submission readiness and print escalation notice if gates pass
        ready, _ = ready_for_submission(scored)
        if ready:
            _print_escalation_notice(
                object_id=tracklet.object_id,
                moid_au=scored.hazard.moid_au,
                rb=scored.features.real_bogus_score,
                pathway=scored.hazard.alert_pathway,
                priority=scored.metadata.discovery_priority,
                dry_run=dry_run,
            )

        if neocp_timeout_hours > 0:
            print(
                f"[neocp] Monitoring NEOCP for {tracklet.object_id} "
                f"(timeout={neocp_timeout_hours}h)",
                flush=True,
            )
            neocp_result = monitor_neocp(
                tracklet.object_id,
                max_wait_hr=neocp_timeout_hours,
                poll_interval_hr=neocp_poll_interval_hours,
            )
            alert_result["neocp_monitor"] = neocp_result
            print(
                f"[neocp] status={neocp_result['status']}, "
                f"confirmed={neocp_result.get('confirmed', False)}",
                flush=True,
            )

        print(summarise(scored), flush=True)
        results.append({
            "object_id": tracklet.object_id,
            "neo_probability": scored.posterior.neo_candidate,
            "hazard_flag": scored.hazard.hazard_flag,
            "alert_pathway": scored.hazard.alert_pathway,
            "moid_au": scored.hazard.moid_au,
            "discovery_priority": scored.metadata.discovery_priority,
            "alert_actions": alert_result["actions"],
            "_submission_ready": ready,
        })
        if review_packet_out is not None:
            review_packets.append(scored.model_dump(mode="json"))

        # Checkpoint after each tracklet: a kill here loses at most one item.
        if run_dir is not None:
            checkpoint = {
                "last_stage": "partial",
                "tracklets": [_tracklet_to_dict(t) for t in tracklets],
                "partial_results": results,
            }
            if review_packet_out is not None:
                checkpoint["review_packets"] = review_packets
            _save_checkpoint(run_dir, checkpoint)

    n_ready = sum(1 for r in results if r.get("_submission_ready", False))
    _print_run_footer(
        n_processed=len(results),
        n_ready=n_ready,
        elapsed_s=time.monotonic() - _t_pipeline_start,
    )
    if review_packet_out is not None:
        review_packet_out.parent.mkdir(parents=True, exist_ok=True)
        review_packet_out.write_text(json.dumps(review_packets, indent=2))
        print(f"Review packets written to {review_packet_out}", flush=True)
    return results


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="NEO detection pipeline")
    parser.add_argument("--ra", type=float, required=True)
    parser.add_argument("--dec", type=float, required=True)
    parser.add_argument("--radius", type=float, default=1.0)
    parser.add_argument("--start-jd", type=float, required=True)
    parser.add_argument("--end-jd", type=float, required=True)
    # Discovery sources: WISE/NEOWISE, DECam/NOIRLab, TESS FFIs are the
    # unreviewed archives this pipeline targets. ZTF and ATLAS are training
    # data only (their own pipelines already submit discoveries to MPC).
    # See docs/MISSION.md §The Two-Part Data Strategy.
    parser.add_argument(
        "--surveys",
        nargs="+",
        default=["WISE"],
        choices=["ZTF", "ATLAS", "MPC", "PanSTARRS", "CSS", "WISE", "DECam", "TESS"],
        help=(
            "Discovery archive(s) to query. Default: WISE (primary discovery target). "
            "WISE/DECam/TESS target unreviewed archives. "
            "ZTF/ATLAS are training-data sources only — do NOT use for discovery."
        ),
    )
    # BooleanOptionalAction gives both --dry-run and --no-dry-run flags.
    # Default is True (safe: no external submissions). Real archive fetching
    # does not require --no-dry-run; reserve that flag for a future MPC-enabled
    # submission workflow after the observatory-code policy is resolved.
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Simulate alert actions without external submission (default: True). "
             "Real archive fetching works in dry-run mode.",
    )
    parser.add_argument(
        "--atlas-token", type=str, default=None,
        help="ATLAS authentication token (or set ATLAS_TOKEN env var)",
    )
    parser.add_argument(
        "--force-refresh", action="store_true", default=False,
        help="Bypass on-disk cache and re-fetch all survey data",
    )
    parser.add_argument(
        "--max-candidates", type=int, default=None,
        help="Optional bounded pilot cap for the number of detected candidates sent to linking",
    )
    parser.add_argument(
        "--max-link-seed-pairs",
        type=int,
        default=_DEFAULT_MAX_LINK_SEED_PAIRS,
        help=(
            "Fail closed before linking if estimated seed pairs exceed this budget "
            f"(default {_DEFAULT_MAX_LINK_SEED_PAIRS}; set 0 to disable)."
        ),
    )
    parser.add_argument(
        "--neocp-timeout-hours", type=float, default=0.0,
        help="Hours to poll NEOCP for independent confirmation (0 = skip)",
    )
    parser.add_argument(
        "--neocp-poll-interval", type=float, default=1.0,
        help="NEOCP poll interval in hours (default 1)",
    )
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument(
        "--review-packet-out",
        type=str,
        default=None,
        help=(
            "Optional JSON output path for full ScoredNEO packets suitable for "
            "Skills/adversarial_review.py."
        ),
    )
    parser.add_argument(
        "--link-scale-plan-out",
        type=str,
        default=None,
        help=(
            "Optional JSON output path for a fail-closed link scale plan when "
            "--max-link-seed-pairs is exceeded."
        ),
    )
    parser.add_argument(
        "--no-delete-cache", action="store_true", default=False,
        help="Skip deleting .neo_cache files after the run (default: delete)",
    )
    parser.add_argument(
        "--no-audit-log", action="store_true", default=False,
        help="Skip writing Logs/pipeline_runs audit log (default: write)",
    )
    parser.add_argument(
        "--no-resume", action="store_true", default=False,
        help="Ignore any existing checkpoint and start the run from scratch",
    )
    args = parser.parse_args(argv)

    t_start = time.monotonic()
    timestamp_utc = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_UTC")

    surveys = tuple(args.surveys)

    # Derive a stable directory from the search parameters so that re-running
    # the same command finds the same checkpoint and audit log.
    key = _param_key(args.ra, args.dec, args.radius, args.start_jd, args.end_jd, surveys)
    run_dir: Path | None = None if args.no_audit_log else (_LOG_ROOT / key)

    # Snapshot cache files present before the run (downloaded during fetch)
    cache_files_before: list[str] = []
    if _CACHE_DIR.is_dir():
        cache_files_before = sorted(f.name for f in _CACHE_DIR.glob("*.json"))

    results: list[dict] = []
    run_status = "complete"
    failure_reason: str | None = None
    exit_code = 0
    try:
        results = run_pipeline(
            ra_deg=args.ra,
            dec_deg=args.dec,
            radius_deg=args.radius,
            start_jd=args.start_jd,
            end_jd=args.end_jd,
            surveys=surveys,
            max_candidates=args.max_candidates,
            dry_run=args.dry_run,
            atlas_token=args.atlas_token,
            force_refresh=args.force_refresh,
            neocp_timeout_hours=args.neocp_timeout_hours,
            neocp_poll_interval_hours=args.neocp_poll_interval,
            run_dir=run_dir,
            resume=not args.no_resume,
            run_id=key,
            review_packet_out=Path(args.review_packet_out) if args.review_packet_out else None,
            max_link_seed_pairs=(
                None if args.max_link_seed_pairs <= 0 else args.max_link_seed_pairs
            ),
            link_scale_plan_out=(
                Path(args.link_scale_plan_out) if args.link_scale_plan_out else None
            ),
        )
    except LinkSeedBudgetExceeded as exc:
        run_status = "blocked_link_seed_budget"
        failure_reason = str(exc)
        exit_code = 2
        print(f"[link] BLOCKED: {failure_reason}", flush=True)

    elapsed = round(time.monotonic() - t_start, 2)

    # Delete raw cache files so the next run starts fresh
    deleted: list[str] = []
    if not args.no_delete_cache:
        deleted = delete_cache_files(_CACHE_DIR)
        if deleted:
            print(
                f"[cache] Deleted {len(deleted)} cache file(s) from {_CACHE_DIR}/",
                flush=True,
            )

    # Write audit log; the same directory holds the checkpoint so it persists
    # across runs until the operator explicitly removes it.
    if run_dir is not None:
        summary = {
            "run_id": key,
            "timestamp_utc": timestamp_utc,
            "ra_deg": args.ra,
            "dec_deg": args.dec,
            "radius_deg": args.radius,
            "start_jd": args.start_jd,
            "end_jd": args.end_jd,
            "surveys": list(surveys),
            "max_candidates": args.max_candidates,
            "dry_run": args.dry_run,
            "status": run_status,
            "failure_reason": failure_reason,
            "link_scale_plan_out": args.link_scale_plan_out,
            "n_results": len(results),
            "elapsed_seconds": elapsed,
            "cache_files_downloaded": cache_files_before,
            "cache_files_deleted": deleted,
        }
        write_run_summary(run_dir, summary)
        print(
            f"[audit] Run summary written to {run_dir}/run_summary.json",
            flush=True,
        )

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}", flush=True)
    else:
        print(json.dumps(results, indent=2))

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
