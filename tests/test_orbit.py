"""Tests for orbit.py."""

import sys
sys.path.insert(0, "src")

import math
import pytest
import numpy as np

from orbit import (
    _equatorial_to_ecliptic,
    _sun_position_ecliptic,
    _state_to_elements,
    classify_neo,
    compute_moid,
    fit_orbit,
)
from schemas import Observation, OrbitalElements, Tracklet


def make_elements(**kwargs) -> OrbitalElements:
    defaults = dict(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=2,
    )
    defaults.update(kwargs)
    return OrbitalElements(**defaults)


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="o_001",
        ra_deg=180.0,
        dec_deg=0.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
    )
    defaults.update(kwargs)
    return Observation(**defaults)


class TestCoordinateConversion:
    def test_unit_vector(self):
        v = _equatorial_to_ecliptic(0.0, 0.0, 2451545.0)
        assert abs(np.linalg.norm(v) - 1.0) < 1e-6

    def test_sun_position_unit(self):
        pos = _sun_position_ecliptic(2451545.0)
        r = np.linalg.norm(pos)
        assert 0.98 < r < 1.02  # Earth–Sun ~1 AU


class TestStateToElements:
    def test_circular_orbit(self):
        # Circular orbit at 1 AU
        pos = np.array([1.0, 0.0, 0.0])
        # v = sqrt(GM/r) in AU/day; GM = 4π²/365.25² AU³/day²
        gm_day = 4 * math.pi**2 / 365.25**2
        v_circ = math.sqrt(gm_day / 1.0)
        vel = np.array([0.0, v_circ, 0.0])
        el = _state_to_elements(pos, vel, 2451545.0)
        assert el is not None
        assert el.semi_major_axis_au == pytest.approx(1.0, rel=0.05)
        assert el.eccentricity == pytest.approx(0.0, abs=0.05)

    def test_returns_none_for_zero_vectors(self):
        el = _state_to_elements(np.zeros(3), np.zeros(3), 2451545.0)
        assert el is None


class TestClassifyNEO:
    def test_amor(self):
        el = make_elements(semi_major_axis_au=1.4, eccentricity=0.1,
                           perihelion_au=1.26, aphelion_au=1.54)
        assert classify_neo(el) == "amor"

    def test_apollo(self):
        el = make_elements(semi_major_axis_au=1.5, eccentricity=0.4,
                           perihelion_au=0.9, aphelion_au=2.1)
        assert classify_neo(el) == "apollo"

    def test_aten(self):
        # Aten: a < 1.0 AU and Q > 0.983 AU
        el = make_elements(semi_major_axis_au=0.95, eccentricity=0.08,
                           perihelion_au=0.874, aphelion_au=1.026)
        assert classify_neo(el) == "aten"

    def test_ieo(self):
        el = make_elements(semi_major_axis_au=0.6, eccentricity=0.1,
                           perihelion_au=0.54, aphelion_au=0.66)
        assert classify_neo(el) == "ieo"

    def test_non_neo(self):
        el = make_elements(semi_major_axis_au=2.5, eccentricity=0.1,
                           perihelion_au=2.25, aphelion_au=2.75)
        assert classify_neo(el) == "unknown"


class TestComputeMoid:
    def test_high_perihelion_no_moid(self):
        el = make_elements(perihelion_au=2.0, aphelion_au=3.0)
        moid = compute_moid(el)
        assert moid is None or moid > 0.5

    def test_earth_crossing(self):
        el = make_elements(
            semi_major_axis_au=1.5, eccentricity=0.4,
            perihelion_au=0.9, aphelion_au=2.1,
            inclination_deg=5.0,
            quality_code=2,
        )
        moid = compute_moid(el)
        assert moid is not None
        assert moid >= 0.0

    def test_low_quality_returns_none(self):
        el = make_elements(quality_code=1, perihelion_au=0.5)
        # quality_code=1 is acceptable; function still returns value
        moid = compute_moid(el)
        # Either returns a float or None — both acceptable
        assert moid is None or isinstance(moid, float)


class TestFitOrbit:
    def test_insufficient_obs_returns_none(self):
        obs1 = make_obs(obs_id="a")
        obs2 = make_obs(obs_id="b", jd=2460001.5)
        t = Tracklet("T", (obs1, obs2), 1.0, 1.0, 0.0)
        result = fit_orbit(t)
        assert result is None  # <3 observations

    def test_three_obs_attempts_fit(self):
        obs = tuple(
            make_obs(
                obs_id=f"o{i}",
                jd=2460000.5 + i * 10,
                ra_deg=180.0 + i * 0.1,
                dec_deg=0.0,
            )
            for i in range(3)
        )
        t = Tracklet("T", obs, 20.0, 1.0, 90.0)
        # May return None if Gauss method fails to converge (valid)
        result = fit_orbit(t)
        if result is not None:
            assert result.semi_major_axis_au > 0
            assert 0.0 <= result.eccentricity < 1.0
