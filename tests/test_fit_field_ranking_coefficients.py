"""Behavioral tests for the real per-mode field-ranking coefficient fit."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "Skills"))

import fit_field_ranking_coefficients as fitter  # noqa: E402


def _record(
    outcome: str,
    scarcity: float,
    population: float,
    geometry: float,
    score: float = 0.5,
    eligible: bool = True,
    mode: str = "aten",
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "ranking_mode": mode,
        "features": {
            "survey_scarcity_score": scarcity,
            "population_score": population,
            "geometry_score": geometry,
            "eligible": eligible,
            "score": score,
        },
    }


def test_fit_mode_coefficients_insufficient_sample_when_one_class_only() -> None:
    records = [_record("positive", 0.9, 0.9, 0.9) for _ in range(6)]

    result = fitter.fit_mode_coefficients(records)

    assert result["status"] == "insufficient_sample"
    assert result["promotion_candidate"] is False


def test_fit_mode_coefficients_insufficient_sample_when_too_few_eligible() -> None:
    records = [
        _record("positive", 0.9, 0.9, 0.9),
        _record("positive", 0.8, 0.8, 0.8),
        _record("null_result", 0.1, 0.1, 0.1),
    ]

    result = fitter.fit_mode_coefficients(records)

    assert result["status"] == "insufficient_sample"
    assert result["promotion_candidate"] is False


def test_fit_mode_coefficients_ignores_ineligible_records() -> None:
    records = [_record("positive", 0.9, 0.9, 0.9, eligible=False) for _ in range(10)]
    records += [_record("null_result", 0.1, 0.1, 0.1, eligible=False) for _ in range(10)]

    result = fitter.fit_mode_coefficients(records)

    assert result["status"] == "insufficient_sample"
    assert result["n_positive"] == 0
    assert result["n_null"] == 0


def test_fit_mode_coefficients_recovers_strong_synthetic_signal() -> None:
    """Oracle check: when scarcity cleanly separates positives from nulls
    but the existing hand-set `score` does not (deliberately uninformative
    here), the fit should find real signal and clearly beat baseline.

    Baseline scores use distinct, deterministic values with no
    relationship to class (score = f(i) unrelated to i < 15 meaning
    positive) rather than one identical constant -- an exactly-tied
    baseline exposed a real, environment-dependent tie-breaking
    instability in calibration.compute_roc_auc's sort-based AUC (0.19
    locally vs 1.0 in CI for the same all-tied input), which is a
    property of that existing, separately-used function, not something
    to route around by relying on ties here."""
    records = []
    for i in range(30):
        # (i * 7) % 30 is a bijection over 0..29 (gcd(7, 30) == 1), so
        # every baseline score is distinct -- no ties at all, regardless
        # of class, avoiding compute_roc_auc's tie-breaking instability
        # entirely rather than just reducing how often it triggers.
        baseline_score = 0.1 + 0.8 * ((i * 7) % 30) / 29
        if i < 15:
            records.append(_record("positive", 0.9 + i * 0.001, 0.5, 0.5, score=baseline_score))
        else:
            records.append(
                _record("null_result", 0.1 + i * 0.001, 0.5, 0.5, score=baseline_score)
            )

    result = fitter.fit_mode_coefficients(records, n_bootstrap=100)

    assert result["status"] == "fit_complete"
    assert result["n_positive"] == 15
    assert result["n_null"] == 15
    assert result["leave_one_out_auc"] > 0.9
    # The baseline score is deliberately uncorrelated with class, so it
    # should land near 0.5 -- the fit (which uses the real separating
    # feature) should clearly beat it.
    assert 0.3 < result["baseline_policy_auc"] < 0.7
    assert result["leave_one_out_auc"] > result["baseline_policy_auc"] + 0.3
    assert result["promotion_candidate"] is True
    assert result["fitted_coefficients"]["survey_scarcity_score"] > 0


def test_fit_mode_coefficients_no_promotion_when_baseline_already_perfect() -> None:
    """When the existing hand-set score already perfectly separates the
    classes, a fit cannot meaningfully improve on it -- promotion_candidate
    must be False with an explicit reason, not a fabricated improvement."""
    records = []
    for i in range(15):
        records.append(_record("positive", 0.5, 0.5, 0.5, score=0.9 + i * 0.001))
    for i in range(15):
        records.append(_record("null_result", 0.5, 0.5, 0.5, score=0.1 + i * 0.001))

    result = fitter.fit_mode_coefficients(records, n_bootstrap=100)

    assert result["status"] == "fit_complete"
    assert result["baseline_policy_auc"] > 0.99
    assert result["promotion_candidate"] is False
    assert "required margin" in result["promotion_candidate_reason"]


def test_build_fit_report_skips_unauthorized_mode(monkeypatch) -> None:
    def _fake_audit(positive_paths, null_path, policy_path):
        return {
            "sources": {"positive_envelopes": [], "searched_nulls": {}},
            "coefficient_promotion_gate": {
                "observed_counts": {
                    "aten": {"positive": 57, "searched_null": 21},
                    "ieo": {"positive": 7, "searched_null": 3},
                },
                "minimum_thresholds": {
                    "aten": {"positive": 20, "searched_null": 20},
                    "ieo": {"positive": 7, "searched_null": 7},
                },
            },
            "records": [],
        }

    monkeypatch.setattr(fitter.ranking_audit, "build_policy_audit", _fake_audit)

    report = fitter.build_fit_report((Path("a"),), Path("b"), Path("c"))

    assert report["per_mode"]["ieo"]["status"] == "not_authorized"
    assert report["per_mode"]["ieo"]["promotion_candidate"] is False


def test_build_fit_report_real_defaults_end_to_end() -> None:
    """Integration check against the real, current default files -- small
    n_bootstrap to keep CI fast; the real production run uses the CLI
    default (500)."""
    report = fitter.build_fit_report(
        fitter.ranking_audit.DEFAULT_POSITIVES,
        fitter.ranking_audit.DEFAULT_NULLS,
        fitter.ranking_audit.DEFAULT_POLICY,
        n_bootstrap=50,
    )

    assert report["schema_version"] == fitter.SCHEMA_VERSION
    assert set(report["per_mode"]) == {"aten", "ieo"}
    for mode_result in report["per_mode"].values():
        assert mode_result["status"] in {"fit_complete", "insufficient_sample", "not_authorized"}
    assert isinstance(report["any_promotion_candidate"], bool)
    # Must be within the gate's own source_aligned_ztf_i41 counts (never
    # exceed them; the fit further restricts to eligible records, which
    # can be a strict subset) -- regression guard for a real bug found in
    # this session where the fitter used every accepted MPC positive for a
    # mode (thousands, for aten) instead of only the ZTF/I41-source-aligned
    # subset the gate itself counts (57 for aten, 7 for ieo at the time
    # this was written).
    audit_result = fitter.ranking_audit.build_policy_audit(
        fitter.ranking_audit.DEFAULT_POSITIVES,
        fitter.ranking_audit.DEFAULT_NULLS,
        fitter.ranking_audit.DEFAULT_POLICY,
    )
    gate_counts = audit_result["coefficient_promotion_gate"]["observed_counts"]
    for mode in ("aten", "ieo"):
        assert report["per_mode"][mode]["n_positive"] <= gate_counts[mode]["positive"]
        assert report["per_mode"][mode]["n_null"] <= gate_counts[mode]["searched_null"]
        assert report["per_mode"][mode]["n_positive"] >= gate_counts[mode]["positive"] - 5
        assert report["per_mode"][mode]["n_null"] >= gate_counts[mode]["searched_null"] - 5
