"""Tests for Skills/lookup_mpc_observation_history.py (Gate Z3 MPC
observation-history cross-check). fetch_mpc_observations is mocked --
this project's standing convention for external-service tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "lookup_mpc_observation_history.py"
)
_spec = importlib.util.spec_from_file_location("lookup_mpc_observation_history", _MODULE_PATH)
lookup_mpc_observation_history = importlib.util.module_from_spec(_spec)
sys.modules["lookup_mpc_observation_history"] = lookup_mpc_observation_history
_spec.loader.exec_module(lookup_mpc_observation_history)

from schemas import Observation  # noqa: E402


def _fake_observations():
    return [
        # Before the archive's coverage window (2018-06-04 = jd 2458273.5).
        Observation(
            obs_id="mpc_old", ra_deg=100.0, dec_deg=5.0, jd=2458000.0,
            mag=18.0, mag_err=0.1, filter_band="?", mission="MPC",
        ),
        # Within the archive's coverage window, matching the confirmed
        # real detection night 20180809.
        Observation(
            obs_id="mpc_1", ra_deg=232.6075742, dec_deg=-8.4449086, jd=2458339.6521991,
            mag=19.5, mag_err=0.1, filter_band="?", mission="MPC",
        ),
        # A second real in-window report, with a mock reporting-observatory
        # code set (via field_id) to confirm it flows through to the report
        # -- the value itself is an arbitrary test placeholder, not a claim
        # about any real station code.
        Observation(
            obs_id="mpc_2", ra_deg=250.0, dec_deg=-13.0, jd=2458385.0,
            mag=19.8, mag_err=0.1, filter_band="?", mission="MPC",
            field_id="TEST_STN",
        ),
    ]


def test_run_lookup_filters_to_archive_window(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_observations()):
        report = lookup_mpc_observation_history.run_lookup("72966", 2458273.5, tmp_path)
    assert report["n_total_reports"] == 3
    assert report["n_reports_in_archive_window"] == 2
    nights = [r["night_yyyymmdd"] for r in report["reports_in_archive_window"]]
    assert "20180809" in nights


def test_run_lookup_surfaces_reporting_observatory(tmp_path):
    """The real reporting-observatory/station code must flow through to the
    report so callers can filter observation history to a specific
    station's reports before selecting a candidate pair."""
    with patch("fetch.fetch_mpc_observations", return_value=_fake_observations()):
        report = lookup_mpc_observation_history.run_lookup("72966", 2458273.5, tmp_path)
    by_jd = {r["jd"]: r["observatory"] for r in report["reports_in_archive_window"]}
    assert by_jd[2458385.0] == "TEST_STN"
    # The 20180809 fixture observation never set field_id, so it must
    # surface as None, not silently fall back to a guessed value.
    assert by_jd[2458339.6521991] is None


def test_run_lookup_resumes_without_network_call(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_observations()) as mock_fetch:
        lookup_mpc_observation_history.run_lookup("72966", 2458273.5, tmp_path)
        assert mock_fetch.call_count == 1

        report = lookup_mpc_observation_history.run_lookup("72966", 2458273.5, tmp_path)
        assert mock_fetch.call_count == 1
    assert report["n_total_reports"] == 3


def test_run_lookup_force_refresh_bypasses_checkpoint(tmp_path):
    """force_refresh must re-fetch even when a checkpoint already exists --
    needed after a code change adds a new report field (e.g. v0.90.53's
    observatory field) that a stale checkpoint predates."""
    with patch("fetch.fetch_mpc_observations", return_value=_fake_observations()) as mock_fetch:
        lookup_mpc_observation_history.run_lookup("72966", 2458273.5, tmp_path)
        assert mock_fetch.call_count == 1

        lookup_mpc_observation_history.run_lookup(
            "72966", 2458273.5, tmp_path, force_refresh=True
        )
        assert mock_fetch.call_count == 2
        # The underlying fetch must also be told to bypass its own disk cache.
        assert mock_fetch.call_args.kwargs["force_refresh"] is True


def test_fetch_mpc_with_retry_recovers_after_transient_failure():
    with patch("time.sleep"):
        with patch(
            "fetch.fetch_mpc_observations",
            side_effect=[ConnectionError("boom"), _fake_observations()],
        ):
            result = lookup_mpc_observation_history._fetch_mpc_with_retry("72966")
    assert len(result) == 3


def test_fetch_mpc_with_retry_raises_after_exhausting_attempts():
    with patch("time.sleep"):
        with patch("fetch.fetch_mpc_observations", side_effect=ConnectionError("still down")):
            try:
                lookup_mpc_observation_history._fetch_mpc_with_retry("72966")
                raise AssertionError("expected RuntimeError")
            except RuntimeError as exc:
                assert "failed after 5 attempts" in str(exc)


def test_night_date_matches_known_real_archive_night(tmp_path):
    """Regression coverage for the same JD noon/midnight trap fixed in
    v0.90.39 -- reuses the exact real obsjd confirmed to originate in
    ztf_public_20180809.tar.gz."""
    with patch("fetch.fetch_mpc_observations", return_value=_fake_observations()):
        report = lookup_mpc_observation_history.run_lookup("72966", 2458273.5, tmp_path)
    matching = [r for r in report["reports_in_archive_window"] if r["jd"] == 2458339.6521991]
    assert len(matching) == 1
    assert matching[0]["night_yyyymmdd"] == "20180809"
