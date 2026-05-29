# Candidate Clustering Technical Reference

This document covers spatial candidate clustering concepts, relevant schema
models, usage patterns, and guardrails for the NEO Detection Pipeline.

---

## Overview

Candidate clustering groups spatially nearby NEO candidates detected in a
single pipeline run.  Clustering serves two primary purposes:

1. **Follow-up scheduling**: Multiple candidates in the same sky region can
   be observed in a single telescope pointing.
2. **Deduplication**: Candidates that are too close together may arise from
   the same physical object detected more than once (e.g., split tracklets
   or duplicate detections across overlapping survey fields).

---

## Schema Models

### `ObservationCluster`

A spatial cluster of individual **observations** (not candidates).  Produced
by `cluster_detections` in `detect.py`.

| Field | Type | Description |
|---|---|---|
| `cluster_id` | `str` | Unique identifier for this cluster |
| `center_ra_deg` | `float` | Cluster centroid RA in degrees |
| `center_dec_deg` | `float` | Cluster centroid Dec in degrees |
| `radius_arcsec` | `float` | Angular radius enclosing all observations |
| `epoch_jd` | `float` | Julian Date of the cluster epoch |
| `n_observations` | `int` | Number of observations in the cluster |
| `observations` | `tuple[Observation, ...]` | Constituent observations |

### `CandidateCluster`

A spatial cluster of **scored NEO candidates** from a single pipeline run.
Produced after the score stage.

| Field | Type | Description |
|---|---|---|
| `cluster_id` | `str` | Unique identifier for this cluster |
| `run_id` | `str` | Pipeline run identifier |
| `center_ra_deg` | `float` | Cluster centroid RA in degrees |
| `center_dec_deg` | `float` | Cluster centroid Dec in degrees |
| `n_candidates` | `int` | Number of candidates in the cluster |
| `candidate_ids` | `tuple[str, ...]` | Ordered candidate object IDs |
| `mean_priority` | `float` | Mean discovery priority score (default 0.0) |

Both models use `ConfigDict(frozen=True)` — they are immutable after
construction.

---

## Using `cluster_detections` (detect.py)

```python
from detect import cluster_detections

# observations: list[Observation] from PreprocessResult
clusters = cluster_detections(observations, radius_arcsec=10.0)
for c in clusters:
    print(c.cluster_id, c.n_observations, c.center_ra_deg, c.center_dec_deg)
```

`cluster_detections` uses greedy spatial clustering: the first unclustered
observation seeds a new cluster, and all observations within `radius_arcsec`
are assigned to it.

---

## Building a `CandidateCluster`

After scoring, group candidates by proximity and build `CandidateCluster`
objects for follow-up scheduling:

```python
import numpy as np
from schemas import CandidateCluster

def build_candidate_cluster(cluster_id, run_id, scored_neos):
    ras = [n.tracklet.observations[0].ra_deg for n in scored_neos]
    decs = [n.tracklet.observations[0].dec_deg for n in scored_neos]
    ids = tuple(n.tracklet.object_id for n in scored_neos)
    priorities = [n.metadata.discovery_priority for n in scored_neos]
    return CandidateCluster(
        cluster_id=cluster_id,
        run_id=run_id,
        center_ra_deg=float(np.mean(ras)),
        center_dec_deg=float(np.mean(decs)),
        n_candidates=len(scored_neos),
        candidate_ids=ids,
        mean_priority=float(np.mean(priorities)),
    )
```

---

## Use Cases

### Follow-up Scheduling
Group candidates into clusters and schedule a single telescope pointing per
cluster to cover multiple candidates.  Use `mean_priority` to prioritize
high-value clusters.

### Deduplication
Candidates with overlapping tracklets in the same cluster should be checked
with `deduplicate_tracklets` from `link.py`.  If the same physical object
appears in two candidates, keep the longer arc.

### Density Analysis
Use `compute_tracklet_density` from `link.py` to count how many other
tracklets fall within a given search radius of each tracklet's first
observation.  High density may indicate a crowded field or a false-positive
cluster.

---

## Guardrails

- **No confirmed detections**: `CandidateCluster` objects represent pipeline
  candidates only.  Never label them as confirmed NEOs without MPC
  confirmation.
- **No impact claims**: Do NOT compute or report impact probabilities from
  cluster data alone.  Defer to CNEOS/MPC for authoritative hazard
  assessment.
- **Alert protocol**: Only candidates that pass all alert-protocol gate
  conditions (MOID ≤ 0.05 AU, orbit quality ≥ 2, real/bogus ≥ 0.90, not
  matched to MPC catalog) may progress to MPC submission.

---

## Related Modules

| Module | Relevant Function |
|---|---|
| `detect.py` | `cluster_detections` — greedy spatial clustering of observations |
| `link.py` | `compute_tracklet_density` — neighbor count per tracklet |
| `link.py` | `deduplicate_tracklets` — remove duplicate tracklets |
| `schemas.py` | `CandidateCluster`, `ObservationCluster` — frozen data models |
