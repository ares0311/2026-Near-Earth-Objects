"""Regression tests for Skills/ztf_alert_archive_ingest.py.

Standing rule: any long-running Skills script must print live progress with
a measurable-quantity ETA. The original implementation placed the progress
print AFTER the real-bogus and sky-box `continue` filters, so it only fired
for records that passed both -- with a narrow sky box (as in the documented
operator command) the overwhelming majority of scanned records never reach
that line, so progress could go silent for the length of a whole night's
archive file (up to 73G). These tests build a synthetic archive where most
records fail the filters and assert progress still fires on every scanned
record.
"""

from __future__ import annotations

import gzip
import io
import sys
import tarfile
from pathlib import Path

import fastavro
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

import ztf_alert_archive_ingest as ingest  # noqa: E402

_SCHEMA = {
    "type": "record",
    "name": "candidate",
    "fields": [
        {"name": "ra", "type": "double"},
        {"name": "dec", "type": "double"},
        {"name": "jd", "type": "double"},
        {"name": "magpsf", "type": "float"},
        {"name": "sigmapsf", "type": "float"},
        {"name": "fid", "type": "int"},
        {"name": "rb", "type": ["null", "float"], "default": None},
        {"name": "field", "type": ["null", "int"], "default": None},
        {"name": "diffmaglim", "type": ["null", "float"], "default": None},
    ],
}

_TOP_SCHEMA = {
    "type": "record",
    "name": "alert",
    "fields": [
        {"name": "candid", "type": "long"},
        {"name": "candidate", "type": _SCHEMA},
    ],
}


def _write_avro_bytes(candid: int, candidate: dict) -> bytes:
    buf = io.BytesIO()
    fastavro.writer(buf, _TOP_SCHEMA, [{"candid": candid, "candidate": candidate}])
    return buf.getvalue()


def _build_fake_tar_gz(records: list[dict]) -> bytes:
    """records: list of (candid, candidate_dict). Each becomes one .avro
    tar member, matching the real archive's one-packet-per-member layout."""
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tf:
        for i, (candid, candidate) in enumerate(records):
            avro_bytes = _write_avro_bytes(candid, candidate)
            info = tarfile.TarInfo(name=f"{candid}.avro")
            info.size = len(avro_bytes)
            tf.addfile(info, io.BytesIO(avro_bytes))
    return gzip.compress(tar_buf.getvalue())


def _candidate(ra=232.6, dec=-8.4, rb=0.9, fid=2, jd=2458339.65):
    return {
        "ra": ra,
        "dec": dec,
        "jd": jd,
        "magpsf": 19.0,
        "sigmapsf": 0.14,
        "fid": fid,
        "rb": rb,
        "field": 377,
        "diffmaglim": 19.6,
    }


class _FakeHeadResp:
    def __init__(self, size: int):
        self.headers = {"Content-Length": str(size)}

    def raise_for_status(self):
        pass


class _FakeStreamResp:
    def __init__(self, data: bytes):
        self.raw = io.BytesIO(data)

    def raise_for_status(self):
        pass

    def close(self):
        pass


def _patch_requests(monkeypatch, data: bytes):
    def fake_head(url, timeout=30, allow_redirects=True):
        return _FakeHeadResp(len(data))

    monkeypatch.setattr(ingest.requests, "head", fake_head)
    monkeypatch.setattr(
        ingest.requests, "get", lambda url, timeout=60, stream=True: _FakeStreamResp(data)
    )


class TestProgressFiresRegardlessOfFilter:
    """Regression test for the exact bug: progress must fire on every
    scanned record, not only on records that pass the rb/sky-box filters."""

    def test_progress_prints_when_all_records_fail_sky_box(self, tmp_path, monkeypatch, capsys):
        # All records are far from the requested sky box and will all be
        # rejected by the sky-box filter -- with the bug, zero progress
        # lines would ever print even though _PROGRESS_EVERY records were
        # scanned.
        monkeypatch.setattr(ingest, "_PROGRESS_EVERY", 3)
        records = [(1000 + i, _candidate(ra=10.0, dec=10.0, rb=0.9)) for i in range(7)]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        state = ingest.ingest_one_night(
            "20180809", tmp_path, min_rb=0.5, ra=232.6, dec=-8.4, radius_deg=2.0, max_per_night=5000
        )
        captured = capsys.readouterr()

        assert state["kept_count"] == 0
        assert state["scanned_count"] == 7
        assert "scanned=3" in captured.out
        assert "scanned=6" in captured.out
        assert "ETA" in captured.out

    def test_progress_prints_when_all_records_fail_rb(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(ingest, "_PROGRESS_EVERY", 3)
        records = [(2000 + i, _candidate(rb=0.1)) for i in range(7)]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        state = ingest.ingest_one_night(
            "20180810", tmp_path, min_rb=0.5, ra=None, dec=None, radius_deg=None, max_per_night=5000
        )
        captured = capsys.readouterr()

        assert state["kept_count"] == 0
        assert state["scanned_count"] == 7
        assert "scanned=3" in captured.out
        assert "scanned=6" in captured.out


class TestFilteringAndMapping:
    def test_keeps_matching_records_only(self, tmp_path, monkeypatch):
        records = [
            (3001, _candidate(ra=232.6, dec=-8.4, rb=0.9)),  # near, high rb -> kept
            (3002, _candidate(ra=10.0, dec=10.0, rb=0.9)),  # far -> dropped
            (3003, _candidate(ra=232.6, dec=-8.4, rb=0.1)),  # near, low rb -> dropped
        ]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        state = ingest.ingest_one_night(
            "20180811", tmp_path, min_rb=0.5, ra=232.6, dec=-8.4, radius_deg=2.0, max_per_night=5000
        )

        assert state["scanned_count"] == 3
        assert state["kept_count"] == 1
        assert state["observations"][0]["obs_id"] == "3001"
        assert state["observations"][0]["mission"] == "ZTF"
        assert state["observations"][0]["filter_band"] == "R"
        assert state["observations"][0]["real_bogus"] == pytest.approx(0.9, abs=1e-3)

    def test_real_confirmed_field_values_map_correctly(self, tmp_path, monkeypatch):
        real_candidate = _candidate(
            ra=232.6075742, dec=-8.4449086, jd=2458339.6521991, rb=0.7766666412353516, fid=2
        )
        records = [(585152193615015014, real_candidate)]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        state = ingest.ingest_one_night(
            "20180812", tmp_path, min_rb=0.5, ra=None, dec=None, radius_deg=None, max_per_night=5000
        )

        obs = state["observations"][0]
        assert obs["ra_deg"] == pytest.approx(232.6075742)
        assert obs["dec_deg"] == pytest.approx(-8.4449086)
        assert obs["obs_id"] == "585152193615015014"


class TestCheckpointResume:
    def test_second_call_uses_checkpoint(self, tmp_path, monkeypatch, capsys):
        records = [(4001, _candidate())]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        ingest.ingest_one_night(
            "20180813", tmp_path, min_rb=0.5, ra=None, dec=None, radius_deg=None, max_per_night=5000
        )
        capsys.readouterr()

        # Break the fake network so a re-download would fail loudly.
        def fail_head(*a, **k):
            raise RuntimeError("no network")

        monkeypatch.setattr(ingest.requests, "head", fail_head)
        state = ingest.ingest_one_night(
            "20180813", tmp_path, min_rb=0.5, ra=None, dec=None, radius_deg=None, max_per_night=5000
        )
        captured = capsys.readouterr()

        assert "[resume]" in captured.out
        assert state["kept_count"] == 1
