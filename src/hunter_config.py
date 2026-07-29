"""Explicit resource and mutable-state path resolution for NEO-Hunter."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _checkout_root() -> Path | None:
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "pyproject.toml").is_file():
        return candidate
    return None


def _default_user_state_root(
    *, platform: str | None = None, operating_system: str | None = None
) -> Path:
    platform = sys.platform if platform is None else platform
    operating_system = os.name if operating_system is None else operating_system
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "NEO-Hunter"
    if operating_system == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "NEO-Hunter"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "neo-hunter"


@dataclass(frozen=True)
class HunterPaths:
    """Resolved immutable-resource and mutable-state locations."""

    resource_root: Path
    state_root: Path

    @property
    def target_queue(self) -> Path:
        return self.resource_root / "data_selection" / "target_priority_queue.csv"

    @property
    def ranking_policy_dir(self) -> Path:
        return self.resource_root / "data_selection" / "ranking_policies"

    @property
    def static_coverage_dir(self) -> Path:
        return self.resource_root / "data_selection" / "coverage_inventories"

    @property
    def model_dir(self) -> Path:
        override = os.environ.get("NEOHUNTER_MODEL_ROOT")
        return Path(override).expanduser() if override else self.resource_root / "models"

    @property
    def hunter_db(self) -> Path:
        return self.state_root / "data_selection" / "hunter_state.sqlite"

    @property
    def candidate_ledger_db(self) -> Path:
        return self.state_root / "data_selection" / "candidate_ledger.sqlite"

    @property
    def search_manifest_dir(self) -> Path:
        return self.state_root / "data_selection" / "search_manifests"

    @property
    def batch_manifest_dir(self) -> Path:
        return self.state_root / "data_selection" / "batch_manifests"

    @property
    def runtime_coverage_dir(self) -> Path:
        return self.state_root / "data_selection" / "coverage_inventories"

    @property
    def work_dir(self) -> Path:
        return self.state_root / "Logs" / "pipeline_runs" / "hunter_cli"

    @property
    def checkpoint_dir(self) -> Path:
        return self.work_dir / "search_runs"

    @property
    def event_log(self) -> Path:
        return self.state_root / "Logs" / "reports" / "hunter_events.jsonl"

    @property
    def shell_history(self) -> Path:
        return self.state_root / "Logs" / "neo_hunter_history"


def get_hunter_paths() -> HunterPaths:
    """Resolve paths, preferring explicit environment configuration."""

    checkout = _checkout_root()
    resource_override = os.environ.get("NEOHUNTER_RESOURCE_ROOT")
    state_override = os.environ.get("NEOHUNTER_HOME")
    resource_root = (
        Path(resource_override).expanduser()
        if resource_override
        else checkout or Path(sys.prefix)
    )
    state_root = (
        Path(state_override).expanduser()
        if state_override
        else checkout or _default_user_state_root()
    )
    return HunterPaths(
        resource_root=resource_root.resolve(),
        state_root=state_root.resolve(),
    )
