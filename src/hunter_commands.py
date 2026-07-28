"""Installed shell entry points for the canonical Hunter product workflow."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path


def _hunter_main() -> Callable[[list[str] | None], int]:
    """Load the repository-owned orchestration module without duplicating it."""
    skills_dir = Path(__file__).resolve().parents[1] / "Skills"
    if str(skills_dir) not in sys.path:
        sys.path.insert(0, str(skills_dir))
    from hunter_cli import main

    return main


def create_new_search() -> int:
    """Create one exact durable new/follow-up search manifest."""
    return _hunter_main()(["create-new-search", *sys.argv[1:]])


def run_new_search() -> int:
    """Execute or resume one exact durable pending search."""
    return _hunter_main()(["run-new-search", *sys.argv[1:]])


def show_follow_ups() -> int:
    """Show actionable durable follow-up evidence."""
    return _hunter_main()(["show-follow-ups", *sys.argv[1:]])


def neo_hunter() -> int:
    """Launch the persistent slash-command NEOHunter terminal."""
    skills_dir = Path(__file__).resolve().parents[1] / "Skills"
    if str(skills_dir) not in sys.path:
        sys.path.insert(0, str(skills_dir))
    from hunter_shell import main

    return main(sys.argv[1:])
