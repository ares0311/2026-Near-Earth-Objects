"""Calibration — Platt scaling and isotonic PAVA for classifier probability calibration."""

from __future__ import annotations

__all__ = [
    "IsotonicCalibrator", "PlattCalibrator",
    "brier_score", "reliability_diagram_data", "expected_calibration_error", "calibrate",
    "bootstrap_confidence_interval",
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

    if not probs or not labels:
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
