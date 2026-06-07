#!/usr/bin/env python
"""Train Tier 1 XGBoost classifier on ZTF labeled alerts + MPC catalog labels.

Reads:
  data/ztf_labeled_alerts.json  — ZTF Avro alerts (label 0=real, 3=bogus)
  data/training_labels.csv      — MPC NEO/MBA catalog labels (optional)

Builds a 10-feature tabular matrix matching classify._features_to_array:
  [real_bogus_score, motion_consistency_score, arc_coverage_score,
   nights_observed_score, brightness_score, color_score,
   lightcurve_variability_score, streak_score, psf_quality_score,
   known_object_score]

5-class label mapping (matches classify._tier1_predict output order):
  0 = neo_candidate      (ZTF real alerts + MPC NEO catalog)
  1 = known_object       (synthesized — no ZTF cross-match available yet)
  2 = main_belt_asteroid (MPC MBA catalog)
  3 = stellar_artifact   (ZTF bogus alerts)
  4 = other_solar_system (synthesized — no labeled catalog available yet)

Classes 1 and 4 are populated with small synthetic batches so the saved model
preserves the 5-class interface expected by classify._tier1_predict.  They
will be replaced with real data once ZTF-matched MPC observations are available.

Saves: models/tier1_xgb.json — auto-loaded by classify._load_xgb_model.

IMPORTANT: Run from repo root on your Mac, not from the coding agent server.
    caffeinate -i python Skills/train_tier1_xgboost.py
    python Skills/train_tier1_xgboost.py --dry-run   # no training; show dataset stats
    python Skills/train_tier1_xgboost.py --n-estimators 200 --max-depth 5

Output: models/tier1_xgb.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Ensure src/ is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ---------------------------------------------------------------------------
# Feature / label constants matching classify.py
# ---------------------------------------------------------------------------

# Column order must match classify._features_to_array exactly
FEATURE_COLS = [
    "real_bogus_score",
    "motion_consistency_score",
    "arc_coverage_score",
    "nights_observed_score",
    "brightness_score",
    "color_score",
    "lightcurve_variability_score",
    "streak_score",
    "psf_quality_score",
    "known_object_score",
]

# 5-class label map matching classify._tier1_predict output order
LABEL_NAMES = {
    0: "neo_candidate",
    1: "known_object",
    2: "main_belt_asteroid",
    3: "stellar_artifact",
    4: "other_solar_system",
}

# ZTF label encoding in ztf_labeled_alerts.json
ZTF_REAL = 0   # rb >= 0.65 — real astrophysical source
ZTF_BOGUS = 3  # rb <  0.35 — instrumental artifact


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_ztf_alerts(json_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load ZTF labeled alert JSON and extract tabular feature matrix.

    Features available per alert: rb (→ real_bogus_score) and drb (→ psf_quality_score).
    All other features default to 0.0 — single alerts have no tracklet motion data.

    Returns (X, y) with shape (n_alerts, 10) and (n_alerts,).
    """
    with json_path.open() as f:
        alerts = json.load(f)

    rows: list[list[float]] = []
    labels: list[int] = []

    for entry in alerts:
        raw_label = int(entry.get("label", -1))
        # Only use definitive real/bogus labels; skip ambiguous
        if raw_label not in (ZTF_REAL, ZTF_BOGUS):
            continue

        rb = float(entry.get("rb", 0.5))
        drb = float(entry.get("drb", -1.0))
        # Use drb as psf_quality_score when it's valid [0, 1]
        psf_quality = float(drb) if 0.0 <= drb <= 1.0 else rb

        # Build feature vector — only rb/drb are real; rest are 0.0 (missing)
        feat = [
            rb,     # real_bogus_score
            0.0,    # motion_consistency_score — no tracklet available
            0.0,    # arc_coverage_score
            0.0,    # nights_observed_score
            0.0,    # brightness_score
            0.0,    # color_score
            0.0,    # lightcurve_variability_score
            0.0,    # streak_score
            psf_quality,  # psf_quality_score (drb if valid, else rb)
            0.0,    # known_object_score
        ]
        rows.append(feat)
        # ZTF label=0 (real) → pipeline class 0 (neo_candidate proxy for "real signal")
        # ZTF label=3 (bogus) → pipeline class 3 (stellar_artifact)
        labels.append(0 if raw_label == ZTF_REAL else 3)

    X = np.array(rows, dtype=np.float32)
    y = np.array(labels, dtype=np.int32)
    return X, y


def load_mpc_labels(csv_path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Load MPC NEO/MBA catalog labels and synthesize feature rows.

    MPC labels have designation + neo_class but no ZTF photometric features.
    We assign representative feature vectors:
      - neo_candidate:      rb=0.90, psf=0.90, known_object=0.0
      - main_belt_asteroid: rb=0.80, psf=0.80, known_object=0.5

    Returns None if the file does not exist.
    """
    if not csv_path.exists():
        return None

    import csv

    rows: list[list[float]] = []
    labels: list[int] = []

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            neo_class = row.get("neo_class", "").strip()
            if neo_class == "neo_candidate":
                # Confirmed NEO — real signal, no artifact
                feat = [0.90, 0.0, 0.8, 0.5, 0.0, 0.0, 0.0, 0.0, 0.90, 0.0]
                labels.append(0)
            elif neo_class == "main_belt_asteroid":
                # MBA — real signal but not a NEO; partial known-object score
                feat = [0.80, 0.0, 0.7, 0.4, 0.0, 0.0, 0.0, 0.0, 0.80, 0.5]
                labels.append(2)
            else:
                # Skip unknown neo_class values
                continue
            rows.append(feat)

    if not rows:
        return None

    X = np.array(rows, dtype=np.float32)
    y = np.array(labels, dtype=np.int32)
    return X, y


def _synthesize_minor_classes(
    rng: np.random.Generator,
    n_each: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate small synthetic batches for classes 1 and 4.

    These preserve the 5-class XGBoost interface until real cross-matched ZTF
    data is available for known objects (class 1) and other solar system bodies
    (class 4).  Each synthetic row has Gaussian noise around a class centroid.

    Class 1 (known_object):       rb≈0.85, known_object_score≈0.9
    Class 4 (other_solar_system): rb≈0.70, streak≈0.4 (comets/TNOs may trail)
    """
    rows: list[list[float]] = []
    labels: list[int] = []

    # Known object: high rb, high known_object_score
    for _ in range(n_each):
        feat = [
            float(np.clip(rng.normal(0.85, 0.05), 0.0, 1.0)),  # real_bogus
            float(np.clip(rng.normal(0.3, 0.1), 0.0, 1.0)),    # motion_consistency
            float(np.clip(rng.normal(0.5, 0.15), 0.0, 1.0)),   # arc_coverage
            float(np.clip(rng.normal(0.5, 0.15), 0.0, 1.0)),   # nights_observed
            0.0, 0.0, 0.0,                                       # brightness, color, lc_var
            0.0,                                                  # streak
            float(np.clip(rng.normal(0.85, 0.05), 0.0, 1.0)),  # psf_quality
            float(np.clip(rng.normal(0.90, 0.05), 0.0, 1.0)),  # known_object_score
        ]
        rows.append(feat)
        labels.append(1)

    # Other solar system (comet/TNO): moderate rb, possible streak
    for _ in range(n_each):
        feat = [
            float(np.clip(rng.normal(0.70, 0.10), 0.0, 1.0)),  # real_bogus
            float(np.clip(rng.normal(0.2, 0.1), 0.0, 1.0)),    # motion_consistency
            float(np.clip(rng.normal(0.4, 0.15), 0.0, 1.0)),   # arc_coverage
            float(np.clip(rng.normal(0.3, 0.1), 0.0, 1.0)),    # nights_observed
            0.0, 0.0, 0.0,
            float(np.clip(rng.normal(0.40, 0.15), 0.0, 1.0)),  # streak
            float(np.clip(rng.normal(0.70, 0.10), 0.0, 1.0)),  # psf_quality
            0.0,
        ]
        rows.append(feat)
        labels.append(4)

    X = np.array(rows, dtype=np.float32)
    y = np.array(labels, dtype=np.int32)
    return X, y


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    n_estimators: int,
    max_depth: int,
    out_path: Path,
) -> dict:
    """Fit XGBoost multi-class classifier and report val metrics.

    Uses per-sample class weights (inverse-frequency) to handle imbalanced
    class counts (typical ZTF data is ~85% real, ~15% bogus).

    Returns a report dict with val_accuracy, macro_auc, feature_importances,
    n_samples_train, n_samples_val, and model_path.
    """
    import xgboost as xgb  # type: ignore[import]
    from sklearn.metrics import (  # type: ignore[import]
        accuracy_score,
        classification_report,
        roc_auc_score,
    )
    from sklearn.preprocessing import label_binarize  # type: ignore[import]
    from sklearn.utils.class_weight import compute_sample_weight  # type: ignore[import]

    # Inverse-frequency sample weights computed from training set only
    sample_weights = compute_sample_weight(class_weight="balanced", y=y_tr)
    n_classes = len(np.unique(np.concatenate([y_tr, y_val])))

    clf = xgb.XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_tr, y_tr, sample_weight=sample_weights)

    # Val metrics
    y_pred = clf.predict(X_val)
    val_acc = float(accuracy_score(y_val, y_pred))

    # Macro AUC (OvR) — requires at least 2 classes in val set
    proba_val = clf.predict_proba(X_val)
    classes = clf.classes_
    auc: float | None = None
    if n_classes >= 2:
        try:
            y_val_bin = label_binarize(y_val, classes=list(classes))
            if y_val_bin.shape[1] == len(classes):
                auc = float(
                    roc_auc_score(y_val_bin, proba_val, multi_class="ovr", average="macro")
                )
        except Exception:
            pass

    # Feature importances (gain-normalized, named)
    raw_imp = clf.feature_importances_
    importances = {col: float(raw_imp[i]) for i, col in enumerate(FEATURE_COLS)}

    # Save model
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clf.save_model(str(out_path))

    print("\n=== Validation Report ===")
    print(classification_report(
        y_val, y_pred,
        labels=list(classes),
        target_names=[LABEL_NAMES.get(int(c), str(c)) for c in classes],
        zero_division=0,
    ))
    print(f"Val accuracy : {val_acc:.4f}")
    if auc is not None:
        print(f"Macro AUC    : {auc:.4f}")
    print("\nTop feature importances (gain):")
    for name, imp in sorted(importances.items(), key=lambda x: -x[1]):
        bar = "#" * int(imp * 40)
        print(f"  {name:<35s} {imp:.4f}  {bar}")

    return {
        "n_samples_train": int(len(y_tr)),
        "n_samples_val": int(len(y_val)),
        "n_classes": n_classes,
        "val_accuracy": val_acc,
        "macro_auc": auc,
        "feature_importances": importances,
        "model_path": str(out_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train Tier 1 XGBoost on ZTF alerts + MPC labels (run from Mac)"
    )
    parser.add_argument(
        "--alerts", type=Path, default=Path("data/ztf_labeled_alerts.json"),
        help="ZTF labeled alerts JSON (default: data/ztf_labeled_alerts.json)",
    )
    parser.add_argument(
        "--mpc-labels", type=Path, default=Path("data/training_labels.csv"),
        help="MPC NEO/MBA training labels CSV (default: data/training_labels.csv)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("models/tier1_xgb.json"),
        help="Output model path (default: models/tier1_xgb.json)",
    )
    parser.add_argument(
        "--n-estimators", type=int, default=300,
        help="XGBoost n_estimators (default: 300)",
    )
    parser.add_argument(
        "--max-depth", type=int, default=5,
        help="XGBoost max_depth (default: 5)",
    )
    parser.add_argument(
        "--val-frac", type=float, default=0.2,
        help="Fraction of data held out for validation (default: 0.2)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--synthetic-minor", type=int, default=50,
        help=(
            "Synthetic examples per minor class (1=known_object, 4=other_solar_system). "
            "Set 0 to disable and train with fewer classes."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print dataset statistics without training",
    )
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    # --- Load ZTF alerts ---
    if not args.alerts.exists():
        print(f"ERROR: {args.alerts} not found.")
        print("Run: caffeinate -i python Skills/download_ztf_training_alerts.py")
        sys.exit(1)

    print(f"Loading ZTF alerts from {args.alerts} ...")
    X_ztf, y_ztf = load_ztf_alerts(args.alerts)
    n_real = int((y_ztf == 0).sum())
    n_bogus = int((y_ztf == 3).sum())
    print(f"  ZTF: {len(y_ztf)} alerts  (real={n_real}  bogus={n_bogus})")

    # --- Load MPC labels ---
    mpc_result = load_mpc_labels(args.mpc_labels)
    if mpc_result is not None:
        X_mpc, y_mpc = mpc_result
        n_neo = int((y_mpc == 0).sum())
        n_mba = int((y_mpc == 2).sum())
        print(f"  MPC: {len(y_mpc)} labels  (neo={n_neo}  mba={n_mba})")
    else:
        X_mpc = np.empty((0, len(FEATURE_COLS)), dtype=np.float32)
        y_mpc = np.empty(0, dtype=np.int32)
        print("  MPC labels not found — skipping MPC augmentation")

    # --- Synthesize minor classes ---
    if args.synthetic_minor > 0:
        X_syn, y_syn = _synthesize_minor_classes(rng, n_each=args.synthetic_minor)
        n_syn = args.synthetic_minor
        print(f"  Synthetic: {len(y_syn)} examples  (known_object={n_syn}  other_ss={n_syn})")
    else:
        X_syn = np.empty((0, len(FEATURE_COLS)), dtype=np.float32)
        y_syn = np.empty(0, dtype=np.int32)

    # --- Combine ---
    X_all = np.vstack([X_ztf, X_mpc, X_syn])
    y_all = np.concatenate([y_ztf, y_mpc, y_syn])

    print(f"\nTotal dataset: {len(y_all)} examples")
    for cls_id, cls_name in LABEL_NAMES.items():
        cnt = int((y_all == cls_id).sum())
        if cnt > 0:
            print(f"  Class {cls_id} ({cls_name}): {cnt}")

    if args.dry_run:
        print("\nDry run complete — no model trained.")
        return

    # --- Train / val split (stratified) ---
    from sklearn.model_selection import train_test_split  # type: ignore[import]

    X_tr, X_val, y_tr, y_val = train_test_split(
        X_all, y_all,
        test_size=args.val_frac,
        random_state=args.seed,
        stratify=y_all,
    )
    print(f"\nTrain: {len(y_tr)}  |  Val: {len(y_val)}")

    # --- Train ---
    print("\nTraining XGBoost ...")
    report = train(
        X_tr, y_tr, X_val, y_val,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        out_path=args.output,
    )

    print(f"\nModel saved → {report['model_path']}")
    print("\nNext step:")
    print("  PYTHONPATH=src python Skills/evaluate_calibration.py \\")
    print(f"      --model {report['model_path']}")


if __name__ == "__main__":
    main()
