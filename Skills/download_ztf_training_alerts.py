#!/usr/bin/env python
"""Download labeled ZTF alert packets for Tier 1/2 ML training.

Downloads nightly ZTF alert tarballs from the ZTF public archive at UW
(https://ztf.uw.edu/alerts/public/). Each tarball contains thousands of
Avro alert packets, each with image cutouts and a real/bogus (rb) score.
Labels each alert real (rb >= 0.65) or bogus (rb < 0.35).

No ztfquery needed — uses only requests (already in pyproject.toml) and
fastavro. No IRSA credentials required for the public archive.

IMPORTANT: Run from your Mac, not from the coding agent server.

Usage (from repo root on your Mac, with venv active):
    pip install fastavro                          # one-time setup
    caffeinate -i python Skills/download_ztf_training_alerts.py
    caffeinate -i python Skills/download_ztf_training_alerts.py --nights 3 --limit 5000
    # dry-run is fast — no caffeinate needed:
    PYTHONPATH=src python Skills/download_ztf_training_alerts.py --dry-run

Output: data/ztf_labeled_alerts.json
    Feed directly into:
    caffeinate -i python Skills/build_cutout_dataset.py \
        --input data/ztf_labeled_alerts.json \
        --output-dir data/cutouts/ \
        --csv data/cutouts/index.csv
"""

from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
import sys
import tarfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import requests

# Ensure src/ is importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ZTF public alert archive — nightly tarballs of Avro alert packets.
# No authentication required. Updated each morning with prior night's alerts.
ZTF_ARCHIVE_BASE = "https://ztf.uw.edu/alerts/public"

# Real/bogus label thresholds matching the ZTF standard cuts.
# Alerts in the ambiguous zone (0.35 <= rb < 0.65) are excluded.
REAL_THRESHOLD = 0.65   # rb >= this → labeled real (label=0)
BOGUS_THRESHOLD = 0.35  # rb <  this → labeled bogus (label=3)

# Print progress every N scanned .avro members. Cutout-carrying records are
# heavier than the metadata-only ztf_alert_archive_ingest.py, so this fires
# more often than that script's 500.
_PROGRESS_EVERY = 200


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TiB"


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


class _CountingReader:
    """Wraps a streaming HTTP response body, counting bytes read as they
    pass through -- used to compute a real, measurable-quantity ETA (bytes
    consumed vs. Content-Length) while streaming through gzip/tar decode,
    since neither gzip nor tarfile expose a native byte-progress hook."""

    def __init__(self, raw):
        self._raw = raw
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = self._raw.read(size)
        self.bytes_read += len(chunk)
        return chunk


def night_tarball_url(date: datetime) -> str:
    """Return the ZTF public archive URL for a given UTC date."""
    # Filename pattern: ztf_public_YYYYMMDD.tar.gz
    date_str = date.strftime("%Y%m%d")
    return f"{ZTF_ARCHIVE_BASE}/ztf_public_{date_str}.tar.gz"


def _decompress_ztf_stamp(stamp_bytes: bytes) -> bytes | None:
    """Decompress a ZTF Avro stampData field to raw float32 bytes.

    ZTF cutout stamps are gzip-compressed FITS files containing a single
    63×63 float32 image. This function strips the gzip and FITS headers,
    returning the 63*63*4 = 15876 raw bytes that build_cutout_dataset.py
    expects to receive via np.frombuffer(..., dtype=np.float32).
    """
    if not stamp_bytes:
        return None
    try:
        # Decompress gzip wrapper to get FITS bytes
        fits_bytes = gzip.decompress(stamp_bytes)
        # Parse FITS in-memory — astropy reads the header and returns the data array
        from astropy.io import fits as astrofits  # type: ignore[import]
        with astrofits.open(io.BytesIO(fits_bytes)) as hdul:
            arr = hdul[0].data  # type: ignore[index]
            if arr is None or arr.shape != (63, 63):
                return None
            # Convert to float32 and return as raw bytes
            return arr.astype(np.float32).tobytes()
    except Exception:
        return None


def parse_avro_alert(avro_bytes: bytes, *, archive_night: str | None = None) -> dict | None:
    """Parse a single ZTF Avro alert and return a labeled dict or None.

    Returns None if the alert is ambiguous (rb between thresholds),
    missing cutouts, or cannot be parsed.

    ZTF Avro schema fields used (field names verified against a real
    downloaded packet — see
    docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md —
    not guessed):
        objectId              — ZTF broker's persistent per-sky-position object
                                 association; the leakage-relevant grouping key
                                 for A4 grouped splits (same object must not
                                 appear in both train and validation).
        candidate.candid       — unique per-detection alert ID
        candidate.jd            — observation Julian date
        candidate.ra, .dec      — J2000 sky position [deg]
        candidate.fid            — filter ID (1=g, 2=r, 3=i)
        candidate.field           — ZTF field ID
        candidate.rb    — real/bogus score [0, 1]
        candidate.drb   — deep-learning real/bogus score [0, 1]
        cutoutScience.stampData   — 63x63 float32 science image (gzip-compressed)
        cutoutTemplate.stampData  — 63x63 float32 reference image (gzip-compressed)
        cutoutDifference.stampData — 63x63 float32 difference image (gzip-compressed)
    """
    try:
        import fastavro  # type: ignore[import]
    except ImportError:
        raise RuntimeError("fastavro not installed. Run: pip install fastavro")

    try:
        reader = fastavro.reader(io.BytesIO(avro_bytes))
        for record in reader:
            candidate = record.get("candidate", {})
            rb = float(candidate.get("rb", -1.0))
            drb = float(candidate.get("drb", -1.0))

            # Skip ambiguous alerts — noisy labels hurt training more than smaller dataset
            if rb >= REAL_THRESHOLD:
                label = 0   # real detection
            elif rb < BOGUS_THRESHOLD:
                label = 3   # bogus / artifact
            else:
                return None  # ambiguous zone — exclude

            # Extract and decompress cutouts — ZTF stampData is gzip-compressed FITS.
            # We decompress to raw float32 bytes so build_cutout_dataset.py can decode
            # them directly with np.frombuffer(..., dtype=np.float32).reshape(63, 63).
            sci_raw = _decompress_ztf_stamp(
                (record.get("cutoutScience") or {}).get("stampData", b"")
            )
            ref_raw = _decompress_ztf_stamp(
                (record.get("cutoutTemplate") or {}).get("stampData", b"")
            )
            diff_raw = _decompress_ztf_stamp(
                (record.get("cutoutDifference") or {}).get("stampData", b"")
            )

            # Skip alerts with missing or malformed cutouts
            if sci_raw is None or ref_raw is None or diff_raw is None:
                return None

            # Base64-encode raw float32 bytes for JSON transport
            obs = {
                "cutout_science": base64.b64encode(sci_raw).decode("ascii"),
                "cutout_reference": base64.b64encode(ref_raw).decode("ascii"),
                "cutout_difference": base64.b64encode(diff_raw).decode("ascii"),
                "rb": rb,
                "drb": drb,
            }
            return {
                "label": label,
                "rb": rb,
                "drb": drb,
                # A4/A1 grouped-split provenance — real per-alert metadata,
                # not derivable after the fact once discarded (see
                # ztf_labeled_alerts_tier2_cnn_v1.json's known_caveats for
                # why the original 10,000-alert sample lacks these fields).
                "object_id": record.get("objectId"),
                "candid": candidate.get("candid") or record.get("candid"),
                "jd": candidate.get("jd"),
                "ra": candidate.get("ra"),
                "dec": candidate.get("dec"),
                "fid": candidate.get("fid"),
                "field": candidate.get("field"),
                "archive_night": archive_night,
                "observations": [obs],
            }

    except Exception:
        return None  # malformed Avro — skip silently

    return None


def download_night(url: str, limit: int, results: list[dict], *, archive_night: str) -> int:
    """Stream-download one nightly tarball, parse alerts, append to results.

    Returns number of alerts added from this night.
    Skips gracefully if the tarball is not yet available (future date)
    or the server returns an error.

    `archive_night` (the tarball's real YYYYMMDD date) is stamped onto every
    alert as a robust, independently-verifiable grouping key alongside the
    per-alert `jd` — this avoids the JD-to-calendar-date off-by-one pitfall
    already found and fixed once in this project (noon-UTC JD increment,
    see docs/evidence/live/2026-07-02-gate-z1-night-date-offbyone-fix.md).

    Streams through the gzip/tar decode instead of buffering the whole
    tarball via `resp.content` first, and prints byte-level progress with a
    measurable-quantity ETA every `_PROGRESS_EVERY` scanned members --
    without this, a single multi-hundred-MB tarball produced total console
    silence for the entire download+decode, which is indistinguishable from
    a hung/broken process. Matches the same proven pattern already used in
    Skills/ztf_alert_archive_ingest.py.
    """
    try:
        head_resp = requests.head(url, timeout=30, allow_redirects=True)
        if head_resp.status_code == 404:
            print(f"  Not available (404): {url}", flush=True)
            return 0
        head_resp.raise_for_status()
        total_bytes = int(head_resp.headers.get("Content-Length", 0))
        print(f"  Remote size: {_fmt_bytes(total_bytes)}", flush=True)
    except Exception as e:
        print(f"  Failed to HEAD {url}: {e}", flush=True)
        return 0

    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Failed to download {url}: {e}", flush=True)
        return 0

    n_added = 0
    scanned = 0
    t0 = time.monotonic()
    try:
        counting_reader = _CountingReader(resp.raw)
        with tarfile.open(fileobj=counting_reader, mode="r|gz") as tar:
            for member in tar:
                if not member.name.endswith(".avro"):
                    continue
                if len(results) >= limit:
                    break
                fobj = tar.extractfile(member)
                if fobj is None:
                    continue

                scanned += 1
                # Progress must fire on every scanned member, BEFORE the
                # ambiguous-rb/missing-cutout filtering inside
                # parse_avro_alert() -- a run that keeps few or no alerts
                # from this specific night must not go silent for the whole
                # file (up to several GB).
                if scanned % _PROGRESS_EVERY == 0:
                    elapsed = time.monotonic() - t0
                    frac = counting_reader.bytes_read / total_bytes if total_bytes else 0
                    eta = (elapsed / frac - elapsed) if frac > 0 else 0
                    print(
                        f"  scanned={scanned} kept={n_added}  "
                        f"{_fmt_bytes(counting_reader.bytes_read)}/{_fmt_bytes(total_bytes)} "
                        f"({100 * frac:.1f}%)  elapsed {_fmt_duration(elapsed)}  "
                        f"ETA {_fmt_duration(eta)}",
                        flush=True,
                    )

                alert = parse_avro_alert(fobj.read(), archive_night=archive_night)
                if alert is not None:
                    results.append(alert)
                    n_added += 1
    except Exception as e:
        print(f"  Error reading tarball {url}: {e}", flush=True)
    finally:
        resp.close()

    elapsed = time.monotonic() - t0
    print(
        f"  Done: scanned={scanned} kept={n_added}  elapsed {_fmt_duration(elapsed)}",
        flush=True,
    )
    return n_added


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download labeled ZTF Avro alerts for ML training (run from Mac)"
    )
    parser.add_argument(
        "--nights", type=int, default=3,
        help="Number of past nights to download (default: 3; each night ~5000-20000 alerts)"
    )
    parser.add_argument(
        "--limit", type=int, default=10000,
        help="Max total alerts to collect across all nights (default: 10000)"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/ztf_labeled_alerts.json"),
        help="Output JSON file for build_cutout_dataset.py"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print URLs that would be downloaded without fetching"
    )
    args = parser.parse_args()

    # Build list of dates to download, working backwards from yesterday
    # (today's night may not be packaged yet)
    today = datetime.now(tz=UTC)
    dates = [today - timedelta(days=i + 1) for i in range(args.nights)]

    print(f"ZTF public alert archive: {ZTF_ARCHIVE_BASE}", flush=True)
    print(f"Nights to download: {args.nights}  |  Alert limit: {args.limit}", flush=True)
    print(flush=True)

    if args.dry_run:
        # HEAD-check each URL to confirm reachability before committing to a download
        print("Dry run — checking URLs:", flush=True)
        all_ok = True
        for d in dates:
            url = night_tarball_url(d)
            try:
                r = requests.head(url, timeout=15)
                size = r.headers.get("Content-Length", "?")
                status = f"HTTP {r.status_code}"
                ok = r.status_code == 200
                symbol = "OK" if ok else "FAIL"
                print(f"  [{symbol}] {url}  ({status}, size={size} bytes)", flush=True)
                if not ok:
                    all_ok = False
            except Exception as e:
                print(f"  [FAIL] {url}  (error: {e})", flush=True)
                all_ok = False
        if all_ok:
            print("\nAll URLs reachable. Drop --dry-run to begin downloading.", flush=True)
        else:
            print(
                "\nSome URLs failed. Check network access or try different --nights value.",
                flush=True,
            )
        return

    results: list[dict] = []

    for d in dates:
        if len(results) >= args.limit:
            break
        url = night_tarball_url(d)
        print(f"Downloading {d.strftime('%Y-%m-%d')}: {url}", flush=True)
        n = download_night(url, args.limit, results, archive_night=d.strftime("%Y%m%d"))
        n_real = sum(1 for a in results if a["label"] == 0)
        n_bogus = sum(1 for a in results if a["label"] == 3)
        print(
            f"  +{n} alerts  (total: {len(results)} | real: {n_real} bogus: {n_bogus})",
            flush=True,
        )

    if not results:
        print(
            "\nNo alerts collected. Check network access and try --dry-run to verify URLs.",
            flush=True,
        )
        return

    print(f"\nWriting {len(results)} alerts to {args.output} ...", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(results, f)
    size_mb = args.output.stat().st_size / 1e6
    print(f"Done: {args.output} ({size_mb:.1f} MB)", flush=True)
    print(flush=True)
    print("Next step:", flush=True)
    print("  PYTHONPATH=src python Skills/build_cutout_dataset.py \\", flush=True)
    print(f"      --input {args.output} \\", flush=True)
    print("      --output-dir data/cutouts/ \\", flush=True)
    print("      --csv data/cutouts/index.csv", flush=True)


if __name__ == "__main__":
    main()
