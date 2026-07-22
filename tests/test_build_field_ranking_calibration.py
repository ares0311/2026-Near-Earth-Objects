"""Behavioral tests for the Phase 2 discovery-field calibration builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "Skills"))

import build_field_ranking_calibration as calibration  # noqa: E402


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.raise_calls = 0

    def raise_for_status(self) -> None:
        self.raise_calls += 1

    def json(self) -> object:
        return self.payload


def _candidates(year: int, count: int = 3) -> list[dict[str, object]]:
    return [
        {
            "designation": f"{year} A{chr(65 + index)}",
            "discovery_year": year,
            "neo_class": "aten",
            "permanent_id": str(1000 + index),
            "name": None,
        }
        for index in range(count)
    ]


def _observations(year: int, designation: str = "2024 AA") -> list[SimpleNamespace]:
    first_jd = {2023: 2460000.5, 2024: 2460310.5}[year]
    return [
        SimpleNamespace(
            obs_id=f"{designation}-{index}",
            jd=first_jd + offset,
            ra_deg=10.0 + index,
            dec_deg=-5.0,
            station="F51",
            discovery=index == 0,
        )
        for index, offset in enumerate((0.0, 0.02, 1.0))
    ]


def test_current_mpc_list_api_normalizes_and_deduplicates() -> None:
    response = _Response(
        {
            "items": [
                {
                    "unpacked_primary_provisional_designation": "2024 AB",
                    "permid": "123",
                    "name": "Example",
                },
                {
                    "unpacked_primary_provisional_designation": "2024 AA",
                    "permid": None,
                    "name": None,
                },
                {
                    "unpacked_primary_provisional_designation": "2024 AB",
                    "permid": "123",
                    "name": "Example",
                },
            ]
        }
    )
    request: dict[str, object] = {}

    def request_get(url: str, **kwargs: object) -> _Response:
        request.update({"url": url, **kwargs})
        return response

    rows = calibration.fetch_mpc_neo_list(2024, request_get=request_get)

    assert response.raise_calls == 1
    assert request == {
        "url": calibration.MPC_LIST_API,
        "json": {
            "list": "neos",
            "like": "2024%",
            "limit": 50_000,
            "offset": 0,
            "order": "ASC",
        },
        "timeout": 60.0,
    }
    assert [row["designation"] for row in rows] == ["2024 AA", "2024 AB"]
    assert rows[1]["permanent_id"] == "123"
    assert rows[1]["name"] == "Example"
    assert rows[1]["neo_class"] == "neo"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "returned no NEO list items"),
        ({"items": []}, "returned no NEO list items"),
        (
            {"items": [{"unpacked_primary_provisional_designation": "2023 AA"}]},
            "out-of-year designation",
        ),
    ],
)
def test_current_mpc_list_api_fails_on_malformed_or_drifting_data(
    payload: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        calibration.fetch_mpc_neo_list(
            2024, request_get=lambda *_args, **_kwargs: _Response(payload)
        )


def test_year_selection_is_stratified_and_deterministic() -> None:
    universe = {2023: _candidates(2023), 2024: _candidates(2024)}

    first = calibration.select_year_candidates(
        universe, years=(2023, 2024), per_year=2, seed=7
    )
    second = calibration.select_year_candidates(
        universe, years=(2024, 2023), per_year=2, seed=7
    )

    assert first == second
    assert [row["discovery_year"] for row in first] == [2023, 2023, 2024, 2024]
    assert len({row["designation"] for row in first}) == 4

    all_candidates = calibration.select_year_candidates(
        universe, years=(2023, 2024), per_year=None, seed=7
    )
    assert len(all_candidates) == 6


def test_year_selection_fails_when_a_year_is_underfilled_or_drifted() -> None:
    with pytest.raises(ValueError, match="only 1 eligible 2024 objects"):
        calibration.select_year_candidates(
            {2024: _candidates(2024, 1)}, years=(2024,), per_year=2
        )
    drifted = _candidates(2024)
    drifted[0]["discovery_year"] = 2023
    with pytest.raises(ValueError, match="year drift"):
        calibration.select_year_candidates(
            {2024: drifted}, years=(2024,), per_year=1
        )


def test_current_mpc_observations_api_normalizes_ades_and_discovery_marker() -> None:
    response = _Response(
        [
            {
                "ADES_DF": [
                    {
                        "obsTime": "2024-01-01T00:00:00.000Z",
                        "ra": 12.5,
                        "dec": -3.5,
                        "stn": "F51",
                        "disc": "*",
                    },
                    {
                        "obsTime": "2024-01-02T00:00:00.000Z",
                        "ra": 12.6,
                        "dec": -3.4,
                        "stn": "F51",
                    },
                ]
            },
            200,
        ]
    )
    request: dict[str, object] = {}

    def request_get(url: str, **kwargs: object) -> _Response:
        request.update({"url": url, **kwargs})
        return response

    rows = calibration.fetch_mpc_observations_api(
        "2024 AA", request_get=request_get
    )

    assert response.raise_calls == 1
    assert request == {
        "url": calibration.MPC_OBSERVATIONS_API,
        "json": {"desigs": ["2024 AA"], "output_format": ["ADES_DF"]},
        "timeout": 60.0,
    }
    assert len(rows) == 2
    assert rows[0].discovery is True
    assert rows[0].station == "F51"
    assert rows[0].obs_id.startswith("MPC_")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "must start with one object result"),
        ([{"ADES_DF": []}], "returned no ADES observations"),
        ([{"ADES_DF": []}, 500], "invalid trailing status metadata"),
        (
            [
                {
                    "ADES_DF": [
                        {
                            "obsTime": "2024-01-01T00:00:00.000Z",
                            "ra": 12.5,
                            "dec": -3.5,
                            "stn": "F51",
                        }
                    ]
                }
            ],
            "no explicit discovery observation",
        ),
    ],
)
def test_current_mpc_observations_api_fails_on_bad_or_unlabeled_data(
    payload: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        calibration.fetch_mpc_observations_api(
            "2024 AA", request_get=lambda *_args, **_kwargs: _Response(payload)
        )


def test_event_uses_discovery_measurement_and_pre_observation_cutoff() -> None:
    candidate = {
        "designation": "2024 AA",
        "discovery_year": 2024,
        "neo_class": "aten",
        "permanent_id": "123",
    }
    event = calibration._event_from_observations(candidate, _observations(2024))

    assert event["discovery_observation"]["obs_id"] == "2024 AA-0"
    assert event["replay_cutoff_jd"] < event["discovery_observation"]["jd"]
    assert event["published_night_count"] == 2
    assert event["label"] == "later_confirmed_neo_discovery_field"
    assert event["permanent_id"] == "123"


def test_event_rejects_year_drift_single_night_and_missing_marker() -> None:
    candidate = {
        "designation": "2024 AA",
        "discovery_year": 2024,
        "neo_class": "aten",
    }
    with pytest.raises(ValueError, match="MPC discovery year"):
        calibration._event_from_observations(candidate, _observations(2023))

    one_night = _observations(2024)
    for index, observation in enumerate(one_night):
        observation.jd = 2460310.5 + index * 0.01
    with pytest.raises(ValueError, match="fewer than two UTC nights"):
        calibration._event_from_observations(candidate, one_night)

    no_marker = _observations(2024)
    for observation in no_marker:
        observation.discovery = False
    with pytest.raises(ValueError, match="no explicit discovery observation"):
        calibration._event_from_observations(candidate, no_marker)


def test_builder_freezes_universe_checkpoints_and_resumes_without_refetch(
    tmp_path: Path,
) -> None:
    out = tmp_path / "events.json"
    list_calls: list[int] = []
    observation_calls: list[str] = []

    def list_fetcher(year: int) -> list[dict[str, object]]:
        list_calls.append(year)
        return _candidates(year, 4)

    def observation_fetcher(designation: str) -> list[SimpleNamespace]:
        observation_calls.append(designation)
        return _observations(2024, designation)

    result = calibration.build_calibration_events(
        out,
        years=(2024,),
        per_year=1,
        query_delay_seconds=0,
        list_fetcher=list_fetcher,
        observation_fetcher=observation_fetcher,
    )
    resumed = calibration.build_calibration_events(
        out,
        years=(2024,),
        per_year=1,
        resume=True,
        query_delay_seconds=0,
        list_fetcher=list_fetcher,
        observation_fetcher=observation_fetcher,
    )

    assert list_calls == [2024]
    assert len(observation_calls) == 1
    assert result["status"] == resumed["status"] == "complete"
    assert resumed["selection"]["evaluated_count"] == 4
    assert len(resumed["selection"]["candidate_universe_sha256"]) == 64
    assert resumed["summary"] == {
        "accepted_count": 1,
        "complete": True,
        "selected_count": 1,
    }
    assert resumed["leakage_policy"]["future_catalog_identity_allowed_in_features"] is False


def test_builder_fails_loudly_with_resumable_event_checkpoint(tmp_path: Path) -> None:
    out = tmp_path / "events.json"

    def unavailable(_designation: str) -> list[SimpleNamespace]:
        raise ConnectionError("provider unavailable")

    with pytest.raises(RuntimeError, match="checkpoint is resumable"):
        calibration.build_calibration_events(
            out,
            years=(2024,),
            per_year=1,
            retries=1,
            query_delay_seconds=0,
            list_fetcher=lambda year: _candidates(year),
            observation_fetcher=unavailable,
        )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["summary"]["complete"] is False
    assert payload["query_log"][-1] == {
        "attempts": 2,
        "designation": payload["selection"]["selected"][0]["designation"],
        "error": "provider unavailable",
        "error_type": "ConnectionError",
        "status": "failed",
    }


def test_builder_retries_and_fails_loudly_during_universe_acquisition(
    tmp_path: Path,
) -> None:
    attempts = 0

    def unavailable(_year: int) -> list[dict[str, object]]:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("list unavailable")

    with pytest.raises(RuntimeError, match="candidate-universe acquisition failed"):
        calibration.build_calibration_events(
            tmp_path / "events.json",
            years=(2024,),
            per_year=1,
            retries=2,
            query_delay_seconds=0,
            list_fetcher=unavailable,
        )
    assert attempts == 3


def test_resume_rejects_changed_selection_parameters(tmp_path: Path) -> None:
    out = tmp_path / "events.json"
    calibration.build_calibration_events(
        out,
        years=(2024,),
        per_year=1,
        query_delay_seconds=0,
        list_fetcher=lambda year: _candidates(year),
        observation_fetcher=lambda designation: _observations(2024, designation),
    )

    with pytest.raises(ValueError, match="selection parameters changed"):
        calibration.build_calibration_events(
            out,
            years=(2024,),
            per_year=2,
            resume=True,
            query_delay_seconds=0,
            list_fetcher=lambda year: _candidates(year),
            observation_fetcher=lambda designation: _observations(2024, designation),
        )
