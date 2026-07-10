"""Regression tests for Skills/download_ztf_training_alerts.py.

Covers the A1/A4 provenance fix: parse_avro_alert() and download_night()
must capture real per-alert objectId/candid/jd/ra/dec/fid/field and the
real archive-night string, so a future training run can build a genuine
grouped-split leakage report -- the original 10,000-alert sample committed
to this project could not, because none of this was ever persisted (see
data_selection/dataset_manifests/ztf_labeled_alerts_tier2_cnn_v1.json's
known_caveats). Field names are verified against a real downloaded packet
per docs/evidence/phase0/2026-07-02-gate-z3-uw-alert-archive-candidate.md,
not guessed.
"""

from __future__ import annotations

import gzip
import io
import sys
from pathlib import Path

import fastavro
import numpy as np
import pytest
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Skills"))

import download_ztf_training_alerts as dl  # noqa: E402

_CANDIDATE_SCHEMA = {
    "type": "record",
    "name": "candidate",
    "fields": [
        {"name": "candid", "type": "long"},
        {"name": "jd", "type": "double"},
        {"name": "ra", "type": "double"},
        {"name": "dec", "type": "double"},
        {"name": "fid", "type": "int"},
        {"name": "field", "type": ["null", "int"], "default": None},
        {"name": "rb", "type": "float"},
        {"name": "drb", "type": ["null", "float"], "default": None},
    ],
}

def _stamp_schema(name: str) -> dict:
    return {
        "type": "record",
        "name": name,
        "fields": [{"name": "stampData", "type": "bytes"}],
    }


_TOP_SCHEMA = {
    "type": "record",
    "name": "alert",
    "fields": [
        {"name": "candid", "type": "long"},
        {"name": "objectId", "type": "string"},
        {"name": "candidate", "type": _CANDIDATE_SCHEMA},
        {"name": "cutoutScience", "type": _stamp_schema("cutoutScience")},
        {"name": "cutoutTemplate", "type": _stamp_schema("cutoutTemplate")},
        {"name": "cutoutDifference", "type": _stamp_schema("cutoutDifference")},
    ],
}


def _fake_stamp() -> bytes:
    """Build a real minimal 63x63 gzip-compressed FITS stamp, matching what
    _decompress_ztf_stamp expects to decode."""
    hdu = fits.PrimaryHDU(data=np.zeros((63, 63), dtype=np.float32))
    buf = io.BytesIO()
    hdu.writeto(buf)
    return gzip.compress(buf.getvalue())


def _write_alert(
    *,
    candid=123456789,
    object_id="ZTF20aabbccd",
    jd=2459123.75,
    ra=232.6,
    dec=-8.4,
    fid=2,
    field=377,
    rb=0.9,
    drb=0.95,
) -> bytes:
    stamp = _fake_stamp()
    record = {
        "candid": candid,
        "objectId": object_id,
        "candidate": {
            "candid": candid,
            "jd": jd,
            "ra": ra,
            "dec": dec,
            "fid": fid,
            "field": field,
            "rb": rb,
            "drb": drb,
        },
        "cutoutScience": {"stampData": stamp},
        "cutoutTemplate": {"stampData": stamp},
        "cutoutDifference": {"stampData": stamp},
    }
    buf = io.BytesIO()
    fastavro.writer(buf, _TOP_SCHEMA, [record])
    return buf.getvalue()


def test_parse_avro_alert_captures_real_provenance_fields():
    alert_bytes = _write_alert(
        candid=42, object_id="ZTF20aabbccd", jd=2459123.75, ra=232.6, dec=-8.4, fid=2, field=377
    )
    result = dl.parse_avro_alert(alert_bytes, archive_night="20200601")

    assert result is not None
    assert result["label"] == 0  # rb=0.9 >= REAL_THRESHOLD
    assert result["object_id"] == "ZTF20aabbccd"
    assert result["candid"] == 42
    assert result["jd"] == pytest.approx(2459123.75)
    assert result["ra"] == pytest.approx(232.6)
    assert result["dec"] == pytest.approx(-8.4)
    assert result["fid"] == 2
    assert result["field"] == 377
    assert result["archive_night"] == "20200601"
    assert len(result["observations"]) == 1


def test_parse_avro_alert_bogus_label():
    alert_bytes = _write_alert(rb=0.1, drb=0.05)
    result = dl.parse_avro_alert(alert_bytes, archive_night="20200601")
    assert result is not None
    assert result["label"] == 3


def test_parse_avro_alert_ambiguous_zone_excluded():
    alert_bytes = _write_alert(rb=0.5)
    result = dl.parse_avro_alert(alert_bytes, archive_night="20200601")
    assert result is None


def test_parse_avro_alert_defaults_archive_night_to_none():
    alert_bytes = _write_alert()
    result = dl.parse_avro_alert(alert_bytes)
    assert result is not None
    assert result["archive_night"] is None


def test_parse_avro_alert_malformed_bytes_returns_none():
    assert dl.parse_avro_alert(b"not a valid avro packet") is None


def _build_fake_tar_gz(alert_bytes_list: list[bytes]) -> bytes:
    import tarfile

    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tf:
        for i, alert_bytes in enumerate(alert_bytes_list):
            info = tarfile.TarInfo(name=f"{i}.avro")
            info.size = len(alert_bytes)
            tf.addfile(info, io.BytesIO(alert_bytes))
    return gzip.compress(tar_buf.getvalue())


def test_download_night_stamps_archive_night_onto_every_result(monkeypatch):
    tar_bytes = _build_fake_tar_gz(
        [
            _write_alert(candid=1, object_id="ZTF20aaa", rb=0.9),
            _write_alert(candid=2, object_id="ZTF20bbb", rb=0.1, drb=0.05),
        ]
    )

    class _FakeHeadResponse:
        status_code = 200
        headers = {"Content-Length": str(len(tar_bytes))}

        def raise_for_status(self) -> None:
            return None

    class _FakeGetResponse:
        status_code = 200
        raw = io.BytesIO(tar_bytes)

        def raise_for_status(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(dl.requests, "head", lambda *a, **k: _FakeHeadResponse())
    monkeypatch.setattr(dl.requests, "get", lambda *a, **k: _FakeGetResponse())

    results: list[dict] = []
    n_added = dl.download_night(
        "https://example.invalid/ztf_public_20200601.tar.gz",
        limit=10,
        results=results,
        archive_night="20200601",
    )

    assert n_added == 2
    assert {r["archive_night"] for r in results} == {"20200601"}
    assert {r["object_id"] for r in results} == {"ZTF20aaa", "ZTF20bbb"}


def test_download_night_prints_progress_with_flush(monkeypatch, capsys):
    """Standing-rule regression: every print in the download path must be
    flush=True and must fire even when the ambiguous zone/no-op filters
    inside parse_avro_alert() would otherwise reject a record -- console
    silence during a multi-hundred-MB download is indistinguishable from a
    hung process (see the real operator report this fix responds to)."""
    alerts = [_write_alert(candid=i, object_id=f"ZTF{i}", rb=0.9) for i in range(3)]
    tar_bytes = _build_fake_tar_gz(alerts)

    class _FakeHeadResponse:
        status_code = 200
        headers = {"Content-Length": str(len(tar_bytes))}

        def raise_for_status(self) -> None:
            return None

    class _FakeGetResponse:
        status_code = 200
        raw = io.BytesIO(tar_bytes)

        def raise_for_status(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(dl.requests, "head", lambda *a, **k: _FakeHeadResponse())
    monkeypatch.setattr(dl.requests, "get", lambda *a, **k: _FakeGetResponse())
    monkeypatch.setattr(dl, "_PROGRESS_EVERY", 1)  # force a progress line per member

    results: list[dict] = []
    dl.download_night(
        "https://example.invalid/ztf_public_20200601.tar.gz",
        limit=10,
        results=results,
        archive_night="20200601",
    )

    out = capsys.readouterr().out
    assert "Remote size:" in out
    assert "scanned=" in out
    assert "ETA" in out
    assert "Done: scanned=3 kept=3" in out
