#!/usr/bin/env python3
"""Run the offline pytest suite as six file shards with six workers each.

Every test file is assigned to exactly one outer shard.  Each shard then uses
pytest-xdist's ``--dist=loadfile`` scheduler with six workers, which keeps all
tests from a file together while allowing independent files to run in
parallel.  The default therefore replaces a long serial suite with six shard
controllers x six xdist workers from one terminal.

Coverage remains authoritative: each outer shard writes a unique coverage data
file, and the parent combines all six only after every shard succeeds before
enforcing ``--fail-under=100``.  No shard appends to another shard's coverage
file.

Usage:
    source .venv/bin/activate
    UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 python \
        Skills/run_sharded_tests.py

Use ``--no-coverage`` for a faster development pass, or ``--dry-run`` to
inspect the exact file partition and child commands without starting tests.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TypedDict

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHARDS = 6
DEFAULT_WORKERS = 6
RUN_ROOT = Path("Logs/pipeline_runs/sharded_tests")
THREAD_LIMIT_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_MAX_THREADS": "1",
}
CONTROLLED_PYTEST_FLAGS = (
    "-n",
    "--numprocesses",
    "--dist",
    "--cov",
    "--cov-append",
    "--cov-report",
)


@dataclass
class TestShard:
    """One running outer test shard and its output-relay resources."""

    index: int
    process: subprocess.Popen[str]
    files: tuple[Path, ...]
    log_path: Path
    log_handle: IO[str]
    output_thread: threading.Thread
    started_monotonic: float


class ShardResult(TypedDict):
    """JSON-serializable completion record for one outer test shard."""

    shard_index: int
    status: str
    return_code: int
    file_count: int
    elapsed_seconds: float
    log_path: str


def _utc_now() -> str:
    """Return a timezone-aware timestamp for the local run summary."""
    return datetime.now(UTC).isoformat()


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds consistently with other operator Skills."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def discover_test_files(test_root: Path) -> list[Path]:
    """Return the deterministic set of offline test modules to partition."""
    return sorted(path for path in test_root.glob("test_*.py") if path.is_file())


def partition_test_files(files: list[Path], shard_count: int) -> list[tuple[Path, ...]]:
    """Greedily balance disjoint test-file shards using file size as a proxy.

    File ownership is exclusive by construction.  Largest files are placed
    first onto the currently lightest shard, which is more balanced than a
    simple alphabetical slice while remaining deterministic.
    """
    if shard_count < 1:
        raise ValueError("shard_count must be >= 1")
    buckets: list[list[Path]] = [[] for _ in range(shard_count)]
    weights = [0] * shard_count
    ordered = sorted(files, key=lambda path: (-path.stat().st_size, path.as_posix()))
    for path in ordered:
        index = min(range(shard_count), key=lambda item: (weights[item], item))
        buckets[index].append(path)
        weights[index] += path.stat().st_size
    return [tuple(sorted(bucket)) for bucket in buckets]


def _contains_controlled_flag(args: tuple[str, ...]) -> str | None:
    """Return the first parent-owned pytest option found in extra arguments."""
    for arg in args:
        for flag in CONTROLLED_PYTEST_FLAGS:
            if arg == flag or arg.startswith(f"{flag}="):
                return flag
    return None


def validate_pytest_args(args: tuple[str, ...]) -> None:
    """Prevent callers from defeating shard ownership or coverage isolation."""
    controlled = _contains_controlled_flag(args)
    if controlled is not None:
        raise ValueError(f"{controlled} is controlled by run_sharded_tests.py")


def build_test_command(
    files: tuple[Path, ...],
    workers: int,
    coverage: bool,
    pytest_args: tuple[str, ...] = (),
) -> list[str]:
    """Build one shell-free pytest-xdist command for a disjoint file shard."""
    command = [
        "caffeinate",
        "-i",
        "uv",
        "run",
        "--no-sync",
        "--python",
        "3.14",
        "python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-n",
        str(workers),
        "--dist=loadfile",
    ]
    if coverage:
        command.extend(("--cov=src", "--cov-report="))
    command.extend(path.as_posix() for path in files)
    command.extend(pytest_args)
    return command


def _child_environment(run_dir: Path, shard_index: int, coverage: bool) -> dict[str, str]:
    """Pin the repo venv/cache, native threads, and per-shard coverage file."""
    env = os.environ.copy()
    env.update(THREAD_LIMIT_ENV)
    env["UV_CACHE_DIR"] = str(REPO_ROOT / ".uv-cache")
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["VIRTUAL_ENV"] = str(REPO_ROOT / ".venv")
    env["PATH"] = f"{REPO_ROOT / '.venv' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    if coverage:
        env["COVERAGE_FILE"] = str(run_dir / f".coverage.shard{shard_index}")
    return env


def _relay_output(stream: IO[str], log_handle: IO[str], shard_index: int) -> None:
    """Copy a shard's output to its log and the shared prefixed terminal."""
    for line in stream:
        log_handle.write(line)
        log_handle.flush()
        print(f"[test shard {shard_index}] {line}", end="", flush=True)


def _terminate_shards(shards: dict[int, TestShard]) -> None:
    """Stop all remaining process groups after a failure or interruption."""
    for shard in shards.values():
        if shard.process.poll() is None:
            os.killpg(shard.process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 10.0
    for shard in shards.values():
        if shard.process.poll() is None:
            try:
                shard.process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(shard.process.pid, signal.SIGKILL)


def combine_coverage(run_dir: Path) -> int:
    """Combine isolated shard data and enforce the repository's 100% gate."""
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(REPO_ROOT / ".uv-cache")
    env["COVERAGE_FILE"] = str(run_dir / ".coverage")
    base = ["uv", "run", "--no-sync", "--python", "3.14", "python", "-m", "coverage"]
    combine = subprocess.run(
        [*base, "combine", "--keep", str(run_dir)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )
    if combine.returncode != 0:
        return combine.returncode
    report = subprocess.run(
        [*base, "report", "--fail-under=100"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )
    return report.returncode


def run_test_shards(
    partitions: list[tuple[Path, ...]],
    workers: int,
    coverage: bool,
    pytest_args: tuple[str, ...],
    run_dir: Path,
) -> int:
    """Run every non-empty shard concurrently and summarize the batch."""
    run_dir = run_dir if run_dir.is_absolute() else REPO_ROOT / run_dir
    coverage_temp = (
        tempfile.TemporaryDirectory(prefix="neo-sharded-coverage-") if coverage else None
    )
    coverage_dir = Path(coverage_temp.name) if coverage_temp is not None else run_dir
    if (REPO_ROOT / "Logs/tier3_pilot.active.json").exists():
        raise RuntimeError("active Tier 3 operator run marker is present")
    if not (REPO_ROOT / ".venv/bin/python").exists():
        raise RuntimeError("repo-local .venv is missing")
    if shutil.which("caffeinate") is None:
        raise RuntimeError("caffeinate is required for the long-running test suite")
    if importlib.util.find_spec("xdist") is None:
        raise RuntimeError(
            "pytest-xdist is missing; restore locked dev dependencies with "
            "UV_CACHE_DIR=.uv-cache uv sync --all-extras --all-groups --python 3.14"
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    running: dict[int, TestShard] = {}
    results: list[ShardResult] = []
    batch_start = time.monotonic()
    exit_code = 0
    try:
        for index, files in enumerate(partitions):
            if not files:
                continue
            log_path = run_dir / f"shard_{index:02d}.log"
            log_handle = log_path.open("w", encoding="utf-8")
            process = subprocess.Popen(
                build_test_command(files, workers, coverage, pytest_args),
                cwd=REPO_ROOT,
                env=_child_environment(coverage_dir, index, coverage),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            if process.stdout is None:  # pragma: no cover - guaranteed by stdout=PIPE
                raise RuntimeError("test shard stdout pipe was not created")
            thread = threading.Thread(
                target=_relay_output,
                args=(process.stdout, log_handle, index),
                daemon=True,
            )
            thread.start()
            running[index] = TestShard(
                index=index,
                process=process,
                files=files,
                log_path=log_path,
                log_handle=log_handle,
                output_thread=thread,
                started_monotonic=time.monotonic(),
            )
            print(
                f"[tests] started shard {index}/{len(partitions)} pid={process.pid} "
                f"files={len(files)} workers={workers}",
                flush=True,
            )

        total = len(running)
        completed = 0
        while running:
            finished = [
                index for index, shard in running.items() if shard.process.poll() is not None
            ]
            if not finished:
                time.sleep(0.25)
                continue
            for index in finished:
                shard = running.pop(index)
                return_code = shard.process.wait()
                shard.output_thread.join(timeout=2.0)
                shard.log_handle.close()
                elapsed = time.monotonic() - shard.started_monotonic
                completed += 1
                status = "succeeded" if return_code == 0 else "failed"
                results.append(
                    {
                        "shard_index": index,
                        "status": status,
                        "return_code": return_code,
                        "file_count": len(shard.files),
                        "elapsed_seconds": round(elapsed, 2),
                        "log_path": shard.log_path.relative_to(REPO_ROOT).as_posix(),
                    }
                )
                batch_elapsed = time.monotonic() - batch_start
                eta = (batch_elapsed / completed) * (total - completed)
                print(
                    f"[tests] shard {index} {status}; completed {completed}/{total} "
                    f"elapsed {_fmt_duration(batch_elapsed)} ETA {_fmt_duration(eta)}",
                    flush=True,
                )
                if return_code != 0:
                    exit_code = return_code or 1
                    _terminate_shards(running)
                    break
            if exit_code:
                break
    except KeyboardInterrupt:
        print("[tests] interrupted; terminating all shards", flush=True)
        _terminate_shards(running)
        exit_code = 130
    except Exception:
        _terminate_shards(running)
        if coverage_temp is not None:
            coverage_temp.cleanup()
        raise
    finally:
        for shard in running.values():
            shard.output_thread.join()
            shard.log_handle.close()

    if exit_code == 0 and coverage:
        exit_code = combine_coverage(coverage_dir)
    if coverage_temp is not None:
        coverage_temp.cleanup()

    summary = {
        "schema_version": "sharded-test-run-v1",
        "generated_at_utc": _utc_now(),
        "shard_count": len(partitions),
        "workers_per_shard": workers,
        "aggregate_workers": len(partitions) * workers,
        "coverage": coverage,
        "status": "succeeded" if exit_code == 0 else "failed",
        "shards": sorted(results, key=lambda item: item["shard_index"]),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    """Create the one-command local test runner interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=int, default=DEFAULT_SHARDS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--test-root", type=Path, default=Path("tests"))
    parser.add_argument(
        "--test-file",
        type=Path,
        action="append",
        default=[],
        help="Run only this test file; repeat for multiple files.",
    )
    parser.add_argument("--no-coverage", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    return parser


def main() -> None:
    """Partition test files, print the plan, and run all shards from one CLI."""
    args = _build_parser().parse_args()
    if args.shards < 1 or args.workers < 1:
        raise SystemExit("--shards and --workers must both be >= 1")
    raw_pytest_args = (
        args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    )
    pytest_args = tuple(raw_pytest_args)
    try:
        validate_pytest_args(pytest_args)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    files = args.test_file or discover_test_files(args.test_root)
    if not files:
        raise SystemExit("no test files found")
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise SystemExit(f"test files do not exist: {missing}")
    partitions = partition_test_files(files, args.shards)
    coverage = not args.no_coverage
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = RUN_ROOT / run_id
    print(
        f"[test plan] shards={args.shards} workers_per_shard={args.workers} "
        f"aggregate_workers={args.shards * args.workers} files={len(files)} "
        f"coverage={coverage}",
        flush=True,
    )
    for index, partition in enumerate(partitions):
        command = build_test_command(partition, args.workers, coverage, pytest_args)
        print(f"[test command {index}] {' '.join(command)}", flush=True)
    if args.dry_run:
        print("[dry-run] no pytest processes started", flush=True)
        return
    try:
        result = run_test_shards(
            partitions,
            args.workers,
            coverage,
            pytest_args,
            run_dir,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    raise SystemExit(result)


if __name__ == "__main__":
    main()
