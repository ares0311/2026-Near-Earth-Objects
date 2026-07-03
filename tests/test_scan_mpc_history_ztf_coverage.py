"""Tests for Skills/scan_mpc_history_ztf_coverage.py (Gate Z3 MPC-history x
ZTF-coverage cross-scan). fetch_mpc_observations and the Gate Z1 IRSA
request are both mocked -- this project's standing convention for
external-service tests. Patches target the shared fetch/requests module
objects (not the dynamically reloaded sibling Skills modules), matching
the pattern already used in test_scan_neo_track_coverage.py."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

from astropy.io import ascii as ap_ascii
from astropy.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "scan_mpc_history_ztf_coverage.py"
)
_spec = importlib.util.spec_from_file_location("scan_mpc_history_ztf_coverage", _MODULE_PATH)
scan_mpc_history_ztf_coverage = importlib.util.module_from_spec(_spec)
sys.modules["scan_mpc_history_ztf_coverage"] = scan_mpc_history_ztf_coverage
_spec.loader.exec_module(scan_mpc_history_ztf_coverage)

from schemas import Observation  # noqa: E402


def _fake_mpc_observations():
    return [
        Observation(
            obs_id=f"mpc_{i}", ra_deg=225.0 + i * 0.4, dec_deg=-5.0 - i * 0.1,
            jd=2458308.5 + i, mag=19.0, mag_err=0.1, filter_band="?", mission="MPC",
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
    table["obsjd"] = [2458308.7] * n_rows
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


def test_run_scan_reports_hits(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(2))):
            report = scan_mpc_history_ztf_coverage.run_scan(
                "72966", 2458273.5, stride=5, size_deg=2.0, out_dir=tmp_path
            )
    assert report["n_reports_checked"] == 2  # 10 rows, stride 5 -> indices 0, 5
    assert report["n_reports_with_ztf_coverage"] == 2
    assert all(hit["n_sci_rows"] == 2 for hit in report["hits"])


def test_run_scan_reports_no_hits_when_no_coverage(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(0))):
            report = scan_mpc_history_ztf_coverage.run_scan(
                "72966", 2458273.5, stride=5, size_deg=2.0, out_dir=tmp_path
            )
    assert report["n_reports_checked"] == 2
    assert report["n_reports_with_ztf_coverage"] == 0
    assert report["hits"] == []


def test_run_scan_rejects_zero_stride():
    parser_args = ["--stride", "0"]
    with patch.object(sys, "argv", ["scan_mpc_history_ztf_coverage.py", *parser_args]):
        try:
            scan_mpc_history_ztf_coverage.main()
            raise AssertionError("expected SystemExit")
        except SystemExit as exc:
            assert "stride" in str(exc)


def test_run_scan_writes_report_file(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(0))):
            scan_mpc_history_ztf_coverage.run_scan(
                "72966", 2458273.5, stride=5, size_deg=2.0, out_dir=tmp_path
            )
    assert (tmp_path / "scan_report.json").exists()


def _fake_mpc_observations_large():
    return [
        Observation(
            obs_id=f"mpc_{i}", ra_deg=225.0 + i * 0.4, dec_deg=-5.0 - i * 0.1,
            jd=2458308.5 + i, mag=19.0, mag_err=0.1, filter_band="?", mission="MPC",
        )
        for i in range(20)
    ]


def test_shards_cover_full_list_with_no_overlap(tmp_path):
    """Running every shard-index 0..shard_count-1 (as separate parallel
    processes would) must together check every row exactly once -- this is
    what makes it safe to run shards concurrently in separate terminal
    tabs without duplicate or missed queries."""
    checked_nights_by_shard = []
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations_large()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(1))):
            for shard_index in range(4):
                report = scan_mpc_history_ztf_coverage.run_scan(
                    "72966", 2458273.5, stride=1, size_deg=2.0, out_dir=tmp_path,
                    shard_index=shard_index, shard_count=4,
                )
                checked_nights_by_shard.append({h["jd"] for h in report["hits"]})

    all_checked = set().union(*checked_nights_by_shard)
    # No two shards checked the same jd (disjoint).
    for a in range(4):
        for b in range(a + 1, 4):
            assert checked_nights_by_shard[a].isdisjoint(checked_nights_by_shard[b])
    # Every real MPC jd in the fake fixture was covered by exactly one shard.
    all_jds = {2458308.5 + i for i in range(20)}
    assert all_checked == all_jds


def test_shard_report_filename_includes_shard_info(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations_large()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(0))):
            scan_mpc_history_ztf_coverage.run_scan(
                "72966", 2458273.5, stride=1, size_deg=2.0, out_dir=tmp_path,
                shard_index=1, shard_count=3,
            )
    assert (tmp_path / "scan_report.shard1of3.json").exists()
    assert not (tmp_path / "scan_report.json").exists()


def test_invalid_shard_args_rejected():
    with patch.object(
        sys, "argv",
        ["scan_mpc_history_ztf_coverage.py", "--shard-index", "5", "--shard-count", "3"],
    ):
        try:
            scan_mpc_history_ztf_coverage.main()
            raise AssertionError("expected SystemExit")
        except SystemExit as exc:
            assert "shard-index" in str(exc)


def test_merge_shards_combines_all_hits(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations_large()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(1))):
            for shard_index in range(4):
                scan_mpc_history_ztf_coverage.run_scan(
                    "72966", 2458273.5, stride=1, size_deg=2.0, out_dir=tmp_path,
                    shard_index=shard_index, shard_count=4,
                )

    merged = scan_mpc_history_ztf_coverage.merge_shards(tmp_path, shard_count=4)
    assert merged["n_reports_checked"] == 20
    assert merged["n_reports_with_ztf_coverage"] == 20  # every fake row was a hit
    assert merged["hits"] == sorted(merged["hits"], key=lambda h: h["jd"])
    assert (tmp_path / "scan_report.merged.json").exists()


def test_merge_shards_fails_closed_when_incomplete(tmp_path):
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations_large()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(0))):
            # Only run 2 of 4 shards -- the other 2 haven't finished yet.
            for shard_index in range(2):
                scan_mpc_history_ztf_coverage.run_scan(
                    "72966", 2458273.5, stride=1, size_deg=2.0, out_dir=tmp_path,
                    shard_index=shard_index, shard_count=4,
                )
    try:
        scan_mpc_history_ztf_coverage.merge_shards(tmp_path, shard_count=4)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "2/4" in str(exc)


def test_run_scan_appends_to_manifest(tmp_path):
    """Each shard completion must append one entry to the shared manifest
    -- this is what lets progress be checked at any time, not just after
    every shard finishes."""
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations_large()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(1))):
            scan_mpc_history_ztf_coverage.run_scan(
                "72966", 2458273.5, stride=1, size_deg=2.0, out_dir=tmp_path,
                shard_index=0, shard_count=4,
            )
    manifest_path = tmp_path / "manifest.jsonl"
    assert manifest_path.exists()
    lines = manifest_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["shard_index"] == 0
    assert entry["shard_count"] == 4


def test_report_status_reflects_partial_progress(tmp_path):
    """Status must be checkable mid-run, before all shards finish, and
    must never raise -- unlike merge_shards()."""
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations_large()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(1))):
            # Only 2 of 4 shards have finished so far.
            for shard_index in range(2):
                scan_mpc_history_ztf_coverage.run_scan(
                    "72966", 2458273.5, stride=1, size_deg=2.0, out_dir=tmp_path,
                    shard_index=shard_index, shard_count=4,
                )

    status = scan_mpc_history_ztf_coverage.report_status(tmp_path, shard_count=4)
    assert status["shards_reported"] == [0, 1]
    assert status["shards_missing"] == [2, 3]
    assert status["n_reports_with_ztf_coverage_so_far"] == 10  # 5 rows/shard * 2 shards, all hits


def test_report_status_before_any_shard_finishes(tmp_path):
    """No manifest exists yet -- must report zero progress, not raise."""
    status = scan_mpc_history_ztf_coverage.report_status(tmp_path, shard_count=4)
    assert status["shards_reported"] == []
    assert status["shards_missing"] == [0, 1, 2, 3]
    assert status["hits_so_far"] == []


def test_manifest_survives_rerun_of_same_shard(tmp_path):
    """Re-running the same shard-index (e.g. after a retry) must replace,
    not duplicate, its manifest entry."""
    with patch("fetch.fetch_mpc_observations", return_value=_fake_mpc_observations_large()):
        with patch("requests.get", return_value=_FakeResponse(_ipac_response_text(1))):
            for _ in range(2):
                scan_mpc_history_ztf_coverage.run_scan(
                    "72966", 2458273.5, stride=1, size_deg=2.0, out_dir=tmp_path,
                    shard_index=0, shard_count=4,
                )
    status = scan_mpc_history_ztf_coverage.report_status(tmp_path, shard_count=4)
    assert status["shards_reported"] == [0]
