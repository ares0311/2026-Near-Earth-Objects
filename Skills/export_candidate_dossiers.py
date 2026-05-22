"""Export one plain-text candidate dossier per NEO from a ScoredNEO JSON file.

Usage:
    python Skills/export_candidate_dossiers.py scored_neos.json [--out-dir OUTPUT_DIR] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export per-candidate dossiers from scored NEO JSON."
    )
    parser.add_argument("input", help="Path to scored NEO JSON file.")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to write dossier files (default: print to stdout).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output a JSON summary instead of plain text dossiers.",
    )
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text())
    if not isinstance(data, list):
        data = [data]

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from alert import format_candidate_dossier
    from tests.conftest import build_scored_neo  # noqa: F401 — only for type hint

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for item in data:
        obj_id = (
            item.get("object_id")
            or (item.get("tracklet") or {}).get("object_id", "unknown")
        )
        try:
            # Reconstruct a minimal ScoredNEO-like object for format_candidate_dossier
            import types

            def _make_obj(**kw):
                o = types.SimpleNamespace(**kw)
                return o

            haz = _make_obj(
                hazard_flag=item.get("hazard", {}).get("hazard_flag", "unknown"),
                alert_pathway=item.get("hazard", {}).get("alert_pathway", "internal_candidate"),
                neo_class=item.get("hazard", {}).get("neo_class", "unknown"),
                moid_au=item.get("hazard", {}).get("moid_au"),
                absolute_magnitude_h=item.get("hazard", {}).get("absolute_magnitude_h"),
                estimated_diameter_m=item.get("hazard", {}).get("estimated_diameter_m"),
                explanation="",
            )
            post_data = item.get("posterior", {})
            post = _make_obj(
                neo_candidate=post_data.get("neo_candidate", 0.0),
                known_object=post_data.get("known_object", 0.0),
                main_belt_asteroid=post_data.get("main_belt_asteroid", 0.0),
                stellar_artifact=post_data.get("stellar_artifact", 0.0),
                other_solar_system=post_data.get("other_solar_system", 0.0),
            )
            meta_data = item.get("metadata", {})
            meta = _make_obj(discovery_priority=meta_data.get("discovery_priority", 0.0))
            track_data = item.get("tracklet", {})
            obs_list = track_data.get("observations", [])
            track = _make_obj(
                object_id=obj_id,
                arc_days=track_data.get("arc_days", 0.0),
                motion_rate_arcsec_per_hour=track_data.get("motion_rate_arcsec_per_hour", 0.0),
                observations=obs_list,
            )
            feat = _make_obj()
            neo = _make_obj(hazard=haz, posterior=post, metadata=meta,
                            tracklet=track, features=feat)

            dossier = format_candidate_dossier(neo)  # type: ignore[arg-type]
        except Exception as exc:
            dossier = f"ERROR generating dossier for {obj_id}: {exc}"

        if args.json:
            summary.append({"object_id": obj_id, "dossier_lines": dossier.count("\n") + 1})
        elif out_dir:
            out_file = out_dir / f"{obj_id}.txt"
            out_file.write_text(dossier)
            print(f"Written: {out_file}")
        else:
            print(dossier)
            print()

    if args.json:
        print(json.dumps(summary, indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
