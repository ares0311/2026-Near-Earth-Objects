"""Negative controls for Skills/check_directive_parity.py (REL-04/REL-09).

Every test builds a real, throwaway tmp_path fixture tree -- never the real
repository -- so a known-bad/malformed case can be exercised without any
risk to this project's actual CLAUDE.md/AGENTS.md/canonical doc.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "Skills" / "check_directive_parity.py"
_spec = importlib.util.spec_from_file_location("check_directive_parity", _MODULE_PATH)
check_directive_parity = importlib.util.module_from_spec(_spec)
sys.modules["check_directive_parity"] = check_directive_parity
_spec.loader.exec_module(check_directive_parity)


def _write_fixture_tree(
    tmp_path: Path,
    *,
    canonical_body: str = "Some canonical text.",
    mirror_body: str | None = None,
    include_claude_ref: bool = True,
    include_agents_ref: bool = True,
    include_mandatory_protocol: bool = True,
) -> Path:
    """Build a minimal, real three-file tree mirroring this repo's own
    CLAUDE.md / AGENTS.md / docs/AGENT_RELIABILITY_DIRECTIVES.md shape."""
    if mirror_body is None:
        mirror_body = canonical_body

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "AGENT_RELIABILITY_DIRECTIVES.md").write_text(
        f"# Canonical\n\n<!-- REQ:REL-01 -->\n{canonical_body}\n<!-- /REQ:REL-01 -->\n"
    )

    claude_body = "# CLAUDE.md\n"
    if include_mandatory_protocol:
        claude_body += "## MANDATORY SESSION-START PROTOCOL\n"
    if include_claude_ref:
        claude_body += "Read docs/AGENT_RELIABILITY_DIRECTIVES.md\n"
    (tmp_path / "CLAUDE.md").write_text(claude_body)

    agents_body = "# AGENTS.md\n"
    if include_agents_ref:
        agents_body += "See docs/AGENT_RELIABILITY_DIRECTIVES.md\n"
    agents_body += f"<!-- REQ:REL-01 -->\n{mirror_body}\n<!-- /REQ:REL-01 -->\n"
    (tmp_path / "AGENTS.md").write_text(agents_body)

    return tmp_path


def test_known_good_case_passes(tmp_path):
    """known-good -> PASS: identical canonical/mirror text, both references present."""
    root = _write_fixture_tree(tmp_path)
    errors = check_directive_parity.check_parity(root)
    assert errors == []


def test_known_bad_drifted_text_fails(tmp_path):
    """known-bad -> FAIL: mirror text has been edited independently of the canonical source."""
    root = _write_fixture_tree(
        tmp_path,
        canonical_body="Always run tests before committing.",
        mirror_body="Sometimes run tests before committing.",
    )
    errors = check_directive_parity.check_parity(root)
    assert any("text differs" in e for e in errors)


def test_known_bad_missing_mirror_block_fails(tmp_path):
    """known-bad -> FAIL: a requirement exists canonically but was never mirrored."""
    root = _write_fixture_tree(tmp_path)
    # Strip the mirror block out of AGENTS.md entirely.
    (root / "AGENTS.md").write_text("# AGENTS.md\nSee docs/AGENT_RELIABILITY_DIRECTIVES.md\n")
    errors = check_directive_parity.check_parity(root)
    assert any("no mirror block" in e for e in errors)


def test_known_bad_missing_claude_reference_fails(tmp_path):
    """known-bad -> FAIL: CLAUDE.md never points at the canonical doc."""
    root = _write_fixture_tree(tmp_path, include_claude_ref=False)
    errors = check_directive_parity.check_parity(root)
    assert any("does not reference" in e and "CLAUDE.md" in e for e in errors)


def test_known_bad_missing_agents_reference_fails(tmp_path):
    """known-bad -> FAIL: AGENTS.md carries the mirror but never names the canonical source."""
    root = _write_fixture_tree(tmp_path, include_agents_ref=False)
    errors = check_directive_parity.check_parity(root)
    assert any("does not reference" in e and "AGENTS.md" in e for e in errors)


def test_known_bad_missing_mandatory_protocol_fails(tmp_path):
    """known-bad -> FAIL: CLAUDE.md has no enforced session-start mechanism at all."""
    root = _write_fixture_tree(tmp_path, include_mandatory_protocol=False)
    errors = check_directive_parity.check_parity(root)
    assert any("MANDATORY SESSION-START PROTOCOL" in e for e in errors)


def test_malformed_missing_canonical_file_fails_loudly(tmp_path):
    """malformed -> FAIL LOUDLY: canonical doc absent entirely, not just empty."""
    root = _write_fixture_tree(tmp_path)
    (root / "docs" / "AGENT_RELIABILITY_DIRECTIVES.md").unlink()
    errors = check_directive_parity.check_parity(root)
    assert any("required file is missing" in e for e in errors)
    # Loud means specific: the exact missing path must be named, not a generic message.
    assert any("AGENT_RELIABILITY_DIRECTIVES.md" in e for e in errors)


def test_malformed_duplicate_requirement_id_raises_loudly(tmp_path):
    """malformed -> FAIL LOUDLY: a corrupted file with two REL-01 blocks must raise a
    clear, specific error rather than silently picking one or crashing obscurely."""
    root = _write_fixture_tree(tmp_path)
    corrupted = (
        "<!-- REQ:REL-01 -->\nFirst copy.\n<!-- /REQ:REL-01 -->\n"
        "<!-- REQ:REL-01 -->\nSecond copy.\n<!-- /REQ:REL-01 -->\n"
    )
    (root / "docs" / "AGENT_RELIABILITY_DIRECTIVES.md").write_text(corrupted)
    with pytest.raises(ValueError, match="duplicate requirement block id"):
        check_directive_parity.check_parity(root)


def test_malformed_zero_requirement_blocks_fails_loudly(tmp_path):
    """malformed -> FAIL LOUDLY: markers stripped out entirely must be caught, not
    silently treated as 'nothing to check, so pass'."""
    root = _write_fixture_tree(tmp_path)
    canonical = root / "docs" / "AGENT_RELIABILITY_DIRECTIVES.md"
    canonical.write_text("# Canonical\nNo markers here.\n")
    errors = check_directive_parity.check_parity(root)
    assert any("zero" in e and "REQ:REL-XX" in e for e in errors)


def test_mirror_ahead_of_canonical_fails(tmp_path):
    """known-bad -> FAIL: a mirror block must never exist without a canonical source --
    that would itself be a second, competing source of truth."""
    root = _write_fixture_tree(tmp_path)
    agents_path = root / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text() + "\n<!-- REQ:REL-99 -->\nRogue text.\n<!-- /REQ:REL-99 -->\n"
    )
    errors = check_directive_parity.check_parity(root)
    assert any("REL-99" in e and "not in" in e for e in errors)


def test_extract_requirement_blocks_strips_outer_whitespace_only():
    """A trailing-newline-only difference must not be treated as drift, but real
    content differences (even subtle ones) must still be caught."""
    text_a = "<!-- REQ:REL-01 -->\nSame text.\n<!-- /REQ:REL-01 -->"
    text_b = "<!-- REQ:REL-01 -->\n\nSame text.\n\n<!-- /REQ:REL-01 -->\n"
    assert (
        check_directive_parity.extract_requirement_blocks(text_a)["REL-01"]
        == check_directive_parity.extract_requirement_blocks(text_b)["REL-01"]
    )


def test_cli_exits_nonzero_on_failure(tmp_path, monkeypatch, capsys):
    """The CLI entry point itself must propagate failure as a non-zero exit code,
    not just print an error and return 0 (REL-01's 'fail loudly' applied to this
    checker's own CLI contract)."""
    root = _write_fixture_tree(tmp_path, include_claude_ref=False)
    monkeypatch.setattr(sys, "argv", ["check_directive_parity.py", "--root", str(root)])
    exit_code = check_directive_parity.main()
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.err


def test_cli_exits_zero_on_success(tmp_path, monkeypatch, capsys):
    root = _write_fixture_tree(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_directive_parity.py", "--root", str(root)])
    exit_code = check_directive_parity.main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "PASS" in captured.out
