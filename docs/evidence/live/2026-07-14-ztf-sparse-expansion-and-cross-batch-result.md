# ZTF Sparse Expansion and Cross-Batch Result — 2026-07-14

## Acquisition result

Run `56c2348f31302291` completed all three archive shards in 5m10s without
service errors. It streamed 19.053230740 GB, scanned 402,053 alerts, retained
2,311 observations, and persisted 1.1 MB. Raw archives were not stored.

Retained observations were concentrated on two nights. `20231003` scanned
136,952 alerts but retained zero portfolio observations. `20231029` retained
1,315 and `20240429` retained 996. Production and two-observation sensitivity
association each formed zero tracklets. A fresh isolated 20-seed ZTF control
passed 20/20 detection, linking, and scoring.

## Cross-batch association

The analyzer combined this expansion with
`ztf_dr24_coverage_selected_2024_v1` while validating each checkpoint against
its own manifest hash, enforcing identical field definitions, and
deduplicating by `obs_id`.

- Aten 81.18: 501 observations across two retained nights, 80 motion
  candidates, zero seed pairs, zero tracklets.
- IEO 147.53: 484 observations across four retained nights, 99 motion
  candidates, 8,956 seed pairs, zero production tracklets.
- The sensitivity pass formed 70 fits; every fit has exactly two observations
  across two nights and is not a candidate.

No time-aware known-object exclusion, classification, scoring, adversarial
review, submission, external alert, discovery claim, or impact claim follows
from these results. Another bulk replay requires an explicit research decision.
