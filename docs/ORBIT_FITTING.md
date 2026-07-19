# Orbit Fitting

Technical reference for the orbit fitting subsystem in `src/orbit.py`.

---

## Overview

Preliminary orbit determination follows a two-stage bounded fit:

1. **Initial state fit** — deterministic multi-start nonlinear least squares fits
   a six-component heliocentric Cartesian state to all available RA/Dec epochs.
2. **Differential correction** — a second least-squares refinement starts from
   the fitted Keplerian state and records the measured astrometric RMS.

Earth positions come from Astropy's bundled `builtin` ephemeris, so the normal
path is offline and never downloads a remote kernel. Propagation uses a
heliocentric two-body model. Distances are in AU, velocities in AU/day, and
angles in degrees unless otherwise noted.

---

## Stage 1: Initial State Fit

### Input
At least three observations, each specified as `(JD, RA_deg, Dec_deg)`. All
observations are used; duplicate/non-finite time geometry fails explicitly.

### Algorithm

1. Convert RA/Dec to ICRS line-of-sight unit vectors.
2. Obtain Earth-centre heliocentric ICRS positions for every epoch.
3. Seed six range hypotheses (0.1, 0.3, 0.7, 1.5, 3, and 8 AU), with a
   finite-difference velocity at the middle epoch.
4. Propagate each state with deterministic RK4 two-body dynamics and minimize
   tangent-plane RA/Dec residuals with SciPy's bounded TRF least-squares solver.
5. Reject non-finite, hyperbolic, out-of-bounds, or RMS > 5 arcsec solutions;
   retain the physical solution with the smallest measured RMS.

### Output
A heliocentric ecliptic state vector `(r, v)` at the middle epoch, or an
explicit no-solution result. The internal function retains its historical
`_gauss_iod` name for compatibility; it is not the previous scalar Gauss
approximation.

### Limitations
- Light-travel-time, observatory topocentric parallax, non-solar perturbations,
  and measurement covariance weighting are not modeled.
- Sparse short arcs can have multiple admissible range solutions. A low
  residual is necessary but not sufficient for a definitive orbit.
- This is a preliminary internal fit, not an MPC orbit determination.
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

Starting from the initial solution, the fitter converts the elements back to a
Cartesian state and reruns the same bounded astrometric least-squares problem.

### Process

1. Propagate the heliocentric state to each observation epoch.
2. Compute tangent-plane RA/Dec residuals in arcseconds.
3. Let SciPy's TRF solver refine all six state components within explicit
   position and velocity bounds.
4. Convert the refined state back to Keplerian elements and store the measured
   RMS in `fit_residual_arcsec`.

### Convergence

`fit_orbit()` returns `None` unless it has at least three observations, finds a
bound elliptic solution, and measures RMS ≤ 5 arcsec. Callers persist the
reason separately as `HazardAssessment.orbit_fit_status`.

---

## Project Arc-Quality Tiers

| Tier | Criterion | Meaning |
|---|---|---|
| 0 | Not assessed | No arc assessment recorded |
| 1 | Arc < 1 day | Insufficient temporal leverage |
| 2 | 1 to < 7 days | Short multi-night arc |
| 3 | 7 to < 30 days | Multi-week arc |
| 4 | ≥ 30 days | Opposition-scale arc |

The tier is assigned in `arc_quality_report()` whether or not a physical orbit
fits. It is stored as `HazardAssessment.arc_quality_tier`; a successful fit also
copies the tier to `OrbitalElements.quality_code` for compatibility.

This is a project arc-sufficiency tier, **not** the MPC `U` uncertainty
parameter. Arc tier and fit success are deliberately separate: a three-night,
six-day tracklet is tier 2 even when `orbit_fit_status == "no_solution"`.

**Never use Tier 1 orbits for hazard assessment.**
`_compute_hazard_flag()` in `score.py` requires a fitted quality tier ≥ 2 before
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

**Short-arc caveat**: The pipeline returns no MOID when there is no accepted
orbital solution. An internal MOID must never be presented as an authoritative
impact or hazard assessment; MPC/CNEOS remain authoritative.

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
from schemas import Observation, Tracklet
from orbit import fit_orbit, classify_neo_class, compute_moid, tisserand_parameter

obs = (
    Observation(obs_id="a", ra_deg=180.1, dec_deg=0.0, jd=2460000.5,
                mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF"),
    Observation(obs_id="b", ra_deg=180.2, dec_deg=0.1, jd=2460001.5,
                mag=19.4, mag_err=0.05, filter_band="r", mission="ZTF"),
    Observation(obs_id="c", ra_deg=180.3, dec_deg=0.2, jd=2460002.5,
                mag=19.3, mag_err=0.05, filter_band="r", mission="ZTF"),
)

tracklet = Tracklet(
    object_id="example",
    observations=obs,
    arc_days=2.0,
    motion_rate_arcsec_per_hour=15.0,
    motion_pa_degrees=45.0,
)
elements = fit_orbit(tracklet)
if elements is not None:
    print(f"a = {elements.semi_major_axis_au:.3f} AU")
    print(f"e = {elements.eccentricity:.4f}")
    print(f"i = {elements.inclination_deg:.2f} deg")
    print(f"NEO class: {classify_neo_class(elements)}")
    print(f"MOID: {compute_moid(elements)} AU")
    print(f"T_J: {tisserand_parameter(elements):.3f}")
    print(f"Quality code: {elements.quality_code}")
```

The illustrative coordinates above are not guaranteed to admit a physical
solution; production callers must handle `None` and preserve `orbit_fit_status`.

---

## References

- Gauss, C.F. (1809). *Theoria Motus Corporum Coelestium*.
- Escobal, P.R. (1965). *Methods of Orbit Determination*. Krieger.
- Milani, A. & Gronchi, G.F. (2010). *Theory of Orbit Determination*. CUP.
- Sitarski, G. (1998). *Acta Astronomica*, 48, 547 — iterative orbit improvement.
- Astropy solar-system ephemerides: `astropy.coordinates.get_body_barycentric_posvel`
- SciPy bounded nonlinear least squares: `scipy.optimize.least_squares`
