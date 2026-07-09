"""Parameterized injection-recovery curve summaries."""

from __future__ import annotations

import math
from typing import Any

DEFAULT_BINS: dict[str, tuple[float, ...]] = {
    "mag": (10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0),
    "motion_arcsec_per_hr": (0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0),
    "n_observations": (0.0, 3.0, 6.0, 9.0, 12.0),
    "n_nights": (0.0, 1.0, 2.0, 3.0, 4.0),
}
_OUTCOMES = ("detected", "linked", "scored")


def _as_bool(value: Any) -> bool:
    return bool(value)


def _bin_label(lower: float, upper: float) -> str:
    return f"[{lower:g},{upper:g})"


def _bin_index(value: float, edges: tuple[float, ...]) -> int | None:
    if len(edges) < 2 or not math.isfinite(value):
        return None
    for index, lower in enumerate(edges[:-1]):
        upper = edges[index + 1]
        if lower <= value < upper:
            return index
    if value == edges[-1]:
        return len(edges) - 2
    return None


def _empty_bin(dimension: str, index: int, edges: tuple[float, ...]) -> dict[str, Any]:
    lower = edges[index]
    upper = edges[index + 1]
    return {
        "dimension": dimension,
        "bin": _bin_label(lower, upper),
        "lower": lower,
        "upper": upper,
        "n": 0,
        "n_detected": 0,
        "n_linked": 0,
        "n_scored": 0,
        "detection_rate": None,
        "link_rate": None,
        "score_rate": None,
    }


def _finalize_bin(row: dict[str, Any]) -> dict[str, Any]:
    n = int(row["n"])
    if n == 0:
        return row
    row["detection_rate"] = row["n_detected"] / n
    row["link_rate"] = row["n_linked"] / n
    row["score_rate"] = row["n_scored"] / n
    return row


def recovery_curve_report(
    records: list[dict[str, Any]],
    *,
    bins: dict[str, tuple[float, ...]] | None = None,
) -> dict[str, Any]:
    """Build per-parameter recovery curves from per-injection records."""
    bins = bins or DEFAULT_BINS
    curves: dict[str, list[dict[str, Any]]] = {}
    missing_dimensions: list[str] = []
    for dimension, edges in bins.items():
        rows = [_empty_bin(dimension, index, edges) for index in range(len(edges) - 1)]
        usable = 0
        for record in records:
            value = record.get(dimension)
            if value is None:
                continue
            index = _bin_index(float(value), edges)
            if index is None:
                continue
            usable += 1
            row = rows[index]
            row["n"] += 1
            row["n_detected"] += int(_as_bool(record.get("detected")))
            row["n_linked"] += int(_as_bool(record.get("linked")))
            row["n_scored"] += int(_as_bool(record.get("scored")))
        if usable == 0:
            missing_dimensions.append(dimension)
        curves[dimension] = [_finalize_bin(row) for row in rows]

    return {
        "schema_version": "injection-recovery-curves-v1",
        "n_records": len(records),
        "outcomes": list(_OUTCOMES),
        "passed": bool(records) and not missing_dimensions,
        "curves": curves,
        "missing_dimensions": missing_dimensions,
        "limitations": [
            "Curves summarize synthetic injection records only.",
            "Seeing/background/trail-length curves require image-level injection metadata.",
        ],
    }
