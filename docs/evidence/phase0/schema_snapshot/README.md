# Phase 0 schema snapshot

Date: 2026-07-02

This directory records the schema/metadata status for Phase 0 of the ZTF DR24
historical-replay pipeline. It is derived only from real operator-observed
responses captured in `../phase0_probe_results.json`; no endpoint, schema, or
field list is inferred.

## Source status

| Source | Snapshot status | Evidence |
|---|---|---|
| Fink schema | Not captured. Both schema probes failed during TLS handshake before an HTTP response. | `fink_schema` and `fink_swagger` in `../phase0_probe_results.json` |
| JPL SBDB | Captured in response signature and fields list. Query returned HTTP 200 with fields `spkid,pdes,full_name,class,neo,pha,moid,H,epoch,e,a,q,i,om,w,ma` and NEO rows including 433 Eros, 719 Albert, and 887 Alinda. | `jpl_sbdb_neo_query` in `../phase0_probe_results.json` |
| MPC get-obs | Captured as truncated ADES XML observation response for 433 Eros. Full response was too large for the evidence preview and was intentionally truncated. | `mpc_get_obs` in `../phase0_probe_results.json` |
| IRSA ZTF image metadata | Captured as truncated IPAC table metadata, including ZTF image metadata columns and `RowsRetrieved = 3277`. Full response was too large for the evidence preview and was intentionally truncated. | `irsa_ztf_sci_metadata` in `../phase0_probe_results.json` |

## Handoff

Fink remains unavailable from the operator's network as of this evidence packet.
Phase 1 ingestion must not depend on an unstated Fink schema. Use IRSA ZTF,
JPL SBDB, and MPC get-obs behavior exactly as captured here unless a later
Phase 0 evidence packet supersedes these files.
