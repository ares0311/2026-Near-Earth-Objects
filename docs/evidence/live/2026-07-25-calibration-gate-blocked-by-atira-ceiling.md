# Coefficient-Fitting Gate Is All-Modes-Joint, Blocked by the Atira Ceiling

Date: 2026-07-25 (America/Los_Angeles)

## Objective

With Aten mode's calibration-eligibility bar closed (57 real positives,
21 real searched-null controls — both ≥20), wire the real exhaustive data
into `Skills/evaluate_field_ranking_policy.py`'s defaults and check whether
coefficient fitting is now authorized.

## Compatibility bug found and fixed

`_load_positive_envelope()` required strict `len(events) == len(selected)`.
This predates `Skills/build_field_ranking_calibration.py`'s PR #270 fix,
which legitimately rejects deterministically-ineligible candidates
(`rejected_ineligible` in `query_log`) and continues rather than aborting
the whole run. The real exhaustive Aten file has 2,109 selected candidates
vs. 2,085 events — 24 real, explained rejections, not a data-integrity
bug. Relaxed the check: a selected candidate missing from `events` is
still accepted, but only if `query_log` explicitly marks it
`rejected_ineligible`; any other gap, or any event not traceable to a
selected candidate, still fails loudly. 3 new tests. Merged as PR #275.

## Real result with the new defaults

```
"coefficient_promotion_gate": {
  "minimum_positive_per_mode": 20,
  "minimum_searched_null_per_mode": 20,
  "observed_counts": {
    "aten": {"positive": 57, "searched_null": 21},
    "ieo":  {"positive": 7,  "searched_null": 3}
  },
  "coefficient_update_authorized": false,
  "decision": "retain_transparent_v2_prior"
}
```

**Aten mode alone now clears both thresholds.** But
`coefficient_update_authorized` is still `false`, because
`build_policy_audit()`'s gate is `all(...)` across *every* mode
(`aten` AND `ieo`), not per-mode independent authorization:

```python
coefficient_update_authorized = all(
    counts["positive"] >= 20 and counts["searched_null"] >= 20
    for counts in source_counts.values()
)
if coefficient_update_authorized:
    raise ValueError("sample gate unexpectedly authorizes an unaudited coefficient fit")
```

The `raise` immediately after is a deliberate tripwire: this function can
never return `coefficient_update_authorized: true` without crashing first,
forcing a human to explicitly edit the code (remove or change the
assertion) once the gate is genuinely met — not something that can happen
silently as a side effect of feeding it more data.

Atira/`ieo` is structurally capped at **7** real I41-attributed positives
(the entire population MPC has ever recorded — 23/23 real Atiras, exhaustively
verified, see `docs/evidence/live/2026-07-24-phase2-aten-exhaustive-calibration-and-null-controls.md`).
It cannot reach 20 unless ZTF discovers more Atiras in the future.

## What this means

**As currently coded, this gate can never authorize fitting for any
mode — including Aten, which already qualifies on its own — until the
Atira ceiling is resolved.** This sharpens the still-open operator
decision flagged in `docs/PRODUCTION_READINESS.md`: it is not just "should
the Atira threshold be revised" in isolation. It is now also "should
coefficient authorization be per-mode independent (so Aten could proceed
without waiting on Atira), or should it stay all-or-nothing across every
mode the policy covers." No code change is proposed here; this evidence
file exists so that decision is made with the real, current picture
rather than an assumption that Aten's threshold closing was sufficient on
its own.

## Exact next work

An explicit operator decision on one of:
1. Revise the Atira ≥20 threshold (e.g. to a number ≤7, or a different
   evidence type for that mode specifically).
2. Change the gate to per-mode independent authorization, so Aten
   coefficients could be fit and reviewed without Atira ever qualifying.
3. Keep the deterministic-transparent-prior policy indefinitely for all
   modes, treating calibration as permanently out of scope for this
   project's sky-coverage pattern.

Until one of these is decided, no further calibration-fitting work should
be attempted — the gate and its tripwire are working exactly as designed.
