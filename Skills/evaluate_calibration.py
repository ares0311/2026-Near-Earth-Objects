#!/usr/bin/env python
"""Evaluate calibration quality for a trained classifier.

Usage:
    PYTHONPATH=src python Skills/evaluate_calibration.py

Generates synthetic scores + labels, fits both Platt and isotonic calibrators,
and prints Brier score and ECE for each method.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np

from calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    brier_score,
    expected_calibration_error,
)


def _synthetic_data(n: int = 500, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    # Raw scores skewed toward 0 (most candidates are not NEOs)
    scores = rng.beta(1.5, 5.0, n)
    # True labels: P(label=1) proportional to score
    labels = (rng.uniform(size=n) < scores).astype(float)
    return scores, labels


def main() -> None:
    scores, labels = _synthetic_data()
    split = len(scores) // 2
    train_s, train_l = scores[:split], labels[:split]
    test_s, test_l = scores[split:], labels[split:]

    platt = PlattCalibrator().fit(train_s, train_l)
    iso = IsotonicCalibrator().fit(train_s, train_l)

    raw_brier = brier_score(test_s, test_l)
    platt_brier = brier_score(platt.predict(test_s), test_l)
    iso_brier = brier_score(iso.predict(test_s), test_l)

    raw_ece = expected_calibration_error(test_s, test_l)
    platt_ece = expected_calibration_error(platt.predict(test_s), test_l)
    iso_ece = expected_calibration_error(iso.predict(test_s), test_l)

    print("Calibration evaluation (synthetic data, n=500)")
    print("-" * 50)
    print(f"{'Method':<12} {'Brier':>8} {'ECE':>8}")
    print(f"{'Raw':<12} {raw_brier:>8.4f} {raw_ece:>8.4f}")
    print(f"{'Platt':<12} {platt_brier:>8.4f} {platt_ece:>8.4f}")
    print(f"{'Isotonic':<12} {iso_brier:>8.4f} {iso_ece:>8.4f}")


if __name__ == "__main__":
    main()
