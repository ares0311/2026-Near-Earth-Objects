"""Width-aware result presentation, target detail view, and machine output.

Specification requirements implemented here:

* UX-TABLE-01 -- for ``N <= 100`` render a clean terminal table of
  decision-critical fields: detect terminal width, use stable column widths,
  truncate intentionally with a visible marker, avoid uncontrolled multi-line
  wrapping, preserve rank and identity visibility, paginate, support row
  selection.
* UX-TABLE-02 -- long explanations, provenance, and rationale live in the
  ``/Inspect-Target`` detail view, not in the table.
* UX-TABLE-03 -- for ``N > 100`` write a timestamped complete export, display a
  concise summary, and report the output path.
* UX-TABLE-04 -- stable machine-readable output with no animation, no ANSI, and
  no prompts.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .theme import Capabilities

# Above this many rows the specification requires an export plus a summary
# instead of a full interactive table.
LARGE_REQUEST_THRESHOLD = 100

# Default rows per page when paginating an interactive table.
DEFAULT_PAGE_SIZE = 20

# Visible truncation marker. A single character keeps column arithmetic exact.
TRUNCATION_MARKER = "~"


@dataclass(frozen=True)
class Column:
    """One table column with a stable width policy.

    ``min_width`` is the width below which the column is dropped entirely rather
    than being truncated into uselessness. ``priority`` orders that dropping:
    lower numbers survive longer, so rank and identity (priority 0) are the last
    things to go, satisfying UX-TABLE-01's "preserve rank and identity
    visibility".
    """

    key: str
    heading: str
    width: int
    min_width: int = 0
    priority: int = 5
    align_right: bool = False

    def __post_init__(self) -> None:
        if self.min_width == 0:
            object.__setattr__(self, "min_width", min(self.width, len(self.heading)))


# Decision-critical fields for a NEOHunter target manifest, in display order.
DEFAULT_COLUMNS: tuple[Column, ...] = (
    Column("rank", "#", width=4, priority=0, align_right=True),
    Column("target_id", "Target", width=22, priority=0),
    Column("neo_class", "Class", width=7, priority=3),
    Column("ra_deg", "RA", width=9, priority=2, align_right=True),
    Column("dec_deg", "Dec", width=9, priority=2, align_right=True),
    Column("score", "Score", width=7, priority=1, align_right=True),
    Column("nights", "Nights", width=7, priority=4, align_right=True),
    Column("storage_mb", "MB", width=8, priority=6, align_right=True),
    Column("status", "Status", width=12, priority=4),
)


def _cell(value: Any) -> str:
    """Render one value as a single line, never introducing a line break."""
    if value is None:
        return "-"
    if isinstance(value, float):
        # Six significant digits keeps sky coordinates readable to ~0.01 degree
        # (for example 217.41 rather than a truncated 217.4) while still
        # trimming trailing zeros so columns stay narrow.
        return f"{value:.6g}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"))
    return str(value).replace("\n", " ").replace("\r", " ")


def fit(text: str, width: int) -> str:
    """Fit text to an exact width, marking truncation visibly.

    Uncontrolled wrapping is what turns a result set into the unreadable
    multi-line record dump UX-TABLE-01 forbids, so this always returns exactly
    ``width`` characters.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text.ljust(width)
    if width == 1:
        return TRUNCATION_MARKER
    return text[: width - 1] + TRUNCATION_MARKER


def select_columns(columns: Sequence[Column], available_width: int) -> list[Column]:
    """Choose the columns that fit, dropping lowest-priority ones first.

    Column widths themselves stay stable -- the specification asks for stable
    column widths, so a narrow terminal loses whole columns rather than silently
    squeezing every column into illegibility.
    """
    chosen = sorted(columns, key=lambda column: (column.priority, columns.index(column)))
    kept: list[Column] = []
    used = 0
    for column in chosen:
        # One separating space precedes every column after the first.
        cost = column.width + (1 if kept else 0)
        if used + cost <= available_width:
            kept.append(column)
            used += cost
    # Restore declared display order rather than priority order.
    return [column for column in columns if column in kept]


def render_row(row: dict[str, Any], columns: Sequence[Column]) -> str:
    """Render one row to exactly the selected column widths."""
    cells = []
    for column in columns:
        text = _cell(row.get(column.key))
        fitted = fit(text, column.width)
        cells.append(fitted.rjust(column.width) if column.align_right else fitted)
    return " ".join(cells).rstrip()


def render_table(
    rows: Sequence[dict[str, Any]],
    capabilities: Capabilities,
    *,
    columns: Sequence[Column] = DEFAULT_COLUMNS,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[str]:
    """Render one page of a width-aware table.

    Returns a list of lines so callers can print, capture, or assert on them.
    """
    selected = select_columns(columns, capabilities.width)
    if not selected:
        # Degenerate terminal: fall back to a stacked view rather than emitting
        # a broken table.
        return render_stacked(rows, capabilities)

    total_pages = max(1, (len(rows) + page_size - 1) // page_size)
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    window = rows[start : start + page_size]

    heading = " ".join(
        fit(column.heading, column.width).rjust(column.width)
        if column.align_right
        else fit(column.heading, column.width)
        for column in selected
    ).rstrip()
    rule = " ".join("-" * column.width for column in selected)

    lines = [capabilities.style(heading, "bold"), capabilities.style(rule, "dim")]
    lines.extend(render_row(row, selected) for row in window)

    # The footer is subject to the same width discipline as the rows: an
    # overflowing footer would reintroduce exactly the uncontrolled wrapping
    # UX-TABLE-01 forbids. Parts are added only while they still fit.
    dropped = len(columns) - len(selected)
    footer_parts = [f"page {page}/{total_pages}", f"{len(rows)} rows"]
    if dropped:
        footer_parts.append(f"{dropped} column(s) hidden")
    footer_parts.append("/Inspect-Target <rank> for detail")

    footer = ""
    for part in footer_parts:
        candidate = f"{footer}  {part}" if footer else part
        if len(candidate) > capabilities.width:
            break
        footer = candidate
    lines.append(capabilities.style(footer, "dim"))
    return lines


def render_stacked(rows: Sequence[dict[str, Any]], capabilities: Capabilities) -> list[str]:
    """Fallback record view for terminals too narrow for any column layout."""
    lines: list[str] = []
    for row in rows:
        identity = _cell(row.get("target_id"))
        lines.append(capabilities.style(f"#{_cell(row.get('rank'))} {identity}", "bold"))
        for column in DEFAULT_COLUMNS[2:]:
            if column.key in row:
                lines.append(f"  {column.heading}: {_cell(row[column.key])}")
    return lines


def render_detail(target: dict[str, Any], capabilities: Capabilities) -> list[str]:
    """Render the ``/Inspect-Target`` detail view (UX-TABLE-02).

    Sections are emitted only when the underlying data is actually present, so
    the view never implies the pipeline recorded something it did not.
    """
    lines: list[str] = []

    identity = _cell(target.get("target_id"))
    lines.append(capabilities.style(f"Target {identity}", "cyan", "bold"))

    def section(title: str, payload: Any) -> None:
        if payload in (None, "", {}, [], ()):
            return
        lines.append("")
        lines.append(capabilities.style(title, "bold"))
        if isinstance(payload, dict):
            width = max((len(str(key)) for key in payload), default=0)
            for key, value in payload.items():
                lines.append(f"  {str(key).ljust(width)}  {_cell(value)}")
        elif isinstance(payload, (list, tuple)):
            for item in payload:
                lines.append(f"  - {_cell(item)}")
        else:
            lines.append(f"  {_cell(payload)}")

    section("Canonical identity and aliases", target.get("identity"))
    section("Scientific metrics", target.get("metrics"))
    section("Score components", target.get("score_components"))
    section("Selection reason", target.get("selection_reason"))
    section("Source and transformation provenance", target.get("provenance"))
    section("Prior-search evidence", target.get("prior_search_evidence"))
    section("Estimated resource requirements", target.get("resources"))
    section("Limitations", target.get("limitations"))

    if len(lines) == 1:
        lines.append(capabilities.style("  No detail recorded for this target.", "dim"))
    return lines


def export_rows(rows: Sequence[dict[str, Any]], destination: Path) -> Path:
    """Write a complete JSONL export for a large request (UX-TABLE-03)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return destination


def render_large_summary(
    rows: Sequence[dict[str, Any]],
    export_path: Path,
    capabilities: Capabilities,
) -> list[str]:
    """Concise summary shown instead of a table when ``N > 100``."""
    scores = [row["score"] for row in rows if isinstance(row.get("score"), (int, float))]
    lines = [
        capabilities.style(f"{len(rows)} targets selected", "bold"),
        f"  complete export: {export_path}",
    ]
    if scores:
        lines.append(f"  score range:     {min(scores):.4g} to {max(scores):.4g}")
    lines.append("  /Inspect-Target <rank-or-id> for full detail on any target")
    return lines


def write_machine_output(rows: Iterable[dict[str, Any]], stream: TextIO) -> None:
    """Emit stable JSONL with no styling, animation, or prompts (UX-TABLE-04)."""
    for row in rows:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
    stream.flush()
