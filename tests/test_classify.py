"""Tests for classify.py."""

import base64
import sys

import numpy as np
import pytest

from classify import (
    _arc_coverage,
    _brightness_score,
    _color_index,
    _decode_cutout_f32,
    _features_to_array,
    _lightcurve_variability,
    _load_xgb_model,
    _mean_real_bogus,
    _motion_consistency,
    _nights_score,
    _stack_predictions,
    _tier1_predict,
    _tracklet_to_sequence,
    classify,
    extract_features,
)
from schemas import CandidateFeatures, Observation, Tracklet


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="c_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.9,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def make_tracklet(n_obs: int = 4, arc_days: float = 3.0) -> Tracklet:
    obs = tuple(
        make_obs(
            obs_id=f"t_{i}",
            jd=2460000.5 + i * arc_days / max(n_obs - 1, 1),
            ra_deg=180.0 + i * 0.005,
        )
        for i in range(n_obs)
    )
    return Tracklet(
        object_id="T001",
        observations=obs,
        arc_days=arc_days,
        motion_rate_arcsec_per_hour=1.2,
        motion_pa_degrees=90.0,
    )


class TestFeatureExtraction:
    def test_real_bogus_mean(self):
        t = make_tracklet()
        rb = _mean_real_bogus(t)
        assert rb == pytest.approx(0.9, abs=1e-6)

    def test_real_bogus_none(self):
        obs = make_obs(real_bogus=None, deep_real_bogus=None)
        t = Tracklet("T", (obs,), 0.0, 0.0, 0.0)
        assert _mean_real_bogus(t) is None

    def test_arc_coverage(self):
        t = make_tracklet(arc_days=15.0)
        score = _arc_coverage(t)
        assert score == pytest.approx(0.5, abs=1e-6)

    def test_arc_coverage_clamp(self):
        t = make_tracklet(arc_days=60.0)
        score = _arc_coverage(t)
        assert score == 1.0

    def test_nights_score_two_nights(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5)
        obs2 = make_obs(obs_id="b", jd=2460001.5)
        t = Tracklet("T", (obs1, obs2), 1.0, 1.0, 0.0)
        score = _nights_score(t)
        assert 0.0 < score <= 1.0

    def test_brightness_score(self):
        t = make_tracklet()
        score = _brightness_score(t)
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_extract_features_returns_features(self):
        t = make_tracklet()
        f = extract_features(t)
        assert isinstance(f, CandidateFeatures)
        assert f.real_bogus_score is not None


class TestTier1Predict:
    def test_returns_five_classes(self):
        f = CandidateFeatures(real_bogus_score=0.9, nights_observed_score=0.5)
        proba = _tier1_predict(f, model=None)
        assert set(proba.keys()) == {
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system"
        }

    def test_probabilities_nonnegative(self):
        f = CandidateFeatures(real_bogus_score=0.7)
        proba = _tier1_predict(f, model=None)
        for v in proba.values():
            assert v is not None and v >= 0.0

    def test_high_rb_scores_neo(self):
        f = CandidateFeatures(
            real_bogus_score=0.99,
            motion_consistency_score=0.9,
            nights_observed_score=0.8,
        )
        proba = _tier1_predict(f, model=None)
        # High rb → higher neo_candidate relative to artifact
        assert proba["neo_candidate"] > proba["stellar_artifact"]


class TestClassifyPipeline:
    def test_returns_features_and_posterior(self):
        t = make_tracklet()
        features, posterior = classify(t)
        assert isinstance(features, CandidateFeatures)
        assert 0.0 <= posterior.neo_candidate <= 1.0
        assert 0.0 <= posterior.stellar_artifact <= 1.0

    def test_posterior_components_nonnegative(self):
        t = make_tracklet()
        _, posterior = classify(t)
        for field in ("neo_candidate", "known_object", "main_belt_asteroid",
                      "stellar_artifact", "other_solar_system"):
            assert getattr(posterior, field) >= 0.0


class TestColorIndex:
    def test_both_bands_present(self):
        obs_g = make_obs(obs_id="g1", filter_band="g", mag=19.0)
        obs_r = make_obs(obs_id="r1", filter_band="r", mag=18.6)
        t = Tracklet("T", (obs_g, obs_r), 1.0, 1.0, 0.0)
        score = _color_index(t)
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_single_band_returns_none(self):
        t = make_tracklet()  # all r-band
        score = _color_index(t)
        assert score is None


class TestLightcurveVariability:
    def test_stable_returns_low(self):
        obs = tuple(make_obs(obs_id=f"s{i}", mag=19.5) for i in range(3))
        t = Tracklet("T", obs, 2.0, 1.0, 0.0)
        score = _lightcurve_variability(t)
        assert score is not None
        assert score == pytest.approx(0.0, abs=1e-6)

    def test_variable_returns_nonzero(self):
        mags = [18.0, 19.5, 21.0]
        obs = tuple(make_obs(obs_id=f"v{i}", mag=m) for i, m in enumerate(mags))
        t = Tracklet("T", obs, 2.0, 1.0, 0.0)
        score = _lightcurve_variability(t)
        assert score is not None
        assert score > 0.0

    def test_too_few_obs_returns_none(self):
        obs1 = make_obs(obs_id="a")
        obs2 = make_obs(obs_id="b")
        t = Tracklet("T", (obs1, obs2), 1.0, 1.0, 0.0)
        assert _lightcurve_variability(t) is None


class TestMotionConsistency:
    def test_linear_motion_high_score(self):
        t = make_tracklet(n_obs=4)
        score = _motion_consistency(t)
        assert score is not None
        assert score > 0.5

    def test_two_obs_returns_none(self):
        obs1 = make_obs(obs_id="a")
        obs2 = make_obs(obs_id="b")
        t = Tracklet("T", (obs1, obs2), 1.0, 1.0, 0.0)
        assert _motion_consistency(t) is None


class TestFeaturesToArray:
    def test_shape(self):
        f = CandidateFeatures(real_bogus_score=0.9)
        arr = _features_to_array(f)
        assert arr.shape == (10,)
        assert arr.dtype == np.float32

    def test_none_becomes_zero(self):
        f = CandidateFeatures()
        arr = _features_to_array(f)
        assert arr[0] == pytest.approx(0.0)  # real_bogus_score is None → 0

    def test_values_passed_through(self):
        f = CandidateFeatures(real_bogus_score=0.88, brightness_score=0.75)
        arr = _features_to_array(f)
        assert arr[0] == pytest.approx(0.88, abs=1e-5)


class TestDecodeCutoutF32:
    def test_valid_cutout(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        result = _decode_cutout_f32(b64)
        assert result is not None
        assert result.shape == (63, 63)

    def test_wrong_size_returns_none(self):
        arr = np.zeros((10, 10), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        result = _decode_cutout_f32(b64)
        assert result is None

    def test_invalid_base64_returns_none(self):
        result = _decode_cutout_f32("not!valid!base64")
        assert result is None


class TestTrackletToSequence:
    def test_returns_array(self):
        t = make_tracklet(n_obs=4)
        seq = _tracklet_to_sequence(t)
        assert seq is not None
        assert seq.shape == (4, 5)
        assert seq.dtype == np.float32

    def test_single_obs_returns_none(self):
        obs = make_obs()
        t = Tracklet("T", (obs,), 0.0, 0.0, 0.0)
        assert _tracklet_to_sequence(t) is None


class TestBrightnessScoreNone:
    def test_all_mag_above_99_returns_none(self):
        obs = tuple(make_obs(obs_id=f"b{i}", mag=99.5) for i in range(3))
        t = Tracklet("T", obs, 2.0, 1.0, 0.0)
        from classify import _brightness_score
        assert _brightness_score(t) is None


class TestTier1WithMockModel:
    def test_uses_model_predict_proba(self):
        from unittest.mock import MagicMock

        import numpy as np

        mock_model = MagicMock()
        proba = np.array([0.5, 0.2, 0.1, 0.1, 0.1])
        mock_model.predict_proba.return_value = [proba]

        f = CandidateFeatures(real_bogus_score=0.9)
        result = _tier1_predict(f, model=mock_model)
        assert set(result.keys()) == {
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        }
        assert result["neo_candidate"] == pytest.approx(0.5, abs=1e-5)



class TestTier2And3NullModel:
    def test_tier2_returns_none_when_no_model(self):
        from classify import _tier2_predict
        t = make_tracklet()
        # No model and no model file → returns None
        assert _tier2_predict(t, model=None) is None

    def test_tier3_returns_none_when_no_model(self):
        from classify import _tier3_predict
        t = make_tracklet()
        assert _tier3_predict(t, model=None) is None


class TestStackPredictions:
    def _base_t1(self):
        return {
            "neo_candidate": 0.6,
            "known_object": 0.1,
            "main_belt_asteroid": 0.1,
            "stellar_artifact": 0.1,
            "other_solar_system": 0.1,
        }

    def test_t1_only(self):
        result = _stack_predictions(self._base_t1(), None, None)
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_t1_t2(self):
        t2 = self._base_t1()
        result = _stack_predictions(self._base_t1(), t2, None)
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_all_tiers(self):
        t = self._base_t1()
        result = _stack_predictions(t, t, t)
        assert abs(sum(result.values()) - 1.0) < 1e-6


class TestLoadXgbModel:
    def test_returns_none_when_no_file(self):
        # Default model dir has no model file → returns None
        result = _load_xgb_model()
        assert result is None

    def test_returns_none_when_xgb_unavailable(self, tmp_path, monkeypatch):
        import classify as cls_mod
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        (tmp_path / "tier1_xgb.json").write_text("{}")
        # xgboost not installed → ImportError caught → returns None
        monkeypatch.setitem(sys.modules, "xgboost", None)
        result = _load_xgb_model()
        assert result is None

    def test_returns_model_when_xgb_available(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        import classify as cls_mod
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        (tmp_path / "tier1_xgb.json").write_text("{}")

        mock_xgb = MagicMock()
        mock_clf = MagicMock()
        mock_xgb.XGBClassifier.return_value = mock_clf
        monkeypatch.setitem(sys.modules, "xgboost", mock_xgb)

        result = _load_xgb_model()
        assert result is mock_clf
        mock_clf.load_model.assert_called_once()
