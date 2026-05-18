# FETCH_GUIDE.md — Data Retrieval Reference

Technical reference for `fetch.py`: how the pipeline retrieves survey photometry and catalog data from ZTF, ATLAS, MPC, and JPL Horizons; caching strategy; survey depth estimation; and multi-survey merging.

---

## Overview

The fetch stage is the first in the pipeline and is responsible for acquiring all raw observational data.  It produces a `FetchResult` containing a tuple of `Observation` objects and a `FetchProvenance` record.

```
sky position + time window → fetch() → FetchResult(alerts, provenance)
```

No downstream stage should call external APIs directly — all network access is centralized in `fetch.py`.

---

## Survey Sources

### ZTF (Primary)

ZTF provides public difference-image alerts via the IRSA TAP service.  Two access methods are supported:

**Method 1 — ztfquery (preferred)**
```python
from fetch import fetch_ztf
obs = fetch_ztf(ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
                start_jd=2460000.5, end_jd=2460003.5)
```

**Method 2 — IRSA cone search (fetch_ztf_alerts)**
```python
from fetch import fetch_ztf_alerts
obs = fetch_ztf_alerts(ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
                       start_jd=2460000.5, end_jd=2460003.5)
```

Key fields available per ZTF alert: `ra`, `dec`, `jd`, `magpsf` (→ `mag`), `sigmapsf` (→ `mag_err`), `fid` (filter: 1=g, 2=r, 3=i), `rb` (real/bogus), `drb` (deep real/bogus).

### ATLAS (Confirmation)

ATLAS forced photometry is fetched via the REST API with task queuing.  An API token is required (set `ATLAS_TOKEN` env var or pass `atlas_token=`).

```python
from fetch import fetch_atlas_forced
obs = fetch_atlas_forced(ra_deg=180.0, dec_deg=10.0,
                         start_jd=2460000.5, end_jd=2460003.5,
                         atlas_token="your_token")
```

Bands: orange (`o`) and cyan (`c`).  2-day cadence.

### MPC Catalog

Known objects in a search field are queried from the MPC:

```python
from fetch import fetch_mpc_known
known = fetch_mpc_known(ra_deg=180.0, dec_deg=10.0,
                        radius_deg=0.5, jd=2460000.5)
```

Historical observation records for a specific designation:
```python
from fetch import fetch_mpc_observations
obs = fetch_mpc_observations("2020 AB1")
```

### JPL Horizons

Ephemerides for known NEOs:
```python
from fetch import fetch_horizons
obs = fetch_horizons(target="Apophis", start_jd=2460000.5, end_jd=2460003.5)
```

---

## Caching

All network calls are cached to disk at `.neo_cache/<md5_hash>.json`.  The cache key includes all query parameters (RA, Dec, radius, JD range).

- **Default**: return cached result if available
- **Force refresh**: pass `force_refresh=True` to bypass the cache

```python
obs = fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.5, 2460003.5, force_refresh=True)
```

Cache files are plain JSON and can be inspected or deleted manually.  Never commit cache files to the repository.

---

## Multi-Survey Merging

To combine results from multiple surveys into a single `FetchResult`:

```python
from fetch import fetch, merge_survey_alerts
result = fetch(ra_deg=180.0, dec_deg=10.0, radius_deg=0.5,
               start_jd=2460000.5, end_jd=2460003.5,
               surveys=["ZTF", "ATLAS"])
```

Or merge independently fetched results:
```python
from fetch import merge_survey_alerts
merged = merge_survey_alerts([ztf_result, atlas_result])
```

`merge_survey_alerts` deduplicates by `obs_id` and concatenates provenance records.

---

## Survey Depth Estimation

`estimate_survey_depth(fetch_result)` returns the 95th-percentile apparent magnitude from the alert set — a robust proxy for the 5σ limiting magnitude:

```python
from fetch import estimate_survey_depth
depth = estimate_survey_depth(result)  # e.g. 20.8
```

Returns `None` if no valid magnitudes are present (all sentinel values ≥ 90 or empty result).

The older `estimate_limiting_magnitude(observations)` function uses the faint-end tail (99th percentile) and operates directly on an observation list.

---

## Filtering

### By motion rate
```python
from fetch import filter_alerts_by_motion
fast = filter_alerts_by_motion(alerts, min_rate=10.0, max_rate=60.0)
```

Filters using the `ssdistnr` field as a motion proxy.  Observations without `ssdistnr` pass through unchanged.

### By survey
```python
from fetch import filter_by_survey
ztf_only = filter_by_survey(result, surveys=["ZTF"])
```

Returns a new `FetchResult` containing only alerts from the specified surveys.

---

## Observation Window

Use `build_observation_window` to create a validated `ObservationWindow` for a pipeline run:

```python
from fetch import build_observation_window
window = build_observation_window(ra_deg=180.0, dec_deg=10.0,
                                  radius_deg=0.5,
                                  start_jd=2460000.5, end_jd=2460003.5,
                                  surveys=["ZTF"])
```

Raises `ValueError` for invalid inputs (bad RA/Dec range, end_jd ≤ start_jd).

---

## Field Summary

`summarise_fetch_result(result)` returns a summary dict useful for logging:

| Key | Description |
|-----|-------------|
| `n_alerts` | Total observation count |
| `surveys` | List of unique surveys |
| `start_jd` / `end_jd` | Time window |
| `limiting_mag` | 95th-percentile depth |
| `n_with_real_bogus` | Count with rb score |

---

## Known Object Count

`count_known_objects_in_field(ra_deg, dec_deg, radius_deg)` queries the MPC for the number of known objects in a circular field.  Returns 0 on failure.  Useful for assessing field contamination before linking.

---

## Batch Fetching

`fetch_batch(windows)` accepts a list of `ObservationWindow` objects and returns a list of `FetchResult` objects in the same order.  Useful for multi-field survey simulation:

```python
from fetch import fetch_batch
results = fetch_batch([window1, window2, window3])
```

---

## Data Quality Notes

- ZTF real/bogus scores (`rb`, `drb`) should be treated as pre-filters, not absolute truth.  Use `rb ≥ 0.65` as the default threshold (configurable in `detect.py`).
- ATLAS forced photometry uses fixed apertures; point-spread-function magnitudes are more reliable for faint objects.
- MPC ephemerides are approximate for short-arc objects; match radius should be ≥5 arcsec for quality-code-1 orbits.
- All magnitudes ≥ 90 are sentinels for non-detections and are excluded from depth estimates and photometric statistics.
