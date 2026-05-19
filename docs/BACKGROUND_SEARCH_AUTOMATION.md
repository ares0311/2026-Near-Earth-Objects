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

Persist the same readiness snapshot to the top-level SQLite log:

```bash
PYTHONPATH=src python Skills/background.py record-automation-readiness
PYTHONPATH=src python Skills/background.py automation-readiness-log-summary
```

## Top-Level SQLite Logs

Background logs live at the repository top level:

```text
Logs/
  background.sqlite
  reports/
```

The SQLite database contains three append-only operational tables:

| Table | Purpose |
|---|---|
| `run_ledger` | One row for every invocation of the one-run command |
| `reviewed_log` | Outcome row when no follow-up is warranted |
| `needs_follow_up_log` | Outcome row when follow-up, tests, or review are required |
| `human_signoff_log` | Manual reviewer signoff records |
| `automation_readiness_log` | Scheduler/live-readiness snapshots |
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
