"""Tests for the real-run audit packet skill."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "Skills" / "audit_real_run.py"
    spec = importlib.util.spec_from_file_location("audit_real_run", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run_abc"
    run_dir.mkdir()
    checkpoint = {
        "last_stage": "partial",
        "tracklets": [
            {
                "object_id": "T001",
                "arc_days": 2.0,
                "motion_rate_arcsec_per_hour": 1.2,
                "motion_pa_degrees": 92.0,
                "observations": [
                    {
                        "obs_id": "o1",
                        "ra_deg": 10.0,
                        "dec_deg": 5.0,
                        "jd": 2460000.5,
                        "mag": 19.0,
                        "mag_err": 0.1,
                        "filter_band": "g",
                        "mission": "ZTF",
                        "real_bogus": 0.9,
                        "field_id": "ZTF_TEST",
                    },
                    {
                        "obs_id": "o2",
                        "ra_deg": 10.01,
                        "dec_deg": 5.01,
                        "jd": 2460002.5,
                        "mag": 18.5,
                        "mag_err": 0.1,
                        "filter_band": "r",
                        "mission": "ZTF",
                        "real_bogus": 0.8,
                        "field_id": "ZTF_TEST",
                    },
                ],
            }
        ],
        "partial_results": [
            {
                "object_id": "T001",
                "neo_probability": 0.2,
                "hazard_flag": "unknown",
                "alert_pathway": "internal_candidate",
                "moid_au": None,
                "discovery_priority": 0.1,
            }
        ],
    }
    summary = {"run_id": "run_abc", "n_results": 1, "max_candidates": 80}
    (run_dir / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (run_dir / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run_dir


def test_build_audit_packet_blocks_without_expected_manifest(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)

    packet = module.build_audit_packet(run_dir)

    assert packet["n_review_rows"] == 1
    assert packet["review_rows"][0]["object_id"] == "T001"
    assert packet["review_rows"][0]["review_priority"] == "standard"
    assert packet["review_rows"][0]["review_flags"] == []
    assert packet["review_rows"][0]["alerce_object_ids"] == ["ZTF_TEST"]
    assert packet["known_object_recovery_gate"]["status"] == "blocked_no_expected_known_manifest"
    assert packet["known_object_recovery_gate"]["passed"] is False
    assert packet["production_promotion_allowed"] is False
    assert packet["safety"]["no_external_submission"] is True


def test_build_audit_packet_evaluates_expected_manifest(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps([{"object_id": "T001"}]), encoding="utf-8")

    packet = module.build_audit_packet(run_dir, expected)

    gate = packet["known_object_recovery_gate"]
    assert gate["status"] == "evaluated"
    assert gate["recovered"] == 1
    assert gate["expected"] == 1
    assert gate["recovery_rate"] == 1.0
    assert gate["passed"] is True
    assert packet["production_promotion_allowed"] is False
    assert packet["human_false_positive_review"]["status"] == "blocked_no_operator_review"


def test_build_audit_packet_blocks_designation_only_manifest(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps([{"designation": "2024 AA"}]), encoding="utf-8")

    packet = module.build_audit_packet(run_dir, expected)

    gate = packet["known_object_recovery_gate"]
    assert gate["status"] == "blocked_invalid_expected_manifest"
    assert gate["expected"] == 1
    assert gate["invalid"] == 1
    assert gate["recovery_rate"] is None
    assert gate["passed"] is False


def test_build_audit_packet_matches_expected_by_sky_time(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps([
            {
                "designation": "Known-1",
                "ra_deg": 10.0,
                "dec_deg": 5.0,
                "jd": 2460000.5,
                "tolerance_arcsec": 2.0,
                "tolerance_days": 0.001,
            }
        ]),
        encoding="utf-8",
    )

    packet = module.build_audit_packet(run_dir, expected)

    gate = packet["known_object_recovery_gate"]
    match = packet["expected_known_matches"][0]
    assert gate["status"] == "evaluated"
    assert gate["recovered"] == 1
    assert gate["expected"] == 1
    assert gate["passed"] is True
    assert match["status"] == "matched"
    assert match["matched_object_id"] == "T001"
    assert match["matched_by"] == "sky_time"
    assert match["best_separation_arcsec"] == 0.0


def test_build_audit_packet_reports_unmatched_expected_object(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps([
            {
                "designation": "Known-2",
                "ra_deg": 100.0,
                "dec_deg": -20.0,
                "jd": 2460000.5,
                "tolerance_arcsec": 2.0,
                "tolerance_days": 0.001,
            }
        ]),
        encoding="utf-8",
    )

    packet = module.build_audit_packet(run_dir, expected)

    gate = packet["known_object_recovery_gate"]
    match = packet["expected_known_matches"][0]
    assert gate["status"] == "evaluated"
    assert gate["recovered"] == 0
    assert gate["unmatched"] == 1
    assert gate["passed"] is False
    assert match["status"] == "unmatched"


def test_build_audit_packet_fails_closed_on_ambiguous_match(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    checkpoint_path = run_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    duplicate = dict(checkpoint["tracklets"][0])
    duplicate["object_id"] = "T002"
    checkpoint["tracklets"].append(duplicate)
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps([
            {
                "designation": "Known-1",
                "ra_deg": 10.0,
                "dec_deg": 5.0,
                "jd": 2460000.5,
                "tolerance_arcsec": 2.0,
                "tolerance_days": 0.001,
            }
        ]),
        encoding="utf-8",
    )

    packet = module.build_audit_packet(run_dir, expected)

    gate = packet["known_object_recovery_gate"]
    match = packet["expected_known_matches"][0]
    assert gate["status"] == "evaluated_with_ambiguous_matches"
    assert gate["ambiguous"] == 1
    assert gate["passed"] is False
    assert match["status"] == "ambiguous_match"
    assert match["candidate_object_ids"] == ["T001", "T002"]


def test_build_audit_packet_requires_sample_tolerance(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps([
            {
                "designation": "Known-1",
                "ra_deg": 10.0,
                "dec_deg": 5.0,
                "jd": 2460000.5,
                "tolerance_arcsec": 0.001,
                "tolerance_days": 0.001,
            }
        ]),
        encoding="utf-8",
    )

    packet = module.build_audit_packet(run_dir, expected)

    assert packet["expected_known_matches"][0]["status"] == "matched"
    expected.write_text(
        json.dumps([
            {
                "designation": "Known-1",
                "ra_deg": 10.001,
                "dec_deg": 5.001,
                "jd": 2460000.5,
                "tolerance_arcsec": 0.001,
                "tolerance_days": 0.001,
            }
        ]),
        encoding="utf-8",
    )
    packet = module.build_audit_packet(run_dir, expected)
    assert packet["expected_known_matches"][0]["status"] == "unmatched"


def test_build_audit_packet_allows_promotion_after_recovery_and_review(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps([{"object_id": "T001"}]), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps([{"object_id": "T001", "decision": "acceptable"}]),
        encoding="utf-8",
    )

    packet = module.build_audit_packet(run_dir, expected, review)

    assert packet["known_object_recovery_gate"]["passed"] is True
    assert packet["human_false_positive_review"]["gate"]["passed"] is True
    assert packet["production_promotion_allowed"] is True
    assert packet["production_promotion_blockers"] == []


def test_build_audit_packet_blocks_incomplete_operator_review(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps([{"object_id": "T001"}]), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps([]), encoding="utf-8")

    packet = module.build_audit_packet(run_dir, expected, review)

    gate = packet["human_false_positive_review"]["gate"]
    assert gate["status"] == "blocked_no_operator_review"
    assert gate["missing_object_ids"] == ["T001"]
    assert packet["production_promotion_allowed"] is False


def test_build_audit_packet_blocks_operator_findings(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps([{"object_id": "T001"}]), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(
        json.dumps([{"object_id": "T001", "decision": "false_positive"}]),
        encoding="utf-8",
    )

    packet = module.build_audit_packet(run_dir, expected, review)

    gate = packet["human_false_positive_review"]["gate"]
    assert gate["status"] == "blocked_operator_review_findings"
    assert gate["blocking_decisions"] == {"T001": "false_positive"}
    assert packet["production_promotion_allowed"] is False


def test_tracklet_review_flags_suspicious_near_stationary_long_arc(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    checkpoint_path = run_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["tracklets"][0]["arc_days"] = 45.0
    checkpoint["tracklets"][0]["motion_rate_arcsec_per_hour"] = 0.001
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    packet = module.build_audit_packet(run_dir)

    row = packet["review_rows"][0]
    assert row["review_priority"] == "high"
    assert row["review_flags"] == [
        "below_min_solar_system_motion",
        "long_arc_near_stationary",
    ]


def test_write_review_csv(tmp_path):
    module = _load_module()
    run_dir = _write_run_dir(tmp_path)
    packet = module.build_audit_packet(run_dir)
    out = tmp_path / "review.csv"

    module.write_review_csv(packet["review_rows"], out)

    text = out.read_text(encoding="utf-8")
    assert "object_id,review_priority,review_flags,n_observations" in text
    assert "T001" in text
    assert "ZTF_TEST" in text
