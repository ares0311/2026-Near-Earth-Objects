#!/usr/bin/env python3
"""Build/install/smoke the NEO-Hunter distribution outside the source checkout.

Two distinct execution surfaces are verified, because a pass on one does not
prove the other (Hunter contract LAUNCH-02):

* ``wheel``    -- the built artifact installed into an isolated environment.
* ``editable`` -- the synchronized/editable install that ``uv sync`` produces,
  which is the surface the documented operator workflow actually uses.

Field blocker NEO-FIELD-01 was an ``editable``-surface failure
(``ModuleNotFoundError: No module named 'Skills'``) that the wheel-only
verification could not detect: the wheel always carried ``Skills/`` as real
package data, while the editable install exposed only ``src/`` until the
``Skills`` ``package-dir`` mapping was added to ``pyproject.toml``. Verifying
both surfaces is the regression control for that escape.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
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
    # The interaction layer is production runtime, not a development helper.
    "Skills/hunter_ux/__init__.py",
    "Skills/hunter_ux/registry.py",
    "Skills/hunter_ux/validation.py",
    "Skills/hunter_ux/palette.py",
    "Skills/hunter_ux/table.py",
    "Skills/hunter_ux/theme.py",
    "Skills/hunter_ux/animation.py",
    "Skills/hunter_ux/preview.py",
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


# Modules the editable install must expose using only the standard library.
# These are exactly the modules the ``NEO-Hunter`` console script touches while
# starting up, so their importability is the precise packaging question behind
# field blocker NEO-FIELD-01. Because they need no third-party dependencies they
# can be probed in a ``--no-deps`` environment in seconds.
REQUIRED_EDITABLE_IMPORTS = (
    "Skills",
    "Skills.hunter_shell",
    "hunter_commands",
    "hunter_config",
)

# Production modules that additionally require the resolved dependency set.
# These are probed against an already-synchronized environment rather than a
# throwaway one, because installing the full dependency closure (torch and
# friends) per verification run would cost minutes and gigabytes without
# testing anything the dependency resolver has not already proven.
REQUIRED_DEPENDENT_IMPORTS = (
    "Skills.hunter_cli",
    "hunter_state",
    "known_object_exclusion",
)


def editable_import_probe_source(modules: tuple[str, ...]) -> str:
    """Return a self-contained probe asserting each module imports and resolves.

    The probe deliberately reports the resolved ``__file__`` of every module so a
    failure distinguishes "not importable at all" from "importable but resolved
    from the wrong tree" (for example editable-source leakage).
    """

    return (
        "import importlib, json, sys\n"
        f"names = {list(modules)!r}\n"
        "resolved = {}\n"
        "for name in names:\n"
        "    module = importlib.import_module(name)\n"
        "    resolved[name] = getattr(module, '__file__', None)\n"
        "json.dump({'sys_path_has_cwd': '' in sys.path, 'resolved': resolved},"
        " sys.stdout)\n"
    )


def verify_editable_surface(*, repo_root: Path | None = None) -> dict[str, str | None]:
    """Install the project editable into a throwaway environment and smoke it.

    Dependencies are intentionally skipped (``--no-deps``): the modules under
    test here reach the operator shell using only the standard library, so the
    probe isolates the *packaging* question (is ``Skills`` importable from an
    editable install?) from unrelated dependency resolution, and stays fast
    enough to run in the normal validation suite.
    """

    root = REPO_ROOT if repo_root is None else repo_root
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv executable is required for editable-surface verification")

    with tempfile.TemporaryDirectory(prefix="neo-hunter-editable-smoke-") as raw_tmp:
        tmp = Path(raw_tmp)
        venv = tmp / "venv"
        state = tmp / "state"
        env = {
            **os.environ,
            "NEOHUNTER_HOME": str(state),
            # An empty PYTHONPATH proves the install itself supplies the modules.
            "PYTHONPATH": "",
            "UV_CACHE_DIR": str(root / ".uv-cache"),
        }
        _run([uv, "venv", "--python", "3.14", str(venv)], cwd=tmp, env=env)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        scripts = venv / ("Scripts" if os.name == "nt" else "bin")
        _run(
            [uv, "pip", "install", "--python", str(python), "--no-deps", "-e", str(root)],
            cwd=tmp,
            env=env,
        )

        # Probe imports from a working directory that is NOT the repository root,
        # so an accidental reliance on the caller's CWD cannot mask a real gap.
        probe = _run(
            [str(python), "-c", editable_import_probe_source(REQUIRED_EDITABLE_IMPORTS)],
            cwd=tmp,
            env=env,
        )
        resolved = json.loads(probe.stdout)["resolved"]

        # Launch the documented console scripts as real subprocesses from that
        # same unrelated working directory.
        for executable in ("NEO-Hunter", "NEOHunter"):
            for command in ("/Help", "/Exit"):
                _run(
                    [str(scripts / executable), "--no-animation", "--command", command],
                    cwd=tmp,
                    env=env,
                )

    return resolved


def verify_dependent_imports(*, python: Path | None = None) -> dict[str, str | None]:
    """Prove the dependency-bearing production modules import in a synced env.

    ``python`` defaults to the interpreter running this verification, which under
    the documented workflow is the ``uv sync``-managed environment.
    """

    interpreter = Path(sys.executable) if python is None else python
    with tempfile.TemporaryDirectory(prefix="neo-hunter-dep-probe-") as raw_tmp:
        tmp = Path(raw_tmp)
        # Run from an unrelated working directory and with PYTHONPATH cleared so
        # the probe cannot be satisfied by the source checkout being the CWD.
        probe = _run(
            [
                str(interpreter),
                "-c",
                editable_import_probe_source(REQUIRED_DEPENDENT_IMPORTS),
            ],
            cwd=tmp,
            env={**os.environ, "PYTHONPATH": "", "NEOHUNTER_HOME": str(tmp / "state")},
        )
    return json.loads(probe.stdout)["resolved"]


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
    parser.add_argument(
        "--surface",
        choices=("wheel", "editable", "both"),
        default="both",
        help="execution surface(s) to verify; 'both' is the contract default (LAUNCH-02)",
    )
    args = parser.parse_args(argv)

    if args.surface in {"wheel", "both"}:
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
        print("[hunter-distribution] PASS -- wheel surface: contents, launch, state isolation")

    if args.surface in {"editable", "both"}:
        resolved = verify_editable_surface()
        print(
            "[hunter-distribution] PASS -- editable surface: "
            f"{len(resolved)} standard-library-reachable modules importable "
            "without PYTHONPATH"
        )
        print(f"[hunter-distribution] Skills resolved from: {resolved['Skills']}")
        dependent = verify_dependent_imports()
        print(
            "[hunter-distribution] PASS -- synced environment: "
            f"{len(dependent)} dependency-bearing production modules importable"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
