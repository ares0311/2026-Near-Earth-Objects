"""Regression tests for Skills/evaluate_cnn_false_discovery.py.

Real gap closed 2026-07-12: false_discovery_report never exercised any CNN
candidate's live inference (derived from Gate Z4's handcrafted-feature
logistic-regression ranking baseline instead). Real archived Gate Z4
negative tracklets cannot be reused for a CNN-specific test -- their
cutout images were never mapped from the raw AVRO packets (documented
limitation, not an oversight) -- so this is an explicitly synthetic-only,
additional evaluation, not a replacement for Gate Z4's real evidence.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

import evaluate_cnn_false_discovery as fd  # noqa: E402

from classify import _build_cnn_model  # noqa: E402


class TestArtifactCutoutSynthesis:
    def test_produces_valid_triplet(self):
        rng = np.random.default_rng(0)
        sci_b64, ref_b64, diff_b64, real_bogus = fd._synthesize_artifact_cutout_triplet(
            rng, 19.5, 10.0
        )
        sci = np.frombuffer(base64.b64decode(sci_b64), dtype=np.float32)
        ref = np.frombuffer(base64.b64decode(ref_b64), dtype=np.float32)
        diff = np.frombuffer(base64.b64decode(diff_b64), dtype=np.float32)
        assert sci.size == ref.size == diff.size == fd._CUTOUT_SIZE * fd._CUTOUT_SIZE
        assert 0.0 <= real_bogus <= 1.0

    def test_artifact_clears_detect_threshold_at_reasonable_background(self):
        """The whole point of this test: the artifact must be bright enough
        (by the same amplitude/background SNR proxy detect.py's pre-filter
        uses) to reach classify() -- otherwise this would only be testing
        detect()'s threshold, not classify()'s shape discrimination."""
        rng = np.random.default_rng(0)
        _, _, _, real_bogus = fd._synthesize_artifact_cutout_triplet(rng, 19.5, 10.0)
        assert real_bogus >= 0.65

    def test_artifact_is_spatially_narrower_than_a_genuine_point_source(self):
        """The artifact's generating sigma must be far narrower than any
        realistic seeing-limited PSF -- otherwise this wouldn't be testing
        an artifact shape at all. Compares the actual generating
        parameters directly rather than reconstructing sigma from noisy
        pixel data, which is confounded by the two profiles' very
        different peak amplitudes (a fair, robust comparison needs the
        ground truth, not a noisy proxy)."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from injection_recovery import _FWHM_FACTOR, _PIXEL_SCALE_ARCSEC_PER_PX  # noqa: E402

        typical_seeing_arcsec = 1.5
        real_sigma_px = (typical_seeing_arcsec / _PIXEL_SCALE_ARCSEC_PER_PX) / _FWHM_FACTOR
        assert fd._ARTIFACT_SPIKE_SIGMA_PX < real_sigma_px / 2


class TestArtifactTracklet:
    def test_generates_expected_observation_count_with_full_triplets(self):
        obs = fd.synthesize_artifact_tracklet(seed=1, n_nights=3)
        assert len(obs) == 6
        for ob in obs:
            assert ob.cutout_science is not None
            assert ob.cutout_reference is not None
            assert ob.cutout_difference is not None

    def test_satisfies_link_motion_consistency(self):
        """The tracklet must actually be linkable -- otherwise this test
        would only be measuring link.py's rejection rate, not classify()'s
        artifact discrimination."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from detect import detect
        from link import link

        obs = fd.synthesize_artifact_tracklet(seed=2, n_nights=3, background_level=8.0)
        det = detect(obs, mpc_cross_match=False)
        assert det.candidates, "artifact must clear detect.py's real_bogus pre-filter"
        result = link(tuple(det.candidates), min_nights=2, min_observations=3)
        assert result.tracklets, "artifact geometry must satisfy link.py's chi2 test"


class TestRunFalseDiscoveryEval:
    @pytest.fixture
    def tiny_model_path(self, tmp_path):
        model = _build_cnn_model()
        assert model is not None
        path = tmp_path / "test_candidate.pt"
        torch.save(model.state_dict(), str(path))
        return path

    def test_missing_model_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="could not be loaded"):
            fd.run_false_discovery_eval(
                cnn_model_path=tmp_path / "does_not_exist.pt", n_artifacts=1, seed=1
            )

    def test_real_run_reports_expected_schema(self, tiny_model_path):
        result = fd.run_false_discovery_eval(
            cnn_model_path=tiny_model_path, n_artifacts=5, seed=3
        )
        assert result["schema_version"] == "cnn-false-discovery-v1"
        assert result["cnn_model_path"] == str(tiny_model_path)
        assert result["n_artifacts"] == 5
        assert result["n_scored"] <= 5
        assert 0.0 <= result["false_discovery_rate"] <= 1.0
        assert 0.0 <= result["tier2_false_discovery_rate"] <= 1.0
        assert len(result["records"]) == 5
        assert any("Synthetic-only" in lim for lim in result["limitations"])

    def test_records_carry_both_ensemble_and_tier2_only_verdicts(self, tiny_model_path):
        result = fd.run_false_discovery_eval(
            cnn_model_path=tiny_model_path, n_artifacts=8, seed=4
        )
        scored = [r for r in result["records"] if r["scored"]]
        assert scored, "expected at least one scored artifact at n=8"
        for record in scored:
            assert record["argmax_class"] in {
                "neo_candidate", "known_object", "main_belt_asteroid",
                "stellar_artifact", "other_solar_system",
            }
            assert record["tier2_argmax_class"] in {
                "neo_candidate", "known_object", "main_belt_asteroid",
                "stellar_artifact", "other_solar_system",
            }
