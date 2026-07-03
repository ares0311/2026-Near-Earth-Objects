"""Tests for Skills/scan_neo_track_coverage.py (Gate Z3 track-coverage scan).

fetch_horizons and the Gate Z1 IRSA request are both mocked -- this
project's standing convention for external-service tests. Patches target
the shared `fetch`/`requests` module objects (not the dynamically
reloaded sibling Skills modules) because scan_neo_track_coverage.py
re-executes its sibling scripts by path on every call; those re-executed
modules still resolve `import requests` / `from fetch import
fetch_horizons` through the same cached module objects in sys.modules,
so patching there reliably intercepts both.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from unittest.mock import patch

from astropy.io import ascii as ap_ascii
from astropy.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = Path(__file__).resolve().parents[1] / "Skills" / "scan_neo_track_coverage.py"
_spec = importlib.util.spec_from_file_location("scan_neo_track_coverage", _MODULE_PATH)
scan_neo_track_coverage = importlib.util.module_from_spec(_spec)
sys.modules["scan_neo_track_coverage"] = scan_neo_track_coverage
_spec.loader.exec_module(scan_neo_track_coverage)

from schemas import Observation  # noqa: E402


def _fake_ephemeris_observations():
    return [
        Observation(
            obs_id=f"horizons_72966_{2458339.5 + i}",
            ra_deg=232.6 + i * 0.4, dec_deg=-8.4 - i * 0.1,
            jd=2458339.5 + i, mag=19.5, mag_err=0.0,
            filter_band="V", mission="MPC",
        )
        for i in range(10)
    ]


def _ipac_response_text(n_rows: int) -> str:
    table = Table()
    table["ra"] = [10.0] * n_rows
    table["dec"] = [20.0] * n_rows
    table["field"] = [100] * n_rows
    table["ccdid"] = [1] * n_rows
    table["qid"] = [1] * n_rows
    table["rcid"] = [0] * n_rows
    table["fid"] = [1] * n_rows
    table["filtercode"] = ["zg"] * n_rows
    table["obsdate"] = ["2024-01-01 05:00:00"] * n_rows
    table["obsjd"] = [2458339.7] * n_rows
    table["exptime"] = [30.0] * n_rows
    table["seeing"] = [2.1] * n_rows
    table["maglimit"] = [20.5] * n_rows
    table["infobits"] = [0] * n_rows
    buf = io.StringIO()
    ap_ascii.write(table, buf, format="ipac")
    header = f"\\fixlen = T\n\\RowsRetrieved = {n_rows}\n\\QUERY_STATUS = 'OK'\n"
    return header + buf.getvalue()


class _FakeResponse:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        pass


def test_run_scan_reports_a_hit_when_coverage_exists(tmp_path):
    with patch("fetch.fetch_horizons", return_value=_fake_ephemeris_observations()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(3))):
            report = scan_neo_track_coverage.run_scan(
                "72966", 2458339.5, 2458439.5, "1d", stride=5, size_deg=2.0, out_dir=tmp_path
            )
    assert report["n_nights_checked"] == 2  # 10 ephemeris points, stride 5 -> indices 0, 5
    assert report["n_nights_with_coverage"] == 2
    assert all(hit["n_sci_rows"] == 3 for hit in report["hits"])


def test_run_scan_reports_no_hits_when_no_coverage(tmp_path):
    with patch("fetch.fetch_horizons", return_value=_fake_ephemeris_observations()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(0))):
            report = scan_neo_track_coverage.run_scan(
                "72966", 2458339.5, 2458439.5, "1d", stride=5, size_deg=2.0, out_dir=tmp_path
            )
    assert report["n_nights_checked"] == 2
    assert report["n_nights_with_coverage"] == 0
    assert report["hits"] == []


def test_run_scan_rejects_zero_stride():
    parser_args = ["--start-jd", "2458339.5", "--end-jd", "2458439.5", "--stride", "0"]
    with patch.object(sys, "argv", ["scan_neo_track_coverage.py", *parser_args]):
        try:
            scan_neo_track_coverage.main()
            raise AssertionError("expected SystemExit")
        except SystemExit as exc:
            assert "stride" in str(exc)


def test_run_scan_writes_report_file(tmp_path):
    with patch("fetch.fetch_horizons", return_value=_fake_ephemeris_observations()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(0))):
            scan_neo_track_coverage.run_scan(
                "72966", 2458339.5, 2458439.5, "1d", stride=5, size_deg=2.0, out_dir=tmp_path
            )
    assert (tmp_path / "scan_report.json").exists()
