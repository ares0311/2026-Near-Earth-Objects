# Phase 2 Time-Aware Known-Object Eligibility — 2026-07-19

## Root cause

`Skills/adversarial_review.py` previously queried a current MPC region and
treated the number of catalog objects inside a 0.5-degree field as if it were
an association. The query had no historical epoch and could leak future
catalog state into replay. Worse, `src.fetch.count_known_objects_in_field()`
turns provider failure into zero, so an unavailable provider could produce a
passing challenge.

The deeper pipeline audit found that `src/detect.py`'s nominal ephemeris loader
is an explicit Ceres placeholder that always returns an empty list, and
`src.known_object_exclusion.known_as_of()` was not consumed anywhere outside
its tests. The source-native pixel path bypasses `detect()` in any case. Thus
the review-stage field-density query was not redundant defense; it was the
only live catalog challenge, and it did not establish identity.

## Implementation

The current Astroquery documentation specifies
[`Skybot.cone_search`](https://github.com/astropy/astroquery/blob/main/docs/imcce/imcce.rst)
for a solar-system cone search at an explicit `SkyCoord`, radius, `Time`, and
observer location. The adversarial challenge now:

1. queries a 10-arcsecond SkyBoT cone at every measured RA/Dec and JD;
2. obtains the earliest published MPC observation for each positional match;
3. calls the shared `known_at_observation_jd()` no-future-leakage predicate;
4. rejects an object only when its first published observation is on or before
   the matched measurement;
5. records a later-discovered positional match as `WARNING` retrospective
   context, not a future-catalog rejection;
6. records policy version, observer code, radius, per-observation association
   evidence, and a deterministic SHA-256 of the policy inputs;
7. returns `FAIL` on provider, schema, identity, or first-observation failure.

Offline review without explicitly injected cached association providers now
also fails this required eligibility challenge. It cannot report a clean
candidate as `SURVIVE` merely because the network stage was omitted.

No AI judgment is used.

## Behavioral verification

Ninety-three focused tests pass across adversarial review and the shared
time-aware exclusion module. Independent oracles cover:

- no positional match -> `PASS`;
- provider exception -> `FAIL` with error type and message;
- first observation exactly equal to candidate epoch -> known then -> `FAIL`;
- first observation after the candidate epoch -> no future leakage ->
  `WARNING`;
- non-finite first-observation evidence -> `FAIL`;
- outside-radius object -> ignored;
- deterministic policy digest;
- documented SkyBoT `Number`/`Name`/`RA`/`DEC` schema normalization;
- numbered-designation zero stripping and name fallback;
- offline review without cached required evidence -> `REJECT` / exit 1.

The original two-candidate Phase 1 packet replay remains `REJECT=2`; each now
also exposes the missing offline association evidence as a fifth explicit
failure rather than silently omitting the stage.

Canonical working-tree verification passed all six mandatory controls:
directive parity, silent-exception and incomplete-implementation gates, ruff,
mypy over all 18 source modules, and 2,082 tests with 2 deselected and 100.00%
coverage across all 5,545 `src` statements. The workflow is rerun after commit
to bind REL-05 freshness to the clean immutable state.

## Live provider result

Two bounded live probes reached `ssp.imcce.fr` on 2026-07-19:

1. the candidate-shaped 10-arcsecond query at RA 180 / Dec +10 / JD 2460000.5;
2. Astroquery's own documented five-arcminute example at RA 0 / Dec 0 /
   2019-05-29 21:42.

Both returned HTTP 500 from SkyBoT. The first sandboxed attempt had failed at
DNS as expected; the approved unsandboxed calls reached the service, proving
this is current external provider behavior rather than local network denial.
No third identical retry was made. The new challenge correctly converts this
condition into a visible disqualifying failure; it cannot be live-positive-
controlled until the provider recovers or a separately verified epoch-cone
source is selected.

No data download, external submission, alert, discovery claim, or impact claim
occurred.

## Status and exact next work

The safety direction is implemented and offline-tested, but live provider
success is **not verified**. Phase 2 remains open and Hunter PROD is not
claimed. Next work is:

1. rerun one bounded documented query after SkyBoT service recovery, then a
   known-object positive control with verified designation/epoch;
2. persist successful association evidence for restart-safe offline review;
3. harden ATLAS confirmation so arbitrary returned rows do not count as
   confirmation without time, position, and quality checks;
4. rerun the original review packets, canonical verification, and CI.
