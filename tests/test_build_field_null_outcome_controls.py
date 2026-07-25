from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "Skills")

import adversarial_review  # noqa: E402
import build_field_null_outcome_controls as controls  # noqa: E402
import hunter_cli  # noqa: E402


def _field(stratum: str = "top", ra_deg: float = 10.0, dec_deg: float = 5.0, rank: int = 1) -> dict:
    return {
        "stratum": stratum,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "rank": rank,
        "score": 0.75,
        "mode": "aten",
        "ranking_jd": 2461246.5,
    }


def test_outcome_id_is_stable_and_stratum_specific() -> None:
    a = controls._outcome_id("top", 217.41, -15.0)
    b = controls._outcome_id("middle", 217.41, -15.0)
    assert a != b
    assert a == controls._outcome_id("top", 217.41, -15.0)
    assert "top" in a and "middle" in b


def test_load_predeclared_fields_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "fields.json"
    path.write_text(json.dumps({"fields": [_field()]}), encoding="utf-8")
    loaded = controls.load_predeclared_fields(path)
    assert loaded == [_field()]


def test_load_predeclared_fields_rejects_missing_keys(tmp_path: Path) -> None:
    path = tmp_path / "fields.json"
    path.write_text(json.dumps({"fields": [{"ra_deg": 1.0}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required keys"):
        controls.load_predeclared_fields(path)


def test_load_predeclared_fields_rejects_empty(tmp_path: Path) -> None:
    path = tmp_path / "fields.json"
    path.write_text(json.dumps({"fields": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty list"):
        controls.load_predeclared_fields(path)


def test_ensure_coverage_committed_skips_live_check_when_already_covered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = hunter_cli.field_selector._coordinate_key(10.0, 5.0)
    monkeypatch.setattr(hunter_cli, "_combined_known_coverage", lambda: {key: {}})
    calls = []
    monkeypatch.setattr(hunter_cli, "_live_coverage_check", lambda *a, **k: calls.append(a))

    controls._ensure_coverage_committed(10.0, 5.0)

    assert calls == []


def test_ensure_coverage_committed_runs_live_check_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hunter_cli, "_combined_known_coverage", lambda: {})
    calls = []
    monkeypatch.setattr(
        hunter_cli, "_live_coverage_check", lambda fields, prefix: calls.append((fields, prefix))
    )

    controls._ensure_coverage_committed(10.0, 5.0)

    expected_field_id = hunter_cli._field_id_from_radec("null_ctrl", 10.0, 5.0)
    assert "." not in expected_field_id
    assert calls == [([(expected_field_id, 10.0, 5.0)], "null_control_coverage")]


def test_build_control_record_null_result_when_zero_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(controls, "_ensure_coverage_committed", lambda *a, **k: None)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [],
        },
    )

    record = controls.build_control_record(_field(), tmp_path)

    assert record["outcome"] == "null_result"
    assert record["production_tracklet_count"] == 0
    assert record["surviving_review_count"] == 0
    assert record["selection_stratum"] == "top"
    assert record["observation_nights_yyyymmdd"] == ["20240101", "20240102", "20240103"]


def test_build_control_record_null_result_when_tracklets_but_zero_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matches this dataset's own outcome_definition: >=1 tracklet linked but
    zero surviving adversarial review still counts as a null_result."""
    verdict = adversarial_review.ReviewVerdict(
        object_id="T1", verdict="REJECT", challenges=(), fail_count=1, warning_count=0,
        summary="test", reviewed_at_utc="2024-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(controls, "_ensure_coverage_committed", lambda *a, **k: None)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "success",
            "candidate_ids": ["T1", "T2"],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [{"packet": {}, "verdict": verdict}],
        },
    )

    record = controls.build_control_record(_field(), tmp_path)

    assert record["outcome"] == "null_result"
    assert record["production_tracklet_count"] == 2
    assert record["surviving_review_count"] == 0


def test_build_control_record_survivor_found_when_something_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verdict = adversarial_review.ReviewVerdict(
        object_id="T1", verdict="SURVIVE", challenges=(), fail_count=0, warning_count=0,
        summary="test", reviewed_at_utc="2024-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(controls, "_ensure_coverage_committed", lambda *a, **k: None)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "success",
            "candidate_ids": ["T1"],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [{"packet": {}, "verdict": verdict}],
        },
    )

    record = controls.build_control_record(_field(), tmp_path)

    assert record["outcome"] == "survivor_found"
    assert record["surviving_review_count"] == 1


def test_build_controls_checkpoints_and_resumes_without_reexecuting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "controls.json"
    calls: list[str] = []

    def _fake_execute_target(target, *a, **k):
        calls.append(target["target_id"])
        return {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [],
        }

    monkeypatch.setattr(controls, "_ensure_coverage_committed", lambda *a, **k: None)
    monkeypatch.setattr(hunter_cli, "execute_target", _fake_execute_target)
    fields = [_field("top", 10.0, 5.0, 1), _field("middle", 20.0, 5.0, 200)]

    first = controls.build_controls(fields, out, tmp_path / "checkpoints")
    assert len(first["entries"]) == 2
    assert calls == [
        hunter_cli.hunter_state.target_id_from_radec(10.0, 5.0),
        hunter_cli.hunter_state.target_id_from_radec(20.0, 5.0),
    ]

    calls.clear()
    resumed = controls.build_controls(fields, out, tmp_path / "checkpoints")
    assert calls == []  # both already checkpointed
    assert len(resumed["entries"]) == 2


def test_build_controls_records_failure_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "controls.json"

    def _fake_execute_target(target, *a, **k):
        if target["ra_deg"] == 10.0:
            raise RuntimeError("simulated acquisition failure")
        return {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [],
        }

    monkeypatch.setattr(controls, "_ensure_coverage_committed", lambda *a, **k: None)
    monkeypatch.setattr(hunter_cli, "execute_target", _fake_execute_target)
    fields = [_field("top", 10.0, 5.0, 1), _field("middle", 20.0, 5.0, 200)]

    result = controls.build_controls(fields, out, tmp_path / "checkpoints")

    assert len(result["entries"]) == 1
    assert len(result["failures"]) == 1
    assert result["failures"][0]["error"] == "simulated acquisition failure"


def test_build_controls_drops_stale_failure_when_field_later_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A field that fails on one resumed attempt and succeeds on the next
    must not keep a stale failure entry alongside its real result."""
    out = tmp_path / "controls.json"
    attempt = {"count": 0}

    def _flaky_execute_target(target, *a, **k):
        attempt["count"] += 1
        if attempt["count"] == 1:
            raise RuntimeError("transient failure on first attempt")
        return {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [],
        }

    monkeypatch.setattr(controls, "_ensure_coverage_committed", lambda *a, **k: None)
    monkeypatch.setattr(hunter_cli, "execute_target", _flaky_execute_target)
    fields = [_field("top", 10.0, 5.0, 1)]

    first = controls.build_controls(fields, out, tmp_path / "checkpoints")
    assert len(first["entries"]) == 0
    assert len(first["failures"]) == 1

    second = controls.build_controls(fields, out, tmp_path / "checkpoints")
    assert len(second["entries"]) == 1
    assert second["failures"] == []


def test_main_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fields_path = tmp_path / "fields.json"
    fields_path.write_text(json.dumps({"fields": [_field()]}), encoding="utf-8")
    out_path = tmp_path / "controls.json"
    monkeypatch.setattr(controls, "_ensure_coverage_committed", lambda *a, **k: None)
    monkeypatch.setattr(
        hunter_cli,
        "execute_target",
        lambda *a, **k: {
            "execution_status": "null_result",
            "candidate_ids": [],
            "nights_acquired": ["20240101", "20240102", "20240103"],
            "scored_candidates": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_field_null_outcome_controls.py",
            "--fields-json",
            str(fields_path),
            "--out",
            str(out_path),
            "--checkpoint-root",
            str(tmp_path / "checkpoints"),
        ],
    )

    exit_code = controls.main()

    assert exit_code == 0
    assert "complete: 1/1 recorded" in capsys.readouterr().out
    assert json.loads(out_path.read_text())["entries"][0]["outcome"] == "null_result"
