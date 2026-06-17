#!/usr/bin/env zsh
# Skills/verify_live_credentials.sh
#
# PURPOSE: Verify that ATLAS and ZTF credentials exist in your macOS Keychain,
# load them into env vars for this shell session, then run a live connection
# test against both APIs and write the result to Logs/reports/live_connection_test.json.
#
# USAGE (run from repo root on your Mac, sourced so exports stay in this shell):
#   source Skills/verify_live_credentials.sh
#
# OUTPUT: Logs/reports/live_connection_test.json
#   Contains pass/fail status and observation counts for ATLAS and ZTF.
#   No credential values are ever written to the output file.
#
# CREDENTIALS: Read from macOS Keychain using the service names registered
# under neo-detection:* — values never leave your Keychain or this shell session.
#
# SAFETY: This file is intended to be sourced. Keep strict shell options local
# to the helper function so a failed downstream command never leaves the
# operator's interactive shell in errexit mode.

_neo_verify_live_credentials_main() {
    emulate -L zsh
    set -uo pipefail

    # ── 1. Load credentials from Keychain into env vars ──────────────────────

    echo "Loading credentials from Keychain..."

    # ATLAS forced-photometry token (required for ATLAS queries)
    export ATLAS_TOKEN=$(security find-generic-password -s "neo-detection:ATLAS_TOKEN" -w 2>/dev/null || true)

    # ZTF/IRSA username and password (required for ZTF full alert stream via ztfquery)
    export ZTF_IRSA_USERNAME=$(security find-generic-password -s "neo-detection:ZTF_IRSA_USERNAME" -w 2>/dev/null || true)
    export ZTF_IRSA_PASSWORD=$(security find-generic-password -s "neo-detection:ZTF_IRSA_PASSWORD" -w 2>/dev/null || true)

    # Report which credentials loaded (presence only — no values printed)
    echo "  ATLAS_TOKEN:       $([ -n "$ATLAS_TOKEN" ]       && echo 'PRESENT' || echo 'MISSING')"
    echo "  ZTF_IRSA_USERNAME: $([ -n "$ZTF_IRSA_USERNAME" ] && echo 'PRESENT' || echo 'MISSING')"
    echo "  ZTF_IRSA_PASSWORD: $([ -n "$ZTF_IRSA_PASSWORD" ] && echo 'PRESENT' || echo 'MISSING')"

    # ── 2. Ensure the output directory exists ────────────────────────────────

    mkdir -p Logs/reports

    # ── 3. Run the live connection test via a Python script ──────────────────
    # Writes JSON to Logs/reports/live_connection_test.json so the coding agent
    # can read the results without ever seeing credential values.

    echo "Running live connection test..."

    if PYTHONPATH=src uv run python Skills/_live_connection_test.py > Logs/reports/live_connection_test.json 2>&1; then
        echo "Done. Results written to Logs/reports/live_connection_test.json"
        cat Logs/reports/live_connection_test.json
        return 0
    fi

    local status=$?
    echo "Live connection test failed. Results written to Logs/reports/live_connection_test.json"
    cat Logs/reports/live_connection_test.json
    return "$status"
}

_neo_verify_live_credentials_main "$@"
_neo_verify_status=$?
unfunction _neo_verify_live_credentials_main 2>/dev/null || true
return "$_neo_verify_status" 2>/dev/null || exit "$_neo_verify_status"
