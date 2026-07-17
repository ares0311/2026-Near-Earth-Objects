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

``--pixel-extraction-pilot`` (requires ``--preflight-motion-products``) is a
tiny, hard-capped validation step: it downloads exactly ONE difference image
(the query window must resolve to exactly one exposure) and runs a minimal
numpy/scipy/astropy source detector on it, reporting candidate RA/Dec
positions. This proves a source-native motion extractor is buildable against
this product family; it is not a batch pixel downloader and never processes
more than one exposure per invocation.

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
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
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
_MAX_PREFLIGHT_EXPOSURES = 100
_MAX_PREFLIGHT_WORKERS = 6
# The pixel-extraction pilot is a tiny single-file validation step, not a
# batch downloader -- hard-capped at exactly one exposure per invocation.
_MAX_PIXEL_PILOT_EXPOSURES = 1
_PIXEL_PILOT_DETECTION_SIGMA = 5.0
_PIXEL_PILOT_MAX_SOURCES = 200


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


def _head_with_retry(url: str) -> requests.Response:
    """HEAD one planned product with the standard bounded retry schedule.

    HTTP-level missing-product responses are returned as scientific findings;
    only transport failures are retried. No response body is requested.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return requests.head(url, timeout=30, allow_redirects=True)
        except (ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc
            print(
                f"[preflight] attempt {attempt}/{_MAX_ATTEMPTS} failed "
                f"({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(
        f"IRSA ZTF product HEAD failed after {_MAX_ATTEMPTS} attempts for {url}"
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


def _save_preflight_checkpoint(path: Path, payload: dict) -> None:
    """Persist the current HEAD results after every completed product."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _preflight_motion_products(
    manifest: dict,
    checkpoint_path: Path,
    max_exposures: int,
    workers: int,
) -> dict:
    """HEAD-check a bounded motion-product plan and attach byte estimates.

    The exposure cap prevents a metadata query from silently becoming a broad
    product probe. Up to six concurrent HEAD requests match the measured IRSA
    metadata-service ceiling; every result is checkpointed immediately so an
    identical rerun resumes without repeating completed probes.
    """
    if not 1 <= max_exposures <= _MAX_PREFLIGHT_EXPOSURES:
        raise ValueError(
            f"max_preflight_exposures must be in [1, {_MAX_PREFLIGHT_EXPOSURES}]"
        )
    if not 1 <= workers <= _MAX_PREFLIGHT_WORKERS:
        raise ValueError(f"preflight_workers must be in [1, {_MAX_PREFLIGHT_WORKERS}]")

    exposures = manifest.get("exposures", [])
    if not exposures:
        raise ValueError("motion-product preflight requires at least one exposure")
    if len(exposures) > max_exposures:
        raise ValueError(
            f"motion-product preflight has {len(exposures)} exposures, exceeding the "
            f"explicit cap of {max_exposures}; narrow the metadata query"
        )

    checkpoint = {
        "schema_version": "ztf-dr24-motion-product-preflight-v1",
        "raw_metadata_sha256": manifest["raw_metadata_sha256"],
        "results": {},
    }
    if checkpoint_path.exists():
        loaded = json.loads(checkpoint_path.read_text())
        if loaded.get("schema_version") != "ztf-dr24-motion-product-preflight-v1":
            raise RuntimeError("motion-product preflight checkpoint has an unsupported schema")
        if loaded.get("raw_metadata_sha256") != manifest["raw_metadata_sha256"]:
            raise RuntimeError("motion-product preflight checkpoint does not match raw metadata")
        if not isinstance(loaded.get("results"), dict):
            raise RuntimeError("motion-product preflight checkpoint has invalid results")
        checkpoint = loaded

    tasks = []
    for exposure in exposures:
        pid = int(exposure["pid"])
        for product_name, url in exposure["product_urls"].items():
            task_key = f"{pid}:{product_name}"
            existing = checkpoint["results"].get(task_key)
            if existing and existing.get("url") == url:
                print(f"[resume] preflight {task_key}: already checked, skipping", flush=True)
                continue
            tasks.append((task_key, url))

    total_products = sum(len(exposure["product_urls"]) for exposure in exposures)
    already_complete = total_products - len(tasks)
    started = time.monotonic()
    if tasks:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_head_with_retry, url): (task_key, url)
                for task_key, url in tasks
            }
            for completed_in_run, future in enumerate(as_completed(futures), start=1):
                task_key, url = futures[future]
                try:
                    response = future.result()
                    raw_length = response.headers.get("content-length")
                    content_length = (
                        int(raw_length) if raw_length and raw_length.isdigit() else None
                    )
                    status_code = response.status_code
                    content_type = response.headers.get("content-type")
                    error = None
                except RuntimeError as exc:
                    # Preserve a fail-closed result for this product while still
                    # collecting/checkpointing sibling futures that completed.
                    content_length = None
                    status_code = None
                    content_type = None
                    error = str(exc)
                available = status_code == 200 and content_length is not None and content_length > 0
                checkpoint["results"][task_key] = {
                    "url": url,
                    "status_code": status_code,
                    "content_length_bytes": content_length,
                    "content_type": content_type,
                    "available": available,
                    "error": error,
                    "checked_at_utc": datetime.now(UTC).isoformat(),
                }
                _save_preflight_checkpoint(checkpoint_path, checkpoint)
                completed = already_complete + completed_in_run
                elapsed = time.monotonic() - started
                seconds_per_product = elapsed / completed_in_run
                eta = seconds_per_product * (len(tasks) - completed_in_run)
                print(
                    f"[preflight] {completed}/{total_products} {task_key}: "
                    f"HTTP {status_code}, bytes={content_length}  "
                    f"elapsed {_fmt_duration(elapsed)}  ETA {_fmt_duration(eta)}",
                    flush=True,
                )

    total_bytes = 0
    all_available = True
    for exposure in exposures:
        pid = int(exposure["pid"])
        product_headers = {}
        for product_name in exposure["product_urls"]:
            result = checkpoint["results"].get(f"{pid}:{product_name}")
            if result is None:
                all_available = False
                continue
            product_headers[product_name] = result
            all_available = all_available and bool(result["available"])
            if result["available"]:
                total_bytes += int(result["content_length_bytes"])
        exposure["product_headers"] = product_headers
        exposure_available = len(product_headers) == len(exposure["product_urls"]) and all(
            item["available"] for item in product_headers.values()
        )
        exposure["availability"] = "verified" if exposure_available else "unavailable"
        exposure["verified_content_bytes"] = sum(
            int(item["content_length_bytes"])
            for item in product_headers.values()
            if item["available"]
        )

    manifest["preflight"] = {
        "status": "passed" if all_available else "failed",
        "all_required_products_available": all_available,
        "checked_products": sum(
            1
            for exposure in exposures
            for product_name in exposure["product_urls"]
            if f"{int(exposure['pid'])}:{product_name}" in checkpoint["results"]
        ),
        "expected_products": total_products,
        "total_content_bytes": total_bytes,
        "max_exposures": max_exposures,
        "workers": workers,
        "checkpoint_path": str(checkpoint_path),
    }
    return manifest


def _fetch_binary_with_retry(url: str) -> bytes:
    """GET a binary science product with the standard bounded retry schedule
    and return its raw body bytes. Used only by the single-exposure pixel-
    extraction pilot below -- never for a batch download."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            return resp.content
        except (ConnectionError, TimeoutError, OSError, requests.HTTPError) as exc:
            last_exc = exc
            print(
                f"[pixel-pilot] attempt {attempt}/{_MAX_ATTEMPTS} failed "
                f"({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(
        f"pixel-extraction pilot product fetch failed after {_MAX_ATTEMPTS} attempts: {url}"
    ) from last_exc


def _psf_shape_correlation(
    data, x: int, y: int, psf_kernel
) -> float | None:
    """Pearson correlation between a cutout of `data` centered at (x, y) and
    the PSF kernel, both flattened. 1.0 means the local pixel pattern is
    shaped like the PSF; values near 0 or negative mean it is not (a cosmic
    ray spike, a bad-column edge, or other non-point-source artifact does
    not correlate well with a smooth PSF). Returns None when a full cutout
    cannot be extracted (source too close to the image edge) rather than
    fabricating a value from a partial/padded cutout.
    """
    import numpy as np

    half_h, half_w = psf_kernel.shape[0] // 2, psf_kernel.shape[1] // 2
    y0, y1 = y - half_h, y - half_h + psf_kernel.shape[0]
    x0, x1 = x - half_w, x - half_w + psf_kernel.shape[1]
    if y0 < 0 or x0 < 0 or y1 > data.shape[0] or x1 > data.shape[1]:
        return None
    cutout = data[y0:y1, x0:x1]
    if cutout.shape != psf_kernel.shape or not np.all(np.isfinite(cutout)):
        return None
    cutout_flat = cutout.ravel()
    psf_flat = psf_kernel.ravel()
    if np.std(cutout_flat) == 0 or np.std(psf_flat) == 0:
        return None
    return float(np.corrcoef(cutout_flat, psf_flat)[0, 1])


def _detect_sources_in_difference_image(
    fits_bytes: bytes,
    mask_fits_bytes: bytes | None = None,
    psf_fits_bytes: bytes | None = None,
    max_sources: int = _PIXEL_PILOT_MAX_SOURCES,
) -> dict:
    """Run a minimal, dependency-light source detector on one ZTF DR24
    difference image and return candidate source positions.

    This is a proof-of-concept extractor for validating that the motion-
    product pivot is buildable, not the final motion linker: it thresholds
    a sigma-clipped background, groups surviving pixels into connected
    components (so one physical residual -- e.g. a bright-star subtraction
    artifact spanning several adjacent pixels -- becomes ONE candidate
    source, not several), and converts the brightest pixel of each
    component to RA/Dec via the image's own WCS. Pure numpy/scipy/astropy
    -- matches this project's existing preference for minimal new
    dependencies (see orbit.py's "no external orbit-determination
    dependency" note). A full calibrated PSF-fit photometric pipeline is
    still out of scope for this tiny validation pilot; `psf_fits_bytes`
    adds a lighter PSF-shape *consistency* score (correlation, not flux-
    calibrated photometry) to help distinguish real point-source-shaped
    detections from non-PSF-shaped artifacts.

    `mask_fits_bytes`, if provided, is the exposure's `science_mask`
    product: any pixel with a nonzero mask value is excluded from both the
    background statistics and candidate detection. This is a deliberately
    coarse simplification -- treating ANY nonzero flag as "exclude" rather
    than decoding ZTF's specific per-bit mask semantics -- disclosed here
    rather than overclaiming bit-level precision this tiny pilot does not
    implement.
    """
    # Lazy imports for heavy third-party libraries, matching this file's
    # existing convention (astropy.io.ascii, astropy.time.Time above).
    import numpy as np
    from astropy.io import fits
    from astropy.stats import sigma_clipped_stats
    from astropy.wcs import WCS
    from scipy.ndimage import label

    with fits.open(io.BytesIO(fits_bytes)) as hdul:
        # .fz (Rice-compressed) ZTF products decompress transparently via
        # astropy's CompImageHDU support; the Primary HDU is header-only, so
        # pick the first HDU that actually carries pixel data.
        hdu = next(h for h in hdul if h.data is not None)
        data = np.asarray(hdu.data, dtype=float)
        header = hdu.header

    finite = np.isfinite(data)
    mask_applied = mask_fits_bytes is not None
    n_masked_pixels = 0
    usable = finite
    if mask_applied:
        with fits.open(io.BytesIO(mask_fits_bytes)) as mask_hdul:
            mask_hdu = next(h for h in mask_hdul if h.data is not None)
            mask_data = np.asarray(mask_hdu.data)
        if mask_data.shape != data.shape:
            raise ValueError(
                f"science_mask shape {mask_data.shape} does not match difference image "
                f"shape {data.shape} -- refusing to apply a mismatched mask"
            )
        flagged = mask_data != 0
        n_masked_pixels = int(flagged.sum())
        usable = finite & ~flagged

    mean, median, std = sigma_clipped_stats(data[usable], sigma=3.0)
    # A conservative 5-sigma cut, matching this project's cautious-detection
    # posture elsewhere (e.g. detect.py's real/bogus threshold discipline).
    threshold = median + _PIXEL_PILOT_DETECTION_SIGMA * std

    above_threshold = usable & (data > threshold)
    n_pixels_above_threshold = int(above_threshold.sum())

    # Connected-component labeling merges adjacent above-threshold pixels
    # (default scipy 4-connectivity) into single sources -- this is what
    # fixes the earlier v1 finding where one bright residual produced
    # several separately-counted "sources" via plain local-maximum
    # suppression.
    labeled, n_components = label(above_threshold)

    psf_applied = psf_fits_bytes is not None
    psf_kernel = None
    psf_kernel_shape = None
    if psf_applied:
        with fits.open(io.BytesIO(psf_fits_bytes)) as psf_hdul:
            psf_hdu = next(h for h in psf_hdul if h.data is not None)
            psf_kernel = np.asarray(psf_hdu.data, dtype=float)
        psf_kernel_shape = list(psf_kernel.shape)

    wcs = WCS(header)
    components = []
    for component_id in range(1, n_components + 1):
        ys, xs = np.nonzero(labeled == component_id)
        values = data[ys, xs]
        peak_idx = int(np.argmax(values))
        y, x = int(ys[peak_idx]), int(xs[peak_idx])
        components.append((float(data[y, x]), x, y, int(len(ys))))

    # Rank by peak brightness and keep only the strongest max_sources so
    # output size stays bounded regardless of how noisy an exposure is.
    components.sort(key=lambda c: c[0], reverse=True)
    sources = []
    for peak_value, x, y, component_size_pixels in components[:max_sources]:
        ra, dec = wcs.all_pix2world(float(x), float(y), 0)
        source = {
            "x": x,
            "y": y,
            "ra_deg": float(ra),
            "dec_deg": float(dec),
            "peak_value": peak_value,
            "snr": float((peak_value - median) / std) if std > 0 else None,
            "component_size_pixels": component_size_pixels,
        }
        if psf_applied:
            source["psf_correlation"] = _psf_shape_correlation(data, x, y, psf_kernel)
        sources.append(source)

    return {
        "background_mean": float(mean),
        "background_median": float(median),
        "background_std": float(std),
        "detection_sigma": _PIXEL_PILOT_DETECTION_SIGMA,
        "detection_threshold": float(threshold),
        "n_pixels": int(data.size),
        "n_finite_pixels": int(finite.sum()),
        "mask_applied": mask_applied,
        "n_masked_pixels": n_masked_pixels,
        "n_pixels_above_threshold": n_pixels_above_threshold,
        "n_connected_components": n_components,
        "n_candidate_sources": len(sources),
        "n_candidate_sources_cap": max_sources,
        "n_candidate_sources_truncated": n_components > max_sources,
        "psf_applied": psf_applied,
        "psf_kernel_shape": psf_kernel_shape,
        "sources": sources,
    }


def _save_pixel_pilot_checkpoint(path: Path, payload: dict) -> None:
    """Persist the pixel-extraction pilot result once download+extraction
    complete, so a re-run resumes instead of re-downloading the product."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _run_pixel_extraction_pilot(manifest: dict, run_dir: Path) -> dict:
    """Download exactly one difference image and run the minimal source
    extractor on it -- the bounded "tiny pixel-extraction pilot" identified
    as the next safe engineering step after the motion-product HEAD
    preflight (see docs/evidence/live/2026-07-16-ztf-dr24-motion-product-
    preflight-first-live-run.md). Hard-capped to a single exposure: this
    validates that a source-native motion extractor is buildable against
    this product family before any wider batch is considered.
    """
    exposures = manifest.get("exposures", [])
    if len(exposures) != _MAX_PIXEL_PILOT_EXPOSURES:
        raise ValueError(
            f"pixel-extraction pilot requires exactly {_MAX_PIXEL_PILOT_EXPOSURES} "
            f"exposure in the bounded query window, got {len(exposures)}; narrow "
            "--size-deg/--start-jd/--end-jd to select a single exposure"
        )
    exposure = exposures[0]
    preflight_result = exposure.get("product_headers", {}).get("difference_image")
    if not preflight_result or not preflight_result.get("available"):
        raise RuntimeError(
            "pixel-extraction pilot requires a passed --preflight-motion-products run "
            "showing the difference image is available before downloading it"
        )

    checkpoint_path = run_dir / "pixel_extraction_pilot.json"
    fits_path = run_dir / "difference_image.fits.fz"
    mask_path = run_dir / "science_mask.fits"
    psf_path = run_dir / "difference_psf.fits"

    if checkpoint_path.exists() and fits_path.exists():
        print(
            "[pixel-pilot] checkpoint and downloaded product already present, skipping fetch",
            flush=True,
        )
        return json.loads(checkpoint_path.read_text())

    url = exposure["product_urls"]["difference_image"]
    print(
        f"[pixel-pilot] Downloading {url} "
        f"(~{preflight_result['content_length_bytes']} bytes)",
        flush=True,
    )
    t0 = time.monotonic()
    content = _fetch_binary_with_retry(url)
    fits_path.parent.mkdir(parents=True, exist_ok=True)
    fits_path.write_bytes(content)
    downloaded_sha256 = hashlib.sha256(content).hexdigest()
    print(
        f"[pixel-pilot] Downloaded {len(content)} bytes  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    # Apply the science mask when the same preflight already verified it
    # available -- soft requirement: an exposure without a verified mask
    # still runs (mask_applied=False is reported explicitly), it just isn't
    # blocked on a product that was never confirmed present.
    mask_bytes: bytes | None = None
    mask_preflight = exposure.get("product_headers", {}).get("science_mask")
    if mask_preflight and mask_preflight.get("available"):
        mask_url = exposure["product_urls"]["science_mask"]
        print(
            f"[pixel-pilot] Downloading science mask {mask_url} "
            f"(~{mask_preflight['content_length_bytes']} bytes)",
            flush=True,
        )
        mask_bytes = _fetch_binary_with_retry(mask_url)
        mask_path.write_bytes(mask_bytes)
        print(f"[pixel-pilot] Downloaded mask {len(mask_bytes)} bytes", flush=True)
    else:
        print(
            "[pixel-pilot] science_mask not verified available for this exposure -- "
            "proceeding without mask filtering",
            flush=True,
        )

    # Same soft-requirement pattern as the mask: apply the PSF-shape
    # correlation score only when the same preflight already verified
    # difference_psf available for this exposure.
    psf_bytes: bytes | None = None
    psf_preflight = exposure.get("product_headers", {}).get("difference_psf")
    if psf_preflight and psf_preflight.get("available"):
        psf_url = exposure["product_urls"]["difference_psf"]
        print(
            f"[pixel-pilot] Downloading difference PSF {psf_url} "
            f"(~{psf_preflight['content_length_bytes']} bytes)",
            flush=True,
        )
        psf_bytes = _fetch_binary_with_retry(psf_url)
        psf_path.write_bytes(psf_bytes)
        print(f"[pixel-pilot] Downloaded PSF {len(psf_bytes)} bytes", flush=True)
    else:
        print(
            "[pixel-pilot] difference_psf not verified available for this exposure -- "
            "proceeding without PSF-shape scoring",
            flush=True,
        )

    extraction = _detect_sources_in_difference_image(
        content, mask_fits_bytes=mask_bytes, psf_fits_bytes=psf_bytes
    )
    result = {
        "schema_version": "ztf-dr24-pixel-extraction-pilot-v3",
        "pid": exposure["pid"],
        "product_url": url,
        "downloaded_bytes": len(content),
        "downloaded_sha256": downloaded_sha256,
        "fits_path": str(fits_path),
        "mask_path": str(mask_path) if mask_bytes else None,
        "psf_path": str(psf_path) if psf_bytes else None,
        **extraction,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    _save_pixel_pilot_checkpoint(checkpoint_path, result)
    truncation_note = (
        f" (truncated from {result['n_connected_components']} connected components)"
        if result["n_candidate_sources_truncated"]
        else ""
    )
    print(
        f"[pixel-pilot] Extracted {result['n_candidate_sources']} candidate source(s) above "
        f"{result['detection_threshold']:.2f} threshold{truncation_note}  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    print(f"[pixel-pilot] Wrote {checkpoint_path}", flush=True)
    return result


def run_bounded_ingest(
    ra: float,
    dec: float,
    size_deg: float,
    start_jd: float,
    end_jd: float,
    out_dir: Path,
    emit_motion_product_manifest: bool = False,
    preflight_motion_products: bool = False,
    max_preflight_exposures: int = 10,
    preflight_workers: int = 4,
    pixel_extraction_pilot: bool = False,
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
    preflight_failed = False
    if emit_motion_product_manifest or preflight_motion_products:
        manifest = _build_motion_product_manifest(table, query, raw_hash)
        manifest_path = run_dir / "motion_product_manifest.json"
        if preflight_motion_products:
            manifest = _preflight_motion_products(
                manifest,
                run_dir / "motion_product_preflight.json",
                max_exposures=max_preflight_exposures,
                workers=preflight_workers,
            )
            preflight = manifest["preflight"]
            report["motion_product_preflight"] = preflight
            preflight_failed = not preflight["all_required_products_available"]
        manifest_path.write_text(json.dumps(manifest, indent=2))
        report["motion_product_manifest_path"] = str(manifest_path)
        report["motion_product_manifest_exposures"] = manifest["n_exposures"]
        availability_message = (
            "availability verified by HEAD preflight"
            if preflight_motion_products and not preflight_failed
            else (
                "availability preflight failed"
                if preflight_motion_products
                else "availability remains unverified"
            )
        )
        print(
            f"[ingest] Planned source-native products for {manifest['n_exposures']} exposure(s); "
            f"{availability_message} and no products were downloaded",
            flush=True,
        )
    if pixel_extraction_pilot:
        if not preflight_motion_products:
            raise ValueError(
                "--pixel-extraction-pilot requires --preflight-motion-products to verify "
                "product availability before any download is attempted"
            )
        if preflight_failed:
            raise RuntimeError(
                "pixel-extraction pilot skipped: motion-product preflight failed"
            )
        report["pixel_extraction_pilot"] = _run_pixel_extraction_pilot(manifest, run_dir)
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
    if preflight_failed:
        raise RuntimeError(
            "motion-product preflight failed: one or more required products are unavailable"
        )
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
    parser.add_argument(
        "--preflight-motion-products",
        action="store_true",
        help=(
            "HEAD-check a bounded product plan, checkpoint each result, and fail closed if "
            "any required product is unavailable; downloads no response bodies"
        ),
    )
    parser.add_argument(
        "--max-preflight-exposures",
        type=int,
        default=10,
        help=(
            "Maximum exposures allowed in a HEAD preflight (default: 10; hard cap: "
            f"{_MAX_PREFLIGHT_EXPOSURES})"
        ),
    )
    parser.add_argument(
        "--preflight-workers",
        type=int,
        default=4,
        help=f"Concurrent HEAD requests (default: 4; hard cap: {_MAX_PREFLIGHT_WORKERS})",
    )
    parser.add_argument(
        "--pixel-extraction-pilot",
        action="store_true",
        help=(
            "Download exactly one difference image (query window must resolve to a "
            "single exposure) and run a minimal source detector on it; requires "
            "--preflight-motion-products. Hard-capped to one exposure per invocation."
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
        preflight_motion_products=args.preflight_motion_products,
        max_preflight_exposures=args.max_preflight_exposures,
        preflight_workers=args.preflight_workers,
        pixel_extraction_pilot=args.pixel_extraction_pilot,
    )


if __name__ == "__main__":
    main()
