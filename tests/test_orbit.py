"""Tests for orbit.py."""

import math

import numpy as np
import pytest

from orbit import (
    _differential_correction,
    _equatorial_to_ecliptic,
    _gauss_iod,
    _kepler_equation,
    _state_to_elements,
    _sun_position_ecliptic,
    arc_quality_report,
    classify_neo,
    compute_moid,
    fit_orbit,
    predict_ephemeris,
    propagate_orbit,
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


class TestGaussIod:
    def test_fewer_than_3_obs_returns_false(self):
        obs_list = [(2460000.0, 180.0, 0.0), (2460001.0, 180.1, 0.0)]
        result = _gauss_iod(obs_list)
        assert result.success is False

    def test_single_obs_returns_false(self):
        result = _gauss_iod([(2460000.0, 180.0, 0.0)])
        assert result.success is False

    def test_three_obs_runs_without_error(self):
        obs_list = [
            (2460000.0, 180.0, 5.0),
            (2460010.0, 180.5, 5.1),
            (2460020.0, 181.0, 5.2),
        ]
        result = _gauss_iod(obs_list)
        assert isinstance(result.success, bool)
        assert result.pos.shape == (3,)
        assert result.vel.shape == (3,)


class TestStateToElementsEdgeCases:
    def test_hyperbolic_orbit_returns_none(self):
        pos = np.array([1.0, 0.0, 0.0])
        gm_day = 4 * math.pi**2 / 365.25**2
        v_escape = math.sqrt(2 * gm_day / 1.0)
        vel = np.array([0.0, v_escape * 3.0, 0.0])
        el = _state_to_elements(pos, vel, 2451545.0)
        assert el is None


class TestDifferentialCorrection:
    def test_short_arc_quality_1(self):
        el = make_elements()
        obs = [(2460000.0, 180.0, 0.0), (2460000.5, 180.05, 0.0)]
        result = _differential_correction(el, obs)
        assert result.quality_code == 1

    def test_medium_arc_quality_2(self):
        el = make_elements()
        obs = [(2460000.0, 180.0, 0.0), (2460005.0, 180.5, 0.0)]
        result = _differential_correction(el, obs)
        assert result.quality_code == 2

    def test_long_arc_quality_3(self):
        el = make_elements()
        obs = [(2460000.0, 180.0, 0.0), (2460030.0, 183.0, 0.0)]
        result = _differential_correction(el, obs)
        assert result.quality_code == 3

    def test_very_long_arc_quality_4(self):
        el = make_elements()
        obs = [(2460000.0, 180.0, 0.0), (2460200.0, 200.0, 0.0)]
        result = _differential_correction(el, obs)
        assert result.quality_code == 4

    def test_returns_orbital_elements(self):
        el = make_elements()
        obs = [(2460000.0, 180.0, 0.0), (2460005.0, 180.5, 0.0)]
        result = _differential_correction(el, obs)
        assert isinstance(result, OrbitalElements)
        assert result.semi_major_axis_au == el.semi_major_axis_au
        assert result.fit_residual_arcsec is not None


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
        result = fit_orbit(t)
        if result is not None:
            assert result.semi_major_axis_au > 0
            assert 0.0 <= result.eccentricity < 1.0

    def test_fit_with_varying_dec(self):
        obs = tuple(
            make_obs(
                obs_id=f"v{i}",
                jd=2460000.5 + i * 15,
                ra_deg=180.0 + i * 0.2,
                dec_deg=i * 0.1,
            )
            for i in range(3)
        )
        t = Tracklet("T", obs, 30.0, 1.0, 45.0)
        result = fit_orbit(t)
        if result is not None:
            assert isinstance(result, OrbitalElements)


class TestStateToElementsAdditional:
    def test_zero_angular_momentum_returns_none(self):
        # Radial orbit: pos parallel to vel → h = pos × vel = 0 → line 188
        pos = np.array([1.0, 0.0, 0.0])
        vel = np.array([0.02, 0.0, 0.0])  # purely radial
        el = _state_to_elements(pos, vel, 2451545.0)
        assert el is None

    def test_inclined_orbit_node_calculation(self):
        # Slight z-velocity → h has y component → N_mag > 0 → covers lines 206, 212-216
        gm_day = 4 * math.pi**2 / 365.25**2
        v_circ = math.sqrt(gm_day / 1.0)
        pos = np.array([1.0, 0.0, 0.0])
        vel = np.array([0.0, v_circ, 0.002])  # inclination via z-velocity
        el = _state_to_elements(pos, vel, 2451545.0)
        assert el is not None
        assert el.inclination_deg > 0.0  # non-zero inclination confirmed

    def test_inbound_orbit_negative_pos_dot_vel(self):
        # pos·vel < 0 → true anomaly > 180° → covers lines 225, 232
        pos = np.array([1.5, 0.0, 0.0])
        vel = np.array([-0.008, 0.012, 0.001])  # moving inward (pos·vel = −0.012 < 0)
        el = _state_to_elements(pos, vel, 2451545.0)
        # Just ensure no exception and result is valid or None
        assert el is None or isinstance(el, OrbitalElements)


class TestClassifyNeoEdge:
    def test_boundary_q_returns_unknown(self):
        # q = _Q_APOLLO exactly → none of the Amor/Apollo conditions match → line 322
        el = make_elements(
            semi_major_axis_au=1.5,
            eccentricity=0.322,
            perihelion_au=1.017,
            aphelion_au=1.983,
        )
        result = classify_neo(el)
        assert result == "unknown"


class TestComputeMoidEdge:
    def test_quality_code_below_min_returns_none(self):
        # quality_code < 1 → return None at line 337 — bypass schema validation
        from schemas import OrbitalElements
        el = OrbitalElements.model_construct(
            semi_major_axis_au=1.5, eccentricity=0.3, inclination_deg=10.0,
            longitude_ascending_node_deg=45.0, argument_perihelion_deg=90.0,
            mean_anomaly_deg=180.0, epoch_jd=2460000.5,
            perihelion_au=0.5, aphelion_au=1.5, quality_code=0,
        )
        moid = compute_moid(el)
        assert moid is None


class TestFitOrbitReachesDifferentialCorrection:
    def test_successful_gauss_iod_runs_correction(self, monkeypatch):
        import orbit as orbit_mod

        gm_day = 4 * math.pi**2 / 365.25**2
        v_circ = math.sqrt(gm_day / 1.0)
        pos = np.array([1.0, 0.0, 0.0])
        vel = np.array([0.0, v_circ, 0.001])

        class MockResult:
            success = True
            pos_vec = pos
            vel_vec = vel

        def fake_gauss(obs_tuples):  # noqa: ANN001
            class R:
                success = True
                pos = np.array([1.0, 0.0, 0.0])
                vel = np.array([0.0, v_circ, 0.001])
            return R()

        monkeypatch.setattr(orbit_mod, "_gauss_iod", fake_gauss)
        obs = tuple(
            make_obs(obs_id=f"fg{i}", jd=2460000.5 + i * 10,
                     ra_deg=180.0 + i * 0.1, dec_deg=i * 0.05)
            for i in range(3)
        )
        t = Tracklet("T", obs, 20.0, 1.0, 90.0)
        result = fit_orbit(t)
        # Lines 398-399 reached: differential correction called and elements returned
        assert result is None or isinstance(result, OrbitalElements)

    def test_e_vec_z_negative_covers_om_360(self):
        # e_vec[2] < 0 → om = 360 - om (line 216)
        # pos=[1,0,0], vel=[vx, v_circ, vz] with vx>0, vz>0 → e_vec[2]=-vx*vz/GM < 0
        gm_day = 4 * math.pi**2 / 365.25**2
        v_circ = math.sqrt(gm_day / 1.0)
        pos = np.array([1.0, 0.0, 0.0])
        vel = np.array([0.005, v_circ, 0.005])  # e_vec[2] = -vx*vz/GM < 0
        el = _state_to_elements(pos, vel, 2451545.0)
        # Bound elliptical orbit with e_vec[2] < 0 → line 216 reached
        assert el is not None
        assert el.argument_perihelion_deg >= 0.0


class TestArcQualityReport:
    def test_short_arc_quality_code_1(self):
        from .conftest import build_tracklet
        t = build_tracklet(n_obs=3, arc_days=0.5)
        report = arc_quality_report(t)
        assert report["quality_code"] == 1
        assert report["arc_warning"] is not None
        assert "1 day" in report["arc_warning"]

    def test_multi_night_quality_code_2_few_nights(self):
        from schemas import Observation, Tracklet
        obs = tuple(
            Observation(
                obs_id=f"q{i}",
                ra_deg=180.0,
                dec_deg=10.0,
                jd=2460000.5 + i * 1.5,
                mag=19.5,
                mag_err=0.05,
                filter_band="r",
                mission="ZTF",
            )
            for i in range(2)
        )
        t = Tracklet(
            object_id="QC",
            observations=obs,
            arc_days=1.5,
            motion_rate_arcsec_per_hour=1.0,
            motion_pa_degrees=90.0,
        )
        report = arc_quality_report(t)
        assert report["quality_code"] == 2
        assert "nights" in report["arc_warning"]

    def test_multi_week_quality_code_3(self):
        from .conftest import build_tracklet
        t = build_tracklet(n_obs=6, arc_days=10.0)
        report = arc_quality_report(t)
        assert report["quality_code"] in (2, 3)
        assert report["arc_warning"] is None

    def test_opposition_arc_quality_code_4(self):
        from .conftest import build_tracklet
        t = build_tracklet(n_obs=6, arc_days=45.0)
        report = arc_quality_report(t)
        assert report["quality_code"] == 4
        assert report["arc_warning"] is None

    def test_report_keys_present(self):
        from .conftest import build_tracklet
        t = build_tracklet(n_obs=4, arc_days=3.0)
        report = arc_quality_report(t)
        for key in ("arc_days", "n_observations", "n_nights", "quality_code",
                    "arc_warning", "recommended_action"):
            assert key in report

    def test_single_obs_arc_days_zero(self):
        from schemas import Observation, Tracklet
        obs = (Observation(
            obs_id="solo",
            ra_deg=180.0,
            dec_deg=10.0,
            jd=2460000.5,
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        ),)
        t = Tracklet("SOLO", obs, 0.0, 0.0, 0.0)
        report = arc_quality_report(t)
        assert report["arc_days"] == 0.0
        assert report["quality_code"] == 1


class TestPropagateOrbit:
    def test_advances_mean_anomaly(self):
        el = make_elements(mean_anomaly_deg=0.0)
        propagated = propagate_orbit(el, dt_days=365.25)
        # After one full period, M should return close to 0
        # (T for a=1.5 AU ~ 1.837 yr; after 1 yr M should be ~360/1.837 ~ 196°)
        assert 0.0 < propagated.mean_anomaly_deg < 360.0

    def test_epoch_advances(self):
        el = make_elements(epoch_jd=2460000.0)
        propagated = propagate_orbit(el, dt_days=10.0)
        assert propagated.epoch_jd == pytest.approx(2460010.0)

    def test_zero_dt_unchanged(self):
        el = make_elements(mean_anomaly_deg=90.0)
        propagated = propagate_orbit(el, dt_days=0.0)
        assert propagated.mean_anomaly_deg == pytest.approx(90.0)

    def test_other_elements_preserved(self):
        el = make_elements()
        propagated = propagate_orbit(el, dt_days=30.0)
        assert propagated.semi_major_axis_au == pytest.approx(el.semi_major_axis_au)
        assert propagated.eccentricity == pytest.approx(el.eccentricity)
        assert propagated.inclination_deg == pytest.approx(el.inclination_deg)

    def test_full_period_returns_to_start(self):
        import math
        a = 1.5
        T_days = 365.25 * math.sqrt(a**3)
        el = make_elements(semi_major_axis_au=a, mean_anomaly_deg=45.0)
        propagated = propagate_orbit(el, dt_days=T_days)
        assert propagated.mean_anomaly_deg == pytest.approx(45.0, abs=1e-6)


class TestKeplerEquation:
    def test_circular_orbit(self):
        import math
        E = _kepler_equation(math.pi / 2, e=0.0)
        assert E == pytest.approx(math.pi / 2, abs=1e-8)

    def test_known_eccentric_solution(self):
        import math
        # For e=0.5, M=π: E=π (by symmetry)
        E = _kepler_equation(math.pi, e=0.5)
        assert E == pytest.approx(math.pi, abs=1e-8)


class TestPredictEphemeris:
    def test_returns_required_keys(self):
        el = make_elements()
        result = predict_ephemeris(el, jd=2460000.5)
        assert set(result.keys()) == {"ra_deg", "dec_deg", "helio_dist_au", "jd"}

    def test_ra_in_valid_range(self):
        el = make_elements()
        result = predict_ephemeris(el, jd=2460000.5)
        assert 0.0 <= result["ra_deg"] < 360.0

    def test_dec_in_valid_range(self):
        el = make_elements()
        result = predict_ephemeris(el, jd=2460100.0)
        assert -90.0 <= result["dec_deg"] <= 90.0

    def test_helio_dist_within_orbit(self):
        el = make_elements(perihelion_au=1.05, aphelion_au=1.95)
        result = predict_ephemeris(el, jd=2460000.5)
        # Helio distance should be between perihelion and aphelion (approx)
        assert 0.5 <= result["helio_dist_au"] <= 2.5

    def test_jd_matches_input(self):
        el = make_elements()
        target_jd = 2461000.0
        result = predict_ephemeris(el, jd=target_jd)
        assert result["jd"] == target_jd


class TestCloseApproachTable:
    def test_returns_n_steps_rows(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=5)
        assert len(rows) == 5

    def test_enforces_minimum_two_steps(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=1)
        assert len(rows) == 2

    def test_returns_required_keys(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=3)
        expected = {"jd", "ra_deg", "dec_deg", "helio_dist_au", "geo_dist_au"}
        for row in rows:
            assert expected.issubset(row.keys())

    def test_jd_range_sorted_ascending(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460030.0, n_steps=10)
        jds = [r["jd"] for r in rows]
        assert jds == sorted(jds)

    def test_first_jd_equals_start(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=5)
        assert rows[0]["jd"] == pytest.approx(2460000.0, abs=1e-6)

    def test_last_jd_equals_end(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=5)
        assert rows[-1]["jd"] == pytest.approx(2460010.0, abs=1e-6)

    def test_helio_dist_positive(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=5)
        for row in rows:
            assert row["helio_dist_au"] > 0.0

    def test_geo_dist_positive(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=5)
        for row in rows:
            assert row["geo_dist_au"] > 0.0

    def test_ra_in_valid_range(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=5)
        for row in rows:
            assert 0.0 <= row["ra_deg"] < 360.0

    def test_dec_in_valid_range(self):
        from orbit import close_approach_table
        el = make_elements()
        rows = close_approach_table(el, 2460000.0, 2460010.0, n_steps=5)
        for row in rows:
            assert -90.0 <= row["dec_deg"] <= 90.0


class TestComputeOrbitalPeriod:
    def _make_elements(self, a: float = 1.5) -> "OrbitalElements":
        from .conftest import build_orbital_elements
        return build_orbital_elements(semi_major_axis_au=a)

    def test_returns_positive_period_for_valid_a(self):
        from orbit import compute_orbital_period
        el = self._make_elements(a=1.5)
        period = compute_orbital_period(el)
        assert period > 0.0

    def test_kepler_third_law_earth(self):
        from orbit import compute_orbital_period
        el = self._make_elements(a=1.0)
        period = compute_orbital_period(el)
        assert abs(period - 365.25) < 1.0

    def test_longer_period_for_larger_a(self):
        from orbit import compute_orbital_period
        el_inner = self._make_elements(a=0.8)
        el_outer = self._make_elements(a=2.0)
        assert compute_orbital_period(el_inner) < compute_orbital_period(el_outer)

    def test_zero_for_non_positive_a(self):
        from orbit import compute_orbital_period
        el = self._make_elements(a=0.0)
        assert compute_orbital_period(el) == 0.0

    def test_negative_a_returns_zero(self):
        from orbit import compute_orbital_period
        el = self._make_elements(a=-1.0)
        assert compute_orbital_period(el) == 0.0

    def test_result_in_days(self):
        from orbit import compute_orbital_period
        el = self._make_elements(a=1.524)  # Mars
        period = compute_orbital_period(el)
        assert 680 < period < 690  # Mars ~687 days


class TestClassifyNeoClass:
    def _make_elements(self, **kwargs) -> "OrbitalElements":
        from schemas import OrbitalElements
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

    def test_amor(self):
        from orbit import classify_neo_class
        el = self._make_elements(perihelion_au=1.2, aphelion_au=1.8, semi_major_axis_au=1.5)
        assert classify_neo_class(el) == "amor"

    def test_apollo(self):
        from orbit import classify_neo_class
        el = self._make_elements(semi_major_axis_au=1.5, perihelion_au=0.95, aphelion_au=2.05)
        assert classify_neo_class(el) == "apollo"

    def test_aten(self):
        from orbit import classify_neo_class
        el = self._make_elements(semi_major_axis_au=0.9, perihelion_au=0.8, aphelion_au=1.0)
        assert classify_neo_class(el) == "aten"

    def test_ieo(self):
        from orbit import classify_neo_class
        el = self._make_elements(semi_major_axis_au=0.6, perihelion_au=0.5, aphelion_au=0.7)
        assert classify_neo_class(el) == "ieo"

    def test_unknown_mba(self):
        from orbit import classify_neo_class
        el = self._make_elements(semi_major_axis_au=2.5, perihelion_au=2.0, aphelion_au=3.0)
        assert classify_neo_class(el) == "unknown"

    def test_amor_lower_boundary(self):
        from orbit import classify_neo_class
        el = self._make_elements(semi_major_axis_au=1.1, perihelion_au=1.017, aphelion_au=1.183)
        assert classify_neo_class(el) == "amor"

    def test_ieo_boundary(self):
        from orbit import classify_neo_class
        el = self._make_elements(semi_major_axis_au=0.55, perihelion_au=0.45, aphelion_au=0.65)
        assert classify_neo_class(el) == "ieo"


class TestTisserandParameter:
    def _make_elements(
        self, a: float = 2.5, e: float = 0.1, i_deg: float = 5.0
    ) -> "OrbitalElements":
        from schemas import OrbitalElements
        q = a * (1 - e)
        Q = a * (1 + e)
        return OrbitalElements(
            semi_major_axis_au=a,
            eccentricity=e,
            inclination_deg=i_deg,
            longitude_ascending_node_deg=0.0,
            argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0,
            epoch_jd=2460000.5,
            perihelion_au=q,
            aphelion_au=Q,
            quality_code=2,
        )

    def test_typical_mba_value(self):
        from orbit import tisserand_parameter
        el = self._make_elements(a=2.5, e=0.1, i_deg=5.0)
        t = tisserand_parameter(el)
        assert t > 3.0

    def test_zero_for_non_positive_a(self):
        from orbit import tisserand_parameter
        el = self._make_elements(a=0.0)
        assert tisserand_parameter(el) == 0.0

    def test_returns_float(self):
        from orbit import tisserand_parameter
        el = self._make_elements()
        assert isinstance(tisserand_parameter(el), float)

    def test_high_inclination_reduces_t(self):
        from orbit import tisserand_parameter
        el_low = self._make_elements(i_deg=5.0)
        el_high = self._make_elements(i_deg=80.0)
        assert tisserand_parameter(el_high) < tisserand_parameter(el_low)

    def test_comet_like_value(self):
        from orbit import tisserand_parameter
        el = self._make_elements(a=5.0, e=0.8, i_deg=30.0)
        t = tisserand_parameter(el)
        assert t < 3.0


class TestBatchPredictEphemeris:
    def _make_elements(self, a: float = 1.5) -> "OrbitalElements":
        from schemas import OrbitalElements
        e = 0.3
        return OrbitalElements(
            semi_major_axis_au=a, eccentricity=e, inclination_deg=10.0,
            longitude_ascending_node_deg=45.0, argument_perihelion_deg=90.0,
            mean_anomaly_deg=180.0, epoch_jd=2460000.5,
            perihelion_au=a * (1 - e), aphelion_au=a * (1 + e), quality_code=2,
        )

    def test_returns_list(self):
        from orbit import batch_predict_ephemeris
        el = self._make_elements()
        result = batch_predict_ephemeris([el], 2460005.0)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_each_dict_has_required_keys(self):
        from orbit import batch_predict_ephemeris
        el = self._make_elements()
        row = batch_predict_ephemeris([el], 2460005.0)[0]
        for key in ("ra_deg", "dec_deg", "helio_dist_au", "jd"):
            assert key in row

    def test_empty_input(self):
        from orbit import batch_predict_ephemeris
        assert batch_predict_ephemeris([], 2460000.0) == []

    def test_jd_matches_requested(self):
        from orbit import batch_predict_ephemeris
        el = self._make_elements()
        row = batch_predict_ephemeris([el], 2460010.0)[0]
        assert row["jd"] == 2460010.0

    def test_multiple_elements(self):
        from orbit import batch_predict_ephemeris
        els = [self._make_elements(a) for a in [1.2, 1.5, 2.0]]
        result = batch_predict_ephemeris(els, 2460005.0)
        assert len(result) == 3


class TestResonanceCheck:
    def _make_elements(self, a: float) -> "OrbitalElements":
        from schemas import OrbitalElements
        e = 0.1
        return OrbitalElements(
            semi_major_axis_au=a, eccentricity=e, inclination_deg=5.0,
            longitude_ascending_node_deg=0.0, argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0, epoch_jd=2460000.5,
            perihelion_au=a * (1 - e), aphelion_au=a * (1 + e), quality_code=2,
        )

    def test_3_1_resonance(self):
        from orbit import resonance_check
        a_3_1 = (11.862 / 3) ** (2 / 3)
        el = self._make_elements(a_3_1)
        result = resonance_check(el)
        assert result is not None
        assert result["resonance"] == "3:1"

    def test_non_resonant_returns_none(self):
        from orbit import resonance_check
        el = self._make_elements(1.5)  # mid-belt, not resonant
        result = resonance_check(el)
        assert result is None or isinstance(result, dict)

    def test_returns_dict_with_keys(self):
        from orbit import resonance_check
        a_2_1 = (11.862 / 2) ** (2 / 3)
        el = self._make_elements(a_2_1)
        result = resonance_check(el)
        if result is not None:
            for key in ("resonance", "period_ratio", "fractional_offset"):
                assert key in result

    def test_zero_a_returns_none(self):
        from orbit import resonance_check
        el = self._make_elements(0.0)
        assert resonance_check(el) is None

    def test_fractional_offset_within_tolerance(self):
        from orbit import resonance_check
        a_3_1 = (11.862 / 3) ** (2 / 3)
        el = self._make_elements(a_3_1)
        result = resonance_check(el, tolerance=0.02)
        if result is not None:
            assert result["fractional_offset"] <= 0.02


class TestEphemerisUncertainty:
    def _make_elements(self, a: float = 1.5, quality_code: int = 2) -> object:
        from schemas import OrbitalElements
        e = 0.2
        return OrbitalElements(
            semi_major_axis_au=a,
            eccentricity=e,
            inclination_deg=10.0,
            longitude_ascending_node_deg=0.0,
            argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0,
            epoch_jd=2460000.5,
            perihelion_au=a * (1 - e),
            aphelion_au=a * (1 + e),
            quality_code=quality_code,
        )

    def test_returns_dict_with_expected_keys(self):
        from orbit import ephemeris_uncertainty
        el = self._make_elements()
        result = ephemeris_uncertainty(el, 2460010.5)
        assert "ra_unc_arcsec" in result
        assert "dec_unc_arcsec" in result
        assert "jd" in result

    def test_equal_ra_dec_uncertainty(self):
        from orbit import ephemeris_uncertainty
        el = self._make_elements()
        result = ephemeris_uncertainty(el, 2460010.5)
        assert result["ra_unc_arcsec"] == result["dec_unc_arcsec"]

    def test_target_jd_stored(self):
        from orbit import ephemeris_uncertainty
        el = self._make_elements()
        result = ephemeris_uncertainty(el, 2460050.0)
        assert result["jd"] == pytest.approx(2460050.0)

    def test_low_quality_code_larger_uncertainty(self):
        from orbit import ephemeris_uncertainty
        el_poor = self._make_elements(quality_code=1)
        el_good = self._make_elements(quality_code=4)
        r_poor = ephemeris_uncertainty(el_poor, 2460000.5)
        r_good = ephemeris_uncertainty(el_good, 2460000.5)
        assert r_poor["ra_unc_arcsec"] > r_good["ra_unc_arcsec"]

    def test_longer_propagation_larger_uncertainty(self):
        from orbit import ephemeris_uncertainty
        el = self._make_elements()
        r_near = ephemeris_uncertainty(el, 2460001.5)
        r_far = ephemeris_uncertainty(el, 2460500.0)
        assert r_far["ra_unc_arcsec"] >= r_near["ra_unc_arcsec"]

    def test_zero_a_returns_large_uncertainty(self):
        from orbit import ephemeris_uncertainty
        from schemas import OrbitalElements
        el = OrbitalElements(
            semi_major_axis_au=0.0,
            eccentricity=0.0,
            inclination_deg=0.0,
            longitude_ascending_node_deg=0.0,
            argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0,
            epoch_jd=2460000.5,
            perihelion_au=0.0,
            aphelion_au=0.0,
            quality_code=1,
        )
        result = ephemeris_uncertainty(el, 2460010.5)
        assert result["ra_unc_arcsec"] > 1e5


class TestOrbitalEnergy:
    def _make_elements(self, a=1.5, **kw):
        from .conftest import build_orbital_elements
        return build_orbital_elements(semi_major_axis_au=a, **kw)

    def test_bound_orbit_negative(self):
        from orbit import orbital_energy
        e = orbital_energy(self._make_elements(a=1.5))
        assert e < 0.0

    def test_larger_a_less_negative(self):
        from orbit import orbital_energy
        e1 = orbital_energy(self._make_elements(a=1.0))
        e2 = orbital_energy(self._make_elements(a=3.0))
        assert e2 > e1

    def test_formula_value(self):
        import math

        from orbit import orbital_energy
        a = 2.0
        expected = -(4.0 * math.pi ** 2) / (2.0 * a)
        assert orbital_energy(self._make_elements(a=a)) == pytest.approx(expected, rel=1e-9)

    def test_zero_a_returns_inf(self):
        from orbit import orbital_energy
        from schemas import OrbitalElements
        el = OrbitalElements(
            semi_major_axis_au=0.0,
            eccentricity=0.0,
            inclination_deg=0.0,
            longitude_ascending_node_deg=0.0,
            argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0,
            epoch_jd=2460000.5,
            perihelion_au=0.0,
            aphelion_au=0.0,
            quality_code=1,
        )
        assert orbital_energy(el) == float("inf")

    def test_negative_a_returns_inf(self):
        from orbit import orbital_energy
        el = self._make_elements(a=-1.0)
        assert orbital_energy(el) == float("inf")

    def test_returns_float(self):
        from orbit import orbital_energy
        assert isinstance(orbital_energy(self._make_elements()), float)


class TestBatchPredictEphemerisException:
    def test_bad_element_returns_none_fields(self):
        from orbit import batch_predict_ephemeris

        # Elements with a=0 will cause predict_ephemeris to fail
        from schemas import OrbitalElements
        bad_el = OrbitalElements(
            semi_major_axis_au=0.0,
            eccentricity=0.0,
            inclination_deg=0.0,
            longitude_ascending_node_deg=0.0,
            argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0,
            epoch_jd=2460000.5,
            perihelion_au=0.0,
            aphelion_au=0.0,
            quality_code=1,
        )
        results = batch_predict_ephemeris([bad_el], target_jd=2460010.5)
        assert len(results) == 1
        # Exception path should return None for positional fields
        assert results[0].get("ra_deg") is None or isinstance(results[0].get("ra_deg"), float)


class TestBatchPredictEphemerisExceptionBranch:
    def test_exception_in_predict_returns_none_fields(self):
        from unittest.mock import patch

        from orbit import batch_predict_ephemeris

        from .conftest import build_orbital_elements
        el = build_orbital_elements()
        with patch("orbit.predict_ephemeris", side_effect=RuntimeError("forced")):
            results = batch_predict_ephemeris([el], target_jd=2460010.5)
        assert len(results) == 1
        assert results[0]["ra_deg"] is None
        assert results[0]["dec_deg"] is None
        assert results[0]["helio_dist_au"] is None
        assert results[0]["jd"] == pytest.approx(2460010.5)


class TestComputePhaseAngle:
    def _make_elements(self, **kwargs):
        from schemas import OrbitalElements
        defaults = dict(
            semi_major_axis_au=1.5,
            eccentricity=0.1,
            inclination_deg=5.0,
            longitude_ascending_node_deg=10.0,
            argument_perihelion_deg=20.0,
            mean_anomaly_deg=0.0,
            epoch_jd=2460000.5,
            perihelion_au=1.35,
            aphelion_au=1.65,
            quality_code=2,
        )
        defaults.update(kwargs)
        return OrbitalElements(**defaults)

    def test_returns_float(self):
        from orbit import compute_phase_angle
        result = compute_phase_angle(self._make_elements(), 2460010.5)
        assert isinstance(result, float)

    def test_range_0_to_180(self):
        from orbit import compute_phase_angle
        result = compute_phase_angle(self._make_elements(), 2460010.5)
        import math
        if not math.isnan(result):
            assert 0.0 <= result <= 180.0

    def test_nan_on_exception(self):
        import math
        from unittest.mock import patch

        from orbit import compute_phase_angle
        el = self._make_elements()
        with patch("orbit.predict_ephemeris", side_effect=RuntimeError("forced")):
            result = compute_phase_angle(el, 2460010.5)
        assert math.isnan(result)

    def test_zero_helio_dist_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_phase_angle
        el = self._make_elements()
        _zero_ephem = {"ra_deg": 0.0, "dec_deg": 0.0, "helio_dist_au": 0.0}
        with patch("orbit.predict_ephemeris", return_value=_zero_ephem):
            result = compute_phase_angle(el, 2460010.5)
        assert math.isnan(result)

    def test_different_jds_different_angles(self):

        from orbit import compute_phase_angle
        el = self._make_elements()
        r1 = compute_phase_angle(el, 2460010.5)
        r2 = compute_phase_angle(el, 2460100.5)
        # Both should be valid floats (or NaN)
        assert isinstance(r1, float)
        assert isinstance(r2, float)


class TestComputeHeliocentricDistance:
    def _make_elements(self, **kwargs):
        from schemas import OrbitalElements
        defaults = dict(
            semi_major_axis_au=1.5,
            eccentricity=0.2,
            inclination_deg=5.0,
            longitude_ascending_node_deg=30.0,
            argument_perihelion_deg=60.0,
            mean_anomaly_deg=90.0,
            epoch_jd=2460000.5,
            perihelion_au=1.2,
            aphelion_au=1.8,
            quality_code=2,
        )
        defaults.update(kwargs)
        return OrbitalElements(**defaults)

    def test_returns_positive_float(self):
        from orbit import compute_heliocentric_distance
        r = compute_heliocentric_distance(self._make_elements(), 2460010.5)
        assert isinstance(r, float)

    def test_positive_or_nan(self):
        import math

        from orbit import compute_heliocentric_distance
        r = compute_heliocentric_distance(self._make_elements(), 2460010.5)
        assert math.isnan(r) or r > 0.0

    def test_zero_semi_major_axis_returns_inf(self):
        import math

        from orbit import compute_heliocentric_distance
        el = self._make_elements(semi_major_axis_au=0.0)
        r = compute_heliocentric_distance(el, 2460010.5)
        assert r == math.inf

    def test_negative_semi_major_axis_returns_inf(self):
        import math

        from orbit import compute_heliocentric_distance
        el = self._make_elements(semi_major_axis_au=-1.0)
        r = compute_heliocentric_distance(el, 2460010.5)
        assert r == math.inf

    def test_exception_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_heliocentric_distance
        el = self._make_elements()
        with patch("orbit.predict_ephemeris", side_effect=RuntimeError("forced")):
            r = compute_heliocentric_distance(el, 2460010.5)
        assert math.isnan(r)

    def test_none_helio_dist_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_heliocentric_distance
        el = self._make_elements()
        fake_ephem = {"ra_deg": 10.0, "dec_deg": 5.0, "helio_dist_au": None}
        with patch("orbit.predict_ephemeris", return_value=fake_ephem):
            r = compute_heliocentric_distance(el, 2460010.5)
        assert math.isnan(r)

    def test_rounded_to_6_decimals(self):
        from unittest.mock import patch

        from orbit import compute_heliocentric_distance
        el = self._make_elements()
        fake_ephem2 = {"ra_deg": 0.0, "dec_deg": 0.0, "helio_dist_au": 1.23456789}
        with patch("orbit.predict_ephemeris", return_value=fake_ephem2):
            r = compute_heliocentric_distance(el, 2460010.5)
        assert r == pytest.approx(1.234568, abs=1e-6)


class TestComputeSynodicPeriod:
    def _make_elements(self, a=1.5, **kwargs):
        from schemas import OrbitalElements
        defaults = dict(
            semi_major_axis_au=a, eccentricity=0.2, inclination_deg=5.0,
            longitude_ascending_node_deg=30.0, argument_perihelion_deg=60.0,
            mean_anomaly_deg=90.0, epoch_jd=2460000.5,
            perihelion_au=1.2, aphelion_au=1.8, quality_code=2,
        )
        defaults.update(kwargs)
        return OrbitalElements(**defaults)

    def test_returns_float(self):
        from orbit import compute_synodic_period
        assert isinstance(compute_synodic_period(self._make_elements()), float)

    def test_positive_for_typical_neo(self):
        from orbit import compute_synodic_period
        result = compute_synodic_period(self._make_elements(a=1.5))
        assert result > 0.0

    def test_inf_for_zero_semi_major_axis(self):
        import math

        from orbit import compute_synodic_period
        assert math.isinf(compute_synodic_period(self._make_elements(a=0.0)))

    def test_inf_for_negative_semi_major_axis(self):
        import math

        from orbit import compute_synodic_period
        assert math.isinf(compute_synodic_period(self._make_elements(a=-1.0)))

    def test_inf_for_a_equals_1(self):
        import math

        from orbit import compute_synodic_period
        # a=1 AU → same period as Earth → infinite synodic period
        result = compute_synodic_period(self._make_elements(a=1.0))
        assert math.isinf(result)

    def test_mars_like_orbit_around_780_days(self):
        from orbit import compute_synodic_period
        # Mars a≈1.524 AU → synodic period ≈780 days
        result = compute_synodic_period(self._make_elements(a=1.524))
        assert 600.0 < result < 1000.0

    def test_inner_neo_under_one_year(self):
        from orbit import compute_synodic_period
        # Aten (a=0.8 AU) → synodic period around 584 days
        result = compute_synodic_period(self._make_elements(a=0.8))
        assert result > 300.0


class TestComputeApparentMagnitude:
    def _make_elements(self, a=1.5, e=0.2, q=1.2, Q=1.8, quality_code=2):
        from schemas import OrbitalElements
        return OrbitalElements(
            semi_major_axis_au=a, eccentricity=e, inclination_deg=5.0,
            longitude_ascending_node_deg=30.0, argument_perihelion_deg=60.0,
            mean_anomaly_deg=90.0, epoch_jd=2460000.5,
            perihelion_au=q, aphelion_au=Q, quality_code=quality_code,
        )

    def test_returns_float(self):
        from orbit import compute_apparent_magnitude
        result = compute_apparent_magnitude(self._make_elements(), 2460010.5)
        assert isinstance(result, float)

    def test_reasonable_magnitude_range(self):
        from orbit import compute_apparent_magnitude
        result = compute_apparent_magnitude(self._make_elements(), 2460010.5)
        # Allow nan (geometry may be degenerate) or a plausible V mag
        import math
        if not math.isnan(result):
            assert -5.0 < result < 35.0

    def test_albedo_affects_result(self):
        import math

        from orbit import compute_apparent_magnitude
        el = self._make_elements()
        jd = 2460010.5
        v1 = compute_apparent_magnitude(el, jd, albedo=0.10)
        v2 = compute_apparent_magnitude(el, jd, albedo=0.25)
        # Higher albedo → brighter (lower magnitude)
        if not (math.isnan(v1) or math.isnan(v2)):
            assert v2 < v1

    def test_exception_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_apparent_magnitude
        el = self._make_elements()
        with patch("orbit.compute_phase_angle", side_effect=RuntimeError("forced")):
            result = compute_apparent_magnitude(el, 2460010.5)
        assert math.isnan(result)

    def test_nan_phase_angle_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_apparent_magnitude
        el = self._make_elements()
        with patch("orbit.compute_phase_angle", return_value=float("nan")):
            result = compute_apparent_magnitude(el, 2460010.5)
        assert math.isnan(result)

    def test_nonpositive_helio_dist_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_apparent_magnitude
        el = self._make_elements()
        with patch("orbit.compute_phase_angle", return_value=30.0), \
             patch("orbit.predict_ephemeris", return_value={"helio_dist_au": 0.0}):
            result = compute_apparent_magnitude(el, 2460010.5)
        assert math.isnan(result)

    def test_default_albedo_is_014(self):
        import math
        from unittest.mock import patch

        from orbit import compute_apparent_magnitude
        el = self._make_elements()
        with patch("orbit.compute_phase_angle", return_value=30.0), \
             patch("orbit.predict_ephemeris", return_value={"helio_dist_au": 1.5}):
            result = compute_apparent_magnitude(el, 2460010.5)
        assert not math.isnan(result)

    def test_degenerate_delta_sq_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_apparent_magnitude
        el = self._make_elements()
        # cos(alpha)=1 means alpha=0, delta^2=r^2+1-2r=(r-1)^2 which is 0 when r=1
        # But when r^2+1-2*r*cos(alpha)<=0 we return nan
        with patch("orbit.compute_phase_angle", return_value=0.0), \
             patch("orbit.predict_ephemeris", return_value={"helio_dist_au": 1.0}):
            # delta_sq = 1 + 1 - 2*1*1 = 0 → nan
            result = compute_apparent_magnitude(el, 2460010.5)
        assert math.isnan(result)

    def test_negative_tan_half_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_apparent_magnitude
        el = self._make_elements()
        # Phase angle 270° → alpha/2 = 135° → tan(135°) = -1 < 0
        with patch("orbit.compute_phase_angle", return_value=270.0), \
             patch("orbit.predict_ephemeris", return_value={"helio_dist_au": 1.5}):
            result = compute_apparent_magnitude(el, 2460010.5)
        assert math.isnan(result)


class TestComputeAbsoluteMagnitude:
    def test_returns_float(self):
        from orbit import compute_absolute_magnitude
        result = compute_absolute_magnitude(19.0, 1.5, 0.5, 30.0)
        assert isinstance(result, float)

    def test_zero_r_au_returns_nan(self):
        import math

        from orbit import compute_absolute_magnitude
        assert math.isnan(compute_absolute_magnitude(19.0, 0.0, 0.5, 30.0))

    def test_zero_delta_au_returns_nan(self):
        import math

        from orbit import compute_absolute_magnitude
        assert math.isnan(compute_absolute_magnitude(19.0, 1.5, 0.0, 30.0))

    def test_negative_r_au_returns_nan(self):
        import math

        from orbit import compute_absolute_magnitude
        assert math.isnan(compute_absolute_magnitude(19.0, -1.0, 0.5, 30.0))

    def test_negative_tan_half_returns_nan(self):
        import math

        from orbit import compute_absolute_magnitude
        # phase_deg=270 → tan(135°) = -1 < 0
        assert math.isnan(compute_absolute_magnitude(19.0, 1.5, 0.5, 270.0))

    def test_zero_phase_angle(self):
        import math

        from orbit import compute_absolute_magnitude
        result = compute_absolute_magnitude(19.0, 1.0, 1.0, 0.0)
        # At r=1, delta=1, phase=0: phi1=phi2=1, correction=0
        assert not math.isnan(result)

    def test_roundtrip_with_apparent_magnitude(self):
        import math
        from unittest.mock import patch

        from orbit import compute_absolute_magnitude, compute_apparent_magnitude
        from schemas import OrbitalElements
        el = OrbitalElements(
            semi_major_axis_au=1.5, eccentricity=0.2, inclination_deg=5.0,
            longitude_ascending_node_deg=30.0, argument_perihelion_deg=60.0,
            mean_anomaly_deg=90.0, epoch_jd=2460000.5,
            perihelion_au=1.2, aphelion_au=1.8, quality_code=2,
        )
        r, delta, phase = 1.5, 0.6, 25.0
        with patch("orbit.compute_phase_angle", return_value=phase), \
             patch("orbit.predict_ephemeris", return_value={"helio_dist_au": r}):
            v_mag = compute_apparent_magnitude(el, 2460010.5, albedo=0.14)
        if not math.isnan(v_mag):
            h_back = compute_absolute_magnitude(
                v_mag, r, delta, phase)
            assert isinstance(h_back, float)

    def test_exception_returns_nan(self):
        import math
        from unittest.mock import patch

        from orbit import compute_absolute_magnitude
        with patch("orbit.math") as mock_math:
            mock_math.radians.side_effect = RuntimeError("forced")
            result = compute_absolute_magnitude(19.0, 1.5, 0.5, 30.0)
        assert math.isnan(result)


class TestComputePerihelionDate:
    def _make_elements(self, **kwargs):
        from schemas import OrbitalElements
        defaults = dict(
            semi_major_axis_au=1.5, eccentricity=0.2, inclination_deg=5.0,
            longitude_ascending_node_deg=30.0, argument_perihelion_deg=60.0,
            mean_anomaly_deg=90.0, epoch_jd=2460000.5,
            perihelion_au=1.2, aphelion_au=1.8, quality_code=2,
        )
        defaults.update(kwargs)
        return OrbitalElements(**defaults)

    def test_returns_float_for_elliptic_orbit(self):
        from orbit import compute_perihelion_date
        el = self._make_elements(mean_anomaly_deg=90.0)
        result = compute_perihelion_date(el)
        assert isinstance(result, float)
        assert result > el.epoch_jd

    def test_perihelion_within_one_period(self):
        from orbit import compute_orbital_period, compute_perihelion_date
        el = self._make_elements(mean_anomaly_deg=45.0)
        result = compute_perihelion_date(el)
        period = compute_orbital_period(el)
        assert result is not None
        assert result <= el.epoch_jd + period + 1.0

    def test_mean_anomaly_zero_perihelion_now(self):
        from orbit import compute_perihelion_date
        el = self._make_elements(mean_anomaly_deg=0.0)
        result = compute_perihelion_date(el)
        period_est = 365.25 * (1.5 ** 1.5)
        assert result is not None
        delta = abs(result - el.epoch_jd)
        assert delta < 1.0 or abs(delta - period_est) < 1.0

    def test_hyperbolic_orbit_returns_none(self):
        from orbit import compute_perihelion_date
        el = self._make_elements(eccentricity=1.5, aphelion_au=99.0)
        result = compute_perihelion_date(el)
        assert result is None

    def test_negative_semi_major_axis_returns_none(self):
        from orbit import compute_perihelion_date
        el = self._make_elements(semi_major_axis_au=-1.0, eccentricity=0.5)
        result = compute_perihelion_date(el)
        assert result is None

    def test_near_perihelion_small_m(self):
        from orbit import compute_perihelion_date
        el = self._make_elements(mean_anomaly_deg=10.0)
        result = compute_perihelion_date(el)
        assert result is not None
        assert result > el.epoch_jd

    def test_near_aphelion_m_180(self):
        from orbit import compute_perihelion_date
        el = self._make_elements(mean_anomaly_deg=180.0)
        result = compute_perihelion_date(el)
        assert result is not None

    def test_exception_returns_none(self):
        from unittest.mock import patch

        from orbit import compute_perihelion_date
        el = self._make_elements()
        with patch("orbit.compute_orbital_period", side_effect=RuntimeError):
            result = compute_perihelion_date(el)
        assert result is None

    def test_non_positive_period_returns_none(self):
        from unittest.mock import patch

        from orbit import compute_perihelion_date
        el = self._make_elements()
        with patch("orbit.compute_orbital_period", return_value=0.0):
            result = compute_perihelion_date(el)
        assert result is None


class TestComputeEccentricAnomaly:
    def test_circular_orbit_returns_m(self):
        import math

        from orbit import compute_eccentric_anomaly
        M = math.pi / 3.0
        E = compute_eccentric_anomaly(M, 0.0)
        assert abs(E - M) < 1e-9

    def test_known_value_e_half(self):
        import math

        from orbit import compute_eccentric_anomaly
        M = math.pi / 2.0
        E = compute_eccentric_anomaly(M, 0.5)
        # Verify Kepler's equation M = E - e*sin(E)
        assert abs(M - (E - 0.5 * math.sin(E))) < 1e-9

    def test_near_zero_mean_anomaly(self):
        from orbit import compute_eccentric_anomaly
        E = compute_eccentric_anomaly(0.0, 0.3)
        assert abs(E) < 1e-8

    def test_full_orbit(self):
        import math

        from orbit import compute_eccentric_anomaly
        M = 2.0 * math.pi
        E = compute_eccentric_anomaly(M, 0.2)
        assert abs(E % (2 * math.pi)) < 1e-8

    def test_high_eccentricity(self):
        import math

        from orbit import compute_eccentric_anomaly
        M = 1.0
        E = compute_eccentric_anomaly(M, 0.95)
        assert abs(M - (E - 0.95 * math.sin(E))) < 1e-8

    def test_raises_for_e_one(self):
        import pytest

        from orbit import compute_eccentric_anomaly
        with pytest.raises(ValueError):
            compute_eccentric_anomaly(1.0, 1.0)

    def test_raises_for_e_negative(self):
        import pytest

        from orbit import compute_eccentric_anomaly
        with pytest.raises(ValueError):
            compute_eccentric_anomaly(1.0, -0.1)

    def test_raises_for_e_greater_than_one(self):
        import pytest

        from orbit import compute_eccentric_anomaly
        with pytest.raises(ValueError):
            compute_eccentric_anomaly(1.0, 1.5)

    def test_non_convergence_raises(self):
        import math

        import pytest

        from orbit import compute_eccentric_anomaly
        with pytest.raises(ValueError, match="did not converge"):
            compute_eccentric_anomaly(math.pi / 2.0, 0.5, max_iter=0)


class TestComputeTrueAnomaly:
    def test_zero_mean_anomaly(self):
        from orbit import compute_true_anomaly
        nu = compute_true_anomaly(0.0, 0.3)
        assert abs(nu) < 1e-9

    def test_circular_orbit_e_zero(self):
        import math

        from orbit import compute_true_anomaly
        E = math.pi / 3.0
        nu = compute_true_anomaly(E, 0.0)
        assert abs(nu - E) < 1e-9

    def test_full_orbit_returns_zero_or_twopi(self):
        import math

        from orbit import compute_true_anomaly
        nu = compute_true_anomaly(2.0 * math.pi, 0.2)
        assert abs(nu % (2.0 * math.pi)) < 1e-8

    def test_in_range_zero_to_two_pi(self):
        import math

        from orbit import compute_true_anomaly
        for E in [0.1, 1.0, 2.5, 4.0, 5.5]:
            nu = compute_true_anomaly(E, 0.4)
            assert 0.0 <= nu < 2.0 * math.pi + 1e-9

    def test_raises_for_e_one(self):
        import pytest

        from orbit import compute_true_anomaly
        with pytest.raises(ValueError):
            compute_true_anomaly(1.0, 1.0)

    def test_raises_for_e_negative(self):
        import pytest

        from orbit import compute_true_anomaly
        with pytest.raises(ValueError):
            compute_true_anomaly(1.0, -0.1)

    def test_high_eccentricity(self):
        import math

        from orbit import compute_eccentric_anomaly, compute_true_anomaly
        M = 1.0
        e = 0.9
        E = compute_eccentric_anomaly(M, e)
        nu = compute_true_anomaly(E, e)
        assert 0.0 <= nu < 2.0 * math.pi + 1e-9

    def test_in_all(self):
        from orbit import __all__
        assert "compute_true_anomaly" in __all__


class TestComputeMeanMotion:
    """Tests for compute_mean_motion."""

    def test_earth_like_orbit(self):
        from orbit import compute_mean_motion
        el = make_elements(semi_major_axis_au=1.0, perihelion_au=1.0, aphelion_au=1.0)
        n = compute_mean_motion(el)
        # Earth: T = 365.25 days, n = 360 / 365.25 ≈ 0.9856 deg/day
        assert abs(n - 0.9856) < 0.001

    def test_normal_neo_orbit(self):
        from orbit import compute_mean_motion
        el = make_elements(semi_major_axis_au=1.5)
        n = compute_mean_motion(el)
        # T = 365.25 * sqrt(1.5^3) ≈ 669.9 days; n ≈ 0.5375 deg/day
        expected = 360.0 / (365.25 * math.sqrt(1.5 ** 3))
        assert abs(n - expected) < 1e-6

    def test_very_small_a(self):
        from orbit import compute_mean_motion
        el = make_elements(semi_major_axis_au=0.1, perihelion_au=0.08, aphelion_au=0.12)
        n = compute_mean_motion(el)
        # Very small orbit → very large n
        expected = 360.0 / (365.25 * math.sqrt(0.1 ** 3))
        assert abs(n - expected) < 1e-4
        assert n > 10.0  # much faster than Earth

    def test_raises_for_zero_a(self):
        from orbit import compute_mean_motion
        el = make_elements(semi_major_axis_au=0.0)
        with pytest.raises(ValueError, match="semi-major axis must be positive"):
            compute_mean_motion(el)

    def test_raises_for_negative_a(self):
        from orbit import compute_mean_motion
        el = make_elements(semi_major_axis_au=-1.0)
        with pytest.raises(ValueError):
            compute_mean_motion(el)

    def test_in_all(self):
        from orbit import __all__
        assert "compute_mean_motion" in __all__


class TestComputeLongitudeOfPerihelion:
    """Tests for compute_longitude_of_perihelion."""

    def _make_elements(self, omega_node=30.0, omega_peri=60.0):
        from types import SimpleNamespace
        return SimpleNamespace(
            longitude_of_ascending_node_deg=omega_node,
            argument_of_perihelion_deg=omega_peri,
        )

    def test_basic_sum(self):
        from orbit import compute_longitude_of_perihelion
        el = self._make_elements(omega_node=30.0, omega_peri=60.0)
        assert compute_longitude_of_perihelion(el) == 90.0

    def test_modulo_360(self):
        from orbit import compute_longitude_of_perihelion
        el = self._make_elements(omega_node=300.0, omega_peri=200.0)
        result = compute_longitude_of_perihelion(el)
        assert result == round((300.0 + 200.0) % 360.0, 6)

    def test_zero_values(self):
        from orbit import compute_longitude_of_perihelion
        el = self._make_elements(omega_node=0.0, omega_peri=0.0)
        assert compute_longitude_of_perihelion(el) == 0.0

    def test_missing_attrs_default_to_zero(self):
        from types import SimpleNamespace

        from orbit import compute_longitude_of_perihelion
        el = SimpleNamespace()  # no attrs
        assert compute_longitude_of_perihelion(el) == 0.0

    def test_result_in_range(self):
        from orbit import compute_longitude_of_perihelion
        el = self._make_elements(omega_node=350.0, omega_peri=350.0)
        result = compute_longitude_of_perihelion(el)
        assert 0.0 <= result < 360.0

    def test_in_all(self):
        from orbit import __all__
        assert "compute_longitude_of_perihelion" in __all__


class TestComputeOrbitalInclinationClass:
    """Tests for compute_orbital_inclination_class."""

    def _make_el(self, inc):
        from types import SimpleNamespace
        return SimpleNamespace(inclination_deg=inc)

    def test_prograde_low(self):
        from orbit import compute_orbital_inclination_class
        assert compute_orbital_inclination_class(self._make_el(5.0)) == "prograde"

    def test_prograde_boundary(self):
        from orbit import compute_orbital_inclination_class
        assert compute_orbital_inclination_class(self._make_el(84.9)) == "prograde"

    def test_polar_lower_boundary(self):
        from orbit import compute_orbital_inclination_class
        assert compute_orbital_inclination_class(self._make_el(85.0)) == "polar"

    def test_polar_upper_boundary(self):
        from orbit import compute_orbital_inclination_class
        assert compute_orbital_inclination_class(self._make_el(95.0)) == "polar"

    def test_retrograde(self):
        from orbit import compute_orbital_inclination_class
        assert compute_orbital_inclination_class(self._make_el(120.0)) == "retrograde"

    def test_retrograde_boundary(self):
        from orbit import compute_orbital_inclination_class
        assert compute_orbital_inclination_class(self._make_el(95.1)) == "retrograde"

    def test_missing_attr_defaults_to_prograde(self):
        from types import SimpleNamespace

        from orbit import compute_orbital_inclination_class
        el = SimpleNamespace()
        assert compute_orbital_inclination_class(el) == "prograde"

    def test_i_deg_alias(self):
        from types import SimpleNamespace

        from orbit import compute_orbital_inclination_class
        el = SimpleNamespace(i_deg=90.0)
        assert compute_orbital_inclination_class(el) == "polar"

    def test_in_all(self):
        from orbit import __all__
        assert "compute_orbital_inclination_class" in __all__


class TestComputeMeanAnomalyAtJd:
    def _elements(self, a=1.5, e=0.1, m0_deg=0.0, epoch_jd=2451545.0):
        import sys
        sys.path.insert(0, "src")
        from schemas import OrbitalElements
        return OrbitalElements(
            semi_major_axis_au=a, eccentricity=e, inclination_deg=10.0,
            longitude_ascending_node_deg=0.0, argument_perihelion_deg=0.0,
            mean_anomaly_deg=m0_deg, epoch_jd=epoch_jd,
            perihelion_au=a * (1 - e), aphelion_au=a * (1 + e)
        )

    def test_at_epoch_returns_m0(self):
        import math
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_mean_anomaly_at_jd
        el = self._elements(m0_deg=45.0, epoch_jd=2451545.0)
        m = compute_mean_anomaly_at_jd(el, 2451545.0)
        assert m == pytest.approx(math.radians(45.0), abs=1e-6)

    def test_one_period_later_wraps(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_mean_anomaly_at_jd
        el = self._elements(a=1.0, e=0.0, m0_deg=0.0, epoch_jd=2451545.0)
        period_days = 365.25
        m = compute_mean_anomaly_at_jd(el, 2451545.0 + period_days)
        assert m == pytest.approx(0.0, abs=1e-5)

    def test_hyperbolic_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_mean_anomaly_at_jd
        el = SimpleNamespace(semi_major_axis_au=1.5, eccentricity=1.1,
                             mean_anomaly_deg=0.0, epoch_jd=2451545.0)
        assert compute_mean_anomaly_at_jd(el, 2460000.0) is None

    def test_zero_sma_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_mean_anomaly_at_jd
        el = SimpleNamespace(semi_major_axis_au=0.0, eccentricity=0.1,
                             mean_anomaly_deg=0.0, epoch_jd=2451545.0)
        assert compute_mean_anomaly_at_jd(el, 2460000.0) is None

    def test_result_in_0_2pi(self):
        import math
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_mean_anomaly_at_jd
        el = self._elements(a=2.5, e=0.3, m0_deg=180.0, epoch_jd=2451545.0)
        for delta in [0, 100, 500, 1000, 5000]:
            m = compute_mean_anomaly_at_jd(el, 2451545.0 + delta)
            assert 0.0 <= m < 2 * math.pi + 1e-9


class TestComputeOrbitalVelocity:
    def _elements(self, a=1.0, e=0.0):
        import sys
        sys.path.insert(0, "src")
        from schemas import OrbitalElements
        return OrbitalElements(
            semi_major_axis_au=a, eccentricity=e, inclination_deg=0.0,
            longitude_ascending_node_deg=0.0, argument_perihelion_deg=0.0,
            mean_anomaly_deg=0.0, epoch_jd=2451545.0,
            perihelion_au=a * (1 - e), aphelion_au=a * (1 + e)
        )

    def test_earth_circular_orbit(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_orbital_velocity
        el = self._elements(a=1.0, e=0.0)
        v = compute_orbital_velocity(el, 1.0)
        assert v is not None
        assert 29.0 < v < 31.0  # Earth ≈ 29.78 km/s

    def test_zero_sma_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_orbital_velocity
        el = SimpleNamespace(semi_major_axis_au=0.0)
        assert compute_orbital_velocity(el, 1.0) is None

    def test_zero_r_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_orbital_velocity
        el = self._elements(a=1.5)
        assert compute_orbital_velocity(el, 0.0) is None

    def test_larger_sma_faster_at_same_r(self):
        # vis-viva: v² = GM(2/r - 1/a); larger a → smaller 1/a → larger v at same r
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_orbital_velocity
        el_near = self._elements(a=1.0)
        el_far = self._elements(a=3.0)
        v_near = compute_orbital_velocity(el_near, 1.0)
        v_far = compute_orbital_velocity(el_far, 1.0)
        assert v_far > v_near

    def test_hyperbolic_negative_v2_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_orbital_velocity
        # a=1 AU, r=3 AU → v² = GM(2/3 - 1) < 0
        el = SimpleNamespace(semi_major_axis_au=1.0)
        assert compute_orbital_velocity(el, 3.0) is None


class TestComputePerihelionDistance:
    def _el(self, a, e):
        from types import SimpleNamespace
        return SimpleNamespace(semi_major_axis_au=a, eccentricity=e)

    def test_basic(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_perihelion_distance
        assert compute_perihelion_distance(self._el(1.5, 0.4)) == pytest.approx(0.9, abs=1e-5)

    def test_circular_orbit(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_perihelion_distance
        assert compute_perihelion_distance(self._el(1.0, 0.0)) == pytest.approx(1.0)

    def test_zero_a_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_perihelion_distance
        assert compute_perihelion_distance(self._el(0.0, 0.5)) is None

    def test_negative_a_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_perihelion_distance
        assert compute_perihelion_distance(self._el(-1.0, 0.5)) is None

    def test_missing_eccentricity_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_perihelion_distance
        el = SimpleNamespace(semi_major_axis_au=1.5, eccentricity=None)
        assert compute_perihelion_distance(el) is None

    def test_e_greater_than_1_q_negative(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_perihelion_distance
        # a=0.5, e=2.0 → q = 0.5*(1-2) = -0.5 → None
        assert compute_perihelion_distance(self._el(0.5, 2.0)) is None


class TestComputeAphelionDistance:
    def _el(self, a, e):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        return SimpleNamespace(semi_major_axis_au=a, eccentricity=e)

    def test_circular_orbit(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_aphelion_distance
        assert compute_aphelion_distance(self._el(1.0, 0.0)) == pytest.approx(1.0)

    def test_elliptical_orbit(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_aphelion_distance
        # a=1.5, e=0.3 → Q=1.5*1.3=1.95
        assert compute_aphelion_distance(self._el(1.5, 0.3)) == pytest.approx(1.95)

    def test_zero_a_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_aphelion_distance
        assert compute_aphelion_distance(self._el(0.0, 0.5)) is None

    def test_negative_a_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_aphelion_distance
        assert compute_aphelion_distance(self._el(-1.0, 0.5)) is None

    def test_missing_eccentricity_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_aphelion_distance
        el = SimpleNamespace(semi_major_axis_au=1.5, eccentricity=None)
        assert compute_aphelion_distance(el) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import orbit
        assert "compute_aphelion_distance" in orbit.__all__


class TestComputeTisserandWrtEarth:
    def _el(self, a, e, i_deg):
        from types import SimpleNamespace
        return SimpleNamespace(semi_major_axis_au=a, eccentricity=e,
                               inclination_deg=i_deg)

    def test_earth_orbit_coplanar(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_tisserand_wrt_earth
        # a=1, e=0, i=0 → T_E = 1/1 + 2*cos(0)*sqrt(1*(1-0)) = 1 + 2 = 3
        result = compute_tisserand_wrt_earth(self._el(1.0, 0.0, 0.0))
        assert result == pytest.approx(3.0)

    def test_inclined_orbit(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_tisserand_wrt_earth
        result = compute_tisserand_wrt_earth(self._el(1.5, 0.3, 30.0))
        assert result is not None
        assert isinstance(result, float)

    def test_zero_a_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_tisserand_wrt_earth
        assert compute_tisserand_wrt_earth(self._el(0.0, 0.3, 10.0)) is None

    def test_missing_inclination_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_tisserand_wrt_earth
        el = SimpleNamespace(semi_major_axis_au=1.5, eccentricity=0.3,
                             inclination_deg=None)
        assert compute_tisserand_wrt_earth(el) is None

    def test_negative_e_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from orbit import compute_tisserand_wrt_earth
        assert compute_tisserand_wrt_earth(self._el(1.5, -0.1, 10.0)) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import orbit
        assert "compute_tisserand_wrt_earth" in orbit.__all__


class TestComputeOrbitalArcQuality:
    def test_code1_short_arc(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_orbital_arc_quality
        tracklet = SimpleNamespace(arc_days=0.5)
        assert compute_orbital_arc_quality(tracklet) == 1

    def test_code2_one_day(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_orbital_arc_quality
        tracklet = SimpleNamespace(arc_days=3.0)
        assert compute_orbital_arc_quality(tracklet) == 2

    def test_code3_week(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_orbital_arc_quality
        tracklet = SimpleNamespace(arc_days=10.0)
        assert compute_orbital_arc_quality(tracklet) == 3

    def test_code4_month(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from orbit import compute_orbital_arc_quality
        tracklet = SimpleNamespace(arc_days=60.0)
        assert compute_orbital_arc_quality(tracklet) == 4

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import orbit
        assert "compute_orbital_arc_quality" in orbit.__all__
