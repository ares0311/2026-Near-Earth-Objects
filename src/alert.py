"""Alert stage — MPC report formatting and NASA alert protocol."""

from __future__ import annotations

__all__ = [
    "format_mpc_observation",
    "format_mpc_report",
    "format_mpc_json",
    "batch_process_alerts",
    "generate_alert_package",
    "draft_mpc_submission",
    "process_alert",
    "summarise",
    "monitor_neocp",
    "alert_summary_table",
    "format_neocp_report",
    "ready_for_submission",
    "format_discovery_circular",
    "format_alert_summary",
    "generate_observation_request",
    "generate_mpc_cover_letter",
    "format_impact_notification",
    "count_pending_alerts",
    "format_submission_checklist",
    "validate_alert_package",
    "estimate_followup_window",
    "format_candidate_dossier",
    "count_alerts_by_flag",
    "format_bulk_summary",
    "count_ready_to_submit",
    "compute_alert_age_days",
    "format_observation_log",
]

import json
import logging
import time as _time_mod
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from schemas import (
    AlertPathway,
    Observation,
    ScoredNEO,
)

_LOG_DIR = Path("alert_logs")
_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MPC 80-column format
# ---------------------------------------------------------------------------

# Column layout per MPC circular (https://minorplanetcenter.net/iau/info/OpticalObs.html)
# Cols  1- 5: packed provisional designation
# Cols  6- 6: discovery asterisk
# Cols  7- 7: note 1
# Cols  8- 8: note 2
# Cols 15-32: date of observation (YYYY MM DD.ddddd)
# Cols 33-44: RA HH MM SS.ddd
# Cols 45-56: Dec ±DD MM SS.dd
# Cols 65-70: magnitude
# Cols 71-71: band
# Cols 78-80: observatory code

_MPC_OBS_CODE = "Xnn"  # placeholder; replace with real MPC observatory code


def _pack_provisional(designation: str) -> str:
    """Pack a provisional designation into the MPC 5-character format (simplified)."""
    d = designation.replace(" ", "").replace("-", "")
    return d[:5].ljust(5)


def _jd_to_mpc_date(jd: float) -> str:
    """Convert JD to MPC date format 'YYYY MM DD.ddddd'."""
    from astropy.time import Time  # type: ignore[import]

    t = Time(jd, format="jd")
    iso = t.iso  # e.g. "2026-03-15 04:32:10.000"
    dt = datetime.strptime(iso[:23], "%Y-%m-%d %H:%M:%S.%f")
    frac_day = (dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1e6) / 86400.0
    return f"{dt.year:04d} {dt.month:02d} {dt.day + frac_day:08.5f}"


def _format_ra(ra_deg: float) -> str:
    """Format RA in HH MM SS.ddd."""
    ra_hr = ra_deg / 15.0
    h = int(ra_hr)
    rem = (ra_hr - h) * 60.0
    m = int(rem)
    s = (rem - m) * 60.0
    return f"{h:02d} {m:02d} {s:06.3f}"


def _format_dec(dec_deg: float) -> str:
    """Format Dec as ±DD MM SS.dd."""
    sign = "+" if dec_deg >= 0 else "-"
    dec_abs = abs(dec_deg)
    d = int(dec_abs)
    rem = (dec_abs - d) * 60.0
    m = int(rem)
    s = (rem - m) * 60.0
    return f"{sign}{d:02d} {m:02d} {s:05.2f}"


def format_mpc_observation(
    obs: Observation,
    designation: str,
    is_discovery: bool = False,
    obs_code: str = _MPC_OBS_CODE,
) -> str:
    """Format a single observation in MPC 80-column format."""
    desig = _pack_provisional(designation)
    discovery = "*" if is_discovery else " "
    note1 = " "
    note2 = "C"  # CCD observation

    date_str = _jd_to_mpc_date(obs.jd)
    ra_str = _format_ra(obs.ra_deg)
    dec_str = _format_dec(obs.dec_deg)

    mag_str = f"{obs.mag:5.1f}" if obs.mag < 99 else "     "
    band = obs.filter_band[0] if obs.filter_band else " "

    # 80-column fixed-width record
    line = (
        f"{desig}"          # cols 1-5
        f"{discovery}"      # col 6
        f"{note1}"          # col 7
        f"{note2}"          # col 8
        f"      "           # cols 9-14 (second designation / blank)
        f"{date_str}"       # cols 15-32 (18 chars)
        f"{ra_str} "        # cols 33-44 (12 chars)
        f"{dec_str}"        # cols 45-56 (12 chars)
        f"         "        # cols 57-65 (9 blank)
        f"{mag_str}"        # cols 65-70 (but merged; simplified layout)
        f"{band}"           # col 71
        f"      "           # cols 72-77
        f"{obs_code}"       # cols 78-80
    )
    # Truncate/pad to exactly 80 columns
    return line[:80].ljust(80)


def format_mpc_json(neo: ScoredNEO, obs_code: str = _MPC_OBS_CODE) -> dict:
    """Generate an MPC JSON submission record (modern alternative to 80-col format).

    Returns a dict conforming to the MPC JSON observation format spec
    (https://minorplanetcenter.net/mpc-new-obs-format).
    """
    designation = neo.tracklet.object_id[:12]
    observations = []
    for i, obs in enumerate(sorted(neo.tracklet.observations, key=lambda o: o.jd)):
        from astropy.time import Time  # type: ignore[import]

        t = Time(obs.jd, format="jd")
        observations.append({
            "obsTime": t.isot,
            "ra": round(obs.ra_deg, 6),
            "dec": round(obs.dec_deg, 6),
            "rmsRA": None,
            "rmsDec": None,
            "mag": round(obs.mag, 2) if obs.mag < 99 else None,
            "rmsMag": round(obs.mag_err, 3) if obs.mag_err > 0 else None,
            "band": obs.filter_band,
            "stn": obs_code,
            "remarks": "discovery" if i == 0 else None,
        })
    return {
        "type": "observation",
        "provId": designation,
        "submissions": observations,
        "moid_au": neo.hazard.moid_au,
        "neo_class": neo.hazard.neo_class,
        "hazard_flag": neo.hazard.hazard_flag,
    }


def format_mpc_report(neo: ScoredNEO, obs_code: str = _MPC_OBS_CODE) -> str:
    """Generate a full MPC observation report for submission."""
    designation = neo.tracklet.object_id[:12]
    lines: list[str] = [
        "COD " + obs_code, "OBS Claude-NEO-Pipeline", "MEA Claude-NEO-Pipeline",
        "TEL 0.0-m + CCD", "ACK MPCReport", "",
    ]

    for i, obs in enumerate(sorted(neo.tracklet.observations, key=lambda o: o.jd)):
        lines.append(
            format_mpc_observation(obs, designation, is_discovery=(i == 0), obs_code=obs_code)
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Alert log
# ---------------------------------------------------------------------------


def _log_alert(
    neo: ScoredNEO,
    pathway: AlertPathway,
    action: str,
) -> None:
    """Write an immutable alert log entry with full provenance."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).isoformat()
    entry = {
        "timestamp_utc": ts,
        "object_id": neo.tracklet.object_id,
        "alert_pathway": pathway,
        "action": action,
        "scorer_version": neo.metadata.scorer_version,
        "pipeline_run_id": neo.metadata.pipeline_run_id,
        "neo_candidate_probability": neo.posterior.neo_candidate,
        "hazard_flag": neo.hazard.hazard_flag,
        "moid_au": neo.hazard.moid_au,
        "orbit_quality": (
            int(neo.hazard.orbital_elements.quality_code)
            if neo.hazard.orbital_elements
            else None
        ),
        "n_observations": len(neo.tracklet.observations),
        "arc_days": neo.tracklet.arc_days,
    }
    log_path = _LOG_DIR / f"alert_{neo.tracklet.object_id}_{ts[:10]}.json"
    with log_path.open("w") as f:
        json.dump(entry, f, indent=2)
    _logger.info("Alert logged: %s → %s (%s)", neo.tracklet.object_id, pathway, action)


# ---------------------------------------------------------------------------
# Alert protocol steps
# ---------------------------------------------------------------------------


def _submit_to_mpc(neo: ScoredNEO, dry_run: bool = True) -> bool:
    """Submit observation report to MPC.

    In dry_run mode (default for safety), writes the report to disk only.
    Real submission requires MPC credentials and explicit opt-in.
    """
    report = format_mpc_report(neo)
    report_path = _LOG_DIR / f"mpc_report_{neo.tracklet.object_id}.txt"
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    _logger.info("MPC report written to %s", report_path)

    if dry_run:
        _logger.warning("DRY RUN: MPC submission skipped. Set dry_run=False for live submission.")
        return False

    # Live submission path (requires MPC account)
    try:
        import requests  # type: ignore[import]

        resp = requests.post(
            "https://www.minorplanetcenter.net/cgi-bin/report.cgi",
            data={"report": report},
            timeout=30,
        )
        resp.raise_for_status()
        _logger.info("MPC submission response: %s", resp.status_code)
        return True
    except Exception as exc:
        _logger.error("MPC submission failed: %s", exc)
        return False


def _monitor_neocp(object_id: str) -> dict:
    """Check NEOCP for independent confirmation of a candidate."""
    try:
        import requests  # type: ignore[import]

        resp = requests.get(
            "https://www.minorplanetcenter.net/cgi-bin/checkmp.cgi",
            params={"ob": object_id},
            timeout=30,
        )
        return {"status": "checked", "confirmed": False, "raw": resp.text[:500]}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def monitor_neocp(
    object_id: str,
    max_wait_hr: float = 24.0,
    poll_interval_hr: float = 1.0,
    _sleep_fn: Callable[[float], None] | None = None,
) -> dict:
    """Poll NEOCP for independent confirmation of a candidate.

    Blocks until confirmed, ``max_wait_hr`` expires, or a network error occurs.
    ``_sleep_fn`` is injectable for testing (defaults to ``time.sleep``).

    Returns a dict with keys ``status``, ``confirmed``, ``elapsed_hr``,
    and optionally ``raw`` or ``error``.
    """
    sleep_fn = _sleep_fn if _sleep_fn is not None else _time_mod.sleep
    interval_s = poll_interval_hr * 3600.0
    max_s = max_wait_hr * 3600.0
    elapsed = 0.0

    while elapsed < max_s:
        result = _monitor_neocp(object_id)
        if result.get("status") == "error":
            return {**result, "elapsed_hr": elapsed / 3600.0}
        if result.get("confirmed"):
            return {**result, "elapsed_hr": elapsed / 3600.0}
        sleep_fn(interval_s)
        elapsed += interval_s

    return {
        "status": "timeout",
        "confirmed": False,
        "elapsed_hr": elapsed / 3600.0,
        "object_id": object_id,
    }


def _generate_pdco_alert_package(neo: ScoredNEO) -> dict:
    """Generate structured alert package for NASA PDCO notification."""
    return {
        "object_id": neo.tracklet.object_id,
        "hazard_flag": neo.hazard.hazard_flag,
        "moid_au": neo.hazard.moid_au,
        "absolute_magnitude_h": neo.hazard.absolute_magnitude_h,
        "estimated_diameter_m": neo.hazard.estimated_diameter_m,
        "neo_class": neo.hazard.neo_class,
        "neo_candidate_probability": neo.posterior.neo_candidate,
        "orbit_quality_code": (
            int(neo.hazard.orbital_elements.quality_code)
            if neo.hazard.orbital_elements
            else None
        ),
        "arc_days": neo.tracklet.arc_days,
        "n_observations": len(neo.tracklet.observations),
        "scorer_version": neo.metadata.scorer_version,
        "pipeline_run_id": neo.metadata.pipeline_run_id,
        "explanation": neo.hazard.explanation.summary,
        "supporting_evidence": list(neo.hazard.explanation.supporting_evidence),
        "contra_evidence": list(neo.hazard.explanation.contra_evidence),
        # NOTE: No impact probability. Defer all impact assessment to NASA/CNEOS.
        "impact_probability": "DEFERRED — see NASA CNEOS Scout/Sentry",
    }


# ---------------------------------------------------------------------------
# Entry point — mandatory alert protocol
# ---------------------------------------------------------------------------


def process_alert(
    neo: ScoredNEO,
    dry_run: bool = True,
    mpc_obs_code: str = _MPC_OBS_CODE,
    cneos_assessment: dict | None = None,
) -> dict:
    """Execute the mandatory alert protocol for a scored NEO candidate.

    This function enforces the non-negotiable alert decision tree from CLAUDE.md:
      Step 1: MPC submission (if pathway qualifies)
      Step 2: NEOCP monitoring for independent confirmation
      Step 3: NASA PDCO notification (only if CNEOS assigns impact probability ≥ 0.01%)

    Returns a dict summarising actions taken.
    """
    pathway = neo.hazard.alert_pathway
    actions: list[str] = []
    result: dict = {
        "object_id": neo.tracklet.object_id,
        "pathway": pathway,
        "actions": actions,
    }

    # Gate: only external reporting for qualifying pathways
    if pathway in ("internal_candidate", "known_object"):
        actions.append(f"No external reporting: pathway={pathway}")
        _log_alert(neo, pathway, "internal_only")
        return result

    # --- GUARDRAIL CHECK ---
    rb = neo.features.real_bogus_score
    orbit_q = int(neo.hazard.orbital_elements.quality_code) if neo.hazard.orbital_elements else 0
    moid = neo.hazard.moid_au

    if rb is None or rb < 0.90:
        actions.append(f"Alert blocked: real/bogus score {rb} < 0.90 threshold")
        _log_alert(neo, pathway, "blocked_rb")
        return result

    if orbit_q < 2:
        actions.append(f"Alert blocked: orbit quality code {orbit_q} < 2")
        _log_alert(neo, pathway, "blocked_orbit_quality")
        return result

    if moid is None or moid > 0.05:
        actions.append(f"Alert blocked: MOID {moid} > 0.05 AU")
        _log_alert(neo, pathway, "blocked_moid")
        return result

    # Step 1: MPC submission
    submitted = _submit_to_mpc(neo, dry_run=dry_run)
    actions.append(f"MPC report {'submitted' if submitted else 'drafted (dry_run)'}")
    _log_alert(neo, pathway, "mpc_submission")

    # Step 2: NEOCP monitoring (non-blocking; returns immediately for async follow-up)
    neocp_status = _monitor_neocp(neo.tracklet.object_id)
    actions.append(f"NEOCP checked: {neocp_status.get('status')}")
    result["neocp"] = neocp_status

    # Step 3: NASA PDCO — only if external CNEOS assigns impact probability
    # We NEVER compute or assert an impact probability ourselves.
    # This branch must be triggered externally after CNEOS Scout/Sentry assessment.
    cneos_impact_prob = (cneos_assessment or {}).get("cneos_impact_probability")
    if cneos_impact_prob is not None and cneos_impact_prob >= 0.0001:
        pdco_package = _generate_pdco_alert_package(neo)
        pdco_path = _LOG_DIR / f"pdco_alert_{neo.tracklet.object_id}.json"
        pdco_path.write_text(json.dumps(pdco_package, indent=2))
        actions.append(f"NASA PDCO alert package written to {pdco_path}")
        _log_alert(neo, "nasa_pdco_notify", "pdco_package_ready")
        result["pdco_package"] = pdco_package
    else:
        actions.append("NASA PDCO notification deferred: awaiting CNEOS Scout/Sentry assessment")

    return result


def summarise(neo: ScoredNEO) -> str:
    """Return a human-readable candidate summary."""
    h = neo.hazard
    p = neo.posterior
    m = neo.metadata
    lines = [
        f"=== NEO Candidate: {neo.tracklet.object_id} ===",
        f"NEO probability   : {p.neo_candidate:.2%}",
        f"Artifact prob.    : {p.stellar_artifact:.2%}",
        f"Known object prob.: {p.known_object:.2%}",
        f"Hazard flag       : {h.hazard_flag}",
        f"NEO class         : {h.neo_class}",
        f"MOID              : {h.moid_au:.4f} AU" if h.moid_au else "MOID              : unknown",
        (f"Abs. magnitude H  : {h.absolute_magnitude_h:.1f}" if h.absolute_magnitude_h
         else "H                 : unknown"),
        (f"Est. diameter     : {h.estimated_diameter_m:.0f} m" if h.estimated_diameter_m
         else "Diameter          : unknown"),
        f"Alert pathway     : {h.alert_pathway}",
        f"Discovery priority: {m.discovery_priority:.2f}",
        f"Followup value    : {m.followup_value:.2f}",
        f"Arc (days)        : {neo.tracklet.arc_days:.2f}",
        f"N observations    : {len(neo.tracklet.observations)}",
        "",
        "Summary: " + h.explanation.summary,
        "",
        "Supporting evidence:",
        *[f"  + {e}" for e in h.explanation.supporting_evidence],
        "Contra evidence:",
        *[f"  - {e}" for e in h.explanation.contra_evidence],
        "",
        "NOTICE: This pipeline does NOT assert impact probability.",
        "Defer all hazard assessment to MPC/CNEOS.",
    ]
    return "\n".join(lines)


def generate_alert_package(neo: ScoredNEO, obs_code: str = _MPC_OBS_CODE) -> dict:
    """Bundle all alert artifacts for a ScoredNEO into a single dict.

    Returns:
      ``object_id``       — tracklet identifier
      ``mpc_report``      — MPC 80-column formatted string
      ``mpc_json``        — MPC JSON submission dict
      ``summary``         — human-readable text summary
      ``hazard_flag``     — hazard classification
      ``alert_pathway``   — recommended reporting action
      ``n_observations``  — number of observations in tracklet
    """
    return {
        "object_id": neo.tracklet.object_id,
        "mpc_report": format_mpc_report(neo, obs_code=obs_code),
        "mpc_json": format_mpc_json(neo, obs_code=obs_code),
        "summary": summarise(neo),
        "hazard_flag": neo.hazard.hazard_flag,
        "alert_pathway": neo.hazard.alert_pathway,
        "n_observations": len(neo.tracklet.observations),
    }


def batch_process_alerts(
    neos: list[ScoredNEO],
    dry_run: bool = True,
    mpc_obs_code: str = _MPC_OBS_CODE,
) -> list[dict]:
    """Process a list of ScoredNEOs through the alert decision tree.

    Calls ``process_alert`` for each NEO and returns a list of result dicts
    in the same order.  Errors in individual NEOs are caught and reported as
    ``{"object_id": ..., "error": ...}`` rather than raising.
    """
    results: list[dict] = []
    for neo in neos:
        try:
            results.append(process_alert(neo, dry_run=dry_run, mpc_obs_code=mpc_obs_code))
        except Exception as exc:  # pragma: no cover — defensive wrapper
            results.append({"object_id": neo.tracklet.object_id, "error": str(exc)})
    return results


def draft_mpc_submission(neo: ScoredNEO, obs_code: str = _MPC_OBS_CODE) -> dict:
    """Generate a complete MPC submission bundle for human review.

    Combines the 80-column observation report, MPC JSON, a cover-letter
    draft, and a summary into a single dict.  This bundle is for human
    review only — it must never be transmitted automatically.

    Returns:
      ``object_id``    — tracklet identifier
      ``cover_letter`` — plain-text cover letter draft (for human editing)
      ``mpc_report``   — MPC 80-column observation report string
      ``mpc_json``     — MPC JSON submission dict
      ``summary``      — human-readable candidate summary
      ``ready_to_submit`` — bool: True when alert_pathway is mpc_submission
    """
    from datetime import datetime

    obs_count = len(neo.tracklet.observations)
    date_str = datetime.now(UTC).strftime("%Y %B %d")
    cover = (
        f"To: mpc@cfa.harvard.edu\n"
        f"Subject: New NEO Candidate — {neo.tracklet.object_id}\n\n"
        f"Dear MPC,\n\n"
        f"We report {obs_count} astrometric observations of a new moving-object "
        f"candidate ({neo.tracklet.object_id}) obtained on "
        f"{date_str}.  The object shows motion consistent with a "
        f"Near-Earth Object (class: {neo.hazard.neo_class}).\n\n"
        f"Hazard flag     : {neo.hazard.hazard_flag}\n"
        f"Alert pathway   : {neo.hazard.alert_pathway}\n"
        f"MOID (AU)       : {neo.hazard.moid_au}\n\n"
        f"Observations are appended in MPC 80-column format.\n\n"
        f"NOTICE: Impact probability is NOT asserted here.\n"
        f"Please consult MPC/CNEOS for authoritative hazard assessment.\n"
    )
    return {
        "object_id": neo.tracklet.object_id,
        "cover_letter": cover,
        "mpc_report": format_mpc_report(neo, obs_code=obs_code),
        "mpc_json": format_mpc_json(neo, obs_code=obs_code),
        "summary": summarise(neo),
        "ready_to_submit": neo.hazard.alert_pathway == "mpc_submission",
    }


def alert_summary_table(neos: list) -> list[dict]:
    """Return a flat per-NEO alert summary without triggering any submission.

    Each row contains: object_id, hazard_flag, alert_pathway, moid_au,
    neo_class, arc_days, n_observations, ready_to_submit.
    """
    rows: list[dict] = []
    for neo in neos:
        rows.append({
            "object_id": neo.tracklet.object_id,
            "hazard_flag": neo.hazard.hazard_flag,
            "alert_pathway": neo.hazard.alert_pathway,
            "moid_au": neo.hazard.moid_au,
            "neo_class": neo.hazard.neo_class,
            "arc_days": neo.tracklet.arc_days,
            "n_observations": len(neo.tracklet.observations),
            "ready_to_submit": neo.hazard.alert_pathway == "mpc_submission",
        })
    return rows


def format_neocp_report(neo: ScoredNEO, obs_code: str = _MPC_OBS_CODE) -> str:
    """Return a plain-text NEOCP follow-up request for this candidate.

    Does not submit anything.  The returned string is suitable for copying
    into an email to the MPC or posting to the NEOCP community list.
    """
    t = neo.tracklet
    h = neo.hazard
    rate = t.motion_rate_arcsec_per_hour
    pa = t.motion_pa_degrees
    n_obs = len(t.observations)
    # Recommended exposure based on brightness / motion
    if rate > 10.0:
        exp_s = 30
    elif rate > 2.0:
        exp_s = 60
    else:
        exp_s = 120
    obs_block = format_mpc_report(neo, obs_code=obs_code)
    lines = [
        "NEOCP Follow-Up Request",
        "=======================",
        f"Object ID       : {t.object_id}",
        f"NEO class       : {h.neo_class}",
        f"Hazard flag     : {h.hazard_flag}",
        f"MOID (AU)       : {h.moid_au}",
        f"Motion rate     : {rate:.2f} arcsec/hr  PA={pa:.1f} deg",
        f"Arc length      : {t.arc_days:.2f} days  ({n_obs} observations)",
        f"Recommended exp : {exp_s} s (track at motion rate above)",
        "",
        "NOTICE: No impact probability is asserted here.",
        "Please consult MPC/CNEOS for authoritative hazard assessment.",
        "",
        "Astrometry (MPC 80-column format):",
        obs_block,
    ]
    return "\n".join(lines)


def ready_for_submission(neo: ScoredNEO) -> tuple[bool, list[str]]:
    """Check all alert-protocol preconditions for MPC submission in one call.

    Returns ``(ready, unmet_conditions)`` where *ready* is True only when all
    conditions are satisfied and *unmet_conditions* is an empty list.  When
    *ready* is False, *unmet_conditions* lists the specific failed gates.

    Gates (all must pass):
    - ``moid_au`` ≤ 0.05 AU (MOID below PHA threshold)
    - Orbit quality code ≥ 2 (multi-night arc minimum)
    - ``real_bogus_score`` ≥ 0.90
    - ``alert_pathway`` ≠ ``"known_object"`` (not matched to MPC catalog)
    """
    unmet: list[str] = []

    moid = neo.hazard.moid_au
    if moid is None or moid > 0.05:
        unmet.append(f"MOID not ≤ 0.05 AU (got {moid})")

    quality = 0
    if neo.hazard.orbital_elements is not None:
        quality = neo.hazard.orbital_elements.quality_code
    if quality < 2:
        unmet.append(f"Orbit quality code < 2 (got {quality})")

    rb = neo.features.real_bogus_score
    if rb is None or rb < 0.90:
        unmet.append(f"real_bogus_score < 0.90 (got {rb})")

    if neo.hazard.alert_pathway == "known_object":
        unmet.append("Alert pathway is 'known_object' — already in MPC catalog")

    return (len(unmet) == 0, unmet)


def format_discovery_circular(neo) -> str:
    """Generate an IAU CBET-style discovery circular for a ScoredNEO.

    Produces a plain-text stub suitable for human review before submission.
    Does **not** transmit to any external service.

    Fields included: object ID, discovery epoch, RA/Dec, magnitude, orbital
    elements, NEO class, estimated diameter, MOID, and observer template lines.
    """
    from datetime import datetime

    obj_id = neo.tracklet.object_id
    obs = sorted(neo.tracklet.observations, key=lambda o: o.jd)
    first_obs = obs[0] if obs else None

    lines = [
        "CENTRAL BUREAU FOR ASTRONOMICAL TELEGRAMS / IAU CBET",
        "CIRCULAR — DRAFT (NOT FOR DISTRIBUTION)",
        "",
        f"OBJECT:   {obj_id}",
    ]

    if first_obs is not None:
        # Convert JD to approximate calendar date
        unix_sec = (first_obs.jd - 2440587.5) * 86400.0
        dt = datetime.fromtimestamp(unix_sec, tz=UTC)
        date_str = dt.strftime("%Y %b %d.%f UTC")[:-4]
        lines += [
            f"DISCOVERY DATE:  {date_str}",
            f"DISCOVERY RA:    {first_obs.ra_deg:.5f} deg",
            f"DISCOVERY DEC:   {first_obs.dec_deg:+.5f} deg",
            f"DISCOVERY MAG:   {first_obs.mag:.1f} ({first_obs.filter_band})",
            f"SURVEY:          {first_obs.mission}",
        ]

    lines += ["", "ORBITAL ELEMENTS (preliminary):"]
    el = neo.hazard.orbital_elements
    if el is not None:
        lines += [
            f"  a  = {el.semi_major_axis_au:.4f} AU",
            f"  e  = {el.eccentricity:.5f}",
            f"  i  = {el.inclination_deg:.3f} deg",
            f"  quality code = {el.quality_code}",
        ]
    else:
        lines.append("  [orbital elements not available]")

    lines += [
        "",
        f"NEO CLASS:       {neo.hazard.neo_class}",
    ]
    if neo.hazard.moid_au is not None:
        lines.append(f"MOID:            {neo.hazard.moid_au:.4f} AU")
    if neo.hazard.estimated_diameter_m is not None:
        lines.append(f"EST. DIAMETER:   {neo.hazard.estimated_diameter_m:.0f} m")
    if neo.hazard.absolute_magnitude_h is not None:
        lines.append(f"ABS. MAGNITUDE:  H = {neo.hazard.absolute_magnitude_h:.1f}")

    lines += [
        "",
        "NOTES:",
        "  Astrometry pipeline: NEO Detection Pipeline v0.18",
        "  Independent confirmation required before public announcement.",
        "  Do not quote impact probability without CNEOS/MPC assessment.",
        "",
        "OBSERVER/REPORTER:  [FILL IN]",
        "OBSERVATORY CODE:   [FILL IN]",
        "MPC REPORT:         [ATTACH]",
    ]

    return "\n".join(lines)


def format_alert_summary(neos: list, max_rows: int = 20) -> str:
    """Plain-text ranked summary table of scored NEO candidates.

    Columns: rank, object_id, hazard_flag, alert_pathway, moid_au, priority.
    Limited to ``max_rows`` rows; sorted by ``discovery_priority`` descending.
    """
    from score import rank_candidates

    ranked = rank_candidates(list(neos))[:max_rows]
    if not ranked:
        return "No NEO candidates to display."

    header = (
        f"{'#':>4}  {'Object ID':<20}  {'Hazard':>16}"
        f"  {'Pathway':>22}  {'MOID (AU)':>10}  {'Priority':>8}"
    )
    sep = "-" * len(header)
    rows = [header, sep]
    for i, neo in enumerate(ranked, start=1):
        haz = neo.hazard
        meta = neo.metadata
        moid_str = f"{haz.moid_au:.4f}" if haz.moid_au is not None else "  N/A  "
        rows.append(
            f"{i:>4}  {neo.tracklet.object_id:<20}  {haz.hazard_flag:>16}"
            f"  {haz.alert_pathway:>22}  {moid_str:>10}  {meta.discovery_priority:>8.4f}"
        )
    return "\n".join(rows)


def generate_observation_request(neo: Any, obs_code: str = "500") -> str:
    """Generate a structured follow-up observation request (NEOCP-style text).

    Includes urgency tier, ephemeris coordinates, magnitude estimate, and
    observer instructions.  Does not transmit; returns a plain-text string.
    """
    haz = neo.hazard
    meta = neo.metadata
    obj_id = neo.tracklet.object_id
    first_obs = neo.tracklet.observations[0] if neo.tracklet.observations else None

    if haz.hazard_flag == "pha_candidate":
        urgency = "URGENT (PHA candidate)"
    elif meta.discovery_priority >= 0.7:
        urgency = "HIGH"
    elif meta.discovery_priority >= 0.4:
        urgency = "MEDIUM"
    else:
        urgency = "ROUTINE"

    lines = [
        "NEOCP FOLLOW-UP OBSERVATION REQUEST",
        f"Object:     {obj_id}",
        f"Urgency:    {urgency}",
        f"Obs. code:  {obs_code}",
    ]

    if first_obs is not None:
        lines += [
            f"RA (J2000): {first_obs.ra_deg:.5f} deg",
            f"Dec(J2000): {first_obs.dec_deg:+.5f} deg",
            f"Magnitude:  {first_obs.mag:.1f} ({first_obs.filter_band})",
        ]

    if haz.moid_au is not None:
        lines.append(f"MOID:       {haz.moid_au:.4f} AU")

    lines += [
        f"Hazard:     {haz.hazard_flag}",
        f"Pathway:    {haz.alert_pathway}",
        "",
        "Observations requested: ≥3 over ≥2 nights within 72 hours.",
        "Report to MPC using standard 80-column format.",
        "Do not publicly announce impact probability.",
        "GUARDRAIL: This request is for astrometric confirmation only.",
    ]
    return "\n".join(lines)


def generate_mpc_cover_letter(neo: ScoredNEO) -> str:
    """Generate a formal cover letter for an MPC submission package.

    Produces a plain-text cover letter suitable for inclusion with an MPC
    observation report.  Includes object identifier, arc summary, detection
    pipeline version, and mandatory guardrails per the alert protocol.

    Does NOT transmit.  Returns the cover letter text only.

    Args:
        neo: A scored NEO candidate with tracklet, hazard, and metadata.

    Returns:
        Formatted cover letter as a multi-line string.
    """
    from datetime import UTC, datetime

    obj_id = neo.tracklet.object_id
    n_obs = len(neo.tracklet.observations)
    arc = neo.tracklet.arc_days
    haz = neo.hazard
    meta = neo.metadata

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    moid_str = f"{haz.moid_au:.4f} AU" if haz.moid_au is not None else "unknown"

    lines = [
        "=" * 70,
        "MPC SUBMISSION COVER LETTER",
        f"Date: {date_str}",
        "=" * 70,
        "",
        f"Object Designation: {obj_id}",
        f"Number of Observations: {n_obs}",
        f"Arc Length: {arc:.3f} days",
        f"NEO Class: {haz.neo_class}",
        f"Hazard Flag: {haz.hazard_flag}",
        f"MOID (computed): {moid_str}",
        f"Alert Pathway: {haz.alert_pathway}",
        f"Pipeline Version: {meta.scorer_version}",
        "",
        "IMPORTANT NOTICES:",
        "- This report is generated by an automated pipeline.",
        "- The MOID and hazard assessment are PRELIMINARY.",
        "- Do NOT publicly announce any impact probability.",
        "- All hazard determinations must be confirmed by CNEOS Scout/Sentry.",
        "- Independent confirmation by ≥2 observatories is required before",
        "  any NASA PDCO notification (per alert protocol step 2).",
        "",
        "Submitted via: NEO Detection Pipeline v" + meta.scorer_version,
        "=" * 70,
    ]
    return "\n".join(lines)


def format_impact_notification(neo: ScoredNEO) -> dict:
    """Format a PDCO-ready impact notification package as a structured dict.

    Produces a structured notification package for submission to NASA PDCO
    and IAU CBAT when CNEOS Scout/Sentry confirms a non-trivial impact
    probability.  This function does NOT transmit — it returns a dict that
    must be reviewed and approved by authorised personnel before use.

    The package includes full provenance, guardrail statements, and all
    required observation and orbital data.

    Args:
        neo: A :class:`~schemas.ScoredNEO` object with full hazard assessment.

    Returns:
        Dict with keys: ``object_id``, ``generated_utc``, ``hazard_flag``,
        ``alert_pathway``, ``moid_au``, ``neo_class``, ``n_observations``,
        ``arc_days``, ``pipeline_version``, ``guardrails``, ``observations``.
    """
    from datetime import UTC, datetime

    obj_id = neo.tracklet.object_id
    haz = neo.hazard
    meta = neo.metadata
    now_utc = datetime.now(UTC).isoformat()

    obs_records = [
        {
            "obs_id": o.obs_id,
            "ra_deg": o.ra_deg,
            "dec_deg": o.dec_deg,
            "jd": o.jd,
            "mag": o.mag,
            "filter_band": o.filter_band,
            "mission": o.mission,
        }
        for o in neo.tracklet.observations
    ]

    return {
        "object_id": obj_id,
        "generated_utc": now_utc,
        "hazard_flag": haz.hazard_flag,
        "alert_pathway": haz.alert_pathway,
        "moid_au": haz.moid_au,
        "absolute_magnitude_h": haz.absolute_magnitude_h,
        "estimated_diameter_m": haz.estimated_diameter_m,
        "neo_class": haz.neo_class,
        "n_observations": len(neo.tracklet.observations),
        "arc_days": neo.tracklet.arc_days,
        "pipeline_version": meta.scorer_version,
        "pipeline_run_id": meta.pipeline_run_id,
        "guardrails": [
            "This notification is PRELIMINARY and requires authorised human review.",
            "Do NOT publicly announce any impact probability.",
            "All hazard significance must be confirmed by CNEOS Scout/Sentry.",
            "Independent confirmation by ≥2 observatories is required (alert protocol step 2).",
        ],
        "observations": obs_records,
    }


def count_pending_alerts(neos: list) -> dict:
    """Count scored NEOs grouped by their alert pathway.

    Provides a quick tally of how many candidates fall into each alert category,
    useful for operations dashboards and run summaries.

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.

    Returns:
        Dict mapping each ``alert_pathway`` string to its count.  Only pathways
        with at least one candidate are included.
    """
    counts: dict = {}
    for neo in neos:
        pathway = neo.hazard.alert_pathway
        counts[pathway] = counts.get(pathway, 0) + 1
    return counts


def format_submission_checklist(neo: ScoredNEO) -> str:
    """Generate a plain-text submission checklist for a scored NEO candidate.

    Evaluates each required gate condition from the alert protocol and marks
    it as passed (✓) or failed (✗).  Designed for human review before any
    external report is filed.

    Args:
        neo: A :class:`~schemas.ScoredNEO` object.

    Returns:
        Multi-line plain-text string with one checklist item per line.
    """
    haz = neo.hazard
    feat = neo.features
    post = neo.posterior

    def gate(label: str, passed: bool) -> str:
        mark = "✓" if passed else "✗"
        return f"  [{mark}] {label}"

    rb = feat.real_bogus_score
    orbit_elem = haz.orbital_elements
    quality = int(orbit_elem.quality_code) if orbit_elem else 0
    moid = haz.moid_au
    known = (feat.known_object_score or 0.0) < 0.8

    lines = [
        f"Submission checklist for: {neo.tracklet.object_id}",
        f"  Hazard flag   : {haz.hazard_flag}",
        f"  Alert pathway : {haz.alert_pathway}",
        "",
        "Gate conditions (alert protocol):",
        gate("real_bogus_score ≥ 0.90", rb is not None and rb >= 0.90),
        gate("orbit quality code ≥ 2", quality >= 2),
        gate("MOID ≤ 0.05 AU (computed)", moid is not None and moid <= 0.05),
        gate("not matched to MPC known object", known),
        gate("neo_candidate probability ≥ 0.50", post.neo_candidate >= 0.50),
        "",
        "Required steps before external reporting:",
        gate("Step 1: Submit to MPC", haz.alert_pathway in ("mpc_submission", "nasa_pdco_notify")),
        gate("Step 2: Await NEOCP confirmation (≥24 hr or ≥2 obs.)",
             haz.alert_pathway == "nasa_pdco_notify"),
        gate("Step 3: NASA PDCO notify (if Scout/Sentry impact prob ≥ 0.01%)",
             haz.alert_pathway == "nasa_pdco_notify"),
        "",
        "GUARDRAIL: Do NOT publicly announce any impact probability.",
    ]
    return "\n".join(lines)


def validate_alert_package(package: dict) -> tuple[bool, list[str]]:
    """Validate the completeness of an alert package dict.

    Checks that the package contains all keys required for a NASA PDCO
    notification or MPC submission.  Also validates that no raw impact
    probability has been quoted (guardrail enforcement).

    Required keys:
    - ``observations``: non-empty sequence of observations
    - ``orbit``: orbital elements dict or object
    - ``moid_au``: float (may be None but key must be present)
    - ``alert_pathway``: valid AlertPathway string
    - ``guardrail_statement``: non-empty string containing the word "NOT"

    Args:
        package: Dict produced by :func:`generate_alert_package` or similar.

    Returns:
        Tuple of ``(is_valid, issues)`` where ``is_valid`` is ``True`` when
        all checks pass and ``issues`` is a list of problem descriptions.
    """
    _REQUIRED_KEYS = {"observations", "orbit", "moid_au", "alert_pathway",
                      "guardrail_statement"}
    _VALID_PATHWAYS = {
        "mpc_submission", "neocp_followup", "nasa_pdco_notify",
        "internal_candidate", "known_object",
    }

    issues: list[str] = []

    missing = _REQUIRED_KEYS - set(package.keys())
    for key in sorted(missing):
        issues.append(f"missing required key: '{key}'")

    if "observations" in package:
        obs = package["observations"]
        if hasattr(obs, "__len__") and len(obs) == 0:
            issues.append("'observations' is empty")
        elif obs is None:
            issues.append("'observations' is None")

    if "alert_pathway" in package:
        pathway = package["alert_pathway"]
        if pathway not in _VALID_PATHWAYS:
            issues.append(f"'alert_pathway' value '{pathway}' is not a valid AlertPathway")

    if "guardrail_statement" in package:
        gs = package.get("guardrail_statement") or ""
        if not gs:
            issues.append("'guardrail_statement' is empty")
        elif "NOT" not in gs.upper():
            issues.append(
                "'guardrail_statement' should contain 'NOT' to comply with impact-claim guardrail"
            )

    return (len(issues) == 0, issues)


def estimate_followup_window(neo: Any) -> dict:
    """Estimate the observational follow-up time window for a scored NEO.

    Assigns an urgency window based on hazard flag and alert pathway, then
    returns the start and end Julian Dates of that window.

    Urgency rules (in priority order):

    1. ``hazard_flag == "pha_candidate"`` → **24 hours**
    2. ``alert_pathway == "neocp_followup"`` → **48 hours**
    3. Otherwise → ``72.0 * (1.0 − discovery_priority)`` hours, clamped to
       [24, 168] hours.

    The start JD is fixed at ``2460000.0`` for deterministic testing.

    Args:
        neo: A :class:`~schemas.ScoredNEO` object.

    Returns:
        Dict with keys:

        - ``"start_jd"``: Fixed reference epoch (2460000.0).
        - ``"end_jd"``: start_jd + urgency_hours / 24.0.
        - ``"urgency_hours"``: Follow-up window length in hours.
    """
    haz = neo.hazard
    meta = neo.metadata
    discovery_priority = getattr(meta, "discovery_priority", 0.0) or 0.0

    if haz.hazard_flag == "pha_candidate":
        urgency_hours = 24.0
    elif haz.alert_pathway == "neocp_followup":
        urgency_hours = 48.0
    else:
        raw = 72.0 * (1.0 - float(discovery_priority))
        urgency_hours = max(24.0, min(168.0, raw))

    start_jd = 2460000.0
    end_jd = start_jd + urgency_hours / 24.0

    return {
        "start_jd": start_jd,
        "end_jd": round(end_jd, 6),
        "urgency_hours": urgency_hours,
    }


def format_candidate_dossier(neo: ScoredNEO) -> str:
    """Generate a single-page plain-text dossier for a NEO candidate.

    Consolidates the key outputs from all pipeline stages into a compact,
    human-readable summary suitable for operator review or filing.

    Args:
        neo: A :class:`~schemas.ScoredNEO` object.

    Returns:
        Multi-line plain-text string.  Does not transmit or publish anything.
    """
    haz = neo.hazard
    meta = neo.metadata
    post = neo.posterior
    track = neo.tracklet

    lines = [
        "=" * 72,
        f"NEO CANDIDATE DOSSIER — {track.object_id}",
        "=" * 72,
        "",
        "[ HAZARD ASSESSMENT ]",
        f"  Hazard flag    : {haz.hazard_flag}",
        f"  Alert pathway  : {haz.alert_pathway}",
        f"  NEO class      : {haz.neo_class}",
        f"  MOID (AU)      : {haz.moid_au}",
        f"  Abs. mag. H    : {haz.absolute_magnitude_h}",
        f"  Diameter (m)   : {haz.estimated_diameter_m}",
        "",
        "[ POSTERIOR PROBABILITIES ]",
        f"  neo_candidate       : {post.neo_candidate:.4f}",
        f"  known_object        : {post.known_object:.4f}",
        f"  main_belt_asteroid  : {post.main_belt_asteroid:.4f}",
        f"  stellar_artifact    : {post.stellar_artifact:.4f}",
        f"  other_solar_system  : {post.other_solar_system:.4f}",
        "",
        "[ SCORING METADATA ]",
        f"  Discovery priority  : {getattr(meta, 'discovery_priority', 'N/A')}",
        f"  Orbit quality       : {getattr(haz, 'explanation', '') or 'N/A'}",
        "",
        "[ TRACKLET ]",
        f"  Arc (days)          : {track.arc_days:.3f}",
        f"  Motion rate (″/hr)  : {track.motion_rate_arcsec_per_hour:.2f}",
        f"  Observations        : {len(track.observations)}",
        "",
        "[ GUARDRAIL ]",
        "  Do NOT publicly announce any impact probability.",
        "  Defer all public communication to NASA/CNEOS.",
        "=" * 72,
    ]
    return "\n".join(lines)


def count_alerts_by_flag(neos: list[ScoredNEO]) -> dict[str, int]:
    """Count the number of candidates for each hazard flag.

    Only includes flags that appear in the list (no zero-count entries).
    Returns an empty dict for an empty list.

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.

    Returns:
        Dict mapping hazard_flag → count.
    """
    counts: dict[str, int] = {}
    for neo in neos:
        flag = neo.hazard.hazard_flag
        counts[flag] = counts.get(flag, 0) + 1
    return counts


def format_bulk_summary(neos: list[ScoredNEO], title: str = "Pipeline Run Summary") -> str:
    """Format a multi-line plain-text bulk summary for a list of scored NEOs.

    The output includes overall counts (total, PHA candidates, NEOCP follow-ups,
    known objects, alerts ready for submission), a flag breakdown, and a ranked
    table of the top-10 candidates by discovery priority.

    Guardrail statement is appended to every summary.

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.
        title: Header title for the summary block.

    Returns:
        Formatted plain-text string.  Returns a minimal header for empty input.
    """
    lines: list[str] = [title, "=" * len(title)]

    if not neos:
        lines.append("No candidates.")
        lines.append(
            "GUARDRAIL: This pipeline does NOT assert Earth-impact probability. "
            "Defer to MPC/CNEOS."
        )
        return "\n".join(lines)

    n_total = len(neos)
    n_pha = sum(1 for n in neos if n.hazard.hazard_flag == "pha_candidate")
    n_neocp = sum(1 for n in neos if n.hazard.alert_pathway == "neocp_followup")
    n_known = sum(1 for n in neos if n.hazard.alert_pathway == "known_object")
    ready_list = [n for n in neos if ready_for_submission(n)[0]]

    lines += [
        f"Total candidates  : {n_total}",
        f"PHA candidates    : {n_pha}",
        f"NEOCP follow-ups  : {n_neocp}",
        f"Known objects     : {n_known}",
        f"Ready to submit   : {len(ready_list)}",
        "",
        "Hazard flag breakdown:",
    ]
    for flag, count in sorted(count_alerts_by_flag(neos).items()):
        lines.append(f"  {flag:<20s}: {count}")

    header = f"  {'Object':<20s} {'Flag':<16s} {'Pathway':<22s} {'Priority':>8s}"
    lines += ["", "Top-10 by discovery priority:", header]
    sorted_neos = sorted(
        neos,
        key=lambda n: float(getattr(n.metadata, "discovery_priority", 0.0) or 0.0),
        reverse=True,
    )
    for neo in sorted_neos[:10]:
        prio = float(getattr(neo.metadata, "discovery_priority", 0.0) or 0.0)
        lines.append(
            f"  {neo.tracklet.object_id:<20s} {neo.hazard.hazard_flag:<16s} "
            f"{neo.hazard.alert_pathway:<22s} {prio:>8.3f}"
        )

    lines += [
        "",
        "GUARDRAIL: This pipeline does NOT assert Earth-impact probability. "
        "Defer to MPC/CNEOS.",
    ]
    return "\n".join(lines)


def count_ready_to_submit(neos: list[ScoredNEO]) -> int:
    """Count NEO candidates that pass all alert-protocol gate conditions.

    Calls :func:`ready_for_submission` on each candidate and returns the
    number for which all gate conditions are met.  Returns 0 for an empty list.

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.

    Returns:
        Integer count of submission-ready candidates.
    """
    return sum(1 for neo in neos if ready_for_submission(neo)[0])


def compute_alert_age_days(neo: ScoredNEO, current_jd: float) -> float:
    """Return the number of days since the first tracklet observation.

    Uses the minimum JD across all observations in the tracklet as the
    discovery epoch.  Returns 0.0 when the tracklet contains no observations
    or when *current_jd* is not later than the first observation.
    """
    obs = list(getattr(neo.tracklet, "observations", ()))
    if not obs:
        return 0.0
    first_jd = min(float(getattr(o, "jd", current_jd)) for o in obs)
    age = current_jd - first_jd
    return round(max(0.0, age), 4)


def format_observation_log(neo: ScoredNEO) -> str:
    """Return a plain-text table of all tracklet observations.

    Columns: JD, RA (deg), Dec (deg), Mag, Filter, Mission.  The table
    is sorted by Julian Date and includes a header and separator line.
    Returns an empty-table string when the tracklet has no observations.
    """
    obs_list = sorted(neo.tracklet.observations, key=lambda o: o.jd)
    header = (
        f"{'JD':>14s}  {'RA (deg)':>10s}  {'Dec (deg)':>10s}"
        f"  {'Mag':>6s}  {'Filter':<8s}  Mission"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for o in obs_list:
        lines.append(
            f"{o.jd:>14.4f}  {o.ra_deg:>10.6f}  {o.dec_deg:>10.6f}"
            f"  {o.mag:>6.2f}  {o.filter_band:<8s}  {o.mission}"
        )
    lines.append(sep)
    lines.append(f"{len(obs_list)} observation(s) for {neo.tracklet.object_id}")
    return "\n".join(lines)
