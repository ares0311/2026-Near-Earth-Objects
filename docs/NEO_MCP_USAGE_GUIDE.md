# NEO MCP Usage Guide

This guide covers the three MCP servers bundled with the NEO Detection Pipeline
and how to use them safely within Claude Code sessions.

---

## Overview

The pipeline ships three MCP servers, configured in `.mcp.json` and described in
`docs/Near_Earth_Objects_MCP_BOOTSTRAP.md`. They are launched automatically when
Claude Code starts a session in this repository.

| Server name        | Purpose                                         |
|--------------------|--------------------------------------------------|
| `neo-project_files`| Bounded file reads inside the project root      |
| `neo-git_read`     | Read-only git inspection (no write operations)  |
| `neo-neo_guard`    | Fixed offline validation and readiness commands |

All three servers run via `Skills/neo_mcp_server.py` with different mode flags.

---

## MCPServerStatus Schema

The `MCPServerStatus` model (added in v0.78.0 to `schemas.py`) captures a
snapshot of a single server's health:

```python
from schemas import MCPServerStatus

status = MCPServerStatus(
    server_name="neo-project_files",
    is_healthy=True,
    tool_count=2,
    offline_mode=True,
)
```

Fields:

| Field         | Type   | Description                                      |
|---------------|--------|--------------------------------------------------|
| `server_name` | `str`  | Logical server name (matches `.mcp.json` key)   |
| `is_healthy`  | `bool` | Whether the server responded to `initialize`    |
| `tool_count`  | `int`  | Number of tools exposed by the server           |
| `offline_mode`| `bool` | `True` when server makes no external network calls |

---

## Server Descriptions

### neo-project_files

Exposes two tools:

- **`list_project_files`** — lists all files in the project matching an optional
  glob pattern (e.g. `"src/*.py"`). Paths outside the project root are rejected.
- **`read_project_file`** — reads a single file by relative path. Path traversal
  (`..`) is blocked; files outside the project root return an error.

Example usage from a Claude Code prompt:

```
Use neo-project_files to list all files in Skills/ and read compute_threat_scores.py
```

### neo-git_read

Exposes five fixed read-only git operations:

| Command          | Description                             |
|------------------|-----------------------------------------|
| `git_status`     | Working tree status                     |
| `git_log`        | Recent commit history (last 20)         |
| `git_diff_staged`| Staged diff                             |
| `git_branch`     | List local branches                     |
| `git_show_head`  | Show the HEAD commit                    |

No write operations (push, commit, reset) are available through this server.

### neo-neo_guard

Exposes fixed offline validation and readiness commands that mirror the
`Skills/background.py` CLI. No network access or external submission is
performed. Available commands:

- `validate_offline` — run offline validation checks
- `readiness_check` — confirm scheduler/policy readiness without going live

---

## Security Model

1. **Path containment**: `neo-project_files` blocks reads outside the project
   root. Symlink traversal is also rejected.
2. **No writes**: Neither `neo-project_files` nor `neo-git_read` can modify
   files or the git repository.
3. **No network**: All three servers are offline-only; they make no external
   HTTP calls during operation.
4. **No impact claims**: The guard server never emits impact probabilities.
   All output defers to MPC/CNEOS per the project guardrails.

---

## Verifying Server Health

To verify all three servers are reachable, send a JSON-RPC `initialize` request:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' \
  | python Skills/neo_mcp_server.py --mode project_files
```

A healthy response contains `"result"` with the server's name and capabilities.
A missing or error response indicates the server is not reachable.

---

## Configuration

Server paths are defined in `.mcp.json`:

```json
{
  "mcpServers": {
    "neo-project_files": {
      "command": ".venv/bin/python",
      "args": ["Skills/neo_mcp_server.py", "--mode", "project_files"]
    },
    "neo-git_read": {
      "command": ".venv/bin/python",
      "args": ["Skills/neo_mcp_server.py", "--mode", "git_read"]
    },
    "neo-neo_guard": {
      "command": ".venv/bin/python",
      "args": ["Skills/neo_mcp_server.py", "--mode", "neo_guard"]
    }
  }
}
```

If the `.venv` interpreter is unavailable, the servers fall back to the system
Python (see `.codex/config.toml` for the Codex equivalent).

---

## Guardrails

- Never use these servers to read credentials or secret files.
- The `neo-project_files` server will deny reads of `.env`, private keys, and
  files outside the project root.
- `neo-neo_guard` output must never be used to assert an impact probability
  without MPC/CNEOS confirmation.
- All alert pathway decisions remain the sole responsibility of the human
  operator following the protocol in `docs/ALERT_PROTOCOL.md`.
