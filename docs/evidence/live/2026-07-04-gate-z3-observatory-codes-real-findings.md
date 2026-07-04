# Gate Z3 — real observatory codes for both failed candidate pairs

## Command and real result

```bash
uv run --python 3.14 python Skills/lookup_mpc_observation_history.py \
    --designation 72966 --archive-start-jd 2458273.5 --force-refresh
```

Real, complete result: 1332 total MPC-confirmed observations, 526 in the
ZTF archive's coverage window, each now printed with its real reporting
`observatory` code (v0.90.53/v0.90.54).

## Real observatory codes at the exact reference positions used

**Pair 1: 20220817/20220819** (ref RA/Dec 257.0809/-10.7456 and
257.5497/-10.9843):

| Night | Exact match | mag | observatory |
|---|---|---|---|
| 20220817 (ref, night 1) | RA=257.0809 Dec=-10.7456 | 19.19 (real) | **T05** |
| 20220819 (ref, night 2) | RA=257.5497 Dec=-10.9843 | **99.00 (sentinel)** | **C51** |

**Pair 2: 20210106/20210111** (ref RA/Dec 116.1336/8.6041 and
114.9238/8.8044):

| Night | Exact match | mag | observatory |
|---|---|---|---|
| 20210106 (ref, night 1) | RA=116.1336 Dec=8.6041 | 19.46 (real) | **I41** |
| 20210111 (ref, night 2) | RA=114.9238 Dec=8.8044 | 19.23 (real) | **G96** |

## Interpretation (careful, not over-claimed)

**Pair 1's failure has a clean, well-supported explanation**: the exact
reference position used to center the night-2 alert-archive search
(257.5497, -10.9843) came from an MPC report with `mag=99.00` --
consistent with a sentinel/masked value used elsewhere in this codebase
for missing photometry, not a genuine measured detection. Several other
`observatory=C51` rows for this object also show `mag=99.00` (e.g.
20180714, 20180715, 20220818). A low-quality or placeholder position
reference is a poor anchor for a 2-degree search box, independent of
which specific survey reported it.

**Pair 2's failure is NOT as cleanly explained by report quality**: both
reference positions have real, plausible magnitudes (19.46 and 19.23) --
neither looks like a placeholder. They do come from two different
observatory codes (`I41` vs `G96`), which is a real, confirmed fact, but
different observatories reporting real astrometric detections should
still each be close to the object's true position (professional
observatories are generally sub-arcsec to few-arcsec precision) -- so
"different station" alone does not fully explain a 35-arcmin gap. The
original, simpler hypothesis from
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-third-attempt.md`
(a real sky-imaging pass existing does not guarantee a confident
`rb >= 0.5` alert-level detection at that exact sub-position) remains a
plausible, unresolved contributor here, alongside the different-station
observation.

**Do not over-generalize the observatory-code finding**: comparing the
successful (close) raw-observation matches from
`docs/evidence/live/2026-07-04-gate-z3-raw-observation-check-inconclusive.md`
and `docs/evidence/live/2026-07-04-gate-z3-second-pair-no-match-plus-observatory-fix.md`,
the *close* matches came from `T05` (pair 1, night 1) and `I41` (pair 2,
night 1) -- two different codes. Neither `T05` nor `I41` can be assumed
to be "ZTF's own code" from this evidence alone; this project has not
independently verified which MPC station code corresponds to ZTF, and no
guess is made here. It is equally plausible that any precise, real
astrometric report (regardless of reporting survey) tends to be near a
real ZTF-imaged position most nights, simply because ZTF surveys the
whole visible sky every ~3 nights.

## What is now confirmed, well-supported, and actionable

1. **Real, direct, confirmed finding**: a real fix (v0.90.53/v0.90.54)
   now surfaces every MPC report's reporting-observatory code and can
   distinguish real photometric detections (real mag) from sentinel/
   placeholder entries (mag=99.00).
2. **Actionable filter for future candidate-pair selection**: exclude
   MPC reports with `mag >= 90` (sentinel/placeholder) from candidate
   reference-position selection in `scan_mpc_history_ztf_coverage.py` --
   this is real, direct, and would have avoided pair 1's night-2 anchor.
   Not yet implemented in this PR; recommended for a follow-up.
3. **Not yet resolved**: pair 2's failure (both real-magnitude reports,
   different stations) remains unexplained by data quality alone. This
   could reflect either genuine ZTF non-detection that specific night, or
   an as-yet-unverified station/precision effect.

## Recommendation for next session

Given 5 real apparitions of designation 72966 have now been checked
across this project (20180809/20180810/20180812/20180902/20180903 in
earlier sessions, plus the two full 2-night pairs this session) without
a confirmed clean two-night positive control, continuing to probe this
exact designation may have diminishing returns. Two productive paths
forward, in order of effort:

1. **Cheap, immediate**: filter `scan_mpc_history_ztf_coverage.py`'s
   candidate selection to exclude `mag >= 90` sentinel reports before
   trying a third apparition of 72966.
2. **More substantial**: select a different, well-observed real NEO
   designation entirely (via the same MPC-history-scan methodology) for
   the Gate Z3 positive control, rather than continuing to exhaust
   apparitions of a single object.

Either way, the mechanical exercise itself is already a real, valuable
result: `detect()`/`link()`/`preprocess()` correctly process real
archived ZTF alert data end-to-end and form real cross-night tracklets
(546 formed across the two attempted pairs combined) -- the remaining gap
is confirming one specific tracklet's identity against a known object,
not whether the pipeline mechanics work on real data.
