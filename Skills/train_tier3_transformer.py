#!/usr/bin/env python3
"""Train the Tier 3 Transformer on MPC tracklet observation sequences.

Usage:
    PYTHONPATH=src python Skills/train_tier3_transformer.py \
        --labels data/tier3_labels.csv \
        --epochs 30 \
        --out models/tier3_transformer.pt

Expected CSV columns: object_id, label (0-4), obs_json
  obs_json: JSON list of {ra_deg, dec_deg, mag, jd, filter_band} per observation
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib

LABEL_NAMES = [
    "neo_candidate", "known_object", "main_belt_asteroid",
    "stellar_artifact", "other_solar_system",
]
FILTER_MAP = {"g": 0, "r": 1, "i": 2, "o": 3, "c": 4, "V": 5}


def _obs_to_seq(obs_list: list[dict]):  # noqa: ANN201
    import numpy as np
    import torch

    obs_sorted = sorted(obs_list, key=lambda o: o["jd"])
    t0 = obs_sorted[0]["jd"]
    rows = [
        [
            o["ra_deg"] / 360.0,
            (o["dec_deg"] + 90.0) / 180.0,
            o["mag"] / 30.0,
            (o["jd"] - t0) / 30.0,
            FILTER_MAP.get(o.get("filter_band", "r"), 1) / 5.0,
        ]
        for o in obs_sorted
    ]
    return torch.from_numpy(np.array(rows, dtype=np.float32)).unsqueeze(0)  # (1, T, 5)


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
        for row in rows:
            obs_list = json.loads(row["obs_json"])
            if len(obs_list) < 2:
                continue
            x = _obs_to_seq(obs_list)
            label = torch.tensor([int(row["label"])], dtype=torch.long)

            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, label)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        print(f"  Epoch {epoch + 1}/{epochs}  loss={total_loss / max(len(rows), 1):.4f}")

    pathlib.Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_path)
    print(f"Saved weights → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--out", default="models/tier3_transformer.pt")
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()
    train(args.labels, args.epochs, args.out, args.lr)
