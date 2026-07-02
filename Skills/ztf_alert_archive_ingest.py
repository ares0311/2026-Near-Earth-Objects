#!/usr/bin/env python
"""Gate Z3 -- bounded, checkpointed, multi-night real-detection ingest from
the University of Washington public ZTF alert archive.

Per docs/ZTF_DR24_PRODUCTION_GATES.md's Gate Z3 "Next Coding Step": builds
real src/schemas.py Observation objects from real per-source ZTF alert
detections, using ONLY field names confirmed live via
Skills/probe_ztf_alert_archive_file.py --dump-all-fields (see
docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md):

    ra_deg      <- candidate.ra
    dec_deg     <- candidate.dec
    jd          <- candidate.jd
    mag         <- candidate.magpsf
    mag_err     <- candidate.sigmapsf
    filter_band <- candidate.fid (1=g, 2=R, 3=i -- documented ZTF filter ID
                   mapping, confirmed via official docs during Phase 0
                   research, not guessed)
    real_bogus  <- candidate.rb (confirmed present; deep_real_bogus/drb is
                   NOT assumed present -- left None unless the packet's
                   schemavsn indicates a version known to include it)
    field_id    <- str(candidate.field)
    limiting_mag <- candidate.diffmaglim

Image cutouts (cutoutScience/cutoutTemplate/cutoutDifference) are NOT
mapped yet -- their internal AVRO structure has not been verified live, so
cutout_science/cutout_reference/cutout_difference are left None rather than
guessed. This is a documented limitation, not an oversight.

Bounded by design: an explicit, small (<= _MAX_NIGHTS) list of nights must
be passed -- there is no "ingest everything" mode. Each night's archive
file is NEVER downloaded to disk or buffered fully in memory: the response
is streamed directly through gzip decompression into tarfile's streaming
mode (mode="r|gz"), and each .avro member is parsed and immediately
filtered (real-bogus threshold, optional sky-box) before being kept or
discarded, since nightly files can be up to 73G.

Checkpoint/resume: after each night completes, its kept Observations are
written to <out-dir>/<night>.json. Re-running the identical command skips
any night whose checkpoint file already exists.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \\
        --nights 20180809 20180810 \\
        --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tarfile
import time
from pathlib import Path

import requests

_ARCHIVE_BASE_URL = "https://ztf.uw.edu/alerts/public/"
_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = (2, 4, 8, 16, 32)
_OUT_DIR = Path("Logs/pipeline_runs/ztf_alert_archive_ingest")
_MAX_NIGHTS = 10
_PROGRESS_EVERY = 500

# ZTF filter ID -> band letter. Documented in the official ZTF alert schema
# (confirmed via WebSearch during Phase 0 research, not guessed):
# 1=g, 2=R, 3=i.
_FID_TO_BAND = {1: "g", 2: "R", 3: "i"}


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TiB"


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


def _angular_separation_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle separation in degrees (haversine formula)."""
    ra1_r, dec1_r, ra2_r, dec2_r = map(math.radians, (ra1, dec1, ra2, dec2))
    d_ra = ra2_r - ra1_r
    d_dec = dec2_r - dec1_r
    a = (
        math.sin(d_dec / 2) ** 2
        + math.cos(dec1_r) * math.cos(dec2_r) * math.sin(d_ra / 2) ** 2
    )
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(a))))


def _open_stream_with_retry(url: str):
    """GET with exponential-backoff retry, returning an open streaming
    response. Caller is responsible for closing it."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(url, timeout=60, stream=True)
            resp.raise_for_status()
            return resp
        except (ConnectionError, TimeoutError, OSError, requests.HTTPError) as exc:
            last_exc = exc
            print(
                f"[ingest] attempt {attempt}/{_MAX_ATTEMPTS} failed "
                f"({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(f"GET {url} failed after {_MAX_ATTEMPTS} attempts") from last_exc


def _packet_to_observation_dict(
    candidate: dict, top_level: dict
) -> dict | None:
    """Map ONLY confirmed real AVRO candidate fields to the Observation
    schema's constructor kwargs (as a plain dict, for JSON checkpointing).
    Returns None if a required field is missing (fails closed rather than
    guessing a default)."""
    required = ("ra", "dec", "jd", "magpsf", "sigmapsf", "fid")
    if any(candidate.get(f) is None for f in required):
        return None

    fid = candidate["fid"]
    band = _FID_TO_BAND.get(fid)
    if band is None:
        return None  # unknown filter ID -- fail closed, do not guess a band

    candid = top_level.get("candid")
    return {
        "obs_id": str(candid) if candid is not None else f"ztf_{candidate['jd']}",
        "ra_deg": float(candidate["ra"]),
        "dec_deg": float(candidate["dec"]),
        "jd": float(candidate["jd"]),
        "mag": float(candidate["magpsf"]),
        "mag_err": float(candidate["sigmapsf"]),
        "filter_band": band,
        "mission": "ZTF",
        "real_bogus": float(candidate["rb"]) if candidate.get("rb") is not None else None,
        "deep_real_bogus": None,  # not assumed present -- see module docstring
        "field_id": str(candidate["field"]) if candidate.get("field") is not None else None,
        "limiting_mag": (
            float(candidate["diffmaglim"]) if candidate.get("diffmaglim") is not None else None
        ),
    }


def ingest_one_night(
    night: str,
    out_dir: Path,
    min_rb: float,
    ra: float | None,
    dec: float | None,
    radius_deg: float | None,
    max_per_night: int,
) -> dict:
    """Stream-download and stream-parse one night's archive file, keeping
    only Observations passing the real-bogus threshold and (if given) the
    sky-box filter, up to max_per_night. Never buffers the full file."""
    checkpoint_path = out_dir / f"{night}.json"
    if checkpoint_path.exists():
        state = json.loads(checkpoint_path.read_text())
        print(
            f"[resume] {night}: checkpoint exists with "
            f"{state['kept_count']} kept observation(s), skipping",
            flush=True,
        )
        return state

    filename = f"ztf_public_{night}.tar.gz"
    url = f"{_ARCHIVE_BASE_URL}{filename}"

    print(f"[ingest] {night}: HEAD {url}", flush=True)
    head_resp = requests.head(url, timeout=30, allow_redirects=True)
    head_resp.raise_for_status()
    total_bytes = int(head_resp.headers.get("Content-Length", 0))
    print(f"[ingest] {night}: remote size {_fmt_bytes(total_bytes)}", flush=True)

    import fastavro

    kept: list[dict] = []
    scanned = 0
    t0 = time.monotonic()

    resp = _open_stream_with_retry(url)
    try:
        counting_reader = _CountingReader(resp.raw)
        with tarfile.open(fileobj=counting_reader, mode="r|gz") as tf:
            for member in tf:
                if not member.name.endswith(".avro"):
                    continue
                if len(kept) >= max_per_night:
                    break
                fh = tf.extractfile(member)
                if fh is None:
                    continue
                for record in fastavro.reader(fh):
                    scanned += 1

                    # Progress must fire on every scanned record, BEFORE any
                    # filter `continue` below -- a narrow sky box or a strict
                    # rb threshold can reject the overwhelming majority of
                    # records, and a print placed after those `continue`
                    # statements would silently never fire for the length of
                    # a night's file (up to 73G) when few or no records pass.
                    if scanned % _PROGRESS_EVERY == 0:
                        elapsed = time.monotonic() - t0
                        frac = counting_reader.bytes_read / total_bytes if total_bytes else 0
                        eta = (elapsed / frac - elapsed) if frac > 0 else 0
                        print(
                            f"[ingest] {night}: scanned={scanned} kept={len(kept)}  "
                            f"{_fmt_bytes(counting_reader.bytes_read)}/{_fmt_bytes(total_bytes)} "
                            f"({100 * frac:.1f}%)  elapsed {_fmt_duration(elapsed)}  "
                            f"ETA {_fmt_duration(eta)}",
                            flush=True,
                        )

                    candidate = record.get("candidate", {})
                    rb = candidate.get("rb")
                    if rb is None or rb < min_rb:
                        continue
                    if ra is not None and dec is not None and radius_deg is not None:
                        sep = _angular_separation_deg(
                            ra, dec, candidate.get("ra", 0.0), candidate.get("dec", 0.0)
                        )
                        if sep > radius_deg:
                            continue
                    obs = _packet_to_observation_dict(candidate, record)
                    if obs is not None:
                        kept.append(obs)
                if len(kept) >= max_per_night:
                    break
    finally:
        resp.close()

    elapsed = time.monotonic() - t0
    print(
        f"[ingest] {night}: complete -- scanned={scanned} kept={len(kept)} "
        f"elapsed {_fmt_duration(elapsed)}",
        flush=True,
    )

    state = {
        "night": night,
        "filename": filename,
        "scanned_count": scanned,
        "kept_count": len(kept),
        "observations": kept,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = checkpoint_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(checkpoint_path)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Bounded, checkpointed, multi-night real-detection ingest from "
            "the UW public ZTF alert archive (Gate Z3)."
        )
    )
    parser.add_argument(
        "--nights",
        nargs="+",
        required=True,
        help=f"Explicit list of UTC nights to ingest, YYYYMMDD (max {_MAX_NIGHTS}).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_OUT_DIR,
        help=f"Checkpoint directory (default: {_OUT_DIR}).",
    )
    parser.add_argument(
        "--min-rb", type=float, default=0.5, help="Minimum real-bogus score to keep (default: 0.5)."
    )
    parser.add_argument("--ra", type=float, default=None, help="Sky-box center RA, degrees.")
    parser.add_argument("--dec", type=float, default=None, help="Sky-box center Dec, degrees.")
    parser.add_argument(
        "--radius-deg", type=float, default=None, help="Sky-box radius, degrees."
    )
    parser.add_argument(
        "--max-per-night",
        type=int,
        default=5000,
        help="Safety cap on kept observations per night (default: 5000).",
    )
    args = parser.parse_args()

    if len(args.nights) > _MAX_NIGHTS:
        raise SystemExit(f"--nights accepts at most {_MAX_NIGHTS} nights, got {len(args.nights)}")

    total_kept = 0
    for night in args.nights:
        state = ingest_one_night(
            night,
            args.out_dir,
            args.min_rb,
            args.ra,
            args.dec,
            args.radius_deg,
            args.max_per_night,
        )
        total_kept += state["kept_count"]

    print()
    print(f"nights_ingested: {len(args.nights)}")
    print(f"total_kept_observations: {total_kept}")
    print(f"out_dir: {args.out_dir}")


if __name__ == "__main__":
    main()
