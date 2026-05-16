"""Plot sky coverage of a scored NEO run (RA/Dec scatter).

Requires matplotlib.  Saves a PNG to disk or shows interactively.

Usage:
    python Skills/plot_sky_coverage.py data/sample_tracklets.json \\
        [--out sky_coverage.png] [--title "My Run"]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def plot_sky_coverage(
    neos: list[dict],
    title: str = "Sky Coverage",
    out: str | None = None,
) -> None:
    """Plot RA/Dec positions of tracklet observations colour-coded by hazard flag."""
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("matplotlib not installed. Run: pip install matplotlib") from exc

    colour_map = {
        "pha_candidate": "red",
        "close_approach": "orange",
        "nominal": "steelblue",
        "unknown": "gray",
    }

    fig, ax = plt.subplots(figsize=(12, 6))

    by_flag: dict[str, tuple[list[float], list[float]]] = {}

    for neo in neos:
        hazard = neo.get("hazard", {})
        flag = hazard.get("hazard_flag", "unknown")
        tracklet = neo.get("tracklet", {})
        observations = tracklet.get("observations", [])
        if not observations:
            continue
        ra_vals = [obs.get("ra_deg", 0.0) for obs in observations]
        dec_vals = [obs.get("dec_deg", 0.0) for obs in observations]
        if flag not in by_flag:
            by_flag[flag] = ([], [])
        by_flag[flag][0].extend(ra_vals)
        by_flag[flag][1].extend(dec_vals)

    for flag, (ras, decs) in by_flag.items():
        colour = colour_map.get(flag, "gray")
        ax.scatter(ras, decs, c=colour, s=10, alpha=0.7, label=flag)

    ax.set_xlabel("RA (deg)")
    ax.set_ylabel("Dec (deg)")
    ax.set_title(title)
    ax.set_xlim(0, 360)
    ax.set_ylim(-90, 90)
    ax.invert_xaxis()
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    if out:
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved sky coverage plot to {out}")
    else:
        plt.show()

    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot sky coverage of scored NEO run")
    parser.add_argument("input", help="JSON file with list of ScoredNEO dicts")
    parser.add_argument("--out", help="output PNG file (default: show interactively)")
    parser.add_argument("--title", default="Sky Coverage", help="plot title")
    args = parser.parse_args()

    data_path = Path(args.input)
    if not data_path.exists():
        print(f"ERROR: {data_path} not found", file=sys.stderr)
        sys.exit(1)

    with data_path.open() as f:
        neos = json.load(f)

    if not isinstance(neos, list):
        print("ERROR: JSON file must contain a list of ScoredNEO dicts", file=sys.stderr)
        sys.exit(1)

    plot_sky_coverage(neos, title=args.title, out=args.out)


if __name__ == "__main__":
    main()
