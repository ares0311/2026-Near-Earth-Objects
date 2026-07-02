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

## RESOLVED 2026-07-02: operator captured the real directory listing

The operator opened `https://ztf.uw.edu/alerts/public/` directly in a
browser and saved it as a PDF (139 pages, committed to the repo at
`docs/Alert Archive.pdf`, commit `b6de270`). This gives the real, observed
file listing — not a guess, not a WebSearch summary.

**Confirmed real file naming convention**: `ztf_public_YYYYMMDD.tar.gz`,
one file per UTC night. Occasional `ztf_public_YYYYMMDD_programid3.tar.gz`
variants exist for the separate "programid3" (Caltech-time / TESS-sector)
subset the page's own description mentions.

**Confirmed real coverage**: the listing runs from `ztf_public_20180601.tar.gz`
(8 years ago, near the service's own stated 2018-06-04 start) through
`ztf_public_20260702.tar.gz` ("10 hours ago" — i.e. essentially real-time
archival, not just historical). This is a genuinely complete, gapless-looking
nightly archive spanning the full ZTF survey era.

**Confirmed file sizes**: highly variable per night, observed from small
placeholder-looking entries (many nights show a bare `44` or `74` byte size
— almost certainly an empty/error placeholder rather than real data, e.g.
during the survey's early commissioning period or scheduled maintenance —
the page itself warns of scheduled maintenance windows) up to very large
real nights, e.g. `ztf_public_20181113.tar.gz` at **73G** and several other
nights above 20-40G. Recent 2026 nights typically run 5-20G. This is a
genuine data firehose and must be sized carefully before any bounded
multi-night ingest window is designed.

**Also present**: `MD5SUMS` (202K, updated "10 hours ago" — i.e. actively
maintained), `VALIDATE` / `VALIDATE.out` housekeeping files. No login
prompt or authentication barrier is visible in the captured listing —
consistent with the HTTP 200 unauthenticated probe result above.

## Why no ingestion code has been written yet

The real file naming convention is now confirmed from direct observation
(the operator's browser-captured listing), not guessed. What remains
undone before any Gate Z3 ingest tool is designed: a single bounded
download-and-inspect test of one real file, to confirm the tar/AVRO format
matches expectations, before attempting anything at the scale of a full
night (up to 73G) or a multi-night window.

## RESOLVED 2026-07-02: operator confirmed real download and tar structure

Operator ran `Skills/probe_ztf_alert_archive_file.py` on `main` @ v0.90.30.
Result: **complete success**.

- HEAD confirmed remote size 31.0MiB, matching the listing.
- GET downloaded the full file in ~3s with visible per-MiB progress and ETA.
- `tarfile.open(..., mode="r:gz")` opened it as a valid gzip/tar archive.
- **715 `.avro` members** were found inside — real per-detection alert
  packets, not a placeholder or error page.
- Sample member names (first 10), e.g. `585152193615015014.avro`,
  `585153143215010000.avro` — numeric filenames consistent with ZTF alert
  `candid` values (candidate IDs), matching the expected AVRO alert-packet
  naming convention from the schema research above.

**This confirms the UW ZTF alert archive is a real, working, unauthenticated,
per-detection candidate source for Gate Z3** — reachable, correctly
structured, and populated with the expected volume of real per-night alert
packets (715 detections for this one August 2018 night, plausible for ZTF's
alert rate).

**Not yet confirmed**: the internal AVRO schema of an individual packet —
i.e. that a packet's `candidate` record actually contains the `ra`, `dec`,
`jd`, `magpsf`, `sigmapsf` fields the WebSearch-sourced schema research
described. The tar/gzip verification above does not parse AVRO content.

## Next step: parse one real AVRO packet's schema (Skill added)

Extended `Skills/probe_ztf_alert_archive_file.py` with `--inspect-first-packet`,
which extracts and parses exactly ONE `.avro` member (the first found) using
`fastavro` (added as a new dependency — the same library the official
`ZwickyTransientFacility/ztf-avro-alert` repository's own example notebook
uses for reading these packets, per the schema research above) and prints
the top-level `candidate` record's field names and values. This is the last
verification step before any Gate Z3 ingest-tool design work: confirming
the real schema matches what was researched, not guessed.

Operator command (reuses the already-downloaded file via checkpoint/resume,
no re-download needed):

```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/probe_ztf_alert_archive_file.py --inspect-first-packet
```
