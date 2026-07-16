#!/usr/bin/env python
"""REL-02/REL-08 -- incomplete-implementation scanner.

Scans production Python (src/**/*.py, Skills/*.py -- never tests/) for
patterns that suggest required behavior was left unfinished:

  - `raise NotImplementedError(...)`
  - `# TODO` / `# FIXME` / `# XXX` comment markers (tokenize-based, so a
    string literal that merely contains the word "TODO" is never a false
    positive -- only an actual source comment counts)
  - a function/method whose entire body is a bare `pass` statement, unless
    it is `@abstractmethod`-decorated or defined inside a `typing.Protocol`
    subclass (both are legitimate, intentional extension points per REL-02)

A narrow, explicit, git-committed allowlist
(data_selection/incomplete_implementation_allowlist.json) can excuse a
specific already-reviewed file:line:pattern with a required justification.
Nothing is excluded by broadening the scanner itself -- only by a named,
reviewable allowlist entry, per REL-02's "excluded via its narrow allowlist
mechanism, not by weakening the scanner's default behavior."
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

_SCAN_DIRS = ("src", "Skills")
_COMMENT_MARKERS = ("TODO", "FIXME", "XXX")
_ALLOWLIST_PATH = "data_selection/incomplete_implementation_allowlist.json"


@dataclass(frozen=True)
class Finding:
    path: str  # POSIX-style, relative to repo root, for stable cross-platform comparison
    line: int
    pattern: str
    detail: str

    def key(self) -> tuple[str, int, str]:
        """The identity an allowlist entry matches on -- not `detail`, so a
        justification can be reworded without breaking the allowlist entry."""
        return (self.path, self.line, self.pattern)


def _iter_production_python_files(root: Path) -> list[Path]:
    """Every .py file under the scanned directories, skipping tests/ and
    caches. Skills/*.py only (not subdirectories) matches this project's
    existing "Skills/ is flat operator scripts" convention."""
    files: list[Path] = []
    src_dir = root / "src"
    if src_dir.is_dir():
        files.extend(sorted(p for p in src_dir.rglob("*.py") if "__pycache__" not in p.parts))
    skills_dir = root / "Skills"
    if skills_dir.is_dir():
        files.extend(sorted(skills_dir.glob("*.py")))
    return files


def _scan_comment_markers(path: Path, rel_path: str) -> list[Finding]:
    """Tokenize-based scan so only real source comments count -- a print()
    string that happens to contain the word TODO must never be flagged."""
    findings: list[Finding] = []
    source = path.read_bytes()
    try:
        tokens = tokenize.tokenize(io.BytesIO(source).readline)
        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                continue
            comment_body = tok.string.lstrip("#").strip()
            for marker in _COMMENT_MARKERS:
                if comment_body.upper().startswith(marker):
                    findings.append(
                        Finding(
                            path=rel_path,
                            line=tok.start[0],
                            pattern=f"comment_marker:{marker}",
                            detail=tok.string.strip(),
                        )
                    )
                    break
    except (tokenize.TokenError, SyntaxError, IndentationError) as exc:
        # A file that cannot even be tokenized is itself a finding -- fail
        # loudly rather than silently skipping a broken/unreadable file.
        findings.append(
            Finding(
                path=rel_path,
                line=0,
                pattern="unparseable_file",
                detail=f"{type(exc).__name__}: {exc}",
            )
        )
    return findings


def _is_protocol_class(node: ast.ClassDef) -> bool:
    """True if the class directly subclasses typing.Protocol (by name only
    -- this is a source-level heuristic, not a type-checker, matching this
    scanner's "lightest practical mechanism" scope from REL-08)."""
    for base in node.bases:
        name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
        if name == "Protocol":
            return True
    return False


def _is_abstractmethod(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        name = decorator.id if isinstance(decorator, ast.Name) else getattr(decorator, "attr", None)
        if name in {"abstractmethod", "abstractproperty"}:
            return True
    return False


def _is_bare_pass_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = node.body
    # A leading docstring is fine; the only *statement* must be `pass`.
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _scan_ast(path: Path, rel_path: str) -> list[Finding]:
    findings: list[Finding] = []
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        findings.append(
            Finding(path=rel_path, line=exc.lineno or 0, pattern="syntax_error", detail=str(exc))
        )
        return findings

    protocol_class_stack: list[bool] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 (ast API name)
            protocol_class_stack.append(_is_protocol_class(node))
            self.generic_visit(node)
            protocol_class_stack.pop()

        def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            for call_node in ast.walk(node):
                if (
                    isinstance(call_node, ast.Raise)
                    and isinstance(call_node.exc, ast.Call)
                    and isinstance(call_node.exc.func, ast.Name)
                    and call_node.exc.func.id == "NotImplementedError"
                ):
                    findings.append(
                        Finding(
                            path=rel_path,
                            line=call_node.lineno,
                            pattern="not_implemented_error",
                            detail=f"raise NotImplementedError(...) in {node.name}()",
                        )
                    )
                elif (
                    isinstance(call_node, ast.Raise)
                    and isinstance(call_node.exc, ast.Name)
                    and call_node.exc.id == "NotImplementedError"
                ):
                    findings.append(
                        Finding(
                            path=rel_path,
                            line=call_node.lineno,
                            pattern="not_implemented_error",
                            detail=f"raise NotImplementedError in {node.name}()",
                        )
                    )

            in_protocol = protocol_class_stack and protocol_class_stack[-1]
            if _is_bare_pass_body(node) and not _is_abstractmethod(node) and not in_protocol:
                findings.append(
                    Finding(
                        path=rel_path,
                        line=node.lineno,
                        pattern="bare_pass_body",
                        detail=f"def {node.name}(...): pass  # no real body",
                    )
                )
            self.generic_visit(node)

        visit_FunctionDef = _visit_function  # noqa: N815 (ast API name)
        visit_AsyncFunctionDef = _visit_function  # noqa: N815 (ast API name)

    Visitor().visit(tree)
    return findings


def scan(root: Path) -> list[Finding]:
    """Scan every production file under `root` and return all findings,
    in stable (path, line) order for reproducible output."""
    findings: list[Finding] = []
    for path in _iter_production_python_files(root):
        rel_path = path.relative_to(root).as_posix()
        findings.extend(_scan_comment_markers(path, rel_path))
        findings.extend(_scan_ast(path, rel_path))
    return sorted(findings, key=lambda f: (f.path, f.line, f.pattern))


def load_allowlist(root: Path) -> dict[tuple[str, int, str], str]:
    """Load the committed allowlist as {(path, line, pattern): reason}.
    A missing file means an empty (not permissive) allowlist -- fail
    closed, not open."""
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
        result[(entry["path"], int(entry["line"]), entry["pattern"])] = reason
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
    args = parser.parse_args()

    findings = scan(args.root)
    allowlist = load_allowlist(args.root)

    unallowlisted = [f for f in findings if f.key() not in allowlist]
    allowlisted = [f for f in findings if f.key() in allowlist]

    if allowlisted:
        print(f"[incomplete-implementations] {len(allowlisted)} allowlisted finding(s):")
        for f in allowlisted:
            print(f"  - {f.path}:{f.line} [{f.pattern}] -- {allowlist[f.key()]}")

    if unallowlisted:
        print(
            f"[incomplete-implementations] FAIL -- {len(unallowlisted)} unallowlisted "
            "finding(s):",
            file=sys.stderr,
        )
        for f in unallowlisted:
            print(f"  - {f.path}:{f.line} [{f.pattern}] {f.detail}", file=sys.stderr)
        return 1

    print(
        f"[incomplete-implementations] PASS -- {len(findings)} finding(s), all allowlisted "
        "and justified"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
