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

Example (illustrative, synthetic inline data — not policy-grade evidence):

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/run_canonical_evals.py \
  data_selection/canonical_evals/example_suite.json
```

## Frozen production suite

`production_suite_v1.json` is the policy-grade suite for A5. Every case's
`observed_path` points at a real, already-committed evidence artifact — no
inline synthetic data:

| Case type | Evidence source |
|---|---|
| `injection_recovery` | `data/injection_recovery_n200.json` — real n=200, seed=42 synthetic-injection baseline (100% detection/link/score) |
| `false_link` | `Logs/reports/ranking_baseline.json` — Gate Z4 evidence: 142 real archived negative tracklets + 200 synthetic positives; the handcrafted logistic-regression baseline achieves perfect purity@K with 0 false positives, vs. the naive real-bogus-only ablation's purity@5=0.0 |
| `review_packet` | `Logs/reports/retrospective_validation.json` — Gate Z6 evidence: 88 real review packets from archived ZTF data, retrospectively checked against the live MPC catalog (all correctly bucketed as `artifact`) |
| `known_neo_recovery` | `docs/evidence/canonical_evals/known_neo_recovery_72966_no_match.json` — a real known-NEO recovery *attempt* (designation 72966, Gate Z3) that did **not** confirm a match; the check only guards against a future regression that would silently treat a multi-degree offset as a match. It is not a positive recovery and must not be read as one. |

Run it:

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/run_canonical_evals.py \
  data_selection/canonical_evals/production_suite_v1.json
```

This closes A5 for model-builder-independent regression protection over the
project's real evidence artifacts. It does not close A7 (real model-specific
promotion evidence) or Gate Z3 (a confirmed known-NEO recovery remains open
and intentionally paused).
