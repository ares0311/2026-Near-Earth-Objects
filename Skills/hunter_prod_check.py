#!/usr/bin/env python3
"""Repository-native PROD gate for NEOHunter (Hunter contract PROD-01).

Emits a versioned machine-readable report and exits nonzero when any mandatory
requirement fails. Unit tests alone are explicitly *not* ``prod-check``: this
gate inspects the installed product, its packaging, its interaction surface, its
durable-state contract, and the integrity of its own claims.

Every check returns one of three outcomes, and the distinction matters:

``PASS``          the requirement was executed and satisfied.
``FAIL``          the requirement was executed and violated.
``NOT_EXECUTED``  the check could not run. Per contract rule CLAIM-03 this is
                  never counted as a pass and never folded into an ``N/N passed``
                  total; it is reported separately with its reason.

Usage::

    uv run --python 3.14 python Skills/hunter_prod_check.py
    uv run --python 3.14 python Skills/hunter_prod_check.py --json report.json
    uv run --python 3.14 python Skills/hunter_prod_check.py --skip-slow
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Skills"))
sys.path.insert(0, str(REPO_ROOT / "src"))

# Report schema version. Bump when the report's shape changes so consumers can
# detect an incompatible format rather than misreading it.
REPORT_SCHEMA_VERSION = "hunter-prod-check-1.0.0"

PASS = "PASS"
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"


@dataclass
class CheckResult:
    """One check's outcome plus the evidence a reader needs to trust it."""

    check_id: str
    area: str
    requirements: tuple[str, ...]
    status: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "area": self.area,
            "requirements": list(self.requirements),
            "status": self.status,
            "detail": self.detail,
            "evidence": self.evidence,
        }


# Registry of every check, populated by the decorator below.
CHECKS: list[tuple[str, str, tuple[str, ...], bool, Callable[[], CheckResult]]] = []


def check(
    check_id: str, area: str, requirements: tuple[str, ...], *, slow: bool = False
):
    """Register one check so the runner can enumerate and report all of them."""

    def decorate(function: Callable[[], CheckResult]) -> Callable[[], CheckResult]:
        CHECKS.append((check_id, area, requirements, slow, function))
        return function

    return decorate


def _result(
    check_id: str,
    area: str,
    requirements: tuple[str, ...],
    status: str,
    detail: str,
    **evidence: Any,
) -> CheckResult:
    return CheckResult(check_id, area, requirements, status, detail, evidence)


def _run(command: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with the repository's own cache and no PYTHONPATH help."""
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": "",
            "UV_CACHE_DIR": str(REPO_ROOT / ".uv-cache"),
        },
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# --- Packaging and installation --------------------------------------------


@check("package-completeness", "packaging", ("LAUNCH-02", "PIPE-01"))
def check_package_completeness() -> CheckResult:
    """Every production runtime package must be declared for installation."""
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    setuptools_config = config["tool"]["setuptools"]
    packages = set(setuptools_config.get("packages", []))
    package_dir = setuptools_config.get("package-dir", {})

    problems = []
    if package_dir.get("Skills") != "Skills":
        problems.append("package-dir is missing the 'Skills' mapping (NEO-FIELD-01)")
    for required in ("Skills", "Skills.hunter_ux"):
        if required not in packages:
            problems.append(f"packages is missing {required!r}")

    scripts = config["project"].get("scripts", {})
    if "NEOHunter" not in scripts:
        problems.append("no NEOHunter console script is registered")

    return _result(
        "package-completeness",
        "packaging",
        ("LAUNCH-02", "PIPE-01"),
        FAIL if problems else PASS,
        "; ".join(problems) if problems else "all production packages and entry points declared",
        packages=sorted(packages),
        console_scripts=sorted(scripts),
    )


@check("installed-launch", "launch", ("LAUNCH-01", "LAUNCH-04"), slow=True)
def check_installed_launch() -> CheckResult:
    """The documented console script must launch from an unrelated directory."""
    executable = REPO_ROOT / ".venv" / "bin" / "NEOHunter"
    if not executable.is_file():
        return _result(
            "installed-launch",
            "launch",
            ("LAUNCH-01", "LAUNCH-04"),
            NOT_EXECUTED,
            f"console script not installed at {executable}; run the documented uv sync first",
        )
    # Run from the user's home directory: outside the repository, so nothing on
    # sys.path can come from the source checkout being the CWD.
    completed = subprocess.run(
        [str(executable), "--no-animation", "--no-color", "--command", "/Help"],
        cwd=Path.home(),
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    ok = completed.returncode == 0 and "NEOHunter commands" in completed.stdout
    return _result(
        "installed-launch",
        "launch",
        ("LAUNCH-01", "LAUNCH-04"),
        PASS if ok else FAIL,
        "installed NEOHunter launched and rendered its command reference"
        if ok
        else f"launch failed (exit {completed.returncode}): {completed.stderr.strip()[:300]}",
        exit_status=completed.returncode,
        working_directory=str(Path.home()),
        resolved_executable=str(executable),
    )


@check("execution-surfaces", "launch", ("LAUNCH-02", "LAUNCH-03"), slow=True)
def check_execution_surfaces() -> CheckResult:
    """Wheel and editable surfaces must each be verified independently."""
    completed = _run(
        [
            "uv", "run", "--no-sync", "--python", "3.14", "python",
            "Skills/verify_hunter_distribution.py", "--surface", "both",
        ]
    )
    ok = completed.returncode == 0
    return _result(
        "execution-surfaces",
        "launch",
        ("LAUNCH-02", "LAUNCH-03"),
        PASS if ok else FAIL,
        "wheel and editable surfaces both verified"
        if ok
        else f"surface verification failed: {completed.stderr.strip()[:300]}",
        exit_status=completed.returncode,
        stdout_tail=completed.stdout.strip().splitlines()[-4:],
    )


# --- Interaction surface ----------------------------------------------------


@check("command-palette", "cli", ("CLI-01", "CLI-02", "UX-CMD-01", "UX-CMD-02"))
def check_command_palette() -> CheckResult:
    """Every required command must exist and describe its parameters."""
    from hunter_ux import registry

    required = {
        "/New-Search",
        "/Follow-Up-Search",
        "/Run-Search",
        "/Show-Follow-Ups",
        "/Inspect-Target",
        "/Help",
        "/Exit",
    }
    registered = {command.name for command in registry.COMMANDS}
    missing = sorted(required - registered)

    undescribed = [
        command.name
        for command in registry.COMMANDS
        if not command.summary
        or (not command.is_meta and not command.params and command.subcommand)
    ]
    problems = []
    if missing:
        problems.append(f"missing commands: {missing}")
    if undescribed:
        problems.append(f"commands without descriptions or parameters: {undescribed}")

    return _result(
        "command-palette",
        "cli",
        ("CLI-01", "CLI-02", "UX-CMD-01", "UX-CMD-02"),
        FAIL if problems else PASS,
        "; ".join(problems) if problems else f"{len(registered)} commands registered and described",
        registered=sorted(registered),
    )


@check("interactive-pty-operator", "cli", ("LAUNCH-04", "CLI-01", "CLI-02", "UX-CMD-01"), slow=True)
def check_interactive_pty_operator() -> CheckResult:
    """The installed executable must pass real keystrokes in a real terminal.

    Delegates to ``Skills/hunter_pty_gate.py``. That gate is deliberately a
    separate executable: the palette requirement (UX-CMD-01) is about what a
    terminal does with a single ``/`` byte before Enter, which nothing importable
    from this process can demonstrate.
    """
    requirements = ("LAUNCH-04", "CLI-01", "CLI-02", "UX-CMD-01")
    report_path = REPO_ROOT / "Logs" / "prod_closure" / "pty_gate.json"
    runner = "bash scripts/run_pty_gate.sh --runs 3"

    # This check consumes the gate's report rather than running the gate, and
    # that is forced by how sandboxing works, not by convenience. The exclusion
    # in sandbox.excludedCommands applies to the command Claude Code launches;
    # a subprocess spawned by an already-sandboxed process inherits the sandbox,
    # so invoking the gate from here yields PTY-denied every time. Measured
    # directly: the same command exits 0 when launched on its own and reports
    # NOT_EXECUTED when spawned from this module.
    if not report_path.is_file():
        return _result(
            "interactive-pty-operator", "cli", requirements, NOT_EXECUTED,
            f"no real-PTY report at {report_path.relative_to(REPO_ROOT)}; run: {runner}",
        )

    try:
        report = json.loads(report_path.read_text())
    except json.JSONDecodeError as exc:
        return _result(
            "interactive-pty-operator", "cli", requirements, FAIL,
            f"real-PTY report is not valid JSON: {exc}",
        )

    # Freshness: a report that predates the code it claims to have exercised is
    # describing a build that no longer exists. Without this, editing the shell
    # would silently inherit the previous run's PASS.
    exercised = [
        REPO_ROOT / "Skills" / "hunter_shell.py",
        REPO_ROOT / "Skills" / "hunter_pty_gate.py",
        REPO_ROOT / "src" / "hunter_commands.py",
        *(REPO_ROOT / "Skills" / "hunter_ux").glob("*.py"),
    ]
    report_mtime = report_path.stat().st_mtime
    stale = [
        str(path.relative_to(REPO_ROOT))
        for path in exercised
        if path.is_file() and path.stat().st_mtime > report_mtime
    ]
    if stale:
        return _result(
            "interactive-pty-operator", "cli", requirements, NOT_EXECUTED,
            f"real-PTY report is stale: {sorted(stale)} changed after it ran; re-run: {runner}",
            report_generated=report.get("finished_at_utc"),
        )

    status = report.get("status")
    runs = int(report.get("completed_runs") or 0)
    if status == NOT_EXECUTED:
        return _result(
            "interactive-pty-operator", "cli", requirements, NOT_EXECUTED,
            f"real-PTY gate did not execute: {report.get('reason')}",
        )
    if status != PASS:
        failed = [
            assertion["assertion_id"]
            for run in report.get("runs", [])
            for assertion in run.get("assertions", [])
            if assertion.get("status") != PASS
        ]
        return _result(
            "interactive-pty-operator", "cli", requirements, FAIL,
            f"real-PTY assertions failed: {sorted(set(failed))}",
        )
    # Contract-required repetition: a single green run does not establish that
    # an interactive terminal surface is stable.
    if runs < 3:
        return _result(
            "interactive-pty-operator", "cli", requirements, NOT_EXECUTED,
            f"real-PTY gate passed but only {runs} run(s) recorded; three are required: {runner}",
        )

    assertion_count = sum(len(run.get("assertions", [])) for run in report.get("runs", []))
    return _result(
        "interactive-pty-operator", "cli", requirements, PASS,
        f"installed executable passed {assertion_count} real-PTY assertions across {runs} runs",
        code_identity=report.get("code_identity"),
        generated_at=report.get("finished_at_utc"),
        resolved_executable=report.get("resolved_executable"),
    )


@check("guided-input-validation", "cli", ("CLI-03", "UX-IN-03", "UX-IN-04"))
def check_guided_input_validation() -> CheckResult:
    """Interactive and scriptable paths must share one validator, and reject bad input."""
    import argparse as _argparse

    from hunter_ux import validation

    problems = []
    for raw in ("twenty", "0", "-1", ""):
        value, error = validation.validate_target_count(raw)
        if value is not None or not error:
            problems.append(f"target count {raw!r} was not rejected")

    converter = validation.as_argparse_type(validation.validate_target_count)
    try:
        converter("0")
        problems.append("argparse adapter accepted an invalid value")
    except _argparse.ArgumentTypeError:
        pass

    return _result(
        "guided-input-validation",
        "cli",
        ("CLI-03", "UX-IN-03", "UX-IN-04"),
        FAIL if problems else PASS,
        "; ".join(problems) if problems else "shared validators reject invalid input on both paths",
    )


@check("domain-animation", "cli", ("CLI-01", "UX-START-01", "UX-START-02", "UX-START-03"))
def check_domain_animation() -> CheckResult:
    """Startup animation must be real, domain-specific, and make no data claim."""
    from hunter_ux import animation, theme

    capabilities = theme.Capabilities(
        is_tty=True, color=False, animation=True, unicode=True, width=100
    )
    frames = list(animation.startup_sequence(capabilities))
    joined = " ".join(frames).casefold()

    themes = (
        "orbital sweep",
        "radar acquisition",
        "trajectory projection",
        "close-approach geometry",
        "moving-object survey",
        "telescope scan",
    )
    missing = [motif for motif in themes if motif not in joined]
    fabricated = [word for word in ("%", "discovered", "detected") if word in joined]

    problems = []
    if len(frames) < 8:
        problems.append(f"only {len(frames)} frames; a static logo is nonconforming")
    if missing:
        problems.append(f"missing NEOHunter themes: {missing}")
    if fabricated:
        problems.append(f"animation implies data state: {fabricated}")

    return _result(
        "domain-animation",
        "cli",
        ("CLI-01", "UX-START-01", "UX-START-02", "UX-START-03"),
        FAIL if problems else PASS,
        "; ".join(problems) if problems else f"{len(frames)} frames across all six NEO themes",
        frame_count=len(frames),
    )


@check("result-table-behavior", "cli", ("CLI-01", "UX-TABLE-01", "UX-TABLE-02"))
def check_result_table_behavior() -> CheckResult:
    """Tables must respect terminal width and preserve rank and identity."""
    from hunter_ux import table, theme

    rows = [
        {
            "rank": index + 1,
            "target_id": f"NEO-FIELD-{index:04d}",
            "neo_class": "aten",
            "ra_deg": 217.41,
            "dec_deg": -15.0,
            "score": 0.93,
            "nights": 3,
            "storage_mb": 512.0,
            "status": "pending",
        }
        for index in range(5)
    ]

    problems = []
    for width in (40, 60, 80, 140, 200):
        capabilities = theme.Capabilities(
            is_tty=False, color=False, animation=False, unicode=True, width=width
        )
        for line in table.render_table(rows, capabilities):
            if len(line) > width:
                problems.append(f"width {width}: line of {len(line)} characters overflows")
                break
        keys = {column.key for column in table.select_columns(table.DEFAULT_COLUMNS, width)}
        if "rank" not in keys or "target_id" not in keys:
            problems.append(f"width {width}: rank or identity column was dropped")

    return _result(
        "result-table-behavior",
        "cli",
        ("CLI-01", "UX-TABLE-01", "UX-TABLE-02"),
        FAIL if problems else PASS,
        "; ".join(problems) if problems
        else "tables fit every tested width with rank and identity preserved",
        widths_tested=[40, 60, 80, 140, 200],
    )


@check("accessible-degradation", "cli", ("UX-START-04", "UX-A11Y-01", "UX-TABLE-04"))
def check_accessible_degradation() -> CheckResult:
    """Animation and colour must degrade for non-TTY and accessibility modes."""
    import io

    from hunter_ux import theme

    class _NonTty(io.StringIO):
        def isatty(self) -> bool:
            return False

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    problems = []
    if theme.detect(_NonTty(), environ={}).animation:
        problems.append("animation stayed enabled on a non-TTY stream")
    if theme.detect(_Tty(), environ={"NO_COLOR": "1"}).color:
        problems.append("NO_COLOR did not disable colour")
    if theme.detect(_Tty(), environ={"CI": "1"}).animation:
        problems.append("animation stayed enabled under CI")
    for mode in ("reduced_motion", "no_animation", "machine_readable"):
        if theme.detect(_Tty(), environ={}, **{mode: True}).animation:
            problems.append(f"{mode} did not disable animation")

    return _result(
        "accessible-degradation",
        "cli",
        ("UX-START-04", "UX-A11Y-01", "UX-TABLE-04"),
        FAIL if problems else PASS,
        "; ".join(problems) if problems else "animation and colour degrade in every required mode",
    )


# --- Canonical pipeline routing --------------------------------------------


@check("canonical-routing", "pipeline", ("PIPE-01", "PIPE-02", "CLI-03"))
def check_canonical_routing() -> CheckResult:
    """The shell must delegate to the one canonical pipeline, not reimplement it."""
    import io

    import hunter_shell
    from hunter_ux import registry, theme

    capabilities = theme.Capabilities(
        is_tty=False, color=False, animation=False, unicode=True, width=100
    )
    captured: list[list[str]] = []

    for line, expected_subcommand in (
        ("/New-Search 5", "create-new-search"),
        ("/Follow-Up-Search 5", "create-new-search"),
        ("/Run-Search", "run-new-search"),
        ("/Show-Follow-Ups", "show-follow-ups"),
    ):
        out, err = io.StringIO(), io.StringIO()
        hunter_shell.execute_slash_command(
            line,
            runner=lambda argv: (captured.append(argv), 0)[1],
            stream=out,
            err=err,
            capabilities=capabilities,
            state=registry.ShellState(pending_search_ids=("S-1",), last_result_count=1),
        )
        if not captured or captured[-1][0] != expected_subcommand:
            return _result(
                "canonical-routing",
                "pipeline",
                ("PIPE-01", "PIPE-02", "CLI-03"),
                FAIL,
                f"{line!r} did not route to {expected_subcommand!r}",
                captured=captured,
            )

    return _result(
        "canonical-routing",
        "pipeline",
        ("PIPE-01", "PIPE-02", "CLI-03"),
        PASS,
        "every interactive command routes to the canonical hunter_cli subcommand",
        routed=[argv[0] for argv in captured],
    )


@check("durable-state-entities", "durability", ("DUR-01", "DUR-02", "DUR-03"))
def check_durable_state_entities() -> CheckResult:
    """The five required durable records must exist with stable identifiers."""
    import hunter_state

    required_tables = {
        "search_manifests",
        "search_manifest_targets",
        "search_runs",
        "search_run_targets",
        "target_search_history",
        "follow_up_registry",
    }
    import sqlite3
    import tempfile

    with tempfile.TemporaryDirectory(prefix="hunter-prod-check-") as raw_tmp:
        database = Path(raw_tmp) / "state.sqlite"
        hunter_state.init_db(database)
        with sqlite3.connect(database) as connection:
            present = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

    missing = sorted(required_tables - present)
    return _result(
        "durable-state-entities",
        "durability",
        ("DUR-01", "DUR-02", "DUR-03"),
        FAIL if missing else PASS,
        f"missing durable tables: {missing}" if missing else
        f"all {len(required_tables)} durable record types present",
        tables=sorted(present),
    )


# --- Claim integrity --------------------------------------------------------


@check("skipped-stage-labeling", "claims", ("CLAIM-03",))
def check_skipped_stage_labeling() -> CheckResult:
    """A notice-only CI workflow must not present itself as an executed test stage."""
    workflow = REPO_ROOT / ".github" / "workflows" / "integration.yml"
    if not workflow.is_file():
        return _result(
            "skipped-stage-labeling",
            "claims",
            ("CLAIM-03",),
            NOT_EXECUTED,
            "integration workflow not found",
        )
    text = workflow.read_text()
    executes_tests = "pytest" in text and "run:" in text and "::notice" not in text
    declares_skip = "NOT EXECUTED" in text or "skipped" in text.casefold()

    problems = []
    if executes_tests:
        problems.append("workflow appears to run tests but is registered as notice-only")
    if not declares_skip:
        problems.append("notice-only workflow does not label itself as not executed")

    return _result(
        "skipped-stage-labeling",
        "claims",
        ("CLAIM-03",),
        FAIL if problems else PASS,
        "; ".join(problems) if problems
        else "notice-only integration workflow is labelled as not executed",
        workflow=str(workflow.relative_to(REPO_ROOT)),
    )


@check("coverage-denominator", "claims", ("CLAIM-02",))
def check_coverage_denominator() -> CheckResult:
    """Coverage configuration must name what it actually measures."""
    workflow = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.is_file():
        return _result(
            "coverage-denominator", "claims", ("CLAIM-02",), NOT_EXECUTED, "ci.yml not found"
        )
    text = workflow.read_text()
    measured = [token for token in ("--cov=src", "--cov=Skills") if token in text]

    # Production runtime lives in both src/ and Skills/. Measuring only src is
    # permitted, but then the denominator must be stated rather than implied.
    covers_skills = "--cov=Skills" in text
    return _result(
        "coverage-denominator",
        "claims",
        ("CLAIM-02",),
        PASS if covers_skills else FAIL,
        "coverage measures both src and the Skills production runtime"
        if covers_skills
        else "coverage measures src only while production runtime also lives in Skills; "
             "either measure Skills or report '100% statement coverage of src only'",
        measured=measured,
    )


@check("state-ledger-integrity", "claims", ("CLAIM-04",))
def check_state_ledger_integrity() -> CheckResult:
    """The PROD ledger must be valid JSON with complete evidence for VERIFIED items."""
    import hunter_prod_state

    try:
        state = hunter_prod_state.load_state()
    except hunter_prod_state.LedgerError as exc:
        return _result(
            "state-ledger-integrity", "claims", ("CLAIM-04",), FAIL, str(exc)
        )
    problems = hunter_prod_state.validate_state(state)
    return _result(
        "state-ledger-integrity",
        "claims",
        ("CLAIM-04",),
        FAIL if problems else PASS,
        "; ".join(problems) if problems
        else "ledger is valid and every VERIFIED claim carries full evidence",
        verified_count=sum(
            1 for record in state.get("requirements", {}).values()
            if record.get("status") == "VERIFIED"
        ),
    )


@check("sibling-write-isolation", "workspace", ("WS-01", "WS-03"))
def check_sibling_write_isolation() -> CheckResult:
    """No runtime import, symlink, or hard-coded path may reach a sibling repository."""
    siblings = ("2026 Exoplanet Research", "2026 Technosignatures", "EXOHunter", "TechnoHunter")
    offenders: list[str] = []

    # This module names the sibling repositories in order to search for them, so
    # scanning itself would be a guaranteed false positive.
    self_path = Path(__file__).resolve()

    # Coupling that matters is *runtime* coupling: an import, or a filesystem
    # path that resolves into a sibling checkout. A sibling name appearing in a
    # comment or docstring is documentation, not a dependency.
    coupling_markers = ("import ", "from ", "Path(", "open(", "sys.path")

    source_files = list((REPO_ROOT / "src").rglob("*.py"))
    source_files += list((REPO_ROOT / "Skills").rglob("*.py"))
    for path in source_files:
        if path.resolve() == self_path:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            if not any(sibling in line for sibling in siblings):
                continue
            if any(marker in line for marker in coupling_markers):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{number} couples to a sibling repository"
                )

    # A symlink escaping the repository is the other coupling route. Generated
    # and vendored trees are excluded: they are not part of the product.
    excluded_roots = {
        ".venv", ".git", "Logs", "build", "dist", ".uv-cache", ".mypy_cache",
        ".pytest_cache", ".ruff_cache", ".neo_cache", "alert_logs",
    }
    def _is_excluded(name: str) -> bool:
        """A directory we never descend into, and never report from."""
        return name in excluded_roots or name.startswith("pytest-of-")

    # os.walk with in-place pruning of `dirnames`, rather than Path.rglob. rglob
    # has no way to skip a subtree: it descends into .venv, .git, .uv-cache, and
    # the data directories in full and only then filters the results. On this
    # repository -- a large tree on a cloud-synced volume -- that cost ~320
    # seconds per run and made the PROD gate itself impractical to execute.
    # Pruning changes only *which paths are visited*, never which paths are
    # reported: every pruned directory was already excluded from the results.
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT, followlinks=False):
        dirnames[:] = [name for name in dirnames if not _is_excluded(name)]
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                continue
            target = path.resolve()
            if REPO_ROOT not in target.parents and target != REPO_ROOT:
                offenders.append(f"{path.relative_to(REPO_ROOT)} symlinks outside the repository")

    return _result(
        "sibling-write-isolation",
        "workspace",
        ("WS-01", "WS-03"),
        FAIL if offenders else PASS,
        "; ".join(offenders[:5]) if offenders else "no sibling-repository coupling found",
        offender_count=len(offenders),
    )


@check("readme-conformance", "readme", ("README-01", "README-02", "README-03"))
def check_readme_conformance() -> CheckResult:
    """README structure and status vocabulary must follow docs/README_SPEC.md."""
    readme = REPO_ROOT / "README.md"
    if not readme.is_file():
        return _result(
            "readme-conformance",
            "readme",
            ("README-01", "README-02", "README-03"),
            FAIL,
            "README.md is missing",
        )
    text = readme.read_text(encoding="utf-8")
    required_headings = [
        "## Table of Contents",
        "## 1. Executive Summary",
        "## 2. CLI Tool Usage",
        "## 3. Analytics, Mathematics, and Theoretical Foundation",
        "## 4. Sibling Repositories and Shared Data",
    ]
    problems = []
    last_index = -1
    for heading in required_headings:
        index = text.find(heading)
        if index == -1:
            problems.append(f"missing required heading {heading!r}")
        elif index < last_index:
            problems.append(f"heading out of order: {heading!r}")
        else:
            last_index = index

    # Forbidden roadmap vocabulary (README-03).
    for banned in ("**Planned**", "**Partial**", "roadmap", "backlog", "future work"):
        if banned.casefold() in text.casefold():
            problems.append(f"forbidden status vocabulary present: {banned!r}")

    return _result(
        "readme-conformance",
        "readme",
        ("README-01", "README-02", "README-03"),
        FAIL if problems else PASS,
        "; ".join(problems[:5]) if problems else "README structure and status vocabulary conform",
        problem_count=len(problems),
    )


@check("golden-ux-tests", "cli", ("EVAL-01",))
def check_golden_ux_tests() -> CheckResult:
    """The specification's golden UX artefacts must exist and be committed."""
    golden_dir = REPO_ROOT / "tests" / "golden"
    expected = (
        "startup_neo.txt",
        "command_palette.txt",
        "new_search_fields.txt",
        "invalid_targets.txt",
        "action_preview.txt",
        "results_table_80_columns.txt",
        "results_table_140_columns.txt",
        "operator_error.txt",
        "non_tty_output.txt",
    )
    missing = [name for name in expected if not (golden_dir / name).is_file()]
    return _result(
        "golden-ux-tests",
        "cli",
        ("EVAL-01",),
        FAIL if missing else PASS,
        f"missing golden artefacts: {missing}" if missing
        else f"{len(expected)} golden UX artefacts present",
        golden_directory=str(golden_dir.relative_to(REPO_ROOT)),
    )


@check("real-data-evidence-freshness", "evidence", ("E2E-01", "E2E-02", "E2E-04"))
def check_real_data_evidence() -> CheckResult:
    """Real-data acceptance evidence must exist for the current contract."""
    import hunter_prod_state

    try:
        state = hunter_prod_state.load_state()
    except hunter_prod_state.LedgerError as exc:
        return _result(
            "real-data-evidence-freshness",
            "evidence",
            ("E2E-01", "E2E-02", "E2E-04"),
            NOT_EXECUTED,
            f"ledger unreadable: {exc}",
        )

    evidence = state.get("evidence", {})
    missing = [
        requirement
        for requirement in ("E2E-01", "E2E-02", "E2E-03", "E2E-04")
        if requirement not in evidence
    ]
    return _result(
        "real-data-evidence-freshness",
        "evidence",
        ("E2E-01", "E2E-02", "E2E-04"),
        FAIL if missing else PASS,
        f"no retained real-data acceptance evidence for: {missing}" if missing
        else "real-data acceptance evidence recorded for every E2E requirement",
        recorded=sorted(set(evidence) & {"E2E-01", "E2E-02", "E2E-03", "E2E-04"}),
    )


def run_checks(*, skip_slow: bool = False) -> list[CheckResult]:
    """Execute every registered check, never letting one failure hide the rest."""
    results: list[CheckResult] = []
    for check_id, area, requirements, slow, function in CHECKS:
        if slow and skip_slow:
            results.append(
                _result(
                    check_id, area, requirements, NOT_EXECUTED,
                    "skipped by --skip-slow; this is not a pass",
                )
            )
            continue
        try:
            results.append(function())
        except Exception as exc:  # noqa: BLE001 - a broken check must be visible, not silent
            results.append(
                _result(
                    check_id, area, requirements, FAIL,
                    f"check raised {type(exc).__name__}: {exc}",
                )
            )
    return results


def build_report(results: list[CheckResult]) -> dict[str, Any]:
    """Assemble the versioned machine-readable report."""
    passed = [r for r in results if r.status == PASS]
    failed = [r for r in results if r.status == FAIL]
    not_executed = [r for r in results if r.status == NOT_EXECUTED]

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": head,
        "summary": {
            # Deliberately three separate counts. CLAIM-03 forbids folding
            # NOT_EXECUTED into an N/N passed total.
            "executed": len(passed) + len(failed),
            "passed": len(passed),
            "failed": len(failed),
            "not_executed": len(not_executed),
        },
        "prod_ready": not failed and not not_executed,
        "results": [result.as_dict() for result in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="write the report to this path")
    parser.add_argument(
        "--skip-slow",
        action="store_true",
        help="skip subprocess-heavy checks; they are then reported NOT_EXECUTED, never passed",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        metavar="CHECK_ID",
        help=(
            "run only the named check(s) and exit 0 only if every one PASSes. "
            "Lets one requirement closure bind to one deterministic command."
        ),
    )
    args = parser.parse_args(argv)

    if args.require:
        known = {check_id for check_id, *_ in CHECKS}
        unknown = sorted(set(args.require) - known)
        if unknown:
            parser.error(f"unknown check id(s) {unknown}; known: {sorted(known)}")
        results = []
        for check_id, area, requirements, _slow, function in CHECKS:
            if check_id not in args.require:
                continue
            try:
                results.append(function())
            except Exception as exc:  # noqa: BLE001 - a broken check must be visible
                results.append(
                    _result(check_id, area, requirements, FAIL,
                            f"check raised {type(exc).__name__}: {exc}")
                )
    else:
        results = run_checks(skip_slow=args.skip_slow)
    report = build_report(results)

    width = max(len(result.check_id) for result in results)
    for result in results:
        print(f"{result.status:<13} {result.check_id.ljust(width)}  {result.detail}")

    summary = report["summary"]
    print()
    print(
        f"executed {summary['executed']}  "
        f"passed {summary['passed']}  "
        f"failed {summary['failed']}  "
        f"NOT EXECUTED {summary['not_executed']}"
    )
    if summary["not_executed"]:
        print("NOT EXECUTED stages are not passes and are excluded from the executed total.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report written to {args.json}")

    # Exit nonzero when any mandatory requirement fails, or when a mandatory
    # check could not be executed at all.
    return 0 if report["prod_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
