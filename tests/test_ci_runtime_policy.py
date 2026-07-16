from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_workflows_do_not_invoke_bare_python_or_pip() -> None:
    forbidden_prefixes = (
        "python ",
        "pip ",
        "PYTHONPATH=src python ",
    )
    violations: list[str] = []

    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, line in enumerate(workflow.read_text().splitlines(), start=1):
            command = line.strip()
            if command.startswith("run: "):
                command = command.removeprefix("run: ")
            if command.startswith(forbidden_prefixes):
                violations.append(f"{workflow.name}:{line_number}: {command}")

    assert violations == []


def test_release_workflow_uses_locked_python_314_uv_environment() -> None:
    release = (WORKFLOWS / "release.yml").read_text()

    assert "uses: astral-sh/setup-uv@v5" in release
    assert 'python-version: "3.14"' in release
    assert "uv sync --locked --extra dev" in release
    assert "uv run --python 3.14 python -m pytest" in release
    assert "run: uv build" in release
    assert "actions/setup-python" not in release
