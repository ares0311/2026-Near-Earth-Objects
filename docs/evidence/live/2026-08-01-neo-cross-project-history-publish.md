# NEOHunter cross-project history publish (deliverable A) — 2026-08-01

Deliverable A of the three-repo Hunter search-history exchange: NEOHunter now
publishes the search history it owns so TechnoHunter and EXOHunter can answer
"has this target already been searched by NEOHunter?" from evidence rather than
assumption.

Scope of this session: **deliverable A (built from scratch)**, plus one blocking
defect found in the existing consumer while verifying A. Deliverable C (New-mode
eligibility gated on decision-grade history from all three projects) is
**not wired in this repo** — see "What is not done" below.

---

## What was built

### A. Publish command (new)

`Skills/hunter_cli.py export-cross-project-history` →
`data_selection/hunter_prior_search_history_v1.json`

Implemented in `src/hunter_cross_project.py`:

| Function | Purpose |
|---|---|
| `build_own_history_export()` | Builds the `schema_version=1` payload from the committed target priority queue |
| `write_own_history_export()` | Writes it, refusing any path outside this repository (WS-01) |

**Source of truth**: `data_selection/target_priority_queue.csv`. This is the
correct source, not `hunter_state.sqlite`: per `CLAUDE.md`, target search history
lives in the queue, while the durable `search_runs` tables record individual
executions. The committed `hunter_state.sqlite` is in fact empty (all tables
0 rows), so exporting from it would have published an empty, useless history.

**Status mapping.** The queue's native statuses are mapped onto the shared
cross-project vocabulary the siblings already validate against, with the native
value preserved verbatim as `native_status`:

| Native queue status | Shared status | Consumer effect |
|---|---|---|
| `null_result` | `no_signal` | COMPLETED → counts as real prior search |
| `insufficient_coverage` | `no_data` | INVALID → correctly does **not** count |
| `insufficient_retained_coverage` | `no_data` | INVALID → correctly does **not** count |
| `not_searched` | *(excluded)* | planning intent is not history |

Mapping thin-coverage rows to `no_data` is deliberate and is the fail-closed
direction: no search actually ran on those fields, so counting them would let a
sibling skip genuinely unsearched sky. An unmapped status **raises** rather than
being published unlabelled.

`searched_at` is recovered from each row's own committed provenance (its dated
`docs/evidence/live/YYYY-MM-DD-*.md` citation or a date in its notes) because the
queue has no timestamp column. A row recording a search but naming no date
**raises** rather than being stamped with `now()`, which would make stale history
look freshly verified.

### Blocking defect found and fixed in the existing consumer

`hunter_cross_project.load_cross_project_history()` raised
`"cross-project history contains no interoperable minor-planet identities"`
whenever an export contained no target it could normalize.

**Root cause**: the contract conflated *trustworthiness* ("is this export
verifiable?") with *domain overlap* ("can I match its targets?"). NEOHunter
searches sky fields; both siblings search stars (TIC/HIP/KIC). The domains are
structurally disjoint, so neither side can **ever** normalize the other's
identities.

**Consequence, measured before the fix**: NEO's consumer raised on both
siblings' real, valid, hash-verified exports. A New-search gate that failed
closed on validity would therefore have deadlocked New searches **permanently**,
not transiently. The symmetric failure exists in EXOHunter (see below).

**Fix**: a structurally sound export whose entries name nothing in this
project's domain now loads as `valid` with zero contributed identities, and
reports `domain_disjoint`, `raw_entry_count`, and `interoperable_entry_count` so
a caller can disclose which case it saw. Genuine failures still raise: absent,
malformed, wrong schema version, unhashable/mismatched source, or a source with
no entries at all.

---

## Verification (exact commands and observable results)

Tested commit: working tree at `000e0c24` + the changes described here
(`src/hunter_cross_project.py`, `Skills/hunter_cli.py`,
`tests/test_hunter_cross_project_export.py`, and the published export).

### 1. Publish; file exists and states schema_version 1

```bash
UV_CACHE_DIR=.uv-cache PYTHONPATH=src uv run --no-sync --python 3.14 \
    python Skills/hunter_cli.py export-cross-project-history
```

```
Published cross-project history export -> .../data_selection/hunter_prior_search_history_v1.json
  schema_version   : 1
  entries          : 13
  unique targets   : 13
  source sha256    : 382539a66aec9d80f442a4cc2e767d56ac37ffe1b3eda64c11125a8049050b84
```

13 entries from the 13 real searched rows in the queue (11 `null_result`,
1 `insufficient_coverage`, 1 `insufficient_retained_coverage`); the 47
`not_searched` rows were correctly excluded.

### 2. A sibling's REAL loader accepts it as decision-grade

Run via a gitignored harness (`Logs/verify_interop.py`) that imports
TechnoHunter's actual module. This is a test harness only — no production module
in this repo imports anything from a sibling (WS-03).

```
sibling_history_export_path('neo_hunter') -> .../2026 Near Earth Objects/data_selection/hunter_prior_search_history_v1.json
  exists: True
  schema_version: 1
  source_project : 2026 Near Earth Objects
  searched_by    : NEO-Hunter
  validity_state : valid
  decision-grade : True
  entries        : 13
  entry validity : {'valid': 11, 'invalid': 2}

RESULT: TechnoHunter accepts NEO export as decision-grade = True
```

`validity_state: valid` means TechnoHunter re-hashed this repo's real
`data_selection/target_priority_queue.csv` and the digest matched. The 2
`invalid` entries are exactly the two thin-coverage rows — correctly excluded
from counting as prior search.

### 3. NEO's consumer reads both siblings' real exports

Before the fix (`Logs/verify_neo_consumes_siblings.py`):

```
=== techno_hunter ===  NEO loader RAISED ValueError: cross-project history contains no interoperable minor-planet identities
=== exo_hunter ===     NEO loader RAISED ValueError: cross-project history contains no interoperable minor-planet identities
```

After the fix:

```
=== techno_hunter ===  validity=valid entries=0 verified=1/1
=== exo_hunter ===     validity=valid entries=0 verified=7/7
```

`verified=1/1` and `7/7` mean NEO re-hashed the siblings' real source artifacts
and every digest matched.

### 4. No file was written into any sibling (WS-01)

Both siblings carry pre-existing uncommitted work (37 and 21 entries) that is the
operator's, not this session's. Distinguishing evidence is modification time:

```
MY EARLIEST WRITE  : 2026-08-01T23:19:04 UTC
TECHNO NEWEST TOUCH: 2026-08-01T22:30:07 UTC   (49 min BEFORE my first write)
EXO  NEWEST TOUCH  : 2026-08-01T17:32:08 UTC
```

No sibling file was modified during this session's write window. Every write this
session made is inside the NEO checkout. Inspection used
`git --no-optional-locks status` so the check itself could not write a sibling's
index.

### 5. Tests, lint, types

```bash
uv run --python 3.14 ruff check src/hunter_cross_project.py Skills/hunter_cli.py \
    tests/test_hunter_cross_project_export.py        # All checks passed!
uv run --python 3.14 python -m mypy src              # Success: no issues found in 23 source files
PYTHONPATH=src uv run --python 3.14 python -m pytest tests/ -q -n 6 --dist=loadfile
```

```
2494 passed, 9 warnings in 35.52s
EXIT=0
```

Exit code captured explicitly into a log file per this project's standing rule
about unreliable background/wrapper completion labels.

16 new regression tests in `tests/test_hunter_cross_project_export.py` cover:
absent queue, no searched rows, unmapped status, missing date, missing position,
WS-01 write refusal, status mapping, `not_searched` exclusion, publish→consume
round trip, domain-disjoint export loading as valid, empty-source still fatal,
wrong schema version, malformed JSON, and source hash mismatch.

---

## What is NOT done (deliberately, and why)

- **Deliverable C — New-mode eligibility gated on all three projects — is not
  wired in this repo.** `Skills/hunter_cli.py:discover_new_targets` still
  *discloses* `cross_project_history_validity` (and a `cross_project_limitation`
  string) without refusing the search. Wiring a hard refusal changes whether the
  operator's primary `create-new-search --mode new` workflow runs at all, so it
  is an explicit operator decision, not a side effect of publishing an export.
  The defect fix above is a prerequisite: before it, such a gate would have
  deadlocked New searches permanently.
- **Deliverable B is partial.** The consumer reads a repo-local copied manifest
  (`data_selection/cross_project_imports/`). It does not yet do repo-relative
  live sibling discovery equivalent to `sibling_history_export_path()`. The
  harness in `Logs/` proves that discovery works from this checkout, but it is
  not production code here.

## Cross-repo finding to hand to the other repos

**EXOHunter has the same defect this session fixed in NEO**, and it is currently
blocking:

```
exo_toolkit.hunter_cross_project.load_cross_project_history(<NEO export>)
  -> ValueError: cross-project history contains no interoperable stellar identities
```

If EXOHunter's New-mode gate fails closed on that loader's result, it will refuse
every New search forever once NEO's export is present, because NEO's sky-field
targets can never normalize into EXO's TIC/HIP/KIC space. TechnoHunter's loader
(`load_cross_project_history_export`) does **not** have this defect — it requires
non-empty entries but does not require normalizable identities.

## What this does not claim

No detection, discovery, external validation, or submission authority. The
export is a local scheduling aid between independently sandboxed projects. NEO's
published entries are sky fields, not catalogued minor planets; a sibling
matching on object identity will correctly find zero overlap, which is honest
disjointness rather than missing data.
