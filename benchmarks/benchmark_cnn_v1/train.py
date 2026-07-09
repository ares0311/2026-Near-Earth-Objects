"""Training entrypoint wrapper for the frozen Tier 2 CNN benchmark.

This file preserves the original training defaults as the benchmark recipe.
Future training changes should create a new benchmark version or be compared
against this one through the promotion gates.
"""

from __future__ import annotations

from Skills.train_tier2_cnn import train as train_tier2_cnn

# The current benchmark was trained with the historical Tier 2 defaults.
DEFAULT_LABELS_CSV = "data/cutouts/index.csv"
DEFAULT_OUTPUT = "models/tier2_cnn.pt"
DEFAULT_EPOCHS = 20
DEFAULT_BATCH_SIZE = 32
DEFAULT_LEARNING_RATE = 1e-4
DEFAULT_VALIDATION_FRACTION = 0.2
DEFAULT_RANDOM_SEED = 42


def train_benchmark() -> None:
    """Re-run the historical benchmark recipe when the private data is present."""
    train_tier2_cnn(
        labels_csv=DEFAULT_LABELS_CSV,
        epochs=DEFAULT_EPOCHS,
        out_path=DEFAULT_OUTPUT,
        lr=DEFAULT_LEARNING_RATE,
        batch_size=DEFAULT_BATCH_SIZE,
        val_fraction=DEFAULT_VALIDATION_FRACTION,
    )
