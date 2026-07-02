# Phase 0 sample ingest report

Date: 2026-07-02

This Phase 0 run performed source verification only. It did not run production
ingestion, download bulk ZTF DR24 alert/image data, submit anything externally,
or create candidate records.

## Probe-only results

| Source | Rows or records observed | Public/proprietary status | Local artifact |
|---|---:|---|---|
| Fink schema/swagger | 0 | Unknown; both probes failed before HTTP response during TLS handshake. | `docs/evidence/phase0/phase0_probe_results.json` |
| JPL SBDB NEO query | 3 preview rows from a reported count of 42153 NEO records | Public HTTP GET, no credentials observed for this probe. | `docs/evidence/phase0/phase0_probe_results.json` |
| MPC get-obs | Full 433 Eros observation response observed; evidence preview truncated from a 9909354-byte response | Public HTTP GET with JSON body, no credentials observed for this probe. | `docs/evidence/phase0/phase0_probe_results.json` |
| IRSA ZTF image metadata | `RowsRetrieved = 3277` in the returned metadata table | Public HTTP GET, no credentials observed for this probe. | `docs/evidence/phase0/phase0_probe_results.json` |

## File hashes

These hashes identify the evidence files used for this report.

| File | SHA-256 |
|---|---|
| `docs/evidence/phase0/phase0_probe_results.json` | `97226187687b1359d6e53315085cc67f908f4ec9f1001adc4381f87b007c88eb` |
| `docs/evidence/phase0/data_sources_verified.md` | `e177b80b64412bade6102a87359e8bead1f6b48129da9df503290f1fee1842a7` |
| `docs/evidence/phase0/auth_requirements.md` | `a02341c1969bbd074998e36ec3d027572b699e4c8c9493fab62bcf15a7cc730d` |
| `docs/evidence/phase0/2026-07-02-root-cause-findings.md` | `38d768eaaa3a8a53003231a419d919510c3dc178f5448a6d123ec1a6f3240a3c` |

## Handoff

This report does not approve Phase 1 bulk ingestion by itself. It closes the
"sample ingest report" requirement for the source-verification step by
recording that no sample ingest occurred and by preserving the exact probe
outputs that were observed. Phase 1 must begin with bounded historical replay,
explicit date windows, no future-catalog leakage, and new production gates for
the ZTF DR24 primary path.
