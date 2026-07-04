"""Tests for Skills/evaluate_ranking_baseline.py (Gate Z4 auditable ranking
baseline).

Reuses the exact real-schema checkpoint fixture pattern already proven in
test_run_archive_positive_control.py for the negative-class loader, and the
project's established synthetic-injection generator for the positive class.
No network calls are made anywhere in this script.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Skills"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "evaluate_ranking_baseline.py"
)
_spec = importlib.util.spec_from_file_location("evaluate_ranking_baseline", _MODULE_PATH)
evaluate_ranking_baseline = importlib.util.module_from_spec(_spec)
sys.modules["evaluate_ranking_baseline"] = evaluate_ranking_baseline
_spec.loader.exec_module(evaluate_ranking_baseline)


def _make_obs_dict(obs_id, jd, ra_deg, dec_deg, mag, real_bogus=0.92):
    return {
        "obs_id": obs_id,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "jd": jd,
        "mag": mag,
        "mag_err": 0.05,
        "filter_band": "r",
        "mission": "ZTF",
        "real_bogus": real_bogus,
        "field_id": "377",
        "limiting_mag": 20.0,
    }


def _write_two_night_checkpoints(out_dir: Path, seed: int = 7):
    """Real-schema checkpoint files matching what
    Skills/ztf_alert_archive_ingest.py writes."""
    rng = np.random.default_rng(seed)
    motion_arcsec_per_hr = 1.0
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    ra0, dec0 = 90.0, 10.0
    nights = ["20220817", "20220819"]

    for night_idx, night in enumerate(nights):
        jd_base = 2459000.5 + night_idx
        ra_base = ra0 + night_idx * dra_per_hr * 24
        obs_a = _make_obs_dict(
            f"n{night_idx}a", jd_base,
            ra_base + rng.normal(0, 0.5 / 3600.0), dec0 + rng.normal(0, 0.5 / 3600.0), 19.5,
        )
        obs_b = _make_obs_dict(
            f"n{night_idx}b", jd_base + 1 / 24,
            ra_base + dra_per_hr + rng.normal(0, 0.5 / 3600.0),
            dec0 + rng.normal(0, 0.5 / 3600.0), 19.5,
        )
        state = {
            "night": night,
            "filename": f"ztf_public_{night}.tar.gz",
            "scanned_count": 100,
            "kept_count": 2,
            "observations": [obs_a, obs_b],
        }
        (out_dir / f"{night}.json").write_text(json.dumps(state, indent=2))
    return nights


class TestRecallPurityAtK:
    def test_recall_at_k_all_positives_first(self):
        labels_sorted = np.array([1, 1, 0, 0, 1])
        # 2 of 3 total positives captured in top 2.
        assert evaluate_ranking_baseline._recall_at_k(labels_sorted, 2) == 2 / 3

    def test_recall_at_k_no_positives_returns_zero(self):
        labels_sorted = np.array([0, 0, 0])
        assert evaluate_ranking_baseline._recall_at_k(labels_sorted, 2) == 0.0

    def test_purity_at_k(self):
        labels_sorted = np.array([1, 0, 1, 0])
        assert evaluate_ranking_baseline._purity_at_k(labels_sorted, 2) == 0.5

    def test_purity_at_zero_k_returns_zero(self):
        labels_sorted = np.array([1, 0])
        assert evaluate_ranking_baseline._purity_at_k(labels_sorted, 0) == 0.0


class TestEvaluateRanking:
    def test_perfect_ranking_gets_full_recall_and_purity(self):
        scores = np.array([0.9, 0.8, 0.2, 0.1])
        labels = np.array([1, 1, 0, 0])
        report = evaluate_ranking_baseline._evaluate_ranking("perfect", scores, labels, (2,))
        assert report["recall_at_k"]["2"] == 1.0
        assert report["purity_at_k"]["2"] == 1.0
        assert report["name"] == "perfect"


class TestLoadRealNegativeTracklets:
    def test_loads_real_tracklets_from_checkpoints(self, tmp_path):
        nights = _write_two_night_checkpoints(tmp_path)
        tracklets = evaluate_ranking_baseline._load_real_negative_tracklets(
            tmp_path, [nights]
        )
        assert len(tracklets) >= 1

    def test_missing_pair_is_skipped_not_raised(self, tmp_path):
        tracklets = evaluate_ranking_baseline._load_real_negative_tracklets(
            tmp_path, [["99999999", "99999998"]]
        )
        assert tracklets == []


class TestMakeSyntheticPositiveTracklets:
    def test_produces_tracklets(self):
        tracklets = evaluate_ranking_baseline._make_synthetic_positive_tracklets(
            n_positive=10, seed=1
        )
        assert len(tracklets) > 0


class TestRunRankingBaseline:
    def test_full_report_structure(self, tmp_path):
        nights = _write_two_night_checkpoints(tmp_path)
        report = evaluate_ranking_baseline.run_ranking_baseline(
            n_positive=10,
            seed=1,
            checkpoint_dir=tmp_path,
            night_pairs=[nights],
            k_values=(1, 2),
            n_splits=2,
        )
        assert report["n_positive"] > 0
        assert report["n_negative"] > 0
        for key in ("logistic_regression_handcrafted", "naive_real_bogus_only"):
            assert key in report
            assert "recall_at_k" in report[key]
            assert "purity_at_k" in report[key]
            assert "ece" in report[key]
        assert "false_positive_review_burden" in report

    def test_raises_without_negatives(self):
        try:
            evaluate_ranking_baseline.run_ranking_baseline(
                n_positive=5,
                seed=1,
                checkpoint_dir=Path("/nonexistent"),
                night_pairs=[["99999999", "99999998"]],
            )
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "positive" in str(exc) or "negative" in str(exc)
