"""Resolved-action preview and operator-facing failure presentation.

Specification section 8 requires that, before a search is frozen, the operator
sees exactly what is about to happen and can confirm, edit, or cancel.
UX-RUN-03 requires failures to be concise and actionable in the terminal, with
the detailed traceback written to logs rather than shown as the primary
response.

Both are presentation concerns only: every value rendered here is supplied by
the caller from canonical state. This module never estimates a quantity the
pipeline has not actually reported -- an unknown field renders as ``unknown``
rather than as an invented number.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .theme import Capabilities

# Field order the specification lists for the preview block, verbatim.
PREVIEW_FIELD_ORDER: tuple[tuple[str, str], ...] = (
    ("mode", "Mode"),
    ("requested_targets", "Requested targets"),
    ("scientific_constraints", "Scientific constraints"),
    ("primary_sources", "Primary sources"),
    ("source_freshness", "Source freshness"),
    ("history_freshness", "Cross-project history freshness"),
    ("estimated_universe", "Estimated discovery universe"),
    ("estimated_storage", "Estimated storage"),
    ("estimated_compute", "Estimated compute"),
    ("output_behavior", "Output behavior"),
)

# Rendered when the caller has no verified value. Chosen over a plausible-looking
# placeholder so the preview can never imply knowledge the system lacks.
UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResolvedAction:
    """Everything the operator should see before a search is frozen."""

    mode: str
    requested_targets: int
    scientific_constraints: dict[str, Any] = field(default_factory=dict)
    primary_sources: tuple[str, ...] = ()
    source_freshness: str = ""
    history_freshness: str = ""
    estimated_universe: str = ""
    estimated_storage: str = ""
    estimated_compute: str = ""
    output_behavior: str = ""

    def as_display_map(self) -> dict[str, str]:
        """Flatten to display strings, substituting ``unknown`` where unset."""
        constraints = (
            ", ".join(
                f"{key}={value}"
                for key, value in sorted(self.scientific_constraints.items())
            )
            if self.scientific_constraints
            else "none"
        )
        return {
            "mode": self.mode,
            "requested_targets": str(self.requested_targets),
            "scientific_constraints": constraints,
            "primary_sources": ", ".join(self.primary_sources) or UNKNOWN,
            "source_freshness": self.source_freshness or UNKNOWN,
            "history_freshness": self.history_freshness or UNKNOWN,
            "estimated_universe": self.estimated_universe or UNKNOWN,
            "estimated_storage": self.estimated_storage or UNKNOWN,
            "estimated_compute": self.estimated_compute or UNKNOWN,
            "output_behavior": self.output_behavior or UNKNOWN,
        }


def render_preview(action: ResolvedAction, capabilities: Capabilities) -> list[str]:
    """Render the preview block in the specification's field order."""
    values = action.as_display_map()
    label_width = max(len(label) for _key, label in PREVIEW_FIELD_ORDER)
    lines = [capabilities.style("Resolved action", "cyan", "bold")]
    for key, label in PREVIEW_FIELD_ORDER:
        rendered = values[key]
        styled = (
            capabilities.style(rendered, "dim") if rendered == UNKNOWN else rendered
        )
        lines.append(f"  {label.ljust(label_width)}  {styled}")
    lines.append("")
    lines.append(capabilities.style("Confirm, edit, or cancel.", "dim"))
    return lines


def diagnostic_id(*, prefix: str = "NEO", now: datetime | None = None, salt: str = "") -> str:
    """Build a short, greppable diagnostic identifier for a failure.

    The identifier is what ties the concise terminal message to the full
    traceback in the log, which is how UX-RUN-03 keeps the interactive response
    short without losing detail.
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    if not salt:
        return f"{prefix}-{stamp}"
    digest = hashlib.sha256(salt.encode("utf-8")).hexdigest()[:4]
    return f"{prefix}-{stamp}-{digest}"


def render_failure(
    *,
    summary: str,
    attempt: int | None = None,
    total_attempts: int | None = None,
    resumable: bool = True,
    diagnostic: str,
    capabilities: Capabilities,
) -> list[str]:
    """Render a concise, actionable operator-facing failure.

    Mirrors the shape the specification gives as its example: what failed, which
    attempt, whether state survives, and the diagnostic identifier.
    """
    lines = [capabilities.style(summary, "red")]
    if attempt is not None and total_attempts is not None:
        lines.append(f"Attempt {attempt} of {total_attempts} failed.")
    lines.append(
        "Search state remains resumable."
        if resumable
        else "Search state was not modified."
    )
    lines.append(f"Diagnostic ID: {diagnostic}")
    return lines


def write_failure_log(
    log_path: Path,
    *,
    diagnostic: str,
    summary: str,
    detail: str,
) -> Path:
    """Append the full failure detail to the log the terminal message points at."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"--- {diagnostic} {stamp}\n{summary}\n{detail}\n")
    return log_path
