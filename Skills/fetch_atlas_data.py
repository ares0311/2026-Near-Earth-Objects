#!/usr/bin/env python3
"""Fetch ATLAS forced photometry for one sky position or a batch of positions.

Single-position mode (original):
    python Skills/fetch_atlas_data.py <ra> <dec> <start_jd> <end_jd> [--token T]

Batch mode (new): reads a CSV with columns ra,dec,start_jd,end_jd[,label],
fetches each position (optionally in parallel), and writes per-position JSON
files to --out-dir.  Supports --resume to skip positions already fetched.

    python Skills/fetch_atlas_data.py \\
        --positions-csv targets.csv \\
        --out-dir data/atlas_batch/ \\
        --workers 8 \\
        --resume \\
        --token "$ATLAS_TOKEN"

Batch CSV format (header required):
    ra,dec,start_jd,end_jd[,label]
    10.5,-5.2,2460000,2460030,target_A
    22.1,+3.7,2460000,2460030

The optional label column becomes the output filename stem; without it the
row index is used.  Existing output files are skipped when --resume is given.
Output files are written as <out-dir>/<label_or_index>.json.

Threading notes
---------------
ATLAS forced photometry requests involve server-side task queuing and a polling
loop; each request may take 10–120 s.  --workers controls how many positions
are fetched concurrently.  Default is 1 (sequential).  With gigabit connectivity
and an ATLAS token, 4–8 workers saturate the practical throughput.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PYTHONPATH_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PYTHONPATH_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHONPATH_SRC))


def _load_positions_csv(path: Path) -> list[dict[str, Any]]:
    """Load and validate the batch positions CSV; return a list of position dicts."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("positions CSV is empty")

    required = {"ra", "dec", "start_jd", "end_jd"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"positions CSV is missing columns: {sorted(missing)}")

    positions = []
    for index, row in enumerate(rows):
        try:
            positions.append(
                {
                    "index": index,
                    "label": str(row.get("label", "") or index).strip() or str(index),
                    "ra": float(row["ra"]),
                    "dec": float(row["dec"]),
                    "start_jd": float(row["start_jd"]),
                    "end_jd": float(row["end_jd"]),
                }
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid row {index}: {exc}") from exc
    return positions


def _fetch_position(
    pos: dict[str, Any],
    atlas_token: str | None,
    force_refresh: bool,
    fetcher: Callable[..., list[Any]],
) -> tuple[dict[str, Any], list[Any]]:
    """Fetch one sky position; return (pos, observations).  Thread-safe."""
    observations = fetcher(
        ra_deg=pos["ra"],
        dec_deg=pos["dec"],
        start_jd=pos["start_jd"],
        end_jd=pos["end_jd"],
        atlas_token=atlas_token,
        force_refresh=force_refresh,
    )
    return pos, observations


def _observations_to_json(observations: list[Any]) -> list[dict[str, Any]]:
    """Serialise Observation objects into dicts for JSON output."""
    return [
        {
            "obs_id": o.obs_id,
            "ra_deg": o.ra_deg,
            "dec_deg": o.dec_deg,
            "jd": o.jd,
            "mag": o.mag,
            "mag_err": o.mag_err,
            "filter_band": o.filter_band,
            "mission": o.mission,
        }
        for o in observations
    ]


def _output_path(out_dir: Path, label: str) -> Path:
    """Derive the per-position output file path from the label."""
    safe_label = str(label).replace("/", "_").replace(" ", "_")
    return out_dir / f"{safe_label}.json"


def run_batch(
    positions_csv: Path,
    out_dir: Path,
    atlas_token: str | None,
    force_refresh: bool,
    resume: bool,
    workers: int,
    fetcher: Callable[..., list[Any]],
    print_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch all positions in the CSV and write per-position JSON output.

    Returns a summary dict with counts: total, skipped, fetched, failed.
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")

    positions = _load_positions_csv(positions_csv)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resume: skip positions where the output file already exists.
    todo = []
    skipped = 0
    for pos in positions:
        out_path = _output_path(out_dir, pos["label"])
        if resume and out_path.exists():
            skipped += 1
        else:
            todo.append(pos)

    fetched = 0
    failed = 0
    _print_lock = threading.Lock()

    def _do_one(pos: dict[str, Any]) -> tuple[dict[str, Any], list[Any] | None, str | None]:
        """Fetch one position; return (pos, observations | None, error_msg | None)."""
        try:
            _, obs = _fetch_position(pos, atlas_token, force_refresh, fetcher)
            return pos, obs, None
        except Exception as exc:
            return pos, None, str(exc)

    if workers == 1:
        results = [_do_one(pos) for pos in todo]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(_do_one, pos): pos for pos in todo}
            for future in as_completed(future_map):
                results.append(future.result())

    for pos, obs, err in results:
        out_path = _output_path(out_dir, pos["label"])
        if err is not None:
            failed += 1
            with _print_lock:
                print_fn(
                    f"FAILED ra={pos['ra']} dec={pos['dec']}: {err}",
                    file=sys.stderr,
                )
            continue
        payload = {
            "ra_deg": pos["ra"],
            "dec_deg": pos["dec"],
            "start_jd": pos["start_jd"],
            "end_jd": pos["end_jd"],
            "label": pos["label"],
            "n_obs": len(obs or []),
            "observations": _observations_to_json(obs or []),
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        fetched += 1
        with _print_lock:
            print_fn(f"OK  {pos['label']:30s} n_obs={len(obs or [])}")

    summary = {
        "total": len(positions),
        "skipped": skipped,
        "fetched": fetched,
        "failed": failed,
    }
    return summary


def main() -> None:
    """Parse CLI for single-position or batch mode."""
    parser = argparse.ArgumentParser(
        description="Fetch ATLAS forced photometry for one or many sky positions."
    )

    # --- Single-position positional args (preserved from original) ---
    parser.add_argument(
        "ra", nargs="?", type=float, help="Right ascension in degrees (single-position mode)"
    )
    parser.add_argument(
        "dec", nargs="?", type=float, help="Declination in degrees (single-position mode)"
    )
    parser.add_argument(
        "start_jd", nargs="?", type=float, help="Start Julian date (single-position mode)"
    )
    parser.add_argument(
        "end_jd", nargs="?", type=float, help="End Julian date (single-position mode)"
    )

    # --- Batch mode args ---
    parser.add_argument(
        "--positions-csv",
        type=Path,
        help="CSV with columns ra,dec,start_jd,end_jd[,label] for batch mode",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Output directory for per-position JSON files (batch mode)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip positions whose output file already exists (batch mode)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel fetch threads for batch mode (default 1)",
    )

    # --- Shared args ---
    parser.add_argument(
        "--token",
        default=None,
        help="ATLAS API token (or set ATLAS_TOKEN environment variable)",
    )
    parser.add_argument("--force-refresh", action="store_true", help="Bypass on-disk cache")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (single mode only)")
    args = parser.parse_args()

    from fetch import fetch_atlas_forced  # type: ignore[import]

    # Batch mode.
    if args.positions_csv:
        if not args.out_dir:
            parser.error("--out-dir is required with --positions-csv")
        summary = run_batch(
            args.positions_csv,
            args.out_dir,
            atlas_token=args.token,
            force_refresh=args.force_refresh,
            resume=args.resume,
            workers=args.workers,
            fetcher=fetch_atlas_forced,
        )
        print(json.dumps(summary, indent=2))
        return

    # Single-position mode (original behaviour).
    if args.ra is None or args.dec is None or args.start_jd is None or args.end_jd is None:
        parser.error("provide ra dec start_jd end_jd or use --positions-csv for batch mode")

    observations = fetch_atlas_forced(
        ra_deg=args.ra,
        dec_deg=args.dec,
        start_jd=args.start_jd,
        end_jd=args.end_jd,
        atlas_token=args.token,
        force_refresh=args.force_refresh,
    )

    if args.json:
        print(json.dumps(_observations_to_json(observations), indent=2))
        return

    if not observations:
        print("No ATLAS observations returned (check token, coordinates, or date range).")
        return

    hdr = f"{'obs_id':<24} {'JD':>13} {'RA':>10} {'Dec':>10} {'mag':>7} {'err':>6} {'band':>5}"
    print(hdr)
    print("-" * len(hdr))
    for o in observations:
        print(
            f"{o.obs_id:<24} {o.jd:>13.5f} {o.ra_deg:>10.5f} {o.dec_deg:>10.5f}"
            f" {o.mag:>7.3f} {o.mag_err:>6.3f} {o.filter_band:>5}"
        )


if __name__ == "__main__":
    main()
