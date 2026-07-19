"""Orbit stage — preliminary fitting, arc assessment, MOID, NEO classification."""

from __future__ import annotations

__all__ = [
    "classify_neo",
    "compute_moid",
    "fit_orbit",
    "arc_quality_report",
    "predict_ephemeris",
    "close_approach_table",
    "classify_neo_class",
    "tisserand_parameter",
    "compute_mean_motion",
]

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


def _earth_heliocentric_equatorial(jds: np.ndarray) -> np.ndarray:
    """Return Earth-center heliocentric ICRS Cartesian positions in AU.

    Astropy's bundled ``builtin`` ephemeris is explicit here so offline runs
    never trigger a remote kernel download.
    """
    from astropy.coordinates import (  # type: ignore[import]
        get_body_barycentric_posvel,
        solar_system_ephemeris,
    )
    from astropy.time import Time  # type: ignore[import]

    times = Time(jds, format="jd", scale="tdb")
    with solar_system_ephemeris.set("builtin"):
        earth, _ = get_body_barycentric_posvel("earth", times)
        sun, _ = get_body_barycentric_posvel("sun", times)
    return np.asarray((earth.xyz - sun.xyz).to_value("au").T, dtype=float)


def _radec_unit_vector(ra_deg: float, dec_deg: float) -> np.ndarray:
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    return np.array(
        [math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)]
    )


def _equatorial_state_to_ecliptic(
    pos: np.ndarray, vel: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    eps = math.radians(23.439291111)
    rotation = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, math.cos(eps), math.sin(eps)],
            [0.0, -math.sin(eps), math.cos(eps)],
        ]
    )
    return rotation @ pos, rotation @ vel


def _ecliptic_state_to_equatorial(
    pos: np.ndarray, vel: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    eps = math.radians(23.439291111)
    rotation = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, math.cos(eps), -math.sin(eps)],
            [0.0, math.sin(eps), math.cos(eps)],
        ]
    )
    return rotation @ pos, rotation @ vel


def _elements_to_equatorial_state(elements: OrbitalElements) -> np.ndarray:
    """Convert elliptic Keplerian elements to an ICRS-oriented state."""
    a = elements.semi_major_axis_au
    e = elements.eccentricity
    eccentric_anomaly = _kepler_equation(math.radians(elements.mean_anomaly_deg), e)
    root = math.sqrt(max(0.0, 1.0 - e**2))
    pos_perifocal = np.array(
        [a * (math.cos(eccentric_anomaly) - e), a * root * math.sin(eccentric_anomaly), 0.0]
    )
    mean_motion = math.sqrt((_GM_SUN / 365.25**2) / a**3)
    scale = mean_motion * a / (1.0 - e * math.cos(eccentric_anomaly))
    vel_perifocal = scale * np.array(
        [-math.sin(eccentric_anomaly), root * math.cos(eccentric_anomaly), 0.0]
    )

    node = math.radians(elements.longitude_ascending_node_deg)
    inc = math.radians(elements.inclination_deg)
    peri = math.radians(elements.argument_perihelion_deg)
    rz_node = np.array(
        [
            [math.cos(node), -math.sin(node), 0.0],
            [math.sin(node), math.cos(node), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    rx_inc = np.array(
        [[1.0, 0.0, 0.0], [0.0, math.cos(inc), -math.sin(inc)], [0.0, math.sin(inc), math.cos(inc)]]
    )
    rz_peri = np.array(
        [
            [math.cos(peri), -math.sin(peri), 0.0],
            [math.sin(peri), math.cos(peri), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    rotation = rz_node @ rx_inc @ rz_peri
    pos_ecl = rotation @ pos_perifocal
    vel_ecl = rotation @ vel_perifocal
    pos_eq, vel_eq = _ecliptic_state_to_equatorial(pos_ecl, vel_ecl)
    return np.concatenate((pos_eq, vel_eq))


def _two_body_derivative(state: np.ndarray) -> np.ndarray:
    pos = state[:3]
    radius = float(np.linalg.norm(pos))
    if radius <= 1e-8:
        return np.full(6, np.nan)
    gm_day = _GM_SUN / 365.25**2
    acceleration = -gm_day * pos / radius**3
    return np.concatenate((state[3:], acceleration))


def _propagate_state(state: np.ndarray, dt_days: float) -> np.ndarray:
    """Propagate a Cartesian two-body state with deterministic RK4 steps."""
    if dt_days == 0.0:
        return state.copy()
    n_steps = max(1, int(math.ceil(abs(dt_days) / 0.25)))
    step = dt_days / n_steps
    current = state.copy()
    for _ in range(n_steps):
        k1 = _two_body_derivative(current)
        k2 = _two_body_derivative(current + 0.5 * step * k1)
        k3 = _two_body_derivative(current + 0.5 * step * k2)
        k4 = _two_body_derivative(current + step * k3)
        current = current + step * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0
        if not np.all(np.isfinite(current)):
            return current
    return current


def _state_astrometric_residuals(
    state: np.ndarray,
    jds: np.ndarray,
    observed: np.ndarray,
    earth: np.ndarray,
    epoch_jd: float,
) -> np.ndarray:
    residuals: list[float] = []
    for jd, (obs_ra, obs_dec), earth_pos in zip(jds, observed, earth, strict=True):
        propagated = _propagate_state(state, float(jd - epoch_jd))
        geo = propagated[:3] - earth_pos
        distance = float(np.linalg.norm(geo))
        if distance <= 1e-10 or not np.isfinite(distance):
            return np.full(2 * len(jds), 1e9)
        ra = math.degrees(math.atan2(geo[1], geo[0])) % 360.0
        dec = math.degrees(math.asin(max(-1.0, min(1.0, geo[2] / distance))))
        dra = ((ra - obs_ra + 180.0) % 360.0) - 180.0
        residuals.extend((dra * math.cos(math.radians(obs_dec)) * 3600.0, (dec - obs_dec) * 3600.0))
    return np.asarray(residuals, dtype=float)


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
    """Fit a heliocentric Cartesian state to geocentric optical astrometry.

    The historical function name is retained for compatibility, but the old
    scalar "Gauss" approximation was not a valid implementation and produced
    impossible states even for a known circular-orbit control. This replacement
    performs deterministic multi-start nonlinear least squares against a
    two-body propagation model and Astropy's built-in Earth ephemeris.
    """
    if len(obs_list) < 3:
        return _GaussResult(np.zeros(3), np.zeros(3), False)
    from scipy.optimize import least_squares  # type: ignore[import-untyped]

    ordered = sorted(obs_list)
    jds = np.array([row[0] for row in ordered], dtype=float)
    if not np.all(np.isfinite(jds)) or np.ptp(jds) <= 0.0:
        return _GaussResult(np.zeros(3), np.zeros(3), False)
    observed = np.array([[row[1], row[2]] for row in ordered], dtype=float)
    if not np.all(np.isfinite(observed)):
        return _GaussResult(np.zeros(3), np.zeros(3), False)

    earth = _earth_heliocentric_equatorial(jds)
    los = np.array([_radec_unit_vector(ra, dec) for ra, dec in observed])
    mid = len(ordered) // 2
    epoch = jds[mid]
    dt_span = jds[-1] - jds[0]
    best_state: np.ndarray | None = None
    best_rms = math.inf

    for rho_au in (0.1, 0.3, 0.7, 1.5, 3.0, 8.0):
        positions = earth + rho_au * los
        velocity = (positions[-1] - positions[0]) / dt_span
        x0 = np.concatenate((positions[mid], velocity))
        result = least_squares(
            _state_astrometric_residuals,
            x0,
            args=(jds, observed, earth, epoch),
            bounds=(
                np.array([-100.0, -100.0, -100.0, -0.2, -0.2, -0.2]),
                np.array([100.0, 100.0, 100.0, 0.2, 0.2, 0.2]),
            ),
            x_scale=np.array([1.0, 1.0, 1.0, 0.02, 0.02, 0.02]),
            max_nfev=1200,
            method="trf",
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            continue
        residuals = _state_astrometric_residuals(result.x, jds, observed, earth, epoch)
        rms = float(np.sqrt(np.mean(residuals**2)))
        pos_ecl, vel_ecl = _equatorial_state_to_ecliptic(result.x[:3], result.x[3:])
        elements = _state_to_elements(pos_ecl, vel_ecl, epoch)
        if elements is None or elements.eccentricity >= 1.0:
            continue
        if not (0.1 <= elements.semi_major_axis_au <= 100.0):
            continue
        if rms < best_rms:
            best_rms = rms
            best_state = result.x

    if best_state is None or best_rms > 5.0:
        return _GaussResult(np.zeros(3), np.zeros(3), False)
    pos_ecl, vel_ecl = _equatorial_state_to_ecliptic(best_state[:3], best_state[3:])
    return _GaussResult(pos_ecl, vel_ecl, True)


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
    """Refine a preliminary state and record a measured astrometric RMS."""
    from scipy.optimize import least_squares  # type: ignore[import-untyped]

    ordered = sorted(observations)
    jds = np.array([row[0] for row in ordered], dtype=float)
    observed = np.array([[row[1], row[2]] for row in ordered], dtype=float)
    earth = _earth_heliocentric_equatorial(jds)
    initial = _elements_to_equatorial_state(elements)
    result = least_squares(
        _state_astrometric_residuals,
        initial,
        args=(jds, observed, earth, elements.epoch_jd),
        bounds=(
            np.array([-100.0, -100.0, -100.0, -0.2, -0.2, -0.2]),
            np.array([100.0, 100.0, 100.0, 0.2, 0.2, 0.2]),
        ),
        x_scale=np.array([1.0, 1.0, 1.0, 0.02, 0.02, 0.02]),
        max_nfev=1200,
        method="trf",
    )
    state = result.x if result.success and np.all(np.isfinite(result.x)) else initial
    residuals = _state_astrometric_residuals(
        state, jds, observed, earth, elements.epoch_jd
    )
    rms = float(np.sqrt(np.mean(residuals**2)))
    pos_ecl, vel_ecl = _equatorial_state_to_ecliptic(state[:3], state[3:])
    refined = _state_to_elements(pos_ecl, vel_ecl, elements.epoch_jd)
    if refined is None:
        refined = elements
    code = _arc_quality_tier(float(jds[-1] - jds[0]))
    return refined.model_copy(update={"quality_code": code, "fit_residual_arcsec": rms})


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


def _arc_quality_tier(arc_days: float) -> OrbitQualityCode:
    if arc_days < 1.0:
        return 1
    if arc_days < 7.0:
        return 2
    if arc_days < 30.0:
        return 3
    return 4


def fit_orbit(tracklet: Tracklet) -> OrbitalElements | None:
    """Fit a bounded two-body preliminary orbit to a tracklet."""
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
    if elements.fit_residual_arcsec is None or elements.fit_residual_arcsec > 5.0:
        return None
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
    n_nights = len({int(o.jd - 0.5) for o in obs})
    quality_code = _arc_quality_tier(arc_days)

    if quality_code == 1:
        arc_warning = f"Short arc ({arc_days:.2f} d < 1 day): MOID unreliable."
        recommended_action = "Obtain observations on additional nights before orbit fitting."
    elif n_nights < 3:
        arc_warning = f"Only {n_nights} distinct nights: orbit poorly constrained."
        recommended_action = "Request follow-up observations to extend to ≥3 nights."
    elif quality_code == 2:
        arc_warning = None
        recommended_action = "Multi-night arc; continue monitoring to improve orbit."
    elif quality_code == 3:
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


























def compute_mean_motion(elements: OrbitalElements) -> float:
    """Compute mean motion n in degrees per day from orbital elements.

    Mean motion is the average angular velocity:
        n = 360.0 / T
    where T is the orbital period in days (Kepler's third law).

    Args:
        elements: Orbital elements containing the semi-major axis.

    Returns:
        Mean motion in degrees per day.

    Raises:
        ValueError: If semi-major axis is ≤ 0.
    """
    a = elements.semi_major_axis_au
    if a <= 0.0:
        raise ValueError(f"semi-major axis must be positive, got {a}")
    T_days = 365.25 * math.sqrt(a ** 3)
    return 360.0 / T_days




























































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
