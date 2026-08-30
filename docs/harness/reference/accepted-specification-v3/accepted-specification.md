# NEO Harness Specification v3

**Role:** NEO harness specification author  
**Controlling checkpoint:** `/Users/Rome/Documents/Codex/2026-08-24/files-pasted-by-the-user-act-3/outputs/NEO-harness-specification-initiation-checkpoint-v1`  
**Checkpoint-manifest SHA-256:** `3f37a7dc6ce5afd95aca7dcbabf1b9ae2bfad0fa539aa7247e071e759a76771c`  
**Assignment SHA-256:** `1dd6347278a83981eb7cd27c19751191f9aa4ace7e9e887fabbe3b19dca7c6e7`  
**Revision status:** `REVISED_AWAITING_INDEPENDENT_REVALIDATION`
**Revision basis:** exact Revision 2 independent verdict `REVISIONS_REQUIRED`; only `CE-R2-SCOPE-10.1-NORMATIVE-EXPANSION` and `CE-REQ044-SECTION13-HANDOFF-CONTRADICTION` are remediated; the Revision 1 G0 verdict/binding and IR-016/G10 lifecycle fixes are retained

## 1. Purpose and authority

This document specifies a bounded, reproducible evaluation harness for comparing NEO-search method branches against the exact accepted NEO-001 Revision 10, NEO-002 Revision 20, and NEO-003 Revision 1 evidence. It is a specification, not an implementation or a scientific result.

The authority order is:

1. live independently sealed evidence and final checkpoints;
2. the controlling initiation checkpoint and its exact pins;
3. older initiation or continuity material;
4. chat.

The harness shall never weaken an accepted information ceiling, uncertainty statement, evidence grade, transfer limit, regime boundary, or claim boundary. A package-validation verdict applies only to its exact frozen package and review contract; it is not evidence of scientific effectiveness or operational fitness.

## 2. Objectives

The harness shall:

1. verify immutable benchmark, dependency, configuration, environment, and result identities before evaluation;
2. evaluate point-like pixel detection, trailed pixel detection, catalog association, single-night tracklet formation, multi-night and cross-survey linking, historical recovery/precovery, and initial-orbit/uncertainty handling as separate branches;
3. compare defensible classical, statistical, optimization, ML/AI, and hybrid candidates only where the input contract supports them;
4. measure stage-wise and end-to-end behavior using explicit denominators, uncertainty intervals, calibration diagnostics, resource accounting, and multidimensional selection functions;
5. preserve missing, ambiguous, censored, and abstained states instead of forcing binary labels or associations;
6. enforce immutable historical cutoffs and strict no-future-leakage partitions;
7. make every evaluation reproducible and auditable from frozen inputs, declared configuration, retained intermediate evidence, and a complete output manifest;
8. produce only evidence-bounded comparison dispositions.

## 3. Explicitly excluded objectives

The harness shall not:

- implement or select a production NEO-search architecture;
- run a production, live, or unbounded scientific search;
- call a candidate a discovery or a precovery solely because it improves an orbit fit;
- infer archive completeness from nominal depth, file count, endpoint availability, simulation, or literature headline metrics;
- calculate, classify, publish, or communicate an impact probability or risk disposition;
- prepare or make a scientific or official submission, public alert, or authority-facing notification;
- contact MPC, JPL/CNEOS, ESA NEOCC, NASA, an observatory, an archive operator, or any other authority;
- independently accept this specification or any later scientific result;
- treat current or planned Rubin/NEO Surveyor capabilities as accepted historical or current data exposure unless a later frozen intake separately establishes them;
- use credentials, create provider state, or retrieve large datasets without a later explicit authorization and budget gate.

## 4. Governing information ceilings

### 4.1 Processing-level ceiling

Each input shall carry one of these processing levels: `RAW_PIXEL`, `CALIBRATED_PIXEL`, `DIFFERENCE_PIXEL`, `EXTRACTED_DETECTION`, `ALERT`, `TRACKLET`, `LINKED_OBJECT`, `ORBIT`, `KNOWN_OBJECT_CONDITIONED`, or `COADD_AGGREGATE`.

- Pixels may support independent detection only when required timing, observer, WCS, calibration, mask, PSF, and uncertainty companions are verified.
- Extracted detections, alerts, and tracklets are censored by upstream extraction and filtering. A missing row is `UNKNOWN_CENSORED`, not a negative physical observation.
- Linked-object, orbit, risk, ephemeris, forced-photometry, known-object, and coadd/mean products are validation or characterization inputs only unless a more limited role is explicitly proven.
- No downstream method can claim recovery below an upstream catalog or alert-record ceiling.

### 4.2 Temporal and association ceilings

- Single-night formation and multi-night/cross-survey linking shall use different corpora, metrics, configurations, and dispositions.
- A single position or trail is not a unique orbit. A short arc shall retain range/range-rate ambiguity and multiple compatible orbit families where applicable.
- Cross-survey linking shall not be treated as merely a longer time window. It requires observer-state, time-scale, reference-frame, astrometric-bias, duplication, filter/photometry, and upstream-censorship contracts.

### 4.3 Historical ceiling

Targeted precovery and blind archival discovery are different tasks. Historical evaluation shall freeze all orbit, designation, observation, prior, label, simulator, archive, and processing state at a declared cutoff. Later truth shall remain cryptographically and logically inaccessible until method output is frozen.

### 4.4 Evidence ceiling

Literature performance establishes only demonstrated feasibility in the cited context. It shall not supply a harness threshold for a different survey, archive, cadence, rate, background, morphology, population, or processing branch. Planned capability, simulation, package conformance, and validation evidence shall remain distinguishable from current empirical effectiveness.

## 5. Required harness outcome vocabulary

The only branch-level evaluation dispositions are:

- `NOT_EVALUABLE_INPUT_CONTRACT`: required identity, schema, ancillary, cutoff, label, or uncertainty evidence is absent or invalid;
- `EVALUATED_BOUNDED`: the branch ran on its declared frozen corpus and all results are limited to that corpus;
- `COMPARISON_CRITERIA_MET`: pre-registered bounded comparison criteria were met, with no broader claim;
- `COMPARISON_CRITERIA_NOT_MET`: one or more pre-registered bounded criteria were not met;
- `INCONCLUSIVE_UNCERTAINTY_OR_POWER`: the evidence cannot resolve the comparison;
- `INVALID_LEAKAGE_OR_INTEGRITY`: leakage, identity drift, incomplete denominators, or integrity failure invalidated the run;
- `STOPPED_RESOURCE_OR_ACCESS_LIMIT`: an authorized resource or access boundary stopped the run.

The words `DISCOVERY`, `ACCEPTED`, `SAFE`, `IMPACT`, and `OPERATIONAL` shall not be emitted as branch dispositions.

## 6. Data contracts

### 6.1 Common immutable input envelope

Every input corpus shall provide:

- absolute source root and externally pinned manifest/digest identity;
- complete no-follow `lstat` inventory covering path, type, POSIX mode, `lstat` size, regular-file SHA-256, and symlink target;
- provider, product identifier, release/archive version, processing level, acquisition interval, and evidence cutoff;
- usage role: `SEARCH_INPUT`, `CALIBRATION_ONLY`, `LABEL_SOURCE`, `LATER_TRUTH_HELD_BACK`, or `VALIDATION_ONLY`;
- schema/version and strict duplicate-key-clean JSON/JSONL where applicable;
- byte-order, character encoding, units, time scale, coordinate/reference frame, observer identity/state, and null/missing-value semantics;
- acquisition, transformation, normalization, and split provenance;
- redistribution/access constraints and a statement that no credential or state creation is required for the bounded run.

Symlinks and other non-regular entries are not silently followed. An undeclared entry or any identity change is a hard stop.

### 6.2 Pixel input contract

A pixel branch is evaluable only when the exact visit image and all required companions are coupled by identity. The minimum fields are exposure start/midtime convention and duration, observer/site, WCS and frame, pixel scale, bandpass, gain/calibration provenance, PSF or a defensible estimator, variance/uncertainty, masks/data-quality planes, saturation and bad-pixel handling, background/subtraction branch, chip/edge coverage, and archive/pipeline version.

Point and trail branches shall be separate. Trail inputs additionally require a declared representation for length, orientation, curvature, surface brightness/SNR per footprint, endpoint/centroid uncertainty, sampling, star-crossing context, and cosmic-ray/satellite/artifact confounders.

### 6.3 Catalog, alert, and tracklet contract

Each detection shall carry immutable record identity, exposure/visit identity, precise time and convention, observer, coordinates and frame, covariance or explicitly justified weight model, photometry/filter where present, upstream flags, extraction/filter version, duplicate lineage, and the processing ceiling. A catalog absence is never encoded as a physical non-detection.

Provider-formed tracklets shall remain distinguishable from harness-formed tracklets. Alternative pairings and unpaired detections shall be retained when available. Known-object services and linked-object products may validate only after the candidate output is frozen.

### 6.4 Historical cutoff packet

A historical corpus is not evaluable until it contains all ten accepted control-packet elements:

1. exact checksummed products and ancillaries;
2. complete POSIX/file-type inventory;
3. acquisition times and observer codes/states;
4. pipeline and release versions;
5. checksummed cutoff-time known-object and observation state;
6. explicit forbidden-future set;
7. per-stage denominators and counts;
8. frozen method output before truth access;
9. separately frozen later-truth partition opened only after output freeze;
10. semantic no-future-information validation.

The nine positive controls proposed by NEO-002 remain `CANDIDATE_ONLY`; none shall be represented as reconstructable until this packet is complete.

### 6.5 Missing-data behavior

Every field shall declare one of `REQUIRED_HARD_STOP`, `OPTIONAL_WITH_MISSINGNESS_INDICATOR`, `BRANCH_BLOCKING`, `VALIDATION_ONLY`, or `NOT_APPLICABLE`. The harness shall not impute observer state, time convention, covariance, mask state, historical identity state, archive presence, or future data availability. Missing critical data causes `NOT_EVALUABLE_INPUT_CONTRACT`; upstream-censored observations remain `UNKNOWN_CENSORED`.

## 7. Label and split contracts

Allowed label classes are `SIMULATED_TRUTH`, `CUTOFF_KNOWN_POSITIVE`, `LATER_TRUTH_HELD_BACK`, `INDEPENDENT_REMEASUREMENT`, `ARTIFACT_CONFIRMED`, `AMBIGUOUS`, and `UNKNOWN`. Every label shall record creator, source bytes, creation time, information cutoff, method, uncertainty, and allowed roles.

The following are mandatory:

- physical-object-disjoint and time-block-disjoint train/tune/test splits;
- night/exposure-disjoint splits where pixel or artifact reuse could leak the answer;
- survey/detector-held-out evaluations for cross-domain claims;
- no detections, cutouts, linked records, later designations, later orbits, current ITF composition, or outcome knowledge shared across a historical cutoff;
- synthetic injections generated without test-image, target-PSF, target-background, or known-object-cutout shortcuts;
- versioned population priors and simulators, with rare/out-of-distribution strata retained;
- ambiguous and unmatched states preserved; no forced association or forced negative label;
- later truth inaccessible to training, tuning, threshold selection, error analysis, or candidate triage until frozen evaluation output exists.

Any leakage finding invalidates the entire affected branch, not only the contaminated records.

## 8. Method branches and defensible baselines

No method is selected for production. A candidate may be evaluated only against the required baseline on identical inputs, splits, opportunity masks, and declared resource accounting.

### 8.1 Point-like pixel detection

- Required baseline: PSF-aware extraction/difference-image thresholding and a variance-weighted PSF likelihood or matched filter with calibrated multiple-testing control.
- Candidate comparisons: bounded shift-and-stack, archive-specific learned real/bogus ranking, and hybrids that retain all pre-classifier candidates and scores.
- Hard limits: correlated subtraction noise, spatial PSF variation, masking, saturation, crowding, proposal-stage misses, and morphology censorship.

### 8.2 Trailed pixel detection

- Required baseline: line/segment or trail-template detection with explicit null/artifact handling and a pixel-domain astrometric refit.
- Candidate comparisons: variance-weighted trail likelihood, coarse-to-fine optimization over bounded trail parameters, archive-specific learned localization, and proposal-plus-learned-veto hybrids.
- Hard limits: look-elsewhere burden, fragmentation, curvature/model mismatch, low surface brightness, star crossings, satellite/cosmic-ray confusion, and endpoint uncertainty propagation.

### 8.3 Catalog association and known-object discrimination

- Required baseline: topocentric ephemeris propagation with time/sky gating and a covariance-aware likelihood retaining multiple hypotheses.
- Candidate comparisons: global assignment and physically gated learned ranking.
- Hard limits: missing/non-Gaussian covariance, timing/site errors, current-catalog leakage, forced matching, and upstream catalog censorship. Unmatched does not mean novel.

### 8.4 Single-night tracklet formation

- Required baseline: constant-velocity pair-and-extend plus weighted robust linear/quadratic fitting, reported separately for two-detection and three-or-more-detection strata.
- Candidate comparisons: trajectory voting/set packing, learned edge ranking, and indexed robust-fit hybrids.
- Hard limits: false-density combinatorics, acceleration, duplicate detections, missing epochs, forced exclusivity, and early pruning.

### 8.5 Multi-night and cross-survey linking

- Required baseline: MOPS-style candidate linking with preliminary/differential orbit filtering and a multiple-hypothesis or statistical-ranging comparison.
- Candidate comparisons: HelioLinC, THOR, Link2/graph-cycle structures, learned proposal ranking with a physics-only fallback, and staged hybrids.
- Hard limits: proposal/grid coverage, cadence and geometry, multimodal collapse, priors, rare-orbit suppression, false density, survey offsets, duplicates, and orbit-filter population sculpting.

### 8.6 Historical recovery and precovery

- Required targeted baseline: cutoff-era orbit/posterior propagation to exposure footprints followed by blinded pixel remeasurement.
- Required blind complement, where the corpus supports it: bounded pixel/catalog search that receives no current identity or orbit.
- Candidate comparisons: posterior ranking, blind digital tracking, archive-specific learned triage, and hybrids.
- Hard limits: incomplete opportunity, posterior-tail misses, confirmation/survivorship bias, mutable cutoff state, and orbit-fit improvement without independent identity evidence.

### 8.7 Initial orbit and uncertainty handling

- Required baseline: admissible-region/statistical or systematic ranging with mode-wise weighted differential correction and residual/outlier audit.
- Candidate comparisons: classical preliminary solutions, global/multistart optimization, and learned proposals only as isolated accelerators.
- Hard limits: multiple roots, singular geometry, prior/weight sensitivity, incomplete tail sampling, mode pruning, and nonphysical or miscalibrated solutions.
- This branch shall never emit an impact disposition.

## 9. Metrics and uncertainty reporting

### 9.1 Common metrics

Every branch shall report:

- exact opportunity denominator and exclusion reasons;
- stage-wise input, candidate, retained, rejected, ambiguous, and abstained counts;
- recovery/recall with uncertainty; precision or false-discovery proportion where truth supports it;
- false candidates per exposure, area, night, detection, or hypothesis as appropriate;
- calibration curves and a declared proper scoring rule when scores are probabilistic;
- performance stratified by product, survey, detector, night, and all applicable selection-function axes;
- repeatability across frozen reruns;
- wall time, CPU time, peak memory, GPU model/time/memory, storage/read volume, candidate fan-out, and failure/retry counts.

Intervals shall respect clustering by object/night/survey rather than treating correlated detections as independent. The interval/resampling method, confidence/credible level, multiplicity handling, and zero-denominator behavior shall be pre-registered. Point estimates without denominators and intervals are nonconforming.

### 9.2 Branch-specific metrics

- Pixel point/trail: injection/recovery by flux/SNR or surface brightness, apparent rate, trail length/angle/curvature, PSF/seeing, background, crowding, mask/edge/chip state, sampling, and subtraction branch; astrometric/photometric residuals; proposal and veto recall.
- Association: correct, incorrect, ambiguous, and unmatched fractions; candidate-set coverage; calibration versus combined measurement/ephemeris uncertainty and density.
- Single-night: tracklet efficiency/purity, duplicate/conflict rate, motion-fit residuals, candidate fan-out, and recall before and after every prune.
- Multi-night/cross-survey: linkage efficiency/purity, orbit-family coverage, hypothesis growth, duplicate/conflict rate, residuals by survey/station/epoch, and rare-regime retention.
- Historical: searchable-footprint opportunity, image usability, predicted-region coverage, pixel/catalog recovery, vetting retention, astrometric acceptance, independent identity evidence, and orbit change, each as a separate stage.
- Orbit/uncertainty: mode count/retention, posterior or admissible-region coverage, withheld-observation predictive score, calibration/coverage curves, residuals, convergence, prior sensitivity, and tail diagnostics.

### 9.3 Selection-function axes

Empirical completeness shall be reported jointly across product identity and processing branch; exposure/night/detector/survey/archive version; flux/SNR or surface brightness; point/trail morphology; rate/acceleration/angle/length/curvature; seeing/PSF/background/crowding/masks/edge/chip state; cadence/multiplicity/arc/geometry/observer diversity; upstream filter state; valid cutoff-known versus cutoff-unknown status; population/orbit regime; ambiguity; and compute. A one-dimensional magnitude curve or literature headline is insufficient.

## 10. Regime-specific bounded acceptance criteria

These criteria govern only whether a frozen benchmark comparison is valid. They are not scientific or operational acceptance.

### 10.1 Common criteria

A branch may receive `COMPARISON_CRITERIA_MET` only if:

1. every identity, manifest, schema, role, and cutoff gate passes;
2. the baseline and candidate use identical frozen opportunity and truth partitions;
3. all pre-registered metrics, intervals, selection strata, resource ledgers, and stage counts are present;
4. no leakage, undeclared entry, hidden data exclusion, post-outcome threshold change, or missing denominator is found;
5. matched baseline/candidate runs complete under the same declared resource policy;
6. every unresolved dependency affecting that branch is closed by frozen evidence or the branch is not evaluated;
7. the numerical comparison thresholds and minimum statistical power are frozen before outcome access.

The numerical thresholds and power requirements are incomplete in v3 and are recorded as `IR-014`; therefore no implementation may claim this disposition yet.

### 10.2 Additional criteria by branch

- Point pixels: pre-classifier proposal recall and veto losses are measurable; pixel ancillaries pass; recovery and false density are stratified over the declared point-source selection axes.
- Trails: endpoint/centroid uncertainty propagates downstream; the hypothesis-volume correction is declared; real/synthetic and survey-held-out results remain separate.
- Association: covariance/time/observer contracts pass; ambiguous and unmatched outcomes are retained; current catalogs are absent from historical tests.
- Single-night: two-detection and three-or-more-detection strata are separate; every prune has measured recall; no tracklet is represented as a unique orbit.
- Multi-night/cross-survey: per-survey timing/frame/bias/duplicate models pass; physics-only fallback coverage is measured; rare-regime and multimodal outcomes are retained.
- Historical: the ten-part cutoff packet passes; blind discovery and targeted precovery remain separate; later truth opens only after output freeze; a precovery identity requires independent evidence beyond orbit-fit improvement.
- Orbit/uncertainty: multiple modes and tails are evaluated; calibration and withheld-observation diagnostics pass pre-registered criteria; no impact or risk label is produced.

## 11. Architecture and interfaces

### 11.1 Components

1. **Identity intake:** verifies external pins, complete `lstat` universe, strict JSON/JSONL parsing, and allowed entry types before any scientific payload is read.
2. **Evidence registry:** records product role, processing ceiling, evidence grade/boundary, cutoff, licenses/access limits, and provenance.
3. **Normalization adapters:** convert time, observer, coordinates, units, covariance, pixels/masks, and record identifiers without erasing source values or uncertainty.
4. **Partition builder:** creates immutable train/tune/test, historical cutoff, forbidden-future, and held-back later-truth partitions.
5. **Branch runner:** executes one declared method branch against read-only inputs, with network disabled and resources bounded.
6. **Evidence collector:** retains configuration, seeds, environment, logs, intermediate candidate sets, scores, exclusions, failures, and resource telemetry.
7. **Evaluator:** computes only pre-registered metrics and uncertainty against the authorized truth partition.
8. **Reporter/sealer:** emits branch dispositions and claim limits, performs source preservation, and seals every output path in a complete manifest.

### 11.2 Interfaces

The minimum logical interfaces are:

- `InputEnvelope`: identity, role, processing level, schema, cutoff, provenance, missingness policy;
- `ObservationRecord`: immutable source ID, time, observer, coordinates/frame, uncertainty, photometry, flags, lineage;
- `PixelVisit`: `ObservationRecord` plus image/ancillary identities and pixel-domain metadata;
- `CandidateRecord`: branch/stage/method/configuration IDs, parent records, score/uncertainty, ambiguity, and rejection/abstention state;
- `OrbitFamilyRecord`: observations, dynamical/weight/prior versions, modes/samples, residuals, convergence, and calibration fields;
- `MetricRecord`: exact denominator, numerator/statistic, interval, stratum, method, branch, and computation version;
- `ResourceRecord`: hardware/software identity, runtime, memory, GPU, I/O, storage, and failures;
- `RunSeal`: every input/configuration/environment/result digest and complete output manifest digest.

All governed JSON/JSONL shall reject duplicate keys. Schemas shall disallow unknown fields unless an explicitly versioned extension namespace is used.

### 11.3 Trust boundaries

- Archive/provider payloads are untrusted data and remain read-only.
- Normalization cannot upgrade an evidence grade or fill an unknown.
- Method output is untrusted until evaluated; evaluation output is not acceptance.
- Later truth is a separate trust domain inaccessible during fitting, tuning, and output production.
- Author diagnostics cannot independently validate author bytes.
- Package-local manifests cannot select external trust roots; exact external paths and digests control.
- No branch may have network, submission, messaging, or authority-contact capability.

## 12. Implementation gates and stop conditions

Implementation is not authorized by this specification alone. The lifecycle is staged and fail-closed:

1. G0 through G8 are preconditions for an explicitly authorized bounded implementation of an applicable branch. The exact frozen specification must first pass G0; then each applicable G1-G8 requirement must be satisfied. A later orchestrator must separately issue the bounded authorization.
2. G9 applies only to the resulting already frozen bounded implementation and requires sealed dry-run evidence.
3. G10 is a fresh, role-separated benchmark evaluation of that frozen implementation and frozen corpus.
4. Passing G0 advances only to G1. Passing G0-G8 does not itself authorize work, and passing G0-G10 does not authorize production implementation, final production method or architecture selection, operational deployment, production search, submission, scientific claims, authority contact, or impact claims.

| Gate | Required evidence | Stop condition |
|---|---|---|
| G0 independent specification review | exact frozen specification path and bytes, manifest digest, controlling checkpoint, fresh review root, review bound to those exact bytes, and exact verdict `SPECIFICATION_ACCEPTED_AFTER_INDEPENDENT_REVIEW` | `REVISIONS_REQUIRED`; missing or unrecognized verdict; changed specification identity; review bound to different bytes, manifest, or checkpoint; or any verdict other than the exact accepting literal |
| G1 dependency closure map | every OQ and IR mapped to closed evidence, an explicitly blocked branch/activity/comparison/disposition, or an approved nonblocking limitation; `IR-016` remains intentionally deferred to post-G10 under Section 17 | assertion-only closure, especially `OQ-16`, or any IR-001 through IR-015 treated as globally nonblocking outside its mapped scope |
| G2 corpus and access authorization | bounded corpus identities, size estimate, access terms, no credentials/state creation, approved download/storage budget | missing pin, large/credentialed/state-creating access, unapproved live request |
| G3 data/schema conformance | file-level ancillaries, time/observer/frame/covariance contracts, complete inventories | ambiguous critical units, missing ancillaries, undeclared entries or non-regular types |
| G4 historical cutoff | complete ten-part packet and isolated later truth | mutable or incomplete cutoff, future leakage, current identity used historically |
| G5 labels and splits | provenance-complete labels and object/time/night/survey-safe splits | leakage, mislabeled censored absence, unresolved ambiguity forced to binary |
| G6 baseline definitions | branch baselines, configurations, search bounds, intermediate-retention requirements | candidate evaluated without defensible matched baseline |
| G7 metrics and decision rule | pre-registered metrics, intervals, power, thresholds, multiplicity, failure policy | threshold chosen or altered after outcome access |
| G8 resource envelope | exact hardware/software/container, CPU/GPU/memory/runtime/storage/download caps | cap exceeded or telemetry incomplete |
| G9 bounded dry run | an already frozen, explicitly authorized bounded implementation; deterministic/repeatable fixture results; and sealed dry-run evidence | implementation is absent or unfrozen, authorization or seal is missing, drift, nondeterminism beyond tolerance, or missing logs/denominators |
| G10 independent benchmark evaluation | fresh, role-separated evaluation of the exact frozen bounded implementation and frozen corpus, with sealed evaluator identity and results | author self-evaluation, reused/non-independent evaluation, identity mismatch, unsealed evidence, or any source mutation |

At any gate, identity mismatch, duplicate JSON key, unsafe path, unexpected symlink/special entry, source mutation, leakage, unbounded resource growth, unapproved credentials, or externally state-creating behavior requires immediate stop and a non-accepting report to the orchestrator.

For G0 specifically, `REVISIONS_REQUIRED`, a missing verdict, an unrecognized verdict, an identity mismatch, or a review bound to any bytes other than the exact frozen specification fails the gate and prohibits bounded implementation. The exact accepting verdict is necessary but not sufficient for any later gate or activity.

## 13. Validation strategy and future independent handoff

Author-side checks may establish internal consistency only.

For an initial specification review, give the reviewer only the frozen specification identity, exact manifest digest, controlling checkpoint, and fresh review root. For remediation revalidation, give the reviewer only the frozen specification identity, exact manifest digest, controlling checkpoint, fresh review root, and exact controlling prior independent-review identity and verdict. For Revision 3 remediation revalidation, the exact controlling prior independent-review identity and verdict are root `/Users/Rome/Documents/Codex/2026-08-24/files-pasted-by-the-user-act-4/outputs/NEO-harness-specification-v2-independent-revalidation`, complete-review-manifest SHA-256 `b60cf61a1cd24fb3dbb55dd62777b0922c0b64623777290b5a2629815d52aea5`, digest-record SHA-256 `3b58d03e566c0a7886ed6ba490400f35152f576fcdcfac2b0ac0ec034a476e7c`, and verdict `REVISIONS_REQUIRED`.

The reviewer shall independently recompute package identity and coverage, strict parsing, dependency traceability, requirement completeness/status, branch separations, claim boundaries, unresolved-dependency retention, source preservation, and internal contradictions. The reviewer shall not repair the frozen specification, rely on author PASS labels, or inherit author-side attack reasoning. Any changed byte, path, type, mode, or external pin requires a new author revision and fresh review identity.

This author task does not select, contact, instruct, or initiate that reviewer.

## 14. Operational, resource, access, and failure limits

- All evaluation inputs are read-only; all outputs use a fresh root.
- No production-scale data, open-ended archive scan, or live provider polling is permitted.
- No credentials, tokens, Keychain access, interactive login, provider submission, or state creation is permitted.
- Network access is off during method execution and truth isolation.
- Download, storage, CPU/GPU, memory, runtime, and candidate-count limits must be numerically frozen at G2/G8; they are incomplete in v2.
- Workload shards shall be independently sealable and resumable without changing earlier outputs.
- Retries shall be bounded and recorded; partial, timeout, corrupted, quota, schema-drift, or access-denied results remain explicit failures, not missing-success assumptions.
- Any candidate suggesting urgent or unusual behavior remains a harness candidate only. The run stops at its declared evidence boundary and does not trigger contact, submission, impact calculation, or public communication.

## 15. Reproducibility and auditability

Every run shall freeze:

- source and corpus manifests; configuration and threshold bytes; code/implementation identity; dependency lock; container/environment; hardware/driver identity; random seeds; deterministic/nondeterministic flags; split and label manifests; cutoff and forbidden-future manifests; method and stage versions; complete logs and intermediate candidate sets; metric/resource records; output manifest and external digest record.

Reproduction shall start from a clean output root and compare the complete path/type/mode/size/hash/link-target universe. Any allowed nondeterminism requires a pre-registered tolerance and distributional comparison; otherwise byte drift is a failure. No report may suppress failed shards, empty denominators, missing strata, or retries.

## 16. Unresolved dependencies

All 16 accepted NEO-003 open questions remain unresolved and are carried exactly into `evidence/unresolved-dependencies.csv`:

- `OQ-01`: immutable cutoff-era MPC ITF and orbit/designation state;
- `OQ-02`: file-level pixel ancillaries;
- `OQ-03`: per-detection covariance/weighting;
- `OQ-04`: trail astrometric error model;
- `OQ-05`: multidimensional injection/recovery design;
- `OQ-06`: cross-survey/detector ML transfer;
- `OQ-07`: time/observer normalization;
- `OQ-08`: upstream false-detection/candidate denominators;
- `OQ-09`: cross-survey frame offsets and duplicate rules;
- `OQ-10`: searchable historical archive opportunity;
- `OQ-11`: common-workload compute and recall;
- `OQ-12`: cutoff-safe priors;
- `OQ-13`: rare-regime retention;
- `OQ-14`: independent precovery identity evidence;
- `OQ-15`: short-arc uncertainty calibration;
- `OQ-16`: historical NEO-001 provenance-path correction.

`OQ-16` is `UNRESOLVED_HISTORICAL_PROVENANCE_LIMITATION`. Two historical NEO-001 core-input paths omit `NEO-001-revision10-package`; unique accepted bytes match the expected digests inside the accepted root. No frozen source or checkpoint is rewritten, and this specification does not close the gap by assertion. An orchestrator-issued corrected pin/checkpoint is the required closure evidence. The limitation does not block this specification but blocks a claim of complete historical provenance closure.

## 17. Incomplete requirements

`evidence/incomplete-requirements.csv` is controlling for incompleteness. In summary, v2 intentionally leaves unresolved the exact benchmark corpora; file-level pixel and detection schemas; trail-error model; injection design; cutoff-safe labels/priors; time/observer and cross-survey calibration; false-candidate denominators; archive-opportunity accounting; numerical resource budgets; rare-regime stress set; precovery identity procedure; uncertainty-calibration thresholds; numerical branch comparison thresholds/power; live access/licensing plan; and final production method/architecture selection.

`IR-001` through `IR-015` remain `INCOMPLETE`. Each one blocks its mapped branch, activity, comparison, or disposition until the applicable gate is satisfied; none may be silently treated as closed or globally nonblocking.

Honest unavailable evidence remains recorded as an OQ or IR and blocks only its mapped scope; it shall never be represented as completed or used to force an unavailable branch through a gate.

`IR-016` remains `INTENTIONALLY_DEFERRED` and mapped to `post-G10`. It blocks only final production method or architecture selection. It does not block an explicitly authorized bounded implementation after applicable G0-G8 satisfaction, the G9 dry run of the resulting frozen bounded implementation, or the G10 fresh role-separated benchmark evaluation needed to create its completion evidence. No successful G0-G10 sequence authorizes production implementation, final production selection, or operational deployment.

Excluded objectives such as production search, submission, impact assessment, and authority contact are prohibitions, not incomplete requirements.

## 18. Exact accepted dependency identities

| Dependency | Frozen identity |
|---|---|
| NEO-001 Revision 10 package | root `/Users/Rome/Documents/Codex/2026-08-11/referenced-chatgpt-conversation-this-is-an-6/outputs/NEO-001-revision10-remediation/NEO-001-revision10-package`; manifest SHA-256 `98f7fd7884de2ae75629e9e1408a414467410fc904c2ea7b947ba2905ff9fb81` |
| NEO-001 Revision 10 independent review | root `/Users/Rome/Documents/Codex/2026-08-11/referenced-chatgpt-conversation-this-is-an-7/outputs/NEO-001-revision10-independent-revalidation`; manifest SHA-256 `4988ab0d4b381b7d0d02ca2f05783d07bcefdf1338c3ceacd01efb05dbe2f663` |
| NEO-002 Revision 20 package | root `/Users/Rome/Documents/Codex/2026-08-22/act-as-the-author-side-migration/outputs/NEO-002-revision20-external-trust-migration`; manifest SHA-256 `247115d37b1701b5880d478a67fc6a4c9678a1916bbf58a9d28d843d88eff34a`; content identity `b8e7915460e53da5be09cbe701c778505ec5bccfb4a8a977af74c4251a5f3892` |
| NEO-002 external verification architecture | root `/Users/Rome/Documents/Codex/2026-08-22/act-as-the-neutral-verification-architecture-2/outputs/NEO-002-external-verification-profile-v1`; manifest SHA-256 `ef2095054c088bd8f23eaa56d40e61c340dcfb2a22751bb67e3a738dd9055a54` |
| NEO-002 external intake binding | root `/Users/Rome/Documents/Codex/2026-08-23/act-as-the-neutral-external-intake/outputs/NEO-002-revision20-external-intake-binding-v1`; manifest SHA-256 `696700802a4ae4d0ed40b4fb4c7ac69a0fe7a42fd1855a26822319e08e68d99c` |
| NEO-002 Revision 20 independent review | root `/Users/Rome/Documents/Codex/2026-08-23/act-as-the-separate-independent-adversarial/outputs/NEO-002-revision20-independent-revalidation`; manifest SHA-256 `1ba943c067afeef1bea5cec50769cca183ea2f03eaad5ea3618f4c98fd9949b8` |
| NEO-002 Revision 20 final checkpoint | root `/Users/Rome/Documents/Codex/2026-08-21/referenced-chatgpt-conversation-this-is-an-3/outputs/NEO-002-orchestrator-revision20-final-checkpoint`; manifest SHA-256 `582aa6b270204e03a1fe85a2ea217a531620738415ea6ae67cdb64571e278ff9` |
| NEO-003 Revision 1 package | root `/Users/Rome/Documents/Codex/2026-08-24/files-pasted-by-the-user-act/outputs/NEO-003-frontier-discovery-methods-revision1`; manifest SHA-256 `47a6e8cb5a8de383c11bdc6ddf9d2492ab7a1a380b2ee02f39dc7ee9e95d3463`; digest-record SHA-256 `d39834a15554cb8445b1c40d1745659861162ba0336cbe08743da88262c88974` |
| NEO-003 Revision 1 independent review | root `/Users/Rome/Documents/Codex/2026-08-21/referenced-chatgpt-conversation-this-is-an-3/outputs/NEO-003-revision1-independent-revalidation`; manifest SHA-256 `7ab28e1543f8210d5d240d116cd350fac24d7b1d9fb6bacb2ffa4c7aea79639f`; digest-record SHA-256 `eed609dfdc9237647388de04564fe98aaeca4c35d62bb331c122dc9d5de5b789` |
| NEO-003 Revision 1 final checkpoint | root `/Users/Rome/Documents/Codex/2026-08-21/referenced-chatgpt-conversation-this-is-an-3/outputs/NEO-003-revision1-final-checkpoint`; manifest SHA-256 `710655a4a2efe62398e681949bbf282c8b92b31b8a493d724a3f020ad99ad495` |
| NEO-003 initiation continuity only | root `/Users/Rome/Documents/Codex/2026-08-21/referenced-chatgpt-conversation-this-is-an-3/outputs/NEO-003-initiation-checkpoint`; manifest SHA-256 `7a0b4240edb9ecbbedf225a63a458023789c3b8aa5132b755cd8202faf7f8cba` |

## 19. Completion and claim boundary

This specification defines the bounded harness objectives, exclusions, data and label contracts, method branches, metrics, uncertainty reporting, comparison criteria, architecture/trust boundaries, staged implementation gates, the initial-review and remediation-revalidation handoff contract, operational limits, failure behavior, reproducibility, unresolved dependencies, and incomplete requirements. It creates no scientific or operational result. It does not itself authorize even bounded implementation, and no G0-G10 result authorizes production implementation, final production architecture selection, operational deployment, production search, submission, authority contact, or an impact claim.

`REVISED_AWAITING_INDEPENDENT_REVALIDATION`
