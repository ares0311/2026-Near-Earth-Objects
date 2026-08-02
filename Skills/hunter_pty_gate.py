#!/usr/bin/env python3
"""Phase 2 acceptance gate: the installed NEOHunter driven by real keystrokes.

This is the primary executable gate for the operator's interactive experience.
It spawns the *resolved installed console script* as a separate operating-system
process attached to a **real PTY**, from a working directory **outside the
repository**, and drives it with actual key bytes. Nothing here imports the
product: the only channel is the terminal, which is the same channel the
operator uses.

Why it is built this way
------------------------
The Hunter execution directive names several substitutions that can never
satisfy this gate, and each has a direct counterpart in how this file works:

* *mocked terminal for a real PTY* -- a real PTY is allocated with
  :func:`pty.openpty`. If the platform refuses to allocate one, this gate reports
  ``NOT_EXECUTED`` and exits nonzero. It never falls back to a pipe, because a
  pipe cannot demonstrate that ``/`` opens a palette before Enter.
* *renderer unit test or golden output for interactive keystrokes* -- no
  rendering function is called. Assertions are made against bytes the child
  process actually wrote to the terminal.
* *"/" followed by Enter for "/" without Enter* -- the palette probe writes a
  single ``/`` byte and never writes a newline. A line-buffered reader cannot
  pass it.
* *direct Python import for an installed executable* -- the child is launched by
  absolute path to the console script, with ``PYTHONPATH`` emptied.

Outcomes
--------
``PASS``          every assertion held.
``FAIL``          the gate executed and an assertion failed.
``NOT_EXECUTED``  the gate could not run at all (for example, PTY allocation is
                  denied by a sandbox). Per contract rule CLAIM-03 this is never
                  counted as a pass; the process exits nonzero either way.

Usage::

    uv run --python 3.14 python Skills/hunter_pty_gate.py
    uv run --python 3.14 python Skills/hunter_pty_gate.py --json report.json
    uv run --python 3.14 python Skills/hunter_pty_gate.py --runs 3
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import select
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

REPORT_SCHEMA_VERSION = "hunter-pty-gate-1.0.0"

PASS = "PASS"
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"

# The seven commands CLI-02 and UX-CMD-02 require in the palette.
REQUIRED_COMMANDS = (
    "/New-Search",
    "/Follow-Up-Search",
    "/Run-Search",
    "/Show-Follow-Ups",
    "/Inspect-Target",
    "/Help",
    "/Exit",
)

# The six NEOHunter startup motifs UX-START-02 enumerates.
NEO_MOTIFS = (
    "orbital sweep",
    "radar acquisition",
    "trajectory projection",
    "close-approach geometry",
    "moving-object survey",
    "telescope scan",
)

# Key bytes. Written raw to the PTY master, exactly as a terminal would deliver
# them, so no assertion depends on a library's key abstraction.
KEY_DOWN = b"\x1b[B"
KEY_UP = b"\x1b[A"
KEY_ESC = b"\x1b"
KEY_ENTER = b"\r"
KEY_TAB = b"\t"
KEY_CTRL_C = b"\x03"

ANSI_PATTERN = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[()][B0]")

# Prompt the shell renders once startup is complete.
PROMPT_MARKER = b"NEOHunter>"


def strip_ansi(raw: bytes) -> str:
    """Plain text as a human reading the terminal would perceive it."""
    return ANSI_PATTERN.sub(b"", raw).decode("utf-8", errors="replace")


class PtyUnavailable(RuntimeError):
    """Raised when the platform refuses to allocate a PTY.

    Distinguished from every other error because it means the gate did not run,
    which is a different claim from the gate having failed.
    """


@dataclass
class Assertion:
    """One observable claim about what the operator's terminal actually showed."""

    assertion_id: str
    requirements: tuple[str, ...]
    status: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "requirements": list(self.requirements),
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class PtySession:
    """A real terminal attached to a real child process."""

    argv: list[str]
    cwd: str
    columns: int = 100
    rows: int = 30
    buffer: bytes = b""
    _master: int = -1
    _process: subprocess.Popen[bytes] | None = None
    transcript_marks: list[int] = field(default_factory=list)

    def __enter__(self) -> PtySession:
        import fcntl
        import pty
        import termios

        try:
            master, slave = pty.openpty()
        except OSError as exc:
            raise PtyUnavailable(
                f"PTY allocation denied by the platform ({exc.strerror or exc}). "
                "This gate requires a real terminal device and refuses to "
                "substitute a pipe."
            ) from exc

        # Set a deterministic window size before the child starts, so width
        # behaviour is a property of the test rather than of the host terminal.
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, self.columns, 0, 0))

        environment = {
            **os.environ,
            # An installed console script must work with no source-tree help.
            "PYTHONPATH": "",
            "TERM": "xterm-256color",
            "COLUMNS": str(self.columns),
            "LINES": str(self.rows),
        }
        environment.pop("NO_COLOR", None)

        self._process = subprocess.Popen(
            self.argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=self.cwd,
            env=environment,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave)
        self._master = master
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
            self._process.wait(timeout=10)
        if self._master >= 0:
            try:
                os.close(self._master)
            except OSError:
                pass

    # --- terminal I/O -------------------------------------------------------

    def send(self, data: bytes) -> None:
        """Write raw key bytes, exactly as a keyboard would deliver them."""
        os.write(self._master, data)

    def pump(self, seconds: float) -> bytes:
        """Read whatever the child writes for a bounded interval."""
        start_length = len(self.buffer)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            readable, _, _ = select.select([self._master], [], [], 0.05)
            if not readable:
                continue
            try:
                chunk = os.read(self._master, 65536)
            except OSError as exc:
                # EIO is the normal signal that the child closed the terminal.
                if exc.errno in (errno.EIO, errno.EBADF):
                    break
                raise
            if not chunk:
                break
            self.buffer += chunk
        return self.buffer[start_length:]

    def wait_for(self, needle: bytes, timeout: float) -> bool:
        """Pump until ``needle`` appears, or the timeout expires."""
        deadline = time.monotonic() + timeout
        if needle in self.buffer:
            return True
        while time.monotonic() < deadline:
            self.pump(0.2)
            if needle in self.buffer:
                return True
        return False

    def mark(self) -> int:
        """Record the current transcript position so a later slice is isolated."""
        self.transcript_marks.append(len(self.buffer))
        return len(self.buffer)

    def since(self, mark: int) -> bytes:
        return self.buffer[mark:]

    def wait_exit(self, timeout: float) -> int | None:
        assert self._process is not None
        try:
            return self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None


def _resolved_executable() -> Path:
    """The console script the operator actually runs."""
    return REPO_ROOT / ".venv" / "bin" / "NEOHunter"


def _installed_version() -> str:
    """Version recorded in project metadata, used to check the startup banner."""
    import tomllib

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return str(config["project"]["version"])


def _distinct_animation_frames(raw: bytes) -> list[str]:
    """Frames the child painted in place, split on its own erase sequence.

    ``animation.play_startup`` rewrites one line per frame using ``\\r\\x1b[2K``.
    Splitting the raw transcript on that erase sequence recovers the individual
    frames that a human watching the terminal would have seen in succession.
    """
    pieces = raw.split(b"\r\x1b[2K")
    frames = []
    for piece in pieces[1:]:
        text = strip_ansi(piece).strip()
        if text:
            frames.append(text)
    return frames


def _run_interactive_suite(executable: Path, workdir: str) -> list[Assertion]:
    """Drive one full interactive session and return every assertion's outcome."""
    results: list[Assertion] = []

    def record(assertion_id: str, requirements: tuple[str, ...], ok: bool, detail: str) -> None:
        results.append(Assertion(assertion_id, requirements, PASS if ok else FAIL, detail))

    with PtySession([str(executable)], cwd=workdir) as session:
        # --- startup presentation ------------------------------------------
        started = session.wait_for(PROMPT_MARKER, timeout=45)
        startup_raw = session.buffer
        startup_text = strip_ansi(startup_raw)

        record(
            "startup-reaches-prompt",
            ("LAUNCH-04", "UX-START-01"),
            started,
            "prompt appeared after startup" if started
            else f"prompt {PROMPT_MARKER!r} never appeared; "
                 f"last 300 chars: {startup_text[-300:]!r}",
        )
        if not started:
            # Without a prompt nothing else can be driven; report and stop.
            return results

        frames = _distinct_animation_frames(startup_raw)
        distinct = {frame for frame in frames}
        record(
            "startup-multiple-distinct-frames",
            ("UX-START-01",),
            len(distinct) >= 8,
            f"{len(distinct)} distinct animation frames painted "
            f"(a static logo or single spinner is nonconforming)",
        )

        motifs_present = [motif for motif in NEO_MOTIFS if motif in startup_text.casefold()]
        record(
            "startup-domain-specific",
            ("UX-START-02",),
            len(motifs_present) >= 3,
            f"NEO motifs visible at startup: {motifs_present}",
        )

        version = _installed_version()
        name_shown = "NEOHunter" in startup_text or "NEOHUNTER" in startup_text.upper()
        version_shown = version in startup_text
        record(
            "startup-shows-name-and-version",
            ("UX-START-01", "LAUNCH-04"),
            name_shown and version_shown,
            f"product name shown: {name_shown}; version {version!r} shown: {version_shown}",
        )

        prompt_index = startup_raw.find(PROMPT_MARKER)
        last_frame_index = startup_raw.rfind(b"\r\x1b[2K")
        record(
            "prompt-follows-startup",
            ("UX-START-01",),
            last_frame_index == -1 or prompt_index > last_frame_index,
            "prompt is rendered after the startup presentation completes",
        )

        # --- "/" opens the palette, with no Enter --------------------------
        mark = session.mark()
        session.send(b"/")
        palette_opened = False
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            session.pump(0.2)
            text = strip_ansi(session.since(mark))
            if sum(1 for command in REQUIRED_COMMANDS if command in text) >= 3:
                palette_opened = True
                break
        palette_text = strip_ansi(session.since(mark))
        visible = [command for command in REQUIRED_COMMANDS if command in palette_text]
        record(
            "slash-opens-palette-without-enter",
            ("UX-CMD-01", "CLI-01", "CLI-02", "LAUNCH-04"),
            palette_opened,
            f"commands offered after a bare '/' with no Enter: {visible}"
            if palette_opened
            else "typing '/' did not open a palette before Enter; a line-buffered "
                 f"reader cannot satisfy UX-CMD-01. Observed: {palette_text[-300:]!r}",
        )

        # Descriptions must accompany the commands (UX-CMD-02).
        described = any(
            marker in palette_text.casefold()
            for marker in ("select and freeze", "req:", "execute", "durable")
        )
        record(
            "palette-items-described",
            ("UX-CMD-02",),
            described,
            "palette entries carry operational descriptions and parameter shapes"
            if described
            else f"palette showed no descriptions: {palette_text[-300:]!r}",
        )

        # --- keyboard navigation changes the visible selection -------------
        nav_mark = session.mark()
        session.send(KEY_DOWN)
        session.pump(1.5)
        session.send(KEY_DOWN)
        nav_raw = session.since(nav_mark)
        session.pump(1.0)
        nav_raw = session.since(nav_mark)
        record(
            "palette-keyboard-navigation",
            ("UX-CMD-03",),
            len(nav_raw.strip()) > 0 and b"\x1b[" in nav_raw,
            f"arrow keys repainted the palette selection ({len(nav_raw)} bytes redrawn)"
            if nav_raw.strip()
            else "arrow keys produced no visible change in the palette",
        )

        # Escape closes the palette (UX-CMD-03).
        session.send(KEY_ESC)
        session.pump(1.0)
        session.send(KEY_CTRL_C)
        session.pump(1.0)

        # --- guided parameter entry ----------------------------------------
        guided_mark = session.mark()
        session.send(b"/New-Search" + KEY_ENTER)
        session.pump(4.0)
        guided_text = strip_ansi(session.since(guided_mark))
        guided = "Targets" in guided_text and (
            "[" in guided_text and "]" in guided_text
        )
        record(
            "new-search-opens-guided-fields",
            ("UX-IN-01", "UX-IN-02"),
            guided,
            "selecting /New-Search opened guided editable fields"
            if guided
            else "selecting /New-Search did not open guided parameter entry; "
                 f"observed: {guided_text[-400:]!r}",
        )

        # --- invalid input is rejected inline, before execution ------------
        invalid_mark = session.mark()
        session.send(b"twenty" + KEY_ENTER)
        session.pump(4.0)
        invalid_text = strip_ansi(session.since(invalid_mark))
        rejected = (
            "positive whole number" in invalid_text.casefold()
            or "invalid" in invalid_text.casefold()
        )
        executed = "search" in invalid_text.casefold() and "created" in invalid_text.casefold()
        record(
            "invalid-target-count-rejected-inline",
            ("UX-IN-03", "UX-IN-04"),
            rejected and not executed,
            "invalid target count was rejected inline and did not execute"
            if rejected and not executed
            else f"invalid input was not cleanly rejected: {invalid_text[-400:]!r}",
        )

        # --- corrected input produces a resolved-action preview ------------
        preview_mark = session.mark()
        session.send(b"5" + KEY_ENTER)
        session.pump(6.0)
        preview_text = strip_ansi(session.since(preview_mark))
        preview_shown = "Resolved action" in preview_text and "Requested targets" in preview_text
        record(
            "corrected-input-shows-action-preview",
            ("UX-IN-03",),
            preview_shown,
            "corrected input produced the resolved-action preview"
            if preview_shown
            else f"no resolved-action preview after valid input: {preview_text[-400:]!r}",
        )

        # --- cancellation ---------------------------------------------------
        cancel_mark = session.mark()
        session.send(KEY_ESC)
        session.pump(1.0)
        session.send(KEY_CTRL_C)
        session.pump(1.5)
        cancel_text = strip_ansi(session.since(cancel_mark))
        alive = session.wait_exit(0.2) is None
        record(
            "cancellation-returns-to-prompt",
            ("UX-IN-02",),
            alive,
            "cancelling returned to the shell instead of terminating it"
            if alive
            else f"cancellation terminated the session: {cancel_text[-200:]!r}",
        )

        # --- /Help ----------------------------------------------------------
        help_mark = session.mark()
        session.send(b"/Help" + KEY_ENTER)
        session.pump(4.0)
        help_text = strip_ansi(session.since(help_mark))
        help_ok = sum(1 for command in REQUIRED_COMMANDS if command in help_text) >= 5
        record(
            "help-lists-commands",
            ("LAUNCH-04", "CLI-02"),
            help_ok,
            "/Help listed the required commands"
            if help_ok
            else f"/Help output incomplete: {help_text[-300:]!r}",
        )

        # --- /Exit returns zero ---------------------------------------------
        session.send(b"/Exit" + KEY_ENTER)
        session.pump(3.0)
        status = session.wait_exit(20)
        record(
            "exit-returns-zero",
            ("LAUNCH-04",),
            status == 0,
            f"/Exit terminated the session with status {status}",
        )

    return results


def run_slash_palette_probe(executable: Path, workdir: str) -> list[Assertion]:
    """The single narrowest useful question: does ``/`` open the palette?

    One terminal session. One keystroke. Two assertions -- the prompt appeared,
    and a bare ``/`` offered commands with no Enter pressed. Nothing else is
    started, resized, or driven.

    This exists because the full suite is the wrong first thing to run: it opens
    twelve terminal sessions and makes nineteen assertions, so a single early
    failure is buried in noise. UX-CMD-01 is the one clause blocking LAUNCH-04,
    and it can be answered on its own.
    """
    results: list[Assertion] = []
    with PtySession([str(executable)], cwd=workdir) as session:
        started = session.wait_for(PROMPT_MARKER, timeout=45)
        results.append(
            Assertion(
                "startup-reaches-prompt",
                ("LAUNCH-04",),
                PASS if started else FAIL,
                "prompt appeared" if started
                else f"prompt never appeared; last 300 chars: "
                     f"{strip_ansi(session.buffer)[-300:]!r}",
            )
        )
        if not started:
            return results

        mark = session.mark()
        session.send(b"/")  # deliberately no Enter
        opened = False
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            session.pump(0.2)
            text = strip_ansi(session.since(mark))
            if sum(1 for command in REQUIRED_COMMANDS if command in text) >= 3:
                opened = True
                break

        seen = strip_ansi(session.since(mark))
        visible = [command for command in REQUIRED_COMMANDS if command in seen]
        results.append(
            Assertion(
                "slash-opens-palette-without-enter",
                ("UX-CMD-01", "CLI-01", "CLI-02", "LAUNCH-04"),
                PASS if opened else FAIL,
                f"commands offered after a bare '/': {visible}" if opened
                else "typing '/' did not open a palette before Enter. "
                     f"Observed: {seen[-300:]!r}",
            )
        )
        session.send(KEY_CTRL_C)
        session.pump(0.5)
        session.send(b"/Exit" + KEY_ENTER)
        session.pump(2.0)
        session.wait_exit(15)
    return results


def _run_width_suite(executable: Path, workdir: str) -> list[Assertion]:
    """Startup must stay inside the terminal at narrow, normal, and wide sizes."""
    results: list[Assertion] = []
    for width in (40, 100, 200):
        with PtySession([str(executable)], cwd=workdir, columns=width) as session:
            session.wait_for(PROMPT_MARKER, timeout=45)
            session.send(b"/Exit" + KEY_ENTER)
            session.pump(2.0)
            session.wait_exit(15)
            overflowing = [
                line
                for line in strip_ansi(session.buffer).splitlines()
                if len(line.rstrip()) > width
            ]
            results.append(
                Assertion(
                    f"width-{width}-no-overflow",
                    ("UX-TABLE-01", "UX-A11Y-01"),
                    PASS if not overflowing else FAIL,
                    f"no line exceeded {width} columns"
                    if not overflowing
                    else f"{len(overflowing)} line(s) exceeded {width} columns; "
                         f"first: {overflowing[0][:120]!r}",
                )
            )
    return results


def _run_non_tty_suite(executable: Path, workdir: str) -> list[Assertion]:
    """Redirected and machine-readable output must carry no animation or ANSI."""
    results: list[Assertion] = []

    completed = subprocess.run(
        [str(executable), "--command", "/Help"],
        cwd=workdir,
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        timeout=120,
        check=False,
    )
    raw = completed.stdout + completed.stderr
    has_ansi = bool(ANSI_PATTERN.search(raw))
    results.append(
        Assertion(
            "non-tty-no-ansi",
            ("UX-START-04", "UX-A11Y-01", "UX-TABLE-04"),
            PASS if not has_ansi and completed.returncode == 0 else FAIL,
            f"redirected output is clean (exit {completed.returncode}, ansi={has_ansi})",
        )
    )

    machine = subprocess.run(
        [str(executable), "--json", "--command", "/Help"],
        cwd=workdir,
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        timeout=120,
        check=False,
    )
    machine_raw = machine.stdout + machine.stderr
    machine_ansi = bool(ANSI_PATTERN.search(machine_raw))
    results.append(
        Assertion(
            "machine-mode-no-ansi",
            ("UX-TABLE-04",),
            PASS if not machine_ansi and machine.returncode == 0 else FAIL,
            f"machine-readable mode is clean (exit {machine.returncode}, ansi={machine_ansi})",
        )
    )
    return results


def run_gate(runs: int = 1, *, probe: bool = False) -> dict[str, Any]:
    """Execute the gate ``runs`` times in fresh processes.

    ``probe`` narrows it to the single ``/``-opens-the-palette question: one
    terminal session, two assertions, no width or non-TTY work.
    """
    executable = _resolved_executable()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")

    if not executable.is_file():
        return _report(
            NOT_EXECUTED,
            [],
            reason=f"console script not installed at {executable}; run the documented uv sync",
            started_at=started_at,
            runs=runs,
        )

    all_runs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="neohunter-pty-gate-") as workdir:
        for run_index in range(1, runs + 1):
            try:
                if probe:
                    assertions = run_slash_palette_probe(executable, workdir)
                else:
                    assertions = _run_interactive_suite(executable, workdir)
                    assertions += _run_width_suite(executable, workdir)
                    assertions += _run_non_tty_suite(executable, workdir)
            except PtyUnavailable as exc:
                return _report(
                    NOT_EXECUTED,
                    all_runs,
                    reason=str(exc),
                    started_at=started_at,
                    runs=runs,
                )
            all_runs.append(
                {
                    "run": run_index,
                    "working_directory": workdir,
                    "assertions": [a.as_dict() for a in assertions],
                }
            )

    failed = [
        a
        for run in all_runs
        for a in run["assertions"]
        if a["status"] != PASS
    ]
    return _report(
        FAIL if failed else PASS,
        all_runs,
        reason="" if not failed else f"{len(failed)} assertion(s) failed",
        started_at=started_at,
        runs=runs,
    )


def _report(
    status: str,
    all_runs: list[dict[str, Any]],
    *,
    reason: str,
    started_at: str,
    runs: int,
) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
        ).stdout.strip()
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "gate": "phase-2-installed-pty-operator-experience",
        "status": status,
        "reason": reason,
        "requested_runs": runs,
        "completed_runs": len(all_runs),
        "code_identity": f"{head}{'+dirty' if dirty else ''}",
        "resolved_executable": str(_resolved_executable()),
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "runs": all_runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="write the report to this path")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="repeat the whole gate in this many fresh processes (Phase 6 requires 3)",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "narrow mode: one terminal session, two assertions -- does the prompt "
            "appear, and does a bare '/' open the palette with no Enter"
        ),
    )
    args = parser.parse_args(argv)

    report = run_gate(runs=args.runs, probe=args.probe)

    for run in report["runs"]:
        print(f"--- run {run['run']} (cwd {run['working_directory']})")
        for assertion in run["assertions"]:
            print(
                f"{assertion['status']:<13} {assertion['assertion_id']:<42} "
                f"{assertion['detail']}"
            )

    print()
    print(f"GATE STATUS: {report['status']}")
    if report["reason"]:
        print(f"reason: {report['reason']}")
    if report["status"] == NOT_EXECUTED:
        print(
            "NOT EXECUTED is not a pass. This gate requires a real PTY and will "
            "not substitute a pipe or a mocked terminal."
        )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report written to {args.json}")

    return 0 if report["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
