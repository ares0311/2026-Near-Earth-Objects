#!/usr/bin/env python3
"""Train the Tier 3 Transformer on MPC tracklet observation sequences.

Usage:
    PYTHONPATH=src python Skills/train_tier3_transformer.py \\
        --labels data/sequences/train.csv \\
        --epochs 30 \\
        --out models/tier3_transformer.pt

Expected CSV format produced by ``Skills/build_sequence_dataset.py``:
  Flat token columns ``tok_0_0`` … ``tok_{T-1}_4`` where feature indices are
  0=RA_norm, 1=Dec_norm, 2=mag_norm, 3=time_norm, 4=filter_id_norm.
  Final column: ``label`` (int 0–4).
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

LABEL_NAMES = [
    "neo_candidate", "known_object", "main_belt_asteroid",
    "stellar_artifact", "other_solar_system",
]
_N_FEATURES = 5


def _row_to_tensor(row: dict):  # noqa: ANN201
    import numpy as np
    import torch

    # Discover max observation index from column names
    tok_keys = [k for k in row if re.match(r"^tok_\d+_\d+$", k)]
    if not tok_keys:
        return None
    max_t = max(int(k.split("_")[1]) for k in tok_keys) + 1
    seq = np.zeros((max_t, _N_FEATURES), dtype=np.float32)
    for key in tok_keys:
        _, t_str, j_str = key.split("_")
        seq[int(t_str), int(j_str)] = float(row[key])
    # Drop all-zero rows (padding) at end
    mask = seq.any(axis=1)
    seq = seq[mask]
    if seq.shape[0] < 2:
        return None
    return torch.from_numpy(seq).unsqueeze(0)  # (1, T, 5)


def train(labels_csv: str, epochs: int, out_path: str, lr: float) -> None:
    import torch
    import torch.nn as nn

    from classify import _build_transformer_model

    model = _build_transformer_model()
    if model is None:
        print("ERROR: torch not available — cannot train Transformer.")
        return

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    rows = list(csv.DictReader(open(labels_csv)))
    if not rows:
        print("ERROR: empty labels CSV")
        return

    print(f"Training on {len(rows)} tracklets for {epochs} epoch(s)...")
    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        n_trained = 0
        for row in rows:
            x = _row_to_tensor(row)
            if x is None:
                continue
            label = torch.tensor([int(row["label"])], dtype=torch.long)

            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, label)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            n_trained += 1

        print(f"  Epoch {epoch + 1}/{epochs}  loss={total_loss / max(n_trained, 1):.4f}")

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_path)
    print(f"Saved weights → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Tier 3 Transformer on sequence CSV")
    parser.add_argument("--labels", required=True,
                        help="CSV with tok_i_j columns and label (from build_sequence_dataset.py)")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--out", default="models/tier3_transformer.pt")
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()
    train(args.labels, args.epochs, args.out, args.lr)
