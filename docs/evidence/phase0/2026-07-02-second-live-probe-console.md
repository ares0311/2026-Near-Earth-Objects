# Phase 0 — second live probe run (post-fix), console transcript

**Date**: 2026-07-02
**Branch/version at run time**: `main` @ v0.90.17 (checkpoint-key fix from
PR #156 applied), started from v0.90.16 checkout before `git pull`.
**Command**:
```bash
git pull origin main
caffeinate -i uv run --python 3.14 python Skills/verify_ztf_dr24_sources.py
```

This is the first live run after both content fixes (JPL SBDB `sb-group=neo`,
MPC get-obs JSON body) AND the checkpoint-key fix (hash full probe
definition, not just IDs) — confirming the checkpoint bug is actually fixed
and the two prior fixes were real, not stale-cache artifacts.

## Result: real live re-probe, not a stale resume

Total elapsed: **3m22s** (nonzero — confirms `[verify]`, not `[resume]`,
ran for every probe; the checkpoint-key fix worked).

| Probe | Result | Notes |
|---|---|---|
| `fink_schema` | **FAILED** after 5 retries (2/4/8/16/32s backoff, ~1m31s) | `SSLEOFError`: `[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol` — identical to the first probe run and the operator's independent native-curl/LibreSSL test. Confirms external Fink TLS blocker, not a regression. |
| `fink_swagger` | **FAILED** after 5 retries (~1m32s) | Same `SSLEOFError` signature. |
| `jpl_sbdb_neo_query` | **200** | `sb-group=neo` fix confirmed working on a fresh, non-cached probe. |
| `mpc_get_obs` | **200** | JSON-body fix confirmed working on a fresh, non-cached probe. |
| `irsa_ztf_sci_metadata` | **200** | Unchanged from the first run; still reachable without credentials. |

## Interpretation

- The checkpoint-key fix (PR #156) is verified: this run made real network
  calls for all 5 probes (nonzero elapsed, `[verify]` not `[resume]` — the
  operator's raw terminal output, not pasted here verbatim, showed
  `[verify] (N/5) Probing ...` lines for every probe).
- The JPL SBDB fix (PR #154) and MPC get-obs fix (PR #155) are now verified
  on a genuinely fresh request, not a stale pre-fix cached result. This
  closes the loop opened when the first post-fix run silently resumed a
  pre-fix checkpoint (documented in
  `docs/evidence/phase0/2026-07-02-root-cause-findings.md`).
- Fink remains confirmed external and non-fixable from our side.

## Outstanding — NOT YET DONE

The script also wrote three generated files to the operator's local
checkout (not committed, not present in this evidence file, and not
present in this coding-agent sandbox, which is a separate clone):

- `docs/evidence/phase0/data_sources_verified.md`
- `docs/evidence/phase0/auth_requirements.md`
- `docs/evidence/phase0/phase0_probe_results.json`

**Next production action**: operator should `git add` and commit those
three files (or paste their contents) so a future session can read the
full per-probe response bodies without re-running the script. Per
`.gitignore`, `docs/evidence/` is not ignored — these are safe to commit
directly.
