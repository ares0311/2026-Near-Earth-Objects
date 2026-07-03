#!/usr/bin/env python
"""Gate Z3 -- scan a known NEO's real MPC-confirmed observation history for
real ZTF coverage overlap.

The first cross-check of the July 2018 MPC cluster (nights 20180711/13/14/15)
against Gate Z1 found real ZTF coverage on only 1 of those 4 real
MPC-confirmed nights (20180713) -- most of those specific reports were
evidently made by a different observatory/survey, not ZTF (MPC's
observation history is not survey-specific in this project's current
Observation mapping). See
docs/evidence/live/2026-07-02-mpc-observation-history-72966.md.

Rather than hand-picking more clusters, this script systematically checks
a bounded, stride-limited subset of ALL real in-archive-window MPC reports
(526 for object 72966) against the cheap Gate Z1 metadata endpoint, at
each report's own real observed position/date -- MPC positions are actual
past observations, not predictions, so this is the highest-confidence
targeting signal available. Reports every real night where BOTH an
independent MPC-confirmed detection AND real ZTF sci-exposure coverage
exist -- the strongest possible candidate set for the Gate Z3 known-object
positive control.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --designation 72966 \\
        --archive-start-jd 2458273.5 --stride 10

Parallel usage (run each in its own terminal tab to cut wall-clock time --
each shard queries a disjoint subset of the same already-strided report
list, so no two shards ever hit the same real position/date and there is
no cache race; the one-time MPC-history fetch itself resumes from the
already-cached checkpoint on this operator's machine, so no shard
re-fetches it over the network):
    caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --designation 72966 --archive-start-jd 2458273.5 --stride 10 \\
        --shard-index 0 --shard-count 4
    caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --designation 72966 --archive-start-jd 2458273.5 --stride 10 \\
        --shard-index 1 --shard-count 4
    caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --designation 72966 --archive-start-jd 2458273.5 --stride 10 \\
        --shard-index 2 --shard-count 4
    caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --designation 72966 --archive-start-jd 2458273.5 --stride 10 \\
        --shard-index 3 --shard-count 4

Each shard, as soon as it finishes, appends one line to a shared
manifest.jsonl in --out-dir (file-locked, so concurrent shards never
corrupt each other's entries) -- this can be checked at any time, not
just after every shard has finished:
    uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --status --shard-count 4

Once all shard-index tabs above have finished, run this once (fast, no
network) to combine all shards' manifest entries into one compact block
that is easy to paste back -- instead of pasting all 4 tabs' full
transcripts:
    uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --merge --shard-count 4
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_SKILLS_DIR = Path(__file__).resolve().parent
_OUT_DIR = Path("Logs/pipeline_runs/scan_mpc_history_ztf_coverage")
_MANIFEST_NAME = "manifest.jsonl"


def _load_skill(name: str):
    """Load a sibling Skills/ script by path -- these are not an installed
    package, matching how this project's other cross-Skill imports work."""
    spec = importlib.util.spec_from_file_location(name, _SKILLS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _append_to_manifest(out_dir: Path, entry: dict) -> Path:
    """Append one shard's completion summary as a JSON line to a shared
    manifest, so any shard (or the operator/agent) can check overall
    progress at any time without waiting for every shard to finish.
    File-locked (fcntl.flock) around the write so concurrent shards
    finishing at nearly the same moment cannot corrupt or interleave each
    other's lines -- each shard holds an exclusive lock only for the
    duration of its own single append."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / _MANIFEST_NAME
    line = json.dumps(entry) + "\n"
    with open(manifest_path, "a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    return manifest_path


def _read_manifest(out_dir: Path) -> dict[int, dict]:
    """Read manifest.jsonl and return the latest entry per shard_index
    (deduplicated, in case a shard was re-run) -- returns {} if the
    manifest does not exist yet."""
    manifest_path = out_dir / _MANIFEST_NAME
    if not manifest_path.exists():
        return {}
    by_shard: dict[int, dict] = {}
    for line in manifest_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        by_shard[entry["shard_index"]] = entry
    return by_shard


def run_scan(
    designation: str,
    archive_start_jd: float,
    stride: int,
    size_deg: float,
    out_dir: Path,
    shard_index: int = 0,
    shard_count: int = 1,
) -> dict:
    """Check real ZTF sci-metadata coverage at a bounded, stride-limited
    subset of a known object's real MPC-confirmed observation positions,
    reusing the already live-verified Gate Z1 metadata tool per candidate
    report. Never downloads the multi-GB alert archive itself.

    When shard_count > 1, only every shard_count-th row (offset by
    shard_index) of the already-strided list is checked here -- running
    all shard_index values 0..shard_count-1 concurrently (e.g. one per
    terminal tab) covers the full strided list with no overlap between
    shards, since each shard's rows are disjoint by construction."""
    mpc_lookup = _load_skill("lookup_mpc_observation_history")
    z1 = _load_skill("ztf_dr24_bounded_ingest")

    mpc_report = mpc_lookup.run_lookup(designation, archive_start_jd, out_dir / "mpc_history")
    all_rows = mpc_report["reports_in_archive_window"][::stride]
    rows = all_rows[shard_index::shard_count] if shard_count > 1 else all_rows
    shard_label = f" shard {shard_index}/{shard_count}" if shard_count > 1 else ""
    print(
        f"[scan]{shard_label} Checking {len(rows)} of {mpc_report['n_reports_in_archive_window']} "
        f"real in-window MPC report(s) (stride={stride}) for real ZTF coverage",
        flush=True,
    )

    t0 = time.monotonic()
    hits = []
    for i, row in enumerate(rows, start=1):
        z1_report = z1.run_bounded_ingest(
            ra=row["ra_deg"],
            dec=row["dec_deg"],
            size_deg=size_deg,
            start_jd=row["jd"] - 0.5,
            end_jd=row["jd"] + 0.5,
            out_dir=out_dir / "z1_checks",
        )
        n_rows = z1_report["n_rows"]
        if n_rows > 0:
            hits.append({**row, "n_sci_rows": n_rows})

        elapsed = time.monotonic() - t0
        eta = (elapsed / i) * (len(rows) - i)
        print(
            f"[scan]{shard_label} ({i}/{len(rows)}) {row['night_yyyymmdd']}: "
            f"RA={row['ra_deg']:.4f} Dec={row['dec_deg']:.4f} -> "
            f"{n_rows} real sci exposure row(s)  elapsed {_fmt_duration(elapsed)}  "
            f"ETA {_fmt_duration(eta)}",
            flush=True,
        )

    report = {
        "designation": designation,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "n_reports_checked": len(rows),
        "n_reports_with_ztf_coverage": len(hits),
        "hits": hits,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    if shard_count <= 1:
        report_name = "scan_report.json"
    else:
        report_name = f"scan_report.shard{shard_index}of{shard_count}.json"
    report_path = out_dir / report_name
    report_path.write_text(json.dumps(report, indent=2))

    print(
        f"[scan]{shard_label} Complete: {len(hits)}/{len(rows)} checked MPC reports "
        f"had real ZTF coverage at their exact position/date  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    for hit in hits:
        print(
            f"[scan]{shard_label}   HIT {hit['night_yyyymmdd']}: RA={hit['ra_deg']:.4f} "
            f"Dec={hit['dec_deg']:.4f}  ({hit['n_sci_rows']} sci row(s))",
            flush=True,
        )
    print(f"[scan]{shard_label} Wrote {report_path}", flush=True)

    manifest_path = _append_to_manifest(out_dir, report)
    print(f"[scan]{shard_label} Updated {manifest_path}", flush=True)
    return report


def report_status(out_dir: Path, shard_count: int) -> dict:
    """Read the shared manifest at any time (even mid-run) and report how
    many of shard_count shards have reported in so far, which are still
    missing, and a running combined hit list from the shards that have
    completed. Never fails closed -- this is an explicitly partial-progress
    check, unlike merge_shards()."""
    by_shard = _read_manifest(out_dir)
    reported = sorted(by_shard)
    missing = [i for i in range(shard_count) if i not in by_shard]
    all_hits = sorted(
        (hit for entry in by_shard.values() for hit in entry["hits"]),
        key=lambda h: h["jd"],
    )
    total_checked = sum(entry["n_reports_checked"] for entry in by_shard.values())

    status = {
        "shard_count": shard_count,
        "shards_reported": reported,
        "shards_missing": missing,
        "n_reports_checked_so_far": total_checked,
        "n_reports_with_ztf_coverage_so_far": len(all_hits),
        "hits_so_far": all_hits,
    }
    print(
        f"[status] {len(reported)}/{shard_count} shard(s) reported in "
        f"(missing: {missing if missing else 'none'})  "
        f"{total_checked} MPC report(s) checked so far, "
        f"{len(all_hits)} with real ZTF coverage so far",
        flush=True,
    )
    for hit in all_hits:
        print(
            f"[status]   HIT {hit['night_yyyymmdd']}: RA={hit['ra_deg']:.4f} "
            f"Dec={hit['dec_deg']:.4f}  ({hit['n_sci_rows']} sci row(s))  jd={hit['jd']:.5f}",
            flush=True,
        )
    return status


def merge_shards(out_dir: Path, shard_count: int) -> dict:
    """Read every shard's entry from the shared manifest and combine them
    into one final summary -- lets the operator paste a single compact
    block instead of every shard's full console transcript. Fails closed
    (raises) if any expected shard hasn't reported in yet, rather than
    silently reporting partial results as if the scan were complete (use
    report_status() for an explicitly partial check instead)."""
    by_shard = _read_manifest(out_dir)
    missing = [i for i in range(shard_count) if i not in by_shard]
    if missing:
        raise FileNotFoundError(
            f"Cannot merge: {len(missing)}/{shard_count} shard(s) have not "
            f"reported in yet -- missing shard_index {missing}. Wait for all "
            f"shards to finish before merging, or use --status for a partial check."
        )

    all_hits = sorted(
        (hit for entry in by_shard.values() for hit in entry["hits"]),
        key=lambda h: h["jd"],
    )
    total_checked = sum(by_shard[i]["n_reports_checked"] for i in range(shard_count))
    merged = {
        "shard_count": shard_count,
        "n_reports_checked": total_checked,
        "n_reports_with_ztf_coverage": len(all_hits),
        "hits": all_hits,
    }
    merged_path = out_dir / "scan_report.merged.json"
    merged_path.write_text(json.dumps(merged, indent=2))

    print(
        f"[merge] Combined {shard_count} shard(s): {total_checked} MPC report(s) "
        f"checked, {len(all_hits)} with real ZTF coverage",
        flush=True,
    )
    for hit in all_hits:
        print(
            f"[merge]   HIT {hit['night_yyyymmdd']}: RA={hit['ra_deg']:.4f} "
            f"Dec={hit['dec_deg']:.4f}  ({hit['n_sci_rows']} sci row(s))  jd={hit['jd']:.5f}",
            flush=True,
        )
    print(f"[merge] Wrote {merged_path}", flush=True)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--designation",
        default="72966",
        help="Real MPC/JPL designation to check (default: 72966).",
    )
    parser.add_argument(
        "--archive-start-jd",
        type=float,
        default=2458273.5,
        help="Only check MPC observations at/after this JD (default: "
        "2458273.5, the UW ZTF alert archive's documented start of real "
        "coverage).",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=10,
        help="Check every Nth in-window MPC report (default: 10) -- bounds "
        "the number of IRSA metadata queries issued.",
    )
    parser.add_argument(
        "--size-deg",
        type=float,
        default=2.0,
        help="Gate Z1 sci-metadata search-box size in degrees (default: 2.0).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_OUT_DIR,
        help=f"Checkpoint directory (default: {_OUT_DIR}).",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=0,
        help="0-based shard index for parallel runs (default: 0). Run one "
        "process per shard-index value 0..shard-count-1 -- e.g. in separate "
        "terminal tabs -- to check disjoint subsets of the same strided "
        "report list concurrently. See module docstring for a 4-shard example.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=1,
        help="Total number of shards for parallel runs (default: 1, no "
        "sharding).",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Skip scanning; instead combine every shard's manifest entry "
        "in --out-dir into one final compact summary (fails closed if any "
        "shard hasn't reported in yet).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Skip scanning; instead report how many shards have reported "
        "in to the shared manifest so far, and a running combined hit list "
        "-- safe to run at any time, even mid-scan, unlike --merge.",
    )
    args = parser.parse_args()

    if args.shard_count < 1:
        raise SystemExit("--shard-count must be >= 1")

    if args.merge:
        merge_shards(args.out_dir, args.shard_count)
        return

    if args.status:
        report_status(args.out_dir, args.shard_count)
        return

    if args.stride < 1:
        raise SystemExit("--stride must be >= 1")
    if not (0 <= args.shard_index < args.shard_count):
        raise SystemExit(
            f"--shard-index must be in [0, {args.shard_count}) for "
            f"--shard-count {args.shard_count}, got {args.shard_index}"
        )

    run_scan(
        args.designation, args.archive_start_jd, args.stride, args.size_deg, args.out_dir,
        args.shard_index, args.shard_count,
    )


if __name__ == "__main__":
    main()
