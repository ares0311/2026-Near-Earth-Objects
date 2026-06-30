# WISE v0.90.2 First Diagnostic Subfield

Date: 2026-06-29 UTC

## Purpose

Run the first WISE/NEOWISE diagnostic subfield emitted by the v0.90.2 scale
plan and determine whether it produces reviewable `ScoredNEO` packets for D1
candidate-survival testing.

## Command

```bash
git pull origin main

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_MAX_THREADS=1 PYTHONPATH=src caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
  --ra 58.1 --dec 20.1 --radius 0.0466 \
  --start-jd 2458880.5 --end-jd 2459250.5 \
  --surveys WISE --no-resume --force-refresh \
  --review-packet-out Logs/reports/wise_diag_subfield_58p1_20p1_review_packets.json \
  --output Logs/reports/wise_diag_subfield_58p1_20p1_candidates.json
```

## Results

- Run ID: `2affb62b0dc2`
- Mode: dry run; no external submission
- Field: RA `58.1`, Dec `20.1`, radius `0.0466` degrees
- Window: JD `2458880.5` to `2459250.5`
- Survey: WISE
- WISE rows/alerts: `532`
- Preprocessed sources: `531/532`
- Detected singleton candidates: `531`
- Known matches: `0`
- Integer-JD nights: `4`
- Link seed pairs: `25053`
- Rate-window seed pairs: `24373`
- Satellite/debris rejected seed pairs: `596`
- Arcs below minimum observations: `23777`
- Arcs below minimum nights: `0`
- Chi-square rejected arcs: `0`
- Tracklets formed: `0`
- Candidates processed: `0`
- Submission-ready candidates: `0`
- Review-packet file: `Logs/reports/wise_diag_subfield_58p1_20p1_review_packets.json`
- Candidate-output file: `Logs/reports/wise_diag_subfield_58p1_20p1_candidates.json`

Both local JSON outputs contained empty arrays (`[]`) because no tracklets were
formed.

## Adversarial Review Attempt

The follow-up adversarial-review command was attempted:

```bash
PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py Logs/reports/wise_diag_subfield_58p1_20p1_review_packets.json --offline --json > Logs/reports/wise_diag_subfield_58p1_20p1_adversarial_review.json
```

It failed with:

```text
ERROR: no valid ScoredNEO entries found in input.
```

This is not a candidate failure; it is an operator-command sequencing error.
The review-packet file was written but empty. Future agents must not run
`Skills/adversarial_review.py` on a review-packet file until they have verified
that the file contains at least one full `ScoredNEO` entry.

## Interpretation

The first v0.90.2 diagnostic subfield was bounded and technically successful,
but it produced no linked tracklets. The dominant rejection mode was failing to
extend rate-valid seed pairs to at least three observations. This subfield does
not advance to adversarial review or operator review.

Do not rerun this exact subfield as the next diagnostic. The next D1 step should
either select a different v0.90.2 recommended subfield or improve the subfield
selection logic so it prioritizes areas more likely to produce three-observation
tracklets rather than only high observation density.

## Safety

No MPC submission was performed. No NASA/PDCO pathway was triggered. No impact
probability was computed or claimed. Raw run outputs remain under ignored
`Logs/`; this document is the durable sanitized evidence.
