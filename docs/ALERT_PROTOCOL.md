# Alert Protocol

Technical reference for the NEO pipeline alert-pathway decision tree, gate
conditions, MPC submission format, NEOCP monitoring, and NASA PDCO notification.

---

## Overview

The pipeline never autonomously asserts a probability of Earth impact.  The
alert pathway is a **mandatory, ordered gate** — no step may be skipped.  All
external actions require independent confirmation from the MPC before proceeding
to NASA notification.

```
Candidate passes all preconditions?
         │
         ▼
Step 1 ── Submit observations to MPC
         │
         ▼
Step 2 ── Monitor NEOCP ≥ 24 h or ≥ 2 confirmations
         │
         ▼
Step 3 ── CNEOS Scout/Sentry assigns P_impact ≥ 0.01%?
         │
         ▼
         Open [HAZARD-ALERT] issue + notify NASA PDCO / IAU CBAT
```

---

## Gate Conditions (`ready_for_submission`)

All four conditions must pass before any external report is generated.
`alert.ready_for_submission(neo)` returns `(True, [])` only when all gates
clear; otherwise it returns `(False, [list of unmet conditions])`.

| Gate | Condition | Rationale |
|---|---|---|
| MOID | `moid_au ≤ 0.05 AU` | Below PHA threshold; only plausible hazards are escalated |
| Orbit quality | `quality_code ≥ 2` | Multi-night arc required; single-night orbits are too uncertain |
| Real/bogus | `real_bogus_score ≥ 0.90` | Eliminates the majority of instrumental artifacts |
| Known object | `alert_pathway ≠ "known_object"` | Already catalogued by MPC; no new report needed |

```python
from alert import ready_for_submission

ready, unmet = ready_for_submission(neo)
if not ready:
    print("Not ready:", unmet)
```

---

## Alert Pathways

| Pathway | Trigger | Action |
|---|---|---|
| `internal_candidate` | Does not pass all gates | Store locally; flag for follow-up |
| `neocp_followup` | Object on NEOCP; needs confirmation | Request observations via `format_neocp_report` |
| `mpc_submission` | Passes all gates; not yet confirmed | Submit via `format_mpc_report` or `format_mpc_json` |
| `nasa_pdco_notify` | MPC confirmed + CNEOS P_impact ≥ 0.01% | Generate alert package; notify PDCO and IAU CBAT |
| `known_object` | Matches MPC catalog within 5 arcsec | No action; log match |

---

## Step 1: MPC Submission

### 80-Column Format

```python
from alert import format_mpc_report

report = format_mpc_report(neo, obs_code="F51")
# POST to https://www.minorplanetcenter.net/cgi-bin/submit_obs.cgi
# or email to obs@minorplanetcenter.net
```

The 80-column record layout (per MPC Circular):

```
Cols  1– 5  Packed provisional designation
Col   6     Discovery asterisk (*)
Col   7     Note 1 (blank)
Col   8     Note 2 (C = CCD)
Cols  9–14  Second designation / blank
Cols 15–32  Date (YYYY MM DD.ddddd)
Cols 33–44  RA  HH MM SS.ddd
Cols 45–56  Dec ±DD MM SS.dd
Cols 65–70  Magnitude
Col  71     Band (g/r/i/o/c)
Cols 78–80  Observatory code
```

### JSON Format (modern)

```python
from alert import format_mpc_json

payload = format_mpc_json(neo, obs_code="F51")
# POST as JSON to https://minorplanetcenter.net/mpc-new-obs-format
```

### Validation

Before submitting, validate the 80-column file:

```bash
python Skills/validate_mpc_report.py report.txt
python Skills/validate_mpc_report.py report.txt --json
```

---

## Step 2: NEOCP Monitoring

After MPC submission, the object should appear on the NEOCP within minutes.
Poll for independent confirmation:

```python
from alert import monitor_neocp

monitor_neocp(
    designation=neo.tracklet.object_id,
    timeout_hours=48,
    poll_interval_s=3600,
)
```

The pipeline waits for **at least 2 independent observatory confirmations** or
24 hours before escalating.  `monitor_neocp` is injectable for testing (pass a
`sleep_fn` argument).

---

## Step 3: NASA PDCO Notification

This step is triggered only when CNEOS Scout or Sentry assigns an impact
probability ≥ 0.01% to a pipeline-submitted object.  The pipeline does **not**
compute impact probabilities — it reads the Scout/Sentry output.

```python
from alert import process_alert, generate_alert_package

# cneos_assessment is a dict from Scout/Sentry API output
package = generate_alert_package(neo, cneos_assessment=cneos_assessment)
process_alert(neo, cneos_assessment=cneos_assessment)
```

Recipients:
- **NASA PDCO**: https://www.nasa.gov/planetarydefense/contact
- **IAU CBAT**: https://www.cbat.eps.harvard.edu/

**Never quote an impact probability in any public output.**
Defer all public communication to NASA/CNEOS.

---

## Discovery Circular

For objects confirmed by MPC that merit a formal discovery announcement,
generate an IAU CBET-style discovery circular:

```python
from alert import format_discovery_circular

text = format_discovery_circular(neo)
# Human-review required before submission
```

The circular includes object ID, discovery epoch, RA/Dec, magnitude, orbital
elements, NEO class, estimated diameter, and MOID.  All fields marked
`[FILL IN]` must be completed by the reporting astronomer.

---

## Follow-Up Requests

Generate NEOCP follow-up request files for candidates needing confirmation:

```bash
python Skills/export_followup_requests.py data/candidates.json \
    --min-priority 0.5 --out-dir requests/ --obs-code F51
```

---

## Audit Trail

Every alert action is logged with full provenance to `alert_logs/`:

```json
{
  "timestamp_utc": "2026-05-17T03:00:00+00:00",
  "object_id": "2026 AA1",
  "alert_pathway": "mpc_submission",
  "action": "mpc_submitted",
  "scorer_version": "0.18.0",
  "pipeline_run_id": "run-001",
  "neo_candidate_probability": 0.82,
  "hazard_flag": "pha_candidate",
  "moid_au": 0.031,
  "orbit_quality": 3,
  "n_observations": 12,
  "arc_days": 14.2
}
```

Log files are named `alert_{object_id}_{date}.json` and are never overwritten.

---

## Guardrails Summary

- **Never skip** MPC submission and independent confirmation before Step 3
- **Never quote** an impact probability in any public output
- **Never suppress** a genuine alert out of uncertainty — report and let
  authorities assess
- **Never trigger** Step 3 on unconfirmed pipeline detections alone
- **Always store** full provenance (observations, orbit fit, MOID computation)
  with every alert action

---

## References

- MPC Observation Format: https://minorplanetcenter.net/iau/info/OpticalObs.html
- MPC JSON Format: https://minorplanetcenter.net/mpc-new-obs-format
- CNEOS Scout: https://cneos.jpl.nasa.gov/scout/
- CNEOS Sentry: https://cneos.jpl.nasa.gov/sentry/
- NASA PDCO: https://www.nasa.gov/planetarydefense/
- IAU CBAT: https://www.cbat.eps.harvard.edu/
- IAU Minor Planet Circular format: https://minorplanetcenter.net/iau/info/MPCircular.html
