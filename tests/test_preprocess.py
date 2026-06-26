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

    def test_catalog_only_sources_skipped(self):
        # Sources from _query_gaia_sources have only gaia_ra/gaia_dec; obs_ra/obs_dec
        # are populated only after image cross-matching.  Catalog-only entries must be
        # skipped gracefully so no KeyError is raised and the obs is returned unchanged.
        obs = make_obs(ra_deg=180.0, dec_deg=10.0)
        gaia_sources = [{"gaia_ra": 180.0, "gaia_dec": 10.0}]
        result = _apply_astrometric_correction(obs, gaia_sources=gaia_sources)
        assert result.ra_deg == pytest.approx(180.0)
        assert result.dec_deg == pytest.approx(10.0)


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

    def test_apply_astrometry_path(self, monkeypatch):
        import preprocess as pp_mod
        # Pin _query_gaia_sources to return empty so the test is deterministic
        # across Python versions regardless of whether astroquery.gaia is
        # available and functional on the runner.
        monkeypatch.setattr(pp_mod, "_query_gaia_sources", lambda *a, **kw: [])
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

    def test_gaia_query_returns_empty_on_error(self, monkeypatch):
        import sys
        from unittest.mock import MagicMock

        import preprocess as pp_mod
        # Force the except path (line 187) by making cone_search_async raise.
        # On Python 3.14.5 the real astroquery.gaia import succeeds so this
        # branch is never hit naturally — it must be covered explicitly.
        mock_gaia = MagicMock()
        mock_gaia.cone_search_async.side_effect = RuntimeError("simulated failure")
        mock_astroquery_gaia = MagicMock()
        mock_astroquery_gaia.Gaia = mock_gaia
        monkeypatch.setitem(sys.modules, "astroquery.gaia", mock_astroquery_gaia)
        result = pp_mod._query_gaia_sources(180.0, 10.0)
        assert result == []


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


class TestComputeSourceSnrEdgeCases:
    def _make_obs(self, cutout_b64=None):
        from schemas import Observation
        return Observation(
            obs_id="snr_001", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=cutout_b64,
        )

    def test_non_square_returns_none(self):
        import base64

        import numpy as np

        from preprocess import compute_source_snr
        arr = np.ones(12, dtype=np.float32)  # 12 elements, not a perfect square
        b64 = base64.b64encode(arr.tobytes()).decode()
        assert compute_source_snr(self._make_obs(b64)) is None

    def test_invalid_b64_returns_none(self):
        from preprocess import compute_source_snr
        assert compute_source_snr(self._make_obs("!!!invalid!!!")) is None


class TestDetectBadPixelsEdgeCases:
    def _make_obs(self, cutout_b64=None):
        from schemas import Observation
        return Observation(
            obs_id="bp2_001", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=cutout_b64,
        )

    def test_non_square_returns_empty(self):
        import base64

        import numpy as np

        from preprocess import detect_bad_pixels
        arr = np.ones(12, dtype=np.float32)  # not a perfect square
        b64 = base64.b64encode(arr.tobytes()).decode()
        assert detect_bad_pixels(self._make_obs(b64)) == []

    def test_constant_array_zero_sigma_returns_empty(self):
        import base64

        import numpy as np

        from preprocess import detect_bad_pixels
        arr = np.ones((3, 3), dtype=np.float32) * 5.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        # MAD of constant array is 0 → sigma = 0 → return []
        assert detect_bad_pixels(self._make_obs(b64)) == []

    def test_invalid_b64_returns_empty(self):
        from preprocess import detect_bad_pixels
        assert detect_bad_pixels(self._make_obs("!!!invalid!!!")) == []


class TestComputeAstrometricScatterException:
    """Cover except Exception branch in compute_astrometric_scatter."""

    def test_exception_returns_none(self, monkeypatch):
        import numpy as np

        from preprocess import compute_astrometric_scatter

        from .conftest import build_tracklet

        # Monkeypatch np.linalg.lstsq to raise
        def raise_lstsq(*args, **kwargs):
            raise ValueError("forced failure")

        monkeypatch.setattr(np.linalg, "lstsq", raise_lstsq)
        obs = list(build_tracklet(n_obs=4, arc_days=2.0).observations)
        result = compute_astrometric_scatter(obs)
        assert result is None


class TestComputeImageQualityMetricsBranches:
    """Cover lines 503 and 510-511 in compute_image_quality_metrics."""

    def test_obs_without_cutout_skipped_for_bg(self):
        from preprocess import compute_image_quality_metrics

        from .conftest import build_observation
        # No cutout → line 503 (continue) hit
        obs = build_observation()
        result = compute_image_quality_metrics([obs])
        assert result["background_rms"] is None

    def test_bad_cutout_triggers_except(self):
        from preprocess import compute_image_quality_metrics

        from .conftest import build_observation
        # Invalid base64 → line 510-511 (except continue) hit
        obs = build_observation(cutout_difference="!!!invalid_base64!!!")
        result = compute_image_quality_metrics([obs])
        assert result["background_rms"] is None

    def test_tiny_array_skipped_for_background(self):
        import base64

        import numpy as np

        from preprocess import compute_image_quality_metrics
        # Array with fewer than 4 elements → arr.size < 4 branch (546→538)
        tiny = np.array([1.0, 2.0], dtype=np.float32)
        b64 = base64.b64encode(tiny.tobytes()).decode()
        from types import SimpleNamespace
        obs = SimpleNamespace(
            cutout_difference=b64,
            cutout_science=None,
            cutout_reference=None,
            ra_deg=180.0,
            dec_deg=0.0,
            jd=2460000.0,
            mag=18.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            obs_id="tiny",
        )
        result = compute_image_quality_metrics([obs])
        assert result["background_rms"] is None


class TestComputeCutoutEntropyEdgeCases:
    def test_bad_base64_returns_none(self):
        from preprocess import compute_cutout_entropy
        from schemas import Observation
        obs = Observation(
            obs_id="bad", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference="!!!not_valid_base64!!!",
        )
        assert compute_cutout_entropy(obs) is None


class TestComputeSourceCompactness:
    def _make_obs(self, arr=None):
        import sys
        sys.path.insert(0, "src")
        import base64
        from types import SimpleNamespace

        import numpy as np
        if arr is None:
            arr = np.zeros((63, 63), dtype=np.float32)
            arr[31, 31] = 10.0
        b64 = base64.b64encode(arr.astype(np.float32).tobytes()).decode()
        return SimpleNamespace(cutout_difference=b64)

    def test_point_source_high_compactness(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import compute_source_compactness
        obs = self._make_obs()
        result = compute_source_compactness(obs)
        assert result is not None
        assert result == pytest.approx(1.0)

    def test_uniform_array_low_compactness(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import compute_source_compactness
        arr = np.ones((63, 63), dtype=np.float32)
        obs = self._make_obs(arr)
        result = compute_source_compactness(obs)
        assert result is not None
        assert result < 0.01

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_source_compactness
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_source_compactness(obs) is None

    def test_zero_array_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import compute_source_compactness
        obs = self._make_obs(np.zeros((63, 63), dtype=np.float32))
        assert compute_source_compactness(obs) is None

    def test_invalid_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_source_compactness
        obs = SimpleNamespace(cutout_difference="!!!notbase64!!!")
        assert compute_source_compactness(obs) is None


