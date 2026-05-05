"""Tests for alert.py — MPC formatting and alert protocol guardrails."""

import sys
sys.path.insert(0, "src")

import pytest
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
from alert import (
    _jd_to_mpc_date,
    _format_ra,
    _format_dec,
    format_mpc_observation,
    format_mpc_report,
    process_alert,
    summarise,
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

    def test_no_impact_probability_assertion(self):
        neo = make_scored_neo()
        summary = summarise(neo)
        # Must not assert any impact probability
        assert "impact probability" not in summary.lower() or "does not assert" in summary.lower()

    def test_summarise_contains_pathway(self):
        neo = make_scored_neo()
        summary = summarise(neo)
        assert "mpc_submission" in summary or "alert_pathway" in summary.lower() or "Alert pathway" in summary
