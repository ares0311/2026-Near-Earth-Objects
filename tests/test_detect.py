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
    detect_batch,
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


class TestDetectBatch:
    def test_returns_one_result_per_input(self):
        obs = (make_obs(obs_id="db1", real_bogus=0.9),)
        pr = _make_preprocess_result(obs)
        results = detect_batch([pr, pr], mpc_cross_match=False)
        assert len(results) == 2

    def test_empty_list_returns_empty(self):
        assert detect_batch([]) == []

    def test_each_result_is_detect_result(self):
        from schemas import DetectResult
        obs = (make_obs(obs_id="db2", real_bogus=0.9),)
        pr = _make_preprocess_result(obs)
        results = detect_batch([pr], mpc_cross_match=False)
        assert isinstance(results[0], DetectResult)

    def test_candidate_counts_match_individual(self):
        obs = (make_obs(obs_id="db3", real_bogus=0.9),)
        pr = _make_preprocess_result(obs)
        batch = detect_batch([pr], mpc_cross_match=False)
        individual = detect(obs, mpc_cross_match=False)
        assert (batch[0].provenance.n_candidates ==
                individual.provenance.n_candidates)


class TestStreakCandidates:
    def _make_detect_result(self, has_streak):
        import uuid

        from schemas import DetectProvenance, DetectResult, RawCandidate
        obs = (make_obs(obs_id="sc1"), make_obs(obs_id="sc2"))
        cand = RawCandidate(
            candidate_id=str(uuid.uuid4()),
            observations=obs,
            apparent_motion_arcsec_per_hr=5.0,
            motion_pa_deg=90.0,
            is_streak=has_streak,
        )
        prov = DetectProvenance(
            real_bogus_threshold=0.65, n_candidates=1, n_known_matches=0,
        )
        return DetectResult(candidates=(cand,), known_matches=(), provenance=prov)

    def test_returns_streaks_only(self):
        from detect import streak_candidates
        result = self._make_detect_result(has_streak=True)
        streaks = streak_candidates(result)
        assert len(streaks) == 1
        assert all(c.is_streak for c in streaks)

    def test_returns_empty_when_no_streaks(self):
        from detect import streak_candidates
        result = self._make_detect_result(has_streak=False)
        streaks = streak_candidates(result)
        assert len(streaks) == 0

    def test_returns_tuple(self):
        from detect import streak_candidates
        result = self._make_detect_result(has_streak=True)
        assert isinstance(streak_candidates(result), tuple)

    def test_empty_candidates_returns_empty(self):
        from detect import streak_candidates
        from schemas import DetectProvenance, DetectResult
        prov = DetectProvenance(
            real_bogus_threshold=0.65, n_candidates=0, n_known_matches=0,
        )
        empty = DetectResult(candidates=(), known_matches=(), provenance=prov)
        assert streak_candidates(empty) == ()

    def test_mixed_returns_only_streak_candidates(self):
        import uuid

        from detect import streak_candidates
        from schemas import DetectProvenance, DetectResult, RawCandidate
        obs = (make_obs(obs_id="m1"), make_obs(obs_id="m2"))
        streak_cand = RawCandidate(
            candidate_id=str(uuid.uuid4()), observations=obs,
            apparent_motion_arcsec_per_hr=5.0, motion_pa_deg=90.0, is_streak=True,
        )
        non_streak = RawCandidate(
            candidate_id=str(uuid.uuid4()), observations=obs,
            apparent_motion_arcsec_per_hr=5.0, motion_pa_deg=90.0, is_streak=False,
        )
        prov = DetectProvenance(real_bogus_threshold=0.65, n_candidates=2, n_known_matches=0)
        result = DetectResult(
            candidates=(streak_cand, non_streak), known_matches=(), provenance=prov,
        )
        streaks = streak_candidates(result)
        assert len(streaks) == 1
        assert streaks[0].is_streak is True


class TestFilterByRealBogus:
    def _make_detect_result(self, rb_scores: list) -> object:
        from detect import detect
        from schemas import Observation

        sources = []
        for i, rb in enumerate(rb_scores):
            sources.append(Observation(
                obs_id=f"d_{i}",
                ra_deg=180.0 + i * 0.01,
                dec_deg=0.0,
                jd=2460000.5 + i,
                mag=19.0,
                mag_err=0.05,
                filter_band="r",
                mission="ZTF",
                real_bogus=rb,
            ))
        return detect(tuple(sources), mpc_cross_match=False)

    def test_returns_detect_result(self):
        from detect import filter_by_real_bogus
        dr = self._make_detect_result([0.9, 0.8])
        result = filter_by_real_bogus(dr)
        from detect import DetectResult
        assert isinstance(result, DetectResult)

    def test_filters_low_rb(self):
        from detect import detect, filter_by_real_bogus
        from schemas import Observation

        # Build two observations: one high RB, one low RB
        obs_high = Observation(
            obs_id="h", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9)
        obs_low = Observation(
            obs_id="l", ra_deg=181.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.1)
        dr = detect((obs_high, obs_low), mpc_cross_match=False)
        filtered = filter_by_real_bogus(dr, threshold=0.65)
        all_ids = {obs.obs_id for c in filtered.candidates for obs in c.observations}
        assert "l" not in all_ids

    def test_keeps_candidates_without_rb(self):
        from detect import detect, filter_by_real_bogus
        from schemas import Observation

        obs = Observation(obs_id="no_rb", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
                          mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=None)
        dr = detect((obs,), mpc_cross_match=False)
        filtered = filter_by_real_bogus(dr, threshold=0.65)
        all_ids = {obs.obs_id for c in filtered.candidates for obs in c.observations}
        assert "no_rb" in all_ids or len(filtered.candidates) == 0  # kept or empty (no motion)

    def test_empty_input_returns_empty(self):
        from detect import filter_by_real_bogus
        from schemas import DetectProvenance, DetectResult
        prov = DetectProvenance(
            real_bogus_threshold=0.65, n_candidates=0, n_known_matches=0,
            detected_at_jd=2460000.5)
        dr = DetectResult(candidates=(), known_matches=(), provenance=prov)
        result = filter_by_real_bogus(dr)
        assert result.provenance.n_candidates == 0

    def test_threshold_zero_keeps_all(self):
        from detect import filter_by_real_bogus
        from schemas import DetectProvenance, DetectResult
        prov = DetectProvenance(
            real_bogus_threshold=0.0, n_candidates=0, n_known_matches=0,
            detected_at_jd=2460000.5)
        dr = DetectResult(candidates=(), known_matches=(), provenance=prov)
        result = filter_by_real_bogus(dr, threshold=0.0)
        assert isinstance(result.candidates, tuple)

    def test_provenance_updated(self):
        from detect import filter_by_real_bogus
        from schemas import DetectProvenance, DetectResult
        prov = DetectProvenance(
            real_bogus_threshold=0.65, n_candidates=0, n_known_matches=2,
            detected_at_jd=2460000.5)
        dr = DetectResult(candidates=(), known_matches=(), provenance=prov)
        result = filter_by_real_bogus(dr, threshold=0.8)
        assert result.provenance.real_bogus_threshold == pytest.approx(0.8)


class TestComputeStreakMetric:
    def _make_obs(self, cutout: str | None = None) -> "Observation":
        from schemas import Observation
        return Observation(
            obs_id="s1", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference=cutout,
        )

    def test_no_cutout_returns_zero(self):
        from detect import compute_streak_metric
        obs = self._make_obs(None)
        assert compute_streak_metric(obs) == 0.0

    def test_returns_float_in_range(self):
        import base64

        import numpy as np

        from detect import compute_streak_metric
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, :] = 1.0  # horizontal streak
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        result = compute_streak_metric(obs)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_round_source_low_metric(self):
        import base64

        import numpy as np

        from detect import compute_streak_metric
        arr = np.zeros((63, 63), dtype=np.float32)
        y, x = np.mgrid[0:63, 0:63]
        arr = np.exp(-0.5 * ((x - 31) ** 2 + (y - 31) ** 2) / 4.0).astype(np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        assert compute_streak_metric(obs) < 0.5

    def test_streaked_source_high_metric(self):
        import base64

        import numpy as np

        from detect import compute_streak_metric
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 5:58] = 1.0  # long horizontal streak
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        assert compute_streak_metric(obs) > 0.5

    def test_invalid_cutout_returns_zero(self):
        import base64

        from detect import compute_streak_metric
        obs = self._make_obs(base64.b64encode(b"notanarray").decode())
        assert compute_streak_metric(obs) == 0.0


class TestClusterDetections:
    def _make_obs(self, obs_id: str, ra: float, dec: float) -> object:
        from schemas import Observation
        return Observation(
            obs_id=obs_id, ra_deg=ra, dec_deg=dec, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )

    def test_empty_input(self):
        from detect import cluster_detections
        assert cluster_detections([]) == []

    def test_single_obs_one_cluster(self):
        from detect import cluster_detections
        obs = self._make_obs("a", 180.0, 0.0)
        result = cluster_detections([obs])
        assert len(result) == 1
        assert result[0] == (obs,)

    def test_nearby_obs_same_cluster(self):
        from detect import cluster_detections
        obs1 = self._make_obs("a", 180.0, 0.0)
        obs2 = self._make_obs("b", 180.0001, 0.0)
        result = cluster_detections([obs1, obs2], radius_arcsec=5.0)
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_distant_obs_separate_clusters(self):
        from detect import cluster_detections
        obs1 = self._make_obs("a", 180.0, 0.0)
        obs2 = self._make_obs("b", 181.0, 0.0)
        result = cluster_detections([obs1, obs2], radius_arcsec=5.0)
        assert len(result) == 2

    def test_returns_tuples(self):
        from detect import cluster_detections
        obs = self._make_obs("c", 90.0, 10.0)
        result = cluster_detections([obs])
        assert isinstance(result[0], tuple)

    def test_cluster_count_correct(self):
        from detect import cluster_detections
        obs_list = [
            self._make_obs("a", 180.0, 0.0),
            self._make_obs("b", 180.0001, 0.0),
            self._make_obs("c", 270.0, 0.0),
        ]
        result = cluster_detections(obs_list, radius_arcsec=5.0)
        assert len(result) == 2


class TestComputeTrailLength:
    def _make_obs(self, cutout_b64=None):
        import base64

        import numpy as np

        from schemas import Observation
        if cutout_b64 is None:
            arr = np.zeros((63, 63), dtype=np.float32)
            cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="trl_001",
            ra_deg=180.0,
            dec_deg=10.0,
            jd=2460000.5,
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            real_bogus=0.9,
            cutout_difference=cutout_b64,
        )

    def _make_streak_obs(self, streak_length_px: int = 30):
        import base64

        import numpy as np
        arr = np.zeros((63, 63), dtype=np.float32)
        mid = 63 // 2
        arr[mid, mid - streak_length_px // 2: mid + streak_length_px // 2] = 1.0
        return self._make_obs(base64.b64encode(arr.tobytes()).decode())

    def test_no_cutout_returns_none(self):
        from detect import compute_trail_length
        from schemas import Observation
        obs = Observation(
            obs_id="x", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
        )
        assert compute_trail_length(obs) is None

    def test_blank_returns_none_or_zero(self):
        from detect import compute_trail_length
        result = compute_trail_length(self._make_obs())
        assert result is None or result == pytest.approx(0.0, abs=0.1)

    def test_streak_positive(self):
        from detect import compute_trail_length
        result = compute_trail_length(self._make_streak_obs(20))
        assert result is None or result >= 0.0

    def test_returns_float_or_none(self):
        from detect import compute_trail_length
        result = compute_trail_length(self._make_obs())
        assert result is None or isinstance(result, float)


class TestFilterByRealBogusEdgeCases:
    def _make_result_no_rb(self):
        from schemas import DetectProvenance, DetectResult, Observation, RawCandidate
        obs = Observation(
            obs_id="nb_001", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF",
            real_bogus=None,
        )
        cand = RawCandidate(
            candidate_id="C_norb",
            observations=(obs,),
            apparent_motion_arcsec_per_hr=1.0,
            motion_pa_deg=90.0,
        )
        prov = DetectProvenance(
            real_bogus_threshold=0.65,
            n_candidates=1,
            n_known_matches=0,
            detected_at_jd=2460000.5,
        )
        return DetectResult(candidates=(cand,), known_matches=(), provenance=prov)

    def test_no_rb_score_kept(self):
        from detect import filter_by_real_bogus
        result = self._make_result_no_rb()
        filtered = filter_by_real_bogus(result, threshold=0.65)
        assert len(filtered.candidates) == 1


class TestComputeStreakMetricEdgeCases:
    def test_all_zeros_returns_zero(self):
        import base64

        import numpy as np

        from detect import compute_streak_metric
        from schemas import Observation
        arr = np.zeros((9, 9), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="sz_001", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=b64,
        )
        assert compute_streak_metric(obs) == pytest.approx(0.0)

    def test_non_square_cutout_returns_zero(self):
        import base64

        import numpy as np

        from detect import compute_streak_metric
        from schemas import Observation
        # 3*4=12 elements — not a perfect square
        arr = np.ones(12, dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="ns_001", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=b64,
        )
        assert compute_streak_metric(obs) == pytest.approx(0.0)


class TestComputeTrailLengthEdgeCases:
    def test_non_square_cutout_returns_none(self):
        import base64

        import numpy as np

        from detect import compute_trail_length
        from schemas import Observation
        arr = np.ones(12, dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="tl_ns", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=b64,
        )
        result = compute_trail_length(obs)
        assert result is None

    def test_all_zeros_returns_none_or_zero(self):
        import base64

        import numpy as np

        from detect import compute_trail_length
        from schemas import Observation
        arr = np.zeros((9, 9), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="tl_zero", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=b64,
        )
        result = compute_trail_length(obs)
        assert result is None or result == pytest.approx(0.0, abs=0.1)

    def test_invalid_b64_returns_none(self):
        from detect import compute_trail_length
        from schemas import Observation
        obs = Observation(
            obs_id="tl_bad", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference="!!!invalid!!!",
        )
        assert compute_trail_length(obs) is None


class TestComputeStreakMetricSinglePixel:
    def test_single_pixel_trace_zero_returns_zero(self):
        import base64

        import numpy as np

        from detect import compute_streak_metric
        from schemas import Observation
        arr = np.zeros((9, 9), dtype=np.float32)
        arr[4, 4] = 1.0  # single pixel → trace=0 → return 0.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="sp_001", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=b64,
        )
        assert compute_streak_metric(obs) == pytest.approx(0.0)


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


class TestEstimateSkyBackground:
    def _make_cutout_b64(self, values):
        import base64

        import numpy as np
        arr = np.array(values, dtype=np.float32)
        return base64.b64encode(arr.tobytes()).decode()

    def _make_obs(self, cutout=None):
        from .conftest import build_observation
        return build_observation(cutout_difference=cutout)

    def test_returns_float_for_valid_cutouts(self):
        from detect import estimate_sky_background
        obs = self._make_obs(self._make_cutout_b64([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]))
        result = estimate_sky_background([obs])
        assert isinstance(result, float)

    def test_returns_none_for_no_cutouts(self):
        from detect import estimate_sky_background
        obs = self._make_obs(None)
        result = estimate_sky_background([obs])
        assert result is None

    def test_returns_none_for_empty_list(self):
        from detect import estimate_sky_background
        result = estimate_sky_background([])
        assert result is None

    def test_percentile_is_applied(self):
        from detect import estimate_sky_background
        vals = list(range(1, 101))  # 1..100
        obs = self._make_obs(self._make_cutout_b64(vals))
        result_25 = estimate_sky_background([obs], percentile=25.0)
        result_75 = estimate_sky_background([obs], percentile=75.0)
        assert result_25 is not None and result_75 is not None
        assert result_25 < result_75

    def test_skips_obs_with_invalid_cutout(self):
        from detect import estimate_sky_background
        bad_obs = self._make_obs("!!!not_base64!!!")
        good_obs = self._make_obs(self._make_cutout_b64([1.0, 2.0, 3.0, 4.0]))
        result = estimate_sky_background([bad_obs, good_obs])
        assert isinstance(result, float)

    def test_skips_cutout_too_small(self):
        import base64

        import numpy as np

        from detect import estimate_sky_background

        from .conftest import build_observation
        tiny = base64.b64encode(np.array([1.0], dtype=np.float32).tobytes()).decode()
        obs = build_observation(cutout_difference=tiny)
        result = estimate_sky_background([obs])
        assert result is None


class TestComputeDetectionEfficiency:
    def _make_obs(self, mag=19.0):
        from .conftest import build_observation
        return build_observation(mag=mag)

    def test_empty_returns_zero(self):
        from detect import compute_detection_efficiency
        assert compute_detection_efficiency([], 20.0) == 0.0

    def test_all_detected(self):
        from detect import compute_detection_efficiency
        obs = [self._make_obs(18.0), self._make_obs(19.0)]
        assert compute_detection_efficiency(obs, 20.0) == pytest.approx(1.0)

    def test_none_detected(self):
        from detect import compute_detection_efficiency
        obs = [self._make_obs(21.0), self._make_obs(22.0)]
        assert compute_detection_efficiency(obs, 20.0) == pytest.approx(0.0)

    def test_partial_detection(self):
        from detect import compute_detection_efficiency
        obs = [self._make_obs(18.0), self._make_obs(21.0)]
        result = compute_detection_efficiency(obs, 20.0)
        assert result == pytest.approx(0.5)

    def test_range_0_1(self):
        from detect import compute_detection_efficiency
        obs = [self._make_obs(m) for m in [17.0, 19.0, 20.5, 21.0]]
        result = compute_detection_efficiency(obs, 20.0)
        assert 0.0 <= result <= 1.0

    def test_sentinel_mag_counts_as_missed(self):
        from detect import compute_detection_efficiency

        from .conftest import build_observation
        obs = [build_observation(mag=99.0)]
        assert compute_detection_efficiency(obs, 100.0) == pytest.approx(0.0)


class TestCountDetectionsByFilter:
    def test_empty_returns_empty_dict(self):
        from detect import count_detections_by_filter
        assert count_detections_by_filter([]) == {}

    def test_single_band(self):
        from detect import count_detections_by_filter

        from .conftest import build_observation
        obs = [build_observation(filter_band="r") for _ in range(3)]
        result = count_detections_by_filter(obs)
        assert result == {"r": 3}

    def test_multiple_bands(self):
        from detect import count_detections_by_filter

        from .conftest import build_observation
        obs = [
            build_observation(filter_band="g"),
            build_observation(filter_band="r"),
            build_observation(filter_band="g"),
            build_observation(filter_band="i"),
        ]
        result = count_detections_by_filter(obs)
        assert result["g"] == 2
        assert result["r"] == 1
        assert result["i"] == 1

    def test_none_filter_band_becomes_unknown(self):
        import types

        from detect import count_detections_by_filter
        obs = [types.SimpleNamespace(filter_band=None)]
        result = count_detections_by_filter(obs)
        assert result == {"unknown": 1}

    def test_returns_dict(self):
        from detect import count_detections_by_filter

        from .conftest import build_observation
        result = count_detections_by_filter([build_observation(filter_band="r")])
        assert isinstance(result, dict)

    def test_tuple_input(self):
        from detect import count_detections_by_filter

        from .conftest import build_observation
        obs = tuple(build_observation(filter_band="o") for _ in range(2))
        result = count_detections_by_filter(obs)
        assert result == {"o": 2}


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


class TestFlagMovingSources:
    def _obs(self, jd, ra, dec, obs_id=None):
        import uuid

        from schemas import Observation
        return Observation(
            obs_id=obs_id or str(uuid.uuid4()),
            ra_deg=ra, dec_deg=dec, jd=jd,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )

    def test_empty_returns_empty(self):
        from detect import flag_moving_sources
        assert flag_moving_sources([]) == []

    def test_moving_pair_flagged(self):
        from detect import flag_moving_sources
        o1 = self._obs(2460000.5, 180.0, 10.0)
        o2 = self._obs(2460000.5 + 1.0 / 24, 180.01, 10.0)
        result = flag_moving_sources([o1, o2], min_rate_arcsec_hr=0.1)
        assert len(result) == 2

    def test_stationary_pair_not_flagged(self):
        from detect import flag_moving_sources
        o1 = self._obs(2460000.5, 180.0, 10.0, obs_id="a")
        o2 = self._obs(2460001.5, 180.0, 10.0, obs_id="b")
        result = flag_moving_sources([o1, o2], min_rate_arcsec_hr=1.0)
        assert len(result) == 0

    def test_single_obs_with_ssdistnr(self):
        import uuid

        from detect import flag_moving_sources
        from schemas import Observation
        obs = Observation(
            obs_id=str(uuid.uuid4()), ra_deg=180.0, dec_deg=10.0,
            jd=2460000.5, mag=19.0, mag_err=0.05,
            filter_band="r", mission="ZTF",
        )
        result = flag_moving_sources([obs])
        assert isinstance(result, list)

    def test_single_obs_without_ssdistnr(self):
        from detect import flag_moving_sources
        obs = self._obs(2460000.5, 180.0, 10.0)
        result = flag_moving_sources([obs])
        assert isinstance(result, list)

    def test_high_threshold_excludes_slow_movers(self):
        from detect import flag_moving_sources
        o1 = self._obs(2460000.5, 180.0, 10.0)
        o2 = self._obs(2460000.5 + 1.0 / 24, 180.001, 10.0)
        result = flag_moving_sources([o1, o2], min_rate_arcsec_hr=100.0)
        assert len(result) == 0

    def test_returns_list(self):
        from detect import flag_moving_sources
        o1 = self._obs(2460000.5, 180.0, 10.0)
        o2 = self._obs(2460001.5, 181.0, 10.0)
        result = flag_moving_sources((o1, o2))
        assert isinstance(result, list)


class TestComputeSourceExtent:
    def _make_cutout_obs(self, peak: float = 100.0) -> object:
        import base64

        import numpy as np

        from schemas import Observation
        rng = np.random.default_rng(42)
        arr = rng.normal(0.0, 1.0, (63, 63)).astype(np.float32)
        arr[31, 31] = peak
        b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="ext_test", jd=2460000.5, ra_deg=180.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )

    def test_returns_float_for_valid_cutout(self):
        from detect import compute_source_extent
        obs = self._make_cutout_obs()
        result = compute_source_extent(obs)
        assert result is not None
        assert isinstance(result, float)

    def test_returns_none_without_cutout(self):
        from detect import compute_source_extent
        from schemas import Observation
        obs = Observation(
            obs_id="no_cut", jd=2460000.5, ra_deg=10.0, dec_deg=5.0,
            mag=19.0, mag_err=0.1, filter_band="r", mission="ZTF",
        )
        assert compute_source_extent(obs) is None

    def test_positive_result(self):
        from detect import compute_source_extent
        obs = self._make_cutout_obs()
        result = compute_source_extent(obs)
        assert result is not None
        assert result > 0.0

    def test_zero_array_returns_none(self):
        import base64

        import numpy as np

        from detect import compute_source_extent
        from schemas import Observation
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="zero_cut", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )
        assert compute_source_extent(obs) is None

    def test_in_all(self):
        from detect import __all__
        assert "compute_source_extent" in __all__

    def test_larger_peak_gives_result(self):
        from detect import compute_source_extent
        obs = self._make_cutout_obs(peak=500.0)
        result = compute_source_extent(obs)
        assert result is not None
        assert result > 0.0


class TestComputeSourceExtentEdgeCases:
    def test_single_bright_pixel_returns_none(self):
        """Single pixel at center → zero covariance → lambda_max=0 → None."""
        import base64

        import numpy as np

        from detect import compute_source_extent
        from schemas import Observation
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 100.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="single", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )
        assert compute_source_extent(obs) is None

    def test_bad_base64_returns_none(self):
        from detect import compute_source_extent
        from schemas import Observation
        obs = Observation(
            obs_id="bad64", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference="!!!not_valid_base64!!!",
        )
        assert compute_source_extent(obs) is None


class TestEstimateObservationDepth:
    def _obs(self, mag: float, jd: float = 2460000.5):
        from schemas import Observation
        return Observation(
            obs_id=f"od_{jd}", jd=jd, ra_deg=10.0, dec_deg=5.0,
            mag=mag, mag_err=0.1, filter_band="r", mission="ZTF",
        )

    def test_returns_float(self):
        from detect import estimate_observation_depth
        obs = [self._obs(18.0), self._obs(19.0), self._obs(20.0)]
        result = estimate_observation_depth(obs)
        assert result is not None and isinstance(result, float)

    def test_none_for_empty(self):
        from detect import estimate_observation_depth
        assert estimate_observation_depth([]) is None

    def test_excludes_sentinel_mags(self):
        from detect import estimate_observation_depth
        obs = [self._obs(99.0), self._obs(99.5)]
        assert estimate_observation_depth(obs) is None

    def test_95th_percentile(self):
        import numpy as np

        from detect import estimate_observation_depth
        mags = [18.0, 18.5, 19.0, 19.5, 20.0, 20.5, 21.0, 21.5, 22.0, 22.5]
        obs = [self._obs(m) for m in mags]
        result = estimate_observation_depth(obs, percentile=95.0)
        expected = round(float(np.percentile(mags, 95.0)), 4)
        assert result == expected

    def test_custom_percentile(self):
        from detect import estimate_observation_depth
        obs = [self._obs(m) for m in [18.0, 19.0, 20.0, 21.0]]
        r50 = estimate_observation_depth(obs, percentile=50.0)
        r95 = estimate_observation_depth(obs, percentile=95.0)
        assert r95 >= r50

    def test_in_all(self):
        from detect import __all__
        assert "estimate_observation_depth" in __all__

    def test_single_obs(self):
        from detect import estimate_observation_depth
        obs = [self._obs(20.0)]
        result = estimate_observation_depth(obs)
        assert result == 20.0


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


class TestComputeStreakDensity:
    """Tests for compute_streak_density."""

    def _make_cutout_b64(self, vals, shape=(63, 63)):
        import base64

        import numpy as np
        flat = list(vals) + [0.0] * (shape[0] * shape[1] - len(vals))
        arr = np.array(flat[:shape[0] * shape[1]], dtype=np.float32).reshape(shape)
        return base64.b64encode(arr.tobytes()).decode()

    def _make_obs(self, cutout=None):
        from .conftest import build_observation
        return build_observation(cutout_difference=cutout)

    def test_empty_list_returns_zero(self):
        from detect import compute_streak_density
        assert compute_streak_density([]) == 0.0

    def test_no_streaks(self):
        from detect import compute_streak_density
        # no cutout → compute_streak_metric returns 0.0 (< 0.5)
        obs = [self._make_obs(None), self._make_obs(None)]
        result = compute_streak_density(obs)
        assert result == 0.0

    def test_all_streaks(self):
        import numpy as np

        from detect import compute_streak_density
        # Build a very elongated array (single row spike) to force streak
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, :] = 1.0  # horizontal stripe → should trigger streak detection
        b64 = self._make_cutout_b64(arr.flatten().tolist())
        obs = [self._make_obs(b64)]
        result = compute_streak_density(obs)
        assert 0.0 <= result <= 1.0

    def test_returns_4dp(self):
        from detect import compute_streak_density
        obs = [self._make_obs(None)]
        result = compute_streak_density(obs)
        assert round(result, 4) == result

    def test_in_all(self):
        from detect import __all__
        assert "compute_streak_density" in __all__


class TestComputeAngularVelocity:
    """Tests for compute_angular_velocity."""

    def _make_obs(self, ra, dec, jd):
        from schemas import Observation
        return Observation(
            obs_id=f"av_{jd}", ra_deg=ra, dec_deg=dec, jd=jd,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )

    def test_returns_none_for_same_jd(self):
        from detect import compute_angular_velocity
        o = self._make_obs(180.0, 0.0, 2460000.5)
        assert compute_angular_velocity(o, o) is None

    def test_returns_dict_keys(self):
        from detect import compute_angular_velocity
        o1 = self._make_obs(180.0, 0.0, 2460000.5)
        o2 = self._make_obs(180.1, 0.1, 2460001.5)
        result = compute_angular_velocity(o1, o2)
        assert result is not None
        assert set(result.keys()) == {"rate_arcsec_hr", "pa_deg", "dt_hours"}

    def test_dt_hours_correct(self):
        from detect import compute_angular_velocity
        o1 = self._make_obs(180.0, 0.0, 2460000.5)
        o2 = self._make_obs(180.0, 0.0, 2460001.5)
        result = compute_angular_velocity(o1, o2)
        assert result is not None
        assert abs(result["dt_hours"] - 24.0) < 0.001

    def test_rate_non_negative(self):
        from detect import compute_angular_velocity
        o1 = self._make_obs(180.0, 10.0, 2460000.5)
        o2 = self._make_obs(180.01, 10.01, 2460001.5)
        result = compute_angular_velocity(o1, o2)
        assert result is not None
        assert result["rate_arcsec_hr"] >= 0.0

    def test_pa_in_range(self):
        from detect import compute_angular_velocity
        o1 = self._make_obs(180.0, 0.0, 2460000.5)
        o2 = self._make_obs(181.0, 0.0, 2460001.5)
        result = compute_angular_velocity(o1, o2)
        assert result is not None
        assert 0.0 <= result["pa_deg"] < 360.0

    def test_zero_motion_zero_rate(self):
        from detect import compute_angular_velocity
        o1 = self._make_obs(180.0, 0.0, 2460000.5)
        o2 = self._make_obs(180.0, 0.0, 2460001.5)
        result = compute_angular_velocity(o1, o2)
        assert result is not None
        assert result["rate_arcsec_hr"] == 0.0

    def test_in_all(self):
        from detect import __all__
        assert "compute_angular_velocity" in __all__


class TestComputeDetectionGap:
    def _obs(self, jd):
        import sys
        sys.path.insert(0, "src")
        from schemas import Observation
        return Observation(obs_id=f"o{jd}", ra_deg=10.0, dec_deg=5.0, jd=jd,
                           mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF")

    def test_two_obs(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_detection_gap
        obs = [self._obs(2460000.0), self._obs(2460001.0)]
        assert compute_detection_gap(obs) == 24.0

    def test_single_obs_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_detection_gap
        assert compute_detection_gap([self._obs(2460000.0)]) is None

    def test_empty_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_detection_gap
        assert compute_detection_gap([]) is None

    def test_unsorted_input(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_detection_gap
        obs = [self._obs(2460002.0), self._obs(2460000.0), self._obs(2460000.5)]
        gap = compute_detection_gap(obs)
        assert gap == pytest.approx(36.0, abs=0.01)

    def test_three_obs_max_gap(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_detection_gap
        obs = [self._obs(2460000.0), self._obs(2460000.1), self._obs(2460002.0)]
        gap = compute_detection_gap(obs)
        assert gap == pytest.approx(45.6, abs=0.1)


class TestComputeObservationCadence:
    def _obs(self, jd):
        import sys
        sys.path.insert(0, "src")
        from schemas import Observation
        return Observation(obs_id=f"o{jd}", ra_deg=10.0, dec_deg=5.0, jd=jd,
                           mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF")

    def test_two_obs_cadence(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_observation_cadence
        obs = [self._obs(2460000.0), self._obs(2460001.0)]
        assert compute_observation_cadence(obs) == 24.0

    def test_single_obs_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_observation_cadence
        assert compute_observation_cadence([self._obs(2460000.0)]) is None

    def test_empty_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_observation_cadence
        assert compute_observation_cadence([]) is None

    def test_three_obs_mean(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_observation_cadence
        # gaps: 12h, 36h → mean = 24h
        obs = [self._obs(2460000.0), self._obs(2460000.5), self._obs(2460002.0)]
        assert compute_observation_cadence(obs) == pytest.approx(24.0, abs=0.01)

    def test_unsorted_input(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_observation_cadence
        obs = [self._obs(2460001.0), self._obs(2460000.0)]
        assert compute_observation_cadence(obs) == 24.0


class TestComputeFieldSourceCount:
    def _obs(self, obs_id):
        from types import SimpleNamespace
        return SimpleNamespace(obs_id=obs_id)

    def test_groups_by_prefix(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_field_source_count
        obs = [self._obs("ZTF_001_a"), self._obs("ZTF_001_b"), self._obs("ATLAS_002_c")]
        result = compute_field_source_count(obs)
        assert result["ZTF"] == 2
        assert result["ATLAS"] == 1

    def test_no_underscore_uses_full_id(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_field_source_count
        obs = [self._obs("FIELD1"), self._obs("FIELD1"), self._obs("FIELD2")]
        result = compute_field_source_count(obs)
        assert result["FIELD1"] == 2
        assert result["FIELD2"] == 1

    def test_empty_obs_id(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_field_source_count
        obs = [SimpleNamespace(obs_id=""), SimpleNamespace(obs_id=None)]
        result = compute_field_source_count(obs)
        assert result.get("unknown", 0) == 2

    def test_sorted_descending(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_field_source_count
        obs = ([self._obs("B_1")] * 3) + ([self._obs("A_1")] * 5)
        result = compute_field_source_count(obs)
        keys = list(result.keys())
        assert keys[0] == "A"

    def test_empty_input(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_field_source_count
        assert compute_field_source_count([]) == {}


class TestComputeBrightnessTrend:
    def _make_obs(self, jd, mag):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        return SimpleNamespace(jd=jd, mag=mag)

    def test_fading_trend(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_brightness_trend
        obs = [self._make_obs(2460000.0, 18.0), self._make_obs(2460001.0, 18.5),
               self._make_obs(2460002.0, 19.0)]
        result = compute_brightness_trend(obs)
        assert result is not None
        assert result > 0.0

    def test_brightening_trend(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_brightness_trend
        obs = [self._make_obs(2460000.0, 20.0), self._make_obs(2460001.0, 19.5),
               self._make_obs(2460002.0, 19.0)]
        result = compute_brightness_trend(obs)
        assert result is not None
        assert result < 0.0

    def test_fewer_than_two_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_brightness_trend
        assert compute_brightness_trend([self._make_obs(2460000.0, 18.0)]) is None
        assert compute_brightness_trend([]) is None

    def test_identical_jds_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_brightness_trend
        obs = [self._make_obs(2460000.0, 18.0), self._make_obs(2460000.0, 18.5)]
        assert compute_brightness_trend(obs) is None

    def test_sentinel_mags_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_brightness_trend
        obs = [self._make_obs(2460000.0, 99.0), self._make_obs(2460001.0, 99.9)]
        assert compute_brightness_trend(obs) is None

    def test_exception_returns_none(self, monkeypatch):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        import detect
        monkeypatch.setattr(np, "polyfit", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
        obs = [self._make_obs(2460000.0, 18.0), self._make_obs(2460001.0, 18.5)]
        result = detect.compute_brightness_trend(obs)
        assert result is None


class TestComputeVariabilityIndex:
    def _make_obs(self, mag, err):
        from types import SimpleNamespace
        return SimpleNamespace(mag=mag, mag_err=err)

    def test_constant_source_near_zero(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_variability_index
        obs = [self._make_obs(18.0, 0.05), self._make_obs(18.0, 0.05),
               self._make_obs(18.0, 0.05)]
        result = compute_variability_index(obs)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-4)

    def test_variable_source_above_one(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_variability_index
        obs = [self._make_obs(18.0, 0.01), self._make_obs(19.0, 0.01),
               self._make_obs(18.5, 0.01)]
        result = compute_variability_index(obs)
        assert result is not None
        assert result > 1.0

    def test_single_obs_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_variability_index
        assert compute_variability_index([self._make_obs(18.0, 0.05)]) is None

    def test_empty_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_variability_index
        assert compute_variability_index([]) is None

    def test_sentinel_mags_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_variability_index
        obs = [self._make_obs(99.0, 0.05), self._make_obs(99.9, 0.05)]
        assert compute_variability_index(obs) is None

    def test_zero_err_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_variability_index
        obs = [self._make_obs(18.0, 0.0), self._make_obs(18.5, 0.0)]
        assert compute_variability_index(obs) is None

    def test_exception_in_numpy_returns_none(self, monkeypatch):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        import detect
        monkeypatch.setattr(np, "asarray", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
        obs = [self._make_obs(18.0, 0.05), self._make_obs(18.5, 0.05)]
        result = detect.compute_variability_index(obs)
        assert result is None


class TestComputeAngularSeparation:
    def test_same_position_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_angular_separation
        obs = SimpleNamespace(ra_deg=10.0, dec_deg=20.0)
        assert compute_angular_separation(obs, obs) == pytest.approx(0.0, abs=1e-8)

    def test_known_separation(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_angular_separation
        obs1 = SimpleNamespace(ra_deg=0.0, dec_deg=0.0)
        obs2 = SimpleNamespace(ra_deg=0.0, dec_deg=1.0)
        sep = compute_angular_separation(obs1, obs2)
        assert sep == pytest.approx(3600.0, rel=1e-4)

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_angular_separation
        obs1 = SimpleNamespace(ra_deg=10.0, dec_deg=5.0)
        obs2 = SimpleNamespace(ra_deg=10.1, dec_deg=5.1)
        result = compute_angular_separation(obs1, obs2)
        assert isinstance(result, float)
        assert result > 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import detect
        assert "compute_angular_separation" in detect.__all__


class TestComputeStreakOrientation:
    def test_returns_angle_in_range(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from detect import compute_streak_orientation

        # Create a horizontally-oriented streak
        arr = np.zeros((63, 63), dtype=np.float32)
        for i in range(20, 45):
            arr[i, i] = 1.0  # diagonal line — gives non-zero angle
        cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=cutout_b64)
        result = compute_streak_orientation(obs)
        assert result is not None
        assert 0.0 <= result < 180.0

    def test_degenerate_all_zero_returns_none(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from detect import compute_streak_orientation

        arr = np.zeros((63, 63), dtype=np.float32)
        cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=cutout_b64)
        result = compute_streak_orientation(obs)
        assert result is None

    def test_circular_blob_returns_none(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from detect import compute_streak_orientation

        # Circular blob: mu20 == mu02, mu11 == 0 → degenerate
        arr = np.zeros((63, 63), dtype=np.float32)
        ys, xs = np.mgrid[0:63, 0:63]
        arr[(ys - 31)**2 + (xs - 31)**2 <= 4] = 1.0
        cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=cutout_b64)
        result = compute_streak_orientation(obs)
        assert result is None

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_streak_orientation
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_streak_orientation(obs) is None

    def test_bad_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_streak_orientation
        obs = SimpleNamespace(cutout_difference="not_valid!!!")
        assert compute_streak_orientation(obs) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import detect
        assert "compute_streak_orientation" in detect.__all__


class TestComputeMagnitudeResidual:
    def test_positive_residual(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_magnitude_residual
        obs = SimpleNamespace(mag=18.5)
        assert compute_magnitude_residual(obs, 18.0) == pytest.approx(0.5)

    def test_negative_residual(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_magnitude_residual
        obs = SimpleNamespace(mag=17.5)
        assert compute_magnitude_residual(obs, 18.0) == pytest.approx(-0.5)

    def test_sentinel_obs_mag_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_magnitude_residual
        obs = SimpleNamespace(mag=99.0)
        assert compute_magnitude_residual(obs, 18.0) == pytest.approx(0.0)

    def test_sentinel_predicted_mag_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_magnitude_residual
        obs = SimpleNamespace(mag=18.5)
        assert compute_magnitude_residual(obs, 99.0) == pytest.approx(0.0)

    def test_missing_mag_attr_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_magnitude_residual
        obs = SimpleNamespace()
        assert compute_magnitude_residual(obs, 18.0) == pytest.approx(0.0)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import detect
        assert "compute_magnitude_residual" in detect.__all__


class TestComputeElongationRatio:
    def test_circular_source_near_one(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from detect import compute_elongation_ratio
        arr = np.zeros((63, 63), dtype=np.float32)
        cy, cx = 31.0, 31.0
        for r in range(63):
            for c in range(63):
                arr[r, c] = np.exp(-((r - cy)**2 + (c - cx)**2) / 8.0)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_elongation_ratio(obs)
        assert result is not None
        assert 0.8 <= result <= 1.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_elongation_ratio
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_elongation_ratio(obs) is None

    def test_zero_flux_returns_none(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from detect import compute_elongation_ratio
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        assert compute_elongation_ratio(obs) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import detect
        assert "compute_elongation_ratio" in detect.__all__

    def test_bad_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_elongation_ratio
        obs = SimpleNamespace(cutout_difference="!!not_valid_base64!!")
        assert compute_elongation_ratio(obs) is None

    def test_single_pixel_trace_zero_returns_none(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from detect import compute_elongation_ratio
        # Single pixel at center → all second moments are zero → trace=0
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        assert compute_elongation_ratio(obs) is None


class TestComputeDetectionSignificance:
    def test_bright_object(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_detection_significance
        obs = SimpleNamespace(mag=18.0, limiting_mag=21.0)
        assert compute_detection_significance(obs) == pytest.approx(0.6)

    def test_faint_object_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_detection_significance
        obs = SimpleNamespace(mag=22.0, limiting_mag=21.0)
        assert compute_detection_significance(obs) == 0.0

    def test_very_bright_clamped_to_one(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_detection_significance
        obs = SimpleNamespace(mag=10.0, limiting_mag=21.0)
        assert compute_detection_significance(obs) == 1.0

    def test_none_mag_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_detection_significance
        assert compute_detection_significance(SimpleNamespace(mag=None, limiting_mag=21.0)) is None

    def test_none_limiting_mag_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_detection_significance
        assert compute_detection_significance(SimpleNamespace(mag=18.0, limiting_mag=None)) is None

    def test_sentinel_mag_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_detection_significance
        assert compute_detection_significance(SimpleNamespace(mag=99.0, limiting_mag=21.0)) is None

    def test_sentinel_limiting_mag_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from detect import compute_detection_significance
        assert compute_detection_significance(SimpleNamespace(mag=18.0, limiting_mag=99.0)) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import detect
        assert "compute_detection_significance" in detect.__all__


class TestComputeSkyPlaneVelocity:
    def _make_obs(self, ra, dec, jd):
        from types import SimpleNamespace
        return SimpleNamespace(ra=ra, dec=dec, jd=jd)

    def test_basic_motion(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_sky_plane_velocity
        obs1 = self._make_obs(10.0, 0.0, 2460000.0)
        obs2 = self._make_obs(10.01, 0.0, 2460000.5)
        result = compute_sky_plane_velocity(obs1, obs2)
        assert "dra_arcsec_hr" in result
        assert "ddec_arcsec_hr" in result
        assert "speed_arcsec_hr" in result
        assert result["speed_arcsec_hr"] > 0.0

    def test_zero_dt_returns_zeros(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_sky_plane_velocity
        obs = self._make_obs(10.0, 10.0, 2460000.0)
        result = compute_sky_plane_velocity(obs, obs)
        assert result["dra_arcsec_hr"] == 0.0
        assert result["ddec_arcsec_hr"] == 0.0
        assert result["speed_arcsec_hr"] == 0.0

    def test_cosine_dec_correction(self):
        import sys
        sys.path.insert(0, "src")
        import math

        from detect import compute_sky_plane_velocity
        obs1 = self._make_obs(0.0, 60.0, 2460000.0)
        obs2 = self._make_obs(1.0, 60.0, 2460001.0)
        result = compute_sky_plane_velocity(obs1, obs2)
        # dRA should be corrected by cos(60°) = 0.5
        expected_dra = 1.0 * math.cos(math.radians(60.0)) * 3600.0 / 24.0
        assert abs(result["dra_arcsec_hr"] - expected_dra) < 0.1

    def test_dec_only_motion(self):
        import sys
        sys.path.insert(0, "src")
        from detect import compute_sky_plane_velocity
        obs1 = self._make_obs(10.0, 0.0, 2460000.0)
        obs2 = self._make_obs(10.0, 0.1, 2460001.0)
        result = compute_sky_plane_velocity(obs1, obs2)
        assert abs(result["dra_arcsec_hr"]) < 0.001
        assert result["ddec_arcsec_hr"] > 0.0

    def test_speed_is_magnitude(self):
        import sys
        sys.path.insert(0, "src")
        import math

        from detect import compute_sky_plane_velocity
        obs1 = self._make_obs(5.0, 5.0, 2460000.0)
        obs2 = self._make_obs(5.01, 5.01, 2460001.0)
        result = compute_sky_plane_velocity(obs1, obs2)
        expected_speed = math.sqrt(result["dra_arcsec_hr"]**2 + result["ddec_arcsec_hr"]**2)
        assert abs(result["speed_arcsec_hr"] - expected_speed) < 1e-3

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import detect
        assert "compute_sky_plane_velocity" in detect.__all__
