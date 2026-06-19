# MCP Bootstrapper — Near-Earth Object Detection and Ranking

> **Use:** Place this file at the repository root as `MCP_BOOTSTRAP.md` or keep this descriptive filename and instruct the coding agent to read it immediately after `AGENTS.md`.
>
> **Purpose:** Give Claude Code and Codex enough repo-local instructions to generate safe, project-scoped MCP configuration files for the NEO project without using manual application settings as the source of truth.

---

## 1. Objective

Bootstrap a conservative, project-scoped MCP setup for the **Near-Earth Object Detection and Ranking Pipeline**.

The rollout must generate, validate, and hand off these files:

```text
.mcp.json
.codex/config.toml
```

This repository has planetary-defense-adjacent workflows. MCP must therefore be stricter than ordinary scientific-code tooling. It may help agents inspect files, inspect git state, run fixed local validation commands, and produce internal readiness summaries. It must not allow autonomous impact claims, external alerting, live provider access by default, NASA/MPC escalation, or credential exposure.

This file is the source-of-truth rollout instruction. The generated config files are implementation artifacts derived from this policy.

---

## 2. Required Reading Before Any Change

Before creating or modifying MCP config, read these files in this order:

```text
AGENTS.md
README.md
docs/PIPELINE_SPEC.md
docs/DATA_SOURCES.md
docs/DECISIONS.md
CONTRIBUTING.md
pyproject.toml
```

If a listed file is missing, record the missing file in the rollout handoff and continue only if the remaining files are sufficient to preserve safety.

Do not rely on chat history, prior memory, or unstated assumptions as the source of truth.

---

## 3. Existing Project Constraints To Preserve

The MCP rollout must preserve the repository's standing rules:

- Python 3.11+.
- Package: `neo-detection`.
- Pipeline: `Fetch → Preprocess → Detect → Link → Classify → Score → Alert`.
- Standalone utility scripts belong in `Skills/`.
- Never assert an Earth-impact probability from internally computed data alone.
- Always defer authoritative hazard assessment to MPC/CNEOS.
- Never trigger the NASA/MPC alert pathway on unconfirmed detections.
- Independent confirmation is required before any escalation.
- Never publicly announce or quote impact probabilities.
- Default tests must exclude `integration_live`.
- Tokens and passwords must stay outside git.
- Live dry-run and readiness commands are offline/mock by default unless explicitly approved.

---

## 4. Files To Generate Or Update

Generate or conservatively merge the following files:

```text
.mcp.json
.codex/config.toml
```

Create parent directories as needed.

If either file already exists:

1. Read it fully.
2. Preserve unrelated existing servers and comments where possible.
3. Do not overwrite existing user configuration.
4. Add only the NEO project MCP entries required by this bootstrap.
5. If merge safety is uncertain, stop and write a clear handoff instead of replacing the file.

Do not modify `AGENTS.md` unless the human explicitly asks.

---

## 5. MCP Server Design

Configure only a small, conservative MCP set.

### 5.1 Required Server: Project Files

Purpose:

- Read project files.
- Inspect docs, source, tests, schemas, fixtures, configs, and Skills.
- Limit file access to this repository root.

Rules:

- Repository-root scope only.
- No access to parent directories.
- No access to global home directories.
- No access to `.venv/`, `.env`, `data/`, `logs/`, `artifacts/`, large caches, credential files, or generated outputs unless the current human task explicitly requires read-only inspection.
- Never expose token values, password values, Keychain exports, or credential file contents.

### 5.2 Required Server: Git Read / Limited Git

Purpose:

- Inspect `git status`, diffs, branches, and recent history.
- Help avoid overwriting unrelated user changes.

Allowed operations:

```text
git status --short --branch
git diff
git diff --staged
git log --oneline --decorate -n 20
git branch --show-current
```

Forbidden operations through MCP unless the human explicitly approves in the current task:

```text
git push
git push --force
git push --force-with-lease
git reset --hard
git clean -fd
git checkout -- .
git rebase
git merge
git tag
git remote set-url
```

### 5.3 Required Server: `neo_guard`

Create or configure a narrow local validation guard named:

```text
neo_guard
```

The guard must expose fixed commands only. It must not provide arbitrary shell access.

Allowed `neo_guard` commands:

```bash
ruff check .
python -m mypy src
PYTHONPATH=src python -m pytest
OMP_NUM_THREADS=1 PYTHONPATH=src python -m pytest
python Skills/smoke_test.py
python Skills/diagnose_pipeline.py
python Skills/background.py automation-readiness
python Skills/background.py live-credential-inventory
python Skills/background.py live-dry-run-plan
```

The following are allowed only when they remain mock-only / no-network as documented by the repository and the command output confirms no external submission and no network access:

```bash
python Skills/background.py live-dry-run-execute
python Skills/background.py record-live-dry-run-plan
```

If any command would contact ZTF, ATLAS, MPC, JPL Horizons, CNEOS, Gaia, or another external provider, stop and request human approval before proceeding.

### 5.4 Optional Server: GitHub Read-Only

Configure GitHub MCP only if credentials are already available through the approved local mechanism and the human has authorized GitHub access for the task.

Allowed:

- Read issues.
- Read pull requests.
- Read workflow status.
- Read repository metadata.

Forbidden unless explicitly approved:

- Opening or editing public hazard alerts.
- Publishing reports.
- Creating releases.
- Editing branch protections.
- Deleting branches.
- Force-pushing.
- Writing secrets.
- Submitting observations to MPC.
- Notifying NASA PDCO, IAU CBAT, or any external party.

---

## 6. Forbidden MCP Capabilities

Do not configure MCP tools that allow:

- arbitrary shell execution;
- unrestricted filesystem access;
- package installation without approval;
- credential reading, printing, exporting, or modification;
- live ZTF, ATLAS, MPC, JPL Horizons, CNEOS, Gaia, Pan-STARRS, or MAST access by default;
- MPC observation submission;
- NEOCP follow-up escalation;
- NASA PDCO notification;
- public impact-probability statements;
- changing live-policy files to approved without explicit human approval;
- editing `background/live_review_policy.example.json` to bypass or dilute
  human approval, rate limits, no-submission guardrails, or no-impact-claim
  guardrails;
- external submission enablement;
- bypassing failing tests;
- editing hazard thresholds without a documented decision;
- committing `.venv/`, caches, raw survey data, SQLite runtime logs, generated reports, credential inventories containing values, or API tokens.

---

## 7. Live Network And Alert Policy

Default MCP operation is offline.

Live network access is allowed only when all of the following are true:

1. The current human task explicitly asks for live access.
2. The provider is named: ZTF, ATLAS, MPC, JPL Horizons, CNEOS, Gaia, Pan-STARRS, or another specific source.
3. The sky region, time range, survey scope, and rate limits are bounded.
4. The live review policy is contract-valid and explicitly approved by a human.
5. Credentials are referenced by environment variable or macOS Keychain service name only.
6. No external submission is enabled.
7. No impact probability is stated unless quoted from an authoritative MPC/CNEOS source and the user explicitly requested that authoritative status.

MCP must never turn readiness checks or dry-run plans into live provider calls by silently changing config.

---

## 8. Secrets And Credentials Policy

Never store secrets in:

```text
.mcp.json
.codex/config.toml
AGENTS.md
MCP_BOOTSTRAP.md
docs/
tests/
background/*.example.json
```

Allowed credential reference patterns:

```text
env:ATLAS_TOKEN
env:ZTF_IRSA_USERNAME
env:ZTF_IRSA_PASSWORD
env:MAST_API_TOKEN
macOS Keychain service: neo-detection:ATLAS_TOKEN
macOS Keychain service: neo-detection:ZTF_IRSA_USERNAME
macOS Keychain service: neo-detection:ZTF_IRSA_PASSWORD
macOS Keychain service: neo-detection:MAST_API_TOKEN
```

The `live-credential-inventory` command may report credential presence booleans and source names. It must never print token values.

If a credential is required but absent, report the missing credential name and stop that live-network step. Do not prompt the agent to paste secrets into chat.

---

## 9. Generated Configuration Requirements

### 9.1 Claude Code: `.mcp.json`

Generate project-scoped Claude Code MCP configuration in:

```text
.mcp.json
```

Requirements:

- Keep server scope project-local.
- Use environment-variable references for secrets.
- Prefer stdio transports for local guard servers.
- Include only the approved servers from this file.
- Avoid global, user-home, or parent-directory file access.
- Do not include any server that can execute arbitrary shell commands.
- Include comments only if the target format supports them; JSON generally does not.

After writing `.mcp.json`, tell the human that Claude Code may require a one-time project trust / MCP approval prompt before using the servers.

### 9.2 Codex: `.codex/config.toml`

Generate project-scoped Codex MCP configuration in:

```text
.codex/config.toml
```

Requirements:

- Use project-local MCP server entries.
- Keep secrets out of TOML; use environment-variable references only.
- Do not modify global `~/.codex/config.toml`.
- Do not assume application UI settings are the source of truth.
- If Codex CLI syntax has changed, consult current local help or official docs and record any deviation in the handoff.

---

## 10. Validation Procedure

Run the safest available checks in this order:

```bash
git status --short --branch
python --version
ruff check .
python -m mypy src
PYTHONPATH=src python -m pytest
python Skills/smoke_test.py
python Skills/diagnose_pipeline.py
python Skills/background.py automation-readiness
python Skills/background.py live-credential-inventory
python Skills/background.py live-dry-run-plan
```

Do not run live-network tests during bootstrap.

Do not submit observations.

Do not notify NASA, MPC, IAU CBAT, CNEOS, or any external party.

If any validation fails:

1. Do not hide the failure.
2. Record the exact command and failure summary.
3. Fix only failures directly caused by the MCP bootstrap changes.
4. If the failure predates the bootstrap or is unrelated, report it as an existing blocker.

---

## 11. Acceptance Criteria

The rollout is complete only when all of the following are true:

- `.mcp.json` exists or an existing file was safely merged.
- `.codex/config.toml` exists or an existing file was safely merged.
- Configured MCP servers are limited to project files, safe git inspection, and fixed validation/readiness commands.
- No arbitrary shell MCP is configured.
- No secrets are present in config files.
- No live network access is enabled by default.
- No live-policy file has been changed to approved.
- No external submission path is enabled.
- No impact-probability claim is generated.
- Default validation commands have been run or blockers are documented.
- The handoff states whether Claude Code and Codex require a one-time trust/approval action.
- No candidate, hazard, alert, or external-submission status has been changed by this rollout.

---

## 12. Handoff Format

At the end, report:

```text
MCP Bootstrap Handoff — Near-Earth Objects

Files created/modified:
- ...

Servers configured:
- ...

Validation run:
- command: PASS/FAIL/SKIPPED — note

Live network status:
- disabled by default

External alert status:
- MPC submission disabled
- NASA/PDCO notification disabled
- no impact probability generated

Secrets status:
- no secrets stored in repo config

Human actions required:
- approve Claude Code project MCP config if prompted
- trust Codex project config if prompted
- provide any needed credentials through environment variables or Keychain only
- explicitly approve any live network test or external submission separately

Known blockers:
- ...
```

Do not claim the repository is ready for live planetary-defense operations, hazard notification, or external submission merely because MCP bootstrap succeeded.
