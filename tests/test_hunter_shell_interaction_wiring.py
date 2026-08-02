"""Regression tests: guided entry and the action preview are reachable in production.

These exist because of a specific, verified defect. ``palette.run_guided_entry``
and ``preview.render_preview``/``ResolvedAction`` were fully implemented, fully
unit-tested, and had **no production caller** -- a grep across ``Skills/`` and
``src/`` found them referenced only by their own defining modules and by tests.
Contract rule PIPE-02 names exactly that condition ("code reachable only through
tests or direct imports"), and the golden tests that covered them were the
forbidden substitution of a renderer test for an operator-reachable path.

Every test here therefore drives ``hunter_shell.execute_slash_command`` -- the
function the interactive loop actually calls -- rather than the UX modules
directly. A test that imported ``palette`` and called ``run_guided_entry`` would
pass just as happily against the broken code and would prove nothing.

The real end-to-end proof is ``Skills/hunter_pty_gate.py``, which drives the
installed executable with real keystrokes in a real terminal. These tests are the
fast regression net beneath it, not a replacement for it.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Skills"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import hunter_shell  # noqa: E402
from hunter_ux import palette, registry, theme  # noqa: E402


def _capabilities() -> theme.Capabilities:
    """Deterministic non-TTY capabilities: no colour, no animation, fixed width."""
    return theme.Capabilities(
        is_tty=False, color=False, animation=False, unicode=True, width=100
    )


def _run(line: str, *, read_field=None, confirm=None, state=None):
    """Drive one slash command through the shell and capture what it produced."""
    out, err = io.StringIO(), io.StringIO()
    captured: list[list[str]] = []

    def runner(argv: list[str] | None) -> int:
        captured.append(list(argv or []))
        return 0

    should_exit, status = hunter_shell.execute_slash_command(
        line,
        runner=runner,
        stream=out,
        err=err,
        capabilities=_capabilities(),
        state=state or registry.ShellState(),
        read_field=read_field,
        confirm=confirm,
    )
    return {
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
        "argv": captured,
        "status": status,
        "should_exit": should_exit,
    }


# --- guided parameter entry (UX-IN-01, UX-IN-02, UX-IN-03) ------------------


def test_missing_required_argument_opens_guided_entry() -> None:
    """A bare /New-Search prompts for its required field instead of erroring."""
    asked: list[str] = []

    def read_field(spec: registry.ParamSpec, current: str) -> object:
        asked.append(spec.name)
        return "7"

    result = _run("/New-Search", read_field=read_field, confirm=lambda _block: True)

    assert asked == ["targets"], "guided entry must prompt for the required field"
    assert result["argv"] == [
        ["create-new-search", "--mode", "new", "--targets", "7"]
    ], "the guided value must reach the canonical pipeline unchanged"


def test_guided_entry_rejects_invalid_input_then_accepts_correction() -> None:
    """UX-IN-03: invalid input cannot advance; a correction proceeds normally."""
    answers = iter(["twenty", "0", "5"])

    def read_field(_spec: registry.ParamSpec, _current: str) -> object:
        return next(answers)

    result = _run("/New-Search", read_field=read_field, confirm=lambda _block: True)

    assert result["argv"] == [["create-new-search", "--mode", "new", "--targets", "5"]]
    # The rejected values must never have reached the pipeline.
    flattened = " ".join(result["argv"][0])
    assert "twenty" not in flattened and "--targets 0" not in flattened


def test_guided_entry_cancellation_executes_nothing() -> None:
    """Escaping out of guided entry must not run the command."""
    result = _run(
        "/New-Search",
        read_field=lambda _spec, _current: palette.CANCELLED,
        confirm=lambda _block: True,
    )

    assert result["argv"] == [], "a cancelled form must not invoke the pipeline"
    assert "cancelled" in result["stdout"].casefold()
    assert result["status"] == 0, "cancelling is a normal outcome, not a failure"


def test_scripted_path_still_errors_instead_of_prompting() -> None:
    """CLI-03: the non-interactive path keeps its actionable message.

    Guided entry must not leak into ``--command`` scripting, where there is no
    operator to answer a prompt and a blocked read would hang the process.
    """
    result = _run("/New-Search")  # no read_field: this is the scripted surface

    assert result["argv"] == []
    assert result["status"] == 2
    assert "requires targets" in result["stderr"].casefold()
    assert "traceback" not in result["stderr"].casefold()


def test_explicit_argument_bypasses_guided_entry() -> None:
    """Supplying the value inline must not re-prompt for it."""
    asked: list[str] = []

    def read_field(spec: registry.ParamSpec, _current: str) -> object:
        asked.append(spec.name)
        return "99"

    result = _run("/New-Search 5", read_field=read_field, confirm=lambda _block: True)

    assert asked == [], "an inline value must not trigger a prompt"
    assert result["argv"] == [["create-new-search", "--mode", "new", "--targets", "5"]]


# --- resolved-action preview (specification section 8) ----------------------


def test_freezing_command_shows_resolved_action_preview() -> None:
    """A search may not be frozen before the operator sees what will happen."""
    shown: list[list[str]] = []

    def confirm(block: list[str]) -> bool:
        shown.append(block)
        return True

    result = _run("/New-Search 5", confirm=confirm)

    assert shown, "no resolved-action preview was rendered before freezing"
    text = "\n".join(shown[0])
    for required_label in (
        "Resolved action",
        "Mode",
        "Requested targets",
        "Primary sources",
        "Estimated discovery universe",
        "Output behavior",
    ):
        assert required_label in text, f"preview is missing {required_label!r}"
    assert result["argv"], "confirming must proceed to the canonical pipeline"


def test_declining_the_preview_freezes_nothing() -> None:
    """The operator can cancel at the preview, and nothing is executed."""
    result = _run("/New-Search 5", confirm=lambda _block: False)

    assert result["argv"] == [], "declining the preview must not invoke the pipeline"
    assert "cancelled" in result["stdout"].casefold()


def test_preview_reports_mode_and_count_actually_resolved() -> None:
    """The preview must describe the real argument vector, not a plausible one."""
    shown: list[list[str]] = []
    _run("/Follow-Up-Search 3", confirm=lambda block: shown.append(block) or True)

    text = "\n".join(shown[0])
    assert "follow-up" in text
    assert "3" in text


def test_non_freezing_command_shows_no_preview() -> None:
    """Only manifest-freezing commands warrant a confirmation step."""
    shown: list[list[str]] = []
    _run(
        "/Show-Follow-Ups",
        confirm=lambda block: shown.append(block) or True,
    )

    assert shown == [], "a read-only command must not demand confirmation"


# --- startup identity -------------------------------------------------------


def test_startup_banner_reports_product_name_and_version() -> None:
    """The operator, and any evidence transcript, must record the build in use."""
    from hunter_ux import animation

    banner = "\n".join(animation.identity_lines(_capabilities()))
    version = animation.product_version()

    assert "NEOHunter" in banner
    assert version in banner
    assert version != "unknown", (
        "product version resolved to 'unknown'; the distribution metadata for "
        "neo-detection is not installed in this environment"
    )


@pytest.mark.parametrize("stripped", ["/", "  /  "])
def test_bare_slash_still_renders_the_palette(stripped: str) -> None:
    """Regression guard: wiring guided entry must not break palette discovery."""
    result = _run(stripped)

    assert "/New-Search" in result["stdout"]
    assert result["status"] == 0


# --- the interactive loop's own hooks ---------------------------------------
#
# The tests above inject `read_field`/`confirm` directly. These drive
# `run_interactive`, which is where those two callables are actually
# constructed -- otherwise the shell could build them incorrectly and every test
# above would still pass.


def _interactive(answers: list[str], tmp_path: Path) -> dict[str, object]:
    """Run the real interactive loop against a scripted operator."""
    supplied = iter(answers)
    out, err = io.StringIO(), io.StringIO()
    captured: list[list[str]] = []

    def input_function(_prompt: str) -> str:
        try:
            return next(supplied)
        except StopIteration:
            raise EOFError from None

    status = hunter_shell.run_interactive(
        runner=lambda argv: (captured.append(list(argv or [])), 0)[1],
        input_function=input_function,
        stream=out,
        err=err,
        history_path=tmp_path / "history",
        capabilities=_capabilities(),
    )
    return {"status": status, "stdout": out.getvalue(), "argv": captured}


def test_interactive_loop_guides_then_confirms(tmp_path: Path) -> None:
    """End to end through run_interactive: prompt, preview, confirm, execute."""
    result = _interactive(["/New-Search", "5", "y", "/Exit"], tmp_path)

    assert result["argv"] == [["create-new-search", "--mode", "new", "--targets", "5"]]
    assert "Resolved action" in result["stdout"]
    assert result["status"] == 0


def test_interactive_loop_declining_confirmation_executes_nothing(tmp_path: Path) -> None:
    """Answering anything other than yes at the preview cancels the search."""
    result = _interactive(["/New-Search", "5", "n", "/Exit"], tmp_path)

    assert result["argv"] == []
    assert "cancelled" in result["stdout"].casefold()


def test_interactive_loop_blank_answer_keeps_the_visible_default(tmp_path: Path) -> None:
    """UX-IN-02: a visible default is accepted by pressing Enter, not cleared."""
    result = _interactive(["/New-Search", "", "y", "/Exit"], tmp_path)

    # The registry's declared default for targets is 20, shown in the editor.
    assert result["argv"] == [["create-new-search", "--mode", "new", "--targets", "20"]]


def test_interactive_loop_eof_during_guided_entry_cancels(tmp_path: Path) -> None:
    """Ctrl-D partway through a form cancels it rather than executing a partial."""
    result = _interactive(["/New-Search"], tmp_path)

    assert result["argv"] == []
    assert result["status"] == 0
