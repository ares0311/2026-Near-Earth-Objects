"""Regression control for modules imported by installed Hunter entry points."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cross_project_history_module_is_packaged() -> None:
    """The wheel must include the module imported by ``Skills.hunter_cli``."""
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    modules = set(config["tool"]["setuptools"]["py-modules"])

    assert "hunter_cross_project" in modules
