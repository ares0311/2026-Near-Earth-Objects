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
import json
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


@pytest.fixture(autouse=True)
def _isolate_manifest(tmp_path, monkeypatch):
    """Every test must write to an isolated manifest path, never the real
    committed Logs/reports/ztf_alert_archive_ingest_manifest.jsonl -- that
    file is meant to be populated by real operator runs and committed to
    git, not polluted by test runs."""
    monkeypatch.setattr(ingest, "_MANIFEST_PATH", tmp_path / "isolated_manifest.jsonl")


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


class TestManifest:
    """Regression coverage for the git-relay manifest: the operator's
    complaint was that pasting console output from concurrent tabs is
    fragile. Every completed night must append to a committed (not
    gitignored) manifest so results are readable via `git pull` alone."""

    def test_fresh_ingest_appends_manifest_entry(self, tmp_path, monkeypatch):
        records = [(5001, _candidate(ra=257.0809, dec=-10.7456))]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        ingest.ingest_one_night(
            "20220817", tmp_path, min_rb=0.5, ra=257.0809, dec=-10.7456,
            radius_deg=2.0, max_per_night=5000,
        )

        by_night = ingest.read_manifest()
        assert "20220817" in by_night
        assert by_night["20220817"]["kept_count"] == 1
        assert by_night["20220817"]["ra"] == 257.0809
        assert by_night["20220817"]["resumed_from_checkpoint"] is False

    def test_resume_also_appends_manifest_entry(self, tmp_path, monkeypatch):
        records = [(5002, _candidate())]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        ingest.ingest_one_night(
            "20220819", tmp_path, min_rb=0.5, ra=257.5497, dec=-10.9843,
            radius_deg=2.0, max_per_night=5000,
        )
        # Second call resumes from checkpoint (no network) but must still
        # record a manifest entry -- this is exactly the case that matters
        # for a tab that finished, got its manifest entry, and is re-run.
        ingest.ingest_one_night(
            "20220819", tmp_path, min_rb=0.5, ra=257.5497, dec=-10.9843,
            radius_deg=2.0, max_per_night=5000,
        )

        by_night = ingest.read_manifest()
        assert by_night["20220819"]["resumed_from_checkpoint"] is True
        # Re-running must replace, not duplicate, the manifest entry.
        assert len(ingest._MANIFEST_PATH.read_text().splitlines()) == 2

    def test_state_persists_query_params_for_future_sync(self, tmp_path, monkeypatch):
        """The checkpoint itself must store ra/dec/radius/min_rb so a later
        --sync backfill (for checkpoints from a run that predates this
        feature) can report real values instead of unknown/guessed ones
        for any run made after this change."""
        records = [(5003, _candidate())]
        data = _build_fake_tar_gz(records)
        _patch_requests(monkeypatch, data)

        state = ingest.ingest_one_night(
            "20220820", tmp_path, min_rb=0.5, ra=1.0, dec=2.0, radius_deg=3.0, max_per_night=5000
        )
        assert state["ra"] == 1.0
        assert state["dec"] == 2.0
        assert state["radius_deg"] == 3.0
        assert state["min_rb"] == 0.5


class TestSync:
    def test_sync_backfills_from_existing_checkpoints(self, tmp_path, monkeypatch):
        # Simulate a checkpoint written by an older version of this script,
        # before ra/dec/radius/min_rb were persisted into the state dict.
        old_style_state = {
            "night": "20180809",
            "filename": "ztf_public_20180809.tar.gz",
            "scanned_count": 715,
            "kept_count": 21,
            "observations": [],
        }
        (tmp_path / "20180809.json").write_text(json.dumps(old_style_state))
        monkeypatch.setattr(ingest, "commit_and_push_manifest", lambda: True)

        synced = ingest.sync_manifest_from_checkpoints(tmp_path)

        assert synced == 1
        by_night = ingest.read_manifest()
        assert by_night["20180809"]["kept_count"] == 21
        # Fields absent from the old-style checkpoint are reported as
        # unknown (None), never guessed.
        assert by_night["20180809"]["ra"] is None

    def test_sync_reports_zero_for_empty_out_dir(self, tmp_path):
        assert ingest.sync_manifest_from_checkpoints(tmp_path) == 0


class TestCommitAndPushManifest:
    def test_returns_false_when_manifest_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ingest, "_MANIFEST_PATH", tmp_path / "nonexistent.jsonl")
        assert ingest.commit_and_push_manifest() is False

    def test_skips_commit_when_nothing_changed(self, monkeypatch):
        calls = []

        def fake_run_git(args):
            calls.append(args)
            if args[0] == "diff":
                return 0, "", ""  # exit 0 == nothing staged
            return 0, "", ""

        monkeypatch.setattr(ingest, "_run_git", fake_run_git)
        ingest._MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        ingest._MANIFEST_PATH.write_text('{"night": "x"}\n')
        try:
            result = ingest.commit_and_push_manifest()
        finally:
            ingest._MANIFEST_PATH.unlink(missing_ok=True)

        assert result is True
        # Check the git subcommand itself (args[0]), not a substring search
        # across the full joined command -- the isolated tmp_path used by
        # other tests can legitimately contain "commit" as a substring
        # (it's derived from this test's own function name).
        assert all(c[0] != "commit" for c in calls)

    def test_retries_push_after_pull_rebase_on_conflict(self, tmp_path, monkeypatch):
        manifest = tmp_path / "manifest.jsonl"
        manifest.write_text('{"night": "x"}\n')
        monkeypatch.setattr(ingest, "_MANIFEST_PATH", manifest)
        monkeypatch.setattr(ingest, "_BACKOFF_SECONDS", (0, 0, 0, 0, 0))  # no real sleep in tests

        push_attempts = []

        def fake_run_git(args):
            if args[0] == "add":
                return 0, "", ""
            if args[0] == "diff":
                return 1, "", ""  # exit 1 == changes staged
            if args[0] == "commit":
                return 0, "", ""
            if args[0] == "push":
                push_attempts.append(1)
                if len(push_attempts) < 2:
                    return 1, "", "! [rejected] (fetch first)"
                return 0, "", ""
            if args[0] == "pull":
                return 0, "", ""
            raise AssertionError(f"unexpected git command: {args}")

        monkeypatch.setattr(ingest, "_run_git", fake_run_git)
        result = ingest.commit_and_push_manifest()

        assert result is True
        assert len(push_attempts) == 2

    def test_gives_up_after_max_attempts_without_raising(self, tmp_path, monkeypatch):
        manifest = tmp_path / "manifest.jsonl"
        manifest.write_text('{"night": "x"}\n')
        monkeypatch.setattr(ingest, "_MANIFEST_PATH", manifest)
        monkeypatch.setattr(ingest, "_BACKOFF_SECONDS", (0, 0, 0, 0, 0))

        def fake_run_git(args):
            if args[0] == "add":
                return 0, "", ""
            if args[0] == "diff":
                return 1, "", ""
            if args[0] == "commit":
                return 0, "", ""
            if args[0] == "push":
                return 1, "", "! [rejected]"
            if args[0] == "pull":
                return 0, "", ""
            raise AssertionError(f"unexpected git command: {args}")

        monkeypatch.setattr(ingest, "_run_git", fake_run_git)
        result = ingest.commit_and_push_manifest()  # must not raise

        assert result is False
