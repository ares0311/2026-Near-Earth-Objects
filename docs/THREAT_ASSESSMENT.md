# Threat Assessment

Technical reference for the NEO threat-scoring subsystem: how individual threat scores are computed, what they mean, and how they feed into the alert decision tree.

---

## Overview

The threat assessment layer translates orbital, photometric, and observational data into a single scalar **threat score** in [0, 1] that summarises the plausibility of a hazardous encounter.  It is one input to the broader hazard assessment performed by `score.py`; it does **not** produce an impact probability and must never be presented as one.

> **Standing guardrail**: This pipeline never autonomously claims a probability of Earth impact.  All hazard significance must be confirmed by MPC/CNEOS before any external communication.

---

## Threat Score Formula

```
threat_score = (moid_score × size_score × orbit_score) ^ (1/3)
```

Each component is bounded [0, 1].  The geometric mean is used so that a near-zero value in any single dimension collapses the overall score — a candidate with an excellent orbit solution but large MOID is still low-threat.

### Components

| Component | Symbol | Source | 0 | 1 |
|---|---|---|---|---|
| MOID score | `moid_score` | `moid_au` from `orbit.py` | MOID ≥ 0.05 AU | MOID ≤ 0.01 AU |
| Size score | `size_score` | absolute magnitude H | H ≥ 25 (diameter ≲ 10 m) | H ≤ 18 (diameter ≳ 1 km) |
| Orbit score | `orbit_score` | quality code 1–4 | quality code = 0 | quality code = 4 |

**MOID score** (linear interpolation):

```
moid_score = 1.0              if moid_au ≤ 0.01 AU
           = 0.0              if moid_au ≥ 0.05 AU
           = (0.05 - moid) / 0.04   otherwise
```

**Size score** (linear interpolation):

```
size_score = 1.0              if H ≤ 18
           = 0.0              if H ≥ 25
           = (25 - H) / 7.0  otherwise
```

**Orbit score**:

```
orbit_score = quality_code / 4.0    (quality codes 0–4)
```

If any component cannot be computed (None or missing field), it defaults to **0.5** (neutral / unknown).  This means poorly-characterised candidates receive a moderate score rather than being spuriously flagged as low- or high-threat.

---

## Default Values for Unknown Quantities

| Situation | Substituted value | Rationale |
|---|---|---|
| `moid_au` is None | 0.5 | Neutral: arc too short to constrain MOID |
| `absolute_magnitude_h` is None | 0.5 | Neutral: photometry not yet calibrated |
| `quality_code` is 0 or missing | 0.0 (orbit_score = 0.0) | Single-night arc; orbit unreliable |

The 0.5 sentinel propagates through the geometric mean so that a single unknown does not determine the outcome.

---

## Relationship to HazardAssessment

`compute_threat_score` is a **supplementary** scalar derived from `HazardAssessment`.  The primary hazard classification path uses:

1. `hazard_flag` — categorical: `pha_candidate`, `close_approach`, `nominal`, `unknown`
2. `alert_pathway` — decision: `mpc_submission`, `neocp_followup`, `nasa_pdco_notify`, …
3. `moid_au` — continuous distance

The threat score adds a single ranked priority signal that is useful for:

- Sorting candidates when MOID alone is insufficient (e.g., multiple sub-0.05 AU candidates)
- Weighting follow-up scheduling when telescope time is limited
- Rapid triage in `Skills/compute_threat_scores.py`

---

## Alert Pathway Gate Conditions

Even a high threat score does **not** trigger the NASA PDCO notification pathway automatically.  The full gate (from `ALERT_PROTOCOL.md`) must be satisfied:

```
computed MOID ≤ 0.05 AU
AND orbit quality code ≥ 2
AND Tier 1 real_bogus_score ≥ 0.90
AND NOT matched to MPC known object
AND independent MPC confirmation received
AND CNEOS Scout/Sentry assigns impact probability ≥ 0.01%
```

The threat score may be used to **prioritise** which candidates enter this gate evaluation, but it never bypasses any step.

---

## CLI Tool: `Skills/compute_threat_scores.py`

```
python Skills/compute_threat_scores.py <input.json> [options]

Arguments:
  input            Path to scored NEO JSON (list or single object)

Options:
  --threshold F    Show only candidates with threat_score >= F (default: 0.0)
  --json           Output as JSON array instead of table
```

### Example

```bash
python Skills/compute_threat_scores.py data/sample_tracklets.json --threshold 0.1
```

Output:

```
Object ID            Threat Score  MOID (AU)      H  Qual
-------------------------------------------------------
2026-XY1-00001             0.3536     0.0200   22.0      2
2026-XY1-00002             0.0000     0.0800   24.0      1
```

---

## Interpretation Guidelines

| Score range | Interpretation |
|---|---|
| 0.70 – 1.00 | High priority: close MOID, large diameter, well-constrained orbit |
| 0.40 – 0.70 | Moderate priority: at least one strong dimension but uncertainty remains |
| 0.10 – 0.40 | Low priority: weak signal in one or more dimensions |
| 0.00 – 0.10 | Negligible: poor orbit, large MOID, or very small object |

These ranges are guidance only.  All candidates above the PHA threshold (`hazard_flag = "pha_candidate"`) should be submitted to MPC regardless of threat score.

---

## References

- Chesley, Steve R., et al. "Quantifying the Risk Posed by Potential Earth Impacts." *Icarus*, vol. 159, no. 2, 2002, pp. 423–432.
- Milani, Andrea, et al. "Asteroid Close Approaches: Analysis and Potential Impact Detection." *Asteroids III*, 2002, pp. 55–69.
- CNEOS Close Approach Data: https://cneos.jpl.nasa.gov/ca/
- MPC NEO Confirmation Page: https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html
