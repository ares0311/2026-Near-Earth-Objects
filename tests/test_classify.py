"""Tests for classify.py."""

import sys

sys.path.insert(0, "src")

import pytest

from classify import (
    _arc_coverage,
    _brightness_score,
    _mean_real_bogus,
    _nights_score,
    _tier1_predict,
    classify,
    extract_features,
)
from schemas import CandidateFeatures, Observation, Tracklet


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="c_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.9,
    )
    defaults.update(kwargs)
    return Observation(**defaults)


def make_tracklet(n_obs: int = 4, arc_days: float = 3.0) -> Tracklet:
    obs = tuple(
        make_obs(
            obs_id=f"t_{i}",
            jd=2460000.5 + i * arc_days / max(n_obs - 1, 1),
            ra_deg=180.0 + i * 0.005,
        )
        for i in range(n_obs)
    )
    return Tracklet(
        object_id="T001",
        observations=obs,
        arc_days=arc_days,
        motion_rate_arcsec_per_hour=1.2,
        motion_pa_degrees=90.0,
    )


class TestFeatureExtraction:
    def test_real_bogus_mean(self):
        t = make_tracklet()
        rb = _mean_real_bogus(t)
        assert rb == pytest.approx(0.9, abs=1e-6)

    def test_real_bogus_none(self):
        obs = make_obs(real_bogus=None, deep_real_bogus=None)
        t = Tracklet("T", (obs,), 0.0, 0.0, 0.0)
        assert _mean_real_bogus(t) is None

    def test_arc_coverage(self):
        t = make_tracklet(arc_days=15.0)
        score = _arc_coverage(t)
        assert score == pytest.approx(0.5, abs=1e-6)

    def test_arc_coverage_clamp(self):
        t = make_tracklet(arc_days=60.0)
        score = _arc_coverage(t)
        assert score == 1.0

    def test_nights_score_two_nights(self):
        obs1 = make_obs(obs_id="a", jd=2460000.5)
        obs2 = make_obs(obs_id="b", jd=2460001.5)
        t = Tracklet("T", (obs1, obs2), 1.0, 1.0, 0.0)
        score = _nights_score(t)
        assert 0.0 < score <= 1.0

    def test_brightness_score(self):
        t = make_tracklet()
        score = _brightness_score(t)
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_extract_features_returns_features(self):
        t = make_tracklet()
        f = extract_features(t)
        assert isinstance(f, CandidateFeatures)
        assert f.real_bogus_score is not None


class TestTier1Predict:
    def test_returns_five_classes(self):
        f = CandidateFeatures(real_bogus_score=0.9, nights_observed_score=0.5)
        proba = _tier1_predict(f, model=None)
        assert set(proba.keys()) == {
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system"
        }

    def test_probabilities_nonnegative(self):
        f = CandidateFeatures(real_bogus_score=0.7)
        proba = _tier1_predict(f, model=None)
        for v in proba.values():
            assert v is not None and v >= 0.0

    def test_high_rb_scores_neo(self):
        f = CandidateFeatures(
            real_bogus_score=0.99,
            motion_consistency_score=0.9,
            nights_observed_score=0.8,
        )
        proba = _tier1_predict(f, model=None)
        # High rb → higher neo_candidate relative to artifact
        assert proba["neo_candidate"] > proba["stellar_artifact"]


class TestClassifyPipeline:
    def test_returns_features_and_posterior(self):
        t = make_tracklet()
        features, posterior = classify(t)
        assert isinstance(features, CandidateFeatures)
        assert 0.0 <= posterior.neo_candidate <= 1.0
        assert 0.0 <= posterior.stellar_artifact <= 1.0

    def test_posterior_components_nonnegative(self):
        t = make_tracklet()
        _, posterior = classify(t)
        for field in ("neo_candidate", "known_object", "main_belt_asteroid",
                      "stellar_artifact", "other_solar_system"):
            assert getattr(posterior, field) >= 0.0
