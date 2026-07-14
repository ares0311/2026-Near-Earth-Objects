# ZTF DR24 Sparse-Field Expansion Selection — 2026-07-14

## Trigger

Coverage-qualified run `017eb50381badb75` produced no production tracklet and
left two new fields below three populated retained nights:

- Aten 81.18,+22.50: one retained night;
- IEO 147.53,+15.00: two retained nights.

The expansion targets those coverage gaps. It does not reinterpret any of the
222 underconstrained two-point fits as candidates.

## Measured selection

Unused nights were ranked by combined central-box exposure rows for the two
sparse fields. The 12 highest-exposure candidates were checked with bounded
HTTP HEAD requests, never exceeding six concurrent requests. Across all
three-night combinations giving each target at least 80 exposure rows, the
lowest verified transfer is:

| Night | Verified bytes | Aten rows | IEO rows |
|---|---:|---:|---:|
| `20231003` | 6,490,521,903 | 9 | 55 |
| `20231029` | 5,690,739,473 | 41 | 13 |
| `20240429` | 6,871,969,364 | 48 | 20 |
| **Total** | **19,053,230,740** | **98** | **88** |

The committed source of truth is
`data_selection/batch_manifests/ztf_dr24_sparse_field_expansion_2024_v1.json`.
All nine portfolio fields remain in the streaming filter, and the post-ingest
moving-source injection remains the control allocation.

## Boundaries

Run as three archive-night shards with one worker each. Raw tar archives must
be streamed and evicted; retained output remains capped at 1 GB. The batch is
historical replay only and does not authorize MPC/NEOCP submission, authority
contact, public alerts, discovery claims, or impact-probability statements.
