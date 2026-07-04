"""Tests for Skills/evaluate_retrospective_validation.py (Gate Z5
retrospective validation).

The real MPC network lookup is always injected via ``mpc_lookup_fn`` in
these tests -- no network call is ever made here. The injected fakes
mirror the real return shape of
Skills/check_mpc_known.py:check_candidates_against_mpc exactly (a list of
dicts, one per queried observation, with an ``mpc_match`` key that is
``None`` on no match).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Skills"))

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "Skills" / "evaluate_retrospective_validation.py"
)
_spec = importlib.util.spec_from_file_location(
    "evaluate_retrospective_validation", _MODULE_PATH
)
evaluate_retrospective_validation = importlib.util.module_from_spec(_spec)
sys.modules["evaluate_retrospective_validation"] = evaluate_retrospective_validation
_spec.loader.exec_module(evaluate_retrospective_validation)


def _make_packet(object_id: str, known_object_score: float | None = None) -> dict:
    return {
        "tracklet": {
            "object_id": object_id,
            "observations": [
                {
                    "obs_id": f"{object_id}_a",
                    "ra_deg": 180.0,
                    "dec_deg": 10.0,
                    "jd": 2460000.5,
                    "mag": 19.5,
                    "mag_err": 0.05,
                    "filter_band": "r",
                    "mission": "ZTF",
                },
                {
                    "obs_id": f"{object_id}_b",
                    "ra_deg": 180.01,
                    "dec_deg": 10.01,
                    "jd": 2460001.5,
                    "mag": 19.6,
                    "mag_err": 0.05,
                    "filter_band": "r",
                    "mission": "ZTF",
                },
            ],
            "arc_days": 1.0,
            "motion_rate_arcsec_per_hour": 1.5,
            "motion_pa_degrees": 45.0,
        },
        "features": {"known_object_score": known_object_score},
    }


def _no_match_lookup(observations, radius_deg):
    return [{"obs_id": o.obs_id, "mpc_match": None} for o in observations]


def _match_lookup(observations, radius_deg):
    return [{"obs_id": o.obs_id, "mpc_match": "2024 AB1"} for o in observations]


class TestClassifyRetrospectiveOutcome:
    def test_matched_and_known_at_replay_is_recovered(self):
        outcome = evaluate_retrospective_validation.classify_retrospective_outcome(
            known_object_score=0.9, mpc_matched=True, verdict="REJECT"
        )
        assert outcome == "recovered_known_object"

    def test_matched_but_not_known_at_replay_is_later_confirmed(self):
        outcome = evaluate_retrospective_validation.classify_retrospective_outcome(
            known_object_score=0.1, mpc_matched=True, verdict="SURVIVE"
        )
        assert outcome == "later_confirmed_object"

    def test_no_match_and_rejected_is_artifact(self):
        outcome = evaluate_retrospective_validation.classify_retrospective_outcome(
            known_object_score=0.0, mpc_matched=False, verdict="REJECT"
        )
        assert outcome == "artifact"

    def test_no_match_and_no_reject_is_unresolved(self):
        outcome = evaluate_retrospective_validation.classify_retrospective_outcome(
            known_object_score=None, mpc_matched=False, verdict="SURVIVE"
        )
        assert outcome == "unresolved_candidate"

    def test_no_match_and_missing_verdict_is_unresolved(self):
        outcome = evaluate_retrospective_validation.classify_retrospective_outcome(
            known_object_score=None, mpc_matched=False, verdict=None
        )
        assert outcome == "unresolved_candidate"


class TestRunRetrospectiveValidation:
    def test_all_four_outcomes_bucketed_correctly(self):
        packets = [
            _make_packet("recovered", known_object_score=0.95),
            _make_packet("later_confirmed", known_object_score=0.05),
            _make_packet("artifact", known_object_score=0.0),
            _make_packet("unresolved", known_object_score=0.0),
        ]
        verdicts = {"artifact": "REJECT", "unresolved": "SURVIVE"}

        def lookup(observations, radius_deg):
            matched_ids = {"recovered", "later_confirmed"}
            return [
                {
                    "obs_id": o.obs_id,
                    "mpc_match": "2024 AB1" if o.obs_id in matched_ids else None,
                }
                for o in observations
            ]

        report = evaluate_retrospective_validation.run_retrospective_validation(
            packets, verdicts_by_object_id=verdicts, mpc_lookup_fn=lookup
        )
        assert report["outcome_counts"] == {
            "recovered_known_object": 1,
            "later_confirmed_object": 1,
            "artifact": 1,
            "unresolved_candidate": 1,
        }
        assert report["n_candidates"] == 4

    def test_no_verdicts_supplied_defaults_to_unresolved(self):
        packets = [_make_packet("obj1", known_object_score=0.0)]
        report = evaluate_retrospective_validation.run_retrospective_validation(
            packets, mpc_lookup_fn=_no_match_lookup
        )
        assert report["outcome_counts"]["unresolved_candidate"] == 1

    def test_matched_with_no_known_score_is_later_confirmed(self):
        packets = [_make_packet("obj1", known_object_score=None)]
        report = evaluate_retrospective_validation.run_retrospective_validation(
            packets, mpc_lookup_fn=_match_lookup
        )
        assert report["outcome_counts"]["later_confirmed_object"] == 1
