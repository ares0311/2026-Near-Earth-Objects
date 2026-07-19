# Active Handoff — ZTF DR24 Motion-Product Pivot

Updated: 2026-07-19 (Hunter PROD Directive integrated)

## Operator closed Phase 1; Phase 2 active (2026-07-19)

After reviewing the implementation, real replay, clean-commit reliability
record, and all-green GitHub CI in PR #258, the operator explicitly closed
Phase 1 and authorized Phase 2. PR #258 was squash-merged to `main` as
`1cc6351f`. The active work is now deterministic, explainable, reproducible
search ranking and eligibility hardening. Phase 3 CLI/durable-state packaging
remains blocked until Phase 2 closes.

The first Phase 2 unit now gates scoring on measured three-night coverage and
preserved terminal search history, with explicit `new`/`follow-up` semantics.
It also corrects the misleading `gap_score` name to
`survey_scarcity_score`, removes the nonexistent/opaque model hook, and
appends terminal evidence for six completed searches without rewriting their
older planning rows. Targeted result: 75 selector tests passed; real committed
state replay returns zero of those six as `new` and all six in the follow-up
eligible universe before observability filtering. Evidence:
`docs/evidence/live/2026-07-19-phase2-ranking-eligibility.md`.

Phase 2 is not closed. The next gap is replay-cutoff-aware known-object
association in adversarial eligibility; the present-day live density check can
also turn provider failure into a passing zero count. Do not start Phase 3.

That next gap is now implemented as epoch-specific SkyBoT positional matching
plus earliest published MPC observation filtering, wired to the shared
no-future-leakage predicate. Provider/schema/history failures and offline
review without cached evidence now `FAIL`; later-discovered matches warn but do
not reject. Focused result: 93 tests passed and the Phase 1 packet replay stays
`REJECT=2` with the previously omitted evidence now explicit. Live-positive
verification is still open: both a bounded candidate-shaped request and
Astroquery's documented example reached SkyBoT but returned HTTP 500 on
2026-07-19. Evidence:
`docs/evidence/live/2026-07-19-phase2-known-object-eligibility.md`.

Do not retry the same provider request in a loop. On service recovery, run one
documented probe and one known-object positive control. Independently, the next
safe Phase 2 code gap is ATLAS confirmation quality: the current challenge can
treat arbitrary returned rows as confirmation without validating time,
position, or measurement quality. Phase 3 remains blocked.

## Phase 1 implementation complete; operator closure pending (2026-07-19)

Both named Phase 1 detection-hardening gaps now meet their technical exit
criteria, with tests and a replay of the original three-night field-1 data.
Phase 2 remains blocked because the roadmap requires explicit operator closure.

1. Pixel extraction now preserves its real PSF-kernel correlation as
   `Observation.psf_shape_correlation` and aggregates it separately as
   `psf_quality_score`. It deliberately does not fabricate a calibrated
   `real_bogus_score`; `tier2_cnn_v4` cannot consume this path's products
   because its required three 63x63 cutouts do not exist here. Adversarial
   review fails closed on missing coverage or any correlation below the
   independently tested 0.5 artifact discriminator; even complete passing
   coverage yields `WARNING`, not `PASS`.
2. The invalid approximate orbit initialization and hard-coded fit residual
   were replaced with a deterministic bounded two-body state fit using the
   bundled offline Earth ephemeris and measured astrometric RMS. Arc sufficiency
   is now stored independently as `arc_quality_tier`; fit outcome is stored as
   `orbit_fit_status`. A tier-2 arc with no physical solution now says exactly
   that instead of exposing an ambiguous null quality code.

Real replay result: 471 observations, two linked tracklets, both correctly
rejected. Their PSF means are 0.0680 and 0.0116 with incomplete coverage; both
have `arc_quality_tier: 2`, `orbit_fit_status: no_solution`, and no invented
orbital elements. Canonical verification passed all six stages with 2,067 tests
and 100% `src/` coverage before the final documentation update. Full evidence:
`docs/evidence/live/2026-07-19-phase1-detection-hardening.md`.

## Hunter PROD Directive confirmed and integrated (2026-07-19)

Jerome W. Lindsey III confirmed a cross-project "Hunter PROD Directive"
(this repo is NEO-Hunter; sibling repos Techno-Hunter/EXO-Hunter are
independently sandboxed, no cross-repo coupling) is real and intentional
— it extends, not contradicts, the three-phase roadmap below. Recorded
verbatim in `docs/HUNTER_PROD_DIRECTIVE.md`, referenced from both
`CLAUDE.md`'s MANDATORY SESSION-START PROTOCOL and `AGENTS.md`'s
mandatory-read list.

Performed the directive's required SESSION START pipeline-mapping
exercise against this repo's actual code (verified, not assumed): the
candidate universe, identity/history resolution, data acquisition,
preprocessing, composite interpretation, and durable results/provenance
stages all have real, working implementations already. Real gaps found:
no unified CLI exists at all (verified via `pyproject.toml` — no
`[project.scripts]`, and no CLI wrapper in the repo root); no discrete
"pending search" entity exists before execution; the existing manifest
(`data_selection/target_priority_queue.csv`) is a running priority list,
not a per-run manifest; there is no durable follow-up registry (only ad
hoc scripts). Full stage-by-stage table in `CLAUDE.md`'s "Current
Roadmap Phase" section.

Phase 1 (harden the detection pipeline) remains active and unchanged.
Phase 2 and Phase 3 were reframed in the Hunter directive's specific
terms (deterministic ranking model for Phase 2; the required CLI +
5 durable-state entities for Phase 3), without changing their blocked
status. **No code changes — documentation/roadmap integration only.**

## Operator decision (2026-07-19): three-phase roadmap replaces the old 3-way decision

Jerome W. Lindsey III flagged that continued field-expansion runs
(fields 3, 4, 6 below) after MP1-MP7 already closed was drift —
re-exercising an already-proven pipeline mechanism rather than doing real
hardening work. Replaced the "resume Z3 / broader batch / MPC path"
3-way decision with an explicit sequence: **Phase 1 (active) — harden
the detection pipeline; Phase 2 (blocked) — harden the search algorithm;
Phase 3 (blocked) — package the application to run autonomously offline.**
Recorded in full in `CLAUDE.md`'s "Current Roadmap Phase" section
(immediately after PRIMARY DIRECTIVE) and mirrored into `AGENTS.md` for
Codex parity. Phase 1's two concrete named gaps, found by inspecting real
review-packet output from the five completed field tests below (not
guessed): (1) `real_bogus_score` is always `None` for pixel-extraction
candidates — no real/bogus signal exists for this data path; (2)
`fit_orbit()` returns `quality_code: null` for every tested candidate
rather than a graded low-quality code, despite the schema anticipating
short-arc cases. **Do not run another field-expansion batch, resume Gate
Z3, or start MPC-submission work until both gaps are investigated and
closed (fixed or explicitly documented as correct).**
Repository identity: `2026 Near Earth Objects`
Branch: `main`
Merged batch selection: `d81af0a0` (PR #235)
Execution manifest: `b048be9c`
App version: `v0.91.0`

## Operator decision (2026-07-16): motion-product pivot approved

Jerome W. Lindsey III chose Option 1 of the three-way decision below:
**pivot candidate generation to survey detection/image products designed
for motion**, keeping the completed alert-replay work as benchmark/null
evidence. This is now the active ZTF DR24 direction. The immediate next
step taken under this decision was the first live, integrated run of
`Skills/ztf_dr24_bounded_ingest.py --preflight-motion-products` (previously
only manually HEAD-probed): all four products for the one-exposure bounded
verification window (RA 232.6, Dec -8.4, 0.01 deg, JD 2458339.5-2458340.5)
returned HTTP 200, `available: true`, aggregate 27,311,040 bytes, no bodies
downloaded. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-motion-product-preflight-first-live-run.md`.
This confirms the checkpointed preflight tool itself, not just the manual
probe.

**Next step completed same day**: the bounded, single-exposure
pixel-extraction pilot named above. `Skills/ztf_dr24_bounded_ingest.py
--pixel-extraction-pilot` downloads exactly one difference image and runs a
minimal numpy/scipy/astropy source detector, converting hits to RA/Dec via
WCS. Real live run on the same verified exposure: 855 pixels genuinely
cleared a 5-sigma threshold, output capped at 200 -- a report bug that
silently hid the true 855 count behind the cap was caught and fixed (per
the standing no-silent-caps rule) before this was recorded, with two new
regression tests. This proves real RA/Dec extraction from DR24 pixels works
end-to-end, independent of `prv_candidates`; it also honestly surfaces that
bad-pixel masking (the already-verified `science_mask` product), peak
deduplication, and PSF-matched photometry are still needed before the
source list is usable for real candidate generation. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md`.

**Masking + deduplication closed same day**: the detector now applies the
exposure's verified `science_mask` (nonzero pixels excluded) and uses
connected-component labeling instead of local-maximum filtering, so one
physical residual spanning several pixels becomes one candidate source.
Real re-run on the same exposure: 855 raw pixel-hits -> 74 after masking ->
71 connected components, untruncated. Masking alone did nearly all the
work; most surviving components are 1-2 pixels (consistent with genuine
near-threshold detections, not artifact blobs). Schema bumped to
`ztf-dr24-pixel-extraction-pilot-v2`. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-masking-dedup.md`.
**PSF-shape scoring closed same day — single-exposure arc complete**: the
detector now Pearson-correlates a cutout around each candidate against the
real `difference_psf` kernel (shape consistency, not flux-calibrated
photometry). Real result: the PSF kernel is 25x25 pixels, larger than
assumed when this gap was scoped, so 38 of the 71 v2 candidates were too
close to the image edge for a full cutout. **Of the 33 that could be
scored, none exceed 0.18 correlation** (mean 0.037, median 0.010) -- an
honest null result. A unit test confirms the method itself works (a real
synthetic Gaussian source correlates >0.95 against its own generating
shape), so this is a genuine finding about this exposure's candidates, not
a broken metric: none of them show meaningful evidence of being real point
sources, consistent with noise-level fluctuations right at the 5-sigma
threshold. Schema bumped to `ztf-dr24-pixel-extraction-pilot-v3`. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-psf-scoring.md`.

**This completes the single-exposure pixel-extraction pilot arc**
(preflight -> extraction -> masking/dedup -> PSF-shape scoring), each step
closing the disclosed gap from the one before it. **Still not authorized**:
a wider batch, a candidate claim, Gate Z3 resumption, or any external
submission. **The next step is a genuine operator decision, not another
same-exposure refinement**: try this pipeline against a different
exposure/field (this null result may just mean this one night/field had
nothing), build real multi-exposure tracklet linking (the actual next
scientific rung -- consistency across exposures, not just single-exposure
PSF shape), or pause this path here having validated the extraction
mechanics end-to-end on real data.

## Operator decision (2026-07-17): multi-night linking, not a different field

Jerome W. Lindsey III chose real multi-exposure linking (the scientifically
necessary path, since motion can only be measured across >=2 epochs) over
retrying a different field. Acquired 2 additional real nights (20180802,
20180806) of the same field via a metadata-only coverage query (52 real
nights found over ~400 days; picked the 2 closest), ran the full pilot
pipeline on each, and linked across all 3 nights.

New: `Skills/convert_pixel_extraction_to_observations.py` and
`Skills/run_pixel_extraction_positive_control.py` (reuses `preprocess()`+
`link()`, bypasses `detect()`'s WISE/DECam/TESS-only singleton-preservation
gate rather than modifying shared `detect.py` core logic -- root-caused
live: `detect()`'s ZTF path structurally cannot handle single-exposure-
per-night data). A real magnitude-proxy bug (negative values rejected by
`preprocess()`'s `mag <= 0` gate, 0/471 observations passing) was also
root-caused and fixed before this evidence was recorded.

**Result**: `min_observations=2` produced 200 tracklets -- expected
combinatorial explosion (36-arcsec field, 60 arcsec/hr x multi-day
tolerance covers the whole field), reproducing the same crowded-field
pairing phenomenon Gate Z6 already documented for the old alert-based
path. The real default `min_observations=3` (chi2 orbit-consistency
required) collapsed this to **2** tracklets. Both fail independent
cross-validation against the earlier PSF-shape scores: every observation
is at/near the 5-sigma noise floor with `psf_correlation` far below the
real-source threshold (max 0.068 vs >0.95 for a real injected source).
**Honest conclusion: a well-supported null result across the full
pipeline** -- extraction, masking, dedup, PSF-scoring, and linking all
work correctly end-to-end on real data; no candidate from this 3-night,
one-field test is plausible. Evidence:
`docs/evidence/live/2026-07-17-ztf-dr24-multi-night-linking-first-test.md`.

**Still not authorized**: a wider batch, a candidate claim, Gate Z3
resumption, or any external submission.

**Second field run same day, per operator direction ("pick a promising
field via the project's existing selection scoring")**: ran the identical,
unmodified pipeline against `Skills/select_survey_fields.py --mode aten`'s
rank-1 field (RA 217.41, Dec -15.0, score 0.9308, elongation 82.8 deg,
never processed before), a real ZTF field 325 with 31 real covered nights
found via metadata-only query. Acquired 3 nights (20180327, 20180330,
20180409). Result: `min_observations=2` again gave 200 combinatorial
tracklets; the real default `min_observations=3` gave **5** survivors, all
failing independent PSF-shape cross-validation (max correlation 0.168,
still far below the >0.5 real-source threshold). **A second,
algorithmically-selected field reproduces the same null result as the
first** -- this strengthens, not weakens, the conclusion that it is not an
artifact of one specific field/night combination. No code changes were
needed. Evidence:
`docs/evidence/live/2026-07-17-ztf-dr24-selected-field-linking-test.md`.

Still not authorized: a wider batch, a candidate claim, Gate Z3 resumption,
or any external submission. Two fields, six real nights, and the complete
pipeline (extraction through linking) are now validated end-to-end with
consistent, cross-validated null results. Next is an operator decision.

## MP6/MP7 closed same day (2026-07-17) — all Motion-Product Gates now CLOSED

Executed the MP6 closure plan pre-written in `docs/ZTF_DR24_PRODUCTION_GATES.md`.
Added `--build-review-packets`/`--review-packet-out` to
`Skills/run_pixel_extraction_positive_control.py` (mirroring
`run_archive_positive_control.py`'s existing pattern), then ran field 1's
checkpoints through the real `classify() -> fit_orbit() -> score() ->
process_alert(dry_run=True)` chain: 2 real `ScoredNEO` packets produced.
Found and fixed a real interface gap along the way: the plan's original
`--out` command writes a wrapper dict `adversarial_review.py` cannot parse
as a `ScoredNEO` array; the new `--review-packet-out` flag writes the plain
array both `adversarial_review.py` and `export_ades_report.py` actually
expect. With that fix, the drill produced exactly the predicted result:
`SURVIVE=0 BORDERLINE=0 REJECT=2`, with `artifact_posterior` FAIL
(`stellar_artifact` ~0.99) independently agreeing with MP4's PSF-correlation
finding via a third distinct signal (classifier posterior, not pixel-shape
correlation). `export_ades_report.py` produced valid `stn=XXX` ADES PSV
text; code inspection confirmed zero network-capable imports. Evidence:
`docs/evidence/live/2026-07-17-ztf-dr24-mp6-no-submission-drill.md`.

MP7 followed mechanically: added a "ZTF DR24 motion-product path" section
to `docs/OPERATOR_GO_NO_GO_RUNBOOK.md`, mirroring the existing alert-replay
section, citing the corrected `--review-packet-out` command and the MP6
evidence above.

**All seven Motion-Product Gates (MP1-MP7) are now CLOSED.** No candidate
survived adversarial review on either tested field — a well-supported null
result (three independent signals agree: geometric chi2-consistency,
PSF-shape correlation, and classifier posterior), not a tooling gap. Per
the Production Definition in `docs/ZTF_DR24_PRODUCTION_GATES.md`, this does
not block production readiness; a confirmed discovery is not a
precondition. Still not authorized without further operator direction: a
new field/wider batch, Gate Z3 resumption, or any external submission.

## Third field expanded same day (2026-07-17), per operator decision to keep expanding

Jerome W. Lindsey III chose "expand to more fields" over resuming Gate Z3
or pausing (offered as a structured 3-option decision after MP6/MP7
closed). Selected rank 2 of the same `--mode aten --top-n 20` batch that
gave field 2 (RA 217.41, Dec -15.0, now marked `null_result` in
`data_selection/target_priority_queue.csv`): **RA 54.35, Dec 15.0, score
0.8997**. Acquired 3 real nights (20180807, 20180810, 20180813) of real
ZTF field 506 via the identical, unmodified pixel-extraction pipeline.

**Result**: `min_observations=2` gave 71 tracklets (lower than either
prior field's 200, consistent with this field's lower raw per-night
candidate counts: 18/200-capped/53). The real default `min_observations=3`
gave **zero** tracklets -- a cleaner null result than fields 1 (2
survivors) and 2 (5 survivors), since the chi2 orbit-consistency filter
rejected every combinatorial candidate outright with nothing left to run
through PSF-shape cross-validation or adversarial review.
`--build-review-packets --review-packet-out` correctly wrote an empty
packet list. Evidence:
`docs/evidence/live/2026-07-17-ztf-dr24-third-field-linking-test.md`.

**Three consecutive algorithmically-selected fields, nine real nights
total, now show consistent null results** across the fully-validated
pipeline. Still not authorized without further operator direction: a wider
batch, a candidate claim, Gate Z3 resumption, or any external submission.

## Fourth field expanded (2026-07-18), continuing "expand to more fields"

Selected rank 3 of the same `--mode aten --top-n 20` batch that gave
fields 2 and 3: **RA 48.71, Dec 22.5, score 0.8879**. Acquired 3 real
nights (20180713, 20180716, 20180719) of real ZTF field 556.

**Result**: `min_observations=2` gave 200 tracklets (capped); the real
default `min_observations=3` gave **6** survivors -- the most of any
field tested so far. All 6 were correctly REJECTED by
`Skills/adversarial_review.py --offline` (`artifact_posterior`:
`stellar_artifact` ~0.99 for every packet; `neo_dominance`: `neo_candidate`
~0.001 for every packet; 2 of the 6 also failed the hard motion-rate
bound as near-stationary pairings). Independently, PSF-shape correlation
against each night's real PSF kernel maxed at 0.077/0.124/0.187 -- far
below the >0.5 real-source threshold, consistent with fields 1-3.
`Skills/export_ades_report.py` produced valid dry-run ADES PSV for all 6.
Evidence:
`docs/evidence/live/2026-07-18-ztf-dr24-fourth-field-linking-test.md`.

**Four consecutive algorithmically-selected fields, twelve real nights
total, now show consistent null results** under both independent
verification signals (chi2 geometric consistency + classifier
posterior/PSF-shape). Still not authorized without further operator
direction: a wider batch, a candidate claim, Gate Z3 resumption, or any
external submission.

## Sixth field expanded (2026-07-19), continuing "expand to more fields"

Rank 4 of the batch (RA 211.81, Dec -7.5, score 0.8821) was checked and
skipped: metadata-only query found only 2 real distinct nights over the
max 399-day window -- below the 3-night minimum for a meaningful test.
Recorded in `data_selection/target_priority_queue.csv` as
`insufficient_coverage`. Proceeded to rank 5: **RA 46.59, Dec 15.0, score
0.8761**. Acquired 3 real nights (20180714, 20180717, 20180720) of real
ZTF field 505.

**Result**: `min_observations=2` gave 95 tracklets; the real default
`min_observations=3` gave **2** survivors. Both REJECTED by
`Skills/adversarial_review.py --offline` (`artifact_posterior`,
`neo_dominance` -- same pattern as every prior field). Independently, PSF-
shape correlation maxed at 0.260 -- still well below the >0.5 real-source
threshold. `Skills/export_ades_report.py` produced valid dry-run ADES PSV
for both. Evidence:
`docs/evidence/live/2026-07-19-ztf-dr24-sixth-field-linking-test.md`.

**Five algorithmically-selected fields now tested with a real linking
run, fifteen real nights total** (plus one candidate correctly skipped
for insufficient coverage before consuming download budget), all showing
consistent null results under both independent verification signals.
Still not authorized without further operator direction: a wider batch, a
candidate claim, Gate Z3 resumption, or any external submission.

Separately this session: an IRSA concurrency probe (per operator
direction) found the metadata endpoint scales cleanly to 10 concurrent,
while the pixel-download endpoint's apparent degradation at 4-6
concurrent was confounded by the operator's own changing network
connection (boarding a flight) and is recorded as unconfirmed pending a
future clean re-probe. A recurring "background task failed" notification
pattern (present all session) was root-caused to a Claude Code
tool-harness artifact, not real command failures. Full detail:
`docs/evidence/live/2026-07-18-irsa-concurrency-probe.md` and the new
standing rule in `CLAUDE.md`.

## Source-native motion-product path initiated

The recommended metadata-first pivot is now implemented without acquiring
pixels. `Skills/ztf_dr24_bounded_ingest.py --emit-motion-product-manifest`
derives the documented DR24 difference-image, science-mask, science-PSF-catalog,
and difference-PSF URLs for each usable (`infobits < 33554432`) exposure. It
marks every product unverified and performs no product download.

A one-exposure live query returned real DR24 metadata. Four HEAD probes
confirmed all planned products with an aggregate size of 27,311,040 bytes
(~26.0 MiB); no bodies were downloaded. Evidence:
`docs/evidence/live/2026-07-16-ztf-dr24-motion-product-manifest.md`.

The bounded, checkpointed HEAD preflight is now implemented and records
availability and byte estimates:
`--preflight-motion-products` defaults to 10 exposures and 4 workers, has hard
caps of 100 exposures and 6 workers, checkpoints every product, and fails
closed on missing/zero-byte/transport-failed products. Its integrated live
invocation was not authorized in the v0.91.0 session, so only the v0.90.99
manual four-HEAD live evidence exists. A later tiny pixel/extraction pilot
still requires an explicit bounded batch decision. Broad alert replay, Gate
Z3, and all external submission remain paused.

## Latest result and decision gate

Run `56c2348f31302291` completed 3/3 shards in 5m10s: 402,053 scanned,
2,311 retained, 1.1 MB persisted, zero production tracklets, zero sensitivity
tracklets, and a fresh 20/20 control. Cross-batch analysis with run
`017eb50381badb75` gave IEO 147.53 four retained nights and 8,956 seed pairs
but zero production tracklets. Its 70 sensitivity fits are all two-point/
two-night pairs. No candidate proceeds to later gates. Further bulk replay is
now a research decision, not an automatic continuation.

## Historical-context audit and operator decision

The official ZTF Science Data System documentation says `prv_candidates`
contains historical events within 1.5 arcseconds of the triggering alert and
looks back approximately 30 days. ZTF's cautionary notes further explain that
packet histories and `objectId` reuse are position-based and can split or merge
nearby sources. Therefore `prv_candidates` must not be inserted into the
moving-object linker as if it supplied missing tracklet observations.

Decision required before another large transfer:

1. **Recommended:** change candidate generation to survey detection/image
   products designed for motion, keeping the alert replay as benchmark/null
   evidence. This costs more engineering but directly addresses the observed
   mismatch between transient alerts and moving-object discovery.
2. Continue bounded alert replay. This reuses current tooling but accepts the
   measured low yield and another multi-gigabyte transfer with no evidence that
   `prv_candidates` fixes the association gap.
3. Pause the archival search. This avoids more transfer and engineering but
   does not advance the discovery-event gate.

If packet history is retained in future work, use it only as provenance-bound
context or veto evidence after an independent tracklet exists, with explicit
deduplication and no-future-leakage tests.

## Completed sparse-field expansion

`data_selection/batch_manifests/ztf_dr24_sparse_field_expansion_2024_v1.json`
targeted the two fields that remained below three retained nights. Its three
nights (`20231003`, `20231029`, `20240429`) total 19.053230740 GB and provide
98 central-box exposure rows for Aten 81.18 and 88 for IEO 147.53. It is the
minimum-transfer qualifying trio among the 12 highest-exposure candidates
whose archive sizes were HEAD-verified. Run `56c2348f31302291` executed it as
three shards x one worker; raw archives remained streamed/unpersisted and
retained output stayed at 1.1 MB.

## Completed acquisition and association

Coverage-qualified run `017eb50381badb75` completed through
`Skills/run_sharded_download.py` as four disjoint archive-night shards with one
worker each. All shard records merged successfully and the shared manifest was
automatically committed and pushed in `b048be9c`.

- Batch: `data_selection/batch_manifests/ztf_dr24_coverage_selected_2024_v1.json`
- Nights: `20240321`, `20240422`, `20240504`, `20240603`
- Verified transfer: 26.670482707 GB; raw archives were never persisted
- Runtime: 10m36s with no service error or rate limiting
- Alerts scanned: 567,025
- Observations retained: 5,416
- Durable checkpoint output: 2.2 MB
- Production association: 0 tracklets at `min_observations=3`
- Sensitivity association: 222 fits, all exactly two observations across two
  nights; all are underconstrained and not candidates
- Fresh isolated control: 20/20 detected, 20/20 linked, 20/20 scored

Five new fields had retained alerts on at least two nights; four had retained
alerts on three nights. The production analyzer loaded 5,026 observations
from those eligible fields, found 669 within-night motion candidates, examined
96,448 seed pairs, and formed zero valid tracklets. No real alert proceeds to
known-object exclusion, classification, scoring, adversarial review, or
submission.

## Where the data and status live

- Query-bound per-night checkpoints, association reports, and fresh control:
  `Logs/pipeline_runs/ztf_alert_archive_portfolio/ztf_dr24_coverage_selected_2024_v1/`
- Parent per-shard logs:
  `Logs/pipeline_runs/sharded_download/017eb50381badb75/`
- Shared file-locked execution manifest:
  `Logs/reports/sharded_download_manifest.jsonl`
- Committed result: `docs/evidence/live/2026-07-14-ztf-coverage-qualified-search-result.md`
- Downloader implementation:
  `Skills/ztf_alert_archive_portfolio.py`

The first sandboxed launch failed only because DNS and `.git/index.lock` were
blocked. The immediately repeated approved launch is the real network run.
Manifest readers select the latest record for each shard, so the earlier failed
record does not invalidate later successful records.

## Status and recovery commands

First verify `.agent-project-id`, branch state, and absence of
`Logs/tier3_pilot.active.json`. Use the repo venv and local uv cache for every
command.

Safe partial status (v0.90.95 infers four shards from the run manifest):

```bash
source .venv/bin/activate
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/run_sharded_download.py --status \
  --run-id 017eb50381badb75
```

Fail-closed completion check:

```bash
source .venv/bin/activate
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python \
  Skills/run_sharded_download.py --merge \
  --run-id 017eb50381badb75
```

The network command may require the already-approved narrow sandbox exception
for `ztf.uw.edu` and the manifest-only git relay. Do not broaden it.

## Completed analysis and next work

1. The planned coverage-qualified replay is complete and its production result
   is a valid null: zero three-observation tracklets.
2. The 222 two-point sensitivity fits are not candidates and must not enter
   time-aware known-object exclusion or later review stages.
3. The fresh batch-isolated positive control passed 20/20, so the null is not
   explained by a broken detect/link/score chain.
4. `Skills/run_sharded_download.py --status/--merge` now infers non-default
   shard topology from the selected run; legacy manifests without topology
   still require explicit `--shards`.
5. The sparse-field expansion and provenance-bound cross-batch analysis are
   complete. Another bulk replay requires an explicit research decision and a
   newly selected, logged, bounded batch. Gate Z3 remains separately paused.

Validation for v0.91.0: optimized 6x6 broad suite, 1,965 tests in 30 seconds,
100% coverage across 5,447 source statements; full Ruff and mypy clean; uv
lock and repository artifact-policy checks passed.

## Hard boundaries

- This authorization covers archival search and internal review only.
- Do not submit to MPC/NEOCP, contact NASA/PDCO or another authority, publish an
  alert, claim a discovery, or state an impact probability.
- Never call an internally detected object a confirmed NEO. Use “candidate
  consistent with an NEO orbit” until independent MPC/NEOCP confirmation.
- Gate Z3 remains a separate intentionally paused known-object identity search;
  this portfolio run does not reopen or close Z3.
- Stay inside this git root and below the 100 GB project-data ceiling.
