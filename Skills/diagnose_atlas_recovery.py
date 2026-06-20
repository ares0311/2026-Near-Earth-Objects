#!/usr/bin/env python3
"""Diagnose a completed ATLAS recovery run checkpoint.

Reads the checkpoint.json from an ATLAS recovery run directory and prints a
per-designation, per-sample breakdown.  Optionally queries JPL Horizons for
the expected sky position at each sampled JD to check whether the manifest
positions match the actual ephemeris (a manifest error would cause ATLAS to
query the wrong sky position, explaining zero detections).

Usage — show all designations from a run:
    PYTHONPATH=src python Skills/diagnose_atlas_recovery.py \\
        --run-dir Logs/pipeline_runs/atlas_recovery_175ef40ac577

Usage — focus on one designation:
    PYTHONPATH=src python Skills/diagnose_atlas_recovery.py \\
        --run-dir Logs/pipeline_runs/atlas_recovery_175ef40ac577 \\
        --designation 2973

Usage — compare manifest positions against Horizons ephemeris:
    PYTHONPATH=src python Skills/diagnose_atlas_recovery.py \\
        --run-dir Logs/pipeline_runs/atlas_recovery_175ef40ac577 \\
        --designation 2973 \\
        --check-horizons

Usage — JSON output (machine-readable):
    PYTHONPATH=src python Skills/diagnose_atlas_recovery.py \\
        --run-dir Logs/pipeline_runs/atlas_recovery_175ef40ac577 \\
        --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _load_checkpoint(run_dir: Path) -> dict[str, Any]:
    """Load and validate the ATLAS recovery checkpoint from a run directory."""
    cp_path = run_dir / "checkpoint.json"
    if not cp_path.exists():
        raise FileNotFoundError(f"No checkpoint found at {cp_path}")
    data = json.loads(cp_path.read_text(encoding="utf-8"))
    if "samples" not in data:
        raise ValueError("Checkpoint has no 'samples' key — not an ATLAS recovery checkpoint")
    return data


def _sample_status_symbol(status: str) -> str:
    """Single-character symbol for sample status — easier to scan in tables."""
    return {
        "recovered": "✓",
        "not_recovered": "✗",
        "poll_exhausted": "?",
        "polling": "…",
        "failed": "!",
    }.get(status, status)


def _sep_distance_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle angular separation between two sky positions in arcsec."""
    d2r = math.pi / 180.0
    c1 = math.cos(dec1 * d2r)
    c2 = math.cos(dec2 * d2r)
    dra = (ra2 - ra1) * d2r
    ddec = (dec2 - dec1) * d2r
    # Haversine formula — numerically stable for small angles
    a = math.sin(ddec / 2) ** 2 + c1 * c2 * math.sin(dra / 2) ** 2
    sep_rad = 2 * math.asin(math.sqrt(min(a, 1.0)))
    return sep_rad * (180.0 / math.pi) * 3600.0


def _query_horizons_position(designation: str, jd: float) -> dict[str, float] | None:
    """Query JPL Horizons for the sky position of a numbered asteroid at jd.

    Returns dict with keys ra_deg, dec_deg, or None on failure.
    This requires network access and astroquery; failures are silently
    returned as None so the rest of the diagnostic is unaffected.
    """
    try:
        from astroquery.jplhorizons import Horizons

        obj = Horizons(
            id=designation,
            location="500",  # geocenter
            epochs=jd,
            id_type="smallbody",
        )
        eph = obj.ephemerides()
        if eph is None or len(eph) == 0:
            return None
        row = eph[0]
        return {
            "ra_deg": float(row["RA"]),
            "dec_deg": float(row["DEC"]),
        }
    except Exception:
        return None


def diagnose_run(
    run_dir: Path,
    *,
    designation_filter: str | None = None,
    check_horizons: bool = False,
) -> dict[str, Any]:
    """Build a per-designation diagnostic summary from a recovery checkpoint.

    Returns a dict with keys:
      run_id, params, by_designation (list), status_counts, summary
    """
    checkpoint = _load_checkpoint(run_dir)
    run_id = run_dir.name
    params: dict[str, Any] = checkpoint.get("params", {})
    raw_samples: dict[str, Any] = checkpoint.get("samples", {})

    # Group samples by designation
    by_desig: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key, sample in raw_samples.items():
        if not isinstance(sample, dict):
            continue
        desig = str(sample.get("designation") or key).strip()
        by_desig[desig].append(sample)

    # Sort samples within each designation by sample_index for readability
    for desig in by_desig:
        by_desig[desig].sort(key=lambda s: int(s.get("sample_index", 0)))

    status_counts: dict[str, int] = defaultdict(int)
    for samples in by_desig.values():
        for s in samples:
            status_counts[str(s.get("status", "unknown"))] += 1

    by_designation_output: list[dict[str, Any]] = []

    for desig in sorted(by_desig.keys()):
        if designation_filter and desig != designation_filter:
            continue
        samples = by_desig[desig]
        desig_status_counts: dict[str, int] = defaultdict(int)
        for s in samples:
            desig_status_counts[str(s.get("status", "unknown"))] += 1

        sample_rows: list[dict[str, Any]] = []
        for s in samples:
            idx = s.get("sample_index", "?")
            jd = float(s.get("requested_jd", s.get("jd", float("nan"))))
            ra = float(s.get("requested_ra_deg", s.get("ra_deg", float("nan"))))
            dec = float(s.get("requested_dec_deg", s.get("dec_deg", float("nan"))))
            status = str(s.get("status", "unknown"))
            n_usable = int(s.get("n_usable_observations", 0))
            n_raw = int(s.get("n_raw_observations", 0))
            task_url = s.get("task_url") or ""
            queuepos = s.get("queuepos")

            row: dict[str, Any] = {
                "sample_index": idx,
                "jd": jd,
                "ra_deg": ra,
                "dec_deg": dec,
                "status": status,
                "n_raw_observations": n_raw,
                "n_usable_observations": n_usable,
                "task_url": task_url,
                "queuepos": queuepos,
            }

            # Optional Horizons position check
            if check_horizons and not math.isnan(jd) and not math.isnan(ra):
                horizons_pos = _query_horizons_position(desig, jd)
                if horizons_pos is not None:
                    sep = _sep_distance_arcsec(
                        ra, dec, horizons_pos["ra_deg"], horizons_pos["dec_deg"]
                    )
                    row["horizons_ra_deg"] = horizons_pos["ra_deg"]
                    row["horizons_dec_deg"] = horizons_pos["dec_deg"]
                    row["sep_from_horizons_arcsec"] = round(sep, 2)
                else:
                    row["horizons_ra_deg"] = None
                    row["horizons_dec_deg"] = None
                    row["sep_from_horizons_arcsec"] = None

            sample_rows.append(row)

        recovered = desig_status_counts.get("recovered", 0)
        not_recovered = desig_status_counts.get("not_recovered", 0)
        poll_exhausted = desig_status_counts.get("poll_exhausted", 0)
        total = len(samples)

        by_designation_output.append({
            "designation": desig,
            "n_samples": total,
            "n_recovered": recovered,
            "n_not_recovered": not_recovered,
            "n_poll_exhausted": poll_exhausted,
            "verdict": (
                "RECOVERED" if recovered >= 1 else
                "POLL_EXHAUSTED" if poll_exhausted >= 1 else
                "NOT_RECOVERED"
            ),
            "samples": sample_rows,
        })

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "params": params,
        "n_designations": len(by_desig),
        "status_counts": dict(status_counts),
        "by_designation": by_designation_output,
    }


def _print_human_readable(result: dict[str, Any]) -> None:
    """Print a human-readable diagnostic table to stdout."""
    print(f"\n=== ATLAS Recovery Diagnostic: {result['run_id']} ===")
    print(f"Run directory : {result['run_dir']}")
    counts = result["status_counts"]
    total = sum(counts.values())
    print(
        f"Samples       : {total} total  "
        + "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    )
    print()

    for entry in result["by_designation"]:
        desig = entry["designation"]
        verdict = entry["verdict"]
        verdict_symbol = (
            "✓" if verdict == "RECOVERED" else ("?" if verdict == "POLL_EXHAUSTED" else "✗")
        )
        print(
            f"[{verdict_symbol}] {desig:12s}  "
            f"recovered={entry['n_recovered']}/{entry['n_samples']}  "
            f"not_recovered={entry['n_not_recovered']}  "
            f"poll_exhausted={entry['n_poll_exhausted']}"
        )

        # Print sample table with header
        has_horizons = any("horizons_ra_deg" in s for s in entry["samples"])
        header_parts = ["  idx", "  JD", "  RA°", "  Dec°", "  status", "n_raw", "n_usable"]
        if has_horizons:
            header_parts += ["  Horizons_RA°", "  Horizons_Dec°", "  Sep(arcsec)"]
        print("  " + "  ".join(header_parts))
        print("  " + "-" * (70 + (40 if has_horizons else 0)))

        for s in entry["samples"]:
            sym = _sample_status_symbol(s["status"])
            parts = [
                f"  {sym}{str(s['sample_index']):3s}",
                f"  {s['jd']:.3f}",
                f"  {s['ra_deg']:.4f}",
                f"  {s['dec_deg']:.4f}",
                f"  {s['status']:<15s}",
                f"  {s['n_raw_observations']:5d}",
                f"  {s['n_usable_observations']:8d}",
            ]
            if has_horizons:
                h_ra = s.get("horizons_ra_deg")
                h_dec = s.get("horizons_dec_deg")
                sep = s.get("sep_from_horizons_arcsec")
                parts += [
                    f"  {h_ra:.4f}" if h_ra is not None else "  N/A",
                    f"  {h_dec:.4f}" if h_dec is not None else "  N/A",
                    f"  {sep:.1f}" if sep is not None else "  N/A",
                ]
            print("".join(parts))
        print()

    # Key findings summary
    unrecovered = [e for e in result["by_designation"] if e["verdict"] != "RECOVERED"]
    if unrecovered:
        print("=== Unrecovered Designations ===")
        for e in unrecovered:
            print(f"  {e['designation']}: {e['verdict']}  "
                  f"(recovered={e['n_recovered']} not_recovered={e['n_not_recovered']} "
                  f"poll_exhausted={e['n_poll_exhausted']})")
        print()
        poll_ex = [e for e in unrecovered if e["n_poll_exhausted"] > 0]
        zero_raw = [e for e in unrecovered if e["verdict"] == "NOT_RECOVERED" and
                    all(s["n_raw_observations"] == 0 for s in e["samples"])]
        if poll_ex:
            print("DIAGNOSIS: Poll-exhausted samples — ATLAS tasks did not finish before"
                  " polling timed out.")
            print("  ACTION: Re-run with the same run directory to resume polling existing"
                  " ATLAS task URLs.")
        if zero_raw:
            desig_names = ", ".join(e["designation"] for e in zero_raw)
            print(f"DIAGNOSIS: {desig_names} — ATLAS returned 0 raw observations at all "
                  "queried positions.")
            print("  This means ATLAS has no coverage at those RA/Dec/JD positions.")
            print("  Possible causes:")
            print("    1. Object was below ATLAS limiting magnitude at those dates.")
            print("    2. ATLAS did not observe those sky positions on those nights.")
            print("    3. The manifest RA/Dec positions do not match the object's actual"
                  " ephemeris.")
            if "--check-horizons" not in sys.argv:
                print("  Run with --check-horizons to compare manifest positions against"
                      " JPL Horizons.")
    else:
        print("All designations have at least one recovered sample.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose an ATLAS recovery run checkpoint"
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Path to the ATLAS recovery run directory (contains checkpoint.json)",
    )
    parser.add_argument(
        "--designation",
        type=str,
        default=None,
        help="Filter output to a single designation (e.g. '2973')",
    )
    parser.add_argument(
        "--check-horizons",
        action="store_true",
        help="Query JPL Horizons for the expected position at each sampled JD and"
             " report angular separation from manifest position (requires network)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable table",
    )
    args = parser.parse_args()

    result = diagnose_run(
        args.run_dir,
        designation_filter=args.designation,
        check_horizons=args.check_horizons,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human_readable(result)


if __name__ == "__main__":
    main()
