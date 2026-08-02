"""NEO-domain startup identity and stage-aware execution progress.

Specification requirements implemented here:

* UX-START-01 -- interactive startup begins immediately with a prominent
  animated identity; a static logo or generic spinner alone is nonconforming.
* UX-START-02 -- NEOHunter's themes: orbital sweep, radar acquisition,
  trajectory projection, close-approach geometry, moving-object survey, and
  telescope scan. All six appear in the startup sequence below.
* UX-START-03 -- truthful presentation. Nothing here renders a discovery, a
  target count, a percentage, or a data state. The frames are pure ornament plus
  a fixed identity string; every number the operator sees comes from the
  canonical pipeline, never from this module.
* UX-RUN-01/UX-RUN-02 -- execution progress corresponds to real pipeline stages
  and reports only measured quantities.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TextIO

from . import theme
from .theme import Capabilities

# Canonical NEOHunter pipeline stages, in execution order. These names mirror the
# stages the specification lists for NEOHunter and are the labels the execution
# renderer is allowed to display.
PIPELINE_STAGES: tuple[str, ...] = (
    "survey discovery",
    "orbit resolution",
    "known-object exclusion",
    "trajectory propagation",
    "observability scoring",
    "close-approach ranking",
)

# Radar sweep: a beam rotating through a fixed aperture.
_RADAR_FRAMES = ("|", "/", "-", "\\")

# Orbital sweep: a body transiting its orbit past a focus, with the focus fixed.
_ORBIT_FRAMES_UNICODE = (
    "●·····☉·····",
    "··●···☉·····",
    "····●·☉·····",
    "······☉●····",
    "······☉···●·",
    "······☉·····●",
)
_ORBIT_FRAMES_ASCII = (
    "o-----*-----",
    "--o---*-----",
    "----o-*-----",
    "------*o----",
    "------*---o-",
    "------*-----o",
)

# Telescope scan: a widening acquisition field.
_SCAN_FRAMES_UNICODE = ("▁▁▁▁▁", "▂▂▁▁▁", "▃▃▂▁▁", "▄▄▃▂▁", "▅▅▄▃▂", "▆▆▅▄▃")
_SCAN_FRAMES_ASCII = (".....", ":....", "::...", ":::..", "::::.", ":::::")

# Trajectory projection: a track extending ahead of a detection.
_TRACK_FRAMES_UNICODE = ("→", "⇢", "⇒", "⟹")
_TRACK_FRAMES_ASCII = ("->", "-->", "--->", "---->")

_IDENTITY_ASCII = (
    "  _   _ ___ ___  _  _ _   _ _  _ _____ ___ ___ ",
    " | \\ | | __/ _ \\| || | | | | \\| |_   _| __| _ \\",
    " |  \\| | _| (_) | __ | |_| | .` | | | | _||   /",
    " |_|\\__|___\\___/|_||_|\\___/|_|\\_| |_| |___|_|_\\",
)

# Fixed, factual subtitle. Contains no data-dependent claim.
_IDENTITY_SUBTITLE = "Near-Earth Object discovery console"

# Distribution that provides this product, used to report the running version.
_DISTRIBUTION = "neo-detection"


def product_version() -> str:
    """Version of the installed product, or ``unknown`` when it cannot be read.

    Read from installed distribution metadata rather than a hard-coded constant,
    so the banner reports the version the operator is actually running instead of
    the version the source tree last claimed. An uninstalled source checkout has
    no metadata; ``unknown`` is reported rather than a guess.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(_DISTRIBUTION)
    except PackageNotFoundError:
        return "unknown"


@dataclass(frozen=True)
class StageProgress:
    """One measured progress observation from the canonical pipeline.

    Every field is a real count supplied by the caller. ``total`` may be ``None``
    when the pipeline genuinely does not know it yet -- in that case no
    percentage and no estimate is rendered, per UX-RUN-02's prohibition on
    fabricated progress.
    """

    stage: str
    completed: int = 0
    total: int | None = None
    candidates_found: int = 0
    candidates_rejected: int = 0
    expansion_round: int | None = None
    current_source: str = ""
    elapsed_seconds: float = 0.0

    def render(self) -> str:
        """Format the observation, omitting anything not actually known."""
        parts = [self.stage]
        if self.total is not None and self.total > 0:
            share = 100.0 * self.completed / self.total
            parts.append(f"{self.completed}/{self.total} ({share:.0f}%)")
        elif self.completed:
            parts.append(f"{self.completed} done")
        if self.candidates_found:
            parts.append(f"found {self.candidates_found}")
        if self.candidates_rejected:
            parts.append(f"rejected {self.candidates_rejected}")
        if self.expansion_round is not None:
            parts.append(f"round {self.expansion_round}")
        if self.current_source:
            parts.append(f"source {self.current_source}")
        if self.elapsed_seconds > 0:
            minutes, seconds = divmod(int(self.elapsed_seconds), 60)
            parts.append(f"elapsed {minutes}m{seconds:02d}s")
        return "  ".join(parts)


def _frames(capabilities: Capabilities, unicode_frames: Sequence[str], ascii_frames: Sequence[str]):
    """Choose glyphs the stream can actually encode (section 11 Unicode fallback)."""
    return unicode_frames if capabilities.unicode else ascii_frames


# Columns the block-letter banner needs. Below this it is replaced rather than
# truncated: half a letterform is noise, not identity.
_IDENTITY_ASCII_WIDTH = max(len(line) for line in _IDENTITY_ASCII)


def identity_lines(capabilities: Capabilities) -> list[str]:
    """Return the static identity banner, styled and fitted for this stream.

    Carries the product name and the running version: an operator reporting a
    problem, and any evidence transcript, must record which build produced the
    behaviour being described.

    On a terminal too narrow for the block-letter banner the banner is dropped
    entirely in favour of a one-line identity. Truncating the letterforms would
    leave unreadable fragments, and letting the terminal wrap them would be
    worse -- section 11 requires small widths to be supported, not merely
    survived.
    """
    version = product_version()
    if capabilities.width < _IDENTITY_ASCII_WIDTH:
        compact = theme.fit(
            f"NEOHunter {version} - {_IDENTITY_SUBTITLE}",
            capabilities.width,
            unicode_ok=capabilities.unicode,
        )
        return [capabilities.style(compact, "cyan", "bold")]

    lines = [capabilities.style(line, "cyan", "bold") for line in _IDENTITY_ASCII]
    subtitle = theme.fit(
        f"NEOHunter {version} - {_IDENTITY_SUBTITLE}",
        capabilities.width,
        unicode_ok=capabilities.unicode,
    )
    lines.append(capabilities.style(subtitle, "dim"))
    return lines


def startup_sequence(capabilities: Capabilities) -> Iterator[str]:
    """Yield the startup animation frames, newest first.

    Returned as an iterator of already-styled single-line frames so callers can
    drive the timing (or, in tests, consume them without sleeping at all).
    """
    orbit = _frames(capabilities, _ORBIT_FRAMES_UNICODE, _ORBIT_FRAMES_ASCII)
    scan = _frames(capabilities, _SCAN_FRAMES_UNICODE, _SCAN_FRAMES_ASCII)
    track = _frames(capabilities, _TRACK_FRAMES_UNICODE, _TRACK_FRAMES_ASCII)

    # Each labelled phase corresponds to one theme UX-START-02 lists for NEOHunter.
    for frame in scan:
        yield f"{capabilities.style(frame, 'blue')} telescope scan"
    for frame in _RADAR_FRAMES * 2:
        yield f"{capabilities.style(frame, 'green')} radar acquisition"
    for frame in orbit:
        yield f"{capabilities.style(frame, 'cyan')} orbital sweep"
    for frame in track:
        yield f"{capabilities.style(frame, 'magenta')} trajectory projection"
    for frame in orbit[::-1]:
        yield f"{capabilities.style(frame, 'yellow')} close-approach geometry"
    for frame in scan[::-1]:
        yield f"{capabilities.style(frame, 'blue')} moving-object survey"


def play_startup(
    stream: TextIO,
    capabilities: Capabilities,
    *,
    frame_seconds: float = 0.035,
    sleep=time.sleep,
) -> None:
    """Render the startup identity, animating only when the stream supports it.

    When animation is disabled the banner and a single summary line are still
    printed, so a log or CI transcript retains the domain identity without any
    control characters. That is the "degrade cleanly" half of UX-START-04.
    """
    for line in identity_lines(capabilities):
        print(line, file=stream)

    if not capabilities.animation:
        print(
            capabilities.style(
                "orbital sweep | radar acquisition | trajectory projection", "dim"
            ),
            file=stream,
            flush=True,
        )
        return

    for frame in startup_sequence(capabilities):
        stream.write("\r\033[2K" + frame)
        stream.flush()
        sleep(frame_seconds)
    stream.write("\r\033[2K")
    stream.flush()


def render_stage(
    stream: TextIO,
    capabilities: Capabilities,
    progress: StageProgress,
) -> None:
    """Emit one measured pipeline-stage observation.

    On an animated terminal the line is rewritten in place; otherwise each
    observation is appended, which keeps logs readable and complete.
    """
    body = progress.render()
    label = capabilities.style("stage", "cyan")
    if capabilities.animation:
        stream.write(f"\r\033[2K{label} {body}")
        stream.flush()
        return
    print(f"{label} {body}", file=stream, flush=True)


def finish_stage(stream: TextIO, capabilities: Capabilities) -> None:
    """Terminate an in-place animated stage line so later output starts clean."""
    if capabilities.animation:
        stream.write("\n")
        stream.flush()
