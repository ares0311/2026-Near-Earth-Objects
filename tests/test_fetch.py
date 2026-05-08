"""Tests for fetch.py — cache round-trip and fallback behaviour."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

import fetch as fetch_mod
from fetch import (
    _fetch_ztf_irsa_api,
    _load_cache,
    _parse_atlas_photometry,
    _save_cache,
    _ztf_filter_id,
    fetch,
    fetch_horizons,
    fetch_mpc_known,
    fetch_ztf,
)
from schemas import Observation


class TestCacheRoundTrip:
    def test_save_and_load(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        key = "test_key_001"
        obs = Observation(
            obs_id="c_001",
            ra_deg=180.0,
            dec_deg=10.0,
            jd=2460000.5,
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        )
        data = [obs.model_dump()]
        _save_cache(key, data)
        loaded = _load_cache(key)
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0]["obs_id"] == "c_001"

    def test_missing_key_returns_none(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = _load_cache("nonexistent_key_xyz")
        assert result is None

    def test_cache_creates_directory(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        cache_dir = tmp_path / "new_cache_dir"
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", cache_dir)

        assert not cache_dir.exists()
        _save_cache("k", [{"test": 1}])
        assert cache_dir.exists()

    def test_roundtrip_preserves_all_fields(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = Observation(
            obs_id="full_obs",
            ra_deg=123.456,
            dec_deg=-45.678,
            jd=2460100.0,
            mag=20.1,
            mag_err=0.08,
            filter_band="g",
            mission="ATLAS",
            real_bogus=0.85,
        )
        _save_cache("full", [obs.model_dump()])
        loaded = _load_cache("full")
        assert loaded is not None
        restored = Observation(**loaded[0])
        assert restored.obs_id == obs.obs_id
        assert restored.ra_deg == pytest.approx(obs.ra_deg)
        assert restored.real_bogus == pytest.approx(0.85)


class TestZtfFilterId:
    def test_g_band(self):
        assert _ztf_filter_id(1) == "g"

    def test_r_band(self):
        assert _ztf_filter_id(2) == "r"

    def test_i_band(self):
        assert _ztf_filter_id(3) == "i"

    def test_unknown(self):
        assert _ztf_filter_id(99) == "?"


class TestParseAtlasPhotometry:
    def test_with_header(self):
        lines = [
            "#MJD F m dm RA Dec",
            "60000.0 o 18.5 0.1 180.0 10.0",
            "60001.0 c 19.0 0.1 180.1 10.1",
        ]
        obs = _parse_atlas_photometry(lines)
        assert len(obs) == 2
        assert obs[0].filter_band == "o"
        assert obs[0].mission == "ATLAS"

    def test_skip_empty_lines(self):
        lines = [
            "#MJD F m dm RA Dec",
            "60000.0 o 18.5 0.1 180.0 10.0",
            "",
            "60001.0 c 19.0 0.1 180.1 10.1",
        ]
        obs = _parse_atlas_photometry(lines)
        assert len(obs) == 2

    def test_empty_input(self):
        obs = _parse_atlas_photometry([])
        assert obs == []


class TestFetchZtfCached:
    def test_returns_from_cache(self, tmp_path, monkeypatch):
        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = Observation(
            obs_id="ztf_cached",
            ra_deg=180.0,
            dec_deg=10.0,
            jd=2460000.5,
            mag=19.5,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        )
        import hashlib

        cache_key = hashlib.md5(
            b"ztf_180.0_10.0_1.0_2460000.0_2460010.0"
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch_ztf(180.0, 10.0, 1.0, 2460000.0, 2460010.0)
        assert len(result) == 1
        assert result[0].obs_id == "ztf_cached"


class TestFetchZtfIrsaApi:
    def test_parses_irsa_response(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "metadata": [
                {"name": "candid"}, {"name": "ra"}, {"name": "dec"},
                {"name": "jd"}, {"name": "magpsf"}, {"name": "sigmapsf"},
                {"name": "fid"}, {"name": "rb"},
            ],
            "data": [
                ["123456", 180.0, 10.0, 2460005.0, 19.5, 0.05, 2, 0.9],
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            obs = _fetch_ztf_irsa_api(180.0, 10.0, 1.0, 2460000.0, 2460010.0)

        assert len(obs) == 1
        assert obs[0].filter_band == "r"
        assert obs[0].real_bogus == pytest.approx(0.9)

    def test_parses_irsa_response_with_drb(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "metadata": [
                {"name": "candid"}, {"name": "ra"}, {"name": "dec"},
                {"name": "jd"}, {"name": "magpsf"}, {"name": "sigmapsf"},
                {"name": "fid"}, {"name": "rb"}, {"name": "drb"},
            ],
            "data": [
                ["789", 181.0, 11.0, 2460006.0, 20.0, 0.1, 1, 0.85, 0.95],
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            obs = _fetch_ztf_irsa_api(181.0, 11.0, 1.0, 2460000.0, 2460010.0)

        assert len(obs) == 1
        assert obs[0].deep_real_bogus == pytest.approx(0.95)
        assert obs[0].filter_band == "g"


class TestFetchZtfIrsaFallback:
    """Test fetch_ztf falls back to IRSA API when ztfquery not installed."""

    def test_irsa_fallback_when_no_ztfquery(self, tmp_path, monkeypatch):
        import sys

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "metadata": [
                {"name": "candid"}, {"name": "ra"}, {"name": "dec"},
                {"name": "jd"}, {"name": "magpsf"}, {"name": "sigmapsf"},
                {"name": "fid"},
            ],
            "data": [
                ["789", 180.5, 10.5, 2460003.0, 20.0, 0.1, 1],
            ],
        }
        mock_response.raise_for_status = MagicMock()

        # Block ztfquery import
        monkeypatch.setitem(sys.modules, "ztfquery.query", None)

        with patch("requests.get", return_value=mock_response):
            result = fetch_mod.fetch_ztf(180.0, 10.0, 1.0, 2460000.0, 2460010.0)

        assert len(result) == 1
        assert result[0].filter_band == "g"


class TestParseAtlasPhotometryNoHeader:
    def test_no_header_uses_first_col_as_mjd(self):
        lines = ["60000.5 o 19.0 0.1 180.0 10.0"]
        obs = _parse_atlas_photometry(lines)
        assert len(obs) == 1

    def test_skip_comment_lines_in_data(self):
        lines = [
            "#MJD F m dm RA Dec",
            "# comment line",
            "60000.0 o 18.5 0.1 180.0 10.0",
        ]
        obs = _parse_atlas_photometry(lines)
        assert len(obs) == 1


def _make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="f_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460005.0,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
    )
    defaults.update(kwargs)
    return Observation(**defaults)


class TestFetchAtlasCached:
    def test_returns_from_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = _make_obs(obs_id="atlas_cached", mission="ATLAS", filter_band="o")
        cache_key = hashlib.md5(
            b"atlas_180.0_10.0_1.0_2460000.0_2460010.0"
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        from fetch import fetch_atlas
        result = fetch_atlas(180.0, 10.0, 1.0, 2460000.0, 2460010.0)
        assert len(result) == 1
        assert result[0].obs_id == "atlas_cached"

    def test_empty_cache_returns_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        cache_key = hashlib.md5(
            b"atlas_180.0_10.0_1.0_2460000.0_2460010.0"
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [])
        from fetch import fetch_atlas
        result = fetch_atlas(180.0, 10.0, 1.0, 2460000.0, 2460010.0)
        assert result == []

    def test_network_path_no_result_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake-task/1/"}
        queue_resp.raise_for_status = MagicMock()

        poll_resp = MagicMock()
        poll_resp.json.return_value = {"finishtimestamp": "2024-01-01", "result_url": ""}
        poll_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=queue_resp):
            with patch("requests.get", return_value=poll_resp):
                from fetch import fetch_atlas
                result = fetch_atlas(90.0, 0.0, 0.5, 2460000.0, 2460010.0)
        assert result == []


class TestFetchMpcKnownCached:
    def test_returns_from_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = _make_obs(obs_id="mpc_Ceres", mission="MPC", filter_band="V", mag=7.0)
        cache_key = hashlib.md5(b"mpc_180.0_10.0_1.0").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch_mpc_known(180.0, 10.0, 1.0)
        assert len(result) == 1
        assert result[0].obs_id == "mpc_Ceres"

    def test_empty_cache_returns_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        cache_key = hashlib.md5(b"mpc_180.0_10.0_1.0").hexdigest()
        fetch_mod._save_cache(cache_key, [])
        result = fetch_mpc_known(180.0, 10.0, 1.0)
        assert result == []


class TestFetchHorizonsCached:
    def test_returns_from_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = _make_obs(obs_id="horizons_433_2460000.0000", mission="MPC", filter_band="V")
        cache_key = hashlib.md5(b"horizons_433_2460000.0_2460010.0_1h").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch_horizons("433", 181.0, 5.0, 2460000.0, 2460010.0)
        assert len(result) == 1
        assert result[0].obs_id == "horizons_433_2460000.0000"

    def test_empty_cache_returns_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        cache_key = hashlib.md5(b"horizons_433_2460000.0_2460010.0_1h").hexdigest()
        fetch_mod._save_cache(cache_key, [])
        result = fetch_horizons("433", 181.0, 5.0, 2460000.0, 2460010.0)
        assert result == []


class TestFetchTopLevel:
    def test_fetch_no_network_ztf_cached(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = _make_obs(obs_id="top_cached")
        cache_key = hashlib.md5(
            b"ztf_180.0_10.0_1.0_2460000.0_2460010.0"
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch(180.0, 10.0, 1.0, 2460000.0, 2460010.0, surveys=("ZTF",))
        assert len(result.alerts) == 1
        assert result.provenance.surveys == ("ZTF",)

    def test_fetch_empty_surveys(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fetch(180.0, 10.0, 1.0, 2460000.0, 2460010.0, surveys=())
        assert len(result.alerts) == 0

    def test_fetch_with_mpc_survey_cached(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = _make_obs(obs_id="mpc_001", mission="MPC", filter_band="V")
        cache_key = hashlib.md5(b"mpc_180.0_10.0_1.0").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch(180.0, 10.0, 1.0, 2460000.0, 2460010.0, surveys=("MPC",))
        assert len(result.alerts) == 1

    def test_fetch_with_atlas_survey_cached(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = _make_obs(obs_id="atlas_001", mission="ATLAS", filter_band="o")
        cache_key = hashlib.md5(
            b"atlas_180.0_10.0_1.0_2460000.0_2460010.0"
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch(180.0, 10.0, 1.0, 2460000.0, 2460010.0, surveys=("ATLAS",))
        assert len(result.alerts) == 1

    def test_fetch_provenance_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fetch(90.0, -30.0, 0.5, 2460000.0, 2460005.0, surveys=())
        prov = result.provenance
        assert prov.search_ra_deg == pytest.approx(90.0)
        assert prov.search_dec_deg == pytest.approx(-30.0)
        assert prov.start_jd == pytest.approx(2460000.0)
        assert prov.end_jd == pytest.approx(2460005.0)
