#!/usr/bin/env python
"""Gate Z3 candidate source -- bounded single-file verification probe for the
University of Washington public ZTF alert archive.

Per docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md:
the operator's browser-captured directory listing at
https://ztf.uw.edu/alerts/public/ (docs/Alert Archive.pdf) confirms the real
per-night file naming convention (ztf_public_YYYYMMDD.tar.gz) and that the
listing is reachable without authentication. This script downloads exactly
ONE named file -- never a loop over multiple nights -- and verifies it is a
real gzip/tar archive of AVRO alert packets. By default it does not extract
or parse member content; pass --inspect-first-packet to additionally parse
one real .avro member with fastavro and print its candidate record's field
names/values, confirming the schema matches research (ra/dec/jd/magpsf/
sigmapsf) rather than guessing. This is a Phase 0/1 verification step only,
not the Gate Z3 ingest tool itself.

Bounded by design: exactly one file, no default "download everything" mode.
The default target (ztf_public_20180809.tar.gz, 31M) was chosen because it
is one of the smallest genuinely-sized files visible in the operator's
captured listing -- not a `44`/`74`-byte placeholder entry, and not one of
the very large (multi-GB, up to 73G) real nights.

Checkpoint/resume: if the target file already exists locally with a size
matching the server's Content-Length, the download is skipped and a
[resume] line is printed -- re-running the identical command is always safe.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/probe_ztf_alert_archive_file.py
    caffeinate -i uv run --python 3.14 python Skills/probe_ztf_alert_archive_file.py \\
        --filename ztf_public_20200619.tar.gz
"""

from __future__ import annotations

import argparse
import sys
import tarfile
import time
from pathlib import Path

import requests

_ARCHIVE_BASE_URL = "https://ztf.uw.edu/alerts/public/"
_DEFAULT_FILENAME = "ztf_public_20180809.tar.gz"
_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = (2, 4, 8, 16, 32)
_CHUNK_BYTES = 1 << 20  # 1 MiB
_DOWNLOAD_DIR = Path("Logs/pipeline_runs/ztf_alert_archive_probe")
_MAX_MEMBERS_LISTED = 10


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TiB"


def _head_with_retry(url: str) -> requests.Response:
    """HEAD with exponential-backoff retry, per the standing network-retry rule."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.head(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except (ConnectionError, TimeoutError, OSError, requests.HTTPError) as exc:
            last_exc = exc
            print(
                f"[probe] HEAD attempt {attempt}/{_MAX_ATTEMPTS} failed "
                f"({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(f"HEAD {url} failed after {_MAX_ATTEMPTS} attempts") from last_exc


def _download_with_retry(url: str, dest: Path) -> None:
    """GET with exponential-backoff retry and per-chunk progress, writing
    directly to `dest`. Retries restart the download from scratch on this
    single small (~tens of MB) target file -- true byte-range resume is not
    needed at this size and would add complexity without benefit here."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            t0 = time.monotonic()
            with requests.get(url, timeout=60, stream=True) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=_CHUNK_BYTES):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        downloaded += len(chunk)
                        elapsed = time.monotonic() - t0
                        rate = downloaded / elapsed if elapsed > 0 else 0
                        eta = (total - downloaded) / rate if rate > 0 and total else 0
                        pct = f"{100 * downloaded / total:.1f}%" if total else "?%"
                        print(
                            f"[probe] downloading {dest.name}: "
                            f"{_fmt_bytes(downloaded)}/{_fmt_bytes(total)} ({pct})  "
                            f"elapsed {_fmt_duration(elapsed)}  ETA {_fmt_duration(eta)}",
                            flush=True,
                        )
            return
        except (ConnectionError, TimeoutError, OSError, requests.HTTPError) as exc:
            last_exc = exc
            print(
                f"[probe] download attempt {attempt}/{_MAX_ATTEMPTS} failed "
                f"({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            dest.unlink(missing_ok=True)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(f"GET {url} failed after {_MAX_ATTEMPTS} attempts") from last_exc


def _inspect_first_packet(
    dest: Path, member_name: str, dump_all_fields: bool = False
) -> dict:
    """Extract exactly one named .avro member from the tar archive and parse
    its `candidate` record with fastavro, printing the field names/values so
    the real schema can be compared against the WebSearch-sourced research
    (ra, dec, jd, magpsf, sigmapsf) without guessing. Reads into memory --
    a single alert packet is a few KB, not a bulk-extraction operation.

    With dump_all_fields=True, also prints every candidate field name/value
    (not just the six already researched) -- needed to find the real field
    name for real-bogus scores (e.g. rb/drb) before using it in any ingest
    tool, per the standing rule against guessing field names."""
    import fastavro

    print(f"[probe] parsing AVRO packet {member_name}...", flush=True)
    with tarfile.open(dest, mode="r:gz") as tf:
        member = tf.getmember(member_name)
        fh = tf.extractfile(member)
        if fh is None:
            raise RuntimeError(f"could not extract {member_name} from {dest}")
        records = list(fastavro.reader(fh))

    if not records:
        raise RuntimeError(f"{member_name} contained zero AVRO records")

    record = records[0]
    candidate = record.get("candidate", {})
    print(f"[probe] top-level record keys: {sorted(record.keys())}", flush=True)
    print(f"[probe] candidate record has {len(candidate)} field(s)", flush=True)

    expected_fields = ["ra", "dec", "jd", "magpsf", "sigmapsf", "fid"]
    print("[probe] expected schema fields (from research) -- observed values:", flush=True)
    for field in expected_fields:
        present = field in candidate
        value = candidate.get(field)
        mark = "✓" if present else "✗ MISSING"
        print(f"  {field}: {value!r}  [{mark}]", flush=True)

    if dump_all_fields:
        print(f"[probe] ALL {len(candidate)} candidate field(s):", flush=True)
        for name in sorted(candidate.keys()):
            print(f"  {name}: {candidate[name]!r}", flush=True)

    return {
        "member_name": member_name,
        "top_level_keys": sorted(record.keys()),
        "candidate_field_count": len(candidate),
        "expected_fields_present": {f: f in candidate for f in expected_fields},
        "all_candidate_fields": dict(candidate) if dump_all_fields else None,
    }


def run_probe(
    filename: str,
    out_dir: Path,
    inspect_first_packet: bool = False,
    dump_all_fields: bool = False,
) -> dict:
    """Download exactly one named file from the UW ZTF alert archive and
    verify it is a real gzip/tar archive of AVRO alert packets. Returns a
    summary dict. With inspect_first_packet=True, also parses the first
    .avro member's real AVRO content -- otherwise member content is never
    extracted or parsed. dump_all_fields additionally prints every real
    candidate field name/value, not just the six already researched."""
    url = f"{_ARCHIVE_BASE_URL}{filename}"
    dest = out_dir / filename

    print(f"[probe] HEAD {url}", flush=True)
    head = _head_with_retry(url)
    remote_size = int(head.headers.get("Content-Length", 0))
    print(f"[probe] remote size: {_fmt_bytes(remote_size)}", flush=True)

    if dest.exists() and remote_size and dest.stat().st_size == remote_size:
        print(
            f"[resume] {dest} already downloaded and matches remote size "
            f"({_fmt_bytes(remote_size)}), skipping fetch",
            flush=True,
        )
    else:
        _download_with_retry(url, dest)

    print(f"[probe] verifying {dest} is a valid gzip/tar archive...", flush=True)
    members: list[str] = []
    avro_count = 0
    first_avro_member: str | None = None
    with tarfile.open(dest, mode="r:gz") as tf:
        for member in tf:
            if member.name.endswith(".avro"):
                avro_count += 1
                if first_avro_member is None:
                    first_avro_member = member.name
            if len(members) < _MAX_MEMBERS_LISTED:
                members.append(member.name)

    print(
        f"[probe] Complete: {dest.name} is a valid tar archive with "
        f"{avro_count} .avro member(s)",
        flush=True,
    )
    print(f"[probe] first {len(members)} member name(s):", flush=True)
    for name in members:
        print(f"  {name}", flush=True)

    result = {
        "filename": filename,
        "url": url,
        "local_path": str(dest),
        "remote_size_bytes": remote_size,
        "local_size_bytes": dest.stat().st_size,
        "avro_member_count": avro_count,
        "sample_member_names": members,
    }

    if inspect_first_packet:
        if first_avro_member is None:
            raise RuntimeError(f"{dest} contained no .avro members to inspect")
        result["packet_inspection"] = _inspect_first_packet(
            dest, first_avro_member, dump_all_fields=dump_all_fields
        )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Bounded single-file download-and-verify probe for the UW public "
            "ZTF alert archive (Gate Z3 candidate source)."
        )
    )
    parser.add_argument(
        "--filename",
        default=_DEFAULT_FILENAME,
        help=f"Exact archive filename to fetch (default: {_DEFAULT_FILENAME}).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_DOWNLOAD_DIR,
        help=f"Local download directory (default: {_DOWNLOAD_DIR}).",
    )
    parser.add_argument(
        "--inspect-first-packet",
        action="store_true",
        help=(
            "Also parse the first .avro member's real content with fastavro "
            "and print its candidate record fields, to confirm the schema "
            "matches research (ra/dec/jd/magpsf/sigmapsf) without guessing."
        ),
    )
    parser.add_argument(
        "--dump-all-fields",
        action="store_true",
        help=(
            "With --inspect-first-packet, also print every real candidate "
            "field name/value (not just the six already researched) -- "
            "needed to find the real field name for real-bogus scores "
            "(e.g. rb/drb) before using it in any ingest tool."
        ),
    )
    args = parser.parse_args()

    result = run_probe(
        args.filename, args.out_dir, args.inspect_first_packet, args.dump_all_fields
    )
    print()
    print(f"avro_member_count: {result['avro_member_count']}")
    print(f"local_path: {result['local_path']}")


if __name__ == "__main__":
    main()
