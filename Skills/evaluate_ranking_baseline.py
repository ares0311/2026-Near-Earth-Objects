#!/usr/bin/env python
"""Gate Z4 -- "auditable ranking baseline": evaluate a handcrafted-feature
logistic-regression baseline before trusting any LightGBM/XGBoost ranking
for production candidate ranking.

Per docs/ZTF_DR24_PRODUCTION_GATES.md's Gate Z4, this must report
recall@K, purity@K (precision@K), calibration error, false-positive review
burden, and an ablation against a naive single-feature baseline.

This intentionally avoids gambling on which archival night has good data:
- The negative class reuses real archived tracklets already on disk from
  Gate Z6's evidence (the 20220817/20220819 and 20210106/20210111 real
  ZTF alert-archive checkpoints) -- these are confirmed real, and
  confirmed (via adversarial review) to be combinatorial cross-night
  artifacts rather than real single-object NEOs, so labeling them
  negative is legitimate real ground truth, not a guess.
- The positive class uses the project's established synthetic-injection
  generator (the same one behind the committed n=200 injection-recovery
  baseline and Gate P1's positive control) -- known ground truth.

Usage:
    PYTHONPATH=src uv run --python 3.14 python Skills/evaluate_ranking_baseline.py \\
        --n-positive 100 --seed 42 --out Logs/reports/ranking_baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from injection_recovery import inject_synthetic_neo  # noqa: E402
from run_archive_positive_control import load_observations_from_checkpoints  # noqa: E402

from calibration import calibration_report
from classify import extract_features, features_to_vector
from detect import detect
from link import link

_DEFAULT_CHECKPOINT_DIR = Path("Logs/pipeline_runs/ztf_alert_archive_ingest")
_DEFAULT_NEGATIVE_NIGHT_PAIRS = [
    ["20220817", "20220819"],
    ["20210106", "20210111"],
]
_DEFAULT_K_VALUES = (5, 10, 20, 50)


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _load_real_negative_tracklets(checkpoint_dir: Path, night_pairs: list[list[str]]) -> list:
    """Real archived tracklets already confirmed (Gate Z6 evidence) to be
    combinatorial cross-night artifacts, not real single-object NEOs --
    legitimate real negative-class ground truth, no new download needed."""
    from preprocess import preprocess

    tracklets = []
    for nights in night_pairs:
        try:
            observations = load_observations_from_checkpoints(nights, checkpoint_dir)
        except FileNotFoundError as exc:
            print(f"[ranking-baseline] skipping {nights}: {exc}", flush=True)
            continue
        prep = preprocess(tuple(observations), apply_astrometry=False)
        det = detect(prep.sources)
        link_result = link(det.candidates, min_observations=2)
        tracklets.extend(link_result.tracklets)
        print(
            f"[ranking-baseline] {nights}: {len(link_result.tracklets)} real "
            "negative tracklet(s) loaded",
            flush=True,
        )
    return tracklets


def _make_synthetic_positive_tracklets(n_positive: int, seed: int) -> list:
    """Synthetic true-NEO tracklets via the project's established injection
    generator (same one used for the committed n=200 baseline)."""
    rng = np.random.default_rng(seed)
    tracklets = []
    for i in range(n_positive):
        motion = rng.uniform(0.1, 10.0)
        ra0 = rng.uniform(0.0, 359.0)
        dec0 = rng.uniform(-30.0, 30.0)
        mag = rng.uniform(18.0, 21.0)
        obs = inject_synthetic_neo(
            seed=seed * 1000 + i,
            ra0=ra0,
            dec0=dec0,
            motion_arcsec_per_hr=float(motion),
            mag=float(mag),
        )
        det = detect(obs, mpc_cross_match=False)
        if not det.candidates:
            continue
        link_result = link(tuple(det.candidates), min_nights=2, min_observations=3)
        if link_result.tracklets:
            tracklets.append(link_result.tracklets[0])
    return tracklets


def _recall_at_k(labels_sorted: np.ndarray, k: int) -> float:
    """Fraction of all true positives captured in the top-k ranked items."""
    n_pos_total = labels_sorted.sum()
    if n_pos_total == 0:
        return 0.0
    return float(labels_sorted[:k].sum() / n_pos_total)


def _purity_at_k(labels_sorted: np.ndarray, k: int) -> float:
    """Precision@K: fraction of the top-k ranked items that are true positives."""
    if k == 0:
        return 0.0
    return float(labels_sorted[:k].sum() / k)


def _evaluate_ranking(
    name: str, scores: np.ndarray, labels: np.ndarray, k_values: tuple[int, ...]
) -> dict:
    order = np.argsort(-scores)
    labels_sorted = labels[order]
    report = calibration_report(scores, labels)
    report["name"] = name
    report["recall_at_k"] = {
        str(k): _recall_at_k(labels_sorted, k) for k in k_values if k <= len(labels)
    }
    report["purity_at_k"] = {
        str(k): _purity_at_k(labels_sorted, k) for k in k_values if k <= len(labels)
    }
    return report


def run_ranking_baseline(
    n_positive: int = 100,
    seed: int = 42,
    checkpoint_dir: Path = _DEFAULT_CHECKPOINT_DIR,
    night_pairs: list[list[str]] | None = None,
    k_values: tuple[int, ...] = _DEFAULT_K_VALUES,
    n_splits: int = 5,
) -> dict:
    """Evaluate a handcrafted-feature logistic-regression ranking baseline
    via stratified k-fold out-of-fold predictions (never scored on data it
    was fit on), reporting recall@K, purity@K, calibration error, and
    false-positive review burden -- plus an ablation against a naive
    real_bogus-only baseline, per Gate Z4's stated closure requirement."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    night_pairs = night_pairs if night_pairs is not None else _DEFAULT_NEGATIVE_NIGHT_PAIRS
    t0 = time.monotonic()

    negative_tracklets = _load_real_negative_tracklets(checkpoint_dir, night_pairs)
    positive_tracklets = _make_synthetic_positive_tracklets(n_positive, seed)
    print(
        f"[ranking-baseline] {len(positive_tracklets)} synthetic positive(s), "
        f"{len(negative_tracklets)} real negative(s)  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    if not positive_tracklets or not negative_tracklets:
        raise ValueError(
            "Need at least one positive and one negative tracklet to "
            "evaluate a ranking baseline."
        )

    x_rows: list[np.ndarray] = []
    y_rows: list[int] = []
    real_bogus_col: list[float] = []
    for t in positive_tracklets:
        feats = extract_features(t)
        x_rows.append(features_to_vector(feats))
        y_rows.append(1)
        real_bogus_col.append(feats.real_bogus_score or 0.0)
    for t in negative_tracklets:
        feats = extract_features(t)
        x_rows.append(features_to_vector(feats))
        y_rows.append(0)
        real_bogus_col.append(feats.real_bogus_score or 0.0)

    x = np.array(x_rows)
    y = np.array(y_rows)
    real_bogus_scores = np.array(real_bogus_col)

    # Out-of-fold predictions only -- the logistic-regression baseline is
    # never evaluated on data it was fit on.
    n_splits_eff = max(2, min(n_splits, int(y.sum()), int((1 - y).sum())))
    skf = StratifiedKFold(n_splits=n_splits_eff, shuffle=True, random_state=seed)
    oof_scores = np.zeros(len(y))
    for train_idx, test_idx in skf.split(x, y):
        clf = LogisticRegression(max_iter=1000)
        clf.fit(x[train_idx], y[train_idx])
        oof_scores[test_idx] = clf.predict_proba(x[test_idx])[:, 1]

    logreg_report = _evaluate_ranking(
        "logistic_regression_handcrafted", oof_scores, y, k_values
    )
    naive_report = _evaluate_ranking("naive_real_bogus_only", real_bogus_scores, y, k_values)

    threshold = 0.5
    n_flagged = int((oof_scores >= threshold).sum())
    n_flagged_fp = int(((oof_scores >= threshold) & (y == 0)).sum())

    report = {
        "n_positive": len(positive_tracklets),
        "n_negative": len(negative_tracklets),
        "n_splits": n_splits_eff,
        "seed": seed,
        "logistic_regression_handcrafted": logreg_report,
        "naive_real_bogus_only": naive_report,
        "false_positive_review_burden": {
            "threshold": threshold,
            "n_flagged": n_flagged,
            "n_false_positive": n_flagged_fp,
        },
        "elapsed_s": time.monotonic() - t0,
    }
    print(
        f"[ranking-baseline] logreg ECE={logreg_report['ece']} vs "
        f"naive ECE={naive_report['ece']}  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Gate Z4 ranking baseline evaluation")
    parser.add_argument("--n-positive", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--checkpoint-dir", type=Path, default=_DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = run_ranking_baseline(
        n_positive=args.n_positive,
        seed=args.seed,
        checkpoint_dir=args.checkpoint_dir,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"Report written to {args.out}")
    else:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
