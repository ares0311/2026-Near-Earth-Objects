"""Tests for fetch.py — cache round-trip and fallback behaviour."""

import hashlib
import sys
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
    fetch_batch,
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

    def test_atlas_token_sets_auth_header(self, tmp_path, monkeypatch):
        # atlas_token → line 180: headers["Authorization"] = f"Token ..."
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake-task/1/"}
        queue_resp.raise_for_status = MagicMock()
        poll_resp = MagicMock()
        poll_resp.json.return_value = {"finishtimestamp": "2024-01-01", "result_url": ""}
        poll_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=queue_resp) as mock_post:
            with patch("requests.get", return_value=poll_resp):
                from fetch import fetch_atlas
                fetch_atlas(90.0, 0.0, 0.5, 2460000.0, 2460010.0, atlas_token="my_secret")
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"].get("Authorization") == "Token my_secret"

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


class TestFetchZtfQuery:
    """Cover lines 64-73 (ztfquery path) and 83-102 (_parse_ztf_metatable)."""

    def _make_mock_row(self, **kwargs):
        """Return a dict-like row for _parse_ztf_metatable."""
        defaults = {
            "pid": "111", "ra": 180.0, "dec": 10.0, "obsjd": 2460005.0,
            "magpsf": 19.5, "sigmapsf": 0.05, "fid": 2, "rb": 0.9, "drb": 0.95,
        }
        defaults.update(kwargs)
        return defaults

    def _make_mock_meta(self, rows):
        """Fake a pandas DataFrame with iterrows()."""
        mock_df = MagicMock()
        mock_df.iterrows.return_value = iter(enumerate(rows))
        return mock_df

    def test_ztfquery_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        row = self._make_mock_row()
        mock_meta = self._make_mock_meta([row])

        mock_zquery = MagicMock()
        mock_zquery.metatable = mock_meta
        mock_zq_module = MagicMock()
        mock_zq_module.ZTFQuery.return_value = mock_zquery

        # Python resolves `import ztfquery.query as zq` via parent.query attribute
        mock_ztfquery_pkg = MagicMock()
        mock_ztfquery_pkg.query = mock_zq_module
        mock_pd = MagicMock()

        with patch.dict(sys.modules, {
            "ztfquery": mock_ztfquery_pkg,
            "ztfquery.query": mock_zq_module,
            "pandas": mock_pd,
        }):
            result = fetch_mod.fetch_ztf(180.0, 10.0, 1.0, 2460000.0, 2460010.0)
        assert len(result) == 1
        assert result[0].filter_band == "r"
        assert result[0].real_bogus == pytest.approx(0.9)

    def test_parse_ztf_metatable_no_rb(self):
        import sys

        from fetch import _parse_ztf_metatable

        row = {
            "candid": "999", "ra": 181.0, "dec": 11.0, "obsjd": 2460006.0,
            "mag": 20.0, "sigmapsf": 0.1, "fid": 1,
        }
        mock_meta = MagicMock()
        mock_meta.iterrows.return_value = iter([(0, row)])
        mock_pd = MagicMock()
        with patch.dict(sys.modules, {"pandas": mock_pd}):
            obs = _parse_ztf_metatable(mock_meta)
        assert len(obs) == 1
        assert obs[0].real_bogus is None
        assert obs[0].filter_band == "g"


class TestFetchAtlasResultUrl:
    """Cover lines 206-211 (ATLAS result_url path)."""

    def test_network_path_with_result_url(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake-task/1/"}
        queue_resp.raise_for_status = MagicMock()

        poll_resp = MagicMock()
        poll_resp.json.return_value = {
            "finishtimestamp": "2024-01-01",
            "result_url": "http://fake-result/data.txt",
        }
        poll_resp.raise_for_status = MagicMock()

        data_resp = MagicMock()
        data_resp.text = "#MJD F m dm RA Dec\n60000.0 o 18.5 0.1 180.0 10.0"
        data_resp.raise_for_status = MagicMock()

        def mock_get(url, **kwargs):
            if "result" in url:
                return data_resp
            return poll_resp

        with patch("requests.post", return_value=queue_resp):
            with patch("requests.get", side_effect=mock_get):
                from fetch import fetch_atlas
                result = fetch_atlas(90.0, 0.0, 0.5, 2460000.0, 2460010.0)
        assert len(result) == 1
        assert result[0].filter_band == "o"


class TestFetchMpcKnownNetwork:
    """Cover lines 269-293 (astroquery.mpc path in fetch_mpc_known)."""

    def test_mpc_query_with_rows(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_row = {"designation": "Ceres", "RA": 180.0, "Dec": 10.0,
                    "epoch": 2460000.0, "H": 3.4}
        mock_result = [mock_row]

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects_in_region.return_value = mock_result
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fm.fetch_mpc_known(180.0, 10.0, 1.0)
        assert len(result) == 1
        assert result[0].obs_id == "mpc_Ceres"

    def test_mpc_query_returns_none(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects_in_region.return_value = None
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fm.fetch_mpc_known(181.0, 11.0, 0.5)
        assert result == []


class TestFetchHorizonsNetwork:
    """Cover lines 319-345 (astroquery.jplhorizons path in fetch_horizons)."""

    def test_horizons_query(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_row = {
            "RA": 180.0, "DEC": 10.0,
            "datetime_jd": 2460005.0, "V": 19.0,
        }
        mock_eph = [mock_row]

        mock_horizons_inst = MagicMock()
        mock_horizons_inst.ephemerides.return_value = mock_eph
        mock_horizons_cls = MagicMock(return_value=mock_horizons_inst)
        mock_jpl_mod = MagicMock()
        mock_jpl_mod.Horizons = mock_horizons_cls

        mock_time_cls = MagicMock()
        mock_time_cls.return_value.iso = "2024-01-01 00:00:00"
        mock_astropy_time = MagicMock()
        mock_astropy_time.Time = mock_time_cls

        monkeypatch.setitem(sys.modules, "astroquery.jplhorizons", mock_jpl_mod)
        monkeypatch.setitem(sys.modules, "astropy.time", mock_astropy_time)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fm.fetch_horizons("433", 180.0, 10.0, 2460000.0, 2460010.0)
        assert len(result) == 1
        assert result[0].jd == pytest.approx(2460005.0)
        assert result[0].filter_band == "V"


class TestForceRefresh:
    """Tests for force_refresh=True parameter in fetch, fetch_ztf, fetch_atlas."""

    def test_force_refresh_bypasses_ztf_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        # Seed cache with one observation
        obs = _make_obs(obs_id="stale_ztf")
        cache_key = hashlib.md5(b"ztf_180.0_10.0_1.0_2460000.0_2460010.0").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        # force_refresh=True → ignore cache, call IRSA API (mock returns 0 rows)
        mock_response = MagicMock()
        mock_response.json.return_value = {"metadata": [], "data": []}
        mock_response.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_response):
            result = fetch_mod.fetch_ztf(180.0, 10.0, 1.0, 2460000.0, 2460010.0,
                                          force_refresh=True)
        assert len(result) == 0

    def test_load_cache_force_refresh_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        fetch_mod._save_cache("k", [{"x": 1}])
        assert fetch_mod._load_cache("k", force_refresh=False) is not None
        assert fetch_mod._load_cache("k", force_refresh=True) is None

    def test_force_refresh_atlas(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)

        obs = _make_obs(obs_id="stale_atlas", mission="ATLAS", filter_band="o")
        cache_key = hashlib.md5(b"atlas_90.0_0.0_0.5_2460000.0_2460010.0").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake/1/"}
        queue_resp.raise_for_status = MagicMock()
        poll_resp = MagicMock()
        poll_resp.json.return_value = {"finishtimestamp": "2024-01-01", "result_url": ""}
        poll_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=queue_resp):
            with patch("requests.get", return_value=poll_resp):
                result = fetch_mod.fetch_atlas(90.0, 0.0, 0.5, 2460000.0, 2460010.0,
                                               force_refresh=True)
        assert result == []  # stale cache bypassed; no result_url → empty

    def test_force_refresh_top_level_fetch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = _make_obs(obs_id="stale_top")
        cache_key = hashlib.md5(b"ztf_180.0_10.0_1.0_2460000.0_2460010.0").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        mock_response = MagicMock()
        mock_response.json.return_value = {"metadata": [], "data": []}
        mock_response.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_response):
            result = fetch_mod.fetch(180.0, 10.0, 1.0, 2460000.0, 2460010.0,
                                     surveys=("ZTF",), force_refresh=True)
        assert len(result.alerts) == 0


class TestAtlasTokenEnvVar:
    """Tests for ATLAS_TOKEN environment variable fallback."""

    def test_env_var_used_when_no_explicit_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)
        monkeypatch.setenv("ATLAS_TOKEN", "env_token_123")

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake/1/"}
        queue_resp.raise_for_status = MagicMock()
        poll_resp = MagicMock()
        poll_resp.json.return_value = {"finishtimestamp": "2024-01-01", "result_url": ""}
        poll_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=queue_resp) as mock_post:
            with patch("requests.get", return_value=poll_resp):
                fetch_mod.fetch_atlas(10.0, 5.0, 0.5, 2460000.0, 2460005.0)
        assert mock_post.call_args[1]["headers"].get("Authorization") == "Token env_token_123"

    def test_explicit_token_overrides_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)
        monkeypatch.setenv("ATLAS_TOKEN", "env_token")

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake/1/"}
        queue_resp.raise_for_status = MagicMock()
        poll_resp = MagicMock()
        poll_resp.json.return_value = {"finishtimestamp": "2024-01-01", "result_url": ""}
        poll_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=queue_resp) as mock_post:
            with patch("requests.get", return_value=poll_resp):
                fetch_mod.fetch_atlas(10.0, 5.0, 0.5, 2460000.0, 2460005.0,
                                      atlas_token="explicit_token")
        assert mock_post.call_args[1]["headers"].get("Authorization") == "Token explicit_token"


class TestFetchBatch:
    """Tests for fetch_batch."""

    def _mock_fetch(self, monkeypatch, tmp_path):
        """Patch _CACHE_DIR and requests.get to avoid real network calls."""
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": []}
        return mock_resp

    def test_returns_one_result_per_target(self, tmp_path, monkeypatch):
        mock_resp = self._mock_fetch(monkeypatch, tmp_path)
        with patch("requests.get", return_value=mock_resp):
            targets = [(180.0, 0.0), (90.0, 45.0), (270.0, -30.0)]
            results = fetch_batch(targets, radius_deg=0.5, start_jd=2460000.0, end_jd=2460001.0)
        assert len(results) == 3

    def test_empty_targets_returns_empty(self, tmp_path, monkeypatch):
        self._mock_fetch(monkeypatch, tmp_path)
        results = fetch_batch([], radius_deg=0.5, start_jd=2460000.0, end_jd=2460001.0)
        assert results == []

    def test_provenance_reflects_each_target(self, tmp_path, monkeypatch):
        mock_resp = self._mock_fetch(monkeypatch, tmp_path)
        with patch("requests.get", return_value=mock_resp):
            targets = [(10.0, 5.0), (20.0, -5.0)]
            results = fetch_batch(targets, radius_deg=0.5, start_jd=2460000.0, end_jd=2460001.0)
        assert results[0].provenance.search_ra_deg == pytest.approx(10.0)
        assert results[1].provenance.search_ra_deg == pytest.approx(20.0)

    def test_force_refresh_propagated(self, tmp_path, monkeypatch):
        mock_resp = self._mock_fetch(monkeypatch, tmp_path)
        calls = []
        original_fetch = fetch_mod.fetch

        def capturing_fetch(*args, **kwargs):
            calls.append(kwargs.get("force_refresh"))
            return original_fetch(*args, **kwargs)

        monkeypatch.setattr(fetch_mod, "fetch", capturing_fetch)
        with patch("requests.get", return_value=mock_resp):
            fetch_batch([(180.0, 0.0)], radius_deg=0.5, start_jd=2460000.0,
                        end_jd=2460001.0, force_refresh=True)
        assert calls == [True]


@pytest.mark.integration_live
class TestFetchZtfLive:
    """Live integration tests — require network access; excluded from CI."""

    def test_fetch_ztf_live_small_region(self):
        result = fetch_ztf(180.0, 0.0, 0.1, 2460000.0, 2460001.0)
        assert isinstance(result, list)

    def test_fetch_atlas_live_small_region(self):
        from fetch import fetch_atlas
        result = fetch_atlas(180.0, 0.0, 0.1, 2460000.0, 2460001.0)
        assert isinstance(result, list)


class TestEstimateLimitingMagnitude:
    def _make_fetch_result(self, mags):
        from schemas import FetchProvenance, FetchResult, Observation
        obs = tuple(
            Observation(
                obs_id=f"lm{i}",
                ra_deg=180.0,
                dec_deg=10.0,
                jd=2460000.5 + i * 0.1,
                mag=m,
                mag_err=0.05,
                filter_band="r",
                mission="ZTF",
            )
            for i, m in enumerate(mags)
        )
        prov = FetchProvenance(surveys=("ZTF",), start_jd=2460000.0, end_jd=2460001.0)
        return FetchResult(alerts=obs, provenance=prov)

    def test_returns_none_for_fewer_than_5_obs(self):
        from fetch import estimate_limiting_magnitude
        fr = self._make_fetch_result([18.0, 19.0, 20.0, 21.0])
        assert estimate_limiting_magnitude(fr) is None

    def test_returns_float_for_sufficient_obs(self):
        from fetch import estimate_limiting_magnitude
        mags = list(range(15, 25))  # 10 observations
        fr = self._make_fetch_result(mags)
        result = estimate_limiting_magnitude(fr)
        assert result is not None
        assert isinstance(result, float)

    def test_result_in_faint_end_range(self):
        from fetch import estimate_limiting_magnitude
        mags = list(range(15, 25))
        fr = self._make_fetch_result(mags)
        result = estimate_limiting_magnitude(fr)
        # Should be near the faint end (90th-99th percentile of 15-24 = ~23)
        assert result >= 20.0

    def test_filters_out_extreme_magnitudes(self):
        from fetch import estimate_limiting_magnitude
        # Include some out-of-range magnitudes that should be ignored
        mags = [5.0, 10.0] + list(range(18, 28)) + [99.0]
        fr = self._make_fetch_result(mags)
        result = estimate_limiting_magnitude(fr)
        assert result is not None
        assert 10.0 < result < 35.0

    def test_empty_alerts_returns_none(self):
        from fetch import estimate_limiting_magnitude
        fr = self._make_fetch_result([])
        assert estimate_limiting_magnitude(fr) is None


class TestSummariseFetchResult:
    def _make_fetch_result(self, n_alerts: int = 3):
        from schemas import FetchProvenance, FetchResult

        from .conftest import build_observation
        alerts = tuple(
            build_observation(obs_id=f"a{i}", jd=2460000.5 + i)
            for i in range(n_alerts)
        )
        prov = FetchProvenance(
            surveys=("ZTF",),
            start_jd=2460000.0,
            end_jd=2460001.0,
            search_ra_deg=180.0,
            search_dec_deg=10.0,
            search_radius_deg=0.5,
        )
        return FetchResult(alerts=alerts, provenance=prov)

    def test_returns_dict(self):
        from fetch import summarise_fetch_result
        fr = self._make_fetch_result()
        result = summarise_fetch_result(fr)
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        from fetch import summarise_fetch_result
        fr = self._make_fetch_result()
        result = summarise_fetch_result(fr)
        for key in ("n_alerts", "surveys", "search_ra_deg", "search_dec_deg",
                    "search_radius_deg", "start_jd", "end_jd", "limiting_magnitude"):
            assert key in result, f"missing key: {key}"

    def test_n_alerts_correct(self):
        from fetch import summarise_fetch_result
        fr = self._make_fetch_result(n_alerts=5)
        result = summarise_fetch_result(fr)
        assert result["n_alerts"] == 5

    def test_surveys_is_list(self):
        from fetch import summarise_fetch_result
        fr = self._make_fetch_result()
        result = summarise_fetch_result(fr)
        assert isinstance(result["surveys"], list)
        assert "ZTF" in result["surveys"]

    def test_start_jd_matches_provenance(self):
        from fetch import summarise_fetch_result
        fr = self._make_fetch_result()
        result = summarise_fetch_result(fr)
        assert result["start_jd"] == 2460000.0

    def test_invalid_input_raises(self):
        import pytest

        from fetch import summarise_fetch_result
        with pytest.raises(TypeError):
            summarise_fetch_result({"not": "a FetchResult"})  # type: ignore[arg-type]


class TestMergeSurveyAlerts:
    def _make_fetch_result(self, survey: str = "ZTF", n_alerts: int = 2, id_prefix: str = "a"):
        from schemas import FetchProvenance, FetchResult

        from .conftest import build_observation
        alerts = tuple(
            build_observation(obs_id=f"{id_prefix}{i}", jd=2460000.5 + i)
            for i in range(n_alerts)
        )
        prov = FetchProvenance(
            surveys=(survey,),
            start_jd=2460000.0,
            end_jd=2460001.0,
        )
        return FetchResult(alerts=alerts, provenance=prov)

    def test_returns_fetch_result(self):
        from fetch import merge_survey_alerts
        from schemas import FetchResult
        r1 = self._make_fetch_result("ZTF", 2, "a")
        result = merge_survey_alerts([r1])
        assert isinstance(result, FetchResult)

    def test_empty_list_returns_empty(self):
        from fetch import merge_survey_alerts
        result = merge_survey_alerts([])
        assert len(result.alerts) == 0

    def test_deduplicates_obs_ids(self):
        from fetch import merge_survey_alerts
        r1 = self._make_fetch_result("ZTF", 3, "a")
        r2 = self._make_fetch_result("ZTF", 3, "a")  # same IDs
        result = merge_survey_alerts([r1, r2])
        assert len(result.alerts) == 3  # deduplicated

    def test_merges_different_surveys(self):
        from fetch import merge_survey_alerts
        r1 = self._make_fetch_result("ZTF", 2, "z")
        r2 = self._make_fetch_result("ATLAS", 2, "at")
        result = merge_survey_alerts([r1, r2])
        assert len(result.alerts) == 4

    def test_unique_surveys_in_provenance(self):
        from fetch import merge_survey_alerts
        r1 = self._make_fetch_result("ZTF", 1, "z")
        r2 = self._make_fetch_result("ZTF", 1, "zz")
        result = merge_survey_alerts([r1, r2])
        surveys = list(result.provenance.surveys)
        assert surveys.count("ZTF") == 1

    def test_jd_range_widened(self):
        from fetch import merge_survey_alerts
        from schemas import FetchProvenance, FetchResult

        prov1 = FetchProvenance(surveys=("ZTF",), start_jd=2460000.0, end_jd=2460001.0)
        prov2 = FetchProvenance(surveys=("ATLAS",), start_jd=2459999.0, end_jd=2460002.0)
        r1 = FetchResult(alerts=(), provenance=prov1)
        r2 = FetchResult(alerts=(), provenance=prov2)
        result = merge_survey_alerts([r1, r2])
        assert result.provenance.start_jd == pytest.approx(2459999.0)
        assert result.provenance.end_jd == pytest.approx(2460002.0)

    def test_non_overlapping_alerts_all_kept(self):
        from fetch import merge_survey_alerts
        r1 = self._make_fetch_result("ZTF", 3, "aaa")
        r2 = self._make_fetch_result("ATLAS", 3, "bbb")
        result = merge_survey_alerts([r1, r2])
        assert len(result.alerts) == 6


class TestFilterAlertsByMotion:
    def _make_obs(self, obs_id: str, ssdistnr: float | None = None) -> object:
        from schemas import Observation

        kwargs = dict(
            obs_id=obs_id,
            ra_deg=180.0,
            dec_deg=0.0,
            jd=2460000.5,
            mag=19.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        )
        obs = Observation(**kwargs)
        if ssdistnr is not None:
            object.__setattr__(obs, "ssdistnr", ssdistnr)
        return obs

    def test_no_ssdistnr_passes_through(self):
        from fetch import filter_alerts_by_motion
        from schemas import Observation

        obs = Observation(
            obs_id="a",
            ra_deg=180.0,
            dec_deg=0.0,
            jd=2460000.5,
            mag=19.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        )
        result = filter_alerts_by_motion((obs,))
        assert len(result) == 1

    def test_empty_input(self):
        from fetch import filter_alerts_by_motion

        result = filter_alerts_by_motion(())
        assert result == ()

    def test_returns_tuple(self):
        from fetch import filter_alerts_by_motion
        from schemas import Observation

        obs = Observation(
            obs_id="b",
            ra_deg=10.0,
            dec_deg=5.0,
            jd=2460001.0,
            mag=20.0,
            mag_err=0.1,
            filter_band="g",
            mission="ZTF",
        )
        result = filter_alerts_by_motion((obs,))
        assert isinstance(result, tuple)

    def test_default_range_includes_no_ssdistnr(self):
        from fetch import filter_alerts_by_motion
        from schemas import Observation

        obs = Observation(
            obs_id="c",
            ra_deg=90.0,
            dec_deg=10.0,
            jd=2460002.0,
            mag=18.0,
            mag_err=0.03,
            filter_band="r",
            mission="ATLAS",
        )
        result = filter_alerts_by_motion((obs,))
        assert obs in result

    def test_min_rate_zero_by_default(self):
        from fetch import filter_alerts_by_motion
        from schemas import Observation

        obs = Observation(
            obs_id="d",
            ra_deg=270.0,
            dec_deg=-5.0,
            jd=2460003.0,
            mag=21.0,
            mag_err=0.2,
            filter_band="i",
            mission="ZTF",
        )
        result = filter_alerts_by_motion((obs,), min_rate_arcsec_hr=0.0)
        assert isinstance(result, tuple)

    def test_multiple_obs_all_returned_without_ssdistnr(self):
        from fetch import filter_alerts_by_motion
        from schemas import Observation

        obs_list = tuple(
            Observation(
                obs_id=f"e{i}",
                ra_deg=float(i),
                dec_deg=0.0,
                jd=2460000.5 + i,
                mag=19.0,
                mag_err=0.05,
                filter_band="r",
                mission="ZTF",
            )
            for i in range(4)
        )
        result = filter_alerts_by_motion(obs_list)
        assert len(result) == 4
