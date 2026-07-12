"""Regression tests for Skills/injection_recovery.py's checkpoint/resume
behavior (standing rule: any Skills script that processes items in a loop
must survive a process kill without losing work)."""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

import injection_recovery as ir  # noqa: E402


class TestCheckpointKey:
    def test_same_params_same_key(self):
        assert ir._checkpoint_key(10, 42, "ZTF") == ir._checkpoint_key(10, 42, "ZTF")

    def test_different_params_different_key(self):
        assert ir._checkpoint_key(10, 42, "ZTF") != ir._checkpoint_key(10, 43, "ZTF")
        assert ir._checkpoint_key(10, 42, "ZTF") != ir._checkpoint_key(11, 42, "ZTF")
        assert ir._checkpoint_key(10, 42, "ZTF") != ir._checkpoint_key(10, 42, "WISE")
        assert ir._checkpoint_key(10, 42, "ZTF") != ir._checkpoint_key(
            10, 42, "ZTF", image_level=True
        )

    def test_different_cnn_model_path_different_key(self):
        """Real bug precedent (Skills/ztf_alert_archive_ingest.py, 2026-07-11):
        a checkpoint not keyed on every defining parameter can silently
        resume with a different run's cached results. Two runs scoring
        different CNN models must never share a checkpoint."""
        base = ir._checkpoint_key(10, 42, "ZTF", image_level=True)
        with_model_a = ir._checkpoint_key(
            10, 42, "ZTF", image_level=True, cnn_model_path="models/tier2_cnn.pt"
        )
        with_model_b = ir._checkpoint_key(
            10, 42, "ZTF", image_level=True, cnn_model_path="models/tier2_cnn_v3.pt"
        )
        assert base != with_model_a != with_model_b
        assert len({base, with_model_a, with_model_b}) == 3


class TestImageLevelSynthesis:
    """A6: seeing/background/trail-length recovery curves."""

    def test_real_bogus_degrades_with_worse_seeing_background_and_trail(self):
        baseline = ir._analytic_real_bogus(19.5, 1.5, 10.0, 0.0)
        worse_seeing = ir._analytic_real_bogus(19.5, 3.0, 10.0, 0.0)
        worse_background = ir._analytic_real_bogus(19.5, 1.5, 30.0, 0.0)
        worse_trail = ir._analytic_real_bogus(19.5, 1.5, 10.0, 5.0)

        assert 0.0 < baseline < 1.0
        assert worse_seeing < baseline
        assert worse_background < baseline
        assert worse_trail < baseline

    def test_real_bogus_clipped_to_unit_interval(self):
        assert ir._analytic_real_bogus(10.0, 1.0, 0.001, 0.0) == 1.0
        assert ir._analytic_real_bogus(25.0, 4.0, 100.0, 20.0) == 0.0

    def test_synthesize_difference_cutout_shape_and_real_bogus_match(self):
        rng = np.random.default_rng(0)
        cutout_b64, real_bogus = ir._synthesize_difference_cutout(rng, 19.5, 1.5, 10.0, 0.0)

        arr = np.frombuffer(base64.b64decode(cutout_b64), dtype=np.float32)
        assert arr.size == ir._CUTOUT_SIZE * ir._CUTOUT_SIZE
        assert real_bogus == ir._analytic_real_bogus(19.5, 1.5, 10.0, 0.0)

    def test_inject_synthetic_neo_image_level_sets_cutouts_and_real_bogus(self):
        obs = ir.inject_synthetic_neo_image_level(
            seed=1, n_nights=3, seeing_arcsec=1.5, background_level=10.0,
            trail_length_arcsec=0.0,
        )

        assert len(obs) == 6
        for ob in obs:
            assert ob.cutout_difference is not None
            assert 0.0 <= ob.real_bogus <= 1.0

    def test_run_injection_recovery_image_level_populates_curves(self, tmp_path):
        result = ir.run_injection_recovery(
            n_inject=8, seed=3, mission="ZTF", checkpoint_root=tmp_path, image_level=True
        )

        assert result["image_level"] is True
        assert {"seeing_arcsec", "background_level", "trail_length_arcsec"} <= set(
            result["injection_records"][0]
        )
        curves = result["recovery_curves"]["curves"]
        assert set(curves) >= {"seeing_arcsec", "background_level", "trail_length_arcsec"}
        assert not any(
            "require image-level" in limitation
            for limitation in result["recovery_curves"]["limitations"]
        )

    def test_run_injection_recovery_image_level_rejects_non_ztf(self, tmp_path):
        with pytest.raises(ValueError, match="only supported for mission='ZTF'"):
            ir.run_injection_recovery(
                n_inject=1, seed=1, mission="WISE", checkpoint_root=tmp_path, image_level=True
            )


class TestCutoutTriplet:
    """Real bug found 2026-07-11: classify.py's _tier2_predict requires all
    three cutouts (science, reference, difference) to run inference at all --
    the pre-existing --image-level harness only ever populated
    cutout_difference, so no CNN's live weights were ever exercised by
    injection-recovery. _synthesize_cutout_triplet closes that gap."""

    def test_science_minus_reference_equals_difference(self):
        rng = np.random.default_rng(0)
        sci_b64, ref_b64, diff_b64, real_bogus = ir._synthesize_cutout_triplet(
            rng, 19.5, 1.5, 10.0, 0.0
        )
        sci = np.frombuffer(base64.b64decode(sci_b64), dtype=np.float32)
        ref = np.frombuffer(base64.b64decode(ref_b64), dtype=np.float32)
        diff = np.frombuffer(base64.b64decode(diff_b64), dtype=np.float32)

        assert sci.size == ref.size == diff.size == ir._CUTOUT_SIZE * ir._CUTOUT_SIZE
        np.testing.assert_allclose(sci - ref, diff, rtol=1e-5, atol=1e-5)

    def test_difference_cutout_matches_existing_analytic_function_exactly(self):
        """The triplet's difference image and real_bogus must be byte-for-
        byte identical to the pre-existing (unmodified) function, so
        existing committed baselines stay reproducible when
        cnn_scoring=False is used elsewhere."""
        rng_a = np.random.default_rng(5)
        rng_b = np.random.default_rng(5)
        expected_diff_b64, expected_rb = ir._synthesize_difference_cutout(
            rng_a, 19.0, 2.0, 15.0, 1.0
        )
        _, _, actual_diff_b64, actual_rb = ir._synthesize_cutout_triplet(
            rng_b, 19.0, 2.0, 15.0, 1.0
        )
        assert actual_diff_b64 == expected_diff_b64
        assert actual_rb == expected_rb

    def test_inject_synthetic_neo_image_level_cnn_scoring_sets_all_three_cutouts(self):
        obs = ir.inject_synthetic_neo_image_level(
            seed=1, n_nights=3, seeing_arcsec=1.5, background_level=10.0,
            trail_length_arcsec=0.0, cnn_scoring=True,
        )
        assert len(obs) == 6
        for ob in obs:
            assert ob.cutout_science is not None
            assert ob.cutout_reference is not None
            assert ob.cutout_difference is not None

    def test_inject_synthetic_neo_image_level_default_still_omits_triplet(self):
        """cnn_scoring defaults to False -- existing callers/baselines must
        see exactly the pre-existing behavior (difference cutout only)."""
        obs = ir.inject_synthetic_neo_image_level(seed=1, n_nights=3)
        for ob in obs:
            assert ob.cutout_science is None
            assert ob.cutout_reference is None
            assert ob.cutout_difference is not None


class TestCnnScoring:
    """Real Tier 2 CNN inference wired into injection-recovery, per the
    2026-07-11 operator direction to close the gap where injection-recovery
    evidence never reflected any promoted model's actual behavior."""

    @pytest.fixture
    def tiny_model_path(self, tmp_path):
        """A real, freshly-initialized (untrained, random-weight) CNN
        checkpoint -- enough to prove the wiring actually invokes this
        specific file's weights, without needing a full training run."""
        import torch

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from classify import _build_cnn_model

        model = _build_cnn_model()
        assert model is not None
        path = tmp_path / "test_candidate.pt"
        torch.save(model.state_dict(), str(path))
        return path

    def test_cnn_model_path_requires_image_level(self, tmp_path, tiny_model_path):
        with pytest.raises(ValueError, match="requires image_level=True"):
            ir.run_injection_recovery(
                n_inject=1,
                seed=1,
                mission="ZTF",
                checkpoint_root=tmp_path,
                image_level=False,
                cnn_model_path=tiny_model_path,
            )

    def test_missing_cnn_model_fails_closed(self, tmp_path):
        with pytest.raises(ValueError, match="could not be loaded"):
            ir.run_injection_recovery(
                n_inject=1,
                seed=1,
                mission="ZTF",
                checkpoint_root=tmp_path,
                image_level=True,
                cnn_model_path=tmp_path / "does_not_exist.pt",
            )

    def test_real_cnn_run_reports_model_provenance(self, tmp_path, tiny_model_path):
        result = ir.run_injection_recovery(
            n_inject=3,
            seed=2,
            mission="ZTF",
            checkpoint_root=tmp_path,
            image_level=True,
            cnn_model_path=tiny_model_path,
        )
        assert result["cnn_scoring"] is True
        assert result["cnn_model_path"] == str(tiny_model_path)
        assert result["n_injected"] == 3

    def test_different_cnn_models_do_not_share_a_checkpoint(self, tmp_path, tiny_model_path):
        """A second model at a different path must not resume from the
        first model's checkpoint, even with identical n_inject/seed."""
        import torch

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from classify import _build_cnn_model

        other_model = _build_cnn_model()
        other_path = tmp_path / "other_candidate.pt"
        torch.save(other_model.state_dict(), str(other_path))

        ir.run_injection_recovery(
            n_inject=2, seed=9, mission="ZTF", checkpoint_root=tmp_path,
            image_level=True, cnn_model_path=tiny_model_path,
        )
        key_a = ir._checkpoint_key(
            2, 9, "ZTF", image_level=True, cnn_model_path=str(tiny_model_path)
        )
        key_b = ir._checkpoint_key(
            2, 9, "ZTF", image_level=True, cnn_model_path=str(other_path)
        )
        assert key_a != key_b
        assert not (tmp_path / key_b / "checkpoint.json").exists()


class TestAtomicWriteJson:
    def test_writes_readable_json(self, tmp_path):
        path = tmp_path / "sub" / "checkpoint.json"
        ir._atomic_write_json(path, {"a": 1, "b": [1, 2, 3]})
        assert json.loads(path.read_text()) == {"a": 1, "b": [1, 2, 3]}

    def test_no_leftover_tmp_file(self, tmp_path):
        path = tmp_path / "checkpoint.json"
        ir._atomic_write_json(path, {"a": 1})
        assert not path.with_suffix(".json.tmp").exists()


class TestCheckpointResume:
    def test_checkpoint_file_created_after_run(self, tmp_path):
        ir.run_injection_recovery(n_inject=3, seed=1, mission="ZTF", checkpoint_root=tmp_path)
        key = ir._checkpoint_key(3, 1, "ZTF")
        ckpt = tmp_path / key / "checkpoint.json"
        assert ckpt.exists()
        state = json.loads(ckpt.read_text())
        assert state["completed"] == 3
        assert len(state["injection_records"]) == 3
        assert {"mag", "motion_arcsec_per_hr", "detected", "linked", "scored"} <= set(
            state["injection_records"][0]
        )

    def test_completed_checkpoint_short_circuits(self, tmp_path, capsys):
        ir.run_injection_recovery(n_inject=3, seed=1, mission="ZTF", checkpoint_root=tmp_path)
        capsys.readouterr()
        result = ir.run_injection_recovery(
            n_inject=3, seed=1, mission="ZTF", checkpoint_root=tmp_path
        )
        captured = capsys.readouterr()
        assert "[resume] loaded checkpoint: 3/3" in captured.out
        assert result["n_injected"] == 3

    def test_resume_matches_uninterrupted_run(self, tmp_path):
        """A run interrupted after item 3 and resumed to item 6 must produce
        byte-identical results to an uninterrupted 6-item run -- this is the
        core correctness requirement for the RNG bit-generator state
        checkpointing, not just that *a* checkpoint file exists."""
        uninterrupted_root = tmp_path / "uninterrupted"
        full_result = ir.run_injection_recovery(
            n_inject=6, seed=7, mission="ZTF", checkpoint_root=uninterrupted_root
        )

        resumed_root = tmp_path / "resumed"
        partial_result = ir.run_injection_recovery(
            n_inject=3, seed=7, mission="ZTF", checkpoint_root=resumed_root
        )
        # Relabel the completed n=3 checkpoint as a partial n=6 checkpoint,
        # simulating a kill after item 3 of a 6-item run with identical params
        # up to that point (same seed -> identical RNG draws for items 0-2).
        old_key = ir._checkpoint_key(3, 7, "ZTF")
        new_key = ir._checkpoint_key(6, 7, "ZTF")
        state = json.loads((resumed_root / old_key / "checkpoint.json").read_text())
        state["n_inject"] = 6
        new_ckpt = resumed_root / new_key / "checkpoint.json"
        new_ckpt.parent.mkdir(parents=True, exist_ok=True)
        new_ckpt.write_text(json.dumps(state))

        resumed_result = ir.run_injection_recovery(
            n_inject=6, seed=7, mission="ZTF", checkpoint_root=resumed_root
        )

        for key in (
            "n_detected",
            "n_linked",
            "n_scored",
            "detection_rate",
            "link_rate",
            "score_rate",
            "hazard_flag_counts",
        ):
            assert full_result[key] == resumed_result[key], f"mismatch on {key}"
        assert partial_result["n_injected"] == 3
        assert len(resumed_result["injection_records"]) == 6
        assert resumed_result["recovery_curves"]["schema_version"] == "injection-recovery-curves-v1"

    def test_review_packets_survive_resume(self, tmp_path):
        """review_packets accumulated before a resume must be preserved even
        if the interrupted run wasn't given --review-packet-out, since a
        later resumed run might request it."""
        key = ir._checkpoint_key(4, 3, "ZTF")
        partial = ir.run_injection_recovery(
            n_inject=2, seed=3, mission="ZTF", checkpoint_root=tmp_path
        )
        old_key = ir._checkpoint_key(2, 3, "ZTF")
        state = json.loads((tmp_path / old_key / "checkpoint.json").read_text())
        state["n_inject"] = 4
        ckpt = tmp_path / key / "checkpoint.json"
        ckpt.parent.mkdir(parents=True, exist_ok=True)
        ckpt.write_text(json.dumps(state))

        out_path = tmp_path / "packets.json"
        result = ir.run_injection_recovery(
            n_inject=4,
            seed=3,
            mission="ZTF",
            checkpoint_root=tmp_path,
            review_packet_out=out_path,
        )
        assert out_path.exists()
        packets = json.loads(out_path.read_text())
        assert len(packets) == result["n_scored"]
        assert partial["n_injected"] == 2

    def test_curve_json_written_by_cli(self, tmp_path):
        out_path = tmp_path / "curves.json"
        import subprocess

        result = subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "--python",
                "3.14",
                "python",
                "Skills/injection_recovery.py",
                "--n-inject",
                "2",
                "--seed",
                "5",
                "--curve-json",
                str(out_path),
                "--checkpoint-root",
                str(tmp_path / "checkpoints"),
            ],
            capture_output=True,
            env={**os.environ, "UV_CACHE_DIR": ".uv-cache", "PYTHONPATH": "src"},
            text=True,
            check=True,
        )

        assert "Recovery curves saved" in result.stdout
        assert json.loads(out_path.read_text())["schema_version"] == "injection-recovery-curves-v1"

    def test_image_level_cli_writes_curves_with_new_dimensions(self, tmp_path):
        out_path = tmp_path / "curves.json"
        import subprocess

        result = subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "--python",
                "3.14",
                "python",
                "Skills/injection_recovery.py",
                "--n-inject",
                "8",
                "--seed",
                "9",
                "--image-level",
                "--curve-json",
                str(out_path),
                "--checkpoint-root",
                str(tmp_path / "checkpoints"),
            ],
            capture_output=True,
            env={**os.environ, "UV_CACHE_DIR": ".uv-cache", "PYTHONPATH": "src"},
            text=True,
            check=True,
        )

        curves = json.loads(out_path.read_text())["curves"]
        assert "image_level=True" in result.stdout
        assert set(curves) >= {"seeing_arcsec", "background_level", "trail_length_arcsec"}

    def test_image_level_cli_rejects_wise_survey(self, tmp_path):
        import subprocess

        result = subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "--python",
                "3.14",
                "python",
                "Skills/injection_recovery.py",
                "--n-inject",
                "1",
                "--survey",
                "WISE",
                "--image-level",
                "--checkpoint-root",
                str(tmp_path / "checkpoints"),
            ],
            capture_output=True,
            env={**os.environ, "UV_CACHE_DIR": ".uv-cache", "PYTHONPATH": "src"},
            text=True,
        )

        assert result.returncode == 1
        assert "only supported with --survey ZTF" in result.stdout
