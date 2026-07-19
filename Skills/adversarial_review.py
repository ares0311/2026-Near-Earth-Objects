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

"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# Allow running directly as a script or via PYTHONPATH=src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from known_object_exclusion import known_at_observation_jd
from schemas import Observation, ScoredNEO

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
_PSF_SHAPE_GATE = 0.50  # source-native correlation gate; not a probability

# Epoch-specific known-object association policy. Ten arcseconds is wider than
# the detector's 5-arcsecond match radius while remaining an association test,
# not a scientifically invalid field-density proxy.
_KNOWN_OBJECT_POLICY_VERSION = "skybot-mpc-first-observation-v1"
_KNOWN_OBJECT_RADIUS_ARCSEC = 10.0
_KNOWN_OBJECT_OBSERVER_CODE = "500"

# ATLAS documents that moving-object forced photometry needs predicted positions
# accurate to about one pixel (2 arcsec). A 5-sigma magnitude measurement has
# dm <= 1.0857 / 5 under the standard magnitude-error approximation.
_ATLAS_ASSOCIATION_POLICY_VERSION = "linked-tracklet-kinematics-v1"
_ATLAS_MAX_RESIDUAL_ARCSEC = 2.0
_ATLAS_MIN_SNR = 5.0
_MAG_ERROR_TO_SNR = 1.0857362047581296
_ATLAS_SENTINEL_MAG = 90.0

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
        arc_tier = neo.hazard.arc_quality_tier
        fit_status = neo.hazard.orbit_fit_status
        return ChallengeResult(
            name="orbit_quality",
            outcome="FAIL",
            reason=(
                "No orbital elements computed — orbit fit status "
                f"{fit_status}; observational arc tier {arc_tier}."
            ),
            details={
                "solution_quality_code": None,
                "arc_quality_tier": arc_tier,
                "orbit_fit_status": fit_status,
            },
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
    if rb is None:
        psf_values = [
            o.psf_shape_correlation
            for o in neo.tracklet.observations
            if o.psf_shape_correlation is not None
        ]
        n_obs = len(neo.tracklet.observations)
        if len(psf_values) != n_obs:
            return ChallengeResult(
                name="real_bogus",
                outcome="FAIL",
                reason=(
                    "No calibrated real/bogus score and incomplete source-native "
                    f"PSF-shape coverage ({len(psf_values)}/{n_obs}) — fails closed."
                ),
                details={
                    "real_bogus_score": None,
                    "psf_shape_scored": len(psf_values),
                    "n_observations": n_obs,
                    "psf_shape_gate": _PSF_SHAPE_GATE,
                },
            )
        minimum_psf_shape = min(psf_values)
        psf_quality = neo.features.psf_quality_score
        if psf_quality is None or minimum_psf_shape < _PSF_SHAPE_GATE:
            return ChallengeResult(
                name="real_bogus",
                outcome="FAIL",
                reason=(
                    "No calibrated real/bogus score; at least one source-native "
                    f"PSF-shape correlation ({minimum_psf_shape:.3f}) is below "
                    f"{_PSF_SHAPE_GATE}."
                ),
                details={
                    "real_bogus_score": None,
                    "psf_quality_score": psf_quality,
                    "minimum_psf_shape_correlation": minimum_psf_shape,
                    "psf_shape_gate": _PSF_SHAPE_GATE,
                    "quality_signal": "psf_shape_correlation",
                },
            )
        return ChallengeResult(
            name="real_bogus",
            outcome="WARNING",
            reason=(
                "No calibrated real/bogus probability; all observations pass the "
                f"source-native PSF-shape gate ({psf_quality:.3f}). Manual review required."
            ),
            details={
                "real_bogus_score": None,
                "psf_quality_score": psf_quality,
                "minimum_psf_shape_correlation": minimum_psf_shape,
                "psf_shape_gate": _PSF_SHAPE_GATE,
                "quality_signal": "psf_shape_correlation",
            },
        )
    if rb < _RB_GATE:
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
# Live challenges (run unless --offline is specified)
# ---------------------------------------------------------------------------


def _scalar(value: object) -> float:
    """Return a float from an Astropy scalar or a plain numeric value."""
    if hasattr(value, "value"):
        value = value.value
    return float(value)


def _skybot_designation(row: object) -> str:
    """Prefer a numbered designation, falling back to the SkyBoT name."""
    for key in ("Number", "Name"):
        try:
            value = row[key]  # type: ignore[index]
        except (KeyError, TypeError, IndexError):
            continue
        if value is None or getattr(value, "mask", False):
            continue
        text = str(value).strip()
        if text and text not in {"--", "nan"}:
            return text.lstrip("0") or "0"
    raise ValueError("SkyBoT match has no MPC-compatible designation")


def _query_skybot_at_epoch(observation: Observation) -> list[dict]:
    """Return normalized SkyBoT associations for one measured position/time."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.time import Time
    from astroquery.imcce import Skybot  # type: ignore[import]

    field = SkyCoord(observation.ra_deg * u.deg, observation.dec_deg * u.deg)
    rows = Skybot.cone_search(
        field,
        _KNOWN_OBJECT_RADIUS_ARCSEC * u.arcsec,
        Time(observation.jd, format="jd"),
        location=_KNOWN_OBJECT_OBSERVER_CODE,
        cache=False,
    )
    return _normalize_skybot_rows(observation, rows)


def _normalize_skybot_rows(observation: Observation, rows: object) -> list[dict]:
    """Normalize the documented Number/Name/RA/DEC SkyBoT result schema."""
    matches: list[dict] = []
    for row in rows:
        ra_deg = _scalar(row["RA"])
        dec_deg = _scalar(row["DEC"])
        separation = _angular_separation_arcsec(
            observation.ra_deg,
            observation.dec_deg,
            ra_deg,
            dec_deg,
        )
        matches.append(
            {
                "designation": _skybot_designation(row),
                "ephemeris_ra_deg": ra_deg,
                "ephemeris_dec_deg": dec_deg,
                "separation_arcsec": separation,
            }
        )
    return matches


def _query_mpc_first_observation_jd(designation: str) -> float:
    """Return the earliest published MPC observation, failing on no evidence."""
    from fetch import fetch_mpc_observations

    observations = fetch_mpc_observations(designation, raise_on_error=True)
    if not observations:
        raise RuntimeError(f"MPC returned no published observation history for {designation}")
    return min(observation.jd for observation in observations)


def _challenge_known_object_epoch_association(
    neo: ScoredNEO,
    *,
    skybot_query=None,
    first_observation_query=None,
) -> ChallengeResult:
    """Cross-match at each measured epoch and reject only objects known then.

    SkyBoT supplies the predicted position at the historical observation epoch.
    MPC published history supplies the earliest observation date. This prevents
    a current catalog from rejecting a candidate solely because the object was
    discovered later. Provider or provenance failure is a disqualifying FAIL,
    never a passing zero count.
    """
    observations = sorted(neo.tracklet.observations, key=lambda observation: observation.jd)
    policy_input = {
        "object_id": neo.tracklet.object_id,
        "policy_version": _KNOWN_OBJECT_POLICY_VERSION,
        "radius_arcsec": _KNOWN_OBJECT_RADIUS_ARCSEC,
        "observer_code": _KNOWN_OBJECT_OBSERVER_CODE,
        "observations": [
            {
                "obs_id": observation.obs_id,
                "ra_deg": observation.ra_deg,
                "dec_deg": observation.dec_deg,
                "jd": observation.jd,
            }
            for observation in observations
        ],
    }
    input_sha256 = hashlib.sha256(
        json.dumps(policy_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    common = {
        "policy_version": _KNOWN_OBJECT_POLICY_VERSION,
        "policy_input_sha256": input_sha256,
        "radius_arcsec": _KNOWN_OBJECT_RADIUS_ARCSEC,
        "observer_code": _KNOWN_OBJECT_OBSERVER_CODE,
    }
    if not observations:
        return ChallengeResult(
            name="known_object_epoch_association",
            outcome="FAIL",
            reason="No observations are available for time-aware known-object association.",
            details=common,
        )

    skybot_query = skybot_query or _query_skybot_at_epoch
    first_observation_query = first_observation_query or _query_mpc_first_observation_jd
    associations: list[dict] = []
    try:
        for observation in observations:
            matches = skybot_query(observation)
            if not isinstance(matches, list):
                raise TypeError("SkyBoT provider result must be a list")
            for match in matches:
                designation = str(match["designation"]).strip()
                separation = float(match["separation_arcsec"])
                if not designation or not math.isfinite(separation):
                    raise ValueError("SkyBoT association is missing valid identity/separation")
                if separation > _KNOWN_OBJECT_RADIUS_ARCSEC:
                    continue
                associations.append(
                    {
                        "designation": designation,
                        "observation_id": observation.obs_id,
                        "observation_jd": observation.jd,
                        "separation_arcsec": separation,
                    }
                )
        first_observation_by_designation = {
            designation: float(first_observation_query(designation))
            for designation in sorted({row["designation"] for row in associations})
        }
        if any(not math.isfinite(jd) for jd in first_observation_by_designation.values()):
            raise ValueError("MPC first-observation provider returned a non-finite JD")
    except Exception as exc:
        return ChallengeResult(
            name="known_object_epoch_association",
            outcome="FAIL",
            reason=f"Time-aware known-object association could not be verified: {exc}",
            details={**common, "error_type": type(exc).__name__, "error": str(exc)},
        )

    if not associations:
        return ChallengeResult(
            name="known_object_epoch_association",
            outcome="PASS",
            reason="No SkyBoT object is positionally associated at any measured epoch.",
            details={**common, "associations": []},
        )

    evidence = [
        {
            **association,
            "first_observation_jd": first_observation_by_designation[
                association["designation"]
            ],
            "known_at_observation": known_at_observation_jd(
                first_observation_by_designation[association["designation"]],
                association["observation_jd"],
            ),
        }
        for association in associations
    ]
    known_then = [row for row in evidence if row["known_at_observation"]]
    if known_then:
        designations = sorted({row["designation"] for row in known_then})
        return ChallengeResult(
            name="known_object_epoch_association",
            outcome="FAIL",
            reason=(
                "Epoch-specific position and published first-observation history "
                f"associate the tracklet with object(s) {designations} already known then."
            ),
            details={**common, "associations": evidence, "known_designations": designations},
        )
    return ChallengeResult(
        name="known_object_epoch_association",
        outcome="WARNING",
        reason=(
            "A current-catalog object matches the historical positions but its "
            "published first observation is later; retained as retrospective context "
            "without future-catalog rejection."
        ),
        details={**common, "associations": evidence, "known_designations": []},
    )


def _angular_separation_arcsec(
    ra1_deg: float,
    dec1_deg: float,
    ra2_deg: float,
    dec2_deg: float,
) -> float:
    """Return stable great-circle separation in arcseconds."""
    cos_sep = (
        math.sin(math.radians(dec1_deg)) * math.sin(math.radians(dec2_deg))
        + math.cos(math.radians(dec1_deg))
        * math.cos(math.radians(dec2_deg))
        * math.cos(math.radians(ra1_deg - ra2_deg))
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep)))) * 3600.0


def _atlas_association_evidence(neo: ScoredNEO, observation: Observation) -> dict:
    """Validate one ATLAS row against the linked tracklet's kinematics."""
    ztf_observations = sorted(
        (row for row in neo.tracklet.observations if row.mission == "ZTF"),
        key=lambda row: row.jd,
    )
    if not ztf_observations:
        raise ValueError("no ZTF reference observation exists")
    values = (
        observation.ra_deg,
        observation.dec_deg,
        observation.jd,
        observation.mag,
        observation.mag_err,
        neo.tracklet.motion_rate_arcsec_per_hour,
        neo.tracklet.motion_pa_degrees,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("association contains non-finite values")
    if observation.mag >= _ATLAS_SENTINEL_MAG:
        raise ValueError("ATLAS magnitude is a non-detection sentinel")
    if observation.mag_err <= 0.0:
        raise ValueError("ATLAS magnitude uncertainty must be positive")
    snr = _MAG_ERROR_TO_SNR / observation.mag_err
    if snr < _ATLAS_MIN_SNR:
        raise ValueError(f"ATLAS measurement S/N {snr:.3f} is below {_ATLAS_MIN_SNR:.1f}")

    reference = ztf_observations[0]
    elapsed_hours = (observation.jd - reference.jd) * 24.0
    pa_radians = math.radians(neo.tracklet.motion_pa_degrees)
    east_arcsec = neo.tracklet.motion_rate_arcsec_per_hour * math.sin(pa_radians) * elapsed_hours
    north_arcsec = neo.tracklet.motion_rate_arcsec_per_hour * math.cos(pa_radians) * elapsed_hours
    cos_dec = math.cos(math.radians(reference.dec_deg))
    if abs(cos_dec) < 1e-12:
        raise ValueError("tracklet is too close to a celestial pole for tangent-plane replay")
    predicted_ra = (reference.ra_deg + east_arcsec / (3600.0 * cos_dec)) % 360.0
    predicted_dec = reference.dec_deg + north_arcsec / 3600.0
    if not -90.0 <= predicted_dec <= 90.0:
        raise ValueError("kinematic replay predicted an invalid declination")
    residual = _angular_separation_arcsec(
        predicted_ra,
        predicted_dec,
        observation.ra_deg,
        observation.dec_deg,
    )
    if residual > _ATLAS_MAX_RESIDUAL_ARCSEC:
        raise ValueError(
            f"ATLAS residual {residual:.3f} arcsec exceeds "
            f"{_ATLAS_MAX_RESIDUAL_ARCSEC:.1f} arcsec"
        )
    return {
        "obs_id": observation.obs_id,
        "jd": observation.jd,
        "ra_deg": observation.ra_deg,
        "dec_deg": observation.dec_deg,
        "predicted_ra_deg": predicted_ra,
        "predicted_dec_deg": predicted_dec,
        "residual_arcsec": residual,
        "mag": observation.mag,
        "mag_err": observation.mag_err,
        "estimated_snr": snr,
    }


def _challenge_cross_survey_confirmation(neo: ScoredNEO) -> ChallengeResult:
    """Seek independent confirmation from a second survey.

    Only linked ATLAS observations can confirm a moving candidate here. The
    fixed-coordinate forced-photometry endpoint cannot establish a moving-
    object association without a sufficiently precise ephemeris, so this
    challenge never upgrades a candidate from arbitrary live query rows.
    """
    # Determine which survey found the candidate
    missions = {o.mission for o in neo.tracklet.observations}
    has_ztf = "ZTF" in missions
    has_atlas = "ATLAS" in missions

    common = {
        "policy_version": _ATLAS_ASSOCIATION_POLICY_VERSION,
        "missions": sorted(missions),
        "max_residual_arcsec": _ATLAS_MAX_RESIDUAL_ARCSEC,
        "min_snr": _ATLAS_MIN_SNR,
    }

    # Validate linked multi-survey evidence rather than trusting its label.
    if has_ztf and has_atlas:
        evidence: list[dict] = []
        errors: list[dict] = []
        seen: set[tuple[str, float, float, float]] = set()
        for observation in neo.tracklet.observations:
            if observation.mission != "ATLAS":
                continue
            identity = (
                observation.obs_id,
                observation.jd,
                observation.ra_deg,
                observation.dec_deg,
            )
            if identity in seen:
                errors.append({"obs_id": observation.obs_id, "error": "duplicate ATLAS row"})
                continue
            seen.add(identity)
            try:
                evidence.append(_atlas_association_evidence(neo, observation))
            except ValueError as exc:
                errors.append({"obs_id": observation.obs_id, "error": str(exc)})
        if not evidence or errors:
            return ChallengeResult(
                name="cross_survey_confirmation",
                outcome="FAIL",
                reason=(
                    "Claimed ZTF + ATLAS evidence failed kinematic or measurement-quality "
                    "validation; it is not independent confirmation."
                ),
                details={**common, "validated_associations": evidence, "errors": errors},
            )
        return ChallengeResult(
            name="cross_survey_confirmation",
            outcome="PASS",
            reason="Linked ATLAS observation(s) independently match the ZTF tracklet kinematics.",
            details={**common, "validated_associations": evidence, "errors": []},
        )

    if not has_ztf:
        return ChallengeResult(
            name="cross_survey_confirmation",
            outcome="SKIP",
            reason=(
                f"Candidate missions: {sorted(missions)}. "
                "Cross-survey check currently implemented for ZTF-origin candidates only."
            ),
            details=common,
        )

    return ChallengeResult(
        name="cross_survey_confirmation",
        outcome="SKIP",
        reason=(
            "No linked ATLAS observation is present. Fixed-coordinate forced photometry "
            "is not treated as moving-object confirmation without a precise ephemeris."
        ),
        details=common,
    )


# ---------------------------------------------------------------------------
# Aggregate review runner
# ---------------------------------------------------------------------------


def run_adversarial_review(
    neo: ScoredNEO,
    *,
    offline: bool = False,
    skybot_query=None,
    first_observation_query=None,
) -> ReviewVerdict:
    """Run the full adversarial challenge battery on one scored NEO.

    Parameters
    ----------
    neo:
        The ScoredNEO to review.
    offline:
        If True, skip all challenges that require network access.
    skybot_query / first_observation_query:
        Optional injected providers for cached/offline verified association
        evidence and behavioral tests.

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

    # Known-object association is required eligibility evidence. Offline mode
    # may use explicit cached providers; it may not silently omit this stage.
    if not offline or skybot_query is not None:
        challenges.append(
            _challenge_known_object_epoch_association(
                neo,
                skybot_query=skybot_query,
                first_observation_query=first_observation_query,
            )
        )
    else:
        challenges.append(
            ChallengeResult(
                name="known_object_epoch_association",
                outcome="FAIL",
                reason=(
                    "Offline review has no cached epoch-specific known-object "
                    "association evidence; required eligibility cannot be verified."
                ),
                details={"policy_version": _KNOWN_OBJECT_POLICY_VERSION, "offline": True},
            )
        )

    # Cross-survey confirmation remains an optional live enrichment.
    if not offline:
        challenges.append(_challenge_cross_survey_confirmation(neo))

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
        help=(
            "Skip live network challenges (epoch-specific SkyBoT/MPC association "
            "and ATLAS cross-survey confirmation)."
        ),
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output results as a JSON array.",
    )
    args = parser.parse_args(argv)

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
        v = run_adversarial_review(neo, offline=args.offline)
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
