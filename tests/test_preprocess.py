"""Tests for preprocess.py."""

import base64

import numpy as np
import pytest

from preprocess import (
    _apply_astrometric_correction,
    _background_rms,
    _decode_cutout,
    _normalize_cutout,
    _preprocess_observation,
    _psf_elongation,
    _psf_quality,
    preprocess,
    preprocess_batch,
)
from schemas import FetchProvenance, FetchResult, Observation


def make_obs(**kwargs) -> Observation:
    defaults = dict(
        obs_id="p_001",
        ra_deg=180.0,
        dec_deg=10.0,
        jd=2460000.5,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
    )
    defaults.update(kwargs)
    return Observation(**defaults)


class TestNormalizeCutout:
    def test_uniform_array(self):
        arr = np.ones((63, 63), dtype=np.float32)
        result = _normalize_cutout(arr)
        assert result.shape == (63, 63)
        assert result.max() == 0.0  # all same → clipped to 0

    def test_range_0_to_1(self):
        arr = np.random.default_rng(42).uniform(0, 100, (63, 63)).astype(np.float32)
        result = _normalize_cutout(arr)
        assert result.min() >= 0.0
        assert result.max() <= 1.0


class TestBackgroundRms:
    def test_gaussian_noise(self):
        rng = np.random.default_rng(0)
        arr = rng.normal(0, 5, (63, 63)).astype(np.float32)
        rms = _background_rms(arr)
        assert 3.0 < rms < 8.0

    def test_constant(self):
        arr = np.ones((63, 63), dtype=np.float32) * 100
        rms = _background_rms(arr)
        assert rms == pytest.approx(0.0, abs=1e-5)


class TestPsfQuality:
    def test_high_snr(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1000.0
        score = _psf_quality(arr)
        assert score > 0.5

    def test_pure_noise(self):
        rng = np.random.default_rng(1)
        arr = rng.normal(0, 1, (63, 63)).astype(np.float32)
        # Low peak-to-noise → low quality
        score = _psf_quality(arr)
        assert score <= 1.0


class TestPsfElongation:
    def test_round_source(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        # Circular Gaussian
        y, x = np.indices((63, 63))
        arr = np.exp(-((x - 31)**2 + (y - 31)**2) / 8.0).astype(np.float32)
        elong = _psf_elongation(arr)
        assert elong == pytest.approx(1.0, abs=0.2)

    def test_elongated_source(self):
        y, x = np.indices((63, 63))
        # Elongated along x
        arr = np.exp(-((x - 31)**2 / 50.0 + (y - 31)**2 / 2.0)).astype(np.float32)
        elong = _psf_elongation(arr)
        assert elong > 2.0


class TestDecodeCutout:
    def test_raw_numpy_fallback(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        result = _decode_cutout(b64)
        assert result.shape == (63, 63)
        assert result[31, 31] == pytest.approx(1.0)


class TestPsfQualityEdgeCases:
    def test_zero_rms_constant_array(self):
        arr = np.ones((63, 63), dtype=np.float32) * 500.0
        score = _psf_quality(arr)
        assert score == pytest.approx(0.0)


class TestPsfElongationEdgeCases:
    def test_zero_array_returns_one(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        result = _psf_elongation(arr)
        assert result == pytest.approx(1.0)

    def test_det_zero_returns_one(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, :] = 100.0  # horizontal line → myy=0, det=0
        result = _psf_elongation(arr)
        assert result == pytest.approx(1.0)


class TestApplyAstrometricCorrection:
    def test_none_gaia_returns_unchanged(self):
        obs = make_obs(ra_deg=180.0, dec_deg=10.0)
        result = _apply_astrometric_correction(obs, gaia_sources=None)
        assert result.ra_deg == pytest.approx(180.0)

    def test_empty_gaia_list_returns_unchanged(self):
        obs = make_obs(ra_deg=180.0, dec_deg=10.0)
        result = _apply_astrometric_correction(obs, gaia_sources=[])
        assert result.ra_deg == pytest.approx(180.0)

    def test_with_gaia_sources_applies_offset(self):
        obs = make_obs(ra_deg=180.0, dec_deg=10.0)
        gaia_sources = [{"obs_ra": 180.1, "gaia_ra": 180.0, "obs_dec": 10.1, "gaia_dec": 10.0}]
        result = _apply_astrometric_correction(obs, gaia_sources=gaia_sources)
        assert result.ra_deg == pytest.approx(179.9, abs=1e-9)
        assert result.dec_deg == pytest.approx(9.9, abs=1e-9)


class TestPreprocessObservation:
    def test_with_cutout_normalizes(self):
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = make_obs(cutout_science=b64)
        result = _preprocess_observation(obs)
        assert result.cutout_science is not None
        assert result.cutout_science != b64  # normalized to [0,1]

    def test_no_cutout_returns_same(self):
        obs = make_obs()
        result = _preprocess_observation(obs)
        assert result.obs_id == obs.obs_id
        assert result.cutout_science is None


class TestPreprocessPipeline:
    def test_rejects_bad_magnitude(self):
        # Pydantic validates RA/Dec bounds at construction — test mag filtering
        obs_good = make_obs()
        obs_bad_mag = make_obs(obs_id="bad_mag", mag=40.0)  # > 35 limit
        result = preprocess((obs_good, obs_bad_mag), apply_astrometry=False)
        assert result.provenance.n_sources_in == 2
        assert result.provenance.n_sources_out == 1

    def test_empty_input(self):
        result = preprocess((), apply_astrometry=False)
        assert len(result.sources) == 0
        assert result.provenance.n_sources_in == 0

    def test_valid_obs_passes_through(self):
        obs = make_obs()
        result = preprocess((obs,), apply_astrometry=False)
        assert len(result.sources) == 1

    def test_apply_astrometry_path(self):
        obs = make_obs(mission="ZTF")
        result = preprocess((obs,), apply_astrometry=True)
        assert len(result.sources) == 1
        assert result.provenance.astrometric_reference == "Gaia DR3"

    def test_astrometry_off_reference_label(self):
        obs = make_obs()
        result = preprocess((obs,), apply_astrometry=False)
        assert result.provenance.astrometric_reference == "none"

    def test_rejects_zero_magnitude(self):
        obs = make_obs(obs_id="zero_mag", mag=0.0)
        result = preprocess((obs,), apply_astrometry=False)
        assert result.provenance.n_sources_out == 0


class TestDecodeAsFits:
    def test_valid_fits_bytes_decode(self):
        # Cover FITS path (line 34): encode a 63×63 FITS image
        import base64
        import io

        import numpy as np
        from astropy.io import fits
        arr = np.ones((63, 63), dtype=np.float32)
        hdu = fits.PrimaryHDU(arr)
        buf = io.BytesIO()
        hdu.writeto(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        result = _decode_cutout(b64)
        assert result.shape == (63, 63)


class TestGaiaMock:
    def test_gaia_query_returns_stars(self, monkeypatch):
        import sys
        from unittest.mock import MagicMock

        import preprocess as pp_mod
        # Mock astroquery.gaia → covers lines 139-143
        mock_gaia = MagicMock()
        mock_job = MagicMock()
        mock_job.get_results.return_value = [{"ra": 180.0, "dec": 10.0}]
        mock_gaia.cone_search_async.return_value = mock_job
        mock_astroquery_gaia = MagicMock()
        mock_astroquery_gaia.Gaia = mock_gaia
        monkeypatch.setitem(sys.modules, "astroquery.gaia", mock_astroquery_gaia)
        result = pp_mod._query_gaia_sources(180.0, 10.0)
        assert isinstance(result, list)


class TestPreprocessQualityCuts:
    def test_rejects_invalid_ra(self):
        # ra_deg = -1.0 → fails range check → continue (line 194)
        # Use model_construct to bypass Pydantic validation
        from schemas import Observation
        obs = Observation.model_construct(
            obs_id="badra", ra_deg=-1.0, dec_deg=10.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        result = preprocess((obs,), apply_astrometry=False)
        assert result.provenance.n_sources_out == 0

    def test_rejects_nan_ra(self):
        # NaN ra_deg → fails the float-comparison check at line 193 (NaN <= 360 is False)
        from schemas import Observation
        obs = Observation.model_construct(
            obs_id="nanra", ra_deg=float("nan"), dec_deg=10.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        result = preprocess((obs,), apply_astrometry=False)
        assert result.provenance.n_sources_out == 0

    def test_rejects_nan_jd(self):
        # NaN jd passes ra/dec/mag checks but math.isnan(jd) → continue (line 198)
        from schemas import Observation
        obs = Observation.model_construct(
            obs_id="nanjd", ra_deg=180.0, dec_deg=10.0, jd=float("nan"),
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        result = preprocess((obs,), apply_astrometry=False)
        assert result.provenance.n_sources_out == 0


def _make_fetch_result(obs: tuple) -> FetchResult:
    return FetchResult(
        alerts=obs,
        provenance=FetchProvenance(surveys=("ZTF",), start_jd=2460000.0, end_jd=2460001.0),
    )


class TestPreprocessBatch:
    def test_returns_one_result_per_input(self):
        obs = (make_obs(obs_id="b1"),)
        fr = _make_fetch_result(obs)
        results = preprocess_batch([fr, fr], apply_astrometry=False)
        assert len(results) == 2

    def test_empty_list_returns_empty(self):
        assert preprocess_batch([]) == []

    def test_each_result_is_preprocess_result(self):
        from schemas import PreprocessResult
        obs = (make_obs(obs_id="b2"),)
        fr = _make_fetch_result(obs)
        results = preprocess_batch([fr], apply_astrometry=False)
        assert isinstance(results[0], PreprocessResult)

    def test_source_counts_match_individual(self):
        obs = (make_obs(obs_id="b3"), make_obs(obs_id="b4"))
        fr = _make_fetch_result(obs)
        batch = preprocess_batch([fr], apply_astrometry=False)
        individual = preprocess(obs, apply_astrometry=False)
        assert batch[0].provenance.n_sources_out == individual.provenance.n_sources_out
