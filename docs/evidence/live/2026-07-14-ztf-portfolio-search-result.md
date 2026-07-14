# ZTF DR24 Portfolio Search Result — 2026-07-14

## Outcome

The bounded six-shard archival acquisition completed successfully, but it
produced **no reviewable multi-night tracklet**. This is a coverage/association
result, not a model rejection and not evidence of a new object.

Run ID: `0b381aac323c0f28`
Batch: `ztf_dr24_portfolio_2024sep_v1`
Implementation merge: `20576cb4` (PR #231)
Execution-manifest commit: `226d4aee`

## Acquisition

- Six UW archive streams completed in 9m48s with no service error or rate
  limiting.
- 793,005 alerts were scanned across six 2024 September nights.
- 1,211 observations were retained; durable local output was 548 KB.
- Raw nightly tar archives were streamed and never persisted.
- Six-stream concurrency is therefore empirically clean for this exact bounded
  UW archive pattern; it is not evidence that 36 streams are safe.

Retained field/night cells:

| Field | 2024-09-11 | 2024-09-19 | Total |
|---|---:|---:|---:|
| followup Aten 97.42,+22.50 | 517 | 299 | 816 |
| followup IEO 139.76,+15.00 | 71 | 128 | 199 |
| followup Aten 89.30,+22.50 | 0 | 154 | 154 |
| new IEO 147.53,+15.00 | 0 | 42 | 42 |

All other selected field/night cells retained zero. Only the first two fields
had two populated nights. The new-field cells without repeated coverage must
not be reported as scientific null searches.

## Association audit

`Skills/analyze_ztf_alert_archive_portfolio.py` was added because the older
positive-control loader uses `Observation.field_id` as an object-history key.
For these checkpoints that value is the ZTF survey pointing number, not an
object identity. The new analyzer preserves it in source provenance but clears
it on the in-memory association copy, forcing real within-night motion pairing.

At the production minimum of three observations:

- followup Aten field: 816 observations, 132 within-night motion candidates,
  0 linked tracklets;
- followup IEO field: 199 observations, 36 within-night motion candidates,
  0 linked tracklets.

A sensitivity run with `min_observations=2` produced 100 two-point fits (72 and
28). With only two nights, every two-point seed fits a linear path exactly and
has no third observation for a residual test; these are underconstrained and
are **not candidates**. They were not classified, scored, cross-matched,
adversarially reviewed, or submitted.

Because there are zero valid production tracklets, the time-aware known-object
exclusion queue is empty. Candidate review remains fail-closed.

## Control

The committed post-ingest synthetic moving-source control ran with 20 ZTF
injections (seed 42):

- detected: 20/20;
- linked: 20/20;
- scored: 20/20.

This confirms the pipeline mechanics can recover well-formed multi-night
injections. It does not make the real two-night associations valid and does not
exercise live CNN inference (the control used the documented analytic
real/bogus proxy).

## Research interpretation and next step

The research path is unchanged. The acquisition demonstrated that date choice
must be coverage-aware: select at least three archive nights that actually
populate the same new field before transferring full archives. The next search
batch should first build a metadata-only field/night coverage inventory, then
choose three-or-more populated nights per field and reuse the same bounded
streaming/checkpoint design.

No MPC/NEOCP submission, authority contact, discovery claim, public alert, or
impact-probability statement is authorized or warranted.
