# CI Parallel Coverage Evidence — 2026-07-21

## Objective

Restore a complete mandatory GitHub CI result after PR #262's serial test job
exceeded the workflow's 15-minute budget, without changing test selection or
weakening the repository's 100% `src/` coverage requirement.

## Failure evidence

- PR: #262, head `dba544e7b42e5eda8522c054ba4c50cbe8ee0c8f`.
- GitHub Actions run: `29690734426`, job `88202867656`.
- Ruff passed; mypy passed over all 18 source files.
- Pytest advanced to 68% with no reported assertion failure, then GitHub
  cancelled the job at the configured 15-minute timeout.
- Six separate end-to-end workflow checks passed on the same PR.

The failure mode was therefore exhausted wall-clock budget in the serial test
stage, not a known lint, type, test, or coverage defect.

## Change

The existing CI pytest command now adds:

```text
-n auto --dist=loadfile
```

`loadfile` keeps every module's tests together on one worker.  pytest-cov's
documented xdist integration combines worker coverage before applying the
existing `--cov-fail-under=100` gate.  The marker expression, source scope,
coverage report, and threshold are unchanged.

## Behavioral verification

The exact proposed pytest command was run locally with Python 3.14.3 and the
locked environment:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
NUMEXPR_MAX_THREADS=1 PYTHONPATH=src UV_CACHE_DIR=.uv-cache \
uv run --no-sync --python 3.14 python -m pytest \
  -m "not integration_live" -q -n auto --dist=loadfile \
  --cov=src --cov-report=term-missing --cov-fail-under=100
```

Result: `2101 passed` in 38.28 test seconds / 40.84 wall-clock seconds;
5,545 source statements measured; total coverage 100.00%; exit status 0.

The canonical reliability workflow also passed all six stages on the changed
tree: directive parity, silent-exception gate, incomplete-implementation gate,
ruff, mypy, and the full serial pytest/coverage run (`2101 passed`, 2
deselected, 100%).  The adversarial verifier passed all 46 negative controls.
Because the first canonical run necessarily preceded the commit, its freshness
record was dirty; it must be rerun after commit before a `VERIFIED` claim.

## Scope and remaining work

This is a verification-infrastructure repair only.  It does not close Phase 2
ranking calibration and does not unblock Phase 3 packaging by itself.  A fresh
GitHub-hosted CI result is required after the change is pushed.
