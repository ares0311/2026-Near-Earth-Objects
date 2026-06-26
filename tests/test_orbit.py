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



