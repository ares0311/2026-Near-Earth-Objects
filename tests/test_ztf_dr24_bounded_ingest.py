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
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


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
