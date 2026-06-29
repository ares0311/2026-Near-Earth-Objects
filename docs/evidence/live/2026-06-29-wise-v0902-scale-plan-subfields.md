# WISE v0.90.2 Scale-Plan Subfield Selection

Date: 2026-06-29 UTC

## Purpose

Regenerate the Taurus 0.2-degree, 370-day WISE/NEOWISE scale plan on merged
`main` after v0.90.2, so the next D1 diagnostic uses parameters emitted by the
pipeline instead of guessed sky coordinates.

## Command

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_MAX_THREADS=1 PYTHONPATH=src caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 58.0 --dec 20.0 --radius 0.2 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --force-refresh \
  --link-scale-plan-out Logs/reports/wise_link_scale_plan_v0902_58_20_370d.json \
  --output Logs/reports/wise_link_scale_plan_probe_v0902_58_20_370d.json
```

## Results

- Mode: dry run; no external submission
- Run ID: `296774bc0b0e`
- Field: RA `58.0`, Dec `20.0`, radius `0.2` degrees
- Window: JD `2458880.5` to `2459250.5`
- Survey: WISE
- WISE rows/alerts: `12061`
- Preprocessed sources: `12042/12061`
- Detected singleton candidates: `12042`
- Known matches: `0`
- Estimated seed pairs: `11786731`
- Default seed-pair budget: `1000000`
- Outcome: expected fail-closed `blocked_link_seed_budget`
- Scale-plan JSON written locally:
  `Logs/reports/wise_link_scale_plan_v0902_58_20_370d.json`
- Compact blocked output written locally:
  `Logs/reports/wise_link_scale_plan_probe_v0902_58_20_370d.json`

Top night-pair contributors:

| Night A | Night B | Seed pairs |
|---:|---:|---:|
| `2459084` | `2459085` | `9102120` |
| `2459243` | `2459244` | `2503474` |
| `2459242` | `2459243` | `164571` |
| `2459242` | `2459244` | `16566` |

The v0.90.2 scale plan recommended a diagnostic radius of `0.0466` degrees.
The first recommended diagnostic subfield is:

| RA | Dec | Radius | Start JD | End JD | Survey |
|---:|---:|---:|---:|---:|---|
| `58.1` | `20.1` | `0.0466` | `2458880.5` | `2459250.5` | `WISE` |

## Next Command

Run this from `main` to execute the first verified bounded subfield. It is
dry-run only, writes full review packets, uses Python 3.14 through `uv`, keeps
native numerical threads bounded, and does not enable external submission.

```bash
git pull origin main

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_MAX_THREADS=1 PYTHONPATH=src caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 58.1 --dec 20.1 --radius 0.0466 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --force-refresh \
  --review-packet-out Logs/reports/wise_diag_subfield_58p1_20p1_review_packets.json \
  --output Logs/reports/wise_diag_subfield_58p1_20p1_candidates.json
```

If the run produces full review packets, run adversarial review offline:

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py Logs/reports/wise_diag_subfield_58p1_20p1_review_packets.json --offline --json > Logs/reports/wise_diag_subfield_58p1_20p1_adversarial_review.json
```

## Interpretation

The full 0.2-degree field remains too large for the current all-pairs linker.
The selected subfield is a bounded diagnostic emitted by the v0.90.2 scale plan;
it is not complete-field evidence and does not prove production-scale tiling
completeness. Naive sky-cell tiling can miss objects that cross cell boundaries.

## Safety

No MPC submission was performed. No NASA/PDCO pathway was triggered. No impact
probability was computed or claimed. Raw run outputs remain under ignored
`Logs/`; this document is the durable sanitized evidence.
