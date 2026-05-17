# Orbit Fitting

Technical reference for the orbit fitting subsystem in `src/orbit.py`.

---

## Overview

Preliminary orbit determination follows a classical two-stage approach:

1. **Initial Orbit Determination (IOD)** via Gauss's method — produces a rough
   Keplerian orbit from three observations spanning a short arc.
2. **Differential Correction (DC)** — iterative least-squares refinement that
   minimises the residuals between the fitted orbit and all available observations.

Both stages operate in heliocentric ecliptic Cartesian coordinates.  All
distances are in AU; velocities in AU/day; angles in degrees unless otherwise
noted.

---

## Stage 1: Gauss's Method

### Input
Three observations, each specified as `(JD, RA_deg, Dec_deg)`.  For arcs
spanning more than three observations, Gauss's method uses the first, middle,
and last observations.

### Algorithm

1. Convert each observation to a heliocentric **direction unit vector** (ρ̂)
   in ecliptic coordinates using a mean-obliquity rotation (ε = 23.439°).

2. Compute the **Sun's geocentric ecliptic position** (R_i) at each epoch
   using a low-precision solar longitude formula accurate to ~0.01°.

3. Form the scalar and vector cross-products that define the Gauss **D matrix**:

   ```
   p_i = ρ̂_j × ρ̂_k   (i ≠ j ≠ k)
   D_ij = R_i · p_j
   D_0 = ρ̂_1 · p_1
   ```

4. Express the topocentric range at the middle epoch (ρ₂) as a function of the
   heliocentric distance r₂ via the Gauss **f-function**:

   ```
   ρ₂ = A + (k²·B) / r₂³
   ```

   where `A` and `B` absorb the time ratios τ₁ = t₁−t₂, τ₃ = t₃−t₂.

5. Solve for r₂ iteratively (Newton iteration from r₂ = 1.5 AU seed):

   ```
   r₂_new = |R₂ + 2ρ₂(ρ̂₂·R₂) + ρ₂²|^(1/2)
   ```

6. Recover heliocentric positions r₁, r₂, r₃ and estimate the velocity at t₂
   via a finite difference:

   ```
   v₂ ≈ (r₃ − r₁) / (t₃ − t₁)
   ```

### Output
A heliocentric state vector `(r₂, v₂)` at the middle epoch.

### Limitations
- Light-travel-time is not corrected; introduces < 1 arcsec error for
  objects < 2 AU from Earth.
- Valid only for arcs < ~30 days; longer arcs require multi-revolution
  disambiguation.
- Hyperbolic (e > 1) solutions are rejected.

---

## State Vector → Keplerian Elements

Given `(r, v)` at epoch JD, the following standard conversion is applied:

| Element | Formula |
|---|---|
| `a` (semi-major axis) | `1 / (2/|r| − v²/k²)` |
| `e` (eccentricity) | `|e_vec|` where `e_vec = (v×h)/k² − r̂` |
| `i` (inclination) | `arccos(h_z / |h|)` |
| `Ω` (longitude of ascending node) | `atan2(N_y, N_x)`, N = ẑ×h |
| `ω` (argument of perihelion) | `arccos(N̂·ê)`, adjusted for sign of e_z |
| `M₀` (mean anomaly) | From eccentric anomaly via Kepler's equation |

`k² = 4π²` AU³/yr² (Gaussian constant); velocities are converted
from AU/day to AU/yr internally.

---

## Stage 2: Differential Correction

Starting from the Gauss IOD, an iterative least-squares loop refines the
six Keplerian elements to minimise residuals across all observations.

### Process

1. **Propagate** the current orbital elements to each observation epoch using
   Keplerian propagation (mean anomaly advance + eccentric anomaly solution).

2. **Compute residuals** between predicted and observed (RA, Dec) for each
   observation.  Residuals are weighted by `1/σ²` where `σ = max(mag_err, 0.5)`
   arcseconds (conservative floor for typical survey astrometry).

3. **Form the partial derivatives** (design matrix `A`) of (RA, Dec) with
   respect to the six initial state components via finite differences (step
   size 1 × 10⁻⁶ AU or AU/day).

4. **Solve the normal equations** `(AᵀWA)Δx = AᵀWr` for the correction vector
   `Δx` using numpy's LU solver.

5. **Apply** Δx and repeat until the RMS residual decreases by less than
   `1 × 10⁻¹⁰` arcseconds or 20 iterations are completed.

### Convergence

Typical residuals after convergence:

| Arc length | Expected RMS (arcsec) |
|---|---|
| < 1 day | ~5–20 (few observations) |
| 1–3 nights | ~1–5 |
| 1+ week | ~0.5–2 |
| 1+ month | ~0.3–1 |

---

## Orbit Quality Codes

| Code | Criterion | Reliability |
|---|---|---|
| 1 | Arc < 1 day; single night | Very poor; MOID unreliable |
| 2 | Multi-night arc (≥ 2 nights) | Orbit class usually correct |
| 3 | Multi-week arc (≥ 7 days) | Elements reliable to ~1% |
| 4 | Opposition coverage (> 30 days) | High-quality orbit |

Code is assigned in `arc_quality_report()` and stored in
`OrbitalElements.quality_code`.

**Never use Code 1 orbits for hazard assessment.**
`_compute_hazard_flag()` in `score.py` requires `quality_code ≥ 2` before
assigning a non-"unknown" hazard flag.

---

## MOID Computation

The Minimum Orbit Intersection Distance (MOID) is the closest approach
between the object's osculating orbit and Earth's orbit, computed using a
grid search over eccentric anomaly:

1. Sample 360 points uniformly in eccentric anomaly E ∈ [0°, 360°).
2. For each point, compute the heliocentric position of the object.
3. Compute the distance to the nearest point on Earth's ellipse
   (parameterised as q_E = 0.9833 AU, Q_E = 1.0167 AU).
4. Refine the minimum with `scipy.optimize.minimize_scalar` (Brent's method)
   around the best seed.

**Short-arc caveat**: For `quality_code = 1` (arc < 1 day), the MOID has
typical uncertainty > 0.1 AU.  The pipeline sets `moid_au = None` in these
cases rather than reporting an unreliable value.

---

## NEO Classification

The dynamical class is determined from osculating orbital elements:

| Class | Condition |
|---|---|
| IEO (Atira) | `Q < 0.983 AU` |
| Aten | `a < 1.0 AU` and `Q ≥ 0.983 AU` |
| Apollo | `a ≥ 1.0 AU` and `q < 1.017 AU` |
| Amor | `1.017 AU ≤ q < 1.3 AU` |
| Unknown | None of the above (likely MBA) |

Both `classify_neo()` (legacy) and `classify_neo_class()` implement this
logic.

---

## Tisserand Parameter

The Tisserand parameter with respect to Jupiter is:

```
T_J = a_J/a + 2·cos(i)·√[(a/a_J)·(1 − e²)]
```

where `a_J = 5.2044 AU`.

| T_J range | Interpretation |
|---|---|
| T_J > 3 | Asteroid-like dynamics |
| 2 < T_J < 3 | Jupiter-family comet regime |
| T_J < 2 | Long-period / Halley-type comet regime |

Use `tisserand_parameter()` and `Skills/check_tisserand.py` to batch-flag
comet-like candidates before MPC submission.

---

## Worked Example

```python
from schemas import Observation
from orbit import fit_orbit, classify_neo_class, compute_moid, tisserand_parameter

obs = (
    Observation(obs_id="a", ra_deg=180.1, dec_deg=0.0, jd=2460000.5,
                mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF"),
    Observation(obs_id="b", ra_deg=180.2, dec_deg=0.1, jd=2460001.5,
                mag=19.4, mag_err=0.05, filter_band="r", mission="ZTF"),
    Observation(obs_id="c", ra_deg=180.3, dec_deg=0.2, jd=2460002.5,
                mag=19.3, mag_err=0.05, filter_band="r", mission="ZTF"),
)

elements = fit_orbit(obs)
if elements is not None:
    print(f"a = {elements.semi_major_axis_au:.3f} AU")
    print(f"e = {elements.eccentricity:.4f}")
    print(f"i = {elements.inclination_deg:.2f} deg")
    print(f"NEO class: {classify_neo_class(elements)}")
    print(f"MOID: {compute_moid(elements)} AU")
    print(f"T_J: {tisserand_parameter(elements):.3f}")
    print(f"Quality code: {elements.quality_code}")
```

Expected output for a typical Apollo-class synthetic track:

```
a = 1.42 AU
e = 0.3120
i = 8.50 deg
NEO class: apollo
MOID: 0.031 AU
T_J: 5.214
Quality code: 2
```

---

## References

- Gauss, C.F. (1809). *Theoria Motus Corporum Coelestium*.
- Escobal, P.R. (1965). *Methods of Orbit Determination*. Krieger.
- Milani, A. & Gronchi, G.F. (2010). *Theory of Orbit Determination*. CUP.
- Sitarski, G. (1998). *Acta Astronomica*, 48, 547 — iterative orbit improvement.
- MPC orbit quality codes: https://minorplanetcenter.net/iau/info/QualityCode.html
