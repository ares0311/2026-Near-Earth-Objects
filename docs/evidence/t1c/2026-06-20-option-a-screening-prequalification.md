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

## Next Required Step: Follow-Up Run (NOT YET DONE)

Run ATLAS forced photometry against the 5 prequalified objects:

```bash
git pull origin main && \
caffeinate -i uv run python Skills/fetch_atlas_data.py \
    --expected-known Logs/reports/t1c_option_a_prequalified_manifest.json \
    --workers 4
```

Note: Do NOT use `--force-refresh` here — the prequalified manifest is new,
so there is no stale cache to bypass. Using `--force-refresh` would force the
operator to repeat all 5-object queries if the command is re-run.

Approximate query count: 5 objects × 6 samples = ~30 ATLAS queries.
Expected runtime: 5–15 minutes.

---

## After Follow-Up: Audit Step (NOT YET DONE)

```bash
caffeinate -i uv run python Skills/audit_real_run.py \
    --run-dir Logs/pipeline_runs/<new_run_id> \
    --expected-known Logs/reports/t1c_option_a_prequalified_manifest.json \
    --json
```

Replace `<new_run_id>` with the `run_id` printed by the follow-up run.
KPI gate: ≥90% of prequalified objects recovered.

---

## Guardrails (all runs)

- No external submission authorized
- No MPC submission authorized
- No NASA PDCO notification authorized
- No impact-probability claims authorized
- All results remain internal operational evidence only
