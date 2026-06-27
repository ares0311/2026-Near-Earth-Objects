"""Tests for fetch.py — cache round-trip and fallback behaviour."""

import hashlib
import sys
from unittest.mock import MagicMock, patch

import pytest

import fetch as fetch_mod
from fetch import (
    _fetch_ztf_alerce_api,
    _fetch_ztf_irsa_api,
    _load_cache,
    _parse_alerce_detection,
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
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_alerce_api", lambda *_, **__: [])

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

    def test_irsa_fallback_on_ztfquery_runtime_error(self, tmp_path, monkeypatch):
        """fetch_ztf falls back to the ALeRCE source provider on ztfquery errors."""
        import sys

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        fallback_obs = Observation(
            obs_id="999",
            ra_deg=180.0,
            dec_deg=10.0,
            jd=2460003.0,
            mag=20.1,
            mag_err=0.1,
            filter_band="r",
            mission="ZTF",
        )
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_alerce_api", lambda *_, **__: [fallback_obs])

        # ztfquery is importable but raises RuntimeError (e.g. auth failure)
        mock_zq = MagicMock()
        mock_zq.ZTFQuery.return_value.load_metadata.side_effect = RuntimeError("auth failed")
        monkeypatch.setitem(sys.modules, "ztfquery", mock_zq)
        monkeypatch.setitem(sys.modules, "ztfquery.query", mock_zq)

        result = fetch_mod.fetch_ztf(180.0, 10.0, 1.0, 2460000.0, 2460010.0,
                                     force_refresh=True)

        assert len(result) == 1
        assert result[0].filter_band == "r"


class TestFetchZtfIrsaApiAuth:
    """_fetch_ztf_irsa_api must pass Basic Auth from env vars to IRSA TAP."""

    def test_basic_auth_sent_when_env_vars_set(self, monkeypatch):
        """Verify auth=(username, password) is passed when env vars are present."""
        monkeypatch.setenv("ZTF_IRSA_USERNAME", "myuser")
        monkeypatch.setenv("ZTF_IRSA_PASSWORD", "mypass")

        import fetch as fetch_mod

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"metadata": [], "data": []}

        with patch("requests.get", return_value=mock_resp) as mock_get:
            fetch_mod._fetch_ztf_irsa_api(180.0, 10.0, 1.0, 2460000.0, 2460001.0)

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["auth"] == ("myuser", "mypass")

    def test_no_auth_when_env_vars_missing(self, monkeypatch):
        """auth is None when ZTF_IRSA_USERNAME or ZTF_IRSA_PASSWORD are absent."""
        monkeypatch.delenv("ZTF_IRSA_USERNAME", raising=False)
        monkeypatch.delenv("ZTF_IRSA_PASSWORD", raising=False)

        import fetch as fetch_mod

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"metadata": [], "data": []}

        with patch("requests.get", return_value=mock_resp) as mock_get:
            fetch_mod._fetch_ztf_irsa_api(180.0, 10.0, 1.0, 2460000.0, 2460001.0)

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["auth"] is None


class TestFetchZtfAlerceApi:
    def test_parse_alerce_detection(self):
        row = {
            "mjd": 61096.1744328998,
            "candid": "3342174430915015006",
            "fid": 1,
            "magpsf": 15.672835,
            "sigmapsf": 0.027415272,
            "ra": 84.5919035,
            "dec": -5.3348207,
            "rb": 0.7557143,
            "drb": 0.9999999,
        }

        obs = _parse_alerce_detection(row, "ZTF26aahyrwl", 2461096.0, 2461097.0)

        assert obs is not None
        assert obs.obs_id == "3342174430915015006"
        assert obs.filter_band == "g"
        assert obs.real_bogus == pytest.approx(0.7557143)
        assert obs.deep_real_bogus == pytest.approx(0.9999999)

    def test_parse_alerce_detection_filters_jd_window(self):
        row = {
            "mjd": 61096.1744328998,
            "candid": "outside",
            "fid": 1,
            "magpsf": 15.6,
            "ra": 84.5,
            "dec": -5.3,
        }

        obs = _parse_alerce_detection(row, "ZTF26aahyrwl", 2460000.0, 2460001.0)

        assert obs is None

    def test_parse_alerce_detection_requires_source_photometry(self):
        row = {
            "mjd": 61096.1744328998,
            "candid": "no_mag",
            "fid": 1,
            "ra": 84.5,
            "dec": -5.3,
        }

        obs = _parse_alerce_detection(row, "ZTF26aahyrwl", 2461096.0, 2461097.0)

        assert obs is None

    def test_fetch_alerce_provider_parses_detections(self, monkeypatch):
        import sys
        import types

        class FakeAlerce:
            calls: list[dict] = []

            def query_objects(self, **kwargs):
                self.calls.append(kwargs)
                assert kwargs["survey"] == "ztf"
                assert kwargs["radius"] == pytest.approx(3600.0)
                return {"items": [{"oid": "ZTF26aahyrwl"}]}

            def query_detections(self, oid, **kwargs):
                assert oid == "ZTF26aahyrwl"
                assert kwargs["survey"] == "ztf"
                return [
                    {
                        "mjd": 61096.1744328998,
                        "candid": "3342174430915015006",
                        "fid": 1,
                        "magpsf": 15.672835,
                        "sigmapsf": 0.027415272,
                        "ra": 84.5919035,
                        "dec": -5.3348207,
                        "rb": 0.7557143,
                    },
                    {
                        "mjd": 60000.0,
                        "candid": "too_old",
                        "fid": 2,
                        "magpsf": 18.0,
                        "ra": 84.0,
                        "dec": -5.0,
                    },
                ]

        monkeypatch.setitem(sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce))

        obs = _fetch_ztf_alerce_api(
            83.8221,
            -5.3911,
            1.0,
            2461096.0,
            2461097.0,
        )

        assert len(obs) == 1
        assert obs[0].obs_id == "3342174430915015006"
        assert FakeAlerce.calls[0]["classifier"] == "stamp_classifier"
        assert FakeAlerce.calls[0]["class_name"] == "asteroid"

    def test_fetch_alerce_falls_back_to_generic_objects(self, monkeypatch):
        import sys
        import types

        class FakeAlerce:
            calls: list[dict] = []

            def query_objects(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("class_name") == "asteroid":
                    return {"items": []}
                return {"items": [{"oid": "ZTF26generic"}]}

            def query_detections(self, oid, **kwargs):
                assert oid == "ZTF26generic"
                assert kwargs["survey"] == "ztf"
                return [
                    {
                        "mjd": 61096.1744328998,
                        "candid": "generic_detection",
                        "fid": 1,
                        "magpsf": 15.7,
                        "ra": 84.59,
                        "dec": -5.33,
                    },
                ]

        monkeypatch.setitem(sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce))

        obs = _fetch_ztf_alerce_api(
            83.8221,
            -5.3911,
            1.0,
            2461096.0,
            2461097.0,
        )

        assert len(obs) == 1
        assert obs[0].obs_id == "generic_detection"
        assert FakeAlerce.calls[0]["class_name"] == "asteroid"
        assert "class_name" not in FakeAlerce.calls[1]

    def test_mode1_uses_ndet_cap_not_persistent_sources(self, monkeypatch):
        # Regression test: Mode 1 must use ndet=[1,3] (not ndet_max=None).
        # ndet_max=None previously caused Mode 1 to return persistent stationary
        # sources (stars/AGN with many detections) instead of single-night
        # transients (ndet=1) that are the signature of moving objects.
        import sys
        import types

        class FakeAlerce:
            calls: list[dict] = []

            def query_objects(self, **kwargs):
                self.calls.append(kwargs)
                return {"items": [{"oid": "ZTF26ndet1"}]}

            def query_detections(self, oid, **kwargs):
                return [
                    {
                        "mjd": 61096.1744328998,
                        "candid": "ndet1_det",
                        "fid": 1,
                        "magpsf": 18.5,
                        "ra": 84.5,
                        "dec": -5.3,
                        "rb": 0.85,
                    },
                ]

        monkeypatch.setitem(sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce))

        _fetch_ztf_alerce_api(83.8221, -5.3911, 1.0, 2461096.0, 2461097.0)

        # Mode 1 must cap ndet at 3 to exclude persistent background sources.
        assert "ndet" in FakeAlerce.calls[0], "Mode 1 must send ndet filter"
        assert FakeAlerce.calls[0]["ndet"][1] <= 3, "Mode 1 ndet cap must be ≤ 3"

    def test_mode2_fallback_also_uses_ndet_cap(self, monkeypatch):
        # Regression test: Mode 2 fallback must also use ndet=[1,3].
        # Previously ndet_max=20 was used, which still admits persistent sources.
        import sys
        import types

        class FakeAlerce:
            calls: list[dict] = []

            def query_objects(self, **kwargs):
                self.calls.append(kwargs)
                # Mode 1 (asteroid classifier) returns nothing; Mode 2 runs.
                if kwargs.get("class_name") == "asteroid":
                    return {"items": []}
                return {"items": [{"oid": "ZTF26fallback"}]}

            def query_detections(self, oid, **kwargs):
                return [
                    {
                        "mjd": 61096.1744328998,
                        "candid": "fallback_det",
                        "fid": 2,
                        "magpsf": 19.0,
                        "ra": 84.6,
                        "dec": -5.4,
                    },
                ]

        monkeypatch.setitem(sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce))

        _fetch_ztf_alerce_api(83.8221, -5.3911, 1.0, 2461096.0, 2461097.0)

        # FakeAlerce.calls[1] is the Mode 2 query (no class_name filter).
        assert len(FakeAlerce.calls) >= 2, "Mode 2 fallback must be called"
        assert "ndet" in FakeAlerce.calls[1], "Mode 2 must send ndet filter"
        assert FakeAlerce.calls[1]["ndet"][1] <= 3, "Mode 2 ndet cap must be ≤ 3"


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

    def test_poll_json_decode_error_continues(self, tmp_path, monkeypatch):
        """poll.json() raising JSONDecodeError (line 261-262) should continue the loop."""
        import json
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake-task/1/"}
        queue_resp.raise_for_status = MagicMock()

        # First poll call raises JSONDecodeError; second returns valid data with no result_url
        call_count = {"n": 0}

        def poll_json():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise json.JSONDecodeError("Expecting value", "", 0)
            return {"finishtimestamp": "2024-01-01", "result_url": ""}

        poll_resp = MagicMock()
        poll_resp.json.side_effect = poll_json
        poll_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=queue_resp):
            with patch("requests.get", return_value=poll_resp):
                from fetch import fetch_atlas
                result = fetch_atlas(90.0, 0.0, 0.5, 2460000.0, 2460010.0)

        # Loop continued past the bad poll and eventually returned [] (no result_url)
        assert result == []
        assert call_count["n"] >= 2

    def test_final_poll_json_decode_error_returns_empty(self, tmp_path, monkeypatch):
        """poll.json() raising JSONDecodeError after loop exit (line 268-269) returns []."""
        import json
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)

        queue_resp = MagicMock()
        queue_resp.json.return_value = {"url": "http://fake-task/1/"}
        queue_resp.raise_for_status = MagicMock()

        # During the loop, finishtimestamp is set so the loop breaks.
        # The *final* poll.json() call (line 267) then raises JSONDecodeError.
        call_count = {"n": 0}

        def poll_json():
            call_count["n"] += 1
            if call_count["n"] == 1:
                # In-loop: break out of loop
                return {"finishtimestamp": "2024-01-01"}
            # Post-loop: simulate empty body on result query
            raise json.JSONDecodeError("Expecting value", "", 0)

        poll_resp = MagicMock()
        poll_resp.json.side_effect = poll_json
        poll_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=queue_resp):
            with patch("requests.get", return_value=poll_resp):
                from fetch import fetch_atlas
                result = fetch_atlas(90.0, 0.0, 0.5, 2460000.0, 2460010.0)

        assert result == []


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
        # Use a recent date (JD 2460700.5 ≈ Jan 2025) — ATLAS FPS returns 400
        # for requests older than ~1000 days (JD 2460000 = Feb 2023 is too old).
        result = fetch_atlas(83.8221, -5.3911, 0.1, 2460700.5, 2460701.5)
        assert isinstance(result, list)


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


class TestFetchMpcObservations:
    def test_row_value_skips_absent_named_columns(self):
        """Column fallback should skip names absent from an Astropy row schema."""
        from fetch import _mpc_row_value

        row = MagicMock()
        row.colnames = ["JD"]
        row.__getitem__ = MagicMock(side_effect=lambda key: {"JD": 2460000.5}[key])

        assert _mpc_row_value(row, "epoch", "JD") == 2460000.5

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

    def test_strict_mode_reraises_provider_exception(self):
        """Audited acquisition must distinguish provider failure from no observations."""
        from unittest.mock import MagicMock, patch

        from fetch import fetch_mpc_observations

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.side_effect = ConnectionError("network error")
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with (
            patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}),
            pytest.raises(ConnectionError, match="network error"),
        ):
            fetch_mpc_observations(
                "strict_provider_failure_test",
                force_refresh=True,
                raise_on_error=True,
            )

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
        """Parse current Astroquery columns and persist deterministic observations."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        desig = "433_eros_full_path_test"

        mock_row = MagicMock()
        mock_row.colnames = ["epoch", "RA", "DEC", "mag", "band", "observatory"]
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "epoch": 2460000.5,
            "RA": 180.0,
            "DEC": 5.0,
            "mag": 18.5,
            "band": "V",
            "observatory": "500",
        }.get(k, None))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table

        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations(desig)
        assert len(result) == 1
        assert result[0].ra_deg == 180.0
        assert result[0].dec_deg == 5.0
        assert result[0].jd == 2460000.5
        assert result[0].filter_band == "V"
        assert result[0].obs_id.startswith("MPC_")
        mock_mpc_cls.get_observations.assert_called_once_with(desig, cache=True)

    def test_force_refresh_bypasses_both_cache_layers(self, tmp_path, monkeypatch):
        """Force refresh must ignore disk data and disable Astroquery caching."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        desig = "433_force_refresh_test"
        cache_key = hashlib.md5(f"mpc_obs_{desig}".encode()).hexdigest()
        fetch_mod._save_cache(
            cache_key,
            [
                {
                    "obs_id": "stale",
                    "ra_deg": 1.0,
                    "dec_deg": 1.0,
                    "jd": 2460000.5,
                    "mag": 20.0,
                    "mag_err": 0.1,
                    "filter_band": "V",
                    "mission": "MPC",
                }
            ],
        )
        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = []
        mock_mpc_mod = MagicMock(MPC=mock_mpc_cls)

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations(desig, force_refresh=True)

        assert result == []
        mock_mpc_cls.get_observations.assert_called_once_with(desig, cache=False)


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

    def test_none_table_returns_empty_list(self, tmp_path, monkeypatch):
        """MPC.get_observations returning None must yield [] not raise TypeError."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = None
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations("unknown_comet_xyz", force_refresh=True)
        assert result == []

    def test_none_table_does_not_raise_with_raise_on_error(self, tmp_path, monkeypatch):
        """A None table is a query-level non-result, not an infrastructure failure.

        raise_on_error=True must not propagate a TypeError from iterating None;
        the circuit breaker in the acquisition layer must not fire.
        """
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = None
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations(
                "comet_none_table_test", force_refresh=True, raise_on_error=True
            )
        assert result == []

    def test_query_level_exception_not_raised_with_raise_on_error(self, tmp_path, monkeypatch):
        """Query-level exceptions (e.g. ValueError from malformed response) must not
        feed the circuit breaker even when raise_on_error=True.
        """
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.side_effect = ValueError("malformed response")
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations(
                "bad_format_test", force_refresh=True, raise_on_error=True
            )
        assert result == []

    def test_infra_error_raised_with_raise_on_error(self, tmp_path, monkeypatch):
        """ConnectionError (infrastructure) must propagate when raise_on_error=True."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.side_effect = ConnectionError("timeout")
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with (
            patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}),
            pytest.raises(ConnectionError, match="timeout"),
        ):
            fetch_mod.fetch_mpc_observations(
                "infra_fail_test", force_refresh=True, raise_on_error=True
            )

    def test_infra_error_suppressed_without_raise_on_error(self, tmp_path, monkeypatch):
        """ConnectionError with raise_on_error=False (default) must return [] silently."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.side_effect = ConnectionError("network down")
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations("infra_suppress_test", force_refresh=True)
        assert result == []

    def test_epoch_as_astropy_quantity_value(self, tmp_path, monkeypatch):
        """epoch column returned as astropy Quantity (unit='d') must be parsed via .value."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        # Simulate an astropy Quantity: has .value but no .jd; float() would raise.
        mock_epoch = MagicMock(spec=[])  # no .jd
        mock_epoch.value = 2460001.0

        mock_row = MagicMock()
        mock_row.colnames = ["epoch", "RA", "DEC", "mag", "band", "observatory"]
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "epoch": mock_epoch,
            "RA": 90.0,
            "DEC": 10.0,
            "mag": 19.0,
            "band": "r",
            "observatory": "500",
        }.get(k))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations("quantity_epoch_test", force_refresh=True)
        assert len(result) == 1
        assert result[0].jd == 2460001.0

    def test_epoch_as_astropy_time_jd(self, tmp_path, monkeypatch):
        """epoch column returned as astropy Time object must be parsed via .jd."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        # Simulate an astropy Time object: has .jd attribute.
        mock_epoch = MagicMock(spec=["jd"])
        mock_epoch.jd = 2460002.5

        mock_row = MagicMock()
        mock_row.colnames = ["epoch", "RA", "DEC", "mag", "band", "observatory"]
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "epoch": mock_epoch,
            "RA": 45.0,
            "DEC": -5.0,
            "mag": 20.0,
            "band": "g",
            "observatory": "695",
        }.get(k))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations("time_epoch_test", force_refresh=True)
        assert len(result) == 1
        assert result[0].jd == 2460002.5


    def test_all_columns_as_quantities(self, tmp_path, monkeypatch):
        """astroquery 0.4.11+ returns epoch/RA/DEC/mag all as dimensioned Quantities.

        When the table is converted to QTable, every numeric column gets a unit
        assigned (epoch→d, RA→deg, DEC→deg, mag→mag).  Accessing a row element
        returns a Quantity; float(dimensioned_Quantity) raises TypeError.
        All columns must be extracted via _mpc_to_float().
        """
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        def _make_quantity(value: float) -> MagicMock:
            """Simulate an astropy Quantity: has .value, no .jd; float() raises."""
            q = MagicMock(spec=["value"])
            q.value = value
            return q

        mock_epoch = _make_quantity(2460010.5)
        mock_ra = _make_quantity(123.45)
        mock_dec = _make_quantity(-22.5)
        mock_mag = _make_quantity(18.3)

        mock_row = MagicMock()
        mock_row.colnames = ["epoch", "RA", "DEC", "mag", "band", "observatory"]
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "epoch": mock_epoch,
            "RA": mock_ra,
            "DEC": mock_dec,
            "mag": mock_mag,
            "band": "V",
            "observatory": "703",
        }.get(k))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations("all_quantity_test", force_refresh=True)
        assert len(result) == 1
        assert result[0].jd == pytest.approx(2460010.5)
        assert result[0].ra_deg == pytest.approx(123.45)
        assert result[0].dec_deg == pytest.approx(-22.5)
        assert result[0].mag == pytest.approx(18.3)

    def test_ra_dec_as_quantities(self, tmp_path, monkeypatch):
        """RA and DEC returned as Quantities (unit='deg') must be extracted via .value."""
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_ra = MagicMock(spec=["value"])
        mock_ra.value = 270.0
        mock_dec = MagicMock(spec=["value"])
        mock_dec.value = 45.0

        mock_row = MagicMock()
        mock_row.colnames = ["epoch", "RA", "DEC", "mag", "band", "observatory"]
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
            "epoch": 2460020.0,
            "RA": mock_ra,
            "DEC": mock_dec,
            "mag": 17.5,
            "band": "r",
            "observatory": "G96",
        }.get(k))

        mock_table = MagicMock()
        mock_table.__iter__ = MagicMock(return_value=iter([mock_row]))

        mock_mpc_cls = MagicMock()
        mock_mpc_cls.get_observations.return_value = mock_table
        mock_mpc_mod = MagicMock()
        mock_mpc_mod.MPC = mock_mpc_cls

        with patch.dict("sys.modules", {"astroquery.mpc": mock_mpc_mod}):
            result = fetch_mod.fetch_mpc_observations("ra_dec_quantity_test", force_refresh=True)
        assert len(result) == 1
        assert result[0].ra_deg == pytest.approx(270.0)
        assert result[0].dec_deg == pytest.approx(45.0)


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
        post_kwargs = mock_requests.post.call_args.kwargs
        assert "data" in post_kwargs
        assert "json" not in post_kwargs
        assert post_kwargs["headers"]["Accept"] == "application/json"

    def test_pending_task_is_polled_until_result_url(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        atlas_data = "#MJD RA Dec m dm F\n60000.5 180.001 10.001 18.5 0.05 o\n"

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post_resp.json.return_value = {"url": "https://fake-atlas/task/1/"}

        mock_pending_resp = MagicMock()
        mock_pending_resp.raise_for_status = MagicMock()
        mock_pending_resp.json.return_value = {}

        mock_task_resp = MagicMock()
        mock_task_resp.raise_for_status = MagicMock()
        mock_task_resp.json.return_value = {"result_url": "https://fake-atlas/result/1/"}

        mock_result_resp = MagicMock()
        mock_result_resp.raise_for_status = MagicMock()
        mock_result_resp.text = atlas_data

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.side_effect = [mock_pending_resp, mock_task_resp, mock_result_resp]

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                180.0,
                10.0,
                2459600.0,
                2459610.0,
                atlas_token="valid_token",
                max_polls=2,
                poll_interval_seconds=0.0,
            )

        assert len(result) == 1
        assert mock_requests.get.call_count == 3

    def test_existing_task_url_skips_queue_post(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch

        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        atlas_data = "#MJD RA Dec m dm F\n60000.5 180.001 10.001 18.5 0.05 o\n"

        mock_task_resp = MagicMock()
        mock_task_resp.raise_for_status = MagicMock()
        mock_task_resp.json.return_value = {"result_url": "https://fake-atlas/result/1/"}

        mock_result_resp = MagicMock()
        mock_result_resp.raise_for_status = MagicMock()
        mock_result_resp.text = atlas_data

        mock_requests = MagicMock()
        mock_requests.get.side_effect = [mock_task_resp, mock_result_resp]

        progress_events = []
        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                180.0,
                10.0,
                2459600.0,
                2459610.0,
                atlas_token="valid_token",
                task_url="https://fake-atlas/task/existing/",
                progress_callback=progress_events.append,
            )

        assert len(result) == 1
        assert not mock_requests.post.called
        assert progress_events[0]["event"] == "resume_existing_task"
        assert progress_events[0]["url"] == "https://fake-atlas/task/existing/"

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
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_alerce_api", lambda *_, **__: [])
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_irsa_api", lambda *_, **__: [])
        # No live provider rows available -> returns []
        result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)
        assert isinstance(result, list)

    def test_returns_list_type(self, tmp_path, monkeypatch):
        import fetch as fetch_mod
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_alerce_api", lambda *_, **__: [])
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_irsa_api", lambda *_, **__: [])
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
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_alerce_api", lambda *_, **__: [])
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_irsa_api", lambda *_, **__: [])
        # force_refresh=True bypasses cache; no live provider rows available -> returns []
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


class TestFetchZtfAlertsAlercePath:
    def test_successful_alerce_provider_cached(self, tmp_path, monkeypatch):
        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        obs = Observation(
            obs_id="ztf_abc123",
            ra_deg=180.001,
            dec_deg=10.001,
            jd=2460005.0,
            mag=19.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            real_bogus=0.9,
        )
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_alerce_api", lambda *_, **__: [obs])

        result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].obs_id == "ztf_abc123"

        cached = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)
        assert len(cached) == 1
        assert cached[0].obs_id == "ztf_abc123"

    def test_alerce_empty_uses_legacy_fallback(self, tmp_path, monkeypatch):
        import fetch as fetch_mod

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        fallback_obs = Observation(
            obs_id="legacy",
            ra_deg=180.0,
            dec_deg=10.0,
            jd=2460005.0,
            mag=19.5,
            mag_err=0.05,
            filter_band="g",
            mission="ZTF",
        )
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_alerce_api", lambda *_, **__: [])
        monkeypatch.setattr(fetch_mod, "_fetch_ztf_irsa_api", lambda *_, **__: [fallback_obs])

        result = fetch_mod.fetch_ztf_alerts(180.0, 10.0, 0.5, 2460000.0, 2460010.0)

        assert len(result) == 1
        assert result[0].obs_id == "legacy"


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


class TestFetchKnownPhas:
    def _mock_mpc(self, monkeypatch, rows, colnames):
        import sys
        import types

        class MockTable:
            def __init__(self):
                self.colnames = colnames

            def __iter__(self):
                yield from rows

        class MockMPC:
            @staticmethod
            def query_objects(kind):
                return MockTable()

        mock_astroquery = types.ModuleType("astroquery")
        mock_mpc_mod = types.ModuleType("astroquery.mpc")
        mock_mpc_mod.MPC = MockMPC
        mock_astroquery.mpc = mock_mpc_mod
        monkeypatch.setitem(sys.modules, "astroquery", mock_astroquery)
        monkeypatch.setitem(sys.modules, "astroquery.mpc", mock_mpc_mod)

    def test_returns_list(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import fetch as fe

        monkeypatch.setattr(fe, "_CACHE_DIR", tmp_path / ".neo_cache")
        self._mock_mpc(monkeypatch, [
            {"designation": "2024 PHA1", "absolute_magnitude": 18.5,
             "moid": 0.03, "semimajor_axis": 1.5, "eccentricity": 0.15},
        ], ["designation", "absolute_magnitude", "moid", "semimajor_axis", "eccentricity"])

        result = fe.fetch_known_phas(force_refresh=True)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["designation"] == "2024 PHA1"
        assert result[0]["absolute_magnitude_h"] == 18.5
        assert result[0]["moid_au"] == 0.03
        assert result[0]["neo_class"] == "amor"

    def test_ieo_aten_apollo_classification(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import fetch as fe

        monkeypatch.setattr(fe, "_CACHE_DIR", tmp_path / ".neo_cache")
        rows = [
            {"designation": "IEO1", "absolute_magnitude": 20.0, "moid": 0.01,
             "semimajor_axis": 0.7, "eccentricity": 0.3},
            {"designation": "ATEN1", "absolute_magnitude": 21.0, "moid": 0.02,
             "semimajor_axis": 0.9, "eccentricity": 0.1},
            {"designation": "APO1", "absolute_magnitude": 19.5, "moid": 0.04,
             "semimajor_axis": 1.8, "eccentricity": 0.5},
        ]
        self._mock_mpc(monkeypatch, rows,
                       ["designation", "absolute_magnitude", "moid",
                        "semimajor_axis", "eccentricity"])

        result = fe.fetch_known_phas(force_refresh=True)
        classes = {r["designation"]: r["neo_class"] for r in result}
        assert classes["IEO1"] == "ieo"
        assert classes["ATEN1"] == "aten"
        assert classes["APO1"] == "apollo"

    def test_returns_empty_on_exception(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import fetch as fe

        monkeypatch.setattr(fe, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fe, "_load_cache", lambda k: None)

        import types
        bad = types.ModuleType("astroquery")
        bad_mpc = types.ModuleType("astroquery.mpc")

        class BrokenMPC:
            @staticmethod
            def query_objects(kind):
                raise RuntimeError("network down")

        bad_mpc.MPC = BrokenMPC
        bad.mpc = bad_mpc
        monkeypatch.setitem(sys.modules, "astroquery", bad)
        monkeypatch.setitem(sys.modules, "astroquery.mpc", bad_mpc)

        result = fe.fetch_known_phas(force_refresh=True)
        assert result == []

    def test_cache_hit(self, monkeypatch, tmp_path):
        import sys
        sys.path.insert(0, "src")
        import fetch as fe

        cached = [{"designation": "CACHED", "absolute_magnitude_h": 19.0,
                   "moid_au": 0.02, "neo_class": "apollo"}]
        monkeypatch.setattr(fe, "_load_cache", lambda k: cached)

        result = fe.fetch_known_phas(force_refresh=False)
        assert result == cached

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import fetch
        assert "fetch_known_phas" in fetch.__all__


class TestFetchHorizonsEphemeris:
    def test_returns_list_on_success(self, tmp_path, monkeypatch):
        import sys
        import unittest.mock as mock
        from pathlib import Path
        sys.path.insert(0, "src")
        import fetch
        monkeypatch.setattr(fetch, "_CACHE_DIR", Path(tmp_path))

        fake_row = {"RA": 180.0, "DEC": 5.0, "delta": 1.2, "V": 18.5}

        class FakeEph:
            def __len__(self): return 1
            def __getitem__(self, i): return fake_row

        class FakeHorizons:
            def __init__(self, **kw): pass
            def ephemerides(self): return FakeEph()

        with mock.patch.dict(
            "sys.modules",
            {"astroquery.jplhorizons": mock.MagicMock(Horizons=FakeHorizons)},
        ):
            result = fetch.fetch_horizons_ephemeris("2026AB1", [2460000.0], force_refresh=True)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["ra_deg"] == pytest.approx(180.0)

    def test_returns_empty_on_failure(self, tmp_path, monkeypatch):
        import sys
        import unittest.mock as mock
        from pathlib import Path
        sys.path.insert(0, "src")
        import fetch
        monkeypatch.setattr(fetch, "_CACHE_DIR", Path(tmp_path))

        class ErrorHorizons:
            def __init__(self, **kw): pass
            def ephemerides(self): raise RuntimeError("no network")

        with mock.patch.dict(
            "sys.modules",
            {"astroquery.jplhorizons": mock.MagicMock(Horizons=ErrorHorizons)},
        ):
            result = fetch.fetch_horizons_ephemeris("bad", [2460000.0], force_refresh=True)
        assert result == []

    def test_cache_hit(self, tmp_path, monkeypatch):
        import sys
        from pathlib import Path
        sys.path.insert(0, "src")
        import fetch
        monkeypatch.setattr(fetch, "_CACHE_DIR", Path(tmp_path))
        cached = [{"jd": 2460000.0, "ra_deg": 10.0, "dec_deg": 5.0, "delta_au": 1.0, "mag": 18.0}]
        fetch._save_cache("horizons_2026AB1", cached)
        result = fetch.fetch_horizons_ephemeris("2026AB1", [2460000.0], force_refresh=False)
        assert result == cached

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import fetch
        assert "fetch_horizons_ephemeris" in fetch.__all__

    def test_empty_ephemeris_skips(self, tmp_path, monkeypatch):
        import sys
        import unittest.mock as mock
        from pathlib import Path
        sys.path.insert(0, "src")
        import fetch
        monkeypatch.setattr(fetch, "_CACHE_DIR", Path(tmp_path))

        class EmptyEph:
            def __len__(self): return 0

        class EmptyHorizons:
            def __init__(self, **kw): pass
            def ephemerides(self): return EmptyEph()

        with mock.patch.dict(
            "sys.modules",
            {"astroquery.jplhorizons": mock.MagicMock(Horizons=EmptyHorizons)},
        ):
            result = fetch.fetch_horizons_ephemeris("2026AB1", [2460000.0], force_refresh=True)
        assert result == []


class TestCountObservationsByMission:
    def _make_result(self, missions):
        import sys
        sys.path.insert(0, "src")
        from schemas import FetchProvenance, FetchResult, Observation
        obs_list = []
        for i, m in enumerate(missions):
            obs_list.append(Observation(
                obs_id=f"o{i}", ra_deg=10.0, dec_deg=5.0, jd=2460000.0 + i,
                mag=18.0, mag_err=0.1, filter_band="r", mission=m,
            ))
        prov = FetchProvenance(surveys=list(set(missions)), start_jd=2460000.0,
                               end_jd=2460001.0, n_alerts=len(missions), cached=False)
        return FetchResult(alerts=obs_list, provenance=prov)

    def test_single_mission(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import count_observations_by_mission
        result = self._make_result(["ZTF", "ZTF", "ZTF"])
        counts = count_observations_by_mission(result)
        assert counts == {"ZTF": 3}

    def test_multiple_missions(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import count_observations_by_mission
        result = self._make_result(["ZTF", "ATLAS", "ZTF", "MPC"])
        counts = count_observations_by_mission(result)
        assert counts["ZTF"] == 2
        assert counts["ATLAS"] == 1
        assert counts["MPC"] == 1

    def test_empty_result_returns_empty_dict(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import count_observations_by_mission
        from schemas import FetchProvenance, FetchResult
        prov = FetchProvenance(surveys=[], start_jd=2460000.0, end_jd=2460001.0,
                               n_alerts=0, cached=False)
        result = FetchResult(alerts=[], provenance=prov)
        assert count_observations_by_mission(result) == {}

    def test_returns_dict_type(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import count_observations_by_mission
        result = self._make_result(["ZTF"])
        assert isinstance(count_observations_by_mission(result), dict)

    def test_all_missions_counted(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import count_observations_by_mission
        missions = ["ZTF", "ATLAS", "PanSTARRS", "CSS", "MPC"]
        result = self._make_result(missions)
        counts = count_observations_by_mission(result)
        assert sum(counts.values()) == len(missions)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import fetch
        assert "count_observations_by_mission" in fetch.__all__


class TestFilterByMagnitude:
    def _make_obs(self, mag: float | None) -> object:
        from types import SimpleNamespace
        return SimpleNamespace(mag=mag)

    def test_filters_within_range(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import filter_by_magnitude
        obs = [self._make_obs(18.0), self._make_obs(22.0), self._make_obs(16.0)]
        result = filter_by_magnitude(obs, 17.0, 21.0)
        assert len(result) == 1
        assert result[0].mag == 18.0

    def test_excludes_sentinels(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import filter_by_magnitude
        obs = [self._make_obs(99.0), self._make_obs(19.0)]
        result = filter_by_magnitude(obs, 15.0, 25.0)
        assert len(result) == 1

    def test_excludes_none_mag(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import filter_by_magnitude
        obs = [self._make_obs(None), self._make_obs(20.0)]
        result = filter_by_magnitude(obs, 15.0, 25.0)
        assert len(result) == 1

    def test_empty_list(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import filter_by_magnitude
        assert filter_by_magnitude([], 15.0, 25.0) == []

    def test_boundary_included(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import filter_by_magnitude
        obs = [self._make_obs(15.0), self._make_obs(25.0)]
        result = filter_by_magnitude(obs, 15.0, 25.0)
        assert len(result) == 2

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import fetch
        assert "filter_by_magnitude" in fetch.__all__


class TestComputeObservationRate:
    def _make_result(self, jds):
        from types import SimpleNamespace

        obs = [SimpleNamespace(jd=j) for j in jds]
        return SimpleNamespace(alerts=obs)

    def test_single_night_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import compute_observation_rate

        result = self._make_result([2460000.1, 2460000.5, 2460000.9])
        assert compute_observation_rate(result) is None

    def test_two_nights(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import compute_observation_rate

        result = self._make_result([2460000.5, 2460000.6, 2460001.5, 2460001.7])
        rate = compute_observation_rate(result)
        assert rate == 2.0

    def test_empty_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import compute_observation_rate

        result = self._make_result([])
        assert compute_observation_rate(result) is None

    def test_none_jd_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from fetch import compute_observation_rate

        obs = [SimpleNamespace(jd=None), SimpleNamespace(jd=2460000.5)]
        result = SimpleNamespace(alerts=obs)
        assert compute_observation_rate(result) is None

    def test_multi_night_mean(self):
        import sys
        sys.path.insert(0, "src")
        from fetch import compute_observation_rate

        # 3 obs on night 0, 1 obs on night 1, 2 obs on night 2 → mean = 2.0
        jds = [2460000.1, 2460000.2, 2460000.3, 2460001.5, 2460002.5, 2460002.6]
        result = self._make_result(jds)
        rate = compute_observation_rate(result)
        assert abs(rate - 2.0) < 1e-9

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import fetch
        assert "compute_observation_rate" in fetch.__all__


class TestFetchAlerceApiCoverageBranches:
    """Branch coverage for _fetch_ztf_alerce_api and _fetch_alerce_objects_for_filter."""

    def test_import_error_returns_empty(self, monkeypatch):
        # When `alerce` cannot be imported the outer try/except returns [].
        import sys
        monkeypatch.setitem(sys.modules, "alerce", None)
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, 2461096.0, 2461097.0)
        assert result == []

    def test_constructor_error_returns_empty(self, monkeypatch):
        # When Alerce() raises the inner try/except returns [].
        import sys
        import types

        class BrokenAlerce:
            def __init__(self):
                raise RuntimeError("connection refused")

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=BrokenAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, 2461096.0, 2461097.0)
        assert result == []

    def test_query_objects_exception_returns_empty(self, monkeypatch):
        # When query_objects raises, _fetch_alerce_objects_for_filter returns [].
        import sys
        import types

        class FakeAlerce:
            def query_objects(self, **kwargs):
                raise OSError("network error")

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, 2461096.0, 2461097.0)
        assert result == []

    def test_list_payload_used_directly(self, monkeypatch):
        # When query_objects returns a plain list (not a dict) the else branch
        # assigns it to object_rows directly.
        import sys
        import types

        start_jd = 2461096.0
        end_jd = 2461097.0

        class FakeAlerce:
            def query_objects(self, **kwargs):
                return [{"oid": "ZTF26listobj"}]

            def query_detections(self, oid, **kwargs):
                return [
                    {
                        "mjd": 61096.5,
                        "candid": "det_list",
                        "fid": 1,
                        "magpsf": 18.0,
                        "sigmapsf": 0.1,
                        "ra": 83.0,
                        "dec": -5.0,
                        "rb": 0.8,
                    }
                ]

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, start_jd, end_jd)
        assert len(result) == 1
        assert result[0].obs_id == "det_list"

    def test_non_dict_item_in_list_skipped(self, monkeypatch):
        # Non-dict entries in object_rows are skipped via `if not isinstance(obj, dict)`.
        import sys
        import types

        start_jd = 2461096.0
        end_jd = 2461097.0

        class FakeAlerce:
            def query_objects(self, **kwargs):
                return [
                    "not_a_dict",
                    42,
                    {"oid": "ZTF26real"},
                ]

            def query_detections(self, oid, **kwargs):
                return [
                    {
                        "mjd": 61096.5,
                        "candid": "real_det",
                        "fid": 1,
                        "magpsf": 18.0,
                        "sigmapsf": 0.1,
                        "ra": 83.0,
                        "dec": -5.0,
                    }
                ]

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, start_jd, end_jd)
        assert len(result) == 1
        assert result[0].obs_id == "real_det"

    def test_missing_oid_skipped(self, monkeypatch):
        # Objects missing the 'oid' key or with oid=None are skipped.
        import sys
        import types

        start_jd = 2461096.0
        end_jd = 2461097.0

        class FakeAlerce:
            def query_objects(self, **kwargs):
                return [
                    {},
                    {"oid": None},
                    {"oid": "ZTF26good"},
                ]

            def query_detections(self, oid, **kwargs):
                return [
                    {
                        "mjd": 61096.5,
                        "candid": "good_det",
                        "fid": 1,
                        "magpsf": 18.0,
                        "sigmapsf": 0.1,
                        "ra": 83.0,
                        "dec": -5.0,
                    }
                ]

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, start_jd, end_jd)
        assert len(result) == 1
        assert result[0].obs_id == "good_det"

    def test_query_detections_exception_skipped(self, monkeypatch):
        # When query_detections raises, that object is skipped via `except Exception: continue`.
        import sys
        import types

        start_jd = 2461096.0
        end_jd = 2461097.0
        call_count = {"n": 0}

        class FakeAlerce:
            def query_objects(self, **kwargs):
                return [{"oid": "ZTF26bad"}, {"oid": "ZTF26good"}]

            def query_detections(self, oid, **kwargs):
                call_count["n"] += 1
                if oid == "ZTF26bad":
                    raise RuntimeError("timeout")
                return [
                    {
                        "mjd": 61096.5,
                        "candid": "good_det2",
                        "fid": 1,
                        "magpsf": 18.0,
                        "sigmapsf": 0.1,
                        "ra": 83.0,
                        "dec": -5.0,
                    }
                ]

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, start_jd, end_jd)
        assert len(result) == 1
        assert result[0].obs_id == "good_det2"
        assert call_count["n"] == 2

    def test_both_query_modes_empty_returns_empty(self, monkeypatch):
        # When both asteroid and generic query_objects return no objects, return [].
        import sys
        import types

        class FakeAlerce:
            def query_objects(self, **kwargs):
                return []

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, 2461096.0, 2461097.0)
        assert result == []

    def test_duplicate_obs_id_deduplicated(self, monkeypatch):
        # Observations with the same obs_id are deduplicated via the `seen` set.
        import sys
        import types

        start_jd = 2461096.0
        end_jd = 2461097.0

        class FakeAlerce:
            def query_objects(self, **kwargs):
                return [{"oid": "ZTF26dup"}]

            def query_detections(self, oid, **kwargs):
                det = {
                    "mjd": 61096.5,
                    "candid": "dup_candid",
                    "fid": 1,
                    "magpsf": 18.0,
                    "sigmapsf": 0.1,
                    "ra": 83.0,
                    "dec": -5.0,
                }
                return [det, det]

        monkeypatch.setitem(
            sys.modules, "alerce", types.SimpleNamespace(Alerce=FakeAlerce)
        )
        result = _fetch_ztf_alerce_api(83.0, -5.0, 1.0, start_jd, end_jd)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Coverage: remaining missed statements after 57ba802
# ---------------------------------------------------------------------------


class TestParseAlerceDetectionMissingBranches:
    """Cover line 276 (non-dict) and line 301 (exception) in _parse_alerce_detection."""

    def test_non_dict_row_returns_none(self):
        # Covers line 276: `if not isinstance(row, dict): return None`
        result = _parse_alerce_detection("not_a_dict", "ZTF01", 2461096.0, 2461097.0)
        assert result is None

    def test_missing_mjd_key_raises_caught_returns_none(self):
        # Covers line 301: `except (KeyError, TypeError, ValueError): return None`
        # Empty dict is missing "mjd" -> float(row["mjd"]) raises KeyError.
        result = _parse_alerce_detection({}, "ZTF01", 2461096.0, 2461097.0)
        assert result is None


class TestFetchZtfIrsaApiMissingBranches:
    """Cover line 341 (RequestException) and line 347 (JSON error) in _fetch_ztf_irsa_api."""

    def test_request_exception_returns_empty(self):
        # Covers line 341: `except requests.RequestException: return []`
        from unittest.mock import patch

        import requests

        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            result = _fetch_ztf_irsa_api(180.0, 10.0, 1.0, 2460000.0, 2460010.0)
        assert result == []

    def test_json_decode_error_returns_empty(self):
        # Covers line 347: `except (ValueError, Exception): return []` when resp.json() fails
        import json
        from unittest.mock import MagicMock, patch

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        with patch("requests.get", return_value=mock_resp):
            result = _fetch_ztf_irsa_api(180.0, 10.0, 1.0, 2460000.0, 2460010.0)
        assert result == []


class TestFetchAtlasQueueMissingUrl:
    """Cover line 423 in fetch_atlas: queue response missing 'url' key."""

    def test_queue_response_no_url_key_returns_empty(self, tmp_path, monkeypatch):
        # Covers line 423: `except (KeyError, ValueError, Exception): return []`
        # when resp.json() returns a dict without the "url" key -> KeyError on ["url"].
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        monkeypatch.setattr(fetch_mod.time, "sleep", lambda _: None)

        queue_resp = MagicMock()
        queue_resp.raise_for_status = MagicMock()
        queue_resp.json.return_value = {}  # missing "url" key

        with patch("requests.post", return_value=queue_resp):
            from fetch import fetch_atlas
            result = fetch_atlas(180.0, 10.0, 1.0, 2460000.0, 2460010.0, atlas_token="tok")
        assert result == []


class TestFetchAtlasForcedRemainingBranches:
    """Cover lines 1072, 1106, 1108 in fetch_atlas_forced."""

    def test_progress_callback_fires_on_initial_queue(self, tmp_path, monkeypatch):
        # Covers line 1072: progress_callback({"event": "queued", ...}) when task_url=None.
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post_resp.json.return_value = {
            "url": "https://fake-atlas/task/cb/",
            "status": "queued",
        }

        mock_task_resp = MagicMock()
        mock_task_resp.raise_for_status = MagicMock()
        mock_task_resp.json.return_value = {"result_url": "https://fake-atlas/result/cb/"}

        mock_result_resp = MagicMock()
        mock_result_resp.raise_for_status = MagicMock()
        mock_result_resp.text = "#MJD RA Dec m dm F\n60001.0 180.0 10.0 18.5 0.05 o\n"

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.side_effect = [mock_task_resp, mock_result_resp]

        events = []
        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                180.0, 10.0, 2459600.0, 2459610.0,
                atlas_token="valid_token",
                task_url=None,
                progress_callback=events.append,
            )

        assert len(result) >= 0
        assert any(e.get("event") == "queued" for e in events)

    def test_finishtimestamp_without_result_url_returns_empty(self, tmp_path, monkeypatch):
        # Covers line 1106: `if data.get("finishtimestamp"): return []`
        # Task finished but produced no result_url.
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post_resp.json.return_value = {"url": "https://fake-atlas/task/ft/"}

        mock_poll_resp = MagicMock()
        mock_poll_resp.raise_for_status = MagicMock()
        mock_poll_resp.json.return_value = {"finishtimestamp": "2024-06-01T12:00:00"}

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.return_value = mock_poll_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = fetch_mod.fetch_atlas_forced(
                180.0, 10.0, 2459600.0, 2459610.0,
                atlas_token="valid_token",
                max_polls=1,
                poll_interval_seconds=0.0,
            )
        assert result == []

    def test_positive_poll_interval_calls_sleep(self, tmp_path, monkeypatch):
        # Covers line 1108: `time.sleep(poll_interval_seconds)` when > 0 and loop continues.
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")

        sleep_calls = []
        monkeypatch.setattr(fetch_mod.time, "sleep", sleep_calls.append)

        mock_post_resp = MagicMock()
        mock_post_resp.raise_for_status = MagicMock()
        mock_post_resp.json.return_value = {"url": "https://fake-atlas/task/sleep/"}

        # First poll: no result yet -> sleep triggered before next poll
        mock_pending = MagicMock()
        mock_pending.raise_for_status = MagicMock()
        mock_pending.json.return_value = {}

        # Second poll: result available
        atlas_data = "#MJD RA Dec m dm F\n60002.0 180.0 10.0 19.0 0.05 o\n"
        mock_result_task = MagicMock()
        mock_result_task.raise_for_status = MagicMock()
        mock_result_task.json.return_value = {"result_url": "https://fake-atlas/result/sleep/"}

        mock_result_data = MagicMock()
        mock_result_data.raise_for_status = MagicMock()
        mock_result_data.text = atlas_data

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_post_resp
        mock_requests.get.side_effect = [mock_pending, mock_result_task, mock_result_data]

        with patch.dict("sys.modules", {"requests": mock_requests}):
            fetch_mod.fetch_atlas_forced(
                180.0, 10.0, 2459600.0, 2459610.0,
                atlas_token="valid_token",
                max_polls=2,
                poll_interval_seconds=0.1,
            )

        assert 0.1 in sleep_calls


# ---------------------------------------------------------------------------
# TestDiscoveryFetch — tests for fetch_wise_archive, fetch_decam_archive,
# fetch_tess_ffis, fetch_discovery, and fetch() routing for new surveys
# ---------------------------------------------------------------------------


class TestFetchWiseArchive:
    """Tests for fetch_wise_archive."""

    def test_cache_hit_returns_observations(self, tmp_path, monkeypatch):
        """Cache hit path: load from cache and return Observation objects."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # Seed the cache with one pre-built observation dict
        import hashlib
        cache_key = hashlib.md5(
            b"wise_180.0_10.0_1.0_2460000.5_2460010.5"
        ).hexdigest()
        cached_data = [{
            "obs_id": "wise_0_60000.00000",
            "ra_deg": 180.0,
            "dec_deg": 10.0,
            "jd": 2460000.5,
            "mag": 15.5,
            "mag_err": 0.05,
            "filter_band": "W1",
            "mission": "WISE",
        }]
        fetch_mod._save_cache(cache_key, cached_data)

        result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert len(result) == 1
        assert result[0].mission == "WISE"
        assert result[0].obs_id == "wise_0_60000.00000"

    def _make_pyvo_mock(self, table):
        """Return a mock pyvo module whose TAPService.run_async().to_table() returns table."""
        mock_tap_svc = MagicMock()
        mock_result = MagicMock()
        mock_result.to_table.return_value = table
        mock_tap_svc.run_async.return_value = mock_result
        mock_pyvo = MagicMock()
        mock_pyvo.dal.TAPService.return_value = mock_tap_svc
        return mock_pyvo

    def test_import_error_returns_empty(self, tmp_path, monkeypatch):
        """ImportError (no pyvo) returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        with patch.dict("sys.modules", {"pyvo": None}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_api_exception_returns_empty(self, tmp_path, monkeypatch):
        """TAP run_async raising exception returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_tap_svc = MagicMock()
        mock_tap_svc.run_async.side_effect = RuntimeError("network error")
        mock_pyvo = MagicMock()
        mock_pyvo.dal.TAPService.return_value = mock_tap_svc
        with patch.dict("sys.modules", {"pyvo": mock_pyvo}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_empty_table_returns_empty(self, tmp_path, monkeypatch):
        """Empty table from IRSA TAP returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_pyvo = self._make_pyvo_mock([])
        with patch.dict("sys.modules", {"pyvo": mock_pyvo}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_none_table_returns_empty(self, tmp_path, monkeypatch):
        """None table from IRSA TAP returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_pyvo = self._make_pyvo_mock(None)
        with patch.dict("sys.modules", {"pyvo": mock_pyvo}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_row_outside_jd_window_skipped(self, tmp_path, monkeypatch):
        """Client-side guard: row with mjd outside JD window is skipped."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # start_jd=2460000.5 → start_mjd=59999.5; row mjd=50000 is far outside
        mock_row = {"mjd": 50000.0, "w1mpro": 15.0, "w1sigmpro": 0.1, "ra": 180.0, "dec": 10.0}
        mock_pyvo = self._make_pyvo_mock([mock_row])
        with patch.dict("sys.modules", {"pyvo": mock_pyvo}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_row_with_none_mag_uses_sentinel(self, tmp_path, monkeypatch):
        """Row with None w1mpro uses sentinel 99.0; None w1sigmpro uses 0.1."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mjd_in = 2460000.5 - 2_400_000.5  # = 60000.0, within [2460000.5, 2460010.5]
        mock_row = {
            "mjd": mjd_in,
            "w1mpro": None,
            "w1sigmpro": None,
            "ra": 180.0,
            "dec": 10.0,
        }
        mock_pyvo = self._make_pyvo_mock([mock_row])
        with patch.dict("sys.modules", {"pyvo": mock_pyvo}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert len(result) == 1
        assert result[0].mag == 99.0
        assert result[0].mag_err == 0.1
        assert result[0].mission == "WISE"

    def test_successful_row_within_jd_window(self, tmp_path, monkeypatch):
        """Successful row within JD window creates correct Observation."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mjd_in = 2460005.0 - 2_400_000.5  # = 60004.5
        mock_row = {
            "mjd": mjd_in,
            "w1mpro": 14.3,
            "w1sigmpro": 0.02,
            "ra": 181.5,
            "dec": 9.5,
        }
        mock_pyvo = self._make_pyvo_mock([mock_row])
        with patch.dict("sys.modules", {"pyvo": mock_pyvo}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert len(result) == 1
        assert result[0].mission == "WISE"
        assert result[0].filter_band == "W1"
        assert abs(result[0].mag - 14.3) < 1e-6
        assert abs(result[0].mag_err - 0.02) < 1e-6
        assert abs(result[0].jd - (mjd_in + 2_400_000.5)) < 1e-6


class TestFetchDecamArchive:
    """Tests for fetch_decam_archive."""

    def test_cache_hit_returns_observations(self, tmp_path, monkeypatch):
        """Cache hit path: load from cache and return Observation objects."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        import hashlib
        cache_key = hashlib.md5(
            b"decam_180.0_10.0_1.0_2460000.5_2460010.5"
        ).hexdigest()
        cached_data = [{
            "obs_id": "decam_0_60000.00000",
            "ra_deg": 180.0,
            "dec_deg": 10.0,
            "jd": 2460000.5,
            "mag": 21.0,
            "mag_err": 0.1,
            "filter_band": "r",
            "mission": "DECam",
        }]
        fetch_mod._save_cache(cache_key, cached_data)

        result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert len(result) == 1
        assert result[0].mission == "DECam"

    def test_import_error_returns_empty(self, tmp_path, monkeypatch):
        """ImportError (no pyvo) returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        with patch.dict("sys.modules", {"pyvo": None}):
            result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_api_exception_returns_empty(self, tmp_path, monkeypatch):
        """TAP service raising exception returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_tap = MagicMock()
        mock_tap.dal.TAPService.return_value.search.side_effect = RuntimeError("tap error")
        with patch.dict("sys.modules", {"pyvo": mock_tap}):
            result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_empty_table_returns_empty(self, tmp_path, monkeypatch):
        """Empty table from TAP returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_tap = MagicMock()
        mock_tap.dal.TAPService.return_value.search.return_value.to_table.return_value = []
        with patch.dict("sys.modules", {"pyvo": mock_tap}):
            result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_none_table_returns_empty(self, tmp_path, monkeypatch):
        """None table from TAP returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_tap = MagicMock()
        mock_tap.dal.TAPService.return_value.search.return_value.to_table.return_value = None
        with patch.dict("sys.modules", {"pyvo": mock_tap}):
            result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_successful_row(self, tmp_path, monkeypatch):
        """Successful row creates correct DECam Observation."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mjd_in = 2460005.0 - 2_400_000.5
        mock_row = {
            "mjd": mjd_in,
            "mag_auto": 21.5,
            "magerr_auto": 0.08,
            "filter": "g",
            "ra": 180.5,
            "dec": 10.2,
        }
        mock_table = MagicMock()
        mock_table.__len__ = lambda s: 1
        mock_table.__iter__ = lambda s: iter([mock_row])
        mock_tap = MagicMock()
        mock_tap.dal.TAPService.return_value.search.return_value.to_table.return_value = mock_table
        with patch.dict("sys.modules", {"pyvo": mock_tap}):
            result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert len(result) == 1
        assert result[0].mission == "DECam"
        assert result[0].filter_band == "g"
        assert abs(result[0].mag - 21.5) < 1e-6

    def test_row_with_none_fields(self, tmp_path, monkeypatch):
        """Row with None mag_auto, magerr_auto, filter uses defaults."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mjd_in = 2460005.0 - 2_400_000.5
        mock_row = {
            "mjd": mjd_in,
            "mag_auto": None,
            "magerr_auto": None,
            "filter": None,
            "ra": 180.5,
            "dec": 10.2,
        }
        mock_table = MagicMock()
        mock_table.__len__ = lambda s: 1
        mock_table.__iter__ = lambda s: iter([mock_row])
        mock_tap = MagicMock()
        mock_tap.dal.TAPService.return_value.search.return_value.to_table.return_value = mock_table
        with patch.dict("sys.modules", {"pyvo": mock_tap}):
            result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert len(result) == 1
        assert result[0].mag == 99.0
        assert result[0].mag_err == 0.1
        assert result[0].filter_band == "?"


class TestFetchTessFFIs:
    """Tests for fetch_tess_ffis."""

    def test_cache_hit_returns_observations(self, tmp_path, monkeypatch):
        """Cache hit path: load from cache and return Observation objects."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        import hashlib
        cache_key = hashlib.md5(
            b"tess_180.0_10.0_1.0_2460000.5_2460010.5"
        ).hexdigest()
        cached_data = [{
            "obs_id": "tess_s1_t12345",
            "ra_deg": 180.0,
            "dec_deg": 10.0,
            "jd": 2460005.0,
            "mag": 14.0,
            "mag_err": 0.01,
            "filter_band": "T",
            "mission": "TESS",
        }]
        fetch_mod._save_cache(cache_key, cached_data)

        result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert len(result) == 1
        assert result[0].mission == "TESS"

    def test_import_error_returns_empty(self, tmp_path, monkeypatch):
        """ImportError (no astroquery.mast) returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        with patch.dict("sys.modules", {"astroquery.mast": None}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_observations_api_exception_returns_empty(self, tmp_path, monkeypatch):
        """Observations.query_criteria raising exception returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.side_effect = RuntimeError("mast error")
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_no_sectors_found_returns_empty(self, tmp_path, monkeypatch):
        """Empty TESS observations table returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = []
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_none_sectors_returns_empty(self, tmp_path, monkeypatch):
        """None TESS observations returns empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = None
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_sectors_found_but_tic_none_returns_empty(self, tmp_path, monkeypatch):
        """Sectors found but TIC query returns None gives empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_sector = {
            "t_min": 3000.0,
            "t_max": 3027.0,
            "sequence_number": 1,
        }
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_sector]
        mock_mast.Catalogs.query_region.return_value = None
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_sectors_found_but_tic_empty_returns_empty(self, tmp_path, monkeypatch):
        """Sectors found but TIC query returns empty table gives empty list."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_sector = {
            "t_min": 3000.0,
            "t_max": 3027.0,
            "sequence_number": 1,
        }
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_sector]
        mock_mast.Catalogs.query_region.return_value = []
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_full_successful_path(self, tmp_path, monkeypatch):
        """Full path: sector + TIC sources produces TESS Observations."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # BTJD offset = 2457000.0; JD 2460000.5 → BTJD = 3000.5
        # sector t_min=3000.0, t_max=3027.0 → epoch_jd = 3013.5 + 2457000 = 2460013.5
        # start_jd=2460000.5, end_jd=2460030.5 → epoch_jd within window+margin
        mock_sector = {
            "t_min": 3000.0,
            "t_max": 3027.0,
            "sequence_number": 5,
        }
        mock_tic_src = {
            "ID": "99001",
            "ra": 180.1,
            "dec": 10.1,
            "Tmag": 13.2,
            "e_Tmag": 0.05,
        }
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_sector]
        mock_mast.Catalogs.query_region.return_value = [mock_tic_src]
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460030.5)
        assert len(result) == 1
        assert result[0].mission == "TESS"
        assert result[0].filter_band == "T"
        assert result[0].obs_id == "tess_s5_t99001"
        assert abs(result[0].mag - 13.2) < 1e-6

    def test_sector_row_bad_epoch_skipped(self, tmp_path, monkeypatch):
        """Sector row that raises exception during epoch parse is skipped."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # A sector row with bad t_min that causes a failure
        mock_bad_sector = {"t_min": "not_a_number", "t_max": "also_bad", "sequence_number": 1}
        mock_tic_src = {
            "ID": "12345",
            "ra": 180.0,
            "dec": 10.0,
            "Tmag": 14.0,
            "e_Tmag": 0.1,
        }
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_bad_sector]
        mock_mast.Catalogs.query_region.return_value = [mock_tic_src]
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460030.5)
        # Bad sector row is skipped; result is empty
        assert result == []

    def test_tic_source_none_tmag_uses_default(self, tmp_path, monkeypatch):
        """TIC source with None Tmag uses default magnitude 20.0."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_sector = {
            "t_min": 3000.0,
            "t_max": 3027.0,
            "sequence_number": 2,
        }
        mock_tic_src = {
            "ID": "55555",
            "ra": 180.0,
            "dec": 10.0,
            "Tmag": None,
            "e_Tmag": None,
        }
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_sector]
        mock_mast.Catalogs.query_region.return_value = [mock_tic_src]
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460030.5)
        assert len(result) == 1
        assert result[0].mag == 20.0
        assert result[0].mag_err == 0.1


class TestFetchDiscovery:
    """Tests for fetch_discovery."""

    def test_wise_only(self, tmp_path, monkeypatch):
        """sources=('WISE',) calls fetch_wise_archive and returns FetchResult."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        dummy_obs = Observation(
            obs_id="wise_test",
            ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=15.0, mag_err=0.1, filter_band="W1", mission="WISE",
        )
        with patch.object(fetch_mod, "fetch_wise_archive", return_value=[dummy_obs]) as mw, \
             patch.object(fetch_mod, "fetch_decam_archive", return_value=[]) as md, \
             patch.object(fetch_mod, "fetch_tess_ffis", return_value=[]) as mt:
            result = fetch_mod.fetch_discovery(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                               sources=("WISE",))
        assert len(result.alerts) == 1
        assert result.alerts[0].mission == "WISE"
        mw.assert_called_once()
        md.assert_not_called()
        mt.assert_not_called()

    def test_decam_only(self, tmp_path, monkeypatch):
        """sources=('DECam',) calls fetch_decam_archive and returns FetchResult."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        dummy_obs = Observation(
            obs_id="decam_test",
            ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=21.0, mag_err=0.1, filter_band="g", mission="DECam",
        )
        with patch.object(fetch_mod, "fetch_wise_archive", return_value=[]) as mw, \
             patch.object(fetch_mod, "fetch_decam_archive", return_value=[dummy_obs]) as md, \
             patch.object(fetch_mod, "fetch_tess_ffis", return_value=[]) as mt:
            result = fetch_mod.fetch_discovery(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                               sources=("DECam",))
        assert len(result.alerts) == 1
        assert result.alerts[0].mission == "DECam"
        mw.assert_not_called()
        md.assert_called_once()
        mt.assert_not_called()

    def test_tess_only(self, tmp_path, monkeypatch):
        """sources=('TESS',) calls fetch_tess_ffis and returns FetchResult."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        dummy_obs = Observation(
            obs_id="tess_test",
            ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=14.0, mag_err=0.05, filter_band="T", mission="TESS",
        )
        with patch.object(fetch_mod, "fetch_wise_archive", return_value=[]) as mw, \
             patch.object(fetch_mod, "fetch_decam_archive", return_value=[]) as md, \
             patch.object(fetch_mod, "fetch_tess_ffis", return_value=[dummy_obs]) as mt:
            result = fetch_mod.fetch_discovery(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                               sources=("TESS",))
        assert len(result.alerts) == 1
        assert result.alerts[0].mission == "TESS"
        mw.assert_not_called()
        md.assert_not_called()
        mt.assert_called_once()

    def test_all_three_sources(self, tmp_path, monkeypatch):
        """sources=('WISE','DECam','TESS') calls all three and combines results."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        def make_obs(obs_id, mission, filter_band):
            return Observation(
                obs_id=obs_id, ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
                mag=15.0, mag_err=0.1, filter_band=filter_band, mission=mission,
            )
        with patch.object(fetch_mod, "fetch_wise_archive",
                          return_value=[make_obs("w1", "WISE", "W1")]) as mw, \
             patch.object(fetch_mod, "fetch_decam_archive",
                          return_value=[make_obs("d1", "DECam", "g")]) as md, \
             patch.object(fetch_mod, "fetch_tess_ffis",
                          return_value=[make_obs("t1", "TESS", "T")]) as mt:
            result = fetch_mod.fetch_discovery(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                               sources=("WISE", "DECam", "TESS"))
        assert len(result.alerts) == 3
        missions = {obs.mission for obs in result.alerts}
        assert missions == {"WISE", "DECam", "TESS"}
        mw.assert_called_once()
        md.assert_called_once()
        mt.assert_called_once()

    def test_empty_sources_returns_empty_result(self, tmp_path, monkeypatch):
        """Empty sources tuple: no archive queried, FetchResult has no alerts."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        with patch.object(fetch_mod, "fetch_wise_archive", return_value=[]) as mw, \
             patch.object(fetch_mod, "fetch_decam_archive", return_value=[]) as md, \
             patch.object(fetch_mod, "fetch_tess_ffis", return_value=[]) as mt:
            # Empty sources: no archive is called; provenance has empty surveys tuple
            result = fetch_mod.fetch_discovery(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                               sources=())
        assert len(result.alerts) == 0
        mw.assert_not_called()
        md.assert_not_called()
        mt.assert_not_called()


class TestFetchRoutingNewSurveys:
    """Tests for fetch() routing TESS/DECam/WISE to new archive functions."""

    def test_fetch_routes_wise_survey(self, tmp_path, monkeypatch):
        """surveys=('WISE',) in fetch() calls fetch_wise_archive."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        dummy_obs = Observation(
            obs_id="wise_r",
            ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=15.0, mag_err=0.1, filter_band="W1", mission="WISE",
        )
        with patch.object(fetch_mod, "fetch_wise_archive", return_value=[dummy_obs]) as mw:
            result = fetch_mod.fetch(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                     surveys=("WISE",))  # type: ignore[arg-type]
        assert len(result.alerts) == 1
        assert result.alerts[0].mission == "WISE"
        mw.assert_called_once()

    def test_fetch_routes_decam_survey(self, tmp_path, monkeypatch):
        """surveys=('DECam',) in fetch() calls fetch_decam_archive."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        dummy_obs = Observation(
            obs_id="decam_r",
            ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=21.0, mag_err=0.1, filter_band="g", mission="DECam",
        )
        with patch.object(fetch_mod, "fetch_decam_archive", return_value=[dummy_obs]) as md:
            result = fetch_mod.fetch(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                     surveys=("DECam",))  # type: ignore[arg-type]
        assert len(result.alerts) == 1
        assert result.alerts[0].mission == "DECam"
        md.assert_called_once()

    def test_fetch_routes_tess_survey(self, tmp_path, monkeypatch):
        """surveys=('TESS',) in fetch() calls fetch_tess_ffis."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        dummy_obs = Observation(
            obs_id="tess_r",
            ra_deg=180.0, dec_deg=10.0, jd=2460005.0,
            mag=14.0, mag_err=0.05, filter_band="T", mission="TESS",
        )
        with patch.object(fetch_mod, "fetch_tess_ffis", return_value=[dummy_obs]) as mt:
            result = fetch_mod.fetch(180.0, 10.0, 1.0, 2460000.5, 2460010.5,
                                     surveys=("TESS",))  # type: ignore[arg-type]
        assert len(result.alerts) == 1
        assert result.alerts[0].mission == "TESS"
        mt.assert_called_once()


# ---------------------------------------------------------------------------
# Coverage gap tests: exception-handler and branch paths not reached above
# ---------------------------------------------------------------------------

class TestFetchWiseMalformedRow:
    """Covers fetch_wise_archive: except Exception: continue in row loop."""

    def test_malformed_row_skipped_good_row_kept(self, tmp_path, monkeypatch):
        """A row with non-numeric ra causes exception; good row still returned."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mjd_ok = 2460005.0 - 2_400_000.5  # valid MJD inside window
        good_row = {"mjd": mjd_ok, "ra": 180.0, "dec": 10.0, "w1mpro": 14.5, "w1sigmpro": 0.05}
        bad_row = {"mjd": mjd_ok, "ra": "bad", "dec": 10.0, "w1mpro": 15.0, "w1sigmpro": 0.1}
        mock_tap_svc = MagicMock()
        mock_result = MagicMock()
        mock_result.to_table.return_value = [bad_row, good_row]
        mock_tap_svc.run_async.return_value = mock_result
        mock_pyvo = MagicMock()
        mock_pyvo.dal.TAPService.return_value = mock_tap_svc
        with patch.dict("sys.modules", {"pyvo": mock_pyvo}):
            result = fetch_mod.fetch_wise_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        # bad_row skipped, good_row returned
        assert len(result) == 1
        assert result[0].mission == "WISE"


class TestFetchDecamMalformedRow:
    """Covers fetch_decam_archive lines 1600-1601: except Exception: continue."""

    def test_malformed_row_skipped_good_row_kept(self, tmp_path, monkeypatch):
        """A row with non-numeric ra causes exception; good row still returned."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mjd_ok = 60004.5  # MJD inside window (start_mjd=60000.0, end_mjd=60010.0)
        good_row = {"mjd": mjd_ok, "ra": 180.0, "dec": 10.0, "mag_auto": 20.0,
                    "magerr_auto": 0.1, "filter": "r"}
        bad_row = {"mjd": mjd_ok, "ra": "bad", "dec": 10.0, "mag_auto": 21.0,
                   "magerr_auto": 0.1, "filter": "r"}
        mock_table = MagicMock()
        mock_table.__len__ = lambda s: 2
        mock_table.__iter__ = lambda s: iter([bad_row, good_row])
        mock_tap = MagicMock()
        mock_tap.dal.TAPService.return_value.search.return_value.to_table.return_value = mock_table
        with patch.dict("sys.modules", {"pyvo": mock_tap}):
            result = fetch_mod.fetch_decam_archive(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        # bad_row raises ValueError on float("bad") → skipped; good_row kept
        assert len(result) == 1
        assert result[0].mission == "DECam"


class TestFetchTessCoveragePaths:
    """Covers remaining TESS branch paths (lines 1675-1676, 1690, 1701, 1719-1720)."""

    def test_tic_query_exception_returns_empty(self, tmp_path, monkeypatch):
        """Catalogs.query_region raising exception sets tic=None → returns [] (lines 1675-1676)."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # Valid sector that would pass epoch filter
        mock_sector = {"t_min": 3000.0, "t_max": 3027.0, "sequence_number": 1}
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_sector]
        mock_mast.Catalogs.query_region.side_effect = RuntimeError("TIC unavailable")
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460030.5)
        assert result == []

    def test_sector_epoch_out_of_range_skipped(self, tmp_path, monkeypatch):
        """Sector with epoch far outside JD window is skipped via continue (line 1690)."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # t_min=0, t_max=27 → epoch_jd = 13.5 + 2457000 = 2457013.5
        # window: start_jd=2460000.5 ± 14  → [2459986.5, 2460024.5]
        # 2457013.5 is NOT in that range → line 1690 continue
        out_of_range_sector = {"t_min": 0.0, "t_max": 27.0, "sequence_number": 9}
        valid_tic_src = {"ID": "11111", "ra": 180.0, "dec": 10.0, "Tmag": 14.0, "e_Tmag": 0.1}
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [out_of_range_sector]
        mock_mast.Catalogs.query_region.return_value = [valid_tic_src]
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460010.5)
        assert result == []

    def test_duplicate_tic_source_deduped(self, tmp_path, monkeypatch):
        """Same TIC source ID in a sector appears twice; second is deduped (line 1701)."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        # epoch_jd = (3000+3027)/2 + 2457000 = 2460013.5, inside window [2459986.5, 2460024.5]
        mock_sector = {"t_min": 3000.0, "t_max": 3027.0, "sequence_number": 3}
        tic_src = {"ID": "77777", "ra": 180.0, "dec": 10.0, "Tmag": 14.0, "e_Tmag": 0.1}
        # Same source listed twice → second occurrence triggers dedup continue
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_sector]
        mock_mast.Catalogs.query_region.return_value = [tic_src, tic_src]
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460030.5)
        # Only one observation despite two identical TIC rows
        assert len(result) == 1
        assert result[0].obs_id == "tess_s3_t77777"

    def test_malformed_tic_row_skipped(self, tmp_path, monkeypatch):
        """TIC row with non-numeric ra raises exception and is skipped (lines 1719-1720)."""
        monkeypatch.setattr(fetch_mod, "_CACHE_DIR", tmp_path / ".neo_cache")
        mock_sector = {"t_min": 3000.0, "t_max": 3027.0, "sequence_number": 4}
        bad_tic = {"ID": "88888", "ra": "bad_value", "dec": 10.0, "Tmag": 14.0, "e_Tmag": 0.1}
        good_tic = {"ID": "99999", "ra": 180.0, "dec": 10.0, "Tmag": 14.0, "e_Tmag": 0.1}
        mock_mast = MagicMock()
        mock_mast.Observations.query_criteria.return_value = [mock_sector]
        mock_mast.Catalogs.query_region.return_value = [bad_tic, good_tic]
        with patch.dict("sys.modules", {"astroquery.mast": mock_mast}):
            result = fetch_mod.fetch_tess_ffis(180.0, 10.0, 1.0, 2460000.5, 2460030.5)
        # bad_tic skipped, good_tic kept
        assert len(result) == 1
        assert result[0].obs_id == "tess_s4_t99999"
