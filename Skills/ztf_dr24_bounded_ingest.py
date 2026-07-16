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
fetch per-source photometry or image pixels. The optional
``--emit-motion-product-manifest`` mode derives the documented URLs for the
single-exposure products needed by a future source-native motion extractor;
it still downloads no products and records their availability as unverified.

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
    "ra,dec,field,ccdid,qid,rcid,fid,filtercode,pid,obsdate,obsjd,filefracday,"
    "imgtypecode,exptime,seeing,maglimit,infobits,ipac_pub_date"
)

# Product suffixes and semantics are documented by IRSA's ZTF metadata page.
# Difference pixels are the source-native detection input; the science mask,
# science PSF catalog, and difference PSF provide artifact/static-source vetoes
# and extraction context without treating position-matched alert history as
# moving-object observations.
_MOTION_PRODUCT_SUFFIXES = {
    "difference_image": "scimrefdiffimg.fits.fz",
    "science_mask": "mskimg.fits",
    "science_psf_catalog": "psfcat.fits",
    "difference_psf": "diffimgpsf.fits",
}
_IRSA_DATA_ROOT = "https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci"
_MOTION_MANIFEST_SCHEMA = "ztf-dr24-motion-product-manifest-v1"
_QUALITY_FILTER = "infobits<33554432"

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
        {
            "ra": ra,
            "dec": dec,
            "size_deg": size_deg,
            "start_jd": start_jd,
            "end_jd": end_jd,
            # Include the projection contract so a schema change cannot resume
            # an older raw response that lacks newly required columns.
            "columns": _COLUMNS,
            # Include the selection policy for the same reason: changing a
            # quality constraint must force a fresh metadata response.
            "quality_filter": _QUALITY_FILTER,
        },
        sort_keys=True,
    )
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def _build_url(ra: float, dec: float, size_deg: float, start_jd: float, end_jd: float) -> str:
    """Build the IRSA IBE query URL from verified parameter syntax (POS/SIZE
    spatial box, WHERE obsjd time bound, COLUMNS projection)."""
    # DR24 release notes section 12.b.i recommends INFOBITS < 33554432 when
    # selecting likely usable single-exposure products. Apply that documented
    # threshold before planning any downstream product acquisition.
    where = f"obsjd>{start_jd}+AND+obsjd<{end_jd}+AND+{_QUALITY_FILTER}"
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


def _science_product_url(row: object, suffix: str) -> str:
    """Derive one IRSA science-product URL from a metadata-table row.

    The path pattern is copied from IRSA's official ZTF metadata contract.
    Validation is deliberately strict because a malformed identifier would
    otherwise produce a plausible-looking but invented archive URL.
    """
    filefracday = str(int(row["filefracday"]))
    if len(filefracday) != 14 or not filefracday.isdigit():
        raise ValueError(f"invalid ZTF filefracday {filefracday!r}; expected 14 digits")
    field = int(row["field"])
    ccdid = int(row["ccdid"])
    qid = int(row["qid"])
    filtercode = str(row["filtercode"]).strip()
    imgtypecode = str(row["imgtypecode"]).strip()
    if not (0 <= field <= 999999 and 1 <= ccdid <= 16 and 1 <= qid <= 4):
        raise ValueError(
            "invalid ZTF product identifiers: "
            f"field={field}, ccdid={ccdid}, qid={qid}"
        )
    if not filtercode or not imgtypecode:
        raise ValueError("filtercode and imgtypecode must be populated")

    year = filefracday[:4]
    month_day = filefracday[4:8]
    fracday = filefracday[8:14]
    basename = (
        f"ztf_{filefracday}_{field:06d}_{filtercode}_c{ccdid:02d}_"
        f"{imgtypecode}_q{qid}_{suffix}"
    )
    return f"{_IRSA_DATA_ROOT}/{year}/{month_day}/{fracday}/{basename}"


def _build_motion_product_manifest(table: object, query: dict, raw_hash: str) -> dict:
    """Build a metadata-only acquisition plan for source-native products.

    Every URL remains explicitly unverified because DR24 states that a
    difference product exists only when a reference image existed during the
    original processing. A later bounded HEAD preflight must select available
    rows before any pixels are downloaded.
    """
    required_columns = {
        "pid",
        "obsjd",
        "field",
        "ccdid",
        "qid",
        "filtercode",
        "filefracday",
        "imgtypecode",
        "infobits",
    }
    missing = sorted(required_columns.difference(table.colnames))
    if missing:
        raise RuntimeError(
            "IRSA metadata response is missing motion-manifest columns: " + ", ".join(missing)
        )

    exposures = []
    for row in table:
        exposures.append(
            {
                "pid": int(row["pid"]),
                "obsjd": float(row["obsjd"]),
                "field": int(row["field"]),
                "ccdid": int(row["ccdid"]),
                "qid": int(row["qid"]),
                "filtercode": str(row["filtercode"]).strip(),
                "filefracday": str(int(row["filefracday"])),
                "imgtypecode": str(row["imgtypecode"]).strip(),
                "infobits": int(row["infobits"]),
                "availability": "unverified",
                "product_urls": {
                    product_name: _science_product_url(row, suffix)
                    for product_name, suffix in _MOTION_PRODUCT_SUFFIXES.items()
                },
            }
        )

    return {
        "schema_version": _MOTION_MANIFEST_SCHEMA,
        "artifact_kind": "metadata_only_acquisition_plan",
        "data_role": "live_search",
        "source_name": "IRSA ZTF single-exposure archive",
        "source_release": "DR24",
        "source_metadata_url": _IRSA_SCI_URL,
        "source_documentation": [
            "https://irsa.ipac.caltech.edu/docs/program_interface/ztf_api.html",
            "https://irsa.ipac.caltech.edu/docs/program_interface/ztf_metadata.html",
            "https://irsa.ipac.caltech.edu/data/ZTF/docs/releases/dr24/ztf_release_notes_dr24.pdf",
        ],
        "query": query,
        "raw_metadata_sha256": raw_hash,
        "n_exposures": len(exposures),
        "availability_policy": (
            "unverified until bounded HEAD preflight; do not download or treat a URL as present "
            "from filename construction alone"
        ),
        "quality_filter": "infobits < 33554432",
        "products": dict(_MOTION_PRODUCT_SUFFIXES),
        "exposures": exposures,
    }


def run_bounded_ingest(
    ra: float,
    dec: float,
    size_deg: float,
    start_jd: float,
    end_jd: float,
    out_dir: Path,
    emit_motion_product_manifest: bool = False,
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
    fields = set()
    if "field" in table.colnames:
        fields = {int(v) for v in table["field"]}

    # Map each row's real UTC calendar date (matching the alert archive's
    # ztf_public_YYYYMMDD.tar.gz naming) directly from its raw, fractional
    # obsjd -- NOT from a pre-truncated integer JD. JD increments at NOON
    # UTC, not midnight, so int(obsjd) silently lands on noon UTC of the
    # day BEFORE the correct calendar date whenever the fractional part is
    # < 0.5 (confirmed live: obsjd 2458339.6521991, from the packet already
    # verified to originate in ztf_public_20180809.tar.gz, truncates to
    # int 2458339 -- which converts back to 2018-08-08 12:00 UTC, not
    # 2018-08-09). Deriving the date from each row's full obsjd value
    # avoids this trap entirely.
    from astropy.time import Time  # lazy import, matches project convention

    distinct_nights_yyyymmdd = sorted(
        {Time(float(v), format="jd").datetime.strftime("%Y%m%d") for v in table["obsjd"]}
        if "obsjd" in table.colnames
        else set()
    )

    raw_hash = hashlib.sha256(raw_text.encode()).hexdigest()
    query = {
        "ra": ra,
        "dec": dec,
        "size_deg": size_deg,
        "start_jd": start_jd,
        "end_jd": end_jd,
    }
    report = {
        "query": query,
        "n_rows": n_rows,
        "n_distinct_nights": len(distinct_nights_yyyymmdd),
        "distinct_nights_yyyymmdd": distinct_nights_yyyymmdd,
        "n_distinct_fields": len(fields),
        "raw_response_path": str(raw_path),
        "raw_response_sha256": raw_hash,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    if emit_motion_product_manifest:
        manifest = _build_motion_product_manifest(table, query, raw_hash)
        manifest_path = run_dir / "motion_product_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        report["motion_product_manifest_path"] = str(manifest_path)
        report["motion_product_manifest_exposures"] = manifest["n_exposures"]
        print(
            f"[ingest] Planned source-native products for {manifest['n_exposures']} exposure(s); "
            "availability remains unverified and no products were downloaded",
            flush=True,
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(report, indent=2))
    report_path = run_dir / "sample_ingest_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print(
        f"[ingest] Parsed {n_rows} rows across {len(distinct_nights_yyyymmdd)} distinct night(s), "
        f"{len(fields)} distinct field(s)  elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    print(f"[ingest] Distinct real nights (YYYYMMDD): {distinct_nights_yyyymmdd}", flush=True)
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
    parser.add_argument(
        "--emit-motion-product-manifest",
        action="store_true",
        help=(
            "Write a metadata-only plan containing documented difference-image, mask, "
            "science-catalog, and difference-PSF URLs; downloads no products"
        ),
    )
    args = parser.parse_args()

    run_bounded_ingest(
        args.ra,
        args.dec,
        args.size_deg,
        args.start_jd,
        args.end_jd,
        Path(args.out_dir),
        emit_motion_product_manifest=args.emit_motion_product_manifest,
    )


if __name__ == "__main__":
    main()
