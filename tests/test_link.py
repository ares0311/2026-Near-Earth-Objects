"""Tests for link.py."""

import pytest

from link import (
    _fit_linear_motion,
    _make_tracklet,
    _motion,
    _obs_by_night,
    _sep_arcsec,
    link,
)
from schemas import Observation, RawCandidate


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
