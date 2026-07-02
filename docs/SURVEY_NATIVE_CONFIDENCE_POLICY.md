# Survey-Native Confidence Policy — WISE/NEOWISE, DECam, TESS

**Established**: 2026-07-02
**Status**: Closes `docs/PRODUCTION_READINESS.md` Gate P2 (survey-native confidence policy)
**Authoritative inputs**: `docs/MISSION.md`, `docs/neo_discovery_agent_brief.md`,
`docs/MPC_SUBMISSION_POLICY.md`, `Skills/adversarial_review.py`

---

## Purpose

The production discovery sources (WISE/NEOWISE, DECam, TESS) do not carry a
ZTF-style `real_bogus`/`deep_real_bogus` score. Gate P1 proved the discovery
*path* (fetch → detect → link → classify → score) works structurally. Gate P2
documents, for each source, exactly what evidence stands in for the missing
ZTF real/bogus score, what the pipeline does when that evidence is also
absent, and which sources are verified against a live endpoint versus
code-complete but unverified. This is a documentation and verification gate,
not a request to add new ML models — the existing `detect.py`/`link.py`/
`score.py` gates already fail closed on missing evidence; this document
records that behavior as the intentional policy and identifies open gaps.

Per `docs/neo_discovery_agent_brief.md`, every claim below is either (a) a
direct citation of code already merged to `main`, or (b) marked as
**unverified** — no endpoint schema, auth behavior, or rate limit is stated
here without either a source-code citation or a durable evidence file under
`docs/evidence/live/`.

---

## Source-Verification Matrix

| Source | Endpoint | Query mechanism | Auth | Schema — verified how | Live-verified? |
|---|---|---|---|---|---|
| WISE/NEOWISE | `https://irsa.ipac.caltech.edu/TAP` | pyvo async TAP, ADQL cone + `mjd BETWEEN` on `neowiser_p1bs_psd` (`src/fetch.py:1497` `fetch_wise_archive`) | None required for public NEOWISE single-epoch photometry | Columns `source_id, ra, dec, mjd, w1mpro, w1sigmpro, sso_flg, allwise_cntr, n_allwise, r_allwise` confirmed live: `docs/evidence/live/2026-06-27-wise-live-sweep.md` (111,913 rows returned with exactly these column names) and multiple subsequent runs through v0.90.5 (e.g. `docs/evidence/live/2026-06-30-wise-v0905-parent-field-probe.md`, 16,582 rows) | **Yes** — repeatedly, through `docs/evidence/live/*.md` and the P1 harness (`docs/evidence/prod-loop/2026-07-02-gate-p1-wise-injection-recovery.md`) |
| DECam | `https://datalab.noirlab.edu/tap` | pyvo sync TAP, ADQL `q3c_radial_query` on `nsc_dr2.meas`, hardcoded `LIMIT 2000` (`src/fetch.py:1652` `fetch_decam_archive`) | None required (public Data Lab TAP) per code path (no credential parameter exists in `fetch_decam_archive`) | Columns `ra, dec, mjd, mag_auto, magerr_auto, filter` assumed from `nsc_dr2.meas` schema in code; **not confirmed against a live response** | **No** — no entry in `docs/evidence/live/` returns real DECam rows or confirms these column names against the live service |
| TESS | MAST via `astroquery.mast.Observations` + `astroquery.mast.Catalogs` (TIC) (`src/fetch.py:1738` `fetch_tess_ffis`) | `Observations.query_criteria(obs_collection="TESS", dataproduct_type="image", ...)` for sector coverage, then `Catalogs.query_region(..., catalog="TIC")` for reference positions, capped at 50 TIC sources per sector | None required for public MAST/TIC access per code path | Fields `t_min`, `t_max`, `sequence_number` (sector metadata) and `ID`, `ra`, `dec`, `Tmag`, `e_Tmag` (TIC) assumed from `astroquery.mast` documentation conventions in code; **not confirmed against a live response** | **No** — no entry in `docs/evidence/live/` |

**Action taken this cycle**: `Skills/run_pipeline.py` now prints an explicit
`[fetch] WARNING` to stderr whenever `--surveys DECam` or `--surveys TESS` is
selected, pointing here. `run_pipeline.py --surveys` still defaults to
`["WISE"]` only (`Skills/run_pipeline.py:910`) — DECam/TESS require an
explicit, informed operator choice.

**Structural limitation — TESS is not a per-epoch detection source as coded.**
`fetch_tess_ffis`'s own docstring states: "The TIC catalog contains static
stellar sources used as the reference background... full FFI-level source
detection is performed by preprocess.py." `preprocess.py` contains no FFI
pixel-level source-extraction logic (grep confirms zero `TESS`/`FFI`
references in `src/preprocess.py`). This means every `Observation` currently
returned for `mission="TESS"` is a **known TIC catalog star position**
replicated across each sector epoch, not a genuine transient/moving-object
detection. Any "candidate" the pipeline forms from TESS input today is
linking known static stars across epochs, not detecting a new moving object.
**Recommendation**: do not run `--surveys TESS` for discovery until FFI-level
difference-image source extraction is implemented; the current TESS path is
retained as fetch-layer scaffolding (sector/TIC metadata acquisition), not a
production discovery source. This is now stated explicitly rather than left
implicit in a docstring.

---

## Quantitative Confidence Thresholds

These thresholds are enforced in `src/detect.py`, `src/link.py`, and
`Skills/adversarial_review.py` today; this table is the authoritative record
of what each number means per source; it does not introduce new thresholds.

| Control | Threshold | Enforced in | Applies to |
|---|---|---|---|
| Motion-rate plausibility (solar-system-consistent) | 0.05–60 arcsec/hr | `detect.py:_MOTION_MIN/MAX_ARCSEC_PER_HR`, `link.py:_MOTION_MIN/MAX_ARCSEC_PER_HR` | All sources uniformly. The 0.05 arcsec/hr floor was raised in v0.90.4 specifically to reject WISE near-stationary/artifact associations before they reach review. |
| Real/bogus score | ≥ 0.90 for MPC-submission pathway; missing → fail closed | `score.py:_determine_alert_pathway` (`rb is None or rb < 0.90` → `internal_candidate`) | ZTF natively; WISE/DECam/TESS have no native score, so `real_bogus_score` is always `None` for these sources today, which **already routes every WISE/DECam/TESS candidate to `internal_candidate`** — none can reach `mpc_submission`, `neocp_followup`, or `nasa_pdco_notify` regardless of any other feature. This is the correct fail-closed behavior for a source with no real/bogus evidence, and it is why every WISE positive-control packet in the Gate P1 evidence scores `hazard_flag: unknown`. |
| Real/bogus in the composite log-score (`score.py:_compute_log_score_neo`) | Missing feature contributes 0 (neutral), not a fabricated confidence | `score.py:_NEO_WEIGHTS` loop: `if val is not None: score += w * val` | All sources. A `None` `real_bogus_score` for WISE/DECam/TESS neither helps nor hurts the neo_candidate log-score; it is excluded from the sum entirely, matching the CLAUDE.md scoring-model documentation. |
| Satellite/artifact trail rejection | Rejects near-cardinal (E-W/N-S) high-rate (≥30 arcsec/hr) pairs | `link.py:_is_satellite_trail` | All sources uniformly — geometric, not survey-specific. |
| Structural tracklet requirements | ≥3 detections, ≥2 distinct nights (`int(obs.jd)` buckets), reduced χ² ≤ 5.0 for linear-motion fit | `link.py:_MIN_OBSERVATIONS`, `_MIN_NIGHTS`, `_CHI2_DOF_THRESHOLD` | All sources uniformly. |
| Known-object exclusion | MPC cross-match at fetch/detect time; `known_object_score > 0.8` routes to `known_object` pathway | `detect.py` (`mpc_cross_match` param), `score.py:_determine_alert_pathway` | All sources. Uses the **current** MPC catalog state at query time (see leakage discussion below), not a time-aware historical snapshot. |
| Astrometric jitter (WISE) | Documented at ~1 arcsec position-fit precision (Mainzer et al. 2014) | Used as the noise model in `Skills/injection_recovery.py:inject_synthetic_neo_wise`; no separate quantitative gate is applied in `detect.py`/`link.py` beyond the `position_tolerance_arcsec=10.0` seed-pair-extension window in `link.py` | WISE. **Gap**: no WISE-specific astrometric-residual quality gate exists beyond the generic 10 arcsec tolerance; this is acceptable given the 100% recovery result in Gate P1 evidence but is flagged for future tightening if WISE real-sky candidate volume grows. |
| Photometric noise (WISE W1) | `w1sigmpro` typically 0.03–0.2 mag at NEO-detectable depths (Mainzer et al. 2014); masked/missing values default to sentinel `mag=99.0`, `mag_err=0.1` (`src/fetch.py:1623-1624`) | `fetch.py:fetch_wise_archive` | WISE. Sentinel-masked rows are not separately excluded before `detect.py`'s real/bogus pass-through filter; a `mag=99.0` sentinel row can still form a candidate. **Gap**: no explicit sentinel-magnitude rejection filter exists for WISE; recommend adding one if real-sky WISE volume increases false candidates from masked photometry. |
| Adversarial review margin | rb 0.90–0.92 flagged as "borderline" even though it technically passes | `Skills/adversarial_review.py:_RB_GATE=0.90`, `_RB_BORDERLINE_MARGIN=0.02` | ZTF-scored candidates only; WISE/DECam/TESS candidates never reach this check because they never pass the `rb ≥ 0.90` gate above. |

---

## No-Future-Catalog-Leakage Statement

`docs/neo_discovery_agent_brief.md` requires stating how the pipeline avoids
future-catalog leakage. The current production pipeline is a **live discovery**
system, not a historical-replay/backtesting system: `Skills/run_pipeline.py`
always queries the MPC known-object catalog at the wall-clock time the
pipeline runs, and every fetched observation's `jd` is within the requested
search window at or before "now." There is no code path today that evaluates
a *past* time window while intentionally masking catalog knowledge gained
*after* that window — so there is no leakage risk in the live-discovery mode
currently implemented.

Historical-replay evaluation, as described in
`docs/neo_discovery_agent_brief.md` (§Historical Replay), is **out of scope**
for the current WISE/DECam/TESS production path and is not implemented. If a
future production decision adds historical-replay evaluation (for example,
to validate the candidate ranker against ZTF DR24 per the brief), that work
must snapshot the known-object catalog state as of the replay window's start
(`known_object_catalog_snapshots` schema in the brief) and must not use any
catalog snapshot fetched after the replay window ends. This is a requirement
for that future work, not a gap in the current live-discovery pipeline.

---

## ZTF/Fink/SNAPS Reference-Only Reaffirmation

Per `docs/MISSION.md §Authoritative Brief Integration` (already updated by
the operator in v0.90.7): ZTF DR24, Fink/Fink-FAT, and SNAPS are
methodology, benchmarking, and candidate-ranker validation references. They
are not a production MPC discovery-submission stream. `fetch.py`'s
`fetch_discovery()` routing function still raises `ValueError` for ZTF/ATLAS
inputs (`src/fetch.py:1857`), preventing any accidental use of training-only
sources for discovery. No change was needed here — this document simply
confirms the existing enforcement is consistent with the brief.

---

## Pretrained Model Audit Status

No third-party pretrained model (DeepStreaks, `timm` vision backbones,
AstroM3-CLIP, Chronos, or similar) is currently used anywhere in production
scoring. The three trained ML tiers (`models/tier1_xgb.json`,
`models/tier2_cnn.pt`, `models/tier3_transformer.pt`) were trained in-house
on project-collected ZTF/MPC data (see `CLAUDE.md §Key Changes in v0.87.1/
v0.87.6/v0.87.9`), not initialized from third-party pretrained weights, so
the brief's `pretrained_model_audit.md` requirement does not yet apply.

**Standing requirement for future work**: before any third-party pretrained
model contributes to production scoring (e.g., a `timm` embedding feeding the
candidate ranker), create `pretrained_model_audit.md` (or a versioned
equivalent under `docs/evidence/`) per the brief's required fields — model
ID, source URL, license, download size, preprocessing, cache path, use mode,
and `use`/`defer`/`reject` decision — before that model's output is allowed
into `classify.py`/`score.py`.

---

## Gate P2 Checklist Status

- [x] Quantitative confidence thresholds documented per source (table above).
- [x] ML-output-to-source mapping documented; missing real/bogus for
      WISE/DECam/TESS confirmed to fail closed at the alert-pathway gate
      (`score.py:_determine_alert_pathway`), not silently pass.
- [x] Source-verification matrix added; DECam and TESS marked unverified with
      operator-visible runtime warnings added to `Skills/run_pipeline.py`.
- [x] ZTF/Fink/SNAPS reference-only status reaffirmed against existing
      `fetch_discovery()` enforcement.
- [x] No-future-catalog-leakage statement recorded for the current
      live-discovery pipeline; historical-replay requirement documented for
      future work.
- [x] Pretrained-model audit requirement recorded as a standing future-work
      gate; confirmed not currently applicable (no third-party pretrained
      model in production scoring today).
- [ ] **Open**: WISE sentinel-magnitude (`mag=99.0`) rejection filter — not
      yet implemented; recommended if real-sky WISE volume increases false
      candidates from masked photometry rows.
- [ ] **Open**: DECam/TESS live endpoint verification (Phase 0 per the brief)
      — not performed; both sources remain code-complete but unverified.
