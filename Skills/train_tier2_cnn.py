#!/usr/bin/env python3
"""Fine-tune the Tier 2 CNN on labeled ZTF cutout data.

Usage:
    PYTHONPATH=src python Skills/train_tier2_cnn.py \
        --labels data/tier2_labels.csv \
        --cutouts data/cutouts/ \
        --epochs 20 \
        --out models/tier2_cnn.pt

Expected CSV columns: obs_id, label (0-4 int matching NEOPosterior order),
                      cutout_science_path, cutout_reference_path, cutout_difference_path
"""

from __future__ import annotations

import argparse
import csv
import pathlib

LABEL_NAMES = [
    "neo_candidate", "known_object", "main_belt_asteroid",
    "stellar_artifact", "other_solar_system",
]


def _load_cutout(path: str):  # noqa: ANN201
    import numpy as np
    import torch

    arr = np.fromfile(path, dtype=np.float32).reshape(63, 63)
    arr = (arr - arr.min()) / max(arr.max() - arr.min(), 1e-6)
    return torch.from_numpy(arr).unsqueeze(0)  # (1, 63, 63)


def train(labels_csv: str, epochs: int, out_path: str, lr: float) -> None:
    import torch
    import torch.nn as nn

    from classify import _build_cnn_model

    model = _build_cnn_model()
    if model is None:
        print("ERROR: torch not available — cannot train CNN.")
        return

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    rows = list(csv.DictReader(open(labels_csv)))
    if not rows:
        print("ERROR: empty labels CSV")
        return

    print(f"Training on {len(rows)} examples for {epochs} epoch(s)...")
    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for row in rows:
            sci = _load_cutout(row["cutout_science_path"]).unsqueeze(0)
            ref = _load_cutout(row["cutout_reference_path"]).unsqueeze(0)
            diff = _load_cutout(row["cutout_difference_path"]).unsqueeze(0)
            label = torch.tensor([int(row["label"])], dtype=torch.long)

            optimizer.zero_grad()
            out = model(sci, ref, diff)
            loss = criterion(out, label)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        print(f"  Epoch {epoch + 1}/{epochs}  loss={total_loss / len(rows):.4f}")

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_path)
    print(f"Saved weights → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--out", default="models/tier2_cnn.pt")
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()
    train(args.labels, args.epochs, args.out, args.lr)
