# Observation Statistics Guide

This document describes the observation-level and survey-level statistics helpers
added across v0.78–v0.80, covering temporal coverage, night gaps, mission counts,
cluster summaries, and the `SurveyRunSummary` schema.

---

## Schemas

### `ObservationCluster` (schemas.py)

Groups spatially and temporally co-located detections from a single pipeline epoch.

```python
from schemas import ObservationCluster

cluster = ObservationCluster(
    cluster_id="C-001",
    center_ra_deg=83.8221,
    center_dec_deg=-5.3911,
    radius_arcsec=5.0,
    epoch_jd=2460000.5,
    observations=(),
    n_observations=4,
)
```

| Field | Type | Description |
|---|---|---|
| `cluster_id` | `str` | Unique cluster identifier |
| `center_ra_deg` | `float` | RA of cluster centroid |
| `center_dec_deg` | `float` | Dec of cluster centroid |
| `radius_arcsec` | `float` | Cluster radius in arcsec |
| `epoch_jd` | `float` | Representative epoch of the cluster |
| `observations` | `tuple[Observation, ...]` | Member observations |
| `n_observations` | `int` | Count of member observations |

### `SurveyRunSummary` (schemas.py)

High-level summary of a single survey run for reporting and logging.

```python
from schemas import SurveyRunSummary

summary = SurveyRunSummary(
    run_id="ztf-2026-06-04",
    field_id="ZTF_F0001",
    night_jd=2460000.5,
    n_alerts=1200,
    n_candidates=43,
    n_pha_candidates=1,
    limiting_mag=20.8,
    pipeline_version="0.80.0",
)
```

---

## Fetch-Level Statistics

### `count_observations_by_night(fetch_result)` — fetch.py

Returns `dict[int_jd, count]` for all observations in a FetchResult.

### `compute_temporal_coverage(fetch_result)` — fetch.py

Returns `{"n_observations", "min_jd", "max_jd", "span_days", "n_nights"}`.

### `compute_observation_rate(fetch_result)` — fetch.py

Returns the mean number of observations per night.  `None` for single-night
datasets where a rate is undefined.

```python
rate = compute_observation_rate(fetch_result)
# e.g. 142.3 observations/night
```

---

## Link-Level Statistics

### `compute_night_gap_statistics(tracklets)` — link.py

Returns inter-night gap statistics across all tracklets:

```python
from link import compute_night_gap_statistics
stats = compute_night_gap_statistics(tracklets)
# {'mean_gap_nights': 1.5, 'max_gap_nights': 3, 'n_tracklets': 12}
```

Use `Skills/compute_night_gap_stats.py` for a CLI interface.

---

## Detect-Level Statistics

### `count_detections_by_mission(detect_result)` — detect.py

Returns `dict[mission, count]` for all candidates in a DetectResult.

```python
from detect import count_detections_by_mission
counts = count_detections_by_mission(result)
# {'ZTF': 38, 'ATLAS': 5, 'unknown': 1}
```

---

## Preprocess-Level Statistics

### `compute_reference_cutout_snr(obs)` — preprocess.py

Returns the peak-to-RMS SNR of the 63×63 reference (template) cutout.
High SNR indicates a clean, star-subtracted template; low SNR may indicate
a poor or absent reference image.

---

## Skills Scripts

| Script | Description |
|---|---|
| `Skills/compute_temporal_coverages.py` | Temporal coverage summary from tracklet JSON; `--json` flag |
| `Skills/compute_night_gap_stats.py` | Inter-night gap statistics from tracklet JSON; `--json` flag |

---

## Guardrails

All observation statistics are internal pipeline diagnostics only.  They do NOT
imply a confirmed NEO detection or Earth-impact probability.  Follow the alert
protocol in `docs/ALERT_PROTOCOL.md` for any external reporting.
