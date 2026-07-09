# Canonical Regression Evals

A5 requires sample-level regression reports before model-promotion claims. The
runner in `Skills/run_canonical_evals.py` evaluates JSON suites with cases for:

- `known_neo_recovery`
- `false_link`
- `injection_recovery`
- `review_packet`

Each case cites a `dataset_id`, provides inline `observed` JSON or an
`observed_path`, and defines checks with `path`, `operator`, and `expected`.
Supported operators are `eq`, `ne`, `gte`, `lte`, `gt`, `lt`, and `contains`.

Example:

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/run_canonical_evals.py \
  data_selection/canonical_evals/example_suite.json
```

This scaffold does not close A5 by itself. A5 closes only when the project has
frozen, policy-grade suites covering known NEO detections, false-link examples,
injected moving-source controls, and review-packet examples with committed
manifest IDs.
