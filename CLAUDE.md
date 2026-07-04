# CLAUDE.md — NEO Detection & Ranking Project

This file is read automatically by Claude Code at session start.
It contains the facts a coding agent needs to work productively without re-reading every document.

---

## MANDATORY SESSION-START PROTOCOL

**At the start of every session, before planning or executing any steps, you must:**
0. Run `git pull origin main` — the local repo resets to a checkpoint at each session start; pull ensures all files reflect the latest committed state before reading them.
1. Call `Read` on `CLAUDE.md` — do not rely on memory or prior context. (This file; re-read to reactivate all standing rules.)
2. Call `Read` on `AGENTS.md` — do not rely on memory or prior context.
3. Call `Read` on `docs/PRODUCTION_READINESS.md` — do not rely on memory or prior context.
4. Call `Read` on `docs/SYSTEM_PROFILE.md` — this committed file governs local
   optimization defaults for project code, tests, notebooks, and operator
   commands.
5. Call `Read` on `docs/near_earth_objects_research_brief.md` — the canonical
   primer on ranked space assets (WISE/NEOWISE, NEO Surveyor, Gaia), frontier
   AI methods (THOR, HelioLinC3D, CNN streak detection), submission best
   practices, and key literature. Must be re-read each session to keep agents
   current on the discovery-paper data strategy.
6. Call `Read` on `docs/neo_discovery_agent_brief.md` — the authoritative
   workflow brief for candidate language, historical replay, source
   verification, no future-catalog leakage, pretrained-model audits, and
   auditable candidate-ranker design.

These steps are non-negotiable. No planning or code changes may happen before all seven are complete.

---

## PRIMARY DIRECTIVE

**You may ONLY work on tasks that advance this project to PRODUCTION.**

Before proposing or executing any task, apply this gate:

> *Does this task close or directly unblock a named T1 or T2 gap from `docs/PRODUCTION_READINESS.md`?*

If the answer is NO, do not do it. In particular:
- **Never add new public helper APIs** unless they directly unblock a named gap. The v0.77–v0.87 API accumulation cycle (110 helpers, zero production impact) must never recur.
- **Never add new Skills scripts** that are single-function wrappers. Only add a Skill if it is operationally necessary for a named gap.
- **Never add new documentation files** that duplicate existing content.
- **Never propose log modules, schemas, or scaffolding** that do not directly unblock a named T1 or T2 gap.
- **Never repeat work listed under "What Is Complete"** in `docs/PRODUCTION_READINESS.md`.

If the highest-priority T1 gap cannot be resolved because a human blocker is unresolved, **state that explicitly** and limit scope to T2 gaps or documentation sync.

---

## Standing Rules

- Before switching branches or editing tracked files, check for
  `Logs/tier3_pilot.active.json`. If present, do not alter the shared checkout
  until the operator run exits and removes the marker.

- **Python runtime is 3.14.3 — always use `uv run`**: The project venv is
  Python 3.14.3, managed by uv from `uv.lock`. Never invoke bare `python`,
  `pytest`, `mypy`, or `ruff` directly — always prefix with `uv run` so the
  correct interpreter and locked dependencies are used. CI enforces the same
  via `astral-sh/setup-uv@v5` with `python-version: "3.14"`.
  Example: `PYTHONPATH=src uv run --python 3.14 python -m pytest`
- **Local system profile governs optimization defaults**: `docs/SYSTEM_PROFILE.md`
  is a committed directive for local resource sizing. Optimize project code,
  tests, notebooks, and operator commands for that profile unless portability or
  a task requirement says otherwise. Do not hardcode machine-specific assumptions
  into scientific logic; expose performance-sensitive behavior through
  configuration or documented runtime defaults.
- **Use local compute deliberately**: When implementing or running AI training,
  first target the local Apple GPU/Metal acceleration described in
  `docs/SYSTEM_PROFILE.md` (for example PyTorch MPS) when the framework supports
  it, and report any CPU fallback explicitly. Other CPU-heavy local code should
  use bounded multithreading or multiprocessing by default, sized from
  `docs/SYSTEM_PROFILE.md`, while avoiding native-library oversubscription and
  keeping live external-service concurrency conservative. Performance-sensitive
  worker counts, device selection, batch sizes, and thread limits must be
  configurable or documented runtime defaults, not hidden machine-specific
  constants.
- **Discovery paper goal — NOT citizen science**: Jerome W. Lindsey III is the
  project operator and reviewer. The goal is a **defensible discovery paper**:
  find new NEOs in unreviewed archival data, submit candidates to MPC, obtain
  a provisional designation via independent NEOCP confirmation, and publish.
  We NEVER claim discovery — only "candidates consistent with NEO orbits."
  Two review stages gate every submission: (1) automated adversarial review
  (`Skills/adversarial_review.py` — 13 challenges, tries to REJECT each
  candidate), then (2) operator review. Only SURVIVE/BORDERLINE candidates
  proceed to MPC submission. See `docs/MISSION.md` (authoritative) and
  `docs/neo_discovery_agent_brief.md` (authoritative workflow brief) plus
  `docs/MPC_SUBMISSION_POLICY.md` for the full submission policy.
  Do NOT reinstate a "blocked until expert review" guardrail — MPC/NEOCP/Scout
  IS the expert review system. Do NOT frame this as citizen science.
- **Repository artifact policy supports `git add .`**: The standard operator
  cadence may use `git add .`, so `.gitignore` must protect local/generated
  outputs by default. Treat `Logs/**` as local operational output and never
  commit it except `Logs/.gitkeep` and `Logs/reports/.gitkeep`. When run
  evidence must be visible to future agents, promote a compact, sanitized
  summary into `docs/evidence/` or `data/evidence/` instead of committing raw
  `Logs/` files. Production model artifacts in `models/` must be explicitly
  allowlisted by filename; do not use broad `!models/*.pt` or `!models/*.json`
  rules. Before committing, inspect `git status --short`, the staged filename
  list, and ignore behavior for generated outputs; if `git add .` would capture
  local run debris, fix `.gitignore` and untrack it before committing.

- **Always comment all code**: Every function, class, script, shell command, and non-trivial code block must include comments explaining what it does and why. This applies to all Python source files, all Skills scripts, all shell commands given to the operator, and all inline code snippets in documentation. No exceptions. This rule overrides any default behavior that would omit comments.
- **caffeinate all long-running Mac commands**: Any operator command expected to run longer than ~30 seconds must be prefixed with `caffeinate -i` to prevent macOS from sleeping mid-run. This applies to all downloads, training runs, and pipeline executions. Example: `caffeinate -i uv run --python 3.14 python Skills/download_ztf_training_alerts.py ...`
- **All long-running scripts must print live progress with ETA**: Any script or pipeline stage that runs for more than a few seconds MUST emit per-item or per-batch progress lines to **stdout**, including: items processed / total, current status, running accepted counts, elapsed time, and estimated time remaining (ETA). Silent long-running processes are unacceptable — the operator must always be able to see that the process is alive and estimate when it will finish. This rule applies to all Skills scripts that loop over network queries, training epochs, or large data processing. Use `print(..., flush=True)` (stdout, NOT stderr — stderr is not reliably interleaved with stdout in the operator's terminal). ETA format: `elapsed {m}m{s:02d}s  ETA {m}m{s:02d}s`. ETA must be computed from a measurable quantity (bytes read, items processed, batches done) — elapsed-only heartbeats are not acceptable as a substitute for ETA.

- **All long-running pipeline scripts must implement checkpoint/resume**: Any Skills script that makes network calls or processes items in a loop MUST survive a network drop, machine sleep, or process kill without losing work. The implementation rules are:
  1. **Derive the run directory from the search parameters** (not a timestamp) so that re-running the exact same command finds the existing checkpoint: `Logs/pipeline_runs/<param_key>/checkpoint.json`. The key must be a stable hash of all parameters that define the work (sky position, time window, surveys, etc.).
  2. **Write a checkpoint after every expensive stage** — at minimum after the network fetch stage and after each item in a per-item processing loop.
  3. **On startup, load the checkpoint and skip completed stages** — print a clear `[resume]` line for each skipped stage so the operator knows the script is continuing, not starting over.
  4. **Wrap all network fetch calls in a retry loop** with exponential backoff: 2 s, 4 s, 8 s, 16 s, 32 s (max 5 attempts). Catch `(ConnectionError, TimeoutError, OSError)`. Print the error and retry count on each failure. Raise after the final attempt.
  5. **The operator must never need to edit the command** to resume — re-running the identical command is the only required action after a sleep/wake or network interruption.
  This is the System Directive standard. Scripts that do not meet it are incomplete.
- **Always evaluate sharding/multiprocessing/parallelism for any operator command expected to take longer than 3 minutes**:
  Before handing off any operator command, or building the Skills script
  behind it, if the total expected run time is more than ~3 minutes you
  MUST evaluate whether the work is parallelizable — not just default to a
  single sequential run. Independent items with no shared mutable state
  (multiple sky positions, multiple nights, multiple designations,
  multiple report rows, multiple files) are candidates for:
  1. **Sharding across concurrent terminal tabs** (per the manifest
     standing rule immediately below) when the work is a series of
     network-bound calls to the same external service.
  2. **Bounded local multiprocessing/multithreading within one process**
     (sized per `docs/SYSTEM_PROFILE.md`'s local resource-sizing rule)
     when the work is CPU-bound rather than network-bound.
  3. **Naturally-independent concurrent invocations with no code changes**
     when a tool already checkpoints per-item with no shared state (e.g.
     each night/position writes its own file) — in that case, say so
     explicitly and just tell the operator to run the existing commands in
     separate tabs, rather than building new sharding scaffolding that
     isn't needed.
  State explicitly, every time, whether you evaluated parallelism and why
  you did or didn't apply it — never silently hand off a long sequential
  command without considering the alternative first. If it is ambiguous
  whether parallelizing is worth the added complexity (e.g. rate-limit
  risk to a shared external API, unclear item independence, a short
  enough remaining runtime that the overhead isn't worth it), **ask the
  operator** rather than deciding unilaterally.
- **Progressively probe toward the safe concurrency ceiling for repeated batches against the same external service — don't stay pinned to the conservative starting point forever**:
  `docs/SYSTEM_PROFILE.md`'s "usually 4 to 6 workers" for I/O-heavy/external-service
  work is an explicitly conservative **first-batch** starting point, not a
  permanent ceiling — it mirrors the same doc's CPU-worker guidance
  ("increase only after measuring"). The implementation rules are:
  1. **After a batch completes with zero errors, zero rate-limit/429/503
     responses, and no unusual per-request latency degradation**, the next
     batch against that *same* external service may step concurrency up by
     a bounded increment (roughly +2, or up to ~1.5x) rather than repeating
     the same conservative number indefinitely.
  2. **Step back down immediately** to the last known-clean level the
     moment any batch shows errors, rate-limiting, timeouts, or degraded
     latency — never keep pushing past a bad signal, and never retry a
     failed higher-concurrency batch at the same or higher level.
  3. **A documented rate limit from the service itself is authoritative**
     and must never be exceeded regardless of how clean prior batches
     looked — verify the limit via the service's own docs (never guessed)
     before treating any number above it as safe.
  4. **Record the empirically-found safe level per service** (not a
     blanket default) in `docs/SYSTEM_PROFILE.md` or a dated
     `docs/evidence/` file, so future sessions start from established
     ground truth instead of re-discovering it from the conservative
     default every time.
  5. This does not override the "ask when ambiguous" rule above — if
     escalating risks overwhelming a small/community-run resource (as
     opposed to a large commercial CDN sized for bulk concurrent access),
     confirm with the operator before continuing to increase.
- **Parallel/sharded Skills scripts must write a live-updating shared manifest, not just an isolated per-process report**:
  Any Skills script that supports splitting its work across multiple
  operator-launched concurrent processes (e.g. `--shard-index`/`--shard-count`
  for parallel terminal tabs) must, per the operator's explicit direction
  ("like when a pull request merges"), have every process append its
  completion summary to one shared manifest file the moment it finishes —
  not only write its own isolated report file. The implementation rules are:
  1. **Append, don't overwrite.** Use a shared append-only file (e.g.
     `manifest.jsonl`, one JSON line per completed process/shard) so
     partial progress is visible before every process finishes.
  2. **Lock the append.** Wrap each write in a file lock (e.g. `fcntl.flock`
     on POSIX) so two processes finishing near-simultaneously can never
     corrupt or interleave each other's entries.
  3. **Provide a `--status` check that never fails closed.** It must be
     safe to run at any time, including mid-run with some shards still
     outstanding, and must report which shards have/haven't reported in
     plus a running combined result — never raise just because the run is
     incomplete.
  4. **Provide a `--merge`/finalize check that does fail closed.** Once the
     operator believes all shards are done, a separate command combines
     every entry into one final result and must raise if any expected
     shard has not reported in, rather than silently treating partial
     results as complete.
  5. **Re-running the same shard must replace, not duplicate, its entry**
     (key manifest entries by shard index, not by append order).
  This turns a batch of parallel terminal tabs into one thing the operator
  can check on and paste a single compact summary from, instead of
  collecting and pasting every tab's full transcript.
- **The shared manifest must live in a committed path and be pushed automatically — git is the relay, not the operator's filesystem**:
  A local manifest file (per the rule above) alone does not solve the
  "avoid pasting console output" problem, because the coding agent has no
  access to the operator's local filesystem or terminal — only to what is
  pushed to the shared GitHub remote. Per the operator's explicit
  correction ("You don't need access to my Mac... the whole point is for
  you to know automatically"), any Skills script with a shared manifest
  must:
  1. **Write the manifest to a committed path**, not the gitignored
     `Logs/**` tree — `Logs/reports/` is already allowlisted in
     `.gitignore` for exactly this. Keep any large/sensitive per-item
     payload (e.g. full observation lists) in the separate gitignored
     checkpoint as before; the manifest itself should be a compact summary
     only.
  2. **Have the script itself commit and push the manifest** at the end of
     every invocation (`git add <manifest> && git commit && git push`,
     using the manifest's own file lock to stay safe under concurrent
     tabs), so the coding agent can read real results via a plain
     `git pull` with no operator git commands and no pasted console output.
     Retry push with `git pull --rebase` on conflict (another concurrent
     tab pushing first); never raise on final failure — the underlying
     work is already safe on local disk, so print a manual fallback
     command instead of crashing the run.
  3. **Scope the auto-push narrowly**: only ever add/commit the one
     manifest file, never source code or other paths — this is a
     deliberate, explicit exception to the normal PR-review workflow
     used for all code changes, justified only because the payload is an
     inert data/evidence file, not code.
  4. **Provide a `--sync` backfill** for manifest entries that predate
     this behavior (e.g. checkpoints from a run started before the
     feature existed) — read local checkpoints already on disk and
     manifest+push them without re-doing the underlying work.
- **Persist operator command results immediately — no re-run loops**:
  Every time the operator runs a command at your direction and pastes the output,
  you MUST, in the same turn, commit a durable record before replying with the
  next step. Never proceed to the next step without first writing the result to a
  committed file. Failure to do this creates a death loop: conversation context
  compacts → result is lost → you ask the operator to run the same command again.

  Rules:
  1. **Write the result first.** As soon as you receive operator terminal output,
     write a sanitized summary to `docs/evidence/<subsystem>/YYYY-MM-DD-<slug>.md`
     (or update the active evidence file for the current milestone).
  2. **Update the handoff state in `CLAUDE.md`.** Mark the completed step DONE
     and write the exact next command with a "NOT YET DONE" marker. The handoff
     block is the first thing future sessions read.
  3. **Update `docs/PRODUCTION_READINESS.md`.** Add or update the dated paragraph
     for the current T1/T2 gap so the state is visible without reading conversation
     history.
  4. **Commit and push before giving the next operator command.** Never queue up
     the next shell command without first pushing the durable record. The commit
     message must name the specific milestone (run ID, KPI result, object count).
  5. **At session start, read the committed evidence files before planning.**
     Never rely on conversation memory or summaries for run results. If a
     `docs/evidence/` file says a step is DONE, treat it as done — do not ask
     the operator to re-run it.

- **Diagnose root cause before writing any fix (symptom-loop prevention)**:
  Before writing code to fix a hang, missing output, wrong output, or performance problem, you MUST first state the root cause in one sentence from first principles. If you cannot state the root cause, do NOT write code — re-read the diagnostic output and reason about it until you can. Applying a workaround (e.g., a heartbeat, a retry, a timeout) without identifying the root cause is prohibited.

- **Physically impossible output is a diagnostic signal — stop and reason**:
  If operator output contains a value that is physically impossible (e.g., a 7.1 MB file read in 0.0 s; a network call completing faster than a round-trip), STOP. That value tells you the operation did NOT do what you assumed. Reason about what mechanism produces that value before writing any code. Example: "file read in 0.0 s" means the OS returned without reading bytes (mmap, cached descriptor, or placeholder) — the actual I/O will happen later, elsewhere.

- **Failed fix → re-diagnose, not re-patch**:
  If a fix lands (PR merged, operator re-runs) and the operator reports the same category of failure, the root cause was not correctly identified. Do NOT apply another layer of the same pattern (another heartbeat, another print, another retry). Re-diagnose from the original operator output as if no fix had been attempted. The second failure is proof the first diagnosis was wrong.

- **State predicted output before submitting a PR**:
  Before opening any PR that fixes a hang or missing output, write explicitly: (a) the root cause in one sentence, (b) what the operator's console WILL show after the fix, and (c) what it will show if the root cause was still wrong. If you cannot answer all three, re-diagnose before writing the PR.

- **Operator always runs from main — no exceptions**: The operator's Mac always runs code from the `main` branch. Never instruct the operator to `git checkout` a feature branch or `git pull origin <feature-branch>`. Feature branch code must not be given to the operator to run until it is merged to main.
- **Merge PR before giving operator commands**: Before giving the operator any command that depends on a code fix or new script, the PR containing that fix must be merged to `main` first. Wait for CI to pass, merge the PR, confirm the merge, then give the operator the command.
- **Always prepend `git pull origin main` to operator command sequences**: Every block of operator commands must begin with `git pull origin main` to ensure the operator has the latest merged code before running anything.
- **Close PRs promptly**: After CI passes, merge and close the PR immediately. Do not accumulate open PRs. One PR at a time; merge before opening the next.
- **Skills directory**: Any standalone `.py` utility script created to perform a task must be saved in `Skills/` at the project root.
- **No impact claims**: Never assert a probability of Earth impact from internally computed data alone. Always defer to MPC/CNEOS for authoritative hazard assessment.
- **Alert protocol is sacred**: The NASA/MPC alert pathway (see §Alert Protocol) must never be triggered on unconfirmed detections. Require independent confirmation first.
- **Dead code must be removed, not tested**: If a function or class has no reachable callers, delete it rather than adding a test.
- **Conservative by default**: When uncertain about classification, flag for human review. Never output "confirmed NEO" for internally detected objects.
- **Calibration promotion is KPI-based**: Production calibration is approved only
  when the quantitative gate in `docs/PRODUCTION_READINESS.md` passes on held-out
  real labeled data. Reliability diagrams are evidence artifacts, not a human
  approval gate. Any failed or missing KPI blocks promotion.

---

## Project

**Near-Earth Object Detection and Ranking Pipeline**
Automated pipeline for detecting, linking, classifying, and ranking Near-Earth Object (NEO) candidates from publicly available survey photometry, with MPC-compatible reporting and a NASA alert pathway for high-confidence hazard signals.

Repository: `<owner>/neo-detection` (to be created)
Active branch: `main`

---

## Scientific Context

Near-Earth Objects are small solar system bodies with perihelion distances $q < 1.3$ AU. They are divided into four dynamical classes:

| Class | Definition |
|---|---|
| Amor | $1.017 < q < 1.3$ AU |
| Apollo | $a > 1.0$ AU, $q < 1.017$ AU |
| Aten | $a < 1.0$ AU, $Q > 0.983$ AU |
| IEO (Atira) | $Q < 0.983$ AU |

Potentially Hazardous Asteroids (PHAs) are NEOs with absolute magnitude $H \leq 22$ (diameter $\gtrsim 140$ m) and Minimum Orbit Intersection Distance (MOID) $\leq 0.05$ AU. The pipeline must identify and flag PHA candidates.

The global NEO survey is dominated by:
- **ZTF** (Zwicky Transient Facility) — **primary discovery target as of 2026-07-02** via ZTF DR24 archival historical replay (bounded time window, time-aware known-object exclusion, retrospective validation against later MPC/JPL outcomes). Live ZTF alert-stream consumption remains prohibited (ZTF ZAPS already processes and submits from the live stream in real time) — the historical-replay archive path is the exception, not the live stream.
- **ATLAS** — **training-data source only** (ATLAS pipeline already processes and submits); 24–48 hr warning capability
- **Pan-STARRS** — deep survey; public catalog access
- **CSS** (Catalina Sky Survey) — MPC-feeding survey
- **WISE/NEOWISE** (archival) — **secondary/paused discovery target** as of 2026-07-02 (was primary through v0.90.10); infrared detections of 158,000+ minor planets; accessible via IRSA without credentials; code and Gate P1–P5 evidence preserved
- **NEO Surveyor** (launch ≥ 2027) — future dedicated IR discovery mission; not yet available
- **Rubin/LSST** (upcoming) — will discover 100,000+ NEOs; tracklet-less linking (HelioLinC3D) required

**Key discovery constraint (updated 2026-07-02)**: `docs/neo_discovery_agent_brief.md` supersedes the prior "UNREVIEWED archives only" framing. ZTF DR24 archival historical replay is now the primary discovery path; DECam/NOIRLab, WISE/NEOWISE, and TESS FFIs are secondary/paused. See `docs/MISSION.md §Operator Decision (2026-07-02)` (authoritative) and `docs/near_earth_objects_research_brief.md`/`docs/neo_discovery_agent_brief.md` for full details.

As of 2026, approximately 35,000 NEOs are known. Rubin/LSST is expected to discover 100,000+ more over its 10-year survey.

---

## Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

Each stage produces a typed, immutable result object. No shared mutable state.

### Module Build Order

| Module | Status | Tests | Description |
|---|---|---|---|
| `schemas.py` | complete | test_schemas.py | All pipeline data models (Pydantic, frozen) |
| `fetch.py` | complete | test_fetch.py | WISE/DECam/TESS discovery layer + ZTF/ATLAS/MPC (training) |
| `preprocess.py` | complete | test_preprocess.py | Difference image handling, source extraction |
| `detect.py` | complete | test_detect.py | Moving object detection; streak/trail identification |
| `link.py` | complete | test_link.py | Tracklet linking across nights |
| `classify.py` | complete | test_classify.py | ML real/bogus + NEO type classification |
| `orbit.py` | complete | test_orbit.py | Preliminary orbit fitting; MOID calculation |
| `score.py` | complete | test_score.py | Hazard ranking; PHA flag; novelty score |
| `alert.py` | complete | test_alert.py | MPC report formatting; NASA alert protocol |
| `calibration.py` | complete | test_calibration.py | Classifier calibration (Platt / isotonic PAVA) |

Build in the order listed. Each module depends on all prior modules.

---

## Data Sources

### Primary Survey Data

**ZTF (recommended primary source)**
- Public alert stream via IRSA (`ztfquery` Python package or direct API)
- 3-night cadence over the full northern sky; $g$, $r$, $i$ bands
- Difference-image alerts include cutouts (science, reference, difference) — ideal for CNN input
- Access: `pip install ztfquery`; IRSA account required (free)
- Key fields per alert: `ra`, `dec`, `jd`, `magpsf`, `sigmapsf`, `fid`, `rb` (real/bogus score), `drb` (deep learning real/bogus), `ssdistnr`, `ssmagnr`

**ATLAS Forced Photometry Server**
- Public REST API; forced photometry at any sky position
- Orange ($o$) and cyan ($c$) bands; 2-day cadence
- Useful for confirming candidates found in ZTF
- Access: `https://fallingstar-data.com/forcedphot/`

**Minor Planet Center (MPC)**
- Known object catalog: `astroquery.mpc` or direct MPC API
- NEO Confirmation Page (NEOCP): unconfirmed candidates needing follow-up
- Submit formatted reports for new detections
- Access: `from astroquery.mpc import MPC`

**JPL Horizons / CNEOS**
- Ephemerides for known objects: `astroquery.jplhorizons`
- Close approach tables: CNEOS API
- Scout and Sentry impact monitoring output (read-only reference)

### Astrometric Reference
- **Gaia DR3** via `astroquery.gaia` — sub-milliarcsecond astrometry for calibration

---

## Core Design Decisions

### DECISION-001: ZTF DR24 historical replay as primary discovery path (SUPERSEDED 2026-07-02)
**Superseded by operator decision 2026-07-02**: `docs/neo_discovery_agent_brief.md`
now supersedes the WISE-primary strategy below. ZTF DR24 archival historical
replay (bounded time window, time-aware known-object exclusion, Fink-FAT-style
tracklet linking, LightGBM/XGBoost candidate ranker, retrospective validation)
is now the primary discovery path. WISE/NEOWISE, DECam, and TESS are demoted
to secondary/paused — their code and Gate P1–P5 evidence are preserved but are
not the active development target. Live ZTF alert-stream and live ATLAS
consumption remain prohibited for discovery (still circular); ZTF DR24
archival reprocessing is the exception, per the brief's Fink-FAT precedent.
See `docs/MISSION.md §Operator Decision (2026-07-02)` for the full record.

**Original decision (2026-06-27, now secondary)**: WISE/NEOWISE was the primary discovery target: 158,000+ minor-planet infrared detections in unreviewed archival data accessible via IRSA without credentials. DECam/NOIRLab NSC DR2 and TESS FFIs were secondary discovery targets. ZTF and ATLAS were treated as **training-data sources only**. `--surveys WISE` (default), `DECam`, or `TESS` remain valid CLI options for the now-secondary path; do not delete this code.

### DECISION-002: Tiered ML Architecture
Follow the same three-tier approach as the exoplanet pipeline:
- **Tier 1**: Gradient-boosted trees (XGBoost/LightGBM) on tabular features — fast, interpretable, works with small labeled sets (~500 examples)
- **Tier 2**: CNN on ZTF image triplets (science / reference / difference cutouts) — proven for real/bogus classification (Duev et al. 2019)
- **Tier 3**: Transformer on tracklet sequences — frontier method for multi-night linking and NEO type classification (Lin et al. 2022)

### DECISION-003: No Autonomous Impact Claims
The pipeline produces a ranked candidate list and hazard flags. It never autonomously asserts a probability of Earth impact. The alert pathway requires a computed MOID ≤ 0.05 AU AND independent MPC confirmation before any NASA notification.

### DECISION-004: MPC-Compatible Output First
All detections must be expressible in MPC 80-column format or the newer MPC JSON format. This ensures interoperability with the global NEO community regardless of downstream ML additions.

### DECISION-005: Conservative Classification
Mirror the exoplanet pipeline's conservatism:
- `None` feature scores fail gate conditions
- Unknown objects default to "candidate" not "confirmed NEO"
- PHAs require orbit quality code ≥ 2 before flagging

---

## Key Types (schemas.py)

All models use `ConfigDict(frozen=True)` — immutable after construction.

```python
Mission = Literal["ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC", "TESS", "DECam", "WISE"]

NEOClass = Literal["amor", "apollo", "aten", "ieo", "unknown"]

HazardFlag = Literal["pha_candidate", "close_approach", "nominal", "unknown"]

AlertPathway = Literal[
    "mpc_submission",        # Report to MPC for confirmation
    "neocp_followup",        # Object on NEOCP; request observations
    "nasa_pdco_notify",      # High-confidence PHA; follow NASA protocol
    "internal_candidate",    # Below threshold for external reporting
    "known_object",          # Matches MPC catalog
]

# Core signal
@dataclass(frozen=True)
class Tracklet:
    object_id: str
    observations: tuple[Observation, ...]  # ≥2 obs per tracklet
    arc_days: float
    motion_rate_arcsec_per_hour: float
    motion_pa_degrees: float

# Feature vector (all OptScore = float | None, bounded [0,1])
class CandidateFeatures(BaseModel):
    # Detection quality
    real_bogus_score: OptScore
    streak_score: OptScore
    psf_quality_score: OptScore
    # Motion
    motion_consistency_score: OptScore
    arc_coverage_score: OptScore
    nights_observed_score: OptScore
    # Photometry
    brightness_score: OptScore       # proxy for size
    color_score: OptScore             # g-r, r-i
    lightcurve_variability_score: OptScore
    # Orbit (populated after orbit.py)
    orbit_quality_score: OptScore    # 0=poor, 1=good
    moid_score: OptScore             # 1 = MOID ≤ 0.05 AU
    neo_class_confidence: OptScore
    pha_flag_confidence: OptScore
    # Catalog
    known_object_score: OptScore     # 0 = new, 1 = known

# Posterior over NEO classification hypotheses
class NEOPosterior(BaseModel):
    neo_candidate: Score             # genuine new NEO
    known_object: Score              # matches MPC catalog
    main_belt_asteroid: Score        # MBA on unusual orbit
    stellar_artifact: Score          # cosmic ray / satellite / artifact
    other_solar_system: Score        # comet, TNO, etc.

class HazardAssessment(BaseModel):
    hazard_flag: HazardFlag
    moid_au: float | None
    estimated_diameter_m: float | None
    absolute_magnitude_h: float | None
    neo_class: NEOClass
    alert_pathway: AlertPathway
    explanation: CandidateExplanation

class ScoredNEO(BaseModel):
    tracklet: Tracklet
    features: CandidateFeatures
    posterior: NEOPosterior
    hazard: HazardAssessment
    metadata: ScoringMetadata
```

---

## Pipeline Stage Specifications

### 1. fetch.py
**Inputs**: sky region (RA, Dec, radius) or target list, date range, survey selection
**Process**:
- Query ZTF alert stream via IRSA or `ztfquery`
- Download ATLAS forced photometry for confirmed positions
- Query MPC for known objects in the search field
- Query JPL Horizons for ephemerides of known NEOs

**Output**: `FetchResult(alerts, provenance: FetchProvenance)`

**Notes**:
- Lazy-import all survey-specific libraries inside functions
- Cache raw alerts to disk; never re-download what is already cached
- Record survey, filter, limiting magnitude, and epoch in provenance

### 2. preprocess.py
**Inputs**: raw alerts with image cutouts
**Process**:
- Validate difference image quality (PSF, background RMS)
- Normalize cutout pixel values to [0,1] for CNN input
- Extract aperture photometry and morphological features
- Apply astrometric correction relative to Gaia DR3

**Output**: `PreprocessResult(sources, provenance: PreprocessProvenance)`

**Notes**:
- No external image-subtraction pipeline needed — ZTF alerts already include difference cutouts
- For ATLAS: use forced-photometry magnitudes directly

### 3. detect.py
**Inputs**: preprocessed source catalog
**Process**:
- Filter on real/bogus score (`rb ≥ 0.65` default threshold; configurable)
- Identify moving sources: compare positions across epochs; compute apparent motion rate
- Flag streaks/trails (fast-moving NEOs may trail in 30s ZTF exposures)
- Cross-match against MPC known object ephemerides to separate new vs. known

**Output**: `DetectResult(candidates: list[RawCandidate], known_matches: list[KnownMatch])`

### 4. link.py
**Inputs**: single-night candidates across multiple nights
**Process**:
- Implement a simplified tracklet linker (THOR-inspired; Moeyens et al. 2021):
  - Pair detections consistent with solar system object motion (0.05–60 arcsec/hr)
  - Extend pairs to triplets and longer arcs using a $\chi^2$ orbit-consistency test
- Require ≥3 detections on ≥2 nights for a reportable tracklet
- Compute arc length, motion rate, position angle, and rate uncertainty

**Output**: `LinkResult(tracklets: list[Tracklet])`

**Notes**:
- Pure numpy/scipy implementation; no external orbit-determination dependency at this stage
- `orbit.py` handles full orbit fitting downstream

### 5. classify.py
**Inputs**: linked tracklets + image cutouts
**Process** (three-tier, build in order):

**Tier 1 — XGBoost on tabular features**
- Features: real/bogus score, motion rate, arc length, nights observed, brightness, color index, streak score, PSF elongation, MPC match distance
- Labels: ZTF real/bogus labels + MPC confirmed NEO catalog
- Output: `real_bogus_score`, `neo_class_confidence` as `OptScore`

**Tier 2 — CNN on image triplets** (build after Tier 1 is calibrated)
- Input: 63×63 pixel cutout triplets (science, reference, difference) normalized to [0,1]
- Architecture: adapted from Duev et al. (2019) — three parallel convolutional branches merged at dense layer
- Pre-trained weights from ZTF real/bogus training set (public) available as starting point
- Fine-tune on confirmed NEO vs. artifact subset
- Output: calibrated real/bogus probability

**Tier 3 — Transformer on tracklet sequences** (frontier; build after Tier 2)
- Input: sequence of (RA, Dec, magnitude, time, filter) observations per tracklet, tokenized per observation
- Architecture: standard encoder-only transformer (BERT-style) with positional encoding based on observation time
- Task: multi-class classification (neo_candidate / known_object / main_belt / artifact / other)
- Training data: MPC observation history for confirmed NEOs + MBA sample + artifact labels from ZTF
- Reference: Lin et al. (2022) applied transformers to asteroid light-curve classification

**Ensemble (Tier 3 output)**
- Stacking meta-learner (logistic regression) over Tier 1 + Tier 2 + Tier 3 outputs
- Calibrate final probabilities via `calibration.py` (Platt or isotonic)

### 6. orbit.py
**Inputs**: linked tracklets (≥3 nights recommended)
**Process**:
- Initial orbit determination via Gauss's method (pure Python/numpy)
- Improve with differential correction (least-squares fit to observed positions)
- Compute orbital elements: $a$, $e$, $i$, $\Omega$, $\omega$, $M_0$
- Classify as Amor/Apollo/Aten/IEO/MBA from $(a, e, q, Q)$
- Compute MOID (Minimum Orbit Intersection Distance) relative to Earth's orbit
- Assign orbit quality code (1 = arc < 1 day, 2 = multi-night, 3 = multi-week, 4 = opposition)

**Notes**:
- Use `astropy` for coordinate transformations
- For short arcs (<24 hr), MOID is unreliable — flag accordingly
- Do not use `skyfield` or `rebound` in v0; keep dependencies minimal

### 7. score.py
**Inputs**: classified tracklets with orbital elements
**Process**:
- Compute `HazardAssessment` for each candidate:
  - `moid_au` from `orbit.py`
  - `estimated_diameter_m` from absolute magnitude H using geometric albedo assumption ($p_v = 0.14$ default)
  - `hazard_flag`: PHA candidate if MOID ≤ 0.05 AU AND $H \leq 22$
  - `alert_pathway` from ordered gate (see §Alert Protocol)
- Compute derived scores:
  - `discovery_priority`: combination of novelty, orbit quality, and PHA flag
  - `followup_value`: based on brightness, arc length, orbit uncertainty
  - `scientific_interest`: unusual orbital elements, extreme $a$ or $e$, short MOID

### 8. alert.py
**Inputs**: `ScoredNEO` objects
**Process**:
- Format MPC 80-column observation report for any `alert_pathway` ≥ `mpc_submission`
- Generate human-readable candidate summary
- For `nasa_pdco_notify`: generate structured alert package (see §Alert Protocol)
- Log all alert actions with timestamps and provenance

---

## Alert Protocol

This section defines the mandatory decision tree for external reporting. **No step may be skipped.**
Full policy: `docs/MPC_SUBMISSION_POLICY.md` (operator-approved 2026-06-21).

```
ready_for_submission() returns True:
  MOID ≤ 0.05 AU
  AND orbit quality code ≥ 2
  AND real_bogus_score ≥ 0.90
  AND alert_pathway ≠ known_object
         │
         ▼
Step 1: Submit observations to MPC in ADES PSV format  ←── pipeline does this
        Requires a registered MPC observatory code (one-time operator setup;
        use code XXX for first submission to obtain a permanent code).
        Use Skills/export_ades_report.py to generate the submission file.
         │
         ▼
Step 2: MPC calculates digest2 score automatically (~minutes)
        digest2 > 65 → MPC posts object to NEOCP automatically
        No pipeline action required for this step.
         │
         ▼ (if on NEOCP)
Step 3: Global follow-up observatories confirm independently (~hours)
        NEOCP is monitored 24/7 by professional observatories worldwide.
        Scout (CNEOS/JPL) simultaneously assesses impact probability.
        No pipeline action required — this IS the expert review step.
         │
         ▼ (if Scout detects impact risk)
Step 4: Scout automatically alerts NASA PDCO.
        Do NOT contact PDCO directly.
        Do NOT publicly state impact probabilities.
        Open a GitHub Issue tagged [HAZARD-ALERT] for operator awareness only.
```

**Permanent guardrails** (not affected by the 2026-06-21 policy change):
- Never assert impact probability in any pipeline output — defer to Scout/Sentry/CNEOS
- Never contact NASA PDCO directly — Scout handles this automatically
- Never publicly announce a candidate before MPC assigns a provisional designation
- Never output "confirmed NEO" — all objects are candidates until MPEC publication
- Never lower the quality gates in `ready_for_submission()`
- Store full provenance (observations, orbit fit, MOID computation) with every alert

---

## ML Training Data

| Dataset | Source | Size | Use |
|---|---|---|---|
| ZTF real/bogus labels | Duev et al. (2019) / Broker APIs | ~100,000 alerts | Tier 1 + Tier 2 training |
| MPC confirmed NEO catalog | `astroquery.mpc` | ~35,000 objects | Positive labels |
| MPC MBA sample | `astroquery.mpc` | large | Negative labels for NEO classifier |
| ZTF NEO observation history | IRSA | varies | Tracklet sequence training |
| ATLAS detections of known NEOs | ATLAS server | varies | Tier 1 feature validation |

**Label quality note**: Use only MPC-numbered objects as high-confidence positives. Provisional designations may be reassigned and should be treated with lower weight.

---

## Scoring Model

### Hypotheses

| Symbol | Hypothesis | Prior |
|---|---|---|
| $H_\text{neo}$ | Genuine new NEO candidate | 0.05 |
| $H_\text{ko}$ | Known MPC object | 0.30 |
| $H_\text{mba}$ | Main-belt asteroid | 0.35 |
| $H_\text{art}$ | Instrumental artifact | 0.25 |
| $H_\text{other}$ | Other solar system body | 0.05 |

Priors are deliberately pessimistic about new NEOs (most moving objects are known MBAs or artifacts). Adjust priors for high-ecliptic-latitude fields where MBA contamination is lower.

### Log-Score Model

$$\ell_i = \log P(H_i) + \sum_k w_{ik}\,\phi_k(\mathbf{D})$$

$$p_i = \frac{\exp(\ell_i - \ell_{\max})}{\sum_j \exp(\ell_j - \ell_{\max})}$$

All features $\phi_k \in [0,1]$; missing features contribute 0 (neutral).

### Key Feature Weights (planet_candidate analogue → neo_candidate)

```
log_score_neo =
    log_prior_neo
    + 2.0 * real_bogus_score
    + 1.5 * arc_coverage_score
    + 1.5 * nights_observed_score
    + 1.2 * motion_consistency_score
    + 1.0 * orbit_quality_score
    - 2.5 * known_object_score
    - 2.0 * stellar_artifact_score
    - 1.5 * main_belt_consistency_score
```

---

## Quality Commands

**Always use `uv run` — never call `python` or `pytest` directly.**
The project venv is Python 3.14.3 managed by uv from `uv.lock`. Using bare
`python` risks picking up a different system interpreter and diverging from CI.

```bash
# Lint
uv run --python 3.14 ruff check .
uv run --python 3.14 ruff check . --fix

# Type-check
uv run --python 3.14 python -m mypy src

# Tests (PYTHONPATH=src set via env for uv run)
PYTHONPATH=src uv run --python 3.14 python -m pytest

# macOS local runs with XGBoost/OpenMP may need deterministic threading
OMP_NUM_THREADS=1 PYTHONPATH=src uv run --python 3.14 python -m pytest

# All three
uv run --python 3.14 ruff check . && uv run --python 3.14 python -m mypy src && PYTHONPATH=src uv run --python 3.14 python -m pytest
```

CI uses `uv sync --extra dev` (from `uv.lock`) then `uv run` — identical to
the local venv. Python version is pinned to 3.14 in `.github/workflows/ci.yml`.

Live integration tests (require network access to ZTF/ATLAS/MPC) must be marked:

```python
@pytest.mark.integration_live
```

and excluded from CI.

---

## Guardrails

- Never output "confirmed NEO" for internally detected objects
- Never state or imply an impact probability without MPC/CNEOS confirmation
- Always expose artifact and known-object evidence alongside every candidate score
- Store scoring model version and observation provenance with every result
- Prefer conservative classifications; when uncertain, flag for human review
- The alert protocol is non-negotiable and must be followed in full

---

## Key Literature

- Bellm, Eric C., et al. "The Zwicky Transient Facility: System Overview, Performance, and First Results." *PASP*, vol. 131, 2019, p. 018002.
- Duev, Dmitry A., et al. "Real-bogus Classification for the Zwicky Transient Facility Using Deep Learning." *MNRAS*, vol. 489, no. 3, 2019, pp. 3582–3590.
- Lin, Hsing-Wen, et al. "Astronomical Image Time Series Classification Using CONVolutional Neural nETworks (ConvNet)." *AJ*, vol. 163, 2022, p. 154.
- Moeyens, Joachim, et al. "THOR: An Algorithm for Cadence-independent Asteroid Discovery." *AJ*, vol. 162, no. 4, 2021, p. 143.
- Ye, Quanzhi, et al. "Hundreds of New Near-Earth Asteroids Found with ZTF." *AJ*, vol. 159, no. 2, 2020, p. 70.
- Jedicke, Robert, et al. "Observational Selection Effects in Asteroid Surveys." *Asteroids III*, Univ. of Arizona Press, 2002, pp. 71–87.
- Mainzer, Amy, et al. "Initial Performance of the NEOWISE Reactivation Mission." *ApJ*, vol. 792, no. 1, 2014, p. 30.

---

## Current State (v0.90.55)

All 10 pipeline modules are complete. The offline suite passes 1573 tests, with
2 live/integration checks deselected. CI is green on Python 3.14 with the 100%
coverage target. All three ML tiers have trained weights: Tier 1 XGBoost
(val_acc=99.95%), Tier 2 CNN (val_acc=91.3%), and Tier 3 Transformer
(val_macro_f1=0.9400, best epoch 17/30).
**T1-A CLOSED. T1-B CLOSED. T1-C CLOSED. T1-D CLOSED.**
Ensemble stacker KPIs passed 2026-06-14 (AUC=0.9809, Brier=0.0211, ECE=0.0000).
T2-C CLOSED 2026-06-21 (operator sign-off by Jerome W. Lindsey III).
T2-D CLOSED 2026-06-21 (model-weight CI job + `Skills/validate_model_weights.py`).
**fetch.py discovery layer COMPLETE (PR #119, 2026-06-27)**: `fetch_wise_archive`,
`fetch_decam_archive`, `fetch_tess_ffis`, `fetch_discovery` routing layer added.
`run_pipeline.py` default survey changed from ZTF → WISE.

**No legacy T1 production blockers remain.** The WISE/DECam/TESS path is
preserved as secondary historical evidence, not the current primary discovery
target. Per `docs/MISSION.md` and `docs/neo_discovery_agent_brief.md`, the
active path is ZTF DR24 archival historical replay with no future-catalog
leakage, auditable source verification, and fail-closed submission controls.
ZTF live alert-stream discovery remains prohibited. Gate Z1 bounded ingest and
Gate Z2 time-aware known-object exclusion are code-complete pending operator
live verification. **Gate Z3's source-verification blocker is now CLOSED**
(2026-07-02): the University of Washington's public ZTF alert archive is a
real, unauthenticated, schema-verified per-detection source — see the v19
handoff below. Gate Z3 as a whole remains open pending a bounded multi-night
ingest tool and a real known-object positive control run through the
existing linker. The older ALeRCE-backed source provider is real
bounded-pilot evidence, but
`docs/evidence/phase0/alerce_source_detection_assessment.md` records that it
is not current DR24 production evidence until verified for the historical-
replay protocol.

### Handoff state as of 2026-07-04 v48 (CURRENT)

**Implemented the recommended cheap fix: sentinel-magnitude MPC reports
are now excluded from candidate selection (v0.90.55)** —
`Skills/scan_mpc_history_ztf_coverage.py` now filters out MPC reports with
`mag >= 90` (sentinel/placeholder, not a real detection) before striding
and selecting candidates, directly addressing the root cause found in the
20220817/20220819 pair's failure (its night-2 reference position was a
`mag=99.00` report). 1 new regression test (14 total in this file, all
passing). `docs/ZTF_DR24_PRODUCTION_GATES.md`'s Gate Z3 row and "Next
Coding Step" updated to reflect the current real state (pipeline mechanics
confirmed on real data; single-object match not yet confirmed for either
tried pair) instead of stale 2026-07-02 content.

**Next production action (NOT YET DONE)**: re-run the systematic MPC scan
now that sentinel-mag reports are filtered, to select a fresh (third)
candidate-pair recommendation with higher confidence than the prior two:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10
```

This reuses the already-cached MPC history (no new network call for that
part) and only issues new Gate Z1 metadata queries (cheap, no alert-
archive download) for the filtered candidate list. Read the printed
`[scan] Excluded N sentinel/placeholder-magnitude MPC report(s)` line to
confirm the filter engaged, then evaluate the resulting hit list for a
new candidate pair before running another multi-GB alert-archive
ingest.

### Handoff state as of 2026-07-04 v47

**Real observatory codes obtained; partial explanation found, not fully
resolved** — operator ran the `--force-refresh` lookup and got real
per-report observatory codes for the first time. Pair 1's failure (night
20220819) now has a clean, well-supported explanation: the exact
reference position came from an MPC report with `mag=99.00` (a
sentinel/placeholder value, observatory `C51`), not a genuine measured
detection — a poor anchor for the search box regardless of station. Pair
2's failure is less cleanly explained: both reference positions have real
magnitudes (19.46 `I41`, 19.23 `G96`) from different stations, which
doesn't by itself explain a 35-arcmin gap. Full evidence:
`docs/evidence/live/2026-07-04-gate-z3-observatory-codes-real-findings.md`.

**Do not assume any specific MPC code (T05, I41, G96, C51, etc.) is or
isn't ZTF's own code** — this has not been independently verified in this
project and must not be guessed.

**Recommendation for next session** (not yet implemented): two paths,
in order of effort — (1) filter `scan_mpc_history_ztf_coverage.py`'s
candidate selection to exclude `mag >= 90` sentinel reports before trying
a third apparition of 72966; (2) select a different, well-observed real
NEO designation entirely rather than continuing to exhaust apparitions of
this one object. Five real apparitions of 72966 have now been checked
across this project without a confirmed clean two-night positive control
— continuing to probe this exact object may have diminishing returns.

**What IS already a real, valuable result, independent of confirming one
specific object**: `preprocess()`/`detect()`/`link()` correctly process
real archived ZTF alert data end-to-end and form real cross-night
tracklets (546 formed across the two attempted pairs combined this
session) — the remaining gap is confirming one specific tracklet's
identity against a known object, not whether the pipeline mechanics work
on real data.

### Handoff state as of 2026-07-04 v46

**Stale checkpoint blocked the observatory-code lookup -- missing
`--force-refresh` flag added (v0.90.54)** — operator re-ran
`Skills/lookup_mpc_observation_history.py` after v0.90.53 merged, but it
printed `checkpoint already present, skipping fetch` and returned the
pre-fix cached report, which does not contain the new `observatory`
field (that checkpoint was written before v0.90.53 added it). Root cause:
the script's checkpoint-exists short-circuit had no way to force a
re-fetch, and even bypassing it would still hit `fetch_mpc_observations`'
own separate disk cache. Fixed by adding `--force-refresh` (threads
through to both the script's own checkpoint and the underlying fetch's
cache). 1 new regression test confirms both cache layers are bypassed
together. This is a real, necessary unblock, not a speculative feature —
the prior handoff's instruction to just re-run the lookup command was
insufficient without this flag.

**Next production action (NOT YET DONE)**: re-run with the new flag to
get real per-report observatory codes for both nights of each of the two
failed candidate pairs:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/lookup_mpc_observation_history.py \
    --designation 72966 \
    --archive-start-jd 2458273.5 \
    --force-refresh
```

Inspect the printed `observatory=` value for nights 20220817, 20220819,
20210106, and 20210111 specifically. If a pair's two nights show
different codes, that confirms the root-cause hypothesis and the next
step is filtering `scan_mpc_history_ztf_coverage.py`'s candidate
selection to same-station pairs before trying a third apparition.

### Handoff state as of 2026-07-04 v45

**Second candidate pair also fails to positively control (69.5 arcmin →
70.5 arcmin, same pattern); real root cause found and fixed** — operator
ran the full run_archive_positive_control.py → match_positive_control_tracklet.py
→ find_nearest_raw_observation.py sequence against 20210106/20210111 (the
other real candidate pair with substantial kept data). Real result: 54
tracklets formed, best match 4231.5 arcsec (70.5 arcmin) off -- ruled out,
same as the first pair. Raw-observation check: night 20210106 has a
strong match at 14.1 arcsec; night 20210111's closest is 2103.1 arcsec
(35.1 arcmin) away -- too far. **Both of the two candidate pairs tried so
far show this exact pattern: strong match on the pair's first night, no
match on the second.**

**Root cause (found, not guessed)**: `docs/evidence/phase0/2026-07-02-root-cause-findings.md`
already recorded that MPC's `get-obs` API returns observations from
"multiple stations/surveys" for a real designation -- MPC's observation
history is NOT ZTF-exclusive. `src/fetch.py:fetch_mpc_observations`
already extracted the real per-observation `observatory` code from
astroquery but only used it internally for a hash string -- it was never
exposed on the returned `Observation`, so every tool that selected these
candidate pairs (`scan_mpc_history_ztf_coverage.py`) could only confirm
"ZTF has sci-exposure metadata here" + "MPC has *some* report here," never
"this MPC report specifically came from ZTF." A non-ZTF station reporting
the object's real position, combined with ZTF separately imaging near
that position the same night (routine, since ZTF resurveys the whole sky
every ~3 nights), produces a false-positive scan "hit."

**Fix (v0.90.53, this PR)**: `fetch_mpc_observations` now surfaces the
already-fetched observatory code via the existing `field_id` field (no
schema change, no new API). `lookup_mpc_observation_history.py`'s report
and console output, and `scan_mpc_history_ztf_coverage.py`'s per-hit
console line, now include it. 2 new regression tests. Full evidence:
`docs/evidence/live/2026-07-04-gate-z3-second-pair-no-match-plus-observatory-fix.md`.

**Next production action (NOT YET DONE)**: do not select a third
candidate pair blindly. Re-run the already-cached lookup (no new network
call) and inspect the new `observatory` field for both nights of each
tried pair:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/lookup_mpc_observation_history.py \
    --designation 72966 \
    --archive-start-jd 2458273.5
```

If the two nights within a pair have different observatory codes, that
directly explains the observed pattern, and future candidate-pair
selection (a possible follow-up to `scan_mpc_history_ztf_coverage.py`)
should filter to matching station codes before spending more download
bandwidth on another apparition.

### Handoff state as of 2026-07-04 v44

**Raw-observation check: night 1 has a plausible near-match, night 2 does
not -- this candidate pair does not currently support a positive
control** — operator ran `Skills/find_nearest_raw_observation.py` against
both nights' existing checkpoints. Real result: night 20220817's closest
real detection is **74.1 arcsec** from the known reference position
(`real_bogus=0.85`, plausibly consistent with real astrometric/orbit-
propagation error). Night 20220819's closest real detection is **615.7
arcsec (10.3 arcmin)** away -- far too large to be explained by the
object's own expected motion (~38.7 arcsec/hr would require ~16 hours of
drift to reach that offset, inconsistent with a single UTC night). Full
evidence:
`docs/evidence/live/2026-07-04-gate-z3-raw-observation-check-inconclusive.md`.

**Conclusion**: combined with the prior finding that no linked tracklet
matches either position
(`docs/evidence/live/2026-07-04-gate-z3-no-tracklet-matches-72966.md`),
the 20220817/20220819 pair does not currently support a genuine Gate Z3
positive control. Continuing to probe this exact pair further (lower
real-bogus threshold, wider search radius) is a possible future
refinement, but the more productive next step is trying the other real
candidate pair already ingested this session.

**Next production action (NOT YET DONE)**: run the positive control
against the 20210106/20210111 pair (kept=272/177, real per-source data
already on disk from the six-tab batch, never yet run through
`run_archive_positive_control.py`):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20210106 20210111 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_20210106_20210111.json
```

Then rank with `Skills/match_positive_control_tracklet.py` against
reference positions RA/Dec 116.1336/8.6041 (20210106) and
114.9238/8.8044 (20210111), and if inconclusive, check raw observations
with `Skills/find_nearest_raw_observation.py` as done for the first pair.

### Handoff state as of 2026-07-04 v43

**No tracklet matches designation 72966's real position -- genuine
negative, not inconclusive** — operator ran
`Skills/match_positive_control_tracklet.py` against the real
`report_min2.json`. Real result: best-matching tracklet's total offset
from the two known reference positions is **4172.4 arcsec (69.5 arcmin,
1.16 deg)** — far too large to be real astrometric/orbit-propagation
noise (which would be at most a few arcmin). All 88 tracklets are ruled
out as a match for designation 72966. Full evidence:
`docs/evidence/live/2026-07-04-gate-z3-no-tracklet-matches-72966.md`.

**Root cause (diagnosed, not guessed)**: `link()` only checks motion-rate
consistency between candidate pairs (0.05-60 arcsec/hr window), never
positional proximity to a target. In a crowded 116-candidate field, the
real object's two genuine detections (if captured that night) may simply
never be paired together by a greedy pairing algorithm — a different,
unrelated candidate can plausibly steal either side of the pair first.
This means "no tracklet near the known position" does not prove ZTF
failed to image the object that night; it only proves the linker's
specific pairing choices didn't recover it.

**New tool (v0.90.52, this PR)**: `Skills/find_nearest_raw_observation.py`
bypasses detect()/link() entirely and searches a single night's raw kept
observations (already on disk from `ztf_alert_archive_ingest.py`) for the
nearest real detection to a known reference position -- a narrower, prior
question: did ZTF's archive record any confident detection near the real
position that night at all? 6 offline tests.

**Next production action (NOT YET DONE)**: check both nights' raw
observations directly (fast, local, no re-run of detect/link needed):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20220817.json \
    --ref 257.0809 -10.7456
uv run --python 3.14 python Skills/find_nearest_raw_observation.py \
    Logs/pipeline_runs/ztf_alert_archive_ingest/20220819.json \
    --ref 257.5497 -10.9843
```

If both nights show a close raw observation (tens of arcsec), the object
was captured but the linker failed to pair it -- a linker limitation
(next fix: position-aware linking), not a data-availability problem. If
neither night shows a close raw observation, this candidate pair should
be treated as exhausted for Gate Z3 and a different apparition/pair from
the 30-hit MPC scan should be tried next (e.g. 20191005/20191008 or
20210106/20210111, both already ingested with real kept observations).

### Handoff state as of 2026-07-03 v42

**Re-run at `--min-observations 2` reproduced the same 88 tracklets (new
UUIDs, identical rates/arcs) -- still not confirmed as designation
72966** — operator re-ran the identical command on `main` @ v0.90.50
(with the per-observation-position fix from PR #192). Real result:
identical distribution of 88 two-observation tracklets (same arc lengths
and rates as the prior run, e.g. `068f107d` at 38.10 arcsec/hr,
`e1454478` at 40.28 arcsec/hr), confirming the run is deterministic, not
flaky. The console print statement does not surface per-observation
positions (only the JSON report does), so a follow-up analysis step is
needed to actually identify a match rather than eyeballing rates.

**New tool (v0.90.51, this PR)**: `Skills/match_positive_control_tracklet.py`
ranks each tracklet in a `report_min2.json` by real angular offset (arcsec)
from the two known reference positions, instead of relying on rate
proximity alone. 6 offline tests confirm it correctly ranks a synthetic
"close" tracklet above a "far" one and excludes single-observation
tracklets. Not yet run against the real 88-tracklet report (needs the
operator's local `report_min2.json` file).

**Next production action (NOT YET DONE)**: run the new matching tool
against the already-produced local report:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/match_positive_control_tracklet.py \
    Logs/pipeline_runs/run_archive_positive_control/report_min2.json \
    --ref1 257.0809 -10.7456 \
    --ref2 257.5497 -10.9843
```

This is a fast, local, no-network analysis of the file already on disk —
no re-run of the positive control itself is needed. If the best match's
total offset is large (many arcmin or more), the 88 tracklets are almost
certainly combinatorial artifacts and this candidate pair should be
considered a Gate Z3 negative; if a tracklet's offset is small (sub-arcmin
to a few arcsec, consistent with real astrometric/orbit-propagation
error), that specific tracklet is real supporting evidence, not final
confirmation.

### Handoff state as of 2026-07-03 v41

**`--min-observations 2` produced 88 tracklets, but this is NOT yet
confirmed evidence of recovering designation 72966** — operator re-ran
`Skills/run_archive_positive_control.py --nights 20220817 20220819
--min-observations 2`. Real result: 88 tracklets formed, each with exactly
2 observations (one per night), arc lengths 1.94-2.02 days, rates from
~4.5 to ~59.9 arcsec/hr. Root cause of why this is not yet confirmation
(diagnosed, not guessed): `link()` has no chi-square orbit-consistency
check for 2-observation arcs (that check only applies at >=3
observations), so in a crowded 116-candidate field, any two points across
the two nights whose implied rate falls in the deliberately broad
0.05-60 arcsec/hr window forms a "tracklet" — 88 is consistent with
combinatorial cross-matching of unrelated real sources, not confirmation
of the genuine object. Computed directly (not guessed) from the two real
MPC-reported center positions that anchored these search boxes
(257.0809/-10.7456 and 257.5497/-10.9843), designation 72966's real
implied motion between them is separation=1866.9 arcsec, rate=38.70
arcsec/hr, PA=117.4 deg. Several of the 88 tracklets have rates near this
value (e.g. `8633d484` at 39.27 arcsec/hr) but rate proximity alone is not
sufficient — need per-observation positions to confirm. Full evidence:
`docs/evidence/live/2026-07-03-gate-z3-positive-control-min2-88-tracklets.md`.

**Fix (v0.90.50, this PR)**: `Skills/run_archive_positive_control.py`'s
report now includes `motion_pa_degrees` and each tracklet's
per-observation `[{ra_deg, dec_deg, jd}, ...]` list, so the specific
tracklet nearest the two known real center positions can be identified by
angular offset instead of by rate alone.

**Next production action (NOT YET DONE)**: re-run the identical command
(now with the updated script) and inspect `report_min2.json`'s
`tracklets[].observations` for the tracklet closest to the two real
center positions above:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_min2.json
```

Do not treat "88 tracklets" as confirmation of anything until a specific
tracklet's positions are matched against the two real center coordinates.

### Handoff state as of 2026-07-03 v40

**First real positive-control run: 0 tracklets at default threshold, retry
with `--min-observations 2` not yet run** — operator ran
`Skills/run_archive_positive_control.py --nights 20220817 20220819` on
`main` @ v0.90.49. Real result: 553 real observations loaded (267 + 286),
all 553 passed preprocessing, `detect()` formed 116 candidates (0 known
matches), `link()` formed **0 tracklets** at the default
`min_observations=3`. Not yet conclusive — the same threshold-sensitivity
finding from v0.90.42 (a genuine 2-night tracklet can be rejected at
`min_observations=3` if too few of the SAME object's detections land in
the arc) applies here and must be ruled out before concluding this pair
does not positively control. Full evidence:
`docs/evidence/live/2026-07-03-gate-z3-positive-control-first-attempt.md`.

**Next production action (NOT YET DONE)**:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 --min-observations 2 \
    --out Logs/pipeline_runs/run_archive_positive_control/report_min2.json
```

If this still reports 0 tracklets, the 116 detect-stage candidates are
most likely independent real field sources rather than the same object
observed on both nights (real field crowding in a 2-degree box, not a
linker defect) — the next escalation would be a tighter sky-box re-ingest
centered more precisely on the MPC-reported position for this designation,
not a further linker-threshold change.

### Handoff state as of 2026-07-03 v39

**All 6 parallel-tab nights completed with real results; git-relay manifest
had a real .gitignore bug that blocked its first live use (v0.90.49)** —
the 6-night batch (20220817, 20220819, 20191005, 20191008, 20210106,
20210111) all completed and were relayed via console paste since they ran
on `main` @ v0.90.47, before the git-relay auto-push existed. Operator then
upgraded to v0.90.48 and ran `--sync` to backfill the manifest from the
11 checkpoints already on disk (6 new + 5 from earlier sessions) — this
independently reproduced the same `kept` counts from the pasted transcripts,
confirming they're real. **Real result**: night 20220817 kept 267, night
20220819 kept 286 — the first time this project has substantial real
per-source detections on both nights of a candidate pair (2 days apart).
Secondary pair 20210106/20210111 also positive (272/177 kept). 20191005 and
20191008 were real negatives (0 kept on both). Full evidence:
`docs/evidence/live/2026-07-03-gate-z3-six-tab-batch-results.md`.

**Real bug found on first live use of `--sync`**: `git add` on the manifest
failed with "ignored by .gitignore". Root cause: `.gitignore`'s
`!Logs/reports/` only un-ignores the directory entry itself; `Logs/**`
still matched every file inside it except the one pre-existing explicit
`.gitkeep` exception, so the new manifest file was never actually
committable. Fixed in v0.90.49 by widening to `!Logs/reports/**`. The
auto-commit-and-push code path added in v0.90.48 had never actually been
exercised until this real run — it should work end-to-end on the next
invocation now that the underlying `.gitignore` bug is fixed.

**Next production action (NOT YET DONE)**: once this PR merges, run the
Gate Z3 "known-object positive control" against the strongest real pair:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

If this reports zero tracklets, re-run with `--min-observations 2` (per the
v0.90.42 finding that the linker's default `min_observations=3` can reject
a genuine short-per-night tracklet — real archived data here has far more
observations per night than the synthetic case that finding was based on,
so this is a fallback, not the expected outcome).

### Handoff state as of 2026-07-02 v38

**Automatic git-relay manifest added to `ztf_alert_archive_ingest.py`
(v0.90.48)** — operator ran 6 concurrent tabs (3 candidate night pairs)
and correctly pointed out that pasting console output from 6 tabs is
exactly the fragile process we were trying to eliminate, and that this
tool should have had the same git-relay pattern already built for
`scan_mpc_history_ztf_coverage.py`. Two corrections along the way:
(1) the manifest must live in a **committed** path (`Logs/reports/`,
already allowlisted in `.gitignore`) and the script must **auto-commit
and push it itself** — a local-only manifest still requires either
filesystem access I don't have or manual pasting, neither of which
solves the actual problem; (2) git, not the operator's filesystem, is the
real communication channel.

Every completed night now appends to
`Logs/reports/ztf_alert_archive_ingest_manifest.jsonl` and the script
auto-pushes it (retry with `pull --rebase` on conflict). New `--status`
(read manifest) and `--sync` (backfill from checkpoints already on disk,
for runs started before this existed — exactly the 6 tabs currently
running) flags. 9 new tests, 14 total, all passing offline.

**Next production action (NOT YET DONE)**: once the 6 currently-running
tabs finish (they used the pre-manifest version, so they won't auto-push)
and this PR is merged, run `--sync` once to backfill and push all 6
results without re-downloading anything:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py --sync
```

Then I read the results via `git pull` directly — no pasting needed from
this point forward for this tool.

### Handoff state as of 2026-07-02 v37

**Full systematic MPC-history scan found 30 real hits** ✓ — operator ran
the (pre-sharding, sequential) `Skills/scan_mpc_history_ztf_coverage.py`
to full completion (53/53 checked, ~12 min). Real result: **30 of 53**
checked MPC reports had real ZTF sci-exposure coverage at their exact
position/date — far richer than the earlier hand-picked cluster (1/4).
Full evidence:
`docs/evidence/live/2026-07-02-gate-z3-full-mpc-scan-30-hits.md`.

**Selected target pair**: **20220817 and 20220819** (RA 257.08/Dec
-10.75 and RA 257.55/Dec -10.98) — only 2 real days apart, both with
substantial independent real sci coverage (16 and 24 rows), both
independently MPC-confirmed. Strongest candidate pair found so far.

**Next production action (NOT YET DONE)**:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20220817 \
    --ra 257.0809 --dec -10.7456 --radius-deg 2.0 --min-rb 0.5
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20220819 \
    --ra 257.5497 --dec -10.9843 --radius-deg 2.0 --min-rb 0.5
```

If both yield >=1 kept observation, run:

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

Backup candidates if this pair fails: 20191005/20191008 (3 days apart,
30/24 sci rows) or 20220626/20220628 (2 days apart, but night 2 only has
2 sci rows — riskier).

### Handoff state as of 2026-07-02 v36

**Live-updating manifest added per operator request (v0.90.47)** —
operator asked for something "like when a pull request merges": each
shard updating a shared status as it finishes, instead of only a final
merge step. Each shard now appends one file-locked JSON line to
`manifest.jsonl` in `--out-dir` the moment it completes. New `--status`
flag reports progress (shards reported/missing, running combined hit
list) safely at any time, even mid-run — `--merge` still exists for the
final, fail-closed full combine. 5 new tests (13 total).

**Next production action (NOT YET DONE)**: run the 4 parallel shard
commands from the v34 handoff below, each in its own terminal tab. Check
progress anytime with:

```bash
uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --status --shard-count 4
```

Once all 4 report in, run the final combine:

```bash
uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --merge --shard-count 4
```

and paste that output. I'll pick the two best resulting real nights and
target `Skills/ztf_alert_archive_ingest.py` there next.

### Handoff state as of 2026-07-02 v35

**Merge mode added for the sharded MPC-history scan (v0.90.46)** —
operator asked "do I still need to paste all 4 tabs' output?" Answer:
each shard only writes a local JSON file, not visible to the agent
without pasting — so yes, unless a merge step is added. Added `--merge`:
after all 4 shard tabs finish, run one fast, no-network command that
combines the 4 `scan_report.shard{i}of4.json` files into one compact
`scan_report.merged.json` and prints a single consolidated summary,
replacing the need to paste 4 separate transcripts. Fails closed if any
shard hasn't finished yet. 2 new tests (9 total, all passing).

**Next production action (NOT YET DONE)**: run the 4 parallel shard
commands from the v34 handoff below, each in its own terminal tab. Once
all 4 finish, run:

```bash
uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --merge --shard-count 4
```

and paste that single output block. I'll pick the two best resulting real
nights and target `Skills/ztf_alert_archive_ingest.py` there next.

### Handoff state as of 2026-07-02 v34

**Parallel sharding added to the MPC-history scan (v0.90.45)** — operator
asked to parallelize the ~53-query `Skills/scan_mpc_history_ztf_coverage.py`
scan across multiple terminal tabs instead of running sequentially. Added
`--shard-index`/`--shard-count`: each shard checks a disjoint subset
(`rows[shard_index::shard_count]`) of the same already-strided report
list, so no two shards ever duplicate or race on a query. The one-time
MPC-history fetch resumes from the operator's already-cached checkpoint
(from the prior `lookup_mpc_observation_history.py` run), so no shard
re-fetches it over the network — safe to launch all shards at once. 3 new
tests confirm shards partition the full list with zero overlap. Sharded
report files are named `scan_report.shard{i}of{n}.json`.

**Next production action (NOT YET DONE)**: run these 4 commands, each in
its own terminal tab:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
```

```bash
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 0 --shard-count 4
```
```bash
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 1 --shard-count 4
```
```bash
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 2 --shard-count 4
```
```bash
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 3 --shard-count 4
```

Once all 4 tabs complete, read the printed `HIT` lines (or the
`scan_report.shard{i}of4.json` files) and target
`Skills/ztf_alert_archive_ingest.py` at the two best resulting real
nights.

### Handoff state as of 2026-07-02 v33

**First real cross-check of an MPC-confirmed cluster against Gate Z1** —
only 1 of 4 real MPC-confirmed nights showed ZTF coverage — operator ran
`Skills/ztf_dr24_bounded_ingest.py` (RA 225.44,
Dec -5.08, 8-day window). Real result: 9 rows, 1 distinct night
(20180713), 1 field. Interpretation: MPC's observation history aggregates
reports from many surveys; this project's `fetch_mpc_observations`
mapping doesn't expose the reporting observatory, so a real MPC report
doesn't guarantee it came from ZTF. Night 20180713 is now the strongest
single-night candidate found so far (two independent real confirmations:
MPC + Gate Z1) — but still only one night. Full evidence:
`docs/evidence/live/2026-07-02-gate-z1-mpc-cluster-crosscheck.md`.

**New tool (v0.90.44)**: `Skills/scan_mpc_history_ztf_coverage.py`
systematically checks a bounded, stride-limited subset of ALL 526 real
in-window MPC reports against Gate Z1 (instead of hand-picking more
clusters), at each report's own exact real observed position/date.
Offline-tested (4 tests, mocked); not yet run live.

**Next production action (NOT YET DONE)**:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 \
    --archive-start-jd 2458273.5 --stride 10
```

This issues ~53 cheap Gate Z1 queries. Target
`Skills/ztf_alert_archive_ingest.py` at the two best resulting real
nights (closest in time to minimize orbit-motion targeting error) next.

### Handoff state as of 2026-07-02 v32

**MPC observation history for 72966 returned dense real data** ✓ —
operator ran `Skills/lookup_mpc_observation_history.py`. Real result:
1332 total MPC-confirmed observations, 526 within the ZTF archive's
coverage window (JD >= 2458273.5). This is far denser real evidence of
detection activity than the single `ssnamenr` cross-match that originally
identified this object. Full evidence:
`docs/evidence/live/2026-07-02-mpc-observation-history-72966.md`.

**Candidate cluster identified**: a dense real run of 4 report nights in
July 2018 (20180711, 20180713, 20180714, 20180715, all Dec ~-5, well
within ZTF's footprint) — a much stronger candidate than prior single-
night guesses, since MPC independently confirms real detection activity
across multiple nights here.

**Next production action (NOT YET DONE)**: cross-check this cluster
against the cheap Gate Z1 ZTF sci-metadata tool before spending bandwidth
on another multi-GB alert-archive download:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 225.44 --dec -5.08 --size-deg 2.0 \
    --start-jd 2458308.5 --end-jd 2458316.5
```

If this reports >=2 distinct real ZTF nights overlapping the MPC cluster,
target `Skills/ztf_alert_archive_ingest.py` at those specific real
nights/positions next.

### Handoff state as of 2026-07-02 v31

**Third real alert-archive attempt (nights 20180809/20180903, the corrected
pair from targeted ephemeris scanning) came back empty on night 2 again —
real negative, root cause diagnosed** — night 20180903 downloaded 8.5GiB,
scanned 193,223 real packets over 8m36s with correct progress/ETA, but
kept 0, despite Gate Z1 confirming 6 real sci exposure rows at this exact
position that night. **Root cause**: a real science exposure existing
confirms only that ZTF pointed a camera there — not that a real alert
(`rb >= 0.5` difference-image detection) was generated at that specific
sub-position. "Was the sky imaged" and "did a real alert fire" are
different questions; Gate Z1's metadata check only answers the first.
Full evidence:
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-third-attempt.md`.

**Pivot (v0.90.43)**: `Skills/lookup_mpc_observation_history.py` queries a
categorically stronger signal — MPC's own confirmed observation history
(`src/fetch.py:fetch_mpc_observations`, already Phase-0-verified
production code, 100% covered). A real MPC-reported observation means a
real alert-equivalent detection genuinely happened and was credible
enough to be submitted and accepted by the community, not just that the
sky was imaged. Wraps the fetch call in its own retry-with-backoff and
reuses the v0.90.39 JD-to-date fix. Offline-tested (5 tests, mocked); not
yet run live.

Also merged this handoff: `Skills/run_archive_positive_control.py`
(v0.90.42, PR #182) — the detect→link loader/runner for the eventual
positive control, offline-verified against the exact synthetic generator
already proven in `injection_recovery.py`'s baseline. Found a real
`min_observations` parameter-sensitivity issue (link()'s default of 3 can
reject a genuine 2-night tracklet with few observations per night;
`--min-observations 2` is available to re-check).

**Next production action (NOT YET DONE)**: run the MPC history lookup,
then cross-check any in-window real report nights against the cheap Gate
Z1 metadata tool before committing to another multi-GB alert-archive
download:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/lookup_mpc_observation_history.py \
    --designation 72966 \
    --archive-start-jd 2458273.5
```

If 72966 has very few or no MPC-confirmed reports within the archive
window (2018-06-04 onward), the next escalation is to pick a different,
more actively-observed real NEO rather than continuing to chase this
specific object.

### Handoff state as of 2026-07-02 v30

**Gate Z3 known-object positive control loader/runner built (v0.90.42)** —
`Skills/run_archive_positive_control.py` loads real per-source
`Observation` objects from >=2 nights' `ztf_alert_archive_ingest.py`
checkpoint files and runs the exact production `preprocess()` ->
`detect()` -> `link()` chain (matching `run_pipeline.py`'s call pattern),
reporting whether the linker recovers a real multi-night tracklet.
Diagnostic only — never claims "confirmed NEO."

**Real finding from offline verification**: using the exact synthetic
generator already proven in `Skills/injection_recovery.py`'s 100%-link
baseline, 20/20 seeds with a 2-night, 2-obs-per-night tracklet FAILED to
link at `link()`'s default `min_observations=3`, but 20/20 linked
successfully at `min_observations=2`. This is not a fundamental "2 nights
can't work" limitation — it's specifically that too few observations per
night in the final linked arc trip the default threshold. Real archived
data has far more observations per night (21 on night 20180809 alone), so
the default is likely fine, but `--min-observations` is exposed so a
zero-tracklet result can be re-checked before concluding failure. 5 new
tests, all passing, including one exercising the real production chain
end-to-end and one regression-testing this exact finding.

**Next production action (NOT YET DONE)**: this depends on the pending
night 20180903 alert-archive ingest (see v29 below — not yet run). Once
that completes:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20180809 20180903 \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

If this reports zero tracklets, re-run with `--min-observations 2` before
concluding the positive control failed.

### Handoff state as of 2026-07-02 v29

**Real second night found at object 72966's actual predicted position** ✓
— operator ran `Skills/scan_neo_track_coverage.py` (stride=5, 100-day
window). Real result: 2 of 21 checked nights had real ZTF coverage near
the object's real predicted position — night 20180809 (already known) and
**night 20180903** (new: RA 242.0130, Dec -11.6968, 6 real sci exposure
rows). This is the first real, non-guessed second night found via
targeted ephemeris-based scanning, after two prior blind field-revisit
attempts (nights 20180810, 20180902) both failed. Full evidence:
`docs/evidence/live/2026-07-02-gate-z3-track-coverage-scan-hit.md`.

**Next production action (NOT YET DONE)**: run the alert-archive ingest
tool against night 20180903, centered on this night's real predicted
position:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180903 \
    --ra 242.0130 --dec -11.6968 --radius-deg 2.0 --min-rb 0.5
```

Night 20180809's cached data (21 kept, from RA 232.6/Dec -8.4, within
~0.05 deg of 72966's real predicted position that night) already covers
this object and needs no re-fetch. If night 20180903 also yields >=1 kept
observation, this project will have real per-source detections on 2 real
nights for the first time — the next step after that (not yet built) is
loading both checkpoints through `src/detect.py` -> `src/link.py` for
Gate Z3's "known-object positive control."

### Handoff state as of 2026-07-02 v28

**Real ephemeris for NEO 72966 explains the second attempt's miss — it was
a targeting error, not a cadence finding** ✓ — operator ran
`Skills/lookup_neo_archive_ephemeris.py` (RA/Dec query for designation
72966, 100-day window from night 20180809). Real result: 101 ephemeris
points; night 20180809's predicted position (RA 232.5584, Dec -8.4239)
matches the already-confirmed real detection within 0.05 deg (validates
the tool). By night 20180902, the real predicted position had moved to
RA 241.5899, Dec -11.5706 — about 9.4 deg in RA and 3.2 deg in Dec away
from the original fixed 2-degree search box used in the second alert-
archive attempt. The earlier Gate Z1 "hit" for that night was a
coincidental revisit of the *original* field, unrelated to where the
object actually was — the zero-kept alert-archive result was a targeting
error (wrong sky position), not further evidence about that field's
cadence. Full evidence:
`docs/evidence/live/2026-07-02-neo-72966-ephemeris-and-targeting-error.md`.

**New tool (v0.90.41)**: `Skills/scan_neo_track_coverage.py` fixes the
targeting error going forward — for a bounded, stride-limited subset of
real ephemeris points, it re-centers the cheap Gate Z1 metadata check on
that specific night's real predicted position (not a stale fixed field),
reporting which real nights have real ZTF coverage near where the object
actually was. Offline-tested (4 tests, mocked); not yet run live.

**Next production action (NOT YET DONE)**: run the track-coverage scan
before spending bandwidth on another multi-GB alert-archive download:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_neo_track_coverage.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d --stride 5
```

This issues 21 cheap Gate Z1 metadata queries (1 per 5 real nights) at the
object's real predicted position for each, reporting which nights (if
any) show real ZTF science exposure there. Only run
`Skills/ztf_alert_archive_ingest.py` against a night this scan confirms
has real coverage, using that night's predicted RA/Dec as the search
center — not the original fixed field.

### Handoff state as of 2026-07-02 v27

**Second real alert-archive attempt (nights 20180809/20180902, the
corrected pair) came back empty on night 2** — night 20180809 resumed
from cache (21 kept, unchanged); night 20180902 downloaded 8.5GiB, scanned
192,243 real packets over 7m09s with correct live progress/ETA throughout
(confirms v0.90.36 and v0.90.39 both work together on a real, large file),
but kept 0 despite a confirmed real ZTF exposure that night (per Gate Z1
metadata). This is a genuine negative, not a bug. Full evidence:
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-second-attempt.md`.

**Two real multi-GB downloads (5.3GiB + 8.5GiB) via blind field-revisit
sampling have now produced zero net progress** toward a linkable 2-night
detection pair. Blind guessing more individual nights is no longer the
recommended approach.

**New tool (v0.90.40)**: `Skills/lookup_neo_archive_ephemeris.py` replaces
blind guessing with a targeted approach — queries the Phase-0-verified
JPL Horizons endpoint (`src/fetch.py:fetch_horizons`, already 100%-covered
production code) for a real, known minor planet's real predicted sky
position across a date range. Default designation `72966` is the real
`ssnamenr` cross-match already present in a real Gate Z3 alert packet —
not a guess. Wraps `fetch_horizons` in its own retry-with-backoff (the
underlying function has none) and reuses the v0.90.39 full-precision
JD-to-date conversion. Offline-tested (4 tests, all mocked); not yet run
live (no live network in this sandbox).

**Next production action (NOT YET DONE)**: operator runs the ephemeris
lookup tool, then cross-checks a couple of the reported real nights
against the cheap Gate Z1 metadata tool (centered on the object's
predicted position) before committing to another multi-GB alert-archive
download:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/lookup_neo_archive_ephemeris.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d
```

### Handoff state as of 2026-07-02 v26

**Real off-by-one bug found and fixed in the v0.90.38 night-date output**
— the first real run of the fixed metadata report printed
`['20180808', '20180902']`, but `20180808` contradicted already-established
ground truth (a packet with that exact `obsjd` was already confirmed, via
direct download in an earlier gate, to originate in the real archive file
`ztf_public_20180809.tar.gz`). Root cause: JD increments at noon UTC, not
midnight; the code truncated `obsjd` to an integer before converting to a
calendar date, which silently lands on the day *before* the correct date
whenever the fractional part is < 0.5. Fixed in v0.90.39 by deriving each
row's date from its full, un-truncated `obsjd`. Regression-tested with the
exact real value that exposed the bug. Full evidence:
`docs/evidence/live/2026-07-02-gate-z1-night-date-offbyone-fix.md`.

**Corrected real result**: this sky position's two real observing nights
within the 100-day window are **20180809** (not 20180808) and **20180902**
— about 24 days apart. The underlying real data (14 rows, 2 nights, 1
field) was always correct; only the calendar-date labels were wrong.

**Next production action (NOT YET DONE)**: target the alert-archive ingest
tool at the corrected real night pair:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180809 20180902 \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

Night 20180809 is already cached locally (21 kept observations from the
first Gate Z3 run) and will resume without re-download; only 20180902
needs a fresh fetch.

### Handoff state as of 2026-07-02 v25

**Recurring operational note**: on this operator's Mac, `uv run` locally
rewrites `uv.lock`'s own `neo-detection` self-version pin after nearly
every invocation, leaving an uncommitted local diff. Since every recent PR
also bumps `pyproject.toml`'s version (and therefore `uv.lock` to match),
the next `git pull origin main` reliably fails with "Your local changes to
... uv.lock would be overwritten by merge" unless that local diff is
cleared first. This has now happened twice (before the v0.90.35 and
v0.90.38 commands). Going forward, **always prepend
`git checkout -- uv.lock` before `git pull origin main`** in operator
command blocks for this project — the local diff is machine-generated
lockfile drift, never manual operator edits, so discarding it is always
safe.

**Real second night found at the Gate Z3 target field** ✓ — operator ran
the widened 100-day Gate Z1 metadata query (RA 232.6, Dec -8.4, JD
2458339.5-2458439.5). Real result: 14 rows across 2 distinct real nights,
1 field. First real evidence that this field is revisited (just far less
often than every 3 nights). Evidence:
`docs/evidence/live/2026-07-02-gate-z1-wider-window-second-night.md`.

**Follow-up fix (v0.90.38)**: the report only exposed `n_distinct_nights`
as a bare count, not which real nights they were — a real gap blocking
the very next step (targeting the alert-archive ingest tool at the actual
second night). Added `distinct_nights_yyyymmdd` to the report, converting
each `obsjd` to a real UTC calendar date matching the archive's
`ztf_public_YYYYMMDD.tar.gz` naming convention. Computed from the
already-cached raw IPAC response on the operator's machine — re-running
the identical command resumes from checkpoint and re-derives the report
with **no new network call**. Regression-tested in
`tests/test_ztf_dr24_bounded_ingest.py` (1 new test, 10 total, all pass).

**Next production action (NOT YET DONE)**: re-run the identical command to
read the real night-date list, then target the alert-archive ingest tool
at those two real nights:

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 2.0 \
    --start-jd 2458339.5 --end-jd 2458439.5
```

Read the printed `[ingest] Distinct real nights (YYYYMMDD): [...]` line,
then run:

```bash
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights <night1> <night2> \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

substituting the two real dates from the metadata report. This is the
first real, non-guessed night pair confirmed to both have coverage at this
sky position — the "known-object positive control" detect.py→link.py
loader/runner still should not be built until this run produces real
detections on both nights.

### Handoff state as of 2026-07-02 v24

**Gate Z1 CLOSED — first live run against the real IRSA sci-metadata
endpoint** ✓ — operator ran `Skills/ztf_dr24_bounded_ingest.py` (RA 232.6,
Dec -8.4, 2 deg box, 10-day window from night 20180809). Real result: 5
rows, 1 distinct night, 1 distinct field. This is a genuine, non-mocked
live result and closes Gate Z1's "pending operator live verification"
status. Full evidence:
`docs/evidence/live/2026-07-02-gate-z1-bounded-ingest-first-live-run.md`.

**Root cause of the Gate Z3 zero-match nights, now confirmed rather than
inferred**: the 1-distinct-night result above proves ZTF took no science
exposures at all at this exact sky position on nights 20180810 or 20180812
— it's not a linking bug, not a filter bug, and not bad luck within the
documented ~3-night cadence; this specific field genuinely was not
revisited in that window. Blindly trying more individual nights against
the multi-GB alert archive is no longer the right move.

**Also fixed this handoff**: the operator's `git pull origin main` was
initially blocked by a local `uv.lock` diff (machine-generated by `uv run`
locally, not manual edits) conflicting with the `uv.lock` regenerated in
PR #173. Resolved with `git checkout -- uv.lock` before pulling — no code
or dependency-version change was lost, this is expected lockfile drift
between environments, not a real conflict.

**Next production action (NOT YET DONE)**: use the now-verified Gate Z1
tool with a wider (100-day, still bounded) window to find this field's
real revisit cadence before downloading more alert-archive nights:

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_dr24_bounded_ingest.py \
    --ra 232.6 --dec -8.4 --size-deg 2.0 \
    --start-jd 2458339.5 --end-jd 2458439.5
```

Read the resulting `n_distinct_nights` and the raw IPAC table's `obsjd`
column values to pick real candidate nights for the next
`ztf_alert_archive_ingest.py` run — do not guess another night without
this metadata first.

### Handoff state as of 2026-07-02 v23

**First live run of the Gate Z3 ingest tool — real archive data obtained** ✓
— operator ran the (pre-v0.90.36) ingest command against real nights
20180809/20180810. Results: night 20180809 (31.0MiB, 715 real packets)
scanned in 3s, kept 21 real observations inside the 2-degree sky box with
`rb >= 0.5`; night 20180810 (5.3GiB, 119,815 real packets) scanned in
4m47s, kept 0 — no revisit of the same sky patch that night. This is a
legitimate negative, not a bug: ZTF's documented cadence is ~3 nights per
field, not nightly. Full evidence:
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-first-live-run.md`.

This run also produced **live confirmation** of the progress-silence bug
fixed in v0.90.36 (PR #173, merged): the 4m47s/119,815-record scan of night
2 printed zero progress lines, exactly matching the defect diagnosed from
code inspection alone before this run. No further action needed on that
fix — it is already merged and regression-tested.

`docs/ZTF_DR24_PRODUCTION_GATES.md`'s Gate Z3 row and "Next Coding Step"
updated: the ingest tool is now confirmed working against the real
archive; the ONLY remaining Z3 blocker is finding 2 real nights with
detections in the same sky box so `src/link.py` has cross-night pairs.

**Next production action (NOT YET DONE)**: retry with a night spaced by
ZTF's actual ~3-night cadence instead of night+1, same sky box:

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180809 20180812 \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

Do not build the detect.py -> link.py loader/runner for the "known-object
positive control" until a run produces real detections on >=2 nights in
the same sky box — there is nothing to link otherwise.

### Handoff state as of 2026-07-02 v22

**System Directive compliance fix for the Gate Z3 ingest tool (v0.90.36)** —
operator flagged before running v0.90.35's `Skills/ztf_alert_archive_ingest.py`
that its progress print was not System Directive compliant: the print was
placed after the real-bogus and sky-box filter `continue` statements inside
the per-record loop, so it only fired for records that passed both filters.
With the documented operator command's narrow 2-degree sky box, the
overwhelming majority of scanned records would never reach that line —
progress could go completely silent for the length of a whole night's
archive file (which can be up to 73G) even while actively scanning. Fixed
by moving the progress print to fire immediately after `scanned += 1`,
before any filter `continue`, so it now fires deterministically every
`_PROGRESS_EVERY` (500) scanned records regardless of filter outcome.

Added `tests/test_ztf_alert_archive_ingest.py` (5 tests, new file — this
script previously had no committed tests, only ad hoc sandbox verification):
two tests build synthetic archives where every record fails the sky-box or
real-bogus filter respectively and assert progress still prints at the
expected `scanned` counts (these would have caught the bug), plus filtering/
field-mapping and checkpoint/resume coverage. All pass locally (via a
sandbox-only `typing._eval_type` shim needed for this environment's
Python 3.14.0rc2 vs. the pinned 3.14.3 — not a code issue, not committed).

This was caught before any live operator run consumed real archive data, so
no wasted download occurred. The operator command is unchanged and now
correctly compliant:

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180809 20180810 \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

**Next production action (NOT YET DONE)**: operator runs the ingest tool
above against 2 real nights. Then a follow-up step (not yet built) loads
the resulting checkpoint JSON and runs it through `src/detect.py` ->
`src/link.py` for Z3's "known-object positive control" — do not build that
follow-up step until the ingest tool itself has been confirmed working
against the real archive first.

### Handoff state as of 2026-07-02 v21

**Bounded multi-night ingest tool built for Gate Z3** —
`Skills/ztf_alert_archive_ingest.py` (v0.90.35) builds real `Observation`
objects from real UW ZTF alert archive detections, using only the field
names confirmed live in the v20 handoff (`ra`/`dec`/`jd`/`magpsf`/
`sigmapsf`/`fid`-mapped-to-band/`rb`/`field`/`diffmaglim`; cutouts left
unmapped since their AVRO structure is unverified). Streams each night's
archive file directly through gzip/tar decode (never buffers a full night,
up to 73G) with a real-bogus threshold and optional sky-box filter applied
per-record, checkpointed per night, retried with backoff, bounded to at
most 10 nights per invocation. Verified offline against a synthetic
archive matching the real schema: sky-box filtering, real-bogus filtering,
and Observation field mapping all confirmed correct; the exact real field
values from the v19/v20 handoffs were confirmed to construct a valid
`Observation` object.

**Not yet run against the real archive** (no live internet access in this
sandbox). `docs/ZTF_DR24_PRODUCTION_GATES.md`'s Gate Z3 row and "Next
Coding Step" updated with the operator command and rationale (sky box
centered on the real position already confirmed present in
`ztf_public_20180809.tar.gz`, so a first run is guaranteed at least one
match).

**Next production action (NOT YET DONE)**: operator runs the ingest tool
against 2 real nights, then a follow-up step (not yet built) loads the
resulting checkpoint JSON and runs it through `src/detect.py` ->
`src/link.py` for Z3's "known-object positive control" — do not build that
follow-up step until the ingest tool itself has been confirmed working
against the real archive first.

```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180809 20180810 \
    --ra 232.6 --dec -8.4 --radius-deg 2.0 --min-rb 0.5
```

### Handoff state as of 2026-07-02 v20

**Real-bogus field name confirmed: `rb`, not `drb`** — operator ran
`Skills/probe_ztf_alert_archive_file.py --inspect-first-packet --dump-all-fields`
on `main` @ v0.90.33, dumping all 100 real `candidate` fields from the
checked packet. `rb: 0.7766666412353516` is present; **`drb` is absent
entirely** from this 2018-era packet's schema (`rbversion: 't8_f5_c3'`).
Any Gate Z3 ingest tool must use `rb` and must not assume `drb` availability
without checking `schemavsn` first.

**Unplanned finding, flagged for future research, NOT wired in yet**: the
packet already contains ZTF's own solar-system cross-match fields
(`ssnamenr: '72966'`, `ssdistnr: 1.0`, `ssmagnr: 19.5`) — this specific
detection was already matched to a known minor planet by ZTF's own
pipeline at alert-generation time. This *could* simplify Gate Z2's
known-object exclusion, but must NOT be used for that purpose without first
researching the cross-match catalog's provenance and update cadence
relative to the no-future-leakage requirement — `src/known_object_exclusion.py`'s
existing JPL SBDB `first_obs` approach remains the only currently-verified
mechanism. Full details:
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`.
`docs/ZTF_DR24_PRODUCTION_GATES.md`'s "Next Coding Step" updated with the
confirmed field names.

**Next production action (NOT YET DONE)**: design and build the bounded,
checkpointed, multi-night real-detection ingest tool described in
`docs/ZTF_DR24_PRODUCTION_GATES.md`'s Next Coding Step — this is now
unblocked on all fronts (source verified, schema verified, field names
confirmed). Do not research the SSO cross-match provenance question unless
explicitly asked; it's a documented future optimization, not blocking
current work.

### Handoff state as of 2026-07-02 v19

**Gate Z3 source-verification blocker CLOSED** ✓ — operator ran
`Skills/probe_ztf_alert_archive_file.py --inspect-first-packet` on `main` @
v0.90.31 and it succeeded completely: all six researched schema fields
(`ra`, `dec`, `jd`, `magpsf`, `sigmapsf`, `fid`) confirmed present with real
values in a real downloaded ZTF alert packet
(`ztf_public_20180809.tar.gz`/`585152193615015014.avro`). The packet
contains far more than checked — 100 total `candidate` fields, plus real
`cutoutScience`/`cutoutTemplate`/`cutoutDifference` image triplets (directly
usable by `classify.py`'s existing Tier 2 CNN input format) and
`prv_candidates` prior-detection history. Full evidence with the real
observed values table:
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`.

`docs/ZTF_DR24_PRODUCTION_GATES.md` Gate Z3 row and "Next Coding Step"
updated to reflect this: the long-standing "verified per-source ZTF DR24
detection source" blocker is resolved. **Gate Z3 is NOT fully closed** —
what's still open: a bounded, checkpointed, multi-night real-detection
ingest tool (the current probe only verifies one file), and a real
known-object positive control (linking real alerts across ≥2 real archived
nights into a tracklet through the existing `src/link.py`, matching a
documented known NEO). Nightly file sizes vary up to 73G, so any multi-night
ingest tool must stream-parse and filter, not naively download whole nights.

**Next production action (NOT YET DONE)**: design and build the bounded
multi-night ingest tool described above. Before using any field beyond the
six already confirmed (e.g. `rb`/`drb` real-bogus scores, very likely
present among the packet's other 94 unlisted `candidate` fields), confirm
its exact field name from a real packet — do not assume the name matches
other ZTF documentation without checking.

### Handoff state as of 2026-07-02 v18

**Gate Z3 UW alert archive candidate: CONFIRMED WORKING END-TO-END** ✓ —
operator ran `Skills/probe_ztf_alert_archive_file.py` on `main` @ v0.90.30
and it succeeded completely: downloaded the real 31MiB
`ztf_public_20180809.tar.gz` in ~3s with visible progress/ETA, confirmed it
is a valid gzip/tar archive containing **715 real `.avro` alert packets**
with plausible ZTF `candid`-style numeric filenames. This is not a
placeholder or error page — it is a genuine per-night archive of real
per-detection alert data. Full evidence:
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`.

**v0.90.31**: added `--inspect-first-packet` to the same probe script,
which parses one real `.avro` member with `fastavro` (new dependency,
added because it's the same library the official
`ZwickyTransientFacility/ztf-avro-alert` repo's own example notebook uses)
and prints the `candidate` record's field names/values, to confirm the
real schema contains `ra`/`dec`/`jd`/`magpsf`/`sigmapsf`/`fid` as researched
rather than guessed. Verified locally in the sandbox against a synthetic
AVRO packet built with the exact researched schema — the parsing logic
correctly extracts and reports all six expected fields. **Not yet run
against the real downloaded file** (this sandbox has no live internet
access; the operator's already-downloaded file at
`Logs/pipeline_runs/ztf_alert_archive_probe/ztf_public_20180809.tar.gz`
will be reused via the existing checkpoint/resume logic, no re-download
needed).

**Next production action (NOT YET DONE)**: operator re-runs the probe with
`--inspect-first-packet` to confirm the real schema. If confirmed, Gate Z3's
candidate-source verification is essentially complete, and the next work
becomes designing an actual bounded, checkpointed Gate Z3 ingest tool
(single bounded night or small multi-night window, with the file-size
volume risk already documented — up to 73G for a single night) — do not
skip ahead to that design before this schema confirmation lands.

```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/probe_ztf_alert_archive_file.py --inspect-first-packet
```

### Handoff state as of 2026-07-02 v17

**Gate Z3 UW alert archive candidate: real file listing confirmed** — the
operator opened `https://ztf.uw.edu/alerts/public/` in a browser and saved
the full directory listing as a PDF (139 pages, committed at
`docs/Alert Archive.pdf`, commit `b6de270`). This confirms, from direct
observation (not a guess, not a WebSearch summary):
- **Real file naming convention**: `ztf_public_YYYYMMDD.tar.gz`, one file
  per UTC night, with occasional `_programid3` variants.
- **Real coverage**: `ztf_public_20180601.tar.gz` through
  `ztf_public_20260702.tar.gz` ("10 hours ago" at capture time) — essentially
  the full ZTF survey era, gapless-looking.
- **Real file sizes**: highly variable, from placeholder-looking `44`/`74`
  byte entries up to `ztf_public_20181113.tar.gz` at **73G**. This is a
  genuine firehose; multi-night ingest windows must be sized carefully.
- **No authentication barrier visible**, consistent with the earlier HTTP
  200 unauthenticated probe result.
- `MD5SUMS` file present and actively updated (10 hours old at capture).

Added `Skills/probe_ztf_alert_archive_file.py` (v0.90.30): a bounded,
checkpointed, single-file download-and-verify probe (default target:
`ztf_public_20180809.tar.gz`, 31M — one of the smallest genuinely-sized
files in the listing). Downloads exactly one file, verifies it's a real
gzip/tar archive, lists `.avro` member names — does NOT extract or parse
AVRO content (no new parsing dependency added yet; that's later work once
the tar structure itself is confirmed live). Full trail:
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`.

**Next production action (NOT YET DONE)**: operator runs
`Skills/probe_ztf_alert_archive_file.py` to confirm the tar/AVRO structure
of one real file live. Only after that succeeds should any AVRO-parsing
dependency or Gate Z3 ingest-tool design be proposed — do not skip ahead
to multi-night ingest design before this single-file check passes.

```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/probe_ztf_alert_archive_file.py
```

### Handoff state as of 2026-07-02 v16

**Gate Z3 new candidate source found reachable (2026-07-02)** — the
University of Washington's public ZTF alert archive
(`https://ztf.uw.edu/alerts/public/`) was probed live by the operator via
`Skills/verify_ztf_dr24_sources.py` (new probe id
`uw_ztf_alert_archive_listing`, added in the docs-only PR #166) and returned
**HTTP 200, no authentication required**. The response body matches prior
WebSearch research word-for-word: a bulk, static, historical (not
live-stream) tar-per-UTC-night archive of the full unfiltered 5-sigma ZTF
alert stream since 2018-06-04, in AVRO format, with per-packet `ra`, `dec`,
`jd`, `magpsf`, `sigmapsf` fields from real difference-image detections —
i.e. genuine per-epoch positions capable of representing a moving tracklet,
unlike IRSA's coadd-keyed Objects/Lightcurves catalogs (see
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md` for
the full research trail and why those standard IRSA products cannot close
Gate Z3). Raw probe response committed at `f3dc9c24`
(`docs/evidence/phase0/phase0_probe_results.json`).

### Handoff state as of 2026-07-02 v15

**classify() hang CONFIRMED RESOLVED (v0.90.29)** ✓ — operator re-ran the
Gate Z3 recheck command on `main` and it completed cleanly: 200/200
injection-recovery items in 5s (no hang, no heartbeat needed — model files
were already locally cached), 100% detection/link/score rate, and
`Skills/adversarial_review.py --offline` correctly processed all 200 full
review packets (`SURVIVE=0 BORDERLINE=0 REJECT=200` — expected for synthetic
short-arc injections with no fitted orbit, not a defect). Full evidence:
`docs/evidence/prod-loop/2026-07-02-classify-hang-root-cause-resolved.md`.
This closes out the multi-session hang-diagnosis saga (v0.90.23 → v0.90.24 →
v0.90.28 → v0.90.29); the true root cause was `_load_xgb_model()`'s
unprotected file read, not the CNN loader that was patched twice before it.
**This does NOT close Gate Z3** — it's a synthetic-data pipeline-mechanics
confirmation, not real ZTF DR24 archival data. Gate Z3's real blocker is
unchanged: a verified per-source ZTF DR24 detection source (Gate Z1 only
fetches image metadata today).

**Next production action**: resume Gate Z3 source verification — research
a documented, officially-verified public API for real per-source ZTF DR24
moving-object detections (not the ALeRCE static-lightcurve endpoint already
ruled insufficient in `docs/evidence/phase0/alerce_source_detection_assessment.md`,
and not the Gate Z1 image-metadata-only endpoint). Do not invent or guess an
endpoint; if no verified source can be found without live network access
this sandbox lacks, delegate the lookup to the operator's research agent or
ask the operator to verify a specific candidate URL/API before any ingestion
code is written against it.

### Handoff state as of 2026-07-02 v14

**v0.90.24's CNN-warmup fix (PR #163) did NOT resolve the injection_recovery
hang — root cause was misdiagnosed until per-stage diagnostic prints
isolated it.** After PR #163 merged, the operator re-ran the Gate Z3
recheck command and hit the same hang at item (1/200) with zero output —
critically, not even a single heartbeat line from the PR #163 CNN warmup
fix. Per the standing rule ("failed fix → re-diagnose, not re-patch"), this
proved that fix's diagnosis was wrong, not just insufficient. Rather than
patching `_load_cnn_model()` a third time, added temporary per-stage print
statements around every call inside `run_injection_recovery()`'s loop
(`detect()`, `link()`, `extract_features()`, `fit_orbit()`, `classify()`,
`score()`). The operator's next run showed execution reaching
`classify()` and then producing zero further output — isolating the hang
to inside `classify()`, before Tier 2's CNN is ever reached.

**True root cause**: `_load_xgb_model()` (Tier 1) called
`clf.load_model(str(model_path))` — a bare path-based read with **zero**
chunked pre-read, heartbeat, or print statement of any kind. `_tier1_predict()`
runs first inside `classify()`, before Tier 2 (CNN) or Tier 3 (Transformer),
so this unprotected read blocked before any of PR #163's CNN deadlock
mitigations were ever executed — explaining the zero-heartbeat symptom.
`_load_transformer_model()` had the identical unprotected-read bug and
would have caused the same hang on any tracklet reaching Tier 3 without
Tier 2 cutouts first.

**v0.90.28 fix**: added a shared `_read_file_with_heartbeat()` helper
(64 KB chunked reads + heartbeat thread, same pattern already proven for
the CNN loader) and applied it to both `_load_xgb_model()` (now passes
xgboost a `bytearray` instead of a path) and `_load_transformer_model()`
(now pre-reads into `BytesIO` plus its own independent matmul warmup,
since it cannot assume Tier 2 already ran). Removed the temporary
diagnostic prints from `injection_recovery.py` now that the root cause is
fixed. Verified in the sandbox: `_load_xgb_model()` loads the real
committed `models/tier1_xgb.json` correctly via the new bytearray path
(`n_classes_=5`, confirmed with `pip install xgboost scikit-learn`).
`_load_transformer_model()`'s new code path was exercised through
`_read_file_with_heartbeat()` but this sandbox has no `torch` install
(network-restricted, install times out) and cannot exercise the real
macOS-specific ATen deadlock — that part remains unverified until the
operator's next real run.

**Predicted operator console output after this fix**: after
`[injection] (1/200) ...`, the console should show either (a) rapid
progression through all 200 items with no further prints (if the XGBoost
model file was already fully synced locally), or (b) a
`  reading Tier 1 XGBoost model … still working (0m05s elapsed)` heartbeat
line every 5 seconds if the file read is genuinely slow (e.g. Dropbox not
yet fully synced), followed by progression once the read completes. If the
console instead shows nothing at all — not even that heartbeat — for
several minutes, the cause is something even earlier than `_load_xgb_model()`
itself (e.g. the bare `import xgboost` statement's native library load) and
needs fresh re-diagnosis from this new symptom, not another patch to
`_load_xgb_model()` or `_load_transformer_model()`.

**Next operator action**: re-run the Gate Z3 recheck command from `main`
after this PR merges and paste the console output.

### Handoff state as of 2026-07-02 v13

**Current merged state through PR #163**:

- v0.90.20 added the bounded, checkpointed IRSA ZTF DR24 image-metadata ingest
  tool. It is offline tested and awaits one operator live verification run.
- v0.90.21 added fail-closed, time-aware known-object exclusion using
  documented `first_obs` evidence. It awaits operator live confirmation that
  the already-verified JPL SBDB `sb-group=neo` query returns real `first_obs`
  dates.
- v0.90.22 corrected Gate Z3: `src/link.py` already supplies the
  Fink-FAT-style linear tracklet linker; the real blocker is not linker code
  but verified per-source ZTF DR24 detections (RA, Dec, time, magnitude).
- v0.90.23 added visible progress to injection recovery so long model-load
  gaps are not silent.
- v0.90.24 ported missing macOS CNN-load warmups into `src/classify.py`. The
  sandbox can only verify the code path on Linux; one operator Mac re-run is
  required to field-confirm the deadlock fix.
- v0.90.25 synchronized handoff docs and the production loop ledger.
- v0.90.26 clarified that legacy ALeRCE source-level ZTF support does not
  close current DR24 Gate Z3 without explicit verification for historical
  replay.
- v0.90.27 adds the ALeRCE source-detection assessment under
  `docs/evidence/phase0/`; official ALeRCE docs verify source-level detection
  fields but do not prove DR24 static-archive or no-future-leakage suitability.
  The next coding work is Gate Z3 source verification for per-source ZTF DR24
  detections using official docs or live evidence only; no guessed endpoints,
  schemas, coordinates, or request bodies.

### Handoff state as of 2026-07-02 v12

**Phase 0 source verification is materially complete except for the external
Fink TLS blocker.** The current committed evidence packet is
`docs/evidence/phase0/`:

- `data_sources_verified.md`: JPL SBDB, MPC get-obs, and IRSA ZTF metadata
  returned HTTP 200 in real operator-observed runs. Fink schema/swagger still
  fail before HTTP response during TLS handshake.
- `auth_requirements.md`: JPL/MPC/IRSA required no credentials for the tested
  read-only calls. Fink auth remains unknown because no HTTP response was
  reached.
- `phase0_probe_results.json`: raw captured headers/body previews; MPC
  get-obs uses GET with JSON body `{"desigs": ["433"]}` and JPL SBDB uses
  `sb-group=neo`.
- `schema_snapshot/README.md`, `sample_ingest_report.md`, and
  `pretrained_model_audit.md` complete the brief's required Phase 0 artifact
  set without inventing ingestion or approving pretrained models.
- `2026-07-02-root-cause-findings.md`: root causes recorded. JPL `neo=Y` was
  invalid, MPC get-obs requires a JSON body, Fink is external, and v0.90.17
  fixed stale checkpoint reuse by hashing full probe definitions.

**Next production action**: work Gate Z1 from
`docs/ZTF_DR24_PRODUCTION_GATES.md` by building Phase 1 as a bounded prototype:
IRSA ZTF metadata access, time-aware known-object exclusion, Fink-FAT-style
linear linking, handcrafted features, and a logistic-regression baseline before
LightGBM/XGBoost. Do not block on Fink unless the specific Phase 1 task needs
Fink schema access; use the verified IRSA/JPL/MPC path first.

### Handoff state as of 2026-07-02 v9

**Root cause found and fixed for JPL SBDB; MPC narrowed; Fink is external** —
see `docs/evidence/phase0/2026-07-02-root-cause-findings.md` for full detail.
Every finding below is from a real command the operator ran, not
documentation review (this sandbox cannot reach these domains directly).

- **JPL SBDB — FIXED**: the brief's `neo=Y` filter parameter is rejected by
  the live API (HTTP 400, "query parameter was not recognized"). Operator
  `curl` confirmed `sb-group=neo` is the correct filter — returned real NEO
  records (433 Eros, 719 Albert, 887 Alinda, all `class: AMO`, count 42,153
  vs. 1,556,924 for the unfiltered query). `Skills/verify_ztf_dr24_sources.py`
  and `docs/neo_discovery_agent_brief.md` both corrected to use
  `sb-group=neo`.
- **MPC get-obs — fixed in v0.90.16**: the API needs an actual JSON request
  body even for GET. Operator verification showed `{"desigs": ["433"]}`
  returns HTTP 200 with ADES observation data; `Skills/verify_ztf_dr24_sources.py`
  now sends that body.
- **Fink API — external blocker, not our bug**: `curl` with the operator's
  native LibreSSL failed identically to Python's `requests` (`SSL_ERROR_SYSCALL`
  immediately after ClientHello, from two independent TLS stacks on the
  operator's real network). This rules out a client-side fix. No code
  change applies; retry later or treat as unavailable for Phase 1.
- **Status update v0.90.18**: MPC is no longer pending. Phase 0 evidence is
  committed; Fink remains the only unavailable source and is external.

### Handoff state as of 2026-07-02 v8

**First live Phase 0 probe run (2026-07-02, operator Mac, `main` @ `d4f3f908`)**:
5 probes run, elapsed 3m23s. Results:
- `irsa_ztf_sci_metadata`: **HTTP 200** — confirmed reachable without
  credentials, matches the brief's claim.
- `jpl_sbdb_neo_query`: **HTTP 400** — server reachable, request rejected.
  Root cause not yet known; need the response body.
- `mpc_get_obs`: **HTTP 501** — server reachable, unusual status for a
  documented GET endpoint. Root cause not yet known; need the response body.
- `fink_schema`, `fink_swagger`: both **FAILED** after 5 retries with
  `SSLError: SSLEOFError` (TLS handshake dropped, not a 4xx). Inconclusive —
  could be a WAF/CDN blocking this TLS client fingerprint, a transient
  outage, or something else. Needs a retry and/or a different client to
  distinguish.
- Full per-probe response bodies were written locally to
  `docs/evidence/phase0/{data_sources_verified.md,auth_requirements.md,
  phase0_probe_results.json}` on the operator's Mac by the script itself but
  were not yet pasted/committed as of this handoff. Console-level summary
  preserved at `docs/evidence/phase0/2026-07-02-first-live-probe-console.md`.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: get the operator to paste or
  commit the three files above so the actual JPL SBDB / MPC response bodies
  can be read and the 400/501 causes diagnosed before adjusting the brief's
  example request URLs or building any ingestion code against them.

### Handoff state as of 2026-07-02 v7

**Phase 0 tool built (v0.90.13)**: `Skills/verify_ztf_dr24_sources.py` probes
the exact endpoints cited in `docs/neo_discovery_agent_brief.md` (Fink
schema/swagger, JPL SBDB NEO query, MPC get-obs, IRSA ZTF image metadata) —
GET-only, checkpoint/resume, retry-with-backoff, writes
`docs/evidence/phase0/data_sources_verified.md` and `auth_requirements.md`
from real observed HTTP responses. This sandbox's network proxy blocks these
domains outright (policy denial at the CONNECT level, confirmed via
`$HTTPS_PROXY/__agentproxy/status`), so the probes could not be run from
here — the operator must run this on their Mac, which has normal internet
access. **Next operator action**: run the command in the handoff-state
message below and paste the output.

### Handoff state as of 2026-07-02 v6 — MAJOR PIVOT

**Operator decision: ZTF DR24 historical replay is now the primary discovery
pipeline, superseding WISE/DECam/TESS.** See `docs/MISSION.md §Operator
Decision (2026-07-02)` for the full authoritative record. Summary:

- `docs/neo_discovery_agent_brief.md` supersedes the 2026-07-01 reconciliation
  that kept WISE/DECam/TESS primary. The brief's own Phase 1 recommendation —
  ZTF DR24 archival historical replay with time-aware known-object exclusion,
  a Fink-FAT-style tracklet linker, and a LightGBM/XGBoost candidate ranker —
  is now the active development target.
- WISE/DECam/TESS code (`fetch_wise_archive`, `fetch_decam_archive`,
  `fetch_tess_ffis`) and all Gate P1–P5 evidence are **preserved, not
  deleted** — they are now a secondary/paused path and a decision record,
  not the thing to build next.
- Live ZTF alert-stream and live ATLAS discovery remain prohibited (still
  circular — ZTF ZAPS/ATLAS already process and submit from those streams in
  real time). This decision does **not** reverse that prohibition. What
  changed is specifically: *archival* ZTF DR24 historical reprocessing is now
  permitted and primary, per the brief's Fink-FAT precedent (111M processed
  ZTF alerts → 389,530 SSO candidates → 327 new orbits, 65 unreported at
  publication — proof that ZTF's own real-time processing does not exhaust
  what's findable in the archive).
- **The existing `docs/PRODUCTION_READINESS.md` P1–P5 gate register describes
  the now-secondary WISE/DECam/TESS pipeline.** Those gates stay CLOSED as a
  historical record but do **not** establish production readiness for the
  new ZTF DR24 pipeline. New gates must be defined for that pipeline before
  claiming it is production-capable. Do not conflate "P1–P5 closed" with
  "the current primary pipeline is production-ready" — it is not yet.
- **Next production action**: Phase 0 source verification per
  `docs/neo_discovery_agent_brief.md` — verify ZTF DR24/public archive
  access, Fink API auth/schema (`swagger.json`), JPL SBDB behavior, and MPC
  observation API behavior; produce `data_sources_verified.md`,
  `auth_requirements.md`, and `pretrained_model_audit.md`. Do not write any
  ingestion code before Phase 0 deliverables exist — this is an explicit
  brief requirement, not optional sequencing.
- **Self-correction note**: an earlier same-session response described the
  production-capability gates (P1–P3, P5 closed) as if that meant the full
  brief's best practices were satisfied. That was a real gap in framing —
  gate closure on the WISE/DECam/TESS path does not imply the brief's model
  (candidate ranker), adapter (JPL SBDB), or completeness-testing
  requirements were met. Future agents: do not repeat that conflation.

### Handoff state as of 2026-07-02 v5

**Correction to the v4 handoff below (operator-flagged 2026-07-02)**: v4's
description of Gate P4 as something requiring active operator action ("it is
human-gated — Jerome must obtain written MPC confirmation... waiting on
Jerome's Gate P4 correspondence") was wrong in framing, even though the
underlying facts (C51 attribution is unresolved) were accurate. **There is
no candidate yet, so there is nothing to tell MPC and no reason to contact
them.** Gate P4 is **dormant**, not an active to-do for the operator — it
only becomes relevant once a real WISE-sourced candidate survives
adversarial review and operator review (`docs/OPERATOR_GO_NO_GO_RUNBOOK.md`
Step 5). Do not describe Gate P4 as "awaiting operator correspondence" or
similar in future handoffs; it awaits an actual candidate, not operator
action. `docs/PRODUCTION_READINESS.md` Gate P4 and
`docs/OPERATOR_GO_NO_GO_RUNBOOK.md` Step 5 were both corrected to reflect
this. No code changed; this is a documentation/framing fix only.

### Handoff state as of 2026-07-02 v4

**Gate P5 CLOSED (v0.90.10)** ✓ — Operator go/no-go runbook:
- New `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`: one-page flow for the day a real
  candidate appears — review-packet location, the exact
  `Skills/adversarial_review.py` and `Skills/export_ades_report.py` commands
  (verified against the Gate P3 drill, not invented), an operator-review
  checklist, the Gate P4 human-gated MPC-authority check, and the permanent
  forbidden-communications list (no PDCO contact, no impact-probability
  statements, no "confirmed NEO," no lowering `ready_for_submission()` gates).
  States explicitly that `SURVIVE`/`BORDERLINE` means "candidate may be
  reviewed for MPC submission," never a confirmation.
- **Production capability gates P1, P2, P3, P5 are now all CLOSED.** Only
  Gate P4 (MPC submission protocol) remains open, and it is **human-gated**
  — no further coding-agent work can close it. It requires Jerome to obtain
  written MPC confirmation for archival WISE/NEOWISE C51 submission
  authority (see `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents`).
- **Next production action for a coding agent**: with all code-addressable
  production-capability gates closed, the historical v4 next-action framing
  below was later corrected by v5 and superseded by v10. Do not wait on
  Jerome's Gate P4 correspondence today; there is no candidate yet. Current
  work is the ZTF DR24 Phase 1 path described in the v10 handoff above.

### Handoff state as of 2026-07-02 v3

**Gate P3 CLOSED (v0.90.9)** ✓ — No-submission package drill:
- `Skills/injection_recovery.py` gained `--review-packet-out` to write full
  `ScoredNEO` packets from injection runs (same format as
  `Skills/run_pipeline.py --review-packet-out`).
- Drilled a 5-candidate Gate P1 WISE positive-control packet through
  `Skills/adversarial_review.py --offline` (5/5 `REJECT` — expected for a
  synthetic packet with no real/bogus score and a short-arc orbit fit; this
  drills the mechanism, not a submission claim) and
  `Skills/export_ades_report.py` twice: default args (fails closed — WISE
  requires `stn=C51`) and `--obs-code C51` without the confirmation flag
  (fails closed independently — requires
  `--mpc-confirmed-wise-c51-submission`). No `.psv` file was written in
  either case; no network call occurs anywhere in the export path (verified
  by code inspection).
- Evidence: `docs/evidence/prod-loop/2026-07-02-gate-p3-no-submission-drill.md`;
  `docs/PRODUCTION_READINESS.md` Gate P3 marked CLOSED.
- **Historical next action (superseded by v5/v10)**: This section originally
  framed Gate P4 as an active MPC-correspondence task. That framing is no
  longer current; there is no candidate yet, so there is nothing to submit or
  ask MPC about today. Keep the fail-closed submission controls, and follow
  the current ZTF DR24 Phase 1 path above.

### Handoff state as of 2026-07-02 v2

**Gate P2 CLOSED (v0.90.8)** ✓ — Survey-native confidence policy:
- New `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md` documents, per source
  (WISE/DECam/TESS): a source-verification matrix (WISE live-verified across
  many runs; DECam and TESS are code-complete but have **never** been
  live-verified against their real endpoints), the quantitative confidence
  thresholds already enforced in code (motion-rate window, real/bogus gate,
  structural tracklet requirements, satellite-trail rejection, known-object
  exclusion), the no-future-catalog-leakage statement for the current
  live-discovery pipeline, ZTF/Fink/SNAPS reference-only reaffirmation, and
  the pretrained-model-audit requirement (not yet applicable — no third-party
  pretrained model is in production scoring today).
- **Key finding confirmed from code, not assumed**: `score.py:_determine_alert_pathway`
  already fails closed on a missing real/bogus score (`rb is None or rb < 0.90`
  → `internal_candidate`), so every WISE/DECam/TESS candidate is structurally
  barred from `mpc_submission`/`neocp_followup`/`nasa_pdco_notify` regardless
  of any other feature. This is why Gate P1's WISE positive-control packets
  score `hazard_flag: unknown` — that is the correct, already-existing
  fail-closed behavior, not a defect.
- **Key finding — TESS is not a real per-epoch detection source as coded**:
  `fetch_tess_ffis` returns TIC catalog star positions replicated per sector
  epoch, not genuine FFI difference-image detections (`preprocess.py` has zero
  FFI/TESS-specific source-extraction logic). `Skills/run_pipeline.py` now
  prints an operator-visible `[fetch] WARNING` when `--surveys DECam` or
  `--surveys TESS` is selected, pointing to the policy doc. Default surveys
  remains `["WISE"]` only.
- Two items remain explicitly open for future work (not blocking): a WISE
  sentinel-magnitude (`mag=99.0`) rejection filter, and DECam/TESS live
  endpoint verification per the discovery-agent brief's Phase 0.
- **Next production action**: Gate P3 — no-submission package drill from a
  Gate P1 positive-control packet through `Skills/adversarial_review.py`,
  operator review packet generation, and MPC-compatible export
  (`Skills/export_ades_report.py`).

### Handoff state as of 2026-07-02 (v1)

**Discovery-agent brief folded into workflow (v0.90.7)** ✓:
- `docs/neo_discovery_agent_brief.md` is now authoritative workflow guidance
  and must be read at session start.
- Gate P2 must apply the brief's source-verification matrix, no-future-catalog
  leakage rule, historical-replay discipline, pretrained-model audit
  requirement, and auditable candidate-ranker guidance.
- ZTF/Fink/SNAPS are authoritative methodology, benchmark, and ranker-validation
  references, but not an automatic MPC discovery-submission stream unless a
  future documented decision proves a non-duplicative path.

**Gate P1 CLOSED (2026-07-02)** ✓ — WISE/NEOWISE discovery-source positive control:
- `Skills/injection_recovery.py` gained `--survey WISE`: injects a source-native
  NEOWISE-visit-cadence synthetic tracklet (single-epoch W1 exposures over a
  54-hour, 3-distinct-night visit; no native real/bogus score; ~1 arcsec
  astrometric jitter; 0.08 mag photometric noise) through the real production
  `detect.py` discovery-archive singleton path, `link.py`, `classify.py`, and
  `score.py` — not a mocked/parallel path.
- Verified 100% detection/link/score rate (n=50, seed=42) in an isolated
  Python 3.11 sanity venv (this sandbox cannot run the pinned Python 3.14 venv;
  CI is authoritative). Default `--survey ZTF` path unchanged, still matches
  committed `data/injection_recovery_n200.json` baseline (no regression).
- New CI job `wise-injection` in `.github/workflows/e2e.yml` runs the WISE
  positive control on every push/PR and fails closed if `n_linked` or
  `n_scored` drops to 0.
- Evidence: `docs/evidence/prod-loop/2026-07-02-gate-p1-wise-injection-recovery.md`;
  `docs/PRODUCTION_READINESS.md` Gate P1 marked CLOSED.
- **This closes the "no more live WISE runs until P1/P2 supplies a measured
  reason" block from the 2026-06-30 handoff.** Gate P2 (survey-native confidence
  policy) remains open — the WISE positive-control packets score `hazard_flag:
  unknown` because there is no WISE-native real/bogus or quality signal yet.
- **Next production action**: work Gate P2 — document quantitative WISE/DECam/TESS
  confidence thresholds so archive candidates don't rely on absent ZTF-style
  real/bogus evidence. See `docs/PRODUCTION_READINESS.md` Gate P2.

### Handoff state as of 2026-06-30

**v0.90.5 patch status**:
- `Skills/select_survey_fields.py --wise-archive-probes` now enriches ranked
  field selections with dry-run WISE/NEOWISE scale-plan probe commands. These
  commands use `caffeinate -i`, `uv run --python 3.14`, bounded native
  numerical thread settings, `--surveys WISE`, `--force-refresh`, and
  `--link-scale-plan-out`.
- This is the next D1 path after Taurus exhaustion: use the selector to choose a
  new non-Taurus parent field/window and run a scale-plan probe before any full
  diagnostic. Do not hand-pick new WISE coordinates without either selector
  output or a documented field-window rationale.
- Generated commands are dry-run only and do not authorize external submission.
  Run adversarial review only after a pipeline run reports a non-zero full
  `ScoredNEO` review-packet count.
- The selector-generated non-Taurus parent field was live-probed from merged
  `main`: RA `209.64`, Dec `-15.0`, radius `0.2`, JD `2458880.5` to
  `2459250.5`, survey `WISE`. It fetched `16582` WISE rows, passed
  `16558/16582`, detected `16558` singleton candidates, and stopped
  fail-closed at `27845455` estimated seed pairs over the `1000000` budget.
  Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0905-parent-field-probe.md`.
- The rank 1 v0.90.5 support-positive subfield was then run from merged
  `main`: RA `209.5`, Dec `-14.9`, radius `0.0303`. It fetched `690` WISE
  rows, passed `686/690`, detected `686` singleton candidates, linked `58596`
  seed pairs, and produced `0` tracklets and `0` review packets. The pipeline
  correctly instructed the operator to skip adversarial review. This is valid
  diagnostic evidence, not a crash; it is historical context for why the v0.90.6
  WISE positive-control harness was needed to close Gate P1.
- This historical v0.90.5 diagnostic no longer blocks Gate P1; the v0.90.6 WISE
  positive-control harness closed P1. Do not ask the operator for another live
  WISE run until Gate P2 supplies a measured, non-guesswork confidence policy.

**v0.90.4 patch status**:
- `detect.py`, `link.py`, and `Skills/audit_real_run.py` now share the
  adversarial-review hard lower motion floor of `0.05 arcsec/hr`. This prevents
  WISE near-stationary associations from producing review packets that are
  guaranteed to fail D1 on motion-rate grounds.
- `src/background.py` now lazy-loads classify/orbit/score stages so
  metadata-only background CLI commands avoid cold-start subprocess timeouts.
- The Taurus v0.90.3 diagnostic subfields remain exhausted; do not rerun them.
  The next D1 blocker is either a new WISE/NEOWISE field-window strategy likely
  to produce faster non-static candidates, or a defensible WISE-native
  real/bogus/quality policy for archive detections.

**v0.90.3 patch status**:
- `Skills/run_pipeline.py --review-packet-out` now prints the number of full
  `ScoredNEO` packets written. If the count is zero, it prints a fail-closed
  operator instruction to skip adversarial review because an empty packet file
  is not reviewable input.
- `Skills/run_pipeline.py --link-scale-plan-out` now ranks recommended
  diagnostic subfields by local cross-night seed-pair support and records
  `support_metrics` for each recommendation, including whether the subfield can
  support at least three observations across at least two nights inside the
  recommended diagnostic radius.

**v0.90.2 patch status**:
- WISE/NEOWISE ADES export is now fail-closed around MPC authority:
  `stn=C51` is allowed only after written MPC confirmation is recorded, and
  ADES note `Z` is added for archival survey astrometry reported by this
  non-survey pipeline.
- `Skills/run_pipeline.py --link-scale-plan-out` writes a compact JSON scale
  plan when the link seed-pair budget fails closed. The plan now includes a
  budget-derived diagnostic radius, recommended subfield parameters, and
  explicit limitations warning that sky-cell diagnostics are not complete-field
  tiling evidence.
- The operator's 0.2-degree, 370-day WISE scale-plan probe produced
  `11786731` estimated seed pairs over the `1000000` default budget. Dominant
  night pairs: `2459084/2459085` (`9102120` seed pairs) and
  `2459243/2459244` (`2503474` seed pairs).
- The v0.90.2 scale-plan probe on `main` regenerated the full-window stop and
  emitted `recommended_diagnostic_subfields`; durable evidence is
  `docs/evidence/live/2026-06-29-wise-v0902-scale-plan-subfields.md`.
  First subfield: RA `58.1`, Dec `20.1`, radius `0.0466`, JD
  `2458880.5` to `2459250.5`, survey `WISE`.
- The first verified subfield was run by the operator. It fetched `532` WISE
  rows, passed `531/532`, detected `531` singleton candidates, linked `25053`
  seed pairs across `4` nights, and formed `0` tracklets. Candidate and
  review-packet outputs were empty arrays (`[]`). Durable evidence:
  `docs/evidence/live/2026-06-29-wise-v0902-subfield-diagnostic.md`.
- Important correction: do not run `Skills/adversarial_review.py` on
  `--review-packet-out` files until confirming the file contains at least one
  full `ScoredNEO` entry. The first subfield's adversarial-review command
  failed correctly with `ERROR: no valid ScoredNEO entries found in input`
  because no tracklets meant no reviewable packets.
- Expected seed-budget stops now exit cleanly with audit/output artifacts
  instead of printing a Python traceback.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: do not rerun the RA `58.1`, Dec
  `20.1`, radius `0.0466` subfield. The v0.90.3 scale plan has been
  regenerated and recorded at
  `docs/evidence/live/2026-06-30-wise-v0903-scale-plan-support.md`. The next
  verified diagnostic was run: RA `58.1`, Dec `19.9`, radius `0.0466`. It
  produced `701` WISE rows, `3` tracklets, `3` full review packets, and `3/3`
  offline adversarial `REJECT` verdicts. Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0903-subfield-58p1-19p9.md`.
  The rank 2 support-positive diagnostic was also run: RA `57.9`, Dec `20.1`,
  radius `0.0466`. It produced `691` WISE rows, `2` tracklets, `2` full review
  packets, and `2/2` offline adversarial `REJECT` verdicts. Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-20p1.md`.
  The final remaining distinct support-positive diagnostic was then run: RA
  `57.9`, Dec `19.9`, radius `0.0466`. It produced `668` WISE rows, `2`
  tracklets, `2` full review packets, and `2/2` offline adversarial `REJECT`
  verdicts. Durable evidence:
  `docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-19p9.md`.
  **NEXT PRODUCTION ACTION — NOT YET DONE**: do not rerun the Taurus v0.90.3
  diagnostic subfields. The support-positive Taurus loop produced either zero
  tracklets or only adversarial `REJECT` candidates. Move D1 forward by
  selecting a new WISE/NEOWISE field-window strategy likely to produce faster,
  non-static candidates, or by improving WISE-specific filtering/linking before
  the next operator live run.

**Discovery paper goal established (2026-06-26)**:
The project goal is a **defensible discovery paper** — not a methods paper and not a
citizen-science reporting tool. The pipeline generates candidates; two review stages
filter them before any external submission:
  1. **Adversarial review** (`Skills/adversarial_review.py`): automated agent tries
     to REJECT each candidate by finding fatal flaws.
  2. **Operator review** (Jerome): reviews survivors manually.
  3. **MPC submission**: surviving candidates submitted → provisional designation.
  4. **Independent confirmation**: NEOCP follow-up observatories confirm.
  5. **Discovery paper**: documents the find with MPC designation as proof.

**PR #117 MERGED (2026-06-27)** ✓:
- Removed 374 dead helper APIs (v0.40–v0.87 accumulation cycle) and ~2000 tests
- Added `docs/MISSION.md` (authoritative data strategy)
- Added `Skills/adversarial_review.py` (13 offline challenges + 2 live checks)
- Added `tests/test_adversarial_review_skill.py` (50+ cases)
- System directives updated: discovery-paper framing, research brief wiring, accurate
  test counts (1531+), Gate D1 command fixed (no `--surveys ZTF`)
- CI green at 100% coverage on Python 3.14 ✓
- Test count: 1534 passing (1531 + 3 new fallback tests for classify.py)

**System directive alignment complete (2026-06-27)** ✓:
- `CLAUDE.md`: step 5 added (read `docs/near_earth_objects_research_brief.md`),
  WISE/NEOWISE marked as primary discovery target, ZTF/ATLAS as training-only
- `AGENTS.md`: discovery-paper framing, DECISION-001 updated, test counts fixed
- `docs/PRODUCTION_READINESS.md`: research brief wired in, Gate D1 fixed,
  all citizen-science language replaced with discovery-paper language
- `docs/near_earth_objects_research_brief.md`: canonical primer, mandatory session read

**PR #129 MERGED (2026-06-27)** ✓ — Add 30s heartbeat poll loop to pyvo async TAP (progress directive fix):
- Root cause of run 3 silent hang: `tap.run_async(adql)` is a single blocking call with no output — violates System Directive requiring live progress with ETA on all long-running calls.
- Fix: replaced `run_async(adql)` with explicit `submit_job → job.run() → poll loop` that prints `[fetch] WISE IRSA TAP: phase=X  elapsed Xm Xs` every 30 seconds.
- Two new coverage tests for lines 1515 (`_time.sleep(30)`) and 1517 (`raise RuntimeError`) using `update.side_effect` to advance phase state and `patch("time.sleep")` to prevent real delay.
- CI green at 100% coverage, 1576 tests ✓
- **Next operator action**: run live WISE pipeline with `--force-refresh --no-resume` (see Step 5 below); paste stderr showing 30s heartbeat lines and final row count.

**PR #131 MERGED (2026-06-28)** ✓ — Fail closed discovery sweeps and clean WISE masked photometry:
- Root cause of the unsafe operator transcript: the live WISE sweep was run with `--no-dry-run`, so console output said external submissions were enabled even though zero candidates reached alert processing. Discovery sweeps must stay in alert dry-run mode until the MPC observatory-code path is resolved.
- Fix: `Skills/run_pipeline.py` and `src/alert.py` now keep MPC submission fail-closed unless `NEO_MPC_SUBMISSION_APPROVED=1` is intentionally set with a real non-placeholder observatory code. PR #131 also records the Taurus WISE run evidence and handles masked WISE table scalars without converting them to `nan`.
- CI green at 100% coverage, 1583 tests ✓

**PR #133 MERGED (2026-06-28)** ✓ — WISE moving-source prefilter and discovery-archive singleton linking:
- Root cause of the Taurus `535` candidates → `0` tracklets result: `fetch_wise_archive()` queried the broad NEOWISE point-source table using only sky/time constraints, so the result was dominated by static stars/galaxies; `detect()` then required same-night pairs before `link()` saw archive rows, dropping the one-detection-per-visit WISE discovery use case.
- Fix: WISE ADQL selects official IRSA association columns (`sso_flg`, `allwise_cntr`, `n_allwise`, `source_id`) and prefilters to known SSOs plus AllWISE-unmatched rows; `detect()` preserves prefiltered WISE/DECam/TESS archive detections as singleton `RawCandidate` objects for multi-night linking.
- Validation: operator targeted run on Python 3.14.3 passed (`80 passed in 0.86s`; targeted ruff clean; mypy clean across 12 source files). CI initially failed only on missing coverage for the new string-scalar helper; coverage test added, full local pytest passed (`1586 passed, 2 deselected`), and GitHub CI passed before merge.
- Evidence: `docs/evidence/live/2026-06-28-wise-linking-root-cause.md`.
- Follow-up diagnostic from `main` at `2a786e18` reached the pyvo polling path but failed before result retrieval with `AttributeError: 'AsyncTAPJob' object has no attribute 'update'`. Root cause: pyvo 1.9.0 exposes `_update()`/`wait()` but not public `update()`. Evidence: `docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-pyvo-update.md`.
- This pyvo blocker was closed by PR #135; see the next handoff block.

**PR #135 MERGED (2026-06-28)** ✓ — WISE TAP polling compatible with pyvo 1.9.0:
- Root cause of the post-PR #133 diagnostic failure: the installed pyvo 1.9.0 `AsyncTAPJob` exposes `_update()`/`wait()` but not public `update()`, so the explicit WISE heartbeat loop failed before `fetch_result()`.
- Fix: WISE TAP polling now uses public `update()` when present, falls back to one-shot `_update(wait_for_statechange=False, timeout=10.0)`, and preserves explicit heartbeat output instead of using silent blocking `wait()`.
- Validation: WISE fetch tests passed (`20 passed`), targeted ruff clean, mypy clean across 12 source files, full local suite passed (`1590 passed, 2 deselected`), and GitHub CI passed before merge.
- Post-merge diagnostic from `main` at `dd35a8c0` completed: `5206` WISE rows, `5200/5206` preprocessed, `5200` singleton candidates, `0` linked tracklets, `0` candidates processed, dry-run safety intact.
- Evidence: `docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-post-pyvo.md`.
- This was diagnosed after PR #136; see the next handoff block.

**PR #136 MERGED (2026-06-28)** ✓ — Linker rejection diagnostics:
- Linker provenance now records nights, observations, total seed pairs, rate-window seeds, satellite rejects, min-observation/min-night rejects, and chi-square rejects. Checkpoints persist the counters.
- Operator validation before merge: targeted pytest `80 passed`, ruff clean, mypy clean. GitHub CI passed before merge.
- Post-merge bounded WISE rerun from `main` at `b8ca1312`: `5206` rows, `5200/5206` preprocessed, `5200` candidates, `0` tracklets.
- Root cause for this specific run: link diagnostics showed `n_nights=1` and `n_seed_pairs_total=0`, so the 1.0°/7-day Taurus sample is not a multi-night linking test. The linker correctly formed no seed pairs.
- Evidence: `docs/evidence/live/2026-06-28-wise-linker-diagnostics-one-night.md`.
- **NEXT CODE ACTION — NOT YET DONE**: select or probe a WISE field/window that spans at least two integer-JD nights after preprocessing. Do not rerun the same 1.0°/7-day Taurus diagnostic.

**PR #127 MERGED (2026-06-27)** ✓ — Use pyvo async TAP with MJD filter for WISE archive query (SUPERSEDED by PR #129):
- Root cause of run 2 `RemoteDisconnected`: `Irsa.query_region` uses IRSA sync TAP which has a ~60s server-side timeout. `SELECT *` on a 3.5° cone of `neowiser_p1bs_psd` returns millions of rows, hitting that timeout. No ORA-00904 in run 2 confirmed `mjd` IS the correct epoch column name.
- Fix: replaced `Irsa.query_region` with `pyvo.dal.TAPService.run_async(adql)` (async TAP = no timeout) plus explicit `mjd BETWEEN start AND end` in ADQL WHERE clause (pushes time filter server-side)
- Tests updated to mock `pyvo.dal.TAPService` instead of `Irsa.query_region`
- CI green at 100% coverage, 1574 tests ✓

**PR #125 MERGED (2026-06-27)** ✓ — Revert mjd_obs → mjd; remove explicit columns; add column logging (SUPERSEDED by PR #127):
- Root cause of PR #124 failure: `columns='ra,dec,mjd_obs,...'` generated ADQL SELECT that Oracle TAP rejected with `ORA-00904: "MJD_OBS": invalid identifier` — proves epoch column is NOT named `mjd_obs`
- Fix: removed explicit `columns=` parameter (back to SELECT *); reverted `row["mjd_obs"]` → `row["mjd"]`; reverted test mocks to `"mjd"` key
- Added stderr logging: column names and row count logged on successful IRSA query so operator can verify actual column names on next live run
- Updated `Skills/diagnose_wise_query.py` to probe `mjd`, `mjd_obs`, `mjd_obs_w1`, `date_obs` candidates
- CI green at 100% coverage, 1574 tests ✓
- **Next operator action**: run live WISE pipeline with `--force-refresh --no-resume` (see Step 5 below); paste stderr output showing `[fetch] WISE IRSA: N rows, cols=[...]`

**PR #124 MERGED (2026-06-27)** ✓ — IRSA error logging + column limit (SUPERSEDED by PR #125):
- Added stderr logging for IRSA exceptions and empty results so operators can diagnose failures
- Added `columns='ra,dec,mjd_obs,w1mpro,w1sigmpro'` to limit payload — this turned out to cause ORA-00904 (see PR #125)
- Added `Skills/diagnose_wise_query.py` for direct IRSA diagnostics
- CI green at 100% coverage, 1574 tests ✓

**PR #123 MERGED (2026-06-27)** ✓ — NEOWISE mjd_obs column fix + coverage:
- Root cause: `fetch_wise_archive` read `row["mjd"]` but NEOWISE `neowiser_p1bs_psd` uses `mjd_obs`. Every row threw `KeyError`, silently caught, producing 0 observations even when IRSA returned real data (confirmed via 61-second live query).
- Fix: `row["mjd_obs"]` in `src/fetch.py`; test mocks updated; `_monitor_neocp` success-path coverage added.
- CI green at 100% coverage on Python 3.14, 1574 tests ✓
- **Next operator action**: run live WISE pipeline with `--force-refresh` (see Step 5 below)

**PR #119 MERGED (2026-06-27)** ✓ — fetch.py WISE/DECam/TESS discovery layer:
- `fetch_wise_archive`: IRSA `neowiser_p1bs_psd` cone search; MJD→JD; disk-cached
- `fetch_decam_archive`: NOIRLab NSC DR2 via pyvo TAP; disk-cached
- `fetch_tess_ffis`: MAST `Observations.query_criteria()` + TIC catalog; BTJD→JD; disk-cached
- `fetch_discovery`: routing enforcer — raises `ValueError` for ZTF/ATLAS inputs
- `schemas.py` `Mission` extended: `"TESS"`, `"DECam"`, `"WISE"` added
- `run_pipeline.py` default survey changed from `ZTF` → `WISE`; choices expanded
- CI green at 100% coverage on Python 3.14, 1573 tests ✓
- `docs/SYSTEM_PROFILE.md` updated: explicit note that tensor data must be `.to(device)`

**CRITICAL — discovery data source**: `run_pipeline.py` must target UNREVIEWED archives
(TESS FFIs, DECam/NOIRLab, WISE/NEOWISE). Do NOT run with `--surveys ZTF` or
`--surveys ATLAS` for discovery — ZTF ZAPS and ATLAS pipeline have already processed
those streams. See `docs/MISSION.md §The Two-Part Data Strategy`.
Default is now `--surveys WISE` which is correct for discovery.

**Current blocker status (updated by v0.90.18 handoff above)**:
1. There is no active MPC-contact task today because there is no candidate yet.
   MPC submission protocol becomes relevant only after a real candidate survives
   automated adversarial review and operator review.
2. The current production path is ZTF DR24 historical replay, not WISE/DECam/TESS.
   Phase 0 is materially complete except for the external Fink TLS blocker.
   Next code-addressable work is Gate Z1: start the bounded Phase 1
   historical-replay ingest prototype using verified IRSA/JPL/MPC behavior.

**Progress tracker**: `docs/evidence/prod-loop/LOOP_PROGRESS.md` — read this
at session start to avoid repeating completed work.

### Handoff state as of 2026-06-26

**Discovery paper goal established (2026-06-26)**:
See handoff state above (2026-06-27) — superseded.

### Handoff state as of 2026-06-22

All T1 and T2 gaps are closed. All operator commands for T1-C are complete —
do NOT re-run any ATLAS screening, prequalification, or audit commands.

**LIVE PIPELINE OPERATIONAL (2026-06-21)**: First live run completed successfully.
- Run ID: `6c1b387e0763`, field RA=83.8221 Dec=-5.3911, ZTF, 7-day window
- Console output conforms to `docs/CONSOLE_OUTPUT_SPEC.md` ✓
- `--no-dry-run` flag working ✓
- 0 alerts (Orion field not in ZTF footprint for that epoch — expected)
- Evidence: `docs/evidence/live/2026-06-21-first-live-run.md`
- DO NOT re-run this specific command — zero-alert result was expected and confirmed

**ZTF fetch ndet cap fix + adversarial test fixes (PR #115, MERGED 2026-06-22)**:
- Root cause of 0 tracklets (Runs 3–5): `_fetch_ztf_alerce_api` Mode 1 used
  `ndet_max=None`, returning persistent stationary sources at fixed sky positions.
  The linker correctly rejected all 3134 seed pairs (rate ≈ 0 arcsec/hr for same
  sky-position repeated detections). Previous fix (ndet ASC in Mode 2 only) was
  irrelevant because Mode 1 always succeeds and Mode 2 is never called.
- True fix: Mode 1 now uses `ndet_max=3` + `order_mode="ASC"`. Moving objects
  appear as ndet=1 OIDs (each night's position is a new OID, since objects move
  ~700 arcsec/night vs the ~1 arcsec OID association radius). This surfaces
  single-detection transients instead of persistent background sources.
- `max_objects` increased 50 → 200 for broader field coverage.
- Evidence: `docs/evidence/live/2026-06-22-ndet-cap-root-cause.md`
- 2 regression tests added to prevent re-introduction of ndet_max=None bug.
- All 5 pre-existing adversarial/pipeline test failures fixed (see AGENTS.md).
- CI green on Python 3.14 with 100% coverage ✓

**Historical next live run (SUPERSEDED — do NOT run for discovery)**:
```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
    --ra 284.13 --dec -22.5 --radius 3.5 \
    --start-jd 2461183.0 --end-jd 2461213.0 \
    --surveys ZTF --no-dry-run --force-refresh --no-resume
```
Expected: ndet≤3 asteroid-classified OIDs → single-night transients at unique
sky positions → linker can form seed pairs with real solar system motion rates.

**T2-A CLOSED (2026-06-21)**: Both integration_live tests passed on operator Mac.
- `test_fetch_ztf_live_small_region` PASSED
- `test_fetch_atlas_live_small_region` PASSED (13s run time)
- Evidence: `docs/evidence/t2a/2026-06-21-integration-live-results.md`
- DO NOT re-run integration_live tests — they are complete.

**T2-B** (live false-positive audit): `Skills/diagnose_pipeline.py --json` confirmed
all 10 synthetic pipeline stages pass (2026-06-21, 25s). Real-data audit against
known-artifact catalog remains a future operator-run step when a credentialed live
ZTF run is available. Not blocking for current discovery-paper production scope.

**All T2 checklist items are now resolved:**
- T2-A: CLOSED ✓ (2026-06-21)
- T2-B: CLOSED ✓ (synthetic adversarial tests + diagnose_pipeline pass; real-data
  audit is a future milestone, not a current blocker)
- T2-C: CLOSED ✓ (2026-06-21)
- T2-D: CLOSED ✓ (2026-06-21)
- Alert protocol compliance: CLOSED ✓ (14-scenario validation, e2e.yml job)
- Guardrail compliance: CLOSED ✓ (static scan clean)
- Docs sync: CLOSED ✓

**Completed T1-C evidence (DO NOT RE-RUN)**:
- Screening run `atlas_recovery_25f3a800a1a2`: DONE (42/101, 5 tracklets)
- Prequalification: DONE — objects 121, 954, 2140, 2172, 5650
- Follow-up run `atlas_recovery_c1712df0f32c`: DONE (16/23, 5/5 objects)
- Audit: DONE — passed=True, 5 multi-night tracklets, 2026-06-20
- Operator review: DONE — Jerome W. Lindsey III, no blocking findings, 2026-06-20
- Full evidence: `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`

No external submission was performed or authorized. No impact-probability claim
was made or authorized.

### Handoff state as of 2026-06-17

`Skills/run_pipeline.py` is now production-ready for live runs:
- **Checkpoint/resume** (PR #105): after network drops or machine sleep, re-running
  the identical command resumes from the last completed stage. Checkpoints live at
  `Logs/pipeline_runs/<param_key>/checkpoint.json`.
- **Retry with backoff** (PR #105): genuine network errors retry up to 5 times
  with 2/4/8/16/32 s waits. `json.JSONDecodeError` (empty API response = no data
  for that region) is explicitly NOT retried (PR #106).
- **Cache auto-delete + audit log** (PR #104): after each run, `.neo_cache/*.json`
  is deleted and `Logs/pipeline_runs/<param_key>/run_summary.json` is written.
- **Credentials wired** (PR #107): `_fetch_ztf_irsa_api` now reads
  `ZTF_IRSA_USERNAME` and `ZTF_IRSA_PASSWORD` from env and passes Basic Auth to
  IRSA TAP. `fetch_ztf` falls back to the IRSA path on any ztfquery exception
  (not just ImportError). Load all three credentials from Keychain before running:
  ```bash
  source Skills/verify_live_credentials.sh
  ```

### Current T1-C blocker: recovery evidence

The original zero-alert blocker has been superseded. Public ALeRCE-backed ZTF
source detection is working and has produced non-zero real data. On 2026-06-16
the Orion-field pilot fetched 4,059 real source detections, detected 520 raw
moving candidates, linked the first 80, and scored 2 internal candidates. That
run is retained only as historical/debug evidence and must not be reused for the
production recovery KPI.

The next production run should target many recoverable known moving objects,
preferably from `Skills/select_survey_fields.py --mode recovery`, then build an
expected-known manifest with `Skills/build_recovery_manifest.py` containing MPC
designations plus Horizons sky/time samples.
`Skills/audit_real_run.py` is the fail-closed promotion gate: it must verify
>=90% known-object recovery and require operator review before
internal production promotion is allowed. It never authorizes MPC submission,
NASA notification, or any impact-probability statement.

**Operator recovery-field selection command**:
```bash
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/select_survey_fields.py \
    --jd now \
    --mode recovery \
    --top-n 10 \
    --history-dir Logs/pipeline_runs \
    --json
```

A second pilot run (post-v0.87.2) fetched 0 observations for all 400
candidates because the MPCORB NEA.txt catalog uses extended packed
designations for numbered asteroids ≥100000 (e.g. `A0004` for asteroid 100004)
which `_unpack_designation()` did not handle — all were passed literally to
`MPC.get_observations()` which returned None. Fixed in v0.87.3 (PR #85). All
three MPCORB packed formats are now handled: leading-zero numeric (`00433` →
`433`), 7-char provisional (`K23A00A` → `2023 AA`), and base-62 extended
numeric (`A0004` → `100004`).

A third pilot run (post-v0.87.3) returned `insufficient_observations` for all
400 candidates because `MPC.get_observations()` now returns epoch as
`astropy.Quantity(value, unit='d')` in newer astroquery versions. `float()` on
a dimensioned Quantity raises `TypeError`, silently caught in the row-parsing
`try/except`, discarding every row. Fixed in v0.87.4 (PR #86): epoch is
extracted via `.jd` (for astropy Time objects), `.value` (for Quantities), or
plain `float()` for legacy scalars.

A fourth pilot run (post-v0.87.4) returned `insufficient_observations` for all
400 candidates because PR #86 only fixed the `epoch` column. astroquery
0.4.11+ assigns `u.deg` units to `RA` and `DEC` columns and `u.mag` to `mag`
as well — `float(Quantity('90.0 deg'))` raises `TypeError` in the same
per-row `except Exception: pass` block. Fixed in v0.87.5 (PR #87): added
`_mpc_to_float()` helper dispatching `.jd` / `.value` / `float()` and
applied it to all four numeric columns. The subsequent fifth Tier 3 pilot
succeeded and produced the trained Tier 3 weights now recorded under T1-A.

### Skills

| Script | Purpose |
|---|---|
| `Skills/smoke_test.py` | Happy-path check for all modules; exits 0 on success |
| `Skills/evaluate_calibration.py` | Brier/ECE evaluation for Platt and isotonic calibrators |
| `Skills/generate_training_labels.py` | Download Tier 1 labels or build the approved four-class MPC Tier 3 pilot manifest |
| `Skills/batch_score.py` | Score a list of tracklets from a JSON file; print ranked table |
| `Skills/run_pipeline.py` | Full end-to-end pipeline run |
| `Skills/injection_recovery.py` | Injection-recovery test: injects synthetic NEOs, measures detection/link/score rates |
| `Skills/verify_ztf_dr24_sources.py` | Phase 0 source verification for the ZTF DR24 pipeline: probes the exact endpoints cited in `docs/neo_discovery_agent_brief.md`, writes `data_sources_verified.md`/`auth_requirements.md` |
| `Skills/check_mpc_known.py` | Cross-match candidate observations against MPC known object catalog |
| `Skills/build_recovery_manifest.py` | Build checkpointed MPC+Horizons expected-known manifests for T1-C recovery audits |
| `Skills/visualize_tracklets.py` | Plot sky positions and light curves for a tracklet JSON file |
| `Skills/export_mpc_report.py` | Export MPC 80-column reports from a scored NEO JSON file |
| `Skills/benchmark_pipeline.py` | Time classify + score on N synthetic tracklets; print throughput table |
| `Skills/train_tier1_xgboost.py` | Train Tier 1 XGBoost on ZTF alerts + MPC labels; saves `models/tier1_xgb.json`; run from Mac with `caffeinate -i` |
| `Skills/train_tier2_cnn.py` | Fine-tune CNN on labeled ZTF cutout CSV; saves `models/tier2_cnn.pt` |
| `Skills/train_tier3_transformer.py` | Train Transformer on MPC tracklet CSV; saves `models/tier3_transformer.pt` |
| `Skills/tune_linker.py` | Parametric sweep of `position_tolerance_arcsec` × `chi2_threshold` vs link/score rate |
| `Skills/background.py` | Unified background automation CLI with run, readiness, live dry-run, summary, detail, history, and signoff subcommands |
| `Skills/neo_mcp_server.py` | Project-scoped MCP guard server for bounded file reads, read-only git inspection, and fixed offline validation/readiness commands |
| `Skills/stress_test_high_motion.py` | Stress-test linker across 3 motion bins (1–10, 10–30, 30–60 arcsec/hr); saves results to `data/` |
| `Skills/build_cutout_dataset.py` | Convert ZTF alert JSON (base64 cutouts) to `.npz` + CSV index for Tier 2 CNN training |
| `Skills/build_sequence_dataset.py` | Validate five classes, create designation-grouped splits, and tokenize Tier 3 sequences |
| `Skills/fetch_alerce_artifact_sequences.py` | Acquire bounded public ALeRCE bogus-object histories for the Tier 3 artifact class |
| `Skills/run_tier3_pilot.py` | One-command, fail-closed Tier 3 pilot with commit pinning, reserve pools, resumable checkpoints, and top-level SQLite stage logs |
| `Skills/validate_mpc_report.py` | Validate MPC 80-column observation report files; CLI with `--json` flag |
| `Skills/diagnose_pipeline.py` | Run each pipeline stage with synthetic data; report pass/fail per stage |
| `Skills/compare_baselines.py` | Compare two injection-recovery JSON baselines; exits 1 on regression |
| `Skills/simulate_survey.py` | Generate synthetic ZTF-like survey observations for a sky field |
| `Skills/export_ranked_table.py` | Export a ranked ScoredNEO table to CSV or HTML |
| `Skills/check_orbit_quality.py` | Check orbit quality and fit preliminary orbit for tracklets from JSON |
| `Skills/generate_obs_schedule.py` | Generate prioritized follow-up observation schedule with urgency tiers |
| `Skills/photometric_calibration.py` | Per-field photometric zero-point fit and magnitude correction |
| `Skills/export_mpc_bulk.py` | Bulk export MPC 80-column reports for a list of ScoredNEOs to a directory |
| `Skills/filter_candidates.py` | Filter scored NEO JSON by hazard flag, alert pathway, or minimum priority |
| `Skills/summarise_run.py` | Print or JSON-export a pipeline run summary from scored NEO JSON |
| `Skills/plot_sky_coverage.py` | RA/Dec scatter plot of tracklet positions colour-coded by hazard flag |
| `Skills/export_candidate_report.py` | Per-candidate plain-text reports from scored NEO JSON; `--split` writes one file per candidate |
| `Skills/tag_neo_class.py` | Batch-tag NEO class for tracklets or ScoredNEO dicts using `classify_neo_class` from orbit.py |
| `Skills/check_tisserand.py` | Batch-compute Tisserand parameter for tracklets/ScoredNEO dicts; flags T_J < threshold as comet-like |
| `Skills/export_followup_requests.py` | Generate NEOCP follow-up request files for candidates above priority threshold; supports `--obs-code` and `--out-dir` |
| `Skills/ephemeris_check.py` | Predict sky positions for tracklets at a given JD; observer-ready RA/Dec/dist table; `--jd` and `--json` flags |
| `Skills/flag_comet_candidates.py` | Combined Tisserand + eccentricity comet-candidate flag; `--threshold`, `--min-ecc`, `--json` flags |
| `Skills/assess_survey_coverage.py` | Survey field coverage report (area, limiting mag, source count, fields per night); `--json` flag |
| `Skills/grade_tracklets.py` | Batch-grade tracklets from JSON (A/B/C/D) using arc, nights, and astrometric RMS; `--json` flag |
| `Skills/query_mpc_observations.py` | Inspect one MPC history or collect a bounded, resumable, versioned Tier 3 raw sequence dataset |
| `Skills/fetch_atlas_data.py` | Fetch ATLAS forced photometry for a sky position; `--token`, `--force-refresh`, `--json` flags |
| `Skills/plot_calibration.py` | Plot reliability diagram from scored NEO or prob/label JSON; saves PNG; prints Brier/ECE/log-loss |
| `Skills/export_survey_summary.py` | Export per-candidate detection summary from pipeline run JSON to CSV or HTML |
| `Skills/triage_candidates.py` | Urgency-sorted triage table from scored NEO JSON; `--urgency`, `--pathway`, `--json` flags |
| `Skills/validate_pipeline_run.py` | Validate pipeline run JSON for required keys, MOID plausibility, and no impact-probability phrases; `--json` flag |
| `Skills/export_atlas_lightcurve.py` | Export ATLAS forced-photometry lightcurve for a sky position; `--format png\|csv\|json`, `--out`, `--token`, `--force-refresh` flags |
| `Skills/analyze_field_detections.py` | Field-level detection statistics and mission/filter breakdowns; `--json` flag |
| `Skills/export_candidate_dossiers.py` | Export conservative per-candidate dossier files; `--out-dir`, `--json` flags |
| `Skills/fetch_recent_neos.py` | Fetch recent MPC NEO observations; `--days`, `--force-refresh`, `--json` flags |
| `Skills/diagnose_atlas_recovery.py` | Diagnose a completed ATLAS recovery run checkpoint; per-designation/per-sample breakdown with `--check-horizons` to compare manifest positions against JPL Horizons ephemeris; `--designation`, `--json` flags |
| `Skills/export_ades_report.py` | Export MPC ADES PSV reports for scored candidates |
| `Skills/fetch_known_phas.py` | Fetch known PHA records with cache support; `--force-refresh`, `--json` flags |
| `Skills/get_top_candidates.py` | Top-N candidates by discovery priority from scored NEO JSON; `--n`, `--json` flags |
| `Skills/validate_model_weights.py` | Load all four committed model files and assert valid calibrated output on synthetic fixtures; `--json` flag; used by `e2e.yml` model-weight CI job |
| `Skills/validate_alert_protocol.py` | Run `ready_for_submission()` on 14 diverse synthetic NEOs and assert correct gate behavior; `--json` flag; used by `e2e.yml` alert-protocol CI job |
| `Skills/match_positive_control_tracklet.py` | Rank `run_archive_positive_control.py` report tracklets by angular offset from two known real reference positions, to identify which (if any) tracklet actually matches a known object rather than a combinatorial cross-night pairing; `--ref1`, `--ref2`, `--top-n` flags |
| `Skills/find_nearest_raw_observation.py` | Rank a single night's raw `ztf_alert_archive_ingest.py` checkpoint observations by angular offset from a known reference position, bypassing detect()/link() entirely, to check whether ZTF's archive recorded any confident detection near a known object's position at all; `--ref`, `--top-n` flags |

### Docs

| File | Purpose |
|---|---|
| `docs/PIPELINE_SPEC.md` | Full stage-by-stage pipeline specification |
| `docs/SCORING_MODEL.md` | Bayesian scoring model: hypotheses, priors, feature weights |
| `docs/TRAINING_GUIDE.md` | Step-by-step ML training guide: Tier 1–3 training, calibration, injection-recovery |
| `docs/DATA_SOURCES.md` | External data sources: ZTF, ATLAS, MPC, JPL Horizons, Gaia DR3 |
| `docs/API_REFERENCE.md` | Public function signatures and schema field reference for all modules |
| `docs/BACKGROUND_SEARCH_AUTOMATION.md` | Implemented one-run background automation, SQLite logs, and scheduler notes |
| `docs/ORBIT_FITTING.md` | Technical reference for orbit fitting: Gauss's method, differential correction, MOID, Tisserand parameter |
| `docs/ALERT_PROTOCOL.md` | Technical reference for alert-pathway decision tree, gate conditions, MPC submission, NEOCP monitoring, NASA PDCO notification |
| `docs/MPC_SUBMISSION_POLICY.md` | **Operator-approved submission policy (2026-06-21).** MPC/NEOCP/Scout is the expert review system; no in-house expert required; submission gates are `ready_for_submission()` thresholds. Read before modifying alert.py or submission logic. |
| `docs/CLASSIFICATION_GUIDE.md` | Technical reference for three-tier ML classification, morphology, ensemble stacking, calibration, and conservative classification policy |
| `docs/QUALITY_METRICS.md` | Reference for all pipeline quality metrics: detection, astrometric, photometric, orbital, calibration, and hazard scoring |
| `docs/THREAT_ASSESSMENT.md` | Technical reference for threat score formula, components, interpretation guidelines, and CLI usage |
| `docs/DETECTION_GUIDE.md` | Technical reference for detect.py: RB threshold, streak detection, clustering, known-object matching, detection efficiency, DetectionSummary |
| `docs/LINKING_GUIDE.md` | Technical reference for link.py: tracklet formation, arc statistics, satellite trail rejection, deduplication, quality grades |
| `docs/FETCH_GUIDE.md` | Technical reference for fetch.py: ZTF/ATLAS/MPC/Horizons retrieval, caching, depth estimation, survey merging, filtering |
| `docs/PREPROCESS_GUIDE.md` | Technical reference for preprocess.py: difference image quality, photometry, astrometric calibration, SNR, scatter, zero-point |
| `docs/CALIBRATION_GUIDE.md` | Technical reference for calibration helpers and metrics |
| `docs/ALERT_PATHWAY_GUIDE.md` | Alert pathway helper and guardrail guide |
| `docs/SCHEMA_REFERENCE.md` | Schema model reference |
| `docs/CONSOLE_OUTPUT_SPEC.md` | **Console output standard for all pipeline runners** (stage prefixes, ETA format, run header/footer, escalation notice). `Skills/run_pipeline.py` is compliant as of 2026-06-21. |

### Data

| File | Purpose |
|---|---|
| `data/sample_tracklets.json` | Two synthetic tracklets for testing batch Skills |
| `data/README.md` | Data directory documentation and format reference |
| `data/injection_recovery_baseline.json` | Injection-recovery results (n=50, seed=42): 100% detection, 62% link, 62% score |
| `data/injection_recovery_n200.json` | Injection-recovery results (n=200, seed=42): 100% detection, 100% link, 100% score |
| `data/stress_test_high_motion.json` | Stress-test results: 100% link rate across all three motion bins |
| `background/config.json` | Automated offline background automation configuration |
| `background/config.schema.json` | JSON Schema for background automation config |
| `background/live_review_policy.example.json` | Example M4 live dry-run review policy; not approved for live network by default |
| `background/live_review_policy.schema.json` | JSON Schema for live dry-run review policy |
| `background/targets.json` | Stable background automation fixture manifest |

### Coverage by Module (v0.87.0)

| Module | Coverage |
|---|---|
| `schemas.py` | 100% |
| `score.py` | 100% |
| `calibration.py` | 100% |
| `link.py` | 100% |
| `alert.py` | 100% |
| `preprocess.py` | 100% |
| `orbit.py` | 100% |
| `detect.py` | 100% |
| `classify.py` | 100% |
| `fetch.py` | 100% (WISE/DECam/TESS + ztfquery, ATLAS, astroquery.mpc, jplhorizons all mocked) |

### Completed Operational Milestones

| Milestone | Status | Description |
|---|---|---|
| 4 (partial) | LIVE ✓ | Production live ZTF runs working; first live run 2026-06-21; scheduler policy in `background/config.json` |
| 5 | DONE ✓ | Tier 2 CNN trained (`models/tier2_cnn.pt`; val_acc=91.3%) |
| 6 | DONE ✓ | Tier 3 Transformer trained (`models/tier3_transformer.pt`; val_macro_f1=0.9400) |
| 7 | DONE ✓ | Ensemble calibration: AUC=0.9809, Brier=0.0211, ECE=0.0000, all 7 KPIs pass |

### One Remaining Human-Gated Blocker

- **MPC archival WISE authority (HUMAN DECISION REQUIRED)** — MPC sources
  document `C51` as the WISE station code and ADES note `Z` for survey
  astrometry reported by a non-survey measurer/pipeline, but written MPC
  confirmation is still required before this independent archival pipeline may
  submit WISE/NEOWISE remeasurements under `C51`. `run_pipeline.py` prints an
  escalation notice for every submission-ready candidate but makes no actual
  submission. See `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents —
  Archival WISE Submission Authority` for the current problem statement.

### Immediate Next Steps

**Goal: defensible discovery paper** (established 2026-06-26 with operator Jerome W. Lindsey III).
Pipeline generates candidates → adversarial review filters → operator reviews survivors →
MPC submission → provisional designation → independent confirmation → journal paper.

1. ~~Merge PR #116~~ DONE ✓
2. ~~Open/merge PR #117~~ DONE ✓ (2026-06-27, CI green, 1534 tests, 100% coverage)
3. ~~**Redesign `fetch.py` discovery layer**~~ DONE ✓ (PR #119 merged 2026-06-27, 1573 tests)
4. ~~**Update `docs/MPC_SUBMISSION_POLICY.md`**~~ DONE ✓ (PR #121 merged 2026-06-27)
5. **WISE/NEOWISE discovery sweep state — 0.2° Taurus full-year cap-2000 dry run completed**:
   - Evidence: `docs/evidence/live/2026-06-29-wise-cap2000-dry-run.md`.
   - The selected Taurus window is data-viable: `12061` WISE rows,
     `12042/12061` preprocessed sources, and `6` integer-JD nights.
   - The uncapped `12042`-candidate all-pairs linker path projected tens of
     minutes and was intentionally interrupted. Do not repeat the uncapped
     command as the next diagnostic.
   - The explicit bounded run used `--max-candidates 2000`, linked `243289`
     seed pairs in `28s`, formed `19` tracklets, processed `19` candidates,
     found `0` submission-ready candidates, and completed in `35.32s`.
   - Offline adversarial review now fails closed on compact pipeline summary
     rows. The cap-2000 report produced `19/19` `REJECT` verdicts because
     `run_pipeline.py` wrote flattened rows rather than full `ScoredNEO`
     review packets.
   - `run_pipeline.py --review-packet-out` was added and live-validated on the
     same bounded WISE diagnostic. The rerun wrote `21` full `ScoredNEO`
     packets; offline adversarial review produced `21/21 REJECT` verdicts with
     fatal `orbit_quality`, `real_bogus`, `artifact_posterior`, and
     `neo_dominance` challenges. No candidate advanced to operator review.
   - `run_pipeline.py --max-link-seed-pairs` now fails closed before the linker
     when estimated all-pairs seed work exceeds the configured budget
     (default `1000000`; set `0` only for a documented override).
   - NEXT CODE ACTION: implement a scale-aware WISE linking strategy or
     explicit tiling plan before another uncapped 12k-candidate run.
   RA=58.0 Dec=20.0 (Taurus) is correct for a Feb 2020 NEOWISE epoch (NEOWISE scans at ~90° from Sun; Sun at RA≈325° in Feb 2020 → survey strip at RA≈55°).
   Do NOT use `--surveys ZTF` or `--surveys ATLAS` for discovery.
   Do NOT pass `--no-dry-run` during discovery sweeps. Real archive fetching
   works in dry-run mode; actual MPC submission remains blocked until the
   observatory-code path is resolved and `NEO_MPC_SUBMISSION_APPROVED=1` is set
   with a real non-placeholder MPC code.
6. **Run adversarial review** (`Skills/adversarial_review.py`) on any candidates found:
   `PYTHONPATH=src uv run --python 3.14 python Skills/adversarial_review.py /tmp/wise_candidates.json`.
7. **Jerome reviews** any SURVIVE or BORDERLINE candidates.
8. **Jerome resolves MPC observatory code** (human-gated; no code can help here).
9. Submit survivors to MPC → await provisional designation.

**Operator WISE run evidence (2026-06-27, PR #127 main)**:
Jerome ran the Taurus WISE command before PR #131 merged. IRSA async TAP returned
`111913` rows with live columns `['ra', 'dec', 'mjd', 'w1mpro', 'w1sigmpro']`;
the pipeline parsed `85335` WISE observations, preprocessed all of them, detected
`535` candidates, linked `0` tracklets, processed `0` candidates, and wrote run
summary `Logs/pipeline_runs/756e0dc7b6be/run_summary.json`. The transcript also
showed masked WISE photometry warnings for `w1mpro` and `w1sigmpro`. Durable
evidence: `docs/evidence/live/2026-06-27-wise-live-sweep.md`. PR #131 now
handles masked WISE photometry explicitly and keeps discovery sweeps in alert
dry-run mode. Do not ask the operator to repeat this exact run; next code work
should diagnose why `535` WISE candidates yielded `0` tracklets.

- Console output is fully compliant with `docs/CONSOLE_OUTPUT_SPEC.md` as of v0.90.2.
- ALWAYS run from `main` — operator never checks out feature branches.
- All commands must begin with `git pull origin main`.
- Never give operator any command before the relevant PR merges.

- Sync docs and changelog after each version bump so `AGENTS.md`, `CLAUDE.md`, `README.md`, and `CHANGELOG.md` stay aligned.
- Inspect background SQLite schema status with `Skills/background.py schema-status-summary` before running operators against older logs.
- Preview background SQLite migrations with `Skills/background.py init-log-db-preview` before running `init-log-db`.
- Use `Skills/background.py schema-operations-summary` to confirm packet-decision command readiness before recording packet-linked decisions.
- Use `Skills/background.py operator-next-action` for one schema-gated conservative next-command recommendation.
- Run `Skills/background.py blueprint-compliance-summary` after background automation changes to confirm blueprint definition-of-done status.
- Persist blueprint compliance snapshots with `Skills/background.py record-blueprint-compliance-summary` after scheduled background cycles.
- Persist operator-facing operations snapshots with `Skills/background.py record-operations-snapshot` after scheduled background cycles.
- Generate internal signoff packets with `Skills/background.py latest-unsigned-signoff-packet` before recording reviewer decisions.
- Inspect persisted packet-decision readiness with `Skills/background.py signoff-packet-decision-readiness` before asking for a packet-linked decision.
- Use `Skills/background.py record-signoff-from-packet` when a reviewer is ready to report a decision from a persisted packet.
- Use `Skills/background.py internal-follow-up-disposition` after internal review to summarize signed fixture follow-ups without approving live search or external submission.
- Use `Skills/background.py live-credential-inventory --write-report Logs/reports/credential_inventory_latest.json` to review env/Keychain credential presence without printing or committing secret values.
- Collect labeled training data via `Skills/generate_training_labels.py`.
- Run credentialed live-data dry runs for ZTF/ATLAS/Pan-STARRS only when tokens and review policy are explicitly configured.
- Train and evaluate Tier 2/Tier 3 model weights on real labeled data.
- Commit `models/tier1_xgb.json` after `.gitignore` update to allow `models/*.json` is merged.

### Key Changes in v0.87.9 (T1-A CLOSED — ensemble stacker KPIs passed)

- `Skills/train_ensemble_stacker.py`: implemented and debugged end-to-end
  ensemble stacking training (PRs #97–#101). Five bugs fixed across four
  operator runs: (1) alert lookup used wrong CSV column (`filename` vs
  `cutout_path`) — fixed to use `entry_idx` from NPZ stem; (2) numpy array
  truthiness `array or fallback` — fixed with walrus operator `is not None`
  check; (3) `IsotonicCalibrator.fit()` requires numpy arrays not Python lists
  — removed `.tolist()` from `calibrator.fit/predict`; (4) KPI functions
  (`brier_score`, `compute_roc_auc`, etc.) use numpy arithmetic — removed
  `.tolist()` from all KPI calls; (5) binary KPI evaluation included MPC
  samples with T2=uniform, suppressing AUC — fixed to evaluate only on
  ZTF-origin samples (source="ztf") where both T1 and T2 features are real.
- `build_stacking_dataset` now returns a `sources` list ("ztf"/"mpc"/
  "synthetic") per sample; `evaluate_stacker_kpis` accepts `sources_val` and
  filters to ZTF-origin samples for binary calibration evaluation.
- Ensemble stacker KPI results (2026-06-14, operator run, 10s total):
  AUC=0.9809, Brier=0.0211, ECE=0.0000, Log-loss=0.0761, CV ECE
  mean=0.0247, Bootstrap Brier CI upper=0.0330, Bootstrap ECE CI upper=0.0225
  — all 7 KPIs PASS; `promotion_gate_passed=true` on 394 ZTF val samples.
- `docs/PRODUCTION_READINESS.md`: T1-A step 12 marked DONE; T1-A status
  updated to CLOSED; checklist rows updated to [x].
- 3528 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.9.

### Key Changes in v0.87.7 (T1-D calibration KPI gate passed)

- `Skills/evaluate_calibration.py`: fixed series of macOS PyTorch deadlocks
  that caused the CNN section to hang indefinitely (PRs #91–#95):
  - **BytesIO pre-read** (PR #91): torch.load on a file path uses mmap and
    returns 0.0s but defers byte reads to load_state_dict, blocking on
    Dropbox-backed files. Fixed by reading into BytesIO in 64KB chunks with
    per-chunk ETA before any torch call.
  - **Matmul warmup** (PR #93): first ATen tensor compute in a new process
    triggers Accelerate/BLAS lazy init (~20s). Fixed with dummy 256×256 matmul
    warmup before load_state_dict.
  - **Conv2d warmup** (PR #94): matmul warmup only activates BLAS paths;
    conv2d dispatches through a separate route (FBGEMM/oneDNN) that lazy-
    compiles on first call. Fixed with dummy 1×1×63×63 CNN forward pass.
  - **Thread-pool deadlock** (PR #95): ATen thread-pool spawn deadlocks on
    macOS when OMP_NUM_THREADS is unconstrained. Fixed by setting
    OMP_NUM_THREADS=1 and MKL_NUM_THREADS=1 via os.environ before import
    torch, and calling torch.set_num_threads(1) immediately after import.
  - **Heartbeats** on all blocking calls (matmul warmup, conv warmup,
    per-batch forward pass) so no call is ever silent.
- T1-D calibration KPI gate results (2026-06-14, operator run, 24s total):
  - Tier 1 XGBoost (Isotonic): Brier=0.0000, ECE=0.0000, Log-loss=0.0004,
    ROC AUC=1.0000 — all 7 KPIs PASS.
  - Tier 2 CNN (Isotonic): Brier=0.0462, ECE=0.0132, Log-loss=0.2398,
    ROC AUC=0.9593 — all 7 KPIs PASS.
  - `promotion_gate_passed=true`; report at `Logs/reports/calibration_report.json`.
- `CLAUDE.md` Standing Rules hardened (PR #92): four new rules to prevent
  symptom-loop debugging (diagnose root cause before writing code; physically
  impossible output is a diagnostic signal; failed fix → re-diagnose; state
  predicted output before submitting PR). ETA rule updated to require
  measurable-quantity ETA; elapsed-only heartbeats explicitly prohibited.
- `docs/PRODUCTION_READINESS.md`: T1-D marked CLOSED; checklist updated;
  T1-A progress updated to reflect calibration gate passed.
- 3511 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.7.

### Key Changes in v0.87.6 (ALeRCE progress output; Tier 3 training complete)

- `Skills/fetch_alerce_artifact_sequences.py`: Added `_print_progress()` helper
  with elapsed time and ETA emitted to stderr after every OID in both sequential
  and parallel acquisition paths. The ALeRCE stage had zero print statements —
  a violation of the standing rule requiring live progress on all long-running
  scripts — making it appear frozen to operators.
- Tier 3 Transformer (operator run, 2026-06-13): Fifth pilot run succeeded.
  MPC collected 50 sequences per class in 3m49s (200 total); ALeRCE collected
  50 stellar_artifact sequences (329 observations). Training on the five-class
  pilot splits: best epoch 17/30, val_macro_f1=0.9400, val_loss=0.2492. Weights
  saved at `models/tier3_transformer.pt` (operator Mac).
- `docs/PRODUCTION_READINESS.md`: Tier 3 row updated to DONE; checklist items 7
  and 9 marked done; T1-A progress block updated.
- 3511 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.6.

### Key Changes in v0.87.5 (astropy Quantity all-columns fix)

- `src/fetch.py`: `fetch_mpc_observations` — astroquery 0.4.11+ assigns units
  to ALL four numeric columns: `epoch→u.d`, `RA→u.deg`, `DEC→u.deg`,
  `mag→u.mag`. PR #86 fixed `epoch` only; `float(Quantity('90.0 deg'))` still
  raised `TypeError` for RA, DEC, and mag, silently discarded per-row, causing
  all 400 fourth-pilot candidates to return `insufficient_observations`.
  Fix: added `_mpc_to_float(val)` helper (dispatches `.jd` / `.value` /
  `float()`) and replaced all four `float(...)` column extractions with it.
- `tests/test_fetch.py`: 2 new tests — `test_all_columns_as_quantities`
  (epoch, RA, DEC, mag all as Quantities — the exact astroquery 0.4.11+ case)
  and `test_ra_dec_as_quantities` (RA/DEC as Quantities, plain float epoch).
- 3511 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.5.

### Key Changes in v0.87.4 (astropy Quantity epoch fix)

- `src/fetch.py`: `fetch_mpc_observations` — `MPC.get_observations()` now
  returns epoch as `astropy.Quantity(value, unit='d')` in newer astroquery.
  `float(dimensioned_Quantity)` raises `TypeError`; silently caught inside the
  row-parsing `try/except`, discarding every observation for every designation.
  This was the root cause of all 400 pilot candidates returning
  `insufficient_observations` on the third pilot run. Fix: dispatch on
  `hasattr(epoch_val, "jd")` → `.jd`, `hasattr(epoch_val, "value")` → `.value`,
  else plain `float()`. (PR #86)
- `src/alert.py`: split compound `if obs is not None and hasattr(...) and len(...)` into
  nested `if` statements to eliminate Python 3.14.6 intermittent branch-coverage
  miss in `validate_alert_package`.
- `tests/test_fetch.py`: 2 new tests — `test_epoch_as_astropy_quantity_value`
  and `test_epoch_as_astropy_time_jd` — covering both epoch dispatch branches.
- 3509 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.4.

### Key Changes in v0.87.3 (designation unpacking)

- `Skills/generate_training_labels.py`: `_unpack_designation()` — added branch
  for extended packed numbers (asteroids ≥100000): 5-char strings with leading
  letter and 4 digits (e.g. `A0004` → `100004`, `Z9999` → `359999`, `a0001`
  → `360001`). This was the root cause of all 400 pilot candidates returning
  zero MPC observations on the second pilot run.
- `src/alert.py`: converted remaining `elif` to independent `if` in
  `validate_alert_package` to fix Python 3.14.6 branch-coverage miss.
- `tests/test_tier3_pilot.py`: 7 new regression tests covering all three packed
  formats and end-to-end designation parse.
- 3507 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.3.

### Key Changes in v0.87.2 (pilot robustness)

- `src/fetch.py`: `fetch_mpc_observations` — added `None`-table guard (MPC returns `None`
  for unknown designations; was causing `TypeError` treated as provider failure); added
  `_INFRA_ERRORS` tuple to distinguish infrastructure failures (`ConnectionError`,
  `TimeoutError`, `OSError`) from query-level errors; query-level errors now return `[]`
  regardless of `raise_on_error` so they are classified as `insufficient_observations`
  rather than `query_error` and do not feed the circuit breaker.
- `src/alert.py`: two remaining `elif` chains in `validate_alert_package` converted to
  independent `if` statements to fix Python 3.14.5 branch-coverage miss.
- `Skills/query_mpc_observations.py`: parallel circuit-breaker effective threshold raised
  to `max_consecutive_query_errors + (workers - 1)` to compensate for `as_completed()`
  ordering bias; error messages now include failing designation names and error types.
- `tests/test_fetch.py`: 4 new tests covering None-table, query-level non-raise, and
  infrastructure-raise behaviour in `fetch_mpc_observations`.
- `tests/test_sequence_acquisition.py`: 2 new tests covering parallel threshold scaling
  and diagnostic message content.
- 3500 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.87.2.

### Key Changes in v0.87.1 (training milestone)

- `Skills/train_tier1_xgboost.py`: new — trains 5-class XGBoost on ZTF labeled alerts (rb/drb features) + MPC NEO/MBA catalog labels; 80/20 stratified val split; inverse-frequency class weights; saves `models/tier1_xgb.json`; auto-loaded by `classify._load_xgb_model`.
- `.gitignore`: added `!models/*.json` to allow `models/tier1_xgb.json` to be committed alongside `models/tier2_cnn.pt`.
- `docs/PRODUCTION_READINESS.md`: T1-A step 8 marked DONE; step 9 added (commit model JSON); checklist updated (Tier 1 XGBoost ✓).
- Tier 1 XGBoost training results: val_acc=99.95%, macro AUC=1.000, 11,100 examples (8,588 ZTF real + 1,412 ZTF bogus + 500 MPC NEO + 500 MPC MBA + 100 synthetic minor-class), 300 estimators, max_depth=5.

### Key Changes in v0.87.0

- `schemas.py`: added `SurveyNightRecord` — frozen model: night_jd, survey, n_obs, n_tracklets, limiting_mag, area_sq_deg.
- `fetch.py`: added `compute_observation_time_span(fetch_result)` — max JD − min JD across valid alerts; None for fewer than 2 finite JDs.
- `preprocess.py`: added `compute_cutout_dynamic_range(obs)` — max minus min pixel value in float32 difference cutout; None if absent or empty.
- `detect.py`: added `compute_detection_gap_days(result)` — max JD gap between consecutive candidate detections; None for fewer than 2 candidates.
- `link.py`: added `compute_inter_night_motion(tracklet)` — mean angular displacement between consecutive distinct nights in arcsec/night; None for fewer than 2 distinct nights.
- `classify.py`: added `compute_classification_entropy_summary(neos)` — dict: mean_entropy, std_entropy, min_entropy, max_entropy across scored NEOs; empty dict if none.
- `orbit.py`: added `compute_mean_longitude(elements)` — mean longitude λ = Ω + ω + M₀ (mod 360°); None for missing attributes.
- `score.py`: added `compute_batch_priority_stats(neos)` — dict: mean, std, min, max of discovery_priority; empty dict if no valid priorities.
- `alert.py`: added `format_alert_pathway_summary(neos)` — multi-line text block with pathway counts and fractions sorted by frequency.
- `calibration.py`: added `compute_negative_predictive_value(probs, labels, threshold=0.5)` — NPV = TN/(TN+FN); 0.0 for empty input or no negative predictions.
- 3475 tests passing; 100% coverage target maintained; ruff + mypy clean.
- Version bumped to 0.87.0.

### Key Changes in v0.86.0

- `schemas.py`: added `NightObservationSummary` — frozen model: night_jd, n_obs, n_candidates, mean_rb, limiting_mag, survey.
- `fetch.py`: added `get_faintest_observation(fetch_result)` — Observation with highest valid magnitude (< 90); None if no valid alerts.
- `preprocess.py`: added `compute_photometric_noise_level(observations)` — MAD of valid observation magnitudes; None for fewer than 2 valid mags.
- `detect.py`: added `compute_candidate_sky_density(result, field_radius_deg)` — candidates per square degree using solid-angle formula; 0.0 for empty or non-positive radius.
- `link.py`: added `compute_max_observation_gap(tracklet)` — maximum gap in days between consecutive observations sorted by JD; None for fewer than 2 observations.
- `classify.py`: added `get_highest_confidence_neo(neos)` — ScoredNEO with highest posterior neo_candidate probability; None if list is empty.
- `orbit.py`: added `compute_orbit_complexity(elements)` — scalar complexity index [0, 1]: 0.5×min(e,1) + 0.5×min(|i|,90)/90; 0.0 for missing attributes.
- `score.py`: added `compute_candidate_priority_spread(neos)` — standard deviation of discovery_priority values; 0.0 for fewer than 2 valid priorities.
- `alert.py`: added `count_ready_for_submission(neos)` — count of candidates passing the ready_for_submission gate.
- `calibration.py`: added `compute_positive_predictive_value(probs, labels, threshold=0.5)` — PPV = TP/(TP+FP); 0.0 for empty input or no positive predictions.
- 3420 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.86.0.

### Key Changes in v0.85.0

- `schemas.py`: added `ScoredNEOBatch` — frozen model: batch_id, pipeline_version, created_at_jd, n_candidates.
- `fetch.py`: added `get_latest_observation(fetch_result)` — Observation with highest JD; None if no valid alerts.
- `preprocess.py`: added `compute_cutout_fill_fraction(obs)` — fraction of non-zero pixels in difference-image float32 cutout; None if absent or decode error.
- `detect.py`: added `compute_mean_motion_rate(result)` — mean apparent motion rate (arcsec/hr) across all candidates; None if empty.
- `link.py`: added `compute_arc_coverage_fraction(tracklet, survey_window_days)` — arc_days / survey_window, clamped [0, 1].
- `classify.py`: added `compute_composite_neo_score(features)` — weighted composite of real_bogus (0.35), arc_coverage (0.25), nights_observed (0.25), orbit_quality (0.15); [0, 1].
- `orbit.py`: added `compute_specific_angular_momentum(elements)` — h = sqrt(GM·a·(1−e²)) in AU² yr⁻¹; None for invalid/hyperbolic orbits.
- `score.py`: added `compute_weighted_hazard_index(neo)` — composite: 0.4×threat + 0.3×MOID_proximity + 0.3×orbit_quality; [0, 1].
- `alert.py`: added `format_neo_summary_table(neos, max_rows=20)` — plain-text ASCII ranked table with header, separator, and data rows.
- `calibration.py`: added `compute_sharpness(probs)` — mean squared deviation from 0.5; [0, 0.25]; 0.25 = perfectly sharp.
- 3367 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.85.0.

### Key Changes in v0.84.0

- `schemas.py`: added `AlertSummaryRecord` — frozen model: neo_id, alert_pathway, hazard_flag, discovery_priority, moid_au, submitted_at_jd.
- `fetch.py`: added `get_brightest_observation(fetch_result)` — return Observation with lowest mag (< 90); None if none.
- `preprocess.py`: added `compute_image_rms(obs)` — RMS pixel value of difference-image float32 cutout; None if absent or decode error.
- `detect.py`: added `get_brightest_candidate(result)` — RawCandidate containing the observation with the smallest valid magnitude.
- `link.py`: added `compute_position_angle_dispersion(tracklet)` — std dev of consecutive pair position angles in degrees; 0.0 for exactly 2 obs.
- `classify.py`: added `compute_mean_neo_probability(neos)` — mean posterior neo_candidate probability across scored NEOs; None if no valid posteriors.
- `orbit.py`: added `compute_aphelion_velocity(elements)` — speed at aphelion in km/s via vis-viva equation; None for invalid/hyperbolic orbits.
- `score.py`: added `count_by_alert_pathway(neos)` — dict[pathway → count] across all scored NEOs.
- `alert.py`: added `format_candidate_summary_line(neo)` — compact single-line summary with ID, pathway, hazard flag, priority, MOID.
- `calibration.py`: added `compute_calibration_spread(probs, labels, n_bins=10)` — std dev of per-bin calibration errors; 0.0 for < 2 non-empty bins.
- 3309 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.84.0.

### Key Changes in v0.83.0

- `schemas.py`: added `FieldCoverageReport` — frozen model: field_id, ra_deg, dec_deg, area_sq_deg, n_obs, n_tracklets, limiting_mag, pipeline_version.
- `fetch.py`: added `count_observations_by_filter(fetch_result)` — dict[filter_band → count] across all alerts.
- `preprocess.py`: added `compute_cutout_contrast_ratio(obs)` — peak/median pixel ratio in difference cutout; None if absent or median zero.
- `detect.py`: added `count_candidates_above_rb(result, threshold=0.65)` — count of candidates with max real_bogus ≥ threshold.
- `link.py`: added `compute_tracklet_span_nights(tracklet)` — number of distinct integer nights spanned.
- `classify.py`: added `count_by_dominant_hypothesis(neos)` — dict[hypothesis → count] across scored NEOs.
- `orbit.py`: added `compute_perihelion_velocity(elements)` — speed at perihelion in km/s via vis-viva.
- `score.py`: added `compute_pha_fraction(neos)` — fraction of candidates flagged pha_candidate.
- `alert.py`: added `validate_obs_code(obs_code)` — (bool, str) validity check on MPC obs code format.
- `calibration.py`: added `compute_fraction_calibrated(probs, labels, threshold=0.1, n_bins=10)` — fraction of bins within threshold of perfect calibration.
- 3251 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.83.0.

### Key Changes in v0.82.0

- `schemas.py`: added `ObservationQualityReport` — frozen model: field_id, epoch_jd, n_obs, mean_snr, mean_fwhm_arcsec, n_saturated, limiting_mag.
- `fetch.py`: added `group_observations_by_night(fetch_result)` — dict[int_jd → list[Observation]] grouped by floor(jd); skips non-finite JDs.
- `preprocess.py`: added `compute_cutout_peak_value(obs)` — peak pixel value in difference cutout; None if no cutout or decode error.
- `detect.py`: added `compute_rb_score_distribution(result, n_bins=10)` — equal-width histogram of max RB scores per candidate; excludes None scores.
- `link.py`: added `estimate_observation_cadence(tracklet)` — mean inter-observation time in hours; None for <2 obs.
- `classify.py`: added `filter_by_neo_probability(neos, min_prob=0.5)` — filter ScoredNEOs by posterior neo_candidate probability.
- `orbit.py`: added `compute_argument_of_perihelion_rate(elements)` — secular ω precession rate in deg/yr from solar J2 perturbation.
- `score.py`: added `get_top_candidates(neos, n=10)` — top-N ScoredNEOs by discovery_priority descending.
- `alert.py`: added `count_submissions_by_pathway(neos)` — dict[pathway → count] for candidates passing ready_for_submission gate.
- `calibration.py`: added `compute_calibration_resolution(probs, labels, n_bins=10)` — normalized resolution score [0, 1] measuring class separation.
- 3189 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.82.0.

### Key Changes in v0.81.0

- `schemas.py`: added `PipelineHealthReport` — frozen model for pipeline health snapshot (n_modules_tested, coverage_pct, lint_clean, mypy_clean, test_count, pipeline_version).
- `fetch.py`: added `compute_magnitude_distribution(fetch_result, n_bins=10)` — equal-width histogram of alert magnitudes (bin_edges, counts, n_total); excludes sentinel mags ≥ 90.
- `preprocess.py`: added `compute_cutout_noise_level(obs)` — std dev of difference-image float32 pixels; None if no valid cutout.
- `detect.py`: added `filter_by_streak_score(result, min_streak_score=0.5)` — return new DetectResult keeping candidates where max compute_streak_metric ≥ threshold.
- `link.py`: added `compute_field_tracklet_density(tracklets, field_radius_deg)` — tracklets per sq-deg for a circular field using solid-angle formula.
- `classify.py`: added `batch_dominant_hypothesis(neos)` — list of {object_id, hypothesis, probability} dicts for each scored NEO.
- `orbit.py`: added `compute_longitude_ascending_node_rate(elements)` — secular nodal precession rate in deg/yr from solar J2 perturbation.
- `score.py`: added `filter_by_discovery_priority(neos, min_priority=0.5)` — list of ScoredNEOs with discovery_priority ≥ threshold.
- `alert.py`: added `format_complete_mpc_submission(neo, obs_code)` — complete paste-ready MPC submission (header + blank line + 80-col obs block).
- `calibration.py`: added `compute_max_calibration_error(probs, labels, n_bins=10)` — MCE: maximum bin-wise |mean_prob − fraction_positive|.
- 3128 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.81.0.

### Key Changes in v0.60.0

- `background.py`: added `background_operator_next_action_summary(config_path, db_path, input_path)` to schema-gate the operator workflow and recommend the next conservative local command.
- `Skills/background.py`: added `operator-next-action` for machine-readable next-command triage.
- The operator summary blocks on incomplete SQLite schemas before consulting operations snapshots, includes packet-decision readiness for current schemas, and preserves no-network/no-external-submission guardrails.
- 3 new tests (2123 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.60.0.

### Key Changes in v0.59.0

- `background.py`: added `background_schema_operations_summary(db_path)` to combine schema status, migration preview, packet-decision command readiness, and the next safe operator action.
- `Skills/background.py`: added `schema-operations-summary` for read-only schema operations triage.
- The operations summary reports whether packet-decision commands are ready and recommends `init-log-db` only when the current SQLite schema is incomplete.
- 4 new tests (2120 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.59.0.

### Key Changes in v0.58.0

- `background.py`: added `background_schema_migration_preview(db_path)` to preview additive SQLite log migration effects without creating or changing a database.
- `Skills/background.py`: added `init-log-db-preview` for no-write operator review before running `init-log-db`.
- Migration preview reports missing tables, would-create tables, current schema state, the init command, and guardrail flags while preserving no-network, no-external-submission, no-signoff, no-packet, and no-report-write behavior.
- 4 new tests (2116 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.58.0.

### Key Changes in v0.57.0

- `background.py`: added `background_schema_status_summary(db_path)` for read-only inspection of expected top-level SQLite log tables.
- `background.py`: added `migrate_background_log_db(db_path)` to run the additive `init_log_db` migration and report before/after schema state.
- `Skills/background.py`: added `schema-status-summary` and `init-log-db` subcommands.
- Schema inspection and migration reports explicitly preserve the no-network, no-external-submission, no-signoff, no-packet, and no-report-write guardrails.
- 4 new tests (2112 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.57.0.

### Key Changes in v0.56.0

- `background.py`: added `signoff_packet_decision_readiness(db_path)` and `latest_undecided_signoff_packet(db_path)` for no-network review of persisted packets that still need packet-linked decisions.
- `Skills/background.py`: added `signoff-packet-decision-readiness` and `latest-undecided-signoff-packet` subcommands.
- Packet-decision readiness now reports ready, blocked, signed, and already decided packet states without recording a signoff, writing a packet, or enabling live/external action.
- 5 new tests (2108 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.56.0.

### Key Changes in v0.55.0

- `background.py`: added `record_signoff_from_packet(...)` and `signoff_packet_decision_summary(db_path)` to record reviewer decisions from persisted internal signoff packets.
- `Skills/background.py`: added `record-signoff-from-packet` and `signoff-packet-decision-summary` subcommands.
- `init_log_db`: added top-level SQLite table `signoff_packet_decision_log` for packet-linked reviewer decisions and resulting operations snapshots.
- Packet-based decisions validate the packet, unsigned follow-up state, and target/run match before writing a normal human signoff plus decision audit row. Each packet decision also records a post-decision operations snapshot while keeping network access and external submission disabled.
- 5 new tests (2103 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.55.0.

### Key Changes in v0.54.0

- `background.py`: added `signoff_packet(run_id, db_path)`, `latest_unsigned_signoff_packet(db_path)`, `write_signoff_packet(...)`, `record_signoff_packet(...)`, and `signoff_packet_log_summary(db_path)` for internal human-review packets that do not record signoff decisions.
- `Skills/background.py`: added `signoff-packet`, `latest-unsigned-signoff-packet`, `write-signoff-packet`, `record-signoff-packet`, and `signoff-packet-log-summary` subcommands.
- `init_log_db`: added top-level SQLite table `signoff_packet_log` for persisted signoff packet metadata.
- 5 new tests (2098 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.54.0.

### Key Changes in v0.53.0

- `background.py`: added `background_operations_snapshot(config_path, db_path, input_path)`, `record_background_operations_snapshot(...)`, and `background_operations_snapshot_log_summary(db_path)` to aggregate and persist conservative operator-facing background status snapshots.
- `Skills/background.py`: added `operations-snapshot`, `record-operations-snapshot`, and `operations-snapshot-log-summary` subcommands.
- `validation_summary`: now exposes `total_follow_up` directly for aggregate operation-state consumers.
- 4 new tests (2093 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.53.0.

### Key Changes in v0.52.0

- `background.py`: added `record_blueprint_compliance_summary(db_path, input_path)` and `blueprint_compliance_log_summary(db_path)` to persist background blueprint compliance snapshots in top-level SQLite logs.
- `Skills/background.py`: added `record-blueprint-compliance-summary` and `blueprint-compliance-log-summary` subcommands.
- 3 new tests (2089 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.52.0.

### Key Changes in v0.51.0

- `background.py`: added `background_blueprint_compliance_summary(db_path, input_path)` to audit background automation against `BACKGROUND_SEARCH_AUTOMATION_BLUEPRINT.md`.
- `Skills/background.py`: added `blueprint-compliance-summary` subcommand.
- Follow-up report drafts now explicitly include uncertainty language alongside negative evidence and limitations.
- 3 new tests (2086 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.51.0.

### Key Changes in v0.50.0

- Added 10 public APIs across alert, calibration, classify, detect, fetch, link, orbit, preprocess, schemas, and score modules.
- 2083 tests passing; 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.50.0.

### Key Changes in v0.49.0

- Added 10 public APIs for mission counts, calibration error, class probability ranges, angular separation, field overlap, tracklet completeness, orbital arc quality, cutout peak positions, and hazard summaries.
- Version bumped to 0.49.0.

### Key Changes in v0.48.0

- Added 10 public APIs for NEOCP submission formatting, calibration uniformity, posterior stability, variability, MPC orbit catalogs, sky density, Earth Tisserand parameter, compactness, tracklet clusters, and weighted risk.
- Version bumped to 0.48.0.

### Key Changes in v0.47.0

- Added 10 public APIs for discovery reports, calibration drift, Tier 1 confidence, brightness trends, NEOCP confirmations, motion summaries, aphelion distance, PSF asymmetry, night summaries, and survey completeness.
- Version bumped to 0.47.0.

### Key Changes in v0.46.0

- Added 10 public APIs for ADES PSV export, reliability, posterior update, field source counts, known NEO lists, tracklet arc nights, perihelion distance, radial profiles, observation coverage, and priority ranks.
- Version bumped to 0.46.0.

### Key Changes in v0.45.0

- Added 10 public APIs for observation logs, expected positive rate, NEO class distribution, cadence, MPC orbit elements, motion-rate filtering, orbital velocity, streak angle, residual summaries, and hazard grades.
- Version bumped to 0.45.0.

### Key Changes in v0.44.0

- Added 10 public APIs for alert age, resolution score, class entropy summary, detection gaps, NEOCP objects, inter-night gaps, mean anomaly at JD, cutout symmetry, astrometric residuals, and weighted hazard scoring.
- Version bumped to 0.44.0.

### Key Changes in v0.43.0

- Added 10 public APIs for ready-to-submit counts, discrimination, Tier 1 score distributions, angular velocity, known NEO ephemerides, velocity dispersion, inclination class, image gradients, observation clusters, and arc-quality bonuses.
- Version bumped to 0.43.0.

### Key Changes in v0.42.0

- Added 10 public APIs for bulk summaries, Brier skill score, class entropy stats, streak density, field completeness, night span, longitude of perihelion, cutout contrast, ephemeris points, and weighted priority.
- Version bumped to 0.42.0.

### Key Changes in v0.41.0

- Added 10 public APIs for alert-flag counts, calibration sharpness, batch morphology, magnitude filtering, recent MPC NEO retrieval, tracklet quality, mean motion, pixel histograms, survey statistics, and combined priority.
- Version bumped to 0.41.0.

### Key Changes in v0.40.0

- Added 10 public APIs for true anomaly, observation depth, position-angle consistency, calibration gain, close-approach scoring, candidate dossiers, Pan-STARRS moving objects, background level, candidate reports, and average precision.
- Version bumped to 0.40.0.

### Key Changes in v0.39.0

- Added 10 public APIs for eccentric anomaly, source extent, great-circle residuals, confusion matrices, size estimates, follow-up windows, CSS alerts, cutout entropy, orbital summaries, and F1 score.
- Version bumped to 0.39.0.

### Key Changes in v0.38.0

- `background.py`: added `record_live_dry_run_operator_handoff(config_path, db_path, report_dir)` and `live_dry_run_operator_handoff_log_summary(db_path)` to write operator handoffs and persist them in top-level SQLite logs.
- `Skills/background.py`: added `record-live-dry-run-operator-handoff` and `live-dry-run-operator-handoff-log-summary` subcommands.
- 3 new tests (1361 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.38.0.

### Key Changes in v0.37.0

- `background.py`: added `live_dry_run_operator_handoff(config_path)` and `write_live_dry_run_operator_handoff(config_path, report_dir)` to render a conservative no-network Markdown handoff for operator review.
- `Skills/background.py`: added `live-dry-run-operator-handoff` and `write-live-dry-run-operator-handoff` subcommands.
- 4 new tests (1358 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.37.0.

### Key Changes in v0.36.0

- `background.py`: added `record_live_dry_run_approval_bundle(config_path, db_path)` and `live_dry_run_approval_bundle_log_summary(db_path)` to persist no-network approval-bundle reviews in top-level SQLite logs.
- `Skills/background.py`: added `record-live-dry-run-approval-bundle` and `live-dry-run-approval-bundle-log-summary` subcommands.
- 3 new tests (1354 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.36.0.

### Key Changes in v0.35.0

- `background.py`: added `live_dry_run_approval_bundle(config_path)` to aggregate scheduler readiness, policy contract validation, provider readiness, dry-run planning, and blocker status into one no-network review object.
- `Skills/background.py`: added `live-dry-run-approval-bundle` for operator review before any mock live dry-run execution attempt.
- 3 new tests (1351 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.35.0.

### Key Changes in v0.34.0

- `Skills/background.py`: added `live-provider-readiness-summary` to expose no-network provider readiness from the unified CLI.
- CLI coverage now checks default blocked provider output and approved temp-config readiness with credentials.
- 1 new test (1348 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.34.0.

### Key Changes in v0.33.0

- `Skills/background.py`: added `live-policy-contract-summary` to expose no-network live review policy contract validation from the unified CLI.
- CLI coverage now checks both a valid default policy contract and an unsafe policy that allows external submission.
- 1 new test (1347 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.33.0.

### Key Changes in v0.32.0

- `background.py`: added `live_policy_contract_summary(config_path)` for no-network validation of the live review policy file and schema contract.
- `automation_readiness_summary` and `live_dry_run_plan`: now include live review policy contract status and report `LIVE_REVIEW_POLICY_CONTRACT_INVALID` for structural policy failures.
- The intentionally unapproved example policy remains contract-valid, while unsafe policies that allow external submission or omit required files are blocked before any live action.
- 3 new tests (1346 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.32.0.

### Key Changes in v0.31.0

- `background.py`: added `live_provider_capabilities()` and `live_provider_readiness(config_path)` for no-network provider-specific M4 readiness checks.
- `automation_readiness_summary` and `live_dry_run_plan`: now include provider-by-provider credential, policy, rate-limit, and submission-safety readiness details.
- Live mode now reports `LIVE_PROVIDER_NOT_READY` when any provider has missing credentials, policy approval gaps, unsupported live queries, submission capability, or insufficient rate-limit policy.
- 3 new tests (1343 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.31.0.

### Key Changes in v0.30.0

- `background.py`: added `LiveDryRunProvider` and `MockLiveDryRunProvider` for injected no-network survey dry-run probes.
- `live_dry_run_execute` and `record_live_execution_attempt`: now accept an optional provider map, aggregate per-survey query results, and report missing providers.
- Provider results are rejected if they claim network access or external submission, preserving the M4 no-submission guardrail.
- 2 new tests (1340 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.30.0.

### Key Changes in v0.29.0

- `background.py`: added `live_dry_run_execute(config_path)`, `record_live_execution_attempt(config_path, db_path)`, and `live_execution_log_summary(db_path)`.
- `init_log_db`: added top-level SQLite table `live_execution_log` for auditable dry-run execution attempts.
- `Skills/background.py`: added `live-dry-run-execute` and `live-execution-log-summary` subcommands.
- Live dry-run execution remains mock-only: no network access is performed and external submission remains disabled.
- 2 new tests (1338 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.29.0.

### Key Changes in v0.28.0

- `background.py`: added `live_dry_run_plan(config_path)`, `record_live_dry_run_plan(config_path, db_path)`, and `live_dry_run_plan_log_summary(db_path)`.
- `background/live_review_policy.example.json` and `background/live_review_policy.schema.json`: added a formal live review policy contract for M4 dry-run approval.
- `background/config.json`: requires `ATLAS_TOKEN` for ATLAS dry-run readiness, treats public ZTF/Pan-STARRS as no-credential by default, and points to the example review policy.
- `Skills/background.py`: added `live-dry-run-plan`, `record-live-dry-run-plan`, and `live-dry-run-plan-log-summary` subcommands.
- `automation_readiness_summary`: now validates live review policy fields and reports policy-specific blockers before any network access.
- 1 new test (1336 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.28.0.

### Key Changes in v0.27.0

- `background.py`: added `automation_readiness_log_summary(db_path)` and `record_automation_readiness(config_path, db_path)`.
- `init_log_db`: added top-level SQLite table `automation_readiness_log` for scheduler/live-readiness snapshots.
- `Skills/background.py`: added `record-automation-readiness` and `automation-readiness-log-summary` subcommands.
- `docs/BACKGROUND_SEARCH_AUTOMATION.md` and `docs/API_REFERENCE.md`: documented persisted readiness checks and new CLI/API entries.
- 2 new tests (1335 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.27.0.

### Key Changes in v0.26.0

- `schemas.py`: `BackgroundRunMode` now supports `automated`; `BackgroundConfig` added scheduler readiness fields, live review policy, and required credential environment variable names.
- `background.py`: added `automation_readiness_summary(config_path)` and `launchd_plist(config_path)`; live network mode now reports explicit blockers before any network action.
- `Skills/background.py`: added `automation-readiness` and `launchd-plist` subcommands.
- `background/config.json`: default mode is automated offline scheduling with live network disabled and required credential names declared.
- `docs/BACKGROUND_SEARCH_AUTOMATION.md`: updated scheduler guidance for automated offline runs and macOS launchd template generation.
- 4 new tests (1333 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.26.0.

### Key Changes in v0.25.0

- `orbit.py`: added `compute_perihelion_date(elements)` — next perihelion passage JD from mean anomaly and orbital period; None for hyperbolic/parabolic orbits or non-positive period.
- `detect.py`: added `flag_moving_sources(observations, min_rate_arcsec_hr)` — return observations with apparent motion rate ≥ threshold; uses `compute_motion_vector` pairwise; cosine-Dec-corrected.
- `link.py`: added `validate_tracklet(tracklet)` — (bool, reasons) tuple checking ≥2 obs, non-negative arc/rate, sorted JDs, no duplicate obs_ids.
- `classify.py`: added `compute_artifact_probability(features)` — log-score artifact probability [0, 1] using stellar_artifact_score, psf_quality_score, real_bogus_score, streak_score, motion_consistency_score.
- `score.py`: added `compute_observation_priority(neo)` — [0, 1] urgency score weighting last-observation gap (0.3), discovery_priority (0.4), and orbit uncertainty (0.3).
- `alert.py`: added `validate_alert_package(package)` — (bool, issues) tuple enforcing required keys, non-empty observations, valid alert_pathway, and guardrail_statement containing "NOT".
- `fetch.py`: added `fetch_panstarrs_catalog(ra_deg, dec_deg, radius_deg, epoch_jd, force_refresh)` — PanSTARRS DR2 cone search via astroquery.mast; disk-cached; returns list[Observation].
- `preprocess.py`: added `compute_difference_image_snr(obs)` — peak-to-background RMS SNR from 63×63 difference-image cutout; None if no cutout or zero background.
- `schemas.py`: added `AlertPackage` — frozen model: neo_id, alert_pathway, moid_au, observations, submission_timestamp_jd, guardrail_statement.
- `calibration.py`: added `compute_precision_recall_curve(probs, labels)` — PR curve dict with precisions, recalls, thresholds, average_precision; anchored at (recall=0, precision=1) for correct AP.
- `Skills/validate_pipeline_run.py`: new — validate pipeline run JSON for required keys, MOID plausibility [0, 10] AU, no impact-probability phrases, valid pathways; exits 0/1; `--json` flag.
- `Skills/export_atlas_lightcurve.py`: new — ATLAS forced-photometry lightcurve export; `--format png|csv|json`, `--out`, `--token`, `--force-refresh` flags.
- `docs/PREPROCESS_GUIDE.md`: new — technical reference for preprocess.py: difference image quality, photometry, astrometric calibration, SNR, scatter, zero-point.
- 87 new tests (1329 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.25.0.

### Key Changes in v0.24.0

- `orbit.py`: added `compute_absolute_magnitude(observed_mag, r_au, delta_au, phase_deg, g=0.15)` — inverse IAU HG phase function; returns H from apparent magnitude, distances, and phase angle; NaN for degenerate geometry.
- `detect.py`: added `compute_motion_vector(obs1, obs2)` — dict with dra_arcsec_hr, ddec_arcsec_hr, rate_arcsec_hr, pa_deg; cosine-Dec-corrected; zero vector for identical JDs.
- `link.py`: added `merge_overlapping_tracklets(tracklets)` — union-find merge of tracklets sharing ≥1 obs_id; picks longest-arc representative; deduplicates and recomputes arc_days.
- `classify.py`: added `compute_neo_probability(features)` — log-score model probability for neo_candidate hypothesis vs all others; uses CLAUDE.md feature weights; [0, 1].
- `score.py`: added `compute_discovery_score(neo)` — weighted combination of discovery_priority (0.5), orbit_quality_score (0.3), brightness_score (0.2); clamped [0, 1].
- `alert.py`: added `format_submission_checklist(neo)` — multi-line checklist with ✓/✗ per alert-protocol gate condition (rb≥0.90, quality≥2, MOID≤0.05, not known, neo_prob≥0.50) plus Step 1/2/3 status.
- `fetch.py`: added `filter_by_survey(fetch_result, surveys)` — return new FetchResult containing only observations whose mission is in the supplied list.
- `preprocess.py`: added `estimate_zero_point(observations, catalog_mags)` — median(obs.mag − catalog_mag) zero-point offset; None if <2 valid pairs; excludes sentinel mags ≥ 90.
- `schemas.py`: added `ObservationStatistics` — frozen model: n_obs, mean_mag, mag_range, mean_real_bogus, n_filters, arc_days.
- `calibration.py`: added `compute_roc_auc(probs, labels)` — ROC AUC via trapezoidal rule; 0.5 for single-class or empty input; NumPy 1.x/2.x compatible.
- `docs/FETCH_GUIDE.md`: new — technical reference for fetch.py: ZTF/ATLAS/MPC/Horizons retrieval, caching, depth estimation, merging, filtering.
- 75 new tests (1242 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.24.0.

### Key Changes in v0.23.0

- `orbit.py`: added `compute_apparent_magnitude(elements, target_jd, albedo=0.14)` — approximate V-band apparent magnitude using IAU HG phase function; returns NaN for degenerate geometry.
- `detect.py`: added `count_detections_by_filter(observations)` — dict mapping filter_band → count; None filter_band mapped to "unknown".
- `link.py`: added `filter_by_nights_observed(tracklets, min_nights=2)` — keep only tracklets spanning ≥ min distinct integer-JD nights.
- `classify.py`: added `get_posterior_vector(posterior)` — 5-element numpy array [neo_candidate, known_object, main_belt_asteroid, stellar_artifact, other_solar_system].
- `score.py`: added `compute_followup_urgency(neo)` — URGENT/HIGH/MEDIUM/ROUTINE tier based on hazard_flag, MOID, and discovery_priority.
- `alert.py`: added `count_pending_alerts(neos)` — dict of alert_pathway → count; only pathways with ≥1 candidate included.
- `fetch.py`: added `estimate_survey_depth(fetch_result)` — 95th-percentile magnitude from valid alerts; None if no valid magnitudes.
- `preprocess.py`: added `compute_photometric_scatter(observations)` — RMS scatter of magnitudes; None for <2 valid observations.
- `schemas.py`: added `PhotometricSolution` — frozen model: zero_point, color_coeff, extinction_coeff, rms_scatter, n_stars, filter_band, epoch_jd.
- `calibration.py`: added `compare_calibrators(probs_list, labels, names)` — dict of name → calibration_report for multiple calibrator comparisons.
- `Skills/triage_candidates.py`: new — urgency-sorted triage table; `--urgency`, `--pathway`, `--json` flags.
- `docs/LINKING_GUIDE.md`: new — tracklet formation, arc statistics, satellite trail rejection, deduplication, quality grades.
- 78 new tests (1167 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.23.0.

### Key Changes in v0.22.0

- `orbit.py`: added `compute_synodic_period(elements)` — synodic period vs Earth in days; inf for a ≤ 0 or a = 1 AU.
- `detect.py`: added `compute_detection_efficiency(observations, limiting_mag)` — fraction of obs brighter than limiting_mag; 0.0 if empty; sentinel mag ≥ 90 counts as missed.
- `link.py`: added `summarize_arc_statistics(tracklets)` — aggregate dict: n_tracklets, mean/max arc_days, fraction_multi_night.
- `classify.py`: added `compute_classification_table(neos)` — list of dicts per NEO: object_id, dominant_hypothesis, probability, entropy_bits.
- `score.py`: added `filter_by_alert_pathway(neos, pathway)` — filter ScoredNEO list by exact alert_pathway match.
- `alert.py`: added `format_impact_notification(neo)` — PDCO-ready notification dict with full provenance, observation list, and guardrail statements.
- `fetch.py`: added `fetch_ztf_alerts(ra, dec, radius, start_jd, end_jd, force_refresh)` — ZTF IRSA cone search; disk-cached; returns list[Observation].
- `preprocess.py`: added `compute_image_quality_metrics(observations)` — dict: n_sources, mean/median_fwhm_arcsec, mean_snr, background_rms.
- `schemas.py`: added `DetectionSummary` — frozen model: field_id, epoch_jd, survey, n_candidates, n_known_matches, n_new, limiting_mag.
- `calibration.py`: added `calibration_report(probs, labels)` — comprehensive dict: brier_score, ece, log_loss, n_samples, mean_prob, fraction_positive.
- `Skills/plot_calibration.py`: new — reliability diagram plot from scored NEO or prob/label JSON; saves PNG; prints Brier/ECE/log-loss.
- `Skills/export_survey_summary.py`: new — per-candidate detection summary export to CSV or HTML; sorted by discovery_priority.
- `docs/DETECTION_GUIDE.md`: new — technical reference for detect.py: RB threshold, streak/trail detection, clustering, known-object matching, detection efficiency, DetectionSummary.
- 71 new tests (1089 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.22.0.

### Key Changes in v0.21.0

- `orbit.py`: added `compute_heliocentric_distance(elements, target_jd)` — heliocentric distance in AU at target JD via `predict_ephemeris`; inf for non-positive semi-major axis; NaN on error.
- `detect.py`: added `estimate_sky_background(observations, percentile)` — percentile of pixel values across difference-image cutouts; None if no valid cutouts.
- `link.py`: added `filter_by_arc_length(tracklets, min_arc_days)` — keep only tracklets with arc_days ≥ threshold (default 1.0).
- `classify.py`: added `calibrate_posterior(posterior, calibrator)` — re-calibrate NEOPosterior with Laplace smoothing (alpha=0.05) or optional calibrator; always normalised to 1.0.
- `score.py`: added `compute_threat_score(neo)` — geometric mean of MOID proximity, H-magnitude size proxy, and orbit quality; [0, 1]; 0.5 sentinel for unknown components.
- `alert.py`: added `generate_mpc_cover_letter(neo)` — formal plain-text MPC submission cover letter with mandatory guardrail "Do NOT publicly announce any impact probability."
- `fetch.py`: added `fetch_atlas_forced(ra_deg, dec_deg, start_jd, end_jd, atlas_token, force_refresh)` — ATLAS forced photometry via REST API with task queuing, polling, and disk cache.
- `preprocess.py`: added `normalize_photometry(observations, zero_point, reference_zero_point)` — zero-point correction; drops corrected mags outside [0, 35]; returns new Observation list.
- `schemas.py`: added `ObservationBatch` — frozen Pydantic model grouping Observations from the same survey field and night (batch_id, field_id, night_jd, mission, observations, limiting_mag).
- `calibration.py`: added `reliability_diagram(probs, labels, n_bins)` — equal-width bin reliability diagram; returns dict with bin_centers, fraction_positive, bin_counts; empty bins excluded.
- `Skills/fetch_atlas_data.py`: new — ATLAS forced photometry CLI; `--token`, `--force-refresh`, `--json` flags.
- `docs/THREAT_ASSESSMENT.md`: new — threat score formula, component breakdowns, interpretation table, alert gate conditions.
- 69 new tests (1018 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.21.0.

### Key Changes in v0.20.0

- `orbit.py`: added `compute_phase_angle(elements, target_jd)` — Sun–target–observer phase angle via law of cosines; returns NaN on degenerate geometry.
- `detect.py`: added `compute_psf_fwhm(obs)` — PSF FWHM in arcsec from 2D Gaussian moment fit; returns None if no cutout or degenerate.
- `link.py`: added `compute_tracklet_grade(tracklet)` — A/B/C/D quality grade from arc length, nights observed, and astrometric RMS.
- `classify.py`: added `summarize_classifications(neos)` — aggregate summary dict: total, dominant_hypothesis_counts, mean_entropy_bits, mean_real_bogus_score, pha_candidate_count.
- `score.py`: added `compute_novelty_score(neo, catalog_elements)` — orbital distance from nearest known NEO in (a, e, i) space; 1.0 = fully novel.
- `alert.py`: added `generate_observation_request(neo, obs_code)` — structured NEOCP follow-up request with urgency tier (URGENT/HIGH/MEDIUM/ROUTINE) and guardrail.
- `fetch.py`: added `fetch_mpc_observations(designation)` — query MPC observation history for a designation; caches to disk; returns list[Observation].
- `preprocess.py`: added `compute_astrometric_scatter(observations)` — RMS of linear RA/Dec fit residuals in arcsec; None for <2 obs or identical JDs.
- `schemas.py`: added `PipelineConfig` — frozen Pydantic model capturing sky position, time window, survey selection, and detection thresholds for a pipeline run.
- `calibration.py`: added `compute_log_loss(probs, labels, eps)` — binary cross-entropy with clipping; returns 0.0 for empty inputs.
- `Skills/grade_tracklets.py`: new — batch-grade tracklets from JSON; `--json` flag.
- `Skills/query_mpc_observations.py`: new — query MPC observation history for a designation; `--json` flag.
- `docs/QUALITY_METRICS.md`: new — comprehensive quality metrics reference for all pipeline stages.
- 69 new tests (949 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.20.0.

### Key Changes in v0.19.0

- `orbit.py`: added `orbital_energy(elements)` — specific orbital energy in AU²/yr²; negative = bound, inf for a ≤ 0.
- `detect.py`: added `compute_trail_length(obs)` — trail length in arcsec from difference-image second moments.
- `link.py`: added `assess_link_confidence(tracklet)` — [0, 1] confidence from linear-fit RMS residual vs 10 arcsec reference.
- `classify.py`: added `batch_morphology(tracklet)` — modal_class, class_counts, streak_fraction across all observations.
- `score.py`: added `compute_impact_energy(diameter_m, velocity_km_s, density_kg_m3)` — kinetic impact energy in megatons TNT.
- `alert.py`: added `format_alert_summary(neos, max_rows)` — plain-text ranked summary table with hazard flag, pathway, MOID, priority.
- `fetch.py`: added `count_known_objects_in_field(ra_deg, dec_deg, radius_deg)` — count MPC known objects in a circular field; returns 0 on failure.
- `preprocess.py`: added `detect_bad_pixels(obs, sigma_threshold)` — MAD-based sigma clipping; returns list of (row, col) tuples.
- `schemas.py`: added `SurveyField` — frozen Pydantic model for survey field metadata (field_id, ra_deg, dec_deg, radius_deg, limiting_mag, n_sources, jd).
- `calibration.py`: added `cross_validate_calibration(probs, labels, n_folds, metric)` — K-fold CV returning (mean, std). Fixed `bootstrap_confidence_interval` empty-guard for numpy arrays.
- `Skills/assess_survey_coverage.py`: new — survey field coverage report; `--json` flag.
- `docs/CLASSIFICATION_GUIDE.md`: new — three-tier ML classification reference.
- 81 new tests (880 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.19.0.

### Key Changes in v0.18.0

- `orbit.py`: added `ephemeris_uncertainty(elements, target_jd)` — sky-plane uncertainty propagated from quality code; scales with propagation time.
- `detect.py`: added `cluster_detections(observations, radius_arcsec)` — greedy spatial clustering; returns list of Observation tuples.
- `link.py`: added `compute_arc_statistics(tracklet)` — summary dict: n_observations, n_nights, arc_days, mean_motion_arcsec_hr, motion_pa_std_deg.
- `classify.py`: added `classify_morphology(obs)` — source morphology from image moments: 'point_source', 'extended', or 'streak'.
- `score.py`: added `absolute_magnitude_from_diameter(diameter_m, albedo)` — H from diameter and albedo; returns inf for zero/negative inputs. Fixed formula.
- `alert.py`: added `format_discovery_circular(neo)` — IAU CBET-style discovery circular; does not transmit.
- `fetch.py`: added `build_observation_window(ra_deg, dec_deg, ...)` — validated ObservationWindow factory with ValueError for bad inputs.
- `preprocess.py`: added `compute_source_snr(obs)` — peak-to-background SNR from difference-image cutout.
- `schemas.py`: added `CloseApproachEvent` — frozen model for a close approach event.
- `calibration.py`: added `bootstrap_confidence_interval(probs, labels, n_bootstrap, metric)` — bootstrap 95% CI for Brier or ECE.
- `Skills/ephemeris_check.py`: new — ephemeris prediction table at user-specified JD.
- `Skills/flag_comet_candidates.py`: new — combined T_J + eccentricity comet-candidate flag.
- `docs/ALERT_PROTOCOL.md`: new — alert pathway technical reference.
- 70 new tests (799 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.18.0.

### Key Changes in v0.17.0

- `orbit.py`: added `batch_predict_ephemeris(elements_list, target_jd)` — batch sky-position prediction; per-element error isolation.
- `orbit.py`: added `resonance_check(elements, tolerance)` — mean-motion resonance detection with Jupiter; checks T_J/T_asteroid ratio against p:q pairs; returns resonance label or None.
- `detect.py`: added `compute_streak_metric(obs)` — streak severity from difference-image second moments; [0, 1]; handles degenerate zero-eigenvalue (perfectly elongated) case.
- `link.py`: added `split_tracklet(tracklet, split_jd)` — split tracklet at a JD boundary into two sub-tracklets; raises ValueError if either part has fewer than 2 observations.
- `classify.py`: added `dominant_hypothesis(posterior)` — return (name, probability) for highest-probability class; ("unknown", 0.0) for all-zero posterior.
- `score.py`: added `close_approach_candidates(neos, max_moid_au)` — filter by MOID ≤ threshold; None MOID excluded.
- `alert.py`: added `ready_for_submission(neo)` — boolean gate for all alert-protocol preconditions; returns (bool, unmet list); fixed field name orbit_quality_code → quality_code.
- `fetch.py`: added `filter_alerts_by_motion(alerts, min_rate, max_rate)` — filter by ssdistnr-based motion proxy; observations without ssdistnr pass through.
- `preprocess.py`: added `estimate_source_density(observations, field_radius_deg)` — source count per square degree via great-circle centroid.
- `schemas.py`: added `TrackletSummary` — lightweight frozen model for tracklet display/export.
- `Skills/check_tisserand.py`: new — batch Tisserand parameter check; comet-like flag; `--threshold` and `--json` CLI flags.
- `Skills/export_followup_requests.py`: new — NEOCP follow-up request generator; `--min-priority`, `--out-dir`, `--obs-code`, `--summary` CLI flags.
- `docs/ORBIT_FITTING.md`: new — orbit fitting technical reference.
- 146 new tests (729 total); 100% coverage maintained; ruff + mypy clean.
- Version bumped to 0.17.0.

### Key Changes in v0.16.0

- `orbit.py`: added `classify_neo_class(elements)` — derive NEO dynamical class from orbital elements.
- `orbit.py`: added `tisserand_parameter(elements)` — Tisserand parameter relative to Jupiter; T_J < 3 distinguishes comets.
- `detect.py`: added `filter_by_real_bogus(result, threshold)` — filter DetectResult by max real/bogus score.
- `link.py`: added `deduplicate_tracklets(tracklets)` — remove tracklets with ≥ 50% overlapping obs_ids; longer arc wins.
- `score.py`: added `pha_candidates(neos)` — filter to PHA candidates only.
- `score.py`: added `compute_statistics(neos)` — aggregate NEOStatistics (counts, priority, class distribution).
- `classify.py`: added `posterior_entropy(posterior)` — Shannon entropy of NEOPosterior in bits.
- `alert.py`: added `format_neocp_report(neo, obs_code)` — plain-text NEOCP follow-up request with guardrails.
- `fetch.py`: added `merge_survey_alerts(results)` — merge and deduplicate multiple FetchResults.
- `preprocess.py`: added `compute_color_index(obs1, obs2)` — magnitude difference for observations in different bands.
- `schemas.py`: added `NEOStatistics` — frozen Pydantic model for aggregate pipeline statistics.
- `Skills/export_candidate_report.py`: new — per-candidate plain-text reports; `--split` writes one file per candidate.
- `Skills/tag_neo_class.py`: new — batch-tag NEO class using `classify_neo_class`.
- `docs/TRAINING_GUIDE.md`: new — step-by-step ML training guide (Tier 1–3, calibration, injection-recovery).
- 77 new tests; 660 total; 100% coverage maintained.
- Version bumped to 0.16.0.

### Key Changes in v0.15.0

- `orbit.py`: added `compute_orbital_period` — Kepler's third law; T = 365.25 × √(a³) days.
- `link.py`: added `filter_high_motion(tracklets, min_rate_arcsec_hr)` — filter by motion rate threshold (default 10 arcsec/hr).
- `score.py`: added `followup_priority_table(neos)` — flat ranked table dict list sorted by discovery priority.
- `classify.py`: added `batch_explain(tracklets)` — batch version of `explain_classification`.
- `alert.py`: added `alert_summary_table(neos)` — flat per-NEO alert summary with ready_to_submit flag.
- `fetch.py`: added `summarise_fetch_result(result)` — summary dict of a FetchResult.
- `preprocess.py`: added `flag_saturated_sources(result, saturation_mag)` — return obs_ids of likely saturated sources.
- `schemas.py`: added `CandidateSummary` — lightweight frozen Pydantic model for NEO display/export.
- `Skills/filter_candidates.py`: new — filter scored NEO JSON by hazard flag, pathway, or priority.
- `Skills/summarise_run.py`: new — human-readable or JSON pipeline run summary.
- `Skills/plot_sky_coverage.py`: new — RA/Dec scatter plot colour-coded by hazard flag (matplotlib).
- `docs/API_REFERENCE.md`: updated with all v0.14.0 and v0.15.0 APIs.
- 55 new tests; 583 total; 100% coverage maintained.
- Version bumped to 0.15.0.

### Key Changes in v0.14.0

- `orbit.py`: added `close_approach_table` — tabulate geocentric distance over a time window.
- `link.py`: added `estimate_motion_uncertainty` — rate and PA error from linear fit residuals.
- `score.py`: added `discovery_report` — comprehensive nested summary dict for human review.
- `classify.py`: added `explain_classification` — structured classification breakdown with Tier 1 importances. Fixed Pydantic v2.11 `model_fields` deprecation.
- `alert.py`: added `draft_mpc_submission` — complete MPC submission bundle with guardrail cover letter.
- `schemas.py`: added `ObservationWindow` — frozen typed model for sky/time search queries.
- `fetch.py`: added `estimate_limiting_magnitude` — survey depth proxy from faint-end magnitude tail.
- `preprocess.py`: added `quality_summary` — per-field PSF quality, background RMS, and elongation statistics.
- `detect.py`: added `streak_candidates` — filter `DetectResult` for streak/trail detections only.
- `background.py`: added `audit_report` — consolidated cross-log audit report.
- `Skills/generate_obs_schedule.py`: prioritized follow-up observation schedule with urgency tiers.
- `Skills/photometric_calibration.py`: per-field photometric zero-point fit via Gaia DR3.
- `Skills/export_mpc_bulk.py`: bulk MPC 80-column report export with manifest.
- `docs/SCORING_MODEL.md`: updated with ranking, discovery report, motion uncertainty, close-approach table, and photometric calibration.
- 63 new tests; 528 total; 100% coverage maintained.
- Version bumped to 0.14.0.

### Key Changes in v0.13.0

- `fetch.py`: added `fetch_batch` — fetch multiple sky positions in one call.
- `preprocess.py`: added `preprocess_batch` — batch preprocessing from `FetchResult` list.
- `detect.py`: added `detect_batch` — batch detection from `PreprocessResult` list.
- `link.py`: added `merge_tracklets` — merge two tracklets into a longer deduplicated arc.
- `orbit.py`: added `propagate_orbit` (Keplerian propagation), `predict_ephemeris` (geocentric RA/Dec at target JD).
- `score.py`: added `rank_candidates` — sort `ScoredNEO` list by priority with PHA tier.
- `alert.py`: added `generate_alert_package` — bundle all alert artifacts into one dict.
- `schemas.py`: added `PipelineResult` — immutable top-level pipeline run container.
- `Skills/simulate_survey.py`: synthetic ZTF-like survey generator.
- `Skills/export_ranked_table.py`: CSV/HTML ranked table export.
- `Skills/check_orbit_quality.py`: orbit quality CLI for tracklet JSON.
- `tests/conftest.py`: extended with `build_raw_candidate`, `build_scored_neo`, and `scored_neo`/`raw_candidate` fixtures.
- `docs/PIPELINE_SPEC.md`: updated with all v0.13.0 APIs and `PipelineResult` container.
- 54 new tests; 465 total; 100% coverage maintained.
- Version bumped to 0.13.0.

### Key Changes in v0.12.0

- `link.py`: added `_is_satellite_trail` — rejects purely E-W or N-S fast-moving pairs (≥30 arcsec/hr) as satellite/debris trails.
- `classify.py`: added `classify_batch` and `get_tier1_feature_importances` public APIs.
- `orbit.py`: added `arc_quality_report` — returns quality dict with codes 1–4.
- `score.py`: added `score_batch`; `ScoringMetadata.close_approach_au` now populated from MOID when orbit quality ≥ 2.
- `schemas.py`: added `close_approach_au: float | None = None` to `ScoringMetadata`.
- `alert.py`: added `format_mpc_json` and `batch_process_alerts` public APIs.
- `Skills/validate_mpc_report.py`: new — validate MPC 80-column report format.
- `Skills/diagnose_pipeline.py`: new — per-stage diagnostic runner with synthetic data.
- `Skills/compare_baselines.py`: new — compare injection-recovery baselines; regression detection.
- `docs/API_REFERENCE.md`: updated with all v0.12.0 public APIs.
- 34 new tests; 411 total; 100% coverage maintained.
- Version bumped to 0.12.0.

### Key Changes in v0.11.0

- `link.py`: fixed chi² error proxy (`max(mag_err * 0.1, 0.1)` → `max(mag_err, 0.5)`) — link rate 62% → 100%
- `link.py`: added `_predict_from_arc` (quadratic polyfit for ≥3 obs, linear fallback) for more accurate position prediction
- `fetch.py`: added `force_refresh` flag to bypass on-disk cache; ATLAS token now falls back to `ATLAS_TOKEN` env var
- `alert.py`: added public `monitor_neocp` with injectable sleep for NEOCP polling loop
- `classify.py`: added `retrain_tier1` and `retrain_stacker` public APIs for incremental retraining
- `Skills/run_pipeline.py`: added `--atlas-token`, `--force-refresh`, `--neocp-timeout-hours`, `--neocp-poll-interval` flags
- `Skills/stress_test_high_motion.py`: stress-test linker across 3 motion bins; all bins 100%
- `Skills/build_cutout_dataset.py`: build `.npz` + CSV index from ZTF alert JSON for Tier 2 training
- `Skills/build_sequence_dataset.py`: build flat token CSV from tracklet JSON for Tier 3 training
- `Skills/train_tier2_cnn.py`: updated to read `.npz` cutout files from `cutout_path` column
- `Skills/train_tier3_transformer.py`: updated to read flat `tok_i_j` columns
- `Skills/smoke_test.py`: added `monitor_neocp` and `retrain` smoke tests
- `Skills/check_mpc_known.py`: added `--neocp` CLI flag and `check_neocp` function
- `data/injection_recovery_n200.json`: n=200 baseline: 100% detection, link, score
- `data/stress_test_high_motion.json`: stress-test results
- CHANGELOG.md: full Keep-a-Changelog history added (v0.1.0–v0.11.0)
- 31 new tests; 377 total; 100% coverage maintained
- Version bumped to 0.11.0.

### Key Changes in v0.10.0

- Removed deprecated background wrapper scripts; `Skills/background.py` is the single supported CLI.
- Added versioned background target manifest support and `background/config.schema.json`.
- Added run detail, target history, signoff readiness, and unsigned follow-up audit views.
- Added CLI and manifest regression tests; 346 total; 100% coverage.
- Version bumped to 0.10.0.

### Key Changes in v0.9.0

- `link.py`: fixed prediction bug — `_predict_position` now uses `obs_c.jd` instead of integer night key; link rate 2% → 62%
- `Skills/tune_linker.py`: parametric sweep of tolerance × chi² vs link/score rate
- 4 new tests (regression test for prediction fix + arc_below_min_obs + tune_linker smoke); 328 total; 100% coverage
- Injection-recovery baseline updated: 62% link rate (n=50, seed=42)
- Version bumped to 0.9.0

### Key Changes in v0.8.0

- `classify.py`: added `_build_ensemble` (sklearn LogisticRegression meta-learner) + `ensemble_predict` public API
- `Skills/injection_recovery.py`: added `--json PATH` flag to save results
- Baseline injection-recovery run saved to `data/injection_recovery_baseline.json`
- 8 new tests; 324 total; 100% coverage maintained
- Version bumped to 0.8.0

### Key Changes in v0.7.0

- fetch.py: 75% → 100% via mocks for ztfquery, ATLAS network, astroquery.mpc, jplhorizons
- CI coverage gate raised from 95% → 100%; actual coverage 100.00%
- New Skills: `benchmark_pipeline.py`, `train_tier2_cnn.py`, `train_tier3_transformer.py`
- New infra: `.github/ISSUE_TEMPLATE/` (bug + feature request templates), `models/` directory
- Version bumped to 0.7.0 in `pyproject.toml` and `src/__init__.py`

### Key Changes in v0.6.0

- torch installed; CNN (Tier 2) and Transformer (Tier 3) paths fully tested (100% classify.py coverage)
- Alert module: `process_alert` accepts `cneos_assessment` parameter for PDCO path testing
- Coverage gate raised from 85% → 95% in CI; actual coverage 97.44%
- 40 new tests added across orbit, detect, preprocess, calibration, classify, alert modules
- Version bumped to 0.6.0 in `pyproject.toml` and `src/__init__.py`
