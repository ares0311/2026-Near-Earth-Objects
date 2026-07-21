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

The first diagnostic changed the CI pytest command to add:

```text
-n auto --dist=loadfile
```

`loadfile` keeps every module's tests together on one worker.  pytest-cov's
documented xdist integration combines worker coverage before applying the
existing `--cov-fail-under=100` gate.  The marker expression, source scope,
coverage report, and threshold are unchanged.

That hosted run (`29852308200`, job `88707966513`) reached 99% in 6 minutes 24
seconds, then printed nothing for 7 minutes 53 seconds before cancellation.
Four Python worker processes were still alive.  Therefore xdist removed the
general serial bottleneck but exposed a final Linux-only hang.  The dots-only
console could not name the unfinished test.

The follow-up diagnostic replaces quiet output with `-vv` and adds
`--timeout=120 --timeout-method=thread`.  Every running test is now named in
the console; a worker that stops for two minutes dumps its thread stacks and
exits nonzero instead of remaining silent until the job-wide timeout.  The
timeout is diagnostic and fail-loud behavior, not a skipped test or relaxed
gate.

## Behavioral verification

The exact proposed pytest command was run locally with Python 3.14.3 and the
locked environment:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
NUMEXPR_MAX_THREADS=1 PYTHONPATH=src UV_CACHE_DIR=.uv-cache \
uv run --no-sync --python 3.14 python -m pytest \
  -m "not integration_live" -vv -n auto --dist=loadfile \
  --timeout=120 --timeout-method=thread \
  --cov=src --cov-report=term-missing --cov-fail-under=100
```

Result: `2101 passed` in 38.28 test seconds / 40.84 wall-clock seconds;
5,545 source statements measured; total coverage 100.00%; exit status 0.

The final verbose/timeout form was also executed locally: `2101 passed` in
32.68 test seconds, 100.00% coverage, exit status 0.  Its console named each
scheduled/running test and reported the configured 120-second thread timeout.

The canonical reliability workflow also passed all six stages on the changed
tree: directive parity, silent-exception gate, incomplete-implementation gate,
ruff, mypy, and the full serial pytest/coverage run (`2101 passed`, 2
deselected, 100%).  The adversarial verifier passed all 46 negative controls.
Because the first canonical run necessarily preceded the commit, its freshness
record was dirty; it must be rerun after commit before a `VERIFIED` claim.

## Scope and remaining work

This is a verification-infrastructure repair only.  It does not close Phase 2
ranking calibration and does not unblock Phase 3 packaging by itself.  The
next GitHub-hosted run must either complete or name/dump the exact hanging test;
partial output is not accepted as success.
