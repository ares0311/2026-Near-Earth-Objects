"""Canonical parameter validators for every NEOHunter entry surface.

Specification rule UX-IN-04 requires that interactive and scriptable operation
use *the same* validation functions, so that a value accepted by the guided
editor is accepted identically by the scriptable command, and a value rejected
in one is rejected in the other with the same wording.

Every validator here follows one contract:

    validate_x(raw: str) -> tuple[value | None, str | None]

returning ``(parsed_value, None)`` on success or ``(None, message)`` on failure,
where ``message`` is a complete operator-facing sentence. Validators never raise
for ordinary bad input and never print -- the caller decides how to surface the
result, which is what lets one function serve both an inline live sentinel and
an ``argparse`` type converter.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Result of a validation attempt: parsed value, or None plus an error message.
ValidationResult = tuple[Any, str | None]

# NEO dynamical classes the canonical pipeline accepts for target selection.
NEO_CLASS_CHOICES = ("all", "aten", "ieo")

# Lifecycle states the follow-up registry exposes.
FOLLOW_UP_STATUS_CHOICES = ("open", "actioned", "dismissed", "expired", "all")

# Upper bound on a single request. This is a guard against an obvious typo
# (a pasted identifier, a stray zero) rather than a scientific limit; the
# contract forbids arbitrarily fixed candidate pools, and this bounds only the
# *request*, never the discovery universe explored to satisfy it.
MAX_REQUESTED_TARGETS = 10_000


def validate_target_count(raw: str) -> ValidationResult:
    """Validate the requested number of targets ``N``.

    ``N`` must be a positive whole number. The specification gives the exact
    sentinel wording for the two common mistakes (non-numeric input and zero),
    and those messages are reproduced here verbatim.
    """
    text = raw.strip()
    if not text:
        return None, "Required - enter a positive whole number."
    try:
        value = int(text)
    except ValueError:
        return None, "Invalid - enter a positive whole number."
    if value <= 0:
        return None, "Invalid - targets must be greater than zero."
    if value > MAX_REQUESTED_TARGETS:
        return None, f"Invalid - targets must not exceed {MAX_REQUESTED_TARGETS:,}."
    return value, None


def validate_neo_class(raw: str) -> ValidationResult:
    """Validate the NEO dynamical-class filter (an enumeration)."""
    text = raw.strip().casefold()
    if not text:
        return "all", None
    if text not in NEO_CLASS_CHOICES:
        joined = ", ".join(NEO_CLASS_CHOICES)
        return None, f"Invalid - choose one of: {joined}."
    return text, None


def validate_follow_up_status(raw: str) -> ValidationResult:
    """Validate the follow-up registry lifecycle-state filter."""
    text = raw.strip().casefold()
    if not text:
        return "open", None
    if text not in FOLLOW_UP_STATUS_CHOICES:
        joined = ", ".join(FOLLOW_UP_STATUS_CHOICES)
        return None, f"Invalid - choose one of: {joined}."
    return text, None


def validate_optional_positive_number(raw: str) -> ValidationResult:
    """Validate an optional positive number such as a download ceiling in GB."""
    text = raw.strip()
    if not text:
        return None, None
    try:
        value = float(text)
    except ValueError:
        return None, "Invalid - enter a positive number, or leave blank."
    if value <= 0:
        return None, "Invalid - must be greater than zero, or leave blank."
    return value, None


def validate_optional_pool_limit(raw: str) -> ValidationResult:
    """Validate the optional explicit discovery-pool safety limit.

    This is an operator safety valve, not a scientific bound. When it prevents
    sufficiency the canonical pipeline fails loudly rather than persisting a
    short manifest, so a value below the requested target count is rejected here
    only if it is not a positive whole number -- the sufficiency interaction is
    the pipeline's decision, not this validator's.
    """
    text = raw.strip()
    if not text:
        return None, None
    try:
        value = int(text)
    except ValueError:
        return None, "Invalid - enter a positive whole number, or leave blank."
    if value <= 0:
        return None, "Invalid - must be greater than zero, or leave blank."
    return value, None


def validate_search_id(raw: str) -> ValidationResult:
    """Validate a durable search identifier, or the ``--latest`` sentinel.

    Identifier syntax is intentionally permissive about *shape* but strict about
    character class: a stray shell fragment or path must not reach the
    persistence layer as if it were an identifier.
    """
    text = raw.strip()
    if not text:
        return None, None
    if text.casefold() in {"latest", "--latest"}:
        return "--latest", None
    if not all(character.isalnum() or character in "-_" for character in text):
        return None, "Invalid - identifiers use letters, digits, hyphen, and underscore only."
    return text, None


def validate_target_reference(raw: str) -> ValidationResult:
    """Validate an ``/Inspect-Target`` argument: a rank number or a target id."""
    text = raw.strip()
    if not text:
        return None, "Required - enter a result rank number or a target identifier."
    if text.isdigit():
        rank = int(text)
        if rank <= 0:
            return None, "Invalid - rank must be greater than zero."
        return rank, None
    if not all(character.isalnum() or character in "-_." for character in text):
        return None, "Invalid - enter a rank number or a valid target identifier."
    return text, None


def validate_existing_directory(raw: str) -> ValidationResult:
    """Validate an optional output directory, checking existence and writability."""
    text = raw.strip()
    if not text:
        return None, None
    path = Path(text).expanduser()
    if not path.exists():
        return None, f"Invalid - directory does not exist: {path}"
    if not path.is_dir():
        return None, f"Invalid - not a directory: {path}"
    # A directory the operator cannot write to would fail much later, during
    # export, after real work has already been done. Catch it during entry.
    import os

    if not os.access(path, os.W_OK):
        return None, f"Invalid - directory is not writable: {path}"
    return path, None


def as_argparse_type(
    validator: Callable[[str], ValidationResult],
) -> Callable[[str], Any]:
    """Adapt a canonical validator into an ``argparse`` ``type=`` callable.

    This is the mechanism that makes UX-IN-04 true rather than aspirational: the
    scriptable parser and the interactive editor call the identical function, so
    their accept/reject behaviour and message text cannot drift apart.
    """

    def _convert(raw: str) -> Any:
        value, error = validator(raw)
        if error is not None:
            raise argparse.ArgumentTypeError(error)
        return value

    return _convert
