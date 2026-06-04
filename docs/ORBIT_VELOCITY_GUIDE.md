# Orbit Velocity Guide

This document covers orbital velocity helper functions in `orbit.py` (v0.84.0).

---

## Perihelion Velocity

### `compute_perihelion_velocity(elements)` — orbit.py

Speed at perihelion (closest approach to Sun) in km/s using the vis-viva equation:

$$v_q = \sqrt{GM\left(\frac{2}{q} - \frac{1}{a}\right)}$$

where $q = a(1 - e)$ is the perihelion distance in AU.

Returns `None` for invalid elements (non-positive $a$, eccentricity $\geq 1$, missing attributes).

```python
from orbit import compute_perihelion_velocity
from types import SimpleNamespace

elements = SimpleNamespace(a_au=1.5, e=0.3)
v_peri = compute_perihelion_velocity(elements)
# e.g. ~34.8 km/s for a=1.5 AU, e=0.3
```

---

## Aphelion Velocity

### `compute_aphelion_velocity(elements)` — orbit.py

Speed at aphelion (farthest point from Sun) in km/s using the vis-viva equation:

$$v_Q = \sqrt{GM\left(\frac{2}{Q} - \frac{1}{a}\right)}$$

where $Q = a(1 + e)$ is the aphelion distance in AU.

Returns `None` for invalid elements (non-positive $a$, eccentricity $\geq 1$, missing attributes).

For bound orbits ($e < 1$), aphelion velocity is always less than perihelion velocity. Higher eccentricity
produces lower aphelion velocity for a fixed semi-major axis.

```python
from orbit import compute_aphelion_velocity
from types import SimpleNamespace

elements = SimpleNamespace(a_au=1.5, e=0.3)
v_aph = compute_aphelion_velocity(elements)
# e.g. ~18.6 km/s for a=1.5 AU, e=0.3
```

---

## Orbital Velocity (Mean)

### `compute_orbital_velocity(elements)` — orbit.py

Approximate mean orbital speed in km/s using the vis-viva approximation at semi-major axis distance:

$$\bar{v} \approx \sqrt{\frac{GM}{a}}$$

Returns `None` for non-positive $a$ or missing attributes.

---

## Velocity Summary Table

For a typical Apollo-class NEO (a=1.8 AU, e=0.6):

| Quantity | Value |
|---|---|
| Semi-major axis | 1.8 AU |
| Perihelion distance | 0.72 AU |
| Aphelion distance | 2.88 AU |
| Perihelion velocity | ~47 km/s |
| Mean velocity | ~22 km/s |
| Aphelion velocity | ~12 km/s |

---

## Guardrails

Orbital velocity estimates are computed from preliminary orbital elements and carry
significant uncertainty for short arcs. Do not use these values for collision geometry
calculations without confirming the orbit through MPC. Always defer to CNEOS/Scout
for authoritative close-approach velocity estimates.
