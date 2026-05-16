"""Bulk export MPC 80-column observation reports for a list of ScoredNEOs.

Usage:
    python Skills/export_mpc_bulk.py <scored_neos.json>
        [--out-dir PATH] [--obs-code XXX] [--min-priority 0.3]
        [--pathways mpc_submission neocp_followup]

Reads a list of ScoredNEO-compatible dicts, filters by alert pathway and
minimum priority, and writes one MPC 80-column report file per object into
the output directory.  Also writes a manifest JSON summarising all exports.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alert import format_mpc_report  # noqa: E402
from schemas import ScoredNEO  # noqa: E402

_DEFAULT_OBS_CODE = "500"  # geocentric placeholder; override with real observatory code
_DEFAULT_PATHWAYS = {"mpc_submission", "neocp_followup", "nasa_pdco_notify"}
_MIN_PRIORITY_DEFAULT = 0.3


def _safe_filename(object_id: str) -> str:
    """Convert an object_id to a safe filename component."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in object_id)


def export_bulk(
    neos: list[ScoredNEO],
    out_dir: Path,
    obs_code: str = _DEFAULT_OBS_CODE,
    min_priority: float = _MIN_PRIORITY_DEFAULT,
    allowed_pathways: set[str] | None = None,
) -> dict:
    """Export MPC 80-column reports for qualifying ScoredNEOs to *out_dir*.

    Args:
        neos:              List of :class:`ScoredNEO` objects to export.
        out_dir:           Directory to write report files into (created if absent).
        obs_code:          MPC observatory code (3 characters).
        min_priority:      Minimum ``discovery_priority`` to include.
        allowed_pathways:  Set of ``alert_pathway`` strings to include.
                           Defaults to ``{mpc_submission, neocp_followup,
                           nasa_pdco_notify}``.

    Returns:
        Manifest dict with keys ``n_exported``, ``n_skipped``,
        ``out_dir``, and ``files`` (list of per-object export records).
    """
    if allowed_pathways is None:
        allowed_pathways = _DEFAULT_PATHWAYS

    out_dir.mkdir(parents=True, exist_ok=True)

    exported: list[dict] = []
    skipped: list[dict] = []

    for neo in neos:
        priority = neo.metadata.discovery_priority
        pathway = neo.hazard.alert_pathway

        if priority < min_priority:
            skipped.append({
                "object_id": neo.tracklet.object_id,
                "reason": f"priority {priority:.4f} < threshold {min_priority}",
            })
            continue

        if pathway not in allowed_pathways:
            skipped.append({
                "object_id": neo.tracklet.object_id,
                "reason": f"pathway '{pathway}' not in allowed set",
            })
            continue

        report = format_mpc_report(neo, obs_code=obs_code)
        fname = _safe_filename(neo.tracklet.object_id) + "_mpc.txt"
        fpath = out_dir / fname
        fpath.write_text(report)

        exported.append({
            "object_id": neo.tracklet.object_id,
            "file": str(fpath),
            "pathway": pathway,
            "hazard_flag": neo.hazard.hazard_flag,
            "discovery_priority": round(priority, 4),
            "n_observations": len(neo.tracklet.observations),
        })

    manifest = {
        "n_exported": len(exported),
        "n_skipped": len(skipped),
        "out_dir": str(out_dir),
        "files": exported,
        "skipped": skipped,
    }

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Bulk export MPC 80-column reports for scored NEOs."
    )
    parser.add_argument("input", help="Scored NEOs JSON file")
    parser.add_argument("--out-dir", default="mpc_reports",
                        help="Output directory for report files (default: mpc_reports)")
    parser.add_argument("--obs-code", default=_DEFAULT_OBS_CODE,
                        help="MPC observatory code (default: 500)")
    parser.add_argument("--min-priority", type=float, default=_MIN_PRIORITY_DEFAULT,
                        help="Minimum discovery priority to export")
    parser.add_argument("--pathways", nargs="+",
                        default=list(_DEFAULT_PATHWAYS),
                        help="Alert pathways to include")
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input).read_text())
    neos = [ScoredNEO(**item) for item in data]
    allowed = set(args.pathways)

    out_dir = Path(args.out_dir)
    manifest = export_bulk(
        neos,
        out_dir=out_dir,
        obs_code=args.obs_code,
        min_priority=args.min_priority,
        allowed_pathways=allowed,
    )

    print(f"Exported {manifest['n_exported']} report(s) to {out_dir}/")
    print(f"Skipped  {manifest['n_skipped']} object(s).")
    print(f"Manifest written to {out_dir}/manifest.json")

    if manifest["n_skipped"] and "--verbose" in (argv or []):
        for s in manifest["skipped"]:
            print(f"  SKIP {s['object_id']}: {s['reason']}")

    sys.exit(0)


if __name__ == "__main__":
    main()
