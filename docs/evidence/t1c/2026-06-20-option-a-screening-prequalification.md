# T1-C Evidence: Option A Screening + Prequalification (2026-06-20)

**Status**: Screening complete. Prequalification complete. Follow-up run PENDING.  
**Run ID (screening)**: `atlas_recovery_25f3a800a1a2`  
**Checkpoint**: `Logs/pipeline_runs/atlas_recovery_25f3a800a1a2/` (local, ignored by git)  
**Prequalified manifest**: `Logs/reports/t1c_option_a_prequalified_manifest.json` (local, ignored by git)

---

## Predeclared Policy (approved 2026-06-20)

See `docs/evidence/t1c/2026-06-20-option-a-predeclared-policy.md` for the full
pre-run policy document. Key parameters:

- Objects in screening: **25**
- Samples per object: **6** (101 total)
- Prequalification rule: ≥3 recovered ATLAS samples across ≥2 distinct nights
- Follow-up KPI gate: ≥90% recovery rate on prequalified denominator
- Query budget declared: 160 combined queries
- No external submission, no impact-probability claims authorized

---

## Screening Run Results

**Run ID**: `atlas_recovery_25f3a800a1a2`  
**Command used**:
```bash
caffeinate -i uv run python Skills/fetch_atlas_data.py \
    --expected-known Logs/reports/t1c_option_a_source_manifest.json \
    --workers 4 --force-refresh
```

**Results** (from operator terminal output, 2026-06-20):
- Total samples queried: **101**
- Recovered samples: **42**
- Tracklets emitted: **5**
- Failures: **0**
- Pending (poll-exhausted): **0**
- Runtime: ~16 minutes

**Budget note**: The operator ran the screening command twice (second run used
`--force-refresh`), consuming approximately 202 total screening queries. This
exceeds the predeclared 160-query combined budget. Noted for the record;
cannot be undone. The second run's checkpoint is the authoritative one.

---

## Prequalification Results

**Command used**:
```bash
caffeinate -i uv run python Skills/build_recovery_manifest.py \
    --prequalify-from-atlas-run Logs/pipeline_runs/atlas_recovery_25f3a800a1a2 \
    --prequalified-source-manifest Logs/reports/t1c_option_a_source_manifest.json \
    --prequalified-min-recovered-samples 3 \
    --prequalified-min-nights 2 \
    --output Logs/reports/t1c_option_a_prequalified_manifest.json
```

**Results** (from operator terminal output, 2026-06-20):
- Source objects: 25
- Qualified designations: **5**
- Prequalified objects: **121, 954, 2140, 2172, 5650**
- Output: `Logs/reports/t1c_option_a_prequalified_manifest.json`

---

## Follow-Up Run Results — DONE 2026-06-20

**Run ID**: `atlas_recovery_c1712df0f32c`  
**Command used**:
```bash
git pull origin main && \
caffeinate -i uv run python Skills/fetch_atlas_data.py \
    --expected-known Logs/reports/t1c_option_a_prequalified_manifest.json \
    --workers 4
```

**Results** (from operator terminal output, 2026-06-20):
- Objects in manifest: **5**
- Samples queried: **23**
- Recovered samples: **16/23**
- Tracklets emitted: **5** (one per object = 5/5 objects recovered)
- Failures: **0**
- Pending: **0**
- Runtime: ~19s (most samples served from `.neo_cache/` populated during screening)

**Per-object sample recovery**:
| Object | Recovered samples | Total samples |
|--------|-------------------|---------------|
| 121    | 3 (samples 0,3,4) | 5             |
| 954    | 3 (samples 1,3,4) | 5             |
| 2140   | 3 (samples 0,1,2) | 3             |
| 2172   | 3 (samples 0,1,3) | 5             |
| 5650   | 4 (samples 0,2,3,4)| 5            |

**Preliminary KPI result**: 5/5 objects produced audit tracklets = **100% recovery**.
KPI gate is ≥90%. **PASSES** — pending formal `audit_real_run.py` confirmation.

---

## Audit Step

**First attempt (FAILED — wrong expected-known file)**:
Used `Logs/reports/t1c_option_a_prequalified_manifest.json` which has no
`tolerance_days` field, so the audit defaulted to 0.02 days (29 min). ATLAS
observations can be up to 1.0 day from the predicted Horizons JD, so all
sky/time matches failed. Output: `Recovery gate: evaluated (passed=False)`.

**Root cause**: `fetch_atlas_data.py` writes a purpose-built audit manifest at
`Logs/pipeline_runs/atlas_recovery_c1712df0f32c/expected_known_atlas_forced.json`
with `tolerance_days=1.0`. The audit must use THAT file, not the prequalified
manifest directly.

**Correct audit command result (2026-06-20) — PASSED**:
```bash
caffeinate -i uv run python Skills/audit_real_run.py \
    --run-dir Logs/pipeline_runs/atlas_recovery_c1712df0f32c \
    --expected-known Logs/pipeline_runs/atlas_recovery_c1712df0f32c/expected_known_atlas_forced.json \
    --report-out Logs/reports/t1c_option_a_audit_report.json \
    --review-csv Logs/reports/t1c_option_a_review.csv
```

Terminal output:
```
Audit packet written: Logs/reports/t1c_option_a_audit_report.json
Review CSV written : Logs/reports/t1c_option_a_review.csv
Tracklets reviewed : 5
Recovery gate      : evaluated (passed=True)
Same-night subgate : applies=False passed=False (n_same_night=0 n_multi_night=5)
No external submission performed.
```

**Recovery KPI: PASSED.** 5/5 multi-night tracklets, recovery gate True.

---

## Next Step: Citizen-Science Operator Review (HUMAN BLOCKER)

The automated recovery gate has passed. T1-C closure now requires citizen-science
operator review of the 5 tracklets in `Logs/reports/t1c_option_a_review.csv`.

Jerome W. Lindsey III must review each of the 5 tracklet rows and confirm:
- No false positives that would require blocking promotion
- Findings noted (this is citizen-science review, not professional validation)
- No external submission, MPC report, or NASA notification is authorized

After review, record the decision and close T1-C in `docs/PRODUCTION_READINESS.md`.

---

## Guardrails (all runs)

- No external submission authorized
- No MPC submission authorized
- No NASA PDCO notification authorized
- No impact-probability claims authorized
- All results remain internal operational evidence only
