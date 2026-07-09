"""Locked preprocessing helpers for benchmark_cnn_v1.

These helpers mirror the existing Tier 2 paths: ZTF science, reference, and
difference cutouts are 63x63 float32 arrays with non-finite values zero-filled.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from classify import _decode_cutout_f32

# The CNN architecture and stored cutouts both assume 63 by 63 pixel planes.
CUTOUT_SIZE = 63

# The channel order is frozen for training, evaluation, and score reports.
TRIPLET_KEYS = ("science", "reference", "difference")


def decode_base64_triplet(
    science: str,
    reference: str,
    difference: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Decode one alert triplet using the same base64 float32 contract as classify."""
    decoded = (
        _decode_cutout_f32(science, CUTOUT_SIZE),
        _decode_cutout_f32(reference, CUTOUT_SIZE),
        _decode_cutout_f32(difference, CUTOUT_SIZE),
    )
    if any(arr is None for arr in decoded):
        return None
    return decoded  # type: ignore[return-value]


def load_npz_triplet(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load a persisted cutout triplet and zero-fill NaN or infinite pixels."""
    data = np.load(path)
    planes = []
    for key in TRIPLET_KEYS:
        # Use float32 explicitly so evals exercise the same tensor precision.
        plane = np.nan_to_num(
            data[key],
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)
        if plane.shape != (CUTOUT_SIZE, CUTOUT_SIZE):
            msg = f"{key} cutout has shape {plane.shape}, expected {(CUTOUT_SIZE, CUTOUT_SIZE)}"
            raise ValueError(msg)
        planes.append(plane)
    return tuple(planes)  # type: ignore[return-value]
