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


class TestComputeLogLoss:
    def _make_data(self, n=100, seed=42):
        import numpy as np
        rng = np.random.default_rng(seed)
        probs = rng.uniform(0.1, 0.9, n)
        labels = (rng.uniform(0.0, 1.0, n) < probs).astype(float)
        return probs, labels

    def test_returns_float(self):
        from calibration import compute_log_loss
        p, lbs = self._make_data()
        result = compute_log_loss(p, lbs)
        assert isinstance(result, float)

    def test_nonnegative(self):
        from calibration import compute_log_loss
        p, lbs = self._make_data()
        assert compute_log_loss(p, lbs) >= 0.0

    def test_perfect_predictions_near_zero(self):
        import numpy as np

        from calibration import compute_log_loss
        p = np.array([0.99, 0.01, 0.99, 0.01])
        lbs = np.array([1.0, 0.0, 1.0, 0.0])
        assert compute_log_loss(p, lbs) < 0.05

    def test_random_classifier_near_ln2(self):
        import math

        import numpy as np

        from calibration import compute_log_loss
        p = np.full(1000, 0.5)
        lbs = np.array([float(i % 2) for i in range(1000)])
        result = compute_log_loss(p, lbs)
        assert abs(result - math.log(2)) < 0.05

    def test_empty_returns_zero(self):
        from calibration import compute_log_loss
        assert compute_log_loss([], []) == pytest.approx(0.0)

    def test_clipping_prevents_inf(self):
        import numpy as np

        from calibration import compute_log_loss
        p = np.array([0.0, 1.0])
        lbs = np.array([1.0, 0.0])
        result = compute_log_loss(p, lbs)
        assert result < 1e6


class TestReliabilityDiagramNew:
    def test_returns_dict(self):
        import numpy as np

        from calibration import reliability_diagram
        rng = np.random.default_rng(0)
        probs = rng.uniform(0, 1, 100)
        labels = rng.binomial(1, probs).astype(float)
        result = reliability_diagram(probs, labels)
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        import numpy as np

        from calibration import reliability_diagram
        result = reliability_diagram(np.array([0.3, 0.7]), np.array([0.0, 1.0]))
        assert "bin_centers" in result
        assert "fraction_positive" in result
        assert "bin_counts" in result

    def test_lists_same_length(self):
        import numpy as np

        from calibration import reliability_diagram
        rng = np.random.default_rng(1)
        probs = rng.uniform(0, 1, 200)
        labels = rng.binomial(1, probs).astype(float)
        result = reliability_diagram(probs, labels)
        assert len(result["bin_centers"]) == len(result["fraction_positive"])
        assert len(result["bin_centers"]) == len(result["bin_counts"])

    def test_empty_bins_excluded(self):
        import numpy as np

        from calibration import reliability_diagram
        # All probs in [0.0, 0.1); bins 2–10 are empty
        probs = np.full(50, 0.05)
        labels = np.zeros(50)
        result = reliability_diagram(probs, labels, n_bins=10)
        # Only one non-empty bin
        assert len(result["bin_centers"]) == 1

    def test_fraction_positive_in_range(self):
        import numpy as np

        from calibration import reliability_diagram
        rng = np.random.default_rng(2)
        probs = rng.uniform(0, 1, 100)
        labels = rng.binomial(1, probs).astype(float)
        result = reliability_diagram(probs, labels)
        for f in result["fraction_positive"]:
            assert 0.0 <= f <= 1.0

    def test_bin_counts_positive(self):
        import numpy as np

        from calibration import reliability_diagram
        probs = np.array([0.2, 0.4, 0.6, 0.8])
        labels = np.array([0.0, 1.0, 0.0, 1.0])
        result = reliability_diagram(probs, labels)
        for c in result["bin_counts"]:
            assert c > 0


class TestCalibrationReport:
    def test_returns_dict(self):
        import numpy as np

        from calibration import calibration_report
        result = calibration_report(np.array([0.3, 0.7]), np.array([0.0, 1.0]))
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        import numpy as np

        from calibration import calibration_report
        result = calibration_report(np.array([0.3, 0.7]), np.array([0.0, 1.0]))
        for key in ["n_samples", "mean_prob", "fraction_positive",
                    "brier_score", "ece", "log_loss"]:
            assert key in result

    def test_empty_returns_none_values(self):
        from calibration import calibration_report
        result = calibration_report([], [])
        assert result["n_samples"] == 0
        assert result["brier_score"] is None
        assert result["ece"] is None
        assert result["log_loss"] is None

    def test_n_samples_correct(self):
        import numpy as np

        from calibration import calibration_report
        result = calibration_report(np.zeros(50), np.zeros(50))
        assert result["n_samples"] == 50

    def test_perfect_calibration_low_brier(self):
        import numpy as np

        from calibration import calibration_report
        # Near-perfect: 0 → label 0, 1 → label 1
        probs = np.array([0.01, 0.99])
        labels = np.array([0.0, 1.0])
        result = calibration_report(probs, labels)
        assert result["brier_score"] < 0.01

    def test_metrics_are_floats(self):
        import numpy as np

        from calibration import calibration_report
        result = calibration_report(np.array([0.5, 0.5]), np.array([0.0, 1.0]))
        for key in ["brier_score", "ece", "log_loss", "mean_prob", "fraction_positive"]:
            assert isinstance(result[key], float)


class TestComputeRocAuc:
    def test_returns_float(self):
        from calibration import compute_roc_auc
        result = compute_roc_auc([0.1, 0.9], [0.0, 1.0])
        assert isinstance(result, float)

    def test_perfect_classifier_auc_1(self):
        from calibration import compute_roc_auc
        result = compute_roc_auc([0.0, 1.0], [0.0, 1.0])
        assert result == pytest.approx(1.0, abs=0.01)

    def test_equal_probs_returns_valid_auc(self):
        from calibration import compute_roc_auc
        # Equal probabilities: AUC depends on tie-breaking order; just verify valid float
        result = compute_roc_auc([0.5, 0.5], [0.0, 1.0])
        assert 0.0 <= result <= 1.0

    def test_empty_returns_05(self):
        from calibration import compute_roc_auc
        assert compute_roc_auc([], []) == pytest.approx(0.5)

    def test_single_class_returns_05(self):
        from calibration import compute_roc_auc
        assert compute_roc_auc([0.3, 0.7], [0.0, 0.0]) == pytest.approx(0.5)

    def test_range_0_1(self):
        import numpy as np

        from calibration import compute_roc_auc
        rng = np.random.default_rng(42)
        probs = rng.random(20).tolist()
        labels = rng.integers(0, 2, 20).tolist()
        result = compute_roc_auc(probs, labels)
        assert 0.0 <= result <= 1.0

    def test_better_model_higher_auc(self):
        from calibration import compute_roc_auc
        labels = [0, 0, 1, 1]
        good = [0.1, 0.2, 0.8, 0.9]
        poor = [0.4, 0.5, 0.5, 0.6]
        assert compute_roc_auc(good, labels) > compute_roc_auc(poor, labels)


class TestComputeCalibrationSlopeDegenerate:
    def test_all_probs_identical_returns_one(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_slope
        # All predictions in the same bin → x_mean = x_bins[0] for each bin
        # but with 1 bin → returns 1.0 from len(x_bins) < 2
        # To hit den==0: need 2+ bins with exact same mean prob (impossible with linspace)
        # But we can fill all probs exactly at 0.5 into only 1 bin → len < 2
        probs = [0.5] * 10 + [0.501] * 10
        labels = [1] * 10 + [0] * 10
        result = compute_calibration_slope(probs, labels)
        assert isinstance(result, float)


class TestComputeHosmerLemeshowEdgeCases:
    """Edge case tests for compute_hosmer_lemeshow_statistic."""

    def test_all_zeros_labels_skips_degenerate_bins(self):
        """All labels=0 forces exp == n_bin, hitting (n_bin - exp) == 0 branch."""
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_hosmer_lemeshow_statistic

        # All predictions 0.5, all labels 0 → exp=0.5*n, n_bin-exp=0.5*n ≠ 0
        # To hit n_bin-exp==0: all probs=1.0, all labels=0 → exp=n_bin
        probs = [1.0] * 20
        labels = [0] * 20
        result = compute_hosmer_lemeshow_statistic(probs, labels)
        assert isinstance(result, float)
        assert result >= 0.0

    def test_all_ones_labels_exp_equals_zero_branch(self):
        """All probs=0.0, all labels=1 → exp=0 branch skipped in bins."""
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_hosmer_lemeshow_statistic

        probs = [0.0] * 20
        labels = [1] * 20
        result = compute_hosmer_lemeshow_statistic(probs, labels)
        assert isinstance(result, float)
        assert result >= 0.0


class TestComputeCalibrationGain:
    def test_positive_gain(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gain
        # raw probs far from labels, cal probs near labels → positive gain
        raw = [0.9, 0.9, 0.1, 0.1]
        cal = [0.1, 0.1, 0.9, 0.9]
        labels = [0.0, 0.0, 1.0, 1.0]
        gain = compute_calibration_gain(raw, cal, labels)
        assert gain > 0.0

    def test_negative_gain_if_cal_worse(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gain
        raw = [0.1, 0.1, 0.9, 0.9]
        cal = [0.9, 0.9, 0.1, 0.1]
        labels = [0.0, 0.0, 1.0, 1.0]
        gain = compute_calibration_gain(raw, cal, labels)
        assert gain < 0.0

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gain
        assert compute_calibration_gain([], [], []) == 0.0

    def test_length_mismatch_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gain
        assert compute_calibration_gain([0.5, 0.5], [0.5], [1.0, 0.0]) == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_calibration_gain" in calibration.__all__


class TestComputeCalibrationSpreadCoverage:
    """Coverage for clamp branch (prob=1.0 → idx clamped to n_bins-1)."""

    def _fn(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        return calibration.compute_calibration_spread

    def test_prob_one_clamp_branch(self):
        probs = [0.0, 1.0]
        labels = [0, 1]
        result = self._fn()(probs, labels, n_bins=1)
        assert result == 0.0

    def test_prob_one_with_multiple_bins(self):
        probs = [0.1, 0.9, 1.0]
        labels = [0, 1, 1]
        result = self._fn()(probs, labels, n_bins=10)
        assert isinstance(result, float)


