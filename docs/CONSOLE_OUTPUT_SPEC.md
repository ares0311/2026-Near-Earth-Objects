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

Every progress line must begin with a bracketed stage tag followed by a space.
**Every line must also include `elapsed {M}m{S:02d}s`** — no stage print may be
silent about elapsed time. Long-running stages additionally include an ETA.

```
[fetch]      Querying 1 survey(s): ('ZTF',)  RA=284.13, Dec=-22.5, r=3.5°  elapsed 0m00s
[fetch]      (1/1) Starting ZTF  elapsed 0m00s
[fetch]      (1/1) ZTF: 87 alerts  elapsed 3m42s  ETA 0m00s
[fetch]      Complete: 87 alerts total  elapsed 3m42s
[preprocess] Validating and normalising 87 sources  elapsed 3m42s
[preprocess] 87/87 sources passed  elapsed 3m43s
[detect]     Identifying moving object candidates  elapsed 3m43s
[detect]     12 candidates, 0 known matches  elapsed 3m43s
[link]       Linking 12 candidates across nights  elapsed 3m43s
[link]       progress 120/500 seed pairs; tracklets=4; elapsed 0m12s  ETA 0m38s
[link]       2 tracklets formed  elapsed 3m44s
[classify]   (1/2) NEO-00001  elapsed 3m44s  ETA 0m02s
[orbit]      (1/2) NEO-00001  elapsed 3m44s
[score]      (1/2) NEO-00001  elapsed 3m45s
[alert]      (1/2) NEO-00001  elapsed 3m45s
[neocp]      Monitoring NEOCP for NEO-00001 (timeout=2.0h)
[resume]     Checkpoint found (last stage: link); resuming from last completed stage.
[resume]     Reloading 12 tracklets from checkpoint (skipping fetch / preprocess / detect / link).
[resume]     Skipping already-processed NEO-00001  elapsed 3m45s
[cache]      Deleted 3 cache file(s) from .neo_cache/
[audit]      Run summary written to Logs/pipeline_runs/<key>/run_summary.json
```

Stage tags are lowercase. A single space after `]` is sufficient.

The **fetch stage** iterates over surveys one-by-one, emitting a `(N/M) Starting <survey>`
line before each survey call and a `(N/M) <survey>: X alerts  elapsed Xm Xs  ETA Xm Xs`
line after. ETA is computed from actual time-per-survey.

The **per-tracklet loop** (`[classify]`, `[orbit]`, `[score]`, `[alert]`) includes
`(idx/total)` counters. `[classify]` also includes an ETA computed from
time-per-tracklet so far this session.

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
