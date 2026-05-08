"""Tests for detect.py."""

import base64

import numpy as np
import pytest

from detect import (
    _angular_sep_arcsec,
    _cross_match_mpc,
    _find_moving_sources,
    _group_by_night,
    _is_streak,
    _motion_rate_and_pa,
    _passes_real_bogus,
    detect,
)
from schemas import Observation


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="d_001",
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


class TestAngularSep:
    def test_same_point(self):
        sep = _angular_sep_arcsec(10.0, 20.0, 10.0, 20.0)
        assert sep == pytest.approx(0.0, abs=1e-8)

    def test_known_separation(self):
        # 1 degree on the equator
        sep = _angular_sep_arcsec(0.0, 0.0, 1.0, 0.0)
        assert sep == pytest.approx(3600.0, rel=1e-4)

    def test_pole_to_equator(self):
        sep = _angular_sep_arcsec(0.0, 0.0, 0.0, 90.0)
        assert sep == pytest.approx(90 * 3600.0, rel=1e-4)


class TestMotionRate:
    def test_no_motion(self):
        obs1 = make_obs(obs_id="a", jd=2460000.0)
        obs2 = make_obs(obs_id="b", jd=2460001.0)
        rate, pa = _motion_rate_and_pa(obs1, obs2)
        assert rate == pytest.approx(0.0, abs=1e-8)

    def test_eastward_motion(self):
        obs1 = make_obs(obs_id="a", jd=2460000.0, ra_deg=180.0, dec_deg=0.0)
        obs2 = make_obs(obs_id="b", jd=2460001.0, ra_deg=180.1, dec_deg=0.0)
        rate, pa = _motion_rate_and_pa(obs1, obs2)
        # 0.1 deg = 360 arcsec over 24 hours = 15 arcsec/hr
        assert rate == pytest.approx(15.0, rel=0.01)

    def test_zero_dt(self):
        obs1 = make_obs(obs_id="a", jd=2460000.0)
        obs2 = make_obs(obs_id="b", jd=2460000.0)
        rate, pa = _motion_rate_and_pa(obs1, obs2)
        assert rate == pytest.approx(0.0, abs=1e-8)


class TestRealBogus:
    def test_passes_above_threshold(self):
        obs = make_obs(real_bogus=0.8)
        assert _passes_real_bogus(obs, 0.65) is True

    def test_fails_below_threshold(self):
        obs = make_obs(real_bogus=0.4)
        assert _passes_real_bogus(obs, 0.65) is False

    def test_no_score_passes(self):
        obs = make_obs()
        assert _passes_real_bogus(obs, 0.65) is True

    def test_prefers_deep_rb(self):
        obs = make_obs(real_bogus=0.3, deep_real_bogus=0.9)
        assert _passes_real_bogus(obs, 0.65) is True


class TestGroupByNight:
    def test_single_night(self):
        obs1 = make_obs(obs_id="a", jd=2460000.1)
        obs2 = make_obs(obs_id="b", jd=2460000.9)
        nights = _group_by_night((obs1, obs2))
        assert len(nights) == 1

    def test_two_nights(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5)
        obs2 = make_obs(obs_id="b", jd=2460001.5)
        nights = _group_by_night((obs1, obs2))
        assert len(nights) == 2


class TestDetectPipeline:
    def test_empty_input(self):
        result = detect((), mpc_cross_match=False)
        assert len(result.candidates) == 0
        assert len(result.known_matches) == 0

    def test_single_obs_no_candidate(self):
        obs = make_obs(real_bogus=0.9)
        result = detect((obs,), mpc_cross_match=False)
        # Need ≥2 obs for a moving pair
        assert len(result.candidates) == 0

    def test_stationary_pair_no_candidate(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5, real_bogus=0.9)
        obs2 = make_obs(obs_id="b", jd=2460001.5, real_bogus=0.9)  # same RA/Dec
        result = detect((obs1, obs2), mpc_cross_match=False)
        assert len(result.candidates) == 0

    def test_moving_pair_detected(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5, ra_deg=180.0, real_bogus=0.9)
        # Move 0.01 deg in RA over 1 hr → 36 arcsec/hr — within [0.01, 60] limit
        obs2 = make_obs(obs_id="b", jd=2460000.5 + 1 / 24, ra_deg=180.01, real_bogus=0.9)
        result = detect((obs1, obs2), mpc_cross_match=False)
        assert len(result.candidates) >= 1

    def test_rb_filter_removes_bogus(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5, ra_deg=180.0, real_bogus=0.2)
        obs2 = make_obs(obs_id="b", jd=2460000.5 + 1 / 24, ra_deg=180.05, real_bogus=0.2)
        result = detect((obs1, obs2), real_bogus_threshold=0.65, mpc_cross_match=False)
        assert len(result.candidates) == 0

    def test_provenance_counts(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5, ra_deg=180.0, real_bogus=0.9)
        obs2 = make_obs(obs_id="b", jd=2460000.5 + 1 / 24, ra_deg=180.01, real_bogus=0.9)
        result = detect((obs1, obs2), mpc_cross_match=False)
        assert result.provenance.n_candidates == len(result.candidates)
        assert result.provenance.n_known_matches == 0

    def test_too_fast_motion_excluded(self):
        # > 60 arcsec/hr — exceeds solar system limit
        obs1 = make_obs(obs_id="a", jd=2460000.5, ra_deg=180.0, real_bogus=0.9)
        obs2 = make_obs(obs_id="b", jd=2460000.5 + 1 / 24, ra_deg=181.0, real_bogus=0.9)
        result = detect((obs1, obs2), mpc_cross_match=False)
        assert len(result.candidates) == 0


class TestIsStreak:
    def _make_streak_cutout(self) -> str:
        # Highly elongated Gaussian along x-axis (sigma_x >> sigma_y)
        y, x = np.indices((63, 63))
        arr = np.exp(-((x - 31) ** 2 / 400.0 + (y - 31) ** 2 / 2.0)).astype(np.float32)
        arr *= 100.0
        raw = arr.tobytes()
        return base64.b64encode(raw).decode()

    def _make_round_cutout(self) -> str:
        y, x = np.indices((63, 63))
        arr = np.exp(-((x - 31) ** 2 + (y - 31) ** 2) / 8.0).astype(np.float32)
        raw = arr.tobytes()
        return base64.b64encode(raw).decode()

    def test_no_cutout_returns_false(self):
        obs = make_obs()
        assert _is_streak(obs) is False

    def test_streak_detected(self):
        obs = make_obs(cutout_difference=self._make_streak_cutout())
        assert _is_streak(obs) is True

    def test_round_source_not_streak(self):
        obs = make_obs(cutout_difference=self._make_round_cutout())
        assert _is_streak(obs) is False

    def test_bad_base64_returns_false(self):
        obs = make_obs(cutout_difference="not-valid-base64!!!")
        assert _is_streak(obs) is False

    def test_zero_array_returns_false(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        raw = arr.tobytes()
        b64 = base64.b64encode(raw).decode()
        obs = make_obs(cutout_difference=b64)
        assert _is_streak(obs) is False


class TestCrossMatchMpc:
    def test_match_found(self):
        obs = make_obs(ra_deg=180.0, dec_deg=10.0)
        ephem = [{"designation": "Ceres", "ra": 180.0, "dec": 10.0}]
        match = _cross_match_mpc(obs, ephem, match_radius_arcsec=5.0)
        assert match is not None
        assert match.mpc_designation == "Ceres"

    def test_no_match_far(self):
        obs = make_obs(ra_deg=180.0, dec_deg=10.0)
        ephem = [{"designation": "Ceres", "ra": 181.0, "dec": 10.0}]
        match = _cross_match_mpc(obs, ephem, match_radius_arcsec=5.0)
        assert match is None

    def test_empty_ephem(self):
        obs = make_obs()
        assert _cross_match_mpc(obs, [], match_radius_arcsec=5.0) is None


class TestFindMovingSources:
    def test_too_slow_motion_excluded(self):
        # Essentially stationary — rate < 0.01 arcsec/hr
        obs1 = make_obs(obs_id="a", jd=2460000.5, ra_deg=180.0)
        obs2 = make_obs(obs_id="b", jd=2460001.5, ra_deg=180.0)
        result = _find_moving_sources([obs1, obs2])
        assert len(result) == 0

    def test_valid_motion_pair(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5, ra_deg=180.0)
        obs2 = make_obs(obs_id="b", jd=2460000.5 + 1 / 24, ra_deg=180.01)
        result = _find_moving_sources([obs1, obs2])
        assert len(result) == 1
        assert result[0].apparent_motion_arcsec_per_hr is not None
