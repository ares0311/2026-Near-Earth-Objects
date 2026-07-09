# benchmark_cnn_v1 Model Card

## Status

`benchmark_cnn_v1` freezes the existing Tier 2 CNN as a reproducible benchmark.
It is **not production-promoted** and must not be used as the main scientific
claim for NEO discovery. Its current role is an image/artifact feature source
and a measuring stick for future model changes.

## Frozen Artifact

- Benchmark ID: `benchmark_cnn_v1`
- Weight artifact: `models/tier2_cnn.pt`
- Artifact SHA-256:
  `981a59f6935c51ec66321cd171a4e74d8ac58eaf6fd73ca0e84f79c0ea3218ec`
- Architecture source: `src/classify.py::_build_cnn_model`
- Loader source: `src/classify.py::_load_cnn_model`
- Training recipe source: `Skills/train_tier2_cnn.py`

The benchmark wraps the existing committed artifact rather than copying it into
this directory. That keeps the repository artifact policy exact-file allowlist
intact while still providing a stable benchmark package.

## Inputs And Preprocessing

- Input planes: science, reference, difference.
- Shape: `3 x 63 x 63`.
- Dtype: `float32`.
- Alert cutouts: base64-encoded raw `float32` arrays decoded with
  `classify._decode_cutout_f32`.
- Persisted cutouts: `.npz` files with `science`, `reference`, and
  `difference` arrays.
- Non-finite pixels: `NaN`, positive infinity, and negative infinity are
  replaced with `0.0`.

## Architecture

The benchmark uses the repository's existing three-branch CNN: one convolutional
branch each for the science, reference, and difference planes, merged into a
dense head with five posterior outputs:

- `neo_candidate`
- `known_object`
- `main_belt_asteroid`
- `stellar_artifact`
- `other_solar_system`

## Historical Training Record

The historical Tier 2 training record in the repository reports:

- Training data: 10,000 real ZTF cutout triplets under the local
  `data/cutouts/` workspace.
- Split: random 80/20 split with seed `42`.
- Epochs: `20`.
- Optimizer: Adam.
- Learning rate: `1e-4`.
- Loss: class-weighted `NLLLoss` over clamped softmax probabilities.
- Reported validation loss: `0.258`.
- Reported validation accuracy: `91.3%`.

These metrics are historical benchmark metrics only. Random-split accuracy does
not authorize production promotion, MPC submission, or impact-probability
language.

## Known Limitations

- The historical split is random-only and therefore diagnostic, not
  policy-grade.
- The benchmark does not yet cite separate training, validation, calibration,
  and frozen-eval manifest IDs.
- The benchmark has not yet been evaluated with grouped object, field, night,
  and source splits.
- The benchmark has not yet been validated through downstream moving-source
  injection-recovery curves.
- Synthetic-inclusive and real-only evaluation reports are not yet separated.
- Pretrained-weight use remains deferred unless a future audit records source,
  license, input domain, preprocessing reproducibility, and leakage risk.

## Promotion Requirements

Before any CNN-derived score can be described as production-promoted, the repo
must complete the remaining Astrometrics gates:

- A4 grouped NEO splits and leakage checks.
- A5 canonical sample-level regression evals.
- A6 downstream injection-recovery curves by magnitude, velocity, trail length,
  seeing/background, and missed frames.
- A7 calibration and promotion report citing manifests, split definitions,
  frozen evals, injection-recovery evidence, calibration quantiles, and
  false-discovery estimates.

## Safety

This benchmark never confirms a NEO, never asserts impact probability, and never
authorizes external submission. MPC submission remains gated by adversarial
review, operator review, and the repository submission policy.
