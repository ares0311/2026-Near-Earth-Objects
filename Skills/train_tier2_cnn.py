#!/usr/bin/env python3
"""Fine-tune the Tier 2 CNN on labeled ZTF cutout data.

Reads a CSV produced by Skills/build_cutout_dataset.py with columns
``cutout_path`` (.npz file) and ``label`` (int 0–4 matching NEOPosterior).

Three key design choices vs. the naive implementation:

1. NLLLoss(log(output)) instead of CrossEntropyLoss — the TripleCNN model in
   classify.py ends with nn.Softmax, so its output is already a probability
   distribution.  CrossEntropyLoss internally applies LogSoftmax a second time,
   producing double-softmax / numerical instability.  We use NLLLoss with an
   explicit log() instead.

2. Class-weighted loss — ZTF real/bogus data is typically ~85/15 real/bogus.
   Without weighting the model learns to predict "real" for everything and
   achieves 85% accuracy while being useless for artifact rejection.  Weights
   are computed from the training split only (not the val split) to avoid leakage.

3. Mini-batch DataLoader + a grouped train/validation/test split (A4) —
   stochastic mini-batch updates (batch_size 32) converge much faster than
   sample-at-a-time updates, and grouping by real ZTF object_id (not a plain
   random split) guarantees the same physical detection series never appears
   in both train and validation/test. Requires a labels CSV with
   object_id/jd/ra_deg/dec_deg columns from Skills/build_cutout_dataset.py
   fed by Skills/download_ztf_training_alerts.py's provenance-capturing fix;
   legacy datasets without those columns fall back to singleton per-row
   groups (no leakage guarantee) with a printed warning.

4. PyTorch MPS device selection + configurable --num-workers — this script
   previously never selected a device at all (silently CPU-only even on
   MPS-capable hardware) and hardcoded num_workers=0 (single-threaded
   .npz loading). Both are now fixed per docs/SYSTEM_PROFILE.md's mandatory
   device-selection rule. CutoutDataset had to move from a function-local
   class to module level for DataLoader worker processes to pickle it.
   Note: a genuinely sandboxed execution environment may block BOTH MPS
   (torch.backends.mps.is_available() returns False) AND multiprocess
   DataLoader workers (torch_shm_manager needs shared-memory socket access
   the sandbox denies) -- if so, this falls back to
   --num-workers 0 --device cpu automatically/explicitly and trains
   correctly, just much slower; run on an unsandboxed terminal for the
   real speedup.

5. Optional synthetic hard-negative augmentation (--n-hard-negatives) —
   added 2026-07-12 after tier2_cnn_v3 was REJECTED for showing 100%
   false-discovery on a synthetic sub-pixel-artifact adversarial test
   (docs/evidence/a7/2026-07-12-cnn-adversarial-false-discovery.md) versus
   15.5% for benchmark_cnn_v1. Reuses
   Skills/evaluate_cnn_false_discovery.py's exact artifact-synthesis math
   (not reimplemented, to avoid drift) to generate N additional
   stellar_artifact-labeled triplets on the fly, with sigma drawn from a
   configurable range rather than one fixed extreme case, so the model
   learns a genuine shape-discrimination boundary. Off by default
   (--n-hard-negatives 0) -- this is an explicit opt-in, not a silent
   change to existing training behavior. These are clearly synthetic,
   provenance-tagged examples, never real archived detections; they are
   added to the training split only, never validation/test, so reported
   val_loss/val_acc always reflect real data only. See
   docs/evidence/a7/2026-07-12-model-rejected-retune-required.md for the
   full rationale and retune plan.

Usage:
    PYTHONPATH=src caffeinate -i python Skills/train_tier2_cnn.py \\
        --labels data/cutouts/index.csv \\
        --epochs 20 \\
        --out models/tier2_cnn.pt

    # Audit the split before training (A4/A7 evidence):
    PYTHONPATH=src python Skills/train_tier2_cnn.py \\
        --labels data/cutouts/index.csv \\
        --emit-split-csv data/cutouts/grouped_split.csv
    PYTHONPATH=src python Skills/validate_grouped_splits.py \\
        data/cutouts/grouped_split.csv > grouped_split_report.json
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from pathlib import Path
from typing import Any

# Ensure src/ modules (classify.py etc.) are importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# Ensure this script's own directory (Skills/) is importable regardless of
# invocation style (direct script run already puts it on sys.path[0], but
# pytest module-loading via importlib does not) -- needed for the
# hard-negative augmentation's reuse of evaluate_cnn_false_discovery.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from grouped_splits import load_grouped_split_gate

# Human-readable names for the 5 NEOPosterior classes (index = label int)
LABEL_NAMES = [
    "neo_candidate",        # 0 — real ZTF detection
    "known_object",         # 1
    "main_belt_asteroid",   # 2
    "stellar_artifact",     # 3 — bogus ZTF detection
    "other_solar_system",   # 4
]


def assign_grouped_split(
    rows: list[dict], *, val_fraction: float, test_fraction: float, seed: int
) -> tuple[list[str], int]:
    """Assign each row to train/validation/test by real object_id group.

    Rows sharing the same real ZTF `object_id` (the broker's persistent
    per-sky-position identifier -- see
    Skills/download_ztf_training_alerts.py) are always assigned to the same
    split, so the same physical detection series can never appear in both
    train and validation/test. This replaces the prior `random_split()`,
    which had no such guarantee and could leak the same object across
    splits when a short download window (e.g. `--nights 3`) produces
    multiple alerts for the same object.

    Returns (assignments, n_rows_missing_object_id), aligned with `rows`
    order. Rows without a usable `object_id` (e.g. legacy datasets
    downloaded before this fix) each form their own singleton group -- a
    fallback that avoids crashing, not a leakage guarantee; the caller
    should warn loudly when this count is nonzero.
    """
    import random

    groups: dict[str, list[int]] = {}
    n_missing = 0
    for idx, row in enumerate(rows):
        object_id = (row.get("object_id") or "").strip()
        if not object_id:
            n_missing += 1
            object_id = f"__no_object_id_row_{idx}"
        groups.setdefault(object_id, []).append(idx)

    group_keys = sorted(groups)  # deterministic order before shuffling
    rng = random.Random(seed)
    rng.shuffle(group_keys)

    n_total = len(rows)
    target_val = max(1, int(round(val_fraction * n_total)))
    target_test = max(1, int(round(test_fraction * n_total)))

    assignments = ["train"] * n_total
    n_val_assigned = 0
    n_test_assigned = 0
    for key in group_keys:
        indices = groups[key]
        if n_test_assigned < target_test:
            split = "test"
            n_test_assigned += len(indices)
        elif n_val_assigned < target_val:
            split = "validation"
            n_val_assigned += len(indices)
        else:
            break  # remaining groups stay "train" (already the default)
        for idx in indices:
            assignments[idx] = split

    return assignments, n_missing


def assign_night_based_split(
    rows: list[dict], *, val_fraction: float, test_fraction: float
) -> tuple[list[str], dict[str, Any]]:
    """Assign whole calendar nights to train/validation/test, then resolve
    any object_id conflicts a whole-night assignment creates.

    `assign_grouped_split()` (object_id-only) guarantees object purity but
    lets a given night's alerts scatter across every split, which fails
    Skills/validate_grouped_splits.py's night_key hard-leakage check whenever
    the source data spans few distinct nights (see
    docs/evidence/a7/2026-07-10-second-attempt-object-id-split-still-leaks-night-and-sky.md).
    This function assigns entire nights to entire splits instead, using the
    exact same `night_key` derivation the validator uses (imported from
    grouped_splits, not reimplemented, to avoid drift), so night purity is
    guaranteed by construction. Nights are consumed chronologically test,
    then validation, then train, tracking *record* counts (not night counts)
    against val_fraction/test_fraction so split sizes stay close to the
    requested ratio even when nights have uneven alert counts.

    Whole-night assignment alone does not guarantee object_id purity: a real
    object detected across two nights assigned to different splits would
    still leak. Resolved by keeping every row for a given object_id in the
    split of that object's chronologically *earliest* night (determined by
    actual night_key order, not row order -- an earlier implementation
    assumed row order was chronological, but
    Skills/download_ztf_training_alerts.py iterates nights most-recent-first,
    which silently inverted which occurrence "won" and produced leakage only
    on the earliest nights; see
    docs/evidence/a7/2026-07-10-fourth-attempt-object-conflict-resolution-used-file-order-not-chronological-order.md),
    moving any later-night rows for the same object into that earliest
    split and counting how many rows this displaced.

    Returns (assignments, diagnostics) where diagnostics reports per-night
    split assignment and the object-conflict-resolution count, so callers
    can print this instead of silently reshaping the requested split sizes.
    """
    from collections import Counter

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from grouped_splits import _night_key  # reuse the validator's own key, not a copy

    night_of_idx = [_night_key(row) for row in rows]
    counts = Counter(night_of_idx)

    def _night_sort_key(night: str) -> tuple[int, str]:
        if night.startswith("jdnight:"):
            return (0, f"{int(night.split(':', 1)[1]):020d}")
        return (1, night)  # non-standard/explicit night keys sort after, stably

    nights_sorted = sorted(counts, key=_night_sort_key)

    n_total = len(rows)
    target_test = max(1, round(test_fraction * n_total))
    target_val = max(1, round(val_fraction * n_total))

    night_split: dict[str, str] = {}
    running_test = 0
    running_val = 0
    for night in nights_sorted:
        n_records = counts[night]
        if running_test < target_test:
            night_split[night] = "test"
            running_test += n_records
        elif running_val < target_val:
            night_split[night] = "validation"
            running_val += n_records
        else:
            night_split[night] = "train"

    assignments = [night_split[night] for night in night_of_idx]

    # Determine each object's canonical split from its chronologically
    # earliest night, independent of row order in the input CSV.
    object_earliest_night: dict[str, str] = {}
    for idx, row in enumerate(rows):
        object_id = (row.get("object_id") or "").strip() or f"__no_object_id_row_{idx}"
        night = night_of_idx[idx]
        current_earliest = object_earliest_night.get(object_id)
        if current_earliest is None or _night_sort_key(night) < _night_sort_key(current_earliest):
            object_earliest_night[object_id] = night

    n_reassigned = 0
    for idx, row in enumerate(rows):
        object_id = (row.get("object_id") or "").strip() or f"__no_object_id_row_{idx}"
        canonical_split = night_split[object_earliest_night[object_id]]
        if assignments[idx] != canonical_split:
            assignments[idx] = canonical_split
            n_reassigned += 1

    diagnostics = {
        "strategy": "night",
        "n_nights": len(nights_sorted),
        "night_split_counts": {
            night: {"split": split, "n_records": counts[night]}
            for night, split in night_split.items()
        },
        "n_reassigned_for_object_conflict": n_reassigned,
    }
    return assignments, diagnostics


def write_grouped_split_csv(rows: list[dict], assignments: list[str], out_path: Path) -> None:
    """Write a CSV matching Skills/validate_grouped_splits.py's input contract."""
    fieldnames = [
        "sample_id",
        "split",
        "label",
        "object_id",
        "jd",
        "ra_deg",
        "dec_deg",
        "source_key",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row, split in zip(rows, assignments, strict=True):
            candidate_id = row.get("candidate_id") or row.get("cutout_path", "")
            writer.writerow(
                {
                    "sample_id": candidate_id,
                    "split": split,
                    "label": row.get("label", ""),
                    "object_id": row.get("object_id") or candidate_id,
                    "jd": row.get("jd", ""),
                    "ra_deg": row.get("ra_deg", ""),
                    "dec_deg": row.get("dec_deg", ""),
                    "source_key": row.get("source_key") or "ZTF:P48",
                }
            )


def _load_cutout_npz(npz_path: str):  # noqa: ANN201
    """Load a single .npz cutout triplet as three (1,63,63) float32 tensors.

    Returns (science, reference, difference) each shaped (1, H, W) where the
    leading 1 is the channel dimension expected by the ConvBranch modules.
    The DataLoader will stack these into (B, 1, H, W) batches automatically.
    """
    import numpy as np
    import torch

    data = np.load(npz_path)
    # Replace any NaN/Inf with 0 before converting to tensor.
    # ZTF FITS cutouts can have NaN pixels (bad/masked regions); a single NaN
    # propagates through all conv layers, makes the loss NaN on the first batch,
    # corrupts weights with NaN gradients, and keeps loss NaN for every epoch.
    sci = torch.from_numpy(
        np.nan_to_num(data["science"], nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    ).unsqueeze(0)   # (63,63) → (1,63,63) channel dim
    ref = torch.from_numpy(
        np.nan_to_num(data["reference"], nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    ).unsqueeze(0)
    diff = torch.from_numpy(
        np.nan_to_num(data["difference"], nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    ).unsqueeze(0)
    return sci, ref, diff


def _build_dataset(rows: list[dict]) -> Any:
    """Wrap a list of CSV rows in a torch Dataset.

    `CutoutDataset` must be a module-level class (not nested inside this
    function) so DataLoader worker processes can pickle it -- a
    function-local class raised `_pickle.PicklingError` the moment
    `--num-workers` was set above 0, which is why every DataLoader in this
    file previously ran single-threaded regardless of machine core count.
    """
    return CutoutDataset(rows)


class CutoutDataset:
    """torch Dataset over cutout CSV rows; must stay picklable (see
    _build_dataset's docstring) for multiprocess DataLoader workers."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> tuple[Any, Any, Any, Any]:
        import torch

        row = self.rows[idx]
        sci, ref, diff = _load_cutout_npz(row["cutout_path"])
        label = torch.tensor(int(row["label"]), dtype=torch.long)
        return sci, ref, diff, label


# Label index for "stellar_artifact" in LABEL_NAMES -- every synthetic
# hard-negative generated by SyntheticArtifactDataset is tagged with this.
_STELLAR_ARTIFACT_LABEL = LABEL_NAMES.index("stellar_artifact")


class SyntheticArtifactDataset:
    """torch Dataset generating synthetic hard-negative (stellar_artifact)
    cutout triplets on the fly -- no npz files written to disk. Must stay
    picklable (see CutoutDataset's docstring) for multiprocess DataLoader
    workers.

    Reuses Skills/evaluate_cnn_false_discovery.py's
    _synthesize_artifact_cutout_arrays (the exact math behind the
    adversarial test that rejected tier2_cnn_v3) rather than reimplementing
    it, so "the model was trained against the same artifact shape it will
    later be graded on" is true by construction, not by coincidence. Each
    sample draws its own sigma from `sigma_range` (not one fixed value) so
    training exposes a continuum of spike widths, teaching a genuine
    shape-discrimination boundary instead of memorizing one parameter.
    Every sample is deterministic given (seed, idx) for reproducibility.
    """

    def __init__(
        self,
        n_samples: int,
        seed: int = 0,
        sigma_range: tuple[float, float] = (0.05, 0.35),
    ) -> None:
        self.n_samples = n_samples
        self.seed = seed
        self.sigma_min, self.sigma_max = sigma_range

    def __len__(self) -> int:
        return self.n_samples

    def __getitem__(self, idx: int) -> tuple[Any, Any, Any, Any]:
        import numpy as np
        import torch
        from evaluate_cnn_false_discovery import _synthesize_artifact_cutout_arrays

        rng = np.random.default_rng(self.seed + idx)
        sigma_px = float(rng.uniform(self.sigma_min, self.sigma_max))
        mag = float(rng.uniform(18.0, 21.0))
        background_level = float(rng.uniform(2.0, 40.0))
        sci_arr, ref_arr, diff_arr, _real_bogus = _synthesize_artifact_cutout_arrays(
            rng, mag, background_level, sigma_px=sigma_px
        )

        def _to_tensor(arr: Any) -> Any:
            return torch.from_numpy(
                np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
            ).unsqueeze(0)

        sci, ref, diff = _to_tensor(sci_arr), _to_tensor(ref_arr), _to_tensor(diff_arr)
        label = torch.tensor(_STELLAR_ARTIFACT_LABEL, dtype=torch.long)
        return sci, ref, diff, label


def _compute_class_weights(
    rows: list[dict], extra_label_counts: dict | None = None
) -> Any:
    """Compute inverse-frequency class weights for NLLLoss.

    Only classes that appear in `rows` (plus any nonzero `extra_label_counts`
    entries, e.g. synthetic hard negatives added outside `rows`) contribute;
    unused classes get weight 1.0 so they don't produce NaN gradients if the
    model ever predicts them. `extra_label_counts` lets callers fold in
    counts that never had a real CSV row (SyntheticArtifactDataset), so
    weights reflect the true combined training composition, not just the
    real-data split. Returns a torch.Tensor of shape (n_classes,).
    """
    from collections import Counter

    import torch

    counts: Counter[int] = Counter(int(r["label"]) for r in rows)
    if extra_label_counts:
        for cls, n in extra_label_counts.items():
            if n:
                counts[int(cls)] += int(n)
    total = sum(counts.values())
    n_present = len(counts)

    weights = torch.ones(len(LABEL_NAMES))
    for cls, count in counts.items():
        # Balanced inverse-frequency: total / (n_classes_present * count)
        weights[cls] = total / (n_present * count)
    return weights


def train(labels_csv: str, epochs: int, out_path: str, lr: float,
          batch_size: int, val_fraction: float, test_fraction: float,
          num_workers: int = 4, n_hard_negatives: int = 0,
          hard_negative_sigma_range: tuple[float, float] = (0.05, 0.35),
          hard_negative_seed: int = 0) -> None:
    """Train the Tier 2 CNN and save the best checkpoint by val loss.

    Per docs/SYSTEM_PROFILE.md's mandatory device-selection rule ("All
    tensor data must be moved to the device explicitly"), this now targets
    PyTorch MPS/Metal when available and falls back to CPU with an explicit
    printed report -- previously this script never selected a device at
    all, so it silently ran CPU-only even on hardware with a working GPU.

    `n_hard_negatives > 0` mixes in that many synthetic stellar_artifact
    hard negatives (see SyntheticArtifactDataset) into the TRAINING split
    only -- validation/test stay real-data-only so reported val_loss/val_acc
    remain comparable across model versions.
    """
    import torch
    import torch.nn as nn
    from torch.utils.data import ConcatDataset, DataLoader, Subset

    from classify import _build_cnn_model

    device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
    fallback_note = "" if device.type == "mps" else "  (CPU fallback — MPS unavailable)"
    print(f"Device: {device}{fallback_note}")

    model = _build_cnn_model()
    if model is None:
        print("ERROR: torch not available — cannot train CNN.")
        return
    model = model.to(device)

    # Load all CSV rows
    with open(labels_csv) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("ERROR: empty labels CSV")
        return

    # A4 grouped split by real object_id (see assign_grouped_split docstring):
    # the same physical detection series can never appear in both train and
    # validation/test, unlike the prior random_split(). The held-out "test"
    # split is excluded from training entirely; it exists for independent
    # evaluation (Skills/evaluate_calibration.py or similar), not for this
    # script to consume.
    assignments, n_missing_object_id = assign_grouped_split(
        rows, val_fraction=val_fraction, test_fraction=test_fraction, seed=42
    )
    if n_missing_object_id:
        print(
            f"WARNING: {n_missing_object_id}/{len(rows)} rows have no real "
            "object_id (legacy dataset predating Skills/download_ztf_training_alerts.py's "
            "provenance fix). Each was treated as its own singleton group — "
            "this does NOT protect against leakage for these specific rows."
        )
    train_indices = [i for i, a in enumerate(assignments) if a == "train"]
    val_indices = [i for i, a in enumerate(assignments) if a == "validation"]
    test_indices = [i for i, a in enumerate(assignments) if a == "test"]
    if not train_indices or not val_indices:
        print("ERROR: grouped split produced an empty train or validation set.")
        return

    dataset = _build_dataset(rows)
    train_ds: Any = Subset(dataset, train_indices)
    val_ds = Subset(dataset, val_indices)
    n_train = len(train_indices)
    n_val = len(val_indices)
    print(
        f"Grouped split: {n_train} train / {n_val} validation / "
        f"{len(test_indices)} test (held out, unused here)"
    )

    # Compute class weights from training rows only (avoid val leakage)
    train_rows = [rows[i] for i in train_ds.indices]
    extra_label_counts = {_STELLAR_ARTIFACT_LABEL: n_hard_negatives} if n_hard_negatives else None
    class_weights = _compute_class_weights(train_rows, extra_label_counts=extra_label_counts)

    # Optional hard-negative augmentation (see SyntheticArtifactDataset):
    # concatenated onto the TRAINING split only -- val_ds/n_val are computed
    # above and untouched, so val_loss/val_acc always reflect real data only.
    if n_hard_negatives > 0:
        synthetic_ds = SyntheticArtifactDataset(
            n_hard_negatives, seed=hard_negative_seed, sigma_range=hard_negative_sigma_range
        )
        # SyntheticArtifactDataset deliberately does not subclass
        # torch.utils.data.Dataset -- this module keeps `import torch`
        # lazy (function-local) so --dry-run/--emit-split-csv work without
        # torch installed; it only needs to satisfy Dataset's structural
        # protocol (__len__/__getitem__), which it does.
        train_ds = ConcatDataset([train_ds, synthetic_ds])  # type: ignore[list-item]
        n_train += n_hard_negatives
        print(
            f"Hard-negative augmentation: +{n_hard_negatives} synthetic "
            f"stellar_artifact triplets (sigma range "
            f"{hard_negative_sigma_range[0]}-{hard_negative_sigma_range[1]} px, "
            f"seed={hard_negative_seed}) -- see "
            "docs/evidence/a7/2026-07-12-model-rejected-retune-required.md"
        )

    # Summarise the split and class balance before starting
    from collections import Counter
    train_counts = Counter(int(r["label"]) for r in train_rows)
    if n_hard_negatives:
        train_counts[_STELLAR_ARTIFACT_LABEL] += n_hard_negatives
    val_counts   = Counter(int(rows[i]["label"]) for i in val_ds.indices)
    print(f"Training on {n_train} samples, validating on {n_val} samples")
    print(f"  Train label counts: { {LABEL_NAMES[k]: v for k, v in sorted(train_counts.items())} }")
    print(f"  Val   label counts: { {LABEL_NAMES[k]: v for k, v in sorted(val_counts.items())} }")
    cw_display = {
        LABEL_NAMES[i]: round(class_weights[i].item(), 3)
        for i in range(len(LABEL_NAMES))
        if class_weights[i] != 1.0 or i in train_counts
    }
    print(f"  Class weights:      {cw_display}")
    print()

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                              num_workers=num_workers, pin_memory=False,
                              persistent_workers=num_workers > 0)
    val_loader   = DataLoader(val_ds, batch_size=batch_size, shuffle=False,
                              num_workers=num_workers, pin_memory=False,
                              persistent_workers=num_workers > 0)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    # NLLLoss is correct here because the model already applies Softmax.
    # CrossEntropyLoss would apply LogSoftmax again (double-softmax bug).
    criterion = nn.NLLLoss(weight=class_weights.to(device))

    best_val_loss = float("inf")
    out_path_obj = pathlib.Path(out_path)
    out_path_obj.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(epochs):
        # ── Training pass ─────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        for sci, ref, diff, label in train_loader:
            sci, ref, diff = sci.to(device), ref.to(device), diff.to(device)
            label = label.to(device)
            optimizer.zero_grad()
            out = model(sci, ref, diff)
            # log() needed because NLLLoss expects log-probabilities;
            # clamp avoids log(0) for any class with Softmax output near zero.
            loss = criterion(torch.log(out.clamp(min=1e-9)), label)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(label)
        train_loss /= n_train

        # ── Validation pass ───────────────────────────────────────────────────
        model.eval()
        val_loss = 0.0
        n_correct = 0
        with torch.no_grad():
            for sci, ref, diff, label in val_loader:
                sci, ref, diff = sci.to(device), ref.to(device), diff.to(device)
                label = label.to(device)
                out = model(sci, ref, diff)
                loss = criterion(torch.log(out.clamp(min=1e-9)), label)
                val_loss += loss.item() * len(label)
                preds = out.argmax(dim=1)
                n_correct += (preds == label).sum().item()
        val_loss /= n_val
        val_acc = n_correct / n_val

        # Save best checkpoint so we can stop early or resume
        improved = ""
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), out_path)
            improved = "  ← best"

        print(f"  Epoch {epoch + 1:3d}/{epochs}  "
              f"train_loss={train_loss:.4f}  "
              f"val_loss={val_loss:.4f}  "
              f"val_acc={val_acc:.3f}{improved}")

    print()
    print(f"Best val loss: {best_val_loss:.4f}")
    print(f"Saved best weights → {out_path}")


def main() -> None:
    """Parse CLI args, enforce the A4 production-candidate gate, then train."""
    parser = argparse.ArgumentParser(
        description="Train Tier 2 CNN on labeled ZTF cutout dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--labels", required=True,
        help="CSV with cutout_path and label columns (from build_cutout_dataset.py)",
    )
    parser.add_argument("--epochs", type=int, default=20,
                        help="Number of training epochs")
    parser.add_argument("--out", default="models/tier2_cnn.pt",
                        help="Output path for best model checkpoint")
    parser.add_argument("--lr", type=float, default=1e-4,
                        help="Adam learning rate")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Mini-batch size for DataLoader")
    parser.add_argument(
        "--num-workers", type=int, default=4,
        help=(
            "DataLoader worker processes for cutout loading. Previously "
            "hardcoded to 0 (single-threaded), which left most of the "
            "machine's cores idle during .npz loading -- see "
            "docs/SYSTEM_PROFILE.md's local resource-sizing guidance "
            "(start conservative, raise after measuring for this project's "
            "machine). Set 0 to disable multiprocessing entirely."
        ),
    )
    parser.add_argument("--val-fraction", type=float, default=0.2,
                        help="Fraction of data held out for validation")
    parser.add_argument("--test-fraction", type=float, default=0.15,
                        help="Fraction of data held out as a test split (unused by this "
                             "script; carved out for independent evaluation)")
    parser.add_argument(
        "--n-hard-negatives", type=int, default=0,
        help=(
            "Mix N synthetic stellar_artifact hard negatives (sub-pixel "
            "artifact spikes, see SyntheticArtifactDataset) into the "
            "TRAINING split only. Off by default (0) -- explicit opt-in, "
            "added 2026-07-12 after tier2_cnn_v3 was rejected for 100%% "
            "false-discovery on Skills/evaluate_cnn_false_discovery.py's "
            "adversarial test. See "
            "docs/evidence/a7/2026-07-12-model-rejected-retune-required.md."
        ),
    )
    parser.add_argument(
        "--hard-negative-sigma-min", type=float, default=0.05,
        help="Minimum synthetic artifact spike sigma (pixels) for --n-hard-negatives.",
    )
    parser.add_argument(
        "--hard-negative-sigma-max", type=float, default=0.35,
        help=(
            "Maximum synthetic artifact spike sigma (pixels) for --n-hard-negatives. "
            "Kept below real seeing-limited PSF sigma (~0.4-1.1 px at this project's "
            "1.01 arcsec/px cutout scale) so hard negatives never overlap genuine "
            "point-source width and mislabel real detections as artifacts."
        ),
    )
    parser.add_argument(
        "--hard-negative-seed", type=int, default=0,
        help="Seed for synthetic hard-negative generation (reproducibility).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Check the labels CSV and grouped split gate; exit without training.",
    )
    parser.add_argument(
        "--emit-split-csv",
        type=Path,
        default=None,
        help=(
            "Write the real grouped train/validation/test split this run would use "
            "(by object_id, matching Skills/download_ztf_training_alerts.py's "
            "provenance) to this CSV path, in the format "
            "Skills/validate_grouped_splits.py consumes, then exit without training. "
            "Requires --labels to have object_id/jd/ra_deg/dec_deg columns."
        ),
    )
    parser.add_argument(
        "--split-strategy",
        choices=("object", "night"),
        default="object",
        help=(
            "'object' (default) groups by object_id only -- guarantees object "
            "purity but can leak night_key/sky_cell when the source data spans "
            "few distinct nights. 'night' assigns whole calendar nights to "
            "whole splits (then resolves any resulting object_id conflicts), "
            "guaranteeing night_key purity by construction -- needed when "
            "--labels covers only a handful of nights. See "
            "docs/evidence/a7/2026-07-10-second-attempt-object-id-split-still-leaks-night-and-sky.md."
        ),
    )
    parser.add_argument(
        "--grouped-split-report",
        type=Path,
        default=None,
        help=(
            "A4 grouped split leakage report from Skills/validate_grouped_splits.py. "
            "Required when --production-candidate is set."
        ),
    )
    parser.add_argument(
        "--production-candidate",
        action="store_true",
        help=(
            "Fail closed unless policy-grade promotion prerequisites are present. "
            "Currently requires a passing grouped split report."
        ),
    )
    args = parser.parse_args()

    if args.emit_split_csv is not None:
        labels_path = Path(args.labels)
        with labels_path.open() as f:
            rows = list(csv.DictReader(f))
        if not rows:
            print("ERROR: empty labels CSV")
            sys.exit(1)
        if not any(row.get("object_id") for row in rows):
            print(
                "ERROR: --labels has no object_id column populated. "
                "Re-download with Skills/download_ztf_training_alerts.py and rebuild "
                "the cutout index with Skills/build_cutout_dataset.py before emitting "
                "a grouped split — legacy datasets cannot be grouped-split retroactively."
            )
            sys.exit(1)
        if args.split_strategy == "night":
            assignments, diagnostics = assign_night_based_split(
                rows, val_fraction=args.val_fraction, test_fraction=args.test_fraction
            )
            n_missing = 0
        else:
            assignments, n_missing = assign_grouped_split(
                rows, val_fraction=args.val_fraction, test_fraction=args.test_fraction, seed=42
            )
            diagnostics = None
        write_grouped_split_csv(rows, assignments, args.emit_split_csv)
        counts = {s: assignments.count(s) for s in ("train", "validation", "test")}
        print(f"Grouped split CSV written: {args.emit_split_csv}")
        print(f"  strategy: {args.split_strategy}")
        print(f"  counts: {counts}")
        if diagnostics is not None:
            print(f"  nights: {diagnostics['n_nights']}")
            for night, info in sorted(diagnostics["night_split_counts"].items()):
                print(f"    {night}: {info['split']} ({info['n_records']} records)")
            print(
                "  object_id conflict resolution: "
                f"{diagnostics['n_reassigned_for_object_conflict']} rows moved to "
                "their object's first-seen split"
            )
        if n_missing:
            print(f"  WARNING: {n_missing} rows lacked object_id (singleton fallback groups)")
        print(
            "\nNext step:\n"
            f"  uv run --python 3.14 python Skills/validate_grouped_splits.py "
            f"{args.emit_split_csv} > grouped_split_report.json"
        )
        return

    grouped_split_gate = load_grouped_split_gate(args.grouped_split_report)
    if args.grouped_split_report is not None or args.production_candidate:
        print("\nGrouped split gate:")
        print(f"  report     : {grouped_split_gate['path']}")
        print(f"  passed     : {str(grouped_split_gate['passed']).lower()}")
        if grouped_split_gate["blockers"]:
            print(f"  blockers   : {', '.join(grouped_split_gate['blockers'])}")

    if args.production_candidate and not grouped_split_gate["passed"]:
        print("\nERROR: --production-candidate requires a passing grouped split report.")
        sys.exit(1)

    if args.dry_run:
        labels_path = Path(args.labels)
        print(f"\nLabels CSV : {'FOUND' if labels_path.exists() else 'MISSING'} {labels_path}")
        print("Dry run — exiting without training.")
        return

    train(args.labels, args.epochs, args.out, args.lr,
          args.batch_size, args.val_fraction, args.test_fraction,
          num_workers=args.num_workers,
          n_hard_negatives=args.n_hard_negatives,
          hard_negative_sigma_range=(args.hard_negative_sigma_min, args.hard_negative_sigma_max),
          hard_negative_seed=args.hard_negative_seed)


if __name__ == "__main__":
    main()
