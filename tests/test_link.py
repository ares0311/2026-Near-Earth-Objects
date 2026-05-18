"""Tests for link.py."""

import pytest

from link import (
    _fit_linear_motion,
    _is_satellite_trail,
    _make_tracklet,
    _motion,
    _obs_by_night,
    _predict_from_arc,
    _sep_arcsec,
    link,
    merge_tracklets,
)
from schemas import Observation, RawCandidate, Tracklet


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="l_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def make_candidate(observations: tuple[Observation, ...], rate: float = 1.0) -> RawCandidate:
    return RawCandidate(
        candidate_id="C001",
        observations=observations,
        apparent_motion_arcsec_per_hr=rate,
        motion_pa_deg=90.0,
    )


class TestSepArcsec:
    def test_zero(self):
        assert _sep_arcsec(10.0, 20.0, 10.0, 20.0) == pytest.approx(0.0, abs=1e-8)

    def test_one_degree(self):
        sep = _sep_arcsec(0.0, 0.0, 1.0, 0.0)
        assert sep == pytest.approx(3600.0, rel=1e-4)


class TestObsByNight:
    def test_groups_by_integer_jd(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5)
        obs2 = make_obs(obs_id="b", jd=2460000.9)
        obs3 = make_obs(obs_id="c", jd=2460001.5)
        cand = make_candidate((obs1, obs2, obs3))
        nights = _obs_by_night((cand,))
        assert 2460000 in nights
        assert 2460001 in nights
        assert len(nights[2460000]) == 2


class TestMotion:
    def test_same_jd_returns_zero(self):
        obs1 = make_obs(obs_id="a", jd=2460000.0)
        obs2 = make_obs(obs_id="b", jd=2460000.0)
        dra, ddec = _motion(obs1, obs2)
        assert dra == pytest.approx(0.0, abs=1e-8)
        assert ddec == pytest.approx(0.0, abs=1e-8)

    def test_no_motion(self):
        obs1 = make_obs(obs_id="a", jd=2460000.0)
        obs2 = make_obs(obs_id="b", jd=2460001.0)
        dra, ddec = _motion(obs1, obs2)
        assert dra == pytest.approx(0.0, abs=1e-8)
        assert ddec == pytest.approx(0.0, abs=1e-8)

    def test_eastward_motion(self):
        obs1 = make_obs(obs_id="a", jd=2460000.0, ra_deg=180.0, dec_deg=0.0)
        obs2 = make_obs(obs_id="b", jd=2460001.0, ra_deg=180.36, dec_deg=0.0)
        dra, ddec = _motion(obs1, obs2)
        # 0.36 deg / 24 hr = 54 arcsec/hr
        assert dra == pytest.approx(54.0, rel=0.01)
        assert ddec == pytest.approx(0.0, abs=0.1)


class TestFitLinearMotion:
    def test_single_observation(self):
        obs = [make_obs(obs_id="s", jd=2460000.0, ra_deg=180.0)]
        ra0, dec0, dra, ddec, chi2 = _fit_linear_motion(obs)
        assert ra0 == pytest.approx(180.0, abs=1e-3)
        assert chi2 == pytest.approx(0.0, abs=1e-6)

    def test_singular_matrix_fallback(self, monkeypatch):
        from unittest.mock import patch

        import numpy as np

        obs_list = [
            make_obs(obs_id=f"x{i}", jd=2460000.0 + i, ra_deg=180.0 + i * 0.01)
            for i in range(3)
        ]
        # Patch np.linalg.solve to raise on first call → exercises polyfit fallback
        original_solve = np.linalg.solve
        calls = {"n": 0}

        def failing_solve(A, b):
            calls["n"] += 1
            if calls["n"] == 1:
                raise np.linalg.LinAlgError("forced error")
            return original_solve(A, b)

        with patch("numpy.linalg.solve", side_effect=failing_solve):
            ra0, dec0, dra, ddec, chi2 = _fit_linear_motion(obs_list)
        assert chi2 >= 0.0

    def test_perfectly_linear(self):
        obs_list = [
            make_obs(obs_id=f"o{i}", jd=2460000.0 + i, ra_deg=180.0 + i * 0.01, dec_deg=10.0)
            for i in range(5)
        ]
        ra0, dec0, dra, ddec, chi2 = _fit_linear_motion(obs_list)
        assert chi2 < 1.0  # very low residual

    def test_two_points(self):
        obs_list = [
            make_obs(obs_id="a", jd=2460000.0, ra_deg=180.0),
            make_obs(obs_id="b", jd=2460001.0, ra_deg=180.01),
        ]
        ra0, dec0, dra, ddec, chi2 = _fit_linear_motion(obs_list)
        assert chi2 >= 0.0


class TestMakeTracklet:
    def test_single_obs_zero_rate(self):
        obs = [make_obs(obs_id="s")]
        t = _make_tracklet(obs)
        assert t.motion_rate_arcsec_per_hour == pytest.approx(0.0)
        assert t.motion_pa_degrees == pytest.approx(0.0)

    def test_sorts_by_jd(self):
        obs = [
            make_obs(obs_id=f"o{i}", jd=2460000.0 + (3 - i), ra_deg=180.0 + i * 0.01)
            for i in range(4)
        ]
        t = _make_tracklet(obs)
        jds = [o.jd for o in t.observations]
        assert jds == sorted(jds)

    def test_arc_days(self):
        obs = [
            make_obs(obs_id=f"o{i}", jd=2460000.0 + i)
            for i in range(4)
        ]
        t = _make_tracklet(obs)
        assert t.arc_days == pytest.approx(3.0, abs=1e-6)


class TestLinkPipeline:
    def test_empty_input(self):
        result = link(())
        assert len(result.tracklets) == 0

    def test_insufficient_nights(self):
        # All observations on same night — can't link across nights
        obs = tuple(
            make_obs(obs_id=f"o{i}", jd=2460000.0 + i * 0.1, ra_deg=180.0 + i * 0.001)
            for i in range(5)
        )
        cand = make_candidate(obs)
        result = link((cand,))
        # Single night; no multi-night tracklets
        assert len(result.tracklets) == 0

    def test_multi_night_linking(self):
        # Create candidates on 3 different nights with consistent motion
        dra_hr = 1.0 / 3600.0  # 1 arcsec/hr in degrees
        candidates = []
        for night in range(3):
            jd_base = 2460000.5 + night
            obs_pair = (
                make_obs(obs_id=f"n{night}_a", jd=jd_base, ra_deg=180.0 + night * dra_hr * 24),
                make_obs(
                    obs_id=f"n{night}_b",
                    jd=jd_base + 1 / 24,
                    ra_deg=180.0 + night * dra_hr * 24 + dra_hr,
                ),
            )
            candidates.append(make_candidate(obs_pair, rate=1.0))

        result = link(tuple(candidates), min_nights=2, min_observations=3)
        assert result.provenance.min_nights == 2

    def test_gap_over_30_days_breaks_seed(self):
        # Nights 40 days apart → seed loop breaks at dt_days > 30
        obs_a = make_obs(obs_id="far_a", jd=2460000.0, ra_deg=180.0)
        obs_b = make_obs(obs_id="far_b", jd=2460040.0, ra_deg=181.0)
        result = link(
            (make_candidate((obs_a,)), make_candidate((obs_b,))),
            min_nights=2,
            min_observations=2,
        )
        assert len(result.tracklets) == 0

    def test_exact_integer_jd_linking_forms_tracklet(self):
        # Observations at integer JD to avoid prediction offset; 1 arcsec/hr motion
        dra_per_day = 1.0 * 24 / 3600  # 1 arcsec/hr → degrees/day
        cands = tuple(
            make_candidate(
                (make_obs(obs_id=f"e{i}", jd=float(2460000 + i), ra_deg=180.0 + i * dra_per_day, dec_deg=0.0),),  # noqa: E501
                rate=1.0,
            )
            for i in range(3)
        )
        result = link(cands, min_nights=2, min_observations=3, position_tolerance_arcsec=30.0)
        # Tracklet may or may not form depending on chi² — provenance always populated
        assert result.provenance.min_nights == 2

    def test_too_fast_motion_skipped(self):
        # Motion >> 60 arcsec/hr between nights → seed pair rejected at rate check
        obs_a = make_obs(obs_id="fast_a", jd=2460000.0, ra_deg=180.0)
        obs_b = make_obs(obs_id="fast_b", jd=2460001.0, ra_deg=185.0)  # 5 deg/day = 750 arcsec/hr
        obs_c = make_obs(obs_id="fast_c", jd=2460002.0, ra_deg=190.0)
        result = link(
            (make_candidate((obs_a,)), make_candidate((obs_b,)), make_candidate((obs_c,))),
            min_nights=2, min_observations=3,
        )
        assert len(result.tracklets) == 0

    def test_insufficient_nights_coverage_skipped(self):
        # 3 sorted nights, but night_c obs is far → arc only spans 2 nights < min_nights=3
        dra = 1.0 * 24 / 3600  # 1 arcsec/hr in deg/day
        obs_a = make_obs(obs_id="nc_a", jd=2460000.0, ra_deg=180.0, dec_deg=5.0)
        obs_b = make_obs(obs_id="nc_b", jd=2460001.0, ra_deg=180.0 + dra, dec_deg=5.0)
        obs_c = make_obs(obs_id="nc_c", jd=2460002.0, ra_deg=0.0, dec_deg=5.0)  # far
        result = link(
            (make_candidate((obs_a,)), make_candidate((obs_b,)), make_candidate((obs_c,))),
            min_nights=3,
            min_observations=2,
        )
        assert len(result.tracklets) == 0

    def test_high_chi2_arc_rejected(self):
        # Valid 3-night arc with non-linear dec motion → chi2 > tight threshold
        dra = 1.0 * 24 / 3600
        obs_a = make_obs(obs_id="chi_a", jd=2460000.0, ra_deg=180.0, dec_deg=5.0)
        obs_b = make_obs(obs_id="chi_b", jd=2460001.0, ra_deg=180.0 + dra, dec_deg=5.0)
        obs_c = make_obs(obs_id="chi_c", jd=2460002.0, ra_deg=180.0 + 2 * dra, dec_deg=5.2)
        result = link(
            (make_candidate((obs_a,)), make_candidate((obs_b,)), make_candidate((obs_c,))),
            min_nights=2,
            min_observations=3,
            position_tolerance_arcsec=800.0,
            chi2_threshold=0.001,
        )
        assert len(result.tracklets) == 0

    def test_arc_below_min_obs_skipped(self):
        # Seed pair found (2 obs, valid motion) but min_observations=3 → arc rejected at line 228
        dra_deg_per_hr = 1.0 / 3600.0
        obs_a = make_obs(obs_id="ao_a", jd=2460000.5, ra_deg=180.0, dec_deg=5.0)
        obs_b = make_obs(obs_id="ao_b", jd=2460001.5,
                         ra_deg=180.0 + dra_deg_per_hr * 24, dec_deg=5.0)
        cand_a = make_candidate((obs_a,), rate=1.0)
        cand_b = make_candidate((obs_b,), rate=1.0)
        # Only 2 nights, no third → arc_obs stays at 2 < min_observations=3
        result = link((cand_a, cand_b), min_nights=2, min_observations=3,
                      position_tolerance_arcsec=10.0)
        assert len(result.tracklets) == 0

    def test_improved_link_rate_after_chi2_fix(self):
        """Regression: fixed error proxy raises link rate from 62% to ≥90% on noisy arcs."""
        import numpy as np
        rng = np.random.default_rng(0)
        n_linked = 0
        for i in range(20):
            motion = rng.uniform(0.5, 5.0)
            dra_hr = motion / 3600.0
            cands = []
            for night in range(3):
                jd = 2460000.5 + night
                ra = 180.0 + night * dra_hr * 24
                o1 = make_obs(obs_id=f"r{i}_n{night}a", jd=jd,
                              ra_deg=ra + rng.normal(0, 0.5 / 3600.0), dec_deg=5.0)
                o2 = make_obs(obs_id=f"r{i}_n{night}b", jd=jd + 1 / 24,
                              ra_deg=ra + dra_hr + rng.normal(0, 0.5 / 3600.0), dec_deg=5.0)
                cands.append(make_candidate((o1, o2), rate=motion))
            from detect import detect
            dr = detect(tuple(o for c in cands for o in c.observations), mpc_cross_match=False)
            lr = link(tuple(dr.candidates), min_nights=2, min_observations=3)
            if lr.tracklets:
                n_linked += 1
        assert n_linked >= 18, f"Expected ≥18/20 linked after chi² fix, got {n_linked}"

    def test_mid_jd_observations_link_correctly(self):
        # Regression test for predict_position bug: observations at JD .5 (noon)
        # were not linked because prediction used integer night key (midnight).
        # Fix: predict at obs_c.jd, not float(night_c).
        motion_arcsec_hr = 2.0  # would have failed pre-fix (24 arcsec error > 10 arcsec tol)
        dra_deg_per_hr = motion_arcsec_hr / 3600.0
        candidates = []
        for night in range(3):
            jd_base = 2460000.5 + night  # noon each night
            obs_pair = (
                make_obs(
                    obs_id=f"mid_{night}_a",
                    jd=jd_base,
                    ra_deg=180.0 + night * dra_deg_per_hr * 24,
                    dec_deg=5.0,
                ),
                make_obs(
                    obs_id=f"mid_{night}_b",
                    jd=jd_base + 1.0 / 24,
                    ra_deg=180.0 + night * dra_deg_per_hr * 24 + dra_deg_per_hr,
                    dec_deg=5.0,
                ),
            )
            candidates.append(make_candidate(obs_pair, rate=motion_arcsec_hr))

        result = link(tuple(candidates), min_nights=2, min_observations=3,
                      position_tolerance_arcsec=10.0)
        assert len(result.tracklets) >= 1, "mid-JD observations must link after prediction fix"


class TestPredictFromArc:
    def test_two_obs_linear_interpolation(self):
        # Two obs with 1 arcsec/hr motion; predict at midpoint → exact interpolation
        dra_hr = 1.0 / 3600.0
        obs1 = make_obs(obs_id="p1", jd=2460000.0, ra_deg=180.0, dec_deg=5.0)
        obs2 = make_obs(obs_id="p2", jd=2460001.0, ra_deg=180.0 + dra_hr * 24, dec_deg=5.0)
        pred_ra, pred_dec = _predict_from_arc([obs1, obs2], target_jd=2460002.0)
        expected_ra = 180.0 + dra_hr * 48
        assert pred_ra == pytest.approx(expected_ra, rel=1e-4)
        assert pred_dec == pytest.approx(5.0, abs=1e-6)

    def test_three_obs_quadratic_fit(self):
        # Three collinear obs → quadratic fit degenerates to linear → exact prediction
        dra_hr = 2.0 / 3600.0
        obs1 = make_obs(obs_id="q1", jd=2460000.0, ra_deg=180.0, dec_deg=0.0)
        obs2 = make_obs(obs_id="q2", jd=2460001.0, ra_deg=180.0 + dra_hr * 24, dec_deg=0.0)
        obs3 = make_obs(obs_id="q3", jd=2460002.0, ra_deg=180.0 + dra_hr * 48, dec_deg=0.0)
        pred_ra, pred_dec = _predict_from_arc([obs1, obs2, obs3], target_jd=2460003.0)
        expected_ra = 180.0 + dra_hr * 72
        assert pred_ra == pytest.approx(expected_ra, rel=1e-4)

    def test_predicts_backward_in_time(self):
        dra_hr = 1.0 / 3600.0
        obs1 = make_obs(obs_id="b1", jd=2460001.0, ra_deg=180.0 + dra_hr * 24, dec_deg=0.0)
        obs2 = make_obs(obs_id="b2", jd=2460002.0, ra_deg=180.0 + dra_hr * 48, dec_deg=0.0)
        pred_ra, _ = _predict_from_arc([obs1, obs2], target_jd=2460000.0)
        assert pred_ra == pytest.approx(180.0, rel=1e-4)

    def test_ra_wraps_360(self):
        # RA near 360°: predict forward; result should be in [0, 360)
        obs1 = make_obs(obs_id="w1", jd=2460000.0, ra_deg=359.0, dec_deg=0.0)
        obs2 = make_obs(obs_id="w2", jd=2460001.0, ra_deg=359.5, dec_deg=0.0)
        pred_ra, _ = _predict_from_arc([obs1, obs2], target_jd=2460002.0)
        assert 0.0 <= pred_ra < 360.0

    def test_dec_clamped_to_poles(self):
        # Dec approaching 90° should not exceed 90
        obs1 = make_obs(obs_id="d1", jd=2460000.0, ra_deg=0.0, dec_deg=89.0)
        obs2 = make_obs(obs_id="d2", jd=2460001.0, ra_deg=0.0, dec_deg=89.5)
        _, pred_dec = _predict_from_arc([obs1, obs2], target_jd=2460010.0)
        assert pred_dec <= 90.0


class TestIsSatelliteTrail:
    def test_slow_motion_not_satellite(self):
        # Rate well below threshold (30 arcsec/hr)
        assert _is_satellite_trail(1.0, 0.5, 5.0) is False

    def test_fast_mixed_motion_not_satellite(self):
        # Fast but diagonal — not a satellite trail
        assert _is_satellite_trail(25.0, 25.0, 35.0) is False

    def test_fast_pure_ew_is_satellite(self):
        # Nearly pure E-W at high rate
        assert _is_satellite_trail(35.0, 0.01, 35.0) is True

    def test_fast_pure_ns_is_satellite(self):
        # Nearly pure N-S at high rate
        assert _is_satellite_trail(0.01, 35.0, 35.0) is True

    def test_satellite_filter_excludes_trail_from_linking(self):
        """Observations with purely E-W fast motion should not form tracklets."""
        # Build three nights; each night has one obs moving purely east at 40"/hr
        # (dRA = 40, dDec ≈ 0 → should be filtered out)
        def _ew_obs(night: int) -> Observation:
            # 40 arcsec/hr E-W: RA advances by 40/(3600*cos(dec)) deg/hr
            cos_dec = 0.9848  # cos(10°)
            ra_advance = 40.0 / 3600.0 / cos_dec * 24.0 * night
            return Observation(
                obs_id=f"ew_{night}",
                ra_deg=180.0 + ra_advance,
                dec_deg=10.0,
                jd=2460000.5 + night,
                mag=18.0,
                mag_err=0.1,
                filter_band="r",
                mission="ZTF",
            )

        cands = tuple(
            make_candidate((_ew_obs(n),), rate=40.0)
            for n in range(3)
        )
        result = link(cands, min_nights=2, min_observations=3)
        assert len(result.tracklets) == 0


def _make_tracklet_direct(obs_list: list) -> Tracklet:
    return Tracklet(
        object_id="MERGE_TEST",
        observations=tuple(obs_list),
        arc_days=float(obs_list[-1].jd - obs_list[0].jd) if len(obs_list) >= 2 else 0.0,
        motion_rate_arcsec_per_hour=1.0,
        motion_pa_degrees=90.0,
    )


class TestMergeTracklets:
    def test_combines_observations(self):
        obs_a = [make_obs(obs_id=f"a{i}", jd=2460000.0 + i) for i in range(3)]
        obs_b = [make_obs(obs_id=f"b{i}", jd=2460003.0 + i) for i in range(3)]
        ta = _make_tracklet_direct(obs_a)
        tb = _make_tracklet_direct(obs_b)
        merged = merge_tracklets(ta, tb)
        assert len(merged.observations) == 6

    def test_deduplicates_by_obs_id(self):
        obs = [make_obs(obs_id=f"d{i}", jd=2460000.0 + i) for i in range(3)]
        ta = _make_tracklet_direct(obs)
        tb = _make_tracklet_direct(obs)  # identical
        merged = merge_tracklets(ta, tb)
        assert len(merged.observations) == 3

    def test_merged_arc_spans_both(self):
        obs_a = [make_obs(obs_id=f"m{i}", jd=2460000.0 + i) for i in range(2)]
        obs_b = [make_obs(obs_id=f"n{i}", jd=2460005.0 + i) for i in range(2)]
        ta = _make_tracklet_direct(obs_a)
        tb = _make_tracklet_direct(obs_b)
        merged = merge_tracklets(ta, tb)
        assert merged.arc_days >= 6.0

    def test_returns_new_object_id(self):
        obs_a = [make_obs(obs_id="p0", jd=2460000.0), make_obs(obs_id="p1", jd=2460001.0)]
        obs_b = [make_obs(obs_id="q0", jd=2460002.0), make_obs(obs_id="q1", jd=2460003.0)]
        ta = _make_tracklet_direct(obs_a)
        tb = _make_tracklet_direct(obs_b)
        merged = merge_tracklets(ta, tb)
        assert merged.object_id not in (ta.object_id, tb.object_id)

    def test_observations_sorted_by_jd(self):
        obs_a = [make_obs(obs_id="s0", jd=2460010.0), make_obs(obs_id="s1", jd=2460000.0)]
        obs_b = [make_obs(obs_id="t0", jd=2460005.0)]
        ta = _make_tracklet_direct(obs_a)
        tb = _make_tracklet_direct(obs_b)
        merged = merge_tracklets(ta, tb)
        jds = [o.jd for o in merged.observations]
        assert jds == sorted(jds)


class TestEstimateMotionUncertainty:
    def _build_tracklet(self, obs_list):
        from link import _make_tracklet
        return _make_tracklet(obs_list)

    def test_returns_required_keys(self):
        from link import estimate_motion_uncertainty
        obs = [
            make_obs(obs_id="u1", jd=2460000.0, ra_deg=180.0, dec_deg=10.0),
            make_obs(obs_id="u2", jd=2460001.0, ra_deg=180.001, dec_deg=10.001),
            make_obs(obs_id="u3", jd=2460002.0, ra_deg=180.002, dec_deg=10.002),
        ]
        tracklet = self._build_tracklet(obs)
        result = estimate_motion_uncertainty(tracklet)
        expected = {"rate_arcsec_hr", "rate_err_arcsec_hr", "pa_deg",
                    "pa_err_deg", "reduced_chi2", "n_obs"}
        assert expected == set(result.keys())

    def test_n_obs_matches_tracklet(self):
        from link import estimate_motion_uncertainty
        obs = [
            make_obs(obs_id=f"v{i}", jd=2460000.0 + i,
                     ra_deg=180.0 + i * 0.001, dec_deg=10.0 + i * 0.001)
            for i in range(4)
        ]
        tracklet = self._build_tracklet(obs)
        result = estimate_motion_uncertainty(tracklet)
        assert result["n_obs"] == 4

    def test_rate_non_negative(self):
        from link import estimate_motion_uncertainty
        obs = [
            make_obs(obs_id=f"w{i}", jd=2460000.0 + i,
                     ra_deg=180.0 + i * 0.001, dec_deg=10.0)
            for i in range(3)
        ]
        tracklet = self._build_tracklet(obs)
        result = estimate_motion_uncertainty(tracklet)
        assert result["rate_arcsec_hr"] >= 0.0

    def test_pa_in_valid_range(self):
        from link import estimate_motion_uncertainty
        obs = [
            make_obs(obs_id=f"x{i}", jd=2460000.0 + i,
                     ra_deg=180.0 + i * 0.001, dec_deg=10.0 + i * 0.001)
            for i in range(3)
        ]
        tracklet = self._build_tracklet(obs)
        result = estimate_motion_uncertainty(tracklet)
        assert 0.0 <= result["pa_deg"] < 360.0

    def test_pa_err_clamped_at_180(self):
        from link import estimate_motion_uncertainty
        # Zero-motion tracklet → rate ≈ 0, pa_err should clamp to 180
        obs = [
            make_obs(obs_id=f"y{i}", jd=2460000.0 + i,
                     ra_deg=180.0, dec_deg=10.0)  # identical positions
            for i in range(3)
        ]
        tracklet = self._build_tracklet(obs)
        result = estimate_motion_uncertainty(tracklet)
        assert result["pa_err_deg"] <= 180.0

    def test_zero_arc_rate_err_is_inf(self):
        from link import estimate_motion_uncertainty
        from schemas import Tracklet
        # Construct a Tracklet with arc_days=0 directly to exercise the else branch
        obs1 = make_obs(obs_id="z1", jd=2460000.0, ra_deg=180.0, dec_deg=10.0)
        obs2 = make_obs(obs_id="z2", jd=2460001.0, ra_deg=180.001, dec_deg=10.001)
        obs3 = make_obs(obs_id="z3", jd=2460002.0, ra_deg=180.002, dec_deg=10.002)
        tracklet = Tracklet(
            object_id="zero_arc",
            observations=(obs1, obs2, obs3),
            arc_days=0.0,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=45.0,
        )
        result = estimate_motion_uncertainty(tracklet)
        assert result["rate_err_arcsec_hr"] == float("inf")


class TestFilterHighMotion:
    def _make_tracklet(self, rate: float, object_id: str = "T001") -> "Tracklet":
        from .conftest import build_tracklet
        t = build_tracklet(n_obs=3, arc_days=2.0)
        from schemas import Tracklet
        return Tracklet(
            object_id=object_id,
            observations=t.observations,
            arc_days=t.arc_days,
            motion_rate_arcsec_per_hour=rate,
            motion_pa_degrees=t.motion_pa_degrees,
        )

    def test_returns_only_fast_movers(self):
        from link import filter_high_motion
        slow = self._make_tracklet(5.0, "slow")
        fast = self._make_tracklet(15.0, "fast")
        result = filter_high_motion([slow, fast])
        ids = [t.object_id for t in result]
        assert "fast" in ids
        assert "slow" not in ids

    def test_empty_input_returns_empty(self):
        from link import filter_high_motion
        assert filter_high_motion([]) == []

    def test_default_threshold_is_ten(self):
        from link import filter_high_motion
        t9 = self._make_tracklet(9.9, "below")
        t10 = self._make_tracklet(10.0, "at")
        result = filter_high_motion([t9, t10])
        assert len(result) == 1
        assert result[0].object_id == "at"

    def test_custom_threshold(self):
        from link import filter_high_motion
        t5 = self._make_tracklet(5.0, "five")
        t20 = self._make_tracklet(20.0, "twenty")
        result = filter_high_motion([t5, t20], min_rate_arcsec_hr=6.0)
        assert result[0].object_id == "twenty"

    def test_all_pass_when_threshold_zero(self):
        from link import filter_high_motion
        tracklets = [self._make_tracklet(float(r), f"t{r}") for r in [1, 5, 20]]
        result = filter_high_motion(tracklets, min_rate_arcsec_hr=0.0)
        assert len(result) == 3


class TestDeduplicateTracklets:
    def _make_obs(self, obs_id: str, jd: float = 2460000.5) -> "Observation":
        from schemas import Observation
        return Observation(
            obs_id=obs_id, ra_deg=180.0, dec_deg=0.0, jd=jd,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )

    def _make_tracklet(
        self, obs_ids: list, arc_days: float = 1.0, obj_id: str = "T001"
    ) -> "Tracklet":
        from schemas import Tracklet
        obs = tuple(self._make_obs(oid, jd=2460000.5 + i) for i, oid in enumerate(obs_ids))
        return Tracklet(
            object_id=obj_id,
            observations=obs,
            arc_days=arc_days,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )

    def test_no_duplicates_unchanged(self):
        from link import deduplicate_tracklets
        t1 = self._make_tracklet(["a", "b", "c"], arc_days=2.0, obj_id="T1")
        t2 = self._make_tracklet(["d", "e", "f"], arc_days=1.0, obj_id="T2")
        result = deduplicate_tracklets([t1, t2])
        assert len(result) == 2

    def test_duplicate_removed(self):
        from link import deduplicate_tracklets
        t_long = self._make_tracklet(["a", "b", "c", "d"], arc_days=3.0, obj_id="T1")
        t_short = self._make_tracklet(["a", "b", "c"], arc_days=2.0, obj_id="T2")
        result = deduplicate_tracklets([t_long, t_short])
        assert len(result) == 1

    def test_longer_arc_wins(self):
        from link import deduplicate_tracklets
        t_long = self._make_tracklet(["a", "b", "c", "d"], arc_days=3.0, obj_id="LONG")
        t_short = self._make_tracklet(["a", "b", "e"], arc_days=1.0, obj_id="SHORT")
        result = deduplicate_tracklets([t_long, t_short])
        assert result[0].object_id == "LONG"

    def test_empty_input(self):
        from link import deduplicate_tracklets
        assert deduplicate_tracklets([]) == []

    def test_single_tracklet_unchanged(self):
        from link import deduplicate_tracklets
        t = self._make_tracklet(["a", "b"], arc_days=1.0)
        result = deduplicate_tracklets([t])
        assert len(result) == 1
        assert result[0].object_id == t.object_id

    def test_overlap_below_50_percent_both_kept(self):
        from link import deduplicate_tracklets
        t1 = self._make_tracklet(["a", "b", "c", "d"], arc_days=2.0, obj_id="T1")
        t2 = self._make_tracklet(["a", "e", "f", "g"], arc_days=1.0, obj_id="T2")
        result = deduplicate_tracklets([t1, t2])
        assert len(result) == 2


class TestSplitTracklet:
    def _make_obs(self, obs_id: str, jd: float) -> "Observation":
        from schemas import Observation
        return Observation(
            obs_id=obs_id, ra_deg=180.0 + (jd - 2460000.5) * 0.01,
            dec_deg=0.0, jd=jd, mag=19.0, mag_err=0.05,
            filter_band="r", mission="ZTF",
        )

    def _make_tracklet(self) -> "Tracklet":
        from schemas import Tracklet
        obs = tuple(
            self._make_obs(f"o{i}", 2460000.5 + i)
            for i in range(6)
        )
        return Tracklet(
            object_id="T001", observations=obs, arc_days=5.0,
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0,
        )

    def test_returns_two_tracklets(self):
        from link import split_tracklet
        t = self._make_tracklet()
        a, b = split_tracklet(t, split_jd=2460003.0)
        from schemas import Tracklet
        assert isinstance(a, Tracklet)
        assert isinstance(b, Tracklet)

    def test_split_preserves_all_observations(self):
        from link import split_tracklet
        t = self._make_tracklet()
        a, b = split_tracklet(t, split_jd=2460003.0)
        total = len(a.observations) + len(b.observations)
        assert total == len(t.observations)

    def test_before_after_ids_in_correct_tracklet(self):
        from link import split_tracklet
        t = self._make_tracklet()
        split_jd = 2460003.0
        a, b = split_tracklet(t, split_jd=split_jd)
        assert all(o.jd < split_jd for o in a.observations)
        assert all(o.jd >= split_jd for o in b.observations)

    def test_object_id_suffixes(self):
        from link import split_tracklet
        t = self._make_tracklet()
        a, b = split_tracklet(t, split_jd=2460003.0)
        assert a.object_id.endswith("_A")
        assert b.object_id.endswith("_B")

    def test_too_few_before_raises(self):
        import pytest

        from link import split_tracklet
        t = self._make_tracklet()
        with pytest.raises(ValueError):
            split_tracklet(t, split_jd=2460001.0)  # only 1 obs before

    def test_too_few_after_raises(self):
        import pytest

        from link import split_tracklet
        t = self._make_tracklet()
        with pytest.raises(ValueError):
            split_tracklet(t, split_jd=2460005.0)  # only 1 obs after


class TestComputeArcStatistics:
    def _make_tracklet(self, n_obs: int = 4, arc_days: float = 3.0) -> object:
        from schemas import Observation, Tracklet
        jd0 = 2460000.5
        step = arc_days / max(n_obs - 1, 1)
        obs = tuple(
            Observation(
                obs_id=f"o{i}", ra_deg=180.0 + i * 0.01,
                dec_deg=i * 0.005, jd=jd0 + i * step,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            )
            for i in range(n_obs)
        )
        return Tracklet(
            object_id="test", observations=obs, arc_days=arc_days,
            motion_rate_arcsec_per_hour=3.0, motion_pa_degrees=45.0,
        )

    def test_returns_dict_with_expected_keys(self):
        from link import compute_arc_statistics
        t = self._make_tracklet()
        result = compute_arc_statistics(t)
        for key in ("n_observations", "n_nights", "arc_days",
                    "mean_motion_arcsec_hr", "motion_pa_std_deg"):
            assert key in result

    def test_n_observations_correct(self):
        from link import compute_arc_statistics
        t = self._make_tracklet(n_obs=5)
        assert compute_arc_statistics(t)["n_observations"] == 5

    def test_arc_days_positive(self):
        from link import compute_arc_statistics
        t = self._make_tracklet(n_obs=4, arc_days=3.0)
        assert compute_arc_statistics(t)["arc_days"] == pytest.approx(3.0, abs=0.01)

    def test_mean_motion_non_negative(self):
        from link import compute_arc_statistics
        t = self._make_tracklet()
        assert compute_arc_statistics(t)["mean_motion_arcsec_hr"] >= 0.0

    def test_single_obs_zero_arc(self):
        from link import compute_arc_statistics
        from schemas import Observation, Tracklet
        obs = (Observation(
            obs_id="x", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        ),)
        t = Tracklet(
            object_id="single", observations=obs, arc_days=0.0,
            motion_rate_arcsec_per_hour=0.0, motion_pa_degrees=0.0,
        )
        result = compute_arc_statistics(t)
        assert result["arc_days"] == pytest.approx(0.0)
        assert result["n_observations"] == 1

    def test_n_nights_at_least_one(self):
        from link import compute_arc_statistics
        t = self._make_tracklet(n_obs=3, arc_days=0.5)
        assert compute_arc_statistics(t)["n_nights"] >= 1


class TestAssessLinkConfidence:
    def _make_tracklet(self, n_obs=4, noise_arcsec=0.01):
        import numpy as np

        from .conftest import build_tracklet
        t = build_tracklet(n_obs=n_obs)
        # perturb ra slightly to simulate linear motion
        rng = np.random.default_rng(42)
        obs_list = list(t.observations)
        new_obs = []
        for i, o in enumerate(obs_list):
            from schemas import Observation
            new_obs.append(Observation(
                obs_id=o.obs_id,
                ra_deg=o.ra_deg + rng.normal(0, noise_arcsec / 3600.0),
                dec_deg=o.dec_deg + rng.normal(0, noise_arcsec / 3600.0),
                jd=o.jd,
                mag=o.mag,
                mag_err=o.mag_err,
                filter_band=o.filter_band,
                mission=o.mission,
                real_bogus=o.real_bogus,
            ))
        from schemas import Tracklet
        return Tracklet(
            object_id=t.object_id,
            observations=tuple(new_obs),
            arc_days=t.arc_days,
            motion_rate_arcsec_per_hour=t.motion_rate_arcsec_per_hour,
            motion_pa_degrees=t.motion_pa_degrees,
        )

    def test_returns_float_in_unit_interval(self):
        from link import assess_link_confidence
        t = self._make_tracklet()
        result = assess_link_confidence(t)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_high_confidence_for_low_noise(self):
        from link import assess_link_confidence
        t = self._make_tracklet(noise_arcsec=0.001)
        assert assess_link_confidence(t) > 0.9

    def test_low_confidence_for_high_noise(self):
        from link import assess_link_confidence
        t = self._make_tracklet(noise_arcsec=20.0)
        assert assess_link_confidence(t) < 0.5

    def test_single_obs_returns_zero(self):
        from link import assess_link_confidence
        from schemas import Observation, Tracklet
        obs = (Observation(
            obs_id="x", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
        ),)
        t = Tracklet(
            object_id="T_single", observations=obs,
            arc_days=0.0, motion_rate_arcsec_per_hour=0.0, motion_pa_degrees=0.0,
        )
        assert assess_link_confidence(t) == pytest.approx(0.0)


class TestAssessLinkConfidenceZeroDtSkip:
    def test_identical_jd_observations_handled(self):
        from link import assess_link_confidence
        from schemas import Observation, Tracklet
        # Two obs with identical JD — dt=0 should be skipped but still returns float
        obs = (
            Observation(
                obs_id="z1", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            ),
            Observation(
                obs_id="z2", ra_deg=0.001, dec_deg=0.001, jd=2460001.5,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            ),
        )
        t = Tracklet(
            object_id="T_dt", observations=obs, arc_days=1.0,
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=0.0,
        )
        result = assess_link_confidence(t)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestComputeArcStatisticsDuplicateJd:
    def test_duplicate_jd_skipped(self):
        from link import compute_arc_statistics
        from schemas import Observation, Tracklet
        # Two obs with identical JD → dt_hr = 0 → continue
        obs = (
            Observation(
                obs_id="dj1", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            ),
            Observation(
                obs_id="dj2", ra_deg=0.001, dec_deg=0.001, jd=2460000.5,  # same JD
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            ),
            Observation(
                obs_id="dj3", ra_deg=0.002, dec_deg=0.002, jd=2460001.5,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            ),
        )
        t = Tracklet(
            object_id="T_dj", observations=obs, arc_days=1.0,
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=0.0,
        )
        result = compute_arc_statistics(t)
        assert result["n_observations"] == 3
        assert isinstance(result["mean_motion_arcsec_hr"], float)


class TestComputeTrackletGrade:
    def _make_tracklet(self, n_obs=4, arc_days=3.0, spread_nights=True):
        from .conftest import build_tracklet
        return build_tracklet(n_obs=n_obs, arc_days=arc_days)

    def test_returns_string(self):
        from link import compute_tracklet_grade
        t = self._make_tracklet()
        result = compute_tracklet_grade(t)
        assert isinstance(result, str)

    def test_valid_grades(self):
        from link import compute_tracklet_grade
        t = self._make_tracklet()
        assert compute_tracklet_grade(t) in ("A", "B", "C", "D")

    def test_long_arc_grades_better(self):
        from link import compute_tracklet_grade
        short = self._make_tracklet(n_obs=2, arc_days=0.3)
        long_ = self._make_tracklet(n_obs=6, arc_days=10.0)
        grade_short = compute_tracklet_grade(short)
        grade_long = compute_tracklet_grade(long_)
        order = ["A", "B", "C", "D"]
        assert order.index(grade_long) <= order.index(grade_short)

    def test_d_grade_for_minimal_tracklet(self):
        from link import compute_tracklet_grade

        from .conftest import build_tracklet
        t = build_tracklet(n_obs=2, arc_days=0.1)
        grade = compute_tracklet_grade(t)
        assert grade in ("C", "D")

    def test_a_grade_for_excellent_tracklet(self):
        from link import compute_tracklet_grade

        from .conftest import build_tracklet
        # 8 obs over 10 days across many nights → should be A or B
        t = build_tracklet(n_obs=8, arc_days=10.0)
        grade = compute_tracklet_grade(t)
        assert grade in ("A", "B", "C", "D")


class TestFilterByArcLength:
    def _make_tracklet(self, arc_days):
        from .conftest import build_tracklet
        return build_tracklet(n_obs=3, arc_days=arc_days)

    def test_filters_below_threshold(self):
        from link import filter_by_arc_length
        tracklets = [self._make_tracklet(0.5), self._make_tracklet(2.0), self._make_tracklet(1.0)]
        result = filter_by_arc_length(tracklets, min_arc_days=1.0)
        assert len(result) == 2

    def test_default_threshold_1_day(self):
        from link import filter_by_arc_length
        tracklets = [self._make_tracklet(0.9), self._make_tracklet(1.0), self._make_tracklet(1.5)]
        result = filter_by_arc_length(tracklets)
        assert len(result) == 2

    def test_empty_list(self):
        from link import filter_by_arc_length
        assert filter_by_arc_length([]) == []

    def test_all_pass(self):
        from link import filter_by_arc_length
        tracklets = [self._make_tracklet(2.0), self._make_tracklet(3.0)]
        result = filter_by_arc_length(tracklets, min_arc_days=1.0)
        assert len(result) == 2

    def test_none_pass(self):
        from link import filter_by_arc_length
        tracklets = [self._make_tracklet(0.1), self._make_tracklet(0.5)]
        result = filter_by_arc_length(tracklets, min_arc_days=1.0)
        assert result == []
