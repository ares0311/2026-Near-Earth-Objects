"""Behavioural controls for the persistent NEOHunter terminal.

These cover ``docs/CLI_UX_SPEC.md`` (``HUNTER-CLI-UX-2026-07-30.3``). The shell
is a presentation layer, so every test asserts either that a required
interaction behaviour exists, or that the shell delegates to the canonical
pipeline without duplicating business logic (specification section 12).
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Skills"))

import hunter_shell  # noqa: E402
from hunter_ux import (  # noqa: E402
    animation,
    palette,
    preview,
    registry,
    table,
    theme,
    validation,  # noqa: E402
)


def _capabilities(
    *, tty: bool = False, width: int = 100, color: bool = False
) -> theme.Capabilities:
    """Deterministic capabilities so rendering never depends on the host terminal."""
    return theme.Capabilities(
        is_tty=tty, color=color, animation=tty, unicode=True, width=width
    )


class _Stream(io.StringIO):
    """A StringIO that can pretend to be (or not be) a terminal."""

    def __init__(self, tty: bool = False) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


# --- Command registry (CLI-02, UX-CMD-02, UX-CMD-03) ------------------------


def test_every_required_command_is_registered() -> None:
    """CLI-02 enumerates seven mandatory interactive commands."""
    required = {
        "/New-Search",
        "/Follow-Up-Search",
        "/Run-Search",
        "/Show-Follow-Ups",
        "/Inspect-Target",
        "/Help",
        "/Exit",
    }
    assert {command.name for command in registry.COMMANDS} == required


def test_mode_is_inherent_and_needs_no_redundant_flag() -> None:
    """CLI-02: mode comes from the command identity, not an operator flag."""
    new_argv = registry.lookup("/New-Search").build_argv({"targets": 5})
    follow_argv = registry.lookup("/Follow-Up-Search").build_argv({"targets": 5})

    assert new_argv[0] == "create-new-search"
    assert new_argv.count("--mode") == 1
    assert "new" in new_argv
    assert "follow-up" in follow_argv


def test_palette_items_describe_parameters_and_availability() -> None:
    """UX-CMD-02: name, description, required, optional, and availability."""
    state = registry.ShellState(pending_search_ids=())
    described = registry.describe(registry.lookup("/New-Search"), state)

    assert described[0] == "/New-Search"
    assert "Required: targets" in described[2]
    assert any("Optional:" in line for line in described)

    run_described = registry.describe(registry.lookup("/Run-Search"), state)
    assert any("Unavailable" in line for line in run_described)


def test_palette_filters_live_while_typing() -> None:
    """UX-CMD-03: filtering by command name, summary, and description."""
    # A prefix narrows to the follow-up commands and excludes everything else.
    follow_matches = {command.name for command in registry.search("/foll")}
    assert "/Follow-Up-Search" in follow_matches
    assert "/New-Search" not in follow_matches
    assert "/Exit" not in follow_matches

    # An empty query lists the full catalogue.
    assert registry.search("") == list(registry.COMMANDS)

    # A domain word the operator knows, but which is not in any command name,
    # still finds the right command via its description.
    assert any(command.name == "/Show-Follow-Ups" for command in registry.search("registry"))

    # A term matching nothing returns nothing rather than the whole catalogue.
    assert registry.search("spectroscopy") == []


def test_aliases_resolve_to_the_canonical_command() -> None:
    assert registry.lookup("/create-new-search").name == "/New-Search"
    assert registry.lookup("/RUN-SEARCH").name == "/Run-Search"
    assert registry.lookup("/nonexistent") is None


# --- Shared validation (UX-IN-03, UX-IN-04) ---------------------------------


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("twenty", "Invalid - enter a positive whole number."),
        ("0", "Invalid - targets must be greater than zero."),
        ("-3", "Invalid - targets must be greater than zero."),
    ],
)
def test_target_count_sentinels_match_specification_wording(raw: str, message: str) -> None:
    """UX-IN-03 specifies this sentinel wording for the two common mistakes."""
    value, error = validation.validate_target_count(raw)
    assert value is None
    assert error == message


def test_interactive_and_scriptable_share_one_validator() -> None:
    """UX-IN-04: the argparse adapter wraps the identical canonical function."""
    converter = validation.as_argparse_type(validation.validate_target_count)
    assert converter("7") == 7
    with pytest.raises(argparse.ArgumentTypeError, match="greater than zero"):
        converter("0")


def test_enumerations_reject_values_outside_the_choice_set() -> None:
    assert validation.validate_neo_class("aten") == ("aten", None)
    value, error = validation.validate_neo_class("comet")
    assert value is None
    assert "choose one of" in error


def test_invalid_input_cannot_advance_or_execute() -> None:
    """UX-IN-03: an invalid required field blocks execution."""
    form = palette.GuidedForm.for_command(registry.lookup("/New-Search"))
    targets = form.fields[0]
    targets.raw = "twenty"
    targets.validate()

    assert not targets.is_valid
    assert not form.is_executable
    assert any("targets" in problem.lower() for problem in form.blocking_errors())


def test_guided_form_focus_starts_at_first_required_field() -> None:
    """UX-IN-02: focus begins at the first required field."""
    form = palette.GuidedForm.for_command(registry.lookup("/New-Search"))
    assert form.fields[form.first_required_index].spec.required


def test_guided_form_shows_defaults_and_labels_optional_fields() -> None:
    """UX-IN-02: defaults visible, optional fields clearly labelled."""
    form = palette.GuidedForm.for_command(registry.lookup("/New-Search"))
    rendered = "\n".join(form.render(_capabilities(), focus_index=0))

    assert "Targets" in rendered
    assert "[20]" in rendered
    assert "Scientific constraints" in rendered  # progressive disclosure, UX-ADV-01


# --- Shell behaviour --------------------------------------------------------


def test_bare_slash_opens_the_palette_without_help() -> None:
    """UX-CMD-01: typing '/' immediately lists commands."""
    out, err = _Stream(), _Stream()
    calls: list[list[str]] = []

    should_exit, status = hunter_shell.execute_slash_command(
        "/",
        runner=lambda argv: (calls.append(argv), 0)[1],
        stream=out,
        err=err,
        capabilities=_capabilities(),
    )

    assert (should_exit, status) == (False, 0)
    assert calls == [], "opening the palette must not run the pipeline"
    rendered = out.getvalue()
    for name in ("/New-Search", "/Run-Search", "/Inspect-Target"):
        assert name in rendered


def test_shell_delegates_once_to_the_canonical_pipeline() -> None:
    """Specification section 12: the CLI must not duplicate business logic."""
    calls: list[list[str]] = []
    out, err = _Stream(), _Stream()

    should_exit, status = hunter_shell.execute_slash_command(
        "/New-Search 5",
        runner=lambda argv: (calls.append(argv), 0)[1],
        stream=out,
        err=err,
        capabilities=_capabilities(),
    )

    assert (should_exit, status) == (False, 0)
    assert calls == [["create-new-search", "--mode", "new", "--targets", "5"]]


def test_shell_passes_through_explicit_flags() -> None:
    """Lower-level scriptable options remain available through the same path."""
    calls: list[list[str]] = []
    out, err = _Stream(), _Stream()

    hunter_shell.execute_slash_command(
        "/New-Search 5 --neo-class aten",
        runner=lambda argv: (calls.append(argv), 0)[1],
        stream=out,
        err=err,
        capabilities=_capabilities(),
    )

    assert calls[0][:5] == ["create-new-search", "--mode", "new", "--targets", "5"]
    assert "--neo-class" in calls[0]
    assert "aten" in calls[0]


def test_shell_reports_nonzero_status_with_a_diagnostic_id() -> None:
    """UX-RUN-03: concise, actionable failure that stays resumable."""
    out, err = _Stream(), _Stream()

    _should_exit, status = hunter_shell.execute_slash_command(
        "/New-Search 5",
        runner=lambda _argv: 3,
        stream=out,
        err=err,
        capabilities=_capabilities(),
    )

    assert status == 3
    message = err.getvalue()
    assert "did not complete" in message
    assert "resumable" in message
    assert "Diagnostic ID: NEO-" in message
    assert "Traceback" not in message


def test_shell_surfaces_pipeline_system_exit_without_crashing() -> None:
    out, err = _Stream(), _Stream()

    def exploding_runner(_argv):
        raise SystemExit("coverage inventory unavailable")

    _should_exit, status = hunter_shell.execute_slash_command(
        "/New-Search 5",
        runner=exploding_runner,
        stream=out,
        err=err,
        capabilities=_capabilities(),
    )

    assert status == 1
    assert "coverage inventory unavailable" in err.getvalue()


def test_unknown_command_shows_matching_commands_not_a_usage_dump() -> None:
    """UX-IN-04: raw argparse dumps are not the normal interactive error."""
    out, err = _Stream(), _Stream()

    _should_exit, status = hunter_shell.execute_slash_command(
        "/Nope",
        runner=lambda _argv: 0,
        stream=out,
        err=err,
        capabilities=_capabilities(),
    )

    assert status == 2
    assert "Unknown command" in err.getvalue()
    assert "usage:" not in err.getvalue()


def test_missing_required_argument_is_actionable() -> None:
    out, err = _Stream(), _Stream()

    _should_exit, status = hunter_shell.execute_slash_command(
        "/New-Search",
        runner=lambda _argv: 0,
        stream=out,
        err=err,
        capabilities=_capabilities(),
    )

    assert status == 2
    assert "requires targets" in err.getvalue()


def test_exit_and_help_do_not_touch_the_pipeline() -> None:
    out, err = _Stream(), _Stream()
    runner_calls: list[list[str]] = []

    def runner(argv):
        runner_calls.append(argv)
        return 0

    _, help_status = hunter_shell.execute_slash_command(
        "/Help", runner=runner, stream=out, err=err, capabilities=_capabilities()
    )
    should_exit, exit_status = hunter_shell.execute_slash_command(
        "/Exit", runner=runner, stream=out, err=err, capabilities=_capabilities()
    )

    assert help_status == 0
    assert (should_exit, exit_status) == (True, 0)
    assert runner_calls == []
    assert "NEOHunter commands" in out.getvalue()


def test_state_dependent_command_refuses_when_unavailable() -> None:
    """UX-CMD-02: availability is enforced, not merely displayed."""
    out, err = _Stream(), _Stream()

    _should_exit, status = hunter_shell.execute_slash_command(
        "/Inspect-Target 1",
        runner=lambda _argv: 0,
        stream=out,
        err=err,
        capabilities=_capabilities(),
        state=registry.ShellState(last_result_count=0),
    )

    assert status == 2
    assert "unavailable" in err.getvalue().lower()


def test_interactive_session_persists_until_exit() -> None:
    """Specification section 2: the shell stays active until /Exit."""
    out, err = _Stream(), _Stream()
    lines = iter(["/Help", "", "/Exit"])

    status = hunter_shell.run_interactive(
        runner=lambda _argv: 0,
        input_function=lambda _prompt: next(lines),
        stream=out,
        err=err,
        history_path=ROOT / "Logs" / "does-not-exist" / "history",
        capabilities=_capabilities(),
    )

    assert status == 0
    assert "NEOHunter session closed." in out.getvalue()


def test_interactive_handles_eof_and_interrupt_cleanly() -> None:
    out, err = _Stream(), _Stream()
    history = ROOT / "Logs" / "does-not-exist" / "history"

    def raise_eof(_prompt):
        raise EOFError

    assert (
        hunter_shell.run_interactive(
            runner=lambda _argv: 0,
            input_function=raise_eof,
            stream=out,
            err=err,
            history_path=history,
            capabilities=_capabilities(),
        )
        == 0
    )

    responses = iter([KeyboardInterrupt(), "/Exit"])

    def interrupt_then_exit(_prompt):
        value = next(responses)
        if isinstance(value, BaseException):
            raise value
        return value

    out2, err2 = _Stream(), _Stream()
    assert (
        hunter_shell.run_interactive(
            runner=lambda _argv: 0,
            input_function=interrupt_then_exit,
            stream=out2,
            err=err2,
            history_path=history,
            capabilities=_capabilities(),
        )
        == 0
    )
    assert "Interrupted" in out2.getvalue()


def test_main_runs_scripted_commands_and_stops_on_failure() -> None:
    out, err = _Stream(), _Stream()

    status = hunter_shell.main(
        ["--no-animation", "--no-color", "--command", "/New-Search 2"],
        runner=lambda _argv: 4,
        stream=out,
        err=err,
    )

    assert status == 4


def test_main_hydrates_run_search_availability_from_durable_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "operator-state"
    monkeypatch.setenv("NEOHUNTER_HOME", str(state_root))
    db_path = state_root / "data_selection" / "hunter_state.sqlite"
    target = hunter_shell.hunter_state.ManifestTarget(
        target_id="radec_10.00_5.00",
        ra_deg=10.0,
        dec_deg=5.0,
        score=0.9,
        selection_reason="independent durable-state fixture",
    )
    hunter_shell.hunter_state.create_search_manifest(
        db_path,
        "search-1",
        "new",
        1,
        "policy.json",
        "digest",
        [target],
        10,
        True,
        {},
    )
    calls: list[list[str]] = []

    status = hunter_shell.main(
        ["--no-animation", "--no-color", "--command", "/Run-Search search-1"],
        runner=lambda argv: (calls.append(argv or []), 0)[1],
        stream=_Stream(),
        err=_Stream(),
    )

    assert status == 0
    assert calls == [["run-new-search", "--search-id", "search-1"]]


# --- Accessibility and degradation (UX-START-04, section 11) ----------------


def test_animation_and_color_disable_for_non_tty() -> None:
    capabilities = theme.detect(_Stream(tty=False), environ={})
    assert not capabilities.is_tty
    assert not capabilities.animation
    assert not capabilities.color


@pytest.mark.parametrize(
    "environ",
    [{"NO_COLOR": "1"}, {"TERM": "dumb"}, {"NEOHUNTER_NO_COLOR": "1"}],
)
def test_color_disables_for_accessibility_environments(environ: dict[str, str]) -> None:
    assert not theme.detect(_Stream(tty=True), environ=environ).color


@pytest.mark.parametrize(
    "kwargs",
    [{"reduced_motion": True}, {"no_animation": True}, {"machine_readable": True}],
)
def test_animation_disables_for_explicit_modes(kwargs: dict[str, bool]) -> None:
    assert not theme.detect(_Stream(tty=True), environ={}, **kwargs).animation


def test_animation_disables_in_continuous_integration() -> None:
    assert not theme.detect(_Stream(tty=True), environ={"CI": "true"}).animation


def test_machine_readable_output_carries_no_ansi() -> None:
    """UX-TABLE-04: machine output has no animation or control sequences."""
    stream = _Stream()
    table.write_machine_output([{"rank": 1, "target_id": "T-1", "score": 0.9}], stream)
    payload = stream.getvalue()

    assert "\033" not in payload
    assert payload.strip().startswith("{")


def test_terminal_state_is_restored_after_use() -> None:
    """Section 11: the UI must restore terminal state."""
    stream = _Stream(tty=True)
    theme.restore(stream, _capabilities(tty=True, color=True))
    assert "\033[2K" in stream.getvalue()


# --- Startup and execution animation (UX-START-01/02/03, UX-RUN-01/02) ------


def test_startup_is_animated_and_domain_specific() -> None:
    """UX-START-01/02: a real animation using NEOHunter's own themes."""
    frames = list(animation.startup_sequence(_capabilities(tty=True)))

    assert len(frames) > 8, "a single static frame is nonconforming"
    joined = " ".join(frames)
    for motif in (
        "telescope scan",
        "radar acquisition",
        "orbital sweep",
        "trajectory projection",
        "close-approach geometry",
        "moving-object survey",
    ):
        assert motif in joined


def test_startup_animation_makes_no_data_claim() -> None:
    """UX-START-03: no fabricated discoveries, counts, or percentages."""
    joined = " ".join(animation.startup_sequence(_capabilities(tty=True))).casefold()
    for banned in ("%", "discovered", "candidates", "detected"):
        assert banned not in joined


def test_startup_degrades_without_control_characters() -> None:
    """UX-START-04: identity survives, animation does not, on a non-TTY."""
    stream = _Stream(tty=False)
    animation.play_startup(stream, _capabilities(tty=False))
    rendered = stream.getvalue()

    assert "NEOHUNTER" in rendered.upper().replace(" ", "") or "orbital sweep" in rendered
    assert "\033[2K" not in rendered


def test_execution_stages_are_the_documented_pipeline_stages() -> None:
    """UX-RUN-01: animation corresponds to actual pipeline stages."""
    assert animation.PIPELINE_STAGES == (
        "survey discovery",
        "orbit resolution",
        "known-object exclusion",
        "trajectory propagation",
        "observability scoring",
        "close-approach ranking",
    )


def test_progress_reports_only_measured_quantities() -> None:
    """UX-RUN-02: no percentage is invented when the total is unknown."""
    unknown_total = animation.StageProgress(stage="survey discovery", completed=7)
    known_total = animation.StageProgress(stage="survey discovery", completed=7, total=10)

    assert "%" not in unknown_total.render()
    assert "70%" in known_total.render()


# --- Result presentation (UX-TABLE-01/02/03) -------------------------------


def _rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "rank": index + 1,
            "target_id": f"NEO-FIELD-{index:04d}",
            "neo_class": "aten",
            "ra_deg": 217.41 + index,
            "dec_deg": -15.0 + index,
            "score": 0.93 - index * 0.01,
            "nights": 3,
            "storage_mb": 512.0,
            "status": "pending",
        }
        for index in range(count)
    ]


@pytest.mark.parametrize("width", [40, 80, 140])
def test_table_never_exceeds_terminal_width(width: int) -> None:
    """UX-TABLE-01: stable widths, intentional truncation, no wrapping."""
    lines = table.render_table(_rows(5), _capabilities(width=width))

    assert lines
    for line in lines:
        assert len(line) <= width, f"line exceeds width {width}: {line!r}"
        assert "\n" not in line


def test_narrow_terminal_preserves_rank_and_identity() -> None:
    """UX-TABLE-01: rank and identity survive column dropping."""
    keys = {column.key for column in table.select_columns(table.DEFAULT_COLUMNS, 40)}
    assert "rank" in keys
    assert "target_id" in keys


def test_truncation_is_visibly_marked() -> None:
    fitted = table.fit("an-extremely-long-target-identifier", 12)
    assert len(fitted) == 12
    assert fitted.endswith(table.TRUNCATION_MARKER)


def test_table_paginates_and_points_at_the_detail_view() -> None:
    lines = table.render_table(_rows(50), _capabilities(), page=2, page_size=20)
    joined = "\n".join(lines)

    assert "page 2/3" in joined
    assert "/Inspect-Target" in joined


def test_large_request_exports_and_summarises(tmp_path: Path) -> None:
    """UX-TABLE-03: N > 100 writes a complete export and reports its path."""
    rows = _rows(150)
    destination = tmp_path / "export.jsonl"
    table.export_rows(rows, destination)
    summary = table.render_large_summary(rows, destination, _capabilities())

    assert len(destination.read_text().splitlines()) == 150
    assert any(str(destination) in line for line in summary)
    assert any("150 targets selected" in line for line in summary)


def test_detail_view_holds_the_long_explanations() -> None:
    """UX-TABLE-02: rationale and provenance belong to /Inspect-Target."""
    joined = "\n".join(
        table.render_detail(
            {
                "target_id": "NEO-FIELD-0001",
                "identity": {"canonical_id": "ZTF-325"},
                "score_components": {"elongation": 0.82},
                "selection_reason": "highest ranked uncovered Aten field",
                "provenance": {"search_id": "S-1"},
                "limitations": ["uncalibrated ranking prior"],
            },
            _capabilities(),
        )
    ).casefold()

    for expected in (
        "canonical identity",
        "score components",
        "selection reason",
        "provenance",
        "limitations",
    ):
        assert expected in joined


def test_detail_view_omits_sections_it_has_no_data_for() -> None:
    """Absent evidence must not be implied by an empty heading."""
    detail = "\n".join(table.render_detail({"target_id": "T-1"}, _capabilities()))

    assert "Score components" not in detail
    assert "No detail recorded" in detail


# --- Resolved-action preview (section 8) ------------------------------------


def test_preview_lists_every_required_field_in_order() -> None:
    joined = "\n".join(
        preview.render_preview(
            preview.ResolvedAction(mode="new", requested_targets=5), _capabilities()
        )
    )

    for _key, label in preview.PREVIEW_FIELD_ORDER:
        assert label in joined
    assert "Confirm, edit, or cancel." in joined


def test_preview_marks_unknown_rather_than_inventing_estimates() -> None:
    """Fields the pipeline has not reported must read 'unknown'."""
    joined = "\n".join(
        preview.render_preview(
            preview.ResolvedAction(mode="new", requested_targets=5), _capabilities()
        )
    )
    assert joined.count(preview.UNKNOWN) >= 5


def test_diagnostic_ids_are_stable_and_greppable() -> None:
    stamp = preview.diagnostic_id(salt="create-new-search --targets 5")
    assert stamp.startswith("NEO-")
    assert len(stamp.split("-")) == 4
