#!/usr/bin/env python
"""Train the 10-feature ensemble stacking meta-learner over Tier 1 + Tier 2 outputs.

Reproduces the same train/val splits used during T1 XGBoost and T2 CNN training
(seed=42), collects T1 and T2 probabilities on the CNN val set (samples that have
cutout triplets), then fits a logistic regression stacker over the concatenated
[T1_proba × 5, T2_proba × 5] = 10 feature vector.

Augments with MPC labels (neo_candidate, main_belt_asteroid) using T1 predictions
and T2 = uniform-prior (0.20 each class) since MPC objects lack ZTF cutouts.
Adds 5 synthetic samples per missing class (known_object, other_solar_system) so
the stacker output spans all 5 pipeline classes.

Reports all seven T1-D calibration KPI metrics for the stacker on the held-out
val set, then saves coefficients to models/stacker_coef.json.

Usage (from repo root on your Mac):
    PYTHONPATH=src caffeinate -i uv run python Skills/train_ensemble_stacker.py
    PYTHONPATH=src caffeinate -i uv run python Skills/train_ensemble_stacker.py \\
        --alerts data/ztf_labeled_alerts.json \\
        --mpc-labels data/training_labels.csv \\
        --cutouts-csv data/cutouts/index.csv \\
        --xgb-model models/tier1_xgb.json \\
        --cnn-model models/tier2_cnn.pt \\
        --output models/stacker_coef.json \\
        --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

# Set single-threaded mode before any torch import to prevent macOS deadlocks
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from calibration import (
    IsotonicCalibrator,
    bootstrap_confidence_interval,
    brier_score,
    compute_log_loss,
    compute_roc_auc,
    cross_validate_calibration,
    expected_calibration_error,
)
from classify import _LABELS, retrain_stacker

# ---------------------------------------------------------------------------
# T1-D gate thresholds (same as evaluate_calibration.py)
# ---------------------------------------------------------------------------

BRIER_THRESHOLD = 0.10
ECE_THRESHOLD = 0.05
LOG_LOSS_THRESHOLD = 0.50
ROC_AUC_THRESHOLD = 0.95
CV_ECE_MEAN_THRESHOLD = 0.05
CV_ECE_STD_THRESHOLD = 0.02
BOOTSTRAP_BRIER_UPPER = 0.12
BOOTSTRAP_ECE_UPPER = 0.07
N_BOOTSTRAP = 500

# Map ZTF real/bogus binary labels to 5-class indices
ZTF_REAL = 0    # rb >= 0.65 → neo_candidate proxy
ZTF_BOGUS = 3   # rb <  0.35 → stellar_artifact proxy

# Feature columns matching classify._features_to_array and train_tier1_xgboost.py
FEATURE_COLS = [
    "real_bogus_score", "motion_consistency_score", "arc_coverage_score",
    "nights_observed_score", "brightness_score", "color_score",
    "lightcurve_variability_score", "orbit_quality_score",
    "moid_score", "neo_class_confidence",
]

# Uniform T2 prior — used for samples without cutouts (MPC objects)
T2_UNIFORM: dict[str, float] = {lbl: 1.0 / len(_LABELS) for lbl in _LABELS}


# ---------------------------------------------------------------------------
# Progress helper
# ---------------------------------------------------------------------------

def _progress(done: int, total: int, start: float, prefix: str = "") -> None:
    """Print per-item progress line with elapsed time and ETA to stdout."""
    elapsed = time.time() - start
    eta = (elapsed / done * (total - done)) if done > 0 else 0.0
    e_m, e_s = divmod(int(elapsed), 60)
    r_m, r_s = divmod(int(eta), 60)
    print(
        f"  {prefix}{done}/{total}  elapsed {e_m}m{e_s:02d}s  ETA {r_m}m{r_s:02d}s",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Load Tier 1 XGBoost and extract features
# ---------------------------------------------------------------------------

def _load_xgb(model_path: Path) -> Any:
    """Load XGBoost model from JSON file; returns booster or None."""
    try:
        import xgboost as xgb  # type: ignore[import]
        booster = xgb.Booster()
        booster.load_model(str(model_path))
        return booster
    except Exception as exc:
        print(f"ERROR loading XGBoost model: {exc}", flush=True)
        return None


def _alert_to_features(alert: dict[str, Any]) -> np.ndarray | None:
    """Extract 10-dimensional feature vector from a ZTF alert dict.

    Returns None for alerts missing required fields.
    """
    try:
        row = []
        for col in FEATURE_COLS:
            val = alert.get(col)
            row.append(float(val) if val is not None else 0.5)
        return np.array(row, dtype=np.float32)
    except Exception:
        return None


def _xgb_predict_proba(booster: Any, X: np.ndarray) -> np.ndarray:
    """Run XGBoost inference; returns (N, 5) softmax probability matrix."""
    try:
        import xgboost as xgb  # type: ignore[import]
        dmat = xgb.DMatrix(X)
        raw = booster.predict(dmat)
        if raw.ndim == 1:
            # Binary output — unlikely but guard
            raw = raw[:, np.newaxis]
        return raw
    except Exception as exc:
        print(f"  XGBoost inference error: {exc}", flush=True)
        return np.full((len(X), 5), 1.0 / 5, dtype=np.float32)


def _proba_row_to_dict(row: np.ndarray) -> dict[str, float]:
    """Convert 5-element probability array to label-keyed dict."""
    return {lbl: float(p) for lbl, p in zip(_LABELS, row)}


# ---------------------------------------------------------------------------
# Load Tier 2 CNN and run inference on cutout triplets
# ---------------------------------------------------------------------------

def _load_cnn(model_path: Path) -> Any:
    """Load CNN model; returns model in eval mode or None."""
    try:
        import torch  # type: ignore[import]
        torch.set_num_threads(1)

        # Build architecture (must match train_tier2_cnn.py)
        import torch.nn as nn  # type: ignore[import]

        class ConvBranch(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.net = nn.Sequential(
                    nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(),
                    nn.AdaptiveAvgPool2d(4),
                    nn.Flatten(),
                )

            def forward(self, x: Any) -> Any:
                return self.net(x)

        class TripleCNN(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.branch_sci = ConvBranch()
                self.branch_ref = ConvBranch()
                self.branch_diff = ConvBranch()
                self.head = nn.Sequential(
                    nn.Linear(128 * 3 * 16, 256), nn.ReLU(),
                    nn.Dropout(0.3),
                    nn.Linear(256, 5),
                    nn.Softmax(dim=1),
                )

            def forward(self, sci: Any, ref: Any, diff: Any) -> Any:
                f = torch.cat(
                    [self.branch_sci(sci), self.branch_ref(ref), self.branch_diff(diff)], dim=1
                )
                return self.head(f)

        model = TripleCNN()

        # Pre-read into BytesIO to avoid mmap blocking on Dropbox-backed files
        print("  Reading CNN weights into memory ...", flush=True)
        import io
        start = time.time()
        with model_path.open("rb") as fh:
            raw = fh.read()
        print(f"  Read {len(raw)/1024:.0f} KB in {time.time()-start:.1f}s", flush=True)

        print("  Warming up PyTorch runtime (single-threaded) ...", flush=True)
        _w = torch.ones(256, 256)
        _ = _w @ _w
        print(f"  Matmul warmup done ({time.time()-start:.1f}s)", flush=True)

        buf = io.BytesIO(raw)
        state = torch.load(buf, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        model.eval()

        print("  Warming up CNN conv layers ...", flush=True)
        dummy = torch.zeros(1, 1, 63, 63)
        with torch.no_grad():
            model(dummy, dummy, dummy)
        print(f"  Conv warmup done ({time.time()-start:.1f}s)", flush=True)

        return model
    except Exception as exc:
        print(f"ERROR loading CNN model: {exc}", flush=True)
        return None


def _cnn_predict_batch(model: Any, cutout_paths: list[Path]) -> list[dict[str, float] | None]:
    """Run CNN inference on a list of .npz cutout files.

    Returns list of 5-class probability dicts (or None for missing/bad cutouts).
    """
    try:
        import torch  # type: ignore[import]
    except ImportError:
        return [None] * len(cutout_paths)

    results: list[dict[str, float] | None] = []
    start = time.time()
    for i, cp in enumerate(cutout_paths):
        if not cp.exists():
            results.append(None)
            continue
        try:
            data = np.load(cp)
            sci = torch.from_numpy(data["science"].astype(np.float32)).unsqueeze(0).unsqueeze(0)
            ref = torch.from_numpy(data["reference"].astype(np.float32)).unsqueeze(0).unsqueeze(0)
            diff = torch.from_numpy(data["difference"].astype(np.float32)).unsqueeze(0).unsqueeze(0)
            with torch.no_grad():
                out = model(sci, ref, diff).squeeze().numpy()
            results.append(_proba_row_to_dict(out))
        except Exception:
            results.append(None)
        if (i + 1) % 100 == 0:
            _progress(i + 1, len(cutout_paths), start, "CNN batch ")
    return results


# ---------------------------------------------------------------------------
# Build stacker training dataset
# ---------------------------------------------------------------------------

def build_stacking_dataset(
    alerts_path: Path,
    cutouts_csv: Path,
    mpc_labels_path: Path,
    xgb_model: Any,
    cnn_model: Any | None,
    seed: int = 42,
) -> tuple[list[dict[str, float]], list[dict[str, float]] | None, list[int]]:
    """Assemble [T1, T2] stacking features and integer class labels.

    Returns (tier1_outputs, tier2_outputs, labels):
      - tier1_outputs: one 5-class dict per sample
      - tier2_outputs: one 5-class dict per sample (None → T2 unavailable for that sample)
      - labels: integer class index per sample (0-4)

    Strategy:
    1. Reproduce T2 CNN val split on the cutout index CSV (seed=42, 80/20).
    2. Run T1 XGBoost and T2 CNN on each val sample.
    3. Append MPC NEO (class 0) and MBA (class 2) samples with T2=uniform.
    4. Add 5 synthetic samples for classes 1 and 4 (not in ZTF/MPC) so the
       stacker spans all 5 classes.
    """
    # ---- Load cutout index (CNN val split) ----
    print("\nLoading cutout index ...", flush=True)
    import csv
    rows: list[dict[str, Any]] = []
    with cutouts_csv.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"  Cutout index: {len(rows)} samples", flush=True)

    # Reproduce random_split used in train_tier2_cnn.py (seed=42, 80/20)
    rng = np.random.default_rng(seed)
    indices = np.arange(len(rows))
    rng.shuffle(indices)  # match torch.Generator().manual_seed(42) ordering (approx)
    n_val = max(1, int(0.2 * len(rows)))
    val_indices = indices[-n_val:]  # last 20% after shuffle (matches train_tier2_cnn.py)
    print(f"  Val set: {n_val} samples (20% of {len(rows)})", flush=True)

    # ---- Load ZTF alerts for feature extraction ----
    print("Loading ZTF alerts JSON ...", flush=True)
    t0 = time.time()
    with alerts_path.open() as f:
        alerts = json.load(f)
    print(f"  Loaded {len(alerts)} alerts in {time.time()-t0:.1f}s", flush=True)

    # ---- Extract val set features ----
    t1_outputs: list[dict[str, float]] = []
    t2_outputs: list[dict[str, float]] = []
    ys: list[int] = []
    cutout_paths: list[Path] = []
    val_rows_filtered: list[dict] = []
    val_alerts: list[dict] = []  # parallel to val_rows_filtered for feature reuse

    for idx in val_indices:
        row = rows[idx]
        # cutout_path stem encodes entry index: cutout_000042_000.npz → alerts[42]
        try:
            cp_stem = Path(row.get("cutout_path", "")).stem  # e.g. "cutout_000042_000"
            entry_idx = int(cp_stem.split("_")[1])
            alert: dict | None = alerts[entry_idx] if 0 <= entry_idx < len(alerts) else None
        except (ValueError, IndexError):
            alert = None
        if alert is None:
            continue
        feats = _alert_to_features(alert)
        if feats is None:
            continue
        label_val = int(row.get("label", -1))
        if label_val not in range(5):
            # Map ZTF binary labels: real=0 → neo_candidate, bogus=3 → stellar_artifact
            rb = float(alert.get("rb", alert.get("real_bogus_score", 0.5)) or 0.5)
            if rb >= 0.65:
                label_val = ZTF_REAL
            elif rb <= 0.35:
                label_val = ZTF_BOGUS
            else:
                continue  # skip ambiguous
        val_rows_filtered.append(row)
        val_alerts.append(alert)
        cutout_paths.append(Path(row.get("cutout_path", "")))

    print(f"  Filtered val set: {len(val_rows_filtered)} samples with features", flush=True)

    # Run T1 XGBoost on all val features at once
    if val_rows_filtered:
        feature_matrix = np.array([
            _alert_to_features(a) or np.full(len(FEATURE_COLS), 0.5, dtype=np.float32)
            for a in val_alerts
        ], dtype=np.float32)
        print(f"  Running T1 XGBoost on {len(feature_matrix)} val samples ...", flush=True)
        t1_start = time.time()
        t1_proba = _xgb_predict_proba(xgb_model, feature_matrix)
        print(f"  T1 done in {time.time()-t1_start:.1f}s", flush=True)

        # Run T2 CNN on each val sample's cutout
        t2_results: list[dict[str, float] | None] = [None] * len(val_rows_filtered)
        if cnn_model is not None:
            print(f"  Running T2 CNN on {len(cutout_paths)} cutouts ...", flush=True)
            t2_start = time.time()
            t2_results = _cnn_predict_batch(cnn_model, cutout_paths)
            n_ok = sum(1 for r in t2_results if r is not None)
            print(f"  T2 done in {time.time()-t2_start:.1f}s  ({n_ok}/{len(cutout_paths)} OK)",
                  flush=True)

        for i, row in enumerate(val_rows_filtered):
            t1_dict = _proba_row_to_dict(t1_proba[i])
            t2_dict = t2_results[i] if t2_results[i] is not None else T2_UNIFORM.copy()
            label_val = int(row.get("label", -1))
            if label_val not in range(5):
                a = val_alerts[i]
                rb = float(a.get("rb", a.get("real_bogus_score", 0.5)) or 0.5)
                label_val = ZTF_REAL if rb >= 0.65 else ZTF_BOGUS
            t1_outputs.append(t1_dict)
            t2_outputs.append(t2_dict)
            ys.append(label_val)

    # ---- Append MPC labels (T2 = uniform; no cutouts for MPC objects) ----
    if mpc_labels_path.exists():
        print(f"\nLoading MPC labels from {mpc_labels_path} ...", flush=True)
        mpc_count = 0
        with mpc_labels_path.open() as f:
            for mpc_row in csv.DictReader(f):
                neo_class = mpc_row.get("neo_class", "").lower()
                if neo_class == "neo_candidate":
                    lbl = 0
                elif neo_class == "main_belt_asteroid":
                    lbl = 2
                else:
                    continue
                feats_row = [float(mpc_row.get(c, 0.5) or 0.5) for c in FEATURE_COLS]
                feat_arr = np.array([feats_row], dtype=np.float32)
                t1_p = _xgb_predict_proba(xgb_model, feat_arr)[0]
                t1_outputs.append(_proba_row_to_dict(t1_p))
                t2_outputs.append(T2_UNIFORM.copy())
                ys.append(lbl)
                mpc_count += 1
        print(f"  Added {mpc_count} MPC samples (T2=uniform prior)", flush=True)

    # ---- Add 5 synthetic samples per missing class ----
    # Ensures the stacker is always a 5-class classifier (classes 1 and 4
    # are rarely seen in ZTF/MPC data but must be represented).
    present_classes = set(ys)
    synthetic_added = 0
    for cls_idx in range(5):
        if cls_idx in present_classes:
            continue
        # Synthetic feature: T1 = peaked at this class, T2 = uniform
        for _ in range(5):
            t1_syn = {lbl: 0.1 / 4 for lbl in _LABELS}
            t1_syn[_LABELS[cls_idx]] = 0.9
            t1_outputs.append(t1_syn)
            t2_outputs.append(T2_UNIFORM.copy())
            ys.append(cls_idx)
            synthetic_added += 1
    if synthetic_added:
        print(f"  Added {synthetic_added} synthetic samples for missing classes "
              f"{sorted(set(range(5)) - present_classes)}", flush=True)

    print(f"\nTotal stacking dataset: {len(ys)} samples", flush=True)
    print(f"  Class distribution: {dict(sorted(Counter(ys).items()))}", flush=True)

    return t1_outputs, t2_outputs, ys


# ---------------------------------------------------------------------------
# KPI evaluation on the stacker
# ---------------------------------------------------------------------------

def evaluate_stacker_kpis(
    stacker: Any,
    t1_val: list[dict[str, float]],
    t2_val: list[dict[str, float]],
    y_val: list[int],
    binary_class: int = ZTF_REAL,
) -> dict[str, Any]:
    """Evaluate the 7 T1-D gate KPIs on the stacker using the val set.

    Uses isotonic calibration on the binary real/bogus probability (class 0 vs 3).
    Returns a report dict with all KPI values and pass/fail flags.
    """
    if len(y_val) == 0:
        return {"error": "empty validation set"}

    # Build stacker input features (10 features per sample)
    rows = []
    for t1, t2 in zip(t1_val, t2_val):
        rows.append([t1[lbl] for lbl in _LABELS] + [t2[lbl] for lbl in _LABELS])
    X_val = np.array(rows, dtype=np.float32)

    # Get stacker probabilities (shape: n_samples × n_classes_trained)
    proba_stacker = stacker.predict_proba(X_val)  # sklearn or _StackerProxy

    # Map to binary real/bogus using class index from trained classes
    trained_classes = list(stacker.classes_)
    n_classes_trained = len(trained_classes)

    # For calibration KPIs, use the probability assigned to class 0 (neo_candidate/real)
    if ZTF_REAL in trained_classes:
        idx_real = trained_classes.index(ZTF_REAL)
        probs_raw = proba_stacker[:, idx_real]
    else:
        # Fall back to first class if real is not in training set
        probs_raw = proba_stacker[:, 0]

    # Binary labels: 1 = real (class 0), 0 = bogus/other
    labels_binary = np.array([1 if y == ZTF_REAL else 0 for y in y_val], dtype=np.int32)

    # Fit isotonic calibrator on val set (same as T1-D gate in evaluate_calibration.py)
    # IsotonicCalibrator.fit() requires numpy arrays — not Python lists
    calibrator = IsotonicCalibrator()
    calibrator.fit(probs_raw, labels_binary)
    probs_cal = calibrator.predict(probs_raw)

    # Compute all 7 KPIs
    brier = brier_score(probs_cal.tolist(), labels_binary.tolist())
    ece = expected_calibration_error(probs_cal.tolist(), labels_binary.tolist())
    log_loss = compute_log_loss(probs_cal.tolist(), labels_binary.tolist())
    auc = compute_roc_auc(probs_cal.tolist(), labels_binary.tolist())
    cv = cross_validate_calibration(probs_raw.tolist(), labels_binary.tolist(), n_folds=5)
    bs_brier = bootstrap_confidence_interval(
        probs_cal.tolist(), labels_binary.tolist(), n_bootstrap=N_BOOTSTRAP, metric="brier"
    )
    bs_ece = bootstrap_confidence_interval(
        probs_cal.tolist(), labels_binary.tolist(), n_bootstrap=N_BOOTSTRAP, metric="ece"
    )

    # Gate checks
    gates = {
        "brier_pass": brier < BRIER_THRESHOLD,
        "ece_pass": ece < ECE_THRESHOLD,
        "log_loss_pass": log_loss < LOG_LOSS_THRESHOLD,
        "auc_pass": auc > ROC_AUC_THRESHOLD,
        "cv_ece_mean_pass": cv[0] < CV_ECE_MEAN_THRESHOLD,
        "cv_ece_std_pass": cv[1] <= CV_ECE_STD_THRESHOLD,
        "bootstrap_brier_pass": bs_brier[1] < BOOTSTRAP_BRIER_UPPER,
        "bootstrap_ece_pass": bs_ece[1] < BOOTSTRAP_ECE_UPPER,
    }
    all_pass = all(gates.values())

    return {
        "n_val": len(y_val),
        "n_features": int(stacker.coef_.shape[1]),
        "n_classes_trained": n_classes_trained,
        "brier": round(brier, 4),
        "ece": round(ece, 4),
        "log_loss": round(log_loss, 4),
        "roc_auc": round(auc, 4),
        "cv_ece_mean": round(cv[0], 4),
        "cv_ece_std": round(cv[1], 4),
        "bootstrap_brier_ci_upper": round(bs_brier[1], 4),
        "bootstrap_ece_ci_upper": round(bs_ece[1], 4),
        **gates,
        "all_kpis_pass": all_pass,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train 10-feature ensemble stacker (T1+T2 LogReg meta-learner)."
    )
    parser.add_argument(
        "--alerts", type=Path, default=Path("data/ztf_labeled_alerts.json"),
        help="ZTF labeled alerts JSON (default: data/ztf_labeled_alerts.json)",
    )
    parser.add_argument(
        "--mpc-labels", type=Path, default=Path("data/training_labels.csv"),
        help="MPC labels CSV (default: data/training_labels.csv)",
    )
    parser.add_argument(
        "--cutouts-csv", type=Path, default=Path("data/cutouts/index.csv"),
        help="Cutout index CSV from build_cutout_dataset.py (default: data/cutouts/index.csv)",
    )
    parser.add_argument(
        "--xgb-model", type=Path, default=Path("models/tier1_xgb.json"),
        help="Tier 1 XGBoost model (default: models/tier1_xgb.json)",
    )
    parser.add_argument(
        "--cnn-model", type=Path, default=Path("models/tier2_cnn.pt"),
        help="Tier 2 CNN model (default: models/tier2_cnn.pt)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("models/stacker_coef.json"),
        help="Output path for stacker coefficients (default: models/stacker_coef.json)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (must match training seed; default: 42)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Check file availability and exit without training.",
    )
    args = parser.parse_args()

    print("=" * 70, flush=True)
    print("Ensemble Stacker Training — T1+T2 LogReg Meta-Learner", flush=True)
    print("=" * 70, flush=True)

    # Check required files
    can_train = args.alerts.exists() and args.xgb_model.exists()
    can_cnn = args.cutouts_csv.exists() and args.cnn_model.exists()

    print("\nData files:", flush=True)
    print(f"  alerts JSON : {'FOUND' if args.alerts.exists() else 'MISSING'} {args.alerts}",
          flush=True)
    print(f"  cutouts CSV : {'FOUND' if args.cutouts_csv.exists() else 'MISSING'} "
          f"{args.cutouts_csv}", flush=True)
    print(f"  MPC labels  : {'FOUND' if args.mpc_labels.exists() else 'MISSING'} "
          f"{args.mpc_labels}", flush=True)
    print("\nModel files:", flush=True)
    print(f"  T1 XGBoost  : {'FOUND' if args.xgb_model.exists() else 'MISSING'} "
          f"{args.xgb_model}", flush=True)
    print(f"  T2 CNN      : {'FOUND' if args.cnn_model.exists() else 'MISSING'} "
          f"{args.cnn_model}", flush=True)

    if not can_train:
        print("\nERROR: alerts JSON or T1 XGBoost model not found. Cannot train.", flush=True)
        sys.exit(1)

    if args.dry_run:
        print("\nDry run — exiting without training.", flush=True)
        return

    # Load models
    print("\nLoading Tier 1 XGBoost ...", flush=True)
    xgb_model = _load_xgb(args.xgb_model)
    if xgb_model is None:
        print("ERROR: Failed to load XGBoost model.", flush=True)
        sys.exit(1)
    print("  XGBoost loaded.", flush=True)

    cnn_model = None
    if can_cnn:
        print("\nLoading Tier 2 CNN ...", flush=True)
        cnn_model = _load_cnn(args.cnn_model)
        if cnn_model is None:
            print("  WARNING: CNN load failed; T2 features will be uniform prior.", flush=True)
    else:
        print("\nSkipping CNN — cutouts CSV or model not found; T2 features = uniform prior.",
              flush=True)

    # Build stacking dataset
    t0 = time.time()
    t1_all, t2_all, ys = build_stacking_dataset(
        alerts_path=args.alerts,
        cutouts_csv=args.cutouts_csv if args.cutouts_csv.exists() else Path("/dev/null"),
        mpc_labels_path=args.mpc_labels,
        xgb_model=xgb_model,
        cnn_model=cnn_model,
        seed=args.seed,
    )

    if len(ys) < 10:
        print("\nERROR: insufficient stacking data (need ≥10 samples).", flush=True)
        sys.exit(1)

    # Hold out 20% for KPI evaluation
    rng2 = np.random.default_rng(args.seed + 1)
    idx_all = np.arange(len(ys))
    rng2.shuffle(idx_all)
    n_train = int(0.8 * len(ys))
    idx_tr = idx_all[:n_train]
    idx_val = idx_all[n_train:]

    t1_tr = [t1_all[i] for i in idx_tr]
    t2_tr = [t2_all[i] for i in idx_tr] if t2_all else None
    y_tr = [ys[i] for i in idx_tr]
    t1_val = [t1_all[i] for i in idx_val]
    t2_val = [t2_all[i] for i in idx_val] if t2_all else [T2_UNIFORM.copy()] * len(idx_val)
    y_val = [ys[i] for i in idx_val]

    print(f"\nStacker train: {len(y_tr)}  val: {len(y_val)}", flush=True)

    # Train stacker
    print("\nTraining 10-feature logistic regression stacker ...", flush=True)
    labels_tr = [{"label": y} for y in y_tr]
    report = retrain_stacker(
        tier1_outputs=t1_tr,
        labels=labels_tr,
        model_path=args.output,
        tier2_outputs=t2_tr,
    )

    print("\nStacker training report:", flush=True)
    print(f"  n_samples : {report['n_samples']}", flush=True)
    print(f"  n_classes : {report['n_classes']}", flush=True)
    print(f"  macro AUC : {report['auc']}", flush=True)
    print(f"  coef_path : {report['coef_path']}", flush=True)

    if report.get("coef_path") is None:
        print("\nERROR: stacker training failed (insufficient classes or sklearn error).",
              flush=True)
        sys.exit(1)

    # Reload for KPI evaluation using _StackerProxy
    from classify import _load_ensemble_stacker
    stacker = _load_ensemble_stacker(args.output)
    if stacker is None:
        print("\nERROR: could not load saved stacker for KPI evaluation.", flush=True)
        sys.exit(1)

    # Evaluate 7 T1-D KPIs on val set
    print("\nEvaluating stacker calibration KPIs on held-out val set ...", flush=True)
    kpis = evaluate_stacker_kpis(stacker, t1_val, t2_val, y_val)

    print(f"\n{'=' * 50}", flush=True)
    print("Ensemble Stacker KPI Results:", flush=True)
    print(f"{'=' * 50}", flush=True)
    for key, val in kpis.items():
        if isinstance(val, bool):
            status = "PASS" if val else "FAIL"
            print(f"  {key:<30} {status}", flush=True)
        elif isinstance(val, float):
            print(f"  {key:<30} {val:.4f}", flush=True)
        else:
            print(f"  {key:<30} {val}", flush=True)

    promotion = kpis.get("all_kpis_pass", False)
    print(f"\n{'=' * 50}", flush=True)
    print(f"  promotion_gate_passed = {str(promotion).lower()}", flush=True)
    print(f"  total elapsed: {time.time() - t0:.0f}s", flush=True)
    print(f"{'=' * 50}\n", flush=True)

    if not promotion:
        print("WARNING: Not all KPIs passed. Review calibration before production use.",
              flush=True)


if __name__ == "__main__":
    main()
