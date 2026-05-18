#!/usr/bin/env python3
"""Plot a reliability (calibration) diagram from scored NEO JSON or raw prob/label data."""

from __future__ import annotations

import argparse
import json
import sys


def _load_from_scored_neos(path: str) -> tuple[list[float], list[float]]:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]
    probs, labels = [], []
    for d in data:
        p = d.get("posterior", {}).get("neo_candidate")
        hazard = d.get("hazard", {})
        flag = hazard.get("hazard_flag", "unknown")
        label = 1.0 if flag in ("pha_candidate", "close_approach") else 0.0
        if p is not None:
            probs.append(float(p))
            labels.append(label)
    return probs, labels


def _load_from_prob_label_json(path: str) -> tuple[list[float], list[float]]:
    """Expect JSON: [{"prob": 0.8, "label": 1}, ...]"""
    with open(path) as f:
        data = json.load(f)
    probs = [float(d["prob"]) for d in data]
    labels = [float(d["label"]) for d in data]
    return probs, labels


def plot_calibration(input_path: str, output_path: str, n_bins: int = 10) -> int:
    sys.path.insert(0, "src")
    from calibration import calibration_report, reliability_diagram  # type: ignore[import]

    # Try scored NEO format first, fall back to prob/label format
    try:
        probs, labels = _load_from_scored_neos(input_path)
        if not probs:
            raise ValueError("no data")
    except Exception:
        try:
            probs, labels = _load_from_prob_label_json(input_path)
        except Exception:
            print(f"ERROR: Could not parse {input_path} as scored NEO JSON or prob/label JSON.")
            return 1


    rd = reliability_diagram(probs, labels, n_bins=n_bins)
    report = calibration_report(probs, labels)

    try:
        import matplotlib.pyplot as plt  # type: ignore[import]

        fig, ax = plt.subplots(figsize=(6, 6))
        ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration", alpha=0.5)
        ax.plot(rd["bin_centers"], rd["fraction_positive"], "o-", label="Model")
        ax.set_xlabel("Mean predicted probability")
        ax.set_ylabel("Fraction positive")
        ax.set_title(
            f"Reliability Diagram\n"
            f"Brier={report['brier_score']:.4f}  ECE={report['ece']:.4f}"
            f"  n={report['n_samples']}"
        )
        ax.legend()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        fig.tight_layout()
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
        print(f"Reliability diagram saved to: {output_path}")
    except ImportError:
        print("WARNING: matplotlib not available; printing data only.")

    print(f"Brier score:          {report['brier_score']}")
    print(f"ECE:                  {report['ece']}")
    print(f"Log loss:             {report['log_loss']}")
    print(f"N samples:            {report['n_samples']}")
    print(f"Mean predicted prob:  {report['mean_prob']}")
    print(f"Fraction positive:    {report['fraction_positive']}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot reliability diagram from scored NEO JSON or prob/label JSON."
    )
    parser.add_argument("input", help="Path to scored NEO or prob/label JSON file")
    parser.add_argument(
        "--output",
        default="calibration_diagram.png",
        help="Output PNG path (default: calibration_diagram.png)",
    )
    parser.add_argument("--bins", type=int, default=10, help="Number of bins (default: 10)")
    args = parser.parse_args()

    sys.exit(plot_calibration(args.input, args.output, n_bins=args.bins))


if __name__ == "__main__":
    main()
