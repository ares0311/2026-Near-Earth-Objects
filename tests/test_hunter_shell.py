"""Behavioral controls for the persistent NEOHunter terminal."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Skills"))

import hunter_shell  # noqa: E402


@pytest.mark.parametrize(
    ("line", "kind", "expected"),
    [
        (
            "/New-Search 5 --neo-class aten",
            "new-search",
            [
                "create-new-search",
                "--targets",
                "5",
                "--mode",
                "new",
                "--neo-class",
                "aten",
            ],
        ),
        (
            "/Follow-Up-Search 2 --db state.sqlite",
            "follow-up-search",
            [
                "create-new-search",
                "--targets",
                "2",
                "--mode",
                "follow-up",
                "--db",
                "state.sqlite",
            ],
        ),
        ("/Run-Search", "run-search", ["run-new-search", "--latest"]),
        (
            "/Run-Search search_new_123 --db state.sqlite",
            "run-search",
            ["run-new-search", "--search-id", "search_new_123", "--db", "state.sqlite"],
        ),
        (
            "/Run-Search --latest --db state.sqlite",
            "run-search",
            ["run-new-search", "--latest", "--db", "state.sqlite"],
        ),
        (
            "/Show-Follow-Ups --status all",
            "show-follow-ups",
            ["show-follow-ups", "--status", "all"],
        ),
        (
            "/Create-New-Search 3",
            "new-search",
            ["create-new-search", "--targets", "3", "--mode", "new"],
        ),
        ("/Run-New-Search", "run-search", ["run-new-search", "--latest"]),
    ],
)
def test_translate_slash_commands_to_canonical_pipeline(
    line: str, kind: str, expected: list[str]
) -> None:
    assert hunter_shell._translate_command(line) == (kind, expected)


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("/New-Search", "usage"),
        ("/New-Search nope", "integer target count"),
        ("/New-Search 0", "must be positive"),
        ("/Help extra", "usage"),
        ("/Exit now", "usage"),
        ("/Unknown", "unknown command"),
        ('/New-Search "unterminated', "could not parse"),
    ],
)
def test_translate_rejects_invalid_commands_loudly(line: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        hunter_shell._translate_command(line)


def test_slash_lists_required_commands_and_completion() -> None:
    assert hunter_shell._translate_command("/") == ("help", None)
    assert hunter_shell._translate_command("") == ("noop", None)
    assert hunter_shell._completion_candidates("/F") == ["/Follow-Up-Search"]
    assert hunter_shell._completion_candidates("/show") == ["/Show-Follow-Ups"]
    assert hunter_shell._readline_complete("/New", 0) == "/New-Search"
    assert hunter_shell._readline_complete("/New", 1) is None


def test_execute_delegates_once_and_preserves_canonical_status() -> None:
    seen: list[list[str] | None] = []
    stream = io.StringIO()
    err = io.StringIO()

    should_exit, status = hunter_shell.execute_slash_command(
        "/New-Search 4 --neo-class ieo",
        runner=lambda argv: seen.append(argv) or 0,
        stream=stream,
        err=err,
        color=False,
        animation=False,
    )

    assert should_exit is False
    assert status == 0
    assert seen == [
        [
            "create-new-search",
            "--targets",
            "4",
            "--mode",
            "new",
            "--neo-class",
            "ieo",
        ]
    ]
    assert "adaptive discovery" in stream.getvalue()
    assert "orbital-sweep" in stream.getvalue()
    assert err.getvalue() == ""


def test_execute_surfaces_pipeline_system_exit_and_keeps_state_resumable() -> None:
    def fail(_argv: list[str] | None) -> int:
        raise SystemExit("provider unavailable")

    stream = io.StringIO()
    err = io.StringIO()
    should_exit, status = hunter_shell.execute_slash_command(
        "/Run-Search",
        runner=fail,
        stream=stream,
        err=err,
        color=False,
        animation=False,
    )

    assert should_exit is False
    assert status == 1
    assert "provider unavailable" in err.getvalue()
    assert "durable state is resumable" in err.getvalue()


def test_execute_handles_help_exit_noop_and_validation_error_without_runner() -> None:
    calls = 0

    def runner(_argv: list[str] | None) -> int:
        nonlocal calls
        calls += 1
        return 0

    stream = io.StringIO()
    err = io.StringIO()
    assert hunter_shell.execute_slash_command(
        "", runner=runner, stream=stream, err=err, color=False, animation=False
    ) == (False, 0)
    assert hunter_shell.execute_slash_command(
        "/", runner=runner, stream=stream, err=err, color=False, animation=False
    ) == (False, 0)
    assert hunter_shell.execute_slash_command(
        "/Nope", runner=runner, stream=stream, err=err, color=False, animation=False
    ) == (False, 2)
    assert hunter_shell.execute_slash_command(
        "/Exit", runner=runner, stream=stream, err=err, color=False, animation=False
    ) == (True, 0)
    assert calls == 0
    assert "/Follow-Up-Search" in stream.getvalue()
    assert "unknown command" in err.getvalue()


def test_script_mode_stops_on_first_failed_command() -> None:
    seen: list[list[str] | None] = []

    def runner(argv: list[str] | None) -> int:
        seen.append(argv)
        return 3

    status = hunter_shell.main(
        [
            "--no-color",
            "--no-animation",
            "--command",
            "/Show-Follow-Ups",
            "--command",
            "/Run-Search",
        ],
        runner=runner,
        stream=io.StringIO(),
        err=io.StringIO(),
    )

    assert status == 3
    assert seen == [["show-follow-ups"]]


def test_script_mode_exit_and_success_sequence() -> None:
    seen: list[list[str] | None] = []
    stream = io.StringIO()
    status = hunter_shell.main(
        [
            "--command",
            "/Show-Follow-Ups",
            "--command",
            "/Exit",
            "--command",
            "/Run-Search",
        ],
        runner=lambda argv: seen.append(argv) or 0,
        stream=stream,
        err=io.StringIO(),
    )

    assert status == 0
    assert seen == [["show-follow-ups"]]
    assert "\033[" not in stream.getvalue()


def test_interactive_session_persists_until_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = iter(["/", "/Show-Follow-Ups", "/Exit"])
    stream = io.StringIO()
    err = io.StringIO()
    seen: list[list[str] | None] = []
    monkeypatch.setattr(hunter_shell, "_configure_history", lambda path, err: False)

    status = hunter_shell.run_interactive(
        runner=lambda argv: seen.append(argv) or 0,
        input_function=lambda _prompt: next(commands),
        stream=stream,
        err=err,
        history_path=Path("unused"),
        color=False,
        animation=False,
    )

    assert status == 0
    assert seen == [["show-follow-ups"]]
    assert stream.getvalue().count("NEOHunter slash commands") == 2
    assert "session closed" in stream.getvalue()


def test_interactive_eof_and_keyboard_interrupt_are_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = iter([KeyboardInterrupt(), EOFError()])

    def input_function(_prompt: str) -> str:
        event = next(events)
        raise event

    stream = io.StringIO()
    monkeypatch.setattr(hunter_shell, "_configure_history", lambda path, err: False)
    status = hunter_shell.run_interactive(
        runner=lambda _argv: 0,
        input_function=input_function,
        stream=stream,
        err=io.StringIO(),
        history_path=Path("unused"),
        color=False,
        animation=False,
    )

    assert status == 0
    assert "Interrupted current prompt" in stream.getvalue()


def test_terminal_capabilities_disable_for_redirects_and_accessibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redirected = io.StringIO()
    assert hunter_shell._terminal_capabilities(
        redirected, no_color=False, no_animation=False
    ) == (False, False)

    class TTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    tty = TTY()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("NEOHUNTER_NO_ANIMATION", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert hunter_shell._terminal_capabilities(
        tty, no_color=False, no_animation=False
    ) == (True, True)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("NEOHUNTER_NO_ANIMATION", "1")
    assert hunter_shell._terminal_capabilities(
        tty, no_color=False, no_animation=False
    ) == (False, False)


def test_orbital_animation_is_bounded_and_domain_specific(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()
    delays: list[float] = []
    monkeypatch.setattr(hunter_shell.time, "sleep", delays.append)

    hunter_shell._orbital_event(
        "exact search execution",
        "acquire real products",
        stream=stream,
        color=False,
        animation=True,
    )

    output = stream.getvalue()
    assert len(delays) == len(hunter_shell._ORBIT_FRAMES)
    assert "o-----*-----." in output
    assert "orbital-sweep exact search execution" in output


def test_history_failures_are_visible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class BrokenReadline:
        __doc__ = "Importing this module enables command line editing using libedit readline."

        def __init__(self) -> None:
            self.binding = ""

        def set_completer_delims(self, _value: str) -> None:
            return None

        def set_completer(self, _value) -> None:
            return None

        def parse_and_bind(self, value: str) -> None:
            self.binding = value

        def read_history_file(self, _path: Path) -> None:
            raise OSError("cannot read")

        def write_history_file(self, _path: Path) -> None:
            raise OSError("cannot write")

    history = tmp_path / "history"
    history.write_text("old\n", encoding="utf-8")
    err = io.StringIO()
    fake_readline = BrokenReadline()
    monkeypatch.setattr(hunter_shell, "readline", fake_readline)

    assert hunter_shell._configure_history(history, err) is True
    hunter_shell._save_history(history, True, err)

    assert fake_readline.binding == "bind ^I rl_complete"
    assert "cannot read" in err.getvalue()
    assert "cannot write" in err.getvalue()


def test_gnu_readline_uses_portable_tab_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class GNUReadline:
        __doc__ = "Importing this module enables command line editing using GNU readline."

        def __init__(self) -> None:
            self.binding = ""

        def set_completer_delims(self, _value: str) -> None:
            return None

        def set_completer(self, _value) -> None:
            return None

        def parse_and_bind(self, value: str) -> None:
            self.binding = value

    fake_readline = GNUReadline()
    monkeypatch.setattr(hunter_shell, "readline", fake_readline)

    assert hunter_shell._configure_history(tmp_path / "missing", io.StringIO()) is True
    assert fake_readline.binding == "tab: complete"
