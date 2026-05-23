# Orbital Mechanics Reference

Technical reference for the orbital mechanics functions implemented in `orbit.py`.

---

## Overview

`orbit.py` provides a suite of analytical and numerical tools for computing orbital
elements, ephemerides, and derived quantities from preliminary orbit solutions.
All functions accept an `elements` object (or `SimpleNamespace`) with fields
matching the `OrbitalElements` schema.

---

## Fundamental Quantities

### Semi-Major Axis (`a`)

The semi-major axis `a` (AU) defines the size of the orbit. It determines the
orbital energy and period via Kepler's third law.

- Elliptical orbit: `a > 0`
- Parabolic orbit: `a → ∞` (not supported; use `e < 1` guard)
- Hyperbolic orbit: `a < 0`

### Orbital Elements

| Field | Symbol | Units | Description |
|---|---|---|---|
| `semi_major_axis_au` | `a` | AU | Orbit size |
| `eccentricity` | `e` | — | Shape (`0`=circle, `<1`=ellipse) |
| `inclination_deg` | `i` | degrees | Tilt relative to ecliptic |
| `lon_ascending_node_deg` | `Ω` | degrees | Ascending node longitude |
| `arg_perihelion_deg` | `ω` | degrees | Argument of perihelion |
| `mean_anomaly_deg` | `M₀` | degrees | Mean anomaly at epoch |
| `epoch_jd` | `t₀` | JD | Reference epoch |
| `quality_code` | — | 1–4 | Orbit quality (arc coverage) |

---

## Anomaly Calculations

### Mean Anomaly at a Target JD

```python
from orbit import compute_mean_anomaly_at_jd

M_rad = compute_mean_anomaly_at_jd(elements, target_jd)
```

Returns the mean anomaly in radians ∈ [0, 2π) at `target_jd`.

The mean anomaly advances linearly in time:

```
n = 2π / T   (mean motion, rad/day)
M = M₀ + n·(t - t₀)   mod 2π
```

where `T` is the orbital period and `M₀` is the mean anomaly at epoch.

Returns `None` for non-positive semi-major axis or zero/negative period.

### Eccentric Anomaly

```python
from orbit import compute_eccentric_anomaly

E_rad = compute_eccentric_anomaly(M_rad, e)
```

Solves Kepler's equation `M = E - e·sin(E)` iteratively via Newton–Raphson:

```
E_{n+1} = E_n - (E_n - e·sin(E_n) - M) / (1 - e·cos(E_n))
```

Raises `ValueError` for `e ≥ 1` (hyperbolic orbits) or failure to converge
within `max_iter` steps. Default tolerance: `1e-12` rad.

### True Anomaly

```python
from orbit import compute_true_anomaly

f_rad = compute_true_anomaly(E_rad, e)
```

Converts eccentric anomaly to true anomaly via the half-angle formula:

```
tan(f/2) = sqrt((1+e)/(1-e)) · tan(E/2)
```

Returns true anomaly in [0, 2π). Raises `ValueError` for `e ≥ 1`.

---

## Vis-Viva Equation and Orbital Velocity

### Orbital Speed at a Heliocentric Distance

```python
from orbit import compute_orbital_velocity

v_km_s = compute_orbital_velocity(elements, r_au)
```

Computes the orbital speed at heliocentric distance `r_au` using the vis-viva
equation:

```
v² = GM☉ · (2/r − 1/a)
```

where:
- `GM☉ = 1.327124400 × 10²⁰ m³/s²`
- `r` = heliocentric distance in metres
- `a` = semi-major axis in metres

Returns speed in km/s, or `None` if `a ≤ 0`, `r ≤ 0`, or `v² < 0`.

**Key physical insight:** At the same heliocentric distance `r`, a larger
semi-major axis `a` results in a *higher* orbital speed (the `−1/a` term
becomes less negative, increasing `v²`). This counterintuitive result follows
because objects on larger orbits have more total energy for the same `r`.

**Examples:**

| Object | `a` (AU) | `r` (AU) | `v` (km/s) |
|---|---|---|---|
| Earth | 1.00 | 1.00 | ~29.8 |
| Apollo NEO | 1.50 | 1.00 | ~34.3 |
| Aten NEO | 0.80 | 0.80 | ~36.4 |

### Perihelion Velocity

The maximum orbital speed is reached at perihelion (`r = q = a(1 − e)`):

```
v_peri² = GM☉ · (2/q − 1/a)
```

For an Earth-crossing Apollo with `a = 1.5 AU`, `e = 0.6`:
- `q = 0.60 AU` → `v_peri ≈ 46 km/s`

---

## Orbital Period

```python
from orbit import compute_orbital_period

T_days = compute_orbital_period(elements)
```

Kepler's third law:

```
T = 365.25 · √(a³)   days
```

Returns `None` for `a ≤ 0`. For reference: Earth's period is 365.25 days
(`a = 1.0 AU`).

---

## Synodic Period

```python
from orbit import compute_synodic_period

P_syn_days = compute_synodic_period(elements)
```

Time between successive oppositions with Earth:

```
1/P_syn = |1/P_obj − 1/P_Earth|
```

Returns `inf` for `a = 1.0 AU` (no oppositions). Short synodic periods
indicate frequent observing windows; long periods mean rare opportunities.

---

## Mean Anomaly at Epoch

```python
from orbit import compute_mean_anomaly_at_jd

M_rad = compute_mean_anomaly_at_jd(elements, target_jd=2460000.5)
```

The mean anomaly at epoch is stored in `elements.mean_anomaly_deg`. This
function propagates it forward (or backward) in time to a target JD.

---

## Perihelion Date

```python
from orbit import compute_perihelion_date

t_peri_jd = compute_perihelion_date(elements)
```

Computes the next perihelion passage JD from the current mean anomaly and
orbital period. Returns `None` for hyperbolic orbits or non-positive periods.

```
t_peri = t₀ + (2π − M₀) / n   if M₀ > 0
t_peri = t₀ − M₀ / n           if M₀ = 0 (at perihelion)
```

---

## Heliocentric Distance

```python
from orbit import compute_heliocentric_distance

r_au = compute_heliocentric_distance(elements, target_jd)
```

Propagates the orbit to `target_jd` and returns the heliocentric distance.
Returns `inf` for non-positive `a`; `NaN` on numerical error.

---

## Phase Angle

```python
from orbit import compute_phase_angle

phase_deg = compute_phase_angle(elements, target_jd)
```

Sun–target–observer phase angle in degrees via the law of cosines:

```
cos(α) = (r² + Δ² − R²) / (2rΔ)
```

where `r` = heliocentric distance, `Δ` = geocentric distance,
`R` = 1 AU (Earth's distance from Sun).

Returns `NaN` for degenerate geometry.

---

## Absolute Magnitude

```python
from orbit import compute_absolute_magnitude

H = compute_absolute_magnitude(observed_mag, r_au, delta_au, phase_deg, g=0.15)
```

Reduces an apparent magnitude to absolute magnitude using the IAU HG phase
function. Returns `NaN` for degenerate geometry (zero distances or invalid
phase angles).

---

## MOID Computation

```python
from orbit import compute_moid

moid_au = compute_moid(elements)
```

Minimum Orbit Intersection Distance relative to Earth's orbit. The MOID is
used to classify Potentially Hazardous Asteroids (PHAs):

- PHA condition: `MOID ≤ 0.05 AU` **AND** `H ≤ 22`

MOID is unreliable for short arcs (quality code 1, arc < 1 day). Flag
accordingly and require multi-night coverage before reporting.

---

## NEO Dynamical Classification

```python
from orbit import classify_neo_class

neo_class = classify_neo_class(elements)
```

Assigns an NEO dynamical class from orbital elements:

| Class | Condition |
|---|---|
| Amor | `1.017 < q < 1.3 AU` |
| Apollo | `a > 1.0 AU`, `q < 1.017 AU` |
| Aten | `a < 1.0 AU`, `Q > 0.983 AU` |
| IEO (Atira) | `Q < 0.983 AU` |
| MBA | `q > 1.3 AU` |
| Unknown | Insufficient elements |

where `q = a(1 − e)` is perihelion distance and `Q = a(1 + e)` is aphelion
distance.

---

## Tisserand Parameter

```python
from orbit import tisserand_parameter

T_J = tisserand_parameter(elements)
```

The Tisserand parameter relative to Jupiter:

```
T_J = a_J/a + 2·cos(i)·√(a/a_J · (1 − e²))
```

where `a_J = 5.2 AU`. Objects with `T_J < 3` are considered comet-like.
Typical values:

| Population | `T_J` range |
|---|---|
| Jupiter-family comets | 2 < T_J < 3 |
| Long-period comets | T_J < 2 |
| Near-Earth asteroids | T_J > 3 |
| Main-belt asteroids | 3 < T_J < 5 |

---

## Resonance Detection

```python
from orbit import resonance_check

label = resonance_check(elements, tolerance=0.01)
```

Checks for mean-motion resonances with Jupiter by comparing orbital period
ratios `T_obj / T_Jupiter` against integer p:q pairs. Common resonances
checked include 3:1, 5:2, 7:3, 2:1 (Kirkwood gaps) and 3:2, 4:3 (resonant
groups).

Returns a resonance label string (e.g. `"3:1"`) or `None` if no resonance
detected within `tolerance`.

---

## Orbit Quality Codes

| Code | Arc Length | Reliability |
|---|---|---|
| 1 | < 1 day | MOID unreliable; no PHA flag |
| 2 | Multi-night | Preliminary; suitable for MPC submission |
| 3 | Multi-week | Good; suitable for close approach table |
| 4 | Opposition | High confidence; full hazard assessment |

MOID and close approach distances are only reported for quality code ≥ 2.
PHA flags require quality code ≥ 2 (see Alert Protocol).

---

## Ephemeris Prediction

```python
from orbit import predict_ephemeris, batch_predict_ephemeris

pos = predict_ephemeris(elements, target_jd)
positions = batch_predict_ephemeris(elements_list, target_jd)
```

Propagates the orbit to `target_jd` via Keplerian two-body motion and returns
geocentric RA, Dec, and distance. Uses `astropy` for coordinate transforms.

Sky-plane uncertainty is estimated from the quality code:

| Quality | σ (1 day propagation) | σ (30 day propagation) |
|---|---|---|
| 1 | ~10 arcsec | ~300 arcsec |
| 2 | ~1 arcsec | ~30 arcsec |
| 3 | ~0.1 arcsec | ~3 arcsec |
| 4 | ~0.01 arcsec | ~0.3 arcsec |

---

## Orbital Energy

```python
from orbit import orbital_energy

E = orbital_energy(elements)   # AU² / yr²
```

Specific orbital energy:

```
E = −GM☉ / (2a)
```

- `E < 0`: bound orbit (ellipse)
- `E = 0`: parabolic escape
- `E > 0`: hyperbolic (interstellar object)

Returns `inf` for `a ≤ 0`.

---

## See Also

- `docs/ALERT_PROTOCOL.md` — hazard gate conditions and MOID thresholds
- `docs/THREAT_ASSESSMENT.md` — threat score computation
- `docs/SCORING_MODEL_V2.md` — size estimate and close-approach score
- `Skills/compute_orbital_velocity.py` — batch orbital velocity CLI
- `Skills/compute_eccentric_anomaly.py` — batch eccentric anomaly CLI
- `Skills/compute_true_anomaly.py` — batch true anomaly CLI
- `Skills/check_tisserand.py` — Tisserand parameter and comet-like flag
- `Skills/ephemeris_check.py` — sky position prediction table
