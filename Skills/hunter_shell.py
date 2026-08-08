#!/usr/bin/env python
"""Persistent terminal application for the canonical NEO-Hunter workflow.

This module is deliberately a thin operator shell. Slash commands are translated
to ``Skills/hunter_cli.py`` arguments; discovery, ranking, durable search
creation, execution, scoring, and persistence remain owned by that one canonical
pipeline, as ``docs/CLI_UX_SPEC.md`` section 12 requires.

Interaction and presentation live in :mod:`Skills.hunter_ux`:

* command catalogue, help, and argument construction -- ``hunter_ux.registry``;
* shared validators for interactive and scriptable input -- ``hunter_ux.validation``;
* terminal capability detection and degradation -- ``hunter_ux.theme``;
* NEO-domain startup and stage animation -- ``hunter_ux.animation``;
* width-aware tables and the target detail view -- ``hunter_ux.table``;
* resolved-action preview and failure presentation -- ``hunter_ux.preview``;
* the searchable palette and guided entry -- ``hunter_ux.palette``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

import hunter_state
from hunter_config import get_hunter_paths

if __package__:
    from .hunter_ux import animation, palette, preview, registry, table, theme
else:  # pragma: no cover - direct script execution outside the package
    from hunter_ux import animation, palette, preview, registry, table, theme

try:
    import readline
except ImportError:  # pragma: no cover - readline ships with the supported macOS runtime
    readline = None  # type: ignore[assignment]

DEFAULT_HISTORY_PATH = get_hunter_paths().shell_history

Runner = Callable[[list[str] | None], int]
InputFunction = Callable[[str], str]

# Supplies one guided field's raw text. Returns ``palette.CANCELLED`` when the
# operator escapes out. ``None`` in the shell means "not interactive", which is
# what keeps ``--command`` scripting free of prompts.
FieldReader = Callable[[registry.ParamSpec, str], object]

# Asks the operator to confirm a resolved action before a search is frozen.
Confirmer = Callable[[list[str]], bool]
StateProvider = Callable[[], registry.ShellState]

# Subcommands that freeze a durable manifest. Specification section 8 requires a
# resolved-action preview before this happens, so the operator can confirm, edit,
# or cancel while it is still free to do so.
_FREEZING_SUBCOMMANDS = frozenset({"create-new-search"})


def _durable_shell_state() -> registry.ShellState:
    """Hydrate command availability from the durable lifecycle database."""
    state = hunter_state.get_operator_state(get_hunter_paths().hunter_db)
    return registry.ShellState(
        pending_search_ids=state.pending_search_ids,
        open_follow_up_count=state.open_follow_up_count,
        last_result_count=state.last_result_count,
    )


def _resolved_action_for(
    command: registry.CommandSpec, argv: list[str]
) -> preview.ResolvedAction:
    """Build the preview block from the argument vector about to be executed.

    Every field comes from what was actually resolved, or is left unset so the
    preview renders ``unknown``. Nothing here estimates a quantity the pipeline
    has not reported -- an invented storage or compute figure would be exactly
    the fabricated progress UX-RUN-02 forbids.
    """
    mode = "follow-up" if "follow-up" in command.fixed_args else "new"
    requested = 0
    constraints: dict[str, object] = {}
    for index, token in enumerate(argv):
        if token == "--targets" and index + 1 < len(argv):
            requested = int(argv[index + 1])
        elif token in ("--neo-class", "--max-pool", "--max-download-gb") and index + 1 < len(argv):
            constraints[token.lstrip("-")] = argv[index + 1]
    return preview.ResolvedAction(
        mode=mode,
        requested_targets=requested,
        scientific_constraints=constraints,
        output_behavior="Freeze an exact durable manifest; no acquisition until /Run-Search.",
    )


def _canonical_runner(argv: list[str] | None) -> int:
    """Delegate to the one production orchestration module."""
    if __package__:
        from .hunter_cli import main as hunter_main
    else:
        from hunter_cli import main as hunter_main

    return hunter_main(argv)


def _configure_history(path: Path, err: TextIO) -> bool:
    """Enable history and Tab completion over the registry's command names."""
    if readline is None:
        print("History/autocomplete unavailable: Python readline is not installed.", file=err)
        return False

    def _complete(text: str, state: int) -> str | None:
        matches = [command.name for command in registry.search(text)]
        return matches[state] if state < len(matches) else None

    readline.set_completer_delims(" \t\n")
    readline.set_completer(_complete)
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


def build_argv_from_tokens(
    command: registry.CommandSpec,
    tokens: tuple[str, ...],
) -> tuple[list[str] | None, str | None]:
    """Build an argument vector from typed tokens using the canonical validators.

    Positional tokens fill the command's declared fields in order; anything that
    already looks like a flag is passed through untouched so power users keep
    access to the full scriptable surface. Returning an error message rather than
    raising is what lets the shell answer with an actionable sentinel instead of
    an argparse usage dump (UX-IN-04).
    """
    positional = [token for token in tokens if not token.startswith("-")]
    passthrough: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("-"):
            passthrough.append(token)
            # A flag's value, when present, follows it directly.
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
                passthrough.append(tokens[index + 1])
                index += 1
        index += 1

    # Only positional tokens that are not a flag's value are treated as fields.
    consumed_as_values = set(passthrough)
    field_tokens = [token for token in positional if token not in consumed_as_values]

    values: dict[str, object] = {}
    fields = registry.required_field_order(command, include_advanced=True)
    for spec, raw in zip(fields, field_tokens):
        value, error = spec.validator(raw)
        if error is not None:
            return None, f"{command.name} {spec.label.lower()}: {error}"
        values[spec.name] = value

    for spec in fields:
        if spec.required and spec.name not in values:
            return None, (
                f"{command.name} requires {spec.label.lower()}. "
                f"Usage: {command.name} <{spec.name}>"
            )

    argv = command.build_argv(values)
    argv.extend(passthrough)
    return argv, None


def execute_slash_command(
    line: str,
    *,
    runner: Runner,
    stream: TextIO,
    err: TextIO,
    capabilities: theme.Capabilities,
    state: registry.ShellState | None = None,
    read_field: FieldReader | None = None,
    confirm: Confirmer | None = None,
) -> tuple[bool, int]:
    """Execute one slash command and return ``(should_exit, status)``.

    ``read_field`` and ``confirm`` are the interactive hooks. When both are
    ``None`` -- the scripted ``--command`` path -- behaviour is unchanged: a
    missing required argument produces an actionable message rather than a
    prompt. When they are supplied by the interactive shell, a command invoked
    without its required arguments opens guided entry (UX-IN-01), and a command
    that freezes a durable manifest shows the resolved-action preview and waits
    for confirmation (specification section 8).
    """
    shell_state = state or registry.ShellState()
    stripped = line.strip()
    if not stripped:
        return False, 0

    # A bare slash opens the palette -- the operator never needs /Help to
    # discover commands (UX-CMD-01).
    if stripped == "/":
        for rendered in palette.render_palette("", capabilities, shell_state):
            print(rendered, file=stream)
        return False, 0

    try:
        command, tokens = palette.resolve_command_line(stripped)
    except ValueError as exc:
        print(capabilities.style(f"ERROR: could not parse command: {exc}", "red"), file=err)
        return False, 2

    if command is None:
        # Unknown command: show the palette filtered by what was typed, which is
        # more useful than a bare error.
        print(
            capabilities.style(
                f"Unknown command {stripped.split()[0]!r}. Matching commands:", "yellow"
            ),
            file=err,
        )
        for rendered in palette.render_palette(stripped.split()[0], capabilities, shell_state):
            print(rendered, file=err)
        return False, 2

    if command.name == "/Help":
        print(registry.help_text(shell_state, capabilities.width), file=stream)
        return False, 0
    if command.name == "/Exit":
        print(capabilities.style("NEOHunter session closed.", "yellow"), file=stream)
        return True, 0

    availability = command.availability(shell_state)
    if not availability.enabled:
        print(
            capabilities.style(f"{command.name} unavailable: {availability.reason}", "yellow"),
            file=err,
        )
        return False, 2

    # Interactive path: a command typed without its required arguments opens
    # guided entry instead of answering with an error. This is the only route by
    # which an operator can reach the guided editor, so it must exist in
    # production and not merely be exercised by tests (contract PIPE-02).
    missing_required = any(
        spec.required
        for spec in registry.required_field_order(command, include_advanced=False)
    ) and not [token for token in tokens if not token.startswith("-")]

    if read_field is not None and missing_required:
        guided = palette.run_guided_entry(
            command,
            capabilities,
            read_field=read_field,
            emit=lambda line: print(line, file=stream),
        )
        if guided is palette.CANCELLED:
            print(capabilities.style(f"{command.name} cancelled.", "yellow"), file=stream)
            return False, 0
        assert isinstance(guided, list)
        argv, error = guided, None
    else:
        argv, error = build_argv_from_tokens(command, tokens)

    if error is not None:
        print(capabilities.style(f"ERROR: {error}", "red"), file=err)
        return False, 2

    # Resolved-action preview before anything is frozen (specification section 8).
    assert argv is not None
    if confirm is not None and command.subcommand in _FREEZING_SUBCOMMANDS:
        block = preview.render_preview(_resolved_action_for(command, argv), capabilities)
        if not confirm(block):
            print(capabilities.style(f"{command.name} cancelled.", "yellow"), file=stream)
            return False, 0

    animation.render_stage(
        stream,
        capabilities,
        animation.StageProgress(stage=f"{command.stage_label}: {command.stage_detail}"),
    )
    animation.finish_stage(stream, capabilities)

    assert argv is not None
    try:
        status = runner(argv)
    except SystemExit as exc:
        if exc.code is None:
            status = 0
        elif isinstance(exc.code, int):
            status = exc.code
        else:
            print(capabilities.style(f"ERROR: {exc.code}", "red"), file=err)
            status = 1
    if status != 0:
        diagnostic = preview.diagnostic_id(salt=" ".join(argv))
        for rendered in preview.render_failure(
            summary=f"{command.name} did not complete (exit status {status}).",
            resumable=True,
            diagnostic=diagnostic,
            capabilities=capabilities,
        ):
            print(rendered, file=err)
    return False, status


def run_interactive(
    *,
    runner: Runner,
    input_function: InputFunction,
    stream: TextIO,
    err: TextIO,
    history_path: Path,
    capabilities: theme.Capabilities,
    state_provider: StateProvider = _durable_shell_state,
) -> int:
    """Run the persistent shell until ``/Exit`` or end of input."""
    history_enabled = _configure_history(history_path, err)
    animation.play_startup(stream, capabilities)
    print(registry.help_text(width=capabilities.width), file=stream)
    prompt = capabilities.style("NEOHunter> ", "green")

    def _read_field(spec: registry.ParamSpec, current: str) -> object:
        """Prompt for one guided field; Ctrl-C or EOF cancels the whole form."""
        label = f"  {spec.label} [{current or spec.placeholder()}]: "
        try:
            typed = input_function(capabilities.style(label, "cyan"))
        except (EOFError, KeyboardInterrupt):
            return palette.CANCELLED
        # An empty answer accepts the visible default rather than clearing it.
        return typed.strip() or current

    def _confirm(block: list[str]) -> bool:
        """Show the resolved action and require an explicit confirmation."""
        for line in block:
            print(line, file=stream)
        try:
            answer = input_function(
                capabilities.style("  Confirm? [y/N]: ", "cyan")
            )
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip().casefold() in {"y", "yes"}

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
                capabilities=capabilities,
                state=state_provider(),
                read_field=_read_field,
                confirm=_confirm,
            )
            if should_exit:
                return 0
    finally:
        theme.restore(stream, capabilities)
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
    parser.add_argument(
        "--reduced-motion",
        action="store_true",
        help="accessibility mode: suppress animation while keeping colour",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="machine_readable",
        help="machine-readable output: no animation, colour, or prompts",
    )
    return parser


def _default_input_function(capabilities: theme.Capabilities) -> InputFunction:
    """Choose the line reader that matches the terminal's real capabilities.

    On a real terminal this returns the ``prompt_toolkit``-backed reader, whose
    live completer opens the searchable command palette the moment ``/`` is
    typed -- no Enter required, as UX-CMD-01 demands. Anywhere else (a pipe,
    a redirected stdin, a test harness) it falls back to plain ``input``, which
    is what keeps scripted and redirected operation working.
    """
    if not capabilities.is_tty:
        return input

    try:
        session = palette._build_prompt_session(capabilities)
    except (ImportError, OSError):
        # A terminal we cannot drive interactively is not a reason to refuse to
        # start; degrade to the plain reader and keep the shell usable.
        return input

    def _read(prompt: str) -> str:
        return session.prompt(prompt)

    return _read


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner = _canonical_runner,
    input_function: InputFunction | None = None,
    stream: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
    state_provider: StateProvider = _durable_shell_state,
) -> int:
    args = build_parser().parse_args(argv)
    capabilities = theme.detect(
        stream,
        no_color=args.no_color,
        no_animation=args.no_animation,
        reduced_motion=args.reduced_motion,
        machine_readable=args.machine_readable,
    )
    if input_function is None:
        input_function = _default_input_function(capabilities)
    try:
        if args.command:
            for command in args.command:
                should_exit, status = execute_slash_command(
                    command,
                    runner=runner,
                    stream=stream,
                    err=err,
                    capabilities=capabilities,
                    state=state_provider(),
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
            capabilities=capabilities,
            state_provider=state_provider,
        )
    finally:
        theme.restore(stream, capabilities)


# Re-exported for callers and tests that render results directly.
render_table = table.render_table
render_detail = table.render_detail

if __name__ == "__main__":
    raise SystemExit(main())
