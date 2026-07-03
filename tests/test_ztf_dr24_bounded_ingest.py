"""Tests for Skills/ztf_dr24_bounded_ingest.py (Gate Z1 bounded ingest tool).

All network calls are mocked -- this project's standing convention for
external-service tests. The IPAC fixture text is generated with astropy's
own IPAC writer so the parser under test is exercised against a real,
library-round-tripped table, not a hand-typed guess at the format.
"""

from __future__ import annotations

import importlib.util
import io
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


def _ipac_response_text(query_status: str = "OK", n_rows: int = 2) -> str:
    """Build a realistic IPAC table response using astropy's own writer, with
    the header lines the live IRSA response includes (RowsRetrieved,
    QUERY_STATUS) prepended, matching the captured Phase 0 evidence format."""
    table = Table()
    table["ra"] = [10.0 + 0.1 * i for i in range(n_rows)]
    table["dec"] = [20.0 + 0.1 * i for i in range(n_rows)]
    table["field"] = [100 + i for i in range(n_rows)]
    table["ccdid"] = [1] * n_rows
    table["qid"] = [1] * n_rows
    table["rcid"] = [0] * n_rows
    table["fid"] = [1] * n_rows
    table["filtercode"] = ["zg"] * n_rows
    table["obsdate"] = [f"2024-01-{i + 1:02d} 05:00:00" for i in range(n_rows)]
    table["obsjd"] = [2460310.7 + i for i in range(n_rows)]
    table["exptime"] = [30.0] * n_rows
    table["seeing"] = [2.1] * n_rows
    table["maglimit"] = [20.5] * n_rows
    table["infobits"] = [0] * n_rows

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
    assert "WHERE=obsjd>2460310.5+AND+obsjd<2460311.5" in url
    assert "COLUMNS=" in url
