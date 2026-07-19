# Hunter PROD Directive

**Established**: 2026-07-19, by Jerome W. Lindsey III.
**Scope**: applies independently to three sibling repos — NEO-Hunter (this
repo, `2026 Near Earth Objects`), Techno-Hunter (`2026 Technosignatures`),
and EXO-Hunter (`2026 Exoplanet Research`). Each repo runs in an isolated
sandbox; this session has no access to the other two and must not assume
their state. The three should share common CLI/lifecycle/provenance
semantics where practical, but each must remain independently buildable,
testable, and runnable.

**Relationship to this repo's existing roadmap**: this directive does not
contradict the three-phase roadmap recorded in `CLAUDE.md`'s "Current
Roadmap Phase" section (harden detection pipeline → harden search
algorithm → package the application) — it is a more complete, cross-project
specification of what "package the application" (Phase 3) concretely means,
and it reframes "harden the search algorithm" (Phase 2) in terms of a
specific ranking/selection/durable-state model. Phase 1's two named gaps
(missing real/bogus score for pixel-extraction candidates; `fit_orbit()`
returning `quality_code: null` for every short-arc candidate) remain the
active, concrete next work and map onto this directive's "eligibility" and
"scoring" pipeline stages below.

Verbatim text follows.

---

HUNTER PROD DIRECTIVE
Applies independently to:
* NEO-Hunter
* Techno-Hunter
* EXO-Hunter
Each repo runs in an isolated sandbox. Do not assume access to another repo. The projects should follow the same Hunter architecture contract where practical, but each implementation must remain independently buildable, testable, and runnable.

## HARD INVARIANTS
Always optimize for this sequence:
READ HISTORY → MAP PIPELINE → CLOSE GAPS → BUILD END-TO-END → VERIFY → DOCUMENT PR → CONTINUE LOOP

Never violate these rules:
1. Core application logic must work without AI.
2. No required pipeline gaps or undocumented manual bridges.
3. Never overwrite search history or provenance.
4. Never silently substitute targets, data, results, or failed work.
5. Never declare partial work PROD.
6. Do not stop for routine, reversible, nondestructive work.
7. Do not repeat failed strategies in a doom loop.
8. Write compact, direct, maintainable code.

## SESSION START
Before editing:
1. Read repo instructions, architecture/specs, relevant tests, and current TODOs.
2. Read the 3 most recent PRs, including descriptions, review comments, and discussion.
3. Inspect relevant recent commits.
4. Verify current behavior.
5. Map the complete production pipeline and identify the highest-priority gap.
Do not blindly continue a prior agent's plan.

Maintain this working checklist:
- [ ] Last 3 PRs read
- [ ] Current state verified
- [ ] Pipeline mapped
- [ ] Highest-priority gap identified
- [ ] End-to-end path remains intact
- [ ] No AI dependency introduced
- [ ] Durable history/provenance preserved
- [ ] Relevant tests pass
- [ ] PROD definition checked
- [ ] PR handoff updated

## MISSION
Bring this repo completely across the PROD threshold. The application must support this complete path:

candidate universe → identity/history resolution → eligibility → ranking/selection → manifest → durable search creation → data acquisition → preprocessing → scoring → composite interpretation → durable results/provenance → follow-up creation → follow-up recommendation

No required stage may depend on an undocumented manual workaround. For every stage, verify:
* required inputs exist;
* outputs are valid and durable where required;
* the next stage actually consumes them;
* schemas agree;
* failures are visible;
* restart/resume works where needed.

Fix pipeline gaps before polishing isolated components.

## REQUIRED CLI
Shell entry points: NEO-Hunter, Techno-Hunter, EXO-Hunter.

Core workflow:
- `/Create-New-Search --targets <N> --mode <new|follow-up>`
- `/Run-New-Search`
- `/Show-Follow-Ups`

The CLI must be polished and usable in its own terminal tab with:
* restrained semantic color;
* useful progress/animations;
* readable tables;
* clear failures;
* scriptable/non-interactive operation.

Visual polish is secondary to correctness and pipeline completeness.

## SEARCH MODEL
Support two modes:

**New**: select promising eligible targets not previously searched under the applicable revisit policy.

**Follow-Up**: select prior targets searched by this project, another internal project, or external researchers/projects where reliable provenance exists.

Never erase or overwrite history. Preserve: who searched; when; why; source/project; method/data; result; follow-up relationships.

Candidate selection must:
* evaluate a much larger pool than requested;
* target roughly 100 selected from 10,000+ viable candidates when data permits;
* be deterministic, explainable, reproducible, and testable;
* use project-appropriate scientific metrics;
* consider prior searches, novelty, expected information gain, suitability, data availability, storage/compute cost, prior results, follow-up value, and identity resolution.

Do not use opaque LLM judgment as core ranking logic.

## DURABLE STATE
Maintain distinct durable concepts for:
1. candidate catalog;
2. search manifest;
3. search run;
4. target search history;
5. follow-up registry.

Use stable IDs, explicit relationships, timestamps, provenance, and versioned schemas. CSV manifests are for operator review, not the durable system of record.

Every search run must preserve: exact selected targets; configuration; inputs/data provenance; code/model/scorer versions; individual scores; composite result; interpretation; failures; execution state; follow-up disposition.

## SEARCH WORKFLOW

**Create**: `/Create-New-Search` must rank/select targets and create a durable pending search. For <=100 targets, show a terminal table. For >100 targets, write a timestamped CSV to the Search Manifest Directory and print the path and concise summary. Useful fields include: primary and canonical identifiers; object/classification; distance where meaningful; storage/compute estimate; new/follow-up status; prior-search provenance; ranking score; selection reason; project-specific metrics.

**Run**: `/Run-New-Search` must execute the exact pending search. Never silently regenerate the candidate list. Persist all applicable: scorer outputs; scorer versions; composite result; interpretation; anomalies/evidence; failures; provenance. Partial execution must never appear complete. Failures must be loud and resumable. Evidence-based follow-up candidates must be durably registered.

**Follow-Ups**: `/Show-Follow-Ups` must show enough information to act: target; evidence/results; reason flagged; prior-search provenance; priority; recommended next action.

## CROSS-PROJECT CONTRACT
The three repos should share common semantics for: CLI workflow; search lifecycle; durable entities; provenance; failure/status handling; manifests; follow-ups; recovery; PROD acceptance. Keep domain-specific: candidate sources; scientific features; ranking; scorers; thresholds; interpretation.

Do not create runtime coupling through: relative cross-repo imports; symlinks; unpublished shared code; assumptions about another sandbox. A separately versioned shared package may be created later if clearly justified. It must not block PROD.

## IMPLEMENTATION RULES
Write compact code. Prefer: simple control flow; small coherent modules; minimal duplication; abstractions only where they reduce real repetition; deletion of replaced/dead paths.

Avoid: speculative frameworks; unnecessary compatibility layers; giant functions; cryptic compression; production stubs; fake data; placeholder implementations; TODO-based production paths.

Use the simplest production-safe implementation. Parallelize safely parallelizable bottlenecks. Preserve determinism, data integrity, rate limits, reproducibility, and resumability. Avoid duplicate downloads, computation, and searches. Persistence must be durable, versioned, recoverable, and tested. Scientific thresholds and weights must be evidence-based and provenance-stamped.

## AGENT LOOP
Stay in the execution loop until PROD is actually achieved or a genuine blocker requires the operator. Do not interrupt for: routine decisions; reversible choices; nondestructive commands; testing; ordinary refactoring; repo inspection; dependency inspection; documentation lookup; research the agent can perform itself.

Every task must directly advance PROD or a necessary prerequisite. After each meaningful work unit: CHECK PIPELINE → TEST → IDENTIFY NEXT HIGHEST-PRIORITY GAP → CONTINUE. Do not drift into unrelated cleanup. Use tokens efficiently. Do not repeatedly rediscover settled facts. Persist important decisions in the repo and PR.

## NO DOOM LOOPS
Do not repeatedly retry the same failed strategy. On repeated failure: diagnose → gather new evidence → change approach → test again. Before escalating, exhaust: repo → last 3 PRs → relevant history/docs → authoritative research → safe alternative approaches.

Escalate only for genuine blockers such as: missing credentials; unavailable required access/information; destructive approval; an irreducible material product/scientific decision. Use the BLOCKER/WHY I NEED YOU/WHAT I TRIED/RECOMMENDATION/QUESTION/RESEARCH-AGENT PROMPT format.

## PR HANDOFF
Every PR must leave enough context for the next agent to reconstruct the session without guessing. Include: objective; material changes; important decisions; tests and results; known gaps/risks; exact next work. Do not write vague summaries.

## DEFINITION OF DONE
Do not claim PROD until the repo demonstrably performs, without AI or undocumented manual intervention: launch → build large candidate pool → resolve identity/history → rank/select new or follow-up targets → create/show/export manifest → durably create exact search → acquire/process required data → run applicable scorers → generate composite interpretation → persist complete results/provenance → create follow-ups → recommend next actions → recover correctly after restart.

Mocks, scaffolding, planned work, and partial paths do not count. At completion report only: (1) changes made; (2) exact run commands; (3) tests and results; (4) remaining limitations; (5) evidence against each PROD requirement.
