# Phase 0 — Root cause findings for JPL SBDB / MPC / Fink probe failures

**Date**: 2026-07-02
**Method**: every finding below is from a real command the operator ran and
pasted output for (either the Skill script or direct `curl`), not from
documentation review alone — this sandbox's network proxy blocks these
domains, so nothing here was verified by direct fetch from the coding-agent
side. See `docs/evidence/phase0/2026-07-02-first-live-probe-console.md` for
the original probe run this follows up on.

## JPL SBDB — ROOT CAUSE CONFIRMED, FIXED

**Symptom**: `sbdb_query.api?...&neo=Y&full-prec=true&limit=3` returned HTTP
400: `{"message":"one or more query parameter was not recognized","code":"400"}`.

**Root cause**: `neo=Y` (from `docs/neo_discovery_agent_brief.md`'s example)
is not a recognized query parameter on the live API.

**Verification** (operator `curl`, both real 200 responses with real data):

```
curl "https://ssd-api.jpl.nasa.gov/sbdb_query.api?fields=...&full-prec=true&limit=3"
  -> 200, MBA objects (1 Ceres, 2 Pallas, 3 Juno), count: 1556924

curl "https://ssd-api.jpl.nasa.gov/sbdb_query.api?fields=...&sb-group=neo&full-prec=true&limit=3"
  -> 200, NEO objects (433 Eros class AMO, 719 Albert class AMO,
     887 Alinda class AMO), count: 42153
```

The base query works without any NEO filter; adding `sb-group=neo` correctly
restricts results to NEOs (confirmed by the returned `class: AMO` records
and the plausible NEO population count of 42,153 vs. 1,556,924 for all
small bodies).

**Fix applied**:
- `Skills/verify_ztf_dr24_sources.py`: `jpl_sbdb_neo_query` probe URL changed
  from `neo=Y` to `sb-group=neo`.
- `docs/neo_discovery_agent_brief.md`: JPL SBDB example section annotated
  with the correction and the live-verified working URL, per the brief's own
  §Assumption Audit rule that live-verified behavior supersedes the brief
  text.

## MPC get-obs — root cause narrowed to "needs a JSON request body"

**Symptom (probe 1, query-string only)**: `get-obs?desigs=433&output_format=XML`
returned HTTP 501: `{"error": "content_type_error", "message": "Content-Type
not supported, use application/json"}`.

**Symptom (probe 2, header added, no body)**: adding
`-H "Content-Type: application/json"` with no request body changed the error
to HTTP 400: `{"error": "general_error", "message": "get-obs failed with 400
Bad Request: Failed to decode JSON object: Expecting value: line 1 column 1
(char 0)"}`.

**Root cause (confirmed by the error message itself, not assumed)**: the
API parses the request body as JSON regardless of HTTP method, and rejects
an empty body ("Expecting value: line 1 column 1 (char 0)" is Python's
`json.loads("")` error). This means `get-obs` requires an actual JSON
request body (e.g. `{"desigs": ["433"]}`), not query-string parameters, even
though the request is a GET. This is unusual but is exactly what the request
body content-negotiation error describes.

**Status**: CONFIRMED AND FIXED. Operator ran
`curl -sS -X GET -H "Content-Type: application/json" -d '{"desigs": ["433"]}' "https://data.minorplanetcenter.net/api/get-obs"`
and got HTTP 200 with a full ADES XML observation history for 433 Eros
(hundreds of `<optical>` records spanning 2026-01-24 through 2026-06-30,
multiple stations/surveys, `MPEC` references). The response is large simply
because Eros has a long observation history, not because of an error --
this is the correct, expected shape of a successful `get-obs` response.

**Fix applied**: `Skills/verify_ztf_dr24_sources.py`'s `mpc_get_obs` probe
now carries a `"body": {"desigs": ["433"]}` key, and `_probe_one()` sends it
via `requests.request("GET", url, json=body, timeout=30)` when a probe
defines a body (falls back to plain `requests.get()` otherwise). The
existing `_BODY_PREVIEW_CHARS = 2000` truncation already caps how much of
large responses like this one get written into `phase0_probe_results.json`.

## Fink API — external blocker, not a bug in our code

**Symptom**: both `fink_schema` and `fink_swagger` fail identically with an
SSL handshake error. Python's `requests`/urllib3 reported
`SSLEOFError(8, '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in
violation of protocol')`. The operator independently confirmed via plain
`curl` (LibreSSL, the Mac's native TLS stack — a completely different
implementation from Python's `ssl` module):

```
* Connected to api.fink-portal.org (157.136.255.32) port 443
* ALPN: curl offers h2,http/1.1
* (304) (OUT), TLS handshake, Client hello (1):
* LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to api.fink-portal.org:443
curl: (35) LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to api.fink-portal.org:443
```

**Root cause determination**: TCP connects successfully (DNS resolves, socket
connects, ALPN offer sent), but the TLS handshake itself dies immediately
after the ClientHello, before any response — and this happens identically
across two independent TLS stacks (Python `ssl`/urllib3 and the operating
system's LibreSSL) from the operator's real network. This rules out a
client-library bug on our side. The failure is either a server-side TLS
termination problem, an outage, or a WAF/edge dropping the connection based
on some property of the handshake (fingerprint, cipher offer, etc.) that is
outside this project's control.

## Checkpoint key ignored probe content — stale results silently resumed

**Symptom** (operator run, 2026-07-02, after both fixes above landed on
`main`): re-running `Skills/verify_ztf_dr24_sources.py` printed
`[resume] (N/5) ...: already probed, skipping` for all 5 probes and
completed in `elapsed 0m00s`. Zero seconds for a script that makes live
HTTPS calls is a physically impossible value for real network I/O — per the
standing diagnostic rule, this meant no network calls happened at all, not
that the calls were somehow instant.

**Root cause**: `_checkpoint_path()` derived its checkpoint filename by
hashing only the probe **IDs** (`jpl_sbdb_neo_query`, `mpc_get_obs`, etc.),
not their URL/method/body. Both the JPL SBDB and MPC get-obs fixes changed
a probe's `url`/`body` while keeping its `id` the same (deliberately, to
preserve traceability). That meant the checkpoint filename never changed
across either fix, so the script kept finding and trusting the *original*
checkpoint file — written before either bug was diagnosed — and reported
`[resume]` on every probe instead of re-querying with the corrected
requests. The console output from that run reflected pre-fix, broken
responses, not the shipped fixes.

**Fix applied**: `_checkpoint_path()` now hashes the full probe definition
(`id`, `url`, `method`, `body`) for every probe, not just the ID list.
Editing any probe's request now produces a new checkpoint filename
automatically, so a code fix to a probe is guaranteed to be re-probed on
the next run rather than silently resumed from a stale cache — while
probes that are genuinely unchanged still resume correctly.

**Status**: fix applied, not yet operator-verified. Predicted result of the
next run: this is a *new* checkpoint filename (the old file is now orphaned
and harmless — `Logs/**` is git-ignored), so all 5 probes will print
`[verify]` (not `[resume]`) and make live network calls again, with a
nonzero `elapsed` value. Expect `jpl_sbdb_neo_query`, `mpc_get_obs`, and
`irsa_ztf_sci_metadata` to report HTTP 200; `fink_schema`/`fink_swagger`
are expected to still fail (5 retries with 2/4/8/16/32s backoff each,
consistent with the confirmed external Fink TLS blocker above) — if Fink
instead succeeds, or the other three fail, the fix is not what we think it
is.

**No code fix is applicable here.** This is recorded as an external service
availability issue, not a defect in `Skills/verify_ztf_dr24_sources.py`.
Retry later, or check Fink's own status channels
(https://github.com/astrolabsoftware/fink-object-api or the Fink Slack/community)
if Fink API access becomes a hard blocker for Phase 1 — SNAPS/other reference
sources remain available regardless.
