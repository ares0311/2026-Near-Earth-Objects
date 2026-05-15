#!/usr/bin/env python
"""Build a flat sequence CSV dataset from tracklet JSON for Tier 3 Transformer training.

Reads a tracklet JSON (same format as ``data/sample_tracklets.json``) where each
entry has ``observations`` and a ``label`` integer.  Converts each tracklet to a
flat row of ``tok_i_j`` columns where ``i`` is the observation index and ``j`` is
the feature index (0=RA_norm, 1=Dec_norm, 2=mag_norm, 3=time_norm, 4=filter_id_norm).

Output CSV columns: ``tok_0_0``, ``tok_0_1``, ..., ``tok_{T-1}_4``, ``label``.
Rows with fewer than ``max_seq`` observations are zero-padded; longer rows are truncated.
The CSV is the expected input for ``Skills/train_tier3_transformer.py``.

Usage:
    PYTHONPATH=src python Skills/build_sequence_dataset.py \\
        --input data/labeled_tracklets.json \\
        --output data/sequences/train.csv \\
        --max-seq 20
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_FILTER_MAP = {"g": 0, "r": 1, "i": 2, "o": 3, "c": 4, "V": 5}
_N_FEATURES = 5


def _obs_to_token(obs: dict, t0: float) -> list[float]:
    ra = obs.get("ra_deg", 0.0) / 360.0
    dec = (obs.get("dec_deg", 0.0) + 90.0) / 180.0
    mag = obs.get("mag", 20.0) / 30.0
    dt = (obs.get("jd", t0) - t0) / 30.0
    filt = _FILTER_MAP.get(obs.get("filter_band", "r"), 1) / 5.0
    return [ra, dec, mag, dt, filt]


def build_sequence_dataset(
    input_json: Path,
    output_csv: Path,
    max_seq: int = 20,
) -> int:
    with input_json.open() as f:
        entries = json.load(f)

    header = [f"tok_{i}_{j}" for i in range(max_seq) for j in range(_N_FEATURES)] + ["label"]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0

    with output_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()

        for entry in entries:
            label = int(entry.get("label", 0))
            observations = sorted(entry.get("observations", []),
                                  key=lambda o: o.get("jd", 0.0))
            t0 = observations[0].get("jd", 0.0) if observations else 0.0
            row: dict = {k: "0.0" for k in header}
            row["label"] = str(label)
            for i, obs in enumerate(observations[:max_seq]):
                tok = _obs_to_token(obs, t0)
                for j, v in enumerate(tok):
                    row[f"tok_{i}_{j}"] = f"{v:.6f}"
            writer.writerow(row)
            n_written += 1

    return n_written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sequence CSV for Tier 3 Transformer")
    parser.add_argument("--input", type=Path, required=True, help="Labeled tracklet JSON")
    parser.add_argument("--output", type=Path, default=Path("data/sequences/train.csv"))
    parser.add_argument("--max-seq", type=int, default=20,
                        help="Maximum observations per tracklet (default 20)")
    args = parser.parse_args()

    n = build_sequence_dataset(args.input, args.output, args.max_seq)
    print(f"Wrote {n} sequences → {args.output}")


if __name__ == "__main__":
    main()
