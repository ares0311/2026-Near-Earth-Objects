"""Calibration — Platt scaling and isotonic PAVA for classifier probability calibration."""

from __future__ import annotations

__all__ = [
    "IsotonicCalibrator", "PlattCalibrator",
    "brier_score", "reliability_diagram_data", "expected_calibration_error", "calibrate",
    "bootstrap_confidence_interval",
    "cross_validate_calibration",
    "compute_log_loss",
    "reliability_diagram",
    "calibration_report",
    "compare_calibrators",
    "compute_roc_auc",
    "compute_precision_recall_curve",
    "compute_f1_score", "compute_average_precision",
    "compute_calibration_sharpness",
    "compute_brier_skill_score",
    "compute_discrimination_score",
    "compute_resolution_score",
    "compute_expected_positive_rate",
    "compute_reliability_score",
    "compute_calibration_drift",
    "compute_calibration_uniformity",
    "compute_mean_calibration_error",
    "compute_resolution",
    "compute_calibration_slope",
    "compute_overconfidence_score",
    "compute_calibration_summary",
    "compute_hosmer_lemeshow_statistic",
    "compute_spiegelhalter_z",
    "compute_brier_skill_score_weighted",
    "compute_isotonic_calibration_error",
    "compute_expected_calibration_error_weighted",
    "compute_positive_rate",
    "compute_weighted_brier_score",
    "compute_calibration_gap",
    "compute_calibration_gain",
    "compute_calibration_bias",
    "compute_overconfidence_fraction",
    "compute_max_calibration_error",
    "compute_calibration_resolution",
    "compute_fraction_calibrated",
]

import math
from pathlib import Path

import numpy as np

_CALIBRATION_DIR = Path("models/calibration")

# ---------------------------------------------------------------------------
# Isotonic regression (PAVA — Pool Adjacent Violators Algorithm)
# ---------------------------------------------------------------------------


def _pava(y: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    """Isotonic regression via PAVA (non-decreasing).

    Args:
        y: raw scores to isotonize
        w: optional sample weights

    Returns:
        Isotonically transformed scores (non-decreasing)
    """
    n = len(y)
    if n == 0:
        return y.copy()
    if w is None:
        w = np.ones(n)

    # Blocks: each block is a contiguous set of equal-valued estimates
    block_sums = list(y * w)
    block_weights = list(w)
    block_size = [1] * n

    i = 0
    while i < len(block_sums) - 1:
        # Check if next block violates monotonicity
        if block_sums[i] / block_weights[i] > block_sums[i + 1] / block_weights[i + 1]:
            # Merge blocks
            block_sums[i] += block_sums[i + 1]
            block_weights[i] += block_weights[i + 1]
            block_size[i] += block_size[i + 1]
            del block_sums[i + 1]
            del block_weights[i + 1]
            del block_size[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1

    # Expand blocks back to individual estimates
    result = np.empty(n)
    pos = 0
    for s, w_block, size in zip(block_sums, block_weights, block_size):
        val = s / w_block
        result[pos : pos + size] = val
        pos += size
    return result


class IsotonicCalibrator:
    """Isotonic regression calibrator (PAVA).

    Fits a non-decreasing mapping from raw scores → calibrated probabilities.
    """

    def __init__(self) -> None:
        self._x_train: np.ndarray | None = None
        self._y_iso: np.ndarray | None = None
        self._fitted = False

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> IsotonicCalibrator:
        """Fit isotonic calibration.

        Args:
            scores: 1D array of raw classifier scores in [0, 1]
            labels: 1D binary labels (0 or 1)
        """
        order = np.argsort(scores)
        x_sorted = scores[order]
        y_sorted = labels[order].astype(float)
        y_iso = _pava(y_sorted)
        self._x_train = x_sorted
        self._y_iso = y_iso
        self._fitted = True
        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        """Map raw scores to calibrated probabilities via piecewise-linear interpolation."""
        if not self._fitted or self._x_train is None or self._y_iso is None:
            raise RuntimeError("IsotonicCalibrator not fitted")
        return np.interp(scores, self._x_train, self._y_iso)

    def save(self, name: str) -> None:
        if not self._fitted:
            raise RuntimeError("Cannot save unfitted calibrator")
        _CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
        np.savez(
            _CALIBRATION_DIR / f"{name}_isotonic.npz",
            x=self._x_train,
            y=self._y_iso,
        )

    def load(self, name: str) -> IsotonicCalibrator:
        path = _CALIBRATION_DIR / f"{name}_isotonic.npz"
        data = np.load(path)
        self._x_train = data["x"]
        self._y_iso = data["y"]
        self._fitted = True
        return self


# ---------------------------------------------------------------------------
# Platt scaling
# ---------------------------------------------------------------------------


class PlattCalibrator:
    """Platt scaling — fits a sigmoid A·f(x) + B to map scores to probabilities."""

    def __init__(self, max_iter: int = 100, tol: float = 1e-7) -> None:
        self._A = 0.0
        self._B = 0.0
        self._max_iter = max_iter
        self._tol = tol
        self._fitted = False

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> PlattCalibrator:
        """Fit Platt scaling via maximum likelihood (Newton–Raphson).

        Uses the modified targets from Platt (1999):
          t+ = (N+ + 1) / (N+ + 2)
          t- = 1 / (N- + 2)
        """
        n_pos = int(labels.sum())
        n_neg = int(len(labels) - n_pos)
        t_pos = (n_pos + 1.0) / (n_pos + 2.0)
        t_neg = 1.0 / (n_neg + 2.0)
        t = np.where(labels == 1, t_pos, t_neg)

        A, B = 0.0, math.log((n_neg + 1.0) / (n_pos + 1.0))
        f = scores

        for _ in range(self._max_iter):
            fApB = f * A + B
            np.where(
                fApB >= 0,
                t * fApB + np.logaddexp(0, -fApB),
                (t - 1) * fApB + np.logaddexp(0, fApB),
            ).sum()  # log-likelihood (not stored; drives convergence check)

            # Numerically stable sigmoid via scipy
            from scipy.special import expit  # type: ignore[import]
            p = expit(-fApB)
            p = np.clip(p, 1e-15, 1 - 1e-15)
            q = 1 - p

            dA = float(np.dot(f, p - t))
            dB = float(np.sum(p - t))
            d2A = float(np.dot(f**2, p * q))
            d2B = float(np.sum(p * q))
            d2AB = float(np.dot(f, p * q))

            det = d2A * d2B - d2AB**2
            if abs(det) < 1e-15:
                break
            A_new = A - (dA * d2B - dB * d2AB) / det
            B_new = B - (dB * d2A - dA * d2AB) / det

            if abs(A_new - A) + abs(B_new - B) < self._tol:
                A, B = A_new, B_new
                break
            A, B = A_new, B_new

        self._A = float(A)
        self._B = float(B)
        self._fitted = True
        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("PlattCalibrator not fitted")
        fApB = scores * self._A + self._B
        from scipy.special import expit  # type: ignore[import]
        return expit(-fApB)

    def save(self, name: str) -> None:
        if not self._fitted:
            raise RuntimeError("Cannot save unfitted calibrator")
        _CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
        np.savez(_CALIBRATION_DIR / f"{name}_platt.npz", A=np.array(self._A), B=np.array(self._B))

    def load(self, name: str) -> PlattCalibrator:
        path = _CALIBRATION_DIR / f"{name}_platt.npz"
        data = np.load(path)
        self._A = float(data["A"])
        self._B = float(data["B"])
        self._fitted = True
        return self


# ---------------------------------------------------------------------------
# Calibration metrics
# ---------------------------------------------------------------------------


def brier_score(proba: np.ndarray, labels: np.ndarray) -> float:
    """Compute Brier score (lower is better; 0 = perfect)."""
    return float(np.mean((proba - labels) ** 2))


def reliability_diagram_data(
    proba: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> list[dict]:
    """Compute reliability diagram data for calibration assessment."""
    bins = np.linspace(0, 1, n_bins + 1)
    results = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (proba >= lo) & (proba < hi)
        if mask.sum() == 0:
            continue
        mean_predicted = float(proba[mask].mean())
        fraction_positive = float(labels[mask].mean())
        results.append({
            "bin_lo": float(lo),
            "bin_hi": float(hi),
            "n_samples": int(mask.sum()),
            "mean_predicted": mean_predicted,
            "fraction_positive": fraction_positive,
            "calibration_error": abs(mean_predicted - fraction_positive),
        })
    return results


def expected_calibration_error(
    proba: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error (ECE)."""
    rd = reliability_diagram_data(proba, labels, n_bins)
    n = len(proba)
    ece = sum(d["n_samples"] * d["calibration_error"] for d in rd) / max(n, 1)
    return float(ece)


# ---------------------------------------------------------------------------
# Convenience: calibrate a probability array using the best available method
# ---------------------------------------------------------------------------


def calibrate(
    raw_scores: np.ndarray,
    labels: np.ndarray | None = None,
    method: str = "isotonic",
    model_name: str = "neo_classifier",
) -> np.ndarray:
    """Calibrate raw classifier scores.

    If labels are provided, fits a new calibrator and returns calibrated scores.
    If labels are None, attempts to load a pre-fitted calibrator from disk.

    Args:
        raw_scores: 1D array of raw scores in [0, 1]
        labels: 1D binary labels (1 = NEO, 0 = non-NEO). None to load saved model.
        method: "isotonic" or "platt"
        model_name: base name for saved calibrator

    Returns:
        Calibrated probability array in [0, 1]
    """
    if method == "isotonic":
        cal: IsotonicCalibrator | PlattCalibrator = IsotonicCalibrator()
    elif method == "platt":
        cal = PlattCalibrator()
    else:
        raise ValueError(f"Unknown calibration method: {method!r}")

    if labels is not None:
        cal.fit(raw_scores, labels)
        cal.save(model_name)
    else:
        cal.load(model_name)

    return cal.predict(raw_scores)


def bootstrap_confidence_interval(
    probs: list[float],
    labels: list[float],
    n_bootstrap: int = 1000,
    metric: str = "brier",
    seed: int = 42,
) -> tuple[float, float, float]:
    """Compute a bootstrap confidence interval for a calibration metric.

    Draws *n_bootstrap* samples with replacement from (probs, labels) and
    evaluates *metric* on each sample.  Returns ``(lower, upper, mean)``
    where *lower* and *upper* are the 2.5th and 97.5th percentiles of the
    bootstrap distribution (95% CI).

    Supported metrics: ``"brier"`` (Brier score) and ``"ece"``
    (expected calibration error).

    Raises ``ValueError`` for empty inputs or unknown metric.
    """
    import random

    if len(probs) == 0 or len(labels) == 0:
        raise ValueError("probs and labels must be non-empty")
    if len(probs) != len(labels):
        raise ValueError("probs and labels must have the same length")
    if metric not in ("brier", "ece"):
        raise ValueError(f"Unknown metric {metric!r}; choose 'brier' or 'ece'")

    rng = random.Random(seed)
    n = len(probs)
    samples: list[float] = []

    for _ in range(n_bootstrap):
        indices = [rng.randint(0, n - 1) for _ in range(n)]
        p_boot = [probs[i] for i in indices]
        l_boot = [labels[i] for i in indices]
        if metric == "brier":
            val = brier_score(np.array(p_boot), np.array(l_boot))
        else:
            val = expected_calibration_error(np.array(p_boot), np.array(l_boot))
        samples.append(val)

    samples.sort()
    lo = samples[int(0.025 * n_bootstrap)]
    hi = samples[int(0.975 * n_bootstrap)]
    mean = sum(samples) / len(samples)
    return (round(lo, 6), round(hi, 6), round(mean, 6))


def cross_validate_calibration(
    probs: np.ndarray,
    labels: np.ndarray,
    n_folds: int = 5,
    metric: str = "brier",
) -> tuple[float, float]:
    """K-fold cross-validation of calibration quality.

    Splits ``probs`` and ``labels`` into ``n_folds`` folds, computes the
    requested ``metric`` on each fold, and returns ``(mean, std)`` rounded to
    6 decimal places.  Accepts either ``"brier"`` or ``"ece"`` as metric.
    Returns ``(0.0, 0.0)`` when fewer than ``n_folds`` samples are provided.

    Args:
        probs: array of predicted probabilities, shape (N,)
        labels: array of binary labels, shape (N,)
        n_folds: number of cross-validation folds (default 5)
        metric: ``"brier"`` or ``"ece"``

    Returns:
        (mean_score, std_score)
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    if n < n_folds:
        return (0.0, 0.0)

    fold_size = n // n_folds
    scores: list[float] = []
    for k in range(n_folds):
        start = k * fold_size
        end = start + fold_size if k < n_folds - 1 else n
        p_fold = probs[start:end]
        l_fold = labels[start:end]
        if metric == "brier":
            scores.append(brier_score(p_fold, l_fold))
        else:
            scores.append(expected_calibration_error(p_fold, l_fold))

    arr = np.array(scores)
    return (round(float(arr.mean()), 6), round(float(arr.std()), 6))


def compute_log_loss(probs: np.ndarray, labels: np.ndarray, eps: float = 1e-7) -> float:
    """Binary cross-entropy log-loss for calibration evaluation.

    Clips probabilities to [eps, 1 - eps] to avoid log(0).  Lower is better;
    a perfectly calibrated classifier has log-loss equal to its Brier score
    in the limit of many samples.

    Args:
        probs: array of predicted probabilities, shape (N,)
        labels: array of binary labels (0 or 1), shape (N,)
        eps: small constant to avoid log(0)

    Returns:
        Mean log-loss as a non-negative float.  Returns 0.0 for empty inputs.
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    if len(probs) == 0:
        return 0.0
    p = np.clip(probs, eps, 1.0 - eps)
    loss = -(labels * np.log(p) + (1.0 - labels) * np.log(1.0 - p))
    return round(float(loss.mean()), 6)


def reliability_diagram(
    probs: np.ndarray | list,
    labels: np.ndarray | list,
    n_bins: int = 10,
) -> dict:
    """Compute reliability diagram data for calibration visualisation.

    Bins predicted probabilities into ``n_bins`` equal-width bins over [0, 1]
    and returns the mean predicted probability and observed positive fraction
    within each bin.  Empty bins are excluded from the output.

    Args:
        probs: Array of predicted probabilities in [0, 1], shape (N,).
        labels: Array of binary labels (0 or 1), shape (N,).
        n_bins: Number of equal-width bins (default 10).

    Returns:
        Dict with keys:
          - ``"bin_centers"``: list of mean predicted probabilities per bin.
          - ``"fraction_positive"``: list of observed positive fractions per bin.
          - ``"bin_counts"``: list of sample counts per bin.
    """
    probs_arr = np.asarray(probs, dtype=float)
    labels_arr = np.asarray(labels, dtype=float)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    centers: list[float] = []
    fractions: list[float] = []
    counts: list[int] = []
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (probs_arr >= lo) & (probs_arr < hi)
        if mask.sum() == 0:
            continue
        centers.append(round(float(probs_arr[mask].mean()), 4))
        fractions.append(round(float(labels_arr[mask].mean()), 4))
        counts.append(int(mask.sum()))
    return {
        "bin_centers": centers,
        "fraction_positive": fractions,
        "bin_counts": counts,
    }


def calibration_report(
    probs: np.ndarray | list,
    labels: np.ndarray | list,
) -> dict:
    """Produce a comprehensive calibration quality report.

    Combines Brier score, Expected Calibration Error (ECE), binary cross-entropy
    log-loss, and summary statistics into a single dict.  Useful for comparing
    calibrators or tracking calibration quality over time.

    Args:
        probs: Array of predicted probabilities in [0, 1], shape (N,).
        labels: Array of binary labels (0 or 1), shape (N,).

    Returns:
        Dict with keys:
          - ``"n_samples"``: number of samples.
          - ``"mean_prob"``: mean predicted probability.
          - ``"fraction_positive"``: fraction of positive labels.
          - ``"brier_score"``: mean squared calibration error.
          - ``"ece"``: Expected Calibration Error (10 equal-width bins).
          - ``"log_loss"``: binary cross-entropy.
    """
    probs_arr = np.asarray(probs, dtype=float)
    labels_arr = np.asarray(labels, dtype=float)
    n = len(probs_arr)
    if n == 0:
        return {
            "n_samples": 0,
            "mean_prob": None,
            "fraction_positive": None,
            "brier_score": None,
            "ece": None,
            "log_loss": None,
        }
    return {
        "n_samples": n,
        "mean_prob": round(float(probs_arr.mean()), 6),
        "fraction_positive": round(float(labels_arr.mean()), 6),
        "brier_score": round(brier_score(probs_arr, labels_arr), 6),
        "ece": round(expected_calibration_error(probs_arr, labels_arr), 6),
        "log_loss": round(compute_log_loss(probs_arr, labels_arr), 6),
    }


def compare_calibrators(
    probs_list: list[list[float]],
    labels: list[float],
    names: list[str],
) -> dict:
    """Compare multiple calibrator outputs against the same label set.

    For each set of predicted probabilities in ``probs_list``, computes a full
    :func:`calibration_report` and assembles the results in a dict keyed by
    the corresponding name from ``names``.

    Args:
        probs_list: List of probability arrays, one per calibrator.
        labels: Shared ground-truth binary labels (0 or 1).
        names: Human-readable names for each calibrator (same length as
            ``probs_list``).

    Returns:
        Dict mapping each name to its :func:`calibration_report` dict.
        Extra names beyond the length of ``probs_list`` are ignored; missing
        names default to ``"calibrator_<index>"``.
    """
    result: dict = {}
    for idx, probs in enumerate(probs_list):
        name = names[idx] if idx < len(names) else f"calibrator_{idx}"
        result[name] = calibration_report(probs, labels)
    return result


def compute_roc_auc(probs: list | np.ndarray, labels: list | np.ndarray) -> float:
    """Compute the area under the ROC curve (AUC) for a binary classifier.

    Uses the trapezoidal rule on the (FPR, TPR) curve sorted by threshold.
    Returns 0.5 for empty inputs or inputs with only one class label.

    Args:
        probs: Predicted probabilities for the positive class.
        labels: Binary ground-truth labels (0 or 1).

    Returns:
        AUC in [0, 1]; 0.5 indicates a random classifier.
    """
    probs_arr = np.asarray(probs, dtype=float)
    labels_arr = np.asarray(labels, dtype=float)
    n = len(probs_arr)
    if n == 0 or len(np.unique(labels_arr)) < 2:
        return 0.5

    # Sort by descending score
    order = np.argsort(-probs_arr)
    labels_sorted = labels_arr[order]

    n_pos = float(labels_arr.sum())
    n_neg = float(n - n_pos)

    tprs = [0.0]
    fprs = [0.0]
    tp = fp = 0.0
    for lbl in labels_sorted:
        if lbl == 1:
            tp += 1
        else:
            fp += 1
        tprs.append(tp / n_pos)
        fprs.append(fp / n_neg)

    # Trapezoidal integration
    trapz_fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    auc = float(trapz_fn(tprs, fprs))
    return round(abs(auc), 6)


def compute_precision_recall_curve(
    probs: list | np.ndarray,
    labels: list | np.ndarray,
) -> dict:
    """Compute precision-recall curve data for a binary classifier.

    Sweeps classification thresholds from high to low and records precision
    and recall at each step.  Also computes the Average Precision (AP) as
    the area under the PR curve via the trapezoidal rule.

    Args:
        probs: Predicted probabilities for the positive class.
        labels: Binary ground-truth labels (0 or 1).

    Returns:
        Dict with keys:

        - ``"precisions"``: numpy array of precision values.
        - ``"recalls"``: numpy array of recall values.
        - ``"thresholds"``: numpy array of decision thresholds used.
        - ``"average_precision"``: Area under the PR curve (AP score) in [0, 1].
          Returns 0.0 for empty or single-class inputs.
    """
    probs_arr = np.asarray(probs, dtype=float)
    labels_arr = np.asarray(labels, dtype=float)
    n = len(probs_arr)

    empty_result: dict = {
        "precisions": np.array([]),
        "recalls": np.array([]),
        "thresholds": np.array([]),
        "average_precision": 0.0,
    }

    if n == 0 or len(np.unique(labels_arr)) < 2:
        return empty_result

    n_pos = float(labels_arr.sum())

    # Sort by descending probability
    order = np.argsort(-probs_arr)
    probs_sorted = probs_arr[order]
    labels_sorted = labels_arr[order]

    precisions = []
    recalls = []
    thresholds = []

    tp = fp = 0.0
    for i, (prob, lbl) in enumerate(zip(probs_sorted, labels_sorted)):
        if lbl == 1:
            tp += 1
        else:
            fp += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / n_pos
        precisions.append(precision)
        recalls.append(recall)
        thresholds.append(prob)

    precisions_arr = np.array(precisions)
    recalls_arr = np.array(recalls)
    thresholds_arr = np.array(thresholds)

    # AP via trapezoidal integration anchored at (recall=0, precision=1)
    # Prepend anchor so area from recall=0 is included
    recalls_full = np.concatenate([[0.0], recalls_arr])
    precisions_full = np.concatenate([[1.0], precisions_arr])
    order_r = np.argsort(recalls_full)
    trapz_fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    ap = float(abs(trapz_fn(precisions_full[order_r], recalls_full[order_r])))

    return {
        "precisions": precisions_arr,
        "recalls": recalls_arr,
        "thresholds": thresholds_arr,
        "average_precision": round(ap, 6),
    }


def compute_f1_score(
    probs: list | np.ndarray,
    labels: list | np.ndarray,
    threshold: float = 0.5,
) -> dict:
    """Compute precision, recall, and F1 score at a given probability threshold.

    Binarizes the predicted probabilities at ``threshold`` and computes the
    standard binary classification metrics.  All metrics are reported as
    floats in [0, 1].

    Args:
        probs: Predicted probabilities for the positive class (values in [0, 1]).
        labels: Binary ground-truth labels (0 or 1).
        threshold: Decision threshold for binarizing probabilities (default 0.5).

    Returns:
        Dict with keys:

        - ``"precision"``: TP / (TP + FP); 0.0 if no positive predictions.
        - ``"recall"``: TP / (TP + FN); 0.0 if no positive examples.
        - ``"f1"``: Harmonic mean of precision and recall; 0.0 if both are zero.
        - ``"threshold"``: The decision threshold used.
        - ``"n_samples"``: Total number of samples evaluated.
    """
    probs_arr = np.asarray(probs, dtype=float)
    labels_arr = np.asarray(labels, dtype=float)
    n = len(probs_arr)

    if n == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "threshold": threshold, "n_samples": 0}

    predicted = (probs_arr >= threshold).astype(float)

    tp = float(np.sum((predicted == 1) & (labels_arr == 1)))
    fp = float(np.sum((predicted == 1) & (labels_arr == 0)))
    fn = float(np.sum((predicted == 0) & (labels_arr == 1)))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "threshold": threshold,
        "n_samples": n,
    }


def compute_average_precision(
    probs: list | np.ndarray,
    labels: list | np.ndarray,
) -> float:
    """Compute Average Precision (AP) from predicted probabilities and binary labels.

    Convenience wrapper around :func:`compute_precision_recall_curve` that
    returns only the scalar AP value.  The PR curve is anchored at
    (recall=0, precision=1) so that AP is the area under the full curve.

    Args:
        probs: Predicted probabilities for the positive class, values in [0, 1].
        labels: Binary ground-truth labels (0 or 1).

    Returns:
        Average precision in [0, 1]; 0.0 for empty input or single-class labels.
    """
    result = compute_precision_recall_curve(probs, labels)
    return float(result["average_precision"])


def compute_calibration_sharpness(probs: list[float]) -> float:
    """Compute calibration sharpness — mean confidence across all predictions.

    For each predicted probability p, confidence = max(p, 1 − p).
    Sharpness is the mean of these confidences across all samples.

    A perfectly uncertain model (all predictions = 0.5) has sharpness 0.5.
    A perfectly sharp model (all predictions = 0 or 1) has sharpness 1.0.

    Args:
        probs: List of predicted probabilities, each in [0, 1].

    Returns:
        Mean confidence in [0.5, 1.0], rounded to 4 decimal places.
        Returns 0.5 for empty input.
    """
    if not probs:
        return 0.5
    confidences = [max(p, 1.0 - p) for p in probs]
    return round(float(sum(confidences) / len(confidences)), 4)


def compute_brier_skill_score(
    probs: list[float] | np.ndarray,
    labels: list[int] | np.ndarray,
) -> float:
    """Compute the Brier Skill Score (BSS) relative to a climatological baseline.

    BSS = 1 − (BS_model / BS_climatology), where BS_climatology is the Brier
    score of a naive model that always predicts the base rate (fraction of
    positive labels).

    - BSS = 1.0  → perfect forecast
    - BSS = 0.0  → no skill over climatology
    - BSS < 0.0  → worse than climatology

    Returns 0.0 for empty inputs or when BS_climatology is zero (all-same-label
    datasets where climatology is also a perfect predictor).

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: True binary labels (0 or 1).

    Returns:
        Brier Skill Score, rounded to 6 decimal places.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if p.size == 0:
        return 0.0

    bs_model = float(np.mean((p - y) ** 2))
    base_rate = float(np.mean(y))
    bs_clim = float(base_rate * (1.0 - base_rate))

    if bs_clim == 0.0:
        return 0.0

    bss = 1.0 - bs_model / bs_clim
    return round(bss, 6)


def compute_discrimination_score(
    probs: list[float] | np.ndarray,
    labels: list[int] | np.ndarray,
) -> float:
    """Compute a simple discrimination score between positives and negatives.

    Discrimination = |mean(p | y=1) − mean(p | y=0)|.

    A perfectly discriminating model assigns mean probability 1.0 to positives
    and 0.0 to negatives, giving a score of 1.0.  A random model gives ~0.0.

    Returns 0.0 for empty inputs or when only one class is present (score is
    undefined without both positive and negative examples).

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: True binary labels (0 or 1).

    Returns:
        Discrimination score in [0, 1], rounded to 6 decimal places.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if p.size == 0:
        return 0.0
    pos_mask = y == 1
    neg_mask = y == 0
    if not pos_mask.any() or not neg_mask.any():
        return 0.0
    mean_pos = float(p[pos_mask].mean())
    mean_neg = float(p[neg_mask].mean())
    return round(abs(mean_pos - mean_neg), 6)


def compute_resolution_score(
    probs: list[float] | np.ndarray,
    labels: list[int] | np.ndarray,
    n_bins: int = 10,
) -> float:
    """Return the resolution component of the Brier score decomposition.

    Resolution measures how much the per-bin mean outcomes deviate from the
    overall climatological base rate.  Higher resolution indicates better
    discrimination ability.

    Uses equal-width bins over [0, 1].  Bins with no samples are skipped.
    Returns 0.0 for empty inputs or single-class label sets.

    Formula::

        resolution = (1 / n) * Σ_k  n_k * (ȳ_k - ȳ)²
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if p.size == 0:
        return 0.0
    clim = float(y.mean())
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = float(p.size)
    resolution = 0.0
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (p >= lo) & (p < hi)
        if not mask.any():
            continue
        n_k = float(mask.sum())
        y_bar_k = float(y[mask].mean())
        resolution += n_k * (y_bar_k - clim) ** 2
    return round(resolution / total, 8)


def compute_expected_positive_rate(
    probs: list[float] | np.ndarray,
    threshold: float = 0.5,
) -> float:
    """Return the fraction of predictions at or above *threshold*.

    This is the expected positive rate (EPR) — the fraction of items that
    would be classified as positive at the given decision threshold.
    Useful for capacity planning: an EPR of 0.1 with 1,000 candidates
    means roughly 100 follow-up observations are needed.

    Returns 0.0 for empty inputs or when *threshold* > 1.0.
    """
    p = np.asarray(probs, dtype=float)
    if p.size == 0:
        return 0.0
    return round(float((p >= threshold).mean()), 6)


def compute_reliability_score(
    probs: list[float] | np.ndarray,
    labels: list[int] | np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute a reliability score defined as 1 − ECE.

    Higher values (closer to 1.0) indicate better probability calibration.
    Returns 1.0 for empty inputs (perfect by convention).

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: Binary ground-truth labels (0 or 1).
        n_bins: Number of equal-width bins for ECE computation.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if p.size == 0:
        return 1.0
    ece = expected_calibration_error(p, y.astype(int), n_bins=n_bins)
    return round(float(max(0.0, 1.0 - ece)), 6)


def compute_calibration_drift(
    probs_t0: list[float],
    labels_t0: list[int],
    probs_t1: list[float],
    labels_t1: list[int],
    n_bins: int = 10,
) -> float:
    """Return the ECE drift between two time snapshots.

    Computes ECE(t1) - ECE(t0).  A positive value means calibration has
    degraded; negative means it has improved.  Returns 0.0 when either
    input set is empty.
    """
    p0 = np.asarray(probs_t0, dtype=float)
    y0 = np.asarray(labels_t0, dtype=float)
    p1 = np.asarray(probs_t1, dtype=float)
    y1 = np.asarray(labels_t1, dtype=float)
    if p0.size == 0 or p1.size == 0:
        return 0.0
    ece0 = expected_calibration_error(p0, y0.astype(int), n_bins=n_bins)
    ece1 = expected_calibration_error(p1, y1.astype(int), n_bins=n_bins)
    return round(float(ece1 - ece0), 8)


def compute_calibration_uniformity(probs: list[float]) -> float:
    """Return the Kolmogorov-Smirnov statistic of probabilities vs Uniform[0,1].

    Measures how far the predicted probability distribution is from uniform.
    0.0 = perfectly uniform; 1.0 = all mass at one extreme.  Returns 0.0
    for empty input.
    """
    p = np.asarray(probs, dtype=float)
    if p.size == 0:
        return 0.0
    p_sorted = np.sort(p)
    n = len(p_sorted)
    empirical = np.arange(1, n + 1) / n
    theoretical = p_sorted  # CDF of Uniform[0,1] at x is x
    ks_stat = float(np.max(np.abs(empirical - theoretical)))
    return round(float(min(1.0, ks_stat)), 6)


def compute_mean_calibration_error(
    probs_list: list,
    labels_list: list,
    n_bins: int = 10,
) -> float:
    """Return the mean Expected Calibration Error across multiple (probs, labels) pairs.

    Computes ECE for each (probs, labels) pair and returns the arithmetic mean.
    Returns 0.0 when *probs_list* is empty.

    Args:
        probs_list: List of probability lists, one per evaluation set.
        labels_list: List of label lists, parallel to *probs_list*.
        n_bins: Number of equal-width bins for ECE computation (default 10).

    Returns:
        Mean ECE as a float.
    """
    if not probs_list:
        return 0.0
    total = 0.0
    count = 0
    for probs, labels in zip(probs_list, labels_list):
        p = np.asarray(probs, dtype=float)
        y = np.asarray(labels, dtype=float)
        total += expected_calibration_error(p, y.astype(int), n_bins=n_bins)
        count += 1
    return round(float(total / count), 8) if count > 0 else 0.0


def compute_resolution(
    probs: list[float],
    labels: list[int],
    n_bins: int = 10,
) -> float:
    """Compute the resolution component of the Brier score decomposition.

    Resolution = Σ_k (n_k / N) * (o_k - o_bar)^2, where o_k is the fraction
    positive in bin k, o_bar is the overall fraction positive, n_k is the bin
    count, and N is the total number of samples.  Uses equal-width bins on [0, 1].
    Returns 0.0 for empty input or when o_bar is 0 or 1 (no resolution possible).
    Result is rounded to 8 decimal places.
    """
    import numpy as np

    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if len(p) == 0 or len(y) == 0:
        return 0.0
    o_bar = float(y.mean())
    if o_bar == 0.0 or o_bar == 1.0:
        return 0.0
    n_total = len(p)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    resolution = 0.0
    for i in range(n_bins):
        if i < n_bins - 1:
            mask = (p >= bin_edges[i]) & (p < bin_edges[i + 1])
        else:
            mask = (p >= bin_edges[i]) & (p <= bin_edges[i + 1])
        n_k = int(mask.sum())
        if n_k == 0:
            continue
        o_k = float(y[mask].mean())
        resolution += (n_k / n_total) * (o_k - o_bar) ** 2
    return round(float(resolution), 8)


def compute_calibration_slope(
    probs: list[float] | np.ndarray,
    labels: list[int] | np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute the linear regression slope of observed frequency vs mean predicted probability.

    Bins predictions into *n_bins* equal-width bins, computes the mean predicted
    probability and observed positive fraction per non-empty bin, then fits a
    least-squares regression line.  Returns the slope; 1.0 = perfect calibration,
    < 1.0 = overconfident, > 1.0 = underconfident.

    Returns 1.0 if fewer than 2 non-empty bins exist.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if len(p) == 0 or len(y) == 0:
        return 1.0
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    x_bins: list[float] = []
    y_bins: list[float] = []
    for i in range(n_bins):
        if i < n_bins - 1:
            mask = (p >= bin_edges[i]) & (p < bin_edges[i + 1])
        else:
            mask = (p >= bin_edges[i]) & (p <= bin_edges[i + 1])
        n_k = int(mask.sum())
        if n_k == 0:
            continue
        x_bins.append(float(p[mask].mean()))
        y_bins.append(float(y[mask].mean()))
    if len(x_bins) < 2:
        return 1.0
    x_arr = np.array(x_bins)
    y_arr = np.array(y_bins)
    x_mean = x_arr.mean()
    y_mean = y_arr.mean()
    num = float(((x_arr - x_mean) * (y_arr - y_mean)).sum())
    den = float(((x_arr - x_mean) ** 2).sum())
    return round(num / den, 8)


def compute_overconfidence_score(
    probs: list[float] | np.ndarray,
    labels: list[int] | np.ndarray,
) -> float:
    """Compute the overconfidence score: mean predicted probability minus observed fraction.

    Positive = overconfident (predicted higher than reality).
    Negative = underconfident.  Returns 0.0 for empty inputs.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    if len(p) == 0 or len(y) == 0:
        return 0.0
    return round(float(p.mean()) - float(y.mean()), 8)


def compute_calibration_summary(
    probs: list[float], labels: list[float | int]
) -> dict:
    """Compute a comprehensive calibration summary in a single call.

    Returns a dict with keys::

        {
            "brier_score": float,
            "ece": float,
            "log_loss": float,
            "roc_auc": float,
            "overconfidence": float,
            "n_samples": int,
        }

    Returns sentinel values (``0.0`` for error scores, ``0.5`` for
    ``roc_auc``, ``0.0`` for ``overconfidence``) for empty inputs.
    """
    n = len(probs)
    if n == 0:
        return {
            "brier_score": 0.0,
            "ece": 0.0,
            "log_loss": 0.0,
            "roc_auc": 0.5,
            "overconfidence": 0.0,
            "n_samples": 0,
        }
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    return {
        "brier_score": brier_score(p, y),
        "ece": expected_calibration_error(p, y),
        "log_loss": compute_log_loss(p, y),
        "roc_auc": compute_roc_auc(p, y),
        "overconfidence": compute_overconfidence_score(p, y),
        "n_samples": n,
    }


def compute_hosmer_lemeshow_statistic(
    probs: list | np.ndarray,
    labels: list | np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute the Hosmer-Lemeshow goodness-of-fit statistic.

    Sorts samples by predicted probability, splits into ``n_bins`` equal-size
    groups, then returns the sum of ``(O - E)^2 / E`` over non-degenerate
    bins (where ``E > 0`` and ``n_bin - E > 0``).

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: Binary observed labels (0 or 1).
        n_bins: Number of groups (default 10).

    Returns:
        Hosmer-Lemeshow statistic as a float.  Returns ``0.0`` for empty
        input or fewer than 2 samples.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    n = len(p)
    if n < 2:
        return 0.0

    order = np.argsort(p)
    p_sorted = p[order]
    y_sorted = y[order]

    indices = np.array_split(np.arange(n), n_bins)
    hl_stat = 0.0
    for idx in indices:
        if len(idx) == 0:
            continue
        n_bin = float(len(idx))
        obs = float(y_sorted[idx].sum())
        exp = float(p_sorted[idx].sum())
        if exp == 0.0 or (n_bin - exp) == 0.0:
            continue
        hl_stat += (obs - exp) ** 2 / exp
    return float(hl_stat)


def compute_spiegelhalter_z(
    probs: list[float] | np.ndarray,
    labels: list[float] | np.ndarray,
    eps: float = 1e-7,
) -> float:
    """Compute Spiegelhalter's Z-score for probability calibration.

    For each sample *i*, computes ``z_i = (y_i − p_i) * (1 − 2*p_i)``.
    The overall Z-score is::

        Z = sum(z_i) / sqrt(sum(p_i * (1 − p_i) * (1 − 2*p_i)²))

    Returns ``0.0`` for empty input, fewer than 2 samples, or when the
    denominator is ≤ ``eps``.

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: Binary observed labels (0 or 1).
        eps: Minimum denominator threshold (default 1e-7).

    Returns:
        Spiegelhalter Z-score as a float.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    n = len(p)
    if n < 2:
        return 0.0
    p = np.clip(p, eps, 1.0 - eps)
    z_i = (y - p) * (1.0 - 2.0 * p)
    var_i = p * (1.0 - p) * (1.0 - 2.0 * p) ** 2
    denom = float(np.sqrt(np.sum(var_i)))
    if denom <= eps:
        return 0.0
    return float(np.sum(z_i) / denom)


def compute_brier_skill_score_weighted(
    probs: list | np.ndarray,
    labels: list | np.ndarray,
    weights: list | np.ndarray | None = None,
) -> float:
    """Compute a weighted Brier Skill Score (BSS).

    Computes a sample-weighted version of the BSS where the climatological
    baseline uses the same weights:

    - Weighted BS = sum(w * (p − y)²) / sum(w)
    - Weighted climatology p̄ = sum(w * y) / sum(w)
    - Weighted BS_clim = p̄ * (1 − p̄)
    - BSS = 1 − BS / BS_clim

    Returns ``0.0`` for empty input, all-zero weights, or when the
    climatological BS is zero (all labels identical → no skill to measure).

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: True binary labels (0 or 1).
        weights: Non-negative sample weights.  If ``None``, uniform weights
            are used (equivalent to :func:`compute_brier_skill_score`).

    Returns:
        Weighted Brier Skill Score, rounded to 6 decimal places.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    n = len(p)
    if n == 0:
        return 0.0

    if weights is None:
        w = np.ones(n, dtype=float)
    else:
        w = np.asarray(weights, dtype=float)

    total_weight = float(w.sum())
    if total_weight <= 0.0:
        return 0.0

    bs = float(np.sum(w * (p - y) ** 2)) / total_weight
    p_bar = float(np.sum(w * y)) / total_weight
    bs_clim = p_bar * (1.0 - p_bar)

    if bs_clim == 0.0:
        return 0.0

    bss = 1.0 - bs / bs_clim
    return round(float(bss), 6)


def compute_isotonic_calibration_error(
    probs: list | np.ndarray,
    labels: list | np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute the mean absolute calibration error after isotonic regression.

    Fits an isotonic regression calibrator to *probs* and *labels*, obtains
    calibrated probabilities, then computes the mean absolute error between
    the calibrated probabilities and the true labels.  Returns ``0.0`` for
    empty input or fewer than 2 samples.

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: True binary labels (0 or 1).
        n_bins: Unused parameter retained for API consistency (default 10).

    Returns:
        Mean absolute calibration error (float ≥ 0).
    """
    from sklearn.isotonic import IsotonicRegression

    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    n = len(p)
    if n < 2:
        return 0.0
    iso = IsotonicRegression(out_of_bounds="clip")
    calibrated = iso.fit_transform(p, y)
    mae = float(np.mean(np.abs(calibrated - y)))
    return round(mae, 6)


def compute_expected_calibration_error_weighted(
    probs: list[float],
    labels: list[float],
    weights: list[float],
    n_bins: int = 10,
) -> float:
    """Compute weighted Expected Calibration Error (ECE).

    Predictions are binned by their predicted probability value.  Each bin's
    contribution to the ECE is weighted by the fraction of total weight that
    falls in that bin:
    ``abs(mean_prob_in_bin - mean_label_in_bin) * (sum_weights_in_bin / total_weight)``

    Args:
        probs: Predicted probabilities in [0, 1].
        labels: Binary ground-truth labels (0 or 1).
        weights: Non-negative sample weights (one per prediction).
        n_bins: Number of equal-width probability bins (default 10).

    Returns:
        Weighted ECE (float ≥ 0).  Returns 0.0 for empty input or zero
        total weight.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    w = np.asarray(weights, dtype=float)
    if len(p) == 0:
        return 0.0
    total_weight = float(w.sum())
    if total_weight == 0.0:
        return 0.0
    ece = 0.0
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    for i in range(n_bins):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        if not mask.any():
            continue
        bin_weight = float(w[mask].sum())
        if bin_weight == 0.0:
            continue
        mean_prob = float(np.average(p[mask], weights=w[mask]))
        mean_label = float(np.average(y[mask], weights=w[mask]))
        ece += abs(mean_prob - mean_label) * (bin_weight / total_weight)
    return float(ece)


def compute_positive_rate(probs: list[float], threshold: float = 0.5) -> float:
    """Return the fraction of probabilities that exceed *threshold*.

    Returns 0.0 for an empty list.
    """
    if not probs:
        return 0.0
    return float(sum(1 for p in probs if p > threshold)) / float(len(probs))


def compute_weighted_brier_score(
    probs: list[float],
    labels: list[float],
    weights: list[float],
) -> float:
    """Return the sample-weighted Brier score.

    Brier score = Σ wᵢ·(pᵢ − yᵢ)² / Σ wᵢ.
    Returns 0.0 if the input is empty or all weights are zero.
    """
    if not probs or not labels or not weights:
        return 0.0
    total_w = sum(weights)
    if total_w <= 0.0:
        return 0.0
    return float(
        sum(w * (p - y) ** 2 for p, y, w in zip(probs, labels, weights)) / total_w
    )


def compute_calibration_gap(probs: list[float], labels: list[float], n_bins: int = 10) -> float:
    """Return the mean absolute gap between predicted probability and observed frequency.

    Bins predictions into ``n_bins`` equal-width bins, computes |bin_mean_pred − fraction_positive|
    for non-empty bins, and returns their mean.  Returns 0.0 for empty inputs or no non-empty bins.
    """
    if not probs or not labels:
        return 0.0
    import math

    bin_sums: dict[int, float] = {}
    bin_pos: dict[int, float] = {}
    bin_counts: dict[int, int] = {}
    for p, y in zip(probs, labels):
        idx = min(int(math.floor(float(p) * n_bins)), n_bins - 1)
        bin_sums[idx] = bin_sums.get(idx, 0.0) + float(p)
        bin_pos[idx] = bin_pos.get(idx, 0.0) + float(y)
        bin_counts[idx] = bin_counts.get(idx, 0) + 1
    gaps = []
    for idx, cnt in bin_counts.items():
        mean_pred = bin_sums[idx] / cnt
        frac_pos = bin_pos[idx] / cnt
        gaps.append(abs(mean_pred - frac_pos))
    return float(sum(gaps) / len(gaps)) if gaps else 0.0


def compute_calibration_gain(
    raw_probs: list[float],
    cal_probs: list[float],
    labels: list[float],
) -> float:
    """Return the Brier score reduction achieved by calibration.

    Gain = Brier(raw_probs, labels) - Brier(cal_probs, labels).
    Positive gain means calibration improved the predictions.
    Returns 0.0 if either list is empty or lengths differ.
    """
    if not raw_probs or not cal_probs or not labels:
        return 0.0
    if len(raw_probs) != len(cal_probs) or len(raw_probs) != len(labels):
        return 0.0
    p_raw = np.array(raw_probs, dtype=float)
    p_cal = np.array(cal_probs, dtype=float)
    y = np.array(labels, dtype=float)
    raw_brier = brier_score(p_raw, y)
    cal_brier = brier_score(p_cal, y)
    return float(raw_brier - cal_brier)


def compute_calibration_bias(probs: list, labels: list) -> float:
    """Return the mean calibration bias: mean(predicted_prob) - fraction_positive.

    A positive bias means the model is over-confident (predicts higher probabilities
    than the observed positive rate).  A negative bias means under-confidence.
    Returns 0.0 if the input lists are empty or have different lengths.
    """
    if not probs or not labels:
        return 0.0
    if len(probs) != len(labels):
        return 0.0
    p_arr = np.array(probs, dtype=float)
    y_arr = np.array(labels, dtype=float)
    return float(np.mean(p_arr) - np.mean(y_arr))


def compute_overconfidence_fraction(
    probs: list,
    labels: list,
    threshold: float = 0.7,
) -> float:
    """Return the fraction of high-confidence predictions that are incorrect.

    A prediction is "high-confidence" if its probability ≥ *threshold*.
    Among those, the fraction where the true label is 0 (wrong prediction) is
    returned.

    Returns ``0.0`` if the input lists are empty, have different lengths, or
    no prediction exceeds the threshold.
    """
    if not probs or not labels:
        return 0.0
    if len(probs) != len(labels):
        return 0.0
    high_conf = [(p, y) for p, y in zip(probs, labels) if float(p) >= threshold]
    if not high_conf:
        return 0.0
    wrong = sum(1 for _, y in high_conf if float(y) == 0.0)
    return float(wrong / len(high_conf))


def compute_max_calibration_error(
    probs: list,
    labels: list,
    n_bins: int = 10,
) -> float:
    """Return the Maximum Calibration Error (MCE) across equal-width bins.

    MCE = max over non-empty bins of |mean_predicted_prob − fraction_positive|.

    Bins span [0, 1] with width 1/n_bins.  Empty bins are skipped.
    Returns 0.0 for empty input, mismatched lengths, or n_bins < 1.
    """
    if not probs or not labels or len(probs) != len(labels):
        return 0.0
    n_bins = max(1, int(n_bins))
    bin_probs: list[list[float]] = [[] for _ in range(n_bins)]
    bin_labels: list[list[float]] = [[] for _ in range(n_bins)]
    for p, y in zip(probs, labels):
        idx = int(float(p) * n_bins)
        if idx >= n_bins:
            idx = n_bins - 1
        bin_probs[idx].append(float(p))
        bin_labels[idx].append(float(y))
    mce = 0.0
    for bp, bl in zip(bin_probs, bin_labels):
        if not bp:
            continue
        gap = abs(sum(bp) / len(bp) - sum(bl) / len(bl))
        if gap > mce:
            mce = gap
    return float(mce)


def compute_calibration_resolution(
    probs: list,
    labels: list,
    n_bins: int = 10,
) -> float:
    """Return a calibration resolution score in [0, 1].

    Resolution measures how much the per-bin fraction_positive values deviate
    from the overall base rate: high resolution means the model separates
    positives from negatives well.

    .. math::

        \\text{Resolution} = \\frac{1}{n} \\sum_k n_k (\\bar{y}_k - \\bar{y})^2

    where :math:`\\bar{y}` is the overall fraction of positives,
    :math:`\\bar{y}_k` is the fraction of positives in bin *k*, and :math:`n_k`
    is the number of samples in that bin.  The result is normalized by the
    maximum possible value (base_rate × (1 − base_rate)), clamped to [0, 1].
    Returns 0.0 for empty input, mismatched lengths, or n_bins < 1.
    """
    if not probs or not labels or len(probs) != len(labels):
        return 0.0
    n_bins = max(1, int(n_bins))
    n = len(probs)
    base_rate = sum(float(y) for y in labels) / n
    bin_labels: list[list[float]] = [[] for _ in range(n_bins)]
    for p, y in zip(probs, labels):
        idx = int(float(p) * n_bins)
        if idx >= n_bins:
            idx = n_bins - 1
        bin_labels[idx].append(float(y))
    resolution = 0.0
    for bl in bin_labels:
        if not bl:
            continue
        frac = sum(bl) / len(bl)
        resolution += len(bl) * (frac - base_rate) ** 2
    resolution /= n
    normalizer = base_rate * (1.0 - base_rate)
    if normalizer <= 0.0:
        return 0.0
    return float(min(1.0, resolution / normalizer))


def compute_fraction_calibrated(
    probs: list,
    labels: list,
    threshold: float = 0.1,
    n_bins: int = 10,
) -> float:
    """Return the fraction of non-empty bins within *threshold* of perfect calibration.

    For each non-empty equal-width bin, computes |mean_predicted_prob −
    fraction_positive|.  Returns the fraction of non-empty bins where this
    error is ≤ *threshold*.

    Returns 0.0 for empty input, mismatched lengths, or no non-empty bins.
    """
    if not probs or not labels or len(probs) != len(labels):
        return 0.0
    n_bins = max(1, int(n_bins))
    bin_probs: list[list[float]] = [[] for _ in range(n_bins)]
    bin_labels: list[list[float]] = [[] for _ in range(n_bins)]
    for p, y in zip(probs, labels):
        idx = int(float(p) * n_bins)
        if idx >= n_bins:
            idx = n_bins - 1
        bin_probs[idx].append(float(p))
        bin_labels[idx].append(float(y))
    n_calibrated = 0
    n_nonempty = 0
    for bp, bl in zip(bin_probs, bin_labels):
        if not bp:
            continue
        n_nonempty += 1
        mean_p = sum(bp) / len(bp)
        frac_pos = sum(bl) / len(bl)
        if abs(mean_p - frac_pos) <= threshold:
            n_calibrated += 1
    return float(n_calibrated) / n_nonempty if n_nonempty > 0 else 0.0
