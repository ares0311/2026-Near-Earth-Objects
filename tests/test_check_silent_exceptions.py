"""Negative controls for Skills/check_silent_exceptions.py (REL-01/REL-09).

Every scan target is a real, throwaway tmp_path fixture tree -- never this
repository's actual src/fetch.py or src/classify.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "Skills" / "check_silent_exceptions.py"
_spec = importlib.util.spec_from_file_location("check_silent_exceptions", _MODULE_PATH)
check_silent_exceptions = importlib.util.module_from_spec(_spec)
sys.modules["check_silent_exceptions"] = check_silent_exceptions
_spec.loader.exec_module(check_silent_exceptions)


def _write_src_file(root: Path, name: str, content: str) -> Path:
    src_dir = root / "src"
    src_dir.mkdir(exist_ok=True)
    path = src_dir / name
    path.write_text(content)
    return path


def test_known_good_no_bare_except_has_zero_findings(tmp_path):
    """known-good -> PASS: exceptions that are logged/handled (not bare `pass`) are
    exactly what REL-01 wants and must not be flagged."""
    _write_src_file(
        tmp_path,
        "handled.py",
        "import logging\n\n"
        "def fetch(url):\n"
        "    try:\n"
        "        return _do_fetch(url)\n"
        "    except ConnectionError as exc:\n"
        "        logging.error('fetch failed: %s', exc)\n"
        "        raise\n",
    )
    findings = check_silent_exceptions.scan(tmp_path)
    assert findings == []


def test_known_bad_except_exception_pass_detected(tmp_path):
    """known-bad -> FAIL: the exact real-world pattern found in this project's own
    src/fetch.py and src/classify.py."""
    _write_src_file(
        tmp_path,
        "silent.py",
        "def enrich(candidate):\n"
        "    try:\n"
        "        candidate.extra = compute_extra(candidate)\n"
        "    except Exception:\n"
        "        pass\n"
        "    return candidate\n",
    )
    findings = check_silent_exceptions.scan(tmp_path)
    assert len(findings) == 1
    assert findings[0].exception_types == "Exception"


def test_known_bad_bare_except_pass_detected(tmp_path):
    """A bare `except:` (no exception type at all) is even broader/riskier than
    `except Exception:` and must be caught, labeled distinctly as "*"."""
    _write_src_file(
        tmp_path,
        "bare.py",
        "def enrich(candidate):\n"
        "    try:\n"
        "        candidate.extra = compute_extra(candidate)\n"
        "    except:\n"
        "        pass\n"
        "    return candidate\n",
    )
    findings = check_silent_exceptions.scan(tmp_path)
    assert len(findings) == 1
    assert findings[0].exception_types == "*"


def test_known_bad_tuple_except_pass_detected(tmp_path):
    """`except (A, B): pass` must be caught with both exception names recorded."""
    _write_src_file(
        tmp_path,
        "tuple_except.py",
        "def parse(value):\n"
        "    try:\n"
        "        return int(value)\n"
        "    except (ValueError, TypeError):\n"
        "        pass\n",
    )
    findings = check_silent_exceptions.scan(tmp_path)
    assert len(findings) == 1
    assert findings[0].exception_types == "ValueError, TypeError"


def test_except_with_more_than_pass_is_not_flagged(tmp_path):
    """Legitimate case, must NOT be flagged: a handler that does something beyond a
    bare `pass` (even a minimal log call) is not a silent swallow by this check's
    definition."""
    _write_src_file(
        tmp_path,
        "logged.py",
        "def enrich(candidate):\n"
        "    try:\n"
        "        candidate.extra = compute_extra(candidate)\n"
        "    except Exception:\n"
        "        candidate.extra = None\n"
        "    return candidate\n",
    )
    findings = check_silent_exceptions.scan(tmp_path)
    assert findings == []


def test_allowlisted_finding_does_not_fail_cli(tmp_path, monkeypatch, capsys):
    _write_src_file(
        tmp_path,
        "known.py",
        "def enrich(candidate):\n"
        "    try:\n"
        "        candidate.extra = compute_extra(candidate)\n"
        "    except Exception:\n"
        "        pass\n"
        "    return candidate\n",
    )
    data_selection_dir = tmp_path / "data_selection"
    data_selection_dir.mkdir()
    (data_selection_dir / "silent_exception_allowlist.json").write_text(
        json.dumps(
            [
                {
                    "path": "src/known.py",
                    "line": 4,
                    "exception_types": "Exception",
                    "reason": "Pre-existing, catalogued, not yet audited.",
                }
            ]
        )
    )
    monkeypatch.setattr(sys, "argv", ["check_silent_exceptions.py", "--root", str(tmp_path)])
    exit_code = check_silent_exceptions.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "allowlisted" in captured.out


def test_unallowlisted_finding_fails_cli_loudly(tmp_path, monkeypatch, capsys):
    """known-bad -> FAIL LOUDLY: a brand-new silent-except (not in the allowlist) must
    hard-fail with the exact file:line named -- this is the mechanism that stops NEW
    silent-swallow code from landing even though the historical debt is tolerated."""
    _write_src_file(
        tmp_path,
        "new_silent.py",
        "def enrich(candidate):\n"
        "    try:\n"
        "        candidate.extra = compute_extra(candidate)\n"
        "    except Exception:\n"
        "        pass\n"
        "    return candidate\n",
    )
    monkeypatch.setattr(sys, "argv", ["check_silent_exceptions.py", "--root", str(tmp_path)])
    exit_code = check_silent_exceptions.main()
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "src/new_silent.py:4" in captured.err


def test_malformed_allowlist_entry_missing_reason_raises_loudly(tmp_path):
    data_selection_dir = tmp_path / "data_selection"
    data_selection_dir.mkdir()
    (data_selection_dir / "silent_exception_allowlist.json").write_text(
        json.dumps(
            [{"path": "src/x.py", "line": 1, "exception_types": "Exception", "reason": "  "}]
        )
    )
    with pytest.raises(ValueError, match="has no reason"):
        check_silent_exceptions.load_allowlist(tmp_path)


def test_missing_allowlist_file_is_empty_not_permissive(tmp_path):
    assert check_silent_exceptions.load_allowlist(tmp_path) == {}


def test_report_only_mode_prints_json_regardless_of_allowlist(tmp_path, monkeypatch, capsys):
    """--report-only is the mechanism used to (re)seed the allowlist from real
    findings -- it must never consult or fail against the allowlist, and must never
    exit non-zero."""
    _write_src_file(
        tmp_path,
        "reportable.py",
        "def enrich(candidate):\n"
        "    try:\n"
        "        candidate.extra = compute_extra(candidate)\n"
        "    except Exception:\n"
        "        pass\n"
        "    return candidate\n",
    )
    monkeypatch.setattr(
        sys, "argv", ["check_silent_exceptions.py", "--root", str(tmp_path), "--report-only"]
    )
    exit_code = check_silent_exceptions.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == [{"path": "src/reportable.py", "line": 4, "exception_types": "Exception"}]


def test_malformed_unparseable_file_does_not_crash_and_defers_to_completeness_scanner(tmp_path):
    """malformed -> handled, not crashed: a syntactically broken file is skipped by
    THIS scanner (it cannot contain a valid except-handler AST if it doesn't parse)
    rather than raising here. This is an intentional deferral, not a silent-failure
    violation of REL-01 itself: Skills/check_incomplete_implementations.py's
    `syntax_error`/`unparseable_file` finding already covers the same file within
    the same Skills/verify_reliability_controls.py run, so the overall workflow
    still fails loudly on a broken file -- just via the other, more appropriate
    check."""
    _write_src_file(tmp_path, "broken.py", "def f(:\n    pass\n")
    findings = check_silent_exceptions.scan(tmp_path)
    assert findings == []
