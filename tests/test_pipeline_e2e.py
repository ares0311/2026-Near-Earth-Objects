"""End-to-end pipeline integration tests (no network required)."""


from alert import format_mpc_report, process_alert
from classify import classify
from link import link
from schemas import Observation, RawCandidate
from score import score


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="e2e_001",
        ra_deg=180.0,
        dec_deg=5.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.92,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def _make_neo_candidates() -> tuple[RawCandidate, ...]:
    """Three nights of observations with 1 arcsec/hr eastward motion."""
    dra_per_day = 1.0 * 24 / 3600  # degrees/day
    candidates = []
    for night in range(3):
        jd_base = float(2460000 + night)
        obs = (
            make_obs(
                obs_id=f"e2e_n{night}_a",
                jd=jd_base,
                ra_deg=180.0 + night * dra_per_day,
                dec_deg=5.0,
            ),
            make_obs(
                obs_id=f"e2e_n{night}_b",
                jd=jd_base + 1 / 24,
                ra_deg=180.0 + night * dra_per_day + dra_per_day / 24,
                dec_deg=5.0,
            ),
        )
        candidates.append(
            RawCandidate(
                candidate_id=f"C{night:03d}",
                observations=obs,
                apparent_motion_arcsec_per_hr=1.0,
                motion_pa_deg=90.0,
            )
        )
    return tuple(candidates)


class TestLinkToScore:
    def test_link_produces_linkresult(self):
        cands = _make_neo_candidates()
        result = link(cands, min_nights=2, min_observations=3, position_tolerance_arcsec=60.0)
        assert result.provenance.min_nights == 2
        assert result.provenance.min_observations == 3

    def test_classify_on_synthetic_tracklet(self):
        """classify returns CandidateFeatures and NEOPosterior."""
        from tests.test_classify import make_tracklet
        t = make_tracklet(n_obs=4, arc_days=3.0)
        features, posterior = classify(t)
        assert features.real_bogus_score is not None
        assert 0.0 <= posterior.neo_candidate <= 1.0

    def test_score_on_classified_tracklet(self):
        from tests.test_classify import make_tracklet
        from tests.test_score import make_features, make_orbital, make_posterior
        t = make_tracklet(n_obs=4, arc_days=3.0)
        f = make_features(real_bogus_score=0.92)
        p = make_posterior(neo_candidate=0.75)
        orb = make_orbital()
        result = score(t, f, p, orb)
        valid = {"pha_candidate", "close_approach", "nominal", "unknown"}
        assert result.hazard.hazard_flag in valid
        assert result.metadata.scorer_version == "0.1.0"

    def test_alert_format_on_scored_neo(self):
        from tests.test_alert import make_scored_neo
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        report = format_mpc_report(neo)
        assert "COD" in report

    def test_process_alert_dry_run(self, tmp_path, monkeypatch):
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from tests.test_alert import make_scored_neo
        neo = make_scored_neo(rb=0.95, orbit_quality=2, moid_au=0.03)
        result = process_alert(neo, dry_run=True)
        assert "pathway" in result
        assert "actions" in result

    def test_full_chain_no_exceptions(self, tmp_path, monkeypatch):
        """Smoke test: link → classify → score → alert without errors."""
        import alert as alert_mod
        monkeypatch.setattr(alert_mod, "_LOG_DIR", tmp_path)
        from tests.test_classify import make_tracklet
        from tests.test_score import make_orbital

        t = make_tracklet(n_obs=5, arc_days=4.0)
        features, posterior = classify(t)
        orb = make_orbital()
        scored = score(t, features, posterior, orb)
        result = process_alert(scored, dry_run=True)
        assert result is not None
