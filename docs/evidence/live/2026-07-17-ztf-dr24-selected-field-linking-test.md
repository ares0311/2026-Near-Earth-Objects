# ZTF DR24 Multi-Night Linking — Algorithmically-Selected Field

Date: 2026-07-17

Scope: per operator direction, ran the fully-validated pixel-extraction ->
masking/dedup -> PSF-scoring -> multi-night-linking pipeline against a
field chosen by the project's own documented selection scoring
(`Skills/select_survey_fields.py`), rather than reusing the convenience
field from the earlier verification/pilot work. No code changes were
needed -- this run exercises the pipeline built across
2026-07-16/2026-07-17 exactly as-is against new real data.

External submission: none. Diagnostic linking only.

## Field selection (documented, not guessed)

```bash
uv run --python 3.14 python Skills/select_survey_fields.py \
    --jd 2458340.5 --mode aten --top-n 20 \
    --history-dir Logs/pipeline_runs \
    --write-target-queue data_selection/target_priority_queue.csv --json
```

Rank 1 of 20 scored fields (579 candidates scored, 181 observable):

| Field | Value |
|---|---|
| RA / Dec | 217.41 / -15.0 |
| Score | 0.9308 |
| Elongation | 82.8 deg (favorable Aten/quadrature geometry) |
| Novelty | 1.0 (never processed in `Logs/pipeline_runs` history) |
| Reason | "coverage gap 0.95; pop density 0.84; geometry 0.99 (6.1h vis)" |

`--jd 2458340.5` matches the same 2018-era epoch as the earlier pilot work
so the selection reflects real historical observing geometry, not "tonight"
in 2026. Appended to `data_selection/target_priority_queue.csv` per the
data-selection policy's documented-selection-rule requirement.

## Coverage and acquisition

Metadata-only query (RA 217.41, Dec -15.0, 0.01 deg box, ~400-day window)
found 31 real nights of coverage, dominated by real ZTF field 325 (54
exposures). Picked 3 nights with reasonable temporal proximity:
20180327, 20180330, 20180409 (3-day and 10-day gaps). Ran the full
preflight -> download -> mask -> dedup -> PSF-score pipeline, unmodified,
on each (all three products verified/downloaded exactly as before).

## Real live results

| Night | Raw connected components | Output (capped at 200) |
|---|---:|---:|
| 20180327 | 234 | 200 |
| 20180330 | 252 | 200 |
| 20180409 | 505 | 200 |

Converted and linked (`Skills/convert_pixel_extraction_to_observations.py`
+ `Skills/run_pixel_extraction_positive_control.py`, unmodified from the
prior field's run):

| `min_observations` | Tracklets formed |
|---:|---:|
| 2 (exploratory) | 200 -- same combinatorial-explosion phenomenon as the first field |
| 3 (real default) | **5** |

## Cross-validation against PSF-shape scoring: all 5 survivors fail independently

| Tracklet | Night | SNR | component_size | `psf_correlation` |
|---|---|---:|---:|---|
| 4ada2027 | 20180327 | 9.29 | 1 | null (edge) |
| | 20180330 | 6.52 | 1 | 0.0010 |
| | 20180409 | 7.83 | 1 | null (edge) |
| f6438a84 | 20180327 | 7.94 | 3 | null (edge) |
| | 20180330 | 5.61 | 1 | null (edge) |
| | 20180409 | 8.62 | 1 | 0.0079 |
| 0465e93b | 20180327 | 7.89 | 12 | null (edge) |
| | 20180330 | 5.24 | 1 | 0.1681 |
| | 20180409 | 7.77 | 1 | null (edge) |
| e5ded978 | 20180327 | 7.46 | 3 | null (edge) |
| | 20180330 | 6.16 | 1 | 0.0262 |
| | 20180409 | 8.04 | 1 | null (edge) |
| 84e09112 | 20180327 | 6.26 | 1 | null (edge) |
| | 20180330 | 8.35 | 1 | null (edge) |
| | 20180409 | 9.40 | 1 | null (edge) |

Every scored `psf_correlation` is far below the >0.5 threshold a real point
source is expected to clear (max 0.168, versus >0.95 for the synthetic
injected-source control), and every SNR is within a factor of ~2 of the
5-sigma detection floor. One observation (tracklet 0465e93b's first point)
has a 12-pixel connected component -- larger than the 1-2 pixel norm seen
elsewhere, plausibly a genuine subtraction artifact or cosmic-ray track --
but its own subsequent linked observations still show no PSF-shape
evidence, so this does not change the tracklet's overall assessment.

## Honest conclusion

**A second, independently and algorithmically selected field produces the
same result as the first**: the full pipeline works correctly end-to-end
on real data (raw combinatorial explosion at `min_observations=2`,
proper collapse to a small survivor set at the real `min_observations=3`
default), and none of the survivors show independent PSF-shape evidence of
being real point sources. This strengthens, rather than weakens, the
conclusion from the first field's null result -- it is not an artifact of
that one specific field/night combination.

## Decision boundary

Does not authorize a wider batch, a candidate claim, Gate Z3 resumption, or
external submission. Two fields, six real nights total, and the complete
pipeline (extraction through linking) have now been validated end-to-end
against real DR24 data with consistent, cross-validated null results.
