"""Tests for classify.py."""

import base64
import sys

import numpy as np
import pytest

from classify import (
    _arc_coverage,
    _brightness_score,
    _build_ensemble,
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
    ensemble_predict,
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


class TestBuildCnnModel:
    def test_returns_model_with_torch(self):
        from classify import _build_cnn_model
        model = _build_cnn_model()
        assert model is not None

    def test_cnn_model_forward_pass(self):
        import torch

        from classify import _build_cnn_model
        model = _build_cnn_model()
        assert model is not None
        x = torch.zeros(1, 1, 63, 63)
        with torch.no_grad():
            out = model(x, x, x)
        assert out.shape == (1, 5)

    def test_load_cnn_model_saves_and_loads(self, tmp_path, monkeypatch):
        import torch

        import classify as cls_mod
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        model = cls_mod._build_cnn_model()
        assert model is not None
        torch.save(model.state_dict(), str(tmp_path / "tier2_cnn.pt"))
        loaded = cls_mod._load_cnn_model()
        assert loaded is not None


class TestBuildTransformerModel:
    def test_returns_model_with_torch(self):
        from classify import _build_transformer_model
        model = _build_transformer_model()
        assert model is not None

    def test_transformer_forward_pass(self):
        import torch

        from classify import _build_transformer_model
        model = _build_transformer_model()
        assert model is not None
        x = torch.zeros(1, 4, 5)  # batch=1, seq_len=4, features=5
        with torch.no_grad():
            out = model(x)
        assert out.shape == (1, 5)

    def test_load_transformer_model_saves_and_loads(self, tmp_path, monkeypatch):
        import torch

        import classify as cls_mod
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        model = cls_mod._build_transformer_model()
        assert model is not None
        torch.save(model.state_dict(), str(tmp_path / "tier3_transformer.pt"))
        loaded = cls_mod._load_transformer_model()
        assert loaded is not None


class TestTier2PredictWithCutouts:
    def _make_cutout_b64(self) -> str:
        import base64

        import numpy as np
        arr = np.random.rand(63, 63).astype(np.float32)
        return base64.b64encode(arr.tobytes()).decode()

    def test_tier2_with_real_model_and_cutouts(self):
        from classify import _build_cnn_model, _tier2_predict
        from schemas import Tracklet
        model = _build_cnn_model()
        assert model is not None
        b64 = self._make_cutout_b64()
        obs = make_obs(
            obs_id="t2_obs",
            cutout_science=b64,
            cutout_reference=b64,
            cutout_difference=b64,
        )
        t = Tracklet("T2", (obs,), 0.0, 0.0, 0.0)
        result = _tier2_predict(t, model=model)
        assert result is not None
        assert set(result.keys()) == {
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        }

    def test_tier2_no_cutouts_returns_none(self):
        from classify import _build_cnn_model, _tier2_predict
        model = _build_cnn_model()
        t = make_tracklet(n_obs=2)
        result = _tier2_predict(t, model=model)
        assert result is None


class TestTier3PredictWithModel:
    def test_tier3_with_real_model(self):
        from classify import _build_transformer_model, _tier3_predict
        model = _build_transformer_model()
        assert model is not None
        t = make_tracklet(n_obs=4)
        result = _tier3_predict(t, model=model)
        assert result is not None
        assert set(result.keys()) == {
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        }

    def test_tier3_probabilities_sum_to_one(self):
        from classify import _build_transformer_model, _tier3_predict
        model = _build_transformer_model()
        t = make_tracklet(n_obs=5, arc_days=4.0)
        result = _tier3_predict(t, model=model)
        if result is not None:
            assert abs(sum(result.values()) - 1.0) < 1e-4

    def test_tier3_single_obs_seq_none(self):
        # tracklet with 1 obs → _tracklet_to_sequence returns None → line 432
        from classify import _build_transformer_model, _tier3_predict
        model = _build_transformer_model()
        assert model is not None
        t = make_tracklet(n_obs=1)
        result = _tier3_predict(t, model=model)
        assert result is None


class TestBuildEnsemble:
    def _make_probs(self, neo: float = 0.6) -> dict[str, float]:
        rest = (1.0 - neo) / 4
        return {
            "neo_candidate": neo,
            "known_object": rest,
            "main_belt_asteroid": rest,
            "stellar_artifact": rest,
            "other_solar_system": rest,
        }

    def test_returns_model_with_two_classes(self):
        tier1s = [self._make_probs(0.8), self._make_probs(0.2)]
        labels = [{"label": 0}, {"label": 2}]
        model = _build_ensemble(tier1s, labels)
        assert model is not None

    def test_returns_none_with_single_class(self):
        tier1s = [self._make_probs(0.8)] * 5
        labels = [{"label": 0}] * 5
        result = _build_ensemble(tier1s, labels)
        assert result is None

    def test_returns_none_on_bad_input(self):
        result = _build_ensemble([], [])
        assert result is None

    def test_returns_none_when_sklearn_raises(self, monkeypatch):
        from unittest.mock import MagicMock
        bad_clf = MagicMock()
        bad_clf.fit.side_effect = RuntimeError("simulated sklearn error")
        mock_lr_cls = MagicMock(return_value=bad_clf)
        mock_sklearn_mod = MagicMock()
        mock_sklearn_mod.LogisticRegression = mock_lr_cls
        monkeypatch.setitem(sys.modules, "sklearn.linear_model", mock_sklearn_mod)
        tier1s = [self._make_probs(0.9), self._make_probs(0.1)] * 3
        labels = [{"label": 0}, {"label": 2}] * 3
        result = _build_ensemble(tier1s, labels)
        assert result is None


class TestEnsemblePredict:
    def _base_probs(self, neo: float = 0.5) -> dict[str, float]:
        rest = (1.0 - neo) / 4
        return {
            "neo_candidate": neo,
            "known_object": rest,
            "main_belt_asteroid": rest,
            "stellar_artifact": rest,
            "other_solar_system": rest,
        }

    def test_no_meta_model_returns_weighted_avg(self):
        t1 = self._base_probs(0.6)
        result = ensemble_predict(t1)
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_with_meta_model(self):
        tier1s = [self._base_probs(0.8), self._base_probs(0.2)] * 5
        labels = [{"label": 0}, {"label": 2}] * 5
        model = _build_ensemble(tier1s, labels)
        assert model is not None
        t1 = self._base_probs(0.7)
        result = ensemble_predict(t1, meta_model=model)
        assert abs(sum(result.values()) - 1.0) < 1e-6
        assert set(result.keys()) == {
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        }

    def test_with_meta_model_and_t2_t3(self):
        tier1s = [self._base_probs(0.9), self._base_probs(0.1)] * 5
        labels = [{"label": 0}, {"label": 3}] * 5
        model = _build_ensemble(tier1s, labels)
        t1 = self._base_probs(0.6)
        t2 = self._base_probs(0.7)
        t3 = self._base_probs(0.8)
        result = ensemble_predict(t1, t2, t3, meta_model=model)
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_meta_model_exception_falls_back(self, monkeypatch):
        from unittest.mock import MagicMock
        bad_model = MagicMock()
        bad_model.predict_proba.side_effect = RuntimeError("boom")
        t1 = self._base_probs(0.5)
        result = ensemble_predict(t1, meta_model=bad_model)
        assert abs(sum(result.values()) - 1.0) < 1e-6


class TestClassifyErrorPaths:
    def test_load_cnn_model_returns_none_when_build_fails(self, monkeypatch):
        # _build_cnn_model returns None → line 272 in _load_cnn_model
        import pathlib
        import tempfile

        import classify as cls_mod
        with tempfile.TemporaryDirectory() as td:
            fake_dir = pathlib.Path(td)
            (fake_dir / "tier2_cnn.pt").write_bytes(b"dummy")
            monkeypatch.setattr(cls_mod, "_MODEL_DIR", fake_dir)
            monkeypatch.setattr(cls_mod, "_build_cnn_model", lambda: None)
            result = cls_mod._load_cnn_model()
            assert result is None

    def test_load_cnn_model_exception_path(self, monkeypatch):
        # torch.load raises → except Exception → lines 276-277
        import pathlib
        import tempfile

        import classify as cls_mod
        with tempfile.TemporaryDirectory() as td:
            fake_dir = pathlib.Path(td)
            (fake_dir / "tier2_cnn.pt").write_bytes(b"corrupted")
            monkeypatch.setattr(cls_mod, "_MODEL_DIR", fake_dir)
            result = cls_mod._load_cnn_model()
            assert result is None

    def test_tier2_exception_path(self, monkeypatch):
        # Force model(...)to raise → except Exception → lines 319-320
        import base64

        import numpy as np

        import classify as cls_mod
        from classify import _build_cnn_model
        model = _build_cnn_model()
        assert model is not None

        def boom(*args, **kwargs):
            raise RuntimeError("forced error")

        monkeypatch.setattr(model, "forward", boom)
        b64 = base64.b64encode(np.zeros((63, 63), dtype=np.float32).tobytes()).decode()
        obs = make_obs(obs_id="ex", cutout_science=b64, cutout_reference=b64, cutout_difference=b64)
        t = Tracklet("TX", (obs,), 0.0, 0.0, 0.0)
        result = cls_mod._tier2_predict(t, model=model)
        assert result is None

    def test_load_transformer_model_returns_none_when_build_fails(self, monkeypatch):
        # _build_transformer_model returns None → line 413
        import pathlib
        import tempfile

        import classify as cls_mod
        with tempfile.TemporaryDirectory() as td:
            fake_dir = pathlib.Path(td)
            (fake_dir / "tier3_transformer.pt").write_bytes(b"dummy")
            monkeypatch.setattr(cls_mod, "_MODEL_DIR", fake_dir)
            monkeypatch.setattr(cls_mod, "_build_transformer_model", lambda: None)
            result = cls_mod._load_transformer_model()
            assert result is None

    def test_load_transformer_model_exception_path(self, monkeypatch):
        # corrupted weights file → torch.load raises → lines 417-418
        import pathlib
        import tempfile

        import classify as cls_mod
        with tempfile.TemporaryDirectory() as td:
            fake_dir = pathlib.Path(td)
            (fake_dir / "tier3_transformer.pt").write_bytes(b"corrupted")
            monkeypatch.setattr(cls_mod, "_MODEL_DIR", fake_dir)
            result = cls_mod._load_transformer_model()
            assert result is None

    def test_tier3_exception_path(self, monkeypatch):
        # Force model(x) to raise → except Exception → lines 446-447
        import classify as cls_mod
        from classify import _build_transformer_model
        model = _build_transformer_model()
        assert model is not None

        def boom(*args, **kwargs):
            raise RuntimeError("forced error")

        monkeypatch.setattr(model, "forward", boom)
        t = make_tracklet(n_obs=4)
        result = cls_mod._tier3_predict(t, model=model)
        assert result is None
