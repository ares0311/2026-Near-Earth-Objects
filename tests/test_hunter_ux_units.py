"""Unit coverage for the NEOHunter interaction layer's remaining branches.

``tests/test_hunter_shell.py`` covers the behaviours the CLI/UX specification
requires. This module covers the supporting branches -- individual validators,
degraded rendering paths, and error handling -- so the production runtime
denominator defined in ``.coveragerc.production`` is fully measured rather than
partially measured (Hunter contract CLAIM-02, field blocker NEO-FIELD-02).
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Skills"))

from hunter_ux import animation, palette, preview, registry, table, theme, validation  # noqa: E402


def _capabilities(**overrides) -> theme.Capabilities:
    defaults = {
        "is_tty": False,
        "color": False,
        "animation": False,
        "unicode": True,
        "width": 100,
    }
    defaults.update(overrides)
    return theme.Capabilities(**defaults)


class _Stream(io.StringIO):
    """A StringIO with controllable TTY and encoding reporting.

    ``encoding`` is a read-only attribute on ``io.StringIO``, so it is exposed
    here as a property backed by a private field.
    """

    def __init__(self, tty: bool = False, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding

    def isatty(self) -> bool:
        return self._tty


# --- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", "all"), ("aten", "aten"), ("ATEN", "aten"), ("ieo", "ieo")],
)
def test_neo_class_accepts_valid_values(raw: str, expected: str) -> None:
    assert validation.validate_neo_class(raw) == (expected, None)


@pytest.mark.parametrize(
    ("raw", "expected"), [("", "open"), ("actioned", "actioned"), ("ALL", "all")]
)
def test_follow_up_status_accepts_valid_values(raw: str, expected: str) -> None:
    assert validation.validate_follow_up_status(raw) == (expected, None)


def test_follow_up_status_rejects_unknown_state() -> None:
    value, error = validation.validate_follow_up_status("archived")
    assert value is None
    assert "choose one of" in error


def test_target_count_rejects_absurdly_large_requests() -> None:
    """A pasted identifier must not become a request for millions of targets."""
    value, error = validation.validate_target_count("99999999")
    assert value is None
    assert "must not exceed" in error


@pytest.mark.parametrize(
    ("raw", "expected"), [("", (None, None)), ("2.5", (2.5, None))]
)
def test_optional_positive_number(raw: str, expected: tuple) -> None:
    assert validation.validate_optional_positive_number(raw) == expected


@pytest.mark.parametrize("raw", ["nope", "0", "-1"])
def test_optional_positive_number_rejects_bad_values(raw: str) -> None:
    value, error = validation.validate_optional_positive_number(raw)
    assert value is None
    assert error is not None


@pytest.mark.parametrize(
    ("raw", "expected"), [("", (None, None)), ("500", (500, None))]
)
def test_optional_pool_limit(raw: str, expected: tuple) -> None:
    assert validation.validate_optional_pool_limit(raw) == expected


@pytest.mark.parametrize("raw", ["many", "0", "-4"])
def test_optional_pool_limit_rejects_bad_values(raw: str) -> None:
    value, error = validation.validate_optional_pool_limit(raw)
    assert value is None
    assert error is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", None),
        ("latest", "--latest"),
        ("--latest", "--latest"),
        ("SEARCH_2026-07-31", "SEARCH_2026-07-31"),
    ],
)
def test_search_id_accepts_identifiers_and_the_latest_sentinel(raw, expected) -> None:
    assert validation.validate_search_id(raw)[0] == expected


def test_search_id_rejects_path_like_input() -> None:
    """A stray path must never reach persistence as if it were an identifier."""
    value, error = validation.validate_search_id("../../etc/passwd")
    assert value is None
    assert "letters, digits" in error


def test_target_reference_accepts_rank_and_identifier() -> None:
    assert validation.validate_target_reference("3") == (3, None)
    assert validation.validate_target_reference("NEO-FIELD-0001")[0] == "NEO-FIELD-0001"


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [("", "Required"), ("0", "greater than zero"), ("bad target!", "valid target")],
)
def test_target_reference_rejects_bad_input(raw: str, fragment: str) -> None:
    value, error = validation.validate_target_reference(raw)
    assert value is None
    assert fragment in error


def test_existing_directory_validation(tmp_path: Path) -> None:
    assert validation.validate_existing_directory("") == (None, None)
    assert validation.validate_existing_directory(str(tmp_path))[0] == tmp_path

    missing = tmp_path / "absent"
    value, error = validation.validate_existing_directory(str(missing))
    assert value is None
    assert "does not exist" in error

    file_path = tmp_path / "a-file"
    file_path.write_text("x")
    value, error = validation.validate_existing_directory(str(file_path))
    assert value is None
    assert "not a directory" in error


def test_existing_directory_rejects_unwritable_directory(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        value, error = validation.validate_existing_directory(str(locked))
        # Running as a user who can bypass permission bits makes this
        # unobservable; only assert the failure path when it is real.
        if value is None:
            assert "not writable" in error
    finally:
        locked.chmod(0o700)


# --- theme ------------------------------------------------------------------


def test_unicode_detection_falls_back_for_ascii_streams() -> None:
    assert theme.detect(_Stream(encoding="utf-8"), environ={}).unicode is True
    assert theme.detect(_Stream(encoding="ascii"), environ={}).unicode is False
    assert theme.detect(_Stream(encoding=""), environ={}).unicode is False


def test_style_is_a_noop_without_color() -> None:
    assert _capabilities(color=False).style("text", "red") == "text"
    assert _capabilities(color=True).style("text", "red") == "\033[31mtext\033[0m"
    # An unknown style name must not corrupt the output.
    assert _capabilities(color=True).style("text") == "text"


def test_restore_is_safe_on_non_tty_and_closed_streams() -> None:
    non_tty = _Stream(tty=False)
    theme.restore(non_tty, _capabilities())
    assert non_tty.getvalue() == ""

    closed = _Stream(tty=True)
    closed.close()
    # Must not raise: a closed stream is not a reason to crash on the way out.
    theme.restore(closed, _capabilities(is_tty=True))


def test_width_falls_back_for_non_tty() -> None:
    assert theme.detect(_Stream(tty=False), environ={}).width == theme.DEFAULT_NON_TTY_WIDTH


# --- animation --------------------------------------------------------------


def test_identity_lines_include_the_subtitle() -> None:
    lines = animation.identity_lines(_capabilities())
    assert any("Near-Earth Object" in line for line in lines)


def test_ascii_frames_used_when_unicode_unavailable() -> None:
    frames = " ".join(animation.startup_sequence(_capabilities(unicode=False)))
    assert "*" in frames or "o" in frames


def test_play_startup_animates_and_clears_the_line() -> None:
    stream = _Stream(tty=True)
    slept: list[float] = []
    animation.play_startup(
        stream,
        _capabilities(is_tty=True, animation=True),
        frame_seconds=0.0,
        sleep=slept.append,
    )
    rendered = stream.getvalue()

    assert "\033[2K" in rendered
    assert slept, "an animated startup must actually pace its frames"


def test_render_stage_appends_when_not_animated() -> None:
    stream = _Stream()
    animation.render_stage(
        stream, _capabilities(), animation.StageProgress(stage="orbit resolution")
    )
    animation.finish_stage(stream, _capabilities())

    assert "orbit resolution" in stream.getvalue()
    assert "\033[2K" not in stream.getvalue()


def test_render_stage_rewrites_in_place_when_animated() -> None:
    stream = _Stream(tty=True)
    capabilities = _capabilities(is_tty=True, animation=True)
    animation.render_stage(
        stream, capabilities, animation.StageProgress(stage="orbit resolution")
    )
    animation.finish_stage(stream, capabilities)

    assert "\r\033[2K" in stream.getvalue()
    assert stream.getvalue().endswith("\n")


def test_stage_progress_renders_every_measured_field() -> None:
    rendered = animation.StageProgress(
        stage="survey discovery",
        completed=3,
        total=10,
        candidates_found=2,
        candidates_rejected=1,
        expansion_round=4,
        current_source="IRSA",
        elapsed_seconds=125.0,
    ).render()

    for fragment in ("3/10", "30%", "found 2", "rejected 1", "round 4", "IRSA", "2m05s"):
        assert fragment in rendered


# --- table ------------------------------------------------------------------


def test_cell_rendering_handles_every_value_shape() -> None:
    assert table._cell(None) == "-"
    assert table._cell(1.5) == "1.5"
    assert table._cell({"a": 1}) == '{"a":1}'
    assert table._cell([1, 2]) == "[1,2]"
    # Embedded newlines would break the single-line width guarantee.
    assert "\n" not in table._cell("a\nb")


def test_fit_handles_degenerate_widths() -> None:
    assert table.fit("abc", 0) == ""
    assert table.fit("abc", 1) == table.TRUNCATION_MARKER
    assert table.fit("ab", 5) == "ab   "


def test_stacked_fallback_used_when_no_column_fits() -> None:
    rows = [{"rank": 1, "target_id": "T-1", "score": 0.5}]
    lines = table.render_table(rows, _capabilities(width=1))
    assert any("T-1" in line for line in lines)


def test_render_stacked_lists_present_fields_only() -> None:
    lines = table.render_stacked(
        [{"rank": 1, "target_id": "T-1", "score": 0.5}], _capabilities()
    )
    joined = "\n".join(lines)
    assert "T-1" in joined
    assert "Score" in joined
    assert "Nights" not in joined


def test_render_table_clamps_out_of_range_pages() -> None:
    rows = [{"rank": index, "target_id": f"T-{index}"} for index in range(5)]
    assert any("page 1/1" in line for line in table.render_table(rows, _capabilities(), page=99))
    assert any("page 1/1" in line for line in table.render_table(rows, _capabilities(), page=0))


def test_large_summary_without_scores_omits_the_range(tmp_path: Path) -> None:
    rows = [{"rank": 1, "target_id": "T-1"}]
    summary = table.render_large_summary(rows, tmp_path / "out.jsonl", _capabilities())
    assert not any("score range" in line for line in summary)


# --- preview ----------------------------------------------------------------


def test_diagnostic_id_with_and_without_salt() -> None:
    from datetime import UTC, datetime

    fixed = datetime(2026, 7, 31, 18, 42, 11, tzinfo=UTC)
    assert preview.diagnostic_id(now=fixed) == "NEO-20260731-184211"

    salted = preview.diagnostic_id(now=fixed, salt="create-new-search")
    assert salted.startswith("NEO-20260731-184211-")
    # Deterministic for a given salt, so the same failure yields the same id.
    assert salted == preview.diagnostic_id(now=fixed, salt="create-new-search")


def test_failure_rendering_reports_non_resumable_state() -> None:
    lines = preview.render_failure(
        summary="manifest could not be frozen",
        resumable=False,
        diagnostic="NEO-1",
        capabilities=_capabilities(),
    )
    assert any("was not modified" in line for line in lines)


def test_failure_log_captures_the_detail_the_terminal_omits(tmp_path: Path) -> None:
    log_path = tmp_path / "logs" / "failures.log"
    preview.write_failure_log(
        log_path,
        diagnostic="NEO-1",
        summary="connection closed",
        detail="Traceback (most recent call last): ...",
    )
    written = log_path.read_text()

    assert "NEO-1" in written
    assert "Traceback" in written


# --- registry and palette ---------------------------------------------------


def test_availability_predicates_report_reasons() -> None:
    empty = registry.ShellState()
    ready = registry.ShellState(pending_search_ids=("S-1",), last_result_count=3)

    run_command = registry.lookup("/Run-Search")
    assert not run_command.availability(empty).enabled
    assert run_command.availability(ready).enabled

    inspect_command = registry.lookup("/Inspect-Target")
    assert "identifier" in inspect_command.availability(empty).reason
    assert inspect_command.availability(ready).enabled


def test_build_argv_skips_blank_values_and_handles_latest() -> None:
    run_command = registry.lookup("/Run-Search")
    assert run_command.build_argv({"search-id": "--latest"}) == ["run-new-search", "--latest"]
    assert run_command.build_argv({"search-id": None}) == ["run-new-search"]
    assert run_command.build_argv({}) == ["run-new-search"]


def test_help_text_lists_commands_and_keyboard_help() -> None:
    text = registry.help_text(registry.ShellState())
    assert "/Inspect-Target" in text
    assert "Keyboard" in text
    assert "open the searchable command palette" in text


def test_required_field_order_places_required_fields_first() -> None:
    fields = registry.required_field_order(registry.lookup("/New-Search"), include_advanced=True)
    assert fields[0].required
    assert any(field.advanced for field in fields)


def test_palette_reports_no_match() -> None:
    lines = palette.render_palette("zzz", _capabilities(), registry.ShellState())
    assert any("no matching command" in line for line in lines)


def test_field_state_sentinels_cover_every_condition() -> None:
    capabilities = _capabilities()
    spec = registry.lookup("/New-Search").params[0]

    empty = palette.FieldState(spec=spec)
    empty.validate()
    assert "Required" in empty.sentinel(capabilities)

    bad = palette.FieldState(spec=spec, raw="twenty")
    bad.validate()
    assert "Invalid" in bad.sentinel(capabilities)

    good = palette.FieldState(spec=spec, raw="5")
    good.validate()
    assert "OK" in good.sentinel(capabilities)

    optional_spec = registry.lookup("/Show-Follow-Ups").params[0]
    blank_optional = palette.FieldState(spec=optional_spec)
    blank_optional.raw = ""
    blank_optional.validate()
    assert blank_optional.is_valid


def test_guided_entry_builds_argv_from_supplied_values() -> None:
    emitted: list[str] = []
    answers = iter(["5"])

    argv = palette.run_guided_entry(
        registry.lookup("/New-Search"),
        _capabilities(),
        read_field=lambda _spec, _current: next(answers),
        emit=emitted.append,
    )

    assert argv == ["create-new-search", "--mode", "new", "--targets", "5"]
    assert emitted, "guided entry must render the field editor"


def test_guided_entry_reprompts_until_valid() -> None:
    answers = iter(["twenty", "0", "7"])
    argv = palette.run_guided_entry(
        registry.lookup("/New-Search"),
        _capabilities(),
        read_field=lambda _spec, _current: next(answers),
        emit=lambda _line: None,
    )
    assert "7" in argv


def test_guided_entry_can_be_cancelled() -> None:
    result = palette.run_guided_entry(
        registry.lookup("/New-Search"),
        _capabilities(),
        read_field=lambda _spec, _current: palette.CANCELLED,
        emit=lambda _line: None,
    )
    assert result is palette.CANCELLED


def test_guided_entry_returns_immediately_for_parameterless_commands() -> None:
    argv = palette.run_guided_entry(
        registry.lookup("/Help"),
        _capabilities(),
        read_field=lambda _spec, _current: "",
        emit=lambda _line: None,
    )
    assert argv == [""]


def test_resolve_command_line_handles_empty_and_unknown_input() -> None:
    assert palette.resolve_command_line("") == (None, ())
    command, tokens = palette.resolve_command_line("/New-Search 5 --neo-class aten")
    assert command.name == "/New-Search"
    assert tokens == ("5", "--neo-class", "aten")


def test_prompt_line_falls_back_to_input_for_non_tty(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: "typed")
    assert palette.prompt_line(_capabilities(is_tty=False)) == "typed"


def test_prompt_line_uses_the_session_on_a_terminal() -> None:
    class _Session:
        def prompt(self, message: str) -> str:
            return f"session:{message.strip()}"

    result = palette.prompt_line(
        _capabilities(is_tty=True), "NEOHunter> ", session=_Session()
    )
    assert result == "session:NEOHunter>"


def test_prompt_session_completes_slash_commands() -> None:
    """UX-CMD-01: the completer offers commands the instant '/' is typed."""
    from prompt_toolkit.document import Document

    session = palette._build_prompt_session(_capabilities(is_tty=True))
    completer = session.completer

    completions = list(completer.get_completions(Document("/new"), None))
    assert any(item.text == "/New-Search" for item in completions)
    assert all(item.display_meta for item in completions)

    # Non-slash input and argument positions must not trigger the palette.
    assert list(completer.get_completions(Document("plain"), None)) == []
    assert list(completer.get_completions(Document("/New-Search 5"), None)) == []
