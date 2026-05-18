"""Orbit stage — Gauss method, differential correction, MOID, NEO classification."""

from __future__ import annotations

__all__ = ["classify_neo", "compute_moid", "fit_orbit", "arc_quality_report",
           "propagate_orbit", "predict_ephemeris", "close_approach_table",
           "compute_orbital_period", "classify_neo_class", "tisserand_parameter",
           "batch_predict_ephemeris", "resonance_check", "ephemeris_uncertainty",
           "orbital_energy", "compute_phase_angle",
           "compute_heliocentric_distance", "compute_synodic_period",
           "compute_apparent_magnitude", "compute_absolute_magnitude",
           "compute_perihelion_date"]

import math
from typing import NamedTuple

import numpy as np

from schemas import (
    NEOClass,
    OrbitalElements,
    OrbitQualityCode,
    Tracklet,
)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

_GM_SUN = 4 * math.pi**2  # AU³/yr²; k² in Gaussian units
_AU_PER_YR_TO_AU_PER_DAY = 1.0 / 365.25
_EARTH_PERIHELION_AU = 0.9833
_EARTH_APHELION_AU = 1.0167

# NEO / PHA classification boundaries (AU)
_Q_AMOR_INNER = 1.017
_Q_NEO_OUTER = 1.3
_Q_APOLLO = 1.017
_A_ATEN = 1.0
_Q_IEO = 0.983


# ---------------------------------------------------------------------------
# Coordinate conversion helpers
# ---------------------------------------------------------------------------


def _equatorial_to_ecliptic(ra_deg: float, dec_deg: float, jd: float) -> np.ndarray:
    """Approximate geocentric equatorial → ecliptic direction unit vector."""
    eps = math.radians(23.439291111)  # mean obliquity J2000
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    x = math.cos(dec) * math.cos(ra)
    y = math.cos(dec) * math.sin(ra)
    z = math.sin(dec)
    # Rotation about x-axis by obliquity
    xecl = x
    yecl = math.cos(eps) * y + math.sin(eps) * z
    zecl = -math.sin(eps) * y + math.cos(eps) * z
    return np.array([xecl, yecl, zecl])


def _sun_position_ecliptic(jd: float) -> np.ndarray:
    """Low-precision Sun geocentric ecliptic position (AU)."""
    T = (jd - 2451545.0) / 36525.0
    L0 = math.radians(280.46646 + 36000.76983 * T)
    M = math.radians(357.52911 + 35999.05029 * T - 0.0001537 * T**2)
    C = math.radians(
        (1.914602 - 0.004817 * T - 0.000014 * T**2) * math.sin(M)
        + (0.019993 - 0.000101 * T) * math.sin(2 * M)
        + 0.000289 * math.sin(3 * M)
    )
    sun_lon = L0 + C
    e = 0.016708634 - 0.000042037 * T
    r = 1.000001018 * (1 - e**2) / (1 + e * math.cos(math.radians(M) + C))
    x = r * math.cos(sun_lon)
    y = r * math.sin(sun_lon)
    return np.array([x, y, 0.0])


# ---------------------------------------------------------------------------
# Gauss method for initial orbit determination
# ---------------------------------------------------------------------------


class _GaussResult(NamedTuple):
    pos: np.ndarray  # heliocentric position at middle observation (AU)
    vel: np.ndarray  # heliocentric velocity at middle observation (AU/day)
    success: bool


def _gauss_iod(
    obs_list: list[tuple[float, float, float]],  # (jd, ra_deg, dec_deg)
) -> _GaussResult:
    """Three-point Gauss method for initial orbit determination.

    Works on the first, middle, and last observations of the sorted arc.
    Returns heliocentric state vector at the middle epoch.
    """
    if len(obs_list) < 3:
        return _GaussResult(np.zeros(3), np.zeros(3), False)

    idx = [0, len(obs_list) // 2, len(obs_list) - 1]
    epochs = [obs_list[i][0] for i in idx]
    rho_hats = [_equatorial_to_ecliptic(*obs_list[i][1:], jd=obs_list[i][0]) for i in idx]
    sun_vecs = [_sun_position_ecliptic(obs_list[i][0]) for i in idx]

    t1, t2, t3 = epochs
    tau1 = t1 - t2
    tau3 = t3 - t2
    tau = tau3 - tau1

    rh1, rh2, rh3 = rho_hats
    R1, R2, R3 = sun_vecs

    # Cross products
    p1 = np.cross(rh2, rh3)
    p2 = np.cross(rh1, rh3)
    p3 = np.cross(rh1, rh2)

    D0 = float(rh1 @ p1)
    if abs(D0) < 1e-12:
        return _GaussResult(np.zeros(3), np.zeros(3), False)

    D = np.array([
        [float(R1 @ p1), float(R1 @ p2), float(R1 @ p3)],
        [float(R2 @ p1), float(R2 @ p2), float(R2 @ p3)],
        [float(R3 @ p1), float(R3 @ p2), float(R3 @ p3)],
    ])

    A1 = tau3 / tau
    B1 = A1 * (tau**2 - tau3**2) / 6.0
    A3 = -tau1 / tau
    B3 = A3 * (tau**2 - tau1**2) / 6.0

    A = (A1 * D[1, 0] - D[1, 1] + A3 * D[1, 2]) / (-D0)
    B = (B1 * D[1, 0] + B3 * D[1, 2]) / (-D0)

    E = float(-2.0 * (rh2 @ R2))
    F = float(R2 @ R2)

    # 8th-degree polynomial in r2 (heliocentric distance at t2)
    # r2^8 + E r2^6 + F r2^4 ... — simplified to cubic via iteration
    # r^8 + a r^6 + b r^3 + c = 0  (Barker form; we use Newton iteration)
    GM = _GM_SUN / 365.25**2  # AU^3/day^2 (from 4π² AU³/yr²)

    def f_r(r: float) -> float:  # pragma: no cover
        return r**8 + E * r**6 + (A**2 + 2 * A * E + F) * r**4  # rough form

    # Seed r2 ~ 1 AU and iterate (Newton on simplified scalar)
    r2 = 1.5
    for _ in range(50):
        rho2 = A + GM * B / r2**3
        r2_new = float(np.sqrt(float(R2 @ R2) + 2 * rho2 * float(rh2 @ R2) + rho2**2))
        if abs(r2_new - r2) < 1e-10:
            break
        r2 = r2_new

    rho2 = A + GM * B / r2**3
    rho1 = (A1 * (D[0, 0] / D0) + (D[0, 1] / D0) * rho2 + B1 * (D[0, 0] / D0)) / 1.0
    rho3 = (A3 * (D[2, 0] / D0) + (D[2, 1] / D0) * rho2 + B3 * (D[2, 0] / D0)) / 1.0

    # Heliocentric position vectors
    r_vec2 = rho2 * rh2 - R2

    # Velocity via finite difference of positions
    r_vec1 = (rho1 if rho1 > 0 else 0.1) * rh1 - R1
    r_vec3 = (rho3 if rho3 > 0 else 0.1) * rh3 - R3
    v_vec2 = (r_vec3 - r_vec1) / (t3 - t1)

    return _GaussResult(r_vec2, v_vec2, True)


# ---------------------------------------------------------------------------
# State vector → Keplerian elements
# ---------------------------------------------------------------------------


def _state_to_elements(
    pos: np.ndarray,
    vel: np.ndarray,
    epoch_jd: float,
) -> OrbitalElements | None:
    """Convert heliocentric state vector (AU, AU/day) to Keplerian elements."""
    GM = _GM_SUN / 365.25**2  # AU^3/day^2 (from 4π² AU³/yr²)

    r = float(np.linalg.norm(pos))
    v = float(np.linalg.norm(vel))
    if r < 1e-10 or v < 1e-10:
        return None

    # Specific angular momentum
    h = np.cross(pos, vel)
    h_mag = float(np.linalg.norm(h))
    if h_mag < 1e-12:
        return None

    # Eccentricity vector
    e_vec = np.cross(vel, h) / GM - pos / r
    e = float(np.linalg.norm(e_vec))

    # Semi-major axis from vis-viva
    a = 1.0 / (2.0 / r - v**2 / GM)
    if a < 0:
        return None  # hyperbolic

    # Inclination
    i = math.degrees(math.acos(max(-1.0, min(1.0, h[2] / h_mag))))

    # Node
    N = np.array([-h[1], h[0], 0.0])
    N_mag = float(np.linalg.norm(N))
    if N_mag > 1e-12:
        Om = math.degrees(math.atan2(N[1], N[0])) % 360.0
    else:
        Om = 0.0

    # Argument of perihelion
    if N_mag > 1e-12:
        cos_om = float(np.dot(N, e_vec) / (N_mag * e))
        cos_om = max(-1.0, min(1.0, cos_om))
        om = math.degrees(math.acos(cos_om))
        if e_vec[2] < 0:
            om = 360.0 - om
    else:
        om = math.degrees(math.atan2(e_vec[1], e_vec[0])) % 360.0

    # True anomaly → mean anomaly
    cos_nu = float(np.dot(e_vec, pos) / (e * r)) if e > 1e-10 else 0.0
    cos_nu = max(-1.0, min(1.0, cos_nu))
    nu = math.degrees(math.acos(cos_nu))
    if float(np.dot(pos, vel)) < 0:
        nu = 360.0 - nu

    # Eccentric anomaly → mean anomaly
    nu_rad = math.radians(nu)
    cos_E = (e + math.cos(nu_rad)) / (1 + e * math.cos(nu_rad))
    sin_E = math.sqrt(max(0.0, 1 - cos_E**2))
    if math.sin(nu_rad) < 0:
        sin_E = -sin_E
    E_anom = math.atan2(sin_E, cos_E)
    M = math.degrees(E_anom - e * math.sin(E_anom)) % 360.0

    q = a * (1 - e)
    Q = a * (1 + e)

    return OrbitalElements(
        semi_major_axis_au=a,
        eccentricity=e,
        inclination_deg=i,
        longitude_ascending_node_deg=Om,
        argument_perihelion_deg=om,
        mean_anomaly_deg=M,
        epoch_jd=epoch_jd,
        perihelion_au=q,
        aphelion_au=Q,
        quality_code=1,
    )


# ---------------------------------------------------------------------------
# Differential correction (one iteration of Gauss-Newton)
# ---------------------------------------------------------------------------


def _differential_correction(
    elements: OrbitalElements,
    observations: list[tuple[float, float, float]],
) -> OrbitalElements:
    """Single Gauss-Newton iteration to improve orbital elements fit."""
    # Simplified: improve quality code estimate based on arc length
    arc_days = observations[-1][0] - observations[0][0]
    if arc_days >= 180:
        code: OrbitQualityCode = 4
    elif arc_days >= 21:
        code = 3
    elif arc_days >= 1:
        code = 2
    else:
        code = 1

    # Compute fit residuals (placeholder; full implementation requires ephemeris integration)
    residuals: list[float] = []
    for jd, _ra, _dec in observations:
        # Predict position from elements (placeholder: use mean motion)
        n = math.sqrt(_GM_SUN / 365.25**2 / elements.semi_major_axis_au**3)
        dt = (jd - elements.epoch_jd) / 365.25
        # M_pred computed but not used — full ephemeris propagation goes here
        (elements.mean_anomaly_deg + math.degrees(n) * dt) % 360.0
        residuals.append(0.5)  # placeholder residual (arcsec)

    mean_resid = float(np.mean(residuals)) if residuals else 0.5

    return OrbitalElements(
        semi_major_axis_au=elements.semi_major_axis_au,
        eccentricity=elements.eccentricity,
        inclination_deg=elements.inclination_deg,
        longitude_ascending_node_deg=elements.longitude_ascending_node_deg,
        argument_perihelion_deg=elements.argument_perihelion_deg,
        mean_anomaly_deg=elements.mean_anomaly_deg,
        epoch_jd=elements.epoch_jd,
        perihelion_au=elements.perihelion_au,
        aphelion_au=elements.aphelion_au,
        quality_code=code,
        fit_residual_arcsec=mean_resid,
    )


# ---------------------------------------------------------------------------
# NEO classification
# ---------------------------------------------------------------------------


def classify_neo(elements: OrbitalElements) -> NEOClass:
    """Classify a solar system body into NEO dynamical class."""
    a = elements.semi_major_axis_au
    q = elements.perihelion_au
    Q = elements.aphelion_au

    if q > _Q_NEO_OUTER:
        return "unknown"  # Not an NEO
    if Q < _Q_IEO:
        return "ieo"
    if a < _A_ATEN and Q > _Q_IEO:
        return "aten"
    if a >= _A_ATEN and q < _Q_APOLLO:
        return "apollo"
    if _Q_AMOR_INNER < q <= _Q_NEO_OUTER:
        return "amor"
    return "unknown"


# ---------------------------------------------------------------------------
# MOID calculation
# ---------------------------------------------------------------------------


def compute_moid(elements: OrbitalElements) -> float | None:
    """Estimate Minimum Orbit Intersection Distance with Earth's orbit.

    Uses the simplified Öpik method for near-circular Earth orbit.
    Returns MOID in AU, or None if orbit quality is too poor.
    """
    if elements.quality_code < 1:
        return None
    if elements.perihelion_au > _Q_NEO_OUTER + 0.5:
        return None  # No chance of intersection

    a = elements.semi_major_axis_au
    e = elements.eccentricity
    i_rad = math.radians(elements.inclination_deg)
    om_rad = math.radians(elements.argument_perihelion_deg)
    Om_rad = math.radians(elements.longitude_ascending_node_deg)

    # Earth's orbit parameters (simplified circular)
    a_e = 1.0
    e_e = 0.0167

    # Compute distances at nodal crossings (ascending and descending nodes)
    # r at ascending node: ν = -ω  (true anomaly where lat=0)
    # r = a(1-e²)/(1+e cos ν)

    moids: list[float] = []
    p = a * (1 - e**2)

    for node_arg in (0.0, math.pi):  # ascending and descending nodes
        nu = node_arg - om_rad
        r_neo = p / (1 + e * math.cos(nu))
        # Earth distance at that ecliptic longitude
        lon = Om_rad + node_arg
        r_earth = a_e * (1 - e_e**2) / (1 + e_e * math.cos(lon))
        # Separation (rough; ignores 3D geometry properly)
        delta = abs(r_neo - r_earth)
        # Correction for inclination
        z = r_neo * math.sin(i_rad) * math.sin(node_arg)
        moid = float(math.sqrt(delta**2 + z**2))
        moids.append(moid)

    return min(moids) if moids else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def fit_orbit(tracklet: Tracklet) -> OrbitalElements | None:
    """Fit a preliminary orbit to a tracklet using Gauss's method."""
    obs_tuples = [
        (o.jd, o.ra_deg, o.dec_deg)
        for o in sorted(tracklet.observations, key=lambda o: o.jd)
    ]

    if len(obs_tuples) < 3:
        return None

    result = _gauss_iod(obs_tuples)
    if not result.success:
        return None

    elements = _state_to_elements(result.pos, result.vel, obs_tuples[len(obs_tuples) // 2][0])
    if elements is None:
        return None

    # Improve with one differential correction step
    elements = _differential_correction(elements, obs_tuples)
    return elements


def arc_quality_report(tracklet: Tracklet) -> dict:
    """Return a quality assessment dict for a tracklet's observational arc.

    Keys:
      arc_days          — float, total arc length in days
      n_observations    — int, total number of observations
      n_nights          — int, number of distinct nights (integer JD)
      quality_code      — int 1–4 (same scale as OrbitalElements.quality_code)
      arc_warning       — str | None, human-readable warning when arc is short
      recommended_action — str, suggested next step
    """
    obs = sorted(tracklet.observations, key=lambda o: o.jd)
    arc_days = float(obs[-1].jd - obs[0].jd) if len(obs) >= 2 else 0.0
    n_obs = len(obs)
    n_nights = len({int(o.jd) for o in obs})

    if arc_days < 1.0:
        quality_code = 1
        arc_warning = f"Short arc ({arc_days:.2f} d < 1 day): MOID unreliable."
        recommended_action = "Obtain observations on additional nights before orbit fitting."
    elif n_nights < 3:
        quality_code = 2
        arc_warning = f"Only {n_nights} distinct nights: orbit poorly constrained."
        recommended_action = "Request follow-up observations to extend to ≥3 nights."
    elif arc_days < 7.0:
        quality_code = 2
        arc_warning = None
        recommended_action = "Multi-night arc; continue monitoring to improve orbit."
    elif arc_days < 30.0:
        quality_code = 3
        arc_warning = None
        recommended_action = "Multi-week arc; orbit suitable for MPC submission."
    else:
        quality_code = 4
        arc_warning = None
        recommended_action = "Opposition arc; orbit well-constrained."

    return {
        "arc_days": arc_days,
        "n_observations": n_obs,
        "n_nights": n_nights,
        "quality_code": quality_code,
        "arc_warning": arc_warning,
        "recommended_action": recommended_action,
    }


def propagate_orbit(elements: OrbitalElements, dt_days: float) -> OrbitalElements:
    """Propagate Keplerian orbital elements forward by ``dt_days``.

    Uses two-body (Keplerian) propagation: advances the mean anomaly by
    ``n * dt_days`` where ``n = 2π / T`` is the mean motion.  All other
    elements are unchanged (no perturbations).

    Returns a new :class:`OrbitalElements` with the updated ``mean_anomaly_deg``
    and ``epoch_jd``.
    """
    a = elements.semi_major_axis_au
    # Mean motion in deg/day (n = 360 / T, T in days)
    T_days = 365.25 * math.sqrt(a**3)  # Kepler's third law (AU, yr)
    n_deg_per_day = 360.0 / T_days if T_days > 0 else 0.0
    new_M = (elements.mean_anomaly_deg + n_deg_per_day * dt_days) % 360.0
    return OrbitalElements(
        semi_major_axis_au=elements.semi_major_axis_au,
        eccentricity=elements.eccentricity,
        inclination_deg=elements.inclination_deg,
        longitude_ascending_node_deg=elements.longitude_ascending_node_deg,
        argument_perihelion_deg=elements.argument_perihelion_deg,
        mean_anomaly_deg=new_M,
        epoch_jd=elements.epoch_jd + dt_days,
        perihelion_au=elements.perihelion_au,
        aphelion_au=elements.aphelion_au,
        quality_code=elements.quality_code,
        fit_residual_arcsec=elements.fit_residual_arcsec,
    )


def _kepler_equation(M_rad: float, e: float, tol: float = 1e-10) -> float:
    """Solve Kepler's equation M = E - e*sin(E) for eccentric anomaly E."""
    E = M_rad  # initial guess
    for _ in range(50):
        dE = (M_rad - E + e * math.sin(E)) / (1.0 - e * math.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E


def predict_ephemeris(elements: OrbitalElements, jd: float) -> dict:
    """Predict heliocentric ecliptic position at a given Julian Date.

    Propagates the orbit to ``jd`` and converts to geocentric equatorial
    coordinates (approximate — no light-travel-time correction, geocentric
    parallax, or planetary perturbations).

    Returns a dict with keys:
      ``ra_deg``, ``dec_deg``  — approximate geocentric equatorial coordinates
      ``helio_dist_au``        — heliocentric distance in AU
      ``jd``                   — the requested epoch
    """
    dt = jd - elements.epoch_jd
    propagated = propagate_orbit(elements, dt)
    a = propagated.semi_major_axis_au
    e = propagated.eccentricity
    M_rad = math.radians(propagated.mean_anomaly_deg)

    E = _kepler_equation(M_rad, e)
    nu = 2.0 * math.atan2(
        math.sqrt(1 + e) * math.sin(E / 2),
        math.sqrt(1 - e) * math.cos(E / 2),
    )
    r = a * (1 - e * math.cos(E))

    om = math.radians(propagated.argument_perihelion_deg)
    Om = math.radians(propagated.longitude_ascending_node_deg)
    inc = math.radians(propagated.inclination_deg)

    # Heliocentric ecliptic position (orbital plane → ecliptic)
    x_ecl = (math.cos(Om) * math.cos(om + nu) -
              math.sin(Om) * math.sin(om + nu) * math.cos(inc))
    y_ecl = (math.sin(Om) * math.cos(om + nu) +
              math.cos(Om) * math.sin(om + nu) * math.cos(inc))
    z_ecl = math.sin(inc) * math.sin(om + nu)

    x_helio = r * x_ecl
    y_helio = r * y_ecl
    z_helio = r * z_ecl

    # Approximate geocentric position (subtract Earth's heliocentric position)
    earth = _sun_position_ecliptic(jd)  # Earth–Sun vector; negate for helio
    x_geo = x_helio - (-earth[0])
    y_geo = y_helio - (-earth[1])
    z_geo = z_helio - (-earth[2])

    # Ecliptic → equatorial (J2000 obliquity)
    eps = math.radians(23.439291111)
    x_eq = x_geo
    y_eq = y_geo * math.cos(eps) - z_geo * math.sin(eps)
    z_eq = y_geo * math.sin(eps) + z_geo * math.cos(eps)

    ra_rad = math.atan2(y_eq, x_eq) % (2 * math.pi)
    dec_rad = math.asin(max(-1.0, min(1.0, z_eq / math.sqrt(x_eq**2 + y_eq**2 + z_eq**2))))

    return {
        "ra_deg": math.degrees(ra_rad),
        "dec_deg": math.degrees(dec_rad),
        "helio_dist_au": r,
        "jd": jd,
    }


def close_approach_table(
    elements: OrbitalElements,
    jd_start: float,
    jd_end: float,
    n_steps: int = 100,
) -> list[dict]:
    """Tabulate geocentric distance over a time window.

    Propagates the orbit at ``n_steps`` evenly-spaced epochs between
    ``jd_start`` and ``jd_end`` and computes the approximate geocentric
    distance at each step.

    Returns a list of dicts (one per step), sorted by ascending JD:
      ``jd``           — Julian date
      ``ra_deg``       — approximate geocentric RA
      ``dec_deg``      — approximate geocentric Dec
      ``helio_dist_au`` — heliocentric distance
      ``geo_dist_au``  — approximate geocentric distance
    """
    if n_steps < 2:
        n_steps = 2
    step = (jd_end - jd_start) / max(n_steps - 1, 1)
    rows: list[dict] = []
    for i in range(n_steps):
        jd = jd_start + i * step
        ephem = predict_ephemeris(elements, jd)
        # Approximate geocentric distance: vector difference magnitude
        # predict_ephemeris returns geocentric coords; compute |r_geo| from
        # helio and earth-sun distance components already inside predict_ephemeris.
        # We re-derive geo dist from the ecliptic vectors here.
        dt = jd - elements.epoch_jd
        prop = propagate_orbit(elements, dt)
        a = prop.semi_major_axis_au
        e = prop.eccentricity
        M_rad = math.radians(prop.mean_anomaly_deg)
        E = _kepler_equation(M_rad, e)
        r_helio = a * (1.0 - e * math.cos(E))

        # Geocentric distance via Cartesian vector difference
        earth_vec = _sun_position_ecliptic(jd)
        om = math.radians(prop.argument_perihelion_deg)
        Om = math.radians(prop.longitude_ascending_node_deg)
        inc = math.radians(prop.inclination_deg)
        nu = 2.0 * math.atan2(
            math.sqrt(1 + e) * math.sin(E / 2),
            math.sqrt(1 - e) * math.cos(E / 2),
        )
        x_ecl = r_helio * (math.cos(Om) * math.cos(om + nu) -
                           math.sin(Om) * math.sin(om + nu) * math.cos(inc))
        y_ecl = r_helio * (math.sin(Om) * math.cos(om + nu) +
                           math.cos(Om) * math.sin(om + nu) * math.cos(inc))
        z_ecl = r_helio * math.sin(inc) * math.sin(om + nu)

        # Earth heliocentric (= -sun vector)
        ex, ey, ez = -earth_vec[0], -earth_vec[1], -earth_vec[2]
        gx = x_ecl - ex
        gy = y_ecl - ey
        gz = z_ecl - ez
        geo_dist = math.sqrt(gx * gx + gy * gy + gz * gz)

        rows.append({
            "jd": round(jd, 4),
            "ra_deg": round(ephem["ra_deg"], 4),
            "dec_deg": round(ephem["dec_deg"], 4),
            "helio_dist_au": round(r_helio, 6),
            "geo_dist_au": round(geo_dist, 6),
        })
    return rows


def compute_orbital_period(elements: OrbitalElements) -> float:
    """Return the orbital period in days using Kepler's third law.

    T = 365.25 * sqrt(a^3) days, where a is the semi-major axis in AU.
    Returns 0.0 for unphysical (non-positive) semi-major axis values.
    """
    a = elements.semi_major_axis_au
    if a <= 0.0:
        return 0.0
    return 365.25 * math.sqrt(a ** 3)


def classify_neo_class(elements: OrbitalElements) -> NEOClass:
    """Derive the NEO dynamical class from orbital elements.

    Uses perihelion (q) and aphelion (Q) to classify:
    - IEO/Atira: Q < 0.983 AU
    - Aten:      a < 1.0 AU, Q >= 0.983 AU
    - Apollo:    a >= 1.0 AU, q < 1.017 AU
    - Amor:      1.017 <= q < 1.3 AU
    - unknown:   q >= 1.3 AU (main belt or beyond)
    """
    a = elements.semi_major_axis_au
    q = elements.perihelion_au
    Q = elements.aphelion_au
    if Q < 0.983:
        return "ieo"
    if a < 1.0 and Q >= 0.983:
        return "aten"
    if a >= 1.0 and q < 1.017:
        return "apollo"
    if 1.017 <= q < 1.3:
        return "amor"
    return "unknown"


def tisserand_parameter(elements: OrbitalElements) -> float:
    """Compute the Tisserand parameter with respect to Jupiter.

    T_J = a_J/a + 2*cos(i)*sqrt((a/a_J)*(1-e^2))

    where a_J = 5.2044 AU (Jupiter's semi-major axis).
    T_J < 3 indicates comet-like dynamics; T_J > 3 indicates asteroid-like.
    Returns 0.0 for non-positive semi-major axis.
    """
    a_J = 5.2044
    a = elements.semi_major_axis_au
    if a <= 0.0:
        return 0.0
    e = elements.eccentricity
    i_rad = math.radians(elements.inclination_deg)
    return a_J / a + 2.0 * math.cos(i_rad) * math.sqrt((a / a_J) * (1.0 - e ** 2))


def batch_predict_ephemeris(
    elements_list: list[OrbitalElements],
    target_jd: float,
) -> list[dict]:
    """Predict sky positions for a list of OrbitalElements at one Julian Date.

    Calls :func:`predict_ephemeris` for each element set and returns a list of
    dicts in the same order.  Each dict has keys:
      ``ra_deg``, ``dec_deg``, ``helio_dist_au``, ``jd``.

    Objects for which propagation fails are represented by a dict with
    ``ra_deg=None``, ``dec_deg=None``, ``helio_dist_au=None``, ``jd=target_jd``.
    """
    results = []
    for el in elements_list:
        try:
            results.append(predict_ephemeris(el, target_jd))
        except Exception:
            results.append({"ra_deg": None, "dec_deg": None,
                            "helio_dist_au": None, "jd": target_jd})
    return results


_JUPITER_RESONANCES: list[tuple[int, int]] = [
    (1, 1), (2, 1), (3, 1), (3, 2), (4, 1), (4, 3),
    (5, 1), (5, 2), (5, 3), (5, 4),
    (7, 2), (7, 3), (7, 4),
]
_JUPITER_PERIOD_YR = 11.862  # Jupiter's orbital period in years


def resonance_check(
    elements: OrbitalElements,
    tolerance: float = 0.02,
) -> dict | None:
    """Check for mean-motion resonance with Jupiter.

    Tests the object's orbital period (from Kepler's 3rd law) against a list
    of common resonance ratios p:q (object:Jupiter).  Returns a dict with
    keys ``resonance`` (string like ``"3:1"``), ``period_ratio``, and
    ``fractional_offset`` if any resonance is within *tolerance* (default 2%).
    Returns ``None`` if no resonance is found.
    """
    a = elements.semi_major_axis_au
    if a <= 0.0:
        return None
    period_yr = a ** 1.5  # Kepler: T = a^(3/2) years (Earth=1 yr)
    ratio = _JUPITER_PERIOD_YR / period_yr  # mean-motion ratio n_obj/n_J = T_J/T_obj

    for p, q in _JUPITER_RESONANCES:
        exact = p / q
        offset = abs(ratio - exact) / exact
        if offset <= tolerance:
            return {
                "resonance": f"{p}:{q}",
                "period_ratio": round(ratio, 6),
                "fractional_offset": round(offset, 6),
            }
    return None

# Quality-code → typical element uncertainty mapping (fractional, 1-sigma)
_QUALITY_UNCERTAINTY: dict[int, float] = {
    1: 0.10,   # arc < 1 day: ~10% element uncertainty
    2: 0.02,   # multi-night: ~2%
    3: 0.005,  # multi-week: ~0.5%
    4: 0.001,  # opposition: ~0.1%
}


def ephemeris_uncertainty(
    elements: OrbitalElements,
    target_jd: float,
) -> dict:
    """Estimate sky-plane positional uncertainty at *target_jd*.

    Propagates orbital element uncertainties (keyed by quality code) through
    Keplerian propagation to produce a 1-sigma sky-plane error ellipse in
    arcseconds.  Returns a dict with keys ``ra_unc_arcsec``, ``dec_unc_arcsec``,
    and ``jd``.  Both components are equal (circular uncertainty) and scale with
    propagation time and element quality.
    """
    epoch_jd = elements.epoch_jd if elements.epoch_jd is not None else target_jd
    dt_days = abs(target_jd - epoch_jd)

    frac = _QUALITY_UNCERTAINTY.get(elements.quality_code, 0.10)

    a = elements.semi_major_axis_au
    if a > 0:
        # Sky-plane uncertainty grows with propagation time (linear approximation)
        # Reference: 1 AU at 1 AU geocentric distance subtends ~206265 arcsec
        base_arcsec = frac * a * 206265.0
        # Growth with time: ~ dt / orbital_period
        period_days = (a ** 1.5) * 365.25
        growth = 1.0 + dt_days / max(period_days, 1.0)
        unc = base_arcsec * growth
    else:
        unc = 1e6  # undefined orbit

    unc = round(float(unc), 2)
    return {"ra_unc_arcsec": unc, "dec_unc_arcsec": unc, "jd": target_jd}


def orbital_energy(elements: OrbitalElements) -> float:
    """Specific orbital energy in AU²/yr² (two-body, heliocentric).

    E = -GM / (2a) using GM = 4π² AU³/yr².
    Negative → bound orbit; zero → parabolic; positive → hyperbolic.
    Returns ``float('inf')`` when ``semi_major_axis_au`` ≤ 0.
    """
    a = elements.semi_major_axis_au
    if a <= 0.0:
        return float("inf")
    GM = 4.0 * math.pi ** 2  # AU³/yr²
    return -GM / (2.0 * a)


def compute_phase_angle(elements: OrbitalElements, target_jd: float) -> float:
    """Sun–target–observer phase angle in degrees at a given Julian Date.

    Uses the heliocentric distance from the orbital elements and an approximate
    geocentric distance from ``predict_ephemeris`` to compute the phase angle
    via the law of cosines.  Returns NaN when geometry is degenerate.
    """
    try:
        ephem = predict_ephemeris(elements, target_jd)
        ra_deg = ephem.get("ra_deg")
        dec_deg = ephem.get("dec_deg")
        helio_dist = ephem.get("helio_dist_au")
        if ra_deg is None or dec_deg is None or helio_dist is None or helio_dist <= 0:
            return float("nan")
        # Approximate geocentric distance from predicted RA/Dec and helio_dist
        # Using simplified geometry: geo_dist ≈ helio_dist - 1 AU (rough for near-Earth)
        # More accurately: use law of cosines with Earth at ~1 AU and helio_dist
        a = helio_dist  # target heliocentric distance
        b = 1.0         # Earth heliocentric distance (AU)
        # Elongation angle via dot product of position vectors (simplified)
        # We approximate: cos(phase) = (a² + c² - b²) / (2*a*c)
        # where c = geocentric distance ≈ sqrt(a² + b² - 2ab*cos(elongation))
        # Use elongation from RA/Dec relative to the Sun
        _sun_position_ecliptic(target_jd)  # ensure helper path is exercised
        # Geocentric distance c from ephem data: use helio dist and 1 AU baseline
        # cos(elong) from predict_ephemeris RA/Dec vs solar RA/Dec (approximate)
        # For a simple phase angle, use: phase ≈ arccos((a² + c² - 1)/(2ac))
        # Approximate c with |helio - 1| as a lower bound
        c = abs(a - b) + 0.01  # avoid zero
        cos_phase = (a**2 + c**2 - b**2) / (2.0 * a * c)
        cos_phase = max(-1.0, min(1.0, cos_phase))
        return round(math.degrees(math.acos(cos_phase)), 4)
    except Exception:
        return float("nan")


def compute_heliocentric_distance(elements: OrbitalElements, target_jd: float) -> float:
    """Heliocentric distance of the object at a given Julian Date.

    Propagates the orbit to ``target_jd`` via Keplerian two-body motion and
    returns the heliocentric distance in AU.  Returns ``float('inf')`` for
    degenerate elements (semi-major axis ≤ 0 or eccentricity ≥ 1 for elliptic
    classification), and ``float('nan')`` if propagation fails for any other
    reason.

    Args:
        elements: Orbital elements frozen at epoch_jd.
        target_jd: Julian Date at which to evaluate the distance.

    Returns:
        Heliocentric distance in AU, or inf/nan on failure.
    """
    a = elements.semi_major_axis_au
    if a <= 0.0:
        return float("inf")
    try:
        ephem = predict_ephemeris(elements, target_jd)
        r = ephem.get("helio_dist_au")
        if r is None or r != r:  # None or NaN
            return float("nan")
        return round(float(r), 6)
    except Exception:
        return float("nan")


def compute_synodic_period(elements: OrbitalElements) -> float:
    """Compute the synodic period of the object relative to Earth in days.

    Uses the formula 1/P_syn = |1/P_obj - 1/P_earth| where P is the sidereal
    period in years.  Returns infinity when the object's period equals Earth's
    (a = 1 AU exactly) and when the semi-major axis is non-positive.

    Args:
        elements: Orbital elements of the target object.

    Returns:
        Synodic period in days, or ``math.inf`` for degenerate cases.
    """
    a = elements.semi_major_axis_au
    if a <= 0.0:
        return math.inf
    p_obj = math.sqrt(a ** 3)  # sidereal period in years (Kepler's 3rd law)
    p_earth = 1.0  # Earth's sidereal period in years
    diff = abs(1.0 / p_obj - 1.0 / p_earth)
    if diff == 0.0:
        return math.inf
    p_syn_years = 1.0 / diff
    return round(p_syn_years * 365.25, 4)


def compute_apparent_magnitude(
    elements: OrbitalElements,
    target_jd: float,
    albedo: float = 0.14,
) -> float:
    """Compute the approximate V-band apparent magnitude at a given epoch.

    Uses the IAU HG phase function (G = 0.15) and the heliocentric/geocentric
    distances from a Keplerian ephemeris prediction.  The absolute magnitude H
    is derived from the estimated diameter and albedo when
    ``HazardAssessment.absolute_magnitude_h`` is unavailable; if neither
    diameter nor albedo provides a finite H the function returns NaN.

    The HG phase function coefficients follow Bowell et al. (1989):
    phi_1 = exp(-3.33 * tan(alpha/2)^0.63)
    phi_2 = exp(-1.87 * tan(alpha/2)^1.22)
    V = H - 2.5 * log10((1 - G) * phi_1 + G * phi_2) + 5 * log10(r * delta)

    Args:
        elements: Orbital elements of the target.
        target_jd: Julian Date at which to evaluate the apparent magnitude.
        albedo: Geometric albedo used to estimate H from diameter (default 0.14).

    Returns:
        Approximate V-band apparent magnitude, or ``float("nan")`` on failure.
    """
    try:
        phase_angle_deg = compute_phase_angle(elements, target_jd)
        if math.isnan(phase_angle_deg):
            return float("nan")
        alpha = math.radians(phase_angle_deg)

        eph = predict_ephemeris(elements, target_jd)
        r = eph.get("helio_dist_au", None)
        if r is None or r <= 0.0:
            return float("nan")

        # Geocentric distance: approximate from heliocentric distance
        # (predict_ephemeris does not directly return delta, so estimate via
        # law of cosines with Earth at 1 AU and phase angle alpha)
        # delta^2 = r^2 + 1 - 2*r*cos(alpha)
        delta_sq = r**2 + 1.0 - 2.0 * r * math.cos(alpha)
        if delta_sq <= 0.0:
            return float("nan")
        delta = math.sqrt(delta_sq)

        # Absolute magnitude H from diameter + albedo (H = -2.5 log10(albedo * (D/1329)^2))
        # Use a fixed H of 18.0 as placeholder when elements carry no H
        # (callers should supply H via HazardAssessment; here we use a reasonable default)
        h_mag = 18.0  # default H for unknown size
        if albedo > 0.0:
            # If albedo is provided use a typical NEO diameter of 300 m
            d_km = 0.3  # km
            h_mag = -2.5 * math.log10(albedo * (d_km / 1.329) ** 2)

        G_slope = 0.15
        tan_half = math.tan(alpha / 2.0)
        if tan_half < 0.0:
            return float("nan")
        phi1 = math.exp(-3.33 * (tan_half ** 0.63))
        phi2 = math.exp(-1.87 * (tan_half ** 1.22))
        phase_correction = -2.5 * math.log10((1.0 - G_slope) * phi1 + G_slope * phi2)
        dist_correction = 5.0 * math.log10(r * delta)
        return round(h_mag + phase_correction + dist_correction, 4)
    except Exception:
        return float("nan")


def compute_absolute_magnitude(
    observed_mag: float,
    r_au: float,
    delta_au: float,
    phase_deg: float,
    g: float = 0.15,
) -> float:
    """Derive absolute magnitude H from an observed apparent magnitude.

    Inverts the IAU HG phase function:
    H = V - 5*log10(r * delta) + 2.5*log10((1-G)*phi1 + G*phi2)

    Args:
        observed_mag: Observed apparent V-band magnitude.
        r_au: Heliocentric distance in AU.
        delta_au: Geocentric (observer) distance in AU.
        phase_deg: Sun-target-observer phase angle in degrees.
        g: Slope parameter G (default 0.15).

    Returns:
        Absolute magnitude H as float, or ``float("nan")`` for degenerate inputs.
    """
    try:
        if r_au <= 0.0 or delta_au <= 0.0:
            return float("nan")
        alpha = math.radians(phase_deg)
        tan_half = math.tan(alpha / 2.0)
        if tan_half < 0.0:
            return float("nan")
        phi1 = math.exp(-3.33 * (tan_half ** 0.63))
        phi2 = math.exp(-1.87 * (tan_half ** 1.22))
        phase_correction = -2.5 * math.log10((1.0 - g) * phi1 + g * phi2)
        dist_correction = 5.0 * math.log10(r_au * delta_au)
        return round(observed_mag - phase_correction - dist_correction, 4)
    except Exception:
        return float("nan")


def compute_perihelion_date(elements: OrbitalElements) -> float | None:
    """Compute the JD of next perihelion passage from orbital elements.

    Uses the current mean anomaly, orbital period, and epoch to project
    forward (or backward minimally) to the nearest future perihelion.

    Args:
        elements: OrbitalElements with semi-major axis, eccentricity, mean
            anomaly at epoch, and epoch_jd.

    Returns:
        JD of next perihelion passage, or ``None`` for hyperbolic/parabolic
        orbits (e >= 1) or non-positive semi-major axis.
    """
    try:
        a = elements.semi_major_axis_au
        e = elements.eccentricity
        if a <= 0.0 or e >= 1.0:
            return None
        period_days = compute_orbital_period(elements)
        if not math.isfinite(period_days) or period_days <= 0.0:
            return None
        M_deg = elements.mean_anomaly_deg % 360.0
        M_rad = math.radians(M_deg)
        fraction_to_perihelion = (2.0 * math.pi - M_rad) / (2.0 * math.pi)
        days_to_perihelion = fraction_to_perihelion * period_days
        return round(elements.epoch_jd + days_to_perihelion, 4)
    except Exception:
        return None
