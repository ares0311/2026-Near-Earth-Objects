"""Model wrapper for the frozen Tier 2 CNN benchmark.

The benchmark deliberately wraps the existing `classify.py` implementation so
production inference and benchmark inference share one architecture definition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from classify import _build_cnn_model, _load_cnn_model

# Stable identifier used by policy docs, model cards, and future eval reports.
BENCHMARK_ID = "benchmark_cnn_v1"

# Keep the large weight artifact in the already-allowlisted production model path.
MODEL_ARTIFACT = Path("models/tier2_cnn.pt")

# The five outputs match NEOPosterior field order used by classify._tier2_predict.
LABELS = (
    "neo_candidate",
    "known_object",
    "main_belt_asteroid",
    "stellar_artifact",
    "other_solar_system",
)


def build_model() -> Any:
    """Return the frozen benchmark architecture without loading weights."""
    return _build_cnn_model()


def load_model() -> Any:
    """Load the committed benchmark weights through the production-safe loader."""
    return _load_cnn_model()


def benchmark_metadata() -> dict[str, Any]:
    """Return the small metadata contract future evals should cite."""
    return {
        "benchmark_id": BENCHMARK_ID,
        "model_artifact": str(MODEL_ARTIFACT),
        "artifact_sha256": (
            "981a59f6935c51ec66321cd171a4e74d8ac58eaf6fd73ca0e84f79c0ea3218ec"
        ),
        "input_shape": [3, 63, 63],
        "labels": list(LABELS),
        "architecture_source": "src/classify.py::_build_cnn_model",
        "loader_source": "src/classify.py::_load_cnn_model",
        "production_status": "benchmark_only_not_production_promoted",
    }
