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

## Source-native packet-history audit

The [ZTF Science Data System explanatory supplement](https://irsa.ipac.caltech.edu/data/ZTF/docs/ztf_explanatory_supplement.pdf)
defines `prv_candidates` as historical events matched within 1.5 arcseconds of
the triggering alert, with an approximately 30-day lookback. The
[ZTF extended cautionary notes](https://irsa.ipac.caltech.edu/data/ZTF/docs/ztf_extended_cautionary_notes.pdf)
say packet history is constructed by positional matching independently for
each triggering event and warn that `objectId` assignments can split or merge
nearby detections.

Those semantics do not supply a reliable moving-object trajectory. Promoting
`prv_candidates` rows into association would risk manufacturing false links,
so this audit rejects that use. Packet history may be useful later as
context/veto evidence after an independent tracklet exists, but it does not
justify another bulk alert-archive transfer. The recommended research choice
is to move candidate generation to survey detection/image products designed
for motion; continuing the alert replay is an explicit lower-yield option.
