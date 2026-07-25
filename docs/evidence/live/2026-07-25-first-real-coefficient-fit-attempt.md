# First Real Field-Ranking Coefficient Fit Attempt

Date: 2026-07-25 (America/Los_Angeles)

## Objective

Operator decision (2026-07-25, "A" of a three-way choice): now that both
`aten` and `ieo` modes jointly clear `MINIMUM_SAMPLE_THRESHOLDS`
(`evaluate_field_ranking_policy.py`'s `coefficient_promotion_gate`),
actually attempt a real coefficient fit rather than leaving the
deterministic `uncalibrated_transparent_prior` policy untouched
indefinitely.

## What was built

- `Skills/evaluate_field_ranking_policy.py`: removed the deliberate
  tripwire (`if coefficient_update_authorized: raise ValueError(...)`)
  that previously forced a crash the moment both modes qualified. That
  crash's job — stopping automated progress until a human explicitly
  decided how to proceed — is done; the operator has now decided. The
  audit function returns normally, reporting
  `decision: "coefficient_fit_attempt_authorized"`.
- `Skills/fit_field_ranking_coefficients.py` (new): fits a per-mode
  logistic regression on the same three features the existing formula
  already scores (`survey_scarcity_score`, `population_score`,
  `geometry_score`) against real outcome (positive discovery vs. searched
  null), restricted to the same `source_aligned_ztf_i41` + `eligible`
  subset the gate itself counts. Uses leave-one-out cross-validation
  (appropriate given how small these samples still are — refits on n-1
  points and predicts the held-out one, for every point) rather than
  k-fold, and bootstrap-resamples 500 times to check whether the fitted
  coefficients are stable (same sign, similar magnitude) across resamples.
  **Never writes to the production ranking policy file** — it only
  produces a report; a `promotion_candidate: true` result is a
  recommendation to review, not an automatic promotion.

## Real bug found and fixed before the first correct result

The first real run reported `n_positive: 2017` for aten and `17` for ieo
— both far too large. Root cause: `build_fit_report()` filtered
`records` by `ranking_mode` only, forgetting the
`source_aligned_ztf_i41` filter the gate itself applies before counting.
This meant every accepted MPC discovery (2,085 for aten, most of them
from non-ZTF stations) was being used as a "positive" example, not just
the 57/7 real ZTF-attributed ones. Fixed by filtering
`audit_result["records"]` to `source_aligned_ztf_i41` before splitting by
mode. A new regression test asserts the fitter's counts stay within the
gate's own `observed_counts` for both modes.

## Real result

`Logs/pipeline_runs/field_ranking_calibration/coefficient_fit_report_v1.json`
(gitignored; summarized here):

| Mode | n_positive | n_null | Baseline (current policy) AUC | Fit LOO AUC | Improvement | Promotion candidate |
|---|---:|---:|---:|---:|---:|---|
| aten | 56 | 21 | 0.364 | 0.618 | +0.254 | **True** |
| ieo | 7 | 7 | 0.082 | 0.633 | +0.551 | **True** |

Both modes' bootstrap coefficient stability succeeded at 100% (500/500
resamples fit cleanly), and both fits' 95% confidence intervals exclude
zero for `geometry_score` (both modes) and `survey_scarcity_score` (aten
only) — the coefficients are not just noise from a lucky resample.

## The finding that needs explicit interpretation before any promotion

**The current hand-set policy's baseline AUC is below 0.5 for both
modes** — 0.364 for aten, and a striking 0.082 for ieo. An AUC below 0.5
does not mean "no signal"; it means the score is *anti-correlated* with
the real outcome on this sample: fields the current formula ranks higher
are, if anything, less likely to be the ones with a real discovery than
fields it ranks lower, on this specific real data.

This is **not** by itself proof the hand-set formula is wrong in general.
Two real, unresolved possibilities, disclosed rather than picked between:

1. **Sample composition confound**: the searched-null set mixes
   deliberately top-ranked fields (6 of the original 9 v1 entries) with a
   stratified top/middle/bottom/random sample (this session's 15 new
   entries). If most nulls happen to be high-scoring (many *are*,
   including several rank-1/2/3 fields) while the real positives are
   scattered across the whole score range (real discoveries don't
   necessarily cluster where this formula expects), an AUC well below 0.5
   can emerge from that imbalance alone, independent of whether the
   formula's underlying reasoning is actually backwards.
2. **The formula may genuinely be miscalibrated** for at least one of its
   three components, and a real anti-correlation exists.

Both `aten` and `ieo` samples remain small (77 and 14 real records
respectively) — small enough that this specific numeric baseline AUC
should be treated as a real, reportable observation, not yet a settled
fact about the formula's validity in general.

## What this does and does not authorize

- **No coefficient has been promoted or applied.** The active ranking
  policy (`data_selection/ranking_policies/ztf_field_ranking_v2.json`)
  and its live behavior in `Skills/select_survey_fields.py` /
  `Skills/hunter_cli.py` are completely unchanged.
- `promotion_candidate: true` for both modes is the fitter's own
  mechanical output (LOO AUC clears baseline by the required margin,
  bootstrap succeeded) — it is a recommendation to review, explicitly
  not a promotion, per this project's non-negotiable "never lower quality
  gates silently" and "calibration promotion is KPI-based, requiring
  operator review" rules.
- The anti-correlated baseline finding above is exactly the kind of
  result that needs a human decision on how to interpret it before going
  further — analogous to the CNN promotion workflow's own operator-review
  step (`Skills/build_promotion_report.py --operator-signoff-id`), which
  this coefficient-fitting path does not yet have an equivalent of.

## Verification

- `ruff check`, `mypy src`, full sharded suite (6x6): all clean, 100%
  `src/` coverage.
- 16 tests across `test_evaluate_field_ranking_policy.py` (tripwire
  removal) and `test_fit_field_ranking_coefficients.py` (new), including
  a synthetic oracle test (strong signal correctly recovered), a
  no-improvement-possible test (baseline already perfect →
  `promotion_candidate: False`), and a regression guard for the
  source-alignment count bug above.

## Exact next work

An explicit operator decision on how to interpret the anti-correlated
baseline AUC finding before any further action:
1. Investigate whether the searched-null sample's composition (top-ranked
   bias) explains the low baseline AUC on its own, independent of whether
   the formula itself needs revision.
2. If the finding holds up under scrutiny, decide whether to design a
   promotion/sign-off workflow for the fitted coefficients (mirroring
   `build_promotion_report.py`), gather more real data first, or take some
   other path.
3. Continue treating the deterministic `uncalibrated_transparent_prior`
   policy as the live, unchanged production ranker until any of the above
   is explicitly decided and reviewed.
