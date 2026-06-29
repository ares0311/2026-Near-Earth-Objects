# WISE 0.2-Degree Full-Year Capped Dry Run

Date: 2026-06-29 UTC

## Purpose

Validate the selected Taurus WISE/NEOWISE multi-night window through the full
pipeline without external submission, while keeping linker work bounded.

## Commands

The full uncapped 0.2-degree dry run was attempted first after the linker
arc-extension optimization. It fetched and detected successfully, but linking
`12042` singleton candidates required `11786731` seed pairs and projected tens
of minutes of all-pairs work. The run was interrupted intentionally before any
results were written. Do not repeat the uncapped command as the next diagnostic.

The completed bounded diagnostic used an explicit cap:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_MAX_THREADS=1 PYTHONPATH=src caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 58.0 --dec 20.0 --radius 0.2 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --max-candidates 2000 \
  --output Logs/reports/wise_prefilter_diagnostic_58_20_370d_r0p2_cap2000.json
```

Adversarial review was then run offline against the compact output:

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py Logs/reports/wise_prefilter_diagnostic_58_20_370d_r0p2_cap2000.json --offline --json > Logs/reports/wise_prefilter_diagnostic_58_20_370d_r0p2_cap2000_adversarial_review.json
```

## Results

- Run ID: `296774bc0b0e`
- Mode: dry run; no external submission
- Field: RA `58.0`, Dec `20.0`, radius `0.2` degrees
- Window: JD `2458880.5` to `2459250.5`
- Survey: WISE
- WISE rows/alerts: `12061`
- Preprocessed sources: `12042/12061`
- Detected singleton candidates: `12042`
- Explicit link cap: first `2000/12042` candidates
- Link seed pairs under cap: `243289`
- Tracklets formed: `19`
- Candidates processed: `19`
- Submission-ready candidates: `0`
- Pipeline elapsed time: `35.32` seconds

All printed candidate summaries had `alert_pathway=internal_candidate`,
unknown hazard flag, unknown MOID, very low NEO posterior, and high artifact
posterior. The run did not assert impact probability.

## Adversarial Review Outcome

`Skills/adversarial_review.py` now fails closed on compact pipeline summary
rows. The bounded WISE report contains flattened result rows rather than full
`ScoredNEO` review packets, so the review produced `19/19` structured
`REJECT` verdicts with `review_packet_schema` as the failing challenge.

This is the correct safety behavior, but it identifies the next production
code task: export or preserve full `ScoredNEO` evidence packets from
`run_pipeline.py` so automated adversarial review can evaluate real candidates
instead of rejecting compact summaries as incomplete.

## Interpretation

The selected WISE window is viable for bounded diagnostics and can produce
multi-night tracklets. The remaining production work is not data availability;
it is evidence-packet completeness and scalable linking. A full uncapped
12k-candidate pass remains too expensive for the current all-pairs linker and
should not be repeated until a scale-aware linking strategy or explicit survey
tiling plan is implemented.

## Safety

No MPC submission was performed. No NASA/PDCO pathway was triggered. No impact
probability was computed or claimed. Raw run outputs remain under ignored
`Logs/`; this document is the durable sanitized evidence.
