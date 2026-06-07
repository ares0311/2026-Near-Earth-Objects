#!/usr/bin/env python
"""Evaluate calibration quality for Tier 1 XGBoost and Tier 2 CNN on real data.

Reproduces the same train/val splits used during model training, runs each
model on the held-out val set, and reports Brier score and ECE with
PASS/FAIL against T1-D gate thresholds (Brier < 0.10, ECE < 0.05).

Falls back to synthetic-data Platt/isotonic calibrator evaluation when
alert JSON or cutout CSV are not present — safe for CI.

IMPORTANT: Run from repo root on your Mac, not from the coding agent server.
    python Skills/evaluate_calibration.py
    python Skills/evaluate_calibration.py \\
        --alerts data/ztf_labeled_alerts.json \\
        --xgb-model models/tier1_xgb.json \\
        --cutouts-csv data/cutouts/index.csv \\
        --cnn-model models/tier2_cnn.pt

Thresholds (T1-D gate):
    Brier score < 0.10
    ECE         < 0.05
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    brier_score,
    expected_calibration_error,
)

# ---------------------------------------------------------------------------
# Gate thresholds (T1-D)
# ---------------------------------------------------------------------------

BRIER_THRESHOLD = 0.10
ECE_THRESHOLD = 0.05

# Label constants matching train_tier1_xgboost.py and train_tier2_cnn.py
ZTF_REAL = 0   # rb >= 0.65
ZTF_BOGUS = 3  # rb <  0.35

# Feature columns matching classify._features_to_array
FEATURE_COLS = [
    "real_bogus_score", "motion_consistency_score", "arc_coverage_score",
    "nights_observed_score", "brightness_score", "color_score",
    "lightcurve_variability_score", "streak_score", "psf_quality_score",
    "known_object_score",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(val: float, threshold: float, lower_better: bool = True) -> str:
    """Format a metric value with PASS/FAIL annotation."""
    passed = val < threshold if lower_better else val >= threshold
    mark = "PASS" if passed else "FAIL"
    return f"{val:.4f}  [{mark} < {threshold}]"


def _print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def _print_row(name: str, brier: float, ece: float) -> None:
    b_str = _fmt(brier, BRIER_THRESHOLD)
    e_str = _fmt(ece, ECE_THRESHOLD)
    print(f"  {name:<20s}  Brier={b_str}   ECE={e_str}")


# ---------------------------------------------------------------------------
# XGBoost evaluation
# ---------------------------------------------------------------------------

def _load_ztf_features(json_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load ZTF alert JSON and return (X, y_binary).

    Features: [rb, 0, 0, 0, 0, 0, 0, 0, drb, 0] (10-dim, matching training).
    Binary label: 1=real (ZTF label=0), 0=bogus (ZTF label=3).
    """
    with json_path.open() as f:
        alerts = json.load(f)
    rows = []
    labels = []
    for entry in alerts:
        raw = int(entry.get("label", -1))
        if raw not in (ZTF_REAL, ZTF_BOGUS):
            continue
        rb = float(entry.get("rb", 0.5))
        drb = float(entry.get("drb", -1.0))
        psf = drb if 0.0 <= drb <= 1.0 else rb
        feat = [rb, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, psf, 0.0]
        rows.append(feat)
        labels.append(1 if raw == ZTF_REAL else 0)  # binary: 1=real, 0=bogus
    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int32)


def _load_mpc_features(csv_path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Load MPC labels and synthesize feature rows (same as training)."""
    import csv as _csv
    if not csv_path.exists():
        return None
    rows = []
    labels = []
    with csv_path.open(newline="") as f:
        for row in _csv.DictReader(f):
            neo_class = row.get("neo_class", "").strip()
            if neo_class == "neo_candidate":
                rows.append([0.90, 0.0, 0.8, 0.5, 0.0, 0.0, 0.0, 0.0, 0.90, 0.0])
                labels.append(1)  # real
            elif neo_class == "main_belt_asteroid":
                rows.append([0.80, 0.0, 0.7, 0.4, 0.0, 0.0, 0.0, 0.0, 0.80, 0.5])
                labels.append(1)  # real (not bogus)
    if not rows:
        return None
    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int32)


def _synthesize_minor(rng: np.random.Generator, n: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Reproduce synthetic minor-class rows from training (same centroids)."""
    rows = []
    labels = []
    # Class 1 known_object: real
    for _ in range(n):
        rows.append([
            float(np.clip(rng.normal(0.85, 0.05), 0, 1)),
            float(np.clip(rng.normal(0.3, 0.1), 0, 1)),
            float(np.clip(rng.normal(0.5, 0.15), 0, 1)),
            float(np.clip(rng.normal(0.5, 0.15), 0, 1)),
            0.0, 0.0, 0.0, 0.0,
            float(np.clip(rng.normal(0.85, 0.05), 0, 1)),
            float(np.clip(rng.normal(0.90, 0.05), 0, 1)),
        ])
        labels.append(1)
    # Class 4 other_solar_system: real
    for _ in range(n):
        rows.append([
            float(np.clip(rng.normal(0.70, 0.10), 0, 1)),
            float(np.clip(rng.normal(0.2, 0.1), 0, 1)),
            float(np.clip(rng.normal(0.4, 0.15), 0, 1)),
            float(np.clip(rng.normal(0.3, 0.1), 0, 1)),
            0.0, 0.0, 0.0,
            float(np.clip(rng.normal(0.40, 0.15), 0, 1)),
            float(np.clip(rng.normal(0.70, 0.10), 0, 1)),
            0.0,
        ])
        labels.append(1)
    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int32)


def evaluate_xgboost(
    xgb_model_path: Path,
    alerts_path: Path,
    mpc_path: Path,
    seed: int = 42,
    val_frac: float = 0.2,
    n_synthetic: int = 50,
) -> None:
    """Evaluate Tier 1 XGBoost on the held-out val set."""
    import xgboost as xgb  # type: ignore[import]
    from sklearn.model_selection import train_test_split  # type: ignore[import]

    _print_header("Tier 1 XGBoost — binary real/bogus calibration")

    # Reproduce full training dataset (same order as train_tier1_xgboost.py)
    X_ztf, y_ztf = _load_ztf_features(alerts_path)
    print(f"  ZTF alerts: {len(y_ztf)}  (real={y_ztf.sum()}  bogus={(y_ztf == 0).sum()})")

    mpc_result = _load_mpc_features(mpc_path)
    if mpc_result is not None:
        X_mpc, y_mpc = mpc_result
        print(f"  MPC labels: {len(y_mpc)}")
    else:
        X_mpc = np.empty((0, len(FEATURE_COLS)), dtype=np.float32)
        y_mpc = np.empty(0, dtype=np.int32)

    rng = np.random.default_rng(seed)
    X_syn, y_syn = _synthesize_minor(rng, n=n_synthetic)
    print(f"  Synthetic:  {len(y_syn)}")

    X_all = np.vstack([X_ztf, X_mpc, X_syn])
    y_all = np.concatenate([y_ztf, y_mpc, y_syn])
    print(f"  Total: {len(y_all)}")

    # Reproduce the same stratified val split
    _, X_val, _, y_val = train_test_split(
        X_all, y_all, test_size=val_frac, random_state=seed, stratify=y_all,
    )
    print(f"  Val set: {len(y_val)}  (real={y_val.sum()}  bogus={(y_val == 0).sum()})")

    # Load model and predict
    clf = xgb.XGBClassifier()
    clf.load_model(str(xgb_model_path))
    proba = clf.predict_proba(X_val)  # shape (n, n_classes)

    # Find class-3 (stellar_artifact) index in model.classes_
    classes = list(clf.classes_)
    if 3 in classes:
        art_idx = classes.index(3)
        # P(real) = 1 - P(stellar_artifact)
        p_real = 1.0 - proba[:, art_idx]
    else:
        # Fallback: sum non-bogus columns
        p_real = proba.sum(axis=1) - proba[:, -1]

    y_binary = y_val.astype(float)  # 1=real, 0=bogus

    bs = float(brier_score(p_real, y_binary))
    ece = float(expected_calibration_error(p_real, y_binary))

    print()
    _print_row("Raw XGBoost", bs, ece)

    # Platt and isotonic on the XGBoost raw scores
    # Use a 50/50 split of the val set: fit on first half, evaluate on second half
    n_cal = len(p_real) // 2
    platt = PlattCalibrator().fit(p_real[:n_cal], y_binary[:n_cal])
    iso = IsotonicCalibrator().fit(p_real[:n_cal], y_binary[:n_cal])

    p_eval = p_real[n_cal:]
    y_eval = y_binary[n_cal:]
    bs_p = float(brier_score(platt.predict(p_eval), y_eval))
    ece_p = float(expected_calibration_error(platt.predict(p_eval), y_eval))
    bs_i = float(brier_score(iso.predict(p_eval), y_eval))
    ece_i = float(expected_calibration_error(iso.predict(p_eval), y_eval))

    _print_row("+ Platt", bs_p, ece_p)
    _print_row("+ Isotonic", bs_i, ece_i)

    best_brier = min(bs, bs_p, bs_i)
    best_ece = min(ece, ece_p, ece_i)
    gate = best_brier < BRIER_THRESHOLD and best_ece < ECE_THRESHOLD
    print(f"\n  T1-D gate: {'PASS' if gate else 'FAIL'}"
          f"  (best Brier={best_brier:.4f}, best ECE={best_ece:.4f})")


# ---------------------------------------------------------------------------
# CNN evaluation
# ---------------------------------------------------------------------------

def evaluate_cnn(
    cnn_model_path: Path,
    cutouts_csv: Path,
    seed: int = 42,
    val_frac: float = 0.2,
    batch_size: int = 64,
) -> None:
    """Evaluate Tier 2 CNN on the held-out val set."""
    import csv as _csv

    import torch
    from torch.utils.data import Dataset, random_split

    from classify import _build_cnn_model  # type: ignore[import]

    _print_header("Tier 2 CNN — binary real/bogus calibration")

    # Load CSV rows
    with cutouts_csv.open(newline="") as f:
        rows = list(_csv.DictReader(f))
    print(f"  Total cutouts: {len(rows)}")

    # Reproduce the same random_split used in training
    # (train_tier2_cnn.py uses torch.Generator().manual_seed(42))
    n_val = max(1, int(val_frac * len(rows)))
    n_train = len(rows) - n_val

    class _IdxDS(Dataset):
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, idx: int):  # noqa: ANN204
            return idx, int(self.rows[idx]["label"])

    full_ds = _IdxDS(rows)
    train_ds, val_ds = random_split(
        full_ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(seed),
    )

    val_indices = list(val_ds.indices)
    val_rows = [rows[i] for i in val_indices]
    y_val_raw = np.array([int(r["label"]) for r in val_rows])
    y_binary = (y_val_raw == 0).astype(float)  # 1=real, 0=bogus
    n_real = int(y_binary.sum())
    n_bogus = int((y_binary == 0).sum())
    print(f"  Val set: {len(val_rows)}  (real={n_real}  bogus={n_bogus})")

    # Load model
    model = _build_cnn_model()
    if model is None:
        print("  ERROR: torch not available — cannot evaluate CNN.")
        return
    state = torch.load(str(cnn_model_path), map_location="cpu", weights_only=False)
    model.load_state_dict(state)
    model.eval()

    # Run inference on val set in batches
    def _load_npz(path: str) -> tuple:
        import numpy as _np
        data = _np.load(path)
        def _t(k: str):
            return torch.from_numpy(
                _np.nan_to_num(data[k], nan=0.0, posinf=0.0, neginf=0.0)
                .astype(_np.float32)
            ).unsqueeze(0)
        return _t("science"), _t("reference"), _t("difference")

    all_proba: list[float] = []
    with torch.no_grad():
        for i in range(0, len(val_rows), batch_size):
            batch_rows = val_rows[i : i + batch_size]
            sci_b, ref_b, diff_b = [], [], []
            for r in batch_rows:
                s, re, d = _load_npz(r["cutout_path"])
                sci_b.append(s)
                ref_b.append(re)
                diff_b.append(d)
            sci_t = torch.stack(sci_b)
            ref_t = torch.stack(ref_b)
            diff_t = torch.stack(diff_b)
            out = model(sci_t, ref_t, diff_t)  # shape (B, 5) softmax
            # P(real) = 1 - P(stellar_artifact=class3)
            p = 1.0 - out[:, 3].cpu().numpy()
            all_proba.extend(p.tolist())

    p_real = np.array(all_proba, dtype=np.float64)

    bs = float(brier_score(p_real, y_binary))
    ece = float(expected_calibration_error(p_real, y_binary))

    print()
    _print_row("Raw CNN", bs, ece)

    # Platt and isotonic on the CNN raw scores
    # Fit on training val predictions — use a 50/50 split of the val set for calibration
    n_cal = len(p_real) // 2
    platt = PlattCalibrator().fit(p_real[:n_cal], y_binary[:n_cal])
    iso = IsotonicCalibrator().fit(p_real[:n_cal], y_binary[:n_cal])

    p_eval = p_real[n_cal:]
    y_eval = y_binary[n_cal:]
    bs_p = float(brier_score(platt.predict(p_eval), y_eval))
    ece_p = float(expected_calibration_error(platt.predict(p_eval), y_eval))
    bs_i = float(brier_score(iso.predict(p_eval), y_eval))
    ece_i = float(expected_calibration_error(iso.predict(p_eval), y_eval))

    _print_row("+ Platt", bs_p, ece_p)
    _print_row("+ Isotonic", bs_i, ece_i)

    best_brier = min(bs, bs_p, bs_i)
    best_ece = min(ece, ece_p, ece_i)
    gate = best_brier < BRIER_THRESHOLD and best_ece < ECE_THRESHOLD
    print(f"\n  T1-D gate: {'PASS' if gate else 'FAIL'}"
          f"  (best Brier={best_brier:.4f}, best ECE={best_ece:.4f})")


# ---------------------------------------------------------------------------
# Synthetic fallback (for CI — no real data required)
# ---------------------------------------------------------------------------

def _synthetic_eval() -> None:
    """Fallback: evaluate Platt/isotonic calibrators on synthetic scores."""
    rng = np.random.default_rng(42)
    scores = rng.beta(1.5, 5.0, 500)
    labels = (rng.uniform(size=500) < scores).astype(float)
    split = len(scores) // 2
    tr_s, tr_l = scores[:split], labels[:split]
    te_s, te_l = scores[split:], labels[split:]

    platt = PlattCalibrator().fit(tr_s, tr_l)
    iso = IsotonicCalibrator().fit(tr_s, tr_l)

    print("Calibration evaluation (synthetic data, n=500)")
    print("-" * 50)
    print(f"{'Method':<12} {'Brier':>8} {'ECE':>8}")
    raw_b = brier_score(te_s, te_l)
    raw_e = expected_calibration_error(te_s, te_l)
    pl_b = brier_score(platt.predict(te_s), te_l)
    pl_e = expected_calibration_error(platt.predict(te_s), te_l)
    is_b = brier_score(iso.predict(te_s), te_l)
    is_e = expected_calibration_error(iso.predict(te_s), te_l)
    print(f"{'Raw':<12} {raw_b:>8.4f} {raw_e:>8.4f}")
    print(f"{'Platt':<12} {pl_b:>8.4f} {pl_e:>8.4f}")
    print(f"{'Isotonic':<12} {is_b:>8.4f} {is_e:>8.4f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Tier 1 XGBoost and Tier 2 CNN calibration on real data"
    )
    parser.add_argument(
        "--alerts", type=Path, default=Path("data/ztf_labeled_alerts.json"),
        help="ZTF labeled alerts JSON (default: data/ztf_labeled_alerts.json)",
    )
    parser.add_argument(
        "--mpc-labels", type=Path, default=Path("data/training_labels.csv"),
        help="MPC NEO/MBA labels CSV (default: data/training_labels.csv)",
    )
    parser.add_argument(
        "--xgb-model", type=Path, default=Path("models/tier1_xgb.json"),
        help="Tier 1 XGBoost model (default: models/tier1_xgb.json)",
    )
    parser.add_argument(
        "--cutouts-csv", type=Path, default=Path("data/cutouts/index.csv"),
        help="Cutout index CSV from build_cutout_dataset.py (default: data/cutouts/index.csv)",
    )
    parser.add_argument(
        "--cnn-model", type=Path, default=Path("models/tier2_cnn.pt"),
        help="Tier 2 CNN model (default: models/tier2_cnn.pt)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (must match training seed; default: 42)",
    )
    args = parser.parse_args()

    # Determine which real-model evaluations are possible
    can_xgb = args.alerts.exists() and args.xgb_model.exists()
    can_cnn = args.cutouts_csv.exists() and args.cnn_model.exists()

    if not can_xgb and not can_cnn:
        # Neither real dataset available — run synthetic fallback (CI safe)
        _synthetic_eval()
        return

    print(f"\nT1-D calibration gate thresholds: Brier < {BRIER_THRESHOLD}, ECE < {ECE_THRESHOLD}")

    if can_xgb:
        evaluate_xgboost(
            xgb_model_path=args.xgb_model,
            alerts_path=args.alerts,
            mpc_path=args.mpc_labels,
            seed=args.seed,
        )
    else:
        print("\n[XGBoost] Skipped — alerts or model not found.")

    if can_cnn:
        evaluate_cnn(
            cnn_model_path=args.cnn_model,
            cutouts_csv=args.cutouts_csv,
            seed=args.seed,
        )
    else:
        print("\n[CNN] Skipped — cutouts CSV or model not found.")

    print()


if __name__ == "__main__":
    main()
