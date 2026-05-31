"""Batch novelty ranking for scored NEO candidates.

Usage:
    python Skills/compute_novelty_ranks.py data/sample_tracklets.json
    python Skills/compute_novelty_ranks.py data/sample_tracklets.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "src")

from score import compute_novelty_rank


class _Meta:
    def __init__(self, novelty_score: float | None) -> None:
        self.novelty_score = novelty_score


class _Tracklet:
    def __init__(self, object_id: str) -> None:
        self.object_id = object_id


class _Neo:
    def __init__(self, object_id: str, novelty_score: float | None) -> None:
        self.tracklet = _Tracklet(object_id)
        self.metadata = _Meta(novelty_score)


def _load_neos(path: str) -> list[dict]:
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    return data.get("tracklets", [])


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch novelty ranking")
    parser.add_argument("input", help="Path to scored NEO or tracklet JSON file")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    records = _load_neos(args.input)
    neos = []
    for rec in records:
        oid = rec.get("object_id", rec.get("tracklet", {}).get("object_id", "unknown"))
        novelty = rec.get("novelty_score") or rec.get("metadata", {}).get("novelty_score")
        neos.append(_Neo(oid, float(novelty) if novelty is not None else None))

    rankings = compute_novelty_rank(neos)

    if args.json:
        print(json.dumps([{"rank": r, "object_id": oid} for r, oid in rankings], indent=2))
    else:
        print(f"{'Rank':>6} {'Object ID':<40}")
        print("-" * 50)
        for rank, oid in rankings:
            print(f"{rank:>6} {oid:<40}")


if __name__ == "__main__":
    main()
