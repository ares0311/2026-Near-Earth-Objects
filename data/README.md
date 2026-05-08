# data/

Sample and reference data files for the NEO Detection Pipeline.

## Files

### `sample_tracklets.json`

Two synthetic tracklets for testing `Skills/batch_score.py` and `Skills/check_mpc_known.py`.

**Format**: JSON array of tracklet objects.

Each tracklet object has the following structure:

```json
{
  "object_id": "string",
  "observations": [
    {
      "obs_id": "string",
      "ra_deg": 180.0,
      "dec_deg": 5.0,
      "jd": 2460000.5,
      "mag": 19.5,
      "mag_err": 0.05,
      "filter_band": "r",
      "mission": "ZTF"
    }
  ],
  "arc_days": 3.0,
  "motion_rate_arcsec_per_hour": 1.2,
  "motion_pa_degrees": 90.0
}
```

**Usage**:

```bash
PYTHONPATH=src python Skills/batch_score.py data/sample_tracklets.json
PYTHONPATH=src python Skills/check_mpc_known.py data/sample_tracklets.json
PYTHONPATH=src python Skills/visualize_tracklets.py data/sample_tracklets.json
```

## Adding Test Data

Place new sample files in this directory. Follow the naming convention:
- `sample_*.json` — synthetic test fixtures
- `real_*.json` — anonymized real observations (requires data-sharing approval)

Do not commit files larger than 10 MB. For large datasets, use the fetch pipeline to download on demand.
