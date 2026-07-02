#!/usr/bin/env python
"""Gate Z1 -- bounded ZTF DR24 historical replay ingest (dry-run, metadata only).

Per docs/ZTF_DR24_PRODUCTION_GATES.md Gate Z1: "A dry-run command ingests a
small, documented ZTF DR24 historical window from public archive sources,
writes a sample ingest report with row/file counts and hashes, and performs
no live alert-stream discovery."

This script queries ONLY the source verified in Phase 0
(docs/evidence/phase0/data_sources_verified.md): the public IRSA ZTF science
image metadata endpoint. It does not touch the ZTF alert stream (prohibited
for discovery) and does not touch Fink (confirmed externally blocked).

Verified request syntax (not guessed -- see docs cited below):
  - POS=<ra>,<dec>            spatial point (IRSA IBE Image Server API,
                               https://irsa.ipac.caltech.edu/ibe/ibe_search_api.html)
  - SIZE=<deg>[,<deg>]        search-box width[,height] in decimal degrees
                               (same doc)
  - WHERE=obsjd>X+AND+obsjd<Y time-bound filter on the observation Julian
                               date column (https://irsa.ipac.caltech.edu/docs/program_interface/ztf_api.html)
  - Response is an IPAC ASCII table (confirmed live in Phase 0 probe:
    docs/evidence/phase0/phase0_probe_results.json, "\\fixlen = T" header,
    "\\RowsRetrieved = N" row count line) -- parsed here with
    astropy.io.ascii(format="ipac"), the same library already used elsewhere
    in this project for astronomical table I/O.

This is METADATA-ONLY ingest (image/exposure records: sky position, field,
CCD/quadrant, filter, obsdate/obsjd, seeing, magnitude limit). It does not
fetch per-source photometry or difference-image cutouts -- that is later
pipeline work, not Gate Z1's scope.

Bounded by design: both the sky-search box size and the time window are
capped (see _MAX_SIZE_DEG, _MAX_WINDOW_DAYS) and must be passed explicitly
by the caller -- there is no default "search everything" mode.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \\
        --ra 358.3 --dec 25.6 --size-deg 0.2 \\
        --start-jd 2460310.5 --end-jd 2460311.5
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Bounds enforced on every run so this can never become an unbounded scrape.
# ---------------------------------------------------------------------------
_MAX_SIZE_DEG = 2.0
_MAX_WINDOW_DAYS = 400.0

_IRSA_SCI_URL = "https://irsa.ipac.caltech.edu/ibe/search/ztf/products/sci"
# Columns confirmed present in the live Phase 0 IRSA response preview
# (docs/evidence/phase0/phase0_probe_results.json).
_COLUMNS = (
    "ra,dec,field,ccdid,qid,rcid,fid,filtercode,obsdate,obsjd,exptime,seeing,maglimit,infobits"
)

_CACHE_ROOT = Path("Logs/pipeline_runs/ztf_dr24_bounded_ingest")
_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = (2, 4, 8, 16, 32)


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _run_key(ra: float, dec: float, size_deg: float, start_jd: float, end_jd: float) -> str:
    """Stable checkpoint key from the exact search parameters, so re-running
    the identical command resumes instead of re-querying (checkpoint/resume
    standing rule)."""
    payload = json.dumps(
        {"ra": ra, "dec": dec, "size_deg": size_deg, "start_jd": start_jd, "end_jd": end_jd},
        sort_keys=True,
    )
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def _build_url(ra: float, dec: float, size_deg: float, start_jd: float, end_jd: float) -> str:
    """Build the IRSA IBE query URL from verified parameter syntax (POS/SIZE
    spatial box, WHERE obsjd time bound, COLUMNS projection)."""
    where = f"obsjd>{start_jd}+AND+obsjd<{end_jd}"
    return f"{_IRSA_SCI_URL}?POS={ra},{dec}&SIZE={size_deg}&WHERE={where}&COLUMNS={_COLUMNS}"


def _fetch_with_retry(url: str) -> requests.Response:
    """GET with exponential-backoff retry (2/4/8/16/32s, 5 attempts), catching
    (ConnectionError, TimeoutError, OSError) per the standing network-retry
    rule. requests.exceptions.ConnectionError/Timeout both subclass OSError."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp
        except (ConnectionError, TimeoutError, OSError, requests.HTTPError) as exc:
            last_exc = exc
            print(
                f"[ingest] attempt {attempt}/{_MAX_ATTEMPTS} failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(
        f"IRSA ZTF sci metadata fetch failed after {_MAX_ATTEMPTS} attempts"
    ) from last_exc


def _parse_ipac_table(raw_text: str):
    """Parse the IPAC ASCII table response into an astropy Table. Raises if
    QUERY_STATUS is not OK -- fail closed rather than silently returning an
    empty/garbage table."""
    from astropy.io import ascii as ap_ascii  # lazy import, matches project convention

    if "QUERY_STATUS = 'OK'" not in raw_text and 'QUERY_STATUS = "OK"' not in raw_text:
        raise RuntimeError(
            "IRSA response did not report QUERY_STATUS = OK -- refusing to "
            "parse a failed/partial query as data"
        )
    return ap_ascii.read(raw_text, format="ipac")


def run_bounded_ingest(
    ra: float,
    dec: float,
    size_deg: float,
    start_jd: float,
    end_jd: float,
    out_dir: Path,
) -> dict:
    """Run one bounded, checkpointed ZTF DR24 sci-metadata ingest and return
    the sample-ingest-report dict. No candidate detection, no live alert
    stream -- metadata ingest only, per Gate Z1's scope."""
    if size_deg <= 0 or size_deg > _MAX_SIZE_DEG:
        raise ValueError(f"size_deg must be in (0, {_MAX_SIZE_DEG}], got {size_deg}")
    if end_jd <= start_jd:
        raise ValueError(f"end_jd ({end_jd}) must be greater than start_jd ({start_jd})")
    window_days = end_jd - start_jd
    if window_days > _MAX_WINDOW_DAYS:
        raise ValueError(
            f"time window is {window_days:.1f} days, exceeds the bounded cap "
            f"of {_MAX_WINDOW_DAYS} days -- narrow the window or run multiple "
            f"bounded ingests"
        )

    key = _run_key(ra, dec, size_deg, start_jd, end_jd)
    run_dir = out_dir / key
    checkpoint_path = run_dir / "checkpoint.json"
    raw_path = run_dir / "ztf_sci_metadata.ipac"
    t0 = time.monotonic()

    if checkpoint_path.exists() and raw_path.exists():
        print(
            f"[resume] run {key}: checkpoint and raw response already present, skipping fetch",
            flush=True,
        )
        raw_text = raw_path.read_text()
    else:
        url = _build_url(ra, dec, size_deg, start_jd, end_jd)
        print(
            f"[ingest] Requesting {url}  elapsed {_fmt_duration(time.monotonic() - t0)}", flush=True
        )
        resp = _fetch_with_retry(url)
        raw_text = resp.text
        run_dir.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_text)
        print(
            f"[ingest] Received {len(raw_text.encode())} bytes  "
            f"elapsed {_fmt_duration(time.monotonic() - t0)}",
            flush=True,
        )

    table = _parse_ipac_table(raw_text)
    n_rows = len(table)
    nights = set()
    if "obsjd" in table.colnames:
        nights = {int(float(v)) for v in table["obsjd"]}
    fields = set()
    if "field" in table.colnames:
        fields = {int(v) for v in table["field"]}

    raw_hash = hashlib.sha256(raw_text.encode()).hexdigest()
    report = {
        "query": {
            "ra": ra,
            "dec": dec,
            "size_deg": size_deg,
            "start_jd": start_jd,
            "end_jd": end_jd,
        },
        "n_rows": n_rows,
        "n_distinct_nights": len(nights),
        "n_distinct_fields": len(fields),
        "raw_response_path": str(raw_path),
        "raw_response_sha256": raw_hash,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(report, indent=2))
    report_path = run_dir / "sample_ingest_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print(
        f"[ingest] Parsed {n_rows} rows across {len(nights)} distinct night(s), "
        f"{len(fields)} distinct field(s)  elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    print(f"[ingest] Wrote {report_path}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--ra", type=float, required=True, help="Cone-search center RA in decimal degrees"
    )
    parser.add_argument(
        "--dec", type=float, required=True, help="Cone-search center Dec in decimal degrees"
    )
    parser.add_argument(
        "--size-deg",
        type=float,
        required=True,
        help=f"Search-box width/height in decimal degrees, must be in (0, {_MAX_SIZE_DEG}]",
    )
    parser.add_argument("--start-jd", type=float, required=True, help="Window start, Julian date")
    parser.add_argument("--end-jd", type=float, required=True, help="Window end, Julian date")
    parser.add_argument(
        "--out-dir",
        default=str(_CACHE_ROOT),
        metavar="DIR",
        help="Override the Logs/pipeline_runs checkpoint root (advanced/testing use)",
    )
    args = parser.parse_args()

    run_bounded_ingest(
        args.ra, args.dec, args.size_deg, args.start_jd, args.end_jd, Path(args.out_dir)
    )


if __name__ == "__main__":
    main()
