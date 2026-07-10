# NEO Detection & Ranking Project — Handoff History Archive

This file archives detailed dated handoff notes and superseded status
entries that were previously kept inline in `CLAUDE.md`. It is a
historical record, **not** a mandatory session-start read — consult it
only when you need the specific history behind how a gate, blocker, or bug
was resolved. `CLAUDE.md`'s "Current State" section always carries the
latest status and the actual pending next action; this file exists so that
mandatory file stays a manageable size instead of growing without bound.

Entries below are reproduced verbatim from prior `CLAUDE.md` revisions, in
the same reverse-chronological order they previously appeared in. Nothing
in this file should be treated as describing current project state unless
cross-checked against the live `CLAUDE.md` and `docs/PRODUCTION_READINESS.md`.

---

## Latest-sync entries (v0.90.68 – v0.90.73)

**Latest sync (2026-07-10, v0.90.73)**: A1 now has four real, committed
dataset manifests under `data_selection/dataset_manifests/`
(`ztf_labeled_alerts_tier2_cnn_v1`, `gate_z4_ranking_baseline_v1`,
`gate_z6_retrospective_validation_v1`,
`a6_injection_recovery_image_level_n200_v1`), each populated from computed
facts (checksums) or already-documented project history — never guessed.
Citing the training manifest in the A7 promotion report closes the
`dataset_manifest_missing` blocker for real: `benchmark_cnn_v1`'s promotion
report now shows 6/8 evidence checks passing with only **three** real named
blockers left (grouped-split report, calibration report, operator signoff),
down from four.

**Latest sync (2026-07-10, v0.90.72)**: A7's promotion-report builder has now
been run for real against `benchmark_cnn_v1`. New `Skills/extract_promotion_evidence.py`
derives an injection-recovery report and a false-discovery report from
already-committed real evidence (A6's image-level baseline and Gate Z4's
ranking-baseline review-burden counts: 0/200 false positives) without
inventing any data. `Skills/build_promotion_report.py` then produced a real,
committed report — `promotion_allowed=false` with 4 real named blockers
(dataset manifest, grouped-split report, calibration report, operator
signoff). Root-cause finding: `data/ztf_labeled_alerts.json` (the CNN's
committed 10,000-alert training source) never captured per-alert RA/Dec/JD
metadata, so a real grouped split cannot be reconstructed for it — this is
why A4/A1 remain open for the CNN's training set specifically, not a coding
gap. See `docs/PRODUCTION_READINESS.md` for detail.

**Latest sync (2026-07-09, v0.90.71)**: A6 now closes the image-level gap:
`Skills/injection_recovery.py --image-level` synthesizes a real
difference-image cutout per injection (Gaussian PSF + background noise +
trail elongation) and derives `real_bogus` from its analytic peak SNR, so
seeing/background/trail-length sweeps produce real, non-degenerate recovery
curves through the actual `detect()`/`link()`/`classify()`/`score()` chain.
A real n=200, seed=42 baseline is committed at
`data/injection_recovery_image_level_n200.json` (7.5% detection/link/score
rate). All five required A6 dimensions (magnitude, velocity, observation
count, night count, and now seeing/background/trail length) are covered. See
`docs/PRODUCTION_READINESS.md` for detail.

**Latest sync (2026-07-09, v0.90.70)**: A5 now has a frozen, policy-grade
canonical eval suite (`data_selection/canonical_evals/production_suite_v1.json`)
covering all four required case types, every case citing a real,
already-committed evidence artifact (the n=200 injection-recovery baseline,
the Gate Z4 ranking-baseline purity/ablation report, the Gate Z6
retrospective-validation report, and a real, unconfirmed Gate Z3 known-NEO
recovery attempt transcribed to
`docs/evidence/canonical_evals/known_neo_recovery_72966_no_match.json`). This
closes A5 for model-builder-independent regression protection; per-model
canonical suites remain part of A7. See `docs/PRODUCTION_READINESS.md` for
detail.

**Latest sync (2026-07-09, v0.90.69)**: All four model-builder Skills
(`train_tier1_xgboost.py`, `train_tier2_cnn.py`, `train_tier3_transformer.py`,
and `train_ensemble_stacker.py`) now share the same A4 fail-closed
`--grouped-split-report`/`--production-candidate` gate via a shared
`grouped_splits.load_grouped_split_gate` helper. `train_tier2_cnn.py` also
gained `--dry-run` (previously absent) so the gate can be checked without a
full CNN training run. This closes "broader model-builder adoption" from the
v0.90.68 note below; promotion-report wiring with real, model-specific
evidence packets remains open. See `docs/PRODUCTION_READINESS.md` for detail.

**Latest sync (2026-07-09, v0.90.68)**: The Astrometrics coding-agent,
data-selection, and external/cloud-storage policy docs are now mandatory
session-start reads and have repo-local operational scaffolds under
`data_selection/` and `storage/`. The active ZTF DR24 posture is unchanged:
Z1, Z2, Z4, Z5, Z6, and Z7 are closed; Z3 is the only open gate and its
candidate-pair search remains intentionally paused unless the operator
explicitly restarts that path. The most productive non-blocked work is now
policy-backed data selection, storage, ranking, validation, and evidence
hardening, not another unapproved Z3 pair attempt. A1 now has a committed
manifest schema and validator; `Skills/run_pipeline.py` can now cite a source
dataset ID in audit summaries. A2 now has an initial SQLite candidate ledger
schema/CLI plus optional run-pipeline ingestion via `--candidate-ledger-db`.
Both remain partially open until policy-grade manifests cover every real
dataset role and operator production runs routinely use the manifest/ledger
flags. A3's freeze step is complete:
`benchmarks/benchmark_cnn_v1/` wraps `models/tier2_cnn.pt` with locked
preprocessing, config, score/train entrypoints, tests, and a model card. A4
now has initial grouped split/leakage controls in `src/grouped_splits.py` and
`Skills/validate_grouped_splits.py`; `Skills/train_ensemble_stacker.py` now
requires a passing grouped split report when `--production-candidate` is set.
Broader model-builder adoption and promotion report wiring remain open. A5 now
has a fail-closed canonical regression eval
engine in `src/canonical_eval.py` and `Skills/run_canonical_evals.py`; frozen
production suites covering known-NEO recovery, false links, injection-recovery,
and review-packet examples remain open. A6 now has synthetic-harness recovery
curves by magnitude, motion rate, observation count, and night count; image-level
seeing/background/trail-length curves remain open. A7 now has a fail-closed
promotion packet builder in `src/promotion_report.py` and CLI wrapper in
`Skills/build_promotion_report.py`; real model-specific evidence packets still
need to be generated before any production promotion claim.

---

## Dated handoff states (2026-06-17 through 2026-07-05 v58, plus the original T1-C recovery-evidence trail)

### Handoff state as of 2026-07-05 v58 (previous current; superseded by v0.90.60 addendum)

**Gate Z2 is CLOSED** — operator ran a live JPL SBDB query appending
`first_obs` to the already-verified `sb-group=neo` query (exact base URL
reused from `Skills/verify_ztf_dr24_sources.py`, no new endpoint or
schema guessed):

```bash
curl -s "https://ssd-api.jpl.nasa.gov/sbdb_query.api?fields=spkid,pdes,full_name,first_obs&sb-group=neo&full-prec=true&limit=3"
```

Real result: `first_obs` returned populated with real dates for all 3
sampled NEOs (433 Eros: 1893-10-29; 719 Albert: 1911-10-04; 887 Alinda:
1918-02-09) out of 42,153 total NEOs matched — not null, not a
placeholder. This confirms the mechanism `src/known_object_exclusion.py`'s
`known_as_of()` depends on is real and live-working, not just
documented-but-unverified. `src/known_object_exclusion.py`'s docstring
updated to remove the "NOT YET LIVE-VERIFIED" warning. Full evidence:
`docs/evidence/live/2026-07-05-gate-z2-first-obs-verified.md`.
`docs/ZTF_DR24_PRODUCTION_GATES.md`'s Z2 row updated to **CLOSED**.

**Research note**: this sandbox's egress policy blocks direct
`WebFetch`/`curl` access to `ssd-api.jpl.nasa.gov` (403 at the proxy —
an organization policy denial, correctly not routed around). The exact
`fields=` query-parameter syntax was instead confirmed via `WebSearch`
against the official SBDB Query API docs before handing the operator a
command, rather than guessing it.

**This is a docs/evidence + docstring-only commit — no functional code
changed, no version bump.**

**Next production action**: with Z1, Z2, Z4, Z6, Z7 all CLOSED and Z5
also CLOSED, the only remaining open ZTF DR24 gate is **Z3** (candidate-
pair search), still paused pending explicit operator direction per the
standing note below. Exercising Z2's `known_as_of()` end-to-end against
a real linked tracklet (rather than the field-return check just done)
still depends on Z3 resuming. No further coding-agent scoping work
remains on any gate except Z3, and Z3 must not be resumed without the
operator's explicit choice of path.

**Standing note on the Gate Z3 candidate-pair search (unchanged, still in
force)**: do not propose a 5th apparition of designation 72966, or a
different NEO designation, without first getting explicit operator
direction. Wait for their call before resuming that specific
investigation thread.

### Handoff state as of 2026-07-04 v57

**Gate Z4 and Gate Z5 are both CLOSED with real data** — operator ran
both new evaluators to completion. Real results:

1. `Skills/evaluate_ranking_baseline.py --n-positive 200 --seed 42`:
   200 synthetic positives + 142 real archived negatives (88 from
   20220817/20220819, 54 from 20210106/20210111), completed in 5.7s. The
   handcrafted-feature logistic-regression baseline scored ECE=0.044,
   Brier=0.00197, and **perfect purity@K (1.0) at K=5/10/20/50 with 0/200
   false positives** at the 0.5 threshold — vs. the naive real-bogus-only
   baseline's ECE=0.313 and purity@5/10/20=0.0. Real finding: real
   archived negative tracklets already pass the `rb >= 0.5` real/bogus
   gate (they're genuine detections, just mis-paired across nights), so
   real_bogus alone cannot separate them from true positives — exactly
   the ablation value Gate Z4 asks the handcrafted multi-feature model to
   demonstrate.
2. `Skills/evaluate_retrospective_validation.py` against the real
   88-candidate Gate Z6 review-packet set, with 88 real live
   `MPC.query_objects_in_region` calls: `{"recovered_known_object": 0,
   "later_confirmed_object": 0, "artifact": 88, "unresolved_candidate":
   0}` — the correct, expected result, since these 88 are already known
   (Gate Z6) to be combinatorial cross-night artifacts, not real objects.

Both report JSONs are committed at `Logs/reports/ranking_baseline.json`
and `Logs/reports/retrospective_validation.json` (this directory is
allowlisted in `.gitignore` for exactly this). Full evidence and
closure assessment: `docs/evidence/live/2026-07-04-gate-z4-z5-closed.md`.
`docs/ZTF_DR24_PRODUCTION_GATES.md`'s Z4 and Z5 rows both updated to
**CLOSED**.

**This is a docs/evidence-only commit — no code changed, no version
bump** (the code that made this possible already shipped in
v0.90.58/v0.90.59, PRs #205/#206).

**Next production action**: with Z1, Z4, Z6, Z7 all CLOSED and Z5 also
CLOSED, the only remaining open ZTF DR24 gates are **Z2** (time-aware
known-object exclusion — code-complete, needs one live JPL SBDB query
confirming the `first_obs` field is actually returned; the exact query
syntax is not yet verified in this codebase and should not be guessed —
needs official JPL SBDB Query API doc research first, ideally via the
operator's research agent) and **Z3** (candidate-pair search — still
paused pending explicit operator direction, per the standing note below,
unchanged). No further coding-agent scoping work remains on Z4/Z5/Z6/Z7.

**Standing note on the Gate Z3 candidate-pair search (unchanged, still in
force)**: do not propose a 5th apparition of designation 72966, or a
different NEO designation, without first getting explicit operator
direction. Wait for their call before resuming that specific
investigation thread.

### Handoff state as of 2026-07-04 v56

**Gate Z5 (retrospective validation) tooling built and offline-tested;
pending one operator run for a real-data closure result** —
`Skills/evaluate_retrospective_validation.py` (v0.90.59) evaluates
historical-replay review packets against the MPC known-object catalog as
queried *today* (deliberately after the replay window -- that is the
whole point of retrospective validation, and a distinct, legitimate use
of "future" data from the no-future-catalog-leakage rule that governs
replay-time exclusion in `src/known_object_exclusion.py`; nothing here
feeds back into replay-time candidate selection). Buckets each candidate
into `recovered_known_object`, `later_confirmed_object`, `artifact`, or
`unresolved_candidate`, reusing the already-real, already-used
`Skills/check_mpc_known.py:check_candidates_against_mpc` live sky-position
cross-match plus each packet's own already-computed `known_object_score`
— deliberately NOT depending on JPL SBDB's `first_obs` field, which
`src/known_object_exclusion.py` explicitly flags as not yet
live-verified (building a new gate on an unverified mechanism would
compound one guess onto another). 8 new offline tests, all network calls
injected via an `mpc_lookup_fn` parameter — no real network call is ever
made in the test suite.

**Next production action (NOT YET DONE)**: run the new tool against real
review packets (e.g. the ones Gate Z6 already produced) with live MPC
network access:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/evaluate_retrospective_validation.py \
    --review-packets Logs/pipeline_runs/run_archive_positive_control/report_with_packets.json \
    --out Logs/reports/retrospective_validation.json
```

If an `adversarial_review.py --json` verdicts file also exists for the
same packets, pass it via `--verdicts <file>.json` to get more precise
`artifact` vs. `unresolved_candidate` bucketing. Read the printed
`outcome_counts` line to close Gate Z5 with a real result. With this and
Gate Z4's evaluator both landed, both remaining open ZTF DR24
production-capability gates (Z4, Z5) now have code-complete, offline-
tested tooling awaiting only an operator run — no further coding-agent
scoping work is needed on either until those runs report back.

**Standing note on the Gate Z3 candidate-pair search (unchanged, still in
force)**: do not propose a 5th apparition of designation 72966, or a
different NEO designation, without first getting explicit operator
direction. Wait for their call before resuming that specific
investigation thread.

### Handoff state as of 2026-07-04 v55

**Gate Z4 (auditable ranking baseline) tooling built and offline-tested;
pending one operator run for a real-data closure result** —
`Skills/evaluate_ranking_baseline.py` (v0.90.58) evaluates a
handcrafted-feature logistic-regression ranking baseline (via
`classify.extract_features`/the new public `classify.features_to_vector`,
out-of-fold stratified k-fold, never scored on data it was fit on)
against real archived negative tracklets (reusing the Gate Z6-evidenced
20220817/20220819 and 20210106/20210111 checkpoints already on disk — no
new download) and synthetic positive tracklets (the project's established
injection generator). Reports recall@K, purity@K, calibration error
(Brier/ECE/log-loss), false-positive review burden, and an ablation vs. a
naive real-bogus-only baseline — exactly Gate Z4's stated closure
requirement. 10 new offline tests pass against synthetic fixtures
(`tests/test_evaluate_ranking_baseline.py`).

**Also synced this session**: `AGENTS.md` and `docs/PRODUCTION_READINESS.md`
had drifted ~30 versions stale (still described v0.90.27/2026-07-02)
despite being mandatory session-start docs; both now carry a condensed
delta paragraph pointing at this file's full handoff and
`docs/ZTF_DR24_PRODUCTION_GATES.md` for current gate status, without
rewriting their preserved historical detail.

**Next production action (NOT YET DONE)**: run the new tool against the
real archived checkpoints already on disk from the Gate Z3/Z6 work (no new
network access, no new download):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/evaluate_ranking_baseline.py \
    --n-positive 200 --seed 42 \
    --out Logs/reports/ranking_baseline.json
```

This defaults to the two real night-pairs already ingested this project
(`20220817`/`20220819` and `20210106`/`20210111`) as the negative class and
200 synthetic injected tracklets as the positive class. Read the printed
recall@K/purity@K/ECE lines for both the logistic-regression baseline and
the naive real-bogus-only ablation to close Gate Z4 with a real result.

**Standing note on the Gate Z3 candidate-pair search (unchanged, still in
force)**: do not propose a 5th apparition of designation 72966, or a
different NEO designation, without first getting explicit operator
direction. Wait for their call before resuming that specific
investigation thread.

### Handoff state as of 2026-07-04 v54

**Gate Z7 (operator runbook update) is CLOSED** — with Gate Z6 merged
(PR #204), the next fully code-addressable, non-gambling gate was Z7:
`docs/OPERATOR_GO_NO_GO_RUNBOOK.md` was written entirely for the secondary
WISE/DECam/TESS path (Gate P5) and had no ZTF DR24-specific content. Added
a "ZTF DR24 path" section covering: the real packet location
(`run_archive_positive_control.py --build-review-packets`'s
`review_packets` key), the UW ZTF alert archive source-attribution rule
(already verified in Gate Z3 evidence, not re-derived), the same
operator review checklist as the WISE path, and an explicit statement
that ZTF DR24 archival MPC submission authority is **not yet confirmed in
writing** — the `stn=XXX` default not failing closed (unlike WISE's
`stn=C51`) does not constitute that confirmation. Cites the real Gate Z6
drill as the verified basis for every command in the new section. This is
a docs-only change; no code modified, no version bump.

**Next production action**: with Z6 and Z7 both closed, the remaining open,
non-gambling ZTF DR24 gates are Z4 (auditable ranking baseline: handcrafted
features + logistic-regression baseline evaluated before LightGBM/XGBoost,
with recall@K/purity@K/calibration/ablation metrics) and Z5 (retrospective
validation against later MPC/JPL outcomes, no future leakage). Both are
code-and-offline-data tasks — no archival download or operator live run
required to make initial progress. Z2 remains "pending operator field
verification" (needs a live JPL SBDB query with `first_obs` added) and Z3
remains on hold per the standing note below. Recommend starting Z4 next,
since it is a pure ranking/evaluation exercise runnable against the
synthetic/injection-recovery data already in `data/` plus the real
archived tracklets already on disk, without needing operator action.

### Handoff state as of 2026-07-04 v53

**Gate Z6 (no-submission package drill) is CLOSED, with real data** —
operator ran the full v52 command sequence to completion. Real results:

1. `Skills/run_archive_positive_control.py --nights 20220817 20220819
   --min-observations 2 --build-review-packets` built **88 real
   `ScoredNEO` review packets** from the real archived-ZTF 88-tracklet
   result already on disk, via the real
   `classify() -> fit_orbit() -> score() -> process_alert(dry_run=True)`
   chain, in 25 seconds.
2. `Skills/adversarial_review.py --offline` on those 88 packets produced
   **`SURVIVE=0 BORDERLINE=0 REJECT=88`** — the correct outcome, since
   these tracklets are combinatorial pairings of unrelated real sources in
   a crowded field (per the v41 handoff below), not real single-object NEO
   candidates. Every packet failed `orbit_quality` (only 2 observations per
   tracklet, insufficient for orbit fitting); most also failed
   `artifact_posterior` and/or `real_bogus`.
3. `Skills/export_ades_report.py` generated valid ADES PSV-format text for
   all 88 packets (real RA/Dec/mag/band/obsTime per row, `stn=XXX`
   throughout), with **zero network calls** — confirmed both by code
   inspection and by the real run's output.

Full evidence, including the exact commands and a criterion-by-criterion
closure assessment against Gate Z6's stated requirement:
`docs/evidence/live/2026-07-04-gate-z6-no-submission-drill-closed.md`.
`docs/ZTF_DR24_PRODUCTION_GATES.md`'s Z6 row updated to **CLOSED**.

**This is a docs/evidence-only commit — no code changed, no version
bump** (the code that made this possible, `--build-review-packets`,
already shipped in v0.90.57/PR #203).

**Next production action**: with Gate Z6 closed and Gate Z3's
candidate-pair thread still on hold pending explicit operator direction
(see the standing note in the v52 handoff immediately below — unchanged
and still in force), the next evidence-tractable, non-gambling gate to
advance is one of Z4 (auditable ranking baseline), Z5 (retrospective
validation), or Z7 (operator runbook sync) from
`docs/ZTF_DR24_PRODUCTION_GATES.md` — none of which require a new
archival download or hoping a specific night has good data. Do not
resume the Gate Z3 apparition search without the operator's explicit
choice of path.

### Handoff state as of 2026-07-04 v52

**Operator called a real doom loop in the Gate Z3 candidate-pair search;
pivoted to Gate Z6 instead of a 5th pair.** Four candidate pairs of
designation 72966 have now been tried (20220817/19, 20210106/11,
20191030/1101, and 20210105/20210111 in progress) with no confirmed
single-object match — the pattern of "try another apparition, hope this
one confirms" was not producing new information, just repeating the same
approach on a diminishing-returns basis. Per the operator's explicit
"work on evidence only, not hopes" directive, stopped proposing a 5th
pair and pivoted to the fully-open, evidence-tractable **Gate Z6
(no-submission package drill)**, which needs no further downloads or
gambling on archival data luck.

**Gate Z6 tooling built (v0.90.57, this PR)**:
`Skills/run_archive_positive_control.py --build-review-packets` now runs
every tracklet linked from real archived ZTF data through the exact same
real `classify() -> fit_orbit() -> score() -> process_alert(dry_run=True)`
chain `Skills/run_pipeline.py` uses in production, and includes the
resulting real `ScoredNEO` dicts in the report as `review_packets`. This
reuses the real 88-tracklet result already on disk from the
20220817/20220819 pair -- no new download needed. `process_alert` is
always called with `dry_run=True` in this path; nothing is ever submitted
externally. 2 new offline tests (7 total in this file, all passing).

**Next production action (NOT YET DONE)**: build real review packets from
the real 88 tracklets already on disk, then run them through adversarial
review and ADES export in dry-run mode:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 --min-observations 2 --build-review-packets \
    --out Logs/pipeline_runs/run_archive_positive_control/report_with_packets.json
```

Then extract just the `review_packets` array from that JSON into its own
file and run:

```bash
uv run --python 3.14 python Skills/adversarial_review.py \
    <review_packets_file>.json --offline
uv run --python 3.14 python Skills/export_ades_report.py \
    <review_packets_file>.json
```

`export_ades_report.py` defaults to `--obs-code XXX` (the documented
first-submission placeholder) and never makes a network call -- this is
a pure text-generation dry run. No candidate from this drill should ever
be described as "confirmed" or submitted; this is a mechanism test only.

**Standing note on the Gate Z3 candidate-pair search**: do not propose a
5th apparition of designation 72966, or a different NEO designation,
without first getting explicit operator direction -- the operator was
asked to choose a path (different designation / one more try / accept
current evidence / other) and dismissed the question to think it over.
Wait for their call before resuming that specific investigation thread.

### Handoff state as of 2026-07-04 v50

**Re-run with `--force-refresh-mpc` succeeded: real observatory codes now
visible for all 35 hits; new, more principled candidate pair selected** —
operator re-ran the scan with the new flag. Real result: 35/51 real
ZTF-coverage hits, every `HIT` line now shows a real observatory code
(fix confirmed working). Both previously-tried candidate pairs had
**different** stations for their two nights; scanning the new 35-hit list
found two pairs with the **same** station on both nights: **20191030/
20191101** (2 days apart, both `I41`) and 20210105/20210111 (6 days
apart, both `G96`). Selected 20191030/20191101 as the primary candidate
(shorter gap minimizes orbit-motion targeting error). Expected rate
computed directly from the real hit positions: 35.75 arcsec/hr, PA 241.8
deg — plausible and consistent with the object's previously observed
range. Full evidence:
`docs/evidence/live/2026-07-04-gate-z3-observatory-filtered-scan-35-hits.md`.

**Next production action (NOT YET DONE)**: ingest both nights, each
centered on their own real matched position:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20191030 \
    --ra 29.6558 --dec 5.8706 --radius-deg 2.0 --min-rb 0.5
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20191101 \
    --ra 29.2335 --dec 5.6456 --radius-deg 2.0 --min-rb 0.5
```

If both yield real kept observations, run the positive control against
this pair, then `Skills/match_positive_control_tracklet.py` (ref1
29.6558 5.8706, ref2 29.2335 5.6456), per the now-established sequence.
Backup candidate if this pair fails: 20210105/20210111 (same-station G96,
6 days apart).

### Handoff state as of 2026-07-04 v49

**Real re-run of the filtered scan found a genuine bug: every HIT line
showed `observatory=None`** — operator ran the sentinel-filtered
`Skills/scan_mpc_history_ztf_coverage.py` (v0.90.55) for the first time.
Real result: the filter worked (16 sentinel reports excluded, printed
correctly), and the scan found **35 of 51** checked reports had real ZTF
coverage — but every single `HIT` line printed `observatory=None`, even
though the *separate* `lookup_mpc_observation_history.py --force-refresh`
run earlier this session proved the real data has genuine codes (T05,
I41, G96, C51, etc.).

**Root cause (found, not guessed)**: `scan_mpc_history_ztf_coverage.py`
calls `lookup_mpc_observation_history.run_lookup(designation,
archive_start_jd, out_dir / "mpc_history")` — a **separate nested
checkpoint path** (`Logs/pipeline_runs/scan_mpc_history_ztf_coverage/mpc_history/`)
from `lookup_mpc_observation_history.py`'s own default checkpoint
(`Logs/pipeline_runs/lookup_mpc_observation_history/`). The operator's
earlier `--force-refresh` only refreshed the *standalone* script's
checkpoint; the scan's own nested copy was untouched and still predates
the v0.90.53 observatory field, so it kept silently reusing the old data.

**Fix (v0.90.56, this PR)**: added `--force-refresh-mpc` to
`scan_mpc_history_ztf_coverage.py`, threaded through to
`lookup_mpc_observation_history.run_lookup(..., force_refresh=...)`.
1 new regression test (15 total in this file).

**Next production action (NOT YET DONE)**: re-run the scan once more with
this new flag to finally get real per-hit observatory codes for the 35
hits, so a fresh candidate pair can be selected with actual station-code
visibility:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --force-refresh-mpc
```

This will re-issue the same cheap Gate Z1 metadata queries (each already
cached from the just-completed run, so this should resume quickly/mostly
from checkpoint) but with a fresh MPC-history fetch that carries the
observatory field through to the printed `HIT` lines this time.

### Handoff state as of 2026-07-04 v48

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


---

## Superseded "Immediate Next Steps" (WISE/DECam/TESS path, pre-2026-07-02 pivot)

Kept for historical context only. This entire discovery path was superseded
2026-07-02 by ZTF DR24 archival historical replay as the primary discovery
path — see `docs/MISSION.md §Operator Decision (2026-07-02)` and
DECISION-001 in `CLAUDE.md`. Do not treat any command, evidence claim, or
status below as current; do not run any command in this section.

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


---

## AGENTS.md historical notes (Codex-facing companion log)

The section below is archived verbatim from `AGENTS.md`'s "Historical
state" and "Handoff notes" sections. `AGENTS.md` is a Codex-facing
companion to `CLAUDE.md` and was kept as a more condensed, independently
worded status log — its historical entries are not identical to the
`CLAUDE.md`-facing entries earlier in this file, so both are preserved
rather than deduplicated against each other. Not mandatory reading;
consult only for historical context.

### Historical state (as synced 2026-07-02, v0.90.27)

All 10 legacy pipeline modules are complete. The offline suite passes on Python
3.14, all three legacy ML tiers have trained weights, and the WISE/DECam/TESS
production-capability gates P1/P2/P3/P5 are closed as historical evidence.
However, the operator pivot on 2026-07-02 makes ZTF DR24 archival historical
replay the current primary discovery path. The WISE/DECam/TESS path is
secondary/paused and must not be treated as proof that the new ZTF DR24 path is
production-capable.
For the ZTF DR24 path, Gate Z1 bounded ingest and Gate Z2 time-aware
known-object exclusion are code-complete but still require operator live
verification. Gate Z3 is not blocked on linker scaffolding: the existing
linear-motion linker already satisfies the Fink-FAT-style tracklet-linking
shape. The active blocker is finding and verifying a per-source ZTF DR24
detection source that yields real candidate detections (RA/Dec/time/magnitude)
instead of only image/exposure metadata. The older ALeRCE-backed ZTF provider
is real bounded-pilot evidence, but
`docs/evidence/phase0/alerce_source_detection_assessment.md` records that it
does not close the DR24 Gate Z3 source question unless verified for the current
historical-replay protocol. v0.90.24
also ported the missing
macOS CNN model-load warmups into `src/classify.py`; that fix needs one
operator Mac re-run before it is field-confirmed.
Console output is now fully compliant with `docs/CONSOLE_OUTPUT_SPEC.md` —
every stage print includes `elapsed {M}m{S:02d}s` and ETA is computed from
a measurable quantity (surveys done/total, tracklets done/total).

**Production gap status (as of 2026-06-22)**:
- T1-A (Incomplete Trained ML Model Set): **CLOSED.** All Tier 1/2/3 weights
  trained; ensemble stacker KPIs passed (AUC=0.9809, Brier=0.0211, ECE=0.0000);
  `promotion_gate_passed=true`.
- T1-B (No Live Credentials): **CLOSED.** ATLAS token and ZTF IRSA credentials
  confirmed PRESENT via `source Skills/verify_live_credentials.sh`; live
  connection test OK. Credentials stored in macOS Keychain under service names
  `neo-detection:ATLAS_TOKEN`, `neo-detection:ZTF_IRSA_USERNAME`,
  `neo-detection:ZTF_IRSA_PASSWORD` — never stored in repo. Bounded live
  dry-run policy is signed in `background/live_review_policy.example.json`;
  execution still fails closed on missing provider credentials and never
  authorizes external submission or impact-probability claims.
- T1-C (Real-Data Recovery And Operator Review Evidence): **CLOSED
  2026-06-20.** ATLAS Option A follow-up run `atlas_recovery_c1712df0f32c`
  recovered 5/5 prequalified objects (100%); audit passed; operator
  review by Jerome W. Lindsey III found no blocking findings. Full evidence:
  `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`.
- T1-D (No Ensemble Calibration): **CLOSED.** All KPIs passed 2026-06-14.
- T2-C (No External Expert Review): **CLOSED 2026-06-21.** Architecture
  evidence packet signed by Jerome W. Lindsey III (operator sign-off); all 5
  attestation items checked.
- T2-D (No CI for E2E/Integration/Model-Weight Tests): **CLOSED 2026-06-21.**
  `e2e.yml` has smoke/diagnose/injection/model-weights jobs; `integration.yml`
  gated on secrets.
- T2-A (Integration Tests vs Real APIs): **CLOSED 2026-06-21.** Both
  `test_fetch_ztf_live_small_region` and `test_fetch_atlas_live_small_region`
  PASSED on operator Mac. Evidence: `docs/evidence/t2a/`.
- T2-B (Adversarial/Robustness Testing): **CLOSED 2026-06-22.** All 10
  synthetic adversarial tests in `tests/test_adversarial.py` pass in CI.
  Real-data false-positive audit vs known-artifact catalog is a future
  operator-run step and is not a current blocker.

See `docs/PRODUCTION_READINESS.md` for the full gap register.

### Handoff notes (2026-07-02) — v0.90.27 (historical; superseded)

The v0.90.68 addendum above is the current state. This section is preserved
only as dated history for the ZTF DR24 pivot.

**Current merged state through PR #163**:

- v0.90.20 built `Skills/ztf_dr24_bounded_ingest.py` for bounded,
  checkpointed IRSA ZTF DR24 science-image metadata ingest. It is offline
  tested but needs one operator live run before Gate Z1 can close.
- v0.90.21 built `src/known_object_exclusion.py` for time-aware,
  fail-closed known-object filtering from documented `first_obs` evidence.
  It needs operator live confirmation that `first_obs` returns real dates on
  the already-verified JPL SBDB `sb-group=neo` query before Gate Z2 can close.
- v0.90.22 corrected Gate Z3: do not build another linker just to satisfy the
  brief. `src/link.py` already provides the linear-motion tracklet linker. The
  real dependency gap is a verified per-source ZTF DR24 detection source; Gate
  Z1 currently ingests image/exposure metadata only.
- v0.90.23 added progress output to `Skills/injection_recovery.py` so long
  model cold starts are never silent.
- v0.90.24 ported the missing macOS CNN-load warmups into
  `src/classify.py`, fixing the likely real operator deadlock path. This
  cannot be field-confirmed in the Linux sandbox and needs one Mac operator
  re-run.
- v0.90.25 synchronized the durable docs with that state.
- v0.90.26 resolved the legacy ALeRCE wording trap: ALeRCE remains real
  source-level ZTF pilot evidence, but it is not current DR24 production
  evidence until documented as suitable for bounded historical replay.
- v0.90.27 adds `docs/evidence/phase0/alerce_source_detection_assessment.md`
  from official ALeRCE docs. It verifies source-level detection fields exist,
  but finds no doc evidence for DR24 static-archive or no-future-leakage
  suitability.
  Future agents should continue at Gate Z3 by verifying a per-source ZTF DR24
  detection source from official documentation or live evidence. Do not rerun
  exhausted WISE diagnostics, do not restart Gate Z1 scaffolding, and do not
  guess endpoints or schemas.

### Handoff notes (2026-07-02) — v0.90.19

**Phase 0 source verification for the ZTF DR24 historical-replay pipeline is
now materially complete except for the external Fink TLS blocker.** Evidence is
committed under `docs/evidence/phase0/`:

- `data_sources_verified.md`: live operator-observed results show JPL SBDB,
  MPC get-obs, and IRSA ZTF image metadata all returning HTTP 200.
- `auth_requirements.md`: those three probes required no credentials for the
  tested read-only calls; Fink auth remains unknown because both Fink probes
  failed before HTTP response.
- `phase0_probe_results.json`: raw captured headers/body previews. MPC get-obs
  uses a GET with JSON body `{"desigs": ["433"]}`; JPL SBDB uses
  `sb-group=neo`.
- `schema_snapshot/README.md`, `sample_ingest_report.md`, and
  `pretrained_model_audit.md`: complete the brief's Phase 0 deliverable set
  without inventing ingestion or approving pretrained models.
- `2026-07-02-root-cause-findings.md`: root causes recorded. JPL's brief
  example `neo=Y` was wrong; MPC get-obs requires a JSON body; Fink is an
  external TLS-handshake failure reproduced across Python and curl; v0.90.17
  fixed stale checkpoint reuse by hashing full probe definitions; v0.90.18
  commits the refreshed evidence packet and missing Phase 0 deliverables.

**Highest-priority next production work**: work Gate Z1 from
`docs/ZTF_DR24_PRODUCTION_GATES.md` by starting a bounded ZTF DR24 historical
replay ingest prototype: IRSA ZTF metadata access, no-future-catalog-leakage
known-object exclusion, Fink-FAT-style linear linking, auditable handcrafted
features, and a logistic-regression baseline before any LightGBM/XGBoost or
pretrained model work. Do not block on Fink unless a Phase 1 task specifically
requires Fink schema access; the verified IRSA/JPL/MPC path is enough to begin
bounded prototype design.

### Handoff notes (2026-07-02) — v0.90.12 — MAJOR PIVOT

**Operator decision: ZTF DR24 historical replay is now the primary discovery
pipeline, superseding WISE/DECam/TESS.** Full record: `docs/MISSION.md
§Operator Decision (2026-07-02)`. Key points:

- `docs/neo_discovery_agent_brief.md` supersedes the 2026-07-01
  reconciliation that kept WISE/DECam/TESS primary. Build the brief's Phase
  1 pipeline next: ZTF DR24 archival historical replay, time-aware
  known-object exclusion, Fink-FAT-style tracklet linker, LightGBM/XGBoost
  candidate ranker.
- WISE/DECam/TESS code and all Gate P1–P5 evidence are preserved, not
  deleted — secondary/paused, not the active target.
- Live ZTF/ATLAS alert-stream discovery is still prohibited. Only bounded,
  time-aware archival ZTF DR24 reprocessing is newly permitted.
- The `docs/PRODUCTION_READINESS.md` P1–P5 gates describe the now-secondary
  WISE/DECam/TESS pipeline and do not establish readiness for the new ZTF
  DR24 pipeline. New gates are needed before claiming that pipeline is
  production-capable.
- **Status update v0.90.18**: Phase 0 verification is now recorded under
  `docs/evidence/phase0/`. JPL/MPC/IRSA are live-verified; Fink remains an
  external TLS blocker; pretrained models are deferred.

### Handoff notes (2026-07-02) — v0.90.11

**Correction (operator-flagged 2026-07-02)**: earlier same-day handoff notes
described Gate P4 as something requiring active operator action ("Jerome
must obtain written MPC confirmation," "wait on Jerome's Gate P4
correspondence"). That framing was wrong — **there is no candidate yet, so
there is nothing to tell MPC and no reason to contact them.** Gate P4 is
**dormant**, not a pending operator task. It only becomes relevant once a
real WISE-sourced candidate actually survives adversarial review and
operator review. Do not describe Gate P4 as "awaiting operator
correspondence" in future handoffs.

**Current production definition**:
- Production readiness now means demonstrated capability to find, score,
  reject, review, and package candidates from unreviewed archival discovery
  data with defensible, industry-standard confidence controls. It does not
  require that the project has already found a genuinely new NEO.
- `docs/neo_discovery_agent_brief.md` is now authoritative workflow guidance
  and has been applied to close Gate P2: source verification, no future-catalog
  leakage, historical replay discipline, pretrained-model audits, and
  auditable ranker design are recorded in `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md`.
- **Gates P1, P2, P3, and P5 in `docs/PRODUCTION_READINESS.md` are all
  CLOSED.** Gate P4 (MPC submission protocol) is open but dormant — it does
  not require operator action today; it activates only when a real candidate
  needs submitting. No further code work can close it either, since the
  fail-closed guards already exist and were verified in the Gate P3 drill.
  Actual candidate survival is a later event-driven discovery gate.

**Gate P5 CLOSED (2026-07-02)**:
- `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`: one-page flow with review-packet
  location, verified `adversarial_review.py`/`export_ades_report.py`
  commands, an operator-review checklist, the dormant Gate P4 check, and
  the permanent forbidden-communications list. States `SURVIVE`/`BORDERLINE`
  means "candidate may be reviewed for MPC submission," never "confirmed NEO."
- **NEXT PRODUCTION ACTION for a coding agent**: all code-addressable
  production-capability gates are closed. Remaining code-addressable work is
  the two items left open under Gate P2 (WISE sentinel-magnitude rejection
  filter; DECam/TESS live endpoint verification). There is no pending
  operator task to wait on — do not invent one.

**Gate P3 CLOSED (2026-07-02)**:
- `Skills/injection_recovery.py --review-packet-out` writes full `ScoredNEO`
  packets from injection runs, feeding the drill directly from a Gate P1 run.
- Drilled 5 synthetic WISE packets through `Skills/adversarial_review.py
  --offline` (5/5 `REJECT`, expected) and `Skills/export_ades_report.py`
  twice — default args and `--obs-code C51` without confirmation — both
  failed closed with no `.psv` file written and no network call.
- Evidence: `docs/evidence/prod-loop/2026-07-02-gate-p3-no-submission-drill.md`.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: Gate P4 requires Jerome to
  contact MPC in writing about archival WISE/NEOWISE submission authority
  under station code C51 (see `docs/MPC_SUBMISSION_POLICY.md §TODO for Future
  Agents`). No code path can substitute for this.

**Gate P2 CLOSED (2026-07-02)**:
- `docs/SURVEY_NATIVE_CONFIDENCE_POLICY.md` documents the source-verification
  matrix (WISE live-verified; DECam/TESS code-complete but never
  live-verified), confirms `score.py:_determine_alert_pathway` already fails
  closed on missing real/bogus (routes to `internal_candidate`), records the
  no-future-catalog-leakage statement, reaffirms ZTF/Fink/SNAPS as
  reference-only, and records the pretrained-model-audit requirement as not
  yet applicable.
- Finding: TESS's `fetch_tess_ffis` returns TIC catalog star positions, not
  genuine FFI difference-image detections — `preprocess.py` has no FFI source
  extraction. `Skills/run_pipeline.py` now warns operators when `--surveys
  DECam` or `--surveys TESS` is selected.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: work Gate P3 — run an end-to-end
  no-submission package drill from a Gate P1 positive-control packet through
  `Skills/adversarial_review.py`, operator review packet generation, and
  `Skills/export_ades_report.py`, verifying no external submission occurs.

**Gate P1 CLOSED (2026-07-02)**:
- `Skills/injection_recovery.py --survey WISE` injects a source-native
  NEOWISE-visit-cadence synthetic tracklet through the real production
  `detect.py` discovery-archive singleton path, `link.py`, `classify.py`, and
  `score.py`.
- Verified 100% detection/link/score rate (n=50, seed=42); baseline committed
  at `data/injection_recovery_wise_baseline.json`; CI job `wise-injection`
  fails closed if recovery drops to zero.
- Evidence:
  `docs/evidence/prod-loop/2026-07-02-gate-p1-wise-injection-recovery.md`.
- **NEXT PRODUCTION ACTION — NOT YET DONE**: work Gate P2 by documenting
  quantitative WISE/DECam/TESS confidence thresholds so archive candidates do
  not rely on absent ZTF-style real/bogus evidence. Gate P2 must also fold in
  the discovery-agent brief's source-verification matrix, no-future-catalog
  leakage rule, and pretrained-model audit requirement.

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
- WISE/NEOWISE ADES export is fail-closed: `stn=C51` requires written MPC
  confirmation, and ADES note `Z` is emitted for this non-survey archival
  remeasurement pipeline.
- `Skills/run_pipeline.py --link-scale-plan-out` writes top night-pair and
  sky-cell diagnostics when the link seed-pair budget fails closed, including
  a budget-derived diagnostic radius and recommended subfield parameters.
- Operator scale-plan probe result: `11786731` estimated seed pairs over the
  `1000000` default budget. Dominant night pairs are `2459084/2459085`
  (`9102120`) and `2459243/2459244` (`2503474`).
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
- Expected seed-budget stops now exit cleanly with audit/output artifacts, not
  unhandled tracebacks.
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

**Goal: defensible discovery paper** (operator-confirmed 2026-06-26 by Jerome W. Lindsey III).
Two-stage review before any external submission:
  1. `Skills/adversarial_review.py` — automated adversarial challenges try to REJECT
  2. Operator (Jerome) reviews survivors
  3. MPC submission → provisional designation → independent confirmation → journal paper

**Discovery fetch layer complete (PR #119, 2026-06-27)**:
- `fetch_wise_archive`: IRSA `neowiser_p1bs_psd` cone search; MJD→JD; disk-cached
- `fetch_decam_archive`: NOIRLab NSC DR2 via pyvo TAP; disk-cached
- `fetch_tess_ffis`: MAST `Observations.query_criteria()` + TIC catalog; BTJD→JD; disk-cached
- `fetch_discovery`: routing enforcer — raises `ValueError` for ZTF/ATLAS inputs
- `Mission` literal extended: `"TESS"`, `"DECam"`, `"WISE"` added
- `run_pipeline.py` default changed to `--surveys WISE`
- 1573 tests; 100% coverage; CI green on Python 3.14 ✓

**Adversarial review implemented (v0.89.3, PR #116/117)**:
`Skills/adversarial_review.py` — 13 challenges + 2 live checks.
Verdicts: SURVIVE / BORDERLINE / REJECT. Exit codes 0/1/2.
Tests: `tests/test_adversarial_review_skill.py` (50+ cases).

**PR #131 merged (2026-06-28)**:
- Discovery sweeps now fail closed for live MPC submission unless
  `NEO_MPC_SUBMISSION_APPROVED=1` is set with a real non-placeholder MPC
  observatory code.
- The Taurus WISE run evidence is durable at
  `docs/evidence/live/2026-06-27-wise-live-sweep.md`: `111913` IRSA rows,
  `85335` parsed observations, `535` moving-object candidates, `0` linked
  tracklets.
- WISE masked photometry values are handled as missing-data sentinels instead
  of being converted to `nan`.
- Do not ask the operator to repeat the same Taurus sweep.

**PR #133 merged (2026-06-28)**:
- Root cause of the Taurus `535` candidates -> `0` tracklets result: WISE fetch
  queried the broad static NEOWISE point-source population, then `detect()`
  required same-night pairs before `link()` saw archive rows.
- WISE ADQL now narrows rows with official IRSA association columns (`sso_flg`,
  `allwise_cntr`, `n_allwise`, `source_id`) and preserves prefiltered
  WISE/DECam/TESS archive rows as singleton candidates for multi-night linking.
- Validation: operator targeted run on Python 3.14.3 passed (`80 passed in
  0.86s`; targeted ruff clean; mypy clean across 12 source files). CI initially
  failed only on missing helper coverage; coverage test added, full local
  pytest passed (`1586 passed, 2 deselected`), and GitHub CI passed before
  merge.
- Evidence: `docs/evidence/live/2026-06-28-wise-linking-root-cause.md`.
- Follow-up diagnostic from `main` at `2a786e18` reached WISE pyvo polling but
  failed before result retrieval with `AttributeError: 'AsyncTAPJob' object has
  no attribute 'update'`. Root cause: pyvo 1.9.0 exposes `_update()`/`wait()`,
  not public `update()`. Evidence:
  `docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-pyvo-update.md`.
- This pyvo blocker was closed by PR #135.

**PR #135 merged (2026-06-28)**:
- WISE TAP polling is now compatible with pyvo 1.9.0: the poll loop uses public
  `update()` when available, falls back to one-shot `_update()`, and preserves
  explicit heartbeat output.
- Post-merge smaller diagnostic from `main` at `dd35a8c0` completed:
  `5206` WISE rows, `5200/5206` preprocessed, `5200` singleton candidates,
  `0` linked tracklets, `0` candidates processed, dry-run safety intact.
- Evidence:
  `docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-post-pyvo.md`.
- NOT YET DONE: diagnose why current WISE archive singleton candidates do not
  link into multi-night tracklets. Do not rerun the same 1.0°/7-day Taurus
  diagnostic until that diagnosis is recorded and a distinct fix or selection
  change is ready.

**PR #136 merged (2026-06-28)**:
- Linker provenance now records nights, observations, total seed pairs,
  rate-window seeds, satellite rejects, min-observation/min-night rejects, and
  chi-square rejects. Zero-tracklet runs persist these counters in
  `checkpoint.json` and print them when seed pairs exist.
- Operator validation before merge: targeted pytest `80 passed`, ruff clean,
  mypy clean. GitHub CI passed before merge.
- Post-merge bounded WISE rerun from `main` at `b8ca1312`: `5206` rows,
  `5200/5206` preprocessed, `5200` candidates, `0` tracklets.
  Link diagnostics: `n_nights=1`, `n_seed_pairs_total=0`.
- Evidence:
  `docs/evidence/live/2026-06-28-wise-linker-diagnostics-one-night.md`.
- NOT YET DONE: select or probe a WISE field/window that spans at least two
  integer-JD nights after preprocessing. Do not rerun the same 1.0°/7-day
  Taurus diagnostic; it is proven to be a one-night sample.

**WISE window probes after PR #136 (2026-06-28)**:
- 1.0° Taurus, 30 days: `5206` observations on one night (`2458883`).
- 1.0° Taurus, 195 days: `5206` observations on one night (`2458883`).
- 1.0° Taurus, 370 days: `328022` observations on eight nights, too large for
  the next full pipeline diagnostic.
- 0.2° Taurus, 370 days: `12061` observations on six nights
  (`2458883`, `2459084`, `2459085`, `2459242`, `2459243`, `2459244`).
- Evidence: `docs/evidence/live/2026-06-28-wise-window-night-probes.md`.

**WISE cap-2000 dry run (2026-06-29)**:
- Evidence: `docs/evidence/live/2026-06-29-wise-cap2000-dry-run.md`.
- The selected 0.2° Taurus full-year window is data-viable: `12061` WISE rows,
  `12042/12061` valid sources, and multi-night tracklets can form.
- The uncapped `12042`-candidate all-pairs linker path projected tens of
  minutes and was intentionally interrupted; do not rerun it as the next
  diagnostic.
- The explicit bounded run with `--max-candidates 2000` completed in `35.32s`,
  linked `243289` seed pairs, produced `19` tracklets, processed `19`
  candidates, and found `0` submission-ready candidates.
- `Skills/adversarial_review.py` now fails closed on compact pipeline summary
  rows. The cap-2000 output produced `19/19` structured `REJECT` verdicts
  because the output rows are not full `ScoredNEO` review packets.
- `run_pipeline.py --review-packet-out` was then added and live-validated on
  the same bounded WISE diagnostic. The rerun wrote `21` full `ScoredNEO`
  packets; offline adversarial review produced `21/21 REJECT` verdicts with
  fatal `orbit_quality`, `real_bogus`, `artifact_posterior`, and
  `neo_dominance` challenges. No candidate advanced to operator review.
- `run_pipeline.py --max-link-seed-pairs` now fails closed before the linker
  when estimated all-pairs seed work exceeds the configured budget
  (default `1000000`; set `0` only for a documented override).
- NEXT CODE ACTION: address WISE-scale linking with a scale-aware strategy or
  explicit tiling plan before attempting uncapped 12k-candidate runs.

Keep discovery sweeps in alert dry-run mode. Live archive fetching does not
require `--no-dry-run`; actual MPC submission remains fail-closed until the
MPC observatory-code path is resolved and `NEO_MPC_SUBMISSION_APPROVED=1` is
set with a real non-placeholder observatory code.

**Two human-gated blockers remain**:
1. MPC observatory code strategy — Jerome must resolve before any submission.
   See `docs/MPC_SUBMISSION_POLICY.md §TODO for Future Agents — Archival WISE Submission Authority`.
2. Actual candidate discovery — pipeline must find a survivor before paper is possible.

**Progress tracker**: `docs/evidence/prod-loop/LOOP_PROGRESS.md` — read
at session start to avoid repeating completed work.

### Handoff notes (2026-06-22) — v0.89.1

**ZTF fetch ndet cap fix (PR #115, merged 2026-06-22)**: Root cause of 0
tracklets (live Runs 3–5) was `_fetch_ztf_alerce_api` Mode 1 using
`ndet_max=None`, which returned persistent stationary sources whose detections
are all at the same sky position. Mode 1 now uses `ndet_max=3,
order_mode="ASC"` to surface single-detection transients (the moving-object
signature). `max_objects` increased 50→200. Two regression tests added.
Evidence: `docs/evidence/live/2026-06-22-ndet-cap-root-cause.md`.

**Adversarial test fixes (PR #115, merged 2026-06-22)**:
- `compute_streak_metric` now returns `None` (not `0.0`) for observations with
  no cutout — correct sentinel for "cannot determine streak status".
  `filter_by_streak_score` updated to skip `None` values.
- `OrbitQualityCode` extended to include `0` (degenerate/no-orbit sentinel);
  `compute_moid` already returned `None` for `quality_code < 1`.
- `test_very_fast_neo_links` adds a 4th observation on night 3 so the linker
  propagation loop has a third night to visit (seed pair uses nights 1+2;
  propagation skips night_a and night_b).
- `test_short_arc_blocks_submission` adds `sys.path` manipulation to import
  `conftest.build_scored_neo` outside the pytest root path.
- `test_run_pipeline_resumes_from_checkpoint` patches `ready_for_submission`
  to prevent MagicMock vs int comparison failure.

**Historical next live run (SUPERSEDED — do NOT run for discovery)**:
```bash
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py \
    --ra 284.13 --dec -22.5 --radius 3.5 \
    --start-jd 2461183.0 --end-jd 2461213.0 \
    --surveys ZTF --no-dry-run --force-refresh --no-resume
```
Expected: `ndet≤3` asteroid-classified OIDs → single-night transients at
unique sky positions → linker forms seed pairs with real solar system motion
rates → tracklets appear.

### Handoff notes (2026-06-17) — historical T1-C context

**What is now true for T1-C**:
- The original zero-alert diagnosis has been superseded. Public ALeRCE-backed
  ZTF source detection is working and has produced non-zero real data.
- The Orion pilot run `011dd53aa7f4` is retained only as historical/debug
  evidence. Do not reuse Orion for the production recovery KPI.
- The next production run should target many recoverable known moving objects,
  preferably from `Skills/select_survey_fields.py --mode recovery`, then audit
  against a manifest containing MPC designations plus sky/time samples.
- `Skills/audit_real_run.py` is the fail-closed promotion gate. It must verify
  >=90% known-object recovery and require operator review before
  internal production promotion is allowed. It never authorizes MPC submission,
  NASA notification, or any impact-probability statement.

**How to load credentials on operator Mac (NEVER use bare env vars)**:
```bash
source Skills/verify_live_credentials.sh   # loads ATLAS_TOKEN, ZTF_IRSA_USERNAME, ZTF_IRSA_PASSWORD
```
The script uses `security find-generic-password -s "neo-detection:ATLAS_TOKEN" -w`
(full string as service name, no `-a` flag). Do NOT use `-s neo-detection -a ATLAS_TOKEN`.

**Operator recovery-field selection command**:
```bash
git pull origin main
PYTHONPATH=src uv run --python 3.14 python Skills/select_survey_fields.py \
  --jd now \
  --mode recovery \
  --top-n 10 \
  --history-dir Logs/pipeline_runs \
  --json
```


---

## PRODUCTION_READINESS.md historical narrative — T1-C

Archived verbatim from `docs/PRODUCTION_READINESS.md`'s T1-C section
(closed 2026-06-20). This is the full recovery-methodology journey
(checklist plus every dated diagnostic update); the current file keeps
only the closure status line and a pointer here.

**What is needed to close it**:
1. [DONE] Complete the automated live-review policy approval; credentials,
   manual provider connection tests, and the signed bounded dry-run policy are
   now present. Provider readiness can still fail closed when required
   credentials are absent from the active shell.
2. [DONE] Run `Skills/run_pipeline.py` on a bounded real ZTF field in dry-run
   mode. On 2026-06-16, the operator ran the Orion-field ALeRCE-backed pilot:
   4,059 real ZTF source detections fetched, 4,059/4,059 preprocessed, 520
   raw candidates detected, `--max-candidates 80` linked, 2 tracklets scored,
   and 2 internal-candidate outputs written to
   `Logs/reports/t1c_ztf_alerce_pilot.json`. Audit summary:
   `Logs/pipeline_runs/011dd53aa7f4/run_summary.json`.
3. [DONE] Build a fail-closed real-run audit packet with
   `Skills/audit_real_run.py`. For run `011dd53aa7f4`, the tool wrote JSON and
   CSV review evidence, preserved no-network/no-submission safety flags, and
   correctly blocked promotion because no expected-known manifest was
   supplied. Durable GitHub-visible evidence is summarized under
   `docs/evidence/t1c/`; raw `Logs/` outputs remain local operational artifacts.
4. [DONE] Generate an expected-known manifest with MPC designations and
   Horizons sky/time samples using `Skills/build_recovery_manifest.py`, then
   verify ≥90% known-object recovery through `Skills/audit_real_run.py`.
   Pipeline object IDs may be used when known, but they are no longer required.
   Manifest generation has produced valid non-Orion MPC/Horizons sky/time
   manifests; the recovery KPI itself remains open.
5. [CODE] Run an uncapped or staged recovery-audit pilot with link progress/ETA
   enabled, preserving `Logs/pipeline_runs/*/run_summary.json` evidence and
   evaluating it through `Skills/audit_real_run.py`.
6. [DONE — HUMAN] The project operator (Jerome W. Lindsey III) reviewed the
   audit CSV. No blocking findings. This is not professional planetary-defense
   validation and does not authorize external submission.
7. [CODE] Select a new known-object-rich recovery field. The Orion pilot field
   is retained only as historical/debug evidence and must not be reused for the
   production recovery KPI.

**T1-C is CLOSED.** Known-object recovery (≥90%) verified on ATLAS data; operator false-positive review by Jerome W. Lindsey III completed 2026-06-20 with no blocking findings. All runs remained operator-controlled and non-submitting.

**2026-06-18 diagnostic update**: Recovery field selection now supports live
ZTF availability probing and broader MPC asteroid-list manifest preselection.
A ZTF-available fixed field at RA `251.66`, Dec `-22.50`, radius `3.5` produced
valid expected-known manifests and live asteroid-class ALeRCE detections.
However, ALeRCE asteroid-class objects in that field were same-night
three-detection tracklets, not multi-night histories; the 30-day asteroid-class
pipeline fetched `119` alerts, detected `48` candidates, linked `0` multi-night
tracklets, and therefore failed the existing known-object recovery KPI. T1-C
remains open until a multi-night known-object provider/path is used or a
separate same-night diagnostic subgate is explicitly added without replacing
the multi-night production gate. Durable summary:
`docs/evidence/t1c/2026-06-18-recovery-selector-and-provider-diagnostic.md`.

**2026-06-18 ATLAS fallback update**: `Skills/fetch_atlas_data.py` now has an
expected-known ATLAS forced-photometry recovery mode that writes
`audit_real_run.py`-compatible packets and fails closed unless enough usable
samples are recovered across enough nights. The fallback also records explicit
limitations: targeted forced photometry is supporting recovery evidence, not
blind discovery evidence, and it performs no submission or impact claim.
`src/fetch.py::fetch_atlas_forced` was corrected to match the official ATLAS
API contract by submitting form data to `/forcedphot/queue/`, requesting JSON
task responses, and exposing bounded live polling with progress callbacks. A
bounded pre-fix live pilot produced `0/10` recovered samples and correctly
failed the recovery gate. A post-fix redacted diagnostic confirmed JSON task
creation, but the ATLAS queue was deep (`queuepos=164`), so a longer
operator-supervised run is still required. Follow-up hardening records polling
sample state and queued ATLAS task URLs in the checkpoint, preserves checkpoint
resume even with `--force-refresh`, and reuses existing task URLs on resume so
interrupted queue waits do not create duplicate ATLAS jobs. If polling is
exhausted while ATLAS has not finished the task, the sample remains pending as
`poll_exhausted` rather than being counted as unrecovered. Durable summary:
`docs/evidence/t1c/2026-06-18-atlas-forced-fallback-diagnostic.md`.

**2026-06-19 bounded ATLAS recovery pilot**: Jerome W. Lindsey III approved up
to 40 ATLAS forced-photometry sample queries for T1-C recovery evidence only.
The run `atlas_recovery_4eaf93e87f6c` completed 38 sample queries with no
provider/tool failures, recovered 19 samples, emitted 4 multi-night audit
tracklets, and failed the recovery KPI at 4/11 expected objects (`36.36%`;
threshold `90%`). This confirms the live ATLAS fallback plumbing works, but
T1-C remains open. Durable summary:
`docs/evidence/t1c/2026-06-19-atlas-recovery-40-query-pilot.md`.

**2026-06-19 ATLAS prequalification approval**: Jerome W. Lindsey III approved
building a prequalified ATLAS-recoverable expected-known manifest before the
next live run. The documented rule keeps only objects from the screening run
with at least 3 recovered ATLAS samples across at least 2 distinct nights.
`Skills/build_recovery_manifest.py --prequalify-from-atlas-run` now implements
that rule and produced a local ignored manifest with 4 rows and 15 expected
samples (`481`, `1950`, `2172`, `2973`). The next blocker is running the
prequalified manifest through the existing non-submitting T1-C audit path and
then completing operator review if the KPI passes.

**2026-06-19 prequalified ATLAS recovery run**: The prequalified live run
`atlas_recovery_175ef40ac577` completed 15 sample queries with no
provider/tool failures, recovered 10 samples, emitted 3 multi-night audit
tracklets, and failed the recovery KPI at 3/4 expected objects (`75.00%`;
threshold `90%`). The failed object was `2973`; repeat-recovered objects were
`481`, `1950`, and `2172`. T1-C remains open. Further narrowing of the
denominator, such as a repeat-stable object rule, requires explicit operator
approval before more live queries.

**2026-06-20 Option A screening run**: Jerome W. Lindsey III approved a new
predeclared screening approach (25 objects, 6 samples/object, 101 total
samples) documented in `docs/evidence/t1c/2026-06-20-option-a-predeclared-policy.md`.
`Skills/load_credentials.py` was created (PR #113, merged) and wired into
`Skills/fetch_atlas_data.py` so credentials are auto-loaded from macOS Keychain
without a separate shell source step. The screening run `atlas_recovery_25f3a800a1a2`
completed: 42/101 samples recovered, 5 tracklets, 0 failures, 0 pending.
Prequalification (≥3 recovered samples, ≥2 distinct nights) yielded **5 objects:
121, 954, 2140, 2172, 5650**. Prequalified manifest written to
`Logs/reports/t1c_option_a_prequalified_manifest.json` (local, ignored).

**2026-06-20 Option A follow-up run**: `atlas_recovery_c1712df0f32c` completed —
23 samples, 16/23 recovered, 5/5 objects emitted audit tracklets. Preliminary
KPI: **5/5 = 100%** (gate ≥90%). Formal audit via `Skills/audit_real_run.py`
is the next step; operator review follows if audit passes.
Durable evidence: `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`.

**2026-06-20 audit result: PASSED.** Correct audit used
`expected_known_atlas_forced.json` (tolerance_days=1.0) from the run dir. Output:
`Recovery gate: evaluated (passed=True)`, 5 tracklets reviewed, 0 same-night,
5 multi-night, no external submission. T1-C automated KPI gate is now closed.

**2026-06-20 T1-C CLOSED**: Operator review completed by Jerome
W. Lindsey III. All 5 tracklets showed physically plausible motion rates
(26–36 arcsec/hr) and multi-night arcs (12–25 days). No flags, no blocking
findings. Full evidence: `docs/evidence/t1c/2026-06-20-option-a-screening-prequalification.md`.
No external submission or impact-probability claim authorized.

---

## PRODUCTION_READINESS.md historical narrative — Gate D1

Archived verbatim from `docs/PRODUCTION_READINESS.md`'s Gate D1 section.
This is the full WISE/NEOWISE Taurus and non-Taurus field-diagnostic
trail (2026-06-27 through 2026-06-30). The gate remains OPEN and paused;
the current file keeps only a condensed status summary and a pointer
here. This overlaps substantially with the WISE-era content already
archived above from `CLAUDE.md` and `AGENTS.md` — all three are kept
since they were independently written and may contain details the others
omit.

**2026-06-27 WISE live archive sweep evidence**: Jerome ran the Taurus WISE
command from `main` after pulling PR #127. IRSA async TAP returned `111913`
rows with columns `['ra', 'dec', 'mjd', 'w1mpro', 'w1sigmpro']`; the pipeline
parsed `85335` WISE observations, detected `535` moving-object candidates, linked
`0` tracklets, processed `0` candidates, and produced no submission-ready
candidates. This closes the WISE schema/fetch uncertainty for that field and
moves the next D1 blocker downstream to detection/linking diagnostics. Evidence:
`docs/evidence/live/2026-06-27-wise-live-sweep.md`.

**2026-06-28 PR #131 update**: Discovery sweeps now remain fail-closed for live
MPC submission unless explicitly approved with `NEO_MPC_SUBMISSION_APPROVED=1`
and a real non-placeholder MPC observatory code. WISE masked photometry values
are handled as missing-data sentinels instead of becoming `nan`. CI is green
with 1583 offline tests and 100% coverage. Do not ask the operator to repeat the
same Taurus sweep before diagnosing why the recorded `535` WISE candidates
linked into `0` tracklets.

**2026-06-28 PR #133 merged**: Root cause diagnosed for the Taurus
`535` candidates -> `0` tracklets result. `fetch_wise_archive()` queried the
broad static NEOWISE point-source population, and `detect()` required same-night
pairs before the linker could see archive rows. The merged fix uses official
IRSA association columns (`sso_flg`, `allwise_cntr`, `n_allwise`, `source_id`)
to prefilter WISE rows and preserves prefiltered WISE/DECam/TESS archive
detections as singleton candidates for multi-night linking. Validation:
operator targeted run on Python 3.14.3 passed (`80 passed in 0.86s`; targeted
ruff clean; mypy clean across 12 source files). CI initially failed only on
missing helper coverage; coverage test added, full local pytest passed
(`1586 passed, 2 deselected`), and GitHub CI passed before merge. Evidence:
`docs/evidence/live/2026-06-28-wise-linking-root-cause.md`. Next D1 step: run a
smaller WISE dry-run diagnostic from `main`; do not repeat the exact 3.5°/30-day
Taurus sweep yet.

**2026-06-28 pyvo polling compatibility update**: The smaller WISE diagnostic
was run from `main` at `2a786e18` and reached the PR #133 WISE ADQL path, but
failed before result retrieval with `AttributeError: 'AsyncTAPJob' object has no
attribute 'update'`. Root cause: the installed pyvo 1.9.0 async job exposes
`_update()`/`wait()` but not public `update()`. The compatibility fix preserves
explicit heartbeat polling, uses public `update()` when available, falls back to
the pyvo 1.9.0 one-shot `_update()` call, and never switches WISE fetching to a
silent blocking wait. Evidence and predicted operator output:
`docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-pyvo-update.md`.
Next D1 step after merge: rerun the smaller WISE dry-run diagnostic from
`main`; do not give feature-branch commands to the operator.

**2026-06-28 PR #135 merged and post-merge diagnostic complete**: WISE TAP
polling is now compatible with pyvo 1.9.0 while preserving explicit heartbeat
output. GitHub CI passed before merge; local validation included the full
offline suite (`1590 passed, 2 deselected`). The post-merge smaller WISE
diagnostic from `main` at `dd35a8c0` completed in dry-run mode: `5206` WISE
rows, `5200/5206` preprocessed, `5200` singleton candidates, `0` linked
tracklets, `0` candidates processed, and no external submission path invoked.
Evidence:
`docs/evidence/live/2026-06-28-wise-prefilter-diagnostic-post-pyvo.md`.
Next D1 step: diagnose why current WISE archive singleton candidates do not
link into multi-night tracklets; do not rerun the same 1.0°/7-day Taurus
diagnostic until a distinct fix or field-selection change is ready.

**2026-06-28 PR #136 merged and linker diagnostics complete**: Linker
provenance now records nights, observations, seed-pair totals, rate-window
seeds, satellite rejects, min-observation/min-night rejects, and chi-square
rejects. The post-merge bounded WISE rerun from `main` at `b8ca1312` produced
`5206` WISE rows, `5200/5206` preprocessed, `5200` singleton candidates, and
`0` tracklets. The new diagnostics show `n_nights=1` and
`n_seed_pairs_total=0`; therefore this specific 1.0-degree, 7-day Taurus window
is not a valid multi-night WISE linking test. Evidence:
`docs/evidence/live/2026-06-28-wise-linker-diagnostics-one-night.md`.
Next D1 step: select or probe a distinct WISE field/window that spans at least
two integer-JD nights after preprocessing; do not rerun the same 7-day Taurus
diagnostic.

**2026-06-28 WISE window selection update**: Taurus same-field probes show why
the previous 7-day diagnostic was non-informative and identify a bounded
multi-night candidate window. A 1.0-degree, 370-day probe returned `328022`
observations on `8` nights, too large for the next full pipeline run. A
0.2-degree, 370-day probe returned `12061` observations on `6` nights
(`[2458883, 2459084, 2459085, 2459242, 2459243, 2459244]`). Evidence:
`docs/evidence/live/2026-06-28-wise-window-night-probes.md`.

**2026-06-29 WISE cap-2000 dry-run update**: The selected 0.2-degree window ran
through the full dry-run pipeline with `--max-candidates 2000`: `12061` WISE
rows, `12042/12061` preprocessed sources, `243289` capped seed pairs, `19`
tracklets, `19` candidates processed, `0` submission-ready candidates, and
`35.32s` elapsed. The uncapped `12042`-candidate all-pairs linker path projected
tens of minutes and was intentionally interrupted. Offline adversarial review
now fails closed on compact pipeline summary rows; this run produced `19/19`
structured `REJECT` verdicts because full `ScoredNEO` review packets were not
exported.

`run_pipeline.py --review-packet-out` was then added and live-validated on the
same bounded diagnostic. The rerun wrote `21` full `ScoredNEO` packets and
offline adversarial review produced `21/21 REJECT` verdicts with fatal
`orbit_quality`, `real_bogus`, `artifact_posterior`, and `neo_dominance`
challenges. No candidate advanced to operator review. Evidence:
`docs/evidence/live/2026-06-29-wise-cap2000-dry-run.md`. Next D1 step:
implement a scale-aware WISE linking strategy or explicit tiling plan before
another uncapped 12k-candidate run. `run_pipeline.py --max-link-seed-pairs`
now fails closed before linking when estimated all-pairs seed work exceeds the
configured budget (default `1000000`; set `0` only for a documented override).
Use `--link-scale-plan-out Logs/reports/<name>.json` on bounded diagnostics to
write the top night-pair and sky-cell contributors before the fail-closed stop;
the plan is diagnostic only and does not authorize a broad-field override.

**2026-06-29 scale-plan hardening update**: `--link-scale-plan-out` now records
a budget-derived diagnostic radius and recommended subfield parameters from the
actual blocked run inputs. These subfields are explicitly labeled as bounded
diagnostics, not complete-field tiling proof, because naive sky-cell partitioning
can miss objects that cross cell boundaries. Next D1 step after merge: run one
recommended WISE diagnostic subfield from `recommended_diagnostic_subfields` and
review the full `--review-packet-out` adversarial evidence if tracklets are
produced.

**2026-06-29 v0.90.2 scale-plan probe complete**: The merged `main` scale-plan
probe repeated the Taurus 0.2-degree, 370-day WISE dry run and correctly stopped
at `11786731` estimated seed pairs over the `1000000` default budget after
fetching `12061` WISE rows and detecting `12042` singleton candidates. The
scale plan recommended radius `0.0466` degrees and first diagnostic subfield
RA `58.1`, Dec `20.1`, JD `2458880.5` to `2459250.5`, survey `WISE`. Durable
evidence and the exact next command are recorded in
`docs/evidence/live/2026-06-29-wise-v0902-scale-plan-subfields.md`.

**2026-06-29 first v0.90.2 subfield diagnostic complete**: The operator ran
the first recommended subfield at RA `58.1`, Dec `20.1`, radius `0.0466`.
The run fetched `532` WISE rows, passed `531/532`, detected `531` singleton
candidates, linked `25053` seed pairs across `4` nights, and formed `0`
tracklets. Candidate and review-packet JSON outputs were empty arrays (`[]`).
The attempted adversarial-review command failed correctly with
`ERROR: no valid ScoredNEO entries found in input` because no tracklets meant no
reviewable packets. Durable evidence:
`docs/evidence/live/2026-06-29-wise-v0902-subfield-diagnostic.md`. Next D1 step:
do not rerun this exact subfield; select a different recommended subfield or
improve selection to prioritize areas likely to produce at least
three-observation tracklets. Future operator instructions must verify non-empty
full `ScoredNEO` packets before running `Skills/adversarial_review.py`.

**2026-06-29 v0.90.3 D1 guardrail hardening**: `Skills/run_pipeline.py` now
prints the number of full `ScoredNEO` review packets written and explicitly
instructs the operator to skip adversarial review when that count is zero. Link
scale plans now add local `support_metrics` to recommended diagnostic subfields,
including whether a subfield has at least three observations across at least two
nights inside the recommended radius. Next D1 step: regenerate or inspect a
v0.90.3 scale plan, choose a support-positive subfield that is not the failed
RA `58.1`, Dec `20.1`, radius `0.0466` diagnostic, and run adversarial review
only if full review packets are non-empty.

**2026-06-30 v0.90.3 scale-plan support metrics regenerated**: The Taurus
WISE/NEOWISE 0.2 degree, 370 day scale-plan probe was rerun on merged `main`
with v0.90.3. It again fetched `12061` WISE rows, passed `12042/12061`, detected
`12042` singleton candidates, and stopped fail-closed at `11786731` estimated
seed pairs over the `1000000` budget. The new `support_metrics` identify four
support-positive diagnostic subfields. The prior failed subfield RA `58.1`, Dec
`20.1`, radius `0.0466` is rank 3 and should not be rerun next. The next
verified diagnostic is rank 1: RA `58.1`, Dec `19.9`, radius `0.0466`. Codex
attempted that live run, but the approval layer rejected it because of a usage
limit. Durable evidence and the exact operator command are recorded in
`docs/evidence/live/2026-06-30-wise-v0903-scale-plan-support.md`.

**2026-06-30 v0.90.3 rank 1 diagnostic complete**: The rank 1 support-positive
WISE subfield at RA `58.1`, Dec `19.9`, radius `0.0466` was run from merged
`main`. The dry run fetched `701` WISE rows, passed `701/701`, detected `701`
singleton candidates, linked `48105` seed pairs, formed `3` tracklets, wrote
`3` full review packets, and produced `0` submission-ready candidates. Offline
adversarial review evaluated all `3` packets and returned `3/3` `REJECT`
verdicts. Shared rejection causes were missing orbit elements, missing
real/bogus score, artifact posterior about `0.98` to `0.99`, NEO posterior
about `0.001`, and motion below the hard `0.05 arcsec/hr` lower bound. Durable
evidence: `docs/evidence/live/2026-06-30-wise-v0903-subfield-58p1-19p9.md`.
Next D1 step: run the next distinct support-positive subfield from the v0.90.3
scale plan, RA `57.9`, Dec `20.1`, radius `0.0466`, and only run adversarial
review after a non-zero full `ScoredNEO` packet count is reported.

**2026-06-30 v0.90.3 rank 2 diagnostic complete**: The rank 2 support-positive
WISE subfield at RA `57.9`, Dec `20.1`, radius `0.0466` was run from merged
`main`. The dry run fetched `691` WISE rows, passed `691/691`, detected `691`
singleton candidates, linked `33540` seed pairs, formed `2` tracklets, wrote
`2` full review packets, and produced `0` submission-ready candidates. Offline
adversarial review evaluated both packets and returned `2/2` `REJECT` verdicts.
Shared rejection causes matched the rank 1 diagnostic: missing orbit elements,
missing real/bogus score, artifact posterior about `0.99`, NEO posterior about
`0.001`, and motion below the hard `0.05 arcsec/hr` lower bound. Durable
evidence: `docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-20p1.md`.
At that point, the next D1 step was the remaining distinct support-positive
rank 4 subfield, RA `57.9`, Dec `19.9`, radius `0.0466`; that operator-run
blocker was later cleared by the rank 4 diagnostic recorded below.

**2026-06-30 v0.90.3 rank 4 diagnostic complete**: The final remaining
distinct support-positive Taurus WISE subfield at RA `57.9`, Dec `19.9`, radius
`0.0466` was run by the operator. The dry run fetched `668` WISE rows, passed
`665/668`, detected `665` singleton candidates, linked `18776` seed pairs,
formed `2` tracklets, wrote `2` full review packets, and produced `0`
submission-ready candidates. Offline adversarial review evaluated both packets
and returned `2/2` `REJECT` verdicts. Shared rejection causes again matched
the prior diagnostics: missing orbit elements, missing real/bogus score,
artifact posterior about `0.98` to `0.99`, NEO posterior about `0.001`, and
motion below the hard `0.05 arcsec/hr` lower bound. Durable evidence:
`docs/evidence/live/2026-06-30-wise-v0903-subfield-57p9-19p9.md`. Root cause:
this Taurus WISE diagnostic set is producing near-stationary,
artifact-dominated internal candidates, not review survivors. Next D1 step:
do not rerun these Taurus subfields; select a new WISE/NEOWISE field-window
strategy likely to produce faster non-static candidates, or improve
WISE-specific filtering/linking before the next operator live run.

**2026-06-30 v0.90.4 D1 motion-floor alignment**: `detect.py`, `link.py`, and
`audit_real_run.py` now use the same `0.05 arcsec/hr` lower motion floor as
`Skills/adversarial_review.py` and `docs/MISSION.md`. This prevents
near-stationary WISE associations from becoming review packets that are
guaranteed to fail D1 on the motion-rate challenge. The next D1 blocker after
this patch is not Taurus reruns; it is either a new WISE/NEOWISE field-window
strategy likely to produce faster non-static candidates, or a defensible
WISE-native real/bogus/quality policy for archive detections.

**2026-06-30 v0.90.5 WISE parent-field probe selector**:
`Skills/select_survey_fields.py --wise-archive-probes` now enriches ranked
field selections with copy-paste-safe WISE/NEOWISE scale-plan probe commands.
The generated commands use `caffeinate -i`, Python 3.14 via `uv run`, bounded
native thread settings, dry-run mode, and `--link-scale-plan-out` so the next
non-Taurus parent field is measured before any full diagnostic run. This closes
the immediate D1 planning/tooling gap after the Taurus diagnostics were
exhausted. Next D1 step: run the selector for a non-Taurus WISE archive window,
then run the top generated scale-plan probe from merged `main`; do not run
adversarial review unless the subsequent pipeline run writes non-zero full
`ScoredNEO` review packets.

**2026-06-30 v0.90.5 non-Taurus parent-field scale-plan probe complete**: The
v0.90.5 selector-generated parent field at RA `209.64`, Dec `-15.0`, radius
`0.2`, JD `2458880.5` to `2459250.5`, survey `WISE`, ran from merged `main`.
The dry run fetched `16582` WISE rows, passed `16558/16582`, detected `16558`
singleton candidates, and stopped fail-closed at `27845455` estimated seed
pairs over the `1000000` default budget. The scale plan recommended radius
`0.0303` degrees and four support-positive diagnostic subfields. Durable
evidence and the exact next command are recorded in
`docs/evidence/live/2026-06-30-wise-v0905-parent-field-probe.md`.

**2026-06-30 v0.90.5 rank 1 support-positive diagnostic complete**: The rank 1
v0.90.5 support-positive subfield at RA `209.5`, Dec `-14.9`, radius `0.0303`
was run from merged `main`. It fetched `690` WISE rows, passed `686/690`,
detected `686` singleton candidates, linked `58596` seed pairs, and produced
`0` tracklets and `0` full review packets. The pipeline correctly printed the
skip-adversarial-review instruction because there was no reviewable `ScoredNEO`
input. This is valid diagnostic evidence, not a runtime failure. It is
historical context for the v0.90.6 WISE positive-control harness that later
closed Gate P1. Next production-capability step: close Gate P2 by documenting
WISE/DECam/TESS confidence metrics before further live operator runs.

---

## ZTF_DR24_PRODUCTION_GATES.md historical narrative — Gate Z3

Archived verbatim from `docs/ZTF_DR24_PRODUCTION_GATES.md`'s "Next Coding
Step" section. This is the full Gate Z3 diagnostic trail: the state-at-pause
summary (2026-07-04 v0.90.54) followed by every dated update walking back
through the source-verification and four-apparition candidate-pair search.
The gate remains OPEN and intentionally paused; the current file keeps only
the Gates table row and a condensed pause notice plus a pointer here.

**State at pause, as of 2026-07-04 (v0.90.54)**: Gate Z3's remaining blocker is
narrower than it looks -- the detection/linking pipeline is confirmed
working correctly against real archived ZTF data (two full candidate
pairs, 546 real cross-night tracklets formed total). What's missing is a
clean single-object match, not pipeline mechanics. Two candidate pairs of
designation 72966 have been tried and both failed to positively confirm.
Root-cause work found one pair's failure was due to a sentinel/placeholder
MPC report (`mag=99.00`) being used as a position reference; the other
pair's failure remains only partially explained (different reporting
observatories, but that alone doesn't fully account for a 35-arcmin gap).
Do not blindly try a third apparition of 72966 without first doing one of:

1. **(Cheap, recommended first)** Filter `Skills/scan_mpc_history_ztf_coverage.py`'s
   candidate selection to exclude MPC reports with `mag >= 90`
   (sentinel/placeholder, matching this codebase's existing sentinel-mag
   convention elsewhere) before selecting a reference position for a new
   apparition. This directly would have avoided the first pair's failure
   mode.
2. **(More substantial)** Select a different, well-observed real NEO
   designation entirely via the same MPC-history-scan methodology,
   rather than continuing to exhaust apparitions of a single object.

See `docs/evidence/live/2026-07-04-gate-z3-observatory-codes-real-findings.md`
for the full real-data analysis this recommendation is based on.

---

**Superseded 2026-07-02**: the per-source ZTF DR24 detection source, its
schema, and a bounded multi-night ingest tool are now all built and
**confirmed working against the real archive in a live operator run** --
see the Gate Z3 row above and
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-first-live-run.md`.
Do not repeat the source search, the schema-field research, or rebuild the
ingest tool from scratch. Do not re-run the exact `20180809`/`20180810`
pair for its own sake -- that data already exists (21 real kept
observations for night 1, 0 for night 2) and does not need to be redone;
the progress-silence bug that run also caught is separately fixed in
v0.90.36/PR #173.

**Why nights 2 and 3 produced zero matches -- now confirmed, not just
inferred**: `ztf_public_20180810.tar.gz` and `ztf_public_20180812.tar.gz`
both had zero detections in the same 2-degree sky box as night 1. A Gate
Z1 live run against the real IRSA sci-metadata endpoint (2026-07-02, see
Gate Z1 row and
`docs/evidence/live/2026-07-02-gate-z1-bounded-ingest-first-live-run.md`)
confirms this is not a linking or ingest problem: across the full 10-day
window from night 1 (JD 2458339.5-2458349.5), IRSA reports **only 1
distinct night and 1 distinct field** with any real science exposure at
this exact sky position. ZTF simply did not point at this field again in
that window. Blindly trying more individual nights against the multi-GB
alert archive is no longer justified -- use the metadata tool first.

**Update 2026-07-02 (v0.90.38)**: the 100-day-window run above was
executed live and found a **real second night** -- 14 rows across 2
distinct nights, 1 field. See
`docs/evidence/live/2026-07-02-gate-z1-wider-window-second-night.md`. The
tool's report initially only exposed `n_distinct_nights` as a bare count,
not which nights -- fixed by adding `distinct_nights_yyyymmdd` (real UTC
calendar dates, matching the alert archive's `ztf_public_YYYYMMDD.tar.gz`
naming) to the report, computed from the already-cached raw response with
no new network call needed.

**Update 2026-07-02 (v0.90.39)**: the first `distinct_nights_yyyymmdd`
output (`['20180808', '20180902']`) had a real off-by-one bug -- JD
increments at noon UTC, not midnight, and the code truncated `obsjd` to an
integer before converting to a calendar date, silently landing on the day
before the correct one. Fixed; see
`docs/evidence/live/2026-07-02-gate-z1-night-date-offbyone-fix.md`. The
corrected real night pair for this sky position is **20180809** (not
20180808) and **20180902** -- roughly 24 days apart, confirming this
specific 2-degree field is genuinely low-cadence, not a bug.

**Update 2026-07-02 (second attempt result)**: that command was run.
Night 20180809 resumed from cache (21 kept, unchanged). Night 20180902
(real, confirmed exposure via Gate Z1) downloaded 8.5GiB, scanned 192,243
real packets over 7m09s with correct live progress/ETA throughout
(confirms the v0.90.36 and v0.90.39 fixes both work together on a real,
large file) -- but kept **0**. This is a genuine negative, not a bug: see
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-second-attempt.md`.
Two real multi-GB downloads (5.3GiB + 8.5GiB) have now produced zero net
progress toward a linkable 2-night pair via blind field-revisit sampling.
**Blind field-revisit sampling is no longer the recommended next step.**

**Next step (v0.90.40)**: target a real, known NEO instead of an arbitrary
field. `Skills/lookup_neo_archive_ephemeris.py` queries the Phase-0-verified
JPL Horizons endpoint (`src/fetch.py:fetch_horizons`, already 100%-covered
production code) for a real object's real predicted sky position across a
date range, so the alert-archive ingest tool can target a specific real
position instead of guessing. Default designation `72966` is the real
`ssnamenr` cross-match already present in a real Gate Z3 alert packet
(not a guess -- see
`docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md`):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/lookup_neo_archive_ephemeris.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d
```

This prints the object's real predicted RA/Dec on each real calendar night
in the window. **That first live run was executed (2026-07-02)** and
revealed a real targeting error, not just a low-cadence field: by night
20180902 the object's real predicted position had moved ~9.4 deg in RA
and ~3.2 deg in Dec from the original fixed 2-degree search box used in
the second alert-archive attempt -- the earlier "Gate Z1 hit" for that
night was a coincidental revisit of the *original* field, unrelated to
where the object actually was. See
`docs/evidence/live/2026-07-02-neo-72966-ephemeris-and-targeting-error.md`.

**Next step (v0.90.41)**: `Skills/scan_neo_track_coverage.py` re-centers
the cheap Gate Z1 metadata check on each candidate night's real predicted
position (not a stale fixed field), for a bounded, stride-limited subset
of real ephemeris points:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/scan_neo_track_coverage.py \
    --designation 72966 \
    --start-jd 2458339.5 --end-jd 2458439.5 --step 1d --stride 5
```

This checks 1 of every 5 real nights (21 metadata queries, cheap) at the
object's real predicted position for that night, and reports which (if
any) had real ZTF science exposure there. Only once a real, non-guessed
night with confirmed real coverage near the object's real position is
found should `Skills/ztf_alert_archive_ingest.py` be run against it (using
that night's predicted RA/Dec as the search center, not the original
fixed field) -- do not skip straight to the expensive alert-archive step
without this cheap check first.

**Update 2026-07-02 (real hit found)**: that scan was run live. Real
result: 2 of 21 checked nights had real ZTF coverage -- night 20180809
(already known) and **night 20180903** (new, RA 242.0130, Dec -11.6968,
6 real sci exposure rows) -- found via targeted ephemeris-based scanning,
not blind guessing. See
`docs/evidence/live/2026-07-02-gate-z3-track-coverage-scan-hit.md`.

**Next step**: run the alert-archive ingest tool against night 20180903,
centered on this night's real predicted position (not the stale original
field used in the earlier failed attempt):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20180903 \
    --ra 242.0130 --dec -11.6968 --radius-deg 2.0 --min-rb 0.5
```

Night 20180809's existing cached data (21 kept, centered on RA 232.6/Dec
-8.4, within ~0.05 deg of 72966's real predicted position that night)
already covers this object's real location and does not need re-fetching.
If night 20180903 also yields >=1 kept observation, this project will have
real per-source detections on 2 real nights for the first time.

**Update 2026-07-02 (loader/runner built, v0.90.42)**: the positive
control loader/runner is now built --
`Skills/run_archive_positive_control.py` loads real per-source
`Observation` objects from >=2 nights' checkpoint files and runs the exact
production `preprocess()` -> `detect()` -> `link()` chain, reporting
whether a real multi-night tracklet forms. Offline verification (using
the exact synthetic generator already proven in
`Skills/injection_recovery.py`'s baseline) found a real parameter-
sensitivity issue: `link()`'s default `min_observations=3` can reject a
genuine 2-night tracklet when each night contributes only 1-2
observations to the final arc. Real archived data has far more
observations per night (21 on night 20180809 alone) so the default is
likely fine, but `--min-observations 2` is available to re-check a
zero-tracklet result before concluding failure.

Once night 20180903's alert-archive ingest completes (see the command
above), run:

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

**Update 2026-07-02 (third attempt result -- real negative, root cause
diagnosed)**: night 20180903's alert-archive ingest was run. Real result:
8.5GiB, 193,223 real packets scanned over 8m36s with correct progress/ETA,
but **kept 0**, despite Gate Z1 confirming 6 real sci exposure rows at
this exact position that night. Root cause: a real science exposure
existing confirms only that ZTF pointed a camera there -- not that its
difference-imaging pipeline generated a real alert (`rb >= 0.5`) at that
specific sub-position. "Was the sky imaged" and "did a real alert fire
here" are different questions; Gate Z1's metadata check only answers the
first. See
`docs/evidence/live/2026-07-02-ztf-alert-archive-ingest-third-attempt.md`.

**Next step (v0.90.43)**: `Skills/lookup_mpc_observation_history.py`
queries a stronger signal -- MPC's own confirmed observation history
(`src/fetch.py:fetch_mpc_observations`, already Phase-0-verified
production code). A real MPC-reported observation means a real
astrometric detection genuinely happened and was credible enough to be
submitted and accepted, not just that the sky was imaged:

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/lookup_mpc_observation_history.py \
    --designation 72966 \
    --archive-start-jd 2458273.5
```

This reports every real MPC-confirmed observation of 72966 since the ZTF
archive's coverage began (2018-06-04). Cross-check any in-window nights
against `Skills/ztf_dr24_bounded_ingest.py` (cheap) before committing to
another multi-GB alert-archive download. If 72966 turns out to have very
few or no MPC-confirmed reports within the archive window, the next
escalation is to pick a different, more actively-observed real NEO rather
than continuing to chase this specific object.

**Update 2026-07-02 (real result: 1332 total reports, 526 in-window)**:
this returned real, substantial data -- far denser than the single
`ssnamenr` cross-match that originally identified this object. See
`docs/evidence/live/2026-07-02-mpc-observation-history-72966.md`. A dense
real cluster of 4 report nights in July 2018 (20180711, 20180713,
20180714, 20180715) was cross-checked against Gate Z1: only night
20180713 showed real ZTF coverage (9 rows, 1 field) -- most of the other
reports were evidently made by a different observatory/survey, not ZTF.
See `docs/evidence/live/2026-07-02-gate-z1-mpc-cluster-crosscheck.md`.
Night 20180713 is the strongest single-night candidate found so far (two
independent real confirmations), but a second confirmed night is still
needed.

**Next step (v0.90.44, parallelized in v0.90.45)**: `Skills/scan_mpc_history_ztf_coverage.py`
systematically checks a bounded, stride-limited subset of ALL 526 real
in-window MPC reports against Gate Z1, instead of hand-picking more
clusters. `--shard-index`/`--shard-count` split the ~53 queries across
multiple concurrent terminal tabs to cut wall-clock time -- each shard
checks a disjoint subset of the same strided list, so there is no overlap
or duplicate querying, and the one-time MPC-history fetch itself resumes
from the operator's already-cached checkpoint (no re-fetch per shard):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
```

Run each of these 4 commands in its own terminal tab:

```bash
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 0 --shard-count 4
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 1 --shard-count 4
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 2 --shard-count 4
caffeinate -i uv run --python 3.14 python Skills/scan_mpc_history_ztf_coverage.py \
    --designation 72966 --archive-start-jd 2458273.5 --stride 10 \
    --shard-index 3 --shard-count 4
```

Together these issue the same ~53 cheap Gate Z1 metadata queries (1 per
10 real in-window MPC reports) as the single-process run, at each
report's own exact real observed position/date, reporting every real
night with both an MPC-confirmed detection and real ZTF coverage.

**Update 2026-07-02 (real result: 30/53 hits)**: the operator ran the
scan to full completion (sequential, pre-sharding version, ~12 min) and
found **30 of 53** checked real MPC reports with real ZTF coverage --
far richer than the earlier hand-picked cluster. See
`docs/evidence/live/2026-07-02-gate-z3-full-mpc-scan-30-hits.md`. Selected
the strongest candidate pair: **20220817 and 20220819** (2 real days
apart, both independently MPC- and Gate-Z1-confirmed, 16/24 real sci
rows).

**Next step**: run the alert-archive ingest tool against both nights,
each centered on that night's own real matched position:

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

If both yield >=1 kept observation, run the positive control:

```bash
caffeinate -i uv run --python 3.14 python Skills/run_archive_positive_control.py \
    --nights 20220817 20220819 \
    --out Logs/pipeline_runs/run_archive_positive_control/report.json
```

Backup candidates if this pair fails: 20191005/20191008 (3 days apart,
30/24 sci rows) or 20220626/20220628 (2 days apart, but night 2 only has
2 sci rows -- riskier).

The same dump also revealed the packet includes ZTF's own solar-system
cross-match fields (`ssnamenr`/`ssdistnr`/`ssmagnr`) -- do NOT wire these
into known-object exclusion logic yet; their catalog provenance and
update-cadence relative to no-future-leakage requirements has not been
researched. Continue using `src/known_object_exclusion.py`'s existing JPL
SBDB `first_obs` approach as the only currently-verified mechanism for that
gate.

---

## CLAUDE.md original "Key Changes in vX.Y.Z" section (v0.6.0 – v0.87.9)

Archived verbatim from `CLAUDE.md`'s per-version changelog section, which
was removed from `CLAUDE.md` on the assumption it fully duplicated
`CHANGELOG.md`. **That assumption was only partly correct** — a lossless
verification pass found `CHANGELOG.md` has no per-version entry at all for
**v0.87.1 through v0.87.9** (it jumps from v0.87.0 straight to v0.89.0),
so those nine versions' detail — including the T1-A ensemble-stacker
closure, the T1-D calibration KPI gate pass, and the macOS PyTorch
deadlock fixes that produced several still-active `CLAUDE.md` standing
rules — existed nowhere else. Rather than selectively re-inserting just
those nine, the full original section (v0.6.0–v0.87.9) is preserved here
verbatim for a complete, unambiguous record. Cross-reference notes:
- v0.6.0–v0.76.0 and v0.87.0 (excluding v0.77.0–v0.86.0 and v0.87.1–v0.87.9):
  genuinely duplicated in `CHANGELOG.md` under matching `## vX.Y.Z` headings.
- v0.77.0–v0.86.0: `CHANGELOG.md` covers this range with one consolidated
  entry ("API accumulation cycle") noting the added helpers/docs were later
  removed with no production impact — the per-version function-level detail
  below describes code that no longer exists, kept here for completeness only.
- v0.87.1–v0.87.9: genuinely absent from `CHANGELOG.md` — this is the only
  record of that work.

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
