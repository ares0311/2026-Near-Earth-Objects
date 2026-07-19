# Phase 1 Detection Hardening Evidence — 2026-07-19

Scope: the two detection/scoring gaps named in the operator-directed Phase 1
roadmap. No external submission, public alert, or impact-probability claim was
made. The replay used existing local ZTF DR24 products and performed no new
download.

## Gap 1 — pixel-extraction real/bogus evidence

The pixel extractor already computes a Pearson correlation between each source
cutout and the exposure's real difference-image PSF kernel. The converter was
discarding that signal, so review packets contained neither a calibrated
real/bogus probability nor the available source-native shape evidence.

The fix preserves each value as `Observation.psf_shape_correlation`, aggregates
the measured values into `CandidateFeatures.psf_quality_score`, and keeps
`real_bogus_score` as `None`. A raw correlation is not a calibrated probability
and must not be relabeled as one. The existing `tier2_cnn_v4` is not a valid
fallback: it requires three 63x63 science/reference/difference cutouts, while
this path has a difference image, mask, and PSF product but does not create that
triplet.

Adversarial review now fails closed unless every observation has a PSF-shape
measurement and every correlation is at least 0.5. Passing this source-native
gate produces `WARNING`, not `PASS`, and therefore still requires operator
review. The 0.5 discriminator is independently exercised by the existing
matching-Gaussian positive control (>0.95) and single-pixel-artifact negative
control (<0.5) in `tests/test_ztf_dr24_bounded_ingest.py`.

Local inventory supporting the decision: 3,584 sources across 25 existing
pixel-pilot checkpoints; 777 had finite PSF correlations and 2,807 were
unscored because a full PSF-sized cutout was unavailable. The maximum finite
correlation was 0.260. The 30 observations in the ten existing review packets
contained nine finite correlations; the maximum was 0.187. These data do not
support fitting a probability calibrator. Such calibration would require
independently labeled real/artifact examples, grouped splits, and a persisted,
versioned calibrator.

## Gap 2 — arc quality versus orbit-fit success

The previous `_gauss_iod()` was an invalid scalar approximation and
`_differential_correction()` recorded a hard-coded 0.5-arcsec residual rather
than measuring the fit. It failed even on an independently generated bound
circular-orbit control.

`fit_orbit()` now performs deterministic multi-start bounded nonlinear
least-squares fitting of a heliocentric Cartesian state, using Astropy's bundled
offline Earth ephemeris and two-body propagation. It accepts only bound
elliptic solutions with measured RMS <= 5 arcsec. An independent analytic
1.5-AU circular-orbit control over three epochs is recovered with RMS < 1
arcsec. Invalid geometry, failed optimization, singular states, nonphysical
solutions, and high residuals all fail closed in tests.

Arc sufficiency and fit success are now separate durable fields:

- `HazardAssessment.arc_quality_tier`: project tier 1-4 derived from temporal
  coverage whether or not a solution exists;
- `HazardAssessment.orbit_fit_status`: `not_attempted`,
  `insufficient_observations`, `no_solution`, or `fitted`;
- `OrbitalElements.quality_code`: populated only for an accepted fit.

The arc tier is a project sufficiency scale, not the MPC `U` uncertainty
parameter. A three-observation, approximately seven-day arc can correctly be
tier 2 while retaining `orbital_elements: null` and `orbit_fit_status:
no_solution`.

## Real-data replay

The three original field-1 checkpoints were converted into a new ignored output
directory so the prior evidence was not overwritten:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/convert_pixel_extraction_to_observations.py --pilot-checkpoint Logs/pipeline_runs/ztf_dr24_bounded_ingest/15fc0fb77826/pixel_extraction_pilot.json --manifest Logs/pipeline_runs/ztf_dr24_bounded_ingest/15fc0fb77826/motion_product_manifest.json --night 20180802 --out-dir Logs/pipeline_runs/phase1_detection_hardening_field1
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/convert_pixel_extraction_to_observations.py --pilot-checkpoint Logs/pipeline_runs/ztf_dr24_bounded_ingest/a8a10c54beff/pixel_extraction_pilot.json --manifest Logs/pipeline_runs/ztf_dr24_bounded_ingest/a8a10c54beff/motion_product_manifest.json --night 20180806 --out-dir Logs/pipeline_runs/phase1_detection_hardening_field1
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/convert_pixel_extraction_to_observations.py --pilot-checkpoint Logs/pipeline_runs/ztf_dr24_bounded_ingest/3d28311a660d/pixel_extraction_pilot.json --manifest Logs/pipeline_runs/ztf_dr24_bounded_ingest/3d28311a660d/motion_product_manifest.json --night 20180809 --out-dir Logs/pipeline_runs/phase1_detection_hardening_field1
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/run_pixel_extraction_positive_control.py --nights 20180802 20180806 20180809 --checkpoint-dir Logs/pipeline_runs/phase1_detection_hardening_field1 --min-observations 3 --build-review-packets --out Logs/pipeline_runs/phase1_detection_hardening_field1/report.json --review-packet-out Logs/pipeline_runs/phase1_detection_hardening_field1/review_packets.json
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/adversarial_review.py Logs/pipeline_runs/phase1_detection_hardening_field1/review_packets.json --offline
```

Result: 471 real observations linked into the same two three-night tracklets.
Both remain `REJECT`, which is the evidence-consistent result:

| Packet | PSF mean | PSF coverage | Arc tier | Fit status | Orbital elements |
|---|---:|---:|---:|---|---|
| `57138064-a388-4cde-b039-5c27426f8857` | 0.0680 | 1/3 | 2 | `no_solution` | `null` |
| `e70027a7-7284-49c8-bf5b-b12284beab29` | 0.0116 | 2/3 | 2 | `no_solution` | `null` |

The real/bogus challenge now states incomplete PSF coverage explicitly rather
than merely reporting a missing score. The orbit challenge reports a tier-2
arc and `no_solution` rather than presenting `quality_code: null` as an
ambiguous result. Both packets also retain approximately 0.99 artifact
posterior probability. No candidate advanced.

## Verification

Targeted behavioral suite:

```text
627 passed, 2 warnings
```

Orbit-only coverage after negative controls:

```text
87 passed; src/orbit.py 399 statements, 0 missed, 100%
```

Canonical repository workflow:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-sync --python 3.14 python Skills/verify_reliability_controls.py
```

Result on the working tree before this evidence file was added: all six stages
passed; 2,067 tests passed, 2 deselected, total `src/` coverage 100%. A final
clean-tree verification record is still required after commit before claiming
REL-03 `VERIFIED` status.

## Phase 1 disposition

Both named gaps meet the roadmap's technical exit criteria. The implementation
is complete and behaviorally tested; the real replay preserves the honest null
scientific result. Per the roadmap's explicit operator gate, Phase 2 remains
blocked until the operator closes Phase 1.
