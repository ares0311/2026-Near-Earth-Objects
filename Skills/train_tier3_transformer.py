#!/usr/bin/env python3
"""Train and evaluate the Tier 3 Transformer with reproducible evidence.

The input CSV files are produced by ``Skills/build_sequence_dataset.py``.
Training selects the checkpoint with the lowest validation loss and evaluates
that checkpoint once on the held-out test split. The JSON report records source
hashes, class counts, metrics, model hash, and the pilot-only promotion state.

Usage:
    caffeinate -i .venv/bin/python Skills/train_tier3_transformer.py \
        --train data/sequences/pilot/train.csv \
        --validation data/sequences/pilot/calibration.csv \
        --test data/sequences/pilot/test.csv \
        --epochs 30 \
        --out models/tier3_transformer.pt \
        --report data/sequences/pilot/tier3_training_report.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LABEL_NAMES = [
    "neo_candidate",
    "known_object",
    "main_belt_asteroid",
    "stellar_artifact",
    "other_solar_system",
]
_N_FEATURES = 5
REPORT_SCHEMA_VERSION = "tier3-training-report-v1"


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for training provenance."""
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    """Hash one training artifact without loading it fully into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_to_tensor(row: dict[str, str]) -> Any | None:
    """Convert one flat token row into a non-padded ``(1, T, 5)`` tensor."""
    import numpy as np
    import torch

    token_keys = [key for key in row if re.match(r"^tok_\d+_\d+$", key)]
    if not token_keys:
        return None
    max_time = max(int(key.split("_")[1]) for key in token_keys) + 1
    sequence = np.zeros((max_time, _N_FEATURES), dtype=np.float32)
    for key in token_keys:
        _, time_text, feature_text = key.split("_")
        sequence[int(time_text), int(feature_text)] = float(row[key])
    sequence = sequence[sequence.any(axis=1)]
    if sequence.shape[0] < 2:
        return None
    return torch.from_numpy(sequence).unsqueeze(0)


def _load_examples(path: Path) -> list[tuple[Any, int]]:
    """Load one split and fail closed on malformed rows or missing classes."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"empty Tier 3 split: {path}")

    examples: list[tuple[Any, int]] = []
    counts: Counter[int] = Counter()
    for row_index, row in enumerate(rows, start=2):
        try:
            label = int(row["label"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid label at {path}:{row_index}") from exc
        if label not in range(len(LABEL_NAMES)):
            raise ValueError(f"unsupported label {label} at {path}:{row_index}")
        sequence = _row_to_tensor(row)
        if sequence is None:
            raise ValueError(f"insufficient sequence at {path}:{row_index}")
        examples.append((sequence, label))
        counts[label] += 1

    missing = [LABEL_NAMES[label] for label in range(len(LABEL_NAMES)) if not counts[label]]
    if missing:
        raise ValueError(f"Tier 3 split is missing classes: {missing}")
    return examples


def _classification_metrics(labels: list[int], predictions: list[int]) -> dict[str, Any]:
    """Compute accuracy, macro-F1, and per-class recall without hidden averaging."""
    if not labels or len(labels) != len(predictions):
        raise ValueError("labels and predictions must be non-empty and aligned")

    per_class_recall: dict[str, float] = {}
    per_class_f1: list[float] = []
    for class_index, class_name in enumerate(LABEL_NAMES):
        true_positive = sum(
            actual == class_index and predicted == class_index
            for actual, predicted in zip(labels, predictions, strict=True)
        )
        false_positive = sum(
            actual != class_index and predicted == class_index
            for actual, predicted in zip(labels, predictions, strict=True)
        )
        false_negative = sum(
            actual == class_index and predicted != class_index
            for actual, predicted in zip(labels, predictions, strict=True)
        )
        recall_denominator = true_positive + false_negative
        precision_denominator = true_positive + false_positive
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        precision = true_positive / precision_denominator if precision_denominator else 0.0
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        per_class_recall[class_name] = recall
        per_class_f1.append(f1)

    return {
        "accuracy": sum(
            actual == predicted
            for actual, predicted in zip(labels, predictions, strict=True)
        )
        / len(labels),
        "macro_f1": sum(per_class_f1) / len(per_class_f1),
        "per_class_recall": per_class_recall,
    }


def _example_class_counts(examples: list[tuple[Any, int]]) -> dict[str, int]:
    """Return stable human-readable class counts for one prepared split."""
    counts = Counter(label for _sequence, label in examples)
    return {
        class_name: counts[class_index]
        for class_index, class_name in enumerate(LABEL_NAMES)
    }


def _evaluate(model: Any, examples: list[tuple[Any, int]], criterion: Any) -> dict[str, Any]:
    """Evaluate one split using logits and return transparent classification metrics."""
    import torch

    model.eval()
    total_loss = 0.0
    labels: list[int] = []
    predictions: list[int] = []
    with torch.no_grad():
        for sequence, label in examples:
            logits = model(sequence)
            target = torch.tensor([label], dtype=torch.long)
            total_loss += float(criterion(logits, target).item())
            labels.append(label)
            predictions.append(int(torch.argmax(logits, dim=1).item()))
    return {
        "loss": total_loss / len(examples),
        **_classification_metrics(labels, predictions),
    }


def _default_model_factory() -> Any:
    """Construct the production Transformer lazily after ``src`` is importable."""
    import sys

    src_path = Path(__file__).resolve().parent.parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    from classify import _build_transformer_model

    model = _build_transformer_model()
    if model is None:
        raise RuntimeError("torch is not available; cannot train Tier 3")
    return model


def train(
    train_csv: Path,
    validation_csv: Path,
    test_csv: Path,
    *,
    epochs: int,
    out_path: Path,
    report_path: Path,
    learning_rate: float = 1e-4,
    seed: int = 42,
    model_factory: Callable[[], Any] = _default_model_factory,
) -> dict[str, Any]:
    """Train the best validation checkpoint and emit held-out test evidence."""
    if epochs < 1:
        raise ValueError("epochs must be at least 1")
    if learning_rate <= 0:
        raise ValueError("learning_rate must be positive")

    import numpy as np
    import torch
    import torch.nn as nn

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    train_examples = _load_examples(train_csv)
    validation_examples = _load_examples(validation_csv)
    test_examples = _load_examples(test_csv)

    model = model_factory()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss()
    best_validation_loss = float("inf")
    best_epoch = 0
    best_state: dict[str, Any] | None = None
    history: list[dict[str, Any]] = []

    for epoch in range(1, epochs + 1):
        model.train()
        shuffled = list(train_examples)
        random.Random(seed + epoch).shuffle(shuffled)
        total_loss = 0.0
        for sequence, label in shuffled:
            target = torch.tensor([label], dtype=torch.long)
            optimizer.zero_grad()
            logits = model(sequence)
            loss = criterion(logits, target)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())

        validation_metrics = _evaluate(model, validation_examples, criterion)
        epoch_record = {
            "epoch": epoch,
            "train_loss": total_loss / len(shuffled),
            "validation": validation_metrics,
        }
        history.append(epoch_record)
        print(
            f"Epoch {epoch}/{epochs} "
            f"train_loss={epoch_record['train_loss']:.4f} "
            f"val_loss={validation_metrics['loss']:.4f} "
            f"val_macro_f1={validation_metrics['macro_f1']:.4f}"
        )
        if validation_metrics["loss"] < best_validation_loss:
            best_validation_loss = validation_metrics["loss"]
            best_epoch = epoch
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }

    if best_state is None:
        raise RuntimeError("training produced no checkpoint")
    model.load_state_dict(best_state)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_path)
    test_metrics = _evaluate(model, test_examples, criterion)
    train_counts = _example_class_counts(train_examples)
    validation_counts = _example_class_counts(validation_examples)
    test_counts = _example_class_counts(test_examples)
    total_counts = {
        class_name: (
            train_counts[class_name]
            + validation_counts[class_name]
            + test_counts[class_name]
        )
        for class_name in LABEL_NAMES
    }
    pilot_only = min(total_counts.values()) < 200

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at_utc": _utc_now(),
        "seed": seed,
        "epochs_requested": epochs,
        "best_epoch": best_epoch,
        "learning_rate": learning_rate,
        "model_path": str(out_path),
        "model_sha256": _sha256_file(out_path),
        "source_splits": {
            "train": {
                "path": str(train_csv),
                "sha256": _sha256_file(train_csv),
                "examples": len(train_examples),
                "class_counts": train_counts,
            },
            "validation": {
                "path": str(validation_csv),
                "sha256": _sha256_file(validation_csv),
                "examples": len(validation_examples),
                "class_counts": validation_counts,
            },
            "test": {
                "path": str(test_csv),
                "sha256": _sha256_file(test_csv),
                "examples": len(test_examples),
                "class_counts": test_counts,
            },
        },
        "combined_class_counts": total_counts,
        "best_validation": history[best_epoch - 1]["validation"],
        "test": test_metrics,
        "history": history,
        "acceptance_targets": {
            "validation_accuracy_min": 0.85,
            "test_macro_f1_min": 0.80,
        },
        "pilot_acceptance_passed": (
            history[best_epoch - 1]["validation"]["accuracy"] >= 0.85
            and test_metrics["macro_f1"] >= 0.80
        ),
        "pilot_only": pilot_only,
        "production_promotion_allowed": False,
        "safety": {
            "external_submission_enabled": False,
            "impact_probability_generated": False,
            "secret_values_recorded": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Saved best epoch {best_epoch} weights -> {out_path}")
    print(f"Saved held-out metrics -> {report_path}")
    return report


def main() -> None:
    """Parse the production-oriented Tier 3 training command."""
    parser = argparse.ArgumentParser(
        description="Train Tier 3 and emit validation/test evidence."
    )
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("models/tier3_transformer.pt"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/sequences/pilot/tier3_training_report.json"),
    )
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    train(
        args.train,
        args.validation,
        args.test,
        epochs=args.epochs,
        out_path=args.out,
        report_path=args.report,
        learning_rate=args.lr,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
