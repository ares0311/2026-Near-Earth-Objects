#!/usr/bin/env python
"""REL-01 -- new-silent-exception gate.

AST-scans production Python (src/**/*.py, Skills/*.py) for exception
handlers whose entire body is a bare `pass` (`except Exception: pass`,
`except: pass`, `except (A, B): pass`, ...) -- the concrete, checkable
shape of REL-01's "never silently swallow a material failure."

This project's src/fetch.py and src/classify.py contain real, pre-existing
occurrences of this pattern that predate REL-01 (see
docs/AGENT_RELIABILITY_DIRECTIVES.md REL-01's disclosed known limitation).
Retroactively fixing each one is out of scope here. Instead this script
catalogues every existing occurrence in a committed allowlist
(data_selection/silent_exception_allowlist.json) and hard-fails on any
occurrence NOT in that allowlist -- so no NEW silent-swallow can land
without an explicit, reviewed, documented exception, even though the
historical debt remains visible and uncorrected rather than hidden.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_ALLOWLIST_PATH = "data_selection/silent_exception_allowlist.json"


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    exception_types: str  # e.g. "Exception", "*", "OSError, ValueError"

    def key(self) -> tuple[str, int, str]:
        return (self.path, self.line, self.exception_types)


def _exception_types_label(node: ast.ExceptHandler) -> str:
    if node.type is None:
        return "*"  # bare `except:`
    if isinstance(node.type, ast.Tuple):
        names = []
        for elt in node.type.elts:
            names.append(elt.id if isinstance(elt, ast.Name) else ast.dump(elt))
        return ", ".join(names)
    if isinstance(node.type, ast.Name):
        return node.type.id
    return ast.dump(node.type)


def _is_bare_pass_handler(node: ast.ExceptHandler) -> bool:
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # allow a leading string "comment" expression, if any
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _iter_production_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    src_dir = root / "src"
    if src_dir.is_dir():
        files.extend(sorted(p for p in src_dir.rglob("*.py") if "__pycache__" not in p.parts))
    skills_dir = root / "Skills"
    if skills_dir.is_dir():
        files.extend(sorted(skills_dir.glob("*.py")))
    return files


def scan(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_production_python_files(root):
        rel_path = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            # An unparseable production file is REL-08's concern
            # (check_incomplete_implementations.py already flags it there);
            # don't double-report it here.
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _is_bare_pass_handler(node):
                findings.append(
                    Finding(
                        path=rel_path,
                        line=node.lineno,
                        exception_types=_exception_types_label(node),
                    )
                )
    return sorted(findings, key=lambda f: (f.path, f.line))


def load_allowlist(root: Path) -> dict[tuple[str, int, str], str]:
    allowlist_path = root / _ALLOWLIST_PATH
    if not allowlist_path.exists():
        return {}
    entries = json.loads(allowlist_path.read_text())
    result: dict[tuple[str, int, str], str] = {}
    for entry in entries:
        reason = entry.get("reason", "").strip()
        if not reason:
            raise ValueError(
                f"allowlist entry {entry} in {allowlist_path} has no reason -- "
                "every exception must be documented, not just listed"
            )
        result[(entry["path"], int(entry["line"]), entry["exception_types"])] = reason
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to scan (default: this repo). Tests point this at a "
        "tmp_path fixture tree instead of the real repository.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print every finding whether allowlisted or not, without failing. Used to "
        "(re)generate the allowlist seed from real findings -- never used by the "
        "canonical verification workflow.",
    )
    args = parser.parse_args()

    findings = scan(args.root)

    if args.report_only:
        payload = [
            {"path": f.path, "line": f.line, "exception_types": f.exception_types}
            for f in findings
        ]
        print(json.dumps(payload, indent=2))
        return 0

    allowlist = load_allowlist(args.root)
    unallowlisted = [f for f in findings if f.key() not in allowlist]
    allowlisted = [f for f in findings if f.key() in allowlist]

    if allowlisted:
        print(
            f"[silent-exceptions] {len(allowlisted)} allowlisted (pre-existing, catalogued) "
            "finding(s):"
        )
        for f in allowlisted:
            print(f"  - {f.path}:{f.line} except {f.exception_types}: pass -- {allowlist[f.key()]}")

    if unallowlisted:
        print(
            f"[silent-exceptions] FAIL -- {len(unallowlisted)} NEW unallowlisted "
            "silent-except finding(s):",
            file=sys.stderr,
        )
        for f in unallowlisted:
            print(f"  - {f.path}:{f.line} except {f.exception_types}: pass", file=sys.stderr)
        return 1

    print(
        f"[silent-exceptions] PASS -- {len(findings)} finding(s), all pre-existing and "
        "catalogued in the allowlist"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
