"""Negative controls for Skills/check_incomplete_implementations.py (REL-02/REL-08/REL-09).

Every scan target is a real, throwaway tmp_path fixture tree with its own
src/ and Skills/ subdirectories -- never this repository's actual code.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "check_incomplete_implementations.py"
)
_spec = importlib.util.spec_from_file_location("check_incomplete_implementations", _MODULE_PATH)
check_incomplete_implementations = importlib.util.module_from_spec(_spec)
sys.modules["check_incomplete_implementations"] = check_incomplete_implementations
_spec.loader.exec_module(check_incomplete_implementations)


def _write_src_file(root: Path, name: str, content: str) -> Path:
    src_dir = root / "src"
    src_dir.mkdir(exist_ok=True)
    path = src_dir / name
    path.write_text(content)
    return path


def test_known_good_clean_module_has_zero_findings(tmp_path):
    """known-good -> PASS: ordinary, complete code has no findings at all."""
    _write_src_file(
        tmp_path,
        "clean.py",
        "def add(a: int, b: int) -> int:\n"
        '    """Add two numbers."""\n'
        "    return a + b\n",
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert findings == []


def test_known_bad_not_implemented_error_detected(tmp_path):
    """known-bad -> FAIL: a raised NotImplementedError is exactly REL-02's target pattern."""
    _write_src_file(
        tmp_path,
        "stub.py",
        "def compute_orbit(tracklet):\n"
        "    raise NotImplementedError\n",
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert any(f.pattern == "not_implemented_error" for f in findings)


def test_known_bad_not_implemented_error_call_form_detected(tmp_path):
    """The Call form `raise NotImplementedError(\"msg\")` must also be caught, not just
    the bare-name form."""
    _write_src_file(
        tmp_path,
        "stub2.py",
        "def compute_orbit(tracklet):\n"
        '    raise NotImplementedError("not done yet")\n',
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert any(f.pattern == "not_implemented_error" for f in findings)


def test_known_bad_todo_comment_detected(tmp_path):
    """known-bad -> FAIL: a real source-code TODO comment marking unfinished work."""
    _write_src_file(
        tmp_path,
        "todo.py",
        "def score(candidate):\n"
        "    # TODO: implement real scoring, this is a placeholder\n"
        "    return 0.5\n",
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert any(f.pattern == "comment_marker:TODO" for f in findings)


def test_todo_inside_string_literal_is_not_a_false_positive(tmp_path):
    """This is the exact real case found in this project's own Skills/run_pipeline.py:
    an operator-facing print() string containing the word TODO must NEVER be flagged --
    only an actual `#` comment counts. Tokenize-based scanning (not a naive text grep)
    is what makes this distinction possible."""
    _write_src_file(
        tmp_path,
        "escalation.py",
        "def notice():\n"
        '    print("TODO: MPC archival-submission authority unresolved")\n',
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert findings == []


def test_known_bad_bare_pass_function_body_detected(tmp_path):
    """known-bad -> FAIL: a function whose entire body is `pass` reports success-shaped
    code that performs no required operation."""
    _write_src_file(
        tmp_path,
        "empty_impl.py",
        "def submit_to_mpc(report):\n"
        "    pass\n",
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert any(f.pattern == "bare_pass_body" for f in findings)


def test_abstractmethod_pass_is_legitimate_extension_point(tmp_path):
    """Legitimate case, must NOT be flagged: an abstract method is an intentional
    extension point per REL-02, not a stub masquerading as complete."""
    _write_src_file(
        tmp_path,
        "abstract.py",
        "from abc import ABC, abstractmethod\n\n"
        "class Detector(ABC):\n"
        "    @abstractmethod\n"
        "    def detect(self, image):\n"
        "        pass\n",
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert findings == []


def test_protocol_class_pass_is_legitimate_extension_point(tmp_path):
    """Legitimate case, must NOT be flagged: a typing.Protocol body is a structural
    interface, not unfinished work."""
    _write_src_file(
        tmp_path,
        "protocol.py",
        "from typing import Protocol\n\n"
        "class Scorer(Protocol):\n"
        "    def score(self, candidate) -> float:\n"
        "        pass\n",
    )
    findings = check_incomplete_implementations.scan(tmp_path)
    assert findings == []


def test_allowlisted_finding_does_not_fail_cli(tmp_path, monkeypatch, capsys):
    """A finding whose exact (path, line, pattern) is in the committed allowlist, with
    a documented reason, must not fail the CLI -- but must still be reported, not
    silently hidden."""
    _write_src_file(
        tmp_path,
        "known_stub.py",
        "def legacy_hook():\n"
        "    pass\n",
    )
    data_selection_dir = tmp_path / "data_selection"
    data_selection_dir.mkdir()
    (data_selection_dir / "incomplete_implementation_allowlist.json").write_text(
        json.dumps(
            [
                {
                    "path": "src/known_stub.py",
                    "line": 1,
                    "pattern": "bare_pass_body",
                    "reason": "Legacy hook retained for backward compatibility; tracked "
                    "separately, not a fake-completion violation.",
                }
            ]
        )
    )
    monkeypatch.setattr(
        sys, "argv", ["check_incomplete_implementations.py", "--root", str(tmp_path)]
    )
    exit_code = check_incomplete_implementations.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "allowlisted" in captured.out


def test_unallowlisted_finding_fails_cli_loudly(tmp_path, monkeypatch, capsys):
    """known-bad -> FAIL LOUDLY: an unallowlisted finding must exit non-zero and name
    the exact file:line, not just say 'something failed'."""
    _write_src_file(
        tmp_path,
        "new_stub.py",
        "def new_hook():\n"
        "    pass\n",
    )
    monkeypatch.setattr(
        sys, "argv", ["check_incomplete_implementations.py", "--root", str(tmp_path)]
    )
    exit_code = check_incomplete_implementations.main()
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "src/new_stub.py:1" in captured.err


def test_malformed_allowlist_entry_missing_reason_raises_loudly(tmp_path):
    """malformed -> FAIL LOUDLY: an allowlist entry without a reason is itself a
    directive violation (an undocumented exception), not a valid pass-through."""
    data_selection_dir = tmp_path / "data_selection"
    data_selection_dir.mkdir()
    (data_selection_dir / "incomplete_implementation_allowlist.json").write_text(
        json.dumps([{"path": "src/x.py", "line": 1, "pattern": "bare_pass_body", "reason": ""}])
    )
    with pytest.raises(ValueError, match="has no reason"):
        check_incomplete_implementations.load_allowlist(tmp_path)


def test_missing_allowlist_file_is_empty_not_permissive(tmp_path):
    """A missing allowlist file must fail CLOSED (treated as zero exceptions granted),
    not open (treated as 'anything goes')."""
    allowlist = check_incomplete_implementations.load_allowlist(tmp_path)
    assert allowlist == {}


def test_malformed_unparseable_file_is_flagged_loudly(tmp_path):
    """malformed -> FAIL LOUDLY: a source file with broken syntax must itself be a
    finding, not silently skipped as 'couldn't scan it, so nothing to report'."""
    _write_src_file(tmp_path, "broken.py", "def f(:\n    pass\n")
    findings = check_incomplete_implementations.scan(tmp_path)
    patterns = {f.pattern for f in findings}
    assert "syntax_error" in patterns or "unparseable_file" in patterns


def test_skills_directory_is_flat_not_recursive(tmp_path):
    """Skills/ is scanned non-recursively (matching this project's own flat-Skills/
    convention) -- a nested subdirectory under Skills/ must not be scanned, avoiding
    accidental false positives from e.g. a vendored or generated subtree."""
    skills_dir = tmp_path / "Skills" / "nested"
    skills_dir.mkdir(parents=True)
    (skills_dir / "deep_stub.py").write_text("def f():\n    pass\n")
    findings = check_incomplete_implementations.scan(tmp_path)
    assert findings == []
