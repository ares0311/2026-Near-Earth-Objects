#!/usr/bin/env python
"""Gate Z3 -- cross-check a known NEO's real MPC-confirmed observation
history against the ZTF alert archive's coverage window.

Three real Gate Z3 alert-archive attempts (blind field-revisit x2,
ephemeris-targeted x1 -- see docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-*.md)
have each returned zero kept detections, including one on a night with
Gate Z1-confirmed real ZTF science exposure at the object's predicted
position. Root-cause diagnosis: a real science exposure existing confirms
only that ZTF pointed a camera there -- not that its difference-imaging
pipeline generated a real alert with rb >= 0.5 at that exact sub-position.

This script queries a categorically stronger signal: MPC's own confirmed
observation history (src/fetch.py's fetch_mpc_observations, already
Phase-0-verified production code, 100% covered). A real MPC-reported
observation means a real astrometric detection was made and credible
enough to be submitted and accepted by the community -- direct evidence an
alert-equivalent detection genuinely happened, not just that the sky was
imaged.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/lookup_mpc_observation_history.py \\
        --designation 72966 \\
        --archive-start-jd 2458270.5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = (2, 4, 8, 16, 32)
_OUT_DIR = Path("Logs/pipeline_runs/lookup_mpc_observation_history")
# 2018-06-04 00:00 UTC, the UW ZTF public alert archive's documented start
# of real coverage (see docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md).
_DEFAULT_ARCHIVE_START_JD = 2458273.5


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _fetch_mpc_with_retry(designation: str):
    """Wrap fetch.fetch_mpc_observations in exponential-backoff retry --
    the underlying function has its own infra-error handling but no sleep-
    based retry loop, so this script supplies one per the standing rule."""
    from fetch import fetch_mpc_observations  # lazy import, matches project convention

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return fetch_mpc_observations(designation, raise_on_error=True)
        except (ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc
            print(
                f"[lookup] attempt {attempt}/{_MAX_ATTEMPTS} failed "
                f"({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    raise RuntimeError(
        f"MPC observation history fetch for {designation} failed after "
        f"{_MAX_ATTEMPTS} attempts"
    ) from last_exc


def _night_yyyymmdd(jd: float) -> str:
    """Real UTC calendar date from a full, un-truncated JD -- matches the
    v0.90.39 Gate Z1 fix; never truncate a JD to an integer before this."""
    from astropy.time import Time  # lazy import, matches project convention

    return Time(jd, format="jd").datetime.strftime("%Y%m%d")


def run_lookup(designation: str, archive_start_jd: float, out_dir: Path) -> dict:
    """Fetch a real known object's full MPC observation history and report
    which real reports fall within the ZTF alert archive's real coverage
    window, so a follow-up alert-archive attempt targets a night with
    independently-confirmed real detection evidence, not just imaging
    coverage."""
    key = f"{designation}_{archive_start_jd}".replace(" ", "")
    run_dir = out_dir / key
    checkpoint_path = run_dir / "mpc_history_report.json"

    if checkpoint_path.exists():
        print(f"[lookup] {key}: checkpoint already present, skipping fetch", flush=True)
        return json.loads(checkpoint_path.read_text())

    t0 = time.monotonic()
    print(f"[lookup] Requesting MPC observation history for {designation}", flush=True)
    observations = _fetch_mpc_with_retry(designation)
    print(
        f"[lookup] Received {len(observations)} real MPC-reported observation(s)  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    rows = []
    for obs in observations:
        rows.append(
            {
                "jd": obs.jd,
                "ra_deg": obs.ra_deg,
                "dec_deg": obs.dec_deg,
                "mag": obs.mag,
                "night_yyyymmdd": _night_yyyymmdd(obs.jd),
                "in_archive_window": obs.jd >= archive_start_jd,
            }
        )
    rows.sort(key=lambda r: r["jd"])
    in_window = [r for r in rows if r["in_archive_window"]]

    report = {
        "designation": designation,
        "archive_start_jd": archive_start_jd,
        "n_total_reports": len(rows),
        "n_reports_in_archive_window": len(in_window),
        "reports_in_archive_window": in_window,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(report, indent=2))

    print(
        f"[lookup] {designation}: {len(rows)} total real MPC report(s), "
        f"{len(in_window)} within the ZTF archive's coverage window "
        f"(JD >= {archive_start_jd})  elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    for row in in_window:
        print(
            f"[lookup]   {row['night_yyyymmdd']}: RA={row['ra_deg']:.4f} "
            f"Dec={row['dec_deg']:.4f} mag={row['mag']:.2f}  (jd={row['jd']:.5f})",
            flush=True,
        )
    print(f"[lookup] Wrote {checkpoint_path}", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--designation",
        default="72966",
        help="Real MPC designation to look up (default: 72966).",
    )
    parser.add_argument(
        "--archive-start-jd",
        type=float,
        default=_DEFAULT_ARCHIVE_START_JD,
        help=f"Only report MPC observations at/after this JD (default: "
        f"{_DEFAULT_ARCHIVE_START_JD}, the UW ZTF alert archive's documented "
        f"start of real coverage).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_OUT_DIR,
        help=f"Checkpoint directory (default: {_OUT_DIR}).",
    )
    args = parser.parse_args()

    run_lookup(args.designation, args.archive_start_jd, args.out_dir)


if __name__ == "__main__":
    main()
