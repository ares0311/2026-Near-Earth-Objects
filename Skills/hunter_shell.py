#!/usr/bin/env python
"""Persistent terminal application for the canonical NEO-Hunter workflow.

This module is deliberately a thin operator shell. Slash commands are translated
to ``Skills/hunter_cli.py`` arguments; discovery, ranking, durable search
creation, execution, scoring, and persistence remain owned by that one canonical
pipeline.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

try:
    import readline
except ImportError:  # pragma: no cover - readline ships with the supported macOS runtime
    readline = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HISTORY_PATH = REPO_ROOT / "Logs" / "neo_hunter_history"

_SLASH_COMMANDS = (
    "/New-Search",
    "/Follow-Up-Search",
    "/Run-Search",
    "/Show-Follow-Ups",
    "/Help",
    "/Exit",
)
_ALIASES = {
    "/create-new-search": "/new-search",
    "/run-new-search": "/run-search",
}
_ORBIT_FRAMES = (
    "o-----*-----.",
    ".--o--*-----.",
    ".-----*--o--.",
    ".-----*-----o",
)
_RESET = "\033[0m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"

Runner = Callable[[list[str] | None], int]
InputFunction = Callable[[str], str]


def _canonical_runner(argv: list[str] | None) -> int:
    """Delegate to the one production orchestration module."""
    from hunter_cli import main as hunter_main

    return hunter_main(argv)


def _completion_candidates(prefix: str) -> list[str]:
    folded = prefix.casefold()
    return [command for command in _SLASH_COMMANDS if command.casefold().startswith(folded)]


def _readline_complete(text: str, state: int) -> str | None:
    matches = _completion_candidates(text)
    return matches[state] if state < len(matches) else None


def _configure_history(path: Path, err: TextIO) -> bool:
    if readline is None:
        print("History/autocomplete unavailable: Python readline is not installed.", file=err)
        return False
    readline.set_completer_delims(" \t\n")
    readline.set_completer(_readline_complete)
    binding = (
        "bind ^I rl_complete"
        if "libedit" in str(getattr(readline, "__doc__", "")).casefold()
        else "tab: complete"
    )
    readline.parse_and_bind(binding)
    if path.exists():
        try:
            readline.read_history_file(path)
        except OSError as exc:
            print(f"History warning: could not read {path}: {exc}", file=err)
    return True


def _save_history(path: Path, enabled: bool, err: TextIO) -> None:
    if not enabled or readline is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        readline.write_history_file(path)
    except OSError as exc:
        print(f"History warning: could not write {path}: {exc}", file=err)


def _terminal_capabilities(
    stream: TextIO,
    *,
    no_color: bool,
    no_animation: bool,
) -> tuple[bool, bool]:
    is_tty = bool(getattr(stream, "isatty", lambda: False)())
    color = (
        is_tty
        and not no_color
        and "NO_COLOR" not in os.environ
        and os.environ.get("TERM", "") != "dumb"
    )
    animation = (
        is_tty
        and not no_animation
        and "NEOHUNTER_NO_ANIMATION" not in os.environ
        and "CI" not in os.environ
    )
    return color, animation


def _paint(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{_RESET}" if enabled else text


def _orbital_event(
    label: str,
    detail: str,
    *,
    stream: TextIO,
    color: bool,
    animation: bool,
    delay_seconds: float = 0.045,
) -> None:
    """Render a bounded NEO orbital sweep before a real pipeline stage."""
    if animation:
        for frame in _ORBIT_FRAMES:
            stream.write(
                "\r"
                + _paint(frame, _CYAN, color)
                + " "
                + _paint(label, _GREEN, color)
                + f": {detail}"
            )
            stream.flush()
            time.sleep(delay_seconds)
        stream.write("\r\033[2K")
    print(
        f"{_paint('orbital-sweep', _CYAN, color)} "
        f"{_paint(label, _GREEN, color)}: {detail}",
        file=stream,
        flush=True,
    )


def _print_command_help(stream: TextIO, color: bool) -> None:
    title = _paint("NEOHunter slash commands", _CYAN, color)
    print(f"\n{title}", file=stream)
    print(
        "  /New-Search <N> [--neo-class all|aten|ieo] [options]\n"
        "      Select and durably reserve the best available N new targets.\n"
        "  /Follow-Up-Search <N> [--neo-class all|aten|ieo] [options]\n"
        "      Rank validated prior-search evidence for additional work.\n"
        "  /Run-Search [<search-id>|--latest] [options]\n"
        "      Execute or resume the exact durable pending manifest.\n"
        "  /Show-Follow-Ups [--status open|actioned|dismissed|expired|all]\n"
        "      Show durable follow-up evidence and recommended next actions.\n"
        "  /Help\n"
        "      Show this command reference.\n"
        "  /Exit\n"
        "      Leave NEOHunter.\n",
        file=stream,
    )
    print(
        _paint(
            "Type / and press Enter to redisplay commands; press Tab to complete a slash command.",
            _DIM,
            color,
        ),
        file=stream,
    )


def _translate_command(line: str) -> tuple[str, list[str] | None]:
    try:
        tokens = shlex.split(line)
    except ValueError as exc:
        raise ValueError(f"could not parse command: {exc}") from exc
    if not tokens:
        return "noop", None

    raw_command = tokens[0].casefold()
    raw_command = _ALIASES.get(raw_command, raw_command)
    rest = tokens[1:]
    if raw_command == "/":
        return "help", None
    if raw_command == "/help":
        if rest:
            raise ValueError("usage: /Help")
        return "help", None
    if raw_command == "/exit":
        if rest:
            raise ValueError("usage: /Exit")
        return "exit", None
    if raw_command in {"/new-search", "/follow-up-search"}:
        if not rest:
            raise ValueError(f"usage: {tokens[0]} <N> [scientific constraints/options]")
        try:
            requested_n = int(rest[0])
        except ValueError as exc:
            raise ValueError(f"{tokens[0]} requires an integer target count N") from exc
        if requested_n <= 0:
            raise ValueError("target count N must be positive")
        mode = "new" if raw_command == "/new-search" else "follow-up"
        return (
            "new-search" if mode == "new" else "follow-up-search",
            [
                "create-new-search",
                "--targets",
                str(requested_n),
                "--mode",
                mode,
                *rest[1:],
            ],
        )
    if raw_command == "/run-search":
        if not rest:
            rest = ["--latest"]
        elif not rest[0].startswith("-"):
            rest = ["--search-id", rest[0], *rest[1:]]
        return "run-search", ["run-new-search", *rest]
    if raw_command == "/show-follow-ups":
        return "show-follow-ups", ["show-follow-ups", *rest]
    raise ValueError(
        f"unknown command {tokens[0]!r}; type / and press Enter to list commands"
    )


def _pipeline_event(kind: str) -> tuple[str, str]:
    if kind == "new-search":
        return (
            "adaptive discovery",
            "rank broad universe -> exact-product preflight -> durable manifest",
        )
    if kind == "follow-up-search":
        return (
            "trajectory revisit",
            "validated history -> additional-work value -> exact manifest",
        )
    if kind == "run-search":
        return (
            "exact search execution",
            "acquire -> preprocess -> link -> score -> persist -> update history",
        )
    return (
        "follow-up radar",
        "read durable evidence -> priority -> recommended action",
    )


def execute_slash_command(
    line: str,
    *,
    runner: Runner,
    stream: TextIO,
    err: TextIO,
    color: bool,
    animation: bool,
) -> tuple[bool, int]:
    """Execute one slash command and return ``(should_exit, status)``."""
    try:
        kind, argv = _translate_command(line)
    except ValueError as exc:
        print(_paint(f"ERROR: {exc}", _RED, color), file=err)
        return False, 2

    if kind == "noop":
        return False, 0
    if kind == "help":
        _print_command_help(stream, color)
        return False, 0
    if kind == "exit":
        print(_paint("NEOHunter session closed.", _YELLOW, color), file=stream)
        return True, 0

    label, detail = _pipeline_event(kind)
    _orbital_event(
        label,
        detail,
        stream=stream,
        color=color,
        animation=animation,
    )
    assert argv is not None
    try:
        status = runner(argv)
    except SystemExit as exc:
        if exc.code is None:
            status = 0
        elif isinstance(exc.code, int):
            status = exc.code
        else:
            print(_paint(f"ERROR: {exc.code}", _RED, color), file=err)
            status = 1
    if status != 0:
        print(
            _paint(
                f"Command failed with exit status {status}; durable state is resumable.",
                _RED,
                color,
            ),
            file=err,
        )
    return False, status


def run_interactive(
    *,
    runner: Runner,
    input_function: InputFunction,
    stream: TextIO,
    err: TextIO,
    history_path: Path,
    color: bool,
    animation: bool,
) -> int:
    history_enabled = _configure_history(history_path, err)
    _orbital_event(
        "NEO survey console",
        "canonical Hunter pipeline ready; no external submission",
        stream=stream,
        color=color,
        animation=animation,
    )
    _print_command_help(stream, color)
    prompt = _paint("NEOHunter> ", _GREEN, color)
    try:
        while True:
            try:
                line = input_function(prompt)
            except EOFError:
                print(file=stream)
                return 0
            except KeyboardInterrupt:
                print("\nInterrupted current prompt; type /Exit to leave.", file=stream)
                continue
            should_exit, _status = execute_slash_command(
                line,
                runner=runner,
                stream=stream,
                err=err,
                color=color,
                animation=animation,
            )
            if should_exit:
                return 0
    finally:
        _save_history(history_path, history_enabled, err)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--command",
        action="append",
        default=[],
        help="execute one slash command non-interactively; may be repeated",
    )
    parser.add_argument("--history-file", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--no-animation", action="store_true")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner = _canonical_runner,
    input_function: InputFunction = input,
    stream: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    args = build_parser().parse_args(argv)
    color, animation = _terminal_capabilities(
        stream,
        no_color=args.no_color,
        no_animation=args.no_animation,
    )
    if args.command:
        for command in args.command:
            should_exit, status = execute_slash_command(
                command,
                runner=runner,
                stream=stream,
                err=err,
                color=color,
                animation=animation,
            )
            if should_exit:
                return 0
            if status != 0:
                return status
        return 0
    return run_interactive(
        runner=runner,
        input_function=input_function,
        stream=stream,
        err=err,
        history_path=args.history_file,
        color=color,
        animation=animation,
    )


if __name__ == "__main__":
    raise SystemExit(main())
