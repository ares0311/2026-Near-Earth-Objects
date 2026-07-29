#!/usr/bin/env python3
"""Build/install/smoke the NEO-Hunter wheel outside the source checkout."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WHEEL_SUFFIXES = (
    "hunter_commands.py",
    "hunter_config.py",
    "hunter_state.py",
    "Skills/hunter_cli.py",
    "Skills/hunter_shell.py",
    ".data/data/data_selection/target_priority_queue.csv",
    ".data/data/data_selection/ranking_policies/ztf_field_ranking_v4.json",
    ".data/data/models/tier1_xgb.json",
    ".data/data/models/tier2_cnn_v4.pt",
    ".data/data/models/tier3_transformer.pt",
    ".data/data/models/stacker_coef.json",
)


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def validate_wheel_contents(wheel: Path) -> None:
    """Fail if the artifact omits any runtime module or immutable resource."""

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = [
        suffix
        for suffix in REQUIRED_WHEEL_SUFFIXES
        if not any(name.endswith(suffix) for name in names)
    ]
    if missing:
        raise ValueError(f"wheel is missing required runtime content: {missing}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_distribution(wheel: Path) -> None:
    """Install the artifact with dependencies and launch every product command."""

    validate_wheel_contents(wheel)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable is required for isolated distribution verification")
    with tempfile.TemporaryDirectory(prefix="neo-hunter-wheel-smoke-") as raw_tmp:
        root = Path(raw_tmp)
        venv = root / "venv"
        state = root / "state"
        env = {
            **os.environ,
            "NEOHUNTER_HOME": str(state),
            "PYTHONPATH": "",
            "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache"),
        }
        _run(
            [uv, "venv", "--python", "3.14", str(venv)],
            cwd=root,
            env=env,
        )
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        scripts = venv / ("Scripts" if os.name == "nt" else "bin")
        _run(
            [uv, "pip", "install", "--python", str(python), str(wheel.resolve())],
            cwd=root,
            env=env,
        )

        immutable = [
            venv / "data_selection" / "target_priority_queue.csv",
            venv
            / "data_selection"
            / "ranking_policies"
            / "ztf_field_ranking_v4.json",
            venv / "models" / "tier1_xgb.json",
            venv / "models" / "tier2_cnn_v4.pt",
            venv / "models" / "tier3_transformer.pt",
            venv / "models" / "stacker_coef.json",
        ]
        for path in immutable:
            if not path.is_file():
                raise ValueError(f"installed immutable resource is missing: {path}")
        before = {str(path): _sha256(path) for path in immutable}

        commands = (
            [str(scripts / "NEO-Hunter"), "--command", "/Help"],
            [str(scripts / "NEOHunter"), "--command", "/Help"],
            [str(scripts / "Create-New-Search"), "--help"],
            [str(scripts / "Run-New-Search"), "--help"],
            [str(scripts / "Show-Follow-Ups"), "--help"],
            [str(scripts / "Show-Follow-Ups")],
        )
        for command in commands:
            _run(command, cwd=root, env=env)

        expected_state = (
            state / "data_selection" / "hunter_state.sqlite",
            state / "Logs" / "reports" / "hunter_events.jsonl",
        )
        for path in expected_state:
            if not path.is_file():
                raise ValueError(f"installed command did not write expected state: {path}")
        after = {str(path): _sha256(path) for path in immutable}
        if before != after:
            raise ValueError("installed commands mutated immutable distribution resources")


def _select_wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.glob("neo_detection-*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"expected exactly one neo_detection wheel in {wheel_dir}, found {wheels}")
    return wheels[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel-dir",
        type=Path,
        help="directory containing one prebuilt wheel; otherwise build a temporary wheel",
    )
    args = parser.parse_args(argv)
    if args.wheel_dir is not None:
        wheel = _select_wheel(args.wheel_dir)
        verify_distribution(wheel)
    else:
        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError("uv executable is required for distribution verification")
        with tempfile.TemporaryDirectory(prefix="neo-hunter-wheel-build-") as raw_tmp:
            dist = Path(raw_tmp) / "dist"
            env = {**os.environ, "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache")}
            _run(
                [uv, "build", "--wheel", "--out-dir", str(dist)],
                cwd=REPO_ROOT,
                env=env,
            )
            verify_distribution(_select_wheel(dist))
    print("[hunter-distribution] PASS -- isolated wheel contents, launch, and state isolation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
