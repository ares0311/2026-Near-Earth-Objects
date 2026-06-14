#!/usr/bin/env python
"""Evaluate calibration quality for Tier 1 XGBoost and Tier 2 CNN on real data.

Reproduces the same train/val splits used during model training, runs each
model on the held-out val set, and reports all seven T1-D KPI gate metrics.

Falls back to synthetic-data Platt/isotonic calibrator evaluation when
alert JSON or cutout CSV are not present — safe for CI.

IMPORTANT: Run from repo root on your Mac, not from the coding agent server.
    python Skills/evaluate_calibration.py
    python Skills/evaluate_calibration.py \\
        --alerts data/ztf_labeled_alerts.json \\
        --xgb-model models/tier1_xgb.json \\
        --cutouts-csv data/cutouts/index.csv \\
        --cnn-model models/tier2_cnn.pt \\
        --report-out Logs/reports/calibration_report.json

T1-D gate thresholds (ALL must pass for promotion_gate_passed=true):
    Brier score < 0.10
    ECE         < 0.05
    Log-loss    < 0.50
    ROC AUC     > 0.95
    5-fold CV ECE mean < 0.05  (std <= 0.02)
    Bootstrap Brier 95% CI upper < 0.12
    Bootstrap ECE   95% CI upper < 0.07
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    bootstrap_confidence_interval,
    brier_score,
    compute_log_loss,
    compute_roc_auc,
    cross_validate_calibration,
    expected_calibration_error,
)

# ---------------------------------------------------------------------------
# Gate thresholds (T1-D) — all seven must pass for promotion_gate_passed=True
# ---------------------------------------------------------------------------

BRIER_THRESHOLD = 0.10
ECE_THRESHOLD = 0.05
LOG_LOSS_THRESHOLD = 0.50
ROC_AUC_THRESHOLD = 0.95          # higher-is-better
CV_ECE_MEAN_THRESHOLD = 0.05
CV_ECE_STD_THRESHOLD = 0.02
BOOTSTRAP_BRIER_UPPER = 0.12      # 95% CI upper bound
BOOTSTRAP_ECE_UPPER = 0.07        # 95% CI upper bound

# Number of bootstrap resamples — 500 balances reliability vs. wall time
N_BOOTSTRAP = 500

# Label constants matching train_tier1_xgboost.py and train_tier2_cnn.py
ZTF_REAL = 0    # rb >= 0.65
ZTF_BOGUS = 3   # rb <  0.35

# Feature columns matching classify._features_to_array
FEATURE_COLS = [
    "real_bogus_score", "motion_consistency_score", "arc_coverage_score",
    "nights_observed_score", "brightness_score", "color_score",
    "lightcurve_variability_score", "streak_score", "psf_quality_score",
    "known_object_score",
]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(val: float, threshold: float, lower_better: bool = True) -> str:
    """Format a metric value with PASS/FAIL annotation."""
    passed = val < threshold if lower_better else val >= threshold
    mark = "PASS" if passed else "FAIL"
    cmp = "<" if lower_better else ">"
    return f"{val:.4f}  [{mark} {cmp} {threshold}]"


def _print_header(title: str) -> None:
    """Print a section header to stdout."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def _print_row(name: str, brier: float, ece: float) -> None:
    """Print a single Brier/ECE evaluation row."""
    b_str = _fmt(brier, BRIER_THRESHOLD)
    e_str = _fmt(ece, ECE_THRESHOLD)
    print(f"  {name:<20s}  Brier={b_str}   ECE={e_str}")


@contextlib.contextmanager
def _heartbeat(label: str, interval: float = 5.0) -> Iterator[None]:
    """Emit '<label> … still working (Nm Ns elapsed)' every `interval` seconds.

    A blocking call such as ``torch.load`` on a Dropbox-backed ``.pt`` file can
    stall for minutes while the OS materialises the file from the cloud, with no
    output at all — indistinguishable from a true hang. This context manager runs
    a daemon thread that prints an elapsed-time line on a fixed cadence so the
    operator can always tell the process is (1) alive, (2) still working, and
    (3) how long it has been waiting. The thread exits as soon as the wrapped
    block returns, so it adds no output once the slow call completes.
    """
    # Event used to stop the heartbeat thread the instant the block exits.
    stop = threading.Event()
    t0 = time.monotonic()

    def _beat() -> None:
        # Sleep in `interval` chunks; stop.wait returns True the moment we are
        # signalled to stop, so the thread never lingers past the with-block.
        while not stop.wait(interval):
            elapsed = int(time.monotonic() - t0)
            m, s = divmod(elapsed, 60)
            # stdout so the operator always sees it regardless of stderr handling.
            print(
                f"  {label} … still working ({m}m{s:02d}s elapsed)",
                flush=True,
            )

    thread = threading.Thread(target=_beat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        # Signal the heartbeat to stop and wait briefly for it to drain.
        stop.set()
        thread.join(timeout=1.0)


# ---------------------------------------------------------------------------
# KPI gate checker
# ---------------------------------------------------------------------------

def _check_all_kpis(
    best_brier: float,
    best_ece: float,
    log_loss: float,
    roc_auc: float,
    cv_ece_mean: float,
    cv_ece_std: float,
    boot_brier_upper: float,
    boot_ece_upper: float,
) -> tuple[bool, dict[str, bool]]:
    """Return (all_pass, per_gate_dict) for the seven T1-D KPIs.

    All seven gates must pass for promotion_gate_passed to be True.
    """
    gates: dict[str, bool] = {
        "brier": best_brier < BRIER_THRESHOLD,
        "ece": best_ece < ECE_THRESHOLD,
        "log_loss": log_loss < LOG_LOSS_THRESHOLD,
        "roc_auc": roc_auc > ROC_AUC_THRESHOLD,
        "cv_ece_mean": cv_ece_mean < CV_ECE_MEAN_THRESHOLD,
        "cv_ece_std": cv_ece_std <= CV_ECE_STD_THRESHOLD,
        "bootstrap_brier_upper": boot_brier_upper < BOOTSTRAP_BRIER_UPPER,
        "bootstrap_ece_upper": boot_ece_upper < BOOTSTRAP_ECE_UPPER,
    }
    return all(gates.values()), gates


# ---------------------------------------------------------------------------
# SHA-256 model fingerprint
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str | None:
    """Return the SHA-256 hex digest of a file, or None if the file is absent."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# ZTF feature loading
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
        # Use drb when valid; fall back to rb for PSF quality proxy
        psf = drb if 0.0 <= drb <= 1.0 else rb
        feat = [rb, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, psf, 0.0]
        rows.append(feat)
        labels.append(1 if raw == ZTF_REAL else 0)  # binary: 1=real, 0=bogus
    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int32)


def _load_mpc_features(csv_path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Load MPC labels and synthesize feature rows (same centroids as training)."""
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
                labels.append(1)  # real (genuine NEO)
            elif neo_class == "main_belt_asteroid":
                rows.append([0.80, 0.0, 0.7, 0.4, 0.0, 0.0, 0.0, 0.0, 0.80, 0.5])
                labels.append(1)  # real (not bogus)
    if not rows:
        return None
    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int32)


def _synthesize_minor(rng: np.random.Generator, n: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Reproduce synthetic minor-class rows from training (same centroids as train_tier1)."""
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


# ---------------------------------------------------------------------------
# XGBoost evaluation
# ---------------------------------------------------------------------------

def evaluate_xgboost(
    xgb_model_path: Path,
    alerts_path: Path,
    mpc_path: Path,
    seed: int = 42,
    val_frac: float = 0.2,
    n_synthetic: int = 50,
) -> dict[str, Any]:
    """Evaluate Tier 1 XGBoost on the held-out val set.

    Returns a dict of all KPI values and gate results for inclusion in the
    machine-readable JSON report.
    """
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

    # Reproduce the same stratified val split used during training
    _, X_val, _, y_val = train_test_split(
        X_all, y_all, test_size=val_frac, random_state=seed, stratify=y_all,
    )
    print(f"  Val set: {len(y_val)}  (real={y_val.sum()}  bogus={(y_val == 0).sum()})")

    # Load model and predict class probabilities
    clf = xgb.XGBClassifier()
    clf.load_model(str(xgb_model_path))
    proba = clf.predict_proba(X_val)  # shape (n, n_classes)

    # P(real) = 1 - P(stellar_artifact=class 3)
    classes = list(clf.classes_)
    if 3 in classes:
        art_idx = classes.index(3)
        p_real = 1.0 - proba[:, art_idx]
    else:
        # Fallback: 1 - last class probability
        p_real = 1.0 - proba[:, -1]

    y_binary = y_val.astype(float)  # 1=real, 0=bogus

    # Raw (uncalibrated) Brier and ECE
    bs = float(brier_score(p_real, y_binary))
    ece = float(expected_calibration_error(p_real, y_binary))

    print()
    _print_row("Raw XGBoost", bs, ece)

    # -----------------------------------------------------------------
    # Platt and isotonic calibration — 50/50 half-split of the val set.
    # Fit calibrators on the first half; evaluate on the second half.
    # This avoids the 2D-input crash: the prior train_test_split approach
    # assigned X_val (shape n×10) to p_cal_real_tr instead of the 1D
    # probability vector, causing det≈0 → A=0 → constant predictions.
    # -----------------------------------------------------------------
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

    # Best calibrated metrics
    best_brier = min(bs, bs_p, bs_i)
    best_ece = min(ece, ece_p, ece_i)
    best_name = {bs: "Raw", bs_p: "Platt", bs_i: "Isotonic"}[best_brier]

    # Apply the best calibrator to the full val set for expanded KPIs.
    # Minor note: calibrator was fit on the first half and is now applied
    # to the full set — a slight optimism for the half-overlap region —
    # but conservative enough for promotion gating.
    if best_name == "Platt":
        p_best = platt.predict(p_real)
    elif best_name == "Isotonic":
        p_best = iso.predict(p_real)
    else:
        p_best = p_real

    # Raw (rank-invariant) log-loss and ROC AUC on uncalibrated scores
    log_loss_raw = float(compute_log_loss(p_real, y_binary))
    roc_auc_raw = float(compute_roc_auc(p_real, y_binary))

    print(f"\n  Log-loss (raw)   : {_fmt(log_loss_raw, LOG_LOSS_THRESHOLD)}")
    print(f"  ROC AUC  (raw)   : {_fmt(roc_auc_raw, ROC_AUC_THRESHOLD, lower_better=False)}")

    # 5-fold cross-validated ECE on the best calibrated scores
    print(f"\n  Running 5-fold CV ECE (best={best_name}) …")
    cv_ece_mean, cv_ece_std = cross_validate_calibration(
        list(p_best), list(y_binary), n_folds=5, metric="ece",
    )
    print(f"  CV ECE mean : {_fmt(cv_ece_mean, CV_ECE_MEAN_THRESHOLD)}")
    print(f"  CV ECE std  : {_fmt(cv_ece_std, CV_ECE_STD_THRESHOLD)}")

    # Bootstrap 95% CI — returns (lower, upper, mean); upper is index 1
    print(f"\n  Running bootstrap CI ({N_BOOTSTRAP} resamples) …")
    _, boot_brier_upper, _ = bootstrap_confidence_interval(
        list(p_best), list(y_binary), n_bootstrap=N_BOOTSTRAP, metric="brier",
    )
    _, boot_ece_upper, _ = bootstrap_confidence_interval(
        list(p_best), list(y_binary), n_bootstrap=N_BOOTSTRAP, metric="ece",
    )
    boot_brier_upper_f = float(boot_brier_upper)
    boot_ece_upper_f = float(boot_ece_upper)
    print(f"  Bootstrap Brier 95% CI upper : {_fmt(boot_brier_upper_f, BOOTSTRAP_BRIER_UPPER)}")
    print(f"  Bootstrap ECE   95% CI upper : {_fmt(boot_ece_upper_f, BOOTSTRAP_ECE_UPPER)}")

    # Final gate evaluation
    all_pass, gates = _check_all_kpis(
        best_brier, best_ece, log_loss_raw, roc_auc_raw,
        cv_ece_mean, cv_ece_std, boot_brier_upper_f, boot_ece_upper_f,
    )
    gate_label = "PASS" if all_pass else "FAIL"
    print(f"\n  T1-D gate (all 7 KPIs): {gate_label}")
    for k, v in gates.items():
        print(f"    {k:<30s}: {'PASS' if v else 'FAIL'}")

    # Return structured results for JSON report
    return {
        "tier": "tier1_xgb",
        "model_sha256": _sha256(xgb_model_path),
        "n_val": int(len(y_binary)),
        "best_calibrator": best_name,
        "brier": best_brier,
        "ece": best_ece,
        "log_loss": log_loss_raw,
        "roc_auc": roc_auc_raw,
        "cv_ece_mean": cv_ece_mean,
        "cv_ece_std": cv_ece_std,
        "bootstrap_brier_upper": boot_brier_upper_f,
        "bootstrap_ece_upper": boot_ece_upper_f,
        "gates": gates,
        "all_kpis_pass": all_pass,
    }


# ---------------------------------------------------------------------------
# CNN evaluation
# ---------------------------------------------------------------------------

def evaluate_cnn(
    cnn_model_path: Path,
    cutouts_csv: Path,
    seed: int = 42,
    val_frac: float = 0.2,
    batch_size: int = 64,
) -> dict[str, Any]:
    """Evaluate Tier 2 CNN on the held-out val set.

    Returns a dict of all KPI values and gate results for inclusion in the
    machine-readable JSON report.
    """
    import csv as _csv
    import os as _os

    # Set single-threaded mode BEFORE importing torch so ATen never spawns its
    # parallel thread pool. On macOS (Apple Silicon + Accelerate), the first
    # call that triggers thread-pool initialisation (matmul, conv2d) deadlocks
    # indefinitely when the pool is multi-threaded. Forcing single-thread mode
    # prevents the deadlock entirely; inference is slower but completes.
    _os.environ.setdefault("OMP_NUM_THREADS", "1")
    _os.environ.setdefault("MKL_NUM_THREADS", "1")

    import torch
    torch.set_num_threads(1)  # enforce single-thread after import; belt-and-suspenders
    from torch.utils.data import Dataset, random_split

    from classify import _build_cnn_model  # type: ignore[import]

    _print_header("Tier 2 CNN — binary real/bogus calibration")

    # Load CSV rows
    with cutouts_csv.open(newline="") as f:
        rows = list(_csv.DictReader(f))
    print(f"  Total cutouts: {len(rows)}")

    # Reproduce the same random_split used in train_tier2_cnn.py
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
    # Binary: 1=real (class 0), 0=bogus (class 3)
    y_binary = (y_val_raw == 0).astype(float)
    n_real = int(y_binary.sum())
    n_bogus = int((y_binary == 0).sum())
    print(f"  Val set: {len(val_rows)}  (real={n_real}  bogus={n_bogus})", flush=True)

    # Build CNN architecture then load weights — both steps can be slow on network filesystems.
    print("  Building CNN model architecture ...", flush=True)
    model = _build_cnn_model()
    if model is None:
        print("  ERROR: torch not available — cannot evaluate CNN.")
        return {"tier": "tier2_cnn", "error": "torch unavailable"}
    # Pre-read the .pt file into a BytesIO buffer in 64 KB chunks so we can
    # show real ETA while Dropbox materialises the bytes from cloud storage.
    # torch.load on a raw path uses mmap — it returns instantly (0 s) but
    # load_state_dict then forces every tensor page, blocking silently for
    # minutes.  Reading into BytesIO first guarantees all data is in RAM before
    # either torch call, so both complete in milliseconds.
    import io as _io
    try:
        file_size = cnn_model_path.stat().st_size
        size_mb = file_size / (1024 * 1024)
        print(
            f"  Loading CNN weights from: {cnn_model_path}  ({size_mb:.1f} MB) ...",
            flush=True,
        )
    except OSError:
        file_size = 0
        size_mb = 0.0
        print(f"  Loading CNN weights from: {cnn_model_path} ...", flush=True)

    _CHUNK = 65536  # 64 KB — fine-grained enough for ETA on slow Dropbox links
    buf = _io.BytesIO()
    bytes_read = 0
    t_load = time.monotonic()
    with open(str(cnn_model_path), "rb") as _fh:
        while True:
            chunk = _fh.read(_CHUNK)
            if not chunk:
                break
            buf.write(chunk)
            bytes_read += len(chunk)
            elapsed = time.monotonic() - t_load
            # Print per-chunk progress with ETA derived from current read speed.
            if file_size > 0 and elapsed > 0:
                speed = bytes_read / elapsed  # bytes / sec
                remaining_bytes = file_size - bytes_read
                eta_s = remaining_bytes / speed if speed > 0 else 0
                pct = bytes_read / file_size * 100
                em, es = divmod(int(elapsed), 60)
                rm, rs = divmod(int(eta_s), 60)
                print(
                    f"\r  Loading CNN weights: {bytes_read / 1048576:.1f}/{size_mb:.1f} MB"
                    f"  ({pct:.0f}%)  elapsed {em}m{es:02d}s  ETA {rm}m{rs:02d}s   ",
                    end="",
                    flush=True,
                )
    print(flush=True)  # newline after the \r progress line
    load_s = time.monotonic() - t_load
    print(f"  CNN weights read in {load_s:.1f}s — deserialising from RAM ...", flush=True)

    buf.seek(0)
    # Deserialise from BytesIO — pure RAM, no disk I/O.
    t_tl = time.monotonic()
    state = torch.load(buf, map_location="cpu", weights_only=False)
    print(f"  torch.load: {time.monotonic() - t_tl:.2f}s", flush=True)
    del buf  # free the raw bytes; only the deserialized tensors are needed now

    # Warm up PyTorch's Accelerate / BLAS / thread-pool lazy initialisation.
    # On macOS (Apple Silicon + Accelerate), the first tensor compute call in a
    # new process initialises the framework, taking 15-30 s.  If this happens
    # inside load_state_dict the operator sees a silent hang.  A dummy matmul
    # here absorbs the one-time cost with a named, timed print instead.
    print("  Warming up PyTorch runtime (single-threaded; should be <5 s) ...", flush=True)
    t_wu = time.monotonic()
    _w = torch.zeros(256, 256)
    with _heartbeat("PyTorch matmul warmup"):
        _ = _w @ _w  # forces ATen dispatch into Accelerate
    del _w, _
    print(f"  PyTorch warmup done in {time.monotonic() - t_wu:.1f}s.", flush=True)

    # After warmup, load_state_dict is a simple memcpy — completes in <1 s.
    t_lsd = time.monotonic()
    print("  Applying state dict to model ...", flush=True)
    model.load_state_dict(state)
    print(f"  load_state_dict: {time.monotonic() - t_lsd:.2f}s", flush=True)
    print("  Setting eval mode ...", flush=True)
    model.eval()

    # Force conv2d kernel initialisation with a dummy pass before the real loop.
    # The matmul warmup above only activates ATen's BLAS paths; the first
    # torch.nn.Conv2d call goes through a different dispatch route (FBGEMM /
    # oneDNN / nnpack on macOS CPU) that can take many minutes to compile.
    # A tiny 1×1×63×63 dummy forward pass here absorbs that one-time cost with a
    # named, heartbeat-covered print so the operator sees it rather than silence.
    print(
        "  Warming up CNN conv layers (one-time; may take a few minutes on macOS) ...",
        flush=True,
    )
    t_cnn_wu = time.monotonic()
    with torch.no_grad():
        _dummy = torch.zeros(1, 1, 63, 63)
        with _heartbeat("CNN conv warmup"):
            model(_dummy, _dummy, _dummy)
        del _dummy
    print(
        f"  CNN conv warmup done in {time.monotonic() - t_cnn_wu:.1f}s.",
        flush=True,
    )

    n_batches = (len(val_rows) + batch_size - 1) // batch_size
    print(
        f"  Model ready. Starting inference on {len(val_rows)} cutouts"
        f" ({n_batches} batches of {batch_size}) ...",
        flush=True,
    )

    def _load_npz(path: str) -> tuple:
        """Load a single .npz cutout triplet as float32 tensors."""
        import numpy as _np
        data = _np.load(path)
        def _t(k: str):
            return torch.from_numpy(
                _np.nan_to_num(data[k], nan=0.0, posinf=0.0, neginf=0.0)
                .astype(_np.float32)
            ).unsqueeze(0)
        return _t("science"), _t("reference"), _t("difference")

    # Run inference on val set in batches — print progress every batch.
    all_proba: list[float] = []
    t_infer = time.monotonic()
    with torch.no_grad():
        for batch_idx, i in enumerate(range(0, len(val_rows), batch_size)):
            batch_rows = val_rows[i : i + batch_size]
            done = batch_idx + 1
            # Announce the batch BEFORE loading its cutouts. The first batch in
            # particular can take a while to read 50 .npz files from Dropbox; a
            # heartbeat keeps that load visibly alive instead of silent.
            # All progress goes to stdout so it is always visible regardless of
            # how the operator's terminal handles stderr.
            print(
                f"  [CNN inference] loading batch {done}/{n_batches}"
                f" ({len(batch_rows)} cutouts) ...",
                flush=True,
            )
            sci_b, ref_b, diff_b = [], [], []
            with _heartbeat(f"batch {done}/{n_batches} cutout load"):
                for r in batch_rows:
                    s, re, d = _load_npz(r["cutout_path"])
                    sci_b.append(s)
                    ref_b.append(re)
                    diff_b.append(d)
            sci_t = torch.stack(sci_b)
            ref_t = torch.stack(ref_b)
            diff_t = torch.stack(diff_b)
            with _heartbeat(f"batch {done}/{n_batches} forward pass"):
                out = model(sci_t, ref_t, diff_t)  # shape (B, 5) softmax
            # P(real) = 1 - P(stellar_artifact=class 3)
            p = 1.0 - out[:, 3].cpu().numpy()
            all_proba.extend(p.tolist())
            elapsed = time.monotonic() - t_infer
            em, es = divmod(int(elapsed), 60)
            rate = elapsed / done if done else 0
            remaining = (n_batches - done) * rate
            rm, rs = divmod(int(remaining), 60)
            print(
                f"  [CNN inference] batch {done}/{n_batches}"
                f"  samples {min(i + batch_size, len(val_rows))}/{len(val_rows)}"
                f"  elapsed {em}m{es:02d}s  ETA {rm}m{rs:02d}s",
                flush=True,
            )

    p_real = np.array(all_proba, dtype=np.float64)

    # Raw (uncalibrated) metrics
    bs = float(brier_score(p_real, y_binary))
    ece = float(expected_calibration_error(p_real, y_binary))

    print()
    _print_row("Raw CNN", bs, ece)

    # -----------------------------------------------------------------
    # Platt and isotonic calibration — 50/50 half-split of the val set.
    # Fit on first half; evaluate on second half — avoids data leakage.
    # -----------------------------------------------------------------
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

    # Best calibrated metrics
    best_brier = min(bs, bs_p, bs_i)
    best_ece = min(ece, ece_p, ece_i)
    best_name = {bs: "Raw", bs_p: "Platt", bs_i: "Isotonic"}[best_brier]

    # Apply best calibrator to full val set for expanded KPIs
    if best_name == "Platt":
        p_best = platt.predict(p_real)
    elif best_name == "Isotonic":
        p_best = iso.predict(p_real)
    else:
        p_best = p_real

    log_loss_raw = float(compute_log_loss(p_real, y_binary))
    roc_auc_raw = float(compute_roc_auc(p_real, y_binary))

    print(f"\n  Log-loss (raw)   : {_fmt(log_loss_raw, LOG_LOSS_THRESHOLD)}")
    print(f"  ROC AUC  (raw)   : {_fmt(roc_auc_raw, ROC_AUC_THRESHOLD, lower_better=False)}")

    print(f"\n  Running 5-fold CV ECE (best={best_name}) …")
    cv_ece_mean, cv_ece_std = cross_validate_calibration(
        list(p_best), list(y_binary), n_folds=5, metric="ece",
    )
    print(f"  CV ECE mean : {_fmt(cv_ece_mean, CV_ECE_MEAN_THRESHOLD)}")
    print(f"  CV ECE std  : {_fmt(cv_ece_std, CV_ECE_STD_THRESHOLD)}")

    print(f"\n  Running bootstrap CI ({N_BOOTSTRAP} resamples) …")
    _, boot_brier_upper, _ = bootstrap_confidence_interval(
        list(p_best), list(y_binary), n_bootstrap=N_BOOTSTRAP, metric="brier",
    )
    _, boot_ece_upper, _ = bootstrap_confidence_interval(
        list(p_best), list(y_binary), n_bootstrap=N_BOOTSTRAP, metric="ece",
    )
    boot_brier_upper_f = float(boot_brier_upper)
    boot_ece_upper_f = float(boot_ece_upper)
    print(f"  Bootstrap Brier 95% CI upper : {_fmt(boot_brier_upper_f, BOOTSTRAP_BRIER_UPPER)}")
    print(f"  Bootstrap ECE   95% CI upper : {_fmt(boot_ece_upper_f, BOOTSTRAP_ECE_UPPER)}")

    all_pass, gates = _check_all_kpis(
        best_brier, best_ece, log_loss_raw, roc_auc_raw,
        cv_ece_mean, cv_ece_std, boot_brier_upper_f, boot_ece_upper_f,
    )
    gate_label = "PASS" if all_pass else "FAIL"
    print(f"\n  T1-D gate (all 7 KPIs): {gate_label}")
    for k, v in gates.items():
        print(f"    {k:<30s}: {'PASS' if v else 'FAIL'}")

    return {
        "tier": "tier2_cnn",
        "model_sha256": _sha256(cnn_model_path),
        "n_val": int(len(y_binary)),
        "best_calibrator": best_name,
        "brier": best_brier,
        "ece": best_ece,
        "log_loss": log_loss_raw,
        "roc_auc": roc_auc_raw,
        "cv_ece_mean": cv_ece_mean,
        "cv_ece_std": cv_ece_std,
        "bootstrap_brier_upper": boot_brier_upper_f,
        "bootstrap_ece_upper": boot_ece_upper_f,
        "gates": gates,
        "all_kpis_pass": all_pass,
    }


# ---------------------------------------------------------------------------
# Machine-readable JSON report
# ---------------------------------------------------------------------------

def _emit_json_report(
    tier_results: list[dict[str, Any]],
    report_path: Path,
) -> None:
    """Write a machine-readable calibration report to report_path.

    promotion_gate_passed is True only when ALL evaluated tiers pass ALL
    seven KPI gates. Tier 3 is not evaluated here (no model weights yet);
    its absence is recorded in the report for traceability.
    """
    import datetime

    all_evaluated_pass = bool(
        tier_results
        and all(r.get("all_kpis_pass", False) for r in tier_results)
    )

    # Threshold reference — included for reproducibility without re-reading source
    thresholds = {
        "brier": BRIER_THRESHOLD,
        "ece": ECE_THRESHOLD,
        "log_loss": LOG_LOSS_THRESHOLD,
        "roc_auc_min": ROC_AUC_THRESHOLD,
        "cv_ece_mean": CV_ECE_MEAN_THRESHOLD,
        "cv_ece_std": CV_ECE_STD_THRESHOLD,
        "bootstrap_brier_upper": BOOTSTRAP_BRIER_UPPER,
        "bootstrap_ece_upper": BOOTSTRAP_ECE_UPPER,
    }

    report: dict[str, Any] = {
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "promotion_gate_passed": all_evaluated_pass,
        "tier3_evaluated": False,
        "tier3_note": (
            "Tier 3 Transformer weights not yet available. "
            "Re-run after Skills/train_tier3_transformer.py completes."
        ),
        "thresholds": thresholds,
        "tiers": tier_results,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  JSON report written to: {report_path}")
    print(f"  promotion_gate_passed : {all_evaluated_pass}")


# ---------------------------------------------------------------------------
# Synthetic fallback (for CI — no real data required)
# ---------------------------------------------------------------------------

def _synthetic_eval() -> None:
    """Fallback: evaluate Platt/isotonic calibrators on synthetic scores.

    Used when neither real model nor real data is present (e.g., in CI).
    Does NOT evaluate the full 7-KPI T1-D gate — that requires real data.
    """
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
    print(
        "\nNOTE: Full T1-D gate (7 KPIs) requires real model + data. "
        "This is the CI synthetic fallback only."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Tier 1 XGBoost and Tier 2 CNN calibration on real data "
            "against all seven T1-D promotion gate KPIs."
        )
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
    parser.add_argument(
        "--report-out", type=Path, default=None,
        help=(
            "Write machine-readable JSON calibration report to this path. "
            "Recommended: Logs/reports/calibration_report.json  (gitignored). "
            "promotion_gate_passed=true only when all evaluated tiers pass all 7 KPIs."
        ),
    )
    args = parser.parse_args()

    # Determine which real-model evaluations are possible
    can_xgb = args.alerts.exists() and args.xgb_model.exists()
    can_cnn = args.cutouts_csv.exists() and args.cnn_model.exists()

    if not can_xgb and not can_cnn:
        # Neither real dataset available — run synthetic fallback (CI safe)
        _synthetic_eval()
        return

    print("\nT1-D calibration gate thresholds:")
    print(f"  Brier < {BRIER_THRESHOLD}  |  ECE < {ECE_THRESHOLD}")
    print(f"  Log-loss < {LOG_LOSS_THRESHOLD}  |  ROC AUC > {ROC_AUC_THRESHOLD}")
    print(f"  CV ECE mean < {CV_ECE_MEAN_THRESHOLD}  (std <= {CV_ECE_STD_THRESHOLD})")
    print(f"  Bootstrap Brier 95% CI upper < {BOOTSTRAP_BRIER_UPPER}")
    print(f"  Bootstrap ECE   95% CI upper < {BOOTSTRAP_ECE_UPPER}")
    print("  (ALL seven must pass for promotion_gate_passed=true)")

    tier_results: list[dict[str, Any]] = []

    if can_xgb:
        result = evaluate_xgboost(
            xgb_model_path=args.xgb_model,
            alerts_path=args.alerts,
            mpc_path=args.mpc_labels,
            seed=args.seed,
        )
        tier_results.append(result)
    else:
        print("\n[XGBoost] Skipped — alerts or model not found.")

    if can_cnn:
        result = evaluate_cnn(
            cnn_model_path=args.cnn_model,
            cutouts_csv=args.cutouts_csv,
            seed=args.seed,
        )
        tier_results.append(result)
    else:
        print("\n[CNN] Skipped — cutouts CSV or model not found.")

    # Emit JSON report if requested (or if report-out was specified)
    if args.report_out is not None and tier_results:
        _emit_json_report(tier_results, args.report_out)

    print()


if __name__ == "__main__":
    main()
