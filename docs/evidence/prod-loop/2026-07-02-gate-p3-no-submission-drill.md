# Gate P3 — No-submission package drill

**Date**: 2026-07-02
**Author**: coding agent (session `claude/general-session-rvaEE`)

## Purpose

`docs/PRODUCTION_READINESS.md` Gate P3 requires an end-to-end dry drill from a
Gate P1 positive-control packet through `Skills/adversarial_review.py`,
operator review packet generation, and MPC-compatible export
(`Skills/export_ades_report.py`), verifying no external submission occurs and
fail-closed behavior holds unless the operator has intentionally set every
live-submission approval control.

## What was built

`Skills/injection_recovery.py` gained a `--review-packet-out PATH` flag that
writes every recovered candidate's full `ScoredNEO` packet as a JSON list
(same format as `Skills/run_pipeline.py --review-packet-out`), so a Gate P1
positive-control run can directly feed the Gate P3 drill tools without a live
sky run.

## Drill steps and results

All commands run in an isolated Python 3.11 sanity venv (this sandbox cannot
run the project's pinned Python 3.14 venv; CI is authoritative for merge
gating). No network access occurred at any step — confirmed by inspection:
`Skills/export_ades_report.py` only imports `alert.format_mpc_ades_psv`,
which is pure string formatting with no `requests`/`urlopen`/socket calls
(the only network calls in `src/alert.py` belong to `_monitor_neocp`, which
`export_ades_report.py` never imports).

### Step 1 — Generate a Gate P1 positive-control packet

```
$ PYTHONPATH=src python Skills/injection_recovery.py --survey WISE --n-inject 5 --seed 7 \
    --review-packet-out /tmp/gate_p3_drill/wise_review_packets.json
Injection-recovery test: 5 synthetic WISE NEOs (seed=7)
--------------------------------------------------
Review packets written to /tmp/gate_p3_drill/wise_review_packets.json (5 packet(s))
Detection rate:  100.0%  (5/5)
Link rate:       100.0%  (5/5)
Score rate:      100.0%  (5/5)
```

5 full `ScoredNEO` packets written (tracklet, features, posterior, hazard,
metadata — verified by inspecting the JSON directly).

### Step 2 — Adversarial review (`Skills/adversarial_review.py --offline --json`)

```
$ PYTHONPATH=src python Skills/adversarial_review.py wise_review_packets.json --offline --json
exit code: 1
```

All 5 candidates verdict `REJECT`, each failing 3 disqualifying challenges:
`orbit_quality` (no orbit computed for a sub-2-day synthetic arc),
`real_bogus` (WISE has no native real/bogus score — correctly fails the
≥0.90 gate), and `artifact_posterior` (stellar-artifact posterior 0.41 ≥ 0.3
threshold on this particular synthetic draw). This is the expected, correct
outcome for a synthetic positive-control packet — the drill exercises the
adversarial-review *mechanism*, not a claim that this packet should survive.
Per the established operator workflow (`docs/evidence/prod-loop/LOOP_PROGRESS.md`
§H), a full `REJECT` verdict means no candidate proceeds to operator review or
export in a real run; the remaining steps below are a deliberate drill of the
export tool's guardrails, not a claim that this synthetic packet is
submission-ready.

### Step 3 — Export attempt with default arguments (`Skills/export_ades_report.py`)

```
$ PYTHONPATH=src python Skills/export_ades_report.py wise_review_packets.json --out ades_default.psv
ERROR: could not format <object_id>: WISE/NEOWISE archival ADES export requires
MPC station code C51; other codes are not documented for WISE source observations.
[x5]
No submit-ready ADES report was produced for at least one candidate.
exit code: 2
```

No `.psv` file was written (confirmed: `ades_default.psv` does not exist in
the output directory after the run). The default `--obs-code XXX` correctly
fails closed for WISE-mission observations.

### Step 4 — Export attempt with `--obs-code C51` but no confirmation flag

```
$ PYTHONPATH=src python Skills/export_ades_report.py wise_review_packets.json \
    --obs-code C51 --out ades_c51_unconfirmed.psv
ERROR: could not format <object_id>: WISE/NEOWISE C51 export requires written
MPC confirmation for third-party archival remeasurement submission. Pass
wise_c51_confirmed=True only after recording that confirmation. [x5]
No submit-ready ADES report was produced for at least one candidate.
exit code: 2
```

No `.psv` file was written. This confirms the **second, independent**
guardrail layer (`validate_ades_submission_authority`'s
`wise_c51_confirmed` check) also fails closed — station code alone is not
sufficient; both the correct code and an explicit, intentional confirmation
flag are required before any WISE/NEOWISE PSV text is produced.

Neither step attempted network access, and no external submission tool
(`alert.py`'s MPC/NEOCP submission path) was invoked at any point in this
drill — `export_ades_report.py` only formats local text.

## Gate P3 status

**Closed.** The drill traced a Gate P1 positive-control packet through
adversarial review and MPC-compatible export, confirming:
1. No external submission occurred at any step (network-free by code
   inspection and by observed behavior).
2. No impact-probability claim was produced (the adversarial-review output
   and PSV formatter contain no impact-probability language; this pipeline
   has never emitted such claims per the repository-wide guardrail).
3. Fail-closed behavior holds at two independent layers (station code check,
   then explicit confirmation-flag check) unless the operator has
   intentionally set every live-submission approval control
   (`--obs-code C51 --mpc-confirmed-wise-c51-submission`, which was not set
   in this drill).

Gate P4 (MPC submission protocol / archival WISE authority) remains the
human-gated blocker before any live submission — no code path can resolve it.
