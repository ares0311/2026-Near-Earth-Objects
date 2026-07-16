from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SETUP_UV_ACTION = "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990"


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

    assert f"uses: {SETUP_UV_ACTION}" in release
    assert 'python-version: "3.14"' in release
    assert "uv sync --locked --extra dev" in release
    assert "uv run --python 3.14 python -m pytest" in release
    assert "run: uv build" in release
    assert "actions/setup-python" not in release


def test_workflows_use_node24_action_versions() -> None:
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text()
        if "uses: actions/checkout@" in text:
            assert "uses: actions/checkout@v5" in text
            assert "uses: actions/checkout@v4" not in text
        if "uses: astral-sh/setup-uv@" in text:
            assert f"uses: {SETUP_UV_ACTION}" in text
            assert "uses: astral-sh/setup-uv@v5" not in text


def test_parallel_e2e_jobs_do_not_race_to_save_the_same_uv_cache() -> None:
    e2e = (WORKFLOWS / "e2e.yml").read_text()

    assert e2e.count('save-cache: "false"') == e2e.count(f"uses: {SETUP_UV_ACTION}")
