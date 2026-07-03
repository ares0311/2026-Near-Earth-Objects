# Gate Z1 — wider-window run finds a real second night at the Gate Z3 target field

Date: 2026-07-02. Operator: Jerome W. Lindsey III. Branch: `main` @
`b3778df` (v0.90.37).

## Command

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 2.0 \
    --start-jd 2458339.5 --end-jd 2458439.5
```

100-day window from night 20180809, same 2-degree sky box used throughout
the Gate Z3 work.

## Console output (verbatim)

```
[ingest] Requesting https://irsa.ipac.caltech.edu/ibe/search/ztf/products/sci?POS=232.6,-8.4&SIZE=2.0&WHERE=obsjd>2458339.5+AND+obsjd<2458439.5&COLUMNS=ra,dec,field,ccdid,qid,rcid,fid,filtercode,obsdate,obsjd,exptime,seeing,maglimit,infobits  elapsed 0m00s
[ingest] Received 4441 bytes  elapsed 0m04s
[ingest] Parsed 14 rows across 2 distinct night(s), 1 distinct field(s)  elapsed 0m05s
[ingest] Wrote Logs/pipeline_runs/ztf_dr24_bounded_ingest/af142e089e85/sample_ingest_report.json
```

## Result

- Real, live, non-mocked IRSA response: **14 rows across 2 distinct real
  nights**, all in the same single ZTF field, within a 100-day window
  starting at night 20180809.
- This is the first real evidence of a second real observing night at this
  exact sky position -- confirming the field is revisited, just far less
  often than every 3 nights (the 10-day window in the prior evidence file
  found only 1 night; widening to 100 days found the 2nd).
- **Follow-up fix (v0.90.38)**: the tool's report only exposed
  `n_distinct_nights` (a count), not which nights they were, which blocked
  identifying the actual second night to target for the Gate Z3
  alert-archive ingest. Added `distinct_nights_yyyymmdd` to the report
  (converts each `obsjd` to a real UTC calendar date matching the archive's
  `ztf_public_YYYYMMDD.tar.gz` naming), computed from the **already-cached**
  raw IPAC response at
  `Logs/pipeline_runs/ztf_dr24_bounded_ingest/af142e089e85/ztf_sci_metadata.ipac`
  -- no new network call was needed, the identical command resumes from
  checkpoint and just re-derives the report.

## Next step

Re-run the identical command above (now on v0.90.38+) to get the real
`distinct_nights_yyyymmdd` list from the cached response without a new
fetch, then target `Skills/ztf_alert_archive_ingest.py` at exactly those
two real nights for the Gate Z3 "known-object positive control" attempt.
