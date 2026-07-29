from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, "Skills")

import verify_hunter_distribution as distribution  # noqa: E402


def _write_wheel(path: Path, names: tuple[str, ...]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"fixture")
    return path


def test_validate_wheel_contents_accepts_independent_complete_fixture(
    tmp_path: Path,
) -> None:
    names = tuple(
        (
            f"neo_detection-1.0.data/data/{suffix.removeprefix('.data/data/')}"
            if suffix.startswith(".data/data/")
            else suffix
        )
        for suffix in distribution.REQUIRED_WHEEL_SUFFIXES
    )
    wheel = _write_wheel(tmp_path / "neo_detection-1.0-py3-none-any.whl", names)

    distribution.validate_wheel_contents(wheel)


def test_validate_wheel_contents_rejects_metadata_only_wheel(tmp_path: Path) -> None:
    wheel = _write_wheel(
        tmp_path / "neo_detection-1.0-py3-none-any.whl",
        ("neo_detection-1.0.dist-info/METADATA",),
    )

    with pytest.raises(ValueError, match="missing required runtime content"):
        distribution.validate_wheel_contents(wheel)


def test_select_wheel_requires_exactly_one_artifact(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="expected exactly one"):
        distribution._select_wheel(tmp_path)

    _write_wheel(tmp_path / "neo_detection-1.0-py3-none-any.whl", ("x",))
    selected = distribution._select_wheel(tmp_path)
    assert selected.name == "neo_detection-1.0-py3-none-any.whl"

    _write_wheel(tmp_path / "neo_detection-2.0-py3-none-any.whl", ("x",))
    with pytest.raises(ValueError, match="expected exactly one"):
        distribution._select_wheel(tmp_path)
