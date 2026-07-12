# CNN Adversarial False-Discovery Test — A Major, Model-Discriminating Finding

Date: 2026-07-12
Scope: closing the third A7 evidence gap (`false_discovery_report` never
exercised any CNN's live inference), per operator direction to "close all
gaps." This one surfaced something more consequential than an evidence-
quality fix.

## What this test is, and is not

`Skills/evaluate_cnn_false_discovery.py` (new). Real archived Gate Z4
negative tracklets cannot be reused for a CNN-specific test: their cutout
images were never mapped from the raw AVRO packets (documented limitation
in `Skills/ztf_alert_archive_ingest.py`'s module docstring — "left None
rather than guessed," not an oversight). Fabricating pixel data for real
archived detections we don't have would be data fabrication, not evidence.

So this test is explicitly **synthetic-only**: it builds tracklets with
the exact same proven linear-motion generator already used by
`Skills/injection_recovery.py` (guaranteed to satisfy `link.py`'s
motion-consistency requirement), but each cutout is an unresolved,
sub-pixel spike (`sigma=0.15px`, deliberately far narrower than any real
seeing-limited PSF — a stand-in for a cosmic ray or hot pixel) rather than
a genuine point source. The spike's amplitude is tuned to clear
`detect.py`'s 0.65 real_bogus threshold on the same terms a real detection
would, so the question actually being tested is: **does this model's shape
discrimination reject an artifact that the shape-blind analytic proxy
would pass on brightness alone?**

This does **not** replace Gate Z4's real-archived-data false-link evidence
(0/200 false positives on real crowded-field combinatorial artifacts,
still valid, still the officially gating `false_discovery_report`). It
answers a narrower, different question that the real-data evidence
structurally cannot.

## Real results (n=200, seed=42, both models)

| Model | Full ensemble false-discovery rate | Tier 2 CNN alone |
|---|---|---|
| `benchmark_cnn_v1` (`models/tier2_cnn.pt`) | **15.5%** (31/200) | 16.5% (33/200) |
| `tier2_cnn_v3` (`models/tier2_cnn_v3.pt`) | **100%** (200/200) | 100% (200/200) |

Every single one of the 200 synthetic artifacts was detected and linked
for both models (200/200 — the geometry is deliberately designed to pass
`detect()`/`link()` regardless of image content, isolating the
classification question). The divergence is entirely in `classify()`'s
ensemble output.

Tier-2-isolated numbers (bypassing the ensemble, calling
`classify._tier2_predict` directly) closely track the full-ensemble
numbers for both models, which rules out "Tier 1's tabular features are
carrying the ensemble regardless of the CNN" as the explanation — the CNN
itself is making this call.

## What this means, and what it doesn't

This is a real, measured, substantial difference between the two model
candidates on a deliberately adversarial, out-of-distribution test.
`tier2_cnn_v3` shows **no discrimination at all** against this artifact
shape; `benchmark_cnn_v1` shows real (if imperfect) discrimination.

Caveats, stated plainly rather than buried:

- This is one synthetic, extreme edge case (a `0.15px` spike), not a
  representative sample of real-world artifact diversity. It says nothing
  directly about performance on more common real artifacts (satellite
  trails, diffraction spikes, ghost reflections, multi-pixel cosmic rays)
  that both models may handle differently.
- A 100%/15.5% split on *this specific* test does not necessarily
  generalize to the models' overall production false-positive rate —
  `tier2_cnn_v3`'s real calibration KPIs (Brier 0.0192, ECE 0.0054, ROC
  AUC 0.9954 on 18,000 real held-out cutouts) remain genuinely strong on
  realistic data.
- A plausible (not confirmed) explanation: `tier2_cnn_v3`'s training data
  is recent real ZTF alerts (2026-06-22 to 2026-07-09, 18 nights), while
  `benchmark_cnn_v1`'s original training set may have included more bogus
  examples resembling extreme point-source artifacts. This has not been
  independently verified against either model's actual training label
  distribution — flagged as a real, testable follow-up, not asserted as
  fact.

## Why this evidence is NOT mechanically substituted into the promotion gate

`src/promotion_report.py`'s `false_discovery_report` check has a default
`max_false_discovery_rate` of 0.05 (5%), calibrated against Gate Z4's
*original* real-archived-data test. Feeding this new evidence directly
into that same gate would fail it for **both** models (15.5% and 100% both
exceed 5%) — but that threshold was never calibrated against this much
harder, deliberately adversarial test, and changing what a scientific
threshold is being measured against without explicit operator judgment is
exactly the kind of unilateral change
`docs/astrometrics_coding_agents_master_guide.md`'s non-negotiable rule 10
forbids ("Do not change scientific thresholds, labels, or splits without
an audit trail"). This file is that audit trail. The existing
`false_discovery_report` (Gate Z4, real data, 0.0% rate) remains the
officially gating evidence, unchanged. This new evidence is additional and
disclosed, not substituted.

## Real output files

`Logs/reports/cnn_false_discovery_benchmark_v1.json`,
`Logs/reports/cnn_false_discovery_tier2_cnn_v3.json` (local/gitignored,
full per-artifact records). `Skills/evaluate_cnn_false_discovery.py`
(committed, reproducible).

## Operator decision needed

1. Does this change your assessment of `tier2_cnn_v3` for promotion?
2. Should `max_false_discovery_rate` be reconsidered, or should this
   adversarial test get its own, separately-calibrated threshold rather
   than reusing the Gate Z4 one?
3. Is this worth investigating further (e.g. checking `tier2_cnn_v3`'s
   real training label composition for artifact diversity) before a
   promotion decision, or acceptable as a known, disclosed limitation?
