# Phase 2 ranking-policy provenance evidence — 2026-07-19

## Objective

Make the field selector's exact scientific policy reconstructable and prevent
coverage or coefficient provenance gaps from appearing as production-ready
ranking evidence.

## Audit finding

`Skills/select_survey_fields.py` cited Granvik et al. (2018), Ye et al. (2020),
and Harris & D'Abramo (2015) immediately above the exact
35/30/20/15 scoring formula and described several hard-coded curves and class
completeness values as derived from those works. The sources support the
feature directions:

- Granvik et al. provides debiased NEO orbital, absolute-magnitude, and source
  distributions.
- Ye et al. demonstrates ZTF twilight searches at low solar elongation.
- Harris & D'Abramo provides a population-completeness methodology based on
  discovery and re-detection statistics.

They do **not** provide this selector's exact weights, exponentials, windows,
or per-class completeness constants. The old source comments therefore
overstated scientific provenance.

Primary sources:

- [Granvik et al. 2018](https://doi.org/10.1016/j.icarus.2018.04.018)
- [Ye et al. 2020](https://arxiv.org/abs/1912.06109)
- [Harris & D'Abramo 2015](https://doi.org/10.1016/j.icarus.2015.05.004)

## Implementation

- Added the checked-in policy
  `data_selection/ranking_policies/ztf_field_ranking_v1.json`.
- The policy records the exact discovery/recovery weights, elongation windows,
  class-completeness priors, eligibility thresholds, source support boundaries,
  and limitations.
- Its coefficient status is explicitly
  `uncalibrated_transparent_prior`; it cannot be mistaken for a calibrated
  probability model or literature-fitted formula.
- Every selected row now contains the policy schema, ID, SHA256, portable path,
  coefficient status, and limitations.
- Runtime validation fails if the policy is missing, malformed, mislabels its
  model/status, lacks support boundaries, or drifts from the implementation.
- Production coverage inventory validation now requires a non-empty batch ID,
  a 64-hex batch-manifest digest, and a 64-hex raw-response digest per field.
  Missing provenance can no longer flow into an eligible result as `null`.
- No AI dependency was introduced and ranking remains deterministic.

## Verification

Focused command:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python -m pytest \
  tests/test_select_survey_fields.py -q
```

Result: **88 passed**. Negative controls cover coefficient drift, false
calibration status, schema/model/ID drift, missing support boundaries,
missing limitations, malformed/missing policies, and missing batch/per-field
digests.

Deterministic planning replay:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/select_survey_fields.py --jd 2461000.5 --mode aten --top-n 1 --json
```

Result: 579 candidates scored, 169 observable, one selected. Its output stamps
policy `ztf-field-ranking-v1`, SHA256
`27c4b3776088eb09acc8061aae1aee271121c106ccf808d4e88a501d92a4363f`,
and all three calibration limitations.

Canonical working-tree verification passed all six mandatory stages: **2,101
passed, 2 deselected, 100.00% coverage across all 5,545 `src` statements**.
Clean-commit freshness and GitHub CI are recorded in the PR handoff.

## Remaining Phase 2 blocker

The policy is now honest and reproducible, but its exact coefficients still
lack leakage-safe empirical calibration. Phase 2 cannot close on source
citation and unit-test behavior alone. A defensible calibration set needs
historical field outcomes with identities resolved as of each replay cutoff,
including positive recoveries/discoveries and eligible null fields. The current
repo has several real null fields but no comparable frozen positive field set.
SkyBoT, the bounded epoch-specific association source already integrated for
this purpose, returned HTTP 500 for both documented live probes on 2026-07-19.

Do not claim these coefficients are calibrated. After provider recovery, build
and freeze the leakage-safe calibration set, fit or replace the weights, and
add rank-order/out-of-sample regression oracles. Phase 3 remains blocked.
