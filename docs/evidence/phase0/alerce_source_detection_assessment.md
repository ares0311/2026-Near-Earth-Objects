# ALeRCE Source-Detection Assessment for Gate Z3

Date: 2026-07-02
Scope: ZTF DR24 archival historical replay, Gate Z3 source-native candidate linking.

## Question

Can the existing ALeRCE-backed ZTF source-detection provider be treated as the
verified per-source ZTF DR24 detection source required to close Gate Z3?

## Official Sources Checked

- ALeRCE Python Client docs: `https://alerce.readthedocs.io/en/latest/`
- ZTF access tutorial: `https://alerce.readthedocs.io/en/latest/tutorials/ztf_api.html`
- ZTF detection response model: `https://alerce.readthedocs.io/en/latest/models/ztf_detection.html`
- Object response model: `https://alerce.readthedocs.io/en/latest/models/object.html`

## Verified From Official Docs

- ALeRCE exposes a Python client and ZTF API wrapper.
- `query_objects()` returns ZTF object records and supports classifier/class
  filtering.
- `query_detections()` returns detections for a ZTF object.
- The ZTF detection model includes source-level fields needed by this pipeline,
  including `magpsf`, `sigmapsf`, `rb`, `drb`, and processing/reference-image
  identifiers.
- The object model includes object-level timing and position fields including
  `firstmjd`, `lastmjd`, `meanra`, `meandec`, and `ndet`.

## Not Established By The Checked Docs

- The docs checked do not state that the ALeRCE API is a static ZTF DR24
  archive equivalent.
- The docs checked do not define a point-in-time replay cutoff or guarantee
  that query results can be reconstructed exactly as knowable at a historical
  epoch.
- The docs checked do not document a no-future-catalog-leakage mode for object
  classifications, probabilities, crossmatches, or derived features.
- The docs checked do not by themselves establish that ALeRCE is suitable for
  MPC-submission provenance as the primary DR24 historical-replay detection
  source.

## Decision

ALeRCE is a real, documented source-level ZTF detection provider and remains
valid legacy evidence that the code can ingest public ZTF detections. It does
not close Gate Z3 by itself. For the current primary ZTF DR24 historical-replay
pipeline, ALeRCE may be evaluated as a candidate source only after a bounded
live/source-verification packet documents schema, query limits, historical
coverage, and no-future-leakage implications.

## Next Action

Continue Gate Z3 source verification. Prefer a source that explicitly supports
bounded archival ZTF detections with replay-window discipline. If ALeRCE is
used, treat it as a candidate source requiring additional verification rather
than as an already-approved DR24 production source.
