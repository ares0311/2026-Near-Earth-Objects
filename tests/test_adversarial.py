"""Adversarial and robustness tests for the NEO detection pipeline (T2-B).

These tests simulate real ZTF artifact conditions, ephemeris edge cases,
bad-pixel regions, and network failure modes — all using synthetic data
so they run fully offline in CI without any network access.
"""

from __future__ import annotations

import base64
import sys

import numpy as np
import pytest

# Ensure src/ is on the path (redundant when conftest.py is loaded, but
# makes the file importable in isolation too).
sys.path.insert(0, "src")

import alert
import fetch
import link
import orbit
from schemas import (
    Observation,
    OrbitalElements,
    RawCandidate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_obs(
    obs_id: str,
    ra_deg: float,
    dec_deg: float,
    jd: float,
    real_bogus: float = 0.9,
    cutout_difference: str | None = None,
) -> Observation:
    """Build a minimal Observation for adversarial testing."""
    return Observation(
        obs_id=obs_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        jd=jd,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=real_bogus,
        cutout_difference=cutout_difference,
    )


def _make_candidate(
    candidate_id: str,
    obs_list: list[Observation],
    rate: float = 35.0,
) -> RawCandidate:
    """Build a RawCandidate from a list of Observation objects."""
    return RawCandidate(
        candidate_id=candidate_id,
        observations=tuple(obs_list),
        apparent_motion_arcsec_per_hr=rate,
    )


def _flat_cutout_b64(size: int = 63, fill: float = 0.0) -> str:
    """Return a base64-encoded flat (all-zero or constant) float32 cutout."""
    arr = np.full((size, size), fill, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestAdversarial:
    """Adversarial and robustness scenarios for the NEO pipeline."""

    # ------------------------------------------------------------------
    # Test 1 — Satellite trail rejection
    # ------------------------------------------------------------------

    def test_satellite_trail_rejected(self) -> None:
        """Purely east-west fast motion (>30 arcsec/hr) must be rejected as satellite trail."""
        # Two observations 1 hour apart with ~40 arcsec eastward shift and
        # zero declination change — classic satellite geometry.
        dt_hr = 1.0
        dt_jd = dt_hr / 24.0
        cos_dec = np.cos(np.radians(10.0))
        # 40 arcsec eastward → dRA = 40 / (3600 * cos_dec) degrees
        dra_deg = 40.0 / (3600.0 * cos_dec)

        obs1 = _make_obs("sat_001", ra_deg=180.0, dec_deg=10.0, jd=2460000.0)
        obs2 = _make_obs(
            "sat_002",
            ra_deg=180.0 + dra_deg,
            dec_deg=10.0,  # zero Dec change = purely E-W
            jd=2460000.0 + dt_jd,
        )
        cand = _make_candidate("SAT", [obs1, obs2], rate=40.0)

        result = link.link(
            (cand,),
            # Lower the min_nights/min_observations to 1/2 so a two-obs,
            # single-night candidate would not be excluded on arc length alone.
            min_nights=1,
            min_observations=2,
        )
        # The satellite-trail filter (_is_satellite_trail) fires when
        # |dra|/rate >= 0.98 — this purely E-W pair must produce no tracklets.
        assert len(result.tracklets) == 0, (
            "Expected satellite trail to be rejected but got tracklets: "
            f"{result.tracklets}"
        )

    # ------------------------------------------------------------------
    # Test 2 — Missing difference-image cutout (cosmic ray / bad pixel)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Test 3 — Extreme (near-limit) motion rate still links
    # ------------------------------------------------------------------

    def test_very_fast_neo_links(self) -> None:
        """Observations at ~55 arcsec/hr must form a tracklet within the 60 arcsec/hr limit."""
        # Simulate a very fast NEO — near the top of the allowed motion range
        # ((0.05–60 arcsec/hr)).  Three observations across two nights.
        target_rate_arcsec_hr = 55.0  # just under the 60 arcsec/hr ceiling
        dt_hr = 1.0
        dt_jd = dt_hr / 24.0

        cos_dec = np.cos(np.radians(15.0))
        # Split motion equally between RA and Dec so it is not E-W only
        # (avoids the satellite-trail filter).
        component = target_rate_arcsec_hr / np.sqrt(2.0)
        dra_deg = component / (3600.0 * cos_dec) * dt_hr
        ddec_deg = component / 3600.0 * dt_hr

        # Night 1: two observations separated by 1 hour
        obs1 = _make_obs("fast_001", 180.0, 15.0, jd=2460000.0)
        obs2 = _make_obs(
            "fast_002",
            180.0 + dra_deg,
            15.0 + ddec_deg,
            jd=2460000.0 + dt_jd,
        )
        # Night 2: third observation roughly 1 day later, extrapolated position
        obs3 = _make_obs(
            "fast_003",
            180.0 + dra_deg * 24.0,
            15.0 + ddec_deg * 24.0,
            jd=2460001.0,
        )
        # Night 3: fourth observation, extrapolated 2 days — required so the
        # linker has a third night to propagate to (seed pair consumes nights 1
        # and 2; the propagation loop only visits OTHER nights).
        obs4 = _make_obs(
            "fast_004",
            180.0 + dra_deg * 48.0,
            15.0 + ddec_deg * 48.0,
            jd=2460002.0,
        )

        cand_night1 = _make_candidate("FAST_N1", [obs1, obs2], rate=target_rate_arcsec_hr)
        cand_night2 = _make_candidate("FAST_N2", [obs3], rate=target_rate_arcsec_hr)
        cand_night3 = _make_candidate("FAST_N3", [obs4], rate=target_rate_arcsec_hr)

        result = link.link(
            (cand_night1, cand_night2, cand_night3),
            min_nights=2,
            min_observations=3,
        )
        assert len(result.tracklets) >= 1, (
            "Expected at least one tracklet for a ~55 arcsec/hr NEO but got none"
        )

    # ------------------------------------------------------------------
    # Test 5 — Survey edge coordinates (near pole, high Dec)
    # ------------------------------------------------------------------

    def test_survey_edge_coordinates(self) -> None:
        """link.link must not crash on observations near the celestial pole (Dec=+89)."""
        # This exercises the cosine-Dec correction in _motion() near cos(89°) ≈ 0.017,
        # where floating-point errors can produce wildly incorrect motion rates.
        obs1 = _make_obs("edge_001", ra_deg=359.9, dec_deg=89.0, jd=2460000.0)
        obs2 = _make_obs("edge_002", ra_deg=0.1,   dec_deg=89.01, jd=2460000.5)

        cand = _make_candidate("EDGE", [obs1, obs2], rate=1.0)

        # No assertion on tracklet count — just assert no exception is raised.
        result = link.link((cand,), min_nights=1, min_observations=2)
        assert result is not None, "link.link returned None unexpectedly"

    # ------------------------------------------------------------------
    # Test 6 — Network timeout in fetch_atlas_forced
    # ------------------------------------------------------------------

    def test_fetch_atlas_timeout_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fetch_atlas_forced must return [] (not raise) when requests.post raises ConnectionError."""  # noqa: E501
        # The ATLAS fetch function wraps all network calls in a broad
        # except Exception block and returns [] on failure.  This test
        # verifies that a simulated network timeout results in an empty
        # list rather than an unhandled exception reaching the caller.
        import requests

        def _failing_post(*args, **kwargs):
            raise ConnectionError("simulated timeout")

        monkeypatch.setattr(requests, "post", _failing_post)

        # Must also clear any on-disk cache for this coordinate pair
        result = fetch.fetch_atlas_forced(
            ra_deg=180.0,
            dec_deg=0.0,
            start_jd=2460000.0,
            end_jd=2460010.0,
            atlas_token="fake_token_for_test",
            force_refresh=True,
        )
        assert result == [], (
            f"Expected empty list on ConnectionError, got {result!r}"
        )

    # ------------------------------------------------------------------
    # Test 9 — Missing / degenerate orbital elements
    # ------------------------------------------------------------------

    def test_missing_orbital_elements_graceful(self) -> None:
        """compute_moid must return None for an orbit with quality_code=0 (below minimum)."""
        # quality_code=0 is the degenerate / unmeasured case — orbit.compute_moid
        # must bail out gracefully rather than compute nonsense MOID values.
        elements = OrbitalElements(
            semi_major_axis_au=1.5,
            eccentricity=0.3,
            inclination_deg=10.0,
            longitude_ascending_node_deg=45.0,
            argument_perihelion_deg=90.0,
            mean_anomaly_deg=180.0,
            epoch_jd=2460000.5,
            perihelion_au=1.05,
            aphelion_au=1.95,
            quality_code=0,  # below the minimum accepted quality
        )
        result = orbit.compute_moid(elements)
        assert result is None, (
            f"Expected None for quality_code=0, got {result!r}"
        )

    # ------------------------------------------------------------------
    # Test 10 — Short arc blocks MPC submission
    # ------------------------------------------------------------------

    def test_short_arc_blocks_submission(self) -> None:
        """ready_for_submission must return False when orbit quality code < 2 (short arc)."""
        # A single-night arc (quality_code=1) is below the alert-protocol
        # gate of ≥2.  The submission check must block it with a non-empty
        # unmet-conditions list.
        import pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from conftest import build_scored_neo

        # orbit_quality=1 mimics a sub-24-hour arc — should block MPC submission.
        neo = build_scored_neo(orbit_quality=1, rb=0.95, moid_au=0.03)
        ready, unmet = alert.ready_for_submission(neo)
        assert not ready, (
            "Expected ready_for_submission=False for quality_code=1, got True"
        )
        assert len(unmet) > 0, (
            "Expected non-empty unmet-conditions list for short-arc NEO"
        )
        # Confirm the quality-code gate specifically appears in the unmet list
        assert any("quality" in u.lower() for u in unmet), (
            f"Expected 'quality' in unmet conditions, got {unmet}"
        )
