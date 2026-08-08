# P0 launch-surface closure — NEO-FIELD-01

**Date (UTC):** 2026-07-31
**Repository:** NEOHunter (`2026 Near Earth Objects`)
**Commit under test:** `000e0c2421c8ca15807fe46d3426bc02654573b5`
**Contract:** `HUNTER-PROD-2026-07-30.3`
**Requirements addressed:** LAUNCH-01, LAUNCH-02, LAUNCH-03, LAUNCH-04, CLAIM-01, EVAL-01

---

## 1. Reproduction of the field failure

The documented operator workflow was run verbatim against the operator's
`.venv` before any repair:

```
.venv/bin/NEO-Hunter --help
```

Observed:

```
Traceback (most recent call last):
  File ".../.venv/bin/NEO-Hunter", line 12, in <module>
    sys.exit(neo_hunter())
  File ".../src/hunter_commands.py", line 38, in neo_hunter
    getattr(import_module("Skills.hunter_shell"), "main"),
  ...
ModuleNotFoundError: No module named 'Skills'
```

This matches blocker `NEO-FIELD-01` exactly.

## 2. Root cause

**One sentence:** the operator's `.venv` held a *stale editable install of
version 0.91.0*, whose static `__editable__.neo_detection-0.91.0.pth` added only
`src/` to `sys.path`, so the `Skills` package — which lives outside `src/` — was
never importable.

Supporting observations:

| Observation | Value |
|---|---|
| Installed distribution in `.venv` before repair | `neo_detection 0.91.0` |
| `pyproject.toml` version in the working tree | `0.91.1` |
| Contents of the stale `.pth` | a single line pointing at `<repo>/src` |
| Commit that added the `Skills` `package-dir` mapping | `fd989750` (version `0.91.1`) |

So the corrective packaging change had already landed in `pyproject.toml`, but
`uv sync` had not been re-run against it. A fresh editable install of the
*current* tree emits the finder form instead of the static form, and its
`MAPPING` does include `'Skills': '<repo>/Skills'`.

## 3. Test escape

`Skills/verify_hunter_distribution.py` verified **only the wheel surface**.

The built wheel always carried `Skills/` as real package content (107 modules
confirmed present in `neo_detection-0.91.1-py3-none-any.whl`), so the wheel
surface could never observe this defect. The failure lived exclusively on the
*editable / `uv sync`* surface — which is the surface the documented operator
workflow actually uses, and which had no verification at all.

This is precisely the class of escape contract rule LAUNCH-02 names: *"A pass on
one surface does not prove another."*

## 4. Repair

1. No change to `pyproject.toml` was required — commit `fd989750` had already
   added the corrective mapping.
2. The operator environment was repaired with the documented command:
   `uv sync --all-extras --all-groups --python 3.14`
   (uninstalled `0.91.0`, installed `0.91.1`, exit status 0).
3. `Skills/verify_hunter_distribution.py` gained a `--surface {wheel,editable,both}`
   flag and two new verification tiers:
   - `verify_editable_surface()` — creates a throwaway venv, installs the project
     editable with `--no-deps`, and proves `Skills`, `Skills.hunter_shell`,
     `hunter_commands`, and `hunter_config` import with `PYTHONPATH` emptied,
     from a working directory that is **not** the repository root; then launches
     both `NEO-Hunter` and `NEOHunter` console scripts as real subprocesses.
   - `verify_dependent_imports()` — proves `Skills.hunter_cli`, `hunter_state`,
     and `known_object_exclusion` import in the synchronized environment.
4. `tests/test_hunter_launch_surfaces.py` was added as the standing regression
   control.

## 5. Verification

### 5.1 Operator workflow after repair

```
uv sync --all-extras --all-groups --python 3.14
bash Logs/prod_closure/launch_probe.sh "$PWD/.venv" NEO-Hunter "$PWD" \
     "operator-venv upgrade-in-place / repo-root"
```

Environment captured (LAUNCH-03):

| Field | Value |
|---|---|
| commit SHA | `000e0c2421c8ca15807fe46d3426bc02654573b5` |
| Python | 3.14.3 |
| package manager | uv 0.11.3 |
| virtual environment | `<repo>/.venv` |
| resolved executable | `<repo>/.venv/bin/NEO-Hunter` |
| installed version | 0.91.1 |
| installation mode | editable (uv sync managed) |
| working directory | repository root |
| `PYTHONPATH` | unset |

Results:

| Probe | Exit status | Observation |
|---|---|---|
| `--command "/Help"` | 0 | full slash-command reference rendered |
| `--command "/Exit"` | 0 | `NEOHunter session closed.` |
| `--command "/New-Search twenty"` | 2 | `ERROR: /New-Search requires an integer target count N` — actionable, no traceback |

### 5.2 Editable-surface verification

```
uv run --no-sync --python 3.14 python Skills/verify_hunter_distribution.py --surface editable
```

```
[hunter-distribution] PASS -- editable surface: 4 standard-library-reachable modules importable without PYTHONPATH
[hunter-distribution] Skills resolved from: <repo>/Skills/__init__.py
[hunter-distribution] PASS -- synced environment: 3 dependency-bearing production modules importable
EXIT=0
```

### 5.3 Regression control, including an adversarial arm

```
PYTHONPATH=src uv run --no-sync --python 3.14 python -m pytest \
    tests/test_hunter_launch_surfaces.py -q --no-cov
```

```
......                                                                   [100%]
6 passed in 7.05s
```

`test_probe_detects_missing_package_mapping` is parametrized over
`map_extra_package ∈ {True, False}`. It builds a synthetic project with the same
two-root shape as this repository (`src/` plus a second package directory),
installs it editable, and asserts:

- **with** the mapping — the package imports and the probe exits 0;
- **without** the mapping — the probe exits nonzero with
  `No module named 'Extra'`.

This proves the check can actually detect the defect it claims to detect, rather
than merely passing.

## 6. Scope of this evidence

This record closes the **launch** portion of `NEO-FIELD-01` only. It does not
assert that any other contract requirement is met. In particular it makes no
claim about `NEO-FIELD-02` (coverage denominator), `NEO-FIELD-03` (skipped-stage
labeling), the CLI/UX conformance gates (`CLI-01`–`CLI-03`), real-data
acceptance (`E2E-01`–`E2E-04`), or the repository-native PROD gate (`PROD-01`),
all of which remain open in `configs/HUNTER_PROD_STATE.json`.

## 7. Governing-artifact defects found and handled

| Artifact | Defect | Handling |
|---|---|---|
| `configs/HUNTER_PROD_STATE.json` | RTF document with a `.json` extension; unparseable as JSON. Internal `artifact` field read `ARTIFACT 3 — docs/HUNTER_PROD_STATE.json`, which is not this file's path. | Converted losslessly to valid JSON at the canonical path, every field carried over verbatim; `artifact` corrected to `configs/HUNTER_PROD_STATE.json`. Original bytes preserved. |
| `docs/HUNTER_PROD_CONTRACT.md` | RTF document with a `.md` extension. | Converted to real Markdown at operator direction. All 14 sections and 39 requirement IDs verified present. Original bytes preserved. |
| `docs/CLI_UX_SPEC.md` | RTF document with a `.md` extension. | Converted to real Markdown at operator direction. All 14 sections and 22 UX IDs verified present. Original bytes preserved. |
| `docs/README_SPEC.md` | Contract and launch prompt both describe it as *staged and uncommitted*. | Verified reality: committed and unmodified — `git status`, `git diff`, and `git diff --cached` all report no changes. Preserved untouched; discrepancy recorded rather than silently reconciled. |

Original bytes for all three converted artifacts are retained under
`configs/originals/`.
