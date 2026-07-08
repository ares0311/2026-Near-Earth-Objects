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
