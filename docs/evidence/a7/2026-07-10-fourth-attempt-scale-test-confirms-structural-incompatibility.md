# A7 grouped-split closure attempt — 2026-07-10, fourth pass (18-night scale test; decisive evidence)

## What was run

1. A real bug fix: `assign_night_based_split()`'s object-conflict resolution
   used row-encounter order to pick each object's "canonical" split, but
   `Skills/download_ztf_training_alerts.py` iterates nights most-recent-first,
   so row order is the *reverse* of chronological order. This silently
   picked the latest night instead of the earliest, concentrating leakage
   onto only the earliest (test/validation) nights instead of resolving
   symmetrically. Fixed to determine each object's canonical split from its
   actual chronologically-earliest `night_key` (via the same `_night_sort_key`
   ordering already used to assign nights to splits), independent of row
   order. New regression test
   (`test_assign_night_based_split_uses_chronological_order_not_row_order`)
   constructs a reversed-order fixture matching the real download's row
   order and asserts the fix. 13/13 tests pass, ruff/mypy clean.
2. Scale test: downloaded 18 real distinct nights (90,000 alerts,
   `data/ztf_labeled_alerts_v3.json`, ~5.7GB, 2026-06-22 through 2026-07-09),
   built `data/cutouts_v3/index.csv`, emitted a night-aware grouped split
   (`--split-strategy night`, `train:46606 / validation:21624 / test:21770`),
   and validated it.

## Real result

`Logs/reports/tier2_cnn_v3_grouped_split_report.json`:
`"passed": false`, `n_records: 90000`.

| Metric | 3 nights (40,000 alerts) | 18 nights (90,000 alerts) |
|---|---:|---:|
| `night_key` leaking (of total nights) | 2 / 3 | 15 / 18 |
| `sky_cell` leaking (of unique cells) | not computed | 2,698 / 4,343+ (≈62%) |
| object_id conflict-resolution rows | 2,653 | 10,382 (11.5% of all rows) |

Both leakage axes got **relatively worse**, not better, at 18 nights versus
3 nights (15/18 = 83% of nights leak vs 2/3 = 67% at the smaller scale).

## Why: a real, quantified data characteristic, not a bug

```
total distinct objects:            73,560
objects seen on >1 distinct night:  7,645  (10.4%)
```

10.4% of real objects in this real/bogus training population (dominated by
variable stars and other recurring real sources, not one-off transients)
are detected on more than one of the 18 nights. Every one of those objects
forces every night it touches into the split of its *earliest* appearance
-- and because there are far more "later" nights (15) than "earlier" ones
(3, by construction of a chronological test/validation/train ordering), the
contamination spreads to most of the later nights. **More data does not
fix this: more nights strictly increases the chance any given object is
seen on nights that fall in different splits.** This is the opposite of
what the previous chosen direction ("acquire more nights") assumed would
happen, and the real numbers now confirm it.

Separately, `sky_cell` leakage (~62% of unique 1-degree cells appear in
more than one split) is explained by ZTF's routine field-revisit cadence
(the survey deliberately reobserves the same sky positions every few
nights) -- also does not improve with a longer time window, for the same
reason: a longer window means more revisits, not fewer.

## Conclusion

Simultaneous `object_id` + `night_key` + `sky_cell` purity, as currently
required by `Skills/validate_grouped_splits.py`'s `passed` field, is not
achievable for this project's real ZTF training data via any splitting
strategy that also preserves `object_id` purity -- not with 3 nights, not
with 18, and (by the same repeat-detection/revisit-cadence argument) not
with substantially more. This is now empirically decisive, not a guess:
two independently-designed split strategies (object-random, whole-night)
were tried across two real data scales (3 nights, 18 nights), and the
tension held in both, in the direction predicted by the underlying survey
physics.

## Status

`grouped_split_report_missing` blocker: **still open**. Four real,
non-fabricated attempts on real data are now documented in
`docs/evidence/a7/`. The remaining decision is a policy call: which purity
axis(es) should be a hard gate for this data modality, and which should be
a reported/monitored metric -- not something further code iteration on the
splitter can resolve. Flagged to the operator with a recommendation rather
than continuing to guess at splitter variants.
