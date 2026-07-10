# Dataset Manifests

Committed dataset manifests live here when a dataset is used for training,
validation, calibration, frozen evaluation, live search, follow-up search,
positive controls, negative controls, or submission evidence.

Every manifest must validate against
[`../dataset_manifest.schema.json`](../dataset_manifest.schema.json):

```bash
uv run --python 3.14 python Skills/validate_dataset_manifest.py data_selection/dataset_manifests/<manifest>.json
```

Do not place raw archive data in this directory. Store durable identifiers,
query details, checksums, caveats, and regeneration context instead.

## Committed manifests (as of v0.90.72)

| Manifest | Role | Real dataset it documents |
|---|---|---|
| `ztf_labeled_alerts_tier2_cnn_v1.json` | training | `data/ztf_labeled_alerts.json` — the frozen `benchmark_cnn_v1` model's real training source (10,000 real ZTF alerts, gitignored/local). Explicitly documents that no per-alert RA/Dec/JD metadata was preserved, so a real grouped-split leakage report (A4) cannot be reconstructed for it without new acquisition/retraining work. |
| `gate_z4_ranking_baseline_v1.json` | frozen_eval | `Logs/reports/ranking_baseline.json` — Gate Z4's real archived-negative + synthetic-positive ranking evaluation (0/200 false positives). |
| `gate_z6_retrospective_validation_v1.json` | frozen_eval | `Logs/reports/retrospective_validation.json` — Gate Z5/Z6's real retrospective MPC cross-match of 88 review packets. |
| `a6_injection_recovery_image_level_n200_v1.json` | frozen_eval | `data/injection_recovery_image_level_n200.json` — A6's real synthetic image-level injection-recovery baseline. |

Every value in these manifests is either a computed fact (checksum, file
size) or transcribed from already-documented project history (source URLs,
gate-closure dates, real result counts). Where a fact genuinely could not be
determined (e.g. the exact download night-range for the CNN training data),
the field says `"unknown"` explicitly rather than guessing — see each
manifest's `known_caveats`.
