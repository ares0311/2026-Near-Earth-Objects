"""Tests for alert.py — MPC formatting and alert protocol guardrails."""

from unittest.mock import MagicMock, patch

import pytest

from alert import (
    _format_dec,
    _format_ra,
    _generate_pdco_alert_package,
    _jd_to_mpc_date,
    _monitor_neocp,
    _submit_to_mpc,
    batch_process_alerts,
    format_mpc_json,
    format_mpc_observation,
    format_mpc_report,
    generate_alert_package,
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

    def test_low_orbit_quality_blocks_alert(self):
        neo = make_scored_neo(orbit_quality=1, alert_pathway="mpc_submission")
        result = process_alert(neo, dry_run=True)
        assert any("blocked" in a for a in result["actions"])

    def test_high_moid_blocks_alert(self):
        neo = make_scored_neo(moid_au=0.1, alert_pathway="mpc_submission")
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

    def test_exception_path_returns_error_dict(self):
        with patch("requests.get", side_effect=ConnectionError("unreachable")):
            result = _monitor_neocp("TEST001")
        assert result["status"] == "error"
        assert "unreachable" in result["error"]


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


class TestBatchProcessAlerts:
    def test_returns_list_same_length(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neos = [make_scored_neo(alert_pathway="internal_candidate") for _ in range(3)]
        results = batch_process_alerts(neos, dry_run=True)
        assert len(results) == 3

    def test_each_result_has_pathway(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neos = [make_scored_neo(alert_pathway="internal_candidate")]
        results = batch_process_alerts(neos, dry_run=True)
        assert "pathway" in results[0]

    def test_empty_input_returns_empty_list(self):
        assert batch_process_alerts([], dry_run=True) == []


class TestGenerateAlertPackage:
    def test_returns_all_required_keys(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo()
        pkg = generate_alert_package(neo)
        expected = {
            "object_id", "mpc_report", "mpc_json", "summary",
            "hazard_flag", "alert_pathway", "n_observations",
        }
        assert expected.issubset(pkg.keys())

    def test_object_id_matches_tracklet(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo()
        pkg = generate_alert_package(neo)
        assert pkg["object_id"] == neo.tracklet.object_id

    def test_n_observations_correct(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo()
        pkg = generate_alert_package(neo)
        assert pkg["n_observations"] == len(neo.tracklet.observations)

    def test_mpc_report_is_string(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo()
        pkg = generate_alert_package(neo)
        assert isinstance(pkg["mpc_report"], str)

    def test_mpc_json_is_dict(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        neo = make_scored_neo()
        pkg = generate_alert_package(neo)
        assert isinstance(pkg["mpc_json"], dict)


class TestDraftMpcSubmission:
    def test_returns_required_keys(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from alert import draft_mpc_submission
        neo = make_scored_neo()
        result = draft_mpc_submission(neo)
        expected = {"object_id", "cover_letter", "mpc_report",
                    "mpc_json", "summary", "ready_to_submit"}
        assert expected == set(result.keys())

    def test_object_id_matches(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from alert import draft_mpc_submission
        neo = make_scored_neo()
        result = draft_mpc_submission(neo)
        assert result["object_id"] == neo.tracklet.object_id

    def test_ready_to_submit_true_for_mpc_submission(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from alert import draft_mpc_submission
        neo = make_scored_neo(alert_pathway="mpc_submission")
        assert draft_mpc_submission(neo)["ready_to_submit"] is True

    def test_ready_to_submit_false_for_internal(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from alert import draft_mpc_submission
        neo = make_scored_neo(alert_pathway="internal_candidate")
        assert draft_mpc_submission(neo)["ready_to_submit"] is False

    def test_cover_letter_contains_guardrail(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from alert import draft_mpc_submission
        neo = make_scored_neo()
        result = draft_mpc_submission(neo)
        assert "Impact probability is NOT asserted" in result["cover_letter"]

    def test_mpc_report_is_string(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from alert import draft_mpc_submission
        neo = make_scored_neo()
        result = draft_mpc_submission(neo)
        assert isinstance(result["mpc_report"], str)

    def test_mpc_json_is_dict(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from alert import draft_mpc_submission
        neo = make_scored_neo()
        result = draft_mpc_submission(neo)
        assert isinstance(result["mpc_json"], dict)


class TestAlertSummaryTable:
    def _make_neos(self, n: int = 3):
        from .conftest import build_scored_neo
        return [build_scored_neo(object_id=f"OBJ{i:03d}") for i in range(n)]

    def test_returns_list(self):
        from alert import alert_summary_table
        neos = self._make_neos(2)
        result = alert_summary_table(neos)
        assert isinstance(result, list)

    def test_empty_input_returns_empty(self):
        from alert import alert_summary_table
        assert alert_summary_table([]) == []

    def test_row_has_required_keys(self):
        from alert import alert_summary_table
        neos = self._make_neos(1)
        row = alert_summary_table(neos)[0]
        for key in ("object_id", "hazard_flag", "alert_pathway", "moid_au",
                    "neo_class", "arc_days", "n_observations", "ready_to_submit"):
            assert key in row, f"missing key: {key}"

    def test_object_id_matches(self):
        from alert import alert_summary_table

        from .conftest import build_scored_neo
        neo = build_scored_neo(object_id="MYOBJ")
        rows = alert_summary_table([neo])
        assert rows[0]["object_id"] == "MYOBJ"

    def test_ready_to_submit_true_for_mpc_submission(self):
        from alert import alert_summary_table

        from .conftest import build_scored_neo
        neo = build_scored_neo(alert_pathway="mpc_submission")
        rows = alert_summary_table([neo])
        assert rows[0]["ready_to_submit"] is True

    def test_ready_to_submit_false_for_internal(self):
        from alert import alert_summary_table

        from .conftest import build_scored_neo
        neo = build_scored_neo(alert_pathway="internal_candidate")
        rows = alert_summary_table([neo])
        assert rows[0]["ready_to_submit"] is False

    def test_n_observations_correct(self):
        from alert import alert_summary_table
        neos = self._make_neos(1)
        rows = alert_summary_table(neos)
        assert rows[0]["n_observations"] == len(neos[0].tracklet.observations)


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

    def test_returns_tuple(self):
        from alert import ready_for_submission
        neo = self._make_neo()
        result = ready_for_submission(neo)
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestFormatDiscoveryCircular:
    def _make_neo(self):
        from .conftest import build_scored_neo
        return build_scored_neo()

    def test_returns_string(self):
        from alert import format_discovery_circular
        neo = self._make_neo()
        result = format_discovery_circular(neo)
        assert isinstance(result, str)

    def test_contains_object_id(self):
        from alert import format_discovery_circular
        neo = self._make_neo()
        result = format_discovery_circular(neo)
        assert neo.tracklet.object_id in result

    def test_contains_draft_header(self):
        from alert import format_discovery_circular
        neo = self._make_neo()
        result = format_discovery_circular(neo)
        assert "DRAFT" in result

    def test_contains_no_impact_warning(self):
        from alert import format_discovery_circular
        neo = self._make_neo()
        result = format_discovery_circular(neo)
        assert "impact" not in result.lower() or "Do not" in result

    def test_contains_neo_class(self):
        from alert import format_discovery_circular
        neo = self._make_neo()
        result = format_discovery_circular(neo)
        assert "NEO CLASS" in result

    def test_contains_observer_placeholder(self):
        from alert import format_discovery_circular
        neo = self._make_neo()
        result = format_discovery_circular(neo)
        assert "FILL IN" in result


class TestFormatAlertSummary:
    def _make_neo(self, obj_id="NEO_001", priority=0.7, moid=0.04):
        from .conftest import build_scored_neo
        neo = build_scored_neo()
        # Return as-is since build_scored_neo is self-contained
        return neo

    def test_returns_string(self):
        from alert import format_alert_summary

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_alert_summary([neo])
        assert isinstance(result, str)

    def test_empty_list_returns_no_candidates_message(self):
        from alert import format_alert_summary
        result = format_alert_summary([])
        assert "No NEO" in result

    def test_contains_header(self):
        from alert import format_alert_summary

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_alert_summary([neo])
        assert "Object ID" in result

    def test_max_rows_respected(self):
        from alert import format_alert_summary

        from .conftest import build_scored_neo
        neos = [build_scored_neo() for _ in range(5)]
        result = format_alert_summary(neos, max_rows=2)
        # Count separator line + header + up to 2 data rows
        lines = [ln for ln in result.splitlines() if ln.strip() and not ln.startswith("-")]
        assert len(lines) <= 3  # header + 2 data rows max

    def test_contains_rank_column(self):
        from alert import format_alert_summary

        from .conftest import build_scored_neo
        result = format_alert_summary([build_scored_neo()])
        assert "1" in result


class TestFormatDiscoveryCircularNoElements:
    def _make_neo_no_elements(self):
        from .conftest import build_scored_neo
        neo = build_scored_neo()
        # Build a ScoredNEO with no orbital elements on the hazard assessment
        from schemas import HazardAssessment, ScoredNEO
        new_hazard = HazardAssessment(
            hazard_flag=neo.hazard.hazard_flag,
            moid_au=None,
            estimated_diameter_m=None,
            absolute_magnitude_h=None,
            neo_class=neo.hazard.neo_class,
            alert_pathway=neo.hazard.alert_pathway,
            explanation=neo.hazard.explanation,
        )
        return ScoredNEO(
            tracklet=neo.tracklet,
            features=neo.features,
            posterior=neo.posterior,
            hazard=new_hazard,
            metadata=neo.metadata,
        )

    def test_no_orbital_elements_branch(self):
        from alert import format_discovery_circular
        neo = self._make_neo_no_elements()
        # Temporarily clear orbital_elements on the object if present
        result = format_discovery_circular(neo)
        assert isinstance(result, str)
        assert "DRAFT" in result


class TestGenerateObservationRequest:
    def _make_neo(self):
        from .conftest import build_scored_neo
        return build_scored_neo()

    def test_returns_string(self):
        from alert import generate_observation_request
        neo = self._make_neo()
        result = generate_observation_request(neo)
        assert isinstance(result, str)

    def test_contains_object_id(self):
        from alert import generate_observation_request
        neo = self._make_neo()
        result = generate_observation_request(neo)
        assert neo.tracklet.object_id in result

    def test_contains_obs_code(self):
        from alert import generate_observation_request
        neo = self._make_neo()
        result = generate_observation_request(neo, obs_code="695")
        assert "695" in result

    def test_default_obs_code_500(self):
        from alert import generate_observation_request
        neo = self._make_neo()
        result = generate_observation_request(neo)
        assert "500" in result

    def test_contains_urgency(self):
        from alert import generate_observation_request
        neo = self._make_neo()
        result = generate_observation_request(neo)
        assert any(word in result for word in ("URGENT", "HIGH", "MEDIUM", "ROUTINE"))

    def test_guardrail_present(self):
        from alert import generate_observation_request
        neo = self._make_neo()
        result = generate_observation_request(neo)
        assert "impact" in result.lower() or "probability" in result.lower() or "Do not" in result


class TestGenerateObservationRequestBranches:
    """Cover urgency branches HIGH, MEDIUM, ROUTINE in generate_observation_request."""

    def _make_neo(self, priority: float = 0.5, hazard_flag: str = "nominal"):

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        # Use simple namespace to set custom priority/hazard_flag
        import types
        meta = types.SimpleNamespace(
            discovery_priority=priority,
            followup_value=0.5,
            scientific_interest=0.3,
            pipeline_version="0.20.0",
            scoring_timestamp=2460000.5,
            close_approach_au=None,
        )
        haz = types.SimpleNamespace(
            hazard_flag=hazard_flag,
            moid_au=0.1,
            estimated_diameter_m=100.0,
            absolute_magnitude_h=22.5,
            neo_class="amor",
            alert_pathway="internal_candidate",
            explanation=neo.hazard.explanation,
        )
        obj = types.SimpleNamespace(
            tracklet=neo.tracklet,
            features=neo.features,
            posterior=neo.posterior,
            hazard=haz,
            metadata=meta,
        )
        return obj

    def test_high_urgency(self):
        from alert import generate_observation_request
        neo = self._make_neo(priority=0.75, hazard_flag="nominal")
        result = generate_observation_request(neo)
        assert "HIGH" in result

    def test_medium_urgency(self):
        from alert import generate_observation_request
        neo = self._make_neo(priority=0.5, hazard_flag="nominal")
        result = generate_observation_request(neo)
        assert "MEDIUM" in result

    def test_routine_urgency(self):
        from alert import generate_observation_request
        neo = self._make_neo(priority=0.2, hazard_flag="nominal")
        result = generate_observation_request(neo)
        assert "ROUTINE" in result


class TestGenerateMpcCoverLetter:
    def test_returns_string(self):
        from alert import generate_mpc_cover_letter

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = generate_mpc_cover_letter(neo)
        assert isinstance(result, str)

    def test_contains_object_id(self):
        from alert import generate_mpc_cover_letter

        from .conftest import build_scored_neo
        neo = build_scored_neo(object_id="2026-AB1")
        result = generate_mpc_cover_letter(neo)
        assert "2026-AB1" in result

    def test_contains_guardrail_text(self):
        from alert import generate_mpc_cover_letter

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = generate_mpc_cover_letter(neo)
        assert "Do NOT publicly announce any impact probability" in result

    def test_contains_moid(self):
        from alert import generate_mpc_cover_letter

        from .conftest import build_scored_neo
        neo = build_scored_neo(moid_au=0.023)
        result = generate_mpc_cover_letter(neo)
        assert "0.0230" in result

    def test_moid_none_shows_unknown(self):
        from alert import generate_mpc_cover_letter

        from .conftest import build_scored_neo
        neo = build_scored_neo(moid_au=None)
        result = generate_mpc_cover_letter(neo)
        assert "unknown" in result.lower()

    def test_contains_separator(self):
        from alert import generate_mpc_cover_letter

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = generate_mpc_cover_letter(neo)
        assert "=" * 20 in result


class TestFormatImpactNotification:
    def test_returns_dict(self):
        from alert import format_impact_notification

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_impact_notification(neo)
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        from alert import format_impact_notification

        from .conftest import build_scored_neo
        result = format_impact_notification(build_scored_neo())
        for key in ["object_id", "guardrails", "observations", "moid_au",
                    "hazard_flag", "alert_pathway", "neo_class", "arc_days"]:
            assert key in result

    def test_object_id_correct(self):
        from alert import format_impact_notification

        from .conftest import build_scored_neo
        result = format_impact_notification(build_scored_neo(object_id="2026-XY1"))
        assert result["object_id"] == "2026-XY1"

    def test_guardrails_is_list(self):
        from alert import format_impact_notification

        from .conftest import build_scored_neo
        result = format_impact_notification(build_scored_neo())
        assert isinstance(result["guardrails"], list)
        assert len(result["guardrails"]) > 0

    def test_guardrail_contains_no_impact_probability(self):
        from alert import format_impact_notification

        from .conftest import build_scored_neo
        result = format_impact_notification(build_scored_neo())
        all_text = " ".join(result["guardrails"])
        assert "impact probability" in all_text.lower()

    def test_observations_list_nonempty(self):
        from alert import format_impact_notification

        from .conftest import build_scored_neo
        result = format_impact_notification(build_scored_neo())
        assert isinstance(result["observations"], list)
        assert len(result["observations"]) > 0

    def test_generated_utc_is_string(self):
        from alert import format_impact_notification

        from .conftest import build_scored_neo
        result = format_impact_notification(build_scored_neo())
        assert isinstance(result["generated_utc"], str)


class TestCountPendingAlerts:
    def _make_neo(self, pathway):
        from .conftest import build_scored_neo
        return build_scored_neo(alert_pathway=pathway)

    def test_empty_input_returns_empty_dict(self):
        from alert import count_pending_alerts
        assert count_pending_alerts([]) == {}

    def test_single_pathway(self):
        from alert import count_pending_alerts
        neos = [self._make_neo("mpc_submission") for _ in range(3)]
        result = count_pending_alerts(neos)
        assert result == {"mpc_submission": 3}

    def test_multiple_pathways(self):
        from alert import count_pending_alerts
        neos = [
            self._make_neo("mpc_submission"),
            self._make_neo("internal_candidate"),
            self._make_neo("mpc_submission"),
            self._make_neo("known_object"),
        ]
        result = count_pending_alerts(neos)
        assert result["mpc_submission"] == 2
        assert result["internal_candidate"] == 1
        assert result["known_object"] == 1

    def test_returns_dict(self):
        from alert import count_pending_alerts
        result = count_pending_alerts([self._make_neo("internal_candidate")])
        assert isinstance(result, dict)

    def test_only_present_pathways_in_result(self):
        from alert import count_pending_alerts
        neos = [self._make_neo("internal_candidate")]
        result = count_pending_alerts(neos)
        assert "mpc_submission" not in result
        assert "internal_candidate" in result


class TestFormatSubmissionChecklist:
    def test_returns_string(self):
        from alert import format_submission_checklist

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_submission_checklist(neo)
        assert isinstance(result, str)

    def test_contains_object_id(self):
        from alert import format_submission_checklist

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_submission_checklist(neo)
        assert neo.tracklet.object_id in result

    def test_contains_guardrail(self):
        from alert import format_submission_checklist

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_submission_checklist(neo)
        assert "GUARDRAIL" in result

    def test_contains_gate_markers(self):
        from alert import format_submission_checklist

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_submission_checklist(neo)
        assert "✓" in result or "✗" in result

    def test_mpc_submission_pathway_in_checklist(self):
        from alert import format_submission_checklist

        from .conftest import build_scored_neo
        neo = build_scored_neo(alert_pathway="mpc_submission")
        result = format_submission_checklist(neo)
        assert "Step 1" in result

    def test_multiline(self):
        from alert import format_submission_checklist

        from .conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_submission_checklist(neo)
        assert "\n" in result


class TestValidateAlertPackage:
    def _make_valid_package(self):
        from schemas import Observation
        obs = Observation(
            obs_id="o1", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        return {
            "observations": [obs],
            "orbit": {"semi_major_axis_au": 1.5},
            "moid_au": 0.03,
            "alert_pathway": "mpc_submission",
            "guardrail_statement": "Do NOT publicly announce any impact probability.",
        }

    def test_valid_package_passes(self):
        from alert import validate_alert_package
        valid, issues = validate_alert_package(self._make_valid_package())
        assert valid is True
        assert issues == []

    def test_missing_observations_fails(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        del pkg["observations"]
        valid, issues = validate_alert_package(pkg)
        assert valid is False
        assert any("observations" in i for i in issues)

    def test_missing_orbit_fails(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        del pkg["orbit"]
        valid, issues = validate_alert_package(pkg)
        assert valid is False
        assert any("orbit" in i for i in issues)

    def test_empty_observations_fails(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        pkg["observations"] = []
        valid, issues = validate_alert_package(pkg)
        assert valid is False
        assert any("empty" in i for i in issues)

    def test_invalid_pathway_fails(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        pkg["alert_pathway"] = "unknown_pathway"
        valid, issues = validate_alert_package(pkg)
        assert valid is False
        assert any("alert_pathway" in i for i in issues)

    def test_empty_guardrail_fails(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        pkg["guardrail_statement"] = ""
        valid, issues = validate_alert_package(pkg)
        assert valid is False
        assert any("guardrail" in i for i in issues)

    def test_guardrail_without_not_fails(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        pkg["guardrail_statement"] = "Please inform authorities."
        valid, issues = validate_alert_package(pkg)
        assert valid is False
        assert any("NOT" in i for i in issues)

    def test_multiple_missing_keys_reported(self):
        from alert import validate_alert_package
        valid, issues = validate_alert_package({})
        assert valid is False
        assert len(issues) >= 5

    def test_none_moid_allowed(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        pkg["moid_au"] = None
        valid, issues = validate_alert_package(pkg)
        assert valid is True

    def test_none_observations_fails(self):
        from alert import validate_alert_package
        pkg = self._make_valid_package()
        pkg["observations"] = None
        valid, issues = validate_alert_package(pkg)
        assert valid is False
        assert any("None" in i for i in issues)


class TestEstimateFollowupWindow:
    def _make_neo(self, hazard_flag="nominal", alert_pathway="internal_candidate", priority=0.5):
        from tests.conftest import build_scored_neo
        neo = build_scored_neo()
        hazard = neo.hazard.model_copy(update={
            "hazard_flag": hazard_flag,
            "alert_pathway": alert_pathway,
        })
        meta = neo.metadata.model_copy(update={"discovery_priority": priority})
        return neo.model_copy(update={"hazard": hazard, "metadata": meta})

    def test_pha_candidate_24h(self):
        from alert import estimate_followup_window
        neo = self._make_neo(hazard_flag="pha_candidate")
        result = estimate_followup_window(neo)
        assert result["urgency_hours"] == 24.0

    def test_neocp_followup_48h(self):
        from alert import estimate_followup_window
        neo = self._make_neo(alert_pathway="neocp_followup")
        result = estimate_followup_window(neo)
        assert result["urgency_hours"] == 48.0

    def test_nominal_uses_priority(self):
        from alert import estimate_followup_window
        neo = self._make_neo(priority=0.0)
        result = estimate_followup_window(neo)
        assert result["urgency_hours"] == 72.0

    def test_end_jd_gt_start_jd(self):
        from alert import estimate_followup_window
        neo = self._make_neo()
        result = estimate_followup_window(neo)
        assert result["end_jd"] > result["start_jd"]

    def test_start_jd_is_reference(self):
        from alert import estimate_followup_window
        neo = self._make_neo()
        result = estimate_followup_window(neo)
        assert result["start_jd"] == 2460000.0

    def test_urgency_clamped_min(self):
        from alert import estimate_followup_window
        neo = self._make_neo(priority=1.0)
        result = estimate_followup_window(neo)
        assert result["urgency_hours"] >= 24.0

    def test_urgency_clamped_max(self):
        from alert import estimate_followup_window
        neo = self._make_neo(priority=0.0)
        result = estimate_followup_window(neo)
        assert result["urgency_hours"] <= 168.0

    def test_returns_dict_with_required_keys(self):
        from alert import estimate_followup_window
        neo = self._make_neo()
        result = estimate_followup_window(neo)
        assert "start_jd" in result and "end_jd" in result and "urgency_hours" in result


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


class TestCountAlertsByFlag:
    """Tests for count_alerts_by_flag."""

    def _neo(self, hazard_flag="nominal"):
        from .conftest import build_scored_neo
        neo = build_scored_neo()
        hazard = neo.hazard.model_copy(update={"hazard_flag": hazard_flag})
        return neo.model_copy(update={"hazard": hazard})

    def test_empty_list(self):
        from alert import count_alerts_by_flag
        assert count_alerts_by_flag([]) == {}

    def test_single_flag(self):
        from alert import count_alerts_by_flag
        neos = [self._neo("nominal"), self._neo("nominal"), self._neo("nominal")]
        result = count_alerts_by_flag(neos)
        assert result == {"nominal": 3}

    def test_mixed_flags(self):
        from alert import count_alerts_by_flag
        neos = [
            self._neo("pha_candidate"),
            self._neo("nominal"),
            self._neo("close_approach"),
            self._neo("nominal"),
            self._neo("pha_candidate"),
        ]
        result = count_alerts_by_flag(neos)
        assert result["pha_candidate"] == 2
        assert result["nominal"] == 2
        assert result["close_approach"] == 1
        assert "unknown" not in result

    def test_no_zero_count_entries(self):
        from alert import count_alerts_by_flag
        neos = [self._neo("pha_candidate")]
        result = count_alerts_by_flag(neos)
        # Only pha_candidate should appear
        assert list(result.keys()) == ["pha_candidate"]

    def test_in_all(self):
        from alert import __all__
        assert "count_alerts_by_flag" in __all__


class TestFormatBulkSummary:
    """Tests for format_bulk_summary."""

    def _make_neo(self, hazard_flag="nominal", pathway="internal_candidate", priority=0.5):
        from tests.conftest import build_scored_neo
        neo = build_scored_neo()
        hazard = neo.hazard.model_copy(update={
            "hazard_flag": hazard_flag,
            "alert_pathway": pathway,
        })
        meta = neo.metadata.model_copy(update={"discovery_priority": priority})
        return neo.model_copy(update={"hazard": hazard, "metadata": meta})

    def test_empty_list(self):
        from alert import format_bulk_summary
        result = format_bulk_summary([])
        assert "No candidates" in result
        assert "GUARDRAIL" in result

    def test_single_nominal(self):
        from alert import format_bulk_summary
        neo = self._make_neo()
        result = format_bulk_summary([neo])
        assert "Total candidates" in result
        assert "1" in result
        assert "GUARDRAIL" in result

    def test_pha_counted(self):
        from alert import format_bulk_summary
        neos = [
            self._make_neo(hazard_flag="pha_candidate", pathway="nasa_pdco_notify"),
            self._make_neo(hazard_flag="nominal"),
        ]
        result = format_bulk_summary(neos)
        assert "PHA candidates    : 1" in result

    def test_custom_title(self):
        from alert import format_bulk_summary
        result = format_bulk_summary([], title="My Title")
        assert result.startswith("My Title")

    def test_guardrail_present(self):
        from alert import format_bulk_summary
        neos = [self._make_neo() for _ in range(3)]
        result = format_bulk_summary(neos)
        assert "GUARDRAIL" in result
        assert "MPC/CNEOS" in result

    def test_top10_table(self):
        from alert import format_bulk_summary
        neos = [self._make_neo(priority=float(i) / 10) for i in range(5)]
        result = format_bulk_summary(neos)
        assert "Top-10" in result

    def test_in_all(self):
        from alert import __all__
        assert "format_bulk_summary" in __all__


class TestCountReadyToSubmit:
    """Tests for count_ready_to_submit."""

    def _make_neo(self, rb=0.95, quality=2, moid=0.03, known=0.0, neo_prob=0.75):
        from tests.conftest import build_scored_neo
        neo = build_scored_neo()
        features = neo.features.model_copy(update={
            "real_bogus_score": rb,
            "orbit_quality_score": quality / 4.0,
            "moid_score": 1.0 if moid <= 0.05 else 0.0,
            "known_object_score": known,
        })
        hazard = neo.hazard.model_copy(update={"moid_au": moid})
        return neo.model_copy(update={"features": features, "hazard": hazard})

    def test_empty_list_returns_zero(self):
        from alert import count_ready_to_submit
        assert count_ready_to_submit([]) == 0

    def test_no_ready_candidates(self):
        from alert import count_ready_to_submit
        # low rb score → not ready
        neos = [self._make_neo(rb=0.5) for _ in range(3)]
        result = count_ready_to_submit(neos)
        assert isinstance(result, int)
        assert result == 0

    def test_returns_integer(self):
        from alert import count_ready_to_submit
        neos = [self._make_neo()]
        result = count_ready_to_submit(neos)
        assert isinstance(result, int)

    def test_consistent_with_ready_for_submission(self):
        from alert import count_ready_to_submit, ready_for_submission
        neos = [self._make_neo(rb=0.5), self._make_neo(rb=0.95)]
        expected = sum(1 for n in neos if ready_for_submission(n)[0])
        assert count_ready_to_submit(neos) == expected

    def test_in_all(self):
        from alert import __all__
        assert "count_ready_to_submit" in __all__


class TestComputeAlertAgeDays:
    def test_basic_age(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from alert import compute_alert_age_days
        first_jd = min(o.jd for o in scored_neo.tracklet.observations)
        current_jd = first_jd + 3.5
        age = compute_alert_age_days(scored_neo, current_jd)
        assert age == pytest.approx(3.5, abs=0.0001)

    def test_zero_when_current_equals_first(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from alert import compute_alert_age_days
        first_jd = min(o.jd for o in scored_neo.tracklet.observations)
        assert compute_alert_age_days(scored_neo, first_jd) == 0.0

    def test_negative_clamped_to_zero(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from alert import compute_alert_age_days
        first_jd = min(o.jd for o in scored_neo.tracklet.observations)
        assert compute_alert_age_days(scored_neo, first_jd - 1.0) == 0.0

    def test_no_observations_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import compute_alert_age_days
        tracklet = SimpleNamespace(observations=[])
        neo = SimpleNamespace(tracklet=tracklet)
        assert compute_alert_age_days(neo, 2460000.0) == 0.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "compute_alert_age_days" in alert.__all__


class TestFormatObservationLog:
    def test_contains_header(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from alert import format_observation_log
        log = format_observation_log(scored_neo)
        assert "JD" in log
        assert "RA" in log
        assert "Dec" in log

    def test_contains_all_observations(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from alert import format_observation_log
        log = format_observation_log(scored_neo)
        n_obs = len(scored_neo.tracklet.observations)
        assert f"{n_obs} observation" in log

    def test_sorted_by_jd(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from alert import format_observation_log
        log = format_observation_log(scored_neo)
        jds = [float(line.split()[0]) for line in log.splitlines()
               if line and line[0].isdigit()]
        assert jds == sorted(jds)

    def test_contains_object_id(self, scored_neo):
        import sys
        sys.path.insert(0, "src")
        from alert import format_observation_log
        log = format_observation_log(scored_neo)
        assert scored_neo.tracklet.object_id in log


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


class TestFormatDiscoveryReport:
    def test_basic_fields(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_discovery_report
        from tests.conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_discovery_report(neo)
        assert "object_id" in result
        assert "neo_class" in result
        assert "hazard_flag" in result
        assert "alert_pathway" in result
        assert "guardrail_statement" in result
        assert "NOT" in result["guardrail_statement"]

    def test_guardrail_present(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_discovery_report
        neo = SimpleNamespace(tracklet=None, hazard=None,
                              features=None, posterior=None, metadata=None)
        result = format_discovery_report(neo)
        assert "NOT" in result["guardrail_statement"]

    def test_none_components(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_discovery_report
        neo = SimpleNamespace(tracklet=None, hazard=None,
                              features=None, posterior=None, metadata=None)
        result = format_discovery_report(neo)
        assert result["object_id"] == "unknown"
        assert result["moid_au"] is None
        assert result["n_observations"] == 0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_discovery_report" in alert.__all__


class TestFormatNeocpSubmission:
    def test_basic_output(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_neocp_submission
        from tests.conftest import build_scored_neo
        neo = build_scored_neo()
        result = format_neocp_submission(neo, obs_code="T05")
        assert "COD T05" in result
        assert "GUARDRAIL" in result

    def test_guardrail_present(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_neocp_submission
        neo = SimpleNamespace(tracklet=None, hazard=None,
                              features=None, posterior=None, metadata=None)
        result = format_neocp_submission(neo)
        assert "GUARDRAIL" in result
        assert "NOT" in result

    def test_no_observations(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_neocp_submission
        tracklet = SimpleNamespace(object_id="NEO001", observations=())
        neo = SimpleNamespace(tracklet=tracklet, hazard=None,
                              features=None, posterior=None, metadata=None)
        result = format_neocp_submission(neo)
        assert "COD" in result

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_neocp_submission" in alert.__all__


class TestFormatNeocpSubmissionObsError:
    def test_bad_obs_skipped(self, monkeypatch):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import alert as al

        monkeypatch.setattr(al, "format_mpc_observation",
                            lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))

        obs = SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=5.0,
                              mag=18.0, mag_err=0.05, filter_band="r",
                              obs_id="X", mission="ZTF")
        tracklet = SimpleNamespace(object_id="T001", observations=(obs,))
        neo = SimpleNamespace(tracklet=tracklet, hazard=None,
                              features=None, posterior=None, metadata=None)
        result = al.format_neocp_submission(neo)
        assert "GUARDRAIL" in result


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


class TestFormatCloseApproachBulletin:
    def test_contains_guardrail(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_close_approach_bulletin
        tracklet = SimpleNamespace(object_id="NEO001")
        hazard = SimpleNamespace(
            neo_class="apollo",
            hazard_flag="pha_candidate",
            moid_au=0.03,
            estimated_diameter_m=200.0,
            absolute_magnitude_h=21.5,
            alert_pathway="mpc_submission",
        )
        meta = SimpleNamespace(discovery_priority=0.85)
        neo = SimpleNamespace(tracklet=tracklet, hazard=hazard, metadata=meta)
        result = format_close_approach_bulletin(neo)
        assert "NOT" in result
        assert "GUARDRAIL" in result
        assert "NEO001" in result
        assert "0.030000" in result

    def test_handles_none_fields(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_close_approach_bulletin
        neo = SimpleNamespace(tracklet=None, hazard=None, metadata=None)
        result = format_close_approach_bulletin(neo)
        assert "unknown" in result
        assert "NOT" in result

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_close_approach_bulletin" in alert.__all__


class TestFormatIauCircularDraft:
    def _make_neo(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        obs1 = SimpleNamespace(jd=2460000.0, ra_deg=10.0, dec_deg=5.0, mag=18.5)
        obs2 = SimpleNamespace(jd=2460001.0, ra_deg=10.1, dec_deg=5.1, mag=18.4)
        tracklet = SimpleNamespace(object_id="2026AB1", observations=(obs1, obs2))
        hazard = SimpleNamespace(
            neo_class="apollo",
            moid_au=0.03,
            absolute_magnitude_h=21.5,
            alert_pathway="mpc_submission",
        )
        metadata = SimpleNamespace(discovery_priority=0.85)
        return SimpleNamespace(tracklet=tracklet, hazard=hazard, metadata=metadata)

    def test_contains_not_guardrail(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_iau_circular_draft
        neo = self._make_neo()
        result = format_iau_circular_draft(neo)
        assert "NOT" in result

    def test_contains_object_id(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_iau_circular_draft
        neo = self._make_neo()
        result = format_iau_circular_draft(neo)
        assert "2026AB1" in result

    def test_contains_draft_header(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_iau_circular_draft
        neo = self._make_neo()
        result = format_iau_circular_draft(neo)
        assert "DRAFT IAU CIRCULAR" in result

    def test_no_tracklet(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_iau_circular_draft
        neo = SimpleNamespace(tracklet=None, hazard=None, metadata=None)
        result = format_iau_circular_draft(neo)
        assert "NOT" in result
        assert "unknown" in result

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_iau_circular_draft" in alert.__all__


class TestFormatTelescopeTargetList:
    def _make_neo(self, priority=0.9):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        obs = SimpleNamespace(jd=2460000.0, ra_deg=180.0, dec_deg=5.0, mag=18.5)
        tracklet = SimpleNamespace(object_id="2026AB1", observations=(obs,))
        hazard = SimpleNamespace(alert_pathway="mpc_submission")
        metadata = SimpleNamespace(discovery_priority=priority)
        return SimpleNamespace(tracklet=tracklet, hazard=hazard, metadata=metadata)

    def test_contains_not_guardrail(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_telescope_target_list
        result = format_telescope_target_list([self._make_neo()])
        assert "NOT" in result

    def test_contains_object_id(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_telescope_target_list
        result = format_telescope_target_list([self._make_neo()])
        assert "2026AB1" in result

    def test_urgent_sorted_first(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_telescope_target_list
        urgent = self._make_neo(priority=0.9)
        routine = self._make_neo(priority=0.1)
        result = format_telescope_target_list([routine, urgent])
        assert result.index("URGENT") < result.index("ROUTINE")

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_telescope_target_list
        result = format_telescope_target_list([])
        assert "NOT" in result

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_telescope_target_list" in alert.__all__

    def test_no_observations_branch(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_telescope_target_list
        tracklet = SimpleNamespace(object_id="NOOBS", observations=())
        hazard = SimpleNamespace(alert_pathway="internal_candidate")
        metadata = SimpleNamespace(discovery_priority=0.0)
        neo = SimpleNamespace(tracklet=tracklet, hazard=hazard, metadata=metadata)
        result = format_telescope_target_list([neo])
        assert "NOOBS" in result
        assert "ROUTINE" in result

    def test_high_urgency(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_telescope_target_list
        neo = self._make_neo(priority=0.70)
        result = format_telescope_target_list([neo])
        assert "HIGH" in result

    def test_medium_urgency(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_telescope_target_list
        neo = self._make_neo(priority=0.50)
        result = format_telescope_target_list([neo])
        assert "MEDIUM" in result


class TestComputeAlertPriorityScore:
    def test_high_priority_neo(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import compute_alert_priority_score
        features = SimpleNamespace(known_object_score=0.0, orbit_quality_score=0.9)
        metadata = SimpleNamespace(discovery_priority=0.95)
        neo = SimpleNamespace(features=features, metadata=metadata)
        result = compute_alert_priority_score(neo)
        assert result > 0.7

    def test_known_object_low_priority(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import compute_alert_priority_score
        features = SimpleNamespace(known_object_score=1.0, orbit_quality_score=0.5)
        metadata = SimpleNamespace(discovery_priority=0.2)
        neo = SimpleNamespace(features=features, metadata=metadata)
        result = compute_alert_priority_score(neo)
        assert result < 0.5

    def test_missing_values_use_neutral(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import compute_alert_priority_score
        features = SimpleNamespace()
        metadata = SimpleNamespace(discovery_priority=None)
        neo = SimpleNamespace(features=features, metadata=metadata)
        result = compute_alert_priority_score(neo)
        # 0.4*0.5 + 0.3*0.5 + 0.3*0.5 = 0.5
        assert abs(result - 0.5) < 0.01

    def test_result_clamped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import compute_alert_priority_score
        features = SimpleNamespace(known_object_score=0.0, orbit_quality_score=1.0)
        metadata = SimpleNamespace(discovery_priority=1.0)
        neo = SimpleNamespace(features=features, metadata=metadata)
        result = compute_alert_priority_score(neo)
        assert 0.0 <= result <= 1.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "compute_alert_priority_score" in alert.__all__




class TestFormatMpcAdesHeader:
    def _make_neo(self, object_id="NEO-001"):
        from types import SimpleNamespace
        tracklet = SimpleNamespace(object_id=object_id)
        return SimpleNamespace(tracklet=tracklet)

    def test_contains_version(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_header
        neo = self._make_neo()
        result = format_mpc_ades_header(neo)
        assert "# version=2017" in result

    def test_contains_obs_code(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_header
        neo = self._make_neo()
        result = format_mpc_ades_header(neo, obs_code="703")
        assert "703" in result

    def test_contains_guardrail(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_header
        neo = self._make_neo()
        result = format_mpc_ades_header(neo)
        assert "NOT" in result

    def test_contains_neo_id(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_header
        neo = self._make_neo("MY-SPECIAL-NEO")
        result = format_mpc_ades_header(neo)
        assert "MY-SPECIAL-NEO" in result

    def test_default_obs_code(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_header
        neo = self._make_neo()
        result = format_mpc_ades_header(neo)
        assert "500" in result

    def test_returns_string(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_ades_header
        neo = self._make_neo()
        result = format_mpc_ades_header(neo)
        assert isinstance(result, str)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_mpc_ades_header" in alert.__all__


class TestGenerateFollowupPriorityList:
    def test_returns_list(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_followup_priority_list
        neos = [make_scored_neo()]
        result = generate_followup_priority_list(neos)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_guardrail_present(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_followup_priority_list
        neos = [make_scored_neo()]
        result = generate_followup_priority_list(neos)
        assert "NOT" in result[0]["guardrail"]

    def test_empty_neos_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_followup_priority_list
        assert generate_followup_priority_list([]) == []

    def test_max_items_limits_results(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_followup_priority_list
        neos = [make_scored_neo() for _ in range(5)]
        result = generate_followup_priority_list(neos, max_items=3)
        assert len(result) <= 3

    def test_required_keys_present(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_followup_priority_list
        neos = [make_scored_neo()]
        row = generate_followup_priority_list(neos)[0]
        for key in ("object_id", "urgency", "alert_pathway", "moid_au",
                    "discovery_priority", "guardrail"):
            assert key in row

    def test_sorted_by_priority_descending(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_followup_priority_list
        neo_hi = make_scored_neo()
        neo_lo = make_scored_neo()
        # Adjust discovery_priority via SimpleNamespace wrapper
        from types import SimpleNamespace
        lo_meta = SimpleNamespace(discovery_priority=0.1)
        hi_meta = SimpleNamespace(discovery_priority=0.9)
        neo_hi_ns = SimpleNamespace(
            tracklet=neo_hi.tracklet,
            hazard=neo_hi.hazard,
            metadata=hi_meta,
        )
        neo_lo_ns = SimpleNamespace(
            tracklet=neo_lo.tracklet,
            hazard=neo_lo.hazard,
            metadata=lo_meta,
        )
        result = generate_followup_priority_list([neo_lo_ns, neo_hi_ns])
        assert result[0]["discovery_priority"] >= result[1]["discovery_priority"]

    def test_urgency_high_for_low_moid(self):
        """MOID <= 0.1 AU but not PHA → HIGH urgency."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import generate_followup_priority_list
        neo = make_scored_neo(moid_au=0.05, hazard_flag="close_approach")
        hazard = SimpleNamespace(hazard_flag="close_approach", moid_au=0.05,
                                 alert_pathway="mpc_submission")
        meta = SimpleNamespace(discovery_priority=0.5)
        neo_ns = SimpleNamespace(tracklet=neo.tracklet, hazard=hazard, metadata=meta)
        result = generate_followup_priority_list([neo_ns])
        assert result[0]["urgency"] == "HIGH"

    def test_urgency_medium_for_high_priority(self):
        """discovery_priority >= 0.7 → MEDIUM urgency."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import generate_followup_priority_list
        neo = make_scored_neo()
        hazard = SimpleNamespace(hazard_flag="nominal", moid_au=None,
                                 alert_pathway="internal_candidate")
        meta = SimpleNamespace(discovery_priority=0.8)
        neo_ns = SimpleNamespace(tracklet=neo.tracklet, hazard=hazard, metadata=meta)
        result = generate_followup_priority_list([neo_ns])
        assert result[0]["urgency"] == "MEDIUM"

    def test_urgency_routine_for_low_priority_no_moid(self):
        """Low priority, no MOID → ROUTINE."""
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import generate_followup_priority_list
        neo = make_scored_neo()
        hazard = SimpleNamespace(hazard_flag="nominal", moid_au=None,
                                 alert_pathway="internal_candidate")
        meta = SimpleNamespace(discovery_priority=0.3)
        neo_ns = SimpleNamespace(tracklet=neo.tracklet, hazard=hazard, metadata=meta)
        result = generate_followup_priority_list([neo_ns])
        assert result[0]["urgency"] == "ROUTINE"

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "generate_followup_priority_list" in alert.__all__


class TestCountAlertsByHazardFlag:
    def _make_neo(self, hazard_flag):
        import sys
        sys.path.insert(0, "src")
        from .conftest import build_scored_neo
        return build_scored_neo(hazard_flag=hazard_flag)

    def test_empty_list_returns_empty_dict(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_alerts_by_hazard_flag
        assert count_alerts_by_hazard_flag([]) == {}

    def test_single_candidate(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_alerts_by_hazard_flag
        neos = [self._make_neo("pha_candidate")]
        counts = count_alerts_by_hazard_flag(neos)
        assert counts == {"pha_candidate": 1}

    def test_multiple_same_flag(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_alerts_by_hazard_flag
        neos = [self._make_neo("nominal")] * 3
        counts = count_alerts_by_hazard_flag(neos)
        assert counts["nominal"] == 3

    def test_mixed_flags(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_alerts_by_hazard_flag
        neos = [
            self._make_neo("pha_candidate"),
            self._make_neo("nominal"),
            self._make_neo("nominal"),
            self._make_neo("close_approach"),
        ]
        counts = count_alerts_by_hazard_flag(neos)
        assert counts["pha_candidate"] == 1
        assert counts["nominal"] == 2
        assert counts["close_approach"] == 1

    def test_zero_counts_excluded(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_alerts_by_hazard_flag
        neos = [self._make_neo("pha_candidate")]
        counts = count_alerts_by_hazard_flag(neos)
        # Only pha_candidate should appear; no zero-count entries
        for v in counts.values():
            assert v > 0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "count_alerts_by_hazard_flag" in alert.__all__


class TestGenerateMpcBatchHeader:
    def _make_neo(self, object_id="T001", jds=None):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        obs_list = []
        for jd in (jds or [2460000.5, 2460001.5]):
            obs_list.append(SimpleNamespace(jd=jd))
        tracklet = SimpleNamespace(observations=obs_list)
        return SimpleNamespace(tracklet=tracklet)

    def test_basic_header_contains_n_candidates(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_mpc_batch_header
        neos = [self._make_neo()]
        header = generate_mpc_batch_header(neos)
        assert "N candidates: 1" in header

    def test_contains_guardrail(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_mpc_batch_header
        neos = [self._make_neo()]
        header = generate_mpc_batch_header(neos)
        assert "NOT" in header

    def test_epoch_range_from_observations(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_mpc_batch_header
        neos = [self._make_neo(jds=[2460000.5, 2460002.5])]
        header = generate_mpc_batch_header(neos)
        assert "2460000.5000" in header
        assert "2460002.5000" in header

    def test_empty_neos_gives_na_epoch(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_mpc_batch_header
        header = generate_mpc_batch_header([])
        assert "N/A" in header
        assert "N candidates: 0" in header

    def test_custom_obs_code(self):
        import sys
        sys.path.insert(0, "src")
        from alert import generate_mpc_batch_header
        neos = [self._make_neo()]
        header = generate_mpc_batch_header(neos, obs_code="G96")
        assert "G96" in header

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "generate_mpc_batch_header" in alert.__all__


class TestFormatCandidateSummaryTable:
    @staticmethod
    def _make_neo(object_id="NEO-001", hazard_flag="pha_candidate", moid_au=0.03, priority=0.85):
        from types import SimpleNamespace
        tracklet = SimpleNamespace(object_id=object_id)
        hazard = SimpleNamespace(hazard_flag=hazard_flag, moid_au=moid_au)
        metadata = SimpleNamespace(discovery_priority=priority)
        return SimpleNamespace(tracklet=tracklet, hazard=hazard, metadata=metadata)

    def test_header_present(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_summary_table
        neos = [self._make_neo()]
        table = format_candidate_summary_table(neos)
        assert "NOT" in table
        assert "NEO Candidate Summary" in table

    def test_contains_object_id(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_summary_table
        neos = [self._make_neo("MYOBJ-42")]
        table = format_candidate_summary_table(neos)
        assert "MYOBJ-42" in table

    def test_max_rows_truncation(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_summary_table
        neos = [self._make_neo(f"NEO-{i:03d}") for i in range(30)]
        table = format_candidate_summary_table(neos, max_rows=5)
        # 5 rows + header + col header + separator = 8 lines
        lines = table.strip().split("\n")
        assert len(lines) == 8

    def test_empty_neos(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_summary_table
        table = format_candidate_summary_table([])
        assert "NOT" in table
        assert isinstance(table, str)

    def test_none_moid(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_summary_table
        neos = [self._make_neo(moid_au=None)]
        table = format_candidate_summary_table(neos)
        assert "N/A" in table

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_candidate_summary_table" in alert.__all__


class TestEstimateConfirmationTime:
    """Tests for estimate_confirmation_time."""

    @staticmethod
    def _make_neo(hazard_flag="pha_candidate", moid_au=0.01, priority=0.95):
        from types import SimpleNamespace

        hazard = SimpleNamespace(
            hazard_flag=hazard_flag,
            moid_au=moid_au,
        )
        metadata = SimpleNamespace(discovery_priority=priority)
        tracklet = SimpleNamespace(object_id="NEO-TEST")
        return SimpleNamespace(hazard=hazard, metadata=metadata, tracklet=tracklet,
                               features=SimpleNamespace(
                                   arc_coverage_score=0.8,
                                   nights_observed_score=0.7,
                                   moid_score=1.0,
                                   orbit_quality_score=0.9,
                               ))

    def test_urgent_returns_6(self):
        import sys
        sys.path.insert(0, "src")

        from alert import estimate_confirmation_time

        # PHA with very high priority → URGENT
        neo = self._make_neo("pha_candidate", 0.001, 0.99)
        result = estimate_confirmation_time(neo)
        assert result == 6.0

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")

        from alert import estimate_confirmation_time

        neo = self._make_neo()
        result = estimate_confirmation_time(neo)
        assert isinstance(result, float)

    def test_routine_returns_168(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import estimate_confirmation_time

        # Low priority nominal → ROUTINE
        neo = SimpleNamespace(
            hazard=SimpleNamespace(hazard_flag="nominal", moid_au=1.0),
            metadata=SimpleNamespace(discovery_priority=0.1),
            tracklet=SimpleNamespace(object_id="N001"),
            features=SimpleNamespace(
                arc_coverage_score=0.1, nights_observed_score=0.1,
                moid_score=0.0, orbit_quality_score=0.1,
            ),
        )
        result = estimate_confirmation_time(neo)
        assert result == 168.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert

        assert "estimate_confirmation_time" in alert.__all__

    def test_positive_result(self):
        import sys
        sys.path.insert(0, "src")

        from alert import estimate_confirmation_time

        neo = self._make_neo()
        assert estimate_confirmation_time(neo) > 0.0

    def test_result_is_one_of_known_values(self):
        import sys
        sys.path.insert(0, "src")

        from alert import estimate_confirmation_time

        neo = self._make_neo()
        result = estimate_confirmation_time(neo)
        assert result in (6.0, 24.0, 72.0, 168.0)


class TestFormatAlertAgeSummary:
    def _make_neo(self, jds: list[float]) -> object:
        from types import SimpleNamespace
        obs = [SimpleNamespace(jd=j) for j in jds]
        tracklet = SimpleNamespace(observations=tuple(obs))
        return SimpleNamespace(tracklet=tracklet)

    def test_basic_summary(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_alert_age_summary
        neos = [
            self._make_neo([2460000.0, 2460001.0]),
            self._make_neo([2460002.0, 2460003.0]),
        ]
        result = format_alert_age_summary(neos)
        assert result["count"] == 2
        assert result["oldest_jd"] == 2460001.0
        assert result["newest_jd"] == 2460003.0

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_alert_age_summary
        result = format_alert_age_summary([])
        assert result["count"] == 0
        assert result["oldest_jd"] is None
        assert result["newest_jd"] is None

    def test_guardrail_contains_not(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_alert_age_summary
        result = format_alert_age_summary([self._make_neo([2460000.0])])
        assert "NOT" in result["guardrail"]

    def test_no_observations_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_alert_age_summary
        neo_empty = SimpleNamespace(tracklet=SimpleNamespace(observations=()))
        neo_good = self._make_neo([2460010.0])
        result = format_alert_age_summary([neo_empty, neo_good])
        assert result["count"] == 2
        assert result["newest_jd"] == 2460010.0

    def test_single_neo(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_alert_age_summary
        neos = [self._make_neo([2460005.0, 2460006.0])]
        result = format_alert_age_summary(neos)
        assert result["oldest_jd"] == result["newest_jd"] == 2460006.0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_alert_age_summary" in alert.__all__


class TestFormatCandidateCountSummary:
    def _make_neo(self, flag: str, pathway: str) -> object:
        from types import SimpleNamespace
        hazard = SimpleNamespace(hazard_flag=flag, alert_pathway=pathway)
        return SimpleNamespace(hazard=hazard)

    def test_basic_counts(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_count_summary
        neos = [
            self._make_neo("nominal", "internal_candidate"),
            self._make_neo("nominal", "internal_candidate"),
            self._make_neo("pha_candidate", "mpc_submission"),
        ]
        result = format_candidate_count_summary(neos)
        assert result["total"] == 3
        assert result["by_hazard_flag"]["nominal"] == 2
        assert result["by_hazard_flag"]["pha_candidate"] == 1

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_count_summary
        result = format_candidate_count_summary([])
        assert result["total"] == 0
        assert result["by_hazard_flag"] == {}

    def test_guardrail_contains_not(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_count_summary
        result = format_candidate_count_summary([self._make_neo("unknown", "internal_candidate")])
        assert "NOT" in result["guardrail"]

    def test_no_hazard_attr(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_candidate_count_summary
        neo = SimpleNamespace(hazard=None)
        result = format_candidate_count_summary([neo])
        assert result["total"] == 1
        assert result["by_hazard_flag"]["unknown"] == 1

    def test_pathway_counts(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_candidate_count_summary
        neos = [
            self._make_neo("nominal", "mpc_submission"),
            self._make_neo("nominal", "mpc_submission"),
            self._make_neo("nominal", "internal_candidate"),
        ]
        result = format_candidate_count_summary(neos)
        assert result["by_alert_pathway"]["mpc_submission"] == 2
        assert result["by_alert_pathway"]["internal_candidate"] == 1

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_candidate_count_summary" in alert.__all__


class TestFormatObservationCountSummary:
    def _make_neo(self, obs_missions):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace
        obs = [SimpleNamespace(obs_id=f"O{i}", mission=m) for i, m in enumerate(obs_missions)]
        tracklet = SimpleNamespace(observations=tuple(obs))
        return SimpleNamespace(tracklet=tracklet)

    def test_basic_counts(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_observation_count_summary
        neos = [
            self._make_neo(["ZTF", "ZTF", "ATLAS"]),
            self._make_neo(["ZTF"]),
        ]
        result = format_observation_count_summary(neos)
        assert result["total_observations"] == 4
        assert result["by_mission"]["ZTF"] == 3
        assert result["by_mission"]["ATLAS"] == 1
        assert result["n_candidates"] == 2

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_observation_count_summary
        result = format_observation_count_summary([])
        assert result["total_observations"] == 0
        assert result["n_candidates"] == 0
        assert result["by_mission"] == {}

    def test_guardrail_contains_not(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_observation_count_summary
        result = format_observation_count_summary([])
        assert "NOT" in result["guardrail"]

    def test_no_tracklet_attr(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_observation_count_summary
        neo = SimpleNamespace(tracklet=None)
        result = format_observation_count_summary([neo])
        assert result["total_observations"] == 0
        assert result["n_candidates"] == 1

    def test_none_mission_mapped_to_unknown(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from alert import format_observation_count_summary
        obs = [SimpleNamespace(obs_id="O1", mission=None)]
        tracklet = SimpleNamespace(observations=tuple(obs))
        neo = SimpleNamespace(tracklet=tracklet)
        result = format_observation_count_summary([neo])
        assert result["by_mission"]["unknown"] == 1

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_observation_count_summary" in alert.__all__


class TestCountSubmissionReady:
    def _make_neo(self, rb=0.95, quality=2, moid=0.03, known_score=0.0, neo_prob=0.6):
        from types import SimpleNamespace
        features = SimpleNamespace(
            real_bogus_score=rb,
            orbit_quality_score=quality / 4.0,
            known_object_score=known_score,
        )
        orbital_elements = SimpleNamespace(quality_code=quality)
        hazard = SimpleNamespace(
            moid_au=moid,
            neo_class="apollo",
            alert_pathway="mpc_submission",
            orbital_elements=orbital_elements,
        )
        posterior = SimpleNamespace(
            neo_candidate=neo_prob,
            known_object=0.1,
            main_belt_asteroid=0.1,
            stellar_artifact=0.1,
            other_solar_system=0.1,
        )
        meta = SimpleNamespace(
            quality_code=quality,
            discovery_priority=0.5,
            close_approach_au=moid,
        )
        return SimpleNamespace(features=features, hazard=hazard, posterior=posterior, metadata=meta)

    def test_all_ready(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_submission_ready
        neos = [self._make_neo() for _ in range(3)]
        assert count_submission_ready(neos) == 3

    def test_none_ready_low_rb(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_submission_ready
        neos = [self._make_neo(rb=0.5) for _ in range(3)]
        assert count_submission_ready(neos) == 0

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from alert import count_submission_ready
        assert count_submission_ready([]) == 0

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "count_submission_ready" in alert.__all__


class TestFormatMpcObservationBlock:
    def test_returns_string(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_observation_block

        neo = make_scored_neo()
        block = format_mpc_observation_block(neo)
        assert isinstance(block, str)

    def test_line_count_equals_observations(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_observation_block

        neo = make_scored_neo()
        block = format_mpc_observation_block(neo)
        lines = block.split("\n")
        assert len(lines) == len(neo.tracklet.observations)

    def test_each_line_is_80_chars(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_observation_block

        neo = make_scored_neo()
        for line in format_mpc_observation_block(neo).split("\n"):
            assert len(line) == 80, f"Line length {len(line)}: {line!r}"

    def test_first_line_is_discovery(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_observation_block

        neo = make_scored_neo()
        first_line = format_mpc_observation_block(neo).split("\n")[0]
        # Column 6 (index 5) is the discovery asterisk
        assert first_line[5] == "*"

    def test_subsequent_lines_not_discovery(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_observation_block

        neo = make_scored_neo()
        lines = format_mpc_observation_block(neo).split("\n")
        for line in lines[1:]:
            assert line[5] == " "

    def test_custom_obs_code(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_mpc_observation_block

        neo = make_scored_neo()
        block = format_mpc_observation_block(neo, obs_code="703")
        for line in block.split("\n"):
            assert line[76:79] == "703"

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_mpc_observation_block" in alert.__all__


class TestFormatNeocpSubmissionHeader:
    def test_returns_string(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_neocp_submission_header

        neo = make_scored_neo()
        header = format_neocp_submission_header(neo)
        assert isinstance(header, str)

    def test_five_lines(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_neocp_submission_header

        neo = make_scored_neo()
        lines = format_neocp_submission_header(neo).split("\n")
        assert len(lines) == 5

    def test_cod_line(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_neocp_submission_header

        neo = make_scored_neo()
        lines = format_neocp_submission_header(neo, obs_code="703").split("\n")
        assert lines[0] == "COD 703"

    def test_ack_contains_object_id(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_neocp_submission_header

        neo = make_scored_neo()
        header = format_neocp_submission_header(neo)
        assert neo.tracklet.object_id in header

    def test_obs_mea_tel_present(self):
        import sys
        sys.path.insert(0, "src")
        from alert import format_neocp_submission_header

        neo = make_scored_neo()
        header = format_neocp_submission_header(neo)
        assert "OBS " in header
        assert "MEA " in header
        assert "TEL " in header

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import alert
        assert "format_neocp_submission_header" in alert.__all__
