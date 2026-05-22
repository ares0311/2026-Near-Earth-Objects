# ORBIT_DYNAMICS.md — Orbital Dynamics Reference

Technical reference for the orbital mechanics used in the NEO Detection Pipeline.
Covers mean motion, synodic vs sidereal period, resonance detection, longitude of
perihelion, and the eccentric/true anomaly relationship.

---

## 1. Mean Motion

### Definition

Mean motion $n$ is the average angular velocity of a body on a Keplerian orbit,
measured in degrees per day (or radians per unit time):

$$n = \frac{360°}{T}$$

where $T$ is the **sidereal orbital period** in days.

### Relationship to Semi-Major Axis

By Kepler's third law, $T^2 \propto a^3$.  For heliocentric orbits in AU and days:

$$T = 365.25\,\sqrt{a^3} \quad \text{[days]}$$

$$n = \frac{360°}{365.25\,\sqrt{a^3}} \quad \text{[deg/day]}$$

Examples:

| Body         | $a$ (AU) | $T$ (days) | $n$ (deg/day) |
|---|---|---|---|
| Earth        | 1.000    | 365.25     | 0.9856        |
| Mars         | 1.524    | 686.97     | 0.5240        |
| Apophis      | 0.922    | 323.6      | 1.113         |
| Bennu        | 1.126    | 436.6      | 0.825         |

### Implementation

```python
from orbit import compute_mean_motion
n = compute_mean_motion(elements)   # deg/day; raises ValueError for a ≤ 0
```

Mean motion is used to propagate mean anomaly:
$$M(t) = M_0 + n \cdot \Delta t$$

---

## 2. Sidereal vs Synodic Period

### Sidereal Period

The **sidereal period** $T_\text{sid}$ is the time for one complete orbit relative to
the fixed stars — the true orbital period of the object:

$$T_\text{sid} = 365.25 \sqrt{a^3} \quad \text{[days]}$$

### Synodic Period

The **synodic period** $T_\text{syn}$ is the time between successive **oppositions**
(or conjunctions) as seen from Earth.  It depends on the difference in mean motions
between the object and Earth ($n_\oplus = 0.9856$ deg/day):

$$\frac{1}{T_\text{syn}} = \left| \frac{1}{T_\text{sid}} - \frac{1}{T_\oplus} \right|$$

For objects with $a > 1$ AU (exterior):
$$T_\text{syn} = \frac{T_\text{sid} \cdot T_\oplus}{T_\text{sid} - T_\oplus}$$

For objects with $a < 1$ AU (interior):
$$T_\text{syn} = \frac{T_\text{sid} \cdot T_\oplus}{T_\oplus - T_\text{sid}}$$

Special cases:
- $a = 1$ AU: $T_\text{syn} = \infty$ (co-orbital with Earth)
- $a \to 0$: $T_\text{syn} \to T_\oplus = 365.25$ days

### Implementation

```python
from orbit import compute_synodic_period
T_syn = compute_synodic_period(elements)  # days; inf for a = 1 AU or a ≤ 0
```

Synodic period determines the **observation window** for each apparition.  Short
synodic periods mean frequent return opportunities; long periods mean rare windows.

---

## 3. Resonance Detection

### Tisserand Parameter

The Tisserand parameter $T_J$ relative to Jupiter is an approximately conserved
quantity under the restricted three-body approximation:

$$T_J = \frac{a_J}{a} + 2\sqrt{\frac{a}{a_J}(1-e^2)}\cos(i)$$

where $a_J = 5.2$ AU is Jupiter's semi-major axis, $e$ is eccentricity, and $i$
is orbital inclination.

Dynamical significance:

| $T_J$ range | Classification |
|---|---|
| $T_J > 3$   | Asteroid-like; cometary origin unlikely |
| $2 < T_J < 3$ | Jupiter-family comet (JFC) dynamical class |
| $T_J < 2$   | Long-period or Halley-type comet regime |

### Mean-Motion Resonances

An object in a **p:q mean-motion resonance** with Jupiter completes $p$ orbits for
every $q$ Jupiter orbits.  The resonant semi-major axis satisfies:

$$\frac{T_\text{asteroid}}{T_J} = \frac{q}{p}$$

Since $T \propto a^{3/2}$:

$$a_\text{res} = a_J \cdot \left(\frac{q}{p}\right)^{2/3}$$

Common NEO-relevant resonances:

| Resonance | $a$ (AU) | Notes |
|---|---|---|
| 3:1       | 2.50     | Kirkwood gap; Mars-crosser source |
| 5:2       | 2.82     | Strong Kirkwood gap |
| 7:3       | 2.96     | Moderate Kirkwood gap |
| 2:1       | 3.28     | Hecuba gap |
| 1:1       | 5.20     | Trojans (co-orbital with Jupiter) |

### Implementation

```python
from orbit import resonance_check
label = resonance_check(elements, tolerance=0.02)  # e.g. "3:1" or None
```

Resonance checking computes $T_\text{asteroid}/T_J$ and compares to $q/p$ for a
set of candidate integer pairs $(p, q)$ with $p \leq 8$, $q \leq 8$.

---

## 4. Longitude of Perihelion

The **longitude of perihelion** $\varpi$ combines the longitude of the ascending
node $\Omega$ and the argument of perihelion $\omega$:

$$\varpi = \Omega + \omega$$

This is the angle (measured in the ecliptic plane then in the orbital plane) from
the vernal equinox to the direction of perihelion.

Useful for:
- Secular perturbation theory (apsidal precession rate $\dot{\varpi}$)
- Apsidal alignment in resonant pairs (e.g. the $\nu_6$ secular resonance)
- Identifying families of objects with common perihelia directions

For NEOs, rapid $\dot{\varpi}$ precession reduces the MOID over time and can
cause otherwise non-threatening objects to evolve into Earth-crossing orbits.

---

## 5. Eccentric and True Anomaly Relationship

### Eccentric Anomaly

The **eccentric anomaly** $E$ is an auxiliary angle that parameterizes position on
an elliptical orbit.  It is related to the **mean anomaly** $M$ via Kepler's equation:

$$M = E - e \sin(E)$$

Kepler's equation is transcendental in $E$ and is solved iteratively (Newton-Raphson):

$$E_{n+1} = E_n + \frac{M - E_n + e \sin(E_n)}{1 - e \cos(E_n)}$$

Convergence is guaranteed for $e < 1$ (elliptic orbits); typically $< 10$ iterations
to machine precision.

```python
from orbit import compute_eccentric_anomaly
E_rad = compute_eccentric_anomaly(M_rad, e)  # raises ValueError for e ≥ 1
```

### True Anomaly

The **true anomaly** $\nu$ is the actual angle between the object and perihelion,
measured at the focus.  It is related to $E$ via the half-angle formula:

$$\tan\!\left(\frac{\nu}{2}\right) = \sqrt{\frac{1+e}{1-e}} \tan\!\left(\frac{E}{2}\right)$$

Or equivalently:

$$\nu = 2 \arctan\!\left(\sqrt{\frac{1+e}{1-e}} \tan\!\frac{E}{2}\right) \pmod{2\pi}$$

True anomaly ranges over $[0, 2\pi)$ for a complete orbit.

```python
from orbit import compute_true_anomaly
nu_rad = compute_true_anomaly(E_rad, e)  # raises ValueError for e ≥ 1
```

### Heliocentric Distance from True Anomaly

Once $\nu$ is known, the heliocentric distance $r$ follows from the conic section
equation:

$$r = \frac{a(1 - e^2)}{1 + e\cos(\nu)}$$

At perihelion ($\nu = 0$): $r = q = a(1-e)$
At aphelion ($\nu = \pi$): $r = Q = a(1+e)$

### Summary of Anomaly Conversions

```
Mean anomaly M  ──(Kepler's equation)──►  Eccentric anomaly E
                                                  │
                                    (half-angle formula)
                                                  │
                                                  ▼
                                         True anomaly ν
                                                  │
                                          (conic section)
                                                  │
                                                  ▼
                                    Heliocentric distance r
```

---

## See Also

- `docs/ORBIT_FITTING.md` — Gauss method, differential correction, MOID
- `docs/SCORING_MODEL_V2.md` — Threat scoring using orbital elements
- `src/orbit.py` — All orbit-related functions with full docstrings
