"""Scoring wrapper for the frozen Tier 2 CNN benchmark."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from classify import _tier2_predict
from schemas import OptScore, Tracklet


def score_tracklet(
    tracklet: Tracklet,
    model: Any = None,
    predict_fn: Callable[[Tracklet, Any], dict[str, OptScore] | None] = _tier2_predict,
) -> dict[str, OptScore] | None:
    """Score one tracklet through the frozen Tier 2 prediction contract."""
    return predict_fn(tracklet, model)
