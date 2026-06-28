# WISE Window Night Probes

Date: 2026-06-28

Branch/run state: `main` after PR #136 and evidence commit `8f5a32b8`.

## Purpose

Select a WISE field/window that can actually exercise multi-night linking.
The previous 1.0-degree, 7-day Taurus diagnostic produced `5200` candidates on
only one integer-JD night, so a repeat would be non-informative.

## Probe 1: Same Field, 30-Day Window

Command:

```bash
PYTHONPATH=src caffeinate -i uv run --python 3.14 python -c 'from fetch import fetch_wise_archive; obs=fetch_wise_archive(58.0,20.0,1.0,2458880.5,2458910.5,force_refresh=True); nights=sorted({int(o.jd) for o in obs}); print({"n_obs": len(obs), "n_nights": len(nights), "nights": nights[:10], "last_nights": nights[-10:]})'
```

Result:

- WISE rows/observations: `5206`
- Integer-JD nights: `1`
- Nights: `[2458883]`
- TAP elapsed: about `2m33s`

Interpretation:

The same Taurus field remains a one-night WISE sample even when expanded from
7 days to 30 days. The next probe should use WISE cadence knowledge rather than
expanding this month blindly.

## Probe 2: Same Field, 195-Day Window

Command:

```bash
PYTHONPATH=src caffeinate -i uv run --python 3.14 python -c 'from fetch import fetch_wise_archive; obs=fetch_wise_archive(58.0,20.0,1.0,2458880.5,2459075.5,force_refresh=True); nights=sorted({int(o.jd) for o in obs}); print({"n_obs": len(obs), "n_nights": len(nights), "nights": nights[:20], "last_nights": nights[-20:]})'
```

Result:

- WISE rows/observations: `5206`
- Integer-JD nights: `1`
- Nights: `[2458883]`
- TAP elapsed: about `2m02s`

Interpretation:

The same Taurus field remains a one-night WISE sample even when expanded to
approximately half a year. The next diagnostic should either probe a full-year
or mission-era interval with a bounded field, or switch to a field/window with
known repeated WISE coverage.

## Safety

This was a read-only archive fetch. No MPC submission was performed. No
NASA/PDCO notification was performed. No impact-probability claim was made. No
object was described as confirmed.
