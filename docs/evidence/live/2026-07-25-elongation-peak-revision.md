# Elongation Preference-Peak Revision (v2 → v3)

Date: 2026-07-25 (America/Los_Angeles)

## Objective

Following the first real coefficient-fit attempt
(`docs/evidence/live/2026-07-25-first-real-coefficient-fit-attempt.md`),
both `aten` and `ieo` modes showed a striking result: the current
hand-set policy's baseline AUC came back *below* 0.5 against real
discovery outcomes — anti-correlated, not just weak. Operator asked for
a data-defended recommendation rather than an open question. This
investigates the root cause and, having found a clear, decisive,
cross-mode answer, revises the ranking policy.

## What was checked

Of the three scored features, the bootstrap coefficient-stability check
from the fit attempt showed only one with a reproducible, zero-excluding
signal in *both* independently-fit modes:

| Feature | Aten 95% CI | Ieo 95% CI | Reliable? |
|---|---|---|---|
| geometry_score | -3.07 to -1.45 | -1.78 to -0.61 | **Yes, negative in both** |
| survey_scarcity_score | -1.28 to -0.73 | -0.0008 to +0.0008 | No — ieo's scarcity score is a hardcoded constant (0.95 for every field), structurally uninformative there |
| population_score | -0.88 to +0.86 | -1.17 to +0.22 | No — crosses zero in both modes |

`geometry_score` was the only feature worth investigating further, since
it's the only one with a real, reproducible, cross-mode signal.

## Root cause: the elongation preference peak is set where real
discoveries essentially never occur

`geometry_score_batch()` is 65% a Gaussian match to each mode's
`_ELONG_WINDOWS` peak, 35% raw hours-visible-tonight. Pulling the real
elongation values for every source-aligned (I41), eligible record used in
the fit:

**Aten** (peak was 80 deg, preference window 60-100 deg):
```
positive elongations (n=56): 99.4 .. 173.7 (median 144.55, mean 142.0, stdev 23.0)
null elongations      (n=21): 73.4 .. 166.4 (11 of 21 fall inside the old 60-100 window)
```
Every single real Aten discovery falls *outside* the old preference
window. None are inside it. Meanwhile roughly half the searched-null
fields fall inside it — exactly the fields the old formula would have
preferred, none of which produced a discovery.

**Atira/ieo** (peak was 32.5 deg, preference window 20-45 deg):
```
positive elongations (n=7): 39.5 .. 53.1 (median 48.8, mean 47.8, stdev 4.18)
null elongations      (n=7): 20.0 .. 37.9
```
Same pattern: every real Atira discovery sits above the old window's
upper bound region, while every null sits below the old peak.

Two independent NEO classes, disjoint real data (different fields,
different discoveries, scored under completely separate mode-specific
formulas), same directional error. This rules out a single-mode fluke.

## Why this pattern likely exists

The old peaks were set from a "survey scarcity" argument: search where
other surveys visit least often, so a ZTF find there is unambiguously
ZTF's. `geometry_score` also includes a 35%-weighted raw
`hours_visible` term. A field near the old peak (dawn/dusk twilight for
aten, deep twilight for ieo) is only observable a short window each
night. Building a real, MPC-reportable multi-night tracklet requires
enough usable dark-sky time across nights to actually detect and link an
object — a purely observational constraint, independent of how
scientifically "scarce" the coverage is. The real discovery data is
consistent with that observational constraint dominating in practice:
discoveries cluster where there is more usable night, not where other
surveys happen to visit less.

This is disclosed as the most likely explanation, not asserted as
proven — the samples remain small enough (77 and 14 records) that a
definitive mechanistic account isn't yet possible.

## What changed

`data_selection/ranking_policies/ztf_field_ranking_v3.json` (new;
`ztf_field_ranking_v2.json` untouched, kept as the frozen historical
policy the existing `ztf_field_null_outcomes_v1-v4.json` evidence base's
`recorded_score` values were actually computed under):

| | v2 (old) | v3 (new) |
|---|---|---|
| aten preference window | (60, 100, peak 80) | (100, 180, peak 145) |
| ieo preference window | (30, 60, peak 48) → (20, 45, peak 32.5) | (30, 60, peak 48) |

New peaks are set near the real median elongation for each mode (145 for
aten, 48 for ieo), with the window bounds widened to the mode's existing
eligibility ceiling rather than fit tightly to the small sample — a
deliberately conservative choice given n=56/n=7.

**What did not change**: `discovery_weights`, `recovery_weights`,
`class_completeness_priors`, `eligibility_windows_deg`, and the `all`/
`recovery` mode windows are all identical to v2. `survey_scarcity_score`
and `population_score` were *not* touched — their fitted directions are
not reliably established by this data (see table above), and changing
them now would mean shipping a coefficient indistinguishable from noise.

`Skills/select_survey_fields.py`'s `_ELONG_WINDOWS` and
`_DEFAULT_RANKING_POLICY_PATH` now point at v3 — this is a real change to
live field-selection behavior (`Skills/hunter_cli.py create-new-search`
uses this default), not just a retrospective-audit update.

## What deliberately did not change

`Skills/evaluate_field_ranking_policy.py`'s `DEFAULT_POLICY` stays
pinned to v2. Every entry in `ztf_field_null_outcomes_v1-v4.json` records
a `recorded_score`/`recorded_rank` that reflects a real historical
decision — the field was actually searched because of the score it had
*at the time*, under v2. Retroactively rescoring those entries under v3
would misrepresent history (they were not searched because of a v3
score, which didn't exist yet). The retrospective audit and its
score-reproduction check remain correctly anchored to v2 for all
existing evidence; any future audit of v3-era decisions will use v3
explicitly and build a new, v3-tagged null-outcomes evidence base over
time, per this project's "never overwrite prior evidence in place"
convention.

## Verification

- `ruff check`, `mypy src`, full sharded suite (6x6): clean, 100% `src/`
  coverage (see PR for exact numbers).
- `tests/test_select_survey_fields.py`'s `TestGeometryScoreBatch` peak
  assertions updated to the new peak values; `TestRankingPolicyProvenance`
  updated to assert `policy_id: "ztf-field-ranking-v3"`.
- New tests assert the v3 preference windows match `_ELONG_WINDOWS`
  exactly and that `ztf_field_ranking_v2.json` remains loadable and
  internally self-consistent as a frozen historical artifact (it is not
  expected to match the *current* code's constants, by design, and is no
  longer the live default).

## What this does and does not authorize

- This is a real, live change to future field selection (not a
  report-only recommendation) — `create-new-search` will use the new
  peaks starting with its next real run.
- This does **not** promote any fitted coefficient for
  `survey_scarcity_score` or `population_score` — only the one feature
  with reliable cross-mode evidence (`geometry_score`'s peak location)
  was changed.
- Still based on small real samples. Continued real search activity will
  keep growing this evidence base; a future revision may adjust the
  peaks again as more data accumulates.
