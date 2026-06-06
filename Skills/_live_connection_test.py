"""
Skills/_live_connection_test.py

PURPOSE: Test live connections to ATLAS and ZTF APIs using credentials
already loaded into environment variables by verify_live_credentials.sh.

OUTPUT: JSON to stdout — pass/fail status and observation counts only.
No credential values are written anywhere.

Called by: Skills/verify_live_credentials.sh
Do not run directly without first loading credentials into the environment.
"""

import json
import os
import sys

# Add src/ to path so pipeline modules are importable
sys.path.insert(0, "src")

results = {}

# ── ATLAS forced-photometry connection test ───────────────────────────────────
# Uses the ATLAS_TOKEN env var loaded from Keychain.
# Queries a small time window around Orion (RA=83.8, Dec=-5.4) as a sanity field.
try:
    from fetch import fetch_atlas_forced  # type: ignore[import]

    atlas_token = os.environ.get("ATLAS_TOKEN")
    if not atlas_token:
        raise ValueError("ATLAS_TOKEN env var is empty — credential not loaded")

    obs = fetch_atlas_forced(
        ra_deg=83.8221,
        dec_deg=-5.3911,
        start_jd=2460700.5,
        end_jd=2460701.5,
        atlas_token=atlas_token,
        force_refresh=True,  # bypass cache so we actually hit the API
    )
    results["atlas"] = {"status": "OK", "n_obs": len(obs)}

except Exception as exc:
    results["atlas"] = {"status": "FAILED", "error": str(exc)}

# ── ZTF alert stream connection test via IRSA ─────────────────────────────────
# Uses ZTF_IRSA_USERNAME / ZTF_IRSA_PASSWORD env vars loaded from Keychain.
# Same Orion field, same time window.
try:
    from fetch import fetch_ztf_alerts  # type: ignore[import]

    obs = fetch_ztf_alerts(
        ra=83.8221,
        dec=-5.3911,
        radius=0.5,
        start_jd=2460700.5,
        end_jd=2460701.5,
        force_refresh=True,  # bypass cache so we actually hit the API
    )
    results["ztf"] = {"status": "OK", "n_obs": len(obs)}

except Exception as exc:
    results["ztf"] = {"status": "FAILED", "error": str(exc)}

# ── Write JSON result to stdout (redirected to file by the shell script) ──────
print(json.dumps(results, indent=2))
