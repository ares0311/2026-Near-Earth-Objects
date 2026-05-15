#!/usr/bin/env python
"""Build a cutout dataset (.npz files) from ZTF alert JSON for Tier 2 CNN training.

Reads a JSON file where each entry has observations with base64-encoded cutout fields
(``cutout_science``, ``cutout_reference``, ``cutout_difference``) and a ``label`` integer
(0=neo_candidate, 1=known_object, 2=main_belt_asteroid, 3=stellar_artifact,
4=other_solar_system).

Writes one .npz file per valid triplet to ``output_dir/``, then writes a CSV index with
columns: ``cutout_path``, ``label``.  The CSV is the expected input for
``Skills/train_tier2_cnn.py``.

Usage:
    PYTHONPATH=src python Skills/build_cutout_dataset.py \\
        --input data/labeled_alerts.json \\
        --output-dir data/cutouts/ \\
        --csv data/cutouts/index.csv
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np


def _decode_b64(b64_str: str, size: int = 63) -> np.ndarray | None:
    try:
        raw = base64.b64decode(b64_str)
        arr = np.frombuffer(raw, dtype=np.float32)
        if arr.size != size * size:
            return None
        arr_f = arr.reshape(size, size).copy()
        lo, hi = np.percentile(arr_f, 1), np.percentile(arr_f, 99)
        if hi > lo:
            arr_f = (arr_f - lo) / (hi - lo)
        arr_f = np.clip(arr_f, 0.0, 1.0)
        return arr_f
    except Exception:
        return None


def build_cutout_dataset(
    input_json: Path,
    output_dir: Path,
    csv_path: Path,
) -> int:
    """Convert labeled alert JSON to .npz cutout files.  Returns number of valid triplets."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with input_json.open() as f:
        entries = json.load(f)

    rows: list[dict] = []
    n_written = 0

    for entry_idx, entry in enumerate(entries):
        label = int(entry.get("label", 0))
        observations = entry.get("observations", [])
        for obs_idx, obs in enumerate(observations):
            sci = _decode_b64(obs.get("cutout_science", ""))
            ref = _decode_b64(obs.get("cutout_reference", ""))
            diff = _decode_b64(obs.get("cutout_difference", ""))
            if sci is None or ref is None or diff is None:
                continue

            npz_name = f"cutout_{entry_idx:06d}_{obs_idx:03d}.npz"
            npz_path = output_dir / npz_name
            np.savez_compressed(str(npz_path), science=sci, reference=ref, difference=diff)
            rows.append({"cutout_path": str(npz_path), "label": label})
            n_written += 1

    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cutout_path", "label"])
        writer.writeheader()
        writer.writerows(rows)

    return n_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cutout dataset for Tier 2 CNN")
    parser.add_argument("--input", type=Path, required=True, help="Labeled alert JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("data/cutouts"),
                        help="Directory for .npz files")
    parser.add_argument("--csv", type=Path, default=Path("data/cutouts/index.csv"),
                        help="Output CSV index")
    args = parser.parse_args()

    n = build_cutout_dataset(args.input, args.output_dir, args.csv)
    print(f"Wrote {n} cutout triplets → {args.output_dir}")
    print(f"CSV index → {args.csv}")


if __name__ == "__main__":
    main()
