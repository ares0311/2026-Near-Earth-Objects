#!/usr/bin/env python
"""REL-04 -- directive-parity / drift detector.

Verifies that docs/AGENT_RELIABILITY_DIRECTIVES.md (the canonical source)
and AGENTS.md (Codex's verbatim mirror) never drift apart, and that both
CLAUDE.md and AGENTS.md actually reference the canonical file. This is the
mechanical enforcement behind REL-04 ("Claude Code and Codex must receive
equivalent authoritative requirements, verified mechanically, not assumed").

Exit code is non-zero on ANY drift, missing requirement, or missing
reference -- this check must fail loudly, not warn, because a silently
drifted directive is exactly the "competing source of truth" REL-04
forbids.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Matches "<!-- REQ:REL-01 -->...<!-- /REQ:REL-01 -->" and captures the ID
# plus the inner text, non-greedy so adjacent blocks don't merge.
_BLOCK_RE = re.compile(
    r"<!--\s*REQ:(REL-\d+)\s*-->(.*?)<!--\s*/REQ:\1\s*-->",
    re.DOTALL,
)

_CANONICAL_DOC = "docs/AGENT_RELIABILITY_DIRECTIVES.md"


def extract_requirement_blocks(text: str) -> dict[str, str]:
    """Return {REL-ID: stripped inner text} for every marked block found.

    Stripping only the outer whitespace (not internal formatting) keeps the
    comparison robust to a trailing-newline difference while still catching
    any real content drift between the canonical file and its mirror.
    """
    blocks: dict[str, str] = {}
    for match in _BLOCK_RE.finditer(text):
        req_id, body = match.group(1), match.group(2)
        if req_id in blocks:
            raise ValueError(f"duplicate requirement block id {req_id!r} in same file")
        blocks[req_id] = body.strip()
    return blocks


def check_parity(root: Path) -> list[str]:
    """Run every REL-04 parity check against the repo rooted at `root`.

    Returns a list of human-readable error strings; empty list means clean.
    Never raises for an ordinary drift/missing-file finding -- those are
    reported as strings so the caller can print all findings at once
    (fail loudly with full detail, not just the first problem found).
    """
    errors: list[str] = []

    canonical_path = root / _CANONICAL_DOC
    claude_path = root / "CLAUDE.md"
    agents_path = root / "AGENTS.md"

    for path in (canonical_path, claude_path, agents_path):
        if not path.exists():
            errors.append(f"required file is missing: {path}")
    if errors:
        # No point parsing blocks from files that don't exist.
        return errors

    canonical_text = canonical_path.read_text()
    claude_text = claude_path.read_text()
    agents_text = agents_path.read_text()

    canonical_blocks = extract_requirement_blocks(canonical_text)
    mirror_blocks = extract_requirement_blocks(agents_text)

    if not canonical_blocks:
        errors.append(
            f"{canonical_path} contains zero <!-- REQ:REL-XX --> blocks -- "
            "either the file is malformed or the markers were removed"
        )

    for req_id, canonical_body in sorted(canonical_blocks.items()):
        if req_id not in mirror_blocks:
            errors.append(
                f"{req_id} exists in {canonical_path} but has no mirror block in {agents_path}"
            )
            continue
        mirror_body = mirror_blocks[req_id]
        if mirror_body != canonical_body:
            errors.append(
                f"{req_id} text differs between {canonical_path} and its {agents_path} "
                "mirror -- edit both identically, then re-run this check"
            )

    extra_in_mirror = set(mirror_blocks) - set(canonical_blocks)
    for req_id in sorted(extra_in_mirror):
        errors.append(
            f"{req_id} exists in {agents_path}'s mirror but not in {canonical_path} -- "
            "a mirror must never get ahead of the canonical source"
        )

    if _CANONICAL_DOC not in claude_text:
        errors.append(
            f"{claude_path} does not reference {_CANONICAL_DOC} -- Claude Code's "
            "MANDATORY SESSION-START PROTOCOL must include it"
        )
    if "MANDATORY SESSION-START PROTOCOL" not in claude_text:
        errors.append(
            f"{claude_path} has no MANDATORY SESSION-START PROTOCOL section at all"
        )

    if _CANONICAL_DOC not in agents_text:
        errors.append(
            f"{agents_path} does not reference {_CANONICAL_DOC} -- Codex's context "
            "must point at the canonical source, not just carry an unlabeled mirror"
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to check (default: this repo). Tests point this at a "
        "tmp_path fixture tree instead of the real repository.",
    )
    args = parser.parse_args()

    errors = check_parity(args.root)
    if errors:
        print(f"[directive-parity] FAIL -- {len(errors)} issue(s) found:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("[directive-parity] PASS -- CLAUDE.md and AGENTS.md agree with the canonical source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
