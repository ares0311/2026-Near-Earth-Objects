#!/usr/bin/env python
"""Gate Z3 -- targeted candidate-night lookup for a real, known NEO.

Blind field-revisit sampling for Gate Z3's "known-object positive control"
has cost two real multi-GB alert-archive downloads for zero net progress
(see docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-second-attempt.md).
This script replaces guessing with a targeted approach: query the already
Phase-0-verified JPL Horizons endpoint (src/fetch.py's fetch_horizons,
100% covered production code) for a real, known minor planet's real
historical sky position across a date range, so a follow-up
Skills/ztf_dr24_bounded_ingest.py / Skills/ztf_alert_archive_ingest.py run
can target real predicted positions instead of an arbitrary field.

Default target designation "72966" is not a guess -- it is the real
ssnamenr cross-match already present in a real, live-downloaded ZTF alert
packet from night 20180809 at this project's Gate Z3 target field (see
docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md).

Night-date conversion uses the same full-precision-JD approach as the
Gate Z1 tool's v0.90.39 fix (Skills/ztf_dr24_bounded_ingest.py) -- JD
increments at noon UTC, not midnight, so truncating before converting
would reintroduce the same off-by-one bug fixed there.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/lookup_neo_archive_ephemeris.py \\
        --designation 72966 \\
        --start-jd 2458339.5 --end-jd 2458439.5 --step 1d
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
_OUT_DIR = Path("Logs/pipeline_runs/lookup_neo_archive_ephemeris")


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _fetch_horizons_with_retry(designation: str, start_jd: float, end_jd: float, step: str):
    """Wrap fetch.fetch_horizons in exponential-backoff retry -- the
    underlying function has no retry of its own, so this script supplies
    it per the standing network-retry rule."""
    from fetch import fetch_horizons  # lazy import, matches project convention

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return fetch_horizons(
                target=designation, ra_deg=0.0, dec_deg=0.0,
                start_jd=start_jd, end_jd=end_jd, step=step,
            )
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
        f"JPL Horizons ephemeris fetch for {designation} failed after "
        f"{_MAX_ATTEMPTS} attempts"
    ) from last_exc


def _night_yyyymmdd(jd: float) -> str:
    """Real UTC calendar date from a full, un-truncated JD -- matches the
    v0.90.39 Gate Z1 fix; never truncate a JD to an integer before this."""
    from astropy.time import Time  # lazy import, matches project convention

    return Time(jd, format="jd").datetime.strftime("%Y%m%d")


def run_lookup(designation: str, start_jd: float, end_jd: float, step: str, out_dir: Path) -> dict:
    """Fetch a real known object's ephemeris across the requested window and
    report its predicted (RA, Dec) on each distinct real calendar night, so
    a follow-up alert-archive ingest run can target a real position instead
    of guessing a field."""
    key = f"{designation}_{start_jd}_{end_jd}_{step}".replace(" ", "")
    run_dir = out_dir / key
    checkpoint_path = run_dir / "ephemeris_report.json"

    if checkpoint_path.exists():
        print(f"[resume] lookup {key}: checkpoint already present, skipping fetch", flush=True)
        return json.loads(checkpoint_path.read_text())

    t0 = time.monotonic()
    print(
        f"[lookup] Requesting JPL Horizons ephemeris for {designation} "
        f"({start_jd} to {end_jd}, step={step})  elapsed {_fmt_duration(0)}",
        flush=True,
    )
    observations = _fetch_horizons_with_retry(designation, start_jd, end_jd, step)
    print(
        f"[lookup] Received {len(observations)} ephemeris point(s)  "
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
                "night_yyyymmdd": _night_yyyymmdd(obs.jd),
            }
        )
    rows.sort(key=lambda r: r["jd"])

    report = {
        "designation": designation,
        "start_jd": start_jd,
        "end_jd": end_jd,
        "step": step,
        "n_points": len(rows),
        "rows": rows,
        "elapsed_seconds": round(time.monotonic() - t0, 2),
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(report, indent=2))

    print(
        f"[lookup] Parsed {len(rows)} real ephemeris point(s) for {designation}  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    for row in rows:
        print(
            f"[lookup]   {row['night_yyyymmdd']}: RA={row['ra_deg']:.4f} "
            f"Dec={row['dec_deg']:.4f}  (jd={row['jd']:.5f})",
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
        help="Real MPC/JPL designation to look up (default: 72966, the "
        "ssnamenr already confirmed present in a real Gate Z3 alert packet).",
    )
    parser.add_argument("--start-jd", type=float, required=True, help="Window start, Julian date")
    parser.add_argument("--end-jd", type=float, required=True, help="Window end, Julian date")
    parser.add_argument(
        "--step", default="1d", help="Horizons ephemeris step size (default: 1d)"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_OUT_DIR,
        help=f"Checkpoint directory (default: {_OUT_DIR}).",
    )
    args = parser.parse_args()

    run_lookup(args.designation, args.start_jd, args.end_jd, args.step, args.out_dir)


if __name__ == "__main__":
    main()
