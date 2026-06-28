# Linker Diagnostics Validation

Date: 2026-06-28

Branch/run state: local `main` after PR #135, before publishing linker
diagnostic instrumentation.

## Purpose

Validate the linker provenance diagnostics added to explain WISE
`5200` singleton candidates -> `0` tracklets before asking for another live
WISE archive run.

## Operator Validation Command

```bash
git pull origin main
PYTHONPATH=src uv run --python 3.14 --extra dev python -m pytest tests/test_link.py tests/test_schemas.py::TestLinkResult tests/test_pipeline.py::TestRunPipelineCheckpointResume -q
uv run --python 3.14 --extra dev ruff check src/link.py src/schemas.py Skills/run_pipeline.py tests/test_link.py tests/test_schemas.py tests/test_pipeline.py
PYTHONPATH=src uv run --python 3.14 --extra dev python -m mypy src
```

## Result

- `git pull origin main`: already up to date
- Targeted pytest: `80 passed in 1.05s`
- Ruff: all checks passed
- Mypy: success, no issues in 12 source files

## Interpretation

The linker diagnostic instrumentation is locally validated on Python 3.14.3.
The next production step is to publish the instrumentation through GitHub CI,
merge it to `main`, then rerun the bounded WISE dry-run diagnostic only after
the merged code can report seed-pair and rejection-category counts.

## Safety

No live archive query, MPC submission, NASA/PDCO notification, impact-probability
claim, or confirmed-object claim was made by this validation command.
