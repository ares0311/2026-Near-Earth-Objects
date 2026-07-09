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
