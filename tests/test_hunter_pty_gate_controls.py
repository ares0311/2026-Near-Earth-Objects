"""Independent negative controls for terminal restoration acceptance."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Skills"))

import hunter_pty_gate as gate  # noqa: E402


def test_cursor_that_was_never_hidden_is_restored() -> None:
    assert gate.cursor_visibility_restored(b"plain terminal output")


def test_cursor_show_after_hide_is_restored() -> None:
    transcript = b"start" + gate.CURSOR_HIDE + b"paint" + gate.CURSOR_SHOW
    assert gate.cursor_visibility_restored(transcript)


def test_cursor_hide_without_later_show_is_rejected() -> None:
    transcript = gate.CURSOR_SHOW + b"paint" + gate.CURSOR_HIDE
    assert not gate.cursor_visibility_restored(transcript)
