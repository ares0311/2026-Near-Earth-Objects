"""Tests for deterministic six-shard, six-worker pytest orchestration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

import run_sharded_tests as runner  # noqa: E402


def _files(tmp_path: Path, sizes: list[int]) -> list[Path]:
    """Create deterministic synthetic test files with chosen balancing weights."""
    result = []
    for index, size in enumerate(sizes):
        path = tmp_path / f"test_{index:02d}.py"
        path.write_text("x" * size, encoding="utf-8")
        result.append(path)
    return result


def test_partition_is_complete_disjoint_and_deterministic(tmp_path):
    """Every file belongs to exactly one outer shard, with no overlap."""
    files = _files(tmp_path, [100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 5, 1])
    first = runner.partition_test_files(files, 6)
    second = runner.partition_test_files(files, 6)
    flattened = [path for shard in first for path in shard]
    assert first == second
    assert sorted(flattened) == sorted(files)
    assert len(flattened) == len(set(flattened))
    assert all(shard for shard in first)


def test_partition_supports_more_shards_than_files(tmp_path):
    """Empty outer shards are explicit and harmless for tiny targeted runs."""
    partitions = runner.partition_test_files(_files(tmp_path, [10, 5]), 6)
    assert sum(bool(partition) for partition in partitions) == 2


def test_build_test_command_uses_loadfile_and_isolated_coverage_flags():
    """Each outer shard owns files while xdist uses exactly six inner workers."""
    command = runner.build_test_command(
        (Path("tests/test_a.py"), Path("tests/test_b.py")),
        workers=6,
        coverage=True,
        pytest_args=("-k", "fast"),
    )
    assert ["-n", "6"] == command[command.index("-n") : command.index("-n") + 2]
    assert ["-p", "no:cacheprovider"] == command[
        command.index("-p") : command.index("-p") + 2
    ]
    assert "--dist=loadfile" in command
    assert "--cov=src" in command
    assert "--cov-report=" in command
    assert command[-4:] == ["tests/test_a.py", "tests/test_b.py", "-k", "fast"]


def test_no_coverage_command_omits_coverage_options():
    """The fast development mode does not pay collection/reporting overhead."""
    command = runner.build_test_command((Path("tests/test_a.py"),), 6, False)
    assert not any(part.startswith("--cov") for part in command)


@pytest.mark.parametrize("arg", ["-n", "--numprocesses=2", "--dist", "--cov=src"])
def test_pytest_args_cannot_override_parent_owned_parallelism(arg):
    """Caller passthrough options cannot create overlap or coverage races."""
    with pytest.raises(ValueError, match="controlled"):
        runner.validate_pytest_args((arg,))


def test_discover_test_files_ignores_conftest_and_non_tests(tmp_path):
    """Only test modules are assigned to xdist shards."""
    (tmp_path / "test_one.py").write_text("")
    (tmp_path / "conftest.py").write_text("")
    (tmp_path / "helper.py").write_text("")
    assert runner.discover_test_files(tmp_path) == [tmp_path / "test_one.py"]
