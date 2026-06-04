"""Batch alert urgency scores from scored NEO JSON.

Usage:
    python Skills/compute_alert_urgency_scores.py scored_neos.json [--threshold 0.5] [--json]

Reads a JSON file of ScoredNEO-like dicts and prints a table of urgency scores,
optionally filtered by a minimum threshold.
"""
import json
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from score import compute_alert_urgency_score


def _load_neo(d: dict) -> SimpleNamespace:
    hazard_d = d.get("hazard", {})
    hazard = SimpleNamespace(**hazard_d) if isinstance(hazard_d, dict) else SimpleNamespace()
    meta_d = d.get("metadata", {})
    meta = SimpleNamespace(**meta_d) if isinstance(meta_d, dict) else SimpleNamespace()
    feat_d = d.get("features", {})
    feat = SimpleNamespace(**feat_d) if isinstance(feat_d, dict) else SimpleNamespace()
    tracklet_d = d.get("tracklet", {})
    tracklet = SimpleNamespace(**tracklet_d) if isinstance(tracklet_d, dict) else SimpleNamespace()
    return SimpleNamespace(
        tracklet=tracklet,
        hazard=hazard,
        metadata=meta,
        features=feat,
    )


def main(argv: list[str]) -> None:
    as_json = "--json" in argv
    threshold = 0.0
    paths = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--threshold" and i + 1 < len(argv):
            threshold = float(argv[i + 1])
            i += 2
        elif arg.startswith("--"):
            i += 1
        else:
            paths.append(arg)
            i += 1

    if not paths:
        print(
            "Usage: compute_alert_urgency_scores.py <scored_neos.json> "
            "[--threshold T] [--json]",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(paths[0]) as fh:
        data = json.load(fh)
    records = data if isinstance(data, list) else [data]

    results = []
    for r in records:
        neo = _load_neo(r)
        obj_id = getattr(neo.tracklet, "object_id", "unknown")
        score = compute_alert_urgency_score(neo)
        if score >= threshold:
            results.append({"object_id": obj_id, "urgency_score": round(score, 4)})

    results.sort(key=lambda x: x["urgency_score"], reverse=True)

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Object ID':<20}  Urgency Score")
        print("-" * 35)
        for row in results:
            print(f"{row['object_id']:<20}  {row['urgency_score']:.4f}")


if __name__ == "__main__":
    main(sys.argv[1:])
