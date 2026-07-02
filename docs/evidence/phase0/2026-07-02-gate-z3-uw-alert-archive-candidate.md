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

## RESOLVED 2026-07-02: operator live probe confirms reachability

Operator ran `Skills/verify_ztf_dr24_sources.py` on `main` (real internet
access, this sandbox does not have it). Result for
`uw_ztf_alert_archive_listing`: **HTTP 200**, no authentication required,
served by `Apache/2.4.6 (CentOS)` at `ztf.uw.edu`. The returned HTML body
matches the WebSearch summary word-for-word: *"compressed tar archives of
ZTF event alerts (observations detected in image differences). Each tar
file contains alerts collected in the given night (UTC-based), with each
alert stored in a separate file in the AVRO format... The files provided
contain a full, unfiltered, 5-sigma alert stream."* Full raw response
recorded in `docs/evidence/phase0/phase0_probe_results.json` (probe id
`uw_ztf_alert_archive_listing`), committed at `f3dc9c24`.

**Confirmed**: reachable, unauthenticated, real content matching the
research above (not a guess).

**Not yet confirmed**: the actual per-night file listing / naming
convention. The probe tool's 2000-character body preview was consumed by
the page's descriptive text before reaching the directory-listing HTML
(`body_truncated: true`), so no real filename has been observed yet. This
is a minor remaining gap, not a reachability or authentication concern —
see "Next step" below for the simplest way to close it.

## Why no ingestion code has been written yet

Per the discovery brief's Phase 0 requirement and the standing rule against
inventing/guessing endpoints: reachability and content are now confirmed,
but the real per-night file naming pattern is still unknown, and any
ingestion code would need to construct URLs to specific files. Guessing a
filename pattern (e.g. `YYYYMMDD.tar.gz`) without seeing a real example
would violate that rule.

## Next step (NOT YET DONE)

Ask the operator to open `https://ztf.uw.edu/alerts/public/` directly in a
browser (fastest, zero-code way to see the actual file listing — no need
for more probe-tool code for this one-time lookup) and report back a small
number of real file names/dates from the visible listing. Once a real
filename is known, the following becomes possible to scope without
guessing: one bounded single-night download test, real AVRO packet
parsing, and an estimate of total archive size for a bounded multi-night
Gate Z3 ingest window (ZTF processes ~100,000+ alerts/night at peak, so
volume/bandwidth must be sized before any ingest tool is designed).
