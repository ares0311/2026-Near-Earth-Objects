#!/usr/bin/env python3
"""Fine-tune the Tier 2 CNN on labeled ZTF cutout data.

Usage:
    PYTHONPATH=src python Skills/train_tier2_cnn.py \\
        --labels data/cutouts/index.csv \\
        --epochs 20 \\
        --out models/tier2_cnn.pt

Expected CSV columns: ``cutout_path`` (path to .npz file produced by
``Skills/build_cutout_dataset.py``), ``label`` (int 0–4 matching NEOPosterior order).

The .npz file must contain arrays ``science``, ``reference``, ``difference``
each of shape (63, 63) float32, normalised to [0, 1].
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

LABEL_NAMES = [
    "neo_candidate", "known_object", "main_belt_asteroid",
    "stellar_artifact", "other_solar_system",
]


def _load_cutout_npz(npz_path: str):  # noqa: ANN201
    import numpy as np
    import torch

    data = np.load(npz_path)
    sci = torch.from_numpy(data["science"].astype(np.float32)).unsqueeze(0)   # (1,63,63)
    ref = torch.from_numpy(data["reference"].astype(np.float32)).unsqueeze(0)
    diff = torch.from_numpy(data["difference"].astype(np.float32)).unsqueeze(0)
    return sci, ref, diff


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
            sci, ref, diff = _load_cutout_npz(row["cutout_path"])
            sci, ref, diff = sci.unsqueeze(0), ref.unsqueeze(0), diff.unsqueeze(0)
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
    parser = argparse.ArgumentParser(description="Train Tier 2 CNN on cutout dataset")
    parser.add_argument("--labels", required=True,
                        help="CSV with cutout_path and label columns")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--out", default="models/tier2_cnn.pt")
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()
    train(args.labels, args.epochs, args.out, args.lr)
