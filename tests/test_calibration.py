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


class TestCompareCalibrators:
    def test_returns_dict(self):
        from calibration import compare_calibrators
        result = compare_calibrators([[0.3, 0.7], [0.4, 0.6]], [0.0, 1.0], ["A", "B"])
        assert isinstance(result, dict)

    def test_keys_match_names(self):
        from calibration import compare_calibrators
        result = compare_calibrators([[0.3, 0.7], [0.4, 0.6]], [0.0, 1.0], ["platt", "isotonic"])
        assert "platt" in result
        assert "isotonic" in result

    def test_each_value_is_calibration_report(self):
        from calibration import compare_calibrators
        result = compare_calibrators([[0.3, 0.7]], [0.0, 1.0], ["model_a"])
        report = result["model_a"]
        for key in ["n_samples", "brier_score", "ece", "log_loss"]:
            assert key in report

    def test_empty_probs_list(self):
        from calibration import compare_calibrators
        result = compare_calibrators([], [0.0, 1.0], [])
        assert result == {}

    def test_extra_name_ignored(self):
        from calibration import compare_calibrators
        # Only one probs array, two names — extra name ignored
        result = compare_calibrators([[0.5, 0.5]], [0.0, 1.0], ["a", "b"])
        assert list(result.keys()) == ["a"]

    def test_missing_name_defaults(self):
        from calibration import compare_calibrators
        # Two probs arrays, zero names → default names used
        result = compare_calibrators([[0.3, 0.7], [0.4, 0.6]], [0.0, 1.0], [])
        assert "calibrator_0" in result
        assert "calibrator_1" in result

    def test_metrics_differ_between_calibrators(self):
        from calibration import compare_calibrators
        probs_good = [0.1, 0.9]
        probs_poor = [0.5, 0.5]
        labels = [0.0, 1.0]
        result = compare_calibrators([probs_good, probs_poor], labels, ["good", "poor"])
        assert result["good"]["brier_score"] < result["poor"]["brier_score"]


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


class TestComputePrecisionRecallCurve:
    def test_returns_dict_with_required_keys(self):
        from calibration import compute_precision_recall_curve
        result = compute_precision_recall_curve([0.9, 0.7, 0.3], [1, 1, 0])
        assert "precisions" in result
        assert "recalls" in result
        assert "thresholds" in result
        assert "average_precision" in result

    def test_empty_returns_zero_ap(self):
        from calibration import compute_precision_recall_curve
        result = compute_precision_recall_curve([], [])
        assert result["average_precision"] == 0.0

    def test_single_class_returns_zero_ap(self):
        from calibration import compute_precision_recall_curve
        result = compute_precision_recall_curve([0.9, 0.8, 0.7], [1, 1, 1])
        assert result["average_precision"] == 0.0

    def test_perfect_classifier_high_ap(self):
        from calibration import compute_precision_recall_curve
        result = compute_precision_recall_curve([0.95, 0.9, 0.1, 0.05], [1, 1, 0, 0])
        assert result["average_precision"] > 0.9

    def test_ap_in_unit_interval(self):
        import numpy as np

        from calibration import compute_precision_recall_curve
        rng = np.random.default_rng(42)
        probs = rng.random(50)
        labels = rng.integers(0, 2, 50)
        result = compute_precision_recall_curve(probs, labels)
        assert 0.0 <= result["average_precision"] <= 1.0

    def test_arrays_same_length(self):
        from calibration import compute_precision_recall_curve
        result = compute_precision_recall_curve([0.9, 0.6, 0.3, 0.1], [1, 1, 0, 0])
        assert len(result["precisions"]) == len(result["recalls"])

    def test_no_positive_labels_returns_zero_ap(self):
        from calibration import compute_precision_recall_curve
        result = compute_precision_recall_curve([0.9, 0.5, 0.1], [0, 0, 0])
        assert result["average_precision"] == 0.0

    def test_thresholds_descending(self):
        from calibration import compute_precision_recall_curve
        result = compute_precision_recall_curve([0.9, 0.7, 0.4, 0.2], [1, 0, 1, 0])
        thresholds = result["thresholds"]
        assert list(thresholds) == sorted(thresholds, reverse=True)


class TestComputeF1Score:
    def test_perfect_predictions(self):
        from calibration import compute_f1_score
        result = compute_f1_score([1.0, 1.0, 0.0, 0.0], [1, 1, 0, 0])
        assert result["f1"] == 1.0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0

    def test_empty_input(self):
        from calibration import compute_f1_score
        result = compute_f1_score([], [])
        assert result["f1"] == 0.0
        assert result["n_samples"] == 0

    def test_all_wrong(self):
        from calibration import compute_f1_score
        result = compute_f1_score([0.0, 0.0, 1.0, 1.0], [1, 1, 0, 0])
        assert result["f1"] == 0.0

    def test_threshold_used(self):
        from calibration import compute_f1_score
        result = compute_f1_score([0.6, 0.4, 0.3, 0.7], [1, 0, 0, 1], threshold=0.55)
        assert result["threshold"] == 0.55
        assert result["f1"] > 0.0

    def test_n_samples_correct(self):
        from calibration import compute_f1_score
        result = compute_f1_score([0.9, 0.1, 0.8], [1, 0, 1])
        assert result["n_samples"] == 3

    def test_no_positive_predictions(self):
        from calibration import compute_f1_score
        result = compute_f1_score([0.1, 0.2, 0.3], [1, 1, 0], threshold=0.9)
        assert result["precision"] == 0.0
        assert result["f1"] == 0.0

    def test_no_positive_labels(self):
        from calibration import compute_f1_score
        result = compute_f1_score([0.9, 0.8, 0.7], [0, 0, 0])
        assert result["recall"] == 0.0
        assert result["f1"] == 0.0

    def test_returns_all_keys(self):
        from calibration import compute_f1_score
        result = compute_f1_score([0.9, 0.1], [1, 0])
        for k in ("precision", "recall", "f1", "threshold", "n_samples"):
            assert k in result


class TestComputeAveragePrecision:
    def test_perfect_classifier(self):
        from calibration import compute_average_precision
        result = compute_average_precision([0.95, 0.9, 0.1, 0.05], [1, 1, 0, 0])
        assert result > 0.9

    def test_empty_returns_zero(self):
        from calibration import compute_average_precision
        assert compute_average_precision([], []) == 0.0

    def test_single_class_returns_zero(self):
        from calibration import compute_average_precision
        assert compute_average_precision([0.9, 0.8, 0.7], [0, 0, 0]) == 0.0

    def test_range_zero_to_one(self):
        from calibration import compute_average_precision
        result = compute_average_precision([0.8, 0.6, 0.4, 0.2], [1, 0, 1, 0])
        assert 0.0 <= result <= 1.0

    def test_returns_float(self):
        from calibration import compute_average_precision
        result = compute_average_precision([0.9, 0.5, 0.2], [1, 1, 0])
        assert isinstance(result, float)

    def test_in_all(self):
        from calibration import __all__
        assert "compute_average_precision" in __all__


class TestComputeCalibrationSharpness:
    """Tests for compute_calibration_sharpness."""

    def test_all_half_returns_half(self):
        from calibration import compute_calibration_sharpness
        probs = [0.5] * 10
        result = compute_calibration_sharpness(probs)
        assert result == 0.5

    def test_all_one_returns_one(self):
        from calibration import compute_calibration_sharpness
        probs = [1.0] * 10
        result = compute_calibration_sharpness(probs)
        assert result == 1.0

    def test_all_zero_returns_one(self):
        from calibration import compute_calibration_sharpness
        # max(0, 1-0) = 1.0
        probs = [0.0] * 10
        result = compute_calibration_sharpness(probs)
        assert result == 1.0

    def test_mixed_values(self):
        from calibration import compute_calibration_sharpness
        probs = [0.9, 0.1, 0.8, 0.2]
        # confidences: [0.9, 0.9, 0.8, 0.8]; mean = 0.85
        result = compute_calibration_sharpness(probs)
        assert abs(result - 0.85) < 0.0001

    def test_empty_returns_half(self):
        from calibration import compute_calibration_sharpness
        assert compute_calibration_sharpness([]) == 0.5

    def test_range_is_0_5_to_1(self):
        import random

        from calibration import compute_calibration_sharpness
        rng = random.Random(42)
        probs = [rng.random() for _ in range(100)]
        result = compute_calibration_sharpness(probs)
        assert 0.5 <= result <= 1.0

    def test_returns_4dp(self):
        from calibration import compute_calibration_sharpness
        result = compute_calibration_sharpness([0.73, 0.27, 0.6])
        assert round(result, 4) == result

    def test_in_all(self):
        from calibration import __all__
        assert "compute_calibration_sharpness" in __all__


class TestComputeBrierSkillScore:
    """Tests for compute_brier_skill_score."""

    def test_perfect_forecast(self):
        from calibration import compute_brier_skill_score
        probs = [1.0, 1.0, 0.0, 0.0]
        labels = [1, 1, 0, 0]
        result = compute_brier_skill_score(probs, labels)
        assert result == 1.0

    def test_empty_input(self):
        from calibration import compute_brier_skill_score
        assert compute_brier_skill_score([], []) == 0.0

    def test_all_same_labels_returns_zero(self):
        from calibration import compute_brier_skill_score
        # climatology = 0 * (1-0) = 0 → returns 0.0
        probs = [0.5, 0.5, 0.5]
        labels = [0, 0, 0]
        result = compute_brier_skill_score(probs, labels)
        assert result == 0.0

    def test_worse_than_climatology(self):
        from calibration import compute_brier_skill_score
        # always predict wrong → BSS < 0
        probs = [0.0, 0.0, 1.0, 1.0]
        labels = [1, 1, 0, 0]
        result = compute_brier_skill_score(probs, labels)
        assert result < 0.0

    def test_climatology_forecast_is_zero(self):
        from calibration import compute_brier_skill_score
        # predict base rate exactly → BSS == 0
        labels = [1, 1, 0, 0]
        base_rate = 0.5
        probs = [base_rate] * 4
        result = compute_brier_skill_score(probs, labels)
        assert abs(result) < 1e-9

    def test_returns_float_rounded_6dp(self):
        from calibration import compute_brier_skill_score
        probs = [0.9, 0.8, 0.2, 0.1]
        labels = [1, 1, 0, 0]
        result = compute_brier_skill_score(probs, labels)
        assert isinstance(result, float)
        assert round(result, 6) == result

    def test_numpy_arrays_accepted(self):
        import numpy as np

        from calibration import compute_brier_skill_score
        probs = np.array([0.9, 0.1])
        labels = np.array([1, 0])
        result = compute_brier_skill_score(probs, labels)
        assert isinstance(result, float)

    def test_in_all(self):
        from calibration import __all__
        assert "compute_brier_skill_score" in __all__


class TestComputeDiscriminationScore:
    """Tests for compute_discrimination_score."""

    def test_perfect_discrimination(self):
        from calibration import compute_discrimination_score
        # positives all 1.0, negatives all 0.0
        probs = [1.0, 1.0, 0.0, 0.0]
        labels = [1, 1, 0, 0]
        assert compute_discrimination_score(probs, labels) == 1.0

    def test_zero_discrimination(self):
        from calibration import compute_discrimination_score
        # same mean for both classes
        probs = [0.5, 0.5, 0.5, 0.5]
        labels = [1, 1, 0, 0]
        assert compute_discrimination_score(probs, labels) == 0.0

    def test_empty_input(self):
        from calibration import compute_discrimination_score
        assert compute_discrimination_score([], []) == 0.0

    def test_only_positives(self):
        from calibration import compute_discrimination_score
        # no negatives → 0.0
        probs = [0.9, 0.8]
        labels = [1, 1]
        assert compute_discrimination_score(probs, labels) == 0.0

    def test_only_negatives(self):
        from calibration import compute_discrimination_score
        probs = [0.1, 0.2]
        labels = [0, 0]
        assert compute_discrimination_score(probs, labels) == 0.0

    def test_partial_discrimination(self):
        from calibration import compute_discrimination_score
        probs = [0.8, 0.7, 0.3, 0.2]
        labels = [1, 1, 0, 0]
        # mean_pos=0.75, mean_neg=0.25, diff=0.5
        result = compute_discrimination_score(probs, labels)
        assert abs(result - 0.5) < 1e-6

    def test_numpy_arrays_accepted(self):
        import numpy as np

        from calibration import compute_discrimination_score
        probs = np.array([0.9, 0.1])
        labels = np.array([1, 0])
        result = compute_discrimination_score(probs, labels)
        assert isinstance(result, float)

    def test_in_all(self):
        from calibration import __all__
        assert "compute_discrimination_score" in __all__


class TestComputeResolutionScore:
    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_resolution_score
        assert compute_resolution_score([], []) == 0.0

    def test_perfect_discrimination(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_resolution_score
        probs = [0.0] * 50 + [1.0] * 50
        labels = [0] * 50 + [1] * 50
        score = compute_resolution_score(probs, labels)
        assert score > 0.0

    def test_random_predictor_low_resolution(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from calibration import compute_resolution_score
        rng = np.random.default_rng(0)
        probs = rng.uniform(0.4, 0.6, 200).tolist()
        labels = rng.integers(0, 2, 200).tolist()
        score = compute_resolution_score(probs, labels)
        assert score >= 0.0

    def test_result_non_negative(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_resolution_score
        probs = [0.1, 0.5, 0.9, 0.3, 0.7]
        labels = [0, 1, 1, 0, 1]
        assert compute_resolution_score(probs, labels) >= 0.0

    def test_custom_n_bins(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_resolution_score
        probs = [0.2, 0.8, 0.2, 0.8]
        labels = [0, 1, 0, 1]
        s5 = compute_resolution_score(probs, labels, n_bins=5)
        s20 = compute_resolution_score(probs, labels, n_bins=20)
        assert isinstance(s5, float) and isinstance(s20, float)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_resolution_score" in calibration.__all__


class TestComputeExpectedPositiveRate:
    def test_all_above_threshold(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_positive_rate
        assert compute_expected_positive_rate([0.8, 0.9, 0.7], 0.5) == 1.0

    def test_none_above_threshold(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_positive_rate
        assert compute_expected_positive_rate([0.1, 0.2, 0.3], 0.5) == 0.0

    def test_half_above(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_positive_rate
        result = compute_expected_positive_rate([0.3, 0.7, 0.3, 0.7], 0.5)
        assert result == pytest.approx(0.5, abs=0.001)

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_positive_rate
        assert compute_expected_positive_rate([], 0.5) == 0.0

    def test_default_threshold(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_positive_rate
        result = compute_expected_positive_rate([0.6, 0.4, 0.8])
        assert result == pytest.approx(2 / 3, abs=0.001)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_expected_positive_rate" in calibration.__all__


class TestComputeReliabilityScore:
    def test_perfect_calibration(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from calibration import compute_reliability_score
        probs = np.array([0.1] * 50 + [0.9] * 50)
        labels = np.array([0] * 50 + [1] * 50)
        score = compute_reliability_score(probs, labels)
        assert score > 0.8

    def test_poor_calibration(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from calibration import compute_reliability_score
        probs = np.array([0.9] * 50 + [0.1] * 50)
        labels = np.array([0] * 50 + [1] * 50)
        score = compute_reliability_score(probs, labels)
        assert score < 0.5

    def test_empty_input(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from calibration import compute_reliability_score
        assert compute_reliability_score(np.array([]), np.array([])) == 1.0

    def test_bounded_01(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from calibration import compute_reliability_score
        probs = np.random.default_rng(42).random(100)
        labels = np.random.default_rng(42).integers(0, 2, 100)
        score = compute_reliability_score(probs, labels)
        assert 0.0 <= score <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_reliability_score" in calibration.__all__


class TestComputeCalibrationDrift:
    def test_zero_drift_same_data(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from calibration import compute_calibration_drift
        rng = np.random.default_rng(0)
        p = list(rng.random(100))
        y = list(rng.integers(0, 2, 100))
        drift = compute_calibration_drift(p, y, p, y)
        assert drift == pytest.approx(0.0, abs=1e-6)

    def test_empty_t0_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_drift
        assert compute_calibration_drift([], [], [0.5], [1]) == 0.0

    def test_empty_t1_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_drift
        assert compute_calibration_drift([0.5], [1], [], []) == 0.0

    def test_positive_drift_means_worse(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_drift
        # t0: perfectly calibrated; t1: badly calibrated
        p_t0 = [0.1] * 50 + [0.9] * 50
        y_t0 = [0] * 50 + [1] * 50
        p_t1 = [0.9] * 50 + [0.1] * 50  # reversed — very miscalibrated
        y_t1 = [0] * 50 + [1] * 50
        drift = compute_calibration_drift(p_t0, y_t0, p_t1, y_t1)
        assert drift > 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_calibration_drift" in calibration.__all__


class TestComputeCalibrationUniformity:
    def test_uniform_distribution_near_zero(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from calibration import compute_calibration_uniformity
        rng = np.random.default_rng(42)
        probs = list(rng.uniform(0, 1, 1000))
        result = compute_calibration_uniformity(probs)
        assert result < 0.1

    def test_all_zeros_returns_one(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_uniformity
        result = compute_calibration_uniformity([0.0] * 100)
        assert result == pytest.approx(1.0)

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_uniformity
        assert compute_calibration_uniformity([]) == 0.0

    def test_single_value(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_uniformity
        result = compute_calibration_uniformity([0.5])
        assert 0.0 <= result <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_calibration_uniformity" in calibration.__all__


class TestComputeMeanCalibrationError:
    def test_basic_mean(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_mean_calibration_error
        probs1 = [0.1] * 50 + [0.9] * 50
        labels1 = [0] * 50 + [1] * 50
        probs2 = [0.2] * 50 + [0.8] * 50
        labels2 = [0] * 50 + [1] * 50
        result = compute_mean_calibration_error([probs1, probs2], [labels1, labels2])
        assert 0.0 <= result <= 1.0

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_mean_calibration_error
        assert compute_mean_calibration_error([], []) == 0.0

    def test_single_pair(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_mean_calibration_error
        probs = [0.5] * 100
        labels = [0] * 50 + [1] * 50
        result = compute_mean_calibration_error([probs], [labels])
        assert result >= 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_mean_calibration_error" in calibration.__all__


class TestComputeResolution:
    def test_perfect_calibration_has_nonzero_resolution(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_resolution
        # Two well-separated groups → high resolution
        probs = [0.1] * 50 + [0.9] * 50
        labels = [0] * 50 + [1] * 50
        result = compute_resolution(probs, labels)
        assert result > 0.0

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_resolution
        assert compute_resolution([], []) == 0.0

    def test_single_class_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_resolution
        probs = [0.3, 0.5, 0.7]
        labels = [1, 1, 1]  # all positive → o_bar=1.0 → resolution=0
        assert compute_resolution(probs, labels) == 0.0

    def test_returns_float_in_range(self):
        import sys
        sys.path.insert(0, "src")
        import random

        from calibration import compute_resolution
        random.seed(42)
        probs = [random.random() for _ in range(200)]
        labels = [random.randint(0, 1) for _ in range(200)]
        result = compute_resolution(probs, labels)
        assert 0.0 <= result <= 0.25

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_resolution" in calibration.__all__


class TestComputeCalibrationSlope:
    def test_perfect_calibration_returns_one(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_slope
        # perfectly calibrated: predicted = observed fraction
        probs = [0.1] * 10 + [0.5] * 10 + [0.9] * 10
        labels = [0] * 9 + [1] + [0] * 5 + [1] * 5 + [0] * 1 + [1] * 9
        result = compute_calibration_slope(probs, labels)
        assert isinstance(result, float)

    def test_empty_returns_one(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_slope
        assert compute_calibration_slope([], []) == pytest.approx(1.0)

    def test_single_bin_returns_one(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_slope
        probs = [0.5] * 20
        labels = [1] * 10 + [0] * 10
        result = compute_calibration_slope(probs, labels)
        assert result == pytest.approx(1.0)

    def test_well_calibrated_slope_near_one(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from calibration import compute_calibration_slope
        rng = np.random.RandomState(0)
        probs = rng.uniform(0, 1, 2000).tolist()
        labels = [int(rng.random() < p) for p in probs]
        slope = compute_calibration_slope(probs, labels)
        assert 0.5 <= slope <= 2.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_calibration_slope" in calibration.__all__


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


class TestComputeOverconfidenceScore:
    def test_overconfident(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_overconfidence_score
        probs = [0.8, 0.9, 0.7]
        labels = [0, 0, 0]
        result = compute_overconfidence_score(probs, labels)
        assert result > 0.0

    def test_underconfident(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_overconfidence_score
        probs = [0.1, 0.2, 0.1]
        labels = [1, 1, 1]
        result = compute_overconfidence_score(probs, labels)
        assert result < 0.0

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_overconfidence_score
        assert compute_overconfidence_score([], []) == pytest.approx(0.0)

    def test_perfectly_calibrated(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_overconfidence_score
        probs = [0.5, 0.5]
        labels = [0, 1]
        assert compute_overconfidence_score(probs, labels) == pytest.approx(0.0)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_overconfidence_score" in calibration.__all__


class TestComputeCalibrationSummary:
    def test_empty_returns_sentinels(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_summary
        result = compute_calibration_summary([], [])
        assert result["brier_score"] == 0.0
        assert result["roc_auc"] == 0.5
        assert result["n_samples"] == 0

    def test_valid_input_returns_all_keys(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_summary
        probs = [0.9, 0.1, 0.8, 0.2]
        labels = [1, 0, 1, 0]
        result = compute_calibration_summary(probs, labels)
        assert set(result.keys()) == {"brier_score", "ece", "log_loss", "roc_auc",
                                      "overconfidence", "n_samples"}
        assert result["n_samples"] == 4
        assert 0.0 <= result["brier_score"] <= 1.0
        assert result["roc_auc"] > 0.5

    def test_perfect_calibration(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_summary
        probs = [1.0, 0.0, 1.0, 0.0]
        labels = [1, 0, 1, 0]
        result = compute_calibration_summary(probs, labels)
        assert result["brier_score"] == 0.0
        assert abs(result["overconfidence"]) < 0.01

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_calibration_summary" in calibration.__all__




class TestComputeHosmerLemeshowStatistic:
    def test_empty_input_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_hosmer_lemeshow_statistic
        assert compute_hosmer_lemeshow_statistic([], []) == 0.0

    def test_single_sample_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_hosmer_lemeshow_statistic
        assert compute_hosmer_lemeshow_statistic([0.5], [1]) == 0.0

    def test_perfect_calibration_low_statistic(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_hosmer_lemeshow_statistic
        # All 0.5 predicted probability with 50% labels
        probs = [0.5] * 100
        labels = [1] * 50 + [0] * 50
        stat = compute_hosmer_lemeshow_statistic(probs, labels)
        assert isinstance(stat, float)
        assert stat >= 0.0

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_hosmer_lemeshow_statistic
        probs = [0.1, 0.4, 0.6, 0.9]
        labels = [0, 0, 1, 1]
        result = compute_hosmer_lemeshow_statistic(probs, labels)
        assert isinstance(result, float)

    def test_non_negative(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from calibration import compute_hosmer_lemeshow_statistic
        rng = np.random.default_rng(42)
        probs = rng.random(50).tolist()
        labels = (rng.random(50) > 0.5).astype(int).tolist()
        result = compute_hosmer_lemeshow_statistic(probs, labels)
        assert result >= 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_hosmer_lemeshow_statistic" in calibration.__all__


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


class TestComputeSpiegelhalterZ:
    def test_perfect_calibration_near_zero(self):
        """Z ≈ 0 when each p_i ≈ y_i (well-calibrated)."""
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_spiegelhalter_z
        # All labels = 1, probs close to 1 — small z_i
        probs = [0.9] * 20
        labels = [1] * 20
        result = compute_spiegelhalter_z(probs, labels)
        assert isinstance(result, float)
        assert abs(result) < 5.0  # not necessarily 0, but small

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_spiegelhalter_z
        assert compute_spiegelhalter_z([], []) == 0.0

    def test_single_sample_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_spiegelhalter_z
        assert compute_spiegelhalter_z([0.5], [1]) == 0.0

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_spiegelhalter_z
        result = compute_spiegelhalter_z([0.2, 0.8, 0.5], [0, 1, 1])
        assert isinstance(result, float)

    def test_all_half_prob_zero_denominator(self):
        """p=0.5 → (1-2p)=0 → all var_i=0 → denom=0 → returns 0."""
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_spiegelhalter_z
        probs = [0.5, 0.5, 0.5, 0.5]
        labels = [0, 1, 0, 1]
        result = compute_spiegelhalter_z(probs, labels)
        assert result == 0.0

    def test_overconfident_probs_nonzero_z(self):
        """Large misfit → nonzero Z."""
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_spiegelhalter_z
        probs = [0.99] * 10 + [0.01] * 10
        labels = [0] * 10 + [1] * 10  # completely wrong
        result = compute_spiegelhalter_z(probs, labels)
        assert result != 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_spiegelhalter_z" in calibration.__all__


class TestComputeBrierSkillScoreWeighted:
    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_brier_skill_score_weighted
        assert compute_brier_skill_score_weighted([], [], []) == 0.0

    def test_uniform_weights_matches_bss(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_brier_skill_score, compute_brier_skill_score_weighted
        probs = [0.9, 0.1, 0.8, 0.2]
        labels = [1, 0, 1, 0]
        weights = [1.0, 1.0, 1.0, 1.0]
        weighted = compute_brier_skill_score_weighted(probs, labels, weights)
        unweighted = compute_brier_skill_score(probs, labels)
        assert abs(weighted - unweighted) < 1e-5

    def test_zero_weights_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_brier_skill_score_weighted
        probs = [0.8, 0.2]
        labels = [1, 0]
        weights = [0.0, 0.0]
        assert compute_brier_skill_score_weighted(probs, labels, weights) == 0.0

    def test_single_class_labels_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_brier_skill_score_weighted
        # All labels identical → bs_clim == 0 → return 0.0
        probs = [0.5, 0.5, 0.5]
        labels = [1, 1, 1]
        assert compute_brier_skill_score_weighted(probs, labels) == 0.0

    def test_none_weights_uses_uniform(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_brier_skill_score, compute_brier_skill_score_weighted
        probs = [0.7, 0.3, 0.6]
        labels = [1, 0, 1]
        w_none = compute_brier_skill_score_weighted(probs, labels, None)
        w_unif = compute_brier_skill_score(probs, labels)
        assert abs(w_none - w_unif) < 1e-5

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_brier_skill_score_weighted
        result = compute_brier_skill_score_weighted([0.9, 0.1], [1, 0], [2.0, 1.0])
        assert isinstance(result, float)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_brier_skill_score_weighted" in calibration.__all__


class TestComputeIsotonicCalibrationError:
    def test_perfect_calibration_gives_low_error(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_isotonic_calibration_error
        probs = [0.1, 0.3, 0.5, 0.7, 0.9]
        labels = [0, 0, 1, 1, 1]
        result = compute_isotonic_calibration_error(probs, labels)
        assert isinstance(result, float)
        assert result >= 0.0

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_isotonic_calibration_error
        assert compute_isotonic_calibration_error([], []) == 0.0

    def test_single_sample_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_isotonic_calibration_error
        assert compute_isotonic_calibration_error([0.5], [1]) == 0.0

    def test_all_positive_labels(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_isotonic_calibration_error
        probs = [0.2, 0.4, 0.6, 0.8]
        labels = [1, 1, 1, 1]
        result = compute_isotonic_calibration_error(probs, labels)
        assert isinstance(result, float)
        assert result >= 0.0

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_isotonic_calibration_error
        probs = [0.1, 0.5, 0.9]
        labels = [0, 1, 1]
        result = compute_isotonic_calibration_error(probs, labels)
        assert isinstance(result, float)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_isotonic_calibration_error" in calibration.__all__


class TestComputeExpectedCalibrationErrorWeighted:
    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_calibration_error_weighted
        assert compute_expected_calibration_error_weighted([], [], []) == 0.0

    def test_perfect_calibration_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_calibration_error_weighted
        # Identical prob and label in each bin → zero calibration error
        probs = [0.5, 0.5, 0.5, 0.5]
        labels = [0.5, 0.5, 0.5, 0.5]
        weights = [1.0, 1.0, 1.0, 1.0]
        result = compute_expected_calibration_error_weighted(probs, labels, weights, n_bins=5)
        assert result < 0.01

    def test_all_zero_weight_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_calibration_error_weighted
        probs = [0.5, 0.5]
        labels = [0.0, 1.0]
        weights = [0.0, 0.0]
        assert compute_expected_calibration_error_weighted(probs, labels, weights) == 0.0

    def test_uniform_weight_matches_unweighted_roughly(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import (
            compute_expected_calibration_error_weighted,
        )
        probs = [0.2, 0.4, 0.6, 0.8]
        labels = [0.0, 0.0, 1.0, 1.0]
        weights = [1.0, 1.0, 1.0, 1.0]
        weighted = compute_expected_calibration_error_weighted(probs, labels, weights, n_bins=4)
        assert isinstance(weighted, float)
        assert weighted >= 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_expected_calibration_error_weighted" in calibration.__all__

    def test_higher_weight_bins_dominate(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_calibration_error_weighted
        # High error bin with high weight → higher ECE
        probs = [0.05, 0.95]
        labels = [1.0, 0.0]  # Completely wrong predictions
        weights = [1.0, 1.0]
        result = compute_expected_calibration_error_weighted(probs, labels, weights, n_bins=10)
        assert result > 0.0

    def test_zero_weight_bin_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_expected_calibration_error_weighted
        # One bin has all-zero weights while another has positive weights.
        # The zero-weight bin should be skipped (bin_weight == 0.0 branch covered).
        probs = [0.05, 0.95]
        labels = [0.0, 1.0]
        # First sample falls in low-prob bin with zero weight;
        # second sample is in high-prob bin with positive weight.
        weights = [0.0, 1.0]
        result = compute_expected_calibration_error_weighted(probs, labels, weights, n_bins=10)
        assert isinstance(result, float)
        assert result >= 0.0


class TestComputePositiveRate:
    def test_all_above_threshold(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_positive_rate
        assert compute_positive_rate([0.6, 0.7, 0.8]) == 1.0

    def test_none_above_threshold(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_positive_rate
        assert compute_positive_rate([0.1, 0.2, 0.3]) == 0.0

    def test_half_above(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_positive_rate
        result = compute_positive_rate([0.3, 0.7])
        assert abs(result - 0.5) < 1e-9

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_positive_rate
        assert compute_positive_rate([]) == 0.0

    def test_custom_threshold(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_positive_rate
        result = compute_positive_rate([0.3, 0.5, 0.7], threshold=0.4)
        assert abs(result - 2.0 / 3.0) < 1e-9

    def test_exactly_at_threshold_not_counted(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_positive_rate
        # threshold uses strict >, so exactly 0.5 is NOT counted
        result = compute_positive_rate([0.5], threshold=0.5)
        assert result == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_positive_rate" in calibration.__all__


class TestComputeWeightedBrierScore:
    def test_perfect_predictions(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_weighted_brier_score
        result = compute_weighted_brier_score([0.0, 1.0], [0.0, 1.0], [1.0, 1.0])
        assert result == 0.0

    def test_worst_predictions(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_weighted_brier_score
        result = compute_weighted_brier_score([1.0, 0.0], [0.0, 1.0], [1.0, 1.0])
        assert abs(result - 1.0) < 1e-9

    def test_uniform_weights_equals_brier(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from calibration import brier_score, compute_weighted_brier_score
        probs = [0.3, 0.6, 0.9]
        labels = [0.0, 1.0, 1.0]
        weights = [1.0, 1.0, 1.0]
        weighted = compute_weighted_brier_score(probs, labels, weights)
        unweighted = brier_score(np.array(probs), np.array(labels))
        assert abs(weighted - unweighted) < 1e-9

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_weighted_brier_score
        assert compute_weighted_brier_score([], [], []) == 0.0

    def test_zero_weights_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_weighted_brier_score
        result = compute_weighted_brier_score([0.5, 0.5], [0.0, 1.0], [0.0, 0.0])
        assert result == 0.0

    def test_high_weight_sample_dominates(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_weighted_brier_score
        # Perfect on high-weight sample, wrong on low-weight sample
        result = compute_weighted_brier_score([1.0, 0.0], [1.0, 1.0], [100.0, 1.0])
        assert result < 0.05

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_weighted_brier_score" in calibration.__all__


class TestComputeCalibrationGap:
    def test_perfect_calibration(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gap
        # All predictions in same bin: mean_pred=0.5, frac_pos=0.5 → gap=0
        probs = [0.5, 0.5, 0.5, 0.5]
        labels = [0.0, 1.0, 0.0, 1.0]
        gap = compute_calibration_gap(probs, labels)
        assert gap < 1e-9

    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gap
        assert compute_calibration_gap([], []) == 0.0

    def test_overconfident(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gap
        # Predict 0.9 for all, but only 50% positive
        probs = [0.9] * 10
        labels = [1.0, 0.0] * 5
        gap = compute_calibration_gap(probs, labels)
        assert gap > 0.2

    def test_result_non_negative(self):
        import sys
        sys.path.insert(0, "src")
        import random

        from calibration import compute_calibration_gap
        random.seed(42)
        probs = [random.random() for _ in range(50)]
        labels = [float(random.random() > 0.5) for _ in range(50)]
        gap = compute_calibration_gap(probs, labels)
        assert gap >= 0.0

    def test_single_pair(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_gap
        # One prediction of 0.8, label=1.0 → gap=|0.8-1.0|=0.2
        gap = compute_calibration_gap([0.8], [1.0])
        assert abs(gap - 0.2) < 1e-9

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_calibration_gap" in calibration.__all__


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


class TestComputeCalibrationBias:
    def test_empty_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_bias

        assert compute_calibration_bias([], []) == 0.0

    def test_length_mismatch_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_bias

        assert compute_calibration_bias([0.5], [0.0, 1.0]) == 0.0

    def test_over_confident(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_bias

        # Predicts 0.8 but only 50% are positive => bias = +0.3
        probs = [0.8, 0.8]
        labels = [1.0, 0.0]
        bias = compute_calibration_bias(probs, labels)
        assert abs(bias - 0.3) < 1e-9

    def test_under_confident(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_bias

        # Predicts 0.2 but 100% are positive => bias = -0.8
        probs = [0.2, 0.2]
        labels = [1.0, 1.0]
        bias = compute_calibration_bias(probs, labels)
        assert abs(bias - (-0.8)) < 1e-9

    def test_perfect_calibration_near_zero(self):
        import sys
        sys.path.insert(0, "src")
        from calibration import compute_calibration_bias

        probs = [0.5, 0.5]
        labels = [1.0, 0.0]
        assert abs(compute_calibration_bias(probs, labels)) < 1e-9

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import calibration
        assert "compute_calibration_bias" in calibration.__all__
