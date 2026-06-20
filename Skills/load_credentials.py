#!/usr/bin/env python3
"""Load project credentials from macOS Keychain into environment variables.

Call load_credentials() at the start of any skill that needs live network
access (ATLAS, ZTF/IRSA).  The function reads each secret from the Keychain
service names registered under neo-detection:* and sets the corresponding
environment variable for the current process.  Credential values are never
printed or logged.

Usage as a standalone check:
    uv run python Skills/load_credentials.py

Programmatic usage from another skill:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from load_credentials import load_credentials
    load_credentials()
"""

from __future__ import annotations

import os
import subprocess
import sys


# Mapping of env-var name → Keychain service name
_CREDENTIALS: dict[str, str] = {
    "ATLAS_TOKEN": "neo-detection:ATLAS_TOKEN",
    "ZTF_IRSA_USERNAME": "neo-detection:ZTF_IRSA_USERNAME",
    "ZTF_IRSA_PASSWORD": "neo-detection:ZTF_IRSA_PASSWORD",
}


def _read_keychain(service: str) -> str:
    """Return the secret for *service* from macOS Keychain, or '' on failure."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # strip trailing newline; return empty string if command failed
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def load_credentials(*, silent: bool = False) -> dict[str, bool]:
    """Load all project credentials from Keychain into os.environ.

    Already-set environment variables are overwritten only if the Keychain
    returns a non-empty value, so an existing valid token is never erased.

    Returns a dict mapping each credential name to True (present) / False
    (missing).  Prints a PRESENT/MISSING status line for each credential
    unless *silent* is True.
    """
    status: dict[str, bool] = {}

    for env_var, service in _CREDENTIALS.items():
        # If the variable is already set and non-empty, keep it; otherwise
        # try to load it from Keychain.
        value = os.environ.get(env_var, "").strip()
        if not value:
            value = _read_keychain(service)
        if value:
            os.environ[env_var] = value

        present = bool(os.environ.get(env_var, "").strip())
        status[env_var] = present

        if not silent:
            tag = "PRESENT" if present else "MISSING"
            print(f"  {env_var:<20} {tag}", flush=True)

    return status


def _main() -> int:
    """CLI entry point: load credentials, print status, exit 1 if any missing."""
    print("Loading credentials from Keychain...", flush=True)
    status = load_credentials()

    missing = [k for k, v in status.items() if not v]
    if missing:
        print(f"\nERROR: missing credentials: {', '.join(missing)}", file=sys.stderr)
        return 1

    print("\nAll credentials present.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
