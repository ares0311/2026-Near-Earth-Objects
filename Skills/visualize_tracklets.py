"""Visualize tracklet sky positions and motion vectors.

Usage:
    PYTHONPATH=src python Skills/visualize_tracklets.py data/sample_tracklets.json

Requires: matplotlib
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schemas import Observation, Tracklet


def _load_tracklets(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _parse_tracklet(raw: dict) -> Tracklet:
    obs = tuple(
        Observation(**o) for o in raw["observations"]
    )
    return Tracklet(
        object_id=raw["object_id"],
        observations=obs,
        arc_days=raw["arc_days"],
        motion_rate_arcsec_per_hour=raw["motion_rate_arcsec_per_hour"],
        motion_pa_degrees=raw["motion_pa_degrees"],
    )


def visualize(path: str, output: str | None = None) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("ERROR: matplotlib not installed. Run: pip install matplotlib")
        sys.exit(1)

    data = _load_tracklets(path)
    tracklets = [_parse_tracklet(t) for t in data]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax_sky = axes[0]
    ax_motion = axes[1]

    colors = plt.cm.tab10.colors  # type: ignore[attr-defined]

    for idx, t in enumerate(tracklets):
        color = colors[idx % len(colors)]
        ras = [o.ra_deg for o in t.observations]
        decs = [o.dec_deg for o in t.observations]
        jds = [o.jd for o in t.observations]

        ax_sky.plot(ras, decs, "o-", color=color, label=t.object_id, linewidth=1.5, markersize=5)
        ax_sky.annotate(
            t.object_id,
            (ras[0], decs[0]),
            textcoords="offset points",
            xytext=(5, 5),
            fontsize=8,
            color=color,
        )

        dt_hr = [(j - jds[0]) * 24 for j in jds]
        mags = [o.mag for o in t.observations if o.mag is not None]
        if len(mags) == len(jds):
            ax_motion.plot(
                dt_hr, mags, "s-", color=color, label=t.object_id, linewidth=1.5, markersize=5
            )

    ax_sky.set_xlabel("RA (deg)")
    ax_sky.set_ylabel("Dec (deg)")
    ax_sky.set_title("Sky Positions")
    ax_sky.invert_xaxis()
    ax_sky.legend(fontsize=8)
    ax_sky.grid(True, alpha=0.3)

    ax_motion.set_xlabel("Time since first obs (hr)")
    ax_motion.set_ylabel("Magnitude")
    ax_motion.set_title("Light Curves")
    ax_motion.invert_yaxis()
    ax_motion.legend(fontsize=8)
    ax_motion.grid(True, alpha=0.3)

    plt.tight_layout()
    if output:
        plt.savefig(output, dpi=150)
        print(f"Saved: {output}")
    else:
        plt.show()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Skills/visualize_tracklets.py <tracklets.json> [output.png]")
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else None
    visualize(sys.argv[1], out)
