"""Searchable slash-command palette and guided parameter editor.

Specification requirements implemented here:

* UX-CMD-01 -- typing ``/`` immediately opens a searchable command palette; the
  operator never needs ``/Help`` to discover commands.
* UX-CMD-02 -- every palette item shows name, description, required parameters,
  optional parameters, and state-dependent availability.
* UX-CMD-03 -- live filtering while typing, Up/Down navigation, Enter to select,
  Escape to close, Tab completion, discoverable keyboard help.
* UX-IN-01/02 -- guided editable fields, focus starting at the first required
  field, Tab/Shift-Tab movement, Enter only when valid, Escape to cancel,
  visible defaults and descriptions, labelled optional fields, selectable
  enumerations.
* UX-IN-03 -- live validity sentinels during entry.

The palette is built on ``prompt_toolkit`` rather than hand-written escape
sequences, as specification section 12 directs. Every rendering decision routes
through :mod:`Skills.hunter_ux.theme` so the whole surface degrades cleanly on a
non-TTY stream.

Nothing in this module decides *what* a command does: selection resolves to a
:class:`~Skills.hunter_ux.registry.CommandSpec`, and the argument vector is built
by the registry. That keeps the interaction layer free of business logic.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import registry
from .registry import CommandSpec, ParamSpec, ShellState
from .theme import Capabilities

# Sentinel returned when the operator dismisses the palette or cancels entry.
CANCELLED = object()


@dataclass
class FieldState:
    """Live state of one guided input field, including its validity sentinel."""

    spec: ParamSpec
    raw: str = ""
    value: Any = None
    error: str | None = None
    touched: bool = False

    def validate(self) -> None:
        """Re-run the canonical validator and refresh the sentinel."""
        self.value, self.error = self.spec.validator(self.raw)
        # A blank optional field is valid and simply contributes nothing.
        if not self.raw.strip() and not self.spec.required:
            self.error = None

    @property
    def is_valid(self) -> bool:
        if self.spec.required and not self.raw.strip():
            return False
        return self.error is None

    def sentinel(self, capabilities: Capabilities) -> str:
        """Render the live validity sentinel for this field (UX-IN-03)."""
        if self.error:
            return capabilities.style(self.error, "red")
        if self.spec.required and not self.raw.strip():
            return capabilities.style("Required", "yellow")
        if self.raw.strip():
            return capabilities.style("OK", "green")
        return capabilities.style("optional", "dim")


@dataclass
class GuidedForm:
    """A command plus its editable fields, in specification field order."""

    command: CommandSpec
    fields: list[FieldState] = field(default_factory=list)
    show_advanced: bool = False

    @classmethod
    def for_command(cls, command: CommandSpec, *, show_advanced: bool = False) -> GuidedForm:
        specs = registry.required_field_order(command, include_advanced=show_advanced)
        form = cls(command=command, show_advanced=show_advanced)
        for spec in specs:
            state = FieldState(spec=spec)
            # Seed a visible default so the operator sees what will be used.
            if spec.default_display and spec.default_display not in {"optional", "Any"}:
                state.raw = spec.default_display
            state.validate()
            form.fields.append(state)
        return form

    @property
    def first_required_index(self) -> int:
        """Focus begins at the first required field (UX-IN-02)."""
        for index, state in enumerate(self.fields):
            if state.spec.required:
                return index
        return 0

    @property
    def is_executable(self) -> bool:
        """Enter executes only when every required field is valid (UX-IN-02)."""
        return all(state.is_valid for state in self.fields)

    def blocking_errors(self) -> list[str]:
        """Human-readable reasons the form cannot execute yet."""
        problems = []
        for state in self.fields:
            if state.spec.required and not state.raw.strip():
                problems.append(f"{state.spec.label}: required")
            elif state.error:
                problems.append(f"{state.spec.label}: {state.error}")
        return problems

    def values(self) -> dict[str, Any]:
        """Validated values, omitting blank optional fields."""
        collected: dict[str, Any] = {}
        for state in self.fields:
            if not state.raw.strip():
                continue
            collected[state.spec.name] = state.value
        return collected

    def build_argv(self) -> list[str]:
        """Argument vector for the canonical pipeline."""
        return self.command.build_argv(self.values())

    def render(self, capabilities: Capabilities, focus_index: int = 0) -> list[str]:
        """Render the inline editor exactly as UX-IN-01 illustrates."""
        lines = [capabilities.style(self.command.name, "cyan", "bold"), ""]
        label_width = max((len(state.spec.label) for state in self.fields), default=0)
        for index, state in enumerate(self.fields):
            marker = ">" if index == focus_index else " "
            shown = state.raw if state.raw else state.spec.placeholder()
            lines.append(
                f"{marker} {state.spec.label.ljust(label_width)}  "
                f"[{shown}]  {state.sentinel(capabilities)}"
            )
            # The focused field shows its concise description (UX-IN-02).
            if index == focus_index:
                described = capabilities.style(state.spec.description, "dim")
                lines.append(f"  {' ' * label_width}  {described}")
                if state.spec.choices:
                    joined = " | ".join(state.spec.choices)
                    lines.append(f"  {' ' * label_width}  {capabilities.style(joined, 'dim')}")
        if self.command.advanced_params and not self.show_advanced:
            lines.append("")
            lines.append(capabilities.style("  Scientific constraints  [Open...]", "dim"))
        return lines


def render_palette(
    query: str,
    capabilities: Capabilities,
    state: ShellState | None = None,
    selected_index: int = 0,
) -> list[str]:
    """Render the palette for a query, as shown when the operator types ``/``."""
    matches = registry.search(query, state)
    header = capabilities.style(f"Commands matching {query or '/'}", "bold")
    lines = [header]
    if not matches:
        lines.append(capabilities.style("  no matching command", "dim"))
        return lines
    for index, command in enumerate(matches):
        marker = ">" if index == selected_index else " "
        # Two columns are consumed by the selection marker and its space.
        entry = registry.describe(command, state, max(capabilities.width - 2, 8))
        lines.append(f"{marker} {entry[0]}")
        lines.extend(f"  {line}" for line in entry[1:])
    lines.append(
        capabilities.style(
            "  Up/Down move  Enter select  Tab complete  Esc close", "dim"
        )
    )
    return lines


def _build_prompt_session(capabilities: Capabilities):
    """Create a prompt_toolkit session wired for palette completion.

    Imported lazily so the module can be used for pure rendering (and tested)
    on systems or streams where an interactive session is meaningless.
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion

    class _SlashCompleter(Completer):
        """Live palette completion: typing ``/`` immediately offers commands."""

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            # Only the command token participates in completion.
            token = text.split()[0] if text.split() else text
            if " " in text:
                return
            for command in registry.search(token):
                available = command.availability(ShellState())
                suffix = "" if available.enabled else "  (unavailable)"
                required, optional = command.parameter_summary()
                yield Completion(
                    command.name,
                    start_position=-len(token),
                    display=command.name,
                    display_meta=f"{command.summary}  req: {required}  opt: {optional}{suffix}",
                )

    return PromptSession(completer=_SlashCompleter(), complete_while_typing=True)


def prompt_line(
    capabilities: Capabilities,
    message: str = "NEOHunter> ",
    *,
    session: Any = None,
) -> str:
    """Read one line with palette completion active.

    Falls back to plain ``input`` when the stream is not a terminal, which is
    what keeps ``--command`` scripting and redirected stdin working.
    """
    if not capabilities.is_tty:
        return input(message)
    active = session if session is not None else _build_prompt_session(capabilities)
    return active.prompt(message)


def run_guided_entry(
    command: CommandSpec,
    capabilities: Capabilities,
    *,
    read_field: Callable[[ParamSpec, str], str],
    emit: Callable[[str], None],
    show_advanced: bool = False,
) -> list[str] | object:
    """Drive guided entry for one command and return its argument vector.

    ``read_field`` supplies each field's raw text (a real prompt interactively, a
    scripted value in tests). Returning :data:`CANCELLED` means the operator
    escaped out; invalid input can never advance or execute, per UX-IN-03.
    """
    form = GuidedForm.for_command(command, show_advanced=show_advanced)
    if not form.fields:
        return form.build_argv()

    order = list(range(len(form.fields)))
    # Focus begins at the first required field, then proceeds in display order.
    start = form.first_required_index
    order = order[start:] + order[:start]

    for index in order:
        state = form.fields[index]
        while True:
            for line in form.render(capabilities, focus_index=index):
                emit(line)
            raw = read_field(state.spec, state.raw)
            if raw is CANCELLED:
                return CANCELLED
            state.raw = "" if raw is None else str(raw)
            state.touched = True
            state.validate()
            if state.is_valid:
                break
            # Invalid input cannot advance; re-prompt with the sentinel visible.
            emit(state.sentinel(capabilities))

    if not form.is_executable:
        for problem in form.blocking_errors():
            emit(capabilities.style(problem, "red"))
        return CANCELLED
    return form.build_argv()


def resolve_command_line(line: str) -> tuple[CommandSpec | None, Sequence[str]]:
    """Split a typed line into its command and remaining raw tokens.

    Used by the scriptable ``--command`` path so that interactive and scripted
    invocations resolve names identically.
    """
    import shlex

    tokens = shlex.split(line)
    if not tokens:
        return None, ()
    return registry.lookup(tokens[0]), tuple(tokens[1:])
