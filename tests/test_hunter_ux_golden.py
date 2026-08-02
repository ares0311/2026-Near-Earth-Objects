"""Golden UX tests for the NEOHunter terminal (CLI/UX specification section 13).

The specification is explicit that these must not require byte-identical,
timing-dependent animation frames. Each golden file therefore captures a
*stable semantic rendering* -- command descriptions, field labels, validation
messages, stage names, table integrity, and non-TTY behaviour -- produced with
fixed capabilities so the output cannot vary with the host terminal.

Regenerate after an intentional presentation change with::

    NEOHUNTER_REGENERATE_GOLDEN=1 PYTHONPATH=src uv run --python 3.14 \
        python -m pytest tests/test_hunter_ux_golden.py

and review the resulting diff before committing it.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Skills"))

import hunter_shell  # noqa: E402
from hunter_ux import animation, palette, preview, registry, table, theme  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

# Sibling repositories own their own startup goldens; this repository is
# NEOHunter, so startup_exo.txt and startup_techno.txt are Not applicable here
# and are deliberately absent rather than faked.
EXPECTED_GOLDEN_FILES = (
    "startup_neo.txt",
    "command_palette.txt",
    "new_search_fields.txt",
    "invalid_targets.txt",
    "action_preview.txt",
    "results_table_80_columns.txt",
    "results_table_140_columns.txt",
    "operator_error.txt",
    "non_tty_output.txt",
)


def _fixed(width: int = 100, *, tty: bool = False) -> theme.Capabilities:
    """Capabilities pinned to constants so goldens are host-independent."""
    return theme.Capabilities(
        is_tty=tty, color=False, animation=tty, unicode=True, width=width
    )


class _Stream(io.StringIO):
    def __init__(self, tty: bool = False) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def _assert_golden(name: str, rendered: str) -> None:
    """Compare against the committed golden, or regenerate when asked."""
    path = GOLDEN_DIR / name
    payload = rendered.rstrip("\n") + "\n"
    if os.environ.get("NEOHUNTER_REGENERATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        return
    assert path.is_file(), (
        f"missing golden file {path}; regenerate with NEOHUNTER_REGENERATE_GOLDEN=1"
    )
    assert path.read_text(encoding="utf-8") == payload


def _rows(count: int) -> list[dict[str, object]]:
    """Deterministic result rows; no randomness, no clock, no host data."""
    return [
        {
            "rank": index + 1,
            "target_id": f"NEO-FIELD-{index:04d}",
            "neo_class": "aten",
            "ra_deg": round(217.41 + index, 2),
            "dec_deg": round(-15.0 + index, 2),
            "score": round(0.93 - index * 0.01, 4),
            "nights": 3,
            "storage_mb": 512.0,
            "status": "pending",
        }
        for index in range(count)
    ]


def test_golden_startup_neo() -> None:
    """UX-START-01/02: the domain identity and every NEO theme are stable."""
    capabilities = _fixed(tty=True)
    # The banner reports the running version, which necessarily changes on every
    # release. Substituting a stable token keeps this golden asserting the
    # *semantics* -- name, version presence, subtitle, themes -- rather than
    # turning a routine version bump into a test failure.
    version = animation.product_version()
    lines = [
        line.replace(f"NEOHunter {version}", "NEOHunter <version>")
        for line in animation.identity_lines(capabilities)
    ]
    assert any("<version>" in line for line in lines), (
        "the startup banner must report the running product version"
    )
    # Frame glyphs are timing-dependent; the *labels* are the stable semantics.
    labels: list[str] = []
    for frame in animation.startup_sequence(capabilities):
        label = frame.split(" ", 1)[1]
        if label not in labels:
            labels.append(label)
    _assert_golden("startup_neo.txt", "\n".join([*lines, "", *labels]))


def test_golden_command_palette() -> None:
    """UX-CMD-01/02: the palette a bare '/' opens."""
    state = registry.ShellState(pending_search_ids=(), last_result_count=0)
    rendered = palette.render_palette("", _fixed(), state)
    _assert_golden("command_palette.txt", "\n".join(rendered))


def test_golden_new_search_fields() -> None:
    """UX-IN-01/02: guided field entry with defaults and descriptions."""
    form = palette.GuidedForm.for_command(registry.lookup("/New-Search"))
    _assert_golden("new_search_fields.txt", "\n".join(form.render(_fixed(), 0)))


def test_golden_invalid_targets() -> None:
    """UX-IN-03: live validity sentinels for the specified bad inputs."""
    from hunter_ux import validation

    lines: list[str] = []
    for raw in ("twenty", "0", "-3", "abc123", ""):
        _value, error = validation.validate_target_count(raw)
        lines.append(f"Targets: {raw!r}")
        lines.append(f"  {error}")
    _assert_golden("invalid_targets.txt", "\n".join(lines))


def test_golden_action_preview() -> None:
    """Specification section 8: the resolved-action preview block."""
    action = preview.ResolvedAction(
        mode="new",
        requested_targets=5,
        scientific_constraints={"neo-class": "aten"},
        primary_sources=("ZTF DR24 (IRSA)",),
        source_freshness="coverage inventory rebuilt during discovery",
        history_freshness="hunter_state search history, read at creation",
        estimated_universe="planning grid, expanded adaptively until sufficient",
        estimated_storage="512 MB per target (estimated)",
        estimated_compute="bounded local workers",
        output_behavior="durable pending manifest; no external submission",
    )
    _assert_golden("action_preview.txt", "\n".join(preview.render_preview(action, _fixed())))


@pytest.mark.parametrize("width", [80, 140])
def test_golden_results_table(width: int) -> None:
    """UX-TABLE-01: width-aware table integrity at two terminal widths."""
    rendered = table.render_table(_rows(6), _fixed(width=width))
    for line in rendered:
        assert len(line) <= width
    _assert_golden(f"results_table_{width}_columns.txt", "\n".join(rendered))


def test_golden_operator_error() -> None:
    """UX-RUN-03: concise, actionable failure with a diagnostic identifier."""
    lines = preview.render_failure(
        summary="IRSA connection closed before the response completed.",
        attempt=2,
        total_attempts=3,
        resumable=True,
        # Pinned rather than generated, so the golden has no clock dependence.
        diagnostic="NEO-20260731-184211",
        capabilities=_fixed(),
    )
    _assert_golden("operator_error.txt", "\n".join(lines))


def test_golden_non_tty_output() -> None:
    """UX-START-04: redirected output keeps identity, drops control characters."""
    stream = _Stream(tty=False)
    capabilities = _fixed(tty=False)
    animation.play_startup(stream, capabilities)
    hunter_shell.execute_slash_command(
        "/",
        runner=lambda _argv: 0,
        stream=stream,
        err=stream,
        capabilities=capabilities,
    )
    # Same version normalization as the startup golden: assert the version is
    # present and reported, not that it is one particular release.
    version = animation.product_version()
    rendered = stream.getvalue().replace(f"NEOHunter {version}", "NEOHunter <version>")

    assert "\033" not in rendered, "non-TTY output must contain no ANSI sequences"
    _assert_golden("non_tty_output.txt", rendered)


def test_every_applicable_golden_file_exists() -> None:
    """Guard against a golden being silently dropped from the suite."""
    missing = [
        name for name in EXPECTED_GOLDEN_FILES if not (GOLDEN_DIR / name).is_file()
    ]
    assert not missing, f"missing golden files: {missing}"
