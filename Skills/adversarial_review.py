"""Adversarial review of scored NEO candidates — tries to reject each one.

This implements the first stage of the two-stage review process that sits
between the pipeline's internal scoring and any external submission:

    Pipeline → Adversarial Review (this) → Operator review → External submission

The adversarial agent runs a battery of challenges designed to find fatal
flaws in a candidate's candidacy.  Each challenge looks for a specific reason
to reject — mimicking a skeptical reviewer who starts from the presumption that
the candidate is NOT a novel NEO.  Only candidates that survive all challenges
should advance to the operator review stage.

Challenge outcomes:
  PASS    — no concern found for this challenge
  WARNING — potential issue; alone it does not reject, but adds up
  FAIL    — clear disqualifying flaw; candidate must be REJECTED
  SKIP    — challenge could not run (network unavailable, missing data)

Verdict rules (ordered):
  REJECT     — any FAIL (even one disqualifying finding terminates review)
  BORDERLINE — no FAILs, ≥2 WARNINGs (multiple concerns; needs operator scrutiny)
  SURVIVE    — no FAILs, 0–1 WARNINGs (clean bill; advance to operator review)

Usage:
    # Review a single or list of scored NEO JSON objects:
    python Skills/adversarial_review.py data/candidates.json

    # Force offline-only mode (skip all live queries):
    python Skills/adversarial_review.py data/candidates.json --offline

    # Machine-readable output:
    python Skills/adversarial_review.py data/candidates.json --json

    # Supply ATLAS token for cross-survey verification:
    python Skills/adversarial_review.py data/candidates.json --atlas-token TOKEN
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# Allow running directly as a script or via PYTHONPATH=src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from schemas import ScoredNEO

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ChallengeOutcome = Literal["PASS", "WARNING", "FAIL", "SKIP"]
Verdict = Literal["SURVIVE", "BORDERLINE", "REJECT"]

# ---------------------------------------------------------------------------
# Thresholds — all documented so they can be tuned without hunting for magic numbers
# ---------------------------------------------------------------------------

# Motion-rate plausibility bounds (arcsec/hr)
_RATE_MIN_HARD = 0.05    # below → stationary artifact (satellite glint, hot pixel)
_RATE_MAX_HARD = 200.0   # above → satellite/aircraft, not solar system body
_RATE_MIN_SOFT = 0.30    # below → suspicious; genuine very-slow TNO or Trojan, but rare
_RATE_MAX_SOFT = 100.0   # above → fast Earth-crosser; real but warrants scrutiny

# Minimum arc length thresholds (days)
_ARC_FAIL_DAYS = 0.5     # under this: no reliable orbit or MOID computation possible
_ARC_WARN_DAYS = 1.0     # under this: orbit is formally possible but unreliable

# Posterior thresholds
_KNOWN_OBJ_FAIL_PROB = 0.50   # posterior probability: this is a known object → FAIL
_KNOWN_OBJ_WARN_PROB = 0.20   # posterior probability: likely a known object → WARNING
_ARTIFACT_FAIL_PROB = 0.30    # posterior probability: stellar artifact → FAIL
_ARTIFACT_WARN_PROB = 0.15    # posterior probability: possible artifact → WARNING
_NEO_DOMINANCE_FAIL = 0.30    # neo_candidate posterior below this → FAIL
_NEO_DOMINANCE_WARN = 0.50    # neo_candidate posterior below this → WARNING
_MBA_FAIL_PROB = 0.40         # main_belt_asteroid posterior above this → FAIL
_MBA_WARN_PROB = 0.25         # main_belt_asteroid posterior above this → WARNING

# Real/bogus threshold: gate is 0.90; within 2% is "borderline"
_RB_GATE = 0.90
_RB_BORDERLINE_MARGIN = 0.02  # 0.90–0.92 is suspicious even if technically passes

# Field radius for live MPC cone search (degrees)
_LIVE_FIELD_RADIUS_DEG = 0.5

# ATLAS cross-survey: require at least 1 detection in the ATLAS field to confirm
_ATLAS_MIN_DETECTIONS = 1

# Minimum independent nights required for a valid reportable tracklet
_MIN_NIGHTS_HARD = 2     # MPC requires observations on ≥2 distinct nights
_MIN_NIGHTS_WARN = 3     # fewer than 3 nights: orbit is underconstrained


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ChallengeResult:
    """Single challenge verdict with structured reasoning."""
    name: str
    outcome: ChallengeOutcome
    reason: str
    details: dict


@dataclass
class ReviewVerdict:
    """Aggregate adversarial review verdict for one candidate."""
    object_id: str
    verdict: Verdict
    challenges: list[ChallengeResult]
    fail_count: int
    warning_count: int
    summary: str
    reviewed_at_utc: str

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        d = asdict(self)
        d["challenges"] = [asdict(c) for c in self.challenges]
        return d


# ---------------------------------------------------------------------------
# Offline challenges (always run — no network required)
# ---------------------------------------------------------------------------


def _challenge_orbit_quality(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates with no usable orbital solution.

    Orbit quality code 0 means no elements were computed; quality 1 means a
    single-night arc — not enough for a meaningful orbit or MOID.
    """
    elements = neo.hazard.orbital_elements
    if elements is None:
        return ChallengeResult(
            name="orbit_quality",
            outcome="FAIL",
            reason="No orbital elements computed — cannot assess orbit quality.",
            details={"quality_code": None},
        )
    q = elements.quality_code
    if q == 0:
        return ChallengeResult(
            name="orbit_quality",
            outcome="FAIL",
            reason=f"Orbit quality code {q} — degenerate solution, no reliable orbit.",
            details={"quality_code": q},
        )
    if q == 1:
        return ChallengeResult(
            name="orbit_quality",
            outcome="WARNING",
            reason=f"Orbit quality code {q} (single-night arc) — orbit underconstrained.",
            details={"quality_code": q},
        )
    return ChallengeResult(
        name="orbit_quality",
        outcome="PASS",
        reason=f"Orbit quality code {q} ≥ 2 — multi-night arc accepted.",
        details={"quality_code": q},
    )


def _challenge_arc_length(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates with insufficient observational arc.

    Short arcs yield poor orbital solutions and unreliable MOID estimates.
    The MPC generally requires at minimum two distinct nights.
    """
    arc = neo.tracklet.arc_days
    if arc < _ARC_FAIL_DAYS:
        return ChallengeResult(
            name="arc_length",
            outcome="FAIL",
            reason=f"Arc length {arc:.3f} d < {_ARC_FAIL_DAYS} d — too short for any orbit.",
            details={"arc_days": arc, "threshold_fail": _ARC_FAIL_DAYS},
        )
    if arc < _ARC_WARN_DAYS:
        return ChallengeResult(
            name="arc_length",
            outcome="WARNING",
            reason=(
                f"Arc length {arc:.3f} d < {_ARC_WARN_DAYS} d — "
                "orbit and MOID estimates are unreliable on sub-day arcs."
            ),
            details={"arc_days": arc, "threshold_warn": _ARC_WARN_DAYS},
        )
    return ChallengeResult(
        name="arc_length",
        outcome="PASS",
        reason=f"Arc length {arc:.3f} d ≥ {_ARC_WARN_DAYS} d.",
        details={"arc_days": arc},
    )


def _challenge_multi_night(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates observed on fewer than 2 distinct nights.

    MPC requires observations from ≥2 different nights to confirm independent
    motion — a single night of observations can always be explained by a fixed
    artifact appearing multiple times.
    """
    # Count distinct integer Julian dates (proxy for distinct nights)
    nights = {int(o.jd) for o in neo.tracklet.observations}
    n = len(nights)
    n_obs = len(neo.tracklet.observations)
    if n < _MIN_NIGHTS_HARD:
        return ChallengeResult(
            name="multi_night",
            outcome="FAIL",
            reason=(
                f"Only {n} distinct night(s) in {n_obs} observations — "
                "MPC requires ≥2 nights to confirm independent motion."
            ),
            details={"n_nights": n, "n_obs": n_obs, "threshold": _MIN_NIGHTS_HARD},
        )
    if n < _MIN_NIGHTS_WARN:
        return ChallengeResult(
            name="multi_night",
            outcome="WARNING",
            reason=(
                f"{n} nights ({n_obs} obs) — minimum accepted, "
                "orbit solution will be poorly constrained."
            ),
            details={"n_nights": n, "n_obs": n_obs},
        )
    return ChallengeResult(
        name="multi_night",
        outcome="PASS",
        reason=f"{n} distinct nights, {n_obs} observations.",
        details={"n_nights": n, "n_obs": n_obs},
    )


def _challenge_real_bogus(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates that fail or barely pass the real/bogus gate.

    The pipeline gate is rb ≥ 0.90.  Candidates in the 0.90–0.92 margin are
    technically passing but should be treated with additional suspicion —
    the gate exists for a reason and proximity to it is a red flag.
    """
    rb = neo.features.real_bogus_score
    if rb is None or rb < _RB_GATE:
        return ChallengeResult(
            name="real_bogus",
            outcome="FAIL",
            reason=f"real_bogus_score {rb} is None or < {_RB_GATE} — fails submission gate.",
            details={"real_bogus_score": rb, "gate": _RB_GATE},
        )
    if rb < _RB_GATE + _RB_BORDERLINE_MARGIN:
        return ChallengeResult(
            name="real_bogus",
            outcome="WARNING",
            reason=(
                f"real_bogus_score {rb:.3f} passes gate but is within "
                f"{_RB_BORDERLINE_MARGIN:.0%} of threshold {_RB_GATE} — borderline."
            ),
            details={"real_bogus_score": rb, "gate": _RB_GATE, "margin": _RB_BORDERLINE_MARGIN},
        )
    return ChallengeResult(
        name="real_bogus",
        outcome="PASS",
        reason=f"real_bogus_score {rb:.3f} comfortably above gate {_RB_GATE}.",
        details={"real_bogus_score": rb},
    )


def _challenge_known_object_posterior(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates where the classifier strongly favors 'known_object'.

    A high known_object posterior means the ML models believe this is a
    catalogued solar system body, not a novel discovery.
    """
    known_p = neo.posterior.known_object
    if known_p >= _KNOWN_OBJ_FAIL_PROB:
        return ChallengeResult(
            name="known_object_posterior",
            outcome="FAIL",
            reason=(
                f"known_object posterior {known_p:.3f} ≥ {_KNOWN_OBJ_FAIL_PROB} — "
                "classifier strongly indicates this is a catalogued object."
            ),
            details={"known_object_prob": known_p},
        )
    if known_p >= _KNOWN_OBJ_WARN_PROB:
        return ChallengeResult(
            name="known_object_posterior",
            outcome="WARNING",
            reason=(
                f"known_object posterior {known_p:.3f} ≥ {_KNOWN_OBJ_WARN_PROB} — "
                "non-trivial chance this is a known object."
            ),
            details={"known_object_prob": known_p},
        )
    return ChallengeResult(
        name="known_object_posterior",
        outcome="PASS",
        reason=f"known_object posterior {known_p:.3f} below warning threshold.",
        details={"known_object_prob": known_p},
    )


def _challenge_artifact_posterior(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates where the classifier strongly favors 'stellar_artifact'.

    A high artifact posterior means the ML models see patterns (point-spread
    function shape, pixel distribution, host-star proximity) consistent with
    cosmic rays, satellite glints, ghost reflections, or bleeding columns.
    """
    art_p = neo.posterior.stellar_artifact
    if art_p >= _ARTIFACT_FAIL_PROB:
        return ChallengeResult(
            name="artifact_posterior",
            outcome="FAIL",
            reason=(
                f"stellar_artifact posterior {art_p:.3f} ≥ {_ARTIFACT_FAIL_PROB} — "
                "classifier indicates this is likely an instrumental artifact."
            ),
            details={"stellar_artifact_prob": art_p},
        )
    if art_p >= _ARTIFACT_WARN_PROB:
        return ChallengeResult(
            name="artifact_posterior",
            outcome="WARNING",
            reason=(
                f"stellar_artifact posterior {art_p:.3f} ≥ {_ARTIFACT_WARN_PROB} — "
                "non-trivial artifact probability requires scrutiny."
            ),
            details={"stellar_artifact_prob": art_p},
        )
    return ChallengeResult(
        name="artifact_posterior",
        outcome="PASS",
        reason=f"stellar_artifact posterior {art_p:.3f} below warning threshold.",
        details={"stellar_artifact_prob": art_p},
    )


def _challenge_neo_posterior_dominance(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates where the neo_candidate hypothesis does not dominate.

    Even if other checks pass, a weak neo_candidate posterior means the models
    do not actually believe this is a novel NEO — the candidate should be
    explained by one of the other hypotheses first.
    """
    neo_p = neo.posterior.neo_candidate
    if neo_p < _NEO_DOMINANCE_FAIL:
        return ChallengeResult(
            name="neo_dominance",
            outcome="FAIL",
            reason=(
                f"neo_candidate posterior {neo_p:.3f} < {_NEO_DOMINANCE_FAIL} — "
                "classifier does not favour novel NEO hypothesis."
            ),
            details={"neo_candidate_prob": neo_p},
        )
    if neo_p < _NEO_DOMINANCE_WARN:
        return ChallengeResult(
            name="neo_dominance",
            outcome="WARNING",
            reason=(
                f"neo_candidate posterior {neo_p:.3f} < {_NEO_DOMINANCE_WARN} — "
                "NEO hypothesis not dominant; competing hypotheses are plausible."
            ),
            details={"neo_candidate_prob": neo_p},
        )
    return ChallengeResult(
        name="neo_dominance",
        outcome="PASS",
        reason=f"neo_candidate posterior {neo_p:.3f} is dominant.",
        details={"neo_candidate_prob": neo_p},
    )


def _challenge_mba_confusion(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates where the main-belt asteroid hypothesis is dominant.

    Most moving objects in ZTF data are MBAs.  A high MBA posterior means the
    orbital geometry (motion rate, ecliptic latitude, magnitude) matches the
    main belt, not the near-Earth population.  Such candidates would not be
    novel NEO discoveries even if they are real solar system bodies.
    """
    mba_p = neo.posterior.main_belt_asteroid
    if mba_p >= _MBA_FAIL_PROB:
        return ChallengeResult(
            name="mba_confusion",
            outcome="FAIL",
            reason=(
                f"main_belt_asteroid posterior {mba_p:.3f} ≥ {_MBA_FAIL_PROB} — "
                "candidate is more likely an MBA than a NEO."
            ),
            details={"main_belt_asteroid_prob": mba_p},
        )
    if mba_p >= _MBA_WARN_PROB:
        return ChallengeResult(
            name="mba_confusion",
            outcome="WARNING",
            reason=(
                f"main_belt_asteroid posterior {mba_p:.3f} ≥ {_MBA_WARN_PROB} — "
                "MBA contamination cannot be excluded."
            ),
            details={"main_belt_asteroid_prob": mba_p},
        )
    return ChallengeResult(
        name="mba_confusion",
        outcome="PASS",
        reason=f"main_belt_asteroid posterior {mba_p:.3f} below warning threshold.",
        details={"main_belt_asteroid_prob": mba_p},
    )


def _challenge_motion_rate(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates with implausible apparent motion rates.

    Solar system NEOs move between ~0.05 and ~100 arcsec/hr as seen from
    Earth.  Objects outside this range are almost certainly not NEOs:
    slower rates are consistent with stationary artifacts or very distant
    trans-Neptunian objects; faster rates indicate satellites or aircraft.
    """
    rate = neo.tracklet.motion_rate_arcsec_per_hour
    if not math.isfinite(rate):
        return ChallengeResult(
            name="motion_rate",
            outcome="FAIL",
            reason=f"Motion rate is not finite ({rate}) — data corruption suspected.",
            details={"rate_arcsec_hr": rate},
        )
    if rate < _RATE_MIN_HARD or rate > _RATE_MAX_HARD:
        return ChallengeResult(
            name="motion_rate",
            outcome="FAIL",
            reason=(
                f"Motion rate {rate:.3f} arcsec/hr outside hard bounds "
                f"[{_RATE_MIN_HARD}, {_RATE_MAX_HARD}] — not a solar system body."
            ),
            details={
                "rate_arcsec_hr": rate,
                "bound_low": _RATE_MIN_HARD,
                "bound_high": _RATE_MAX_HARD,
            },
        )
    if rate < _RATE_MIN_SOFT or rate > _RATE_MAX_SOFT:
        return ChallengeResult(
            name="motion_rate",
            outcome="WARNING",
            reason=(
                f"Motion rate {rate:.3f} arcsec/hr outside typical NEO range "
                f"[{_RATE_MIN_SOFT}, {_RATE_MAX_SOFT}] — possible but unusual."
            ),
            details={
                "rate_arcsec_hr": rate,
                "bound_low": _RATE_MIN_SOFT,
                "bound_high": _RATE_MAX_SOFT,
            },
        )
    return ChallengeResult(
        name="motion_rate",
        outcome="PASS",
        reason=f"Motion rate {rate:.3f} arcsec/hr within typical NEO range.",
        details={"rate_arcsec_hr": rate},
    )


def _challenge_moid_arc_consistency(neo: ScoredNEO) -> ChallengeResult:
    """Warn when a MOID ≤ 0.05 AU is claimed from an unreliable short arc.

    MOID estimates from arcs shorter than 24 hours are numerically unstable —
    a short arc often maps to a family of plausible orbits with a wide range
    of MOID values.  Claiming PHA-level MOID on a short arc is misleading.
    """
    moid = neo.hazard.moid_au
    arc = neo.tracklet.arc_days
    elements = neo.hazard.orbital_elements
    quality = elements.quality_code if elements is not None else 0

    # Only relevant when a close-approach MOID has been computed
    if moid is None or moid > 0.10:
        return ChallengeResult(
            name="moid_arc_consistency",
            outcome="PASS",
            reason="MOID > 0.10 AU or not computed — no PHA claim to scrutinise.",
            details={"moid_au": moid, "arc_days": arc},
        )

    if arc < 1.0 or quality < 2:
        return ChallengeResult(
            name="moid_arc_consistency",
            outcome="WARNING",
            reason=(
                f"MOID = {moid:.4f} AU (≤ 0.10) claimed from arc {arc:.3f} d "
                f"(quality code {quality}) — MOID is unreliable on sub-day or "
                "single-night arcs; do not use for PHA classification."
            ),
            details={"moid_au": moid, "arc_days": arc, "quality_code": quality},
        )

    return ChallengeResult(
        name="moid_arc_consistency",
        outcome="PASS",
        reason=(
            f"MOID = {moid:.4f} AU from {arc:.2f}-day arc (quality {quality}) — "
            "arc is long enough to give a credible MOID estimate."
        ),
        details={"moid_au": moid, "arc_days": arc, "quality_code": quality},
    )


def _challenge_motion_consistency(neo: ScoredNEO) -> ChallengeResult:
    """Reject candidates with inconsistent apparent motion across observations.

    A real solar system body moves at a predictable, smooth rate following a
    great circle on the sky (to first order).  Low motion_consistency_score
    indicates that the individual positions do not fit a linear trajectory —
    more consistent with a random-walk artifact or matching error.
    """
    mc = neo.features.motion_consistency_score
    if mc is None:
        return ChallengeResult(
            name="motion_consistency",
            outcome="WARNING",
            reason="motion_consistency_score is None — could not be computed.",
            details={"motion_consistency_score": mc},
        )
    if mc < 0.40:
        return ChallengeResult(
            name="motion_consistency",
            outcome="FAIL",
            reason=(
                f"motion_consistency_score {mc:.3f} < 0.40 — "
                "observations do not follow a consistent great-circle trajectory."
            ),
            details={"motion_consistency_score": mc},
        )
    if mc < 0.60:
        return ChallengeResult(
            name="motion_consistency",
            outcome="WARNING",
            reason=(
                f"motion_consistency_score {mc:.3f} < 0.60 — "
                "trajectory consistency is marginal."
            ),
            details={"motion_consistency_score": mc},
        )
    return ChallengeResult(
        name="motion_consistency",
        outcome="PASS",
        reason=f"motion_consistency_score {mc:.3f} ≥ 0.60.",
        details={"motion_consistency_score": mc},
    )


# ---------------------------------------------------------------------------
# Live challenges (run unless --offline is specified; gracefully degrade)
# ---------------------------------------------------------------------------


def _challenge_mpc_field_scan(neo: ScoredNEO) -> ChallengeResult:
    """Query MPC for known objects in the candidate's sky field.

    If known solar system objects are present near the candidate's centroid,
    the candidate may simply be one of them.  Complements the ML known_object
    posterior with a direct catalog lookup.

    Requires network access; returns SKIP if unavailable.
    """
    # Compute centroid from tracklet observations
    obs_list = list(neo.tracklet.observations)
    if not obs_list:
        return ChallengeResult(
            name="mpc_field_scan",
            outcome="SKIP",
            reason="No observations in tracklet — cannot compute centroid for MPC query.",
            details={},
        )

    ra_c = sum(o.ra_deg for o in obs_list) / len(obs_list)
    dec_c = sum(o.dec_deg for o in obs_list) / len(obs_list)

    try:
        from fetch import count_known_objects_in_field
        n_known = count_known_objects_in_field(ra_c, dec_c, _LIVE_FIELD_RADIUS_DEG)
    except Exception as exc:
        return ChallengeResult(
            name="mpc_field_scan",
            outcome="SKIP",
            reason=f"MPC field scan failed (network issue?): {exc}",
            details={"error": str(exc), "ra_deg": ra_c, "dec_deg": dec_c},
        )

    if n_known > 10:
        return ChallengeResult(
            name="mpc_field_scan",
            outcome="FAIL",
            reason=(
                f"MPC catalog reports {n_known} known objects within "
                f"{_LIVE_FIELD_RADIUS_DEG}° of candidate — dense known-object field; "
                "candidate association with known object is highly likely."
            ),
            details={"n_known_in_field": n_known, "radius_deg": _LIVE_FIELD_RADIUS_DEG},
        )
    if n_known > 0:
        return ChallengeResult(
            name="mpc_field_scan",
            outcome="WARNING",
            reason=(
                f"MPC catalog reports {n_known} known object(s) within "
                f"{_LIVE_FIELD_RADIUS_DEG}° — manual cross-match recommended."
            ),
            details={"n_known_in_field": n_known, "radius_deg": _LIVE_FIELD_RADIUS_DEG},
        )

    return ChallengeResult(
        name="mpc_field_scan",
        outcome="PASS",
        reason=(
            f"No known MPC objects found within {_LIVE_FIELD_RADIUS_DEG}° "
            f"of candidate centroid (RA={ra_c:.4f}, Dec={dec_c:.4f})."
        ),
        details={"n_known_in_field": 0, "ra_deg": ra_c, "dec_deg": dec_c},
    )


def _challenge_cross_survey_confirmation(
    neo: ScoredNEO,
    atlas_token: str | None,
) -> ChallengeResult:
    """Seek independent confirmation from a second survey.

    If the candidate was found by ZTF, check whether ATLAS also detected
    it at the same sky position during the observation window.  Independent
    detection by a separate instrument is strong evidence against an
    instrument-specific artifact.

    A PASS here does not guarantee the candidate is real, but a FAIL or SKIP
    without any alternative confirmation is a concern.

    Requires ATLAS token; returns SKIP if unavailable.
    """
    # Determine which survey found the candidate
    missions = {o.mission for o in neo.tracklet.observations}
    has_ztf = "ZTF" in missions
    has_atlas = "ATLAS" in missions

    # If already multi-survey, cross-confirmation already exists
    if has_ztf and has_atlas:
        return ChallengeResult(
            name="cross_survey_confirmation",
            outcome="PASS",
            reason="Candidate already has observations from multiple surveys (ZTF + ATLAS).",
            details={"missions": sorted(missions)},
        )

    # Need ATLAS token for live cross-check
    if not has_ztf:
        return ChallengeResult(
            name="cross_survey_confirmation",
            outcome="SKIP",
            reason=(
                f"Candidate missions: {sorted(missions)}. "
                "Cross-survey check currently implemented for ZTF-origin candidates only."
            ),
            details={"missions": sorted(missions)},
        )

    if not atlas_token:
        return ChallengeResult(
            name="cross_survey_confirmation",
            outcome="SKIP",
            reason=(
                "No ATLAS token provided — cannot query ATLAS for cross-survey confirmation. "
                "Provide --atlas-token or set ATLAS_TOKEN env variable."
            ),
            details={"missions": sorted(missions)},
        )

    # Build query parameters from tracklet
    obs_list = sorted(neo.tracklet.observations, key=lambda o: o.jd)
    ra_c = sum(o.ra_deg for o in obs_list) / len(obs_list)
    dec_c = sum(o.dec_deg for o in obs_list) / len(obs_list)
    start_jd = obs_list[0].jd - 1.0   # 1-day buffer before first observation
    end_jd = obs_list[-1].jd + 1.0    # 1-day buffer after last observation

    try:
        from fetch import fetch_atlas_forced
        atlas_obs = fetch_atlas_forced(
            ra_deg=ra_c,
            dec_deg=dec_c,
            start_jd=start_jd,
            end_jd=end_jd,
            atlas_token=atlas_token,
            force_refresh=False,
        )
    except Exception as exc:
        return ChallengeResult(
            name="cross_survey_confirmation",
            outcome="SKIP",
            reason=f"ATLAS query failed: {exc}",
            details={"error": str(exc)},
        )

    n_atlas = len(atlas_obs)
    if n_atlas >= _ATLAS_MIN_DETECTIONS:
        return ChallengeResult(
            name="cross_survey_confirmation",
            outcome="PASS",
            reason=(
                f"ATLAS independently detected {n_atlas} data point(s) near "
                f"candidate position — cross-survey confirmation obtained."
            ),
            details={
                "n_atlas_detections": n_atlas,
                "ra_deg": ra_c,
                "dec_deg": dec_c,
            },
        )

    return ChallengeResult(
        name="cross_survey_confirmation",
        outcome="WARNING",
        reason=(
            f"ATLAS returned 0 detections near candidate position "
            f"(RA={ra_c:.4f}, Dec={dec_c:.4f}, JD {start_jd:.1f}–{end_jd:.1f}). "
            "Lack of independent confirmation is a concern but not a disqualification "
            "(ATLAS may not cover this field at this epoch)."
        ),
        details={"n_atlas_detections": 0, "ra_deg": ra_c, "dec_deg": dec_c},
    )


# ---------------------------------------------------------------------------
# Aggregate review runner
# ---------------------------------------------------------------------------


def run_adversarial_review(
    neo: ScoredNEO,
    *,
    offline: bool = False,
    atlas_token: str | None = None,
) -> ReviewVerdict:
    """Run the full adversarial challenge battery on one scored NEO.

    Parameters
    ----------
    neo:
        The ScoredNEO to review.
    offline:
        If True, skip all challenges that require network access.
    atlas_token:
        Optional ATLAS forced-photometry API token for cross-survey checks.

    Returns
    -------
    ReviewVerdict
        Verdict is REJECT (any FAIL), BORDERLINE (≥2 WARNINGs), or SURVIVE.
    """
    # --- Offline challenges (always run) ---
    challenges: list[ChallengeResult] = [
        _challenge_orbit_quality(neo),
        _challenge_arc_length(neo),
        _challenge_multi_night(neo),
        _challenge_real_bogus(neo),
        _challenge_known_object_posterior(neo),
        _challenge_artifact_posterior(neo),
        _challenge_neo_posterior_dominance(neo),
        _challenge_mba_confusion(neo),
        _challenge_motion_rate(neo),
        _challenge_moid_arc_consistency(neo),
        _challenge_motion_consistency(neo),
    ]

    # --- Live challenges (skipped when --offline) ---
    if not offline:
        challenges.append(_challenge_mpc_field_scan(neo))
        challenges.append(_challenge_cross_survey_confirmation(neo, atlas_token))

    # --- Aggregate counts ---
    fail_count = sum(1 for c in challenges if c.outcome == "FAIL")
    warn_count = sum(1 for c in challenges if c.outcome == "WARNING")

    # --- Determine verdict (REJECT supersedes everything) ---
    if fail_count > 0:
        verdict: Verdict = "REJECT"
        fail_names = [c.name for c in challenges if c.outcome == "FAIL"]
        summary = (
            f"REJECTED: {fail_count} disqualifying challenge(s) failed — "
            f"{fail_names}. Do not advance to operator review."
        )
    elif warn_count >= 2:
        verdict = "BORDERLINE"
        warn_names = [c.name for c in challenges if c.outcome == "WARNING"]
        summary = (
            f"BORDERLINE: {warn_count} warning(s) — {warn_names}. "
            "Requires careful operator scrutiny before any external submission."
        )
    else:
        verdict = "SURVIVE"
        if warn_count == 0:
            summary = "SURVIVE: All challenges passed — candidate may advance to operator review."
        else:
            warn_names = [c.name for c in challenges if c.outcome == "WARNING"]
            summary = (
                f"SURVIVE: {warn_count} minor warning ({warn_names}) but no disqualifying flaw — "
                "candidate may advance to operator review with the noted caveat."
            )

    return ReviewVerdict(
        object_id=neo.tracklet.object_id,
        verdict=verdict,
        challenges=challenges,
        fail_count=fail_count,
        warning_count=warn_count,
        summary=summary,
        reviewed_at_utc=datetime.now(UTC).isoformat(),
    )


def review_unparseable_candidate(
    item: object,
    index: int,
    error: Exception,
) -> ReviewVerdict:
    """Return a fail-closed verdict for compact or malformed review packets."""
    object_id = f"item_{index}"
    keys: list[str] = []
    if isinstance(item, dict):
        object_id = str(item.get("object_id") or object_id)
        keys = sorted(str(k) for k in item)

    challenge = ChallengeResult(
        name="review_packet_schema",
        outcome="FAIL",
        reason=(
            "Input is not a full ScoredNEO review packet; adversarial review "
            "cannot verify tracklet, feature, posterior, hazard, and metadata evidence."
        ),
        details={
            "item_index": index,
            "object_id": object_id,
            "available_keys": keys,
            "parse_error": str(error),
        },
    )
    return ReviewVerdict(
        object_id=object_id,
        verdict="REJECT",
        challenges=[challenge],
        fail_count=1,
        warning_count=0,
        summary=(
            "REJECTED: candidate packet is incomplete for adversarial review. "
            "Run or export a full ScoredNEO evidence packet before operator review."
        ),
        reviewed_at_utc=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_verdict(verdict: ReviewVerdict, as_json: bool) -> None:
    """Print a single review verdict — JSON or human-readable table."""
    if as_json:
        print(json.dumps(verdict.to_dict(), indent=2), flush=True)
        return

    # Human-readable format
    sep = "─" * 72
    icon = {"SURVIVE": "✓", "BORDERLINE": "⚠", "REJECT": "✗"}.get(verdict.verdict, "?")
    print(sep, flush=True)
    print(
        f"  {icon}  {verdict.verdict}  ·  {verdict.object_id}  "
        f"(FAIL={verdict.fail_count}  WARN={verdict.warning_count})",
        flush=True,
    )
    print(sep, flush=True)
    for ch in verdict.challenges:
        icon_ch = {"PASS": " ✓", "WARNING": " ⚠", "FAIL": "✗✗", "SKIP": " –"}.get(
            ch.outcome, "  "
        )
        print(f"  [{icon_ch}] {ch.name:30s}  {ch.reason}", flush=True)
    print(flush=True)
    print(f"  Summary: {verdict.summary}", flush=True)
    print(sep, flush=True)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the adversarial review CLI.

    Returns 0 if all candidates SURVIVE, 1 if any REJECT, 2 if any BORDERLINE
    (but no REJECT), so the caller can take action based on exit code.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Adversarial review of scored NEO candidates — "
            "tries to find disqualifying flaws before operator review."
        )
    )
    parser.add_argument(
        "input",
        help="Path to JSON file containing a ScoredNEO or list of ScoredNEOs.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip all live network challenges (MPC scan, ATLAS cross-survey).",
    )
    parser.add_argument(
        "--atlas-token",
        default=None,
        metavar="TOKEN",
        help=(
            "ATLAS forced-photometry API token for cross-survey confirmation. "
            "Falls back to ATLAS_TOKEN environment variable if not provided."
        ),
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output results as a JSON array.",
    )
    args = parser.parse_args(argv)

    # Resolve ATLAS token from env if not provided on CLI
    import os
    atlas_token: str | None = args.atlas_token or os.environ.get("ATLAS_TOKEN")

    # Load input JSON
    try:
        with open(args.input) as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"ERROR: could not read {args.input}: {exc}", file=sys.stderr)
        return 1

    if isinstance(data, dict):
        data = [data]

    # Parse ScoredNEO objects. Compact pipeline summary rows fail closed as
    # structured REJECT verdicts instead of being silently skipped.
    neos: list[ScoredNEO] = []
    malformed_verdicts: list[ReviewVerdict] = []
    for i, item in enumerate(data):
        try:
            neos.append(ScoredNEO(**item))
        except Exception as exc:
            print(
                f"WARNING: item {i} is not a full ScoredNEO review packet; "
                "recording fail-closed REJECT verdict.",
                file=sys.stderr,
            )
            malformed_verdicts.append(review_unparseable_candidate(item, i, exc))

    if not neos and not malformed_verdicts:
        print("ERROR: no valid ScoredNEO entries found in input.", file=sys.stderr)
        return 1

    # Run adversarial review on each candidate
    verdicts: list[ReviewVerdict] = list(malformed_verdicts)
    for neo in neos:
        v = run_adversarial_review(neo, offline=args.offline, atlas_token=atlas_token)
        verdicts.append(v)
        if not args.as_json:
            _print_verdict(v, as_json=False)

    # JSON bulk output
    if args.as_json:
        print(json.dumps([v.to_dict() for v in verdicts], indent=2), flush=True)

    # Summary statistics when reviewing multiple candidates
    if len(verdicts) > 1 and not args.as_json:
        n_survive = sum(1 for v in verdicts if v.verdict == "SURVIVE")
        n_border = sum(1 for v in verdicts if v.verdict == "BORDERLINE")
        n_reject = sum(1 for v in verdicts if v.verdict == "REJECT")
        print(
            f"\nSummary: {len(verdicts)} candidates reviewed — "
            f"SURVIVE={n_survive}  BORDERLINE={n_border}  REJECT={n_reject}",
            flush=True,
        )

    # Exit codes: 0=all survive, 1=any reject, 2=borderline-only
    if any(v.verdict == "REJECT" for v in verdicts):
        return 1
    if any(v.verdict == "BORDERLINE" for v in verdicts):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
