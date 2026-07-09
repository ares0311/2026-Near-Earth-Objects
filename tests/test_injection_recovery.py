"""Regression tests for Skills/injection_recovery.py's checkpoint/resume
behavior (standing rule: any Skills script that processes items in a loop
must survive a process kill without losing work)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

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
