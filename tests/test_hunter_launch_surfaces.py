"""NEO-FIELD-01 regression controls for the installed execution surfaces.

The historical field failure was::

    uv sync --all-extras --all-groups --python 3.14 && NEO-Hunter
    ModuleNotFoundError: No module named 'Skills'

Wheel-only verification could not detect it: the built wheel always shipped
``Skills/`` as real package content, while the *editable* install produced by
``uv sync`` exposed only ``src/`` until ``pyproject.toml`` gained a ``Skills``
``package-dir`` mapping. That is the test escape these tests close, per Hunter
contract LAUNCH-02 ("a pass on one surface does not prove another") and
EVAL-01 ("maintain regression tests for all observed field failures", which
names installed-path import failure explicitly).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "Skills")

import verify_hunter_distribution as distribution  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_editable_surface_covers_the_module_that_went_missing() -> None:
    """The packaging-tier probe must name the exact module NEO-FIELD-01 lost."""
    assert "Skills" in distribution.REQUIRED_EDITABLE_IMPORTS
    assert "Skills.hunter_shell" in distribution.REQUIRED_EDITABLE_IMPORTS
    # hunter_commands is what the console script's entry point resolves through.
    assert "hunter_commands" in distribution.REQUIRED_EDITABLE_IMPORTS


def test_dependent_surface_covers_the_canonical_orchestrator() -> None:
    """The dependency tier must cover the module that owns the real pipeline."""
    assert "Skills.hunter_cli" in distribution.REQUIRED_DEPENDENT_IMPORTS
    assert "hunter_state" in distribution.REQUIRED_DEPENDENT_IMPORTS


def test_import_probe_reports_resolution_paths() -> None:
    """The probe must expose each module's resolved file.

    Reporting ``__file__`` is what lets a failure distinguish "not importable"
    from "importable but resolved from the wrong tree" (editable-source leakage).
    """
    source = distribution.editable_import_probe_source(("Skills", "hunter_config"))

    assert "Skills" in source
    assert "hunter_config" in source
    assert "__file__" in source
    assert "json.dump" in source


def test_pyproject_maps_the_skills_package() -> None:
    """Static guard: the packaging mapping that fixes NEO-FIELD-01 must persist.

    This is intentionally a cheap, always-run assertion so that deleting the
    mapping fails the normal suite immediately, without waiting for the slower
    subprocess-based surface checks.
    """
    import tomllib

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    setuptools_config = config["tool"]["setuptools"]

    assert setuptools_config["package-dir"].get("Skills") == "Skills"
    assert "Skills" in setuptools_config["packages"]
    # setuptools does not recurse into subpackages of an explicit package list,
    # so the interaction layer must be enumerated or the installed shell would
    # fail to import it -- the same failure mode as NEO-FIELD-01, one level down.
    assert "Skills.hunter_ux" in setuptools_config["packages"]


def test_shell_and_ux_layer_are_importable_from_the_install() -> None:
    """The UX layer is production runtime, so it must be a probed module."""
    assert "Skills.hunter_shell" in distribution.REQUIRED_EDITABLE_IMPORTS


def _write_minimal_project(root: Path, *, map_extra_package: bool) -> None:
    """Create a tiny two-root project mirroring this repository's layout.

    ``src/`` holds a top-level module and ``Extra/`` holds a second package
    outside that root -- the same shape as ``src/`` plus ``Skills/`` here. When
    ``map_extra_package`` is False the ``Extra`` package is deliberately omitted
    from ``package-dir``, reproducing the NEO-FIELD-01 packaging defect exactly.
    """
    (root / "src").mkdir(parents=True)
    (root / "src" / "probe_config.py").write_text("VALUE = 1\n")
    (root / "Extra").mkdir()
    (root / "Extra" / "__init__.py").write_text('"""fixture package."""\n')

    package_dir = '{"" = "src", "Extra" = "Extra"}' if map_extra_package else '{"" = "src"}'
    packages = '["Extra"]' if map_extra_package else "[]"
    (root / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["setuptools>=68"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        'name = "probe-fixture"\n'
        'version = "0.0.1"\n'
        'requires-python = ">=3.11"\n\n'
        "[tool.setuptools]\n"
        f"package-dir = {package_dir}\n"
        f"packages = {packages}\n"
        'py-modules = ["probe_config"]\n'
    )


@pytest.mark.parametrize("map_extra_package", [True, False])
def test_probe_detects_missing_package_mapping(tmp_path: Path, map_extra_package: bool) -> None:
    """Adversarial control: prove the probe can fail, not merely pass.

    A check that cannot detect the defect it claims to detect is not evidence.
    With the mapping present the package imports from the editable install; with
    it absent the import fails with the same error text as the field report.
    """
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv executable is unavailable in this environment")

    project = tmp_path / "project"
    project.mkdir()
    _write_minimal_project(project, map_extra_package=map_extra_package)

    venv = tmp_path / "venv"
    env = {**os.environ, "PYTHONPATH": "", "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache")}
    run_kwargs = {
        "cwd": tmp_path,
        "env": env,
        "capture_output": True,
        "text": True,
        "timeout": 300,
    }
    subprocess.run([uv, "venv", "--python", "3.14", str(venv)], check=True, **run_kwargs)
    python = venv / "bin" / "python"
    subprocess.run(
        [uv, "pip", "install", "--python", str(python), "--no-deps", "-e", str(project)],
        check=True,
        **run_kwargs,
    )

    # Probe from tmp_path, which is not the fixture project root, so a pass
    # cannot come from the current working directory being on sys.path.
    result = subprocess.run(
        [str(python), "-c", distribution.editable_import_probe_source(("Extra",))],
        check=False,
        **run_kwargs,
    )

    if map_extra_package:
        assert result.returncode == 0, result.stderr
        assert "Extra" in json.loads(result.stdout)["resolved"]
    else:
        assert result.returncode != 0
        assert "No module named 'Extra'" in result.stderr
