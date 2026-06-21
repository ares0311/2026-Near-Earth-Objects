# Console Output Specification — NEO Detection Pipeline

**Established**: 2026-06-21
**Applies to**: `Skills/run_pipeline.py` and any future pipeline runner scripts

---

## Purpose

This spec defines the exact console output format for all pipeline runs so that
the operator can monitor progress, estimate completion time, and identify
candidates requiring escalation — without reading log files.

---

## Run Header

Every run must print a header block before any stage output:

```
══════════════════════════════════════════════════════════════════
  NEO Detection Pipeline — <MODE>
  Run ID  : <12-char param key>
  Field   : RA=<ra>°  Dec=<dec>°  r=<radius>°
  Window  : JD <start_jd> – <end_jd>  (<n_days> days)
  Surveys : <SURVEY1> <SURVEY2> ...
  Started : <YYYY-MM-DD HH:MM:SS UTC>
══════════════════════════════════════════════════════════════════
```

`<MODE>` is one of:
- `DRY RUN  (no external submissions will be made)` — when `dry_run=True`
- `LIVE RUN  ⚠  alerts enabled` — when `dry_run=False`

---

## Stage Prefix Format

Every progress line must begin with a bracketed stage tag followed by a space:

```
[fetch]      Querying ...
[preprocess] ...
[detect]     ...
[link]       progress 120/500 seed pairs; tracklets=4; elapsed 0m12s  ETA 0m38s
[classify]   Classifying tracklet NEO-00001
[orbit]      Fitting orbit for NEO-00001
[score]      Scoring NEO-00001
[alert]      Processing alert for NEO-00001
[neocp]      Monitoring NEOCP for NEO-00001 (timeout=2.0h)
[resume]     Checkpoint found (last stage: link); resuming from last completed stage.
[resume]     Reloading 12 tracklets from checkpoint (skipping fetch / preprocess / detect / link).
[resume]     Skipping already-processed NEO-00001
[cache]      Deleted 3 cache file(s) from .neo_cache/
[audit]      Run summary written to Logs/pipeline_runs/<key>/run_summary.json
```

Stage tags are lowercase and left-justified within 12 characters when printed
inline with a description, but exact spacing is not required — a single space
after `]` is sufficient.

---

## ETA Format

For any stage that loops over items, the progress line must include:

```
elapsed {M}m{S:02d}s  ETA {M}m{S:02d}s
```

where `M` is whole minutes and `S` is seconds within the minute (zero-padded).
ETA must be computed from a measurable quantity (items processed / total).
Elapsed-only heartbeats are **not** acceptable as a substitute for ETA.

Example (link stage):
```
[link] progress 240/500 seed pairs; tracklets=7; elapsed 0m24s  ETA 0m26s
```

---

## Retry Output

On transient network failure, each retry must be announced before the sleep:

```
[fetch] Network error: <exc>  (attempt <N>/<MAX>; retry in <wait>s...)
```

After all retries are exhausted, the error propagates and the run exits with
a non-zero status.

---

## Candidate Escalation Notice

When a candidate passes `ready_for_submission()` (MOID ≤ 0.05 AU, quality ≥ 2,
rb ≥ 0.90, pathway ≠ known_object), print a prominent block **immediately after
the `[alert]` line** for that tracklet:

```
┌─────────────────────────────────────────────────────────────────┐
│  ⚠  SUBMISSION CANDIDATE: <object_id>
│     MOID    : <moid_au> AU
│     RB score: <rb>
│     Pathway : <alert_pathway>
│     Priority: <discovery_priority>
│     TODO: Escalation path not yet implemented — see
│           docs/MPC_SUBMISSION_POLICY.md §TODO for future agents
└─────────────────────────────────────────────────────────────────┘
```

This block must appear on stdout regardless of dry_run mode, since operator
awareness of a high-quality candidate is always required.

In `dry_run=True` mode, additionally print:
```
[alert] DRY RUN — no external submission performed.
```

---

## Run Footer

After all tracklets are processed:

```
──────────────────────────────────────────────────────────────────
  Pipeline complete.
  Candidates processed : <N>
  Submission-ready     : <N_ready>
  Elapsed              : <M>m<S>s
──────────────────────────────────────────────────────────────────
```

where `N_ready` is the count of candidates that passed `ready_for_submission()`.

---

## Mode Warning

When `dry_run=False` (LIVE RUN), print a warning immediately before the first
`[fetch]` line:

```
[alert] ⚠  LIVE MODE — external submissions are ENABLED.
[alert]    Guardrails: no impact-probability claims; no direct PDCO contact.
[alert]    All submissions require quality gates to pass (see alert.py).
```

---

## Prohibited Output

- **Never** print `"confirmed NEO"` for any internally detected object.
- **Never** state or imply an impact probability.
- **Never** print a raw Python traceback without a stage-prefixed context line
  before it.
- **Never** use a silent long-running section: any loop > 5s must emit at least
  one progress line per item or per 5-second interval.
