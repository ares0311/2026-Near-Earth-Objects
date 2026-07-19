# Phase 2 Ranking Eligibility — 2026-07-19

## Scope and result

This is the first bounded Phase 2 work unit after the operator explicitly
closed Phase 1. It hardens field eligibility before ranking; it does not close
Phase 2 or claim Hunter PROD.

`Skills/select_survey_fields.py` now has two explicit stages:

- planning: deterministic analytic ranking over the tessellated sky grid;
- eligible selection: `new` or `follow-up` selection from a versioned,
  metadata-only field/night coverage inventory, joined to the committed target
  provenance queue by normalized coordinates before scoring.

The selector rejects fields below the inventory's three-distinct-night
minimum. `new` excludes any coordinate with a preserved terminal outcome;
`follow-up` requires one. Missing or malformed eligibility inputs fail loudly.
The output preserves the exact coverage nights, raw-response hash, batch ID,
batch-manifest hash, threshold, and prior-search evidence.

The old `gap_score` label was inaccurate: it was an elongation-based cadence
prior, not measured coverage. It is now `survey_scarcity_score`. The advertised
but nonexistent `Skills/train_field_selector.py` path and silent model fallback
were removed. Ranking remains compact, deterministic, explainable, and does
not depend on AI.

## Behavioral oracle

The regression test uses the real review sequence that exposed the gap:

- rank 4 at RA 211.81 / Dec -7.50 had only two measured nights and is rejected
  before scoring;
- rank 5 at RA 46.59 / Dec +15.00 has sufficient measured nights and remains
  eligible.

Additional tests independently recompute the documented score formula, prove
identical repeated output, prove `new` versus `follow-up` history behavior,
and exercise fail-loud malformed inventory/history controls.

Targeted verification:

```text
uv run --no-sync --python 3.14 ruff check Skills/select_survey_fields.py tests/test_select_survey_fields.py
All checks passed!

uv run --no-sync --python 3.14 python -m pytest tests/test_select_survey_fields.py -q
75 passed in 9.51s
```

Canonical working-tree verification after the implementation and evidence
updates passed all six mandatory gates: directive parity, the silent-exception
gate, incomplete-implementation scanning, ruff, mypy over all 18 `src`
modules, and the full test suite. Result: 2,071 passed, 2 deselected, 100.00%
coverage across all 5,542 `src` statements. The separate adversarial verifier
passed all 46 negative controls. A second canonical run is required after the
commit so REL-05 freshness is tied to the clean immutable repository state.

## Real committed-state replay

The real inventory
`ztf_dr24_new_field_coverage_preflight_v1/807efb0e5ef7d55d` contains six
coverage-qualified fields with 44 to 110 measured nights. Inspection found
that all six had already been processed in run `017eb50381badb75`, with two
completed through cross-batch run `56c2348f31302291`, while their committed
queue rows still said `not_searched`. Terminal evidence rows were appended;
the original planning rows were not edited or deleted.

An offline replay at JD 2461241.5 produced:

```text
new_count: 0
follow_up eligible universe: 6
follow_up observable results: 4
new_ieo_204p25_m07p50: 55 nights, prior null_result
new_ieo_196p68_m07p50: 58 nights, prior null_result
new_aten_243p54_m22p50: 44 nights, prior null_result
new_aten_251p66_m22p50: 46 nights, prior null_result
```

The other two follow-up fields were retained in the eligible universe but were
not observable in the selected `all`-mode geometry at that JD. No download,
external query, submission, alert, or scientific claim occurred.

## Remaining Phase 2 gaps

The committed target queue is an interim provenance input, not the Hunter
durable system of record; Phase 3 remains responsible for the five distinct
durable entities and required CLI. Phase 2 still lacks enough labeled field
outcomes to claim ranking-utility calibration: the five comparable real field
tests are all null/rejected and include no randomized or bottom-ranked control.
The next highest-priority Phase 2 gap is time-aware known-object association in
adversarial eligibility: current live density checks use present-day field
density rather than a replay-cutoff-aware association and can degrade a
provider error to a passing zero count.
