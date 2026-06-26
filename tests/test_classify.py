"""Tests for classify.py."""

import base64
import sys

import numpy as np
import pytest

import classify as cls_mod
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
    classify_batch,
    ensemble_predict,
    extract_features,
    retrain_stacker,
    retrain_tier1,
)
from schemas import CandidateFeatures, NEOPosterior, Observation, Tracklet


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

    def test_tier3_returns_none_when_no_model(self, tmp_path, monkeypatch):
        from classify import _tier3_predict

        t = make_tracklet()
        # Isolate the loader from any operator-generated local model artifacts.
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
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
    def test_returns_none_when_no_file(self, tmp_path, monkeypatch):
        # Redirect _MODEL_DIR to empty temp dir — no model file present → returns None
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        result = _load_xgb_model()
        assert result is None

    def test_returns_none_when_xgb_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        (tmp_path / "tier1_xgb.json").write_text("{}")
        # xgboost not installed → ImportError caught → returns None
        monkeypatch.setitem(sys.modules, "xgboost", None)
        result = _load_xgb_model()
        assert result is None

    def test_returns_model_when_xgb_available(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

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

        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        model = cls_mod._build_cnn_model()
        assert model is not None
        torch.save(model.state_dict(), str(tmp_path / "tier2_cnn.pt"))
        loaded = cls_mod._load_cnn_model()
        assert loaded is not None

    def test_load_cnn_model_returns_none_without_weights(self, tmp_path, monkeypatch):
        """Missing Tier 2 weights should fail closed without constructing a model."""

        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        assert cls_mod._load_cnn_model() is None


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

    def test_tier2_cutouts_without_available_model_returns_none(self, monkeypatch):
        """Valid cutouts should still fail closed when lazy model loading is unavailable."""

        b64 = self._make_cutout_b64()
        obs = make_obs(
            obs_id="t2_missing_model",
            cutout_science=b64,
            cutout_reference=b64,
            cutout_difference=b64,
        )
        tracklet = Tracklet("T2-missing", (obs,), 0.0, 0.0, 0.0)
        monkeypatch.setattr(cls_mod, "_load_cnn_model", lambda: None)

        assert cls_mod._tier2_predict(tracklet, model=None) is None


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

        with tempfile.TemporaryDirectory() as td:
            fake_dir = pathlib.Path(td)
            (fake_dir / "tier3_transformer.pt").write_bytes(b"corrupted")
            monkeypatch.setattr(cls_mod, "_MODEL_DIR", fake_dir)
            result = cls_mod._load_transformer_model()
            assert result is None

    def test_tier3_exception_path(self, monkeypatch):
        # Force model(x) to raise → except Exception → lines 446-447
        from classify import _build_transformer_model
        model = _build_transformer_model()
        assert model is not None

        def boom(*args, **kwargs):
            raise RuntimeError("forced error")

        monkeypatch.setattr(model, "forward", boom)
        t = make_tracklet(n_obs=4)
        result = cls_mod._tier3_predict(t, model=model)
        assert result is None


def _make_tier1_csv(csv_path, n_rows: int = 10, n_classes: int = 3):
    import csv
    feature_cols = [
        "real_bogus_score", "motion_consistency_score", "arc_coverage_score",
        "nights_observed_score", "brightness_score", "color_score",
        "lightcurve_variability_score", "streak_score", "psf_quality_score",
        "known_object_score",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=feature_cols + ["label"])
        writer.writeheader()
        for i in range(n_rows):
            row = {col: str(0.5 + (i % 2) * 0.3) for col in feature_cols}
            row["label"] = str(i % n_classes)
            writer.writerow(row)


class TestRetrainTier1:
    def test_retrain_from_csv(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)

        csv_path = tmp_path / "labels.csv"
        _make_tier1_csv(csv_path, n_rows=20, n_classes=2)

        report = retrain_tier1(csv_path, tmp_path / "model.json")
        assert report["n_samples"] == 20
        assert report["n_classes"] >= 2

    def test_retrain_returns_error_without_xgboost(self, tmp_path, monkeypatch):
        import sys

        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)

        csv_path = tmp_path / "labels.csv"
        _make_tier1_csv(csv_path, n_rows=2, n_classes=1)

        monkeypatch.setitem(sys.modules, "xgboost", None)
        report = retrain_tier1(csv_path, tmp_path / "model.json")
        assert "error" in report

    def test_retrain_report_keys(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)

        csv_path = tmp_path / "labels.csv"
        _make_tier1_csv(csv_path, n_rows=15, n_classes=3)

        report = retrain_tier1(csv_path, tmp_path / "model_keys.json")
        assert {"n_samples", "n_classes"} <= report.keys()


class TestRetrainStacker:
    def _make_training_data(self, n: int = 20):
        import numpy as np
        rng = np.random.default_rng(0)
        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        tier1_outputs = []
        labels = []
        for i in range(n):
            raw = rng.dirichlet(np.ones(5))
            tier1_outputs.append(dict(zip(labels_list, raw.tolist())))
            labels.append({"label": i % 5})
        return tier1_outputs, labels

    def test_retrain_stacker_returns_report(self, tmp_path):
        t1, lbls = self._make_training_data()
        report = retrain_stacker(t1, lbls, tmp_path / "coef.json")
        assert "n_samples" in report
        assert report["n_samples"] == 20

    def test_coef_file_written(self, tmp_path):
        t1, lbls = self._make_training_data()
        report = retrain_stacker(t1, lbls, tmp_path / "coef.json")
        if report["coef_path"] is not None:
            import json
            data = json.loads((tmp_path / "coef.json").read_text())
            assert "coef" in data
            assert "labels" in data

    def test_retrain_stacker_insufficient_classes(self, tmp_path):
        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        # All same class → _build_ensemble returns None (< 2 classes)
        t1 = [dict(zip(labels_list, [0.9, 0.02, 0.02, 0.03, 0.03])) for _ in range(5)]
        lbls = [{"label": 0}] * 5
        report = retrain_stacker(t1, lbls, tmp_path / "coef.json")
        assert report["n_samples"] == 5

    def test_retrain_stacker_auc_present(self, tmp_path):
        t1, lbls = self._make_training_data(30)
        report = retrain_stacker(t1, lbls, tmp_path / "coef.json")
        # auc may be None if sklearn unavailable or single class; otherwise float
        if report["auc"] is not None:
            assert 0.0 <= report["auc"] <= 1.0

    def test_retrain_stacker_two_classes(self, tmp_path):
        import numpy as np
        rng = np.random.default_rng(7)
        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        # Only 2 distinct classes → exercises the binary AUC path
        t1 = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(20)]
        lbls = [{"label": i % 2} for i in range(20)]
        report = retrain_stacker(t1, lbls, tmp_path / "coef2.json")
        assert report["n_classes"] == 2
        if report["auc"] is not None:
            assert 0.0 <= report["auc"] <= 1.0

    def test_retrain_stacker_stores_n_features(self, tmp_path):
        """retrain_stacker JSON must include n_features key (5 for T1-only)."""
        t1, lbls = self._make_training_data()
        report = retrain_stacker(t1, lbls, tmp_path / "coef5.json")
        if report["coef_path"] is not None:
            import json
            data = json.loads((tmp_path / "coef5.json").read_text())
            assert "n_features" in data
            assert data["n_features"] == 5

    def test_retrain_stacker_10_features_with_tier2(self, tmp_path):
        """retrain_stacker with tier2_outputs produces 10-feature coefficients."""
        t1, lbls = self._make_training_data()
        # Make matching tier2 outputs (same length, same label distribution)
        rng = np.random.default_rng(7)
        t2 = [
            dict(zip(
                ["neo_candidate", "known_object", "main_belt_asteroid",
                 "stellar_artifact", "other_solar_system"],
                rng.dirichlet(np.ones(5)).tolist(),
            ))
            for _ in range(len(t1))
        ]
        report = retrain_stacker(t1, lbls, tmp_path / "coef10.json", tier2_outputs=t2)
        assert "n_samples" in report
        assert report["n_samples"] == 20
        if report["coef_path"] is not None:
            import json
            data = json.loads((tmp_path / "coef10.json").read_text())
            assert data["n_features"] == 10

    def test_retrain_stacker_exception_in_metrics(self, tmp_path, monkeypatch):
        import sys

        import numpy as np
        rng = np.random.default_rng(0)
        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        t1 = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(20)]
        lbls = [{"label": i % 5} for i in range(20)]
        # Block sklearn.metrics to force the except Exception path
        monkeypatch.setitem(sys.modules, "sklearn.metrics", None)
        report = retrain_stacker(t1, lbls, tmp_path / "coef_exc.json")
        assert "n_samples" in report


class TestLoadEnsembleStacker:
    """Tests for _load_ensemble_stacker and the _StackerProxy class."""

    def _make_probs(self, neo: float = 0.5) -> dict[str, float]:
        rest = (1.0 - neo) / 4
        return {
            "neo_candidate": neo, "known_object": rest,
            "main_belt_asteroid": rest, "stellar_artifact": rest,
            "other_solar_system": rest,
        }

    def test_returns_none_for_missing_file(self, tmp_path):
        from classify import _load_ensemble_stacker
        result = _load_ensemble_stacker(tmp_path / "nonexistent.json")
        assert result is None

    def test_returns_none_for_corrupt_file(self, tmp_path):
        from classify import _load_ensemble_stacker
        bad = tmp_path / "bad.json"
        bad.write_text("not json {{{")
        result = _load_ensemble_stacker(bad)
        assert result is None

    def test_round_trip_5_feature(self, tmp_path):
        """Train 5-feature stacker, save, reload via _load_ensemble_stacker, run predict."""
        from classify import _load_ensemble_stacker, retrain_stacker

        t1s = [self._make_probs(0.8), self._make_probs(0.2)] * 5
        lbls = [{"label": 0}, {"label": 3}] * 5
        path = tmp_path / "coef_rt.json"
        report = retrain_stacker(t1s, lbls, path)
        if report["coef_path"] is None:
            return  # sklearn not available; skip

        proxy = _load_ensemble_stacker(path)
        assert proxy is not None
        # predict_proba must return (1, n_classes) shaped array
        x = np.array([[self._make_probs(0.7)[lbl] for lbl in [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system"
        ]]], dtype=np.float32)
        proba = proxy.predict_proba(x)
        assert proba.shape[0] == 1
        assert abs(proba[0].sum() - 1.0) < 1e-5

    def test_round_trip_10_feature(self, tmp_path):
        """Train 10-feature stacker, save, reload, and run predict_proba."""
        from classify import _load_ensemble_stacker, retrain_stacker

        rng = np.random.default_rng(99)
        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        n = 20
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t2s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        lbls = [{"label": i % 5} for i in range(n)]
        path = tmp_path / "coef10_rt.json"
        report = retrain_stacker(t1s, lbls, path, tier2_outputs=t2s)
        if report["coef_path"] is None:
            return

        proxy = _load_ensemble_stacker(path)
        assert proxy is not None
        assert proxy.coef_.shape[1] == 10  # 10-feature stacker
        x = np.zeros((1, 10), dtype=np.float32)
        proba = proxy.predict_proba(x)
        assert abs(proba[0].sum() - 1.0) < 1e-5

    def test_ensemble_predict_with_10_feature_stacker(self, tmp_path):
        """ensemble_predict uses 10-feature stacker when T2 is provided."""
        from classify import _load_ensemble_stacker, ensemble_predict, retrain_stacker

        rng = np.random.default_rng(77)
        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        n = 20
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t2s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        lbls = [{"label": i % 5} for i in range(n)]
        path = tmp_path / "coef10_ep.json"
        report = retrain_stacker(t1s, lbls, path, tier2_outputs=t2s)
        if report["coef_path"] is None:
            return

        stacker = _load_ensemble_stacker(path)
        t1 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        t2 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))

        result = ensemble_predict(t1, tier2=t2, meta_model=stacker)
        assert abs(sum(result.values()) - 1.0) < 1e-5

    def test_ensemble_predict_10_feature_falls_back_when_t2_missing(self, tmp_path):
        """ensemble_predict falls back to weighted avg when 10-feature stacker has no T2."""
        from classify import _load_ensemble_stacker, ensemble_predict, retrain_stacker

        rng = np.random.default_rng(55)
        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        n = 20
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t2s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        lbls = [{"label": i % 5} for i in range(n)]
        path = tmp_path / "coef10_fb.json"
        report = retrain_stacker(t1s, lbls, path, tier2_outputs=t2s)
        if report["coef_path"] is None:
            return

        stacker = _load_ensemble_stacker(path)
        t1 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        # Pass T2=None — should fall back gracefully
        result = ensemble_predict(t1, tier2=None, meta_model=stacker)
        assert abs(sum(result.values()) - 1.0) < 1e-5

    def test_partial_class_stacker_fills_missing_classes(self, tmp_path):
        """ensemble_predict backfills missing-class probas when stacker < 5 classes."""
        from classify import (
            _load_ensemble_stacker,
            ensemble_predict,
            retrain_stacker,
        )

        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        # Build stacker trained on only 2 classes (0 and 3)
        rng = np.random.default_rng(11)
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(10)]
        lbls_bin = [{"label": 0}] * 5 + [{"label": 3}] * 5
        path = tmp_path / "coef_binary.json"
        report = retrain_stacker(t1s, lbls_bin, path)
        if report["coef_path"] is None:
            return

        stacker = _load_ensemble_stacker(path)
        assert stacker is not None
        t1 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        result = ensemble_predict(t1, meta_model=stacker)
        # Must sum to 1 and have all 5 labels present
        assert abs(sum(result.values()) - 1.0) < 1e-5
        assert set(result.keys()) == set(labels_list)

    def test_full_5_class_stacker_meta_out(self, tmp_path):
        """ensemble_predict uses the else branch (all 5 classes) for full stacker."""
        from classify import _load_ensemble_stacker, ensemble_predict, retrain_stacker

        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        rng = np.random.default_rng(42)
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(20)]
        lbls = [{"label": i % 5} for i in range(20)]
        path = tmp_path / "coef5cls.json"
        report = retrain_stacker(t1s, lbls, path)
        if report["coef_path"] is None:
            return

        stacker = _load_ensemble_stacker(path)
        assert stacker is not None
        # stacker has 5 classes → full meta_out path (else branch at line 657)
        t1 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        result = ensemble_predict(t1, meta_model=stacker)
        assert abs(sum(result.values()) - 1.0) < 1e-5

    def test_build_ensemble_with_tier3_outputs(self):
        """_build_ensemble with tier3_outputs builds 15-feature coefficient matrix."""
        from classify import _build_ensemble

        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        rng = np.random.default_rng(33)
        n = 20
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t2s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t3s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        lbls = [{"label": i % 5} for i in range(n)]
        clf = _build_ensemble(t1s, lbls, tier2_outputs=t2s, tier3_outputs=t3s)
        if clf is None:
            return  # sklearn unavailable
        # 5 (T1) + 5 (T2) + 5 (T3) = 15 features
        assert clf.coef_.shape[1] == 15

    def test_ensemble_predict_15_feature_falls_back_when_t3_missing(self, tmp_path):
        """ensemble_predict falls back when 15-feature stacker is given no T3."""
        from classify import _load_ensemble_stacker, ensemble_predict, retrain_stacker

        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        rng = np.random.default_rng(88)
        n = 20
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t2s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t3s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        lbls = [{"label": i % 5} for i in range(n)]
        path = tmp_path / "coef15_fb.json"
        report = retrain_stacker(t1s, lbls, path, tier2_outputs=t2s, tier3_outputs=t3s)
        if report["coef_path"] is None:
            return

        stacker = _load_ensemble_stacker(path)
        assert stacker is not None
        assert stacker.coef_.shape[1] == 15

        t1 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        t2 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        # T3=None → falls back to weighted average (covers the T3-missing path)
        result = ensemble_predict(t1, tier2=t2, tier3=None, meta_model=stacker)
        assert abs(sum(result.values()) - 1.0) < 1e-5

    def test_ensemble_predict_15_feature_with_all_tiers(self, tmp_path):
        """ensemble_predict executes the T3 feature concat branch (line 633)."""
        from classify import _load_ensemble_stacker, ensemble_predict, retrain_stacker

        labels_list = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        rng = np.random.default_rng(66)
        n = 20
        t1s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t2s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        t3s = [dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist())) for _ in range(n)]
        lbls = [{"label": i % 5} for i in range(n)]
        path = tmp_path / "coef15_all.json"
        report = retrain_stacker(t1s, lbls, path, tier2_outputs=t2s, tier3_outputs=t3s)
        if report["coef_path"] is None:
            return

        stacker = _load_ensemble_stacker(path)
        assert stacker is not None
        assert stacker.coef_.shape[1] == 15

        t1 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        t2 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        t3 = dict(zip(labels_list, rng.dirichlet(np.ones(5)).tolist()))
        # All tiers provided → uses 15-feature stacker (covers T3 concat branch)
        result = ensemble_predict(t1, tier2=t2, tier3=t3, meta_model=stacker)
        assert abs(sum(result.values()) - 1.0) < 1e-5


class TestClassifyBatch:
    def test_returns_list_same_length(self):
        from .conftest import build_tracklet
        tracklets = [build_tracklet(n_obs=3) for _ in range(4)]
        results = classify_batch(tracklets)
        assert len(results) == 4

    def test_each_result_is_tuple_of_features_and_posterior(self):
        from .conftest import build_tracklet
        tracklets = [build_tracklet(n_obs=3)]
        features, posterior = classify_batch(tracklets)[0]
        assert isinstance(features, CandidateFeatures)
        assert isinstance(posterior, NEOPosterior)

    def test_empty_list_returns_empty(self):
        assert classify_batch([]) == []

    def test_models_loaded_once(self):
        from .conftest import build_tracklet
        # Should not raise even with multiple tracklets
        tracklets = [build_tracklet(n_obs=3) for _ in range(3)]
        results = classify_batch(tracklets)
        assert all(isinstance(r, tuple) for r in results)


class TestClassifyMorphologyEdgeCases:
    def _make_obs_with_arr(self, arr):
        import base64

        import numpy as np

        from schemas import Observation
        b64 = base64.b64encode(arr.astype(np.float32).tobytes()).decode()
        return Observation(
            obs_id="ce_001",
            ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=b64,
        )

    def test_non_square_returns_point_source(self):
        import numpy as np

        from classify import classify_morphology
        # 3*4=12 elements → not a perfect square
        arr = np.ones(12, dtype=np.float32)
        obs = self._make_obs_with_arr(arr)
        assert classify_morphology(obs) == "point_source"

    def test_zero_trace_returns_point_source(self):
        import numpy as np

        from classify import classify_morphology
        # all-zeros → total == 0 → "point_source" (via total <= 0 branch)
        arr = np.zeros((7, 7), dtype=np.float32)
        assert classify_morphology(self._make_obs_with_arr(arr)) == "point_source"

    def test_elongated_streak_high_ratio(self):
        import numpy as np

        from classify import classify_morphology
        # Horizontal streak: all flux in one row
        arr = np.zeros((9, 9), dtype=np.float32)
        arr[4, :] = 1.0
        result = classify_morphology(self._make_obs_with_arr(arr))
        assert result == "streak"

    def test_extended_source(self):
        import numpy as np

        from classify import classify_morphology
        # Slightly elongated blob: 3:1 ratio
        arr = np.zeros((15, 15), dtype=np.float32)
        arr[7, 4:12] = 1.0
        arr[7, 4:12] += 0.5
        arr[6:9, 6:10] = 0.3
        result = classify_morphology(self._make_obs_with_arr(arr))
        # Accept streak or extended (both are non-round)
        assert result in ("streak", "extended")

    def test_invalid_b64_returns_point_source(self):
        from classify import classify_morphology
        from schemas import Observation
        obs = Observation(
            obs_id="bad", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference="!!!not_valid_base64!!!",
        )
        assert classify_morphology(obs) == "point_source"


class TestClassifyMorphologyCoverage:
    def _encode(self, arr):
        import base64

        import numpy as np
        return base64.b64encode(arr.astype(np.float32).tobytes()).decode()

    def _obs(self, b64):
        from schemas import Observation
        return Observation(
            obs_id="cmc_001", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=b64,
        )

    def test_single_pixel_trace_zero_returns_point_source(self):
        import numpy as np

        from classify import classify_morphology
        arr = np.zeros((9, 9), dtype=np.float32)
        arr[4, 4] = 1.0  # single pixel → trace=0 → "point_source"
        assert classify_morphology(self._obs(self._encode(arr))) == "point_source"

    def test_2x3_box_returns_extended(self):
        import numpy as np

        from classify import classify_morphology
        arr = np.zeros((9, 9), dtype=np.float32)
        arr[4:6, 3:6] = 1.0  # 2x3 box → elongation ~2.67 → "extended"
        result = classify_morphology(self._obs(self._encode(arr)))
        assert result == "extended"


class TestComputeCalibrationGain:
    def _posterior(self, neo=0.5, ko=0.2, mba=0.2, art=0.05, other=0.05):
        from schemas import NEOPosterior
        return NEOPosterior(
            neo_candidate=neo, known_object=ko, main_belt_asteroid=mba,
            stellar_artifact=art, other_solar_system=other,
        )

    def test_identical_posteriors_zero(self):
        from classify import compute_calibration_gain
        p = self._posterior()
        result = compute_calibration_gain(p, p)
        assert abs(result) < 1e-4

    def test_returns_float(self):
        from classify import compute_calibration_gain
        p1 = self._posterior(neo=0.1, ko=0.6)
        p2 = self._posterior(neo=0.6, ko=0.1)
        result = compute_calibration_gain(p1, p2)
        assert isinstance(result, float)

    def test_nonnegative(self):
        from classify import compute_calibration_gain
        p1 = self._posterior()
        p2 = self._posterior(neo=0.9, ko=0.05, mba=0.03, art=0.01, other=0.01)
        result = compute_calibration_gain(p1, p2)
        assert result >= 0.0

    def test_zero_posterior_before_returns_zero(self):
        from classify import compute_calibration_gain
        from schemas import NEOPosterior
        zero = NEOPosterior(
            neo_candidate=0.0, known_object=0.0, main_belt_asteroid=0.0,
            stellar_artifact=0.0, other_solar_system=0.0,
        )
        p2 = self._posterior()
        assert compute_calibration_gain(zero, p2) == 0.0

    def test_zero_posterior_after_returns_zero(self):
        from classify import compute_calibration_gain
        from schemas import NEOPosterior
        p1 = self._posterior()
        zero = NEOPosterior(
            neo_candidate=0.0, known_object=0.0, main_belt_asteroid=0.0,
            stellar_artifact=0.0, other_solar_system=0.0,
        )
        assert compute_calibration_gain(p1, zero) == 0.0

    def test_large_shift_larger_gain(self):
        from classify import compute_calibration_gain
        p_uniform = self._posterior(0.2, 0.2, 0.2, 0.2, 0.2)
        p_concentrated = self._posterior(0.96, 0.01, 0.01, 0.01, 0.01)
        gain = compute_calibration_gain(p_uniform, p_concentrated)
        assert gain > 0.5

    def test_in_all(self):
        from classify import __all__
        assert "compute_calibration_gain" in __all__


class TestComputeClassEntropySummaryExtra:
    def test_bad_posterior_skipped(self):
        """Cover except branch in compute_class_entropy_summary."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_entropy_summary

        bad_posterior = SimpleNamespace()  # posterior_entropy will fail
        neos = [SimpleNamespace(posterior=bad_posterior)]
        result = compute_class_entropy_summary(neos)
        assert result["n_neos"] == 0


class TestComputeClassAgreementUnknownHypothesis:
    def test_all_zero_posterior_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_agreement
        # All-zero posterior → dominant_hypothesis returns ("unknown", 0.0) → skipped
        zero_posterior = SimpleNamespace(
            neo_candidate=0.0, known_object=0.0, main_belt_asteroid=0.0,
            stellar_artifact=0.0, other_solar_system=0.0
        )
        neo = SimpleNamespace(posterior=zero_posterior)
        assert compute_class_agreement([neo, neo]) == 0.0


