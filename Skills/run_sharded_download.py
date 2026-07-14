#!/usr/bin/env python3
"""Launch a repo-native downloader as six shards with six workers each.

This is an execution orchestrator, not a downloader.  The target Skill remains
responsible for partitioning inputs, checkpoint/resume, retries, per-item
progress, output paths, and its scientific data contract.  This parent process
replaces six terminal tabs by starting every native shard concurrently,
prefixing each shard's output in one terminal, stopping the batch on a child
failure, and recording compact shard completion records.

The target must already expose ``--shard-index``, ``--shard-count``, and
``--workers``.  Refusing targets without those exact native flags prevents this
launcher from guessing how to partition a dataset or creating overlapping
writes.

Example:
    source .venv/bin/activate
    UV_CACHE_DIR=.uv-cache caffeinate -i uv run --no-sync --python 3.14 python \
        Skills/run_sharded_download.py \
        --script Skills/<native_sharded_downloader>.py \
        --estimated-download-gb 20 \
        -- --target-queue data_selection/target_priority_queue.csv --resume

The default is 6 shards x 6 workers (36 bounded target workers in aggregate).
Use ``--dry-run`` to inspect every child command without network or file writes.
Use ``--status`` at any time or ``--merge`` for a fail-closed final check.
Use ``--sync`` to retry the narrow Git relay for already-recorded local results.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHARDS = 6
DEFAULT_WORKERS = 6
DEFAULT_MAX_PROJECT_DATA_GB = 100.0
DEFAULT_MIN_FREE_GB = 10.0
GIT_PUSH_ATTEMPTS = 3
GIT_PUSH_BACKOFF_SECONDS = (2.0, 4.0)
MANIFEST_PATH = Path("Logs/reports/sharded_download_manifest.jsonl")
RUN_ROOT = Path("Logs/pipeline_runs/sharded_download")
PROJECT_DATA_DIRS = (
    "data",
    "datasets",
    "cache",
    ".cache",
    "artifacts",
    "outputs",
    "downloads",
    "tmp",
)
CONTROLLED_FLAGS = {"--shard-index", "--shard-count", "--workers"}
SECRET_FRAGMENTS = ("token", "password", "secret", "api-key", "api_key", "credential")
THREAD_LIMIT_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_MAX_THREADS": "1",
}


@dataclass(frozen=True)
class LaunchConfig:
    """Validated immutable settings shared by all child shard processes."""

    script: Path
    child_args: tuple[str, ...]
    shard_count: int
    workers: int
    estimated_download_gb: float
    max_project_data_gb: float
    min_free_gb: float
    manifest_path: Path
    run_root: Path
    resume: bool


@dataclass
class RunningShard:
    """One child process plus the resources used to relay and persist output."""

    index: int
    process: subprocess.Popen[str]
    log_path: Path
    log_handle: IO[str]
    output_thread: threading.Thread
    started_monotonic: float
    started_at_utc: str


def _utc_now() -> str:
    """Return a timezone-aware timestamp for manifest provenance."""
    return datetime.now(UTC).isoformat()


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds consistently with the project's progress rule."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def _strip_remainder_separator(args: list[str]) -> tuple[str, ...]:
    """Remove argparse's leading ``--`` separator from child arguments."""
    if args and args[0] == "--":
        args = args[1:]
    return tuple(args)


def _contains_flag(args: tuple[str, ...], flag: str) -> bool:
    """Detect both ``--flag value`` and ``--flag=value`` spellings."""
    return any(arg == flag or arg.startswith(f"{flag}=") for arg in args)


def _validate_child_args(args: tuple[str, ...]) -> None:
    """Reject launcher-owned flags and plaintext secret-bearing CLI options."""
    for flag in CONTROLLED_FLAGS:
        if _contains_flag(args, flag):
            raise ValueError(f"{flag} is controlled by this launcher; remove it from child args")

    for arg in args:
        normalized = arg.lower().lstrip("-")
        if any(fragment in normalized for fragment in SECRET_FRAGMENTS):
            raise ValueError(
                "Secret-bearing CLI options are prohibited; use the target Skill's "
                "approved environment/Keychain credential flow instead"
            )


def validate_target_script(script: Path, repo_root: Path = REPO_ROOT) -> Path:
    """Return a repo-relative native sharded Skill path or fail closed.

    Static flag inspection avoids executing an untrusted or credential-loading
    module merely to obtain ``--help`` output.
    """
    candidate = script if script.is_absolute() else repo_root / script
    resolved = candidate.resolve()
    skills_root = (repo_root / "Skills").resolve()
    try:
        resolved.relative_to(skills_root)
    except ValueError as exc:
        raise ValueError(
            "--script must resolve inside this repository's Skills/ directory"
        ) from exc
    if not resolved.is_file() or resolved.suffix != ".py":
        raise ValueError("--script must name an existing Python file under Skills/")
    if resolved == Path(__file__).resolve():
        raise ValueError("run_sharded_download.py cannot launch itself")

    source = resolved.read_text(encoding="utf-8")
    missing = sorted(flag for flag in CONTROLLED_FLAGS if flag not in source)
    if missing:
        raise ValueError(
            f"target does not advertise required native flags: {', '.join(missing)}; "
            "the launcher will not guess shard or worker semantics"
        )
    return resolved.relative_to(repo_root.resolve())


def compute_run_id(
    script: Path,
    child_args: tuple[str, ...],
    shard_count: int,
    workers: int,
) -> str:
    """Create a stable resume key from parameters defining the child batch."""
    payload = json.dumps(
        {
            "script": script.as_posix(),
            "child_args": child_args,
            "shard_count": shard_count,
            "workers": workers,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_shard_command(config: LaunchConfig, shard_index: int) -> list[str]:
    """Build one shell-free, copy-safe child command using native CLI flags."""
    return [
        "caffeinate",
        "-i",
        "uv",
        "run",
        "--no-sync",
        "--python",
        "3.14",
        "python",
        config.script.as_posix(),
        *config.child_args,
        "--shard-index",
        str(shard_index),
        "--shard-count",
        str(config.shard_count),
        "--workers",
        str(config.workers),
    ]


def _directory_size_bytes(path: Path) -> int:
    """Measure a project data directory without following external symlinks."""
    if not path.exists():
        return 0
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
        for name in files:
            file_path = Path(root) / name
            if file_path.is_symlink():
                continue
            try:
                total += file_path.stat().st_size
            except FileNotFoundError:
                # A concurrently-created checkpoint may be atomically replaced
                # while the budget scan runs; the next invocation will count it.
                continue
    return total


def project_data_size_gb(repo_root: Path = REPO_ROOT) -> float:
    """Return the policy-defined project-managed data footprint in decimal GB."""
    total = sum(_directory_size_bytes(repo_root / name) for name in PROJECT_DATA_DIRS)
    return total / 1_000_000_000


def check_storage_budget(config: LaunchConfig, repo_root: Path = REPO_ROOT) -> dict[str, float]:
    """Fail before launch if the conservative local cache budget would be exceeded."""
    if config.estimated_download_gb <= 0:
        raise ValueError("--estimated-download-gb must be greater than zero")
    current_gb = project_data_size_gb(repo_root)
    projected_gb = current_gb + config.estimated_download_gb
    if projected_gb > config.max_project_data_gb:
        raise RuntimeError(
            f"projected project data {projected_gb:.1f} GB exceeds the "
            f"{config.max_project_data_gb:.1f} GB conservative cache ceiling"
        )

    free_gb = shutil.disk_usage(repo_root).free / 1_000_000_000
    projected_free_gb = free_gb - config.estimated_download_gb
    if projected_free_gb < config.min_free_gb:
        raise RuntimeError(
            f"projected free space {projected_free_gb:.1f} GB is below the "
            f"{config.min_free_gb:.1f} GB reserve"
        )
    return {
        "current_project_data_gb": round(current_gb, 3),
        "estimated_download_gb": config.estimated_download_gb,
        "projected_project_data_gb": round(projected_gb, 3),
        "free_space_before_gb": round(free_gb, 3),
        "projected_free_space_gb": round(projected_free_gb, 3),
    }


def append_manifest_record(path: Path, record: dict[str, Any]) -> None:
    """Append one compact JSON record under an exclusive POSIX file lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_run_records(path: Path, run_id: str | None = None) -> tuple[str | None, dict[int, dict]]:
    """Return the latest completion record per shard for one run.

    When ``run_id`` is omitted, the most recently started run is selected.
    Malformed or unrelated manifest rows are ignored so ``--status`` remains
    safe during a partially-written or legacy manifest transition.
    """
    if not path.exists():
        return run_id, {}
    starts: list[dict[str, Any]] = []
    completions: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if record.get("record_type") == "run_started":
            starts.append(record)
        elif record.get("record_type") == "shard_completed":
            completions.append(record)

    selected = run_id
    if selected is None and starts:
        selected = starts[-1].get("run_id")
    if selected is None and completions:
        selected = completions[-1].get("run_id")
    latest: dict[int, dict] = {}
    for record in completions:
        if record.get("run_id") == selected and isinstance(record.get("shard_index"), int):
            latest[record["shard_index"]] = record
    return selected, latest


def _recorded_shard_count(
    path: Path, run_id: str | None, requested: int | None
) -> int:
    """Return an explicit shard count or infer it from the selected run.

    Modern run-start and completion records both carry ``shard_count``.  This
    keeps status/merge faithful to a non-default launch without making the
    operator repeat topology already committed to the manifest.  Legacy rows
    without that field remain fail-closed and require ``--shards`` explicitly.
    """
    if requested is not None:
        return requested
    if path.exists():
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if record.get("run_id") != run_id:
                continue
            shard_count = record.get("shard_count")
            if isinstance(shard_count, int) and shard_count > 0:
                return shard_count
    raise ValueError(
        f"cannot infer shard count for run {run_id or 'unknown'}; "
        "pass --shards explicitly for a legacy manifest"
    )


def report_status(
    path: Path, run_id: str | None, shard_count: int | None
) -> dict[str, Any]:
    """Print partial progress without failing when shards are outstanding."""
    selected, records = read_run_records(path, run_id)
    shard_count = _recorded_shard_count(path, selected, shard_count)
    reported = sorted(records)
    missing = [index for index in range(shard_count) if index not in records]
    failed = sorted(
        index for index, record in records.items() if record.get("status") != "succeeded"
    )
    status = {
        "run_id": selected,
        "shard_count": shard_count,
        "shards_reported": reported,
        "shards_missing": missing,
        "shards_failed": failed,
    }
    print(
        f"[status] run_id={selected or 'none'} reported={len(reported)}/{shard_count} "
        f"missing={missing or 'none'} failed={failed or 'none'}",
        flush=True,
    )
    return status


def merge_run(
    path: Path, run_id: str | None, shard_count: int | None, out_path: Path
) -> dict[str, Any]:
    """Write a final summary only when every expected shard succeeded."""
    selected, records = read_run_records(path, run_id)
    shard_count = _recorded_shard_count(path, selected, shard_count)
    missing = [index for index in range(shard_count) if index not in records]
    if missing:
        raise RuntimeError(f"cannot merge run {selected or 'unknown'}; missing shards {missing}")
    failed = [index for index in range(shard_count) if records[index].get("status") != "succeeded"]
    if failed:
        raise RuntimeError(f"cannot merge run {selected}; failed shards {failed}")
    summary = {
        "run_id": selected,
        "shard_count": shard_count,
        "status": "succeeded",
        "shards": [records[index] for index in range(shard_count)],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[merge] run_id={selected} all {shard_count} shards succeeded -> {out_path}", flush=True)
    return summary


def _run_git(args: list[str], repo_root: Path = REPO_ROOT) -> tuple[int, str, str]:
    """Run one bounded git command for the inert manifest relay."""
    proc = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def commit_and_push_manifest(path: Path, repo_root: Path = REPO_ROOT) -> bool:
    """Commit and push only the compact manifest; never fail the data batch.

    A concurrent manifest relay may advance the remote first.  Retry that
    normal race with a bounded pull-rebase/push cycle, while leaving the local
    data and commit intact if network or branch state prevents synchronization.
    """
    try:
        relative_path = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        print("[git] manifest is outside the repository; relay skipped", flush=True)
        return False
    rc, _out, err = _run_git(["add", relative_path.as_posix()], repo_root)
    if rc != 0:
        print(f"[git] manifest add failed: {err.strip()}", flush=True)
        return False
    rc, _out, _err = _run_git(
        ["diff", "--cached", "--quiet", "--", relative_path.as_posix()], repo_root
    )
    if rc == 0:
        print("[git] manifest unchanged, nothing to push", flush=True)
        return True
    rc, _out, err = _run_git(
        [
            "commit",
            "--only",
            "-m",
            f"Record {relative_path.name} results (automated)",
            "--",
            relative_path.as_posix(),
        ],
        repo_root,
    )
    if rc != 0:
        print(f"[git] manifest commit failed: {err.strip()}", flush=True)
        return False
    for attempt in range(1, GIT_PUSH_ATTEMPTS + 1):
        rc, _out, err = _run_git(["push"], repo_root)
        if rc == 0:
            print(
                f"[git] pushed {relative_path} "
                f"(attempt {attempt}/{GIT_PUSH_ATTEMPTS})",
                flush=True,
            )
            return True
        print(
            f"[git] manifest push attempt {attempt}/{GIT_PUSH_ATTEMPTS} failed: "
            f"{err.strip()}",
            flush=True,
        )
        if attempt < GIT_PUSH_ATTEMPTS:
            rc_pull, _out, pull_err = _run_git(["pull", "--rebase"], repo_root)
            if rc_pull != 0:
                print(f"[git] pull --rebase failed: {pull_err.strip()}", flush=True)
            time.sleep(GIT_PUSH_BACKOFF_SECONDS[attempt - 1])
    print(
        "[git] manifest relay exhausted its retries; data and local commit "
        "remain safe",
        flush=True,
    )
    return False


def _child_environment(repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """Pin the project venv/cache and prevent native-library oversubscription."""
    env = os.environ.copy()
    env.update(THREAD_LIMIT_ENV)
    env["UV_CACHE_DIR"] = str(repo_root / ".uv-cache")
    env["PYTHONPATH"] = str(repo_root / "src")
    env["VIRTUAL_ENV"] = str(repo_root / ".venv")
    env["PATH"] = f"{repo_root / '.venv' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def _relay_output(stream: IO[str], log_handle: IO[str], shard_index: int) -> None:
    """Copy one child's stdout to its log and the shared prefixed terminal."""
    for line in stream:
        log_handle.write(line)
        log_handle.flush()
        print(f"[shard {shard_index}] {line}", end="", flush=True)


def _terminate_running(shards: dict[int, RunningShard]) -> None:
    """Terminate every still-running child process group, then force-kill stragglers."""
    for shard in shards.values():
        if shard.process.poll() is None:
            os.killpg(shard.process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 10.0
    for shard in shards.values():
        remaining = max(0.0, deadline - time.monotonic())
        if shard.process.poll() is None:
            try:
                shard.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(shard.process.pid, signal.SIGKILL)


def run_shards(config: LaunchConfig, run_id: str, repo_root: Path = REPO_ROOT) -> int:
    """Launch all shards concurrently and return zero only if all succeed."""
    active_marker = repo_root / "Logs/tier3_pilot.active.json"
    if active_marker.exists():
        raise RuntimeError(f"active operator run marker present: {active_marker}")
    if not (repo_root / ".venv/bin/python").exists():
        raise RuntimeError("repo-local .venv is missing; restore it before launching downloads")
    if shutil.which("caffeinate") is None:
        raise RuntimeError("caffeinate is required for long-running macOS downloads")

    _selected, previous = read_run_records(repo_root / config.manifest_path, run_id)
    successful_previous = {
        index for index, record in previous.items() if record.get("status") == "succeeded"
    }
    indices = [
        index
        for index in range(config.shard_count)
        if not (config.resume and index in successful_previous)
    ]
    if not indices:
        print(f"[resume] run_id={run_id} all shards already succeeded", flush=True)
        return 0

    run_dir = repo_root / config.run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = repo_root / config.manifest_path
    append_manifest_record(
        manifest,
        {
            "record_type": "run_started",
            "run_id": run_id,
            "script": config.script.as_posix(),
            "shard_count": config.shard_count,
            "workers_per_shard": config.workers,
            "aggregate_workers": config.shard_count * config.workers,
            "started_at_utc": _utc_now(),
        },
    )

    env = _child_environment(repo_root)
    running: dict[int, RunningShard] = {}
    completed = len(successful_previous) if config.resume else 0
    batch_start = time.monotonic()
    exit_code = 0
    try:
        for index in indices:
            command = build_shard_command(config, index)
            log_path = run_dir / f"shard_{index:02d}.log"
            log_handle = log_path.open("a", encoding="utf-8")
            started_at = _utc_now()
            process = subprocess.Popen(
                command,
                cwd=repo_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            if process.stdout is None:  # pragma: no cover - guaranteed by stdout=PIPE
                raise RuntimeError("child stdout pipe was not created")
            thread = threading.Thread(
                target=_relay_output,
                args=(process.stdout, log_handle, index),
                daemon=True,
            )
            thread.start()
            running[index] = RunningShard(
                index=index,
                process=process,
                log_path=log_path,
                log_handle=log_handle,
                output_thread=thread,
                started_monotonic=time.monotonic(),
                started_at_utc=started_at,
            )
            print(
                f"[launcher] started shard {index}/{config.shard_count} pid={process.pid}",
                flush=True,
            )

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
                status = "succeeded" if return_code == 0 else "failed"
                append_manifest_record(
                    manifest,
                    {
                        "record_type": "shard_completed",
                        "run_id": run_id,
                        "script": config.script.as_posix(),
                        "shard_index": index,
                        "shard_count": config.shard_count,
                        "workers": config.workers,
                        "status": status,
                        "return_code": return_code,
                        "started_at_utc": shard.started_at_utc,
                        "completed_at_utc": _utc_now(),
                        "elapsed_seconds": round(elapsed, 2),
                        "log_path": shard.log_path.relative_to(repo_root).as_posix(),
                    },
                )
                completed += 1
                batch_elapsed = time.monotonic() - batch_start
                eta = (batch_elapsed / completed) * (config.shard_count - completed)
                print(
                    f"[launcher] shard {index} {status}; completed "
                    f"{completed}/{config.shard_count} "
                    f"elapsed {_fmt_duration(batch_elapsed)} ETA {_fmt_duration(eta)}",
                    flush=True,
                )
                if return_code != 0:
                    exit_code = return_code or 1
                    _terminate_running(running)
                    break
            if exit_code:
                break
    except KeyboardInterrupt:
        print("[launcher] interrupted; terminating all child shards", flush=True)
        _terminate_running(running)
        exit_code = 130
    except Exception:
        _terminate_running(running)
        raise
    finally:
        for shard in running.values():
            shard.output_thread.join()
            shard.log_handle.close()

    commit_and_push_manifest(manifest, repo_root)
    if exit_code == 0:
        merge_run(
            manifest,
            run_id,
            config.shard_count,
            run_dir / "summary.json",
        )
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    """Create the operator-facing CLI parser with conservative defaults."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--script", type=Path, help="Native shard-aware downloader under Skills/.")
    parser.add_argument(
        "--shards",
        type=int,
        default=None,
        help=(
            f"Shard count (launch default: {DEFAULT_SHARDS}; status/merge default: "
            "infer from the selected manifest run)."
        ),
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--estimated-download-gb", type=float)
    parser.add_argument("--max-project-data-gb", type=float, default=DEFAULT_MAX_PROJECT_DATA_GB)
    parser.add_argument("--min-free-gb", type=float, default=DEFAULT_MIN_FREE_GB)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--run-root", type=Path, default=RUN_ROOT)
    parser.add_argument("--run-id", help="Explicit status/merge run ID; defaults to latest run.")
    parser.add_argument(
        "--resume", action="store_true", help="Skip shards already recorded successful."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print child commands and storage plan only."
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report partial manifest progress; never fails on missing shards.",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Fail-closed final manifest check without launching children.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Commit/push the existing local manifest without launching children.",
    )
    parser.add_argument(
        "child_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to every child after `--`.",
    )
    return parser


def main() -> None:
    """Validate the requested batch, then inspect, report, or launch it."""
    args = _build_parser().parse_args()
    if (args.shards is not None and args.shards < 1) or args.workers < 1:
        raise SystemExit("--shards and --workers must both be >= 1")
    if args.status:
        try:
            report_status(args.manifest, args.run_id, args.shards)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return
    if args.merge:
        selected = args.run_id or "latest"
        try:
            merge_run(
                args.manifest,
                args.run_id,
                args.shards,
                args.run_root / selected / "summary.json",
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        return
    if args.sync:
        manifest = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
        if not manifest.is_file():
            raise SystemExit(f"manifest does not exist: {manifest}")
        commit_and_push_manifest(manifest)
        return
    if args.script is None:
        raise SystemExit("--script is required unless --status, --merge, or --sync is used")
    if args.estimated_download_gb is None:
        raise SystemExit("--estimated-download-gb is required before a download launch")

    args.shards = args.shards or DEFAULT_SHARDS

    child_args = _strip_remainder_separator(args.child_args)
    try:
        _validate_child_args(child_args)
        script = validate_target_script(args.script)
        config = LaunchConfig(
            script=script,
            child_args=child_args,
            shard_count=args.shards,
            workers=args.workers,
            estimated_download_gb=args.estimated_download_gb,
            max_project_data_gb=args.max_project_data_gb,
            min_free_gb=args.min_free_gb,
            manifest_path=args.manifest,
            run_root=args.run_root,
            resume=args.resume,
        )
        storage = check_storage_budget(config)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc

    run_id = args.run_id or compute_run_id(script, child_args, args.shards, args.workers)
    print(
        f"[plan] run_id={run_id} script={script} shards={args.shards} "
        f"workers_per_shard={args.workers} aggregate_workers={args.shards * args.workers}",
        flush=True,
    )
    print(
        f"[storage] current={storage['current_project_data_gb']:.1f} GB "
        f"estimated_add={storage['estimated_download_gb']:.1f} GB "
        f"projected={storage['projected_project_data_gb']:.1f}/"
        f"{args.max_project_data_gb:.1f} GB free_after={storage['projected_free_space_gb']:.1f} GB",
        flush=True,
    )
    for index in range(args.shards):
        print(f"[command {index}] {' '.join(build_shard_command(config, index))}", flush=True)
    if args.dry_run:
        print("[dry-run] no child processes started and no manifest records written", flush=True)
        return
    raise SystemExit(run_shards(config, run_id))


if __name__ == "__main__":
    main()
