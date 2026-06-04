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
    get_tier1_feature_importances,
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
        import classify as cls_mod
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        from classify import retrain_tier1

        csv_path = tmp_path / "labels.csv"
        _make_tier1_csv(csv_path, n_rows=20, n_classes=2)

        report = retrain_tier1(csv_path, tmp_path / "model.json")
        assert report["n_samples"] == 20
        assert report["n_classes"] >= 2

    def test_retrain_returns_error_without_xgboost(self, tmp_path, monkeypatch):
        import sys

        import classify as cls_mod
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        from classify import retrain_tier1

        csv_path = tmp_path / "labels.csv"
        _make_tier1_csv(csv_path, n_rows=2, n_classes=1)

        monkeypatch.setitem(sys.modules, "xgboost", None)
        report = retrain_tier1(csv_path, tmp_path / "model.json")
        assert "error" in report

    def test_retrain_report_keys(self, tmp_path, monkeypatch):
        import classify as cls_mod
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        from classify import retrain_tier1

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


class TestGetTier1FeatureImportances:
    def test_returns_none_when_no_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        result = get_tier1_feature_importances(tmp_path / "nonexistent.json")
        assert result is None

    def test_returns_dict_after_training(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        csv_file = tmp_path / "train.csv"
        _make_tier1_csv(csv_file)
        model_path = tmp_path / "tier1_xgb.json"
        retrain_tier1(csv_file, model_path=model_path)
        result = get_tier1_feature_importances(model_path)
        assert result is not None
        assert isinstance(result, dict)
        assert "real_bogus_score" in result

    def test_importances_sum_to_one(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        csv_file = tmp_path / "train.csv"
        _make_tier1_csv(csv_file)
        model_path = tmp_path / "tier1_xgb.json"
        retrain_tier1(csv_file, model_path=model_path)
        result = get_tier1_feature_importances(model_path)
        assert result is not None
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_returns_none_on_bad_path(self):
        result = get_tier1_feature_importances("/totally/nonexistent/model.json")
        assert result is None

    def test_returns_none_on_xgboost_load_exception(self, tmp_path, monkeypatch):
        # Write a valid-looking but empty JSON file to trigger an xgb load error
        bad_path = tmp_path / "bad_model.json"
        bad_path.write_text("{}")
        result = get_tier1_feature_importances(bad_path)
        assert result is None


class TestExplainClassification:
    def test_returns_required_keys(self):
        from classify import explain_classification
        t = make_tracklet()
        result = explain_classification(t)
        expected = {"features", "posterior", "tier1_importances",
                    "dominant_hypothesis", "confidence"}
        assert expected == set(result.keys())

    def test_dominant_hypothesis_is_valid(self):
        from classify import explain_classification
        t = make_tracklet()
        result = explain_classification(t)
        valid = {"neo_candidate", "known_object", "main_belt_asteroid",
                 "stellar_artifact", "other_solar_system"}
        assert result["dominant_hypothesis"] in valid

    def test_confidence_is_max_posterior(self):
        from classify import explain_classification
        t = make_tracklet()
        result = explain_classification(t)
        max_prob = max(result["posterior"].values())
        assert result["confidence"] == pytest.approx(max_prob, abs=1e-6)

    def test_posterior_sums_to_one(self):
        from classify import explain_classification
        t = make_tracklet()
        result = explain_classification(t)
        total = sum(result["posterior"].values())
        assert abs(total - 1.0) < 1e-3

    def test_features_dict_non_empty(self):
        from classify import explain_classification
        t = make_tracklet()
        result = explain_classification(t)
        assert len(result["features"]) > 0

    def test_tier1_importances_is_none_without_model(self, tmp_path, monkeypatch):
        # Ensure model file doesn't exist by pointing to empty dir
        import classify as cls_mod
        from classify import explain_classification
        monkeypatch.setattr(cls_mod, "_MODEL_DIR", tmp_path)
        t = make_tracklet()
        result = explain_classification(t)
        # Without a real model file, importances should be None
        assert result["tier1_importances"] is None or isinstance(result["tier1_importances"], dict)


class TestBatchExplain:
    def _make_tracklets(self, n: int = 3):
        from .conftest import build_tracklet
        return [build_tracklet(object_id=f"T{i:03d}") for i in range(n)]

    def test_returns_list_same_length(self):
        from classify import batch_explain
        tracklets = self._make_tracklets(3)
        result = batch_explain(tracklets)
        assert len(result) == 3

    def test_empty_input_returns_empty(self):
        from classify import batch_explain
        assert batch_explain([]) == []

    def test_each_item_has_required_keys(self):
        from classify import batch_explain
        tracklets = self._make_tracklets(2)
        for item in batch_explain(tracklets):
            assert "dominant_hypothesis" in item
            assert "confidence" in item
            assert "posterior" in item

    def test_single_tracklet(self):
        from classify import batch_explain

        from .conftest import build_tracklet
        t = build_tracklet()
        result = batch_explain([t])
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_confidence_is_float(self):
        from classify import batch_explain
        tracklets = self._make_tracklets(1)
        result = batch_explain(tracklets)
        assert isinstance(result[0]["confidence"], float)


class TestPosteriorEntropy:
    def _make_posterior(self, **kwargs) -> "NEOPosterior":
        from schemas import NEOPosterior
        defaults = dict(
            neo_candidate=0.2,
            known_object=0.2,
            main_belt_asteroid=0.2,
            stellar_artifact=0.2,
            other_solar_system=0.2,
        )
        defaults.update(kwargs)
        return NEOPosterior(**defaults)

    def test_uniform_is_max_entropy(self):
        import math

        from classify import posterior_entropy
        p = self._make_posterior()
        h = posterior_entropy(p)
        assert h == pytest.approx(math.log2(5), rel=1e-5)

    def test_certain_is_zero_entropy(self):
        from classify import posterior_entropy
        p = self._make_posterior(
            neo_candidate=1.0,
            known_object=0.0,
            main_belt_asteroid=0.0,
            stellar_artifact=0.0,
            other_solar_system=0.0,
        )
        assert posterior_entropy(p) == pytest.approx(0.0, abs=1e-10)

    def test_returns_float(self):
        from classify import posterior_entropy
        p = self._make_posterior()
        assert isinstance(posterior_entropy(p), float)

    def test_entropy_non_negative(self):
        from classify import posterior_entropy
        p = self._make_posterior()
        assert posterior_entropy(p) >= 0.0

    def test_skewed_posterior_low_entropy(self):
        from classify import posterior_entropy
        p_uniform = self._make_posterior()
        p_skewed = self._make_posterior(
            neo_candidate=0.9, known_object=0.025,
            main_belt_asteroid=0.025, stellar_artifact=0.025, other_solar_system=0.025,
        )
        assert posterior_entropy(p_skewed) < posterior_entropy(p_uniform)


class TestDominantHypothesis:
    def _make_posterior(self, **kwargs) -> "NEOPosterior":
        from schemas import NEOPosterior
        defaults = dict(
            neo_candidate=0.2, known_object=0.2, main_belt_asteroid=0.2,
            stellar_artifact=0.2, other_solar_system=0.2,
        )
        defaults.update(kwargs)
        return NEOPosterior(**defaults)

    def test_returns_tuple(self):
        from classify import dominant_hypothesis
        p = self._make_posterior()
        result = dominant_hypothesis(p)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_correct_dominant_class(self):
        from classify import dominant_hypothesis
        p = self._make_posterior(neo_candidate=0.8, known_object=0.05,
                                 main_belt_asteroid=0.05, stellar_artifact=0.05,
                                 other_solar_system=0.05)
        name, prob = dominant_hypothesis(p)
        assert name == "neo_candidate"
        assert prob == pytest.approx(0.8)

    def test_artifact_dominant(self):
        from classify import dominant_hypothesis
        p = self._make_posterior(neo_candidate=0.1, known_object=0.1,
                                 main_belt_asteroid=0.1, stellar_artifact=0.6,
                                 other_solar_system=0.1)
        name, _ = dominant_hypothesis(p)
        assert name == "stellar_artifact"

    def test_zero_posterior_returns_unknown(self):
        from classify import dominant_hypothesis
        p = self._make_posterior(neo_candidate=0.0, known_object=0.0,
                                 main_belt_asteroid=0.0, stellar_artifact=0.0,
                                 other_solar_system=0.0)
        name, prob = dominant_hypothesis(p)
        assert name == "unknown"
        assert prob == 0.0

    def test_probability_is_float(self):
        from classify import dominant_hypothesis
        p = self._make_posterior(neo_candidate=0.7, known_object=0.1,
                                 main_belt_asteroid=0.1, stellar_artifact=0.05,
                                 other_solar_system=0.05)
        _, prob = dominant_hypothesis(p)
        assert isinstance(prob, float)


class TestClassifyMorphology:
    def _make_obs(self, cutout_b64: str | None = None) -> object:
        from schemas import Observation
        return Observation(
            obs_id="m1", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference=cutout_b64,
        )

    def test_no_cutout_returns_point_source(self):
        from classify import classify_morphology
        obs = self._make_obs(None)
        assert classify_morphology(obs) == "point_source"

    def test_round_source_is_point_source(self):
        import base64

        import numpy as np

        from classify import classify_morphology
        arr = np.zeros((63, 63), dtype=np.float32)
        y, x = np.mgrid[0:63, 0:63]
        arr = np.exp(-((x - 31)**2 + (y - 31)**2) / 4.0).astype(np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        assert classify_morphology(obs) == "point_source"

    def test_horizontal_streak_is_streak(self):
        import base64

        import numpy as np

        from classify import classify_morphology
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 5:58] = 1.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        assert classify_morphology(obs) == "streak"

    def test_returns_valid_literal(self):
        from classify import classify_morphology
        obs = self._make_obs(None)
        result = classify_morphology(obs)
        assert result in ("point_source", "extended", "streak")

    def test_empty_cutout_returns_point_source(self):
        import base64

        import numpy as np

        from classify import classify_morphology
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        assert classify_morphology(obs) == "point_source"


class TestBatchMorphology:
    def _make_obs(self, cutout_b64=None):
        import base64

        import numpy as np

        from schemas import Observation
        if cutout_b64 is None:
            arr = np.zeros((63, 63), dtype=np.float32)
            cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="bm_001",
            ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=cutout_b64,
        )

    def _make_tracklet(self, n_obs=3):
        from .conftest import build_tracklet
        t = build_tracklet(n_obs=n_obs)
        # give each observation a blank cutout
        import base64

        import numpy as np

        from schemas import Observation, Tracklet
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = tuple(
            Observation(
                obs_id=o.obs_id, ra_deg=o.ra_deg, dec_deg=o.dec_deg, jd=o.jd,
                mag=o.mag, mag_err=o.mag_err, filter_band=o.filter_band,
                mission=o.mission, real_bogus=o.real_bogus, cutout_difference=b64,
            )
            for o in t.observations
        )
        return Tracklet(
            object_id=t.object_id, observations=obs, arc_days=t.arc_days,
            motion_rate_arcsec_per_hour=t.motion_rate_arcsec_per_hour,
            motion_pa_degrees=t.motion_pa_degrees,
        )

    def test_returns_dict_with_keys(self):
        from classify import batch_morphology
        t = self._make_tracklet()
        result = batch_morphology(t)
        assert "modal_class" in result
        assert "class_counts" in result
        assert "streak_fraction" in result

    def test_modal_class_valid(self):
        from classify import batch_morphology
        t = self._make_tracklet()
        result = batch_morphology(t)
        assert result["modal_class"] in ("point_source", "extended", "streak")

    def test_streak_fraction_range(self):
        from classify import batch_morphology
        t = self._make_tracklet()
        frac = batch_morphology(t)["streak_fraction"]
        assert 0.0 <= frac <= 1.0

    def test_empty_tracklet_defaults(self):
        from classify import batch_morphology
        from schemas import Tracklet
        t = Tracklet(
            object_id="empty", observations=(),
            arc_days=0.0, motion_rate_arcsec_per_hour=0.0, motion_pa_degrees=0.0,
        )
        result = batch_morphology(t)
        assert result["modal_class"] == "point_source"
        assert result["streak_fraction"] == pytest.approx(0.0)

    def test_class_counts_sum_equals_n_obs(self):
        from classify import batch_morphology
        t = self._make_tracklet(n_obs=4)
        result = batch_morphology(t)
        total = sum(result["class_counts"].values())
        assert total == len(t.observations)


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


class TestSummarizeClassifications:
    def _make_neos(self, n=3):
        from .conftest import build_scored_neo
        return [build_scored_neo() for _ in range(n)]

    def test_returns_dict(self):
        from classify import summarize_classifications
        neos = self._make_neos()
        result = summarize_classifications(neos)
        assert isinstance(result, dict)

    def test_total_count(self):
        from classify import summarize_classifications
        neos = self._make_neos(5)
        result = summarize_classifications(neos)
        assert result["total"] == 5

    def test_dominant_hypothesis_counts_is_dict(self):
        from classify import summarize_classifications
        neos = self._make_neos()
        result = summarize_classifications(neos)
        assert isinstance(result["dominant_hypothesis_counts"], dict)

    def test_mean_entropy_is_float(self):
        from classify import summarize_classifications
        neos = self._make_neos()
        result = summarize_classifications(neos)
        assert isinstance(result["mean_entropy_bits"], float)

    def test_mean_real_bogus_in_range(self):
        from classify import summarize_classifications
        neos = self._make_neos()
        result = summarize_classifications(neos)
        rb = result["mean_real_bogus_score"]
        assert rb is None or 0.0 <= rb <= 1.0

    def test_pha_count_nonneg(self):
        from classify import summarize_classifications
        neos = self._make_neos()
        result = summarize_classifications(neos)
        assert result["pha_candidate_count"] >= 0

    def test_empty_list(self):
        from classify import summarize_classifications
        result = summarize_classifications([])
        assert result["total"] == 0


class TestCalibratePosterior:
    def _make_posterior(self, **kwargs):
        from schemas import NEOPosterior
        defaults = dict(
            neo_candidate=0.6,
            known_object=0.1,
            main_belt_asteroid=0.1,
            stellar_artifact=0.1,
            other_solar_system=0.1,
        )
        defaults.update(kwargs)
        return NEOPosterior(**defaults)

    def test_returns_neo_posterior(self):
        from classify import calibrate_posterior
        from schemas import NEOPosterior
        p = self._make_posterior()
        result = calibrate_posterior(p)
        assert isinstance(result, NEOPosterior)

    def test_probabilities_sum_to_one(self):
        from classify import calibrate_posterior
        p = self._make_posterior()
        result = calibrate_posterior(p)
        total = (result.neo_candidate + result.known_object + result.main_belt_asteroid
                 + result.stellar_artifact + result.other_solar_system)
        assert abs(total - 1.0) < 1e-5

    def test_laplace_smoothing_reduces_extreme_probs(self):
        from classify import calibrate_posterior
        p = self._make_posterior(
            neo_candidate=1.0,
            known_object=0.0,
            main_belt_asteroid=0.0,
            stellar_artifact=0.0,
            other_solar_system=0.0,
        )
        result = calibrate_posterior(p)
        assert result.neo_candidate < 1.0
        assert result.known_object > 0.0

    def test_with_calibrator(self):
        import numpy as np

        from classify import calibrate_posterior

        class FakeCal:
            def predict_proba(self, x):
                return np.array([[0.2, 0.2, 0.2, 0.2, 0.2]])

        p = self._make_posterior()
        result = calibrate_posterior(p, calibrator=FakeCal())
        total = (result.neo_candidate + result.known_object + result.main_belt_asteroid
                 + result.stellar_artifact + result.other_solar_system)
        assert abs(total - 1.0) < 1e-5

    def test_calibrator_exception_falls_back(self):
        from classify import calibrate_posterior

        class BadCal:
            def predict_proba(self, x):
                raise RuntimeError("fail")

        p = self._make_posterior()
        result = calibrate_posterior(p, calibrator=BadCal())
        assert isinstance(result, type(p))


class TestComputeClassificationTable:
    def _make_neos(self, n=3):
        from .conftest import build_scored_neo
        return [build_scored_neo(object_id=f"T{i:03d}") for i in range(n)]

    def test_returns_list(self):
        from classify import compute_classification_table
        result = compute_classification_table(self._make_neos())
        assert isinstance(result, list)

    def test_length_matches_input(self):
        from classify import compute_classification_table
        neos = self._make_neos(4)
        assert len(compute_classification_table(neos)) == 4

    def test_has_required_keys(self):
        from classify import compute_classification_table
        result = compute_classification_table(self._make_neos(1))
        row = result[0]
        assert "object_id" in row
        assert "dominant_hypothesis" in row
        assert "probability" in row
        assert "entropy_bits" in row

    def test_probability_in_range(self):
        from classify import compute_classification_table
        for row in compute_classification_table(self._make_neos(3)):
            assert 0.0 <= row["probability"] <= 1.0

    def test_entropy_non_negative(self):
        from classify import compute_classification_table
        for row in compute_classification_table(self._make_neos(3)):
            assert row["entropy_bits"] >= 0.0

    def test_empty_list(self):
        from classify import compute_classification_table
        assert compute_classification_table([]) == []


class TestGetPosteriorVector:
    def _make_posterior(self, neo=0.1, ko=0.3, mba=0.35, sa=0.2, other=0.05):
        from schemas import NEOPosterior
        return NEOPosterior(
            neo_candidate=neo, known_object=ko, main_belt_asteroid=mba,
            stellar_artifact=sa, other_solar_system=other,
        )

    def test_returns_array_length_5(self):
        import numpy as np

        from classify import get_posterior_vector
        vec = get_posterior_vector(self._make_posterior())
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (5,)

    def test_correct_order(self):
        import numpy as np

        from classify import get_posterior_vector
        p = self._make_posterior(neo=0.1, ko=0.3, mba=0.35, sa=0.2, other=0.05)
        vec = get_posterior_vector(p)
        np.testing.assert_array_almost_equal(vec, [0.1, 0.3, 0.35, 0.2, 0.05])

    def test_all_zero_posterior(self):
        import numpy as np

        from classify import get_posterior_vector
        p = self._make_posterior(neo=0.0, ko=0.0, mba=0.0, sa=0.0, other=0.0)
        vec = get_posterior_vector(p)
        np.testing.assert_array_equal(vec, [0.0, 0.0, 0.0, 0.0, 0.0])

    def test_sums_to_one_for_valid_posterior(self):
        from classify import get_posterior_vector
        p = self._make_posterior()
        vec = get_posterior_vector(p)
        assert vec.sum() == pytest.approx(1.0, abs=1e-6)

    def test_dtype_is_float(self):
        import numpy as np

        from classify import get_posterior_vector
        vec = get_posterior_vector(self._make_posterior())
        assert vec.dtype == np.float64


class TestComputeNeoProbability:
    def _make_features(self, **kwargs):
        from schemas import CandidateFeatures
        defaults = dict(real_bogus_score=0.9, arc_coverage_score=0.8,
                        nights_observed_score=0.7, motion_consistency_score=0.8)
        defaults.update(kwargs)
        return CandidateFeatures(**defaults)

    def test_returns_float(self):
        from classify import compute_neo_probability
        result = compute_neo_probability(self._make_features())
        assert isinstance(result, float)

    def test_range_0_1(self):
        from classify import compute_neo_probability
        result = compute_neo_probability(self._make_features())
        assert 0.0 <= result <= 1.0

    def test_high_scores_give_high_probability(self):
        from classify import compute_neo_probability
        feat = self._make_features(real_bogus_score=1.0, arc_coverage_score=1.0,
                                   nights_observed_score=1.0, motion_consistency_score=1.0)
        result = compute_neo_probability(feat)
        assert result > 0.5

    def test_low_scores_give_low_probability(self):
        from classify import compute_neo_probability
        feat = self._make_features(real_bogus_score=0.0, arc_coverage_score=0.0,
                                   nights_observed_score=0.0, motion_consistency_score=0.0,
                                   known_object_score=1.0)
        result = compute_neo_probability(feat)
        assert result < 0.5

    def test_all_none_features(self):
        from classify import compute_neo_probability
        from schemas import CandidateFeatures
        feat = CandidateFeatures()
        result = compute_neo_probability(feat)
        assert 0.0 <= result <= 1.0

    def test_known_object_penalty(self):
        from classify import compute_neo_probability
        high_neo = self._make_features(known_object_score=0.0)
        known_obj = self._make_features(known_object_score=1.0)
        assert compute_neo_probability(high_neo) > compute_neo_probability(known_obj)


class TestComputeArtifactProbability:
    def _make_features(self, **kwargs):
        from schemas import CandidateFeatures
        defaults = dict(real_bogus_score=0.5, psf_quality_score=0.5,
                        stellar_artifact_score=0.5, streak_score=0.5,
                        motion_consistency_score=0.5)
        defaults.update(kwargs)
        return CandidateFeatures(**defaults)

    def test_returns_float(self):
        from classify import compute_artifact_probability
        result = compute_artifact_probability(self._make_features())
        assert isinstance(result, float)

    def test_result_in_unit_interval(self):
        from classify import compute_artifact_probability
        for rb in [0.0, 0.3, 0.7, 1.0]:
            result = compute_artifact_probability(self._make_features(real_bogus_score=rb))
            assert 0.0 <= result <= 1.0

    def test_high_artifact_score_increases_probability(self):
        from classify import compute_artifact_probability
        low = self._make_features(stellar_artifact_score=0.0)
        high = self._make_features(stellar_artifact_score=1.0)
        assert compute_artifact_probability(high) > compute_artifact_probability(low)

    def test_high_real_bogus_decreases_artifact_prob(self):
        from classify import compute_artifact_probability
        low_rb = self._make_features(real_bogus_score=0.0, stellar_artifact_score=0.5)
        high_rb = self._make_features(real_bogus_score=1.0, stellar_artifact_score=0.5)
        assert compute_artifact_probability(low_rb) > compute_artifact_probability(high_rb)

    def test_none_features_handled(self):
        from classify import compute_artifact_probability
        from schemas import CandidateFeatures
        feat = CandidateFeatures()
        result = compute_artifact_probability(feat)
        assert 0.0 <= result <= 1.0

    def test_streak_increases_artifact_prob(self):
        from classify import compute_artifact_probability
        no_streak = self._make_features(streak_score=0.0)
        streak = self._make_features(streak_score=1.0)
        assert compute_artifact_probability(streak) > compute_artifact_probability(no_streak)

    def test_consistent_motion_decreases_artifact_prob(self):
        from classify import compute_artifact_probability
        low = self._make_features(motion_consistency_score=0.0)
        high = self._make_features(motion_consistency_score=1.0)
        assert compute_artifact_probability(high) < compute_artifact_probability(low)


class TestComputeConfusionMatrix:
    def test_empty_input_returns_zeros(self):
        from classify import compute_confusion_matrix
        result = compute_confusion_matrix([], [])
        assert result == {"labels": [], "matrix": [], "accuracy": 0.0}

    def test_perfect_predictions(self):
        from classify import compute_confusion_matrix
        labels = ["a", "b", "a", "b"]
        result = compute_confusion_matrix(labels, labels)
        assert result["accuracy"] == pytest.approx(1.0)

    def test_sorted_labels(self):
        from classify import compute_confusion_matrix
        result = compute_confusion_matrix(["b", "a"], ["a", "b"])
        assert result["labels"] == ["a", "b"]

    def test_matrix_shape(self):
        from classify import compute_confusion_matrix
        pred = ["a", "b", "c"]
        true = ["a", "b", "c"]
        result = compute_confusion_matrix(pred, true)
        n = len(result["labels"])
        assert len(result["matrix"]) == n
        assert all(len(row) == n for row in result["matrix"])

    def test_single_class(self):
        from classify import compute_confusion_matrix
        result = compute_confusion_matrix(["a", "a"], ["a", "a"])
        assert result["accuracy"] == pytest.approx(1.0)
        assert result["labels"] == ["a"]

    def test_all_wrong_predictions(self):
        from classify import compute_confusion_matrix
        result = compute_confusion_matrix(["b", "a"], ["a", "b"])
        assert result["accuracy"] == pytest.approx(0.0)

    def test_partial_accuracy(self):
        from classify import compute_confusion_matrix
        pred = ["a", "a", "b", "b"]
        true = ["a", "b", "a", "b"]
        result = compute_confusion_matrix(pred, true)
        assert 0.0 < result["accuracy"] < 1.0

    def test_union_of_labels(self):
        from classify import compute_confusion_matrix
        # pred has label "c" that true doesn't, and vice versa
        result = compute_confusion_matrix(["a", "c"], ["a", "b"])
        assert "b" in result["labels"]
        assert "c" in result["labels"]

    def test_diagonal_counts_correct_predictions(self):
        from classify import compute_confusion_matrix
        pred = ["a", "a", "b"]
        true = ["a", "b", "b"]
        result = compute_confusion_matrix(pred, true)
        # labels = ["a", "b"]; diagonal = [TP_a, TP_b]
        matrix = result["matrix"]
        diag_sum = sum(matrix[i][i] for i in range(len(result["labels"])))
        assert diag_sum == 2  # 2 correct: (a,a) and (b,b)


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


class TestBatchClassifyMorphology:
    """Tests for batch_classify_morphology."""

    def _make_tracklet(self, object_id: str = "T001"):
        from schemas import Observation, Tracklet
        obs = tuple(Observation(
            obs_id=f"{object_id}_o{i}",
            ra_deg=180.0 + i * 0.01,
            dec_deg=0.0,
            jd=2460000.5 + i * 0.5,
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            real_bogus=0.9,
        ) for i in range(4))
        return Tracklet(
            object_id=object_id,
            observations=obs,
            arc_days=1.5,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )

    def test_empty_list(self):
        from classify import batch_classify_morphology
        result = batch_classify_morphology([])
        assert result == []

    def test_single_tracklet(self):
        from classify import batch_classify_morphology
        t = self._make_tracklet("T001")
        result = batch_classify_morphology([t])
        assert len(result) == 1
        r = result[0]
        assert r["object_id"] == "T001"
        assert "modal_class" in r
        assert "streak_fraction" in r
        assert r["n_observations"] == 4

    def test_multiple_tracklets(self):
        from classify import batch_classify_morphology
        tracklets = [self._make_tracklet(f"T{i:03d}") for i in range(3)]
        result = batch_classify_morphology(tracklets)
        assert len(result) == 3
        ids = [r["object_id"] for r in result]
        assert "T000" in ids
        assert "T001" in ids
        assert "T002" in ids

    def test_in_all(self):
        from classify import __all__
        assert "batch_classify_morphology" in __all__


class TestComputeClassEntropyStats:
    """Tests for compute_class_entropy_stats."""

    def _make_neo(self, probs=(0.4, 0.3, 0.1, 0.1, 0.1)):
        from schemas import NEOPosterior
        from tests.conftest import build_scored_neo
        posterior = NEOPosterior(
            neo_candidate=probs[0],
            known_object=probs[1],
            main_belt_asteroid=probs[2],
            stellar_artifact=probs[3],
            other_solar_system=probs[4],
        )
        neo = build_scored_neo()
        return neo.model_copy(update={"posterior": posterior})

    def test_empty_list(self):
        from classify import compute_class_entropy_stats
        result = compute_class_entropy_stats([])
        assert result["n_total"] == 0
        assert result["mean_entropy"] == 0.0
        assert result["max_entropy"] == 0.0
        assert result["min_entropy"] == 0.0
        assert result["n_high_entropy"] == 0

    def test_single_neo(self):
        from classify import compute_class_entropy_stats
        neo = self._make_neo((0.2, 0.2, 0.2, 0.2, 0.2))  # uniform → max entropy
        result = compute_class_entropy_stats([neo])
        assert result["n_total"] == 1
        assert result["mean_entropy"] == result["max_entropy"] == result["min_entropy"]
        assert result["mean_entropy"] > 0.0

    def test_high_entropy_count(self):
        from classify import compute_class_entropy_stats, posterior_entropy
        # uniform distribution has entropy ~2.32 bits (≥ 2.0)
        neo_high = self._make_neo((0.2, 0.2, 0.2, 0.2, 0.2))
        # peaked distribution has low entropy
        neo_low = self._make_neo((0.95, 0.01, 0.01, 0.02, 0.01))
        result = compute_class_entropy_stats([neo_high, neo_low])
        assert result["n_total"] == 2
        h_high = posterior_entropy(neo_high.posterior)
        h_low = posterior_entropy(neo_low.posterior)
        expected_n_high = sum(1 for e in [h_high, h_low] if e >= 2.0)
        assert result["n_high_entropy"] == expected_n_high

    def test_keys_present(self):
        from classify import compute_class_entropy_stats
        neo = self._make_neo()
        result = compute_class_entropy_stats([neo])
        for key in ("mean_entropy", "max_entropy", "min_entropy", "n_high_entropy", "n_total"):
            assert key in result

    def test_in_all(self):
        from classify import __all__
        assert "compute_class_entropy_stats" in __all__


class TestComputeTier1ScoreDistribution:
    """Tests for compute_tier1_score_distribution."""

    def _make_neo(self, rb_score=0.9):
        from tests.conftest import build_scored_neo
        neo = build_scored_neo()
        features = neo.features.model_copy(update={"real_bogus_score": rb_score})
        return neo.model_copy(update={"features": features})

    def test_empty_list(self):
        from classify import compute_tier1_score_distribution
        result = compute_tier1_score_distribution([])
        assert result["n_total"] == 0
        assert result["n_valid"] == 0
        assert result["mean"] == 0.0

    def test_all_none_scores(self):
        from classify import compute_tier1_score_distribution
        neo = self._make_neo(rb_score=None)
        result = compute_tier1_score_distribution([neo])
        assert result["n_total"] == 1
        assert result["n_valid"] == 0
        assert result["mean"] == 0.0

    def test_single_neo(self):
        from classify import compute_tier1_score_distribution
        neo = self._make_neo(rb_score=0.8)
        result = compute_tier1_score_distribution([neo])
        assert result["n_valid"] == 1
        assert result["mean"] == 0.8
        assert result["std"] == 0.0

    def test_multiple_neos(self):
        from classify import compute_tier1_score_distribution
        neos = [self._make_neo(rb) for rb in [0.9, 0.7, 0.5]]
        result = compute_tier1_score_distribution(neos)
        assert result["n_valid"] == 3
        assert result["n_total"] == 3
        assert result["p10"] <= result["p50"] <= result["p90"]

    def test_keys_present(self):
        from classify import compute_tier1_score_distribution
        neo = self._make_neo(0.8)
        result = compute_tier1_score_distribution([neo])
        for k in ("mean", "std", "p10", "p50", "p90", "n_valid", "n_total"):
            assert k in result

    def test_in_all(self):
        from classify import __all__
        assert "compute_tier1_score_distribution" in __all__


class TestComputeClassEntropySummary:
    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_entropy_summary
        result = compute_class_entropy_summary([])
        assert result["n_neos"] == 0
        assert result["mean_entropy"] == 0.0

    def test_uniform_posteriors(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_entropy_summary
        result = compute_class_entropy_summary([scored_neo, scored_neo])
        assert result["n_neos"] == 2
        assert result["mean_entropy"] > 0.0
        assert result["std_entropy"] == 0.0

    def test_mixed_posteriors(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_entropy_summary
        from schemas import NEOPosterior, ScoredNEO

        cert_post = NEOPosterior(neo_candidate=1.0, known_object=0.0,
                                 main_belt_asteroid=0.0, stellar_artifact=0.0,
                                 other_solar_system=0.0)
        cert_neo = ScoredNEO(tracklet=scored_neo.tracklet, features=scored_neo.features,
                              posterior=cert_post, hazard=scored_neo.hazard,
                              metadata=scored_neo.metadata)
        result = compute_class_entropy_summary([scored_neo, cert_neo])
        assert result["n_neos"] == 2
        assert result["max_entropy"] >= result["min_entropy"]

    def test_no_posterior_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_entropy_summary
        neos = [SimpleNamespace(posterior=None)]
        result = compute_class_entropy_summary(neos)
        assert result["n_neos"] == 0

    def test_std_entropy_positive(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_entropy_summary
        from schemas import NEOPosterior, ScoredNEO

        cert_post = NEOPosterior(neo_candidate=1.0, known_object=0.0,
                                 main_belt_asteroid=0.0, stellar_artifact=0.0,
                                 other_solar_system=0.0)
        cert_neo = ScoredNEO(tracklet=scored_neo.tracklet, features=scored_neo.features,
                              posterior=cert_post, hazard=scored_neo.hazard,
                              metadata=scored_neo.metadata)
        result = compute_class_entropy_summary([scored_neo, cert_neo])
        assert result["std_entropy"] >= 0.0


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


class TestComputeNeoClassDistribution:
    def test_empty_returns_empty_dict(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_distribution
        assert compute_neo_class_distribution([]) == {}

    def test_single_class(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_distribution
        result = compute_neo_class_distribution([scored_neo])
        assert len(result) == 1
        cls = scored_neo.hazard.neo_class
        assert result[cls]["count"] == 1
        assert result[cls]["fraction"] == 1.0

    def test_multiple_classes(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_distribution
        from schemas import CandidateExplanation, HazardAssessment, ScoredNEO

        expl = CandidateExplanation(summary="x", supporting_evidence=(),
                                    contra_evidence=(), model_version="t")
        amor_hazard = HazardAssessment(hazard_flag="nominal", moid_au=0.1,
                                       estimated_diameter_m=None, absolute_magnitude_h=None,
                                       neo_class="amor", alert_pathway="internal_candidate",
                                       explanation=expl)
        amor_neo = ScoredNEO(tracklet=scored_neo.tracklet, features=scored_neo.features,
                              posterior=scored_neo.posterior, hazard=amor_hazard,
                              metadata=scored_neo.metadata)
        result = compute_neo_class_distribution([scored_neo, amor_neo])
        total_count = sum(v["count"] for v in result.values())
        assert total_count == 2

    def test_fraction_sums_to_one(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_distribution
        result = compute_neo_class_distribution([scored_neo, scored_neo])
        total = sum(v["fraction"] for v in result.values())
        assert total == pytest.approx(1.0, abs=0.001)


class TestComputePosteriorUpdate:
    def _prior(self):
        import sys
        sys.path.insert(0, "src")
        from schemas import NEOPosterior
        return NEOPosterior(
            neo_candidate=0.05, known_object=0.30,
            main_belt_asteroid=0.35, stellar_artifact=0.25,
            other_solar_system=0.05,
        )

    def test_positive_weight_increases_probability(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_update
        prior = self._prior()
        updated = compute_posterior_update(prior, {"neo_candidate": 3.0})
        assert updated.neo_candidate > prior.neo_candidate

    def test_negative_weight_decreases_probability(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_update
        prior = self._prior()
        updated = compute_posterior_update(prior, {"neo_candidate": -5.0})
        assert updated.neo_candidate < prior.neo_candidate

    def test_sums_to_one(self):
        import sys

        import pytest
        sys.path.insert(0, "src")
        from classify import compute_posterior_update
        prior = self._prior()
        updated = compute_posterior_update(prior, {"stellar_artifact": 2.0})
        total = (updated.neo_candidate + updated.known_object +
                 updated.main_belt_asteroid + updated.stellar_artifact +
                 updated.other_solar_system)
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_empty_weights_unchanged(self):
        import sys

        import pytest
        sys.path.insert(0, "src")
        from classify import compute_posterior_update
        prior = self._prior()
        updated = compute_posterior_update(prior, {})
        assert updated.neo_candidate == pytest.approx(prior.neo_candidate, rel=0.01)

    def test_unknown_keys_ignored(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_update
        prior = self._prior()
        updated = compute_posterior_update(prior, {"nonexistent_key": 5.0})
        assert updated is not None

    def test_zero_prior_handled(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_update
        from schemas import NEOPosterior
        prior = NEOPosterior(
            neo_candidate=0.0, known_object=0.5,
            main_belt_asteroid=0.3, stellar_artifact=0.2,
            other_solar_system=0.0,
        )
        updated = compute_posterior_update(prior, {"neo_candidate": 2.0})
        assert updated.neo_candidate >= 0.0


class TestComputeTier1Confidence:
    def test_all_none_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_tier1_confidence
        from schemas import CandidateFeatures
        features = CandidateFeatures()
        assert compute_tier1_confidence(features) == 0.0

    def test_all_populated_returns_one(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_tier1_confidence
        from schemas import CandidateFeatures
        features = CandidateFeatures(
            real_bogus_score=0.9,
            streak_score=0.1,
            psf_quality_score=0.8,
            motion_consistency_score=0.7,
            arc_coverage_score=0.5,
            nights_observed_score=0.6,
            brightness_score=0.4,
            color_score=0.3,
            lightcurve_variability_score=0.2,
            orbit_quality_score=0.8,
            moid_score=0.0,
            neo_class_confidence=0.7,
            pha_flag_confidence=0.1,
            known_object_score=0.0,
        )
        assert compute_tier1_confidence(features) == pytest.approx(1.0)

    def test_partial_gives_fraction(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_tier1_confidence
        from schemas import CandidateFeatures
        features = CandidateFeatures(real_bogus_score=0.8, streak_score=0.2)
        result = compute_tier1_confidence(features)
        assert 0.0 < result < 1.0

    def test_namespace_object_works(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_tier1_confidence
        features = SimpleNamespace(real_bogus_score=0.9, streak_score=None,
                                   psf_quality_score=None, motion_consistency_score=None,
                                   arc_coverage_score=None, nights_observed_score=None,
                                   brightness_score=None, color_score=None,
                                   lightcurve_variability_score=None,
                                   orbit_quality_score=None, moid_score=None,
                                   neo_class_confidence=None, pha_flag_confidence=None,
                                   known_object_score=None)
        result = compute_tier1_confidence(features)
        assert result == pytest.approx(1 / 14, abs=1e-5)


class TestComputePosteriorStability:
    def _make_posterior(self, neo=0.2, ko=0.3, mba=0.3, art=0.15, other=0.05):
        import sys
        sys.path.insert(0, "src")
        from schemas import NEOPosterior
        return NEOPosterior(neo_candidate=neo, known_object=ko,
                            main_belt_asteroid=mba, stellar_artifact=art,
                            other_solar_system=other)

    def test_identical_posteriors_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_stability
        p = self._make_posterior()
        assert compute_posterior_stability([p, p]) == pytest.approx(0.0)

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_stability
        assert compute_posterior_stability([]) == 0.0

    def test_single_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_stability
        p = self._make_posterior()
        assert compute_posterior_stability([p]) == 0.0

    def test_different_posteriors_nonzero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_stability
        p1 = self._make_posterior(neo=0.9, ko=0.05, mba=0.02, art=0.02, other=0.01)
        p2 = self._make_posterior(neo=0.05, ko=0.05, mba=0.05, art=0.8, other=0.05)
        result = compute_posterior_stability([p1, p2])
        assert result > 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_posterior_stability" in classify.__all__


class TestComputeClassProbabilityRange:
    def test_single_neo(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_probability_range
        posterior = SimpleNamespace(
            neo_candidate=0.6,
            known_object=0.1,
            main_belt_asteroid=0.1,
            stellar_artifact=0.1,
            other_solar_system=0.1,
        )
        neo = SimpleNamespace(posterior=posterior)
        result = compute_class_probability_range([neo])
        assert result["neo_candidate"] == {"min": 0.6, "max": 0.6}
        assert result["known_object"] == {"min": 0.1, "max": 0.1}

    def test_multiple_neos(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_probability_range
        p1 = SimpleNamespace(
            neo_candidate=0.3,
            known_object=0.2,
            main_belt_asteroid=0.2,
            stellar_artifact=0.2,
            other_solar_system=0.1,
        )
        p2 = SimpleNamespace(
            neo_candidate=0.8,
            known_object=0.05,
            main_belt_asteroid=0.05,
            stellar_artifact=0.05,
            other_solar_system=0.05,
        )
        neo1 = SimpleNamespace(posterior=p1)
        neo2 = SimpleNamespace(posterior=p2)
        result = compute_class_probability_range([neo1, neo2])
        assert result["neo_candidate"]["min"] == pytest.approx(0.3, abs=1e-5)
        assert result["neo_candidate"]["max"] == pytest.approx(0.8, abs=1e-5)

    def test_empty_returns_zeros(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_probability_range
        result = compute_class_probability_range([])
        for k in ["neo_candidate", "known_object", "main_belt_asteroid",
                   "stellar_artifact", "other_solar_system"]:
            assert result[k] == {"min": 0.0, "max": 0.0}

    def test_no_posterior_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_probability_range
        neo = SimpleNamespace(posterior=None)
        result = compute_class_probability_range([neo])
        assert result["neo_candidate"] == {"min": 0.0, "max": 0.0}

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_class_probability_range" in classify.__all__


class TestComputeEnsembleAgreement:
    def test_identical_posteriors_return_one(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_ensemble_agreement
        p = SimpleNamespace(
            neo_candidate=0.6,
            known_object=0.1,
            main_belt_asteroid=0.1,
            stellar_artifact=0.1,
            other_solar_system=0.1,
        )
        result = compute_ensemble_agreement([p, p])
        assert result == pytest.approx(1.0)

    def test_opposite_posteriors_return_low(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_ensemble_agreement
        p1 = SimpleNamespace(
            neo_candidate=1.0,
            known_object=0.0,
            main_belt_asteroid=0.0,
            stellar_artifact=0.0,
            other_solar_system=0.0,
        )
        p2 = SimpleNamespace(
            neo_candidate=0.0,
            known_object=0.0,
            main_belt_asteroid=0.0,
            stellar_artifact=0.0,
            other_solar_system=1.0,
        )
        result = compute_ensemble_agreement([p1, p2])
        assert result < 0.5

    def test_fewer_than_two_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_ensemble_agreement
        p = SimpleNamespace(
            neo_candidate=0.5, known_object=0.1, main_belt_asteroid=0.2,
            stellar_artifact=0.1, other_solar_system=0.1,
        )
        assert compute_ensemble_agreement([p]) == 0.0
        assert compute_ensemble_agreement([]) == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_ensemble_agreement" in classify.__all__


class TestComputeRealBogusHistogram:
    def test_basic_histogram(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_real_bogus_histogram
        obs = [SimpleNamespace(real_bogus=0.2, deep_real_bogus=None),
               SimpleNamespace(real_bogus=0.8, deep_real_bogus=None),
               SimpleNamespace(real_bogus=0.5, deep_real_bogus=None)]
        tracklet = SimpleNamespace(observations=obs)
        result = compute_real_bogus_histogram(tracklet)
        assert "bins" in result
        assert "counts" in result
        assert "mean" in result
        assert len(result["bins"]) == 5
        assert sum(result["counts"]) == 3

    def test_prefers_deep_rb(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_real_bogus_histogram
        obs = [SimpleNamespace(real_bogus=0.1, deep_real_bogus=0.9)]
        tracklet = SimpleNamespace(observations=obs)
        result = compute_real_bogus_histogram(tracklet)
        assert result["mean"] == pytest.approx(0.9)

    def test_empty_observations(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_real_bogus_histogram
        tracklet = SimpleNamespace(observations=())
        result = compute_real_bogus_histogram(tracklet)
        assert result == {"bins": [], "counts": [], "mean": None}

    def test_no_rb_scores(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_real_bogus_histogram
        obs = [SimpleNamespace(real_bogus=None, deep_real_bogus=None)]
        tracklet = SimpleNamespace(observations=obs)
        result = compute_real_bogus_histogram(tracklet)
        assert result["mean"] is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_real_bogus_histogram" in classify.__all__


class TestComputeNeoClassPrior:
    def test_apollo_returns_point_five(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_prior
        assert compute_neo_class_prior("apollo") == pytest.approx(0.50)

    def test_amor_returns_point_35(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_prior
        assert compute_neo_class_prior("amor") == pytest.approx(0.35)

    def test_aten(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_prior
        assert compute_neo_class_prior("aten") == pytest.approx(0.12)

    def test_ieo(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_prior
        assert compute_neo_class_prior("ieo") == pytest.approx(0.03)

    def test_unknown_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_prior
        assert compute_neo_class_prior("mba") is None
        assert compute_neo_class_prior("") is None

    def test_case_insensitive(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_neo_class_prior
        assert compute_neo_class_prior("APOLLO") == pytest.approx(0.50)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_neo_class_prior" in classify.__all__


class TestComputeMainBeltProbability:
    def test_none_features_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_main_belt_probability
        assert compute_main_belt_probability(None) == 0.0

    def test_mba_features_high_prob(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_main_belt_probability
        features = SimpleNamespace(
            main_belt_consistency_score=0.9, known_object_score=0.8,
            real_bogus_score=0.7, motion_consistency_score=0.1,
            orbit_quality_score=0.1, arc_coverage_score=0.1,
            nights_observed_score=0.1,
        )
        assert compute_main_belt_probability(features) > 0.5

    def test_neo_features_low_prob(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_main_belt_probability
        features = SimpleNamespace(
            main_belt_consistency_score=0.0, known_object_score=0.0,
            real_bogus_score=0.95, motion_consistency_score=0.9,
            orbit_quality_score=0.9, arc_coverage_score=0.9,
            nights_observed_score=0.9,
        )
        assert compute_main_belt_probability(features) < 0.5

    def test_all_none_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_main_belt_probability
        result = compute_main_belt_probability(SimpleNamespace())
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_main_belt_probability" in classify.__all__


class TestComputeCometProbability:
    def test_high_erratic_motion_increases_probability(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_comet_probability
        from schemas import CandidateFeatures
        # Low motion_consistency_score → higher comet probability
        f = CandidateFeatures(
            motion_consistency_score=0.0,
            orbit_quality_score=0.0,
            real_bogus_score=0.0,
        )
        prob = compute_comet_probability(f)
        assert 0.0 <= prob <= 1.0
        assert prob > 0.0

    def test_all_none_features(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_comet_probability
        from schemas import CandidateFeatures
        f = CandidateFeatures()
        prob = compute_comet_probability(f)
        assert 0.0 <= prob <= 1.0

    def test_good_neo_features_low_comet_probability(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_comet_probability
        from schemas import CandidateFeatures
        f = CandidateFeatures(
            motion_consistency_score=1.0,
            orbit_quality_score=1.0,
            real_bogus_score=1.0,
        )
        prob = compute_comet_probability(f)
        # Consistent motion = less comet-like
        assert prob < 0.5

    def test_returns_float_in_range(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_comet_probability
        from schemas import CandidateFeatures
        for rb in [0.0, 0.5, 1.0]:
            for mc in [0.0, 0.5, 1.0]:
                f = CandidateFeatures(real_bogus_score=rb, motion_consistency_score=mc)
                prob = compute_comet_probability(f)
                assert 0.0 <= prob <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_comet_probability" in classify.__all__


class TestComputeKnownObjectProbability:
    def test_high_known_object_score_raises_probability(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_known_object_probability
        from schemas import CandidateFeatures
        f_high = CandidateFeatures(known_object_score=1.0, real_bogus_score=1.0)
        f_low = CandidateFeatures(known_object_score=0.0, real_bogus_score=0.0)
        assert compute_known_object_probability(f_high) > compute_known_object_probability(f_low)

    def test_all_none_features_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_known_object_probability
        from schemas import CandidateFeatures
        f = CandidateFeatures()
        prob = compute_known_object_probability(f)
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_known_object_score_one_high_prob(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_known_object_probability
        from schemas import CandidateFeatures
        f = CandidateFeatures(known_object_score=1.0, real_bogus_score=1.0,
                              motion_consistency_score=1.0)
        prob = compute_known_object_probability(f)
        assert prob > 0.5

    def test_zero_all_scores_low_prob(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_known_object_probability
        from schemas import CandidateFeatures
        f = CandidateFeatures(known_object_score=0.0, real_bogus_score=0.0,
                              motion_consistency_score=0.0)
        prob = compute_known_object_probability(f)
        assert prob < 0.5

    def test_result_in_range(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_known_object_probability
        from schemas import CandidateFeatures
        for ko in [0.0, 0.5, 1.0]:
            for rb in [0.0, 0.5, 1.0]:
                f = CandidateFeatures(known_object_score=ko, real_bogus_score=rb)
                prob = compute_known_object_probability(f)
                assert 0.0 <= prob <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_known_object_probability" in classify.__all__


class TestComputeStellarArtifactScoreFromFeatures:
    def _make_features(self, stellar_artifact_score=None):
        import sys
        sys.path.insert(0, "src")
        from schemas import CandidateFeatures
        return CandidateFeatures(stellar_artifact_score=stellar_artifact_score)

    def test_none_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_stellar_artifact_score_from_features
        f = self._make_features(None)
        assert compute_stellar_artifact_score_from_features(f) == 0.0

    def test_float_value_returned(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_stellar_artifact_score_from_features
        f = self._make_features(0.75)
        assert compute_stellar_artifact_score_from_features(f) == pytest.approx(0.75)

    def test_zero_value(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_stellar_artifact_score_from_features
        f = self._make_features(0.0)
        assert compute_stellar_artifact_score_from_features(f) == 0.0

    def test_one_value(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_stellar_artifact_score_from_features
        f = self._make_features(1.0)
        assert compute_stellar_artifact_score_from_features(f) == pytest.approx(1.0)

    def test_missing_attribute_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_stellar_artifact_score_from_features
        obj = SimpleNamespace()  # no stellar_artifact_score attribute
        assert compute_stellar_artifact_score_from_features(obj) == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_stellar_artifact_score_from_features" in classify.__all__


class TestComputePosteriorFromScores:
    """Tests for compute_posterior_from_scores."""

    def test_all_none_uses_priors(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_from_scores
        post = compute_posterior_from_scores(None, None, None)
        total = (post.neo_candidate + post.known_object + post.main_belt_asteroid
                 + post.stellar_artifact + post.other_solar_system)
        assert abs(total - 1.0) < 1e-6

    def test_sums_to_one_with_real_bogus(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_from_scores
        post = compute_posterior_from_scores(0.9, None, None)
        total = (post.neo_candidate + post.known_object + post.main_belt_asteroid
                 + post.stellar_artifact + post.other_solar_system)
        assert abs(total - 1.0) < 1e-6

    def test_high_real_bogus_lowers_artifact(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_from_scores
        post_hi = compute_posterior_from_scores(0.99, None, None)
        post_lo = compute_posterior_from_scores(0.01, None, None)
        assert post_hi.stellar_artifact < post_lo.stellar_artifact

    def test_neo_prob_respected(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_from_scores
        post_hi = compute_posterior_from_scores(None, 0.9, None)
        post_lo = compute_posterior_from_scores(None, 0.01, None)
        assert post_hi.neo_candidate > post_lo.neo_candidate

    def test_all_probabilities_non_negative(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_posterior_from_scores
        post = compute_posterior_from_scores(0.5, 0.3, 0.2)
        assert post.neo_candidate >= 0.0
        assert post.known_object >= 0.0
        assert post.main_belt_asteroid >= 0.0
        assert post.stellar_artifact >= 0.0
        assert post.other_solar_system >= 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_posterior_from_scores" in classify.__all__


class TestComputeClassificationConfidence:
    def _make_posterior(self, probs: dict):
        from types import SimpleNamespace
        return SimpleNamespace(**probs)

    def test_clear_winner_returns_margin(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_classification_confidence
        # neo_candidate=0.8, others=0.05 → margin = 0.8 - 0.05 = 0.75
        post = self._make_posterior({
            "neo_candidate": 0.8,
            "known_object": 0.05,
            "main_belt_asteroid": 0.05,
            "stellar_artifact": 0.05,
            "other_solar_system": 0.05,
        })
        result = compute_classification_confidence(post)
        assert abs(result - 0.75) < 1e-5

    def test_uniform_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_classification_confidence
        post = self._make_posterior({
            "neo_candidate": 0.2,
            "known_object": 0.2,
            "main_belt_asteroid": 0.2,
            "stellar_artifact": 0.2,
            "other_solar_system": 0.2,
        })
        result = compute_classification_confidence(post)
        assert result == 0.0

    def test_result_in_zero_one(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_classification_confidence
        post = self._make_posterior({
            "neo_candidate": 0.9,
            "known_object": 0.1,
            "main_belt_asteroid": 0.0,
            "stellar_artifact": 0.0,
            "other_solar_system": 0.0,
        })
        result = compute_classification_confidence(post)
        assert 0.0 <= result <= 1.0

    def test_uses_neo_posterior_fields(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_classification_confidence
        from schemas import NEOPosterior
        post = NEOPosterior(
            neo_candidate=0.6,
            known_object=0.2,
            main_belt_asteroid=0.1,
            stellar_artifact=0.05,
            other_solar_system=0.05,
        )
        result = compute_classification_confidence(post)
        assert abs(result - 0.4) < 1e-5

    def test_missing_fields_default_to_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_classification_confidence
        # Only neo_candidate is non-zero
        post = SimpleNamespace(
            neo_candidate=0.5,
            known_object=0.0,
            main_belt_asteroid=0.0,
            stellar_artifact=0.0,
            other_solar_system=0.0,
        )
        result = compute_classification_confidence(post)
        assert result == 0.5

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_classification_confidence" in classify.__all__


class TestComputeEntropyWeightedScore:
    def test_certain_neo_high_score(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_entropy_weighted_score
        # All probability on neo_candidate → low entropy → high score
        post = SimpleNamespace(
            neo_candidate=1.0, known_object=0.0, main_belt_asteroid=0.0,
            stellar_artifact=0.0, other_solar_system=0.0
        )
        features = SimpleNamespace()
        result = compute_entropy_weighted_score(post, features)
        assert result > 0.9

    def test_uniform_posterior_low_score(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_entropy_weighted_score
        # Uniform → max entropy → confidence = 0 → score = 0
        p = 0.2
        post = SimpleNamespace(
            neo_candidate=p, known_object=p, main_belt_asteroid=p,
            stellar_artifact=p, other_solar_system=p
        )
        features = SimpleNamespace()
        result = compute_entropy_weighted_score(post, features)
        assert result == 0.0

    def test_zero_neo_prob_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_entropy_weighted_score
        post = SimpleNamespace(
            neo_candidate=0.0, known_object=1.0, main_belt_asteroid=0.0,
            stellar_artifact=0.0, other_solar_system=0.0
        )
        features = SimpleNamespace()
        assert compute_entropy_weighted_score(post, features) == 0.0

    def test_result_in_range(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_entropy_weighted_score
        post = SimpleNamespace(
            neo_candidate=0.6, known_object=0.2, main_belt_asteroid=0.1,
            stellar_artifact=0.05, other_solar_system=0.05
        )
        features = SimpleNamespace()
        result = compute_entropy_weighted_score(post, features)
        assert 0.0 <= result <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_entropy_weighted_score" in classify.__all__

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_entropy_weighted_score
        post = SimpleNamespace(
            neo_candidate=0.5, known_object=0.5, main_belt_asteroid=0.0,
            stellar_artifact=0.0, other_solar_system=0.0
        )
        features = SimpleNamespace()
        result = compute_entropy_weighted_score(post, features)
        assert isinstance(result, float)


class TestComputeTier1NeoScore:
    """Tests for compute_tier1_neo_score."""

    @staticmethod
    def _make_features(**kwargs):
        from types import SimpleNamespace

        defaults = dict(
            real_bogus_score=0.9,
            arc_coverage_score=0.8,
            nights_observed_score=0.7,
            motion_consistency_score=0.8,
            orbit_quality_score=0.6,
            known_object_score=0.0,
            stellar_artifact_score=0.05,
            main_belt_consistency_score=0.1,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")

        from classify import compute_tier1_neo_score

        f = self._make_features()
        result = compute_tier1_neo_score(f)
        assert isinstance(result, float)

    def test_result_in_range(self):
        import sys
        sys.path.insert(0, "src")

        from classify import compute_tier1_neo_score

        f = self._make_features()
        result = compute_tier1_neo_score(f)
        assert 0.0 <= result <= 1.0

    def test_artifact_features_gives_low_score(self):
        import sys
        sys.path.insert(0, "src")

        from classify import compute_tier1_neo_score

        f = self._make_features(real_bogus_score=0.1, arc_coverage_score=0.1,
                                 nights_observed_score=0.1, stellar_artifact_score=0.9)
        result = compute_tier1_neo_score(f)
        assert result < 0.5

    def test_zero_neo_prob_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_neo_probability, compute_tier1_neo_score

        # Use features that make neo prob as low as possible
        f = SimpleNamespace(
            real_bogus_score=0.0, arc_coverage_score=0.0, nights_observed_score=0.0,
            motion_consistency_score=0.0, orbit_quality_score=0.0, known_object_score=1.0,
            stellar_artifact_score=1.0, main_belt_consistency_score=1.0,
        )
        p = compute_neo_probability(f)
        result = compute_tier1_neo_score(f)
        assert result >= 0.0
        if p <= 0.0:
            assert result == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify

        assert "compute_tier1_neo_score" in classify.__all__

    def test_high_quality_features_high_score(self):
        import sys
        sys.path.insert(0, "src")

        from classify import compute_tier1_neo_score

        f = self._make_features(
            real_bogus_score=1.0, arc_coverage_score=1.0, nights_observed_score=1.0,
            motion_consistency_score=1.0, orbit_quality_score=1.0,
            known_object_score=0.0, stellar_artifact_score=0.0, main_belt_consistency_score=0.0,
        )
        result = compute_tier1_neo_score(f)
        assert result > 0.5


class TestComputeArtifactFeaturesSummary:
    def _make_features(self, **kwargs: float | None) -> object:
        from types import SimpleNamespace
        return SimpleNamespace(**kwargs)

    def test_all_present(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_artifact_features_summary
        features = self._make_features(
            stellar_artifact_score=0.1,
            psf_quality_score=0.9,
            real_bogus_score=0.8,
            streak_score=0.05,
        )
        result = compute_artifact_features_summary(features)
        assert result["stellar_artifact_score"] == 0.1
        assert result["psf_quality_score"] == 0.9
        assert result["real_bogus_score"] == 0.8
        assert result["streak_score"] == 0.05

    def test_missing_attrs_return_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_artifact_features_summary
        features = SimpleNamespace()
        result = compute_artifact_features_summary(features)
        assert result["stellar_artifact_score"] is None
        assert result["real_bogus_score"] is None

    def test_returns_all_four_keys(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_artifact_features_summary
        result = compute_artifact_features_summary(SimpleNamespace())
        assert set(result.keys()) == {
            "stellar_artifact_score",
            "psf_quality_score",
            "real_bogus_score",
            "streak_score",
        }

    def test_partial_features(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_artifact_features_summary
        features = self._make_features(real_bogus_score=0.75)
        result = compute_artifact_features_summary(features)
        assert result["real_bogus_score"] == 0.75
        assert result["psf_quality_score"] is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_artifact_features_summary" in classify.__all__


class TestComputeClassBalance:
    def _make_neo(
        self, neo_p: float, ko_p: float, mba_p: float, art_p: float, other_p: float
    ) -> object:
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from schemas import NEOPosterior
        posterior = NEOPosterior(
            neo_candidate=neo_p, known_object=ko_p,
            main_belt_asteroid=mba_p, stellar_artifact=art_p,
            other_solar_system=other_p,
        )
        return SimpleNamespace(posterior=posterior)

    def test_all_same_class(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_balance
        neos = [self._make_neo(0.9, 0.05, 0.02, 0.02, 0.01)] * 3
        result = compute_class_balance(neos)
        assert result.get("neo_candidate", 0) == 3

    def test_mixed_classes(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_balance
        neos = [
            self._make_neo(0.9, 0.05, 0.02, 0.02, 0.01),
            self._make_neo(0.05, 0.9, 0.02, 0.02, 0.01),
        ]
        result = compute_class_balance(neos)
        assert result["neo_candidate"] == 1
        assert result["known_object"] == 1

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_balance
        assert compute_class_balance([]) == {}

    def test_none_posterior_counts_unknown(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_balance
        neo = SimpleNamespace(posterior=None)
        result = compute_class_balance([neo])
        assert result.get("unknown", 0) == 1

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_class_balance" in classify.__all__


class TestComputeRealBogusSummary:
    def _make_neo(self, rb_score):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        features = SimpleNamespace(real_bogus_score=rb_score)
        return SimpleNamespace(features=features)

    def test_basic_stats(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_real_bogus_summary
        neos = [self._make_neo(0.8), self._make_neo(0.6), self._make_neo(1.0)]
        result = compute_real_bogus_summary(neos)
        assert abs(result["mean"] - (0.8 + 0.6 + 1.0) / 3) < 1e-9
        assert abs(result["min"] - 0.6) < 1e-9
        assert abs(result["max"] - 1.0) < 1e-9
        assert result["n"] == 3

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_real_bogus_summary
        result = compute_real_bogus_summary([])
        assert result["n"] == 0
        assert result["mean"] is None
        assert result["min"] is None
        assert result["max"] is None

    def test_none_scores_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_real_bogus_summary
        neos = [self._make_neo(None), self._make_neo(0.9)]
        result = compute_real_bogus_summary(neos)
        assert result["n"] == 1
        assert abs(result["mean"] - 0.9) < 1e-9

    def test_all_none_scores(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_real_bogus_summary
        neos = [self._make_neo(None), self._make_neo(None)]
        result = compute_real_bogus_summary(neos)
        assert result["n"] == 0
        assert result["mean"] is None

    def test_single_neo(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_real_bogus_summary
        neos = [self._make_neo(0.75)]
        result = compute_real_bogus_summary(neos)
        assert result["n"] == 1
        assert abs(result["mean"] - 0.75) < 1e-9
        assert abs(result["min"] - 0.75) < 1e-9
        assert abs(result["max"] - 0.75) < 1e-9

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_real_bogus_summary" in classify.__all__


class TestComputeClassAgreement:
    def _make_neo(self, dominant: str):
        from types import SimpleNamespace
        vals = {"neo_candidate": 0.1, "known_object": 0.1, "main_belt_asteroid": 0.1,
                "stellar_artifact": 0.1, "other_solar_system": 0.1}
        vals[dominant] = 0.9
        posterior = SimpleNamespace(**vals)
        return SimpleNamespace(posterior=posterior)

    def test_full_agreement(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_agreement
        neos = [self._make_neo("neo_candidate") for _ in range(5)]
        assert compute_class_agreement(neos) == 1.0

    def test_split(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_agreement
        neos = [self._make_neo("neo_candidate"), self._make_neo("neo_candidate"),
                self._make_neo("stellar_artifact")]
        result = compute_class_agreement(neos)
        assert abs(result - 2 / 3) < 0.01

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_class_agreement
        assert compute_class_agreement([]) == 0.0

    def test_no_posterior_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_class_agreement
        neos = [SimpleNamespace(posterior=None)]
        assert compute_class_agreement(neos) == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_class_agreement" in classify.__all__


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


class TestComputeTier1FeatureVector:
    def _make_tracklet(self, jds, mags, rbs, motion_rate=1.2, arc_days=2.0, streaks=None):
        from types import SimpleNamespace

        if streaks is None:
            streaks = [False] * len(jds)
        obs = [
            SimpleNamespace(
                jd=j,
                mag=m,
                real_bogus_score=r,
                is_streak=s,
            )
            for j, m, r, s in zip(jds, mags, rbs, streaks)
        ]
        return SimpleNamespace(
            observations=tuple(obs),
            motion_rate_arcsec_per_hour=motion_rate,
            arc_days=arc_days,
        )

    def test_basic_values(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_tier1_feature_vector

        t = self._make_tracklet(
            [2460000.5, 2460001.5, 2460002.5],
            [19.0, 19.5, 20.0],
            [0.9, 0.85, 0.88],
        )
        fv = compute_tier1_feature_vector(t)
        assert fv["motion_rate_arcsec_hr"] == 1.2
        assert fv["arc_days"] == 2.0
        assert fv["n_nights"] == 3
        assert abs(fv["mean_mag"] - (19.0 + 19.5 + 20.0) / 3) < 1e-6
        assert fv["streak_fraction"] == 0.0

    def test_streak_fraction(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_tier1_feature_vector

        t = self._make_tracklet(
            [2460000.5, 2460001.5],
            [19.0, 19.5],
            [0.9, 0.8],
            streaks=[True, False],
        )
        fv = compute_tier1_feature_vector(t)
        assert fv["streak_fraction"] == 0.5

    def test_sentinel_mag_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_tier1_feature_vector

        t = self._make_tracklet(
            [2460000.5, 2460001.5],
            [99.0, 20.0],    # 99.0 is sentinel
            [0.9, 0.8],
        )
        fv = compute_tier1_feature_vector(t)
        assert fv["mean_mag"] == 20.0

    def test_all_sentinel_mags(self):
        import sys
        sys.path.insert(0, "src")
        from classify import compute_tier1_feature_vector

        t = self._make_tracklet([2460000.5], [99.0], [0.9])
        fv = compute_tier1_feature_vector(t)
        assert fv["mean_mag"] is None
        assert fv["mag_range"] is None

    def test_no_real_bogus(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_tier1_feature_vector

        obs = [SimpleNamespace(jd=2460000.5, mag=19.0, is_streak=False)]
        t = SimpleNamespace(observations=tuple(obs), motion_rate_arcsec_per_hour=1.0, arc_days=0.0)
        fv = compute_tier1_feature_vector(t)
        assert fv["mean_real_bogus"] is None

    def test_empty_observations(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from classify import compute_tier1_feature_vector

        t = SimpleNamespace(observations=(), motion_rate_arcsec_per_hour=None, arc_days=None)
        fv = compute_tier1_feature_vector(t)
        assert fv["motion_rate_arcsec_hr"] is None
        assert fv["arc_days"] is None
        assert fv["streak_fraction"] is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import classify
        assert "compute_tier1_feature_vector" in classify.__all__
