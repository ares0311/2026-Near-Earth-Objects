# ZTF DR24 Coverage-Qualified Search Result — 2026-07-14

## Outcome

The coverage-qualified four-night archival search completed successfully and
produced **no reviewable multi-night tracklet**. This is a real bounded null
association result. It is not a model rejection, a confirmed absence of NEOs,
or evidence of a new object.

- Run ID: `017eb50381badb75`
- Batch: `ztf_dr24_coverage_selected_2024_v1`
- Selection implementation: PR #235, merge `d81af0a0`
- Execution-manifest commit: `b048be9c`
- Selected nights: `20240321`, `20240422`, `20240504`, `20240603`

## Acquisition

- Four disjoint UW archive streams completed in 10m36s without a service
  error or rate-limit response.
- The archives totaled 26,670,482,707 verified remote bytes (26.67 GB).
- 567,025 alerts were scanned and 5,416 observations were retained.
- Durable checkpoint output was 2.2 MB. Raw nightly archives were streamed and
  never persisted.
- The initial sandboxed attempt failed immediately at DNS and wrote no science
  data. The approved rerun is the completed run summarized here.
- Fail-closed status and merge both report 4/4 successful shards when bound to
  the recorded four-shard topology.

Retained observations by field and archive night:

| Field | Mar 21 | Apr 22 | May 04 | Jun 03 | Total |
|---|---:|---:|---:|---:|---:|
| followup Aten 89.30,+22.50 | 131 | 0 | 0 | 0 | 131 |
| followup Aten 97.42,+22.50 | 59 | 0 | 0 | 0 | 59 |
| followup IEO 139.76,+15.00 | 0 | 35 | 0 | 0 | 35 |
| new Aten 81.18,+22.50 | 165 | 0 | 0 | 0 | 165 |
| new Aten 243.54,-22.50 | 0 | 174 | 359 | 639 | 1,172 |
| new Aten 251.66,-22.50 | 0 | 708 | 1,077 | 499 | 2,284 |
| new IEO 147.53,+15.00 | 0 | 141 | 8 | 0 | 149 |
| new IEO 196.68,-07.50 | 172 | 0 | 194 | 257 | 623 |
| new IEO 204.25,-07.50 | 221 | 0 | 197 | 380 | 798 |

The IRSA preflight established science-image exposure coverage, not a promise
of retained `rb >= 0.5` alerts. Five new fields had retained observations on
at least two nights; four had retained observations on three nights. New Aten
81.18,+22.50 and all follow-up fields remained single-night after filtering.

## Association audit

`Skills/analyze_ztf_alert_archive_portfolio.py` preserved survey field numbers
in checkpoint provenance but cleared them from the in-memory identity field,
forcing real spatial/temporal motion pairing. At the production minimum of
three observations:

| Field | Loaded | Motion candidates | Seed pairs | Linked tracklets |
|---|---:|---:|---:|---:|
| new Aten 251.66,-22.50 | 2,284 | 329 | 95,472 | 0 |
| new Aten 243.54,-22.50 | 1,172 | 157 | 624 | 0 |
| new IEO 204.25,-07.50 | 798 | 112 | 216 | 0 |
| new IEO 196.68,-07.50 | 623 | 36 | 0 | 0 |
| new IEO 147.53,+15.00 | 149 | 35 | 136 | 0 |

A sensitivity run with `min_observations=2` formed 222 fits. Every fit contains
exactly two observations across exactly two nights. Such a pair defines a
linear path without a third observation for a residual test, so all 222 are
underconstrained and **not candidates**. They were not classified, scored,
cross-matched, adversarially reviewed, or submitted.

Because the production tracklet set is empty, the time-aware known-object
exclusion queue is also empty. Candidate review remains fail-closed.

## Fresh positive control

A fresh batch-isolated ZTF injection-recovery control ran with 20 seeds
(`seed=42`) rather than reusing an older checkpoint:

- detected: 20/20;
- linked: 20/20;
- scored: 20/20.

This confirms the production mechanics recover well-formed multi-night
synthetic injections. It does not validate any real two-point association and
does not exercise live CNN weights; the control uses the documented analytic
real/bogus proxy.

## Research interpretation

The batch closes the planned coverage-qualified replay honestly: archive
selection, sharded streaming, checkpointing, production association, and a
fresh positive control all executed as designed, but no valid real tracklet
survived the minimum association gate. Exposure-level preflight improved
retained-night coverage materially over the preceding September batch, yet it
cannot predict the number of retained alert packets or guarantee an object
path through a particular field.

No MPC/NEOCP submission, authority contact, discovery claim, public alert, or
impact-probability statement is authorized or warranted.
