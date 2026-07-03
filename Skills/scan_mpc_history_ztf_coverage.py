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

Once all shard-index tabs above have finished, run this once (fast, no
network) to combine all shard report files into one compact block that is
easy to paste back -- instead of pasting all 4 tabs' full transcripts:
    uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \\
        --merge --shard-count 4
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_SKILLS_DIR = Path(__file__).resolve().parent
_OUT_DIR = Path("Logs/pipeline_runs/scan_mpc_history_ztf_coverage")


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
    return report


def merge_shards(out_dir: Path, shard_count: int) -> dict:
    """Read all scan_report.shard{i}of{shard_count}.json files already
    written by a completed parallel run and combine them into one summary
    -- lets the operator paste a single compact block instead of every
    shard's full console transcript. Fails closed (raises) if any expected
    shard file is missing, rather than silently reporting partial results
    as if the scan were complete."""
    missing = []
    all_hits = []
    total_checked = 0
    for shard_index in range(shard_count):
        shard_path = out_dir / f"scan_report.shard{shard_index}of{shard_count}.json"
        if not shard_path.exists():
            missing.append(str(shard_path))
            continue
        shard_report = json.loads(shard_path.read_text())
        all_hits.extend(shard_report["hits"])
        total_checked += shard_report["n_reports_checked"]

    if missing:
        raise FileNotFoundError(
            f"Cannot merge: {len(missing)}/{shard_count} shard report(s) missing "
            f"-- {missing}. Wait for all shards to finish before merging."
        )

    all_hits.sort(key=lambda h: h["jd"])
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
        help="Skip scanning; instead combine already-completed "
        "scan_report.shard{i}of{shard-count}.json files in --out-dir into "
        "one compact summary (fails closed if any shard hasn't finished yet).",
    )
    args = parser.parse_args()

    if args.shard_count < 1:
        raise SystemExit("--shard-count must be >= 1")

    if args.merge:
        merge_shards(args.out_dir, args.shard_count)
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
