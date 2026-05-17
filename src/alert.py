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
]

import json
import logging
import time as _time_mod
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

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
