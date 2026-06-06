#!/usr/bin/env python3
"""Fine-tune the Tier 2 CNN on labeled ZTF cutout data.

Reads a CSV produced by Skills/build_cutout_dataset.py with columns
``cutout_path`` (.npz file) and ``label`` (int 0–4 matching NEOPosterior).

Three key design choices vs. the naive implementation:

1. NLLLoss(log(output)) instead of CrossEntropyLoss — the TripleCNN model in
   classify.py ends with nn.Softmax, so its output is already a probability
   distribution.  CrossEntropyLoss internally applies LogSoftmax a second time,
   producing double-softmax / numerical instability.  We use NLLLoss with an
   explicit log() instead.

2. Class-weighted loss — ZTF real/bogus data is typically ~85/15 real/bogus.
   Without weighting the model learns to predict "real" for everything and
   achieves 85% accuracy while being useless for artifact rejection.  Weights
   are computed from the training split only (not the val split) to avoid leakage.

3. Mini-batch DataLoader + 80/20 val split — stochastic mini-batch updates
   (batch_size 32) converge much faster than sample-at-a-time updates and
   the validation split lets us track overfitting and save the best checkpoint.

Usage:
    PYTHONPATH=src caffeinate -i python Skills/train_tier2_cnn.py \\
        --labels data/cutouts/index.csv \\
        --epochs 20 \\
        --out models/tier2_cnn.pt
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from pathlib import Path

# Ensure src/ modules (classify.py etc.) are importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Human-readable names for the 5 NEOPosterior classes (index = label int)
LABEL_NAMES = [
    "neo_candidate",        # 0 — real ZTF detection
    "known_object",         # 1
    "main_belt_asteroid",   # 2
    "stellar_artifact",     # 3 — bogus ZTF detection
    "other_solar_system",   # 4
]


def _load_cutout_npz(npz_path: str):  # noqa: ANN201
    """Load a single .npz cutout triplet as three (1,63,63) float32 tensors.

    Returns (science, reference, difference) each shaped (1, H, W) where the
    leading 1 is the channel dimension expected by the ConvBranch modules.
    The DataLoader will stack these into (B, 1, H, W) batches automatically.
    """
    import numpy as np
    import torch

    data = np.load(npz_path)
    # unsqueeze(0) adds channel dim: (63,63) → (1,63,63)
    sci = torch.from_numpy(data["science"].astype(np.float32)).unsqueeze(0)
    ref = torch.from_numpy(data["reference"].astype(np.float32)).unsqueeze(0)
    diff = torch.from_numpy(data["difference"].astype(np.float32)).unsqueeze(0)
    return sci, ref, diff


def _build_dataset(rows: list[dict]):
    """Wrap a list of CSV rows in a torch Dataset."""
    import torch
    from torch.utils.data import Dataset

    class CutoutDataset(Dataset):
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, idx: int):  # noqa: ANN204
            row = self.rows[idx]
            sci, ref, diff = _load_cutout_npz(row["cutout_path"])
            label = torch.tensor(int(row["label"]), dtype=torch.long)
            return sci, ref, diff, label

    return CutoutDataset(rows)


def _compute_class_weights(rows: list[dict]) -> "torch.Tensor":
    """Compute inverse-frequency class weights for NLLLoss.

    Only classes that appear in `rows` contribute; unused classes get weight 1.0
    so they don't produce NaN gradients if the model ever predicts them.
    """
    import torch
    from collections import Counter

    counts: Counter[int] = Counter(int(r["label"]) for r in rows)
    total = sum(counts.values())
    n_present = len(counts)

    weights = torch.ones(len(LABEL_NAMES))
    for cls, count in counts.items():
        # Balanced inverse-frequency: total / (n_classes_present * count)
        weights[cls] = total / (n_present * count)
    return weights


def train(labels_csv: str, epochs: int, out_path: str, lr: float,
          batch_size: int, val_fraction: float) -> None:
    """Train the Tier 2 CNN and save the best checkpoint by val loss."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, random_split

    from classify import _build_cnn_model

    model = _build_cnn_model()
    if model is None:
        print("ERROR: torch not available — cannot train CNN.")
        return

    # Load all CSV rows
    with open(labels_csv) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("ERROR: empty labels CSV")
        return

    # 80/20 stratified-ish split (random_split preserves label distribution
    # statistically for large N; for small N consider StratifiedShuffleSplit)
    dataset = _build_dataset(rows)
    n_val = max(1, int(val_fraction * len(dataset)))
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42),  # reproducible split
    )

    # Compute class weights from training rows only (avoid val leakage)
    train_rows = [rows[i] for i in train_ds.indices]
    class_weights = _compute_class_weights(train_rows)

    # Summarise the split and class balance before starting
    from collections import Counter
    train_counts = Counter(int(r["label"]) for r in train_rows)
    val_counts   = Counter(int(rows[i]["label"]) for i in val_ds.indices)
    print(f"Training on {n_train} samples, validating on {n_val} samples")
    print(f"  Train label counts: { {LABEL_NAMES[k]: v for k, v in sorted(train_counts.items())} }")
    print(f"  Val   label counts: { {LABEL_NAMES[k]: v for k, v in sorted(val_counts.items())} }")
    print(f"  Class weights:      { {LABEL_NAMES[i]: round(class_weights[i].item(), 3) for i in range(len(LABEL_NAMES)) if class_weights[i] != 1.0 or i in train_counts} }")
    print()

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                              num_workers=0, pin_memory=False)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    # NLLLoss is correct here because the model already applies Softmax.
    # CrossEntropyLoss would apply LogSoftmax again (double-softmax bug).
    criterion = nn.NLLLoss(weight=class_weights)

    best_val_loss = float("inf")
    out_path_obj = pathlib.Path(out_path)
    out_path_obj.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(epochs):
        # ── Training pass ─────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        for sci, ref, diff, label in train_loader:
            optimizer.zero_grad()
            out = model(sci, ref, diff)
            # log() needed because NLLLoss expects log-probabilities;
            # clamp avoids log(0) for any class with Softmax output near zero.
            loss = criterion(torch.log(out.clamp(min=1e-9)), label)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(label)
        train_loss /= n_train

        # ── Validation pass ───────────────────────────────────────────────────
        model.eval()
        val_loss = 0.0
        n_correct = 0
        with torch.no_grad():
            for sci, ref, diff, label in val_loader:
                out = model(sci, ref, diff)
                loss = criterion(torch.log(out.clamp(min=1e-9)), label)
                val_loss += loss.item() * len(label)
                preds = out.argmax(dim=1)
                n_correct += (preds == label).sum().item()
        val_loss /= n_val
        val_acc = n_correct / n_val

        # Save best checkpoint so we can stop early or resume
        improved = ""
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), out_path)
            improved = "  ← best"

        print(f"  Epoch {epoch + 1:3d}/{epochs}  "
              f"train_loss={train_loss:.4f}  "
              f"val_loss={val_loss:.4f}  "
              f"val_acc={val_acc:.3f}{improved}")

    print()
    print(f"Best val loss: {best_val_loss:.4f}")
    print(f"Saved best weights → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train Tier 2 CNN on labeled ZTF cutout dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--labels", required=True,
        help="CSV with cutout_path and label columns (from build_cutout_dataset.py)",
    )
    parser.add_argument("--epochs", type=int, default=20,
                        help="Number of training epochs")
    parser.add_argument("--out", default="models/tier2_cnn.pt",
                        help="Output path for best model checkpoint")
    parser.add_argument("--lr", type=float, default=1e-4,
                        help="Adam learning rate")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Mini-batch size for DataLoader")
    parser.add_argument("--val-fraction", type=float, default=0.2,
                        help="Fraction of data held out for validation")
    args = parser.parse_args()
    train(args.labels, args.epochs, args.out, args.lr,
          args.batch_size, args.val_fraction)
