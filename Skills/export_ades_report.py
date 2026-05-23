"""Export ADES PSV observation reports from scored NEO JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export MPC ADES pipe-separated-values (PSV) reports "
            "for scored NEO candidates."
        )
    )
    parser.add_argument("input", help="Path to JSON file (list of ScoredNEO dicts).")
    parser.add_argument(
        "--obs-code",
        default="Xnn",
        metavar="CODE",
        help="MPC observatory code (default: Xnn).",
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="FILE",
        help="Write combined PSV report to FILE (default: stdout).",
    )
    parser.add_argument("--json", action="store_true",
                        help="Output JSON list of {object_id, psv} dicts.")
    args = parser.parse_args()

    try:
        with open(args.input) as fh:
            data = json.load(fh)
    except Exception as exc:
        print(f"ERROR: could not read {args.input}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        data = [data]

    sys.path.insert(0, "src")
    try:
        from alert import format_mpc_ades_psv
    except ImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    from types import SimpleNamespace

    results = []
    for item in data:
        object_id = (
            item.get("tracklet", {}).get("object_id")
            or item.get("object_id", "unknown")
        )

        obs_list_raw = item.get("tracklet", {}).get("observations") or []
        obs_ns_list = []
        for o in obs_list_raw:
            obs_ns_list.append(SimpleNamespace(
                jd=float(o.get("jd", 2460000.5)),
                ra_deg=float(o.get("ra_deg", 0.0)),
                dec_deg=float(o.get("dec_deg", 0.0)),
                mag=float(o.get("mag", 99.0)),
                mag_err=float(o.get("mag_err", 0.1)),
                filter_band=str(o.get("filter_band", "r")),
                mission=str(o.get("mission", "ZTF")),
            ))

        tracklet_ns = SimpleNamespace(
            object_id=object_id,
            observations=sorted(obs_ns_list, key=lambda o: o.jd),
        )

        hazard = item.get("hazard", {})
        hazard_ns = SimpleNamespace(
            hazard_flag=hazard.get("hazard_flag", "unknown"),
            moid_au=hazard.get("moid_au"),
            neo_class=hazard.get("neo_class", "unknown"),
            alert_pathway=hazard.get("alert_pathway", "internal_candidate"),
        )

        neo_ns = SimpleNamespace(tracklet=tracklet_ns, hazard=hazard_ns)

        try:
            psv = format_mpc_ades_psv(neo_ns, obs_code=args.obs_code)
        except Exception as exc:
            print(f"WARNING: could not format {object_id}: {exc}", file=sys.stderr)
            psv = ""

        results.append({"object_id": object_id, "psv": psv})

    if args.json:
        output = json.dumps(results, indent=2)
    else:
        sections = []
        for r in results:
            sections.append(f"# --- {r['object_id']} ---\n{r['psv']}")
        output = "\n\n".join(sections)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Wrote {len(results)} report(s) to {args.out}")
    else:
        print(output)

    print(f"\n{len(results)} report(s).", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
