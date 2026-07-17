"""Tests for Skills/ztf_dr24_bounded_ingest.py (Gate Z1 bounded ingest tool).

All network calls are mocked -- this project's standing convention for
external-service tests. The IPAC fixture text is generated with astropy's
own IPAC writer so the parser under test is exercised against a real,
library-round-tripped table, not a hand-typed guess at the format.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from astropy.io import ascii as ap_ascii
from astropy.table import Table

# Skills/ scripts are not an installed package -- load by path, matching how
# they are invoked in practice (`uv run python Skills/....py`).
_MODULE_PATH = Path(__file__).resolve().parents[1] / "Skills" / "ztf_dr24_bounded_ingest.py"
_spec = importlib.util.spec_from_file_location("ztf_dr24_bounded_ingest", _MODULE_PATH)
ztf_dr24_bounded_ingest = importlib.util.module_from_spec(_spec)
sys.modules["ztf_dr24_bounded_ingest"] = ztf_dr24_bounded_ingest
_spec.loader.exec_module(ztf_dr24_bounded_ingest)


def _ipac_response_text(
    query_status: str = "OK", n_rows: int = 2, obsjd_values: list[float] | None = None
) -> str:
    """Build a realistic IPAC table response using astropy's own writer, with
    the header lines the live IRSA response includes (RowsRetrieved,
    QUERY_STATUS) prepended, matching the captured Phase 0 evidence format."""
    if obsjd_values is None:
        obsjd_values = [2460310.7 + i for i in range(n_rows)]
    n_rows = len(obsjd_values)
    table = Table()
    table["ra"] = [10.0 + 0.1 * i for i in range(n_rows)]
    table["dec"] = [20.0 + 0.1 * i for i in range(n_rows)]
    table["field"] = [100 + i for i in range(n_rows)]
    table["ccdid"] = [1] * n_rows
    table["qid"] = [1] * n_rows
    table["rcid"] = [0] * n_rows
    table["fid"] = [1] * n_rows
    table["filtercode"] = ["zg"] * n_rows
    table["pid"] = [1000 + i for i in range(n_rows)]
    table["obsdate"] = [f"2024-01-{i + 1:02d} 05:00:00" for i in range(n_rows)]
    table["obsjd"] = obsjd_values
    table["filefracday"] = [20240101000000 + i for i in range(n_rows)]
    table["imgtypecode"] = ["o"] * n_rows
    table["exptime"] = [30.0] * n_rows
    table["seeing"] = [2.1] * n_rows
    table["maglimit"] = [20.5] * n_rows
    table["infobits"] = [0] * n_rows
    table["ipac_pub_date"] = ["2024-01-02 00:00:00"] * n_rows

    buf = io.StringIO()
    ap_ascii.write(table, buf, format="ipac")
    header = f"\\fixlen = T\n\\RowsRetrieved = {n_rows}\n\\QUERY_STATUS = '{query_status}'\n"
    return header + buf.getvalue()


class _FakeResponse:
    def __init__(
        self,
        text: str = "",
        status: int = 200,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ):
        self.text = text
        self.status_code = status
        self.headers = headers or {}
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _synthetic_difference_image_fits_bytes(
    size: int = 50,
    source_xy: tuple[int, int] = (25, 25),
    source_peak: float = 500.0,
    seed: int = 7,
) -> bytes:
    """Build a small synthetic ZTF-like difference image: Gaussian background
    noise plus one bright injected point source, with a real TAN WCS header,
    written via astropy's own FITS writer so the reader under test is
    exercised against a real, library-round-tripped file rather than a
    hand-typed byte layout."""
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    rng = np.random.default_rng(seed)
    data = rng.normal(loc=0.0, scale=5.0, size=(size, size)).astype(np.float32)
    y0, x0 = source_xy
    data[y0, x0] += source_peak

    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [size / 2, size / 2]
    wcs.wcs.cdelt = [-1.0 / 3600, 1.0 / 3600]
    wcs.wcs.crval = [232.6, -8.4]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]

    hdu = fits.PrimaryHDU(data=data, header=wcs.to_header())
    buf = io.BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


def test_run_bounded_ingest_writes_report(tmp_path):
    """A successful fetch parses the table and writes a correct sample-ingest
    report, including a stable sha256 of the raw response."""
    with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(n_rows=2))):
        report = ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=358.3, dec=25.6, size_deg=0.2, start_jd=2460310.5, end_jd=2460312.5, out_dir=tmp_path
        )
    assert report["n_rows"] == 2
    assert report["n_distinct_fields"] == 2
    assert report["n_distinct_nights"] == 2
    assert len(report["raw_response_sha256"]) == 64


def test_motion_product_manifest_uses_documented_urls_without_download(tmp_path):
    """Optional planning mode must derive the four source-native product URLs
    from metadata while making no request beyond the one metadata GET."""
    with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(n_rows=1))) as get:
        report = ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=358.3,
            dec=25.6,
            size_deg=0.2,
            start_jd=2460310.5,
            end_jd=2460311.5,
            out_dir=tmp_path,
            emit_motion_product_manifest=True,
        )
    assert get.call_count == 1
    manifest_path = Path(report["motion_product_manifest_path"])
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema_version"] == "ztf-dr24-motion-product-manifest-v1"
    assert manifest["data_role"] == "live_search"
    assert manifest["quality_filter"] == "infobits < 33554432"
    assert manifest["n_exposures"] == 1
    exposure = manifest["exposures"][0]
    assert exposure["availability"] == "unverified"
    assert exposure["product_urls"] == {
        "difference_image": (
            "https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/2024/0101/000000/"
            "ztf_20240101000000_000100_zg_c01_o_q1_scimrefdiffimg.fits.fz"
        ),
        "science_mask": (
            "https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/2024/0101/000000/"
            "ztf_20240101000000_000100_zg_c01_o_q1_mskimg.fits"
        ),
        "science_psf_catalog": (
            "https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/2024/0101/000000/"
            "ztf_20240101000000_000100_zg_c01_o_q1_psfcat.fits"
        ),
        "difference_psf": (
            "https://irsa.ipac.caltech.edu/ibe/data/ztf/products/sci/2024/0101/000000/"
            "ztf_20240101000000_000100_zg_c01_o_q1_diffimgpsf.fits"
        ),
    }


def test_motion_product_manifest_fails_closed_on_missing_metadata_column():
    """A stale or altered IRSA response must not produce guessed product URLs."""
    table = Table()
    table["pid"] = [1]
    with pytest.raises(RuntimeError, match="missing motion-manifest columns"):
        ztf_dr24_bounded_ingest._build_motion_product_manifest(table, {}, "0" * 64)


def test_science_product_url_rejects_malformed_identifiers():
    """Malformed metadata must fail before a plausible archive URL is emitted."""
    table = ap_ascii.read(_ipac_response_text(n_rows=1), format="ipac")
    table["ccdid"][0] = 17
    with pytest.raises(ValueError, match="invalid ZTF product identifiers"):
        ztf_dr24_bounded_ingest._science_product_url(table[0], "psfcat.fits")


def test_motion_product_preflight_records_headers_and_bytes(tmp_path):
    """A bounded HEAD preflight must verify every product and download no body."""
    head_response = _FakeResponse(
        status=200,
        headers={"content-length": "1024", "content-type": "application/octet-stream"},
    )
    with (
        patch("requests.get", return_value=_FakeResponse(_ipac_response_text(n_rows=1))),
        patch("requests.head", return_value=head_response) as head,
    ):
        report = ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=358.3,
            dec=25.6,
            size_deg=0.2,
            start_jd=2460310.5,
            end_jd=2460311.5,
            out_dir=tmp_path,
            preflight_motion_products=True,
            max_preflight_exposures=1,
            preflight_workers=4,
        )
    assert head.call_count == 4
    assert report["motion_product_preflight"]["status"] == "passed"
    assert report["motion_product_preflight"]["total_content_bytes"] == 4096
    manifest = json.loads(Path(report["motion_product_manifest_path"]).read_text())
    assert manifest["exposures"][0]["availability"] == "verified"
    assert manifest["exposures"][0]["verified_content_bytes"] == 4096


def test_motion_product_preflight_resumes_completed_heads(tmp_path):
    """A repeated preflight must reuse its per-product checkpoint."""
    table = ap_ascii.read(_ipac_response_text(n_rows=1), format="ipac")
    manifest = ztf_dr24_bounded_ingest._build_motion_product_manifest(table, {}, "a" * 64)
    checkpoint_path = tmp_path / "preflight.json"
    response = _FakeResponse(status=200, headers={"content-length": "2"})
    with patch("requests.head", return_value=response) as head:
        ztf_dr24_bounded_ingest._preflight_motion_products(manifest, checkpoint_path, 1, 2)
        assert head.call_count == 4
        manifest = ztf_dr24_bounded_ingest._build_motion_product_manifest(
            table, {}, "a" * 64
        )
        ztf_dr24_bounded_ingest._preflight_motion_products(manifest, checkpoint_path, 1, 2)
    assert head.call_count == 4


def test_motion_product_preflight_rejects_exposure_overflow_before_head(tmp_path):
    """The explicit exposure cap must prevent an accidental broad HEAD sweep."""
    table = ap_ascii.read(_ipac_response_text(n_rows=2), format="ipac")
    manifest = ztf_dr24_bounded_ingest._build_motion_product_manifest(table, {}, "b" * 64)
    with patch("requests.head") as head:
        with pytest.raises(ValueError, match="exceeding the explicit cap"):
            ztf_dr24_bounded_ingest._preflight_motion_products(
                manifest, tmp_path / "preflight.json", 1, 1
            )
    head.assert_not_called()


def test_motion_product_preflight_rejects_empty_or_zero_byte_products(tmp_path):
    """An empty plan or a zero-byte file must never pass availability gates."""
    with pytest.raises(ValueError, match="at least one exposure"):
        ztf_dr24_bounded_ingest._preflight_motion_products(
            {"raw_metadata_sha256": "c" * 64, "exposures": []},
            tmp_path / "empty.json",
            1,
            1,
        )

    table = ap_ascii.read(_ipac_response_text(n_rows=1), format="ipac")
    manifest = ztf_dr24_bounded_ingest._build_motion_product_manifest(table, {}, "d" * 64)
    with patch(
        "requests.head",
        return_value=_FakeResponse(status=200, headers={"content-length": "0"}),
    ):
        result = ztf_dr24_bounded_ingest._preflight_motion_products(
            manifest, tmp_path / "zero.json", 1, 1
        )
    assert result["preflight"]["status"] == "failed"
    assert result["preflight"]["total_content_bytes"] == 0


def test_motion_product_preflight_fails_closed_on_missing_product(tmp_path):
    """A missing required product must write evidence and fail the caller."""
    responses = [
        _FakeResponse(status=404),
        *[
            _FakeResponse(status=200, headers={"content-length": "10"})
            for _ in range(3)
        ],
    ]
    with (
        patch("requests.get", return_value=_FakeResponse(_ipac_response_text(n_rows=1))),
        patch("requests.head", side_effect=responses),
    ):
        with pytest.raises(RuntimeError, match="preflight failed"):
            ztf_dr24_bounded_ingest.run_bounded_ingest(
                ra=358.3,
                dec=25.6,
                size_deg=0.2,
                start_jd=2460310.5,
                end_jd=2460311.5,
                out_dir=tmp_path,
                preflight_motion_products=True,
                max_preflight_exposures=1,
                preflight_workers=1,
            )
    manifest_paths = list(tmp_path.glob("*/motion_product_manifest.json"))
    assert len(manifest_paths) == 1
    manifest = json.loads(manifest_paths[0].read_text())
    assert manifest["preflight"]["status"] == "failed"


def test_motion_product_preflight_checkpoints_transport_failure(tmp_path):
    """An exhausted transport retry must be recorded while siblings finish."""
    table = ap_ascii.read(_ipac_response_text(n_rows=1), format="ipac")
    manifest = ztf_dr24_bounded_ingest._build_motion_product_manifest(table, {}, "e" * 64)
    good = _FakeResponse(status=200, headers={"content-length": "10"})
    with patch.object(
        ztf_dr24_bounded_ingest,
        "_head_with_retry",
        side_effect=[RuntimeError("network exhausted"), good, good, good],
    ):
        result = ztf_dr24_bounded_ingest._preflight_motion_products(
            manifest, tmp_path / "transport.json", 1, 1
        )
    assert result["preflight"]["status"] == "failed"
    assert result["preflight"]["checked_products"] == 4
    checkpoint = json.loads((tmp_path / "transport.json").read_text())
    failures = [item for item in checkpoint["results"].values() if item["error"]]
    assert len(failures) == 1
    assert failures[0]["error"] == "network exhausted"


def test_head_with_retry_recovers_and_exhausts():
    """HEAD transport failures follow the bounded five-attempt retry policy."""
    success = _FakeResponse(status=200, headers={"content-length": "1"})
    with (
        patch("time.sleep"),
        patch("requests.head", side_effect=[ConnectionError("temporary"), success]) as head,
    ):
        response = ztf_dr24_bounded_ingest._head_with_retry("https://example.invalid/product")
    assert response is success
    assert head.call_count == 2

    with (
        patch("time.sleep"),
        patch("requests.head", side_effect=ConnectionError("persistent")) as head,
    ):
        with pytest.raises(RuntimeError, match="HEAD failed after 5 attempts"):
            ztf_dr24_bounded_ingest._head_with_retry("https://example.invalid/product")
    assert head.call_count == 5


def test_motion_product_preflight_rejects_malformed_checkpoint(tmp_path):
    """Unknown schemas and non-mapping results fail before any network call."""
    table = ap_ascii.read(_ipac_response_text(n_rows=1), format="ipac")
    manifest = ztf_dr24_bounded_ingest._build_motion_product_manifest(table, {}, "f" * 64)
    checkpoint = tmp_path / "malformed.json"
    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "unknown",
                "raw_metadata_sha256": "f" * 64,
                "results": {},
            }
        )
    )
    with patch("requests.head") as head:
        with pytest.raises(RuntimeError, match="unsupported schema"):
            ztf_dr24_bounded_ingest._preflight_motion_products(
                manifest, checkpoint, 1, 1
            )
    head.assert_not_called()

    checkpoint.write_text(
        json.dumps(
            {
                "schema_version": "ztf-dr24-motion-product-preflight-v1",
                "raw_metadata_sha256": "f" * 64,
                "results": [],
            }
        )
    )
    with pytest.raises(RuntimeError, match="invalid results"):
        ztf_dr24_bounded_ingest._preflight_motion_products(manifest, checkpoint, 1, 1)


def test_run_bounded_ingest_reports_real_night_dates(tmp_path):
    """The report must expose which real calendar nights (YYYYMMDD, matching
    the alert archive's ztf_public_YYYYMMDD.tar.gz naming) had coverage --
    a bare distinct-night count is not enough to target a follow-up
    alert-archive ingest run without guessing."""
    with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(n_rows=2))):
        report = ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=358.3, dec=25.6, size_deg=0.2, start_jd=2460310.5, end_jd=2460312.5, out_dir=tmp_path
        )
    # obsjd values 2460310.7 and 2460311.7 in the fixture correspond to real
    # distinct UTC calendar nights -- confirm both are reported and sorted.
    assert report["distinct_nights_yyyymmdd"] == sorted(report["distinct_nights_yyyymmdd"])
    assert len(report["distinct_nights_yyyymmdd"]) == 2
    assert all(len(d) == 8 and d.isdigit() for d in report["distinct_nights_yyyymmdd"])


def test_night_date_matches_known_real_archive_night(tmp_path):
    """Regression test for a real off-by-one: JD increments at NOON UTC, not
    midnight, so truncating obsjd to an integer before converting to a
    calendar date silently lands on the day BEFORE the correct one whenever
    the fractional part is < 0.5. This exact obsjd (2458339.6521991) is a
    real value from a packet already confirmed (via a live download and
    schema inspection in an earlier gate) to originate in the real archive
    file ztf_public_20180809.tar.gz -- so it MUST map to '20180809', not
    '20180808'. An operator live run hit this exact bug live before this
    fix (reported '20180808' for a 100-day window starting at this night)."""
    with patch(
        "requests.get",
        return_value=_FakeResponse(_ipac_response_text(obsjd_values=[2458339.6521991])),
    ):
        report = ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=232.6, dec=-8.4, size_deg=2.0, start_jd=2458339.5, end_jd=2458340.5, out_dir=tmp_path
        )
    assert report["distinct_nights_yyyymmdd"] == ["20180809"]


def test_run_bounded_ingest_resumes_without_network_call(tmp_path):
    """Re-running the identical command must not re-fetch -- it should
    resume from the checkpoint written by the first run."""
    with patch("requests.get", return_value=_FakeResponse(_ipac_response_text())) as mock_get:
        ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=1.0, dec=2.0, size_deg=0.1, start_jd=2460310.5, end_jd=2460311.5, out_dir=tmp_path
        )
        assert mock_get.call_count == 1

        # Second run with identical params: must resume, not re-fetch.
        report = ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=1.0, dec=2.0, size_deg=0.1, start_jd=2460310.5, end_jd=2460311.5, out_dir=tmp_path
        )
        assert mock_get.call_count == 1
    assert report["n_rows"] == 2


def test_run_bounded_ingest_rejects_oversized_search_box(tmp_path):
    with pytest.raises(ValueError, match="size_deg"):
        ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=1.0, dec=2.0, size_deg=999.0, start_jd=2460310.5, end_jd=2460311.5, out_dir=tmp_path
        )


def test_run_bounded_ingest_rejects_oversized_time_window(tmp_path):
    with pytest.raises(ValueError, match="bounded cap"):
        ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=1.0, dec=2.0, size_deg=0.1, start_jd=2460000.5, end_jd=2461000.5, out_dir=tmp_path
        )


def test_run_bounded_ingest_rejects_inverted_window(tmp_path):
    with pytest.raises(ValueError, match="greater than"):
        ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=1.0, dec=2.0, size_deg=0.1, start_jd=2460311.5, end_jd=2460310.5, out_dir=tmp_path
        )


def test_fetch_with_retry_recovers_after_transient_failure():
    """Transient connection errors must be retried, not fatal on first try."""
    with patch("time.sleep"):  # do not actually wait during the test
        with patch(
            "requests.get",
            side_effect=[ConnectionError("boom"), _FakeResponse(_ipac_response_text())],
        ):
            resp = ztf_dr24_bounded_ingest._fetch_with_retry("https://example.invalid/probe")
    assert resp.status_code == 200


def test_fetch_with_retry_raises_after_exhausting_attempts():
    with patch("time.sleep"):
        with patch("requests.get", side_effect=ConnectionError("still down")):
            with pytest.raises(RuntimeError, match="failed after 5 attempts"):
                ztf_dr24_bounded_ingest._fetch_with_retry("https://example.invalid/probe")


def test_parse_ipac_table_fails_closed_on_bad_query_status():
    """A non-OK QUERY_STATUS must raise, not silently return an empty/garbage
    table -- fail-closed per the standing conservative-by-default rule."""
    bad_text = _ipac_response_text(query_status="ERROR")
    with pytest.raises(RuntimeError, match="QUERY_STATUS"):
        ztf_dr24_bounded_ingest._parse_ipac_table(bad_text)


def test_build_url_includes_pos_size_where_columns():
    """URL construction uses the documented IRSA IBE parameter names
    (POS/SIZE/WHERE/COLUMNS) -- not invented ones."""
    url = ztf_dr24_bounded_ingest._build_url(358.3, 25.6, 0.2, 2460310.5, 2460311.5)
    assert "POS=358.3,25.6" in url
    assert "SIZE=0.2" in url
    assert (
        "WHERE=obsjd>2460310.5+AND+obsjd<2460311.5+AND+infobits<33554432" in url
    )
    assert "COLUMNS=" in url


def test_detect_sources_in_difference_image_finds_injected_point_source():
    """The minimal detector must recover an injected bright point source at
    approximately its true WCS-derived RA/Dec, not just report a count."""
    from astropy.wcs import WCS

    fits_bytes = _synthetic_difference_image_fits_bytes(source_xy=(25, 25), source_peak=500.0)
    result = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(fits_bytes)

    assert result["n_candidate_sources"] >= 1
    top = result["sources"][0]  # ranked by peak brightness

    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [25.0, 25.0]
    wcs.wcs.cdelt = [-1.0 / 3600, 1.0 / 3600]
    wcs.wcs.crval = [232.6, -8.4]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    expected_ra, expected_dec = wcs.all_pix2world(25.0, 25.0, 0)

    assert top["x"] == 25 and top["y"] == 25
    assert abs(top["ra_deg"] - float(expected_ra)) < 1e-6
    assert abs(top["dec_deg"] - float(expected_dec)) < 1e-6
    assert top["snr"] > ztf_dr24_bounded_ingest._PIXEL_PILOT_DETECTION_SIGMA


def test_detect_sources_in_difference_image_caps_output_count():
    """A noisy image must never return more than the configured cap, however
    many connected components clear the detection threshold -- and must
    report the true pre-cap count rather than silently truncating
    (no-silent-caps rule)."""
    fits_bytes = _synthetic_difference_image_fits_bytes(source_peak=500.0)
    result = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(
        fits_bytes, max_sources=1
    )
    assert result["n_candidate_sources"] <= 1
    assert result["n_candidate_sources_cap"] == 1
    assert result["n_connected_components"] >= result["n_candidate_sources"]
    assert result["n_candidate_sources_truncated"] == (
        result["n_connected_components"] > 1
    )


def test_detect_sources_in_difference_image_reports_untruncated_when_under_cap():
    """When every clearing component fits under the cap, truncation must read
    False rather than defaulting to a misleading truthy value."""
    fits_bytes = _synthetic_difference_image_fits_bytes(source_peak=500.0)
    result = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(
        fits_bytes, max_sources=1000
    )
    assert result["n_candidate_sources_truncated"] is False
    assert result["n_candidate_sources"] == result["n_connected_components"]


def test_detect_sources_deduplicates_adjacent_pixels_into_one_component():
    """The exact real-world fix this session made: a multi-pixel blob (one
    physical residual spanning several adjacent pixels) must collapse into
    ONE candidate source via connected-component labeling, not be counted
    once per pixel the way the earlier local-maximum approach did."""
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    size = 50
    rng = np.random.default_rng(11)
    data = rng.normal(loc=0.0, scale=5.0, size=(size, size)).astype(np.float32)
    # A solid 3x3 block of bright pixels -- one connected blob, 9 pixels.
    data[20:23, 20:23] += 500.0

    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [size / 2, size / 2]
    wcs.wcs.cdelt = [-1.0 / 3600, 1.0 / 3600]
    wcs.wcs.crval = [232.6, -8.4]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    hdu = fits.PrimaryHDU(data=data, header=wcs.to_header())
    buf = io.BytesIO()
    hdu.writeto(buf)

    result = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(buf.getvalue())
    assert result["n_connected_components"] == 1
    assert result["n_pixels_above_threshold"] == 9
    assert result["sources"][0]["component_size_pixels"] == 9


def _synthetic_mask_fits_bytes(
    size: int = 50, flagged_xy: list[tuple[int, int]] | None = None
) -> bytes:
    """An all-zero (nothing flagged) mask by default, or with specific
    (x, y) pixels flagged nonzero when `flagged_xy` is given -- matching
    ZTF's science_mask product shape/semantics at the level this tiny
    pilot implements (any nonzero value means excluded)."""
    import numpy as np
    from astropy.io import fits

    mask = np.zeros((size, size), dtype=np.int32)
    for x, y in flagged_xy or []:
        mask[y, x] = 1
    hdu = fits.PrimaryHDU(data=mask)
    buf = io.BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


def test_detect_sources_excludes_masked_pixels():
    """A pixel flagged nonzero in the science_mask must never become a
    candidate source, even though it clears the brightness threshold --
    this is the real fix for the 855-candidate false-positive finding in
    docs/evidence/live/2026-07-16-ztf-dr24-pixel-extraction-pilot-first-live-run.md."""
    fits_bytes = _synthetic_difference_image_fits_bytes(source_xy=(25, 25), source_peak=500.0)
    mask_bytes = _synthetic_mask_fits_bytes(flagged_xy=[(25, 25)])

    unmasked = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(fits_bytes)
    assert unmasked["n_candidate_sources"] >= 1  # sanity: source is real without masking

    masked = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(
        fits_bytes, mask_fits_bytes=mask_bytes
    )
    assert masked["mask_applied"] is True
    assert masked["n_masked_pixels"] == 1
    assert all((s["x"], s["y"]) != (25, 25) for s in masked["sources"])


def test_detect_sources_mask_shape_mismatch_raises_loudly():
    """malformed -> FAIL LOUDLY: a mask that doesn't match the difference
    image's shape must never be silently applied (e.g. misaligned pixels
    would corrupt the result without warning)."""
    fits_bytes = _synthetic_difference_image_fits_bytes(size=50)
    mismatched_mask = _synthetic_mask_fits_bytes(size=40)
    with pytest.raises(ValueError, match="does not match difference image"):
        ztf_dr24_bounded_ingest._detect_sources_in_difference_image(
            fits_bytes, mask_fits_bytes=mismatched_mask
        )


def _synthetic_psf_fits_bytes(size: int = 9, sigma: float = 1.5) -> bytes:
    """A small 2D Gaussian PSF kernel, matching the general shape of a real
    ZTF difference_psf product (a compact point-spread-function image)."""
    import numpy as np
    from astropy.io import fits

    yy, xx = np.mgrid[0:size, 0:size]
    center = (size - 1) / 2
    kernel = np.exp(-(((xx - center) ** 2 + (yy - center) ** 2) / (2 * sigma**2)))
    kernel = (kernel / kernel.sum()).astype(np.float32)
    hdu = fits.PrimaryHDU(data=kernel)
    buf = io.BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


def test_psf_shape_correlation_high_for_matching_gaussian_source():
    """Independent-oracle test: a source injected with the SAME Gaussian
    shape as the PSF kernel must correlate near 1.0 -- this is the direct
    check that psf_correlation actually measures shape similarity, not just
    presence of a bright pixel."""
    import numpy as np
    from astropy.io import fits

    size = 50
    rng = np.random.default_rng(3)
    data = rng.normal(loc=0.0, scale=1.0, size=(size, size)).astype(np.float64)
    yy, xx = np.mgrid[0:size, 0:size]
    x0, y0 = 25, 25
    gaussian_source = 500.0 * np.exp(-(((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * 1.5**2)))
    data += gaussian_source

    psf_kernel_bytes = _synthetic_psf_fits_bytes(size=9, sigma=1.5)
    with fits.open(io.BytesIO(psf_kernel_bytes)) as hdul:
        psf_kernel = hdul[0].data.astype(float)

    correlation = ztf_dr24_bounded_ingest._psf_shape_correlation(data, x0, y0, psf_kernel)
    assert correlation is not None
    assert correlation > 0.95  # near-perfect match to its own generating shape


def test_psf_shape_correlation_low_for_non_psf_shaped_artifact():
    """A hard single-pixel spike (not smoothly PSF-shaped) must correlate
    much more weakly than a real Gaussian source -- this is the actual
    discrimination this feature exists to provide."""
    import numpy as np
    from astropy.io import fits

    size = 50
    data = np.zeros((size, size), dtype=np.float64)
    data[25, 25] = 500.0  # a single hot pixel, not a smooth PSF-shaped blob

    psf_kernel_bytes = _synthetic_psf_fits_bytes(size=9, sigma=1.5)
    with fits.open(io.BytesIO(psf_kernel_bytes)) as hdul:
        psf_kernel = hdul[0].data.astype(float)

    correlation = ztf_dr24_bounded_ingest._psf_shape_correlation(data, 25, 25, psf_kernel)
    assert correlation is not None
    assert correlation < 0.5  # far from the near-1.0 real-source case above


def test_psf_shape_correlation_returns_none_near_edge():
    """A source too close to the image edge for a full PSF-sized cutout must
    report None rather than fabricate a value from a partial/padded cutout."""
    import numpy as np
    from astropy.io import fits

    data = np.zeros((50, 50), dtype=np.float64)
    psf_kernel_bytes = _synthetic_psf_fits_bytes(size=9)
    with fits.open(io.BytesIO(psf_kernel_bytes)) as hdul:
        psf_kernel = hdul[0].data.astype(float)

    assert ztf_dr24_bounded_ingest._psf_shape_correlation(data, 0, 0, psf_kernel) is None
    assert ztf_dr24_bounded_ingest._psf_shape_correlation(data, 49, 49, psf_kernel) is None


def test_detect_sources_reports_psf_correlation_when_provided():
    """End-to-end within the detector: when a PSF kernel is supplied, every
    reported source gets a psf_correlation field, and psf_applied/
    psf_kernel_shape are recorded for provenance."""
    fits_bytes = _synthetic_difference_image_fits_bytes(source_xy=(25, 25), source_peak=500.0)
    psf_bytes = _synthetic_psf_fits_bytes(size=9)

    result = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(
        fits_bytes, psf_fits_bytes=psf_bytes
    )
    assert result["psf_applied"] is True
    assert result["psf_kernel_shape"] == [9, 9]
    assert len(result["sources"]) >= 1
    assert all("psf_correlation" in s for s in result["sources"])


def test_detect_sources_omits_psf_correlation_when_not_provided():
    """Without a PSF kernel, sources must not carry a psf_correlation key at
    all (not a null placeholder) and psf_applied must read False."""
    fits_bytes = _synthetic_difference_image_fits_bytes(source_xy=(25, 25), source_peak=500.0)
    result = ztf_dr24_bounded_ingest._detect_sources_in_difference_image(fits_bytes)
    assert result["psf_applied"] is False
    assert result["psf_kernel_shape"] is None
    assert all("psf_correlation" not in s for s in result["sources"])


def _available_single_exposure_manifest(
    content_length: int = 1000,
    mask_available: bool | None = None,
    mask_content_length: int = 500,
    psf_available: bool | None = None,
    psf_content_length: int = 300,
) -> dict:
    """One exposure whose difference-image preflight already passed --
    the precondition _run_pixel_extraction_pilot requires. `mask_available`/
    `psf_available` control whether a science_mask/difference_psf entry is
    present at all (None), verified available (True), or
    present-but-unavailable (False)."""
    exposure = {
        "pid": 585152193615,
        "product_urls": {
            "difference_image": "https://irsa.ipac.caltech.edu/product/diff.fits.fz",
        },
        "product_headers": {
            "difference_image": {
                "available": True,
                "content_length_bytes": content_length,
            },
        },
    }
    if mask_available is not None:
        exposure["product_urls"]["science_mask"] = "https://irsa.ipac.caltech.edu/product/mask.fits"
        exposure["product_headers"]["science_mask"] = {
            "available": mask_available,
            "content_length_bytes": mask_content_length,
        }
    if psf_available is not None:
        exposure["product_urls"]["difference_psf"] = "https://irsa.ipac.caltech.edu/product/psf.fits"
        exposure["product_headers"]["difference_psf"] = {
            "available": psf_available,
            "content_length_bytes": psf_content_length,
        }
    return {"exposures": [exposure]}


def test_run_pixel_extraction_pilot_downloads_and_extracts(tmp_path):
    """End-to-end: download the (mocked) difference image and extract
    candidate sources, writing a checkpoint keyed off the real content."""
    fits_bytes = _synthetic_difference_image_fits_bytes()
    manifest = _available_single_exposure_manifest(content_length=len(fits_bytes))
    with patch(
        "requests.get", return_value=_FakeResponse(status=200, content=fits_bytes)
    ) as get:
        result = ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
    assert get.call_count == 1
    assert result["schema_version"] == "ztf-dr24-pixel-extraction-pilot-v3"
    assert result["mask_applied"] is False  # no science_mask entry in this manifest
    assert result["psf_applied"] is False  # no difference_psf entry in this manifest
    assert result["downloaded_bytes"] == len(fits_bytes)
    assert result["downloaded_sha256"] == __import__("hashlib").sha256(fits_bytes).hexdigest()
    assert result["n_candidate_sources"] >= 1
    assert (tmp_path / "difference_image.fits.fz").exists()
    assert (tmp_path / "pixel_extraction_pilot.json").exists()


def test_run_pixel_extraction_pilot_resumes_without_redownload(tmp_path):
    """A repeated call must reuse the checkpoint and never re-fetch the
    (potentially several-MB) product body."""
    fits_bytes = _synthetic_difference_image_fits_bytes()
    manifest = _available_single_exposure_manifest(content_length=len(fits_bytes))
    with patch(
        "requests.get", return_value=_FakeResponse(status=200, content=fits_bytes)
    ) as get:
        first = ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
        assert get.call_count == 1
        second = ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
        assert get.call_count == 1
    assert first == second


def test_run_pixel_extraction_pilot_downloads_mask_when_verified_available(tmp_path):
    """When the same preflight run already verified science_mask available for
    this exposure, the pilot must download and apply it -- not just the
    difference image."""
    fits_bytes = _synthetic_difference_image_fits_bytes()
    mask_bytes = _synthetic_mask_fits_bytes()
    manifest = _available_single_exposure_manifest(
        content_length=len(fits_bytes), mask_available=True, mask_content_length=len(mask_bytes)
    )

    def _get_side_effect(url, *args, **kwargs):
        if "mask" in url:
            return _FakeResponse(status=200, content=mask_bytes)
        return _FakeResponse(status=200, content=fits_bytes)

    with patch("requests.get", side_effect=_get_side_effect) as get:
        result = ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
    assert get.call_count == 2  # difference image + mask
    assert result["mask_applied"] is True
    assert result["mask_path"] is not None
    assert (tmp_path / "science_mask.fits").exists()


def test_run_pixel_extraction_pilot_skips_mask_when_not_verified_available(tmp_path):
    """A science_mask entry present but not verified available (preflight
    failed/missing it) must not be downloaded -- soft requirement, not a
    hard failure of the whole pilot."""
    fits_bytes = _synthetic_difference_image_fits_bytes()
    manifest = _available_single_exposure_manifest(
        content_length=len(fits_bytes), mask_available=False
    )
    with patch(
        "requests.get", return_value=_FakeResponse(status=200, content=fits_bytes)
    ) as get:
        result = ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
    assert get.call_count == 1  # difference image only
    assert result["mask_applied"] is False
    assert result["mask_path"] is None
    assert not (tmp_path / "science_mask.fits").exists()


def test_run_pixel_extraction_pilot_downloads_psf_when_verified_available(tmp_path):
    """When the same preflight run already verified difference_psf available
    for this exposure, the pilot must download and apply it -- not just the
    difference image."""
    fits_bytes = _synthetic_difference_image_fits_bytes()
    psf_bytes = _synthetic_psf_fits_bytes()
    manifest = _available_single_exposure_manifest(
        content_length=len(fits_bytes), psf_available=True, psf_content_length=len(psf_bytes)
    )

    def _get_side_effect(url, *args, **kwargs):
        if "psf" in url:
            return _FakeResponse(status=200, content=psf_bytes)
        return _FakeResponse(status=200, content=fits_bytes)

    with patch("requests.get", side_effect=_get_side_effect) as get:
        result = ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
    assert get.call_count == 2  # difference image + psf
    assert result["psf_applied"] is True
    assert result["psf_path"] is not None
    assert (tmp_path / "difference_psf.fits").exists()


def test_run_pixel_extraction_pilot_skips_psf_when_not_verified_available(tmp_path):
    """A difference_psf entry present but not verified available must not be
    downloaded -- soft requirement, not a hard failure of the whole pilot."""
    fits_bytes = _synthetic_difference_image_fits_bytes()
    manifest = _available_single_exposure_manifest(
        content_length=len(fits_bytes), psf_available=False
    )
    with patch(
        "requests.get", return_value=_FakeResponse(status=200, content=fits_bytes)
    ) as get:
        result = ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
    assert get.call_count == 1  # difference image only
    assert result["psf_applied"] is False
    assert result["psf_path"] is None
    assert not (tmp_path / "difference_psf.fits").exists()


def test_run_pixel_extraction_pilot_rejects_multiple_exposures(tmp_path):
    """The hard single-exposure cap must reject a broader manifest before any
    network call, keeping this a tiny pilot rather than a batch downloader."""
    manifest = _available_single_exposure_manifest()
    manifest["exposures"] = manifest["exposures"] * 2
    with patch("requests.get") as get:
        with pytest.raises(ValueError, match="exactly 1"):
            ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
    get.assert_not_called()


def test_run_pixel_extraction_pilot_requires_verified_availability(tmp_path):
    """An exposure whose preflight never verified (or failed to verify) the
    difference image must not be downloaded."""
    manifest = _available_single_exposure_manifest()
    manifest["exposures"][0]["product_headers"]["difference_image"]["available"] = False
    with patch("requests.get") as get:
        with pytest.raises(RuntimeError, match="requires a passed --preflight-motion-products"):
            ztf_dr24_bounded_ingest._run_pixel_extraction_pilot(manifest, tmp_path)
    get.assert_not_called()


def test_pixel_extraction_pilot_requires_preflight_flag(tmp_path):
    """Requesting the pilot without --preflight-motion-products must fail
    closed before any network call, matching the CLI's documented contract."""
    with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(n_rows=1))) as get:
        with pytest.raises(ValueError, match="requires --preflight-motion-products"):
            ztf_dr24_bounded_ingest.run_bounded_ingest(
                ra=232.6,
                dec=-8.4,
                size_deg=0.01,
                start_jd=2458339.5,
                end_jd=2458340.5,
                out_dir=tmp_path,
                pixel_extraction_pilot=True,
            )
    assert get.call_count == 1  # only the metadata call; no product fetch attempted


def test_run_bounded_ingest_pixel_extraction_pilot_end_to_end(tmp_path):
    """Full CLI-level path: metadata -> manifest -> preflight -> pixel pilot,
    with the metadata GET and all three binary product GETs (difference
    image, the real preflight-verified science_mask, and difference_psf)
    mocked by URL."""
    fits_bytes = _synthetic_difference_image_fits_bytes()
    mask_bytes = _synthetic_mask_fits_bytes()  # all-zero: nothing flagged
    psf_bytes = _synthetic_psf_fits_bytes()
    metadata_response = _FakeResponse(_ipac_response_text(obsjd_values=[2458339.6521991]))
    head_response = _FakeResponse(
        status=200,
        headers={"content-length": str(len(fits_bytes))},
    )

    def _get_side_effect(url, *args, **kwargs):
        if url.startswith(ztf_dr24_bounded_ingest._IRSA_SCI_URL):
            return metadata_response
        if url.endswith("_mskimg.fits"):
            return _FakeResponse(status=200, content=mask_bytes)
        if url.endswith("_diffimgpsf.fits"):
            return _FakeResponse(status=200, content=psf_bytes)
        return _FakeResponse(status=200, content=fits_bytes)

    with (
        patch("requests.get", side_effect=_get_side_effect),
        patch("requests.head", return_value=head_response),
    ):
        report = ztf_dr24_bounded_ingest.run_bounded_ingest(
            ra=232.6,
            dec=-8.4,
            size_deg=0.01,
            start_jd=2458339.5,
            end_jd=2458340.5,
            out_dir=tmp_path,
            preflight_motion_products=True,
            max_preflight_exposures=1,
            preflight_workers=1,
            pixel_extraction_pilot=True,
        )
    pilot = report["pixel_extraction_pilot"]
    assert pilot["n_candidate_sources"] >= 1
    assert pilot["downloaded_bytes"] == len(fits_bytes)
    assert pilot["mask_applied"] is True
    assert pilot["n_masked_pixels"] == 0  # all-zero mask: nothing flagged
    assert pilot["psf_applied"] is True
    assert all("psf_correlation" in s for s in pilot["sources"])


def test_fetch_binary_with_retry_recovers_and_exhausts():
    """Binary product fetch follows the same bounded five-attempt retry
    policy as the metadata and HEAD fetchers."""
    success = _FakeResponse(status=200, content=b"fits-bytes")
    with (
        patch("time.sleep"),
        patch("requests.get", side_effect=[ConnectionError("temporary"), success]) as get,
    ):
        content = ztf_dr24_bounded_ingest._fetch_binary_with_retry(
            "https://example.invalid/diff.fits.fz"
        )
    assert content == b"fits-bytes"
    assert get.call_count == 2

    with (
        patch("time.sleep"),
        patch("requests.get", side_effect=ConnectionError("persistent")) as get,
    ):
        with pytest.raises(RuntimeError, match="failed after 5 attempts"):
            ztf_dr24_bounded_ingest._fetch_binary_with_retry(
                "https://example.invalid/diff.fits.fz"
            )
    assert get.call_count == 5
