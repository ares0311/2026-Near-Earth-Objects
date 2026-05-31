"""Batch orbital speed at perihelion computation from tracklet JSON file."""
import argparse
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from orbit import compute_orbital_speed_at_perihelion


def _elements_from_tracklet(t: dict) -> SimpleNamespace:
    orb = t.get("orbit", t)
    return SimpleNamespace(
        a_au=orb.get("a_au", orb.get("semi_major_axis_au")),
        semi_major_axis_au=orb.get("semi_major_axis_au", orb.get("a_au")),
        e=orb.get("e", orb.get("eccentricity")),
        eccentricity=orb.get("eccentricity", orb.get("e")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute orbital speed at perihelion per tracklet")
    parser.add_argument("input", help="Path to tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    with open(args.input) as fh:
        data = json.load(fh)

    tracklets = data if isinstance(data, list) else data.get("tracklets", [data])

    results = []
    for t in tracklets:
        elements = _elements_from_tracklet(t)
        speed = compute_orbital_speed_at_perihelion(elements)
        results.append(
            {
                "object_id": t.get("object_id", "unknown"),
                "perihelion_speed_km_s": speed,
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<30} {'Speed (km/s)':>14}")
        print("-" * 46)
        for r in results:
            spd = r["perihelion_speed_km_s"]
            spd_str = f"{spd:.2f}" if spd is not None else "N/A"
            print(f"{r['object_id']:<30} {spd_str:>14}")


if __name__ == "__main__":
    main()
