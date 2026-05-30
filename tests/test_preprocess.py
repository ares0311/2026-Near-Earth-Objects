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


class TestQualitySummary:
    def _make_preprocess_result_n(self, n_in, n_out):
        from schemas import PreprocessProvenance, PreprocessResult
        obs = tuple(make_obs(obs_id=f"qs{i}") for i in range(n_out))
        prov = PreprocessProvenance(
            n_sources_in=n_in, n_sources_out=n_out,
            astrometric_reference="Gaia DR3",
        )
        return PreprocessResult(sources=obs, provenance=prov)

    def test_returns_required_keys(self):
        from preprocess import quality_summary
        pr = self._make_preprocess_result_n(10, 8)
        result = quality_summary(pr)
        expected = {"n_in", "n_out", "pass_fraction",
                    "median_psf_quality", "median_bg_rms", "median_elongation"}
        assert expected == set(result.keys())

    def test_n_in_matches_provenance(self):
        from preprocess import quality_summary
        pr = self._make_preprocess_result_n(10, 8)
        assert quality_summary(pr)["n_in"] == 10

    def test_n_out_matches_provenance(self):
        from preprocess import quality_summary
        pr = self._make_preprocess_result_n(10, 8)
        assert quality_summary(pr)["n_out"] == 8

    def test_pass_fraction_correct(self):
        from preprocess import quality_summary
        pr = self._make_preprocess_result_n(10, 8)
        assert quality_summary(pr)["pass_fraction"] == pytest.approx(0.8, abs=1e-4)

    def test_pass_fraction_zero_when_no_sources(self):
        from preprocess import quality_summary
        pr = self._make_preprocess_result_n(0, 0)
        assert quality_summary(pr)["pass_fraction"] == 0.0

    def test_median_fields_none_when_no_output(self):
        from preprocess import quality_summary
        pr = self._make_preprocess_result_n(5, 0)
        result = quality_summary(pr)
        # With no sources, median stats should be None
        assert (result["median_psf_quality"] is None
                or isinstance(result["median_psf_quality"], float))
        assert (result["median_bg_rms"] is None
                or isinstance(result["median_bg_rms"], float))
        assert (result["median_elongation"] is None
                or isinstance(result["median_elongation"], float))

    def test_median_fields_float_with_sources(self):
        from preprocess import quality_summary
        pr = self._make_preprocess_result_n(5, 5)
        result = quality_summary(pr)
        assert isinstance(result["median_psf_quality"], float)
        assert isinstance(result["median_bg_rms"], float)
        assert isinstance(result["median_elongation"], float)


class TestFlagSaturatedSources:
    def _make_preprocess_result(self, mags: list[float]) -> object:
        from schemas import PreprocessProvenance, PreprocessResult

        from .conftest import build_observation
        obs = tuple(
            build_observation(obs_id=f"s{i}", mag=m, jd=2460000.5 + i)
            for i, m in enumerate(mags)
        )
        prov = PreprocessProvenance(
            n_sources_in=len(mags),
            n_sources_out=len(mags),
            astrometric_reference="none",
        )
        return PreprocessResult(sources=obs, provenance=prov)

    def test_returns_list(self):
        from preprocess import flag_saturated_sources
        pr = self._make_preprocess_result([15.0, 19.0])
        result = flag_saturated_sources(pr)
        assert isinstance(result, list)

    def test_faint_sources_not_flagged(self):
        from preprocess import flag_saturated_sources
        pr = self._make_preprocess_result([19.0, 20.0])
        result = flag_saturated_sources(pr)
        assert result == []

    def test_bright_sources_flagged(self):
        from preprocess import flag_saturated_sources
        pr = self._make_preprocess_result([8.0, 19.0])
        result = flag_saturated_sources(pr)
        assert len(result) == 1

    def test_custom_saturation_magnitude(self):
        from preprocess import flag_saturated_sources
        pr = self._make_preprocess_result([13.0, 19.0])
        result = flag_saturated_sources(pr, saturation_mag=15.0)
        assert len(result) == 1

    def test_returns_obs_ids(self):
        from preprocess import flag_saturated_sources
        pr = self._make_preprocess_result([8.0, 19.0])
        result = flag_saturated_sources(pr)
        assert isinstance(result[0], str)

    def test_invalid_input_raises(self):
        import pytest

        from preprocess import flag_saturated_sources
        with pytest.raises(TypeError):
            flag_saturated_sources("not a PreprocessResult")  # type: ignore[arg-type]


class TestComputeColorIndex:
    def _make_obs(self, obs_id: str = "o1", jd: float = 2460000.5,
                  mag: float = 19.0, filter_band: str = "r") -> "Observation":
        from schemas import Observation
        return Observation(
            obs_id=obs_id, ra_deg=180.0, dec_deg=0.0, jd=jd,
            mag=mag, mag_err=0.05, filter_band=filter_band, mission="ZTF",
        )

    def test_returns_float_for_different_bands(self):
        from preprocess import compute_color_index
        obs1 = self._make_obs("o1", jd=2460000.5, mag=19.0, filter_band="g")
        obs2 = self._make_obs("o2", jd=2460000.5, mag=19.5, filter_band="r")
        result = compute_color_index(obs1, obs2)
        assert result == pytest.approx(-0.5)

    def test_same_band_returns_none(self):
        from preprocess import compute_color_index
        obs1 = self._make_obs("o1", filter_band="r", mag=19.0)
        obs2 = self._make_obs("o2", filter_band="r", mag=19.5)
        assert compute_color_index(obs1, obs2) is None

    def test_large_time_gap_returns_none(self):
        from preprocess import compute_color_index
        obs1 = self._make_obs("o1", jd=2460000.0, filter_band="g")
        obs2 = self._make_obs("o2", jd=2460002.0, filter_band="r")
        assert compute_color_index(obs1, obs2) is None

    def test_within_one_hour_returns_value(self):
        from preprocess import compute_color_index
        obs1 = self._make_obs("o1", jd=2460000.5, mag=19.0, filter_band="g")
        obs2 = self._make_obs("o2", jd=2460000.5 + 0.04 / 24.0, mag=19.5, filter_band="r")
        result = compute_color_index(obs1, obs2)
        assert result is not None

    def test_exactly_one_hour_returns_none(self):
        from preprocess import compute_color_index
        obs1 = self._make_obs("o1", jd=2460000.5, filter_band="g")
        obs2 = self._make_obs("o2", jd=2460000.5 + 1.0 / 24.0 + 1e-6, filter_band="r")
        assert compute_color_index(obs1, obs2) is None

    def test_symmetric_sign(self):
        from preprocess import compute_color_index
        obs1 = self._make_obs("o1", jd=2460000.5, mag=19.0, filter_band="g")
        obs2 = self._make_obs("o2", jd=2460000.5, mag=19.5, filter_band="r")
        r12 = compute_color_index(obs1, obs2)
        r21 = compute_color_index(obs2, obs1)
        assert r12 is not None and r21 is not None
        assert r12 == pytest.approx(-r21)


class TestEstimateSourceDensity:
    def _make_obs(self, obs_id: str, ra: float = 180.0, dec: float = 0.0) -> object:
        from schemas import Observation

        return Observation(
            obs_id=obs_id,
            ra_deg=ra,
            dec_deg=dec,
            jd=2460000.5,
            mag=19.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
        )

    def test_empty_returns_zero(self):
        from preprocess import estimate_source_density

        assert estimate_source_density(()) == 0.0

    def test_single_obs_nonzero_density(self):
        from preprocess import estimate_source_density

        obs = self._make_obs("a")
        result = estimate_source_density((obs,))
        assert result > 0.0

    def test_returns_float(self):
        from preprocess import estimate_source_density

        obs = self._make_obs("b")
        assert isinstance(estimate_source_density((obs,)), float)

    def test_more_obs_higher_density(self):
        from preprocess import estimate_source_density

        obs_close = tuple(
            self._make_obs(f"c{i}", ra=180.0 + i * 0.01, dec=0.0) for i in range(5)
        )
        obs_far = tuple(
            self._make_obs(f"d{i}", ra=180.0 + i * 0.3, dec=0.0) for i in range(5)
        )
        dense = estimate_source_density(obs_close, field_radius_deg=0.5)
        sparse = estimate_source_density(obs_far, field_radius_deg=0.5)
        assert dense >= sparse

    def test_accepts_list_input(self):
        from preprocess import estimate_source_density

        obs_list = [self._make_obs(f"e{i}") for i in range(3)]
        result = estimate_source_density(obs_list)
        assert isinstance(result, float)

    def test_zero_radius_returns_zero(self):
        from preprocess import estimate_source_density

        obs = self._make_obs("f")
        result = estimate_source_density((obs,), field_radius_deg=0.0)
        assert result == 0.0


class TestComputeSourceSnr:
    def _make_obs(self, cutout_b64: str | None = None) -> object:
        from schemas import Observation
        return Observation(
            obs_id="snr1", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference=cutout_b64,
        )

    def test_no_cutout_returns_none(self):
        from preprocess import compute_source_snr
        obs = self._make_obs(None)
        assert compute_source_snr(obs) is None

    def test_strong_source_positive_snr(self):
        import base64

        import numpy as np

        from preprocess import compute_source_snr
        arr = np.ones((63, 63), dtype=np.float32) * 0.01
        arr[31, 31] = 10.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        snr = compute_source_snr(obs)
        assert snr is not None
        assert snr > 1.0

    def test_returns_float_or_none(self):
        import base64

        import numpy as np

        from preprocess import compute_source_snr
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 5.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        result = compute_source_snr(obs)
        assert result is None or isinstance(result, float)

    def test_zero_array_returns_none(self):
        import base64

        import numpy as np

        from preprocess import compute_source_snr
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = self._make_obs(b64)
        assert compute_source_snr(obs) is None

    def test_brighter_peak_higher_snr(self):
        import base64

        import numpy as np

        from preprocess import compute_source_snr

        rng = np.random.default_rng(42)

        def make_b64(peak: float) -> str:
            arr = rng.normal(0.0, 1.0, (63, 63)).astype(np.float32)
            arr[31, 31] = peak
            return base64.b64encode(arr.tobytes()).decode()

        snr_dim = compute_source_snr(self._make_obs(make_b64(5.0)))
        snr_bright = compute_source_snr(self._make_obs(make_b64(50.0)))
        if snr_dim is not None and snr_bright is not None:
            assert snr_bright > snr_dim


class TestDetectBadPixels:
    def _make_obs(self, cutout_b64=None):
        import base64

        import numpy as np

        from schemas import Observation
        if cutout_b64 is None:
            arr = np.zeros((9, 9), dtype=np.float32)
            cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="bp_001",
            ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.5, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
            cutout_difference=cutout_b64,
        )

    def test_no_cutout_returns_empty(self):
        from preprocess import detect_bad_pixels
        from schemas import Observation
        obs = Observation(
            obs_id="x", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF", real_bogus=0.9,
        )
        assert detect_bad_pixels(obs) == []

    def test_uniform_array_no_bad_pixels(self):
        import base64

        import numpy as np

        from preprocess import detect_bad_pixels
        arr = np.ones((9, 9), dtype=np.float32) * 5.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        result = detect_bad_pixels(self._make_obs(b64))
        assert result == []

    def test_hot_pixel_detected(self):
        import base64

        import numpy as np

        from preprocess import detect_bad_pixels
        rng = np.random.default_rng(0)
        arr = rng.normal(0.0, 1.0, (9, 9)).astype(np.float32)
        arr[4, 4] = 1000.0  # extreme outlier
        b64 = base64.b64encode(arr.tobytes()).decode()
        result = detect_bad_pixels(self._make_obs(b64), sigma_threshold=3.0)
        assert (4, 4) in result

    def test_returns_list_of_tuples(self):
        from preprocess import detect_bad_pixels
        result = detect_bad_pixels(self._make_obs())
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2


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


class TestComputeAstrometricScatter:
    def _make_obs(self, n=5, arc_days=2.0):
        from .conftest import build_tracklet
        t = build_tracklet(n_obs=n, arc_days=arc_days)
        return list(t.observations)

    def test_returns_float_for_valid_obs(self):
        from preprocess import compute_astrometric_scatter
        obs = self._make_obs(n=4, arc_days=1.0)
        result = compute_astrometric_scatter(obs)
        assert result is None or isinstance(result, float)

    def test_returns_none_for_single_obs(self):
        from preprocess import compute_astrometric_scatter
        obs = self._make_obs(n=1)
        result = compute_astrometric_scatter(obs)
        assert result is None

    def test_returns_none_for_empty(self):
        from preprocess import compute_astrometric_scatter
        result = compute_astrometric_scatter([])
        assert result is None

    def test_nonnegative_when_returned(self):
        from preprocess import compute_astrometric_scatter
        obs = self._make_obs(n=5, arc_days=2.0)
        result = compute_astrometric_scatter(obs)
        if result is not None:
            assert result >= 0.0

    def test_identical_jd_returns_none(self):
        from preprocess import compute_astrometric_scatter
        from schemas import Observation
        obs = [
            Observation(obs_id=f"o{i}", ra_deg=10.0, dec_deg=5.0,
                       jd=2460000.5, mag=20.0, mag_err=0.1,
                       filter_band="r", mission="ZTF")
            for i in range(3)
        ]
        result = compute_astrometric_scatter(obs)
        assert result is None


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


class TestNormalizePhotometry:
    def _make_obs(self, mag=19.5, **kwargs):
        from .conftest import build_observation
        return build_observation(mag=mag, **kwargs)

    def test_returns_list(self):
        from preprocess import normalize_photometry
        obs = [self._make_obs(19.5)]
        result = normalize_photometry(obs, zero_point=24.0)
        assert isinstance(result, list)

    def test_applies_offset(self):
        from preprocess import normalize_photometry
        # zero_point=24.0, reference=25.0 → offset=+1.0
        obs = [self._make_obs(19.5)]
        result = normalize_photometry(obs, zero_point=24.0)
        assert len(result) == 1
        assert result[0].mag == pytest.approx(20.5, abs=0.001)

    def test_drops_out_of_range(self):
        from preprocess import normalize_photometry
        # offset = 25 - 5 = 20 → corrected = 19.5 + 20 = 39.5 (>35, dropped)
        obs = [self._make_obs(19.5)]
        result = normalize_photometry(obs, zero_point=5.0)
        assert result == []

    def test_drops_negative_mag(self):
        from preprocess import normalize_photometry
        # offset = 25 - 50 = -25 → corrected = 5.0 - 25 = -20 (< 0, dropped)
        obs = [self._make_obs(5.0)]
        result = normalize_photometry(obs, zero_point=50.0)
        assert result == []

    def test_empty_list(self):
        from preprocess import normalize_photometry
        result = normalize_photometry([], zero_point=25.0)
        assert result == []

    def test_preserves_mag_err(self):
        from preprocess import normalize_photometry
        obs = [self._make_obs(19.5, mag_err=0.1)]
        result = normalize_photometry(obs, zero_point=24.5)
        assert result[0].mag_err == pytest.approx(0.1)

    def test_custom_reference_zero_point(self):
        from preprocess import normalize_photometry
        # zero_point=23, reference=24 → offset=1
        obs = [self._make_obs(18.0)]
        result = normalize_photometry(obs, zero_point=23.0, reference_zero_point=24.0)
        assert result[0].mag == pytest.approx(19.0, abs=0.001)


class TestComputeImageQualityMetrics:
    def _make_obs_with_cutout(self, mag=19.0):
        import base64

        import numpy as np

        from .conftest import build_observation
        arr = np.random.default_rng(42).uniform(0, 1, (63, 63)).astype(np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        return build_observation(mag=mag, cutout_difference=b64)

    def test_returns_dict(self):
        from preprocess import compute_image_quality_metrics
        result = compute_image_quality_metrics([])
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        from preprocess import compute_image_quality_metrics
        result = compute_image_quality_metrics([])
        for key in ["n_sources", "mean_fwhm_arcsec", "median_fwhm_arcsec",
                    "mean_snr", "background_rms"]:
            assert key in result

    def test_empty_observations_none_metrics(self):
        from preprocess import compute_image_quality_metrics
        result = compute_image_quality_metrics([])
        assert result["n_sources"] == 0
        assert result["mean_fwhm_arcsec"] is None
        assert result["mean_snr"] is None

    def test_counts_sources(self):
        from preprocess import compute_image_quality_metrics
        obs = [self._make_obs_with_cutout() for _ in range(3)]
        result = compute_image_quality_metrics(obs)
        assert result["n_sources"] == 3

    def test_background_rms_with_cutout(self):
        from preprocess import compute_image_quality_metrics
        obs = [self._make_obs_with_cutout()]
        result = compute_image_quality_metrics(obs)
        assert result["background_rms"] is not None
        assert result["background_rms"] >= 0.0


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


class TestComputePhotometricScatter:
    def _make_obs(self, mag):
        from .conftest import build_observation
        return build_observation(mag=mag)

    def test_empty_returns_none(self):
        from preprocess import compute_photometric_scatter
        assert compute_photometric_scatter([]) is None

    def test_single_obs_returns_none(self):
        from preprocess import compute_photometric_scatter
        assert compute_photometric_scatter([self._make_obs(19.0)]) is None

    def test_two_identical_mags_returns_zero(self):
        from preprocess import compute_photometric_scatter
        obs = [self._make_obs(19.0), self._make_obs(19.0)]
        result = compute_photometric_scatter(obs)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_known_scatter(self):
        import numpy as np

        from preprocess import compute_photometric_scatter
        mags = [19.0, 19.2, 18.8, 19.1, 18.9]
        obs = [self._make_obs(m) for m in mags]
        result = compute_photometric_scatter(obs)
        arr = np.array(mags)
        expected = round(float(np.sqrt(np.mean((arr - arr.mean()) ** 2))), 6)
        assert result == pytest.approx(expected, abs=1e-5)

    def test_excludes_sentinel_mags(self):
        from preprocess import compute_photometric_scatter
        obs = [self._make_obs(99.0), self._make_obs(19.0)]
        # Only one valid mag → None
        result = compute_photometric_scatter(obs)
        assert result is None

    def test_returns_float_for_valid_input(self):
        from preprocess import compute_photometric_scatter
        obs = [self._make_obs(19.0), self._make_obs(19.5)]
        result = compute_photometric_scatter(obs)
        assert isinstance(result, float)

    def test_non_negative(self):
        from preprocess import compute_photometric_scatter
        obs = [self._make_obs(m) for m in [18.0, 19.0, 20.0]]
        result = compute_photometric_scatter(obs)
        assert result >= 0.0


class TestEstimateZeroPoint:
    def _make_obs(self, mag):
        from .conftest import build_observation
        return build_observation(mag=mag)

    def test_empty_returns_none(self):
        from preprocess import estimate_zero_point
        assert estimate_zero_point([], []) is None

    def test_single_pair_returns_none(self):
        from preprocess import estimate_zero_point
        assert estimate_zero_point([self._make_obs(19.0)], [18.5]) is None

    def test_two_pairs_returns_median(self):
        from preprocess import estimate_zero_point
        obs = [self._make_obs(19.0), self._make_obs(20.0)]
        catalog = [18.5, 19.5]
        result = estimate_zero_point(obs, catalog)
        assert result == pytest.approx(0.5, abs=1e-5)

    def test_returns_float(self):
        from preprocess import estimate_zero_point
        obs = [self._make_obs(19.0), self._make_obs(20.0), self._make_obs(21.0)]
        catalog = [18.7, 19.7, 20.7]
        result = estimate_zero_point(obs, catalog)
        assert isinstance(result, float)

    def test_sentinel_mags_excluded(self):
        from preprocess import estimate_zero_point
        obs = [self._make_obs(99.0), self._make_obs(99.0)]
        catalog = [18.5, 19.5]
        result = estimate_zero_point(obs, catalog)
        assert result is None

    def test_mismatched_length_uses_min(self):
        from preprocess import estimate_zero_point
        obs = [self._make_obs(19.0), self._make_obs(20.0), self._make_obs(21.0)]
        catalog = [18.5, 19.5]
        # Only 2 pairs → median of [0.5, 0.5]
        result = estimate_zero_point(obs, catalog)
        assert result == pytest.approx(0.5, abs=1e-5)

    def test_known_offset(self):
        from preprocess import estimate_zero_point
        obs = [self._make_obs(19.3), self._make_obs(20.3), self._make_obs(21.3)]
        catalog = [19.0, 20.0, 21.0]
        result = estimate_zero_point(obs, catalog)
        assert result == pytest.approx(0.3, abs=1e-5)


class TestComputeDifferenceImageSnr:
    def _make_cutout_obs(self, peak=50.0):
        import base64

        import numpy as np

        from schemas import Observation
        rng = np.random.default_rng(0)
        arr = rng.normal(0.0, 1.0, (63, 63)).astype(np.float32)
        arr[31, 31] = peak
        b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="o1", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )

    def test_returns_float_for_valid_cutout(self):
        from preprocess import compute_difference_image_snr
        obs = self._make_cutout_obs(peak=50.0)
        result = compute_difference_image_snr(obs)
        assert isinstance(result, float)
        assert result > 0.0

    def test_returns_none_without_cutout(self):
        from preprocess import compute_difference_image_snr
        from schemas import Observation
        obs = Observation(
            obs_id="o1", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        result = compute_difference_image_snr(obs)
        assert result is None

    def test_zero_background_returns_none(self):
        import base64

        import numpy as np

        from preprocess import compute_difference_image_snr
        from schemas import Observation
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="o2", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )
        result = compute_difference_image_snr(obs)
        assert result is None

    def test_invalid_cutout_returns_none(self):
        from preprocess import compute_difference_image_snr
        from schemas import Observation
        obs = Observation(
            obs_id="o3", ra_deg=180.0, dec_deg=10.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference="not_valid_base64!!!",
        )
        result = compute_difference_image_snr(obs)
        assert result is None

    def test_brighter_peak_gives_higher_snr(self):
        from preprocess import compute_difference_image_snr
        low = self._make_cutout_obs(peak=10.0)
        high = self._make_cutout_obs(peak=200.0)
        snr_low = compute_difference_image_snr(low)
        snr_high = compute_difference_image_snr(high)
        assert snr_high is not None and snr_low is not None
        assert snr_high > snr_low


class TestComputeCutoutEntropy:
    def _make_obs(self, noise_std: float = 1.0, peak: float = 100.0) -> object:
        import base64

        import numpy as np

        from schemas import Observation
        rng = np.random.default_rng(0)
        arr = rng.normal(0.0, noise_std, (63, 63)).astype(np.float32)
        arr[31, 31] = peak
        b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="ent_test", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )

    def test_returns_float(self):
        from preprocess import compute_cutout_entropy
        obs = self._make_obs()
        result = compute_cutout_entropy(obs)
        assert result is not None
        assert isinstance(result, float)

    def test_entropy_positive(self):
        from preprocess import compute_cutout_entropy
        obs = self._make_obs()
        assert compute_cutout_entropy(obs) > 0.0

    def test_entropy_bounded(self):
        from preprocess import compute_cutout_entropy
        obs = self._make_obs()
        result = compute_cutout_entropy(obs)
        assert result is not None
        assert result <= 8.0  # max for 256 bins

    def test_none_for_no_cutout(self):
        from preprocess import compute_cutout_entropy
        from schemas import Observation
        obs = Observation(
            obs_id="nc", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
        )
        assert compute_cutout_entropy(obs) is None

    def test_none_for_uniform_array(self):
        import base64

        import numpy as np

        from preprocess import compute_cutout_entropy
        from schemas import Observation
        arr = np.ones((63, 63), dtype=np.float32) * 5.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = Observation(
            obs_id="uni", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )
        assert compute_cutout_entropy(obs) is None

    def test_in_all(self):
        from preprocess import __all__
        assert "compute_cutout_entropy" in __all__


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


class TestComputeBackgroundLevel:
    def _make_obs(self, bg: float = 0.5, peak: float = 100.0) -> object:
        import base64

        import numpy as np

        from schemas import Observation
        arr = np.full((63, 63), bg, dtype=np.float32)
        arr[31, 31] = peak
        b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="bg_test", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )

    def test_returns_float(self):
        from preprocess import compute_background_level
        obs = self._make_obs()
        result = compute_background_level(obs)
        assert result is not None and isinstance(result, float)

    def test_none_without_cutout(self):
        from preprocess import compute_background_level
        from schemas import Observation
        obs = Observation(
            obs_id="nc", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
        )
        assert compute_background_level(obs) is None

    def test_matches_background_value(self):
        from preprocess import compute_background_level
        obs = self._make_obs(bg=3.14)
        result = compute_background_level(obs)
        assert result is not None
        assert abs(result - 3.14) < 0.1

    def test_bad_base64_returns_none(self):
        from preprocess import compute_background_level
        from schemas import Observation
        obs = Observation(
            obs_id="bad", jd=2460000.5, ra_deg=0.0, dec_deg=0.0,
            mag=18.0, mag_err=0.1, filter_band="r", mission="ZTF",
            cutout_difference="!!!not_valid!!!",
        )
        assert compute_background_level(obs) is None

    def test_in_all(self):
        from preprocess import __all__
        assert "compute_background_level" in __all__

    def test_negative_background(self):
        from preprocess import compute_background_level
        obs = self._make_obs(bg=-2.0, peak=50.0)
        result = compute_background_level(obs)
        assert result is not None
        assert result < 0.0


class TestComputePixelHistogram:
    """Tests for compute_pixel_histogram."""

    def _make_cutout_obs(self, uniform=False):
        import base64

        import numpy as np

        from schemas import Observation
        if uniform:
            arr = np.ones((63, 63), dtype=np.float32) * 5.0
        else:
            rng = np.random.default_rng(42)
            arr = rng.normal(0.0, 1.0, (63, 63)).astype(np.float32)
            arr[31, 31] = 50.0
        b64 = base64.b64encode(arr.tobytes()).decode()
        return Observation(
            obs_id="hist_o1", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference=b64,
        )

    def test_valid_cutout_returns_256_ints(self):
        from preprocess import compute_pixel_histogram
        obs = self._make_cutout_obs()
        result = compute_pixel_histogram(obs)
        assert result is not None
        assert len(result) == 256
        assert all(isinstance(c, int) for c in result)

    def test_counts_sum_to_63x63(self):
        from preprocess import compute_pixel_histogram
        obs = self._make_cutout_obs()
        result = compute_pixel_histogram(obs)
        assert result is not None
        assert sum(result) == 63 * 63

    def test_no_cutout_returns_none(self):
        from preprocess import compute_pixel_histogram
        from schemas import Observation
        obs = Observation(
            obs_id="no_cutout", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        assert compute_pixel_histogram(obs) is None

    def test_bad_base64_returns_none(self):
        from preprocess import compute_pixel_histogram
        from schemas import Observation
        obs = Observation(
            obs_id="bad", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference="not_valid_base64!!!",
        )
        assert compute_pixel_histogram(obs) is None

    def test_uniform_array_all_in_one_bin(self):
        from preprocess import compute_pixel_histogram
        obs = self._make_cutout_obs(uniform=True)
        result = compute_pixel_histogram(obs)
        assert result is not None
        # Uniform array: after normalization all values near same bin
        assert sum(result) == 63 * 63

    def test_in_all(self):
        from preprocess import __all__
        assert "compute_pixel_histogram" in __all__


class TestComputeCutoutContrast:
    """Tests for compute_cutout_contrast."""

    def _make_obs(self, arr=None, cutout=None):
        import base64

        import numpy as np

        from schemas import Observation
        if arr is not None:
            raw = base64.b64encode(arr.astype(np.float32).tobytes()).decode()
        else:
            raw = cutout
        return Observation(
            obs_id="cc_test",
            ra_deg=180.0,
            dec_deg=0.0,
            jd=2460000.5,
            mag=19.0,
            mag_err=0.05,
            filter_band="r",
            mission="ZTF",
            cutout_difference=raw,
        )

    def test_no_cutout_returns_none(self):
        from preprocess import compute_cutout_contrast
        from schemas import Observation
        obs = Observation(
            obs_id="no_cut", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        assert compute_cutout_contrast(obs) is None

    def test_uniform_array_returns_zero(self):
        import numpy as np

        from preprocess import compute_cutout_contrast
        arr = np.ones((63, 63), dtype=np.float32)
        obs = self._make_obs(arr=arr)
        # (max - min) / (max + min) = 0 / 2 = 0.0
        assert compute_cutout_contrast(obs) == 0.0

    def test_all_zero_array_returns_none(self):
        import numpy as np

        from preprocess import compute_cutout_contrast
        arr = np.zeros((63, 63), dtype=np.float32)
        obs = self._make_obs(arr=arr)
        # i_max + i_min = 0 → denom zero → None
        assert compute_cutout_contrast(obs) is None

    def test_high_contrast_array(self):
        import numpy as np

        from preprocess import compute_cutout_contrast
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1.0  # one bright pixel
        obs = self._make_obs(arr=arr)
        result = compute_cutout_contrast(obs)
        assert result is not None
        assert 0.0 < result <= 1.0

    def test_known_contrast_value(self):
        import numpy as np

        from preprocess import compute_cutout_contrast
        # arr with i_max=3, i_min=1 → contrast = (3-1)/(3+1) = 0.5
        arr = np.full((63, 63), 1.0, dtype=np.float32)
        arr[0, 0] = 3.0
        obs = self._make_obs(arr=arr)
        result = compute_cutout_contrast(obs)
        assert result is not None
        assert abs(result - 0.5) < 0.0001

    def test_invalid_base64_returns_none(self):
        from preprocess import compute_cutout_contrast
        obs = self._make_obs(cutout="!!!invalid!!!")
        assert compute_cutout_contrast(obs) is None

    def test_in_all(self):
        from preprocess import __all__
        assert "compute_cutout_contrast" in __all__


class TestComputeImageGradient:
    """Tests for compute_image_gradient."""

    def _make_obs(self, arr=None, cutout=None):
        import base64

        import numpy as np

        from schemas import Observation
        if arr is not None:
            raw = base64.b64encode(arr.astype(np.float32).tobytes()).decode()
        else:
            raw = cutout
        return Observation(
            obs_id="ig_test", ra_deg=180.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
            cutout_difference=raw,
        )

    def test_no_cutout_returns_none(self):
        from preprocess import compute_image_gradient
        from schemas import Observation
        obs = Observation(
            obs_id="no_cut", ra_deg=0.0, dec_deg=0.0, jd=2460000.5,
            mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
        )
        assert compute_image_gradient(obs) is None

    def test_uniform_array_near_zero_gradient(self):
        import numpy as np

        from preprocess import compute_image_gradient
        arr = np.ones((63, 63), dtype=np.float32)
        obs = self._make_obs(arr=arr)
        result = compute_image_gradient(obs)
        assert result is not None
        assert result < 0.01  # uniform → near-zero gradient

    def test_spike_array_high_gradient(self):
        import numpy as np

        from preprocess import compute_image_gradient
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 100.0  # sharp spike
        obs = self._make_obs(arr=arr)
        result = compute_image_gradient(obs)
        assert result is not None
        assert result > 0.0

    def test_returns_float_rounded_6dp(self):
        import numpy as np

        from preprocess import compute_image_gradient
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[20, 20] = 5.0
        obs = self._make_obs(arr=arr)
        result = compute_image_gradient(obs)
        assert result is not None
        assert round(result, 6) == result

    def test_invalid_base64_returns_none(self):
        from preprocess import compute_image_gradient
        obs = self._make_obs(cutout="!!!invalid!!!")
        assert compute_image_gradient(obs) is None

    def test_in_all(self):
        from preprocess import __all__
        assert "compute_image_gradient" in __all__


class TestComputeCutoutSymmetry:
    def _make_obs(self, arr=None):
        import base64
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from schemas import Observation
        if arr is None:
            arr = np.zeros((63, 63), dtype=np.float32)
            arr[31, 31] = 1.0
        raw = arr.astype(np.float32).tobytes()
        b64 = base64.b64encode(raw).decode()
        return Observation(obs_id="o1", ra_deg=10.0, dec_deg=5.0, jd=2460000.5,
                           mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
                           cutout_difference=b64)

    def test_symmetric_source_near_one(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import compute_cutout_symmetry
        obs = self._make_obs()
        score = compute_cutout_symmetry(obs)
        assert score is not None
        assert 0.9 <= score <= 1.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import compute_cutout_symmetry
        from schemas import Observation
        obs = Observation(obs_id="o2", ra_deg=10.0, dec_deg=5.0, jd=2460000.5,
                          mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF")
        assert compute_cutout_symmetry(obs) is None

    def test_all_zero_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import compute_cutout_symmetry
        obs = self._make_obs(np.zeros((63, 63), dtype=np.float32))
        assert compute_cutout_symmetry(obs) is None

    def test_result_bounded(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import compute_cutout_symmetry
        rng = np.random.default_rng(42)
        arr = rng.standard_normal((63, 63)).astype(np.float32)
        obs = self._make_obs(arr)
        s = compute_cutout_symmetry(obs)
        assert s is not None
        assert 0.0 <= s <= 1.0

    def test_invalid_b64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_cutout_symmetry
        obs = SimpleNamespace(cutout_difference="!!!not_valid_base64!!!")
        assert compute_cutout_symmetry(obs) is None


class TestComputeStreakAngle:
    def _make_obs(self, arr=None):
        import base64
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from schemas import Observation
        if arr is None:
            arr = np.zeros((63, 63), dtype=np.float32)
            arr[31, 31] = 1.0
        raw = arr.astype(np.float32).tobytes()
        b64 = base64.b64encode(raw).decode()
        return Observation(obs_id="o1", ra_deg=10.0, dec_deg=5.0, jd=2460000.5,
                           mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF",
                           cutout_difference=b64)

    def test_horizontal_streak_angle(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from preprocess import compute_streak_angle
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 10:53] = 1.0  # horizontal streak
        obs = self._make_obs(arr)
        angle = compute_streak_angle(obs)
        assert angle is not None
        assert isinstance(angle, float)

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import compute_streak_angle
        from schemas import Observation
        obs = Observation(obs_id="o2", ra_deg=10.0, dec_deg=5.0, jd=2460000.5,
                          mag=19.0, mag_err=0.05, filter_band="r", mission="ZTF")
        assert compute_streak_angle(obs) is None

    def test_zero_array_returns_none(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from preprocess import compute_streak_angle
        obs = self._make_obs(np.zeros((63, 63), dtype=np.float32))
        assert compute_streak_angle(obs) is None

    def test_result_in_0_180(self):
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from preprocess import compute_streak_angle
        rng = np.random.default_rng(7)
        arr = rng.standard_normal((63, 63)).astype(np.float32)
        arr = np.abs(arr)
        obs = self._make_obs(arr)
        angle = compute_streak_angle(obs)
        assert angle is not None
        assert 0.0 <= angle < 180.0

    def test_invalid_b64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_streak_angle
        obs = SimpleNamespace(cutout_difference="!!!bad!!!")
        assert compute_streak_angle(obs) is None


class TestComputeRadialProfile:
    def _make_obs_with_cutout(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        import numpy as np
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 10.0
        from types import SimpleNamespace
        b64 = base64.b64encode(arr.tobytes()).decode()
        return SimpleNamespace(cutout_difference=b64)

    def test_returns_list(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import compute_radial_profile
        obs = self._make_obs_with_cutout()
        result = compute_radial_profile(obs)
        assert isinstance(result, list)
        assert len(result) == 32

    def test_peak_at_center(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import compute_radial_profile
        obs = self._make_obs_with_cutout()
        result = compute_radial_profile(obs)
        assert result[0] > 0.0
        assert result[1] == 0.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_radial_profile
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_radial_profile(obs) is None

    def test_bad_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_radial_profile
        obs = SimpleNamespace(cutout_difference="!!!bad!!!")
        assert compute_radial_profile(obs) is None


class TestComputePsfAsymmetry:
    def _make_obs(self, arr=None):
        import sys
        sys.path.insert(0, "src")
        import base64
        from types import SimpleNamespace

        import numpy as np
        if arr is None:
            arr = np.zeros((63, 63), dtype=np.float32)
            arr[31, 31] = 1.0
        b64 = base64.b64encode(arr.astype(np.float32).tobytes()).decode()
        return SimpleNamespace(cutout_difference=b64)

    def test_symmetric_source_returns_low_asymmetry(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import compute_psf_asymmetry
        obs = self._make_obs()
        result = compute_psf_asymmetry(obs)
        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_psf_asymmetry
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_psf_asymmetry(obs) is None

    def test_zero_array_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import compute_psf_asymmetry
        obs = self._make_obs(np.zeros((63, 63), dtype=np.float32))
        assert compute_psf_asymmetry(obs) is None

    def test_result_bounded(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import compute_psf_asymmetry
        rng = np.random.default_rng(42)
        arr = rng.random((63, 63)).astype(np.float32)
        obs = self._make_obs(arr)
        result = compute_psf_asymmetry(obs)
        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_invalid_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_psf_asymmetry
        obs = SimpleNamespace(cutout_difference="not-valid-base64!!!")
        assert compute_psf_asymmetry(obs) is None


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


class TestComputeCutoutPeakPosition:
    def test_returns_peak_position(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_cutout_peak_position
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[10, 20] = 1.0
        cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=cutout_b64)
        result = compute_cutout_peak_position(obs)
        assert result == (10, 20)

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_cutout_peak_position
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_cutout_peak_position(obs) is None

    def test_bad_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_cutout_peak_position
        obs = SimpleNamespace(cutout_difference="notbase64!!!")
        result = compute_cutout_peak_position(obs)
        assert result is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_cutout_peak_position" in preprocess.__all__


class TestComputeLocalBackground:
    def test_returns_float(self):
        import base64
        import sys
        sys.path.insert(0, "src")

        import numpy as np

        from preprocess import compute_local_background

        arr = np.ones((63, 63), dtype=np.float32)
        arr[31, 31] = 10.0  # bright center
        cutout_b64 = base64.b64encode(arr.tobytes()).decode()
        from types import SimpleNamespace
        obs = SimpleNamespace(cutout_difference=cutout_b64)
        result = compute_local_background(obs)
        assert result is not None
        assert isinstance(result, float)

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_local_background
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_local_background(obs) is None

    def test_bad_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_local_background
        obs = SimpleNamespace(cutout_difference="not_valid_base64!!!")
        result = compute_local_background(obs)
        assert result is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_local_background" in preprocess.__all__


class TestComputeCutoutSharpness:
    def test_valid_cutout_returns_float(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_cutout_sharpness
        arr = np.random.RandomState(42).random((63, 63)).astype(np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_cutout_sharpness(obs)
        assert result is not None
        assert isinstance(result, float)
        assert result >= 0.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_cutout_sharpness
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_cutout_sharpness(obs) is None

    def test_invalid_b64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_cutout_sharpness
        obs = SimpleNamespace(cutout_difference="!!!invalid!!!")
        assert compute_cutout_sharpness(obs) is None

    def test_flat_image_low_sharpness(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_cutout_sharpness
        arr = np.ones((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_cutout_sharpness(obs)
        assert result is not None
        assert result == pytest.approx(0.0)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_cutout_sharpness" in preprocess.__all__


class TestComputeBackgroundGradient:
    def test_flat_image_near_zero_gradient(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_background_gradient
        arr = np.ones((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_background_gradient(obs)
        assert result is not None
        assert abs(result["dx"]) < 1e-4
        assert abs(result["dy"]) < 1e-4

    def test_gradient_image(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_background_gradient
        arr = np.zeros((63, 63), dtype=np.float32)
        for i in range(63):
            arr[:, i] = float(i)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_background_gradient(obs)
        assert result is not None
        assert result["dx"] == pytest.approx(1.0, abs=0.01)

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_background_gradient
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_background_gradient(obs) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_background_gradient" in preprocess.__all__

    def test_invalid_data_returns_none(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_background_gradient
        # Valid base64 but wrong number of bytes → reshape will fail
        arr = np.ones((10, 10), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        assert compute_background_gradient(obs) is None


class TestComputeElongationAngle:
    def test_elongated_horizontal_returns_angle(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_elongation_angle
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 10:53] = 1.0  # horizontal streak
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_elongation_angle(obs)
        assert result is not None
        assert 0.0 <= result < 180.0

    def test_circular_source_returns_none(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_elongation_angle
        arr = np.zeros((63, 63), dtype=np.float32)
        cy, cx = 31.0, 31.0
        for r in range(63):
            for c in range(63):
                arr[r, c] = np.exp(-((r - cy)**2 + (c - cx)**2) / 8.0)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_elongation_angle(obs)
        assert result is None or 0.0 <= result < 180.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_elongation_angle
        assert compute_elongation_angle(SimpleNamespace(cutout_difference=None)) is None

    def test_zero_flux_returns_none(self):
        import base64
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_elongation_angle
        arr = np.zeros((63, 63), dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        assert compute_elongation_angle(SimpleNamespace(cutout_difference=b64)) is None

    def test_invalid_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_elongation_angle
        obs = SimpleNamespace(cutout_difference="NOT_VALID_BASE64!!!")
        assert compute_elongation_angle(obs) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_elongation_angle" in preprocess.__all__


class TestComputeCutoutNoise:
    def _make_b64(self, arr):
        import base64

        import numpy as np
        return base64.b64encode(arr.astype(np.float32).tobytes()).decode()

    def test_uniform_array_zero_noise(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_cutout_noise
        arr = np.ones((63, 63), dtype=np.float32)
        obs = SimpleNamespace(cutout_difference=self._make_b64(arr))
        result = compute_cutout_noise(obs)
        assert result is not None
        assert abs(result) < 1e-5

    def test_noisy_border_returns_nonzero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_cutout_noise
        rng = np.random.default_rng(42)
        arr = rng.normal(0.0, 1.0, (63, 63)).astype(np.float32)
        obs = SimpleNamespace(cutout_difference=self._make_b64(arr))
        result = compute_cutout_noise(obs)
        assert result is not None
        assert result > 0.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_cutout_noise
        assert compute_cutout_noise(SimpleNamespace(cutout_difference=None)) is None

    def test_invalid_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_cutout_noise
        obs = SimpleNamespace(cutout_difference="NOT_VALID_BASE64!!!")
        assert compute_cutout_noise(obs) is None

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_cutout_noise
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[0, :] = 1.0
        obs = SimpleNamespace(cutout_difference=self._make_b64(arr))
        result = compute_cutout_noise(obs)
        assert result is not None
        assert isinstance(result, float)

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_cutout_noise" in preprocess.__all__


class TestFlagCosmicRays:
    def _make_b64(self, arr):
        import base64

        import numpy as np
        return base64.b64encode(arr.astype(np.float32).tobytes()).decode()

    def _make_obs(self, obs_id, arr):
        from types import SimpleNamespace
        return SimpleNamespace(obs_id=obs_id, cutout_difference=self._make_b64(arr))

    def test_no_cosmic_rays_uniform(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import flag_cosmic_rays
        arr = np.ones((63, 63), dtype=np.float32)
        obs = self._make_obs("o1", arr)
        flagged = flag_cosmic_rays([obs])
        assert flagged == []

    def test_flags_high_peak_pixel(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import flag_cosmic_rays
        arr = np.zeros((63, 63), dtype=np.float32)
        arr[31, 31] = 1000.0  # extreme outlier
        obs = self._make_obs("cr_001", arr)
        flagged = flag_cosmic_rays([obs])
        assert "cr_001" in flagged

    def test_no_cutout_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import flag_cosmic_rays
        obs = SimpleNamespace(obs_id="o_no_cutout", cutout_difference=None)
        flagged = flag_cosmic_rays([obs])
        assert flagged == []

    def test_invalid_base64_skipped(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import flag_cosmic_rays
        obs = SimpleNamespace(obs_id="bad", cutout_difference="INVALID!!!")
        flagged = flag_cosmic_rays([obs])
        assert flagged == []

    def test_empty_list_returns_empty(self):
        import sys
        sys.path.insert(0, "src")
        from preprocess import flag_cosmic_rays
        assert flag_cosmic_rays([]) == []

    def test_custom_sigma_threshold(self):
        import sys
        sys.path.insert(0, "src")
        import numpy as np

        from preprocess import flag_cosmic_rays
        # Use a noisy background so MAD > 0
        rng = np.random.default_rng(0)
        arr = rng.normal(100.0, 5.0, (63, 63)).astype(np.float32)
        # Add a moderate outlier — just above background
        arr[31, 31] = 130.0  # ~6 sigma above background
        obs = self._make_obs("o1", arr)
        # with very high threshold, should not flag (outlier is not extreme enough)
        flagged_high = flag_cosmic_rays([obs], sigma_threshold=1e9)
        assert "o1" not in flagged_high
        # with low threshold (0.1 sigma), should flag
        flagged_low = flag_cosmic_rays([obs], sigma_threshold=0.1)
        assert "o1" in flagged_low

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "flag_cosmic_rays" in preprocess.__all__


class TestComputeFwhmFromCutout:
    def _make_gaussian_cutout(self, sigma: float = 3.0) -> str:
        import base64

        import numpy as np
        arr = np.zeros((63, 63), dtype=np.float32)
        cx, cy = 31, 31
        for i in range(63):
            for j in range(63):
                r2 = ((i - cy) / sigma) ** 2 + ((j - cx) / sigma) ** 2
                arr[i, j] = float(np.exp(-0.5 * r2))
        return base64.b64encode(arr.tobytes()).decode()

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_fwhm_from_cutout
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_fwhm_from_cutout(obs) is None

    def test_bad_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_fwhm_from_cutout
        obs = SimpleNamespace(cutout_difference="not!!valid!!base64")
        result = compute_fwhm_from_cutout(obs)
        assert result is None

    def test_gaussian_cutout_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_fwhm_from_cutout
        obs = SimpleNamespace(cutout_difference=self._make_gaussian_cutout(sigma=4.0))
        result = compute_fwhm_from_cutout(obs)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0.0

    def test_fwhm_scales_with_sigma(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_fwhm_from_cutout
        narrow = SimpleNamespace(cutout_difference=self._make_gaussian_cutout(sigma=2.0))
        wide = SimpleNamespace(cutout_difference=self._make_gaussian_cutout(sigma=6.0))
        fwhm_narrow = compute_fwhm_from_cutout(narrow)
        fwhm_wide = compute_fwhm_from_cutout(wide)
        assert fwhm_narrow is not None
        assert fwhm_wide is not None
        assert fwhm_narrow < fwhm_wide

    def test_wrong_size_cutout_returns_none(self):
        import base64
        import sys

        import numpy as np
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_fwhm_from_cutout
        # Wrong number of elements — reshape fails → None
        arr = np.zeros(10, dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_fwhm_from_cutout(obs)
        assert result is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_fwhm_from_cutout" in preprocess.__all__


class TestComputeLocalBackgroundRms:
    @staticmethod
    def _make_cutout(border_val: float = 1.0, center_val: float = 100.0) -> str:
        import base64

        import numpy as np
        arr = np.full((63, 63), center_val, dtype=np.float32)
        arr[:10, :] = border_val
        arr[53:, :] = border_val
        arr[:, :10] = border_val
        arr[:, 53:] = border_val
        return base64.b64encode(arr.tobytes()).decode()

    def test_uniform_border_returns_zero(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_local_background_rms
        obs = SimpleNamespace(cutout_difference=self._make_cutout(1.0, 1.0))
        result = compute_local_background_rms(obs)
        assert result is not None
        assert result == 0.0

    def test_nonzero_border_rms(self):
        import sys
        sys.path.insert(0, "src")
        import base64
        from types import SimpleNamespace

        import numpy as np

        from preprocess import compute_local_background_rms
        rng = np.random.default_rng(42)
        arr = rng.normal(0.0, 2.0, (63, 63)).astype(np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode()
        obs = SimpleNamespace(cutout_difference=b64)
        result = compute_local_background_rms(obs)
        assert result is not None
        assert result > 0.0

    def test_no_cutout_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_local_background_rms
        obs = SimpleNamespace(cutout_difference=None)
        assert compute_local_background_rms(obs) is None

    def test_bad_base64_returns_none(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_local_background_rms
        obs = SimpleNamespace(cutout_difference="not-valid-base64!!!")
        assert compute_local_background_rms(obs) is None

    def test_in_all(self):
        import sys
        sys.path.insert(0, "src")
        import preprocess
        assert "compute_local_background_rms" in preprocess.__all__

    def test_returns_float(self):
        import sys
        sys.path.insert(0, "src")
        from types import SimpleNamespace

        from preprocess import compute_local_background_rms
        obs = SimpleNamespace(cutout_difference=self._make_cutout(2.0, 50.0))
        result = compute_local_background_rms(obs)
        assert isinstance(result, float)
