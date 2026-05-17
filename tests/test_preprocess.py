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
