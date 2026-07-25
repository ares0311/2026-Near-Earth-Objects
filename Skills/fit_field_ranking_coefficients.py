#!/usr/bin/env python
"""Attempt a real, per-mode field-ranking coefficient fit against real data.

Operator decision (2026-07-25): now that both aten and ieo modes clear
Skills/evaluate_field_ranking_policy.py's MINIMUM_SAMPLE_THRESHOLDS
(coefficient_promotion_gate.coefficient_update_authorized == True),
attempt a real coefficient fit rather than leaving the deterministic
uncalibrated_transparent_prior policy untouched forever.

This script fits a per-mode logistic regression on the same three
features the current hand-set policy already scores
(survey_scarcity_score, population_score, geometry_score) against real
outcome (positive discovery vs. searched null), using every eligible
real record from Skills/evaluate_field_ranking_policy.py's own retrospective
audit -- no separate data loading, no re-derivation.

Because the real samples are still small (ieo: 7 positive + 7 null = 14
total), this uses leave-one-out cross-validation (refitting on n-1 points
and predicting the held-out one, for every point) rather than k-fold,
which would leave near-empty folds. Coefficient stability is checked via
bootstrap resampling. A fit is only reported as a "promotion candidate"
if its honest out-of-fold AUC clearly and stably beats the current
hand-set policy's own AUC on the same data -- otherwise the reason is
stated explicitly.

This script NEVER writes to the production ranking policy file
(data_selection/ranking_policies/ztf_field_ranking_v2.json). It only
produces a report. Promoting a fit into the active policy is a separate,
later, explicitly operator-reviewed step -- this project's existing CNN
promotion workflow (Skills/build_promotion_report.py) is the template for
that step once/if a fit here is worth promoting.

Usage::

    uv run python Skills/fit_field_ranking_coefficients.py \\
        --out Logs/pipeline_runs/field_ranking_calibration/coefficient_fit_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import evaluate_field_ranking_policy as ranking_audit  # noqa: E402

from calibration import brier_score, compute_roc_auc  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "field-ranking-coefficient-fit-report-v1"
FEATURE_NAMES = ("survey_scarcity_score", "population_score", "geometry_score")
# A fit must clear this margin over the baseline (not just be numerically
# larger) to count as a promotion candidate -- guards against reporting
# noise as improvement on these still-small samples.
MINIMUM_AUC_IMPROVEMENT = 0.02
# At least this fraction of bootstrap resamples must produce a fittable
# model (both classes present) for the stability estimate itself to be
# trusted; below this, the sample is too small/imbalanced to say anything
# about coefficient stability.
MINIMUM_BOOTSTRAP_SUCCESS_FRACTION = 0.8


def _leave_one_out_probabilities(X: np.ndarray, y: np.ndarray, C: float) -> np.ndarray | None:
    """Real leave-one-out CV: refit on n-1 points, predict the held-out one.

    Returns None if there are too few points or only one class present
    overall (a fit is not meaningful in either case).
    """
    from sklearn.linear_model import LogisticRegression

    n = len(y)
    if n < 4 or len(set(y.tolist())) < 2:
        return None

    out_of_fold = np.zeros(n)
    for i in range(n):
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        y_train = y[mask]
        if len(set(y_train.tolist())) < 2:
            # Leaving this point out removes the only example of one
            # class from the training fold -- cannot fit; fail closed to
            # a neutral 0.5 rather than a fabricated confident guess.
            out_of_fold[i] = 0.5
            continue
        clf = LogisticRegression(max_iter=1000, solver="lbfgs", C=C)
        clf.fit(X[mask], y_train)
        out_of_fold[i] = clf.predict_proba(X[i : i + 1])[0, 1]
    return out_of_fold


def _bootstrap_coefficient_stability(
    X: np.ndarray, y: np.ndarray, C: float, n_bootstrap: int, seed: int
) -> dict[str, Any] | None:
    """Bootstrap-resample (with replacement) and refit; report each
    coefficient's median and 95% CI to check sign/magnitude stability.

    Returns None if fewer than MINIMUM_BOOTSTRAP_SUCCESS_FRACTION of
    resamples could be fit (e.g. a resample drew only one class).
    """
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(seed)
    n = len(y)
    coefficients: list[np.ndarray] = []
    intercepts: list[float] = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        y_boot = y[idx]
        if len(set(y_boot.tolist())) < 2:
            continue
        clf = LogisticRegression(max_iter=1000, solver="lbfgs", C=C)
        clf.fit(X[idx], y_boot)
        coefficients.append(clf.coef_[0])
        intercepts.append(float(clf.intercept_[0]))

    success_fraction = len(coefficients) / n_bootstrap
    if success_fraction < MINIMUM_BOOTSTRAP_SUCCESS_FRACTION:
        return None

    arr = np.array(coefficients)
    return {
        "n_bootstrap": n_bootstrap,
        "n_successful_resamples": len(coefficients),
        "success_fraction": round(success_fraction, 4),
        "median": {
            name: round(float(np.median(arr[:, i])), 6) for i, name in enumerate(FEATURE_NAMES)
        },
        "ci_lower_95": {
            name: round(float(np.percentile(arr[:, i], 2.5)), 6)
            for i, name in enumerate(FEATURE_NAMES)
        },
        "ci_upper_95": {
            name: round(float(np.percentile(arr[:, i], 97.5)), 6)
            for i, name in enumerate(FEATURE_NAMES)
        },
        "intercept_median": round(float(np.median(intercepts)), 6),
    }


def fit_mode_coefficients(
    mode_records: list[dict[str, Any]],
    regularization_c: float = 1.0,
    n_bootstrap: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Attempt one mode's real coefficient fit; always report, never raise
    on an insufficient/degenerate sample -- that is a legitimate, expected
    outcome for a small real sample, not an error."""
    from sklearn.linear_model import LogisticRegression

    eligible = [row for row in mode_records if row["features"]["eligible"]]
    n_positive = sum(1 for row in eligible if row["outcome"] == "positive")
    n_null = sum(1 for row in eligible if row["outcome"] == "null_result")

    if not eligible or len(set(row["outcome"] for row in eligible)) < 2:
        return {
            "status": "insufficient_sample",
            "reason": "fewer than two outcome classes among eligible records",
            "n_positive": n_positive,
            "n_null": n_null,
            "promotion_candidate": False,
        }

    X = np.array([[row["features"][name] for name in FEATURE_NAMES] for row in eligible])
    y = np.array([1 if row["outcome"] == "positive" else 0 for row in eligible])
    baseline_scores = np.array([row["features"]["score"] for row in eligible])
    baseline_auc = compute_roc_auc(baseline_scores, y)

    out_of_fold = _leave_one_out_probabilities(X, y, regularization_c)
    if out_of_fold is None:
        return {
            "status": "insufficient_sample",
            "reason": "fewer than 4 eligible records or only one outcome class overall",
            "n_positive": n_positive,
            "n_null": n_null,
            "baseline_policy_auc": round(float(baseline_auc), 6),
            "promotion_candidate": False,
        }

    fit_auc = compute_roc_auc(out_of_fold, y)
    fit_brier = brier_score(out_of_fold, y.astype(float))
    stability = _bootstrap_coefficient_stability(X, y, regularization_c, n_bootstrap, seed)

    # Final fit on all eligible data, for reporting coefficients only --
    # the honest performance estimate is the out-of-fold AUC above, not
    # this in-sample fit.
    full_fit = LogisticRegression(max_iter=1000, solver="lbfgs", C=regularization_c)
    full_fit.fit(X, y)

    auc_improvement = float(fit_auc) - float(baseline_auc)
    promotion_candidate = (
        auc_improvement >= MINIMUM_AUC_IMPROVEMENT and stability is not None
    )
    if promotion_candidate:
        reason = (
            "leave-one-out AUC clears the baseline by >= the required margin "
            "with stable bootstrap coefficients"
        )
    elif stability is None:
        reason = (
            "bootstrap coefficient stability could not be established at the "
            "required success rate"
        )
    else:
        reason = (
            f"leave-one-out AUC improvement ({auc_improvement:.4f}) is below the "
            f"required margin ({MINIMUM_AUC_IMPROVEMENT})"
        )

    return {
        "status": "fit_complete",
        "n_positive": n_positive,
        "n_null": n_null,
        "feature_names": list(FEATURE_NAMES),
        "fitted_coefficients": {
            name: round(float(full_fit.coef_[0][i]), 6) for i, name in enumerate(FEATURE_NAMES)
        },
        "fitted_intercept": round(float(full_fit.intercept_[0]), 6),
        "leave_one_out_auc": round(float(fit_auc), 6),
        "leave_one_out_brier": round(float(fit_brier), 6),
        "baseline_policy_auc": round(float(baseline_auc), 6),
        "auc_improvement": round(auc_improvement, 6),
        "coefficient_bootstrap_stability": stability,
        "promotion_candidate": promotion_candidate,
        "promotion_candidate_reason": reason,
    }


def build_fit_report(
    positive_paths: tuple[Path, ...],
    null_path: Path,
    policy_path: Path,
    regularization_c: float = 1.0,
    n_bootstrap: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """Build the full fit-attempt report for every mode that is authorized.

    Reuses evaluate_field_ranking_policy.build_policy_audit()'s own
    records (already scored with the real, current policy) rather than
    re-deriving features -- one source of truth for what "the real data"
    is. Restricted to source_aligned_ztf_i41 records, matching the
    coefficient_promotion_gate's own counting: a non-I41-attributed MPC
    discovery establishes real geometry but was not necessarily
    ZTF-findable, so it is not a meaningful fitting example for "would
    ZTF's own ranking have found what ZTF itself actually found."
    """
    audit_result = ranking_audit.build_policy_audit(positive_paths, null_path, policy_path)
    gate = audit_result["coefficient_promotion_gate"]
    records = [row for row in audit_result["records"] if row["source_aligned_ztf_i41"]]

    per_mode: dict[str, Any] = {}
    for mode in ("aten", "ieo"):
        if not (
            gate["observed_counts"][mode]["positive"]
            >= gate["minimum_thresholds"][mode]["positive"]
            and gate["observed_counts"][mode]["searched_null"]
            >= gate["minimum_thresholds"][mode]["searched_null"]
        ):
            per_mode[mode] = {
                "status": "not_authorized",
                "reason": "does not clear this mode's minimum sample thresholds",
                "observed_counts": gate["observed_counts"][mode],
                "minimum_thresholds": gate["minimum_thresholds"][mode],
                "promotion_candidate": False,
            }
            continue
        mode_records = [row for row in records if row["ranking_mode"] == mode]
        per_mode[mode] = fit_mode_coefficients(
            mode_records, regularization_c=regularization_c, n_bootstrap=n_bootstrap, seed=seed
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "fit_attempt_complete",
        "audit_sources": audit_result["sources"],
        "regularization_c": regularization_c,
        "n_bootstrap": n_bootstrap,
        "seed": seed,
        "per_mode": per_mode,
        "any_promotion_candidate": any(
            result.get("promotion_candidate") for result in per_mode.values()
        ),
        "note": (
            "This report never modifies the production ranking policy file. "
            "A promotion_candidate=true result is a recommendation to review, "
            "not an automatic promotion -- see docs/PRODUCTION_READINESS.md "
            "for the required next step before any policy file is changed."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--positive", type=Path, nargs="+", default=list(ranking_audit.DEFAULT_POSITIVES)
    )
    parser.add_argument("--nulls", type=Path, default=ranking_audit.DEFAULT_NULLS)
    parser.add_argument("--policy", type=Path, default=ranking_audit.DEFAULT_POLICY)
    parser.add_argument("--regularization-c", type=float, default=1.0)
    parser.add_argument("--n-bootstrap", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = build_fit_report(
        tuple(args.positive),
        args.nulls,
        args.policy,
        regularization_c=args.regularization_c,
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
