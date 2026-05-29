# Orbital Elements Reference

Technical reference for orbital elements, derived quantities, NEO class
boundaries, orbit quality codes, MOID, and pipeline module responsibilities.

---

## 1. Classical Orbital Elements

The six Keplerian orbital elements uniquely specify a conic orbit in space.

| Element | Symbol | Units | Convention |
|---------|--------|-------|------------|
| Semi-major axis | a | AU | Positive for elliptic orbits; a > 0 |
| Eccentricity | e | dimensionless | 0 ≤ e < 1 elliptic; e = 1 parabolic; e > 1 hyperbolic |
| Inclination | i | degrees | Angle between orbit and ecliptic plane; 0–180° |
| Longitude of ascending node | Ω (RAAN) | degrees | Angle from vernal equinox to ascending node; 0–360° |
| Argument of perihelion | ω | degrees | Angle from ascending node to perihelion; 0–360° |
| Mean anomaly at epoch | M₀ | degrees | Position along orbit at reference epoch; 0–360° |

All angles are measured in the J2000.0 ecliptic coordinate system unless
otherwise noted.

---

## 2. Derived Quantities

| Quantity | Symbol | Formula | Units |
|----------|--------|---------|-------|
| Perihelion distance | q | q = a(1 − e) | AU |
| Aphelion distance | Q | Q = a(1 + e) | AU |
| Orbital period | T | T = 365.25 × √(a³) | days |
| Longitude of perihelion | ω̄ | ω̄ = Ω + ω | degrees |
| Mean motion | n | n = 360 / T | degrees/day |
| Heliocentric distance | r | r = a(1 − e·cos E) | AU |

Where E is the eccentric anomaly, obtained by solving Kepler's equation:
M = E − e·sin(E).

---

## 3. NEO Dynamical Class Boundaries

Near-Earth Objects (perihelion q < 1.3 AU) are subdivided by semi-major axis
and perihelion/aphelion distance:

| Class | Definition | Condition |
|-------|-----------|-----------|
| Amor | Earth-approaching, exterior | 1.017 < q < 1.3 AU |
| Apollo | Earth-crossing, a > 1 AU | a > 1.0 AU and q < 1.017 AU |
| Aten | Earth-crossing, a < 1 AU | a < 1.0 AU and Q > 0.983 AU |
| IEO (Atira) | Interior Earth orbit | Q < 0.983 AU |

Objects with q ≥ 1.3 AU are Main Belt Asteroids (MBAs) or outer solar system
bodies, not NEOs.  Computed by `classify_neo_class()` in `orbit.py`.

---

## 4. Orbit Quality Codes

| Code | Description | Arc Length |
|------|-------------|------------|
| 1 | Poor — single-night arc | < 1 day |
| 2 | Multi-night arc | 1 day to ~1 week |
| 3 | Multi-week arc | ~1 week to ~3 months |
| 4 | Opposition arc | > ~3 months, includes opposition |

Quality codes are assigned by `arc_quality_report()` in `orbit.py`.  PHA
flagging requires orbit quality ≥ 2.  MPC submission and the NASA alert
pathway require orbit quality ≥ 2.  MOID is considered reliable only for
quality ≥ 2.

---

## 5. MOID and the PHA Threshold

**Minimum Orbit Intersection Distance (MOID)** is the minimum geometric
distance between two orbits (the candidate and Earth's orbit), regardless of
whether the bodies are at those positions simultaneously.

A candidate is flagged as a **Potentially Hazardous Asteroid (PHA)** when:

- MOID ≤ 0.05 AU (approximately 7.5 million km), AND
- Absolute magnitude H ≤ 22 (estimated diameter ≳ 140 m, assuming albedo 0.14)

MOID is computed in `compute_moid()` in `orbit.py` using a numerical
line-of-closest-approach search between the candidate and Earth orbits.

---

## 6. Pipeline Module Responsibilities

| Element / Quantity | Module | Function |
|--------------------|--------|----------|
| a, e, i, Ω, ω, M₀ | `orbit.py` | `fit_orbit()` |
| q (perihelion) | `orbit.py` | `compute_perihelion_distance()` |
| Q (aphelion) | `orbit.py` | `compute_aphelion_distance()` |
| T (period) | `orbit.py` | `compute_orbital_period()` |
| n (mean motion) | `orbit.py` | `compute_mean_motion()` |
| MOID | `orbit.py` | `compute_moid()` |
| NEO class | `orbit.py` | `classify_neo_class()` |
| Orbit quality code | `orbit.py` | `arc_quality_report()` |
| Tisserand parameter | `orbit.py` | `tisserand_parameter()` |
| Hazard flag / PHA | `score.py` | `score()` |
| Alert pathway | `score.py` / `alert.py` | `score()`, `process_alert()` |
| Observation sequence | `link.py` | `link()` |
| Orbital elements schema | `schemas.py` | `OrbitalElements` |
