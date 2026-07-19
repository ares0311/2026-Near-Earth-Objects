# IRSA Concurrency Probe — Metadata vs. Pixel-Product Endpoints

Date: 2026-07-18

Scope: per operator direction ("try more field concurrently to probe the
limit of the host on that end"), progressively probed real concurrent
request levels against IRSA's ZTF DR24 endpoints, per
`CLAUDE.md`'s "Progressively probe toward the safe concurrency ceiling"
standing rule. Two structurally different endpoints were tested
separately, since they have very different real-world behavior:

1. **Metadata endpoint** (`ibe/search/ztf/products/sci` — small JSON/IPAC
   responses, a few KB to ~230KB)
2. **Pixel-product download endpoint** (`ibe/data/ztf/products/sci/...` —
   real difference-image/mask/PSF file downloads, ~5.7KB-19MB each)

All probe queries used genuinely uncached RA/Dec values (verified against
every existing `Logs/pipeline_runs/ztf_dr24_bounded_ingest/*/checkpoint.json`
before each round) to guarantee real network round-trips, not
resume-from-cache short-circuits. A first attempt at this reused two
already-cached RA/Dec pairs from earlier field-selection work and both
calls silently resumed from checkpoint (`EXIT=0`, zero real network
calls) -- caught before being mistaken for a real concurrency result, and
excluded from the findings below.

## Metadata endpoint: clean scaling to at least 10 concurrent

| Round | Concurrency | Result | Per-request elapsed (internal timer) |
|---|---:|---|---|
| 1 | 2 | 2/2 succeeded, `EXIT=0` | 13s, 15s |
| 2 | 4 | 4/4 succeeded, `EXIT=0` | 8s, 12s, 21s, 26s |
| 3 | 6 | 6/6 succeeded, `EXIT=0` | 8s, 13s, 15s, 17s, 23s, 23s |
| 4 | 10 | 10/10 succeeded, `EXIT=0` | 2s, 5s, 9s, 9s, 11s, 14s, 14s, 15s, 18s, 18s |

Zero errors, zero HTTP 429/503, zero timeouts, zero exceptions at any
level tested. Round 4 (10 concurrent) shows **no worse** tail latency than
rounds 2-3 (max 18s vs. max 26s) -- the mild latency spread seen in rounds
2-3 does not compound with concurrency, consistent with normal request
scheduling variance (and likely partly local `uv run` subprocess-startup
jitter from launching several Python interpreters simultaneously on one
machine) rather than genuine server-side throttling. **No real ceiling was
found up to 10 concurrent for this endpoint.**

## Pixel-product download endpoint: real, worsening latency degradation, no hard errors through 6

| Round | Concurrency | Result | Difference-image download elapsed (internal timer) |
|---|---:|---|---|
| serial baseline (established across fields 1-4 earlier this session) | 1 | -- | typically 2-4s, occasionally up to ~14s |
| 5 | 4 | 4/4 succeeded, `EXIT=0` | 33s, 30s, 23s, 26s |
| 6 | 6 | 6/6 succeeded, `EXIT=0` | 21s, 47s, 10s, 37s, 20s, 20s |

Every download in both rounds completed successfully (`EXIT=0`, correct
byte counts, no truncation, no HTTP error codes, no exceptions) -- this
endpoint did **not** hard-fail at either tested level. The same ~7MB
difference-image file that downloads in 2-4s serially took 8-11x longer
at 4 concurrent (23-33s) and up to 16x longer at 6 concurrent (max 47s,
versus 4-concurrent's max 33s).

**Confound identified, not ruled out (operator flagged live during this
probe): rounds 5-6 ran during a transition to degraded/changing local
network connectivity on the operator's Mac (boarding a flight), which
would produce the identical signature** -- uniformly elevated, variable
latency with zero hard errors on every concurrent request, regardless of
how many concurrent connections were open. A client-side connectivity
change is at least as parsimonious an explanation as IRSA server-side
queuing or rate-limiting under concurrent load, and this probe has no way
to distinguish the two after the fact (no client-side network-quality
telemetry was captured during the run). **This confound was not present
for the metadata-endpoint rounds** (1-4 above), which completed earlier
and show no comparable degradation trend -- so the metadata-endpoint
finding is not in question, only the pixel-download-endpoint one.

**Conclusion downgraded accordingly**: the pixel-product download
endpoint's apparent degradation under concurrency is a real, honestly
recorded observation from this session, but it must **not** be treated as
a confirmed IRSA-side rate limit or queuing behavior until re-verified in
a future session under known-stable network conditions. Do not cite this
probe alone as proof that IRSA's data-serving path throttles concurrent
clients -- it is equally consistent with the operator's own connection
degrading during the test.

## Honest interpretation and recommended defaults

- **Metadata-only queries** (coverage checks, field-night inventories):
  safe at least up to **10 concurrent** -- no degradation signal found at
  any tested level. Future batches may use this level directly without
  re-probing.
- **Pixel-product downloads** (`--pixel-extraction-pilot`, or any future
  batch downloader of real DR24 image/mask/PSF products): recommend
  **capping at 3 concurrent as a conservative starting point, not a
  confirmed ceiling** -- the confound above means this session's data
  cannot cleanly separate "IRSA queues/throttles concurrent data
  requests" from "the operator's local connection degraded mid-probe."
  Treat 3 as the conservative default for the same reason this project's
  first-batch default is conservative generally (per the "Progressively
  probe" rule's own framing), not as an empirically confirmed per-service
  ceiling the way the metadata-endpoint row is. **A future session should
  re-run this specific probe (4 and 6 concurrent pixel-product downloads,
  genuinely uncached RA/Dec, on a stable wired/local connection) before
  this endpoint's row in `docs/SYSTEM_PROFILE.md` can be upgraded from
  "conservative, unconfirmed" to "confirmed safe."** Neither this probe
  nor the earlier metadata-endpoint result changes this project's mission
  dependency on IRSA remaining a reliable, unauthenticated public resource
  -- do not push concurrency here past 3 without a clean re-verification.
- **Do not conflate the two endpoints.** A future agent tempted to use
  `Skills/run_sharded_download.py`-style 6x6 defaults against the
  pixel-product endpoint would be applying the metadata endpoint's clean
  result to the wrong path -- this is exactly why they are recorded as two
  separate rows in `docs/SYSTEM_PROFILE.md`.

## Root cause: recurring "background task failed" notifications were a harness artifact, not real command failures

Every single one of the ~30 concurrent probe commands in this session
(and, on inspection, essentially every backgrounded Bash command all
session) produced a `<task-notification>` reporting `status: failed`,
regardless of whether the underlying command actually succeeded. This was
investigated per operator request ("find the root causes of the failures
and report... a durably record").

**Root cause (confirmed, not guessed):** every command in this sandboxed
environment's Bash tool ends with a shell-level line of the form
`zsh:N: operation not permitted: /tmp/claude-501/cwd-XXXXXXXX` -- this
comes from zsh's own prompt/precmd machinery (likely a `cwd`-tracking stat
or write) after the launched command finishes, not from the command
itself. The sandbox denies this stat/write, and zsh reports it as an
error on the interactive shell's own exit path. The background-task
completion classifier appears to key off *any* shell-level error signal
on that path, not specifically the launched command's own exit code --
so it reports `failed` even when the actual command's real exit code
(verified in this probe by explicitly capturing `$?` and writing it into
the command's own redirected log file, e.g. `echo "EXIT=$?" >>
logfile`) is `0` and its output shows complete, correct success.

**Confirmed pattern across every check performed in this probe and
throughout this session:** whenever a background task notification says
`status: failed`, reading the actual repo-local log file (or the
command's own captured `$?`) has, without exception, shown the real
command succeeded. This is consistent with the "Background task false
failures" pattern this session already suspected informally; this probe
is the first time it was root-caused with an explicit, captured exit-code
comparison across ~30 independent samples rather than assumed from a
handful of ad hoc cases.

**Durable rule for future agents** (recorded in `CLAUDE.md`'s standing
rules, not just here): never trust a background-task notification's
`status: failed`/`status: completed` label as the sole signal of whether
a command succeeded. Always verify against the command's own real output
-- redirect to a repo-local log file and capture `$?` explicitly
(`command > logfile 2>&1; echo "EXIT=$?" >> logfile`) for anything where
the actual result matters, then read that file. Piping through `grep -v
"operation not permitted"` (this project's existing convention for
filtering the cosmetic noise from foreground commands) does not fix this
specific issue for *backgrounded* commands, because the false-failure
signal is generated by the harness's own completion classifier, not by
noise visible in the piped output.
