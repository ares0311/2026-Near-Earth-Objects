"""Tests for alert.py — MPC formatting and alert protocol guardrails."""

from unittest.mock import MagicMock, patch

from alert import (
    _format_dec,
    _format_ra,
    _generate_pdco_alert_package,
    _jd_to_mpc_date,
    _monitor_neocp,
    _submit_to_mpc,
    format_mpc_json,
    format_mpc_observation,
    format_mpc_report,
    monitor_neocp,
    process_alert,
    summarise,
)
from schemas import (
    CandidateExplanation,
    CandidateFeatures,
    HazardAssessment,
    NEOPosterior,
    Observation,
    OrbitalElements,
    ScoredNEO,
    ScoringMetadata,
    Tracklet,
)


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="a_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def make_scored_neo(
    moid_au: float = 0.03,
    rb: float = 0.95,
    orbit_quality: int = 2,
    hazard_flag: str = "pha_candidate",
    alert_pathway: str = "mpc_submission",
) -> ScoredNEO:
    obs = tuple(
        make_obs(obs_id=f"o{i}", jd=2460000.5 + i)
        for i in range(3)
    )
    tracklet = Tracklet("T001", obs, 2.0, 1.2, 90.0)
    features = CandidateFeatures(real_bogus_score=rb)
    posterior = NEOPosterior(
        neo_candidate=0.75,
        known_object=0.05,
        main_belt_asteroid=0.1,
        stellar_artifact=0.05,
        other_solar_system=0.05,
    )
    explanation = CandidateExplanation(
        summary="Test candidate",
        supporting_evidence=("High RB score",),
        contra_evidence=(),
        model_version="0.1.0",
    )
    orbital = OrbitalElements(
        semi_major_axis_au=1.5,
        eccentricity=0.3,
        inclination_deg=10.0,
        longitude_ascending_node_deg=45.0,
        argument_perihelion_deg=90.0,
        mean_anomaly_deg=180.0,
        epoch_jd=2460000.5,
        perihelion_au=1.05,
        aphelion_au=1.95,
        quality_code=orbit_quality,
    )
    hazard = HazardAssessment(
        hazard_flag=hazard_flag,  # type: ignore[arg-type]
        moid_au=moid_au,
        estimated_diameter_m=200.0,
        absolute_magnitude_h=21.5,
        neo_class="apollo",
        alert_pathway=alert_pathway,  # type: ignore[arg-type]
        explanation=explanation,
        orbital_elements=orbital,
    )
    metadata = ScoringMetadata(
        scorer_version="0.1.0",
        scored_at_jd=2460000.5,
        pipeline_run_id="test_run_001",
        discovery_priority=0.8,
        followup_value=0.6,
        scientific_interest=0.5,
    )
    return ScoredNEO(
        tracklet=tracklet,
        features=features,
        posterior=posterior,
        hazard=hazard,
        metadata=metadata,
    )


class TestMPCFormatting:
    def test_jd_to_mpc_date_format(self):
        date_str = _jd_to_mpc_date(2451545.0)
        assert "2000" in date_str
        parts = date_str.split()
        assert len(parts) == 3

    def test_format_ra(self):
        ra = _format_ra(180.0)  # 12h 00m 00s
        assert ra.startswith("12")

    def test_format_ra_zero(self):
        ra = _format_ra(0.0)
        assert ra.startswith("00")

    def test_format_dec_positive(self):
        dec = _format_dec(10.0)
        assert dec.startswith("+")

    def test_format_dec_negative(self):
        dec = _format_dec(-10.0)
        assert dec.startswith("-")

    def test_mpc_observation_80_cols(self):
        obs = make_obs()
        line = format_mpc_observation(obs, "2026ABC", is_discovery=True)
        assert len(line) == 80

    def test_mpc_observation_discovery_asterisk(self):
        obs = make_obs()
        line = format_mpc_observation(obs, "2026XY", is_discovery=True)
        assert "*" in line

    def test_mpc_report_contains_header(self):
        neo = make_scored_neo()
        report = format_mpc_report(neo)
        assert "COD" in report


class TestAlertProtocol:
    def test_internal_candidate_no_external_report(self):
        neo = make_scored_neo(alert_pathway="internal_candidate")
        result = process_alert(neo, dry_run=True)
        assert result["pathway"] == "internal_candidate"
        assert any("internal" in a for a in result["actions"])

    def test_known_object_no_external_report(self):
        neo = make_scored_neo(alert_pathway="known_object")
        result = process_alert(neo, dry_run=True)
        assert result["pathway"] == "known_object"

    def test_low_rb_blocks_alert(self):
        neo = make_scored_neo(rb=0.7, alert_pathway="mpc_submission")
        result = process_alert(neo, dry_run=True)
        assert any("blocked" in a for a in result["actions"])

    def test_none_rb_blocks_alert(self):
        # Covers `rb is None` left-hand True branch of `if rb is None or rb < 0.90:`
        neo = make_scored_neo(rb=None, alert_pathway="mpc_submission")
        result = process_alert(neo, dry_run=True)
        assert any("blocked" in a for a in result["actions"])

    def test_low_orbit_quality_blocks_alert(self):
        neo = make_scored_neo(orbit_quality=1, alert_pathway="mpc_submission")
        result = process_alert(neo, dry_run=True)
        assert any("blocked" in a for a in result["actions"])

    def test_high_moid_blocks_alert(self):
        neo = make_scored_neo(moid_au=0.1, alert_pathway="mpc_submission")
        result = process_alert(neo, dry_run=True)
        assert any("blocked" in a for a in result["actions"])

    def test_none_moid_blocks_alert(self):
        # Covers `moid is None` left-hand True branch of `if moid is None or moid > 0.05:`
        neo = make_scored_neo(
            rb=0.95, orbit_quality=2, moid_au=None, alert_pathway="mpc_submission"
        )
        result = process_alert(neo, dry_run=True)
        assert any("blocked" in a for a in result["actions"])

    def test_qualifying_candidate_drafts_mpc_report(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        result = process_alert(neo, dry_run=True)
        assert any("MPC" in a for a in result["actions"])

    def test_dry_run_writes_report_file(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        process_alert(neo, dry_run=True)
        report_files = list(tmp_path.glob("mpc_report_*.txt"))
        assert len(report_files) == 1
        content = report_files[0].read_text()
        assert "COD" in content
        assert len(content.splitlines()) >= 6  # header + observations

    def test_dry_run_writes_alert_log(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        process_alert(neo, dry_run=True)
        log_files = list(tmp_path.glob("alert_*.json"))
        assert len(log_files) >= 1
        import json
        entry = json.loads(log_files[0].read_text())
        assert entry["object_id"] == "T001"
        assert "moid_au" in entry

    def test_no_impact_probability_assertion(self):
        neo = make_scored_neo()
        summary = summarise(neo)
        # Must not assert any impact probability
        assert "impact probability" not in summary.lower() or "does not assert" in summary.lower()

    def test_summarise_contains_pathway(self):
        neo = make_scored_neo()
        summary = summarise(neo)
        assert (
            "mpc_submission" in summary
            or "alert_pathway" in summary.lower()
            or "Alert pathway" in summary
        )


class TestSubmitToMpc:
    def test_dry_run_returns_false(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        result = _submit_to_mpc(neo, dry_run=True)
        assert result is False

    def test_live_submission_success(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.post", return_value=mock_resp):
            result = _submit_to_mpc(neo, dry_run=False)
        assert result is True

    def test_live_submission_failure(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        with patch("requests.post", side_effect=Exception("network error")):
            result = _submit_to_mpc(neo, dry_run=False)
        assert result is False


class TestMonitorNeocp:
    def test_error_path_on_exception(self):
        with patch("requests.get", side_effect=ConnectionError("unreachable")):
            result = _monitor_neocp("TEST001")
        assert result["status"] == "error"
        assert "error" in result


class TestPDCOAlertPackage:
    def test_pdco_package_required_keys(self):
        neo = make_scored_neo(
            alert_pathway="nasa_pdco_notify", rb=0.95, orbit_quality=2, moid_au=0.03
        )
        pkg = _generate_pdco_alert_package(neo)
        required = {
            "object_id", "hazard_flag", "moid_au", "absolute_magnitude_h",
            "estimated_diameter_m", "neo_class", "neo_candidate_probability",
            "orbit_quality_code", "arc_days", "n_observations",
            "scorer_version", "pipeline_run_id", "impact_probability",
        }
        assert required <= pkg.keys()

    def test_pdco_package_no_numeric_impact_probability(self):
        neo = make_scored_neo(
            alert_pathway="nasa_pdco_notify", rb=0.95, orbit_quality=2, moid_au=0.03
        )
        pkg = _generate_pdco_alert_package(neo)
        assert not isinstance(pkg.get("impact_probability"), float)

    def test_pdco_package_object_fields(self):
        neo = make_scored_neo(
            alert_pathway="nasa_pdco_notify", rb=0.95, orbit_quality=2, moid_au=0.03
        )
        pkg = _generate_pdco_alert_package(neo)
        assert pkg["object_id"] == "T001"
        assert pkg["neo_class"] == "apollo"
        assert pkg["orbit_quality_code"] == 2

    def test_pdco_deferred_without_cneos_injection(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(
            alert_pathway="nasa_pdco_notify", rb=0.95, orbit_quality=2, moid_au=0.03
        )
        result = process_alert(neo, dry_run=True)
        assert "pdco_package" not in result
        assert any("deferred" in a.lower() for a in result["actions"])

    def test_pdco_triggered_with_cneos_injection(self, tmp_path, monkeypatch):
        # Inject cneos_assessment → lines 318-323 reached
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(
            alert_pathway="nasa_pdco_notify", rb=0.95, orbit_quality=2, moid_au=0.03
        )
        result = process_alert(
            neo,
            dry_run=True,
            cneos_assessment={"cneos_impact_probability": 0.001},
        )
        assert "pdco_package" in result
        assert any("PDCO" in a for a in result["actions"])

    def test_pdco_deferred_when_cneos_prob_below_threshold(self, tmp_path, monkeypatch):
        # cneos_impact_prob is not None but < 0.0001 — covers the Python 3.14
        # branch where the left side of the compound `and` is True but right is False.
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo(
            alert_pathway="nasa_pdco_notify", rb=0.95, orbit_quality=2, moid_au=0.03
        )
        result = process_alert(
            neo,
            dry_run=True,
            cneos_assessment={"cneos_impact_probability": 0.00001},
        )
        assert "pdco_package" not in result
        assert any("deferred" in a.lower() for a in result["actions"])


class TestMonitorNeocpPublic:
    def test_returns_timeout_when_no_confirmation(self):
        # Mock _monitor_neocp to always return checked-but-not-confirmed
        import alert as alert_mod

        calls = {"n": 0}

        def mock_sleep(seconds):
            calls["n"] += 1

        with patch.object(
            alert_mod, "_monitor_neocp",
            return_value={"status": "checked", "confirmed": False},
        ):
            result = monitor_neocp(
                "TEST001",
                max_wait_hr=2.0,
                poll_interval_hr=1.0,
                _sleep_fn=mock_sleep,
            )
        assert result["status"] == "timeout"
        assert result["confirmed"] is False
        assert calls["n"] == 2

    def test_returns_error_on_first_network_failure(self):
        # If the first _monitor_neocp returns an error, return immediately without sleeping
        import alert as alert_mod

        def mock_sleep(seconds):
            raise AssertionError("should not sleep after error")

        with patch.object(
            alert_mod, "_monitor_neocp",
            return_value={"status": "error", "error": "unreachable"},
        ):
            result = monitor_neocp(
                "ERR001",
                max_wait_hr=1.0,
                poll_interval_hr=0.5,
                _sleep_fn=mock_sleep,
            )
        assert result["status"] == "error"
        assert "elapsed_hr" in result

    def test_elapsed_hr_populated(self):
        import alert as alert_mod

        with patch.object(
            alert_mod, "_monitor_neocp",
            return_value={"status": "error", "error": "blocked"},
        ):
            result = monitor_neocp(
                "X001",
                max_wait_hr=1.0,
                poll_interval_hr=1.0,
                _sleep_fn=lambda _: None,
            )
        assert "elapsed_hr" in result
        assert result["elapsed_hr"] >= 0.0

    def test_returns_confirmed_immediately(self):
        # _monitor_neocp returns confirmed=True → returns on first poll without sleeping
        import alert as alert_mod

        slept = []

        with patch.object(
            alert_mod, "_monitor_neocp",
            return_value={"status": "checked", "confirmed": True, "raw": "..."},
        ):
            result = monitor_neocp(
                "CONF001",
                max_wait_hr=24.0,
                poll_interval_hr=1.0,
                _sleep_fn=lambda s: slept.append(s),
            )
        assert result["confirmed"] is True
        assert result["status"] == "checked"
        assert len(slept) == 0  # returned before sleeping


class TestMonitorNeocpDirect:
    """Tests that exercise the _monitor_neocp function body directly."""

    def test_success_path_returns_checked_dict(self):
        """Cover line 228: successful requests.get returns status=checked dict."""
        mock_resp = MagicMock()
        mock_resp.text = "NEOCP page content"
        with patch("requests.get", return_value=mock_resp):
            result = _monitor_neocp("TEST001")
        assert result["status"] == "checked"
        assert result["confirmed"] is False
        assert "NEOCP" in result["raw"]

    def test_exception_path_returns_error_dict(self):
        with patch("requests.get", side_effect=ConnectionError("unreachable")):
            result = _monitor_neocp("TEST001")
        assert result["status"] == "error"
        assert "unreachable" in result["error"]

    def test_default_sleep_fn_uses_time_sleep(self):
        """Cover line 329 else branch: when _sleep_fn is None, _time_mod.sleep is used."""
        import alert as alert_mod

        # Monitor_neocp with _sleep_fn omitted — exercises else _time_mod.sleep.
        # Mock _time_mod.sleep on the alert module so we don't actually sleep,
        # and mock _monitor_neocp to return an error immediately (no loop).
        with patch.object(alert_mod, "_monitor_neocp", return_value={"status": "error"}):
            with patch.object(alert_mod, "_time_mod") as mock_time:
                result = monitor_neocp("NOCPSLEEP", max_wait_hr=1.0, poll_interval_hr=0.5)
        # Error on first call exits before sleep; sleep should not be called.
        mock_time.sleep.assert_not_called()
        assert result["status"] == "error"


class TestFormatMpcJson:
    def test_returns_dict_with_required_keys(self):
        neo = make_scored_neo()
        result = format_mpc_json(neo)
        assert isinstance(result, dict)
        assert "type" in result
        assert "provId" in result
        assert "submissions" in result
        assert result["type"] == "observation"

    def test_submissions_count_matches_observations(self):
        neo = make_scored_neo()
        result = format_mpc_json(neo)
        assert len(result["submissions"]) == len(neo.tracklet.observations)

    def test_submission_has_obs_time_and_coords(self):
        neo = make_scored_neo()
        sub = format_mpc_json(neo)["submissions"][0]
        assert "obsTime" in sub
        assert "ra" in sub
        assert "dec" in sub
        assert isinstance(sub["ra"], float)

    def test_first_observation_marked_discovery(self):
        neo = make_scored_neo()
        subs = format_mpc_json(neo)["submissions"]
        assert subs[0]["remarks"] == "discovery"
        assert subs[1]["remarks"] is None

    def test_hazard_fields_propagated(self):
        neo = make_scored_neo(moid_au=0.03)
        result = format_mpc_json(neo)
        assert result["moid_au"] == 0.03
        assert result["neo_class"] == "apollo"


class TestFormatNeocopReport:
    def _make_neo(self) -> object:
        from .conftest import build_scored_neo
        return build_scored_neo()

    def test_returns_string(self):
        from alert import format_neocp_report
        neo = self._make_neo()
        result = format_neocp_report(neo)
        assert isinstance(result, str)

    def test_contains_object_id(self):
        from alert import format_neocp_report
        neo = self._make_neo()
        result = format_neocp_report(neo)
        assert neo.tracklet.object_id in result

    def test_contains_guardrail(self):
        from alert import format_neocp_report
        neo = self._make_neo()
        result = format_neocp_report(neo)
        assert "No impact probability" in result

    def test_contains_mpc_header(self):
        from alert import format_neocp_report
        neo = self._make_neo()
        result = format_neocp_report(neo)
        assert "NEOCP Follow-Up Request" in result

    def test_contains_motion_rate(self):
        from alert import format_neocp_report
        neo = self._make_neo()
        result = format_neocp_report(neo)
        assert "Motion rate" in result

    def test_custom_obs_code(self):
        from alert import format_neocp_report
        neo = self._make_neo()
        result = format_neocp_report(neo, obs_code="F51")
        assert isinstance(result, str)

    def test_fast_mover_short_exposure(self):
        from alert import format_neocp_report
        from schemas import Tracklet

        from .conftest import build_scored_neo, build_tracklet
        t = build_tracklet(n_obs=3)
        fast_tracklet = Tracklet(
            object_id=t.object_id,
            observations=t.observations,
            arc_days=t.arc_days,
            motion_rate_arcsec_per_hour=15.0,
            motion_pa_degrees=t.motion_pa_degrees,
        )
        neo = build_scored_neo()
        neo2 = neo.model_copy(update={"tracklet": fast_tracklet})
        result = format_neocp_report(neo2)
        assert "30 s" in result

    def test_medium_mover_medium_exposure(self):
        # Covers the elif rate > 2.0 branch (exp_s = 60) in format_neocp_report.
        from alert import format_neocp_report
        from schemas import Tracklet

        from .conftest import build_scored_neo, build_tracklet
        t = build_tracklet(n_obs=3)
        medium_tracklet = Tracklet(
            object_id=t.object_id,
            observations=t.observations,
            arc_days=t.arc_days,
            motion_rate_arcsec_per_hour=5.0,  # 2 < rate <= 10 → exp_s = 60
            motion_pa_degrees=t.motion_pa_degrees,
        )
        neo = build_scored_neo()
        neo2 = neo.model_copy(update={"tracklet": medium_tracklet})
        result = format_neocp_report(neo2)
        assert "60 s" in result


class TestReadyForSubmission:
    def _make_neo(self, moid_au: float = 0.03, rb: float = 0.95,
                  orbit_quality: int = 2, hazard_flag: str = "pha_candidate",
                  alert_pathway: str = "mpc_submission") -> object:
        from .conftest import build_scored_neo
        return build_scored_neo(
            moid_au=moid_au, rb=rb, orbit_quality=orbit_quality,
            hazard_flag=hazard_flag, alert_pathway=alert_pathway,
        )

    def test_all_gates_pass(self):
        from alert import ready_for_submission
        neo = self._make_neo()
        ready, unmet = ready_for_submission(neo)
        assert ready is True
        assert unmet == []

    def test_high_moid_fails(self):
        from alert import ready_for_submission
        neo = self._make_neo(moid_au=0.1)
        ready, unmet = ready_for_submission(neo)
        assert ready is False
        assert any("MOID" in u for u in unmet)

    def test_low_orbit_quality_fails(self):
        from alert import ready_for_submission
        neo = self._make_neo(orbit_quality=1)
        ready, unmet = ready_for_submission(neo)
        assert ready is False
        assert any("quality" in u.lower() for u in unmet)

    def test_low_rb_fails(self):
        from alert import ready_for_submission
        neo = self._make_neo(rb=0.5)
        ready, unmet = ready_for_submission(neo)
        assert ready is False
        assert any("real_bogus" in u for u in unmet)

    def test_known_object_fails(self):
        from alert import ready_for_submission
        neo = self._make_neo(alert_pathway="known_object")
        ready, unmet = ready_for_submission(neo)
        assert ready is False
        assert any("known_object" in u for u in unmet)

    def test_none_moid_fails(self):
        # Covers the `moid is None` left-hand branch of `if moid is None or moid > 0.05:`
        from alert import ready_for_submission
        neo = self._make_neo(moid_au=None)
        ready, unmet = ready_for_submission(neo)
        assert ready is False
        assert any("MOID" in u for u in unmet)

    def test_none_rb_fails(self):
        # Covers the `rb is None` left-hand branch of `if rb is None or rb < 0.90:`
        from alert import ready_for_submission
        neo = self._make_neo(rb=None)
        ready, unmet = ready_for_submission(neo)
        assert ready is False
        assert any("real_bogus" in u for u in unmet)

    def test_returns_tuple(self):
        from alert import ready_for_submission
        neo = self._make_neo()
        result = ready_for_submission(neo)
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestFormatCandidateDossier:
    def _neo(self):
        from tests.conftest import build_scored_neo
        return build_scored_neo()

    def test_returns_string(self):
        from alert import format_candidate_dossier
        neo = self._neo()
        result = format_candidate_dossier(neo)
        assert isinstance(result, str)

    def test_contains_object_id(self):
        from alert import format_candidate_dossier
        neo = self._neo()
        result = format_candidate_dossier(neo)
        assert neo.tracklet.object_id in result

    def test_contains_guardrail(self):
        from alert import format_candidate_dossier
        neo = self._neo()
        result = format_candidate_dossier(neo)
        assert "NOT" in result.upper()

    def test_contains_hazard_flag(self):
        from alert import format_candidate_dossier
        neo = self._neo()
        result = format_candidate_dossier(neo)
        assert neo.hazard.hazard_flag in result

    def test_contains_posterior_fields(self):
        from alert import format_candidate_dossier
        neo = self._neo()
        result = format_candidate_dossier(neo)
        assert "neo_candidate" in result

    def test_multi_line(self):
        from alert import format_candidate_dossier
        neo = self._neo()
        result = format_candidate_dossier(neo)
        assert result.count("\n") > 5

    def test_in_all(self):
        from alert import __all__
        assert "format_candidate_dossier" in __all__


class TestFormatMpcAdesPsv:
    def test_basic_output(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_psv
        neo = make_scored_neo()
        result = format_mpc_ades_psv(neo)
        assert "version=2017" in result
        assert "mpcCode" in result
        assert "T001" in result

    def test_contains_obs_code(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_psv
        neo = make_scored_neo()
        result = format_mpc_ades_psv(neo, obs_code="G96")
        assert "G96" in result

    def test_psv_data_rows(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_psv
        neo = make_scored_neo()
        result = format_mpc_ades_psv(neo)
        lines = result.split("\n")
        data_rows = [ln for ln in lines if ln.startswith("| ") and "permID" not in ln
                     and "version" not in ln and "mpcCode" not in ln
                     and "name" not in ln and "design" not in ln
                     and "aperture" not in ln and "detector" not in ln]
        assert len(data_rows) == 3  # 3 observations

    def test_guardrail_not_in_output(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_psv
        neo = make_scored_neo()
        result = format_mpc_ades_psv(neo)
        assert "impact probability" not in result.lower()

    def test_header_fields_present(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_psv
        neo = make_scored_neo()
        result = format_mpc_ades_psv(neo)
        assert "obsTime" in result
        assert "ra" in result
        assert "dec" in result


class TestFormatMpcAdesPsvTimeFallback:
    def test_astropy_time_failure_uses_str(self, monkeypatch):
        import sys
        import types as _types
        sys.path.insert(0, "src")

        class FakeTime:
            def __init__(self, *a, **kw):
                raise RuntimeError("no astropy")

        fake_time_mod = _types.ModuleType("astropy.time")
        fake_time_mod.Time = FakeTime
        monkeypatch.setitem(sys.modules, "astropy.time", fake_time_mod)

        from alert import format_mpc_ades_psv
        neo = make_scored_neo()
        result = format_mpc_ades_psv(neo)
        assert "version=2017" in result
        # JD value appears as string fallback
        assert "2460000" in result


class TestCountObservationsByMission:
    def test_counts_missions(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import count_observations_by_mission
        obs1 = SimpleNamespace(mission="ZTF")
        obs2 = SimpleNamespace(mission="ATLAS")
        obs3 = SimpleNamespace(mission="ZTF")
        tracklet = SimpleNamespace(observations=(obs1, obs2, obs3))
        neo = SimpleNamespace(tracklet=tracklet)
        result = count_observations_by_mission(neo)
        assert result == {"ZTF": 2, "ATLAS": 1}

    def test_no_tracklet_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import count_observations_by_mission
        neo = SimpleNamespace(tracklet=None)
        assert count_observations_by_mission(neo) == {}

    def test_empty_observations(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import count_observations_by_mission
        tracklet = SimpleNamespace(observations=())
        neo = SimpleNamespace(tracklet=tracklet)
        assert count_observations_by_mission(neo) == {}

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "count_observations_by_mission" in alert.__all__


