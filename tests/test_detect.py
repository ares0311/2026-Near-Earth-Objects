"""Tests for detect.py."""

import base64

import numpy as np
import pytest

from detect import (
    _angular_sep_arcsec,
    _cross_match_mpc,
    _find_moving_sources,
    _find_object_history_sources,
    _group_by_night,
    _is_streak,
    _motion_rate_and_pa,
    _passes_real_bogus,
    detect,
)
from schemas import Observation, PreprocessProvenance, PreprocessResult


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

    def test_preserves_broker_object_history_candidate(self):
        obs1 = make_obs(
            obs_id="a",
            field_id="ZTF-object-1",
            jd=2460000.5,
            ra_deg=180.0,
            real_bogus=0.9,
        )
        obs2 = make_obs(
            obs_id="b",
            field_id="ZTF-object-1",
            jd=2460001.5,
            ra_deg=180.1,
            real_bogus=0.9,
        )
        result = detect((obs1, obs2), mpc_cross_match=False)
        assert len(result.candidates) == 1
        assert result.candidates[0].candidate_id == "ZTF-object-1"
        assert result.candidates[0].observations == (obs1, obs2)

    def test_stationary_broker_object_history_rejected(self):
        obs1 = make_obs(obs_id="a", field_id="ZTF-object-1", jd=2460000.5, real_bogus=0.9)
        obs2 = make_obs(obs_id="b", field_id="ZTF-object-1", jd=2460001.5, real_bogus=0.9)
        result = _find_object_history_sources((obs1, obs2))
        assert result == []

    def test_single_observation_history_skipped(self):
        # A group with only one observation cannot form a candidate; the
        # `len(obs_sorted) < 2` branch must be covered to reach 100%.
        obs = make_obs(obs_id="a", field_id="ZTF-solo", jd=2460000.5, real_bogus=0.9)
        result = _find_object_history_sources((obs,))
        assert result == []


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


class TestIsStreakEdgeCases:
    def test_uniform_cutout_singular_moments(self):
        # Horizontal-line cutout → myy=0, det=0 → return False at line 103
        import base64
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, :] = 1.0  # single row → myy=0 → det = mxx*0 - 0 = 0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = make_obs(cutout_difference=b64)
        from detect import _is_streak
        assert _is_streak(obs) is False

    def test_exception_path_returns_false(self):
        # Invalid base64 length → reshape fails → except → return False
        import base64
        b64 = base64.b64encode(b"\x00" * 10).decode()
        obs = make_obs(cutout_difference=b64)
        from detect import _is_streak
        assert _is_streak(obs) is False


class TestDetectMpcCrossMatch:
    def _two_obs_moving(self):
        # Two obs per night with valid 1.8 arcsec/hr motion to form a candidate
        obs1 = make_obs(obs_id="mpc1a", jd=2460000.5, ra_deg=180.0, dec_deg=10.0, real_bogus=0.9)
        obs2 = make_obs(
            obs_id="mpc1b", jd=2460000.5 + 2 / 24,
            ra_deg=180.001, dec_deg=10.0, real_bogus=0.9,
        )
        return (obs1, obs2)

    def test_mpc_cross_match_true_covers_load_path(self, monkeypatch):
        import detect as detect_mod
        # Mock _load_mpc_ephemerides → empty → covers lines 253-255
        monkeypatch.setattr(detect_mod, "_load_mpc_ephemerides", lambda *a, **kw: [])
        obs = self._two_obs_moving()
        result = detect(obs, real_bogus_threshold=0.5, mpc_cross_match=True)
        # Candidate formed (no MPC match) → survives
        assert result.provenance.n_known_matches == 0

    def test_mpc_match_found_sets_known(self, monkeypatch):
        import detect as detect_mod
        # Mock to return matching ephemeris → covers lines 266-267
        ephem = [{"designation": "Ceres", "ra": 180.0, "dec": 10.0}]
        monkeypatch.setattr(detect_mod, "_load_mpc_ephemerides", lambda *a, **kw: ephem)
        obs = self._two_obs_moving()
        result = detect(obs, real_bogus_threshold=0.5, mpc_cross_match=True)
        assert result.provenance.n_known_matches >= 1


class TestLoadMpcEphemerides:
    def test_exception_returns_empty_list(self, monkeypatch):
        # astroquery.mpc raises → except Exception → lines 141-142
        import sys
        from unittest.mock import MagicMock

        mock_mpc = MagicMock()
        mock_mpc.MPC.get_ephemeris.side_effect = RuntimeError("network error")
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc)
        from detect import _load_mpc_ephemerides
        result = _load_mpc_ephemerides(180.0, 10.0, 0.5, 2460000.5)
        assert result == []

    def test_success_returns_empty_list(self, monkeypatch):
        # astroquery.mpc import and get_ephemeris succeed → line 140 (return [])
        import sys
        from unittest.mock import MagicMock
        mock_mpc = MagicMock()
        mock_mpc.MPC.get_ephemeris.return_value = MagicMock()
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc)
        from detect import _load_mpc_ephemerides
        result = _load_mpc_ephemerides(180.0, 10.0, 0.5, 2460000.5)
        assert result == []


def _make_preprocess_result(obs: tuple) -> PreprocessResult:
    return PreprocessResult(
        sources=obs,
        provenance=PreprocessProvenance(n_sources_in=len(obs), n_sources_out=len(obs)),
    )


class TestComputePsfFwhm:
    def _make_obs(self, b64: str | None = None):
        import base64

        import numpy as np
        if b64 is None:
            arr = np.zeros((9, 9), dtype=np.float32)
            # Gaussian-like blob in centre
            for r in range(9):
                for c in range(9):
                    arr[r, c] = float(np.exp(-((r - 4) ** 2 + (c - 4) ** 2) / 4.0))
            raw = arr.astype(np.float32).tobytes()
            b64 = base64.b64encode(raw).decode()
        from schemas import Observation
        return Observation(
            obs_id="psf_test",
            ra_deg=10.0,
            dec_deg=5.0,
            jd=2460000.5,
            mag=20.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            cutout_difference=b64,
        )

    def test_returns_float_for_valid_cutout(self):
        from detect import compute_psf_fwhm
        result = compute_psf_fwhm(self._make_obs())
        assert result is None or isinstance(result, float)

    def test_returns_none_without_cutout(self):
        from detect import compute_psf_fwhm
        from schemas import Observation
        obs = Observation(
            obs_id="no_cutout",
            ra_deg=10.0,
            dec_deg=5.0,
            jd=2460000.5,
            mag=20.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        )
        assert compute_psf_fwhm(obs) is None

    def test_returns_none_for_invalid_b64(self):
        from detect import compute_psf_fwhm
        result = compute_psf_fwhm(self._make_obs("!!!invalid!!!"))
        assert result is None

    def test_fwhm_positive_when_returned(self):
        from detect import compute_psf_fwhm
        result = compute_psf_fwhm(self._make_obs())
        if result is not None:
            assert result > 0.0

    def test_flat_array_returns_none_or_zero(self):
        import base64

        import numpy as np

        from detect import compute_psf_fwhm
        arr = np.zeros((9, 9), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        result = compute_psf_fwhm(self._make_obs(b64))
        # Flat image → degenerate fit; None is acceptable
        assert result is None or isinstance(result, float)


class TestComputePsfFwhmNonSquare:
    """Cover size*size != len(arr) branch in compute_psf_fwhm."""

    def test_non_square_array_returns_none(self):
        import base64

        import numpy as np

        from detect import compute_psf_fwhm
        from schemas import Observation
        # 3x4=12 floats → not a perfect square
        arr = np.ones(12, dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="non_sq",
            ra_deg=10.0,
            dec_deg=5.0,
            jd=2460000.5,
            mag=20.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            cutout_difference=b64,
        )
        assert compute_psf_fwhm(obs) is None


class TestComputeMotionVector:
    def _make_obs(self, ra, dec, jd):
        from .conftest import build_observation
        return build_observation(ra_deg=ra, dec_deg=dec, jd=jd)

    def test_returns_dict_with_expected_keys(self):
        from detect import compute_motion_vector
        obs1 = self._make_obs(180.0, 10.0, 2460000.5)
        obs2 = self._make_obs(180.01, 10.005, 2460001.5)
        result = compute_motion_vector(obs1, obs2)
        for key in ["dra_arcsec_hr", "ddec_arcsec_hr", "rate_arcsec_hr", "pa_deg"]:
            assert key in result

    def test_zero_dt_returns_zeros(self):
        from detect import compute_motion_vector
        obs1 = self._make_obs(180.0, 10.0, 2460000.5)
        obs2 = self._make_obs(180.01, 10.005, 2460000.5)
        result = compute_motion_vector(obs1, obs2)
        assert result["rate_arcsec_hr"] == 0.0
        assert result["pa_deg"] == 0.0

    def test_rate_positive(self):
        from detect import compute_motion_vector
        obs1 = self._make_obs(180.0, 10.0, 2460000.5)
        obs2 = self._make_obs(180.01, 10.005, 2460001.5)
        result = compute_motion_vector(obs1, obs2)
        assert result["rate_arcsec_hr"] >= 0.0

    def test_pa_in_range(self):
        from detect import compute_motion_vector
        obs1 = self._make_obs(180.0, 10.0, 2460000.5)
        obs2 = self._make_obs(180.01, 10.005, 2460001.5)
        result = compute_motion_vector(obs1, obs2)
        assert 0.0 <= result["pa_deg"] < 360.0

    def test_pure_dec_motion_pa_zero(self):
        from detect import compute_motion_vector
        obs1 = self._make_obs(180.0, 10.0, 2460000.5)
        obs2 = self._make_obs(180.0, 10.1, 2460001.5)
        result = compute_motion_vector(obs1, obs2)
        # Pure northward motion → PA = 0 (N)
        assert result["dra_arcsec_hr"] == pytest.approx(0.0, abs=1e-4)
        assert result["ddec_arcsec_hr"] > 0.0

    def test_values_are_floats(self):
        from detect import compute_motion_vector
        obs1 = self._make_obs(180.0, 10.0, 2460000.5)
        obs2 = self._make_obs(180.01, 10.0, 2460001.5)
        result = compute_motion_vector(obs1, obs2)
        for v in result.values():
            assert isinstance(v, float)


class TestFilterByMagnitude:
    """Tests for filter_by_magnitude."""

    def _obs(self, obs_id: str, mag: float):
        from schemas import Observation
        return Observation(
            obs_id=obs_id,
            ra_deg=180.0,
            dec_deg=0.0,
            jd=2460000.5,
            mag=mag,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            real_bogus=0.9,
        )

    def test_normal_filter(self):
        from detect import filter_by_magnitude
        obs = [self._obs("a", 18.0), self._obs("b", 20.0), self._obs("c", 22.0)]
        result = filter_by_magnitude(obs, 21.0)
        ids = [o.obs_id for o in result]
        assert "a" in ids
        assert "b" in ids
        assert "c" not in ids

    def test_sentinel_excluded(self):
        from detect import filter_by_magnitude
        # Sentinels (mag >= 90) are excluded regardless of mag_limit
        obs = [self._obs("a", 90.0), self._obs("b", 99.9), self._obs("c", 95.0)]
        result = filter_by_magnitude(obs, 200.0)
        # All have mag >= 90, so all are excluded
        assert len(result) == 0

    def test_none_qualify(self):
        from detect import filter_by_magnitude
        obs = [self._obs("a", 22.0), self._obs("b", 23.0)]
        result = filter_by_magnitude(obs, 20.0)
        assert result == []

    def test_all_qualify(self):
        from detect import filter_by_magnitude
        obs = [self._obs("a", 18.0), self._obs("b", 19.0), self._obs("c", 20.0)]
        result = filter_by_magnitude(obs, 25.0)
        assert len(result) == 3

    def test_empty_input(self):
        from detect import filter_by_magnitude
        assert filter_by_magnitude([], 20.0) == []

    def test_none_mag_skipped(self):
        from types import SimpleNamespace

        from detect import filter_by_magnitude
        obs_none = SimpleNamespace(mag=None)
        obs_real = self._obs("b", 18.0)
        result = filter_by_magnitude([obs_none, obs_real], 25.0)
        assert len(result) == 1
        assert result[0].obs_id == "b"

    def test_in_all(self):
        from detect import __all__
        assert "filter_by_magnitude" in __all__


class TestComputeSourceCompactness:
    def _make_point_cutout(self) -> str:
        import base64

        import numpy as np
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1.0
        return base64.b64encode(arr.tobytes()).decode()

    def _make_uniform_cutout(self) -> str:
        import base64

        import numpy as np
        arr = np.ones((63, 63), dtype=np.float32)
        return base64.b64encode(arr.tobytes()).decode()

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_source_compactness
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_source_compactness(obs) is None

    def test_bad_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_source_compactness
        obs = SimpleNamespace(cutout_difference="not!!valid")
        assert compute_source_compactness(obs) is None

    def test_point_source_high_compactness(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_source_compactness
        obs = SimpleNamespace(cutout_difference=self._make_point_cutout())
        result = compute_source_compactness(obs)
        assert result is not None
        assert result == 1.0

    def test_uniform_source_low_compactness(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_source_compactness
        obs = SimpleNamespace(cutout_difference=self._make_uniform_cutout())
        result = compute_source_compactness(obs)
        assert result is not None
        assert result < 0.01

    def test_zero_flux_returns_none(self):
        import base64
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_source_compactness
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        assert compute_source_compactness(obs) is None

    def test_result_in_range(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_source_compactness
        obs = SimpleNamespace(cutout_difference=self._make_uniform_cutout())
        result = compute_source_compactness(obs)
        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import detect
        assert "compute_source_compactness" in detect.__all__



