"""Command and parameter catalogue for the NEOHunter interaction layer.

One declarative registry drives every surface the specification requires:

* the searchable palette and its per-item descriptions (UX-CMD-01, UX-CMD-02);
* guided parameter entry, field ordering, defaults, and enumerations (UX-IN-01,
  UX-IN-02);
* live validity sentinels, by delegating to ``validation`` (UX-IN-03);
* progressive disclosure of advanced scientific constraints (UX-ADV-01);
* the ``/Help`` reference;
* construction of the ``Skills/hunter_cli.py`` argument vector.

Keeping all of that in one place is what prevents the palette, the help text,
and the actual accepted arguments from drifting apart.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from . import theme, validation

# A predicate over durable application state deciding whether a command is
# currently actionable. Specification UX-CMD-02 requires the palette to show
# state-dependent availability rather than offering commands that must fail.
AvailabilityCheck = Callable[["ShellState"], "Availability"]


@dataclass(frozen=True)
class ShellState:
    """Minimal snapshot of durable state the palette needs to reason about.

    This is a read-only projection supplied by the shell. The UX layer never
    queries persistence directly -- doing so would duplicate business logic that
    specification section 12 reserves for the canonical pipeline.
    """

    pending_search_ids: tuple[str, ...] = ()
    open_follow_up_count: int = 0
    last_result_count: int = 0


@dataclass(frozen=True)
class Availability:
    """Whether a command can run right now, and why not when it cannot."""

    enabled: bool
    reason: str = ""


def _always_available(_state: ShellState) -> Availability:
    """Commands with no durable-state precondition."""
    return Availability(enabled=True)


def _requires_pending_search(state: ShellState) -> Availability:
    """``/Run-Search`` needs a frozen manifest waiting to execute."""
    if state.pending_search_ids:
        return Availability(enabled=True)
    return Availability(
        enabled=False,
        reason="No pending search. Create one with /New-Search or /Follow-Up-Search.",
    )


def _requires_results(state: ShellState) -> Availability:
    """``/Inspect-Target`` needs a result set, or an explicit identifier."""
    if state.last_result_count > 0:
        return Availability(enabled=True)
    return Availability(
        enabled=False,
        reason="No results in this session yet. Inspect by target identifier instead of rank.",
    )


@dataclass(frozen=True)
class ParamSpec:
    """One guided input field.

    ``flag`` is the ``hunter_cli`` argument this field maps to. When ``flag`` is
    ``None`` the value is passed positionally in registry-declared order.
    """

    name: str
    label: str
    description: str
    validator: Callable[[str], validation.ValidationResult]
    required: bool = False
    default_display: str = "optional"
    flag: str | None = None
    choices: tuple[str, ...] = ()
    advanced: bool = False

    def placeholder(self) -> str:
        """Value shown in the guided editor before the operator types."""
        return self.default_display


@dataclass(frozen=True)
class CommandSpec:
    """One slash command as presented and as executed."""

    name: str
    summary: str
    description: str
    subcommand: str
    params: tuple[ParamSpec, ...] = ()
    fixed_args: tuple[str, ...] = ()
    availability: AvailabilityCheck = _always_available
    aliases: tuple[str, ...] = ()
    is_meta: bool = False
    stage_label: str = ""
    stage_detail: str = ""

    @property
    def required_params(self) -> tuple[ParamSpec, ...]:
        return tuple(param for param in self.params if param.required)

    @property
    def optional_params(self) -> tuple[ParamSpec, ...]:
        return tuple(param for param in self.params if not param.required)

    @property
    def advanced_params(self) -> tuple[ParamSpec, ...]:
        """Fields hidden behind progressive disclosure (UX-ADV-01)."""
        return tuple(param for param in self.params if param.advanced)

    def parameter_summary(self) -> tuple[str, str]:
        """Return ``(required, optional)`` summaries for the palette item."""
        required = ", ".join(param.name for param in self.required_params) or "none"
        optional = ", ".join(param.name for param in self.optional_params) or "none"
        return required, optional

    def build_argv(self, values: dict[str, Any]) -> list[str]:
        """Translate validated field values into a ``hunter_cli`` argument vector.

        Only validated values reach this function; it performs no validation of
        its own so there is exactly one place where a rule can live.
        """
        argv: list[str] = [self.subcommand, *self.fixed_args]
        for param in self.params:
            if param.name not in values:
                continue
            value = values[param.name]
            if value is None or value == "":
                continue
            if param.flag is None:
                argv.append(str(value))
                continue
            # ``--latest`` is a standalone switch rather than a flag with a value.
            if isinstance(value, str) and value == "--latest":
                argv.append("--latest")
                continue
            argv.extend([param.flag, str(value)])
        return argv


# --- Shared parameter definitions ------------------------------------------

_TARGETS_PARAM = ParamSpec(
    name="targets",
    label="Targets",
    description="How many targets to select and freeze into this search.",
    validator=validation.validate_target_count,
    required=True,
    default_display="20",
    flag="--targets",
)

_NEO_CLASS_PARAM = ParamSpec(
    name="neo-class",
    label="Target class",
    description="Restrict selection to one NEO dynamical class.",
    validator=validation.validate_neo_class,
    default_display="Any",
    flag="--neo-class",
    choices=validation.NEO_CLASS_CHOICES,
    advanced=True,
)

_MAX_POOL_PARAM = ParamSpec(
    name="max-pool",
    label="Maximum discovery pool",
    description=(
        "Operator safety limit on how many candidates discovery may examine. "
        "Discovery expands adaptively; if this limit prevents sufficiency the "
        "search fails loudly rather than freezing a short manifest."
    ),
    validator=validation.validate_optional_pool_limit,
    flag="--max-pool",
    advanced=True,
)

_MAX_DOWNLOAD_PARAM = ParamSpec(
    name="max-download-gb",
    label="Maximum download",
    description="Ceiling on acquisition volume in gigabytes for this search.",
    validator=validation.validate_optional_positive_number,
    flag="--max-download-gb",
    advanced=True,
)


# --- The seven required commands -------------------------------------------

COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="/New-Search",
        summary="Select and freeze the best available never-before-searched targets.",
        description=(
            "Runs adaptive discovery over the planning universe, applies New-mode "
            "eligibility including complete cross-project search history, ranks the "
            "survivors, evaluates sufficiency, and freezes the exact selected targets "
            "into a durable pending manifest."
        ),
        subcommand="create-new-search",
        fixed_args=("--mode", "new"),
        params=(_TARGETS_PARAM, _NEO_CLASS_PARAM, _MAX_POOL_PARAM, _MAX_DOWNLOAD_PARAM),
        aliases=("/new-search", "/create-new-search"),
        stage_label="adaptive discovery",
        stage_detail="rank universe -> eligibility -> sufficiency -> durable manifest",
    ),
    CommandSpec(
        name="/Follow-Up-Search",
        summary="Rank validated prior-search evidence and freeze the best follow-ups.",
        description=(
            "Ranks open follow-up registry entries and previously searched targets "
            "whose coverage has since improved, then freezes the exact selected "
            "targets into a durable pending manifest."
        ),
        subcommand="create-new-search",
        fixed_args=("--mode", "follow-up"),
        params=(_TARGETS_PARAM, _NEO_CLASS_PARAM, _MAX_POOL_PARAM, _MAX_DOWNLOAD_PARAM),
        aliases=("/follow-up-search", "/followup-search"),
        stage_label="trajectory revisit",
        stage_detail="validated history -> additional-work value -> exact manifest",
    ),
    CommandSpec(
        name="/Run-Search",
        summary="Execute or resume the exact frozen manifest.",
        description=(
            "Executes the exact targets frozen at creation time -- never regenerating, "
            "substituting, or reordering them -- through acquisition, preprocessing, "
            "linking, scoring, adversarial review, and durable persistence."
        ),
        subcommand="run-new-search",
        params=(
            ParamSpec(
                name="search-id",
                label="Search",
                description="Which frozen search to execute. Blank runs the most recent.",
                validator=validation.validate_search_id,
                default_display="--latest",
                flag="--search-id",
            ),
        ),
        availability=_requires_pending_search,
        aliases=("/run-search", "/run-new-search"),
        stage_label="exact search execution",
        stage_detail="acquire -> preprocess -> link -> score -> persist -> update history",
    ),
    CommandSpec(
        name="/Show-Follow-Ups",
        summary="Show durable follow-up evidence and recommended next actions.",
        description=(
            "Reads the durable follow-up registry and reports each entry's state, "
            "priority, originating search, and recommended next action."
        ),
        subcommand="show-follow-ups",
        params=(
            ParamSpec(
                name="status",
                label="Status",
                description="Lifecycle state to display.",
                validator=validation.validate_follow_up_status,
                default_display="open",
                flag="--status",
                choices=validation.FOLLOW_UP_STATUS_CHOICES,
            ),
        ),
        aliases=("/show-follow-ups", "/show-followups"),
        stage_label="follow-up radar",
        stage_detail="read durable evidence -> priority -> recommended action",
    ),
    CommandSpec(
        name="/Inspect-Target",
        summary="Show full scientific detail and provenance for one target.",
        description=(
            "Detail view for one target: canonical identity and aliases, scientific "
            "metrics, score components, selection reason, source and transformation "
            "provenance, prior-search evidence, estimated resource requirements, and "
            "known limitations."
        ),
        subcommand="inspect-target",
        params=(
            ParamSpec(
                name="target",
                label="Rank or target id",
                description="A result rank number from the last table, or a target identifier.",
                validator=validation.validate_target_reference,
                required=True,
                default_display="1",
                flag="--target",
            ),
        ),
        availability=_requires_results,
        aliases=("/inspect-target", "/inspect"),
        stage_label="target dossier",
        stage_detail="identity -> metrics -> score components -> provenance",
    ),
    CommandSpec(
        name="/Help",
        summary="Show the command reference and keyboard help.",
        description="Lists every command with its parameters and keyboard shortcuts.",
        subcommand="",
        is_meta=True,
        aliases=("/help", "/?"),
    ),
    CommandSpec(
        name="/Exit",
        summary="Leave NEOHunter.",
        description="Closes the session. Durable state is unaffected.",
        subcommand="",
        is_meta=True,
        aliases=("/exit", "/quit"),
    ),
)


# Lookup of every accepted spelling (canonical name plus aliases) to its command.
_BY_NAME: dict[str, CommandSpec] = {}
for _command in COMMANDS:
    _BY_NAME[_command.name.casefold()] = _command
    for _alias in _command.aliases:
        _BY_NAME[_alias.casefold()] = _command


def lookup(name: str) -> CommandSpec | None:
    """Resolve a command by canonical name or alias, case-insensitively."""
    return _BY_NAME.get(name.strip().casefold())


def search(query: str, state: ShellState | None = None) -> list[CommandSpec]:
    """Filter commands for the palette as the operator types (UX-CMD-03).

    Matching is a case-insensitive substring test over the command name, its
    summary, and its longer description. Searching the description too is what
    lets an operator who knows the domain word but not the command name -- for
    example ``registry`` -- still find ``/Show-Follow-Ups``. Unavailable commands
    are still listed: the palette shows *why* they are unavailable rather than
    hiding them, which is what UX-CMD-02's state-dependent availability requires.
    """
    text = query.strip().lstrip("/").casefold()
    if not text:
        return list(COMMANDS)
    return [
        command
        for command in COMMANDS
        if text in command.name.casefold().lstrip("/")
        or text in command.summary.casefold()
        or text in command.description.casefold()
    ]


def describe(
    command: CommandSpec,
    state: ShellState | None = None,
    width: int | None = None,
) -> list[str]:
    """Render one palette entry exactly as specification UX-CMD-02 illustrates.

    ``width`` fits each line to the terminal. Command summaries are full
    sentences and comfortably exceed a narrow terminal; without fitting they
    wrap, and a wrapped entry visually merges with the next one so the operator
    can no longer tell where one command ends and another begins.
    """
    required, optional = command.parameter_summary()
    lines = [command.name, f"    {command.summary}"]
    if not command.is_meta:
        lines.append(f"    Required: {required}")
        lines.append(f"    Optional: {optional}")
    if state is not None:
        available = command.availability(state)
        if not available.enabled:
            lines.append(f"    Unavailable: {available.reason}")
    if width is not None:
        lines = [theme.fit(line, width) for line in lines]
    return lines


def help_text(state: ShellState | None = None, width: int | None = None) -> str:
    """Full ``/Help`` reference built from the same registry as the palette."""
    blocks: list[str] = ["NEOHunter commands", ""]
    for command in COMMANDS:
        blocks.extend(describe(command, state, width))
        blocks.append("")
    keyboard = [
        "Keyboard",
        "    /            open the searchable command palette",
        "    Up / Down    move through palette entries",
        "    Enter        select an entry, or run when every required field is valid",
        "    Tab          complete a command, or move to the next field",
        "    Shift-Tab    move to the previous field",
        "    Escape       close the palette, or cancel guided entry",
        "    Ctrl-D       leave NEOHunter",
    ]
    blocks.extend(
        keyboard if width is None else [theme.fit(line, width) for line in keyboard]
    )
    return "\n".join(blocks)


def required_field_order(
    command: CommandSpec, *, include_advanced: bool = False
) -> Sequence[ParamSpec]:
    """Field order for guided entry: required first, then optional (UX-IN-02)."""
    fields = [param for param in command.params if not param.advanced]
    if include_advanced:
        fields.extend(command.advanced_params)
    return sorted(fields, key=lambda param: not param.required)


# Explicitly exported names, so the palette imports a stable surface.
__all__ = [
    "COMMANDS",
    "Availability",
    "CommandSpec",
    "ParamSpec",
    "ShellState",
    "describe",
    "help_text",
    "lookup",
    "required_field_order",
    "search",
]
