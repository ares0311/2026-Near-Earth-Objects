# Phase 0 — First live probe run (console output, operator Mac)

**Date**: 2026-07-02
**Command**: `caffeinate -i uv run --python 3.14 python Skills/verify_ztf_dr24_sources.py`
**Run from**: `main` at `d4f3f908` (v0.90.13)

This file records the raw console output the operator (Jerome W. Lindsey III)
pasted from the first live run of `Skills/verify_ztf_dr24_sources.py`. The
full-detail files (`data_sources_verified.md`, `auth_requirements.md`,
`phase0_probe_results.json`, including response body previews) were written
locally to `docs/evidence/phase0/` on the operator's machine by the script
itself and still need to be committed separately — this file preserves the
console-level result immediately so it is not lost to context compaction.

## Result summary (5 probes, elapsed 3m23s total)

| Probe | Result | Detail |
|---|---|---|
| `fink_schema` (`https://api.fink-portal.org/api/v1/schema`) | FAILED after 5 retries | `SSLError: SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1081)')` — TLS handshake dropped by the server/edge, not a 4xx application-level rejection. Retries did not help (deterministic, not transient). |
| `fink_swagger` (`https://api.fink-portal.org/swagger.json`) | FAILED after 5 retries | Same `SSLEOFError` as above. |
| `jpl_sbdb_neo_query` (`https://ssd-api.jpl.nasa.gov/sbdb_query.api?...&neo=Y&full-prec=true&limit=3`) | HTTP 400 | Server reachable (TLS/connection succeeded); request itself was rejected. Root cause not yet known — need the response body (saved locally in `phase0_probe_results.json`, not yet pasted/committed). |
| `mpc_get_obs` (`https://data.minorplanetcenter.net/api/get-obs?desigs=433&output_format=XML`) | HTTP 501 | Not Implemented. Server reachable; unusual status for a documented GET endpoint. Root cause not yet known — need the response body. |
| `irsa_ztf_sci_metadata` (`https://irsa.ipac.caltech.edu/ibe/search/ztf/products/sci?POS=358.3,25.6`) | HTTP 200 | Success — IRSA ZTF image metadata search is reachable without credentials, confirming the brief's claim for this endpoint. |

## Interpretation (from console output only — not yet the full response bodies)

- **IRSA ZTF metadata access**: confirmed working, no credentials needed.
  Matches `docs/neo_discovery_agent_brief.md`'s claim.
- **Fink API**: inconclusive from this run. An `SSLEOFError` during the TLS
  handshake is a different failure mode than a `403` — it suggests either a
  transient edge/CDN issue, a WAF blocking this specific TLS client
  fingerprint, or a genuine outage, not necessarily "no public access." Needs
  a second attempt and/or a different client (e.g. plain `curl`) to
  distinguish "Fink blocks this Python/requests client" from "Fink was down."
- **JPL SBDB and MPC get-obs**: both reachable (no connection-level failure),
  but both rejected the exact request URL cited in the brief. This is the
  most actionable finding — it means the brief's example URLs are not
  request-ready as written and need adjustment (missing/incorrect parameter,
  wrong HTTP method, or an API change since the brief was written). The
  response bodies are required to diagnose the exact cause and are not yet
  available in this file.

## Next step

Operator to run (from `main`, `PYTHONPATH=src` already set):

```bash
cat docs/evidence/phase0/data_sources_verified.md
cat docs/evidence/phase0/auth_requirements.md
cat docs/evidence/phase0/phase0_probe_results.json
```

and paste the output (or `git add docs/evidence/phase0/ && git commit -m "Record phase0 probe results" && git push origin main` if you'd rather commit them directly) so the actual JPL SBDB and MPC response bodies can be read and the 400/501 causes diagnosed.
