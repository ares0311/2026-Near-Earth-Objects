# Gate Z3 new candidate source: UW ZTF public alert archive (2026-07-02)

## Why the standard IRSA ZTF archive products don't close Gate Z3

Researched via WebSearch (this sandbox's network proxy blocks direct
WebFetch/curl to `irsa.ipac.caltech.edu`, so pages could not be fetched
directly — findings are from WebSearch result summaries, not a fetched page,
and should be independently confirmed before being treated as authoritative).

IRSA hosts two ZTF catalog products relevant here:

1. **Objects Table** — PSF-fit photometry detections extracted from *stacked
   reference-image coadds* (all single exposures for a science program
   stacked together). Rows are keyed to one fixed sky position per object.
2. **Lightcurves** — PSF-fit photometry extracted from *single-exposure*
   images, but explicitly "at the locations of Objects Table detections" —
   i.e. re-measured at the Objects table's fixed position, not a fresh
   detection at wherever a source actually was in that exposure.

**Both are structurally unsuited to moving-object detection.** A genuine NEO
is not at the same RA/Dec across exposures — it moves. A catalog built
around "photometry time series at one fixed position" cannot represent a
tracklet spanning multiple positions. This is consistent with Gate Z1's
existing finding (image metadata only) and explains why simply extending
Gate Z1's IRSA ingest tool to a "sources" endpoint would not work — no such
per-epoch, per-position table exists in the standard coadd/lightcurve
system. One WebSearch result stated explicitly: *"There is no separate DB
table that stores the contents of the epochal source catalog files."*

## New candidate: UW ZTF public alert archive

`https://ztf.uw.edu/alerts/public/` — described (via WebSearch, University
of Washington-hosted) as a bulk historical archive of ZTF's alert stream:
one tar file per UTC night, each containing that night's alerts in AVRO
format, covering the **full unfiltered 5-sigma alert stream since
2018-06-04**. Explicitly framed as "a simple alternative to public event
brokers" (MARS, Lasair, ANTARES, ALeRCE) for downloading historical data,
not a live feed.

The AVRO `candidate` schema (from
`github.com/ZwickyTransientFacility/ztf-avro-alert`, confirmed via
WebSearch, not fetched directly) includes, per alert:
- `jd` (double) — "Observation Julian date at start of exposure"
- `ra`, `dec` (double) — "Right Ascension/Declination of candidate; J2000 [deg]"
- `fid` (int) — filter ID
- `magpsf`, `sigmapsf` — PSF-fit magnitude and uncertainty

These are genuine per-epoch, per-position detections from actual
difference-image processing — exactly the (RA, Dec, time, magnitude) rows
Gate Z3's linker needs, and structurally capable of representing a moving
tracklet (unlike Objects/Lightcurves). Each packet also includes
`prv_candidates`, an array of prior detections at that sky position from
the last 30 days — useful context but not a substitute for the archive
itself, since Gate Z3 needs full-field coverage, not single-position
history.

## Why this is not yet verified and must not be built against

1. **This sandbox cannot reach the domain.** Both direct `curl` and the
   `WebFetch` tool return HTTP 403 at the network proxy level for
   `ztf.uw.edu`, `irsa.ipac.caltech.edu`, and `zwickytransientfacility.github.io`
   alike — this appears to be a broad proxy policy affecting many external
   domains from this sandbox, not something specific to this one candidate.
   Only `WebSearch` (routed differently) produced any information.
2. **All findings above come from WebSearch result summaries**, not a
   fetched page — the actual page content, real HTTP status, actual file
   listing, and any authentication requirement are unconfirmed.
3. Per the discovery brief's Phase 0 requirement and the standing rule
   against inventing/guessing endpoints, **no ingestion code should be
   written against this source** until either:
   - the operator (real internet access) runs the probe added to
     `Skills/verify_ztf_dr24_sources.py` (id: `uw_ztf_alert_archive_listing`)
     and confirms a real HTTP 200 with an actual file listing, or
   - the operator's research agent independently verifies reachability,
     authentication requirements, and the real per-night file naming
     convention.

## Next step

Operator command (read-only, checkpointed, retry-with-backoff — reuses the
existing Phase 0 probe tool rather than an ad hoc `curl`):

```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/verify_ztf_dr24_sources.py
```

This re-runs all five existing Phase 0 probes plus the new
`uw_ztf_alert_archive_listing` probe, and writes results to
`docs/evidence/phase0/data_sources_verified.md` and `auth_requirements.md`
from the real observed HTTP response — not from this summary.

If the listing page is reachable, the follow-up work (not yet started, not
yet designed) would be: verify one specific night's tar file downloads
correctly, verify the AVRO schema by actually parsing one packet, and
confirm total archive size / bandwidth implications for the "unfiltered
5-sigma" volume across a multi-night bounded window (this is a firehose —
ZTF processes ~100,000+ alerts/night at peak — before proposing any bounded
Gate Z3 ingest window design against it.
