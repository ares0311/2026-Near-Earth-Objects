# ZTF Field/Night Coverage Preflight

Date: 2026-07-14
Repository: `2026 Near Earth Objects`
App version: `v0.90.94`

## Result

The metadata-only preflight passed for all six uncovered new Aten/IEO fields.
Run `9a9e148f570d162b` launched six disjoint field shards with one IRSA worker
per shard and completed in 10 seconds without a service or rate-limit error.
The fail-closed scientific merge used query key `807efb0e5ef7d55d`.

| Field | Exposure rows | Distinct UTC nights |
|---|---:|---:|
| `new_aten_251p66_m22p50` | 585 | 46 |
| `new_aten_243p54_m22p50` | 531 | 44 |
| `new_aten_081p18_p22p50` | 2,182 | 93 |
| `new_ieo_204p25_m07p50` | 824 | 55 |
| `new_ieo_196p68_m07p50` | 833 | 58 |
| `new_ieo_147p53_p15p00` | 1,579 | 110 |

The query covered each field's central 2-degree by 2-degree IRSA box over the
exclusive 365-day interval JD 2460209.5–2460574.5. It did not claim coverage
for the full 2-degree-radius portfolio cone.

## Selected archive quartet

An exhaustive four-night combination check found 60 solutions where every new
field has at least three exposure-covered nights. HTTP HEAD checks verified the
archive object sizes for every night appearing in those solutions. The
minimum-transfer valid quartet is:

| Night | Verified bytes | New fields with coverage |
|---|---:|---:|
| `20240321` | 5,014,634,609 | 3 |
| `20240422` | 6,244,536,269 | 4 |
| `20240504` | 11,805,932,297 | 6 |
| `20240603` | 3,605,379,532 | 5 |
| **Total** | **26,670,482,707** | — |

Every new field has coverage on exactly three of these four nights. The
committed acquisition source of truth is
`data_selection/batch_manifests/ztf_dr24_coverage_selected_2024_v1.json`.
The raw archives will be streamed and evicted rather than persisted; retained
observations remain capped at 5,000 per field/night.

One nominally present object, `ztf_public_20240114.tar.gz`, was only 74 bytes
and was excluded as a placeholder rather than counted as usable archive data.

## Interpretation and boundaries

This closes the coverage-planning failure exposed by the first portfolio run:
the next transfer is based on observed science-image exposure nights rather
than guessed common dates. It does not guarantee alert packets, retained
detections, tracklets, or candidates. A scientifically valid null remains
possible.

No alert archive was downloaded during this preflight. No catalog, candidate,
classification, score, external submission, discovery claim, or impact claim
was produced. Gate Z3 remains separately paused.
