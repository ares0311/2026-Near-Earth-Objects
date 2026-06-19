# T1-C Evidence: ATLAS Recovery 40-Query Pilot

This file records the durable GitHub-visible summary for the June 19, 2026
bounded ATLAS forced-photometry recovery pilot. Raw operational outputs remain
local under `Logs/` and are intentionally ignored.

## Approval And Safety Scope

Jerome W. Lindsey III approved up to `40` ATLAS forced-photometry sample queries
for T1-C recovery evidence. No external submission was authorized. No
impact-probability claims were authorized.

The committed live-review policy records this expanded recovery envelope in
`background/live_review_policy.example.json`.

## Run

- run id: `atlas_recovery_4eaf93e87f6c`
- source manifest: `Logs/reports/t1c_expected_known_ztf_available_251p66_m22p5_30d.json`
- manifest rows attempted: `11`
- ATLAS sample queries: `38`
- recovered samples: `19`
- emitted audit tracklets: `4`
- failures: `0`
- pending samples: `0`
- external submission: `false`
- impact-probability claim: `false`

The run stayed inside the approved query cap by using the first `11` manifest
objects, which expanded to `38` sky/time samples.

## Audit Result

`Skills/audit_real_run.py` evaluated the recovery packet:

- expected known objects: `11`
- recovered expected objects: `4`
- unmatched expected objects: `7`
- ambiguous matches: `0`
- invalid matches: `0`
- recovery rate: `36.36%`
- KPI threshold: `90.00%`
- recovery gate passed: `false`
- same-night subgate applies: `false`
- multi-night tracklets reviewed: `4`
- production promotion allowed: `false`

Recovered object designations:

- `481`
- `1950`
- `2172`
- `2973`

The generated review CSV contains four `known_object` rows requiring
citizen-science operator review, but operator review cannot close T1-C by
itself because the known-object recovery KPI failed.

## Conclusion

This pilot closes the prior provider-plumbing question: ATLAS live queueing,
polling, checkpointing, result retrieval, and audit-packet generation all worked
without tool failures. It does not close T1-C because recovery was below the
required `90%` threshold.

The next production blocker is selecting or approving a stronger recovery
strategy before spending more live provider queries. Options include:

- approve a larger bounded ATLAS recovery budget for additional manifest rows;
- build a new expected-known manifest biased toward ATLAS-recoverable objects;
- revise the T1-C recovery method so the KPI evaluates only prequalified
  recoverable objects, with the selection rule documented before the run.

None of these options authorizes MPC submission, NEOCP escalation, NASA
notification, or any impact-probability statement.
