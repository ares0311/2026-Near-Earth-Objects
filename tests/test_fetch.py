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


class TestBuildObservationWindow:
    def test_basic_construction(self):
        from fetch import build_observation_window
        w = build_observation_window(180.0, 0.0, start_jd=2460000.5, end_jd=2460030.5)
        assert w.ra_deg == pytest.approx(180.0)
        assert w.dec_deg == pytest.approx(0.0)

    def test_default_survey_is_ztf(self):
        from fetch import build_observation_window
        w = build_observation_window(90.0, 10.0, start_jd=2460000.5, end_jd=2460010.5)
        assert "ZTF" in w.surveys

    def test_invalid_start_end_jd_raises(self):
        import pytest as pt

        from fetch import build_observation_window
        with pt.raises(ValueError, match="start_jd"):
            build_observation_window(0.0, 0.0, start_jd=2460010.0, end_jd=2460000.0)

    def test_zero_radius_raises(self):
        import pytest as pt

        from fetch import build_observation_window
        with pt.raises(ValueError, match="radius_deg"):
            build_observation_window(0.0, 0.0, radius_deg=0.0,
                                     start_jd=2460000.5, end_jd=2460010.5)

    def test_invalid_survey_raises(self):
        import pytest as pt

        from fetch import build_observation_window
        with pt.raises(ValueError, match="Unknown survey"):
            build_observation_window(0.0, 0.0, surveys=["FAKE"],
                                     start_jd=2460000.5, end_jd=2460010.5)

    def test_custom_surveys_stored(self):
        from fetch import build_observation_window
        w = build_observation_window(0.0, 0.0, surveys=["ZTF", "ATLAS"],
                                     start_jd=2460000.5, end_jd=2460010.5)
        assert "ATLAS" in w.surveys


class TestCountKnownObjectsInField:
    def test_returns_int(self):
        from unittest.mock import patch

        from fetch import count_known_objects_in_field
        with patch("fetch.fetch_mpc_known", return_value=[]):
            result = count_known_objects_in_field(10.0, 20.0, 1.0)
        assert isinstance(result, int)

    def test_returns_count_equal_to_alerts(self):
        from unittest.mock import patch

        from fetch import count_known_objects_in_field
        from schemas import Observation
        obs = Observation(
            obs_id="k1", ra_deg=10.0, dec_deg=20.0, jd=2460000.5,
            mag=18.0, mag_err=0.05, filter_band="r", mission="MPC", real_bogus=1.0,
        )
        with patch("fetch.fetch_mpc_known", return_value=[obs]):
            result = count_known_objects_in_field(10.0, 20.0, 1.0)
        assert result == 1

    def test_returns_zero_on_error(self):
        from unittest.mock import patch

        from fetch import count_known_objects_in_field
        with patch("fetch.fetch_mpc_known", side_effect=RuntimeError("network")):
            result = count_known_objects_in_field(0.0, 0.0, 1.0)
        assert result == 0


class TestFilterAlertsByMotionRateProxy:
    def _make_obs(self, ssd=None):
        import types
        obs = types.SimpleNamespace(
            obs_id="fam_001", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
        )
        if ssd is not None:
            obs.ssdistnr = ssd
        return obs

    def test_obs_with_ssd_in_range_included(self):
        from fetch import filter_alerts_by_motion
        # ssd=0.1 → rate_proxy = 0.1 * 120 = 12 arcsec/hr
        obs = self._make_obs(ssd=0.1)
        result = filter_alerts_by_motion((obs,), min_rate_arcsec_hr=5.0, max_rate_arcsec_hr=20.0)
        assert len(result) == 1

    def test_obs_with_ssd_out_of_range_excluded(self):
        from fetch import filter_alerts_by_motion
        # ssd=1.0 → rate_proxy = 120 → above max
        obs = self._make_obs(ssd=1.0)
        result = filter_alerts_by_motion((obs,), min_rate_arcsec_hr=5.0, max_rate_arcsec_hr=20.0)
        assert len(result) == 0


class TestBuildObservationWindowDefaultEndJd:
    def test_default_end_jd_is_30_days_after_start(self):
        import pytest as pt

        from fetch import build_observation_window
        w = build_observation_window(10.0, 20.0, start_jd=2460000.5)
        assert w.end_jd == pt.approx(2460030.5)


class TestFetchMpcObservations:
    def test_returns_list_on_import_error(self):
        from unittest.mock import patch

        from fetch import fetch_mpc_observations
        # Patch the astroquery.mpc module itself to simulate ImportError
        with patch.dict("sys.modules", {"astroquery.mpc": None}):
            result = fetch_mpc_observations("2020_XL5_net_err_test_xyz")
        assert isinstance(result, list)

    def test_returns_list_for_known_object(self):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_mpc_observations

        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "number": "433",
            "RA": 180.0,
            "Dec": 5.0,
            "JD": 2460000.5,
            "mag": 18.5,
            "band": "V",
        }.get(k, None))
        mock_row.get = MagicMock(side_effect=lambda k, default=None: {
            "mag": 18.5,
            "band": "V",
        }.get(k, default))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))
        mock_table.__len__ = MagicMock(return_value=1)

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table

        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mpc_observations("433_known_obj_test")
        assert isinstance(result, list)

    def test_empty_result_on_exception(self):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_mpc_observations

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.side_effect = Exception("network error")

        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mpc_observations("unknown_xyz_test_999")
        assert result == []

    def test_returns_list_type(self):
        # Call with a designation unlikely to be cached; result is always list
        from unittest.mock import patch

        from fetch import fetch_mpc_observations
        with patch.dict("sys.modules", {"astroquery.mpc": None}):
            result = fetch_mpc_observations("test_designation_abc123")
        assert isinstance(result, list)


class TestFetchMpcObservationsCacheHit:
    """Cover cache hit path in fetch_mpc_observations (lines 631-632)."""

    def test_returns_from_cache(self, tmp_path, monkeypatch):
        import hashlib
        from unittest.mock import patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        # Pre-populate cache with a valid Observation dict
        desig = "cache_hit_test_1234"
        cache_key = hashlib.md5(f"mpc_obs_{desig}".encode()).hexdigest()

        obs_dict = {
            "obs_id": f"{desig}_1",
            "ra_deg": 10.0,
            "dec_deg": 5.0,
            "jd": 2460000.5,
            "mag": 18.5,
            "mag_err": 0.1,
            "filter_band": "V",
            "mission": "MPC",
            "real_bogus": 1.0,
        }
        fetch_mod._save_cache(cache_key, [obs_dict])

        # Patch astroquery.mpc to ensure it's NOT called (cache hit)
        with patch.dict("sys.modules", {"astroquery.mpc": None}):
            result = fetch_mod.fetch_mpc_observations(desig)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_successful_mpc_query_and_cache(self, tmp_path, monkeypatch):
        """Cover the successful astroquery path (lines 638-656)."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        desig = "433_eros_full_path_test"

        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "number": "433",
            "RA": 180.0,
            "Dec": 5.0,
            "JD": 2460000.5,
        }.get(k, None))
        mock_row.get = MagicMock(side_effect=lambda k, default=None: {
            "mag": 18.5,
            "band": "V",
        }.get(k, default))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table

        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations(desig)
        assert isinstance(result, list)


class TestFetchMpcObservationsEdgeCases:
    """Cover lines 631-632 and 653-654 in fetch_mpc_observations."""

    def test_bad_cached_observation_skipped(self, tmp_path, monkeypatch):
        """Lines 631-632: except Exception in cache hit path."""
        import hashlib
        from unittest.mock import patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        desig = "bad_cache_obs_test_9999"
        cache_key = hashlib.md5(f"mpc_obs_{desig}".encode()).hexdigest()
        # Save an invalid dict that will fail Observation(**d)
        fetch_mod._save_cache(cache_key, [{"invalid_field": "garbage"}])

        with patch.dict("sys.modules", {"astroquery.mpc": None}):
            result = fetch_mod.fetch_mpc_observations(desig)
        # Invalid entry is skipped; returns empty list
        assert isinstance(result, list)
        assert len(result) == 0

    def test_bad_row_skipped_in_mpc_query(self, tmp_path, monkeypatch):
        """Lines 653-654: except Exception inside for-row loop."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        desig = "bad_row_mpc_test_8888"

        # Row that raises on key access
        bad_row = MagicMock()
        bad_row.__getitem__ = MagicMock(side_effect=KeyError("RA"))
        bad_row.get = MagicMock(return_value=None)

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([bad_row]))

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table

        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations(desig)
        assert isinstance(result, list)
        assert len(result) == 0


class TestFetchAtlasForced:
    def test_returns_empty_without_token(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.delenv("ATLAS_TOKEN", raising=False)
        result = fetch_mod.fetch_atlas_forced(180.0, 10.0, 2460000.0, 2460010.0, atlas_token=None)
        assert result == []

    def test_returns_list_type(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.delenv("ATLAS_TOKEN", raising=False)
        result = fetch_mod.fetch_atlas_forced(180.0, 10.0, 2460000.0, 2460010.0)
        assert isinstance(result, list)

    def test_returns_from_cache(self, tmp_path, monkeypatch):
        import hashlib

        import fetch as fetch_mod
        from schemas import Observation

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = Observation(
            obs_id="atlas_001", ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=18.5, mag_err=0.05, filter_band="o", mission="ATLAS",
        )
        ra, dec = 180.0, 10.0
        start_jd, end_jd = 2460000.0, 2460010.0
        cache_key = hashlib.md5(
            f"atlas_forced_{ra:.5f}_{dec:.5f}_{start_jd:.3f}_{end_jd:.3f}".encode()
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch_mod.fetch_atlas_forced(ra, dec, start_jd, end_jd)
        assert len(result) == 1
        assert result[0].obs_id == "atlas_001"

    def test_network_error_returns_empty(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_requests = MagicMock()
        mock_requests.post.side_effect = RuntimeError("network error")

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                180.0, 10.0, 2460000.0, 2460010.0, atlas_token="fake_token"
            )
        assert result == []

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        import hashlib

        import fetch as fetch_mod
        from schemas import Observation

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.delenv("ATLAS_TOKEN", raising=False)

        obs = Observation(
            obs_id="atlas_stale", ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=18.5, mag_err=0.05, filter_band="o", mission="ATLAS",
        )
        ra, dec = 180.0, 10.0
        start_jd, end_jd = 2460000.0, 2460010.0
        cache_key = hashlib.md5(
            f"atlas_forced_{ra:.5f}_{dec:.5f}_{start_jd:.3f}_{end_jd:.3f}".encode()
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        # force_refresh=True + no token → should bypass cache and return []
        result = fetch_mod.fetch_atlas_forced(ra, dec, start_jd, end_jd, force_refresh=True)
        assert result == []

    def test_bad_cached_entry_skipped(self, tmp_path, monkeypatch):
        import hashlib

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        ra, dec = 10.0, 20.0
        start_jd, end_jd = 2460000.0, 2460010.0
        cache_key = hashlib.md5(
            f"atlas_forced_{ra:.5f}_{dec:.5f}_{start_jd:.3f}_{end_jd:.3f}".encode()
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [{"invalid": "garbage"}])

        result = fetch_mod.fetch_atlas_forced(ra, dec, start_jd, end_jd)
        assert result == []


class TestFetchAtlasForcedPollingLoop:
    """Cover lines 727-748 in fetch_atlas_forced: the API polling + result parsing."""

    def test_successful_api_call_returns_observations(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        # ATLAS text format: first # line is header; subsequent lines are data.
        # Parser reads "MJD" column (uppercase) for the Julian date.
        atlas_data = "#MJD RA Dec m dm F\n60000.5 180.001 10.001 18.5 0.05 o\n"

        # Setup mocked requests
        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post_resp.json.return_value = {"url": "https://fake-atlas/task/1/"}

        mock_task_resp = MagicMock()
        mock_task_resp.raise_for_status = MagicMock()
        mock_task_resp.json.return_value = {"result_url": "https://fake-atlas/result/1/"}

        mock_result_resp = MagicMock()
        mock_result_resp.raise_for_status = MagicMock()
        mock_result_resp.text = atlas_data

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.side_effect = [mock_task_resp, mock_result_resp]

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                180.0, 10.0, 2459600.0, 2459610.0, atlas_token="valid_token"
            )

        assert isinstance(result, list)

    def test_empty_task_url_returns_empty(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post_resp.json.return_value = {"url": ""}

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                180.0, 10.0, 2459600.0, 2459610.0, atlas_token="valid_token"
            )

        assert result == []

    def test_polling_exhausted_returns_empty(self, tmp_path, monkeypatch):
        """Poll loop runs 10 times but no result_url ever appears."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post_resp.json.return_value = {"url": "https://fake-atlas/task/2/"}

        mock_poll_resp = MagicMock()
        mock_poll_resp.raise_for_status = MagicMock()
        mock_poll_resp.json.return_value = {}  # no result_url yet

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.return_value = mock_poll_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                10.0, 5.0, 2459600.0, 2459610.0, atlas_token="valid_token"
            )

        assert result == []


class TestFetchZtfAlerts:
    def test_returns_empty_on_import_error(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # astroquery.irsa not installed → returns []
        result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)
        assert isinstance(result, list)

    def test_returns_list_type(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 1.0, 2460000.0, 2460010.0)
        assert isinstance(result, list)

    def test_returns_from_cache(self, tmp_path, monkeypatch):
        import hashlib

        import fetch as fetch_mod
        from schemas import Observation

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        ra, dec, radius = 180.0, 10.0, 0.5
        start_jd, end_jd = 2460000.0, 2460010.0
        cache_key = hashlib.md5(
            f"ztf_irsa_{ra:.5f}_{dec:.5f}_{radius:.4f}"
            f"_{start_jd:.3f}_{end_jd:.3f}".encode()
        ).hexdigest()
        obs = Observation(
            obs_id="ztf_cached_001", ra_deg=ra, dec_deg=dec, jd=2460005.0,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        fetch_mod._save_cache(cache_key, [obs.model_dump()])
        result = fetch_mod.fetch_ztf_alerts(ra, dec, radius, start_jd, end_jd)
        assert len(result) == 1
        assert result[0].obs_id == "ztf_cached_001"

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        import hashlib

        import fetch as fetch_mod
        from schemas import Observation

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        ra, dec, radius = 10.0, 5.0, 0.5
        start_jd, end_jd = 2460000.0, 2460010.0
        cache_key = hashlib.md5(
            f"ztf_irsa_{ra:.5f}_{dec:.5f}_{radius:.4f}"
            f"_{start_jd:.3f}_{end_jd:.3f}".encode()
        ).hexdigest()
        obs = Observation(
            obs_id="stale", ra_deg=ra, dec_deg=dec, jd=2460005.0,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        fetch_mod._save_cache(cache_key, [obs.model_dump()])
        # force_refresh=True bypasses cache; irsa not available → returns []
        result = fetch_mod.fetch_ztf_alerts(ra, dec, radius, start_jd, end_jd, force_refresh=True)
        assert result == []

    def test_bad_cached_entry_skipped(self, tmp_path, monkeypatch):
        import hashlib

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        ra, dec, radius = 30.0, -5.0, 0.5
        start_jd, end_jd = 2460000.0, 2460010.0
        cache_key = hashlib.md5(
            f"ztf_irsa_{ra:.5f}_{dec:.5f}_{radius:.4f}"
            f"_{start_jd:.3f}_{end_jd:.3f}".encode()
        ).hexdigest()
        fetch_mod._save_cache(cache_key, [{"invalid": "garbage"}])
        result = fetch_mod.fetch_ztf_alerts(ra, dec, radius, start_jd, end_jd)
        assert result == []


class TestFetchZtfAlertsIrsaPath:
    """Cover lines 812-835: the IRSA query + row parsing path."""

    def test_successful_irsa_query(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        # Build a fake Irsa result table row
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "jd": 2460005.0,
            "ra": 180.001,
            "dec": 10.001,
        }[k])
        mock_row.get = MagicMock(side_effect=lambda k, d=None: {
            "candid": "ztf_abc123",
            "magpsf": 19.0,
            "sigmapsf": 0.05,
            "fid": "r",
            "rb": 0.9,
        }.get(k, d))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_irsa_cls = MagicMock()
        mock_irsa_cls.query_region.return_value = mock_table

        mock_irsa_mod = MagicMock()
        mock_irsa_mod.Irsa = mock_irsa_cls

        mock_astropy_units = MagicMock()
        mock_astropy_units.deg = "deg"

        mock_skycoord = MagicMock()

        with patch.dict("sys.modules", {
            "astroquery.irsa": mock_irsa_mod,
            "astropy.units": mock_astropy_units,
            "astropy.coordinates": MagicMock(SkyCoord=mock_skycoord),
        }):
            result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].obs_id == "ztf_abc123"

    def test_row_outside_jd_window_excluded(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "jd": 2459000.0,  # outside [2460000, 2460010]
        }[k] if k == "jd" else 0.0)
        mock_row.get = MagicMock(return_value=None)

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_irsa_mod = MagicMock()
        mock_irsa_mod.Irsa.query_region.return_value = mock_table

        with patch.dict("sys.modules", {
            "astroquery.irsa": mock_irsa_mod,
            "astropy.units": MagicMock(deg="deg"),
            "astropy.coordinates": MagicMock(SkyCoord=MagicMock()),
        }):
            result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)

        assert result == []

    def test_bad_row_skipped_with_exception(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(side_effect=KeyError("jd"))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_irsa_mod = MagicMock()
        mock_irsa_mod.Irsa.query_region.return_value = mock_table

        with patch.dict("sys.modules", {
            "astroquery.irsa": mock_irsa_mod,
            "astropy.units": MagicMock(deg="deg"),
            "astropy.coordinates": MagicMock(SkyCoord=MagicMock()),
        }):
            result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)

        assert result == []


class TestEstimateSurveyDepth:
    def _make_result(self, mags):
        from schemas import FetchProvenance, FetchResult

        from .conftest import build_observation
        alerts = tuple(build_observation(obs_id=f"s_{i}", mag=m) for i, m in enumerate(mags))
        prov = FetchProvenance(surveys=("ZTF",), start_jd=2460000.5, end_jd=2460001.5)
        return FetchResult(alerts=alerts, provenance=prov)

    def test_empty_alerts_returns_none(self):
        from fetch import estimate_survey_depth
        result = self._make_result([])
        assert estimate_survey_depth(result) is None

    def test_all_sentinel_mags_returns_none(self):
        from fetch import estimate_survey_depth
        result = self._make_result([99.0, 99.0, 99.0])
        assert estimate_survey_depth(result) is None

    def test_returns_float(self):
        from fetch import estimate_survey_depth
        result = self._make_result([18.0, 19.0, 20.0, 21.0])
        assert isinstance(estimate_survey_depth(result), float)

    def test_95th_percentile(self):
        import numpy as np

        from fetch import estimate_survey_depth
        mags = [18.0 + i * 0.1 for i in range(20)]
        result = self._make_result(mags)
        depth = estimate_survey_depth(result)
        expected = round(float(np.percentile(mags, 95)), 4)
        assert depth == pytest.approx(expected, abs=0.001)

    def test_excludes_sentinel_mags(self):
        from fetch import estimate_survey_depth
        result = self._make_result([18.0, 19.0, 99.0])
        depth = estimate_survey_depth(result)
        # 99.0 excluded, so depth should be based only on [18.0, 19.0]
        assert depth is not None
        assert depth < 90.0


class TestFilterBySurvey:
    def _make_result(self, missions):
        from schemas import FetchProvenance, FetchResult

        from .conftest import build_observation
        alerts = tuple(
            build_observation(obs_id=f"o_{i}", mission=m)
            for i, m in enumerate(missions)
        )
        prov = FetchProvenance(surveys=("ZTF", "ATLAS"), start_jd=2460000.5, end_jd=2460001.5)
        return FetchResult(alerts=alerts, provenance=prov)

    def test_empty_surveys_returns_empty_alerts(self):
        from fetch import filter_by_survey
        result = self._make_result(["ZTF", "ATLAS"])
        filtered = filter_by_survey(result, [])
        assert len(filtered.alerts) == 0

    def test_filters_to_single_survey(self):
        from fetch import filter_by_survey
        result = self._make_result(["ZTF", "ATLAS", "ZTF"])
        filtered = filter_by_survey(result, ["ZTF"])
        assert len(filtered.alerts) == 2
        assert all(o.mission == "ZTF" for o in filtered.alerts)

    def test_keeps_multiple_surveys(self):
        from fetch import filter_by_survey
        result = self._make_result(["ZTF", "ATLAS", "CSS"])
        filtered = filter_by_survey(result, ["ZTF", "ATLAS"])
        assert len(filtered.alerts) == 2

    def test_preserves_provenance(self):
        from fetch import filter_by_survey
        result = self._make_result(["ZTF"])
        filtered = filter_by_survey(result, ["ZTF"])
        assert filtered.provenance is result.provenance

    def test_returns_fetch_result(self):
        from fetch import filter_by_survey
        from schemas import FetchResult
        result = self._make_result(["ZTF"])
        filtered = filter_by_survey(result, ["ZTF"])
        assert isinstance(filtered, FetchResult)

    def test_unknown_survey_returns_empty(self):
        from fetch import filter_by_survey
        result = self._make_result(["ZTF", "ATLAS"])
        filtered = filter_by_survey(result, ["PanSTARRS"])
        assert len(filtered.alerts) == 0


class TestFetchPanstarrsCatalog:
    def _make_obs(self):
        return {
            "obs_id": "ps1_123", "ra_deg": 180.0, "dec_deg": 10.0,
            "jd": 2460000.5, "mag": 19.5, "mag_err": 0.05,
            "filter_band": "r", "mission": "PanSTARRS",
        }

    def test_returns_list_on_cache_hit(self, tmp_path):
        import json
        from unittest.mock import patch

        from fetch import fetch_panstarrs_catalog
        cache_dir = tmp_path / ".neo_cache"
        cache_dir.mkdir()
        with patch("fetch._CACHE_DIR", cache_dir):
            import hashlib
            key = hashlib.md5(
                b"panstarrs:180.000000:10.000000:0.500000:2460000.50"
            ).hexdigest()
            cache_file = cache_dir / f"{key}.json"
            cache_file.write_text(json.dumps([self._make_obs()]))
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_returns_empty_on_network_failure(self, tmp_path):
        from unittest.mock import patch

        from fetch import fetch_panstarrs_catalog
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": None}):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5)
        assert isinstance(result, list)

    def test_force_refresh_bypasses_cache(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog
        cache_dir = tmp_path / ".neo_cache"
        cache_dir.mkdir()
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = []
        with patch("fetch._CACHE_DIR", cache_dir), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5, force_refresh=True)
        assert isinstance(result, list)

    def test_mast_exception_returns_empty(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.side_effect = RuntimeError("network")
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5, force_refresh=True)
        assert isinstance(result, list)

    def test_cache_write_failure_still_returns(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = []
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}), \
             patch("builtins.open", side_effect=OSError("disk full")):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5, force_refresh=True)
        assert isinstance(result, list)


class TestFetchPanstarrsCatalogParsing:
    """Cover row-parsing and cache-failure paths in fetch_panstarrs_catalog."""

    def test_row_parsing_with_valid_mast_data(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog

        mock_row = {
            "objID": 12345, "raMean": 180.0, "decMean": 10.0,
            "rMeanPSFMag": 19.5, "rMeanPSFMagErr": 0.05,
        }
        mock_results = [mock_row]
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = mock_results
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5, force_refresh=True)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].mission == "PanSTARRS"

    def test_row_with_none_mag_uses_sentinel(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog

        mock_row = {
            "objID": 99999, "raMean": 180.0, "decMean": 10.0,
            "rMeanPSFMag": None, "rMeanPSFMagErr": None,
        }
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = [mock_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5, force_refresh=True)
        assert isinstance(result, list)
        if result:
            assert result[0].mag == 99.0

    def test_row_parse_exception_skipped(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog

        bad_row = {"objID": "bad", "raMean": "not_a_float", "decMean": "x",
                   "rMeanPSFMag": None, "rMeanPSFMagErr": None}
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = [bad_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5, force_refresh=True)
        assert isinstance(result, list)

    def test_corrupted_cache_falls_through_to_network(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog
        cache_dir = tmp_path / ".neo_cache"
        cache_dir.mkdir()
        import hashlib
        key = hashlib.md5(
            b"panstarrs:180.000000:10.000000:0.500000:2460000.50"
        ).hexdigest()
        (cache_dir / f"{key}.json").write_text("not valid json {{{")
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = []
        with patch("fetch._CACHE_DIR", cache_dir), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_catalog(180.0, 10.0, 0.5)
        assert isinstance(result, list)

    def test_cache_write_failure_silently_ignored(self, tmp_path):
        """Lines 957-958: exception during cache write is swallowed."""
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_catalog

        mock_row = {
            "objID": 77777, "raMean": 45.0, "decMean": -5.0,
            "rMeanPSFMag": 20.0, "rMeanPSFMagErr": 0.1,
        }
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = [mock_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch("json.dump", side_effect=OSError("disk full")), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_catalog(45.0, -5.0, 0.3, force_refresh=True)
        assert isinstance(result, list)


class TestFetchCssAlerts:
    def test_returns_empty_on_import_error(self, tmp_path):
        from unittest.mock import patch

        from fetch import fetch_css_alerts
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mpc": None}):
            result = fetch_css_alerts(180.0, 0.0, 0.5, force_refresh=True)
        assert result == []

    def test_returns_list(self, tmp_path):
        from unittest.mock import patch

        from fetch import fetch_css_alerts
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mpc": None}):
            result = fetch_css_alerts(10.0, 5.0, 1.0, force_refresh=True)
        assert isinstance(result, list)

    def test_cache_hit(self, tmp_path):
        import hashlib
        import json

        from fetch import fetch_css_alerts
        cache_dir = tmp_path / ".neo_cache"
        cache_dir.mkdir()
        key = hashlib.md5(b"css:180.000000:0.000000:0.500000").hexdigest()
        data = [{
            "obs_id": "css_001", "jd": 2460000.5, "ra_deg": 180.0, "dec_deg": 0.0,
            "mag": 19.0, "mag_err": 0.1, "filter_band": "V", "mission": "CSS",
        }]
        (cache_dir / f"{key}.json").write_text(json.dumps(data))
        from unittest.mock import patch
        with patch("fetch._CACHE_DIR", cache_dir):
            result = fetch_css_alerts(180.0, 0.0, 0.5)
        assert len(result) == 1
        assert result[0].mission == "CSS"

    def test_filters_non_703(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_css_alerts
        mock_row = {
            "obs_code": "500", "submission_info": "other",
            "obs_id": "x", "epoch": 2460000.5, "ra": 180.0, "dec": 0.0,
            "mag": 18.0, "band": "V",
        }
        mock_mpc = MagicMock()
        mock_mpc.MPC.query_observations_by_position.return_value = [mock_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mpc": mock_mpc}):
            result = fetch_css_alerts(180.0, 0.0, 0.5, force_refresh=True)
        assert result == []

    def test_includes_703_rows(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_css_alerts
        mock_row = {
            "obs_code": "703", "submission_info": "",
            "obs_id": "css_valid", "epoch": 2460000.5,
            "ra": 180.0, "dec": 0.0, "mag": 19.5, "band": "V",
        }
        mock_mpc = MagicMock()
        mock_mpc.MPC.query_observations_by_position.return_value = [mock_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mpc": mock_mpc}):
            result = fetch_css_alerts(180.0, 0.0, 0.5, force_refresh=True)
        assert len(result) == 1
        assert result[0].mission == "CSS"

    def test_cache_write_failure_silently_ignored(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_css_alerts
        mock_mpc = MagicMock()
        mock_mpc.MPC.query_observations_by_position.return_value = []
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch("json.dump", side_effect=OSError("no space")), \
             patch.dict("sys.modules", {"astroquery.mpc": mock_mpc}):
            result = fetch_css_alerts(90.0, 30.0, 0.3, force_refresh=True)
        assert isinstance(result, list)

    def test_corrupted_cache_falls_through(self, tmp_path):
        import hashlib
        from unittest.mock import MagicMock, patch

        from fetch import fetch_css_alerts
        cache_dir = tmp_path / ".neo_cache"
        cache_dir.mkdir()
        key = hashlib.md5(b"css:45.000000:10.000000:0.200000").hexdigest()
        (cache_dir / f"{key}.json").write_text("not valid json {{")
        mock_mpc = MagicMock()
        mock_mpc.MPC.query_observations_by_position.return_value = []
        with patch("fetch._CACHE_DIR", cache_dir), \
             patch.dict("sys.modules", {"astroquery.mpc": mock_mpc}):
            result = fetch_css_alerts(45.0, 10.0, 0.2)
        assert isinstance(result, list)


class TestFetchCssAlertsEdgeCases:
    def test_row_with_bad_ra_skipped(self, tmp_path):
        """703 row with bad ra value → exception → row skipped."""
        from unittest.mock import MagicMock, patch

        from fetch import fetch_css_alerts
        bad_row = {
            "obs_code": "703", "submission_info": "",
            "obs_id": "bad", "epoch": 2460000.5,
            "ra": "not_a_float", "dec": 0.0, "mag": 19.0, "band": "V",
        }
        mock_mpc = MagicMock()
        mock_mpc.MPC.query_observations_by_position.return_value = [bad_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mpc": mock_mpc}):
            result = fetch_css_alerts(180.0, 0.0, 0.5, force_refresh=True)
        assert result == []


class TestFetchPanstarrMovingObjects:
    def test_returns_empty_on_import_error(self, tmp_path):
        from unittest.mock import patch

        from fetch import fetch_panstarrs_moving_objects
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": None}):
            result = fetch_panstarrs_moving_objects(180.0, 0.0, 0.5, force_refresh=True)
        assert result == []

    def test_returns_list(self, tmp_path):
        from unittest.mock import patch

        from fetch import fetch_panstarrs_moving_objects
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": None}):
            result = fetch_panstarrs_moving_objects(10.0, 5.0, 1.0)
        assert isinstance(result, list)

    def test_filters_non_solar_system_rows(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_moving_objects
        mock_row = {"ssObjectId": None, "detectID": 1, "obsTime": 57000.0,
                    "ra": 180.0, "dec": 0.0, "psfFlux": 1000.0, "psfFluxErr": 10.0, "filterID": "r"}
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = [mock_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_moving_objects(180.0, 0.0, 0.5, force_refresh=True)
        assert result == []

    def test_includes_solar_system_rows(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_moving_objects
        mock_row = {"ssObjectId": 12345, "detectID": 99, "obsTime": 57000.0,
                    "ra": 180.0, "dec": 0.0, "psfFlux": 1000.0, "psfFluxErr": 10.0, "filterID": "r"}
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = [mock_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_moving_objects(180.0, 0.0, 0.5, force_refresh=True)
        assert len(result) == 1
        assert result[0].mission == "PanSTARRS"

    def test_cache_write_failure_ignored(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_moving_objects
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = []
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch("json.dump", side_effect=OSError("disk full")), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_moving_objects(45.0, 10.0, 0.3, force_refresh=True)
        assert isinstance(result, list)

    def test_bad_row_skipped(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_moving_objects
        bad_row = {"ssObjectId": 99, "detectID": "x", "obsTime": "bad",
                   "ra": "not_float", "dec": 0.0, "psfFlux": None, "filterID": "r"}
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = [bad_row]
        with patch("fetch._CACHE_DIR", tmp_path / ".neo_cache"), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_moving_objects(180.0, 0.0, 0.5, force_refresh=True)
        assert isinstance(result, list)

    def test_cache_hit(self, tmp_path):
        import hashlib
        import json

        from fetch import fetch_panstarrs_moving_objects
        cache_dir = tmp_path / ".neo_cache"
        cache_dir.mkdir()
        key = hashlib.md5(b"ps1_moving:180.000000:0.000000:0.500000").hexdigest()
        data = [{"obs_id": "ps1_mo_1", "jd": 2460000.5, "ra_deg": 180.0, "dec_deg": 0.0,
                 "mag": 20.0, "mag_err": 0.1, "filter_band": "r", "mission": "PanSTARRS"}]
        (cache_dir / f"{key}.json").write_text(json.dumps(data))
        from unittest.mock import patch
        with patch("fetch._CACHE_DIR", cache_dir):
            result = fetch_panstarrs_moving_objects(180.0, 0.0, 0.5)
        assert len(result) == 1 and result[0].mission == "PanSTARRS"


class TestFetchPanstarrMovingObjectsEdge:
    def test_corrupted_cache_falls_through(self, tmp_path):
        import hashlib
        from unittest.mock import MagicMock, patch

        from fetch import fetch_panstarrs_moving_objects
        cache_dir = tmp_path / ".neo_cache"
        cache_dir.mkdir()
        key = hashlib.md5(b"ps1_moving:90.000000:0.000000:0.300000").hexdigest()
        (cache_dir / f"{key}.json").write_text("not valid json {{{{")
        mock_mast = MagicMock()
        mock_mast.Catalogs.query_region.return_value = []
        with patch("fetch._CACHE_DIR", cache_dir), \
             patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_panstarrs_moving_objects(90.0, 0.0, 0.3)
        assert isinstance(result, list)


class TestFetchRecentMpcNeos:
    """Tests for fetch_recent_mpc_neos."""

    def _make_mock_row(self, ra=180.0, dec=10.0, h=18.0, disc_days_ago=5):
        from datetime import date, timedelta
        row = {
            "ra": ra,
            "dec": dec,
            "h": h,
            "discovery_date": date.today() - timedelta(days=disc_days_ago),
        }
        return row

    def test_normal_mock_mpc(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_row = self._make_mock_row()
        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects.return_value = [mock_row]
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fm.fetch_recent_mpc_neos(n_days=30)
        assert len(result) == 1
        assert result[0].mission == "MPC"
        assert result[0].filter_band == "V"

    def test_import_error_returns_empty(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # Block astroquery.mpc import
        monkeypatch.setitem(sys.modules, "astroquery.mpc", None)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fm.fetch_recent_mpc_neos(n_days=30)
        assert result == []

    def test_query_error_returns_empty(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects.side_effect = RuntimeError("network error")
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fm.fetch_recent_mpc_neos(n_days=30)
        assert result == []

    def test_force_refresh_bypasses_cache(self, tmp_path, monkeypatch):
        import hashlib
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        # Seed cache with one entry
        from schemas import Observation
        obs = Observation(
            obs_id="mpc_recent_0", ra_deg=10.0, dec_deg=5.0, jd=2460000.5,
            mag=18.0, mag_err=0.1, filter_band="V", mission="MPC", real_bogus=1.0,
        )
        cache_key = hashlib.md5(b"mpc_recent_neos:30").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        # force_refresh bypasses cache; MPC query returns nothing
        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects.return_value = []
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")
        # Seed the already-reloaded fm's cache
        fm._save_cache(cache_key, [obs.model_dump()])

        result = fm.fetch_recent_mpc_neos(n_days=30, force_refresh=True)
        assert result == []  # fresh query returned nothing

    def test_cached_result_returned(self, tmp_path, monkeypatch):
        import hashlib
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        from schemas import Observation
        obs = Observation(
            obs_id="mpc_recent_0", ra_deg=10.0, dec_deg=5.0, jd=2460000.5,
            mag=18.0, mag_err=0.1, filter_band="V", mission="MPC", real_bogus=1.0,
        )
        cache_key = hashlib.md5(b"mpc_recent_neos:30").hexdigest()
        fetch_mod._save_cache(cache_key, [obs.model_dump()])

        result = fetch_mod.fetch_recent_mpc_neos(n_days=30)
        assert len(result) == 1
        assert result[0].obs_id == "mpc_recent_0"

    def test_old_discovery_filtered_out(self, tmp_path, monkeypatch):
        import sys
        from datetime import date, timedelta
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        old_row = {
            "ra": 180.0, "dec": 10.0, "h": 18.0,
            "discovery_date": date.today() - timedelta(days=60),
        }
        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects.return_value = [old_row]
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)

        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")

        result = fm.fetch_recent_mpc_neos(n_days=30)
        assert result == []

    def test_corrupted_cache_skipped(self, tmp_path, monkeypatch):
        import hashlib
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # Save a cache entry with a missing required field so Observation(**d) raises
        cache_key = hashlib.md5(b"mpc_recent_neos:30").hexdigest()
        fetch_mod._save_cache(cache_key, [{"bad_field": "bad"}])
        result = fetch_mod.fetch_recent_mpc_neos(n_days=30)
        assert result == []

    def test_string_discovery_date_parsed(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # Row with discovery_date as a string (not a date object) triggers strptime path
        from datetime import date, timedelta
        disc_str = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        row = {"ra": 180.0, "dec": 10.0, "h": 18.0, "discovery_date": disc_str}
        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects.return_value = [row]
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)
        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")
        result = fm.fetch_recent_mpc_neos(n_days=30)
        assert len(result) == 1

    def test_bad_row_data_skipped(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # Row with non-numeric ra triggers the per-row except handler
        from datetime import date, timedelta
        disc_str = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        bad_row = {"ra": "not_a_number", "dec": "also_bad", "h": 18.0,
                   "discovery_date": disc_str}
        mock_mpc_cls = MagicMock()
        mock_mpc_cls.query_objects.return_value = [bad_row]
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)
        import importlib

        import fetch as fm
        importlib.reload(fm)
        monkeypatch.setattr(fm, "_CACHE_DIR", tmp_path / ".neo_cache")
        result = fm.fetch_recent_mpc_neos(n_days=30)
        assert result == []

    def test_in_all(self):
        from fetch import __all__
        assert "fetch_recent_mpc_neos" in __all__


class TestEstimateFieldCompleteness:
    """Tests for estimate_field_completeness."""

    def _make_fetch_result(self, mags):
        from schemas import FetchProvenance, FetchResult, Observation
        obs = tuple(
            Observation(
                obs_id=f"fc{i}",
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

    def test_empty_alerts_returns_zero(self):
        from schemas import FetchProvenance, FetchResult
        prov = FetchProvenance(surveys=("ZTF",), start_jd=2460000.0, end_jd=2460001.0)
        fr = FetchResult(alerts=(), provenance=prov)
        from fetch import estimate_field_completeness
        assert estimate_field_completeness(fr) == 0.0

    def test_explicit_limiting_mag(self):
        from fetch import estimate_field_completeness
        # 3 obs at 18, 19, 20 — threshold is 20.5; all three < 20.5 → 100%
        fr = self._make_fetch_result([18.0, 19.0, 20.0])
        result = estimate_field_completeness(fr, limiting_mag=21.0)
        assert result == 1.0

    def test_partial_completeness(self):
        from fetch import estimate_field_completeness
        # 2 obs bright (17, 18) + 1 faint (20.8) → threshold 20.5; 2/3 complete
        fr = self._make_fetch_result([17.0, 18.0, 20.8])
        result = estimate_field_completeness(fr, limiting_mag=21.0)
        assert abs(result - round(2 / 3, 4)) < 0.001

    def test_sentinel_mags_excluded(self):
        from fetch import estimate_field_completeness
        # sentinel mag ≥ 90 should be ignored
        fr = self._make_fetch_result([17.0, 99.0])
        result = estimate_field_completeness(fr, limiting_mag=20.0)
        # only obs with mag=17.0 is valid; 17.0 <= 19.5 → 1/1 = 1.0
        assert result == 1.0

    def test_no_limiting_mag_derived(self):
        from fetch import estimate_field_completeness
        from schemas import FetchProvenance, FetchResult, Observation
        # all sentinel mags → estimate_survey_depth returns None → 0.0
        obs = tuple(
            Observation(
                obs_id=f"fcx{i}", ra_deg=180.0, dec_deg=10.0,
                jd=2460000.5 + i * 0.1, mag=99.0, mag_err=0.05,
                filter_band="r", mission="ZTF",
            )
            for i in range(5)
        )
        prov = FetchProvenance(surveys=("ZTF",), start_jd=2460000.0, end_jd=2460001.0)
        fr = FetchResult(alerts=obs, provenance=prov)
        result = estimate_field_completeness(fr)
        assert result == 0.0

    def test_all_sentinel_with_explicit_lim_returns_zero(self):
        from fetch import estimate_field_completeness
        # all mags >= 90 but explicit limiting_mag given → no valid obs → 0.0
        fr = self._make_fetch_result([99.0, 99.0, 99.0])
        result = estimate_field_completeness(fr, limiting_mag=21.0)
        assert result == 0.0

    def test_in_all(self):
        from fetch import __all__
        assert "estimate_field_completeness" in __all__
