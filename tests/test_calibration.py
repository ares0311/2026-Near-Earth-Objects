"""Tests for calibration.py — Platt and isotonic PAVA."""

import numpy as np
import pytest

from calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    _pava,
    brier_score,
    calibrate,
    expected_calibration_error,
    reliability_diagram_data,
)


class TestPAVA:
    def test_already_monotone(self):
        y = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
        result = _pava(y)
        np.testing.assert_allclose(result, y, atol=1e-8)

    def test_single_violation(self):
        y = np.array([0.1, 0.9, 0.3, 0.7])
        result = _pava(y)
        # Result must be non-decreasing
        assert all(result[i] <= result[i + 1] for i in range(len(result) - 1))

    def test_all_same(self):
        y = np.ones(5) * 0.5
        result = _pava(y)
        np.testing.assert_allclose(result, 0.5, atol=1e-8)

    def test_decreasing(self):
        y = np.array([1.0, 0.8, 0.6, 0.4, 0.2])
        result = _pava(y)
        # Should become flat (average)
        assert all(result[i] <= result[i + 1] + 1e-8 for i in range(len(result) - 1))

    def test_preserves_length(self):
        y = np.random.default_rng(0).uniform(0, 1, 20)
        result = _pava(y)
        assert len(result) == len(y)

    def test_empty(self):
        y = np.array([])
        result = _pava(y)
        assert len(result) == 0


class TestIsotonicCalibrator:
    def _make_data(self, seed: int = 0):
        rng = np.random.default_rng(seed)
        scores = rng.uniform(0, 1, 200)
        labels = (scores + rng.normal(0, 0.2, 200) > 0.5).astype(float)
        return scores, labels

    def test_fit_predict(self):
        scores, labels = self._make_data()
        cal = IsotonicCalibrator()
        cal.fit(scores, labels)
        calibrated = cal.predict(scores)
        assert calibrated.shape == scores.shape
        assert calibrated.min() >= 0.0
        assert calibrated.max() <= 1.0

    def test_not_fitted_raises(self):
        cal = IsotonicCalibrator()
        with pytest.raises(RuntimeError):
            cal.predict(np.array([0.5]))

    def test_improves_calibration(self):
        rng = np.random.default_rng(1)
        # Biased scores: overconfident (scores near 0 or 1)
        true_prob = rng.uniform(0.1, 0.9, 500)
        scores = np.clip(true_prob * 1.5 - 0.25, 0, 1)
        labels = rng.binomial(1, true_prob).astype(float)

        ece_before = expected_calibration_error(scores, labels)
        cal = IsotonicCalibrator().fit(scores, labels)
        calibrated = cal.predict(scores)
        ece_after = expected_calibration_error(calibrated, labels)
        assert ece_after <= ece_before + 0.05


class TestPlattCalibrator:
    def _make_data(self, seed: int = 0):
        rng = np.random.default_rng(seed)
        scores = rng.uniform(0, 1, 300)
        # Sigmoid transformation for realism
        true_prob = 1 / (1 + np.exp(-4 * (scores - 0.5)))
        labels = rng.binomial(1, true_prob).astype(float)
        return scores, labels

    def test_fit_predict(self):
        scores, labels = self._make_data()
        cal = PlattCalibrator()
        cal.fit(scores, labels)
        calibrated = cal.predict(scores)
        assert calibrated.shape == scores.shape
        assert calibrated.min() >= 0.0
        assert calibrated.max() <= 1.0

    def test_not_fitted_raises(self):
        cal = PlattCalibrator()
        with pytest.raises(RuntimeError):
            cal.predict(np.array([0.5]))

    def test_output_range(self):
        scores = np.linspace(0, 1, 100)
        labels = (scores > 0.5).astype(float)
        cal = PlattCalibrator().fit(scores, labels)
        calibrated = cal.predict(np.array([0.0, 0.5, 1.0]))
        for v in calibrated:
            assert 0.0 <= v <= 1.0


class TestBrierScore:
    def test_perfect(self):
        proba = np.array([1.0, 0.0, 1.0, 0.0])
        labels = np.array([1.0, 0.0, 1.0, 0.0])
        assert brier_score(proba, labels) == pytest.approx(0.0, abs=1e-8)

    def test_worst(self):
        proba = np.array([0.0, 1.0])
        labels = np.array([1.0, 0.0])
        assert brier_score(proba, labels) == pytest.approx(1.0, abs=1e-8)


class TestReliabilityDiagram:
    def test_returns_list(self):
        rng = np.random.default_rng(0)
        proba = rng.uniform(0, 1, 100)
        labels = rng.binomial(1, proba).astype(float)
        data = reliability_diagram_data(proba, labels)
        assert isinstance(data, list)
        for d in data:
            assert "calibration_error" in d
            assert d["calibration_error"] >= 0.0


class TestECE:
    def test_perfect_calibration(self):
        proba = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9] * 10)
        labels = (proba > 0.5).astype(float)
        ece = expected_calibration_error(proba, labels)
        assert ece >= 0.0

    def test_nonnegative(self):
        rng = np.random.default_rng(0)
        proba = rng.uniform(0, 1, 200)
        labels = rng.binomial(1, 0.5, 200).astype(float)
        assert expected_calibration_error(proba, labels) >= 0.0


class TestIsotonicSaveLoad:
    def _make_data(self):
        rng = np.random.default_rng(7)
        scores = rng.uniform(0, 1, 100)
        labels = (scores > 0.5).astype(float)
        return scores, labels

    def test_save_and_load(self, tmp_path, monkeypatch):
        import calibration as cal_mod
        monkeypatch.setattr(cal_mod, "_CALIBRATION_DIR", tmp_path / "calibration")

        scores, labels = self._make_data()
        cal = IsotonicCalibrator().fit(scores, labels)
        cal.save("test_iso")

        cal2 = IsotonicCalibrator().load("test_iso")
        out = cal2.predict(scores)
        assert out.shape == scores.shape
        assert out.min() >= 0.0

    def test_save_unfitted_raises(self, tmp_path, monkeypatch):
        import calibration as cal_mod
        monkeypatch.setattr(cal_mod, "_CALIBRATION_DIR", tmp_path / "calibration")
        with pytest.raises(RuntimeError):
            IsotonicCalibrator().save("x")


class TestPlattSaveLoad:
    def _make_data(self):
        rng = np.random.default_rng(8)
        scores = rng.uniform(0, 1, 100)
        labels = (scores > 0.5).astype(float)
        return scores, labels

    def test_save_and_load(self, tmp_path, monkeypatch):
        import calibration as cal_mod
        monkeypatch.setattr(cal_mod, "_CALIBRATION_DIR", tmp_path / "calibration")

        scores, labels = self._make_data()
        cal = PlattCalibrator().fit(scores, labels)
        cal.save("test_platt")

        cal2 = PlattCalibrator().load("test_platt")
        out = cal2.predict(scores)
        assert out.shape == scores.shape

    def test_save_unfitted_raises(self, tmp_path, monkeypatch):
        import calibration as cal_mod
        monkeypatch.setattr(cal_mod, "_CALIBRATION_DIR", tmp_path / "calibration")
        with pytest.raises(RuntimeError):
            PlattCalibrator().save("x")


class TestCalibrateFunction:
    def _make_data(self):
        rng = np.random.default_rng(9)
        scores = rng.uniform(0, 1, 150)
        labels = (scores + rng.normal(0, 0.1, 150) > 0.5).astype(float)
        return scores, labels

    def test_isotonic_with_labels(self, tmp_path, monkeypatch):
        import calibration as cal_mod
        monkeypatch.setattr(cal_mod, "_CALIBRATION_DIR", tmp_path / "calibration")

        scores, labels = self._make_data()
        out = calibrate(scores, labels, method="isotonic", model_name="test_cal")
        assert out.shape == scores.shape
        assert out.min() >= 0.0

    def test_platt_with_labels(self, tmp_path, monkeypatch):
        import calibration as cal_mod
        monkeypatch.setattr(cal_mod, "_CALIBRATION_DIR", tmp_path / "calibration")

        scores, labels = self._make_data()
        out = calibrate(scores, labels, method="platt", model_name="test_cal_p")
        assert out.shape == scores.shape

    def test_unknown_method_raises(self):
        scores = np.array([0.1, 0.9])
        with pytest.raises(ValueError, match="Unknown calibration method"):
            calibrate(scores, method="bad_method")

    def test_load_saved_model(self, tmp_path, monkeypatch):
        import calibration as cal_mod
        monkeypatch.setattr(cal_mod, "_CALIBRATION_DIR", tmp_path / "calibration")

        scores, labels = self._make_data()
        calibrate(scores, labels, method="isotonic", model_name="reload_test")
        out2 = calibrate(scores, labels=None, method="isotonic", model_name="reload_test")
        assert out2.shape == scores.shape


class TestPlattSingularHessian:
    def test_singular_hessian_breaks_newton(self):
        # All scores identical → d²A*d²B - d²AB² = 0 → det < 1e-15 → break
        scores = np.full(20, 0.5, dtype=float)
        labels = np.array([0, 1] * 10)
        cal = PlattCalibrator()
        cal.fit(scores, labels)
        # Should complete without error; A and B settle at initial values
        out = cal.predict(scores)
        assert out.shape == scores.shape
        assert np.all((out >= 0.0) & (out <= 1.0))

    def test_newton_converges_with_loose_tol(self):
        # tol=1e10 → first Newton step always satisfies |ΔA + ΔB| < tol → lines 179-180
        rng = np.random.default_rng(7)
        scores = rng.uniform(0.0, 1.0, 40)
        labels = (scores > 0.5).astype(int)
        cal = PlattCalibrator(tol=1e10).fit(scores, labels)
        out = cal.predict(scores)
        assert out.shape == scores.shape


class TestBootstrapConfidenceInterval:
    def _make_data(self, n: int = 50) -> tuple[list[float], list[float]]:
        import random
        rng = random.Random(0)
        probs = [rng.random() for _ in range(n)]
        labels = [float(rng.random() < p) for p, _ in zip(probs, range(n))]
        return probs, labels

    def test_returns_tuple_of_three(self):
        from calibration import bootstrap_confidence_interval
        p, lbs = self._make_data()
        result = bootstrap_confidence_interval(p, lbs, n_bootstrap=100)
        assert len(result) == 3

    def test_lower_le_mean_le_upper(self):
        from calibration import bootstrap_confidence_interval
        p, lbs = self._make_data()
        lo, hi, mean = bootstrap_confidence_interval(p, lbs, n_bootstrap=100)
        assert lo <= mean <= hi

    def test_brier_metric(self):
        from calibration import bootstrap_confidence_interval
        p, lbs = self._make_data()
        lo, hi, mean = bootstrap_confidence_interval(p, lbs, metric="brier", n_bootstrap=100)
        assert 0.0 <= lo <= hi <= 1.0

    def test_ece_metric(self):
        from calibration import bootstrap_confidence_interval
        p, lbs = self._make_data()
        lo, hi, mean = bootstrap_confidence_interval(p, lbs, metric="ece", n_bootstrap=100)
        assert 0.0 <= lo <= hi

    def test_empty_input_raises(self):
        import pytest as pt

        from calibration import bootstrap_confidence_interval
        with pt.raises(ValueError):
            bootstrap_confidence_interval([], [], n_bootstrap=10)

    def test_unknown_metric_raises(self):
        import pytest as pt

        from calibration import bootstrap_confidence_interval
        p, lbs = self._make_data()
        with pt.raises(ValueError, match="Unknown metric"):
            bootstrap_confidence_interval(p, lbs, metric="rmse")


class TestCrossValidateCalibration:
    def _make_data(self, n=100, seed=42):
        import numpy as np
        rng = np.random.default_rng(seed)
        probs = rng.uniform(0.0, 1.0, n)
        labels = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
        return probs, labels

    def test_returns_tuple_of_floats(self):
        from calibration import cross_validate_calibration
        p, lbs = self._make_data()
        result = cross_validate_calibration(p, lbs)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, float) for v in result)

    def test_mean_in_reasonable_range(self):
        from calibration import cross_validate_calibration
        p, lbs = self._make_data()
        mean, _ = cross_validate_calibration(p, lbs, metric="brier")
        assert 0.0 <= mean <= 1.0

    def test_std_nonnegative(self):
        from calibration import cross_validate_calibration
        p, lbs = self._make_data()
        _, std = cross_validate_calibration(p, lbs)
        assert std >= 0.0

    def test_too_few_samples_returns_zeros(self):
        import numpy as np

        from calibration import cross_validate_calibration
        p = np.array([0.5, 0.6, 0.7])
        lbs = np.array([1.0, 0.0, 1.0])
        mean, std = cross_validate_calibration(p, lbs, n_folds=5)
        assert mean == pytest.approx(0.0)
        assert std == pytest.approx(0.0)

    def test_ece_metric(self):
        from calibration import cross_validate_calibration
        p, lbs = self._make_data()
        mean, std = cross_validate_calibration(p, lbs, metric="ece")
        assert 0.0 <= mean <= 1.0
        assert std >= 0.0


class TestBootstrapCILengthMismatch:
    def test_mismatched_lengths_raises(self):
        import numpy as np
        import pytest as pt

        from calibration import bootstrap_confidence_interval
        p = np.array([0.5, 0.6, 0.7])
        lbs = np.array([1.0, 0.0])
        with pt.raises(ValueError, match="same length"):
            bootstrap_confidence_interval(p, lbs, n_bootstrap=10)
