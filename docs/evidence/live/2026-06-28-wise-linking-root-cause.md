# WISE 0-Tracklet Root Cause And Patch

Date: 2026-06-28

## Context

The Taurus WISE sweep `756e0dc7b6be` returned `111913` IRSA rows, parsed
`85335` observations, detected `535` moving-object candidates, and linked `0`
tracklets. The run proved the WISE async TAP path works, but it also showed that
the downstream detection/linking path was not yet appropriate for WISE archival
point-source data.

## Root Cause

`fetch_wise_archive()` queried the broad NEOWISE single-exposure point-source
table using only sky and time constraints:

```sql
SELECT ra, dec, mjd, w1mpro, w1sigmpro
FROM neowiser_p1bs_psd
...
```

That result is dominated by static stars and galaxies. `detect()` then required
same-night pairs before the linker could see an observation. This is suitable
for alert streams or broker histories, but it drops the discovery-archive case
where a moving object may have one useful detection per WISE visit/night.

The `535` candidates were therefore not strong evidence of recoverable moving
objects. They were the small subset of dense point-source rows that happened to
form same-night pairs within the broad solar-system motion-rate bounds.

## Official IRSA Metadata Used

The IRSA TAP schema for `neowiser_p1bs_psd` exposes:

- `sso_flg`: known solar system object association flag
- `allwise_cntr`: closest associated ALLWISE Catalog source counter
- `n_allwise`: number of ALLWISE sources found within the association radius
- `source_id`: unique source ID

These fields let the pipeline avoid querying the entire static point-source
population during the next production diagnostic.

## Patch Strategy

- WISE ADQL now selects the association columns and filters rows to:
  `sso_flg = 1 OR allwise_cntr IS NULL OR n_allwise = 0`.
- This preserves known solar-system-object control detections and broader
  AllWISE-unmatched transient/moving-source candidates.
- `detect()` now preserves prefiltered `WISE`, `DECam`, and `TESS` archive rows
  as singleton candidates so `link()` can build a multi-night tracklet from one
  detection per visit/night.

## Scientific Limits

This is not a discovery claim and does not authorize MPC submission. The filter
is a candidate-generation prefilter only. A reportable candidate must still pass
multi-night linking, scoring, automated adversarial review, operator review, and
the MPC submission policy.

## Next Validation

Operator validation completed on 2026-06-28 on local Python 3.14.3:

```bash
PYTHONPATH=src uv run --python 3.14 --extra dev python -m pytest tests/test_detect.py tests/test_fetch.py::TestFetchWiseArchive -q
uv run --python 3.14 --extra dev ruff check src/detect.py src/fetch.py tests/test_detect.py tests/test_fetch.py
PYTHONPATH=src uv run --python 3.14 --extra dev python -m mypy src
```

Result: `80 passed in 0.86s`; ruff clean; mypy clean across 12 source files.

After merge to `main`, run a smaller WISE diagnostic field in alert dry-run mode
and compare:

- WISE rows fetched should be far below `85335` for the Taurus-like setup.
- Detection candidates should be archive singleton candidates rather than
  arbitrary same-night point-source pairs.
- Any linked tracklet must still be reviewed as a candidate, not a confirmed NEO.
