# T1-C Option A: Predeclared Screening + Prequalification Policy

**Date declared:** 2026-06-20
**Approved by:** Jerome W. Lindsey III (verbal approval 2026-06-20 session)
**ATLAS query budget:** up to 160 queries total (screening + follow-up combined)
**External submission authorized:** false
**Impact-probability claim authorized:** false

---

## Why This Run Is Needed

Two prior ATLAS recovery runs failed the T1-C ≥90% known-object recovery KPI:

- `atlas_recovery_4eaf93e87f6c`: 4/11 objects recovered (36.36%) — screening run
- `atlas_recovery_175ef40ac577`: 3/4 objects recovered (75.00%) — prequalified follow-up

Root cause of the follow-up failure: the source manifest had 3 ephemeris samples for
asteroid 2973 (JD 2461180, 2461187, 2461194). ATLAS had no archived images at the
sky position on JD 2461187 and JD 2461194, so 2 of 3 samples returned 0 raw
observations. With only 1 recovered sample, 2973 could not form a multi-night
tracklet and was counted as unmatched by the audit.

This was a genuine ATLAS sky-coverage gap — not a tool failure, timeout, or
manifest position error.

---

## Predeclared Rule (must not be modified after any query is submitted)

### Step 1 — Source Manifest

Build the source manifest with:

- **--samples 6** (6 ephemeris points per object spread across the date window)
- **--max-objects 25** (screen up to 25 known objects)
- Date window: 30 days bracketing current date, chosen from
  `Skills/select_survey_fields.py --mode recovery --top-n 3 --json` output

Using 6 samples per object (vs 3 previously) ensures that even if 2–3 source JDs
lack ATLAS coverage, there are still enough covered JDs to pass prequalification.

### Step 2 — Screening Run

Run `Skills/fetch_atlas_data.py --expected-known <source_manifest>` against the
source manifest. Budget: up to ~100 queries (25 objects × ~4 expected covered JDs
on average from 6 source JDs each, factoring ~50% ATLAS nightly sky coverage).

### Step 3 — Prequalification

Run `Skills/build_recovery_manifest.py --prequalify-from-atlas-run` against the
screening run checkpoint with:

- **--prequalified-min-recovered-samples 3**
- **--prequalified-min-nights 2**

Objects that do not have ≥3 recovered ATLAS samples across ≥2 distinct nights in
the screening run are excluded from the denominator. This rule is fixed before the
follow-up run begins.

### Step 4 — Follow-up Run

Run `Skills/fetch_atlas_data.py --expected-known <prequalified_manifest>` against
the prequalified manifest. Budget: up to ~60 queries.

Because the prequalified manifest preserves the source manifest's JDs, and the
screening run already confirmed ATLAS coverage at those JDs, the follow-up is
expected to recover the same samples deterministically.

### Step 5 — Audit

Run `Skills/audit_real_run.py` against the follow-up run directory with the
prequalified manifest as `--expected-known`. The audit computes the KPI against
the prequalified denominator only.

---

## KPI Gate

| Metric | Threshold |
|---|---|
| Known-object recovery rate | ≥ 90% of prequalified objects form multi-night tracklets |
| External submission | false (not authorized) |
| Impact-probability claim | false (not authorized) |

A result below 90% does not close T1-C. A result at or above 90% closes T1-C
subject to citizen-science operator false-positive review (T2-C).

---

## Safety Constraints

- No MPC submission
- No NEOCP escalation
- No NASA PDCO notification
- No impact-probability statement
- Operator runs all commands locally on main branch after `git pull origin main`
