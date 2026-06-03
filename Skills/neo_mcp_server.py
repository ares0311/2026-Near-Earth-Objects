#!/usr/bin/env python3
"""Project-scoped MCP guard server for the NEO detection repository.

The server intentionally exposes only narrow, repo-local tools:

- read-only project file listing/reading with generated-output and secret paths denied
- read-only git inspection commands
- fixed validation/readiness commands from the MCP bootstrap

It is not a general shell and it does not enable live provider access.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 200_000
MAX_TOOL_OUTPUT_BYTES = 200_000

DENIED_PARTS = {
    ".git",
    ".venv",
    ".env",
    ".neo_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "Logs",
    "logs",
    "artifacts",
    "data",
    "models",
    "results",
    "reports",
}
DENIED_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".npz",
    ".npy",
    ".pt",
    ".pth",
    ".pkl",
}
ALLOWED_HIDDEN_FILES = {".mcp.json"}
ALLOWED_HIDDEN_PATHS = {Path(".codex/config.toml")}

GIT_COMMANDS: dict[str, list[str]] = {
    "status_short_branch": ["git", "status", "--short", "--branch"],
    "diff": ["git", "diff"],
    "diff_staged": ["git", "diff", "--staged"],
    "log_recent": ["git", "log", "--oneline", "--decorate", "-n", "20"],
    "branch_current": ["git", "branch", "--show-current"],
}

GUARD_COMMANDS: dict[str, tuple[list[str], dict[str, str]]] = {
    "ruff_check": (["ruff", "check", "."], {}),
    "mypy_src": (["python", "-m", "mypy", "src"], {}),
    "pytest": (["python", "-m", "pytest"], {"PYTHONPATH": "src"}),
    "pytest_omp": (
        ["python", "-m", "pytest"],
        {"OMP_NUM_THREADS": "1", "PYTHONPATH": "src"},
    ),
    "smoke_test": (["python", "Skills/smoke_test.py"], {}),
    "diagnose_pipeline": (["python", "Skills/diagnose_pipeline.py"], {}),
    "automation_readiness": (
        ["python", "Skills/background.py", "automation-readiness"],
        {},
    ),
    "live_credential_inventory": (
        ["python", "Skills/background.py", "live-credential-inventory"],
        {},
    ),
    "live_dry_run_plan": (
        ["python", "Skills/background.py", "live-dry-run-plan"],
        {},
    ),
    "live_dry_run_execute_mock": (
        ["python", "Skills/background.py", "live-dry-run-execute"],
        {},
    ),
    "record_live_dry_run_plan": (
        ["python", "Skills/background.py", "record-live-dry-run-plan"],
        {},
    ),
}
NO_NETWORK_GUARD_COMMANDS = {"live_dry_run_execute_mock", "record_live_dry_run_plan"}


def _python_executable() -> str:
    local_python = REPO_ROOT / ".venv" / "bin" / "python"
    if local_python.exists():
        return str(local_python)
    return "python"


def _ruff_executable() -> str:
    local_ruff = REPO_ROOT / ".venv" / "bin" / "ruff"
    if local_ruff.exists():
        return str(local_ruff)
    return "ruff"


def _effective_command(command: list[str]) -> list[str]:
    if command[0] == "python":
        return [_python_executable(), *command[1:]]
    if command[0] == "ruff":
        return [_ruff_executable(), *command[1:]]
    return command


def _relative_path(path_value: str) -> Path:
    candidate = Path(path_value)
    if candidate.is_absolute():
        raise ValueError("absolute paths are not allowed")
    normalized = Path(*candidate.parts)
    if ".." in normalized.parts:
        raise ValueError("parent-directory traversal is not allowed")
    return normalized


def _is_denied_path(relative: Path) -> bool:
    if relative in ALLOWED_HIDDEN_PATHS or relative.name in ALLOWED_HIDDEN_FILES:
        return False
    if any(part in DENIED_PARTS for part in relative.parts):
        return True
    if any(part.startswith(".") for part in relative.parts):
        return True
    if relative.suffix in DENIED_SUFFIXES:
        return True
    lowered = str(relative).lower()
    sensitive_terms = ("password", "passwd", "token", "secret", "credential")
    return any(term in lowered for term in sensitive_terms)


def _resolve_allowed(path_value: str) -> Path:
    relative = _relative_path(path_value)
    if _is_denied_path(relative):
        raise ValueError(f"path is denied by MCP project-file policy: {relative}")
    resolved = (REPO_ROOT / relative).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise ValueError("resolved path escaped repository root")
    if not resolved.is_file():
        raise ValueError(f"path is not a regular file: {relative}")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"file exceeds {MAX_FILE_BYTES} byte MCP read limit: {relative}")
    return resolved


def _tool_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _json_tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    return _tool_result(json.dumps(payload, indent=2, sort_keys=True), is_error=is_error)


def list_project_files(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit", 200))
    if limit < 1 or limit > 1_000:
        raise ValueError("limit must be between 1 and 1000")
    files: list[str] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if _is_denied_path(relative):
            continue
        files.append(str(relative))
        if len(files) >= limit:
            break
    return _json_tool_result({"repo_root": str(REPO_ROOT), "files": files, "limit": limit})


def read_project_file(args: dict[str, Any]) -> dict[str, Any]:
    path_value = str(args.get("path", ""))
    if not path_value:
        raise ValueError("path is required")
    start_line = int(args.get("start_line", 1))
    max_lines = int(args.get("max_lines", 200))
    if start_line < 1:
        raise ValueError("start_line must be at least 1")
    if max_lines < 1 or max_lines > 2_000:
        raise ValueError("max_lines must be between 1 and 2000")
    path = _resolve_allowed(path_value)
    relative = path.relative_to(REPO_ROOT)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    start_index = start_line - 1
    selected = lines[start_index : start_index + max_lines]
    return _json_tool_result(
        {
            "path": str(relative),
            "start_line": start_line,
            "line_count": len(selected),
            "total_lines": len(lines),
            "text": "".join(selected),
        }
    )


def _run_fixed_command(command: list[str], env_updates: dict[str, str]) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(env_updates)
    env["NEO_MCP_OFFLINE_DEFAULT"] = "1"
    completed = subprocess.run(
        _effective_command(command),
        cwd=REPO_ROOT,
        env=env,
        check=False,
        text=True,
        capture_output=True,
        timeout=300,
    )
    stdout = completed.stdout[-MAX_TOOL_OUTPUT_BYTES:]
    stderr = completed.stderr[-MAX_TOOL_OUTPUT_BYTES:]
    return {
        "returncode": completed.returncode,
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_git_read(args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("command", ""))
    if name not in GIT_COMMANDS:
        raise ValueError(f"unsupported git read command: {name}")
    result = _run_fixed_command(GIT_COMMANDS[name], {})
    return _json_tool_result(result, is_error=result["returncode"] != 0)


def _assert_no_network_output(command_name: str, result: dict[str, Any]) -> None:
    combined = f"{result['stdout']}\n{result['stderr']}".lower()
    no_network_markers = (
        '"network_access_performed": false',
        "'network_access_performed': false",
        "network_access_performed=false",
        "no network access",
        "no-network",
    )
    no_submission_markers = (
        '"external_submission_enabled": false',
        "'external_submission_enabled': false",
        "external_submission_enabled=false",
        "no external submission",
        "no-submission",
    )
    if not any(marker in combined for marker in no_network_markers):
        raise ValueError(f"{command_name} output did not confirm no network access")
    if not any(marker in combined for marker in no_submission_markers):
        raise ValueError(f"{command_name} output did not confirm no external submission")


def run_guard_command(args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("command", ""))
    if name not in GUARD_COMMANDS:
        raise ValueError(f"unsupported guard command: {name}")
    command, env_updates = GUARD_COMMANDS[name]
    result = _run_fixed_command(command, env_updates)
    if result["returncode"] == 0 and name in NO_NETWORK_GUARD_COMMANDS:
        _assert_no_network_output(name, result)
    return _json_tool_result(result, is_error=result["returncode"] != 0)


PROJECT_FILE_TOOLS = [
    {
        "name": "list_project_files",
        "description": (
            "List readable repository files excluding generated outputs, caches, "
            "data, logs, and credential paths."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 1000}},
            "additionalProperties": False,
        },
    },
    {
        "name": "read_project_file",
        "description": "Read one approved repository text file by relative path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "max_lines": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]

GIT_TOOLS = [
    {
        "name": "git_read",
        "description": "Run one fixed read-only git inspection command.",
        "inputSchema": {
            "type": "object",
            "properties": {"command": {"type": "string", "enum": sorted(GIT_COMMANDS)}},
            "required": ["command"],
            "additionalProperties": False,
        },
    }
]

GUARD_TOOLS = [
    {
        "name": "run_guard_command",
        "description": (
            "Run one fixed offline validation or readiness command from the MCP bootstrap."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"command": {"type": "string", "enum": sorted(GUARD_COMMANDS)}},
            "required": ["command"],
            "additionalProperties": False,
        },
    }
]

TOOLS_BY_SERVER = {
    "project_files": PROJECT_FILE_TOOLS,
    "git_read": GIT_TOOLS,
    "neo_guard": GUARD_TOOLS,
}


def _dispatch_tool(server: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if server == "project_files":
        if name == "list_project_files":
            return list_project_files(args)
        if name == "read_project_file":
            return read_project_file(args)
    if server == "git_read" and name == "git_read":
        return run_git_read(args)
    if server == "neo_guard" and name == "run_guard_command":
        return run_guard_command(args)
    raise ValueError(f"tool is not available on {server}: {name}")


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _handle_request(server: str, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    if request_id is None and str(method).startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            return _response(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": f"neo-{server}", "version": "1.0.0"},
                },
            )
        if method == "ping":
            return _response(request_id, {})
        if method == "tools/list":
            return _response(request_id, {"tools": TOOLS_BY_SERVER[server]})
        if method == "tools/call":
            tool_name = str(params.get("name", ""))
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
            return _response(request_id, _dispatch_tool(server, tool_name, arguments))
        return _error_response(request_id, -32601, f"method not found: {method}")
    except Exception as exc:
        return _error_response(request_id, -32000, str(exc))


def serve(server: str) -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = _handle_request(server, request)
        except Exception as exc:
            response = _error_response(None, -32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, choices=sorted(TOOLS_BY_SERVER))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return serve(args.server)


if __name__ == "__main__":
    raise SystemExit(main())
