# Background Search Automation

This document describes the project implementation of
`BACKGROUND_SEARCH_AUTOMATION_BLUEPRINT.md`.

## Execution Model

This implementation is automated-ready but still conservative. The scheduler
invokes the same bounded one-run command used for manual review:

```bash
PYTHONPATH=src python Skills/background.py run-once
```

The command performs exactly one offline fixture-based cycle and exits:

1. Load local fixture targets from `background/targets.json`.
2. Score and prioritize targets.
3. Select exactly one target.
4. Run deterministic local follow-up checks.
5. Write one durable ledger entry.
6. Write exactly one outcome entry: reviewed or needs-follow-up.

No long-lived loop is embedded in the project. Use cron, launchd, systemd, or
another external scheduler to repeat the command. The SQLite run lock prevents
overlapping invocations.

## Automation Config

The default config lives at:

```text
background/config.json
background/config.schema.json
```

It pins the run mode to `automated`, enables scheduler readiness, disables live
network access, and requires human signoff before any external action can even
be considered. This means automated offline triage is allowed, but live survey
queries remain blocked until credentials and a review policy are explicitly
configured.

Check readiness without running the pipeline:

```bash
PYTHONPATH=src python Skills/background.py automation-readiness
```

The readiness report includes the one-run command, scheduler blockers, live-mode
blockers, missing credential environment variables, and confirms that external
submission is disabled.

Readiness validates the live review policy contract without contacting external
services. The default example policy is contract-valid even though it is not
approved for live network access. Missing policy files, invalid schema files,
or policy settings that permit external submission are reported as
`LIVE_REVIEW_POLICY_CONTRACT_INVALID`.

Readiness also includes provider-specific entries for ZTF, ATLAS, and
Pan-STARRS. Each entry records the credential environment variable, fetch API,
policy approval state, minimum cadence requirement, and blockers such as
`PROVIDER_CREDENTIAL_MISSING`, `PROVIDER_NOT_POLICY_APPROVED`, or
`PROVIDER_RATE_LIMIT_TOO_FAST`. This is metadata only; it performs no network
queries.

Persist the same readiness snapshot to the top-level SQLite log:

```bash
PYTHONPATH=src python Skills/background.py record-automation-readiness
PYTHONPATH=src python Skills/background.py automation-readiness-log-summary
```

Generate and persist a no-network live dry-run plan:

```bash
PYTHONPATH=src python Skills/background.py live-dry-run-plan
PYTHONPATH=src python Skills/background.py record-live-dry-run-plan
PYTHONPATH=src python Skills/background.py live-dry-run-plan-log-summary
```

The plan is derived from `background/live_review_policy.example.json` until a
reviewer replaces it with an approved policy. The example policy deliberately
sets `approved_for_live_network` to `false`.

Record a mock-only live dry-run execution attempt:

```bash
PYTHONPATH=src python Skills/background.py live-dry-run-execute
PYTHONPATH=src python Skills/background.py live-execution-log-summary
```

This command runs the same preflight gates as the plan command and persists the
attempt to SQLite. It does not contact survey services, download data, submit
observations, or enable any external alert pathway. Real live network execution
requires a separate explicit implementation and review.

Internally, dry-run execution now routes through a small provider interface:
`LiveDryRunProvider.execute(query)`. The default providers are
`MockLiveDryRunProvider` instances for ZTF, ATLAS, and Pan-STARRS. Tests may
inject providers to validate aggregation, but provider results are rejected if
they claim network access or external submission.

`live_dry_run_plan` persists the same provider-readiness details alongside the
planned no-network queries so a reviewer can see which survey would be blocked
before any live run is attempted.

The dry-run plan also includes the live review policy contract summary, making
policy/schema validation auditable in the same top-level SQLite plan log.

## Top-Level SQLite Logs

Background logs live at the repository top level:

```text
Logs/
  background.sqlite
  reports/
```

The SQLite database contains append-only operational tables:

| Table | Purpose |
|---|---|
| `run_ledger` | One row for every invocation of the one-run command |
| `reviewed_log` | Outcome row when no follow-up is warranted |
| `needs_follow_up_log` | Outcome row when follow-up, tests, or review are required |
| `human_signoff_log` | Manual reviewer signoff records |
| `automation_readiness_log` | Scheduler/live-readiness snapshots |
| `live_dry_run_plan_log` | No-network live dry-run query plans |
| `live_execution_log` | Mock-only live dry-run execution attempts |
| `run_lock` | Prevents overlapping invocations |
| `schema_metadata` | SQLite schema version metadata |

Every invocation writes exactly one `run_ledger` row and exactly one row in
either `reviewed_log` or `needs_follow_up_log`.

## Summary Commands

```bash
PYTHONPATH=src python Skills/background.py ledger-summary
PYTHONPATH=src python Skills/background.py reviewed-summary
PYTHONPATH=src python Skills/background.py needs-follow-up-summary
PYTHONPATH=src python Skills/background.py target-priority-summary
PYTHONPATH=src python Skills/background.py follow-up-test-summary
PYTHONPATH=src python Skills/background.py submission-recommendation-summary
PYTHONPATH=src python Skills/background.py validation-summary
PYTHONPATH=src python Skills/background.py human-signoff-summary
PYTHONPATH=src python Skills/background.py signoff-readiness
PYTHONPATH=src python Skills/background.py record-automation-readiness
PYTHONPATH=src python Skills/background.py automation-readiness-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-plan
PYTHONPATH=src python Skills/background.py record-live-dry-run-plan
PYTHONPATH=src python Skills/background.py live-dry-run-plan-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-execute
PYTHONPATH=src python Skills/background.py live-execution-log-summary
PYTHONPATH=src python Skills/background.py unsigned-follow-up
PYTHONPATH=src python Skills/background.py run-detail --run-id <run-id>
PYTHONPATH=src python Skills/background.py target-history --target-id <target-id>
PYTHONPATH=src python Skills/background.py automation-readiness
PYTHONPATH=src python Skills/background.py launchd-plist
```

Each command prints structured JSON for scheduler notifications or manual review.
The deprecated one-file wrapper scripts have been removed; use
`Skills/background.py` with a subcommand for all background operations.

## Human Signoff

Signoff records are explicit and auditable. They do not submit or contact
external parties. Multiple reviewers may record signoffs for the same run; one
`approved_for_internal_review` record is enough for the signoff-readiness audit
view to report the run as signed.

```bash
PYTHONPATH=src python Skills/background.py record-signoff \
  --run-id <run-id> \
  --target-id <target-id> \
  --reviewer "Reviewer Name" \
  --decision approved_for_internal_review \
  --scope "Internal follow-up only" \
  --notes "Reviewed SQLite log and report draft"
```

## Scheduler Examples

### cron

Keep the same one-run command and avoid overlapping invocations:

```cron
0 * * * * cd /path/to/repo && PYTHONPATH=src python Skills/background.py run-once >> Logs/background_cron.log 2>&1
```

### macOS launchd

Generate a plist template that runs the same command from the repository
directory:

```bash
PYTHONPATH=src python Skills/background.py launchd-plist > ~/Library/LaunchAgents/org.neo-detection.background.plist
```

The important scheduler responsibilities are to avoid overlapping runs, capture
stdout/stderr, and notify only on failure or needs-follow-up outcomes.

## Guardrails

- The command is offline by default and uses fixture inputs.
- Automated scheduling does not enable live network access.
- It does not contact external parties.
- It does not submit to MPC, NASA, CNEOS, CBAT, or any other destination.
- It does not claim discovery, confirmation, or authoritative hazard status.
- Needs-follow-up reports are internal drafts and require explicit human review.
