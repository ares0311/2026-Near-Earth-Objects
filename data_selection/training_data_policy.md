# Training Data Policy

Training data may be used to fit model parameters, tune feature transforms, and
calibrate ranking components. It must not leak future catalog knowledge into a
historical-replay or live-search decision.

Required controls:

- Each training batch must have a manifest with source, acquisition time,
  observation-time bounds, labels, label authority, and known-object catalog
  snapshot or query date.
- Cross-validation splits must be grouped by object identity, field, night, or
  other leakage-relevant key when observations are correlated.
- MPC-numbered objects are high-confidence positives; provisional or broker
  labels require lower trust or explicit justification.
- Pretrained weights must have source, license, input domain, and leakage audit
  notes before use.
- Training metrics do not authorize MPC submission; they only support the
  scoring and review gates.

## CNN Promotion Gate

The Astrometrics coding-agent guide requires the current image model to be
treated as a reproducible benchmark, not as the whole scientific thesis.

Before promoting any CNN or CNN-derived score:

- Freeze the current image model as `benchmark_cnn_v1` or document the exact
  committed model artifact that serves that role.
- Record the training, validation, calibration, and frozen-eval manifest IDs
  used to produce the benchmark.
- Replace random-only train/test splits with grouped splits by object, field,
  night, source, or another leakage-relevant key.
- Maintain separate real-only and synthetic-inclusive evaluation reports.
- Run injection-recovery curves through the downstream detection/link/scoring
  path, not only image-chip accuracy.
- Run the canonical evaluation suite and compare against the frozen CNN
  benchmark before claiming improvement.
- If pretrained weights or embeddings are used, complete a pretrained-model
  audit covering source, license, input domain, preprocessing reproducibility,
  and leakage risk.
- Keep CNN output as an artifact/image-quality feature unless a later
  production decision documents why an end-to-end CNN detector is scientifically
  justified.

Current repository state: `benchmarks/benchmark_cnn_v1/` freezes
`models/tier2_cnn.pt` as the benchmark artifact. This closes the freeze step
only; it does not close grouped splits, leakage checks, injection-recovery
curves, or CNN production promotion.

Grouped split state: `src/grouped_splits.py` and
`Skills/validate_grouped_splits.py` provide the initial A4 leakage controls for
object identity, observing night, sky cell, and survey/instrument context.
Future training and frozen-eval reports must cite the emitted grouped-split
JSON report before making any promotion claim.
