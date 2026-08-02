#!/usr/bin/env bash
#
# Run the Phase 2 PTY acceptance gate outside the sandbox.
#
# Why this file exists at exactly this path
# -----------------------------------------
# ~/.claude/settings.json lists "bash scripts/run_pty_gate.sh*" under
# sandbox.excludedCommands, so invoking the gate through this wrapper is the
# supported way to obtain a real terminal device. Run inside the sandbox,
# pty.openpty() fails with "Operation not permitted" and the gate correctly
# reports NOT_EXECUTED rather than degrading to a pipe -- a pipe cannot
# demonstrate that "/" opens the command palette before Enter is pressed.
#
# The sibling Hunter repositories use this same path and wrapper convention, so
# all three projects are driven identically. Keep the filename stable: changing
# it silently removes the sandbox exclusion and the gate stops being runnable.
#
# Usage
# -----
#   bash scripts/run_pty_gate.sh            # full gate, one run
#   bash scripts/run_pty_gate.sh --probe    # narrow: does "/" open the palette
#   bash scripts/run_pty_gate.sh --runs 3   # Phase 6 requires three clean runs
#
# Exit status is the gate's own: 0 only when every assertion passed. NOT_EXECUTED
# is reported distinctly and still exits nonzero, because a gate that did not run
# is not a gate that passed.

set -euo pipefail

# Resolve the repository root from this script's own location, so the gate can be
# launched from any working directory without depending on the caller's cwd.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# The gate writes its machine-readable report here.
mkdir -p Logs/prod_closure

# Use the repository-local uv cache, matching every other command in this project.
export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"

# The gate must never be handed a PYTHONPATH: it verifies an *installed* console
# script, and source-tree assistance would invalidate that.
export PYTHONPATH=""

# caffeinate keeps macOS awake -- a full three-run gate opens dozens of terminal
# sessions and can outlast the display sleep timer.
exec caffeinate -i uv run --no-sync --python 3.14 python \
    Skills/hunter_pty_gate.py \
    --json Logs/prod_closure/pty_gate.json \
    "$@"
