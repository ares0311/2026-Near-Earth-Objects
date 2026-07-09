"""Frozen Tier 2 CNN benchmark package.

This package makes the existing committed CNN artifact a reproducible
benchmark, not a newly promoted production model.
"""

from __future__ import annotations

from .model import BENCHMARK_ID, LABELS, MODEL_ARTIFACT, benchmark_metadata

__all__ = ["BENCHMARK_ID", "LABELS", "MODEL_ARTIFACT", "benchmark_metadata"]
