"""Tests for Skills/adversarial_review.py.

Covers every offline challenge (PASS/WARNING/FAIL branches), the live
challenges via monkeypatch, the aggregate verdict logic, and the CLI
entry point.  All tests run fully offline — no network access is required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure both src/ and Skills/ are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

# Import the module under test
from adversarial_review import (
    _challenge_arc_length,
    _challenge_artifact_posterior,
    _challenge_cross_survey_confirmation,
    _challenge_known_object_epoch_association,
    _challenge_known_object_posterior,
    _challenge_mba_confusion,
    _challenge_moid_arc_consistency,
    _challenge_motion_consistency,
    _challenge_motion_rate,
    _challenge_multi_night,
    _challenge_neo_posterior_dominance,
    _challenge_orbit_quality,
    _challenge_real_bogus,
    _normalize_skybot_rows,
    main,
    run_adversarial_review,
)

from schemas import (
    CandidateExplanation,
    CandidateFeatures,
    HazardAssessment,
    NEOPosterior,
    Observation,
    OrbitalElements,
    ScoredNEO,
    ScoringMetadata,
    Tracklet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _obs(obs_id: str, jd: float, ra_deg: float = 180.0) -> Observation:
    """Build a minimal Observation for testing."""
    return Observation(
        obs_id=obs_id,
        ra_deg=ra_deg,
        dec_deg=10.0,
        jd=jd,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.95,
    )


def _elements(quality: int = 2, moid: float = 0.03) -> OrbitalElements:
    """Build OrbitalElements with a given quality code."""
    return OrbitalElements(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=quality,
    )


def _make_neo(
    arc_days: float = 3.0,
    n_nights: int = 3,
    rb: float | None = 0.95,
    neo_p: float = 0.75,
    known_p: float = 0.05,
    mba_p: float = 0.10,
    art_p: float = 0.05,
    other_p: float = 0.05,
    rate: float = 5.0,
    moid_au: float = 0.03,
    orbit_quality: int = 2,
    motion_consistency: float | None = 0.85,
    mission: str = "ZTF",
    psf_correlations: tuple[float | None, ...] | None = None,
    psf_quality: float | None = None,
) -> ScoredNEO:
    """Build a configurable ScoredNEO for challenge testing."""
    # Spread observations across distinct nights
    obs = tuple(
        Observation(
            obs_id=f"o_{i}",
            ra_deg=180.0 + i * 0.005,
            dec_deg=10.0,
            jd=2460000.5 + i,          # 1 obs per night
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission=mission,            # type: ignore[arg-type]
            real_bogus=0.95 if rb is not None else None,
            psf_shape_correlation=(
                psf_correlations[i] if psf_correlations is not None else None
            ),
        )
        for i in range(n_nights)
    )
    tracklet = Tracklet(
        object_id="T_TEST",
        observations=obs,
        arc_days=arc_days,
        motion_rate_arcsec_per_hour=rate,
        motion_pa_degrees=90.0,
    )
    features = CandidateFeatures(
        real_bogus_score=rb,
        psf_quality_score=psf_quality,
        motion_consistency_score=motion_consistency,
    )
    posterior = NEOPosterior(
        neo_candidate=neo_p,
        known_object=known_p,
        main_belt_asteroid=mba_p,
        stellar_artifact=art_p,
        other_solar_system=other_p,
    )
    explanation = CandidateExplanation(
        summary="Test NEO",
        supporting_evidence=(),
        contra_evidence=(),
        model_version="test",
    )
    hazard = HazardAssessment(
        hazard_flag="pha_candidate",
        moid_au=moid_au,
        estimated_diameter_m=200.0,
        absolute_magnitude_h=21.5,
        neo_class="apollo",
        alert_pathway="mpc_submission",
        explanation=explanation,
        orbital_elements=_elements(quality=orbit_quality, moid=moid_au),
    )
    metadata = ScoringMetadata(
        scorer_version="test",
        scored_at_jd=2460000.5,
        pipeline_run_id="test",
        discovery_priority=0.8,
        followup_value=0.6,
        scientific_interest=0.5,
    )
    return ScoredNEO(
        tracklet=tracklet,
        features=features,
        posterior=posterior,
        hazard=hazard,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Orbit quality challenge
# ---------------------------------------------------------------------------


class TestChallengeOrbitQuality:
    def test_pass_quality_2(self) -> None:
        neo = _make_neo(orbit_quality=2)
        r = _challenge_orbit_quality(neo)
        assert r.outcome == "PASS"

    def test_warn_quality_1(self) -> None:
        neo = _make_neo(orbit_quality=1)
        r = _challenge_orbit_quality(neo)
        assert r.outcome == "WARNING"

    def test_fail_quality_0(self) -> None:
        neo = _make_neo(orbit_quality=0)
        r = _challenge_orbit_quality(neo)
        assert r.outcome == "FAIL"

    def test_fail_no_elements(self) -> None:
        """No orbital elements → FAIL (cannot assess quality at all)."""
        neo = _make_neo()
        # Remove orbital elements via a new HazardAssessment
        from schemas import CandidateExplanation, HazardAssessment
        hazard_no_elements = HazardAssessment(
            hazard_flag="pha_candidate",
            moid_au=0.03,
            estimated_diameter_m=200.0,
            absolute_magnitude_h=21.5,
            neo_class="apollo",
            alert_pathway="mpc_submission",
            explanation=CandidateExplanation(
                summary="Test",
                supporting_evidence=(),
                contra_evidence=(),
                model_version="test",
            ),
            orbital_elements=None,  # explicitly no elements
            arc_quality_tier=2,
            orbit_fit_status="no_solution",
        )
        neo_no_el = ScoredNEO(
            tracklet=neo.tracklet,
            features=neo.features,
            posterior=neo.posterior,
            hazard=hazard_no_elements,
            metadata=neo.metadata,
        )
        r = _challenge_orbit_quality(neo_no_el)
        assert r.outcome == "FAIL"
        assert "No orbital elements" in r.reason
        assert r.details["arc_quality_tier"] == 2
        assert r.details["orbit_fit_status"] == "no_solution"


# ---------------------------------------------------------------------------
# Arc length challenge
# ---------------------------------------------------------------------------


class TestChallengeArcLength:
    def test_pass(self) -> None:
        assert _challenge_arc_length(_make_neo(arc_days=2.0)).outcome == "PASS"

    def test_warn_under_1_day(self) -> None:
        assert _challenge_arc_length(_make_neo(arc_days=0.7)).outcome == "WARNING"

    def test_fail_under_half_day(self) -> None:
        assert _challenge_arc_length(_make_neo(arc_days=0.3)).outcome == "FAIL"

    def test_exactly_one_day_passes(self) -> None:
        assert _challenge_arc_length(_make_neo(arc_days=1.0)).outcome == "PASS"


# ---------------------------------------------------------------------------
# Multi-night challenge
# ---------------------------------------------------------------------------


class TestChallengeMultiNight:
    def test_pass_three_nights(self) -> None:
        assert _challenge_multi_night(_make_neo(n_nights=3)).outcome == "PASS"

    def test_warn_two_nights(self) -> None:
        assert _challenge_multi_night(_make_neo(n_nights=2)).outcome == "WARNING"

    def test_fail_one_night(self) -> None:
        """Single-night tracklet must FAIL."""
        neo = _make_neo(n_nights=2)
        # Override observations to be on the same night
        same_night_obs = (
            Observation(
                obs_id="o_0", ra_deg=180.0, dec_deg=10.0,
                jd=2460000.5, mag=19.5, mag_err=0.05,
                filter_band="r", mission="ZTF", real_bogus=0.95,
            ),
            Observation(
                obs_id="o_1", ra_deg=180.005, dec_deg=10.0,
                jd=2460000.7,   # same integer JD → same night
                mag=19.5, mag_err=0.05,
                filter_band="r", mission="ZTF", real_bogus=0.95,
            ),
        )
        tracklet = Tracklet(
            object_id="T_SAME_NIGHT",
            observations=same_night_obs,
            arc_days=0.2,
            motion_rate_arcsec_per_hour=5.0,
            motion_pa_degrees=90.0,
        )
        neo_1night = ScoredNEO(
            tracklet=tracklet,
            features=neo.features,
            posterior=neo.posterior,
            hazard=neo.hazard,
            metadata=neo.metadata,
        )
        r = _challenge_multi_night(neo_1night)
        assert r.outcome == "FAIL"
        assert "1" in r.reason  # should mention the count


# ---------------------------------------------------------------------------
# Real/bogus challenge
# ---------------------------------------------------------------------------


class TestChallengeRealBogus:
    def test_pass_high_rb(self) -> None:
        assert _challenge_real_bogus(_make_neo(rb=0.97)).outcome == "PASS"

    def test_warn_borderline(self) -> None:
        assert _challenge_real_bogus(_make_neo(rb=0.91)).outcome == "WARNING"

    def test_fail_below_gate(self) -> None:
        assert _challenge_real_bogus(_make_neo(rb=0.85)).outcome == "FAIL"

    def test_fail_none_rb(self) -> None:
        assert _challenge_real_bogus(_make_neo(rb=None)).outcome == "FAIL"

    def test_warn_when_uncalibrated_psf_quality_fully_passes(self) -> None:
        neo = _make_neo(
            rb=None,
            psf_correlations=(0.8, 0.75, 0.7),
            psf_quality=0.75,
        )
        result = _challenge_real_bogus(neo)
        assert result.outcome == "WARNING"
        assert result.details["quality_signal"] == "psf_shape_correlation"

    def test_fail_when_psf_quality_is_low(self) -> None:
        neo = _make_neo(
            rb=None,
            psf_correlations=(0.95, 0.10, 0.95),
            psf_quality=2.0 / 3.0,
        )
        result = _challenge_real_bogus(neo)
        assert result.outcome == "FAIL"
        assert result.details["minimum_psf_shape_correlation"] == 0.10

    def test_fail_when_psf_coverage_is_incomplete(self) -> None:
        neo = _make_neo(
            rb=None,
            psf_correlations=(0.8, None, 0.7),
            psf_quality=0.75,
        )
        result = _challenge_real_bogus(neo)
        assert result.outcome == "FAIL"
        assert result.details["psf_shape_scored"] == 2


# ---------------------------------------------------------------------------
# Known-object posterior challenge
# ---------------------------------------------------------------------------


class TestChallengeKnownObject:
    def test_pass(self) -> None:
        assert _challenge_known_object_posterior(_make_neo(known_p=0.05)).outcome == "PASS"

    def test_warn(self) -> None:
        assert _challenge_known_object_posterior(_make_neo(
            neo_p=0.55, known_p=0.25, mba_p=0.10, art_p=0.05, other_p=0.05,
        )).outcome == "WARNING"

    def test_fail(self) -> None:
        assert _challenge_known_object_posterior(_make_neo(
            neo_p=0.15, known_p=0.55, mba_p=0.15, art_p=0.10, other_p=0.05,
        )).outcome == "FAIL"


# ---------------------------------------------------------------------------
# Artifact posterior challenge
# ---------------------------------------------------------------------------


class TestChallengeArtifact:
    def test_pass(self) -> None:
        assert _challenge_artifact_posterior(_make_neo(art_p=0.05)).outcome == "PASS"

    def test_warn(self) -> None:
        assert _challenge_artifact_posterior(_make_neo(
            neo_p=0.60, known_p=0.05, mba_p=0.15, art_p=0.15, other_p=0.05,
        )).outcome == "WARNING"

    def test_fail(self) -> None:
        assert _challenge_artifact_posterior(_make_neo(
            neo_p=0.40, known_p=0.05, mba_p=0.10, art_p=0.35, other_p=0.10,
        )).outcome == "FAIL"


# ---------------------------------------------------------------------------
# NEO posterior dominance challenge
# ---------------------------------------------------------------------------


class TestChallengeNeoDominance:
    def test_pass(self) -> None:
        assert _challenge_neo_posterior_dominance(_make_neo(neo_p=0.75)).outcome == "PASS"

    def test_warn(self) -> None:
        assert _challenge_neo_posterior_dominance(_make_neo(
            neo_p=0.40, known_p=0.25, mba_p=0.20, art_p=0.10, other_p=0.05,
        )).outcome == "WARNING"

    def test_fail(self) -> None:
        assert _challenge_neo_posterior_dominance(_make_neo(
            neo_p=0.20, known_p=0.40, mba_p=0.20, art_p=0.10, other_p=0.10,
        )).outcome == "FAIL"


# ---------------------------------------------------------------------------
# MBA confusion challenge
# ---------------------------------------------------------------------------


class TestChallengeMBA:
    def test_pass(self) -> None:
        assert _challenge_mba_confusion(_make_neo(mba_p=0.10)).outcome == "PASS"

    def test_warn(self) -> None:
        assert _challenge_mba_confusion(_make_neo(
            neo_p=0.55, known_p=0.05, mba_p=0.30, art_p=0.05, other_p=0.05,
        )).outcome == "WARNING"

    def test_fail(self) -> None:
        assert _challenge_mba_confusion(_make_neo(
            neo_p=0.30, known_p=0.10, mba_p=0.45, art_p=0.10, other_p=0.05,
        )).outcome == "FAIL"


# ---------------------------------------------------------------------------
# Motion rate challenge
# ---------------------------------------------------------------------------


class TestChallengeMotionRate:
    def test_pass_typical_neo(self) -> None:
        assert _challenge_motion_rate(_make_neo(rate=10.0)).outcome == "PASS"

    def test_warn_slow(self) -> None:
        assert _challenge_motion_rate(_make_neo(rate=0.20)).outcome == "WARNING"

    def test_warn_fast(self) -> None:
        assert _challenge_motion_rate(_make_neo(rate=120.0)).outcome == "WARNING"

    def test_fail_stationary(self) -> None:
        assert _challenge_motion_rate(_make_neo(rate=0.01)).outcome == "FAIL"

    def test_fail_satellite_speed(self) -> None:
        assert _challenge_motion_rate(_make_neo(rate=300.0)).outcome == "FAIL"

    def test_fail_infinite_rate(self) -> None:
        import math
        neo = _make_neo()
        tracklet = Tracklet(
            object_id="INF",
            observations=neo.tracklet.observations,
            arc_days=neo.tracklet.arc_days,
            motion_rate_arcsec_per_hour=math.inf,
            motion_pa_degrees=90.0,
        )
        neo_inf = ScoredNEO(
            tracklet=tracklet,
            features=neo.features,
            posterior=neo.posterior,
            hazard=neo.hazard,
            metadata=neo.metadata,
        )
        assert _challenge_motion_rate(neo_inf).outcome == "FAIL"


# ---------------------------------------------------------------------------
# MOID-arc consistency challenge
# ---------------------------------------------------------------------------


class TestChallengeMoidArc:
    def test_pass_good_arc(self) -> None:
        # Multi-night arc with MOID 0.03 → credible
        r = _challenge_moid_arc_consistency(_make_neo(moid_au=0.03, arc_days=2.0, orbit_quality=2))
        assert r.outcome == "PASS"

    def test_warn_short_arc_close_moid(self) -> None:
        r = _challenge_moid_arc_consistency(_make_neo(moid_au=0.03, arc_days=0.8, orbit_quality=1))
        assert r.outcome == "WARNING"

    def test_pass_large_moid_irrelevant(self) -> None:
        # MOID > 0.10 AU — check is not triggered
        r = _challenge_moid_arc_consistency(_make_neo(moid_au=0.20, arc_days=0.5, orbit_quality=1))
        assert r.outcome == "PASS"

    def test_warn_no_elements_close_moid(self) -> None:
        """quality_code=0 with MOID ≤ 0.10 AU triggers WARNING."""
        r = _challenge_moid_arc_consistency(_make_neo(moid_au=0.05, arc_days=1.5, orbit_quality=0))
        assert r.outcome == "WARNING"


# ---------------------------------------------------------------------------
# Motion consistency challenge
# ---------------------------------------------------------------------------


class TestChallengeMotionConsistency:
    def test_pass(self) -> None:
        assert _challenge_motion_consistency(_make_neo(motion_consistency=0.85)).outcome == "PASS"

    def test_warn(self) -> None:
        r = _challenge_motion_consistency(_make_neo(motion_consistency=0.50))
        assert r.outcome == "WARNING"

    def test_fail(self) -> None:
        r = _challenge_motion_consistency(_make_neo(motion_consistency=0.30))
        assert r.outcome == "FAIL"

    def test_warn_none(self) -> None:
        r = _challenge_motion_consistency(_make_neo(motion_consistency=None))
        assert r.outcome == "WARNING"


# ---------------------------------------------------------------------------
# MPC field scan (live, tested via monkeypatch)
# ---------------------------------------------------------------------------


class TestChallengeKnownObjectEpochAssociation:
    @staticmethod
    def _match(designation: str = "433", separation_arcsec: float = 1.2) -> dict:
        return {
            "designation": designation,
            "separation_arcsec": separation_arcsec,
        }

    def test_pass_when_epoch_queries_return_no_associations(self) -> None:
        result = _challenge_known_object_epoch_association(
            _make_neo(),
            skybot_query=lambda _observation: [],
            first_observation_query=lambda _designation: pytest.fail(
                "history must not be queried without a positional association"
            ),
        )

        assert result.outcome == "PASS"
        assert result.details["associations"] == []
        assert len(result.details["policy_input_sha256"]) == 64

    def test_provider_failure_fails_loudly(self) -> None:
        def unavailable(_observation):
            raise ConnectionError("SkyBoT unavailable")

        result = _challenge_known_object_epoch_association(
            _make_neo(),
            skybot_query=unavailable,
            first_observation_query=lambda _designation: 2400000.5,
        )

        assert result.outcome == "FAIL"
        assert result.details["error_type"] == "ConnectionError"
        assert "unavailable" in result.reason

    def test_object_known_on_exact_observation_epoch_fails(self) -> None:
        neo = _make_neo()
        first_jd = neo.tracklet.observations[0].jd
        result = _challenge_known_object_epoch_association(
            neo,
            skybot_query=lambda observation: (
                [self._match()] if observation.obs_id == "o_0" else []
            ),
            first_observation_query=lambda designation: (
                first_jd if designation == "433" else pytest.fail("wrong designation")
            ),
        )

        assert result.outcome == "FAIL"
        assert result.details["known_designations"] == ["433"]
        assert result.details["associations"][0]["known_at_observation"] is True

    def test_later_catalog_match_warns_without_future_leakage(self) -> None:
        neo = _make_neo()
        result = _challenge_known_object_epoch_association(
            neo,
            skybot_query=lambda observation: (
                [self._match("2026 AB1")] if observation.obs_id == "o_0" else []
            ),
            first_observation_query=lambda _designation: max(
                observation.jd for observation in neo.tracklet.observations
            )
            + 100.0,
        )

        assert result.outcome == "WARNING"
        assert result.details["known_designations"] == []
        assert result.details["associations"][0]["known_at_observation"] is False

    def test_malformed_history_result_fails_loudly(self) -> None:
        result = _challenge_known_object_epoch_association(
            _make_neo(),
            skybot_query=lambda _observation: [self._match()],
            first_observation_query=lambda _designation: float("nan"),
        )

        assert result.outcome == "FAIL"
        assert result.details["error_type"] == "ValueError"

    def test_outside_radius_is_not_an_association(self) -> None:
        result = _challenge_known_object_epoch_association(
            _make_neo(),
            skybot_query=lambda _observation: [self._match(separation_arcsec=10.1)],
            first_observation_query=lambda _designation: pytest.fail(
                "outside-radius object must not trigger history lookup"
            ),
        )

        assert result.outcome == "PASS"

    def test_policy_digest_is_reproducible(self) -> None:
        kwargs = {
            "skybot_query": lambda _observation: [],
            "first_observation_query": lambda _designation: 0.0,
        }
        first = _challenge_known_object_epoch_association(_make_neo(), **kwargs)
        second = _challenge_known_object_epoch_association(_make_neo(), **kwargs)
        assert first.details["policy_input_sha256"] == second.details["policy_input_sha256"]

    def test_documented_skybot_schema_normalizes_identity_and_position(self) -> None:
        observation = _obs("schema", 2460000.5, ra_deg=180.0)
        matches = _normalize_skybot_rows(
            observation,
            [{"Number": "00433", "Name": "Eros", "RA": 180.0, "DEC": 10.0}],
        )

        assert matches == [
            {
                "designation": "433",
                "ephemeris_ra_deg": 180.0,
                "ephemeris_dec_deg": 10.0,
                "separation_arcsec": pytest.approx(0.0, abs=0.01),
            }
        ]

    def test_skybot_name_fallback_and_malformed_identity(self) -> None:
        observation = _obs("schema", 2460000.5, ra_deg=180.0)
        matches = _normalize_skybot_rows(
            observation,
            [{"Number": "--", "Name": "2026 AB1", "RA": 180.0, "DEC": 10.0}],
        )
        assert matches[0]["designation"] == "2026 AB1"
        with pytest.raises(ValueError, match="no MPC-compatible designation"):
            _normalize_skybot_rows(
                observation,
                [{"Number": "--", "Name": "", "RA": 180.0, "DEC": 10.0}],
            )


# ---------------------------------------------------------------------------
# Cross-survey confirmation (live, tested via monkeypatch)
# ---------------------------------------------------------------------------


class TestChallengeCrossSurvey:
    def test_skip_no_token(self) -> None:
        neo = _make_neo(mission="ZTF")
        r = _challenge_cross_survey_confirmation(neo, atlas_token=None)
        assert r.outcome == "SKIP"
        assert "token" in r.reason.lower()

    def test_pass_multi_survey_already(self) -> None:
        """Candidate with both ZTF and ATLAS missions is already confirmed."""
        obs_ztf = _obs("o_ztf_0", 2460000.5)
        obs_atlas = Observation(
            obs_id="o_atlas_0", ra_deg=180.0, dec_deg=10.0,
            jd=2460001.5, mag=19.5, mag_err=0.05,
            filter_band="o", mission="ATLAS", real_bogus=None,
        )
        tracklet = Tracklet(
            object_id="MULTI",
            observations=(obs_ztf, obs_atlas),
            arc_days=1.0,
            motion_rate_arcsec_per_hour=5.0,
            motion_pa_degrees=90.0,
        )
        neo = _make_neo()
        multi_neo = ScoredNEO(
            tracklet=tracklet,
            features=neo.features,
            posterior=neo.posterior,
            hazard=neo.hazard,
            metadata=neo.metadata,
        )
        r = _challenge_cross_survey_confirmation(multi_neo, atlas_token="fake")
        assert r.outcome == "PASS"
        assert "already" in r.reason.lower()

    def test_pass_atlas_confirms(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import fetch
        monkeypatch.setattr(
            fetch, "fetch_atlas_forced",
            lambda **kw: [_obs("atlas_det", 2460000.9)],
        )
        neo = _make_neo(mission="ZTF")
        r = _challenge_cross_survey_confirmation(neo, atlas_token="fake_token")
        assert r.outcome == "PASS"
        assert "1" in r.reason  # 1 detection

    def test_warn_atlas_no_detections(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import fetch
        monkeypatch.setattr(fetch, "fetch_atlas_forced", lambda **kw: [])
        neo = _make_neo(mission="ZTF")
        r = _challenge_cross_survey_confirmation(neo, atlas_token="fake_token")
        assert r.outcome == "WARNING"

    def test_skip_atlas_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import fetch

        def _raise(**kw):
            raise ConnectionError("atlas down")

        monkeypatch.setattr(fetch, "fetch_atlas_forced", _raise)
        neo = _make_neo(mission="ZTF")
        r = _challenge_cross_survey_confirmation(neo, atlas_token="fake_token")
        assert r.outcome == "SKIP"

    def test_skip_non_ztf_mission(self) -> None:
        """Non-ZTF, non-ATLAS candidate: cross-survey check is SKIP (not implemented)."""
        neo = _make_neo(mission="CSS")
        r = _challenge_cross_survey_confirmation(neo, atlas_token="fake_token")
        assert r.outcome == "SKIP"


# ---------------------------------------------------------------------------
# Aggregate verdict logic
# ---------------------------------------------------------------------------


class TestRunAdversarialReview:
    def test_survive_clean_candidate(self) -> None:
        """A high-quality candidate should SURVIVE all offline challenges."""
        neo = _make_neo(
            arc_days=3.0,
            n_nights=3,
            rb=0.97,
            neo_p=0.80,
            known_p=0.05,
            mba_p=0.08,
            art_p=0.04,
            other_p=0.03,
            rate=5.0,
            moid_au=0.03,
            orbit_quality=2,
            motion_consistency=0.90,
        )
        v = run_adversarial_review(
            neo,
            offline=True,
            skybot_query=lambda _observation: [],
            first_observation_query=lambda _designation: pytest.fail(
                "no positional match means no history query"
            ),
        )
        assert v.verdict == "SURVIVE"
        assert v.fail_count == 0
        assert v.object_id == "T_TEST"

    def test_offline_without_cached_known_object_evidence_rejects(self) -> None:
        verdict = run_adversarial_review(_make_neo(), offline=True)
        challenge = next(
            challenge
            for challenge in verdict.challenges
            if challenge.name == "known_object_epoch_association"
        )
        assert challenge.outcome == "FAIL"
        assert verdict.verdict == "REJECT"

    def test_reject_low_rb(self) -> None:
        """rb=0.80 should FAIL the real_bogus gate → REJECT."""
        neo = _make_neo(rb=0.80)
        v = run_adversarial_review(neo, offline=True)
        assert v.verdict == "REJECT"
        assert v.fail_count >= 1

    def test_reject_single_night(self) -> None:
        """Single-night tracklet → multi_night FAIL → REJECT."""
        same_night = (
            Observation(
                obs_id="s0", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
                mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF",
            ),
            Observation(
                obs_id="s1", ra_deg=180.01, dec_deg=10.0, jd=2460000.8,
                mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF",
            ),
        )
        neo = _make_neo()
        tracklet = Tracklet(
            object_id="ONENIGHT", observations=same_night,
            arc_days=0.3, motion_rate_arcsec_per_hour=5.0, motion_pa_degrees=90.0,
        )
        neo_1n = ScoredNEO(
            tracklet=tracklet, features=neo.features,
            posterior=neo.posterior, hazard=neo.hazard, metadata=neo.metadata,
        )
        v = run_adversarial_review(neo_1n, offline=True)
        assert v.verdict == "REJECT"

    def test_borderline_multiple_warnings(self) -> None:
        """Two WARNINGs without any FAIL → BORDERLINE."""
        # Low rb (borderline) + 2-night arc (warning) + low neo posterior (warning)
        neo = _make_neo(
            arc_days=1.5,    # > 1 day so no arc FAIL, but orbit quality 1 → WARNING
            n_nights=2,      # WARNING
            rb=0.91,         # borderline → WARNING
            neo_p=0.45,      # < 0.50 → WARNING
            known_p=0.15,    # below warning threshold
            mba_p=0.20,      # below warning threshold
            art_p=0.12,      # below warning threshold
            other_p=0.08,
            orbit_quality=2,  # PASS
            motion_consistency=0.65,  # PASS
        )
        v = run_adversarial_review(neo, offline=True)
        assert v.verdict in {"BORDERLINE", "REJECT"}  # ≥2 warnings → at least BORDERLINE

    def test_verdict_fields(self) -> None:
        """ReviewVerdict must have all required fields populated."""
        neo = _make_neo()
        v = run_adversarial_review(neo, offline=True)
        assert v.object_id == "T_TEST"
        assert isinstance(v.verdict, str)
        assert isinstance(v.challenges, list)
        assert len(v.challenges) > 0
        assert isinstance(v.fail_count, int)
        assert isinstance(v.warning_count, int)
        assert isinstance(v.summary, str)
        assert len(v.summary) > 0
        assert isinstance(v.reviewed_at_utc, str)

    def test_to_dict_serializable(self) -> None:
        """ReviewVerdict.to_dict() must produce a JSON-serializable dict."""
        neo = _make_neo()
        v = run_adversarial_review(neo, offline=True)
        d = v.to_dict()
        # Must round-trip through JSON without error
        s = json.dumps(d)
        loaded = json.loads(s)
        assert loaded["object_id"] == "T_TEST"
        assert "challenges" in loaded
        assert len(loaded["challenges"]) > 0


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_offline_candidate_without_known_object_evidence_exits_1(
        self, tmp_path: Path
    ) -> None:
        """Offline review cannot report survival without required association evidence."""
        neo = _make_neo(
            arc_days=3.0, n_nights=3, rb=0.97,
            neo_p=0.80, known_p=0.05, mba_p=0.08, art_p=0.04, other_p=0.03,
            rate=5.0, orbit_quality=2, motion_consistency=0.90,
        )
        # Serialize to JSON using the ScoredNEO dict representation
        data_file = tmp_path / "candidates.json"
        data_file.write_text(json.dumps([neo.model_dump()]))

        rc = main([str(data_file), "--offline"])
        assert rc == 1

    def test_reject_exit_code_1(self, tmp_path: Path) -> None:
        """A bad candidate → REJECT → exit code 1."""
        neo = _make_neo(rb=0.70)   # clearly below gate → FAIL → REJECT
        data_file = tmp_path / "candidates.json"
        data_file.write_text(json.dumps([neo.model_dump()]))

        rc = main([str(data_file), "--offline"])
        assert rc == 1

    def test_json_output_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """--json flag must emit valid JSON to stdout."""
        neo = _make_neo()
        data_file = tmp_path / "candidates.json"
        data_file.write_text(json.dumps([neo.model_dump()]))

        main([str(data_file), "--offline", "--json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert "verdict" in parsed[0]
        assert "challenges" in parsed[0]

    def test_flat_pipeline_summary_rows_fail_closed(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Compact run_pipeline rows are rejected as incomplete review packets."""
        data_file = tmp_path / "pipeline_summary.json"
        data_file.write_text(json.dumps([
            {
                "object_id": "flat_001",
                "neo_probability": 0.01,
                "hazard_flag": "unknown",
                "alert_pathway": "internal_candidate",
                "moid_au": None,
                "_submission_ready": False,
            }
        ]))

        rc = main([str(data_file), "--offline", "--json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)

        assert rc == 1
        assert parsed[0]["object_id"] == "flat_001"
        assert parsed[0]["verdict"] == "REJECT"
        assert parsed[0]["challenges"][0]["name"] == "review_packet_schema"

    def test_missing_input_file_exits_1(self) -> None:
        rc = main(["/nonexistent/path/to/file.json", "--offline"])
        assert rc == 1

    def test_single_dict_not_list(self, tmp_path: Path) -> None:
        """Input can be a single ScoredNEO dict (not wrapped in a list)."""
        neo = _make_neo()
        data_file = tmp_path / "single.json"
        data_file.write_text(json.dumps(neo.model_dump()))

        rc = main([str(data_file), "--offline"])
        assert rc in {0, 1, 2}   # must not crash

    def test_empty_list_exits_1(self, tmp_path: Path) -> None:
        """Empty input list → error."""
        data_file = tmp_path / "empty.json"
        data_file.write_text(json.dumps([]))
        rc = main([str(data_file), "--offline"])
        assert rc == 1

    def test_malformed_entries_skipped(self, tmp_path: Path) -> None:
        """Malformed JSON entries are skipped; valid ones still reviewed."""
        neo = _make_neo(rb=0.97, arc_days=3.0, n_nights=3, neo_p=0.80,
                        known_p=0.05, mba_p=0.08, art_p=0.04, other_p=0.03,
                        orbit_quality=2, motion_consistency=0.90)
        data = [{"bad": "entry"}, neo.model_dump()]
        data_file = tmp_path / "mixed.json"
        data_file.write_text(json.dumps(data))

        rc = main([str(data_file), "--offline"])
        # Should process the one valid entry; exit code depends on its verdict
        assert rc in {0, 1, 2}
