# Grouped Split Controls

The A4 production gate requires NEO training and evaluation splits to be
audited for correlated astronomical context before any model-promotion claim.
Random splits remain diagnostic only.

Use the validator on any CSV split table that includes, or can derive, these
fields:

- `split`: `train`, `validation`, or `test`.
- `sample_id`: sample, candidate, observation, or designation identifier.
- `label`: class label.
- `object_id`: object, designation, or target identifier.
- Observing night: `night_key`, `night`, `obs_night`, `jd`, `obsjd`, or `mjd`.
- Sky region: `sky_cell`, `field_id`, `field`, or RA/Dec columns.
- Source context: `source_key`, `source_id`, or survey plus instrument columns.

```bash
UV_CACHE_DIR=.uv-cache PYTHONPATH=src uv run --no-sync --python 3.14 python Skills/validate_grouped_splits.py path/to/splits.csv
```

The validator fails closed on hard leakage across object identity, observing
night, and sky cell. Survey/instrument source context is reported separately:
single-source datasets are allowed, but the report preserves that limitation so
promotion packets cannot pretend source-diversity was tested.
