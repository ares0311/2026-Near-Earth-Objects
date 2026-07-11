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
any night whose checkpoint file already exists. The checkpoint filename is
keyed by night only, not by (night, ra, dec, radius_deg, min_rb) -- so a
resume additionally validates that the new call's query parameters match
what the checkpoint was actually built with, and fails closed (raises
SystemExit, does not ingest, does not return data) on any mismatch, rather
than silently handing back a different query's cached results under the
new request's label. This was a real bug (found 2026-07-11, not
hypothetical): re-running this script against an already-ingested night
with a *different* --ra/--dec silently returned the original field's
observations with no warning. Checkpoints written before this validation
existed have no recorded query parameters at all; those resume with a
printed warning instead of a hard failure, since there is nothing to
compare against. If you need a second field on an already-ingested night,
either use a different --out-dir or remove the stale checkpoint file.

Cross-machine visibility (fully automatic, no operator git commands and no
pasting required): every completed night appends a compact (no per-
observation data) summary line to
Logs/reports/ztf_alert_archive_ingest_manifest.jsonl -- a path this
project's .gitignore explicitly does NOT exclude (see the `!Logs/reports/`
allowlist entry), unlike the rest of Logs/**. At the end of every
invocation, the script itself commits and pushes just that one manifest
file (git add/commit/push, with pull-rebase-retry if another concurrent
tab pushed first) -- the operator does not need to run any git commands.
Results become readable via a plain `git pull` on the agent side within
moments of a run finishing. Re-running the same night updates its
manifest entry (keyed by night) rather than duplicating it. Use --status
to print recorded nights, or --sync to backfill manifest entries (and
push them) from checkpoint files already on disk from an earlier run --
e.g. one started before this auto-push behavior existed.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \\
        --nights 20180809 20180810 \\
        --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
"""

from __future__ import annotations

import argparse
import fcntl
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
# Committed (NOT gitignored) manifest path -- see the module docstring's
# "Cross-machine visibility" section. Deliberately outside _OUT_DIR, which
# stays under the gitignored Logs/pipeline_runs/ tree for the (potentially
# large) full per-observation checkpoint data.
_MANIFEST_PATH = Path("Logs/reports/ztf_alert_archive_ingest_manifest.jsonl")

# ZTF filter ID -> band letter. Documented in the official ZTF alert schema
# (confirmed via WebSearch during Phase 0 research, not guessed):
# 1=g, 2=R, 3=i.
_FID_TO_BAND = {1: "g", 2: "R", 3: "i"}


def _append_to_manifest(entry: dict) -> None:
    """Append one night's compact completion summary (no per-observation
    data -- that stays local in the gitignored checkpoint) to the shared,
    committed manifest, file-locked so concurrent tabs finishing near-
    simultaneously never corrupt or interleave each other's lines. This is
    the git-relay channel described in the module docstring -- the
    operator commits and pushes this one file instead of pasting console
    output from every tab."""
    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry) + "\n"
    with open(_MANIFEST_PATH, "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_manifest() -> dict[str, dict]:
    """Read the committed manifest and return the latest entry per night
    (deduplicated -- re-running a night updates, not duplicates, its
    entry). Returns {} if the manifest does not exist yet."""
    if not _MANIFEST_PATH.exists():
        return {}
    by_night: dict[str, dict] = {}
    for line in _MANIFEST_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        by_night[entry["night"]] = entry
    return by_night


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _run_git(args: list[str]) -> tuple[int, str, str]:
    """Run a git command in the current working directory (the project
    root, per how this script is documented to be invoked) and return
    (returncode, stdout, stderr) without raising on a non-zero exit --
    callers decide what a given exit code means."""
    import subprocess

    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def commit_and_push_manifest() -> bool:
    """Automatically commit and push ONLY the manifest file -- never any
    other file -- so results are visible via a plain `git pull` moments
    after a run finishes, with no operator git commands and no console
    output to paste. Scoped narrowly: this touches one inert data file,
    never source code. Retries push with a pull --rebase if another
    concurrent tab (running the same command in a different terminal tab)
    already pushed first. Never raises -- a relay failure must not lose or
    crash real ingest results that are already safely on local disk;
    instead it prints a clear fallback command for the operator."""
    if not _MANIFEST_PATH.exists():
        return False

    rc, _out, err = _run_git(["add", str(_MANIFEST_PATH)])
    if rc != 0:
        print(f"[git] add failed: {err.strip()}", flush=True)
        return False

    rc, _out, _err = _run_git(["diff", "--cached", "--quiet"])
    if rc == 0:
        print("[git] manifest unchanged, nothing to commit", flush=True)
        return True  # already up to date -- not a failure

    rc, _out, err = _run_git(
        ["commit", "-m", f"Record {_MANIFEST_PATH.name} results (automated)"]
    )
    if rc != 0:
        print(f"[git] commit failed: {err.strip()}", flush=True)
        return False

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        rc, _out, err = _run_git(["push"])
        if rc == 0:
            print(f"[git] pushed {_MANIFEST_PATH} (attempt {attempt}/{_MAX_ATTEMPTS})", flush=True)
            return True
        print(
            f"[git] push attempt {attempt}/{_MAX_ATTEMPTS} failed "
            f"(likely a concurrent tab pushed first): {err.strip()}",
            flush=True,
        )
        if attempt < _MAX_ATTEMPTS:
            rc_pull, _out, err_pull = _run_git(["pull", "--rebase"])
            if rc_pull != 0:
                print(f"[git] pull --rebase failed: {err_pull.strip()}", flush=True)
            time.sleep(_BACKOFF_SECONDS[attempt - 1])

    print(
        f"[git] Could not push {_MANIFEST_PATH} after {_MAX_ATTEMPTS} attempts. "
        f"The commit is safe locally -- run `git push` manually when convenient.",
        flush=True,
    )
    return False


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


def _query_params_match(
    recorded: tuple[float | None, float | None, float | None, float | None],
    requested: tuple[float | None, float | None, float | None, float | None],
) -> bool:
    """True if a checkpoint's recorded (ra, dec, radius_deg, min_rb) matches
    a new request's, tolerant of float round-tripping through JSON. None is
    only equal to None (e.g. "no sky-box filter" is itself a distinct query
    from any specific box)."""
    for recorded_value, requested_value in zip(recorded, requested):
        if recorded_value is None or requested_value is None:
            if recorded_value is not requested_value:
                return False
            continue
        if not math.isclose(recorded_value, requested_value, rel_tol=1e-9, abs_tol=1e-9):
            return False
    return True


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
        requested = (ra, dec, radius_deg, min_rb)
        if "ra" in state:
            # Checkpoint recorded its own query params (this validation's
            # normal case going forward) -- refuse to resume with a
            # different query's cached data.
            recorded = (
                state.get("ra"),
                state.get("dec"),
                state.get("radius_deg"),
                state.get("min_rb"),
            )
            if not _query_params_match(recorded, requested):
                raise SystemExit(
                    f"[FAIL-CLOSED] {night}: existing checkpoint {checkpoint_path} was built "
                    f"for ra={recorded[0]} dec={recorded[1]} radius_deg={recorded[2]} "
                    f"min_rb={recorded[3]}, but this run requested ra={requested[0]} "
                    f"dec={requested[1]} radius_deg={requested[2]} min_rb={requested[3]}. "
                    "Refusing to silently return a different query's cached results as if "
                    "they were this one -- use a different --out-dir for this field, or "
                    "remove the stale checkpoint if you intend to replace it."
                )
        else:
            # Legacy checkpoint predates query-parameter recording entirely
            # -- nothing to validate against, so warn rather than guess.
            print(
                f"[resume] {night}: legacy checkpoint has no recorded query parameters "
                "(predates this validation) -- cannot verify it matches this request. "
                "If it was originally ingested for a different field, its cached data "
                "will be wrong for the current one.",
                flush=True,
            )
        print(
            f"[resume] {night}: checkpoint exists with "
            f"{state['kept_count']} kept observation(s), skipping",
            flush=True,
        )
        _append_to_manifest(
            {
                "night": night,
                "scanned_count": state["scanned_count"],
                "kept_count": state["kept_count"],
                # Older checkpoints (written before this field existed)
                # don't store their own ra/dec/radius/min_rb -- fall back to
                # whatever this invocation was actually passed, which is
                # real input, not a guess.
                "ra": state.get("ra", ra),
                "dec": state.get("dec", dec),
                "radius_deg": state.get("radius_deg", radius_deg),
                "min_rb": state.get("min_rb", min_rb),
                "resumed_from_checkpoint": True,
            }
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
        "ra": ra,
        "dec": dec,
        "radius_deg": radius_deg,
        "min_rb": min_rb,
        "observations": kept,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = checkpoint_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(checkpoint_path)

    _append_to_manifest(
        {
            "night": night,
            "scanned_count": scanned,
            "kept_count": len(kept),
            "ra": ra,
            "dec": dec,
            "radius_deg": radius_deg,
            "min_rb": min_rb,
            "elapsed_seconds": round(elapsed, 2),
            "resumed_from_checkpoint": False,
        }
    )
    print(f"[ingest] {night}: updated {_MANIFEST_PATH}", flush=True)
    return state


def sync_manifest_from_checkpoints(out_dir: Path) -> int:
    """Backfill manifest entries from checkpoint files already on disk --
    for nights ingested by an earlier run of this script started before
    the manifest/auto-push behavior existed (or any other reason the
    manifest and checkpoints drifted apart). Does not re-download
    anything; only reads local checkpoint JSON already present. Returns
    the number of nights (re)synced."""
    synced = 0
    for checkpoint_path in sorted(out_dir.glob("*.json")):
        night = checkpoint_path.stem
        state = json.loads(checkpoint_path.read_text())
        print(f"[sync] {night}: found local checkpoint (kept={state['kept_count']})", flush=True)
        _append_to_manifest(
            {
                "night": night,
                "scanned_count": state["scanned_count"],
                "kept_count": state["kept_count"],
                # Fields absent from checkpoints predating this change are
                # reported as unknown (None) rather than guessed.
                "ra": state.get("ra"),
                "dec": state.get("dec"),
                "radius_deg": state.get("radius_deg"),
                "min_rb": state.get("min_rb"),
                "synced_from_existing_checkpoint": True,
            }
        )
        synced += 1
    return synced


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
        default=None,
        help=f"Explicit list of UTC nights to ingest, YYYYMMDD (max {_MAX_NIGHTS}). "
        "Required unless --status is passed.",
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
    parser.add_argument(
        "--status",
        action="store_true",
        help="Skip ingesting; instead print every night recorded in the "
        "committed manifest (Logs/reports/ztf_alert_archive_ingest_manifest.jsonl) "
        "-- run `git pull` first, then this, instead of pasting console "
        "output from concurrent tabs. --nights is ignored in this mode.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Skip ingesting; instead backfill manifest entries (and push "
        "them) from checkpoint files already on --out-dir, e.g. from a run "
        "started before the auto-push behavior existed. --nights is "
        "ignored in this mode.",
    )
    args = parser.parse_args()

    if args.status:
        by_night = read_manifest()
        if not by_night:
            print(
                f"[status] {_MANIFEST_PATH} does not exist yet -- no nights recorded.",
                flush=True,
            )
            return
        print(f"[status] {len(by_night)} night(s) recorded in {_MANIFEST_PATH}:", flush=True)
        for night in sorted(by_night):
            entry = by_night[night]
            print(
                f"[status]   {night}: kept={entry['kept_count']} "
                f"scanned={entry['scanned_count']} "
                f"RA={entry.get('ra')} Dec={entry.get('dec')} "
                f"radius_deg={entry.get('radius_deg')} min_rb={entry.get('min_rb')}",
                flush=True,
            )
        return

    if args.sync:
        synced = sync_manifest_from_checkpoints(args.out_dir)
        print(f"[sync] Backfilled {synced} night(s) from {args.out_dir}", flush=True)
        commit_and_push_manifest()
        return

    if not args.nights:
        raise SystemExit("--nights is required unless --status/--sync is passed")
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
    commit_and_push_manifest()


if __name__ == "__main__":
    main()
