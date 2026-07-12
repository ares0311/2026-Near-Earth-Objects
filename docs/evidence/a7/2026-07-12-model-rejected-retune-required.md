# tier2_cnn_v3 REJECTED — Retune Required

Date: 2026-07-12
Operator: Jerome W. Lindsey III
Decision, recorded verbatim: **"Reject - Retune."**

## Decision

`tier2_cnn_v3` is **not approved** for internal production promotion.
`benchmark_cnn_v1` remains the production/frozen model. No promotion, no
benchmark replacement, no live-search expansion follows from this review.

Disqualifying evidence: `docs/evidence/a7/2026-07-12-cnn-adversarial-false-discovery.md`
— on a synthetic sub-pixel-artifact adversarial test (n=200, seed=42),
`tier2_cnn_v3` showed 100% (200/200) false-discovery versus 15.5% (31/200)
for `benchmark_cnn_v1`, confirmed both in the full ensemble and in the
isolated Tier 2 CNN output.

`docs/evidence/promotion/tier2_cnn_v3_operator_review_packet.md` §7
updated with the recorded rejection.

## Root-cause investigation (partial — reported honestly, not overclaimed)

Per this project's own root-cause-before-fix discipline, checked the
most obvious hypothesis before proposing a retune: **does `tier2_cnn_v3`'s
training data simply contain fewer/less-extreme narrow-artifact examples
than `benchmark_cnn_v1`'s?**

Method: streamed both real training files without loading them fully into
memory (637MB / 5.7GB — `json.JSONDecoder.raw_decode` in a bounded loop,
not `json.load`), sampled up to 300 real `label=3` (bogus/stellar_artifact)
examples from each, and computed each one's real difference-image PSF
FWHM using the exact same formula `src/detect.py`'s `compute_psf_fwhm`
uses (RMS-radius-of-light-distribution → FWHM, 1.01 arcsec/px, mirrored
directly from the read source, not reimplemented from memory).

| Training set | Bogus examples with FWHM < 0.3 arcsec (spike-like) |
|---|---|
| `benchmark_cnn_v1` (`data/ztf_labeled_alerts.json`, 10,000 alerts) | 17.3% (of 300 sampled) |
| `tier2_cnn_v3` (`data/ztf_labeled_alerts_v3.json`, 90,000 alerts) | 16.3% (of 300 sampled) |

**Result: nearly identical.** This rules out "v3's training data lacks
narrow-artifact diversity" as the explanation. Both models were trained on
comparable real proportions of genuinely spike-like bogus examples, yet
`tier2_cnn_v3` still shows zero discrimination on the adversarial test
while `benchmark_cnn_v1` shows partial discrimination.

**What this does NOT tell us**: the true root cause is not identified.
Plausible remaining explanations, none confirmed: different effective
generalization from the same architecture across two independent training
runs (a real, known ML phenomenon, not necessarily traceable to one
specific cause); a distributional gap between the narrow real bogus
examples in training and the specific extreme (`sigma=0.15px`) synthetic
spike used in the adversarial test, in a direction the coarse "<0.3
arcsec" bucket doesn't resolve; or something about `tier2_cnn_v3`'s
specific 20-epoch training run (real MPS run, 2026-07-10) that isn't
visible from data composition alone. Further root-causing has diminishing
returns relative to directly attacking the demonstrated weakness — see
plan below.

## Proposed retune approach

**Hard-negative training augmentation**, not a full architecture change:
add synthetic sub-pixel-spike examples (the exact same construction
`Skills/evaluate_cnn_false_discovery.py` uses for evaluation) into the
Tier 2 CNN's training data as explicit `stellar_artifact`-labeled hard
negatives. This directly, empirically attacks the demonstrated failure
mode without requiring the unresolved root-cause question to be answered
first.

Concretely, not yet implemented:
1. Extend `Skills/train_tier2_cnn.py`'s data loading to optionally mix in
   N synthetic hard-negative triplets (reusing
   `Skills/evaluate_cnn_false_discovery.py`'s `_synthesize_artifact_cutout_triplet`
   and a range of spike widths, not just the single most extreme case, so
   the model learns a genuine shape-discrimination boundary rather than
   memorizing one specific parameter).
2. Retrain (real MPS run, same 18-night/90,000-alert real data plus the
   synthetic hard negatives) producing a new candidate (`tier2_cnn_v4`,
   not overwriting `tier2_cnn_v3` per this project's naming convention for
   non-destructive iteration).
3. Re-run `Skills/evaluate_cnn_false_discovery.py` against the new
   candidate as the acceptance test before any promotion packet is built
   — the retune is only "done" when this specific measured gap closes,
   not when training completes.
4. Re-run calibration (T1-D KPIs) and grouped-split checks, since those
   must be repeated for any new candidate regardless of this specific fix.

This is a real, GPU-time-consuming retrain (recall `tier2_cnn_v3`'s
original retrain took 17m53s on real MPS hardware) — same pattern as
every prior retrain in this project: prepared here, executed on an
unsandboxed terminal with real MPS access, not attempted in this
session's sandbox.

## Not yet started

Item 1 above (extending `train_tier2_cnn.py` with hard-negative
augmentation) is real, non-trivial training-pipeline code, not yet
written. This file records the decision and the diagnostic; the
implementation is the next concrete step, pending confirmation of this
approach.
