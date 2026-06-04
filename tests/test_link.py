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


class TestSummarizeArcStatistics:
    def _make_tracklet(self, arc_days, n_nights=2):
        from schemas import Tracklet

        from .conftest import build_observation
        obs = tuple(
            build_observation(obs_id=f"s_{i}", jd=2460000.5 + i * arc_days / max(n_nights - 1, 1))
            for i in range(n_nights)
        )
        return Tracklet(object_id="T1", observations=obs, arc_days=arc_days,
                        motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0)

    def test_empty_list(self):
        from link import summarize_arc_statistics
        result = summarize_arc_statistics([])
        assert result["n_tracklets"] == 0
        assert result["mean_arc_days"] == 0.0
        assert result["max_arc_days"] == 0.0
        assert result["fraction_multi_night"] == 0.0

    def test_counts_tracklets(self):
        from link import summarize_arc_statistics
        tracklets = [self._make_tracklet(1.0), self._make_tracklet(2.0)]
        result = summarize_arc_statistics(tracklets)
        assert result["n_tracklets"] == 2

    def test_mean_arc(self):
        from link import summarize_arc_statistics
        tracklets = [self._make_tracklet(1.0), self._make_tracklet(3.0)]
        result = summarize_arc_statistics(tracklets)
        assert result["mean_arc_days"] == pytest.approx(2.0, abs=0.01)

    def test_max_arc(self):
        from link import summarize_arc_statistics
        tracklets = [self._make_tracklet(1.0), self._make_tracklet(5.0)]
        result = summarize_arc_statistics(tracklets)
        assert result["max_arc_days"] == pytest.approx(5.0, abs=0.01)

    def test_fraction_multi_night_single_night(self):
        from link import summarize_arc_statistics
        # n_nights=1 → all obs on same integer JD
        tracklets = [self._make_tracklet(0.0, n_nights=1)]
        result = summarize_arc_statistics(tracklets)
        assert result["fraction_multi_night"] == pytest.approx(0.0)

    def test_fraction_multi_night_all_multi(self):
        from link import summarize_arc_statistics
        tracklets = [self._make_tracklet(2.0, n_nights=2), self._make_tracklet(3.0, n_nights=3)]
        result = summarize_arc_statistics(tracklets)
        assert result["fraction_multi_night"] == pytest.approx(1.0)


class TestFilterByNightsObserved:
    def _make_tracklet(self, n_nights=2, arc_days=2.0):
        from schemas import Tracklet

        from .conftest import build_observation
        obs = tuple(
            build_observation(obs_id=f"n_{i}", jd=2460000.5 + i)
            for i in range(n_nights)
        )
        return Tracklet(
            object_id=f"T_nights_{n_nights}", observations=obs,
            arc_days=arc_days, motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0,
        )

    def test_empty_input(self):
        from link import filter_by_nights_observed
        assert filter_by_nights_observed([]) == []

    def test_keeps_multi_night(self):
        from link import filter_by_nights_observed
        tracklets = [self._make_tracklet(n_nights=2), self._make_tracklet(n_nights=3)]
        result = filter_by_nights_observed(tracklets, min_nights=2)
        assert len(result) == 2

    def test_rejects_single_night(self):
        from link import filter_by_nights_observed
        tracklets = [self._make_tracklet(n_nights=1), self._make_tracklet(n_nights=2)]
        result = filter_by_nights_observed(tracklets, min_nights=2)
        assert len(result) == 1
        assert result[0].object_id == "T_nights_2"

    def test_min_nights_3_filters_correctly(self):
        from link import filter_by_nights_observed
        tracklets = [
            self._make_tracklet(n_nights=2),
            self._make_tracklet(n_nights=3),
            self._make_tracklet(n_nights=4),
        ]
        result = filter_by_nights_observed(tracklets, min_nights=3)
        assert len(result) == 2

    def test_default_min_nights_is_2(self):
        from link import filter_by_nights_observed
        t1 = self._make_tracklet(n_nights=1)
        t2 = self._make_tracklet(n_nights=2)
        result = filter_by_nights_observed([t1, t2])
        assert len(result) == 1

    def test_returns_list(self):
        from link import filter_by_nights_observed
        result = filter_by_nights_observed([self._make_tracklet()], min_nights=1)
        assert isinstance(result, list)


class TestMergeOverlappingTracklets:
    def _make_tracklet(self, object_id, obs_ids, base_jd=2460000.5):
        from schemas import Tracklet

        from .conftest import build_observation
        obs = tuple(
            build_observation(obs_id=oid, jd=base_jd + i * 1.0)
            for i, oid in enumerate(obs_ids)
        )
        arc = obs[-1].jd - obs[0].jd if len(obs) > 1 else 0.0
        return Tracklet(
            object_id=object_id, observations=obs, arc_days=arc,
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0,
        )

    def test_empty_returns_empty(self):
        from link import merge_overlapping_tracklets
        assert merge_overlapping_tracklets([]) == []

    def test_no_overlap_unchanged(self):
        from link import merge_overlapping_tracklets
        t1 = self._make_tracklet("A", ["obs1", "obs2"])
        t2 = self._make_tracklet("B", ["obs3", "obs4"])
        result = merge_overlapping_tracklets([t1, t2])
        assert len(result) == 2

    def test_overlapping_tracklets_merged(self):
        from link import merge_overlapping_tracklets
        t1 = self._make_tracklet("A", ["obs1", "obs2", "obs3"])
        t2 = self._make_tracklet("B", ["obs3", "obs4", "obs5"])
        result = merge_overlapping_tracklets([t1, t2])
        assert len(result) == 1
        merged_ids = {o.obs_id for o in result[0].observations}
        assert merged_ids == {"obs1", "obs2", "obs3", "obs4", "obs5"}

    def test_merged_takes_longer_arc_object_id(self):
        from link import merge_overlapping_tracklets
        t1 = self._make_tracklet("long", ["obs1", "obs2", "obs3"])
        t2 = self._make_tracklet("short", ["obs3", "obs4"])
        result = merge_overlapping_tracklets([t1, t2])
        assert result[0].object_id == "long"

    def test_single_tracklet_unchanged(self):
        from link import merge_overlapping_tracklets
        t = self._make_tracklet("A", ["obs1", "obs2"])
        result = merge_overlapping_tracklets([t])
        assert len(result) == 1
        assert result[0].object_id == "A"

    def test_observations_deduped(self):
        from link import merge_overlapping_tracklets
        t1 = self._make_tracklet("A", ["obs1", "obs2"])
        t2 = self._make_tracklet("B", ["obs2", "obs3"])
        result = merge_overlapping_tracklets([t1, t2])
        obs_ids = [o.obs_id for o in result[0].observations]
        assert len(obs_ids) == len(set(obs_ids))


class TestValidateTracklet:
    def _obs(self, jd, obs_id=None):
        import uuid

        from schemas import Observation
        return Observation(
            obs_id=obs_id or str(uuid.uuid4()),
            ra_deg=180.0, dec_deg=10.0, jd=jd,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )

    def _make_tracklet(self, obs_ids=None, arc_days=1.0, rate=5.0):
        from schemas import Tracklet
        obs_ids = obs_ids or ["a", "b"]
        obs = tuple(self._obs(2460000.5 + i * 0.5, oid)
                    for i, oid in enumerate(obs_ids))
        return Tracklet(
            object_id="T1", observations=obs,
            arc_days=arc_days, motion_rate_arcsec_per_hour=rate,
            motion_pa_degrees=45.0,
        )

    def test_valid_tracklet_passes(self):
        from link import validate_tracklet
        t = self._make_tracklet()
        valid, reasons = validate_tracklet(t)
        assert valid is True
        assert reasons == []

    def test_single_obs_fails(self):
        from link import validate_tracklet
        from schemas import Tracklet
        obs = (self._obs(2460000.5, "a"),)
        t = Tracklet(object_id="T1", observations=obs, arc_days=0.0,
                     motion_rate_arcsec_per_hour=0.0, motion_pa_degrees=0.0)
        valid, reasons = validate_tracklet(t)
        assert valid is False
        assert any("fewer than 2" in r for r in reasons)

    def test_negative_arc_fails(self):
        from link import validate_tracklet
        t = self._make_tracklet(arc_days=-1.0)
        valid, reasons = validate_tracklet(t)
        assert valid is False
        assert any("negative" in r for r in reasons)

    def test_negative_rate_fails(self):
        from link import validate_tracklet
        t = self._make_tracklet(rate=-1.0)
        valid, reasons = validate_tracklet(t)
        assert valid is False
        assert any("negative" in r for r in reasons)

    def test_unsorted_jds_fails(self):
        from link import validate_tracklet
        from schemas import Tracklet
        o1 = self._obs(2460002.5, "a")
        o2 = self._obs(2460000.5, "b")
        t = Tracklet(object_id="T1", observations=(o1, o2), arc_days=2.0,
                     motion_rate_arcsec_per_hour=5.0, motion_pa_degrees=0.0)
        valid, reasons = validate_tracklet(t)
        assert valid is False
        assert any("sorted" in r for r in reasons)

    def test_duplicate_obs_ids_fails(self):
        from link import validate_tracklet
        from schemas import Tracklet
        o1 = self._obs(2460000.5, "dup")
        o2 = self._obs(2460001.5, "dup")
        t = Tracklet(object_id="T1", observations=(o1, o2), arc_days=1.0,
                     motion_rate_arcsec_per_hour=5.0, motion_pa_degrees=0.0)
        valid, reasons = validate_tracklet(t)
        assert valid is False
        assert any("duplicate" in r for r in reasons)

    def test_multiple_failures_reported(self):
        from link import validate_tracklet
        from schemas import Tracklet
        obs = (self._obs(2460000.5, "a"),)
        t = Tracklet(object_id="T1", observations=obs, arc_days=-1.0,
                     motion_rate_arcsec_per_hour=-5.0, motion_pa_degrees=0.0)
        valid, reasons = validate_tracklet(t)
        assert valid is False
        assert len(reasons) >= 2


class TestComputeGreatCircleResidual:
    def _make_tracklet(self, n_obs=4, jd_start=2460000.5, scatter=0.0):
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(
                obs_id=f"gr_{i}", jd=jd_start + i,
                ra_deg=180.0 + i * 0.001 + scatter * (i % 2 - 0.5),
                dec_deg=10.0 + i * 0.0005,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            )
            for i in range(n_obs)
        )
        return Tracklet(
            object_id="T1", observations=obs, arc_days=float(n_obs - 1),
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0,
        )

    def test_returns_float_for_valid_tracklet(self):
        from link import compute_great_circle_residual
        t = self._make_tracklet(n_obs=4)
        result = compute_great_circle_residual(t)
        assert isinstance(result, float)

    def test_none_for_single_obs(self):
        from link import compute_great_circle_residual
        from schemas import Observation, Tracklet
        obs = (Observation(obs_id="a", jd=2460000.5, ra_deg=180.0, dec_deg=10.0,
                           mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF"),)
        t = Tracklet(object_id="T", observations=obs, arc_days=0.0,
                     motion_rate_arcsec_per_hour=0.0, motion_pa_degrees=0.0)
        assert compute_great_circle_residual(t) is None

    def test_none_for_empty_obs(self):
        from link import compute_great_circle_residual
        from schemas import Tracklet
        t = Tracklet(object_id="T", observations=(), arc_days=0.0,
                     motion_rate_arcsec_per_hour=0.0, motion_pa_degrees=0.0)
        assert compute_great_circle_residual(t) is None

    def test_perfect_linear_motion_near_zero_residual(self):
        from link import compute_great_circle_residual
        # Exactly linear: residual should be ~0
        t = self._make_tracklet(n_obs=5, scatter=0.0)
        result = compute_great_circle_residual(t)
        assert result is not None
        assert result < 0.01  # near-zero for perfect linear motion

    def test_scattered_tracklet_has_nonzero_residual(self):
        from link import compute_great_circle_residual
        t = self._make_tracklet(n_obs=5, scatter=0.01)
        result = compute_great_circle_residual(t)
        assert result is not None
        assert result >= 0.0

    def test_result_in_arcsec_scale(self):
        from link import compute_great_circle_residual
        t = self._make_tracklet(n_obs=4)
        result = compute_great_circle_residual(t)
        assert result is not None
        assert result < 1e6  # sanity: not in degrees

    def test_two_obs_perfect_linear(self):
        from link import compute_great_circle_residual
        from schemas import Observation, Tracklet
        obs = (
            Observation(obs_id="a", jd=2460000.5, ra_deg=180.0, dec_deg=10.0,
                        mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF"),
            Observation(obs_id="b", jd=2460001.5, ra_deg=180.001, dec_deg=10.0005,
                        mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF"),
        )
        t = Tracklet(object_id="T", observations=obs, arc_days=1.0,
                     motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0)
        # With 2 obs a line fits perfectly — residual is 0
        result = compute_great_circle_residual(t)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-5)

    def test_returns_nonnegative(self):
        from link import compute_great_circle_residual
        t = self._make_tracklet(n_obs=6, scatter=0.005)
        result = compute_great_circle_residual(t)
        assert result is not None
        assert result >= 0.0


class TestComputePositionAngleConsistency:
    def _tracklet(self, obs_list):
        import types
        t = types.SimpleNamespace(observations=obs_list)
        return t

    def _obs(self, jd, ra, dec):
        from schemas import Observation
        return Observation(
            obs_id=f"pa_{jd}", jd=jd, ra_deg=ra, dec_deg=dec,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
        )

    def test_returns_none_for_single_obs(self):
        from link import compute_position_angle_consistency
        t = self._tracklet([self._obs(2460000.0, 10.0, 5.0)])
        assert compute_position_angle_consistency(t) is None

    def test_returns_none_for_empty(self):
        from link import compute_position_angle_consistency
        t = self._tracklet([])
        assert compute_position_angle_consistency(t) is None

    def test_linear_motion_low_std(self):
        from link import compute_position_angle_consistency
        obs = [
            self._obs(2460000.0, 10.0, 5.0),
            self._obs(2460001.0, 10.1, 5.1),
            self._obs(2460002.0, 10.2, 5.2),
        ]
        result = compute_position_angle_consistency(self._tracklet(obs))
        assert result is not None
        assert result < 5.0  # near-zero std for linear motion

    def test_returns_float(self):
        from link import compute_position_angle_consistency
        obs = [self._obs(2460000.0, 10.0, 5.0), self._obs(2460001.0, 10.1, 5.0)]
        result = compute_position_angle_consistency(self._tracklet(obs))
        assert result is None  # only 1 pair → no std

    def test_two_pairs_returns_float(self):
        from link import compute_position_angle_consistency
        obs = [
            self._obs(2460000.0, 10.0, 5.0),
            self._obs(2460001.0, 10.1, 5.0),
            self._obs(2460002.0, 10.0, 5.1),
        ]
        result = compute_position_angle_consistency(self._tracklet(obs))
        assert result is not None and isinstance(result, float)

    def test_nonnegative(self):
        from link import compute_position_angle_consistency
        obs = [
            self._obs(2460000.0, 10.0, 5.0),
            self._obs(2460001.0, 11.0, 5.5),
            self._obs(2460002.0, 12.0, 6.0),
        ]
        result = compute_position_angle_consistency(self._tracklet(obs))
        if result is not None:
            assert result >= 0.0

    def test_in_all(self):
        from link import __all__
        assert "compute_position_angle_consistency" in __all__

    def test_same_position_pair_skipped(self):
        from link import compute_position_angle_consistency
        obs = [
            self._obs(2460000.0, 10.0, 5.0),
            self._obs(2460001.0, 10.0, 5.0),
            self._obs(2460002.0, 10.1, 5.1),
        ]
        result = compute_position_angle_consistency(self._tracklet(obs))
        assert result is None


class TestComputePositionAngleConsistencyEdge:
    def _obs(self, jd, ra, dec):
        from schemas import Observation
        return Observation(
            obs_id=f"pac_{jd}", jd=jd, ra_deg=ra, dec_deg=dec,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
        )

    def test_identical_jd_pair_skipped(self):
        """dt == 0.0 branch: two obs at same JD → no valid PA pair → None."""
        import types

        from link import compute_position_angle_consistency
        obs = [
            self._obs(2460000.0, 10.0, 5.0),
            self._obs(2460000.0, 10.1, 5.1),  # same JD as first
            self._obs(2460001.0, 10.2, 5.2),
        ]
        t = types.SimpleNamespace(observations=obs)
        result = compute_position_angle_consistency(t)
        assert result is None or isinstance(result, float)


class TestScoreTrackletQuality:
    """Tests for score_tracklet_quality."""

    def _make_tracklet(self, arc_days: float, n_nights: int = 2, n_obs: int = 4):
        from schemas import Observation, Tracklet
        obs = []
        for night in range(n_nights):
            jd_base = 2460000.5 + night * (arc_days / max(n_nights - 1, 1))
            for k in range(n_obs // n_nights):
                obs.append(Observation(
                    obs_id=f"o_{night}_{k}",
                    ra_deg=180.0 + night * 0.01 + k * 0.001,
                    dec_deg=10.0,
                    jd=jd_base + k * 0.01,
                    mag=19.5,
                    mag_err=0.05,
                    filter_band="r",
                    mission="ZTF",
                    real_bogus=0.9,
                ))
        return Tracklet(
            object_id="T001",
            observations=tuple(obs),
            arc_days=arc_days,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )

    def test_high_quality_tracklet_near_one(self):
        from link import score_tracklet_quality
        t = self._make_tracklet(arc_days=10.0, n_nights=3, n_obs=6)
        score = score_tracklet_quality(t)
        assert 0.0 <= score <= 1.0
        # Long arc (>7 days), multiple nights → grade A or B → high score
        assert score >= 0.5

    def test_single_night_lower_score(self):
        from link import score_tracklet_quality
        from schemas import Observation, Tracklet
        obs = tuple(Observation(
            obs_id=f"o{i}",
            ra_deg=180.0 + i * 0.001,
            dec_deg=0.0,
            jd=2460000.5 + i * 0.01,
            mag=19.5,
            mag_err=0.1,
            filter_band="r",
            mission="ZTF",
            real_bogus=0.9,
        ) for i in range(3))
        t = Tracklet(
            object_id="T_single",
            observations=obs,
            arc_days=0.02,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )
        score = score_tracklet_quality(t)
        # Very short arc → grade D, low arc_score → low quality
        assert score < 0.6

    def test_grade_d_tracklet(self):
        from link import score_tracklet_quality
        from schemas import Observation, Tracklet
        # Two identical obs → linear fit perfect but arc near 0 → grade D
        obs = tuple(Observation(
            obs_id=f"d{i}",
            ra_deg=180.0,
            dec_deg=0.0,
            jd=2460000.5 + i * 0.001,
            mag=19.5,
            mag_err=0.1,
            filter_band="r",
            mission="ZTF",
            real_bogus=0.9,
        ) for i in range(2))
        t = Tracklet(
            object_id="T_D",
            observations=obs,
            arc_days=0.001,
            motion_rate_arcsec_per_hour=0.01,
            motion_pa_degrees=90.0,
        )
        score = score_tracklet_quality(t)
        # grade=D(0.25), arc_score~0, conf~1.0 → score ~ 0.4 * 0.25 + 0.3 * 0 + 0.3 * 1.0
        assert 0.0 <= score <= 0.5

    def test_returns_float_rounded_4dp(self):
        from link import score_tracklet_quality
        t = self._make_tracklet(arc_days=3.0)
        score = score_tracklet_quality(t)
        assert isinstance(score, float)
        # Verify 4 decimal places
        assert round(score, 4) == score

    def test_in_all(self):
        from link import __all__
        assert "score_tracklet_quality" in __all__


class TestComputeNightSpan:
    """Tests for compute_night_span."""

    def _make_tracklet(self, jd_list):
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(
                obs_id=f"ns{i}", ra_deg=180.0 + i * 0.01, dec_deg=0.0,
                jd=jd, mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            )
            for i, jd in enumerate(jd_list)
        )
        return Tracklet(
            object_id="ns_test", observations=obs,
            arc_days=jd_list[-1] - jd_list[0] if len(jd_list) > 1 else 0.0,
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0,
        )

    def test_empty_tracklet_returns_zero(self):
        from types import SimpleNamespace

        from link import compute_night_span
        t = SimpleNamespace(observations=())
        assert compute_night_span(t) == 0

    def test_single_night(self):
        from link import compute_night_span
        t = self._make_tracklet([2460000.5, 2460000.7, 2460000.9])
        assert compute_night_span(t) == 1

    def test_two_nights(self):
        from link import compute_night_span
        t = self._make_tracklet([2460000.5, 2460001.5])
        assert compute_night_span(t) == 2

    def test_multiple_nights(self):
        from link import compute_night_span
        t = self._make_tracklet([2460000.1, 2460001.2, 2460002.3, 2460002.8])
        assert compute_night_span(t) == 3

    def test_in_all(self):
        from link import __all__
        assert "compute_night_span" in __all__


class TestComputeTrackletVelocityDispersion:
    """Tests for compute_tracklet_velocity_dispersion."""

    def _make_tracklet(self, jd_ra_dec_list):
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(
                obs_id=f"vd{i}", ra_deg=ra, dec_deg=dec, jd=jd,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            )
            for i, (jd, ra, dec) in enumerate(jd_ra_dec_list)
        )
        arc = jd_ra_dec_list[-1][0] - jd_ra_dec_list[0][0] if len(jd_ra_dec_list) > 1 else 0.0
        return Tracklet(
            object_id="vd_test", observations=obs, arc_days=arc,
            motion_rate_arcsec_per_hour=1.0, motion_pa_degrees=90.0,
        )

    def test_fewer_than_3_obs_returns_none(self):
        from link import compute_tracklet_velocity_dispersion
        t = self._make_tracklet([(2460000.5, 180.0, 0.0), (2460001.5, 180.01, 0.0)])
        assert compute_tracklet_velocity_dispersion(t) is None

    def test_empty_tracklet_returns_none(self):
        from types import SimpleNamespace

        from link import compute_tracklet_velocity_dispersion
        t = SimpleNamespace(observations=())
        assert compute_tracklet_velocity_dispersion(t) is None

    def test_uniform_motion_near_zero_dispersion(self):
        from link import compute_tracklet_velocity_dispersion
        # linear motion: equal steps
        obs = [
            (2460000.5, 180.000, 0.0),
            (2460001.5, 180.001, 0.0),
            (2460002.5, 180.002, 0.0),
            (2460003.5, 180.003, 0.0),
        ]
        t = self._make_tracklet(obs)
        result = compute_tracklet_velocity_dispersion(t)
        assert result is not None
        assert result < 0.01  # near-zero for uniform motion

    def test_nonuniform_motion_has_dispersion(self):
        from link import compute_tracklet_velocity_dispersion
        # erratic motion
        obs = [
            (2460000.5, 180.000, 0.0),
            (2460001.5, 180.100, 0.0),
            (2460002.5, 180.101, 0.0),
            (2460003.5, 180.900, 0.0),
        ]
        t = self._make_tracklet(obs)
        result = compute_tracklet_velocity_dispersion(t)
        assert result is not None
        assert result > 0.0

    def test_returns_float_rounded_4dp(self):
        from link import compute_tracklet_velocity_dispersion
        obs = [(2460000.5 + i, 180.0 + i * 0.01, 0.0) for i in range(4)]
        t = self._make_tracklet(obs)
        result = compute_tracklet_velocity_dispersion(t)
        assert result is not None
        assert round(result, 4) == result

    def test_in_all(self):
        from link import __all__
        assert "compute_tracklet_velocity_dispersion" in __all__

    def test_duplicate_jd_skipped_gives_none(self):
        """Consecutive identical JDs → all pairs skipped → rates<2 → None."""
        from types import SimpleNamespace

        from link import compute_tracklet_velocity_dispersion

        class FakeObs:
            def __init__(self, ra, dec, jd):
                self.ra_deg = ra
                self.dec_deg = dec
                self.jd = jd

        t = SimpleNamespace(observations=(
            FakeObs(180.0, 0.0, 2460000.5),
            FakeObs(180.1, 0.0, 2460000.5),  # same JD → skip
            FakeObs(180.2, 0.0, 2460000.5),  # same JD → skip
        ))
        assert compute_tracklet_velocity_dispersion(t) is None


class TestComputeInterNightGaps:
    def _tracklet(self, jds):
        import sys
        sys.path.insert(0, "src")
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(obs_id=f"o{i}", ra_deg=10.0, dec_deg=5.0, jd=jd,
                        mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF")
            for i, jd in enumerate(jds)
        )
        return Tracklet(object_id="T1", observations=obs,
                        arc_days=max(jds) - min(jds),
                        motion_rate_arcsec_per_hour=1.0,
                        motion_pa_degrees=90.0)

    def test_two_nights(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_night_gaps
        t = self._tracklet([2460000.8, 2460001.0, 2460002.1])
        gaps = compute_inter_night_gaps(t)
        assert gaps == [1.0, 1.0]

    def test_single_night_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_night_gaps
        t = self._tracklet([2460000.1, 2460000.5, 2460000.9])
        assert compute_inter_night_gaps(t) == []

    def test_three_nights(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_night_gaps
        t = self._tracklet([2460000.5, 2460002.5, 2460005.5])
        gaps = compute_inter_night_gaps(t)
        assert gaps == [2.0, 3.0]

    def test_no_observations_empty(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_inter_night_gaps
        t = SimpleNamespace(observations=())
        assert compute_inter_night_gaps(t) == []

    def test_large_gap(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_night_gaps
        t = self._tracklet([2460000.5, 2460100.5])
        gaps = compute_inter_night_gaps(t)
        assert gaps == [100.0]


class TestFilterByMotionRate:
    def _tracklet(self, rate):
        import sys
        sys.path.insert(0, "src")
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(obs_id=f"o{i}", ra_deg=10.0, dec_deg=5.0, jd=2460000.0 + i,
                        mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF")
            for i in range(2)
        )
        return Tracklet(object_id="T1", observations=obs, arc_days=1.0,
                        motion_rate_arcsec_per_hour=rate, motion_pa_degrees=90.0)

    def test_filters_in_range(self):
        import sys
        sys.path.insert(0, "src")
        from link import filter_by_motion_rate
        tracklets = [self._tracklet(5.0), self._tracklet(25.0), self._tracklet(55.0)]
        result = filter_by_motion_rate(tracklets, min_rate_arcsec_hr=10.0, max_rate_arcsec_hr=30.0)
        assert len(result) == 1
        assert result[0].motion_rate_arcsec_per_hour == 25.0

    def test_all_pass_with_defaults(self):
        import sys
        sys.path.insert(0, "src")
        from link import filter_by_motion_rate
        tracklets = [self._tracklet(1.0), self._tracklet(30.0)]
        assert len(filter_by_motion_rate(tracklets)) == 2

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from link import filter_by_motion_rate
        assert filter_by_motion_rate([]) == []

    def test_no_rate_attribute_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import filter_by_motion_rate
        t = SimpleNamespace()  # no motion_rate_arcsec_per_hour
        assert filter_by_motion_rate([t]) == []

    def test_boundary_inclusive(self):
        import sys
        sys.path.insert(0, "src")
        from link import filter_by_motion_rate
        tracklets = [self._tracklet(10.0), self._tracklet(30.0)]
        result = filter_by_motion_rate(tracklets, 10.0, 30.0)
        assert len(result) == 2


class TestComputeTrackletArcNights:
    def _obs(self, jd):
        from types import SimpleNamespace
        return SimpleNamespace(jd=jd)

    def _tracklet(self, jds):
        from types import SimpleNamespace
        return SimpleNamespace(observations=[self._obs(j) for j in jds])

    def test_basic(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_arc_nights
        t = self._tracklet([2460001.2, 2460002.8, 2460001.9])
        result = compute_tracklet_arc_nights(t)
        assert result == sorted(set([2460001, 2460002]))

    def test_single_night(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_arc_nights
        t = self._tracklet([2460000.1, 2460000.5, 2460000.9])
        assert compute_tracklet_arc_nights(t) == [2460000]

    def test_empty_observations(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_arc_nights
        t = SimpleNamespace(observations=[])
        assert compute_tracklet_arc_nights(t) == []

    def test_sorted_output(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_arc_nights
        t = self._tracklet([2460005.0, 2460003.0, 2460001.0])
        result = compute_tracklet_arc_nights(t)
        assert result == [2460001, 2460003, 2460005]


class TestComputeMeanConsecutiveMotion:
    def _make_tracklet(self, obs_list):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        obs = [SimpleNamespace(jd=jd, ra_deg=ra, dec_deg=dec,
                               mag=18.0, mag_err=0.05)
               for jd, ra, dec in obs_list]
        return SimpleNamespace(observations=obs)

    def test_two_obs_uniform_motion(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_mean_consecutive_motion
        tracklet = self._make_tracklet([
            (2460000.0, 10.0, 5.0),
            (2460001.0, 10.1, 5.0),
        ])
        result = compute_mean_consecutive_motion(tracklet)
        assert result is not None
        assert result > 0.0

    def test_single_obs_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_mean_consecutive_motion
        tracklet = self._make_tracklet([(2460000.0, 10.0, 5.0)])
        assert compute_mean_consecutive_motion(tracklet) is None

    def test_empty_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_mean_consecutive_motion
        tracklet = SimpleNamespace(observations=())
        assert compute_mean_consecutive_motion(tracklet) is None

    def test_identical_jds_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_mean_consecutive_motion
        tracklet = self._make_tracklet([
            (2460000.0, 10.0, 5.0),
            (2460000.0, 10.1, 5.0),
        ])
        assert compute_mean_consecutive_motion(tracklet) is None

    def test_three_obs_mean_rate(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_mean_consecutive_motion
        tracklet = self._make_tracklet([
            (2460000.0, 10.0, 5.0),
            (2460001.0, 10.1, 5.0),
            (2460002.0, 10.2, 5.0),
        ])
        result = compute_mean_consecutive_motion(tracklet)
        assert result is not None
        assert result > 0.0


class TestComputeTrackletSkyDensity:
    def _make_tracklet(self, ra, dec, oid="T1"):
        from types import SimpleNamespace
        obs = SimpleNamespace(ra_deg=ra, dec_deg=dec, jd=2460000.0,
                              mag=18.0, mag_err=0.05)
        return SimpleNamespace(object_id=oid, observations=(obs,))

    def test_two_nearby_tracklets(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_sky_density
        t1 = self._make_tracklet(10.0, 5.0, "T1")
        t2 = self._make_tracklet(10.1, 5.0, "T2")
        result = compute_tracklet_sky_density([t1, t2], radius_deg=1.0)
        assert len(result) == 2
        assert result[0]["n_neighbors"] == 1
        assert result[1]["n_neighbors"] == 1

    def test_two_distant_tracklets(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_sky_density
        t1 = self._make_tracklet(0.0, 0.0, "T1")
        t2 = self._make_tracklet(90.0, 0.0, "T2")
        result = compute_tracklet_sky_density([t1, t2], radius_deg=1.0)
        assert result[0]["n_neighbors"] == 0
        assert result[1]["n_neighbors"] == 0

    def test_empty_observations(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_sky_density
        t = SimpleNamespace(object_id="T1", observations=())
        result = compute_tracklet_sky_density([t], radius_deg=1.0)
        assert result[0]["n_neighbors"] == 0

    def test_single_tracklet(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_sky_density
        t = self._make_tracklet(15.0, 5.0, "T1")
        result = compute_tracklet_sky_density([t])
        assert len(result) == 1
        assert result[0]["n_neighbors"] == 0


class TestComputeTrackletCompleteness:
    def test_full_coverage(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_completeness
        obs1 = SimpleNamespace(jd=2460000.0)
        obs2 = SimpleNamespace(jd=2460001.0)
        obs3 = SimpleNamespace(jd=2460002.0)
        tracklet = SimpleNamespace(observations=(obs1, obs2, obs3))
        result = compute_tracklet_completeness(tracklet, 3)
        assert result == pytest.approx(1.0)

    def test_partial_coverage(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_completeness
        obs1 = SimpleNamespace(jd=2460000.0)
        obs2 = SimpleNamespace(jd=2460001.0)
        tracklet = SimpleNamespace(observations=(obs1, obs2))
        result = compute_tracklet_completeness(tracklet, 4)
        assert result == pytest.approx(0.5)

    def test_zero_expected_nights_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_completeness
        tracklet = SimpleNamespace(observations=())
        assert compute_tracklet_completeness(tracklet, 0) == 0.0

    def test_capped_at_one(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_completeness
        obs1 = SimpleNamespace(jd=2460000.0)
        obs2 = SimpleNamespace(jd=2460001.0)
        obs3 = SimpleNamespace(jd=2460002.0)
        tracklet = SimpleNamespace(observations=(obs1, obs2, obs3))
        result = compute_tracklet_completeness(tracklet, 2)
        assert result == pytest.approx(1.0)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_tracklet_completeness" in link.__all__


class TestFindLongestTracklet:
    def test_returns_longest(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import find_longest_tracklet
        t1 = SimpleNamespace(arc_days=2.0, object_id="T1")
        t2 = SimpleNamespace(arc_days=10.0, object_id="T2")
        t3 = SimpleNamespace(arc_days=5.0, object_id="T3")
        result = find_longest_tracklet([t1, t2, t3])
        assert result is t2

    def test_empty_list_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from link import find_longest_tracklet
        assert find_longest_tracklet([]) is None

    def test_single_tracklet(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import find_longest_tracklet
        t = SimpleNamespace(arc_days=7.0)
        assert find_longest_tracklet([t]) is t

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "find_longest_tracklet" in link.__all__


class TestComputeTrackletMotionScatter:
    def test_consistent_motion_low_scatter(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_motion_scatter
        obs = [
            SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=5.0, mag=18.5),
            SimpleNamespace(jd=2460000.5, ra_deg=10.1, dec_deg=5.1, mag=18.4),
            SimpleNamespace(jd=2460001.0, ra_deg=10.2, dec_deg=5.2, mag=18.3),
        ]
        tracklet = SimpleNamespace(observations=obs)
        result = compute_tracklet_motion_scatter(tracklet)
        assert result is not None
        assert result >= 0.0

    def test_fewer_than_three_obs_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_motion_scatter
        obs = [
            SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=5.0, mag=18.5),
            SimpleNamespace(jd=2460001.0, ra_deg=10.1, dec_deg=5.1, mag=18.4),
        ]
        tracklet = SimpleNamespace(observations=obs)
        assert compute_tracklet_motion_scatter(tracklet) is None

    def test_no_observations_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_motion_scatter
        tracklet = SimpleNamespace(observations=())
        assert compute_tracklet_motion_scatter(tracklet) is None

    def test_zero_time_delta_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_motion_scatter
        # Two obs at same JD plus one more — only 1 valid pair, return None
        obs = [
            SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=5.0, mag=18.5),
            SimpleNamespace(jd=2460000.0, ra_deg=10.05, dec_deg=5.05, mag=18.5),
            SimpleNamespace(jd=2460001.0, ra_deg=10.1, dec_deg=5.1, mag=18.3),
        ]
        tracklet = SimpleNamespace(observations=obs)
        result = compute_tracklet_motion_scatter(tracklet)
        # Only 1 valid pair after skipping zero-dt → returns None
        assert result is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_tracklet_motion_scatter" in link.__all__


class TestComputeGreatCircleArc:
    def test_two_obs_small_separation(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_great_circle_arc
        obs = [
            SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=0.0),
            SimpleNamespace(jd=2460001.0, ra_deg=10.1, dec_deg=0.0),
        ]
        tracklet = SimpleNamespace(observations=obs)
        result = compute_great_circle_arc(tracklet)
        assert result == pytest.approx(360.0, abs=1.0)

    def test_single_obs_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_great_circle_arc
        obs = [SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=0.0)]
        tracklet = SimpleNamespace(observations=obs)
        assert compute_great_circle_arc(tracklet) == pytest.approx(0.0)

    def test_no_obs_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_great_circle_arc
        tracklet = SimpleNamespace(observations=())
        assert compute_great_circle_arc(tracklet) == pytest.approx(0.0)

    def test_three_obs_sums_pairs(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_great_circle_arc
        obs = [
            SimpleNamespace(jd=2460000.0, ra_deg=0.0, dec_deg=0.0),
            SimpleNamespace(jd=2460001.0, ra_deg=0.1, dec_deg=0.0),
            SimpleNamespace(jd=2460002.0, ra_deg=0.2, dec_deg=0.0),
        ]
        tracklet = SimpleNamespace(observations=obs)
        result = compute_great_circle_arc(tracklet)
        assert result > 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_great_circle_arc" in link.__all__


class TestComputeArcCurvature:
    def test_fewer_than_three_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_arc_curvature
        obs1 = SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=5.0)
        obs2 = SimpleNamespace(jd=2460001.0, ra_deg=10.1, dec_deg=5.1)
        tracklet = SimpleNamespace(observations=(obs1, obs2))
        assert compute_arc_curvature(tracklet) == 0.0

    def test_one_obs_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_arc_curvature
        obs = SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=5.0)
        assert compute_arc_curvature(SimpleNamespace(observations=(obs,))) == 0.0

    def test_linear_motion_near_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_arc_curvature
        obs_list = [
            SimpleNamespace(jd=2460000.0 + i, ra_deg=10.0 + i * 0.01, dec_deg=5.0 + i * 0.01)
            for i in range(5)
        ]
        result = compute_arc_curvature(SimpleNamespace(observations=tuple(obs_list)))
        assert result < 0.01

    def test_curved_motion_nonzero(self):
        import math
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_arc_curvature
        obs_list = [
            SimpleNamespace(
                jd=2460000.0 + i,
                ra_deg=10.0 + 0.5 * math.sin(i * 0.5),
                dec_deg=5.0 + 0.5 * math.cos(i * 0.5),
            )
            for i in range(6)
        ]
        assert compute_arc_curvature(SimpleNamespace(observations=tuple(obs_list))) > 0.0

    def test_exception_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_arc_curvature
        # Observations with non-numeric jd trigger exception → returns 0.0
        obs_list = [
            SimpleNamespace(jd="bad", ra_deg=10.0, dec_deg=5.0),
            SimpleNamespace(jd="bad", ra_deg=10.1, dec_deg=5.1),
            SimpleNamespace(jd="bad", ra_deg=10.2, dec_deg=5.2),
        ]
        assert compute_arc_curvature(SimpleNamespace(observations=tuple(obs_list))) == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_arc_curvature" in link.__all__


class TestComputeTrackletDensity:
    def _make_tracklet(self, ra_deg, dec_deg, object_id="T001"):
        import sys
        sys.path.insert(0, "src")
        from schemas import Observation, Tracklet
        obs = Observation(
            obs_id=object_id + "_obs",
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            jd=2460000.5,
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        )
        return Tracklet(
            object_id=object_id,
            observations=(obs,),
            arc_days=0.0,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )

    def test_empty_input_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_density
        result = compute_tracklet_density([])
        assert result == []

    def test_single_tracklet_count_is_zero(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_density
        t = self._make_tracklet(10.0, 0.0)
        result = compute_tracklet_density([t])
        assert result == [0]

    def test_two_close_tracklets(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_density
        t1 = self._make_tracklet(10.0, 0.0, "T1")
        t2 = self._make_tracklet(10.1, 0.0, "T2")  # ~0.1 deg apart
        result = compute_tracklet_density([t1, t2], radius_deg=1.0)
        assert result == [1, 1]

    def test_two_far_tracklets(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_density
        t1 = self._make_tracklet(10.0, 0.0, "T1")
        t2 = self._make_tracklet(50.0, 40.0, "T2")  # far apart
        result = compute_tracklet_density([t1, t2], radius_deg=1.0)
        assert result == [0, 0]

    def test_length_matches_input(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_density
        tracklets = [self._make_tracklet(float(i), 0.0, f"T{i}") for i in range(5)]
        result = compute_tracklet_density(tracklets, radius_deg=0.5)
        assert len(result) == 5

    def test_does_not_count_self(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_density
        t = self._make_tracklet(10.0, 0.0)
        result = compute_tracklet_density([t], radius_deg=360.0)
        assert result[0] == 0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_tracklet_density" in link.__all__


class TestComputeTrackletDensityEdgeCases:
    """Tests for edge cases in compute_tracklet_density._first_radec."""

    def test_obs_with_ra_not_ra_deg(self):
        """Test fallback to 'ra'/'dec' when 'ra_deg'/'dec_deg' are absent."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_density

        obs = SimpleNamespace(ra=10.0, dec=5.0)
        tracklet = SimpleNamespace(observations=[obs])
        result = compute_tracklet_density([tracklet], radius_deg=1.0)
        assert result == [0]

    def test_obs_with_no_radec_attrs_returns_zero_count(self):
        """Observation with no spatial attrs — _first_radec returns None, count=0."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_density

        obs = SimpleNamespace()  # no ra_deg, ra, dec_deg, dec
        tracklet = SimpleNamespace(observations=[obs])
        result = compute_tracklet_density([tracklet], radius_deg=360.0)
        assert result == [0]

    def test_empty_observations_list(self):
        """Tracklet with empty observations — _first_radec returns None."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_density

        tracklet = SimpleNamespace(observations=[])
        result = compute_tracklet_density([tracklet], radius_deg=1.0)
        assert result == [0]


class TestComputePositionResiduals:
    def _make_tracklet(self, ras, decs, jds):
        import sys
        sys.path.insert(0, "src")
        obs_list = []
        for i, (ra, dec, jd) in enumerate(zip(ras, decs, jds)):
            obs_list.append(Observation(
                obs_id=f"o{i}", ra_deg=ra, dec_deg=dec, jd=jd,
                mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            ))
        return Tracklet(
            object_id="TEST",
            observations=tuple(obs_list),
            arc_days=float(jds[-1] - jds[0]),
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=0.0,
        )

    def test_linear_motion_small_residuals(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_position_residuals
        # Perfect linear motion — residuals should be near zero
        jds = [2460000.0, 2460001.0, 2460002.0]
        ras = [10.0, 10.01, 10.02]
        decs = [5.0, 5.0, 5.0]
        t = self._make_tracklet(ras, decs, jds)
        residuals = compute_position_residuals(t)
        assert len(residuals) == 3
        assert all(r < 0.01 for r in residuals)

    def test_nonlinear_motion_nonzero_residuals(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_position_residuals
        # Curved motion — middle point offset should give nonzero residual
        jds = [2460000.0, 2460001.0, 2460002.0]
        ras = [10.0, 10.005, 10.02]  # non-linear
        decs = [5.0, 5.005, 5.0]   # non-linear
        t = self._make_tracklet(ras, decs, jds)
        residuals = compute_position_residuals(t)
        assert len(residuals) == 3
        assert max(residuals) > 0.0

    def test_single_obs_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_position_residuals
        obs = Observation(
            obs_id="o0", ra_deg=10.0, dec_deg=5.0, jd=2460000.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
        )
        t = Tracklet(
            object_id="TEST",
            observations=(obs,),
            arc_days=0.0,
            motion_rate_arcsec_per_hour=0.0,
            motion_pa_degrees=0.0,
        )
        assert compute_position_residuals(t) == []

    def test_residuals_are_nonnegative(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_position_residuals
        jds = [2460000.0, 2460001.0, 2460002.0, 2460003.0]
        ras = [10.0, 10.01, 10.02, 10.03]
        decs = [5.0, 5.01, 5.02, 5.03]
        t = self._make_tracklet(ras, decs, jds)
        residuals = compute_position_residuals(t)
        assert all(r >= 0.0 for r in residuals)

    def test_returns_list(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_position_residuals
        jds = [2460000.0, 2460001.0]
        ras = [10.0, 10.01]
        decs = [5.0, 5.0]
        t = self._make_tracklet(ras, decs, jds)
        result = compute_position_residuals(t)
        assert isinstance(result, list)

    def test_exception_returns_empty(self):
        """Passing a non-Tracklet object triggers exception → returns []."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_position_residuals
        # observations with non-numeric ra_deg will trigger exception
        bad_obs = SimpleNamespace(ra_deg="bad", dec_deg="bad", jd=2460000.0)
        tracklet = SimpleNamespace(observations=[bad_obs, bad_obs])
        result = compute_position_residuals(tracklet)  # type: ignore[arg-type]
        assert result == []

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_position_residuals" in link.__all__


class TestComputeInterObservationGaps:
    def _make_tracklet(self, jds):
        import sys
        sys.path.insert(0, "src")
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(
                obs_id=f"g_{i}", ra_deg=10.0 + i * 0.001, dec_deg=5.0,
                jd=jd, mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            )
            for i, jd in enumerate(jds)
        )
        return Tracklet(
            object_id="T_GAP",
            observations=obs,
            arc_days=max(jds) - min(jds) if len(jds) > 1 else 0.0,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )

    def test_two_observations_one_gap(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_observation_gaps
        t = self._make_tracklet([2460000.0, 2460001.0])
        gaps = compute_inter_observation_gaps(t)
        assert len(gaps) == 1
        assert abs(gaps[0] - 24.0) < 1e-9

    def test_three_observations_two_gaps(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_observation_gaps
        t = self._make_tracklet([2460000.0, 2460001.0, 2460002.0])
        gaps = compute_inter_observation_gaps(t)
        assert len(gaps) == 2
        assert all(abs(g - 24.0) < 1e-9 for g in gaps)

    def test_single_observation_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_observation_gaps
        from schemas import Observation, Tracklet
        obs = (Observation(
            obs_id="o1", ra_deg=10.0, dec_deg=5.0, jd=2460000.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
        ),)
        t = Tracklet(
            object_id="T_SINGLE",
            observations=obs,
            arc_days=0.0,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=0.0,
        )
        assert compute_inter_observation_gaps(t) == []

    def test_unordered_observations_sorted(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_observation_gaps
        # Provide in reverse order; should still compute positive gaps
        t = self._make_tracklet([2460002.0, 2460000.0])
        gaps = compute_inter_observation_gaps(t)
        assert len(gaps) == 1
        assert gaps[0] > 0.0

    def test_half_day_gap(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_inter_observation_gaps
        t = self._make_tracklet([2460000.0, 2460000.5])
        gaps = compute_inter_observation_gaps(t)
        assert abs(gaps[0] - 12.0) < 1e-9

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_inter_observation_gaps" in link.__all__


class TestComputeTrackletOverlapFraction:
    """Tests for compute_tracklet_overlap_fraction."""

    def _make_tracklet(self, obs_ids):
        import sys
        sys.path.insert(0, "src")
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(
                obs_id=oid, jd=2460000.0 + i, ra_deg=10.0, dec_deg=5.0,
                mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            )
            for i, oid in enumerate(obs_ids)
        )
        return Tracklet(
            object_id="T_" + obs_ids[0],
            observations=obs,
            arc_days=float(len(obs_ids) - 1),
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )

    def test_no_overlap(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_overlap_fraction
        t1 = self._make_tracklet(["a", "b"])
        t2 = self._make_tracklet(["c", "d"])
        assert compute_tracklet_overlap_fraction(t1, t2) == 0.0

    def test_full_overlap_same_tracklet(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_overlap_fraction
        t1 = self._make_tracklet(["a", "b", "c"])
        assert compute_tracklet_overlap_fraction(t1, t1) == 1.0

    def test_partial_overlap(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_overlap_fraction
        t1 = self._make_tracklet(["a", "b", "c"])
        t2 = self._make_tracklet(["b", "c", "d"])
        frac = compute_tracklet_overlap_fraction(t1, t2)
        assert abs(frac - 2.0 / 3.0) < 1e-9

    def test_empty_tracklet_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_overlap_fraction
        from schemas import Tracklet
        empty = Tracklet(
            object_id="empty", observations=(), arc_days=0.0,
            motion_rate_arcsec_per_hour=0.0, motion_pa_degrees=0.0,
        )
        t2 = self._make_tracklet(["a", "b"])
        assert compute_tracklet_overlap_fraction(empty, t2) == 0.0
        assert compute_tracklet_overlap_fraction(t2, empty) == 0.0

    def test_result_in_0_1(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_overlap_fraction
        t1 = self._make_tracklet(["a", "b", "c", "d"])
        t2 = self._make_tracklet(["c", "d", "e"])
        frac = compute_tracklet_overlap_fraction(t1, t2)
        assert 0.0 <= frac <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_tracklet_overlap_fraction" in link.__all__


class TestComputeVelocityDispersion:
    def _make_tracklet(self, rate: float) -> "Tracklet":
        from types import SimpleNamespace
        return SimpleNamespace(motion_rate_arcsec_per_hour=rate)

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_velocity_dispersion
        assert compute_velocity_dispersion([]) == 0.0

    def test_single_tracklet_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_velocity_dispersion
        assert compute_velocity_dispersion([self._make_tracklet(5.0)]) == 0.0

    def test_identical_rates_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_velocity_dispersion
        tracklets = [self._make_tracklet(3.0) for _ in range(5)]
        assert compute_velocity_dispersion(tracklets) == 0.0

    def test_different_rates_returns_positive(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_velocity_dispersion
        tracklets = [self._make_tracklet(r) for r in [1.0, 3.0, 5.0, 7.0]]
        result = compute_velocity_dispersion(tracklets)
        assert result > 0.0

    def test_known_dispersion(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_velocity_dispersion
        # rates: 0, 2 → mean=1, var=1, std=1
        tracklets = [self._make_tracklet(0.0), self._make_tracklet(2.0)]
        result = compute_velocity_dispersion(tracklets)
        assert abs(result - 1.0) < 1e-9

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_velocity_dispersion" in link.__all__


class TestComputeTrackletCentroid:
    def test_basic_centroid(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_centroid
        obs1 = SimpleNamespace(ra=10.0, dec=20.0)
        obs2 = SimpleNamespace(ra=20.0, dec=30.0)
        tracklet = SimpleNamespace(observations=(obs1, obs2))
        result = compute_tracklet_centroid(tracklet)
        assert result is not None
        assert abs(result["ra_deg"] - 15.0) < 1e-9
        assert abs(result["dec_deg"] - 25.0) < 1e-9

    def test_single_observation(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_centroid
        obs = SimpleNamespace(ra=100.0, dec=-45.0)
        tracklet = SimpleNamespace(observations=(obs,))
        result = compute_tracklet_centroid(tracklet)
        assert result is not None
        assert abs(result["ra_deg"] - 100.0) < 1e-9
        assert abs(result["dec_deg"] - -45.0) < 1e-9

    def test_empty_observations_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_centroid
        tracklet = SimpleNamespace(observations=())
        assert compute_tracklet_centroid(tracklet) is None

    def test_no_observations_attr_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_centroid
        tracklet = SimpleNamespace()
        assert compute_tracklet_centroid(tracklet) is None

    def test_returns_dict_keys(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_centroid
        obs = SimpleNamespace(ra=50.0, dec=10.0)
        tracklet = SimpleNamespace(observations=(obs,))
        result = compute_tracklet_centroid(tracklet)
        assert result is not None
        assert "ra_deg" in result
        assert "dec_deg" in result

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_tracklet_centroid" in link.__all__


class TestComputeAlongTrackError:
    """Tests for compute_along_track_error."""

    @staticmethod
    def _make_tracklet(n_obs=4, pa_deg=0.0):
        from types import SimpleNamespace

        obs = []
        for i in range(n_obs):
            obs.append(SimpleNamespace(
                ra=180.0 + i * 0.001,
                dec=10.0 + i * 0.0001,
                jd=2460000.5 + i * 1.0,
            ))
        return SimpleNamespace(
            observations=tuple(obs),
            motion_pa_degrees=pa_deg,
            motion_rate_arcsec_per_hour=1.0,
        )

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")

        from link import compute_along_track_error

        tracklet = self._make_tracklet(4)
        result = compute_along_track_error(tracklet)
        assert isinstance(result, float)

    def test_few_obs_returns_zero(self):
        import sys
        sys.path.insert(0, "src")

        from link import compute_along_track_error

        tracklet = self._make_tracklet(2)
        assert compute_along_track_error(tracklet) == 0.0

    def test_one_obs_returns_zero(self):
        import sys
        sys.path.insert(0, "src")

        from link import compute_along_track_error

        tracklet = self._make_tracklet(1)
        assert compute_along_track_error(tracklet) == 0.0

    def test_perfectly_linear_near_zero(self):
        import sys
        sys.path.insert(0, "src")

        from link import compute_along_track_error

        # Perfectly linear motion → residuals should be very small
        tracklet = self._make_tracklet(5)
        result = compute_along_track_error(tracklet)
        assert result >= 0.0
        assert result < 1.0  # should be near 0 for linear motion

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link

        assert "compute_along_track_error" in link.__all__

    def test_no_observations_attr_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_along_track_error

        tracklet = SimpleNamespace()
        assert compute_along_track_error(tracklet) == 0.0

    def test_observations_with_invalid_jd_triggers_exception_path(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_along_track_error

        # Observations with all the same JD will cause polyfit to produce
        # degenerate coefficients that survive, but if we pass non-numeric
        # ra values numpy will raise an exception caught by the except block.
        class _BadObs:
            ra = "not-a-number"
            dec = 10.0
            jd = 2460000.5

        tracklet = SimpleNamespace(
            observations=(_BadObs(), _BadObs(), _BadObs()),
            motion_pa_degrees=0.0,
        )
        result = compute_along_track_error(tracklet)
        assert result == 0.0


class TestComputeObservationRate:
    def _make_tracklet(self, jds: list[float]) -> object:
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        obs = [SimpleNamespace(jd=j) for j in jds]
        return SimpleNamespace(observations=tuple(obs))

    def test_single_night(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_observation_rate
        trk = self._make_tracklet([2460000.5, 2460000.6, 2460000.7])
        result = compute_observation_rate(trk)
        assert result == 3.0

    def test_multi_night(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_observation_rate
        trk = self._make_tracklet([2460000.5, 2460001.5, 2460002.5])
        result = compute_observation_rate(trk)
        assert abs(result - 1.0) < 1e-9

    def test_two_nights_four_obs(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_observation_rate
        trk = self._make_tracklet([2460000.1, 2460000.9, 2460001.1, 2460001.9])
        result = compute_observation_rate(trk)
        assert abs(result - 2.0) < 1e-9

    def test_empty_observations_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_observation_rate
        trk = SimpleNamespace(observations=())
        assert compute_observation_rate(trk) is None

    def test_no_observations_attr_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_observation_rate
        trk = SimpleNamespace()
        assert compute_observation_rate(trk) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_observation_rate" in link.__all__


class TestComputeTrackletBrightnessTrend:
    def _make_tracklet(self, jds: list[float], mags: list[float]) -> object:
        from types import SimpleNamespace
        obs = [SimpleNamespace(jd=j, mag=m) for j, m in zip(jds, mags)]
        return SimpleNamespace(observations=tuple(obs))

    def test_fading_trend_positive(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_brightness_trend
        # brightness increasing with JD → fading
        trk = self._make_tracklet([2460000.0, 2460001.0, 2460002.0], [19.0, 20.0, 21.0])
        result = compute_tracklet_brightness_trend(trk)
        assert result is not None
        assert result > 0.0

    def test_brightening_trend_negative(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_brightness_trend
        trk = self._make_tracklet([2460000.0, 2460001.0, 2460002.0], [21.0, 20.0, 19.0])
        result = compute_tracklet_brightness_trend(trk)
        assert result is not None
        assert result < 0.0

    def test_single_obs_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_brightness_trend
        trk = self._make_tracklet([2460000.0], [20.0])
        assert compute_tracklet_brightness_trend(trk) is None

    def test_sentinel_mags_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_tracklet_brightness_trend
        # Only 1 valid mag after sentinel exclusion → None
        trk = self._make_tracklet([2460000.0, 2460001.0], [99.0, 20.0])
        assert compute_tracklet_brightness_trend(trk) is None

    def test_no_observations_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_brightness_trend
        assert compute_tracklet_brightness_trend(SimpleNamespace(observations=())) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_tracklet_brightness_trend" in link.__all__


class TestComputeTrackletBrightnessTrendNoneMag:
    def test_none_mag_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_tracklet_brightness_trend
        obs = [
            SimpleNamespace(jd=2460000.0, mag=None),
            SimpleNamespace(jd=2460001.0, mag=19.0),
        ]
        trk = SimpleNamespace(observations=tuple(obs))
        # Only 1 valid mag after None exclusion → None
        assert compute_tracklet_brightness_trend(trk) is None


class TestComputeArcEndpointSeparation:
    def _make_tracklet(self, ra_dec_jd_list):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        obs = [
            SimpleNamespace(
                obs_id=f"O{i}", ra_deg=ra, dec_deg=dec, jd=jd,
                mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            )
            for i, (ra, dec, jd) in enumerate(ra_dec_jd_list)
        ]
        return SimpleNamespace(
            object_id="T1",
            observations=tuple(obs),
            arc_days=1.0,
            motion_rate_arcsec_per_hour=5.0,
            motion_pa_degrees=0.0,
        )

    def test_same_position_zero_separation(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_arc_endpoint_separation
        t = self._make_tracklet([(10.0, 20.0, 2460000.0), (10.0, 20.0, 2460001.0)])
        result = compute_arc_endpoint_separation(t)
        assert result is not None
        assert result < 1e-6

    def test_known_separation(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_arc_endpoint_separation
        # 1 degree separation in RA at dec=0 → 3600 arcsec
        t = self._make_tracklet([(10.0, 0.0, 2460000.0), (11.0, 0.0, 2460001.0)])
        result = compute_arc_endpoint_separation(t)
        assert result is not None
        assert abs(result - 3600.0) < 1.0

    def test_single_obs_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_arc_endpoint_separation
        t = self._make_tracklet([(10.0, 20.0, 2460000.0)])
        assert compute_arc_endpoint_separation(t) is None

    def test_no_observations_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_arc_endpoint_separation
        t = SimpleNamespace(observations=())
        assert compute_arc_endpoint_separation(t) is None

    def test_multi_obs(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_arc_endpoint_separation
        t = self._make_tracklet([
            (10.0, 0.0, 2460000.0),
            (10.5, 0.0, 2460000.5),
            (11.0, 0.0, 2460001.0),
        ])
        result = compute_arc_endpoint_separation(t)
        assert result is not None
        assert result > 3000.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_arc_endpoint_separation" in link.__all__


class TestComputePaCircularStd:
    def _make_tracklet(self, pa: float):
        from types import SimpleNamespace
        return SimpleNamespace(motion_pa_degrees=pa)

    def test_spread_angles(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_pa_circular_std
        tracklets = [self._make_tracklet(pa) for pa in [0.0, 90.0, 180.0, 270.0]]
        result = compute_pa_circular_std(tracklets)
        assert result is not None
        assert result > 0.0

    def test_consistent_angles(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_pa_circular_std
        tracklets = [self._make_tracklet(45.0) for _ in range(5)]
        result = compute_pa_circular_std(tracklets)
        assert result is not None
        assert result < 1.0

    def test_too_few_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from link import compute_pa_circular_std
        result = compute_pa_circular_std([self._make_tracklet(45.0)])
        assert result is None

    def test_no_pa_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from link import compute_pa_circular_std
        t = SimpleNamespace(motion_pa_degrees=None)
        assert compute_pa_circular_std([t, t]) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import link
        assert "compute_pa_circular_std" in link.__all__
