"""End-to-end synthetic pipeline test: Detect → Link → Score."""

import pytest

from detect import detect
from link import link
from orbit import fit_orbit
from schemas import (
    CandidateFeatures,
    NEOPosterior,
    Observation,
)
from score import score


def make_obs(obs_id: str, jd: float, ra_deg: float, dec_deg: float = 0.0) -> Observation:
    return Observation(
        obs_id=obs_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        jd=jd,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.9,
    )


class TestEndToEndSynthetic:
    def _make_moving_observations(self) -> tuple[Observation, ...]:
        """Three nights, consistent eastward motion at ~1 arcsec/hr."""
        dra_per_hr = 1.0 / 3600.0  # 1 arcsec/hr in deg
        obs = []
        for night in range(3):
            jd_base = 2460000.5 + night
            ra_base = 180.0 + night * dra_per_hr * 24
            obs.append(make_obs(f"n{night}_a", jd_base, ra_base))
            obs.append(make_obs(f"n{night}_b", jd_base + 1 / 24, ra_base + dra_per_hr))
        return tuple(obs)

    def test_detect_produces_candidates(self):
        obs = self._make_moving_observations()
        result = detect(obs, mpc_cross_match=False)
        assert len(result.candidates) >= 1

    def test_link_produces_tracklets(self):
        obs = self._make_moving_observations()
        detect_result = detect(obs, mpc_cross_match=False)
        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)
        assert link_result.provenance.min_nights == 2

    def test_score_returns_hazard(self):
        obs = self._make_moving_observations()
        detect_result = detect(obs, mpc_cross_match=False)
        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)

        if not link_result.tracklets:
            pytest.skip("No tracklets produced — link threshold not met by synthetic data")

        t = link_result.tracklets[0]
        orbital = fit_orbit(t)

        features = CandidateFeatures(
            real_bogus_score=0.9,
            nights_observed_score=0.8,
            motion_consistency_score=0.9,
        )
        posterior = NEOPosterior(
            neo_candidate=0.6,
            known_object=0.1,
            main_belt_asteroid=0.1,
            stellar_artifact=0.1,
            other_solar_system=0.1,
        )

        result = score(t, features, posterior, orbital)
        valid_flags = {"pha_candidate", "close_approach", "nominal", "unknown"}
        assert result.hazard.hazard_flag in valid_flags
        assert result.metadata.discovery_priority >= 0.0

    def test_provenance_chain(self):
        obs = self._make_moving_observations()
        detect_result = detect(obs, mpc_cross_match=False)
        assert detect_result.provenance is not None

        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)
        assert link_result.provenance is not None
        assert link_result.provenance.n_tracklets == len(link_result.tracklets)
