"""Tests for Skills/lookup_neo_archive_ephemeris.py (Gate Z3 targeted
candidate-night lookup). fetch_horizons is mocked -- this project's
standing convention for external-service tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "lookup_neo_archive_ephemeris.py"
)
_spec = importlib.util.spec_from_file_location("lookup_neo_archive_ephemeris", _MODULE_PATH)
lookup_neo_archive_ephemeris = importlib.util.module_from_spec(_spec)
sys.modules["lookup_neo_archive_ephemeris"] = lookup_neo_archive_ephemeris
_spec.loader.exec_module(lookup_neo_archive_ephemeris)

from schemas import Observation  # noqa: E402


def _fake_observations():
    return [
        Observation(
            obs_id="horizons_72966_2458339.5000",
            ra_deg=232.6, dec_deg=-8.4, jd=2458339.6521991,
            mag=19.5, mag_err=0.0, filter_band="V", mission="MPC",
        ),
        Observation(
            obs_id="horizons_72966_2458363.6000",
            # 2458339.5 (night 20180809 midnight UTC) + 24 days = 2458363.5
            # (night 20180902 midnight UTC); +0.1 keeps it within the same
            # UTC calendar day rather than landing exactly on the boundary.
            ra_deg=210.1, dec_deg=-5.2, jd=2458363.6,
            mag=19.7, mag_err=0.0, filter_band="V", mission="MPC",
        ),
    ]


def test_run_lookup_writes_report_with_correct_night_dates(tmp_path):
    with patch("fetch.fetch_horizons", return_value=_fake_observations()):
        report = lookup_neo_archive_ephemeris.run_lookup(
            "72966", 2458339.5, 2458439.5, "1d", tmp_path
        )
    assert report["n_points"] == 2
    # The exact real jd (2458339.6521991) already confirmed to originate in
    # ztf_public_20180809.tar.gz must map to "20180809", not "20180808" --
    # regression coverage for the same JD noon/midnight trap fixed upstream.
    assert report["rows"][0]["night_yyyymmdd"] == "20180809"
    assert report["rows"][1]["night_yyyymmdd"] == "20180902"


def test_run_lookup_resumes_without_network_call(tmp_path):
    with patch("fetch.fetch_horizons", return_value=_fake_observations()) as mock_fetch:
        lookup_neo_archive_ephemeris.run_lookup("72966", 2458339.5, 2458439.5, "1d", tmp_path)
        assert mock_fetch.call_count == 1

        report = lookup_neo_archive_ephemeris.run_lookup(
            "72966", 2458339.5, 2458439.5, "1d", tmp_path
        )
        assert mock_fetch.call_count == 1
    assert report["n_points"] == 2


def test_fetch_horizons_with_retry_recovers_after_transient_failure():
    with patch("time.sleep"):
        with patch(
            "fetch.fetch_horizons",
            side_effect=[ConnectionError("boom"), _fake_observations()],
        ):
            result = lookup_neo_archive_ephemeris._fetch_horizons_with_retry(
                "72966", 2458339.5, 2458439.5, "1d"
            )
    assert len(result) == 2


def test_fetch_horizons_with_retry_raises_after_exhausting_attempts():
    with patch("time.sleep"):
        with patch("fetch.fetch_horizons", side_effect=ConnectionError("still down")):
            try:
                lookup_neo_archive_ephemeris._fetch_horizons_with_retry(
                    "72966", 2458339.5, 2458439.5, "1d"
                )
                raise AssertionError("expected RuntimeError")
            except RuntimeError as exc:
                assert "failed after 5 attempts" in str(exc)
