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
7. Call `Read` on `docs/astrometrics_coding_agents_master_guide.md` — the
   cross-project agent guide for production-first work, evaluation discipline,
   candidate ledgers, and benchmark controls.
8. Call `Read` on `docs/astrometrics_data_selection_policy.md` — the
   cross-project policy for selecting, separating, logging, and promoting data
   roles. Apply it before any acquisition, labeling, training, validation,
   replay, or live-search work.
9. Call `Read` on `docs/astrometrics_external_and_cloud_storage_policy.md` —
   the cross-project storage policy for external SSDs, local caches, cloud
   storage, and sync boundaries.

These steps are non-negotiable. No planning or code changes may happen before
all ten are complete.

---

## PRIMARY DIRECTIVE

**You may ONLY work on tasks that advance this project to PRODUCTION.**

Before proposing or executing any task, apply this gate:

> *Does this task close or directly unblock a named production gap from
> `docs/PRODUCTION_READINESS.md`, `docs/ZTF_DR24_PRODUCTION_GATES.md`, or the
> Astrometrics roadmap below?*

If the answer is NO, do not do it. In particular:
- **Never add new public helper APIs** unless they directly unblock a named gap. The v0.77–v0.87 API accumulation cycle (110 helpers, zero production impact) must never recur.
- **Never add new Skills scripts** that are single-function wrappers. Only add a Skill if it is operationally necessary for a named gap.
- **Never add new documentation files** that duplicate existing content.
- **Never propose log modules, schemas, or scaffolding** that do not directly unblock a named T1 or T2 gap.
- **Never repeat work listed under "What Is Complete"** in `docs/PRODUCTION_READINESS.md`.

If the highest-priority production gap cannot be resolved because a human
blocker is unresolved, **state that explicitly** and limit scope to the next
non-blocked ZTF/Astrometrics gate or documentation sync.

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
- **Astrometrics policies govern data and storage work**:
  `docs/astrometrics_coding_agents_master_guide.md`,
  `docs/astrometrics_data_selection_policy.md`, and
  `docs/astrometrics_external_and_cloud_storage_policy.md` are mandatory
  directives. Future data acquisition, model training, scoring, retrospective
  validation, live search, and storage changes must use the repo-visible
  controls under `data_selection/` and `storage/`; do not hand the operator a
  guessed URL, schema, worker count, shard layout, or storage path.
- **Astrometrics production roadmap is now part of the system directives**:
  Work the following gates in order unless the operator explicitly chooses a
  different production path:
  A1 dataset manifest system; A2 candidate ledger; A3 freeze the current CNN
  as `benchmark_cnn_v1`; A4 grouped NEO splits and leakage checks; A5
  OpenAI-evals-style canonical regression suite; A6 parameterized
  injection-recovery curves; A7 calibration/promotion report. Do not promote a
  model, expand live search, or treat the CNN as production-promoted until the
  relevant A-gates close. The existing CNN may be used as an image/artifact
  feature source and benchmark, not as the main scientific thesis.
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

- **Do not inflate caution into artificial readiness/go-live blockers — the same doom-loop discipline this project applies to retries (see Gate Z3) applies to your own status assessments**:
  When asked "are we ready" or "what's blocking X," name only gates that are
  actually open and actually relevant to the specific action being asked
  about right now. Do not cite a gate that is explicitly dormant or
  contingent on a later step (e.g. Gate D3's MPC observatory-code contact,
  which `docs/PRODUCTION_READINESS.md` itself marks dormant "no candidate
  exists yet, so there is nothing to contact MPC about") as if it blocked
  readiness today. Do not treat "the pipeline hasn't produced an outcome
  yet" (e.g., no real NEO discovery found) as evidence it isn't ready —
  `docs/PRODUCTION_READINESS.md`'s operator-approved Production Definition
  (2026-07-01) explicitly states a real discovery is **not** required for
  production readiness. Demanding one before declaring readiness is the
  same circular doom-loop pattern this project already forbids for Gate
  Z3's real-designation retries, just applied to a status answer instead
  of a retry counter — capability-readiness (pipeline validated, gated,
  safe to run) and outcome (has it found something) are different
  questions; only the former is what "ready" usually means. When a report
  exists that the operator needs to review before signing off, paste or
  summarize its actual content in the response — do not only cite the file
  path and leave them to go find it.
  **Why**: Operator correction 2026-07-11 — three separate misframings in
  one "are we ready to go live" answer (a dormant gate cited as a current
  blocker, an unreviewed signoff packet cited by path instead of content,
  and "no discovery yet" cited as a readiness gap) that the operator had to
  individually walk back, after flagging this same general pattern before
  ("I have lost count of the times I have told you this"). See also the
  "Progressively probe toward the safe concurrency ceiling" rule above for
  the same principle applied to a different kind of default-to-caution
  bias.
  **How to apply**: Before any readiness/status answer, check each
  candidate blocker against its own documented current status line (open
  vs. dormant vs. paused-for-a-different-reason) rather than listing every
  gate that sounds thematically related.

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
- **MCP servers, when configured/available**: prefer these over guessing or
  ad hoc web scraping —
  - **GitHub MCP** for issues, PRs, remote branches, repo metadata, PR review
    notes, branch health, and PR links.
  - **Context7 MCP** for current library/framework/API documentation instead
    of relying on training-data recall.
  - **arXiv MCP** for preprint lookup and research context.
  - **NASA ADS MCP** for astronomy/astrophysics literature, bibcodes,
    citations, references, metrics, and BibTeX export.
  This project also runs repo-scoped MCP tools (`neo_project_files`,
  `neo_git_read`, `neo_guard`, configured in `.mcp.json`) for bounded file
  reads, read-only git inspection, and fixed offline validation commands —
  prefer these over raw shell equivalents when doing read-only repo
  inspection.

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

## Current State (v0.90.75)

**Latest sync (2026-07-12)**: Closed a real evidence-quality gap in the
`tier2_cnn_v3` promotion packet, per explicit operator direction. Found
2026-07-11 while answering "did this model pass all tests the System
Directives require": `injection_recovery_report` (along with
`canonical_eval_report`/`false_discovery_report`) never exercised any CNN
candidate's live inference — `classify.py`'s `_tier2_predict()` requires a
full science/reference/difference cutout triplet, and the injection-
recovery harness only ever synthesized `cutout_difference`. Fixed:
`_load_cnn_model()` now accepts an explicit `model_path`;
`Skills/injection_recovery.py` gained `--cnn-model` plus real triplet
synthesis (commit `75899a3d`). Re-ran for real, n=200 seed=42, against
**both** `tier2_cnn_v3` and `benchmark_cnn_v1` (operator: "if we need to
roll back and do this for the last CNN then let's do so") — 14/200 scored
for each, and 8 of those 14 tracklets show genuinely different posteriors
between the two models (e.g. stellar_artifact 0.771 vs 0.438), confirming
real, distinct model behavior. Promotion report regenerated citing the new
real evidence; `operator_signoff_missing` remains the sole blocker
(unchanged — an evidence-quality gap closure, not the signoff itself).
`canonical_eval_report`/`false_discovery_report` remain pipeline-level,
explicitly flagged as still open, out of this session's scope. Full
detail: `docs/evidence/a7/2026-07-12-real-cnn-injection-recovery.md`.

**Earlier sync (2026-07-11/12)**: First genuinely new (non-Z3-tied) ZTF DR24
discovery sweep run to completion. Field selected via
`Skills/select_survey_fields.py --mode aten` (RA 89.3, Dec 22.5, score
0.9238) rather than a known-designation-tracking field. Real UW archive
ingest for nights 20200914/20200916 (12+316 kept observations); found and
fixed a real checkpoint-field-mismatch bug in
`Skills/ztf_alert_archive_ingest.py` along the way (commit `a0fb56e0`).
`Skills/run_archive_positive_control.py --min-observations 2
--build-review-packets` formed 12 real tracklets in ~22s; all 12 REJECTED
by `Skills/adversarial_review.py --offline` (orbit_quality/artifact_posterior/
real_bogus). Clean, expected null result — matches this project's own
Production Definition, which does not require a discovery for readiness.
Target queue rank 1 marked `null_result`. Full detail:
`docs/evidence/live/2026-07-11-first-new-discovery-sweep.md`. Next: select
additional new fields via the same process to build a real search
portfolio (60/30/10 new/follow-up/control per the data-selection policy).

**Earlier sync (2026-07-11, v0.90.85 — doc-sync only, no new code)**: Four
commits landed after the v0.90.81 entry below without a CLAUDE.md sync;
this entry closes that gap. All four are real, verified work:
1. `1ca5fecc` — Added `mpc_training_labels_v1` dataset manifest (A1). Closes
   the last uncovered A1 gap for `models/tier1_xgb.json`'s training inputs:
   `data/training_labels.csv` (500 MPC-confirmed NEO + 500 MBA labels,
   verified by direct row-count inspection) had no manifest even though its
   sibling ZTF-alert input already did.
2. `736a81c5` — Added `tier3_transformer_pilot_v1` dataset manifest (A1).
   Closes the same gap for `models/tier3_transformer.pt`. Found and
   documented a real footgun along the way: the top-level
   `data/sequences/mpc_pilot.json`/`alerce_artifact_pilot.json` files are
   the **first, failed** pilot attempt (0 entries, all
   `insufficient_observations`) — the real training data is
   `data/sequences/tier3_pilot_v2/{mpc_sequences.json,alerce_artifacts.json,splits/}`
   (250 rows, verified against `tier3_training_report.json`'s class
   counts). The manifest points at the real directory and calls out the
   trap explicitly so no future agent re-manifests the wrong file.
3. `41b47fc8` — Added
   `docs/evidence/promotion/tier2_cnn_v3_operator_review_packet.md`. This
   is the actual, readable review packet behind the bare
   `operator_signoff_missing` blocker — training result, all 8 A7 evidence
   checks with real values (not just pass/fail), the full calibration KPI
   table, the one real policy judgment call needing explicit operator
   buy-in (§4: `object_id`-only grouped-split gating — `night_key` overlap
   is 100%, `sky_cell` is 91.3%, neither blocks `passed`), known
   limitations, an explicit "what this does NOT authorize" list, and an
   attestation checklist ending in the exact `build_promotion_report.py
   --operator-signoff-id` command to run once Jerome signs off. **This is
   the artifact to read before recording a signoff decision** — do not
   treat a bare signoff ID as sufficient justification going forward.
4. `c2a02dac` — Made `--candidate-ledger-db` default to
   `data_selection/candidate_ledger.sqlite` in `Skills/run_pipeline.py`
   (A2). Real gap matching
   `docs/astrometrics_coding_agents_master_guide.md`'s non-negotiable rule
   9 ("Do not accept a candidate without manifest and ledger provenance"):
   the flag previously defaulted to `None` (opt-in), so a run without it
   silently produced zero-provenance candidates. Also fixed a sharper bug
   found along the way: `--source-dataset-id` defaults to the literal
   string `"not-recorded"`, which would have satisfied
   `write_candidate_ledger()`'s empty-string check and written that
   placeholder into the ledger as fake provenance every run. `main()` now
   skips ledger ingestion with a printed warning when `--source-dataset-id`
   is empty or `"not-recorded"`, instead of writing fake provenance or
   crashing post-run. `--candidate-ledger-db ''` still fully disables
   ledger writes. 3 new regression tests; full suite 1858 passed / 2
   deselected at that commit.

Net effect: **A1 (dataset manifests) and A2 (candidate ledger) are now
materially more complete** than the v0.90.81 entry below describes — every
trained model's real training data has a manifest, and `run_pipeline.py`
no longer silently produces unprovenanced candidates by default. This does
not change the bottom line: `operator_signoff_missing` remains the sole
blocker on `tier2_cnn_v3` promotion, and it is now backed by a real review
packet rather than a bare CLI command. Re-verified this session: `ruff
check .` clean, `mypy src` clean (18 files), full offline suite run in
progress (see next sync for the pass/fail count).

**Sync (2026-07-11, v0.90.81)**: Ran `Skills/build_promotion_report.py`
for `tier2_cnn_v3` for real. **8/8 evidence checks pass**: dataset_manifest,
grouped_split_report, canonical_eval_report, injection_recovery_report,
calibration_report (`promotion_gate_passed: true`), false_discovery_report
(`false_discovery_rate: 0.0`), pretrained_audit, benchmark_model_card.
Report at `docs/evidence/promotion/tier2_cnn_v3_promotion_report.json`.
`promotion_allowed: false` with exactly one blocker:
**`operator_signoff_missing`** -- this is now the sole remaining blocker in
the entire A1-A7 code-and-evidence-closable roadmap. Nothing further can be
closed by code; the next step is Jerome W. Lindsey III reviewing this
report and its cited evidence, then supplying
`--operator-signoff-id` to `Skills/build_promotion_report.py` to record the
decision. Evidence:
`docs/evidence/a7/2026-07-11-ninth-attempt-promotion-report-eight-of-eight-checks-pass.md`.

**Earlier sync (2026-07-10, v0.90.80)**: **`calibration_report_missing` is
CLOSED with real evidence.** Operator re-ran the v0.90.78 retrain +
calibrate command on their Mac with the v0.90.79 MPS fix merged: both
commands completed cleanly in 17m53s total (confirming the MPS +
parallel-worker fix delivered the expected speedup versus this session's
sandboxed ~3-hour CPU-only estimate). `Device: mps` printed, all 20 epochs
completed with no `RuntimeError`, best checkpoint `val_loss=0.1155`
`val_acc=0.965` saved to `models/tier2_cnn_v3.pt`. The Tier 2 CNN's real
calibration KPIs (`Skills/evaluate_calibration.py` against the real
18-night, 90,000-alert batch): Brier=0.0211, ECE=0.0229 (Isotonic:
Brier=0.0192, ECE=0.0054), Log-loss=0.0760, ROC AUC=0.9954, CV ECE
mean=0.0056 (std=0.0010), Bootstrap Brier/ECE CI upper=0.0192/0.0056 — all
7 T1-D KPIs PASS, `promotion_gate_passed: true`. Report at
`Logs/reports/calibration_report_v3.json` (local-only on the operator's
Mac, same convention as the original `benchmark_cnn_v1` T1-D closure).
Full transcript: `docs/evidence/a7/2026-07-10-eighth-attempt-real-retrain-and-calibration-pass.md`.

**Both A7 blockers that needed a real retrain are now closed**
(`grouped_split_report_missing` in the v0.90.77 entry below,
`calibration_report_missing` here). **`operator_signoff_missing` is the
sole remaining A7 blocker**, and it is inherently human-gated — no further
coding step can close it. The next coding step is regenerating a
`benchmark_cnn_v1_promotion_report.json`-style promotion report for the
new `tier2_cnn_v3` candidate citing this session's real grouped-split and
calibration reports (see `Skills/build_promotion_report.py` /
`Skills/extract_promotion_evidence.py`); this sandboxed session cannot run
that itself because `Logs/reports/calibration_report_v3.json` is
local-only on the operator's Mac and not present here.

**Earlier sync (2026-07-10, v0.90.79)**: Operator ran the real v0.90.78
retrain command on their Mac (real MPS device, `Device: mps` printed
correctly) and hit a genuine PyTorch MPS backend bug on the first training
batch: `RuntimeError: Adaptive pool MPS: input sizes must be divisible by
output sizes` — `ConvBranch`'s conv stack produces a 15×15 feature map and
`AdaptiveAvgPool2d(4)` needs evenly-divisible sizes on MPS (15/4 is not
integer); a real, documented upstream PyTorch limitation
(<https://github.com/pytorch/pytorch/issues/96056>), not a bug in this
project's training logic. Fixed in `src/classify.py`'s `ConvBranch.forward()`
by routing only that one op through CPU when `x.device.type == "mps"`,
matching the error message's own suggested workaround. **First fix attempt
was wrong and caught before committing**: splitting `self.net` into
`self.conv`/`self.pool` changed `state_dict()` key names and broke loading
the frozen `benchmark_cnn_v1` checkpoint
(`Skills/validate_model_weights.py` went from `ALL PASSED` to a real
`FAIL`) — corrected by keeping `self.net` as one unmodified `nn.Sequential`
and iterating its children manually in `forward()` instead, which
preserves state_dict keys exactly.
`Skills/validate_model_weights.py` → `ALL PASSED` again. 2 new regression
tests guard both the state_dict-key stability and CPU-path numerical
equivalence. Full suite 1845 passed / 2 deselected, ruff/mypy clean. Full
detail: `docs/evidence/a7/2026-07-10-seventh-attempt-mps-adaptive-pool-bug-and-fix.md`.
No model was saved by the failed run (crashed before the first
`torch.save`), so `calibration_report_missing` is still open —
**re-run the exact same v0.90.78 retrain + calibrate command block** (now
with this fix merged) on the operator's Mac.

**Earlier sync (2026-07-10, v0.90.78)**: `Skills/train_tier2_cnn.py` gained
real PyTorch device selection (MPS when available, explicit CPU-fallback
reporting otherwise) and a configurable `--num-workers` DataLoader flag —
it previously never selected a device at all (silently CPU-only always)
and hardcoded single-threaded `.npz` loading, contradicting
`docs/SYSTEM_PROFILE.md`'s mandatory device-selection rule. Fixing
`--num-workers` also required moving `CutoutDataset` from a
function-local class (unpicklable by DataLoader workers) to module level.
Full suite 1843 passed / 2 deselected, ruff/mypy clean.

**This session's sandbox cannot validate the speedup**: both
`torch.backends.mps.is_available()` and multiprocess DataLoader workers
(`torch_shm_manager` needs shared-memory socket access) are blocked by
this specific sandboxed execution environment, not by the code or the
real machine. One real CPU-only, `--num-workers 0` epoch on the full
90,000-alert v3 batch took ~9.5 minutes (measured, not estimated) — 20
epochs would be 3+ hours in this degraded mode. Rather than spend 3+ hours
of sandboxed CPU-only compute, the actual retrain is handed off to an
**unsandboxed terminal** (this repo's normal operator-command pattern),
where MPS + parallel workers should make it dramatically faster. Full
detail: `docs/evidence/a7/2026-07-10-sixth-attempt-device-selection-and-sandbox-training-limits.md`.

**Next command (NOT YET RUN)** — real GPU-accelerated retrain on the
already-downloaded, already-passing-grouped-split 18-night batch, closing
`calibration_report_missing`:

```bash
git pull origin main
export PYTHONPATH=src

# data/cutouts_v3/index.csv and data/cutouts_v3/grouped_split.csv already
# exist locally from this session (data/ztf_labeled_alerts_v3.json,
# ~5.7GB, gitignored) with a real passing grouped-split report at
# Logs/reports/tier2_cnn_v3_grouped_split_report.json. If those files are
# not present (e.g. a different machine), re-run the v0.90.74 handoff's
# steps 1-3 with --nights 18 --limit 90000 first.

caffeinate -i uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v3/index.csv \
    --epochs 20 \
    --num-workers 8 \
    --out models/tier2_cnn_v3.pt \
    --grouped-split-report Logs/reports/tier2_cnn_v3_grouped_split_report.json \
    --production-candidate

caffeinate -i uv run --python 3.14 python Skills/evaluate_calibration.py \
    --alerts data/ztf_labeled_alerts_v3.json \
    --cutouts-csv data/cutouts_v3/index.csv \
    --cnn-model models/tier2_cnn_v3.pt \
    --report-out Logs/reports/calibration_report_v3.json
```

Not sharded: single GPU/MPS training job, not independent parallel units —
`docs/SYSTEM_PROFILE.md` says use full local compute headroom here, not
multiprocessing across tabs. Naming: this produces a new candidate
(`tier2_cnn_v3`), not a silent overwrite of the frozen `benchmark_cnn_v1`,
per A3's freeze policy. A follow-up promotion report for the new candidate
(citing the real passing grouped-split report + this calibration report) is
the next coding step once this run completes; `operator_signoff_missing`
remains the final, inherently human-gated blocker after that.

**Earlier sync (2026-07-10, v0.90.77)**: **`grouped_split_report_missing` is
CLOSED with real evidence.** After the v0.90.76 findings below, a real
18-night (90,000-alert) scale test of the night-aware split showed leakage
getting *worse*, not better, with more data (15/18 nights leaking vs 2/3;
object-conflict-resolution rows 2,653 -> 10,382) -- decisive, quantified
evidence that simultaneous `object_id` + `night_key` + `sky_cell` purity is
structurally unachievable for this survey's real training data: 10.4% of
real objects (7,645/73,560) are detected on more than one distinct night
(a physical repeat-detection rate that strictly worsens with more nights),
and ZTF's routine field-revisit cadence reobserves the majority of sky
cells across any time-block split. Operator-approved policy change
(2026-07-10): `src/grouped_splits.py`'s hard-gating groups are now
`("object_id",)` only; `night_key`/`sky_cell` moved to a new
`DEFAULT_MONITORED_GROUPS` -- still computed and reported
(`monitored_leakage`, `monitored_leak_rates`) but no longer block
`passed`. Re-running the (now sufficient) plain object-random split on the
real 18-night, 90,000-alert batch produces the first genuinely passing
report: `Logs/reports/tier2_cnn_v3_grouped_split_report.json`,
`passed=true`, `hard_leakage={}`, with honest disclosed monitored leak
rates (`night_key` 100%, `sky_cell` 91.3%). Full trail: five dated evidence
files in `docs/evidence/a7/` (single-night bug, first split-algorithm gap,
night-aware split + its own chronological-order bug, the 18-night scale
test, and this closing pass). Full suite 1843 passed / 2 deselected,
ruff/mypy clean throughout. **Remaining A7 blockers**:
`calibration_report_missing` (needs an actual `tier2_cnn_v2`/`v3` retrain +
`evaluate_calibration.py` run -- the retrain step needs PyTorch MPS/GPU
acceleration per `docs/SYSTEM_PROFILE.md`, and this sandboxed session found
`torch.backends.mps.is_available()` False here despite the real M4 Max GPU,
so a small-scale timing check is needed before committing to a full
20-epoch run) and `operator_signoff_missing` (inherently human-gated).

**Earlier sync (2026-07-10, v0.90.76)**: Ran the full v0.90.74 handoff
command sequence for real (commits `90bf12cc`, `3914824e`, `a9006211`).
Two real findings, both documented in `docs/evidence/a7/`:
1. **Fixed and verified**: `download_ztf_training_alerts.py --limit 10000`
   (and even `--limit 40000`) let a single night's tarball (40,000+ real
   alerts observed on 2026-07-09) satisfy the whole global limit before the
   loop ever reached night 2/3 -- `--nights 3` produced single-night data
   no matter how high `--limit` was raised. Fixed with a new
   `compute_per_night_target()` helper and `--per-night-limit` flag
   (default `ceil(--limit / --nights)`); verified a re-run now genuinely
   spans 3 distinct archive nights (20260707/08/09, ~13,332-13,334 alerts
   each, 36,038 distinct `object_id`). 3 new regression tests, all pass.
2. **Found, not yet fixed**: even with genuine 3-night data, the grouped
   split still fails `Skills/validate_grouped_splits.py` --
   `train_tier2_cnn.py --emit-split-csv` groups only by `object_id`, but
   the validator independently requires `object_id` AND `night_key` AND
   `sky_cell` purity. With only 3 real nights present, `night_key` purity
   requires assigning whole calendar nights to whole splits -- a coarser,
   statistically weaker split design (one night entirely determines each
   split) than the current object-random split. This is a genuine
   data-acquisition-scale / split-design tradeoff, not a bug: either accept
   whole-night splits, or acquire enough additional nights that whole-night
   assignment can put multiple nights in each split. **Flagged to the
   operator for direction (2026-07-10); not resolved unilaterally.** See
   `docs/evidence/a7/2026-07-10-second-attempt-object-id-split-still-leaks-night-and-sky.md`
   for full detail. `grouped_split_report_missing` remains open.

**Earlier sync (2026-07-10, v0.90.75)**: Operator ran step 1 of the v0.90.74
handoff below and reported total console silence, then killed the process.
**Root cause (found, not guessed)**: `Skills/download_ztf_training_alerts.py`'s
`download_night()` read the entire nightly tarball into memory via a single
blocking `resp.content` call with zero progress output during that read, and
none of the script's `print()` calls used `flush=True` -- so on any stdout
that isn't a raw interactive TTY (common under `uv run`/wrapped terminals),
Python's default block buffering withheld everything until the buffer filled
or the process exited. For a multi-hundred-MB-to-several-GB tarball, that
produced total silence for the whole download+decode, indistinguishable from
a hang. Fixed by porting this repo's own proven pattern from
`Skills/ztf_alert_archive_ingest.py`: HEAD the URL first for `Content-Length`,
stream-decode via `tarfile.open(mode="r|gz")` over a `_CountingReader`
wrapping `resp.raw` (never buffers the full tarball), print byte-level
progress with a measurable-quantity ETA every 200 scanned members
(`scanned=N kept=M  X/Y (Z%)  elapsed ...  ETA ...`), and add `flush=True` to
every print in the file. 1 new regression test asserts progress lines
actually appear. **Predicted operator console after this fix**: immediately
`ZTF public alert archive: ...` / `Nights to download: ...`, then per night
`Downloading YYYY-MM-DD: <url>` followed within seconds by `  Remote size:
<X>`, then periodic `  scanned=...` progress lines throughout the download
(not just at the end), then `  Done: scanned=... kept=... elapsed ...` and
the `+N alerts (total: ...)` summary. **If the console still goes silent
immediately after `Remote size:` and never shows a first `scanned=` line**,
the root cause was NOT buffering -- re-diagnose from that new symptom (e.g.
a network-level stall reading the response body) rather than patching this
same area again.

**Latest sync (2026-07-10, v0.90.74)**: Root-caused and fixed the
acquisition-side gap behind A7's `grouped_split_report_missing` blocker
(operator confirmed this plan). `Skills/download_ztf_training_alerts.py` now
captures each real ZTF alert's `object_id`, `candid`, `jd`, `ra`, `dec`,
`fid`, `field`, and the real archive night -- fields verified present in a
real downloaded packet (Gate Z3 evidence), not guessed.
`Skills/build_cutout_dataset.py` propagates them into `index.csv`.
`Skills/train_tier2_cnn.py` replaces `random_split()` (no leakage guarantee)
with a genuine grouped train/validation/test split by real `object_id`, and
gains `--emit-split-csv` to write a `Skills/validate_grouped_splits.py`-
compatible audit CSV matching the exact split a training run will use. 26
new tests, all offline (synthetic AVRO/CSV fixtures, no network calls).
**This is a code fix only** -- the frozen `benchmark_cnn_v1` and its
committed `data/ztf_labeled_alerts.json` are untouched. Closing the blocker
for real requires one operator-run download + retrain (not yet done):

```bash
git pull origin main
export PYTHONPATH=src

# 1. Download with real provenance captured (expect ~600MB-1GB, well under
#    the storage ceiling; --nights 3 typically satisfies --limit from the
#    first night's tarball, so this is usually 1-2 sequential large HTTP
#    GETs -- not sharded: too few independent units to benefit, and the
#    script would need explicit-date targeting to shard safely without
#    duplicate/overlapping night selection).
caffeinate -i uv run --python 3.14 python Skills/download_ztf_training_alerts.py \
    --nights 3 --limit 10000 \
    --output data/ztf_labeled_alerts_v2.json

# 2. Build cutout dataset + provenance-carrying index CSV
caffeinate -i uv run --python 3.14 python Skills/build_cutout_dataset.py \
    --input data/ztf_labeled_alerts_v2.json \
    --output-dir data/cutouts_v2/ \
    --csv data/cutouts_v2/index.csv

# 3. Emit the real grouped split and validate it (A4 evidence)
uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v2/index.csv \
    --emit-split-csv data/cutouts_v2/grouped_split.csv
uv run --python 3.14 python Skills/validate_grouped_splits.py \
    data/cutouts_v2/grouped_split.csv > Logs/reports/tier2_cnn_grouped_split_report.json

# 4. Retrain, gated on the real passing grouped-split report (not sharded --
#    single GPU/MPS training job; SYSTEM_PROFILE.md says use full local
#    compute headroom here, not multiprocessing)
caffeinate -i uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v2/index.csv \
    --epochs 20 \
    --out models/tier2_cnn_v2.pt \
    --grouped-split-report Logs/reports/tier2_cnn_grouped_split_report.json \
    --production-candidate

# 5. Re-run calibration on the new model (closes the 2nd A7 blocker)
caffeinate -i uv run --python 3.14 python Skills/evaluate_calibration.py \
    --alerts data/ztf_labeled_alerts_v2.json \
    --cutouts-csv data/cutouts_v2/index.csv \
    --cnn-model models/tier2_cnn_v2.pt \
    --report-out Logs/reports/calibration_report_v2.json
```

Naming note: this produces a new candidate (`tier2_cnn_v2`/a future
`benchmark_cnn_v2`), not a silent overwrite of the frozen `benchmark_cnn_v1`
-- per A3's freeze policy ("do not keep casually tuning this model"), the
existing benchmark stays as historical baseline. A follow-up promotion
report for the new candidate (citing steps 3-5's real outputs) is the next
coding step once this run completes; `operator_signoff_missing` remains the
final, inherently human-gated blocker after that.


**Earlier syncs (v0.90.68–v0.90.73)** covering the A1/A2/A3/A4/A5/A6/A7
gate buildout are archived in `docs/HANDOFF_HISTORY.md` — read only for
historical context on how a specific gate was closed; not needed to act on
the pending v0.90.74 command above.


All 10 pipeline modules are complete. The offline suite passes on Python 3.14
with the 100% coverage target in CI. All three ML tiers have trained weights:
Tier 1 XGBoost (val_acc=99.95%), Tier 2 CNN (val_acc=91.3%), and Tier 3
Transformer (val_macro_f1=0.9400, best epoch 17/30). Under the 2026-07-08
Astrometrics roadmap, trained weights are not the same thing as promotion:
model promotion now requires the remaining A-gates as applicable. The CNN is
now frozen as `benchmark_cnn_v1`, but grouped split reports, canonical evals,
injection-recovery curves, and a promotion report are still required before
any CNN-derived production-promotion claim.
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
ZTF live alert-stream discovery remains prohibited. Gates Z1, Z2, Z4, Z5,
Z6, and Z7 are closed with real evidence. Gate Z3's source-verification
blocker is closed — the University of Washington's public ZTF alert archive is
a real, unauthenticated, schema-verified per-detection source — but Gate Z3 as
a whole remains open because four candidate-pair attempts have not produced a
confirmed single-object positive-control recovery. The older ALeRCE-backed
source provider is real bounded-pilot evidence, but
`docs/evidence/phase0/alerce_source_detection_assessment.md` records why it is
not the current DR24 production path.

**Full dated handoff log (2026-06-17 through 2026-07-05 v58, plus the
original T1-C recovery-evidence trail and the superseded WISE/DECam/TESS
"Immediate Next Steps" evidence trail)** is archived in
`docs/HANDOFF_HISTORY.md`. It is not required session-start reading —
consult it only for historical context on a specific gate, blocker, or bug.

### Skills

| Script | Purpose |
|---|---|
| `Skills/smoke_test.py` | Happy-path check for all modules; exits 0 on success |
| `Skills/evaluate_calibration.py` | Brier/ECE evaluation for Platt and isotonic calibrators |
| `Skills/generate_training_labels.py` | Download Tier 1 labels or build the approved four-class MPC Tier 3 pilot manifest |
| `Skills/batch_score.py` | Score a list of tracklets from a JSON file; print ranked table |
| `Skills/run_pipeline.py` | Full end-to-end pipeline run |
| `Skills/select_survey_fields.py` | Algorithmically ranks sky fields for `Skills/run_pipeline.py` by known-object density, geometry, and novelty (`--mode recovery` for known-object-rich fields; `--wise-archive-probes` attaches ready-to-run WISE scale-plan commands); `--write-target-queue` appends real, computed selection results to `data_selection/target_priority_queue.csv` per the data-selection policy's "documented selection rule before execution" requirement — this is the canonical way to pick a target field, not a manual RA/Dec guess or an operator-provided known-object lookup |
| `Skills/injection_recovery.py` | Injection-recovery test: injects synthetic NEOs, measures detection/link/score rates; `--image-level` sweeps seeing/background/trail-length via synthesized difference cutouts for A6 recovery curves |
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
| `Skills/evaluate_ranking_baseline.py` | Gate Z4 auditable ranking baseline: evaluates a handcrafted-feature logistic-regression classifier (out-of-fold, stratified k-fold) against real archived negative tracklets (Gate Z6 evidence) and synthetic positive tracklets (established injection generator), reporting recall@K, purity@K, calibration error, false-positive review burden, and an ablation vs. a naive real-bogus-only baseline; `--n-positive`, `--seed`, `--checkpoint-dir`, `--out` flags |
| `Skills/evaluate_retrospective_validation.py` | Gate Z5 retrospective validation: evaluates review packets against the MPC catalog as queried today (after the replay window, by design), bucketing each into `recovered_known_object`/`later_confirmed_object`/`artifact`/`unresolved_candidate` using the already-real `check_candidates_against_mpc` live cross-match plus each packet's own `known_object_score`; `--review-packets`, `--verdicts`, `--radius-deg`, `--out` flags |
| `Skills/extract_promotion_evidence.py` | A7 promotion-report input derivation: pulls the nested `recovery_curves` object out of an `injection_recovery.py --image-level` report and derives a `false-discovery-report-v1` from a `evaluate_ranking_baseline.py` report's real `false_positive_review_burden` counts, without inventing any new data; `--injection-recovery-source/-out`, `--ranking-baseline-source/-model`, `--false-discovery-out` flags |
| `Skills/validate_dataset_manifest.py` | A1 dataset manifest schema validator; checks one or more manifest JSON files against `data_selection/dataset_manifest.schema.json` |
| `Skills/candidate_ledger.py` | A2 candidate ledger CLI (thin wrapper over `src/candidate_ledger.py`); `init` creates/migrates the SQLite ledger, `ingest` loads pipeline candidate JSON, `list` prints ledger rows as JSON |
| `Skills/audit_real_run.py` | Builds a fail-closed T1-C audit packet from a real `run_pipeline.py` checkpoint/run summary; observation-level evidence only, no external contact or submission |
| `Skills/run_archive_positive_control.py` | Gate Z3 known-object positive control: loads real per-source ZTF alert archive checkpoints for ≥2 real nights and runs them through the real preprocess→detect→link pipeline to check for a genuine known-object recovery |
| `Skills/lookup_neo_archive_ephemeris.py` | Gate Z3 targeted candidate-night lookup for a real, known NEO against the ZTF alert archive |
| `Skills/lookup_mpc_observation_history.py` | Gate Z3: cross-checks a known NEO's real MPC-confirmed observation history against the ZTF alert archive's coverage window |
| `Skills/scan_mpc_history_ztf_coverage.py` | Gate Z3: scans a known NEO's real MPC-confirmed observation history for real ZTF coverage overlap |
| `Skills/scan_neo_track_coverage.py` | Gate Z3: scans a known NEO's real predicted track for real ZTF coverage |
| `Skills/probe_ztf_alert_archive_file.py` | Gate Z3: bounded single-file verification probe for the UW public ZTF alert archive |
| `Skills/ztf_dr24_bounded_ingest.py` | Gate Z1 bounded ZTF DR24 historical replay ingest (dry-run, metadata only) |
| `Skills/diagnose_wise_query.py` | Diagnostic: probes the IRSA NEOWISE query directly with full error reporting, bypassing the pipeline's caching/retry layers |
| `Skills/_live_connection_test.py` | Internal helper invoked by `Skills/verify_live_credentials.sh`; tests live ATLAS/ZTF credential connectivity without printing secret values |
| `Skills/load_credentials.py` | Loads project credentials (ATLAS/ZTF) from macOS Keychain into environment variables; called at the start of any Skill needing live network credentials |
| `Skills/train_ensemble_stacker.py` | Trains the 10-feature ensemble stacking meta-learner (logistic regression) over Tier 1 XGBoost + Tier 2 CNN outputs; saves `models/stacker_coef.json`; supports `--grouped-split-report`/`--production-candidate` |
| `Skills/run_canonical_evals.py` | A5 canonical regression eval suite runner; evaluates a frozen `canonical_evals/*.json` suite and reports pass/fail per case with `--out` for a persisted report |

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
| `data/injection_recovery_image_level_n200.json` | A6 image-level injection-recovery results (n=200, seed=42, `--image-level`): 7.5% detection/link/score with real per-bin seeing/background/trail-length recovery curves |
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

**Goal: defensible discovery paper** (established 2026-06-26 with operator
Jerome W. Lindsey III; active path is ZTF DR24 archival historical replay,
per DECISION-001 above and `docs/MISSION.md §Operator Decision
(2026-07-02)` — WISE/DECam/TESS is secondary/paused).
Pipeline generates candidates → adversarial review filters → operator
reviews survivors → MPC submission → provisional designation → independent
confirmation → journal paper.

Steps 1-3 of the original v0.90.74 handoff (download with real provenance,
build cutout dataset, emit + validate grouped split) are now DONE for real
— see the v0.90.77/78 entries above: `grouped_split_report_missing` is
CLOSED with a real passing report on an 18-night, 90,000-alert batch. The
concrete next action is the retrain + recalibrate command block in the
v0.90.78 entry under **Current State** above. That command has **not yet
been run** — it needs an unsandboxed terminal with real MPS/GPU access
(this session's sandbox verified both MPS and multiprocess DataLoader
workers are blocked here specifically, not by the code or hardware). After
it completes, the next coding step is a promotion report for the new
`tier2_cnn_v3` candidate citing the real grouped-split and calibration
reports; `operator_signoff_missing` remains the final, inherently
human-gated blocker after that. The superseded WISE/DECam/TESS
discovery-sweep evidence trail (pre-2026-07-02 pivot) is archived in
`docs/HANDOFF_HISTORY.md` for historical context only.

### Version-by-Version Changelog

See `CHANGELOG.md` (authoritative; updated on every version bump per the
"Sync docs and changelog" standing rule above) for the full v0.1.0-through-
current changelog. This file's own former per-version "Key Changes" section
(v0.6.0–v0.87.9) is archived verbatim in `docs/HANDOFF_HISTORY.md` — note
that `CHANGELOG.md` has no per-version entry for v0.87.1–v0.87.9, so the
archive is the only record of that range; do not delete it.
