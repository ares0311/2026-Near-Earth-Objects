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

Inspect just the live review policy contract:

```bash
PYTHONPATH=src python Skills/background.py live-policy-contract-summary
```

Readiness also includes provider-specific entries for ZTF, ATLAS, and
Pan-STARRS. Each entry records the credential environment variable, fetch API,
policy approval state, minimum cadence requirement, and blockers such as
`PROVIDER_CREDENTIAL_MISSING`, `PROVIDER_NOT_POLICY_APPROVED`, or
`PROVIDER_RATE_LIMIT_TOO_FAST`. This is metadata only; it performs no network
queries.

Inspect just the provider readiness details:

```bash
PYTHONPATH=src python Skills/background.py live-provider-readiness-summary
```

Prepare a no-secret credential inventory before live dry-run approval:

```bash
PYTHONPATH=src python Skills/background.py live-credential-inventory
PYTHONPATH=src python Skills/background.py live-credential-inventory --write-report Logs/reports/credential_inventory_latest.json
```

The inventory reports required environment variable names, provider mappings,
presence booleans, Keychain service names, and storage guidance. It checks
environment variables first and macOS Keychain second, never prints token
values, performs no network access, and enables no external submission.

Inspect the combined no-network live dry-run approval bundle:

```bash
PYTHONPATH=src python Skills/background.py live-dry-run-approval-bundle
```

The approval bundle aggregates scheduler readiness, live review policy
contract status, provider readiness, the dry-run query plan, and deduplicated
blockers. It exposes `approved_to_attempt_live_dry_run`, but still performs no
network query and enables no external submission.

Generate an internal operator handoff from the same approval bundle:

```bash
PYTHONPATH=src python Skills/background.py live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py write-live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py record-live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py live-dry-run-operator-handoff-log-summary
```

The handoff is Markdown for local review. It summarizes blockers, credentials,
policy approval state, provider readiness, planned surveys, and dry-run scope.
It is not a submission artifact and does not contact outside parties. The
record command writes the handoff and persists the review entry in the
top-level SQLite log.

Persist the same approval-bundle review to the top-level SQLite log:

```bash
PYTHONPATH=src python Skills/background.py record-live-dry-run-approval-bundle
PYTHONPATH=src python Skills/background.py live-dry-run-approval-bundle-log-summary
```

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
| `signoff_packet_log` | Internal human-review packet metadata |
| `signoff_packet_decision_log` | Packet-linked reviewer decisions and resulting operations snapshots |
| `automation_readiness_log` | Scheduler/live-readiness snapshots |
| `blueprint_compliance_log` | Background blueprint compliance snapshots |
| `operations_snapshot_log` | Aggregated operator-facing background status snapshots |
| `live_approval_bundle_log` | No-network live dry-run approval reviews |
| `live_operator_handoff_log` | Written no-network operator handoffs |
| `live_dry_run_plan_log` | No-network live dry-run query plans |
| `live_execution_log` | Mock-only live dry-run execution attempts |
| `run_lock` | Prevents overlapping invocations |
| `schema_metadata` | SQLite schema version metadata |

Every invocation writes exactly one `run_ledger` row and exactly one row in
either `reviewed_log` or `needs_follow_up_log`.

## Summary Commands

```bash
PYTHONPATH=src python Skills/background.py ledger-summary
PYTHONPATH=src python Skills/background.py schema-status-summary
PYTHONPATH=src python Skills/background.py init-log-db-preview
PYTHONPATH=src python Skills/background.py schema-operations-summary
PYTHONPATH=src python Skills/background.py operator-next-action
PYTHONPATH=src python Skills/background.py init-log-db
PYTHONPATH=src python Skills/background.py reviewed-summary
PYTHONPATH=src python Skills/background.py needs-follow-up-summary
PYTHONPATH=src python Skills/background.py internal-follow-up-disposition
PYTHONPATH=src python Skills/background.py target-priority-summary
PYTHONPATH=src python Skills/background.py follow-up-test-summary
PYTHONPATH=src python Skills/background.py submission-recommendation-summary
PYTHONPATH=src python Skills/background.py validation-summary
PYTHONPATH=src python Skills/background.py blueprint-compliance-summary
PYTHONPATH=src python Skills/background.py record-blueprint-compliance-summary
PYTHONPATH=src python Skills/background.py blueprint-compliance-log-summary
PYTHONPATH=src python Skills/background.py operations-snapshot
PYTHONPATH=src python Skills/background.py record-operations-snapshot
PYTHONPATH=src python Skills/background.py operations-snapshot-log-summary
PYTHONPATH=src python Skills/background.py latest-unsigned-signoff-packet
PYTHONPATH=src python Skills/background.py signoff-packet --run-id <run-id>
PYTHONPATH=src python Skills/background.py write-signoff-packet --run-id <run-id>
PYTHONPATH=src python Skills/background.py record-signoff-packet --run-id <run-id>
PYTHONPATH=src python Skills/background.py signoff-packet-log-summary
PYTHONPATH=src python Skills/background.py record-signoff-from-packet --packet-id <packet-id> --reviewer "Reviewer Name" --decision approved_for_internal_review --scope "Internal follow-up only"
PYTHONPATH=src python Skills/background.py signoff-packet-decision-summary
PYTHONPATH=src python Skills/background.py signoff-packet-decision-readiness
PYTHONPATH=src python Skills/background.py latest-undecided-signoff-packet
PYTHONPATH=src python Skills/background.py human-signoff-summary
PYTHONPATH=src python Skills/background.py signoff-readiness
PYTHONPATH=src python Skills/background.py record-automation-readiness
PYTHONPATH=src python Skills/background.py automation-readiness-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-plan
PYTHONPATH=src python Skills/background.py record-live-dry-run-plan
PYTHONPATH=src python Skills/background.py live-dry-run-plan-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-execute
PYTHONPATH=src python Skills/background.py live-execution-log-summary
PYTHONPATH=src python Skills/background.py live-policy-contract-summary
PYTHONPATH=src python Skills/background.py live-provider-readiness-summary
PYTHONPATH=src python Skills/background.py live-credential-inventory
PYTHONPATH=src python Skills/background.py live-dry-run-approval-bundle
PYTHONPATH=src python Skills/background.py record-live-dry-run-approval-bundle
PYTHONPATH=src python Skills/background.py live-dry-run-approval-bundle-log-summary
PYTHONPATH=src python Skills/background.py live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py write-live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py record-live-dry-run-operator-handoff
PYTHONPATH=src python Skills/background.py live-dry-run-operator-handoff-log-summary
PYTHONPATH=src python Skills/background.py unsigned-follow-up
PYTHONPATH=src python Skills/background.py run-detail --run-id <run-id>
PYTHONPATH=src python Skills/background.py target-history --target-id <target-id>
PYTHONPATH=src python Skills/background.py automation-readiness
PYTHONPATH=src python Skills/background.py launchd-plist
```

Each command prints structured JSON for scheduler notifications or manual review.
The deprecated one-file wrapper scripts have been removed; use
`Skills/background.py` with a subcommand for all background operations.

## SQLite Schema Status

Inspect the top-level SQLite log schema without mutating it:

```bash
PYTHONPATH=src python Skills/background.py schema-status-summary
PYTHONPATH=src python Skills/background.py init-log-db-preview
PYTHONPATH=src python Skills/background.py schema-operations-summary
PYTHONPATH=src python Skills/background.py operator-next-action
```

The summary reports the expected table set, present tables, missing tables,
extra tables, schema version, and guardrail flags. It does not create a
database, write rows, generate reports, contact outside parties, enable live
network access, record a packet, or record a signoff.

The preview command reports what `init-log-db` would create, including missing
tables, would-create tables, whether the database file would be created, and
the exact init command. It is also read-only and does not create a missing DB
file.

The operations summary combines schema status and migration preview with a
packet-decision readiness flag and the next safe schema action. Use it before
packet-linked signoff decisions to confirm the SQLite log has the
`signoff_packet_decision_log` table.

The operator next-action summary schema-gates the workflow first. If the
SQLite log is incomplete, it recommends `init-log-db` and does not consult an
operations snapshot. If the schema is current, it combines operations state and
packet-decision readiness into one conservative local command recommendation.

Run the additive local migration only when an operator explicitly wants the
SQLite log database brought up to the current schema:

```bash
PYTHONPATH=src python Skills/background.py init-log-db
```

This command delegates to `init_log_db`, which uses `CREATE TABLE IF NOT
EXISTS` and additive column checks. It reports before/after table state and
created tables. It does not create signoff decisions, write reports, generate
packets, contact outside parties, enable live network access, or perform any
external submission.

## Blueprint Compliance Matrix

The blueprint compliance summary maps the implemented background automation to
the definition of done in `BACKGROUND_SEARCH_AUTOMATION_BLUEPRINT.md`:

```bash
PYTHONPATH=src python Skills/background.py blueprint-compliance-summary
PYTHONPATH=src python Skills/background.py record-blueprint-compliance-summary
PYTHONPATH=src python Skills/background.py blueprint-compliance-log-summary
```

The command returns one machine-readable item per blueprint requirement. Each
item has an `id`, `status`, `evidence`, and optional `blocker`. Empty logs mark
run-dependent requirements as `not_applicable`; once a needs-follow-up record
exists, the summary verifies mandatory follow-up tests, report evidence,
uncertainty and limitation language, conservative top-three recommendations,
and the human approval gate. It performs no network access and never enables
external submission.

Persisted compliance snapshots use the same top-level SQLite log:

```bash
PYTHONPATH=src python Skills/background.py record-blueprint-compliance-summary
PYTHONPATH=src python Skills/background.py blueprint-compliance-log-summary
```

This append-only log makes blueprint status auditable across scheduler runs
without contacting external services or changing submission permissions.

## Operations Snapshots

The operations snapshot is the compact operator view for a background cycle:

```bash
PYTHONPATH=src python Skills/background.py operations-snapshot
PYTHONPATH=src python Skills/background.py operator-next-action
PYTHONPATH=src python Skills/background.py record-operations-snapshot
PYTHONPATH=src python Skills/background.py operations-snapshot-log-summary
```

It aggregates the ledger, reviewed and needs-follow-up logs, validation state,
signoff readiness, automation readiness, live dry-run approval status,
blueprint compliance, and live execution attempts into one structured JSON
object. The snapshot also reports a conservative `next_action`, such as
`run_background_once`, `record_signoff`, `review_follow_up`,
`resolve_scheduler_blockers`, or `continue_offline_scheduler`.
Use `operator-next-action` when an operator needs that action translated into
one local command after schema readiness has been checked.

Operations snapshots are no-network review artifacts. They persist to the
top-level SQLite `operations_snapshot_log` table and explicitly keep
`network_access_performed` and `external_submission_enabled` set to `false`.

## Human Signoff

Signoff records are explicit and auditable. They do not submit or contact
external parties. Multiple reviewers may record signoffs for the same run; one
`approved_for_internal_review` record is enough for the signoff-readiness audit
view to report the run as signed. This approval is internal-only: it records
project tracking or follow-up review state, not live-search approval, discovery
confirmation, hazard assessment, external submission permission, or public
communication approval.

Before recording a signoff, generate an internal signoff packet:

```bash
PYTHONPATH=src python Skills/background.py latest-unsigned-signoff-packet
PYTHONPATH=src python Skills/background.py signoff-packet --run-id <run-id>
PYTHONPATH=src python Skills/background.py write-signoff-packet --run-id <run-id>
PYTHONPATH=src python Skills/background.py record-signoff-packet --run-id <run-id>
PYTHONPATH=src python Skills/background.py signoff-packet-log-summary
PYTHONPATH=src python Skills/background.py record-signoff-from-packet --packet-id <packet-id> --reviewer "Reviewer Name" --decision approved_for_internal_review --scope "Internal follow-up only"
PYTHONPATH=src python Skills/background.py signoff-packet-decision-summary
PYTHONPATH=src python Skills/background.py signoff-packet-decision-readiness
PYTHONPATH=src python Skills/background.py latest-undecided-signoff-packet
PYTHONPATH=src python Skills/background.py internal-follow-up-disposition
```

Signoff packets combine run detail, target history, required tests,
recommendations, operations snapshot status, and report readiness into a local
review artifact. Writing or recording a packet does not approve anything,
contact outside parties, enable live network access, or record a signoff
decision. It only prepares evidence for a human reviewer.

When a reviewer is ready to report a result from a persisted packet, record the
decision from the packet rather than manually reconstructing the run metadata:

```bash
PYTHONPATH=src python Skills/background.py signoff-packet-decision-readiness
PYTHONPATH=src python Skills/background.py latest-undecided-signoff-packet

PYTHONPATH=src python Skills/background.py record-signoff-from-packet \
  --packet-id <packet-id> \
  --reviewer "Reviewer Name" \
  --decision approved_for_internal_review \
  --scope "Internal follow-up only" \
  --notes "Reviewed SQLite log, packet, and report draft"

PYTHONPATH=src python Skills/background.py signoff-packet-decision-summary
```

The readiness commands are read-only operator aids. They list persisted packets
that still need packet-linked decisions, separate packets ready for decision
from blocked packets, and expose blockers such as already decided packets,
already signed runs, missing follow-up rows, or missing report files. They do
not write a signoff, write a packet, contact outside parties, enable live
network access, or perform any external submission.

Packet-based decisions validate that the packet exists, the run is still an
unsigned follow-up run, and the packet target still matches the logged
follow-up target. The command writes a normal human signoff plus an auditable
`signoff_packet_decision_log` row, then records a post-decision operations
snapshot. It remains an internal review action only: it does not contact
outside parties, enable live network access, or perform any external
submission, and it does not convert an offline fixture result into a live
survey detection.

After internal review, use `internal-follow-up-disposition` to summarize signed
fixture follow-ups as internal-tracking records. The command is a review-only
operator aid: it does not close a live search, approve discovery or hazard
claims, contact outside parties, or enable external submission.

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
