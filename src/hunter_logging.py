"""Append-only structured operational events for NEO-Hunter."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def emit_event(
    path: Path,
    *,
    event: str,
    status: str,
    **fields: Any,
) -> None:
    """Append one durable JSONL event or fail visibly."""

    if not event.strip() or not status.strip():
        raise ValueError("event and status must be non-empty")
    payload = {
        "schema_version": 1,
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "status": status,
        **fields,
    }
    data = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        written = os.write(descriptor, data)
        if written != len(data):
            raise OSError(f"short structured-log write: {written}/{len(data)} bytes")
    finally:
        os.close(descriptor)
