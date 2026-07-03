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
) -> dict:
    """Check real ZTF sci-metadata coverage at a bounded, stride-limited
    subset of a known object's real MPC-confirmed observation positions,
    reusing the already live-verified Gate Z1 metadata tool per candidate
    report. Never downloads the multi-GB alert archive itself."""
    mpc_lookup = _load_skill("lookup_mpc_observation_history")
    z1 = _load_skill("ztf_dr24_bounded_ingest")

    mpc_report = mpc_lookup.run_lookup(designation, archive_start_jd, out_dir / "mpc_history")
    rows = mpc_report["reports_in_archive_window"][::stride]
    print(
        f"[scan] Checking {len(rows)} of {mpc_report['n_reports_in_archive_window']} "
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
            f"[scan] ({i}/{len(rows)}) {row['night_yyyymmdd']}: "
            f"RA={row['ra_deg']:.4f} Dec={row['dec_deg']:.4f} -> "
            f"{n_rows} real sci exposure row(s)  elapsed {_fmt_duration(elapsed)}  "
            f"ETA {_fmt_duration(eta)}",
            flush=True,
        )

    report = {
        "designation": designation,
        "n_reports_checked": len(rows),
        "n_reports_with_ztf_coverage": len(hits),
        "hits": hits,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "scan_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print(
        f"[scan] Complete: {len(hits)}/{len(rows)} checked MPC reports had real "
        f"ZTF coverage at their exact position/date  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    for hit in hits:
        print(
            f"[scan]   HIT {hit['night_yyyymmdd']}: RA={hit['ra_deg']:.4f} "
            f"Dec={hit['dec_deg']:.4f}  ({hit['n_sci_rows']} sci row(s))",
            flush=True,
        )
    print(f"[scan] Wrote {report_path}", flush=True)
    return report


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
    args = parser.parse_args()

    if args.stride < 1:
        raise SystemExit("--stride must be >= 1")

    run_scan(
        args.designation, args.archive_start_jd, args.stride, args.size_deg, args.out_dir
    )


if __name__ == "__main__":
    main()
