"""Regression tests for the calibration report artifact."""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "Skills"
if str(SKILLS) not in sys.path:
    sys.path.insert(0, str(SKILLS))

from evaluate_calibration import _emit_json_report  # noqa: E402


def test_emit_json_report_uses_timezone_aware_utc_timestamp(tmp_path: Path) -> None:
    report_path = tmp_path / "calibration.json"

    _emit_json_report([{"all_kpis_pass": True}], report_path)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    generated_at = payload["generated_at_utc"]
    parsed = datetime.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    assert generated_at.endswith("Z")
    assert parsed.tzinfo == datetime.UTC
