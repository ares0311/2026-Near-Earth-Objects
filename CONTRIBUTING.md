# Contributing

Thank you for your interest in contributing to the NEO Detection and Ranking Pipeline.

## Development Setup

```bash
git clone <repo-url>
cd 2026-Near-Earth-Objects
pip install -e ".[dev]"
pip install ruff mypy types-requests
```

## Branch Workflow

- All work goes on a feature branch cut from `main`
- Name branches `feature/<short-desc>` or `fix/<short-desc>`
- Open a draft PR early; mark ready when CI is green

## Quality Checks

Run all three checks before pushing:

```bash
ruff check .
python -m mypy src --ignore-missing-imports
PYTHONPATH=src python -m pytest -m "not integration_live" -q --cov=src --cov-fail-under=80
```

Or all at once:

```bash
ruff check . && python -m mypy src --ignore-missing-imports && PYTHONPATH=src python -m pytest -m "not integration_live" -q --cov=src --cov-fail-under=80
```

## Adding a New Module

1. Place source in `src/<module>.py` with `__all__` defined
2. Add a corresponding `tests/test_<module>.py` with ≥ 80% coverage
3. Update `CLAUDE.md` module table
4. Add a row to `docs/PIPELINE_SPEC.md` if it is a pipeline stage

## Adding a Utility Script

Place standalone scripts in `Skills/` with a docstring and `if __name__ == "__main__":` guard.
Update the Skills table in `CLAUDE.md`.

## Test Guidelines

- Unit tests only in `tests/`; no network calls without `@pytest.mark.integration_live`
- Use `monkeypatch` to redirect `_CACHE_DIR` and other module-level path constants
- Use `patch("requests.get", ...)` for HTTP calls
- Never `time.sleep` inside tests; patch `module.time.sleep` where needed

## Coding Conventions

- Python 3.11+ syntax; `from __future__ import annotations` in every module
- Pydantic v2 models with `ConfigDict(frozen=True)` for all pipeline data types
- All features bounded to `[0, 1]`; missing features are `None` (never `-1` or `0`)
- No mutable global state; pass context as function arguments

## Alert Protocol

The alert pathway defined in `CLAUDE.md` is **non-negotiable**. No PR may bypass:
1. MPC submission before any external notification
2. Independent confirmation before `nasa_pdco_notify`
3. No public impact probability statements from pipeline output alone

## Commit Messages

Use imperative mood, ≤ 72 characters in the subject line:

```
add batch_score.py skill for ranking tracklets from JSON
fix IndexError in _parse_atlas_photometry on empty input
boost preprocess.py coverage to 93%
```

## CI

GitHub Actions runs on every push (Python 3.11 and 3.12):
- `ruff check .` — linting
- `python -m mypy src` — type checking
- `pytest --cov=src --cov-fail-under=80` — tests with 80% coverage gate

Integration tests (requiring live network) are excluded from CI. Run them manually:

```bash
PYTHONPATH=src python -m pytest -m integration_live -v
```
