"""Terminal capability detection and colour handling.

Specification UX-START-04 and section 11 require animation and colour to degrade
cleanly for non-TTY output, redirected output, logs, CI, explicit no-animation
mode, accessibility/reduced-motion mode, and machine-readable output. Doing that
detection in one place keeps every renderer honest: a module that asks
``capabilities.animation`` cannot accidentally animate into a log file.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import TextIO

# Minimum width the table renderer will target. Below this we stop trying to
# lay out columns and fall back to a stacked record view.
MIN_TABLE_WIDTH = 40

# Width assumed when the stream is not a terminal (logs, pipes, CI capture).
DEFAULT_NON_TTY_WIDTH = 80

_RESET = "\033[0m"
_STYLES = {
    "reset": _RESET,
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "blue": "\033[34m",
}


@dataclass(frozen=True)
class Capabilities:
    """What this output stream can actually support, right now."""

    is_tty: bool
    color: bool
    animation: bool
    unicode: bool
    width: int

    def style(self, text: str, *names: str) -> str:
        """Apply styles, or return the text unchanged when colour is disabled."""
        if not self.color or not names:
            return text
        prefix = "".join(_STYLES.get(name, "") for name in names)
        return f"{prefix}{text}{_RESET}" if prefix else text


def fit(text: str, width: int, *, unicode_ok: bool = True) -> str:
    """Trim ``text`` to ``width`` columns, marking that trimming happened.

    Specification section 11 requires small terminal widths to be supported, and
    UX-TABLE-01 requires truncation to be intentional and visibly marked rather
    than left to the terminal's own wrapping -- an uncontrolled wrap turns one
    row into two and destroys the alignment the reader is relying on.

    Applied to unstyled text only. Styling is added after fitting, because ANSI
    escape sequences occupy no columns but would otherwise be counted here.
    """
    if width <= 0 or len(text) <= width:
        return text
    marker = "…" if unicode_ok else "..."
    if width <= len(marker):
        return marker[:width]
    return text[: width - len(marker)] + marker


def _truthy_env(name: str) -> bool:
    """Treat presence of a variable as opting in, matching common CLI convention.

    ``NO_COLOR`` is specified as "presence means disable, regardless of value",
    so an empty string still counts.
    """
    return name in os.environ


def _detect_unicode(stream: TextIO) -> bool:
    """Decide whether box-drawing and domain glyphs are safe to emit."""
    encoding = (getattr(stream, "encoding", None) or "").casefold()
    if not encoding:
        return False
    return "utf" in encoding


def detect(
    stream: TextIO,
    *,
    no_color: bool = False,
    no_animation: bool = False,
    reduced_motion: bool = False,
    machine_readable: bool = False,
    environ: dict[str, str] | None = None,
) -> Capabilities:
    """Resolve capabilities for one output stream.

    ``machine_readable`` forces the most conservative result: UX-TABLE-04
    requires machine output to carry no animation, no ANSI control sequences,
    and no interactive prompts.
    """
    env = os.environ if environ is None else environ
    is_tty = bool(getattr(stream, "isatty", lambda: False)())

    color = (
        is_tty
        and not no_color
        and not machine_readable
        and "NO_COLOR" not in env
        and env.get("NEOHUNTER_NO_COLOR") is None
        and env.get("TERM", "") != "dumb"
    )

    animation = (
        is_tty
        and not no_animation
        and not reduced_motion
        and not machine_readable
        and env.get("NEOHUNTER_NO_ANIMATION") is None
        and env.get("NEOHUNTER_REDUCED_MOTION") is None
        # Continuous integration captures output; animating into a captured log
        # produces unreadable control-character noise.
        and "CI" not in env
    )

    if is_tty:
        width = shutil.get_terminal_size(fallback=(DEFAULT_NON_TTY_WIDTH, 24)).columns
    else:
        width = DEFAULT_NON_TTY_WIDTH

    return Capabilities(
        is_tty=is_tty,
        color=color,
        animation=animation,
        unicode=_detect_unicode(stream) and not machine_readable,
        width=max(width, MIN_TABLE_WIDTH),
    )


def restore(stream: TextIO, capabilities: Capabilities) -> None:
    """Return the terminal to a sane state after an exception or cancellation.

    Section 11 requires the UI to restore terminal state. Clearing any partial
    animation line and resetting attributes is sufficient here because the
    renderers never enter an alternate screen buffer or hide the cursor for
    longer than a single frame.
    """
    if not capabilities.is_tty:
        return
    try:
        # Erase the current line, then drop any lingering colour attributes.
        stream.write("\r\033[2K")
        if capabilities.color:
            stream.write(_RESET)
        stream.flush()
    except (OSError, ValueError):
        # A closed or detached stream is not a reason to crash on the way out.
        return
