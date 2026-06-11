"""Offline tests for bounded MPC sequence acquisition and its safety contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_skill() -> Any:
    """Load the operational Skill directly so tests cover its CLI implementation."""
    skill_path = Path(__file__).resolve().parents[1] / "Skills" / "query_mpc_observations.py"
    spec = importlib.util.spec_from_file_location("sequence_acquisition_skill", skill_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(path: Path, rows: list[tuple[str, str]]) -> None:
    """Write the smallest valid label manifest needed by collector tests."""
    lines = ["designation,neo_class,h_mag,source"]
    lines.extend(f"{designation},{class_name},20.0,test" for designation, class_name in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_window_manifest(path: Path, window: str) -> None:
    """Write one policy-aware manifest row for temporal-window tests."""
    path.write_text(
        "designation,neo_class,h_mag,source,sequence_window,label_basis\n"
        f"433,neo_candidate,20.0,test,{window},test policy\n",
        encoding="utf-8",
    )


def _observations(prefix: str = "obj") -> list[SimpleNamespace]:
    """Create a multi-night observation sequence that satisfies acceptance gates."""
    return [
        SimpleNamespace(
            obs_id=f"{prefix}-{index}",
            ra_deg=10.0 + index,
            dec_deg=5.0,
            jd=2460000.4 + index,
            mag=20.0,
            mag_err=0.1,
            filter_band="V",
            mission="MPC",
        )
        for index in range(3)
    ]


def test_balanced_selection_round_robins_classes(tmp_path: Path) -> None:
    """Bounded collection should not exhaust one class before sampling another."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    _write_manifest(
        manifest,
        [
            ("neo-1", "neo_candidate"),
            ("neo-2", "neo_candidate"),
            ("mba-1", "main_belt_asteroid"),
            ("mba-2", "main_belt_asteroid"),
        ],
    )

    selected = module._balanced_selection(module._load_manifest_rows(manifest), 4)

    assert [row["designation"] for row in selected] == [
        "neo-1",
        "mba-1",
        "neo-2",
        "mba-2",
    ]


def test_collection_records_provenance_and_safety(tmp_path: Path) -> None:
    """Accepted data must include reproducible provenance and fail-safe flags."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, [("433", "neo_candidate")])

    dataset = module.collect_sequence_dataset(
        manifest,
        output,
        1,
        query_delay_seconds=0,
        fetcher=lambda designation, force_refresh=False: _observations(designation),
    )

    assert dataset["schema_version"] == module.SCHEMA_VERSION
    assert dataset["summary"]["accepted_objects"] == 1
    assert dataset["entries"][0]["label"] == 0
    assert dataset["entries"][0]["night_count"] == 3
    assert dataset["safety"] == {
        "external_submission_enabled": False,
        "impact_probability_generated": False,
        "secret_values_recorded": False,
    }
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["source"]["label_manifest_sha256"]
    assert "token" not in output.read_text(encoding="utf-8").lower()
    assert "password" not in output.read_text(encoding="utf-8").lower()


def test_collection_retries_and_rejects_short_sequences(tmp_path: Path) -> None:
    """Empty retries and inadequate arcs must be logged without entering training data."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, [("short", "main_belt_asteroid")])
    refresh_flags: list[bool] = []

    def fetcher(designation: str, force_refresh: bool = False) -> list[SimpleNamespace]:
        """Return no first result, then a same-night sequence that must be rejected."""
        refresh_flags.append(force_refresh)
        if not force_refresh:
            return []
        observations = _observations(designation)
        for index, observation in enumerate(observations):
            observation.jd = 2460000.1 + index * 0.01
        return observations

    dataset = module.collect_sequence_dataset(
        manifest,
        output,
        1,
        retries=1,
        query_delay_seconds=0,
        fetcher=fetcher,
    )

    assert refresh_flags == [False, True]
    assert dataset["entries"] == []
    assert dataset["query_log"][0]["status"] == "insufficient_nights"
    assert dataset["query_log"][0]["attempts"] == 2


def test_collection_applies_temporal_window_and_cap(tmp_path: Path) -> None:
    """Early policy rows should retain multiple nights without exceeding the cap."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_window_manifest(manifest, "early")
    observations = _observations("dense")
    observations.extend(
        SimpleNamespace(
            obs_id=f"dense-extra-{index}",
            ra_deg=20.0,
            dec_deg=5.0,
            jd=2460000.41 + index * 0.001,
            mag=20.0,
            mag_err=0.1,
            filter_band="V",
            mission="MPC",
        )
        for index in range(10)
    )

    dataset = module.collect_sequence_dataset(
        manifest,
        output,
        1,
        max_observations_per_object=4,
        query_delay_seconds=0,
        fetcher=lambda designation, force_refresh=False: observations,
    )

    entry = dataset["entries"][0]
    assert entry["sequence_window"] == "early"
    assert entry["label_basis"] == "test policy"
    assert entry["observation_count"] == 4
    assert entry["night_count"] >= 2
    assert dataset["query_log"][0]["raw_observation_count"] == 13


def test_resume_skips_already_accepted_designations(tmp_path: Path) -> None:
    """Resume mode must preserve checkpoints and avoid duplicate provider queries."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, [("433", "neo_candidate")])
    calls: list[str] = []

    def fetcher(designation: str, force_refresh: bool = False) -> list[SimpleNamespace]:
        """Record provider calls so the second run can prove it performed none."""
        calls.append(designation)
        return _observations(designation)

    module.collect_sequence_dataset(
        manifest,
        output,
        1,
        query_delay_seconds=0,
        fetcher=fetcher,
    )
    resumed = module.collect_sequence_dataset(
        manifest,
        output,
        1,
        query_delay_seconds=0,
        resume=True,
        fetcher=fetcher,
    )

    assert calls == ["433"]
    assert len(resumed["entries"]) == 1
    assert len(resumed["query_log"]) == 1


def test_resume_rejects_changed_manifest(tmp_path: Path) -> None:
    """A changed label manifest must fail closed instead of mixing dataset versions."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, [("433", "neo_candidate")])
    module.collect_sequence_dataset(
        manifest,
        output,
        1,
        query_delay_seconds=0,
        fetcher=lambda designation, force_refresh=False: _observations(designation),
    )
    _write_manifest(manifest, [("434", "neo_candidate")])

    with pytest.raises(ValueError, match="different label manifest"):
        module.collect_sequence_dataset(
            manifest,
            output,
            1,
            query_delay_seconds=0,
            resume=True,
        )


def test_manifest_rejects_duplicate_designations(tmp_path: Path) -> None:
    """Duplicate labels must fail instead of silently shrinking a balanced pilot."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    _write_manifest(
        manifest,
        [
            ("duplicate", "neo_candidate"),
            ("duplicate", "other_solar_system"),
        ],
    )

    with pytest.raises(ValueError, match="duplicate designation"):
        module._load_manifest_rows(manifest)


def test_provider_errors_are_checkpointed_and_trip_circuit_breaker(
    tmp_path: Path,
) -> None:
    """Repeated MPC failures should stop quickly with auditable query-error records."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(
        manifest,
        [
            ("neo-1", "neo_candidate"),
            ("known-1", "known_object"),
            ("mba-1", "main_belt_asteroid"),
        ],
    )

    def failing_fetcher(
        designation: str,
        force_refresh: bool = False,
    ) -> list[SimpleNamespace]:
        """Simulate an unavailable provider without exposing request details."""
        raise ConnectionError(f"provider unavailable for {designation}")

    with pytest.raises(RuntimeError, match="2 consecutive provider errors"):
        module.collect_sequence_dataset(
            manifest,
            output,
            3,
            retries=0,
            query_delay_seconds=0,
            max_consecutive_query_errors=2,
            fetcher=failing_fetcher,
        )

    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    assert checkpoint["schema_version"] == "mpc-tracklet-sequences-v3"
    assert [item["status"] for item in checkpoint["query_log"]] == [
        "query_error",
        "query_error",
    ]
    assert {item["error_type"] for item in checkpoint["query_log"]} == {
        "ConnectionError"
    }
    assert checkpoint["safety"]["secret_values_recorded"] is False


def test_target_per_class_uses_reserve_pool_and_stops_at_target(tmp_path: Path) -> None:
    """Rejected candidates should be replaced from the same class reserve pool."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(
        manifest,
        [
            ("neo-short", "neo_candidate"),
            ("known-short", "known_object"),
            ("neo-good", "neo_candidate"),
            ("known-good", "known_object"),
            ("neo-unused", "neo_candidate"),
            ("known-unused", "known_object"),
        ],
    )
    calls: list[str] = []

    def fetcher(designation: str, force_refresh: bool = False) -> list[SimpleNamespace]:
        """Return empty histories for reserves ending in short."""
        calls.append(designation)
        return [] if designation.endswith("short") else _observations(designation)

    dataset = module.collect_sequence_dataset(
        manifest,
        output,
        6,
        retries=0,
        query_delay_seconds=0,
        target_per_class=1,
        fetcher=fetcher,
    )

    assert dataset["summary"]["target_met"] is True
    assert dataset["summary"]["accepted_class_counts"] == {
        "known_object": 1,
        "neo_candidate": 1,
    }
    assert calls == ["neo-short", "known-short", "neo-good", "known-good"]


def test_target_per_class_fails_when_reserve_pool_is_exhausted(tmp_path: Path) -> None:
    """An undersized accepted set must stop before dataset preparation."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, [("neo-short", "neo_candidate")])

    with pytest.raises(RuntimeError, match="candidate pool exhausted"):
        module.collect_sequence_dataset(
            manifest,
            output,
            1,
            retries=0,
            query_delay_seconds=0,
            target_per_class=1,
            fetcher=lambda designation, force_refresh=False: [],
        )

    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    assert checkpoint["summary"]["target_met"] is False


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([("433", "unsupported")], "unsupported neo_class"),
        ([], "empty"),
    ],
)
def test_manifest_validation_fails_closed(
    tmp_path: Path,
    rows: list[tuple[str, str]],
    message: str,
) -> None:
    """Invalid manifests must be rejected before any provider request is attempted."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, rows)

    with pytest.raises(ValueError, match=message):
        module.collect_sequence_dataset(manifest, output, 1, query_delay_seconds=0)


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("max_objects", 0, "max_objects"),
        ("min_observations", 1, "min_observations"),
        ("min_nights", 0, "min_nights"),
        ("max_observations_per_object", 1, "max_observations_per_object"),
        ("retries", -1, "retries"),
        ("query_delay_seconds", -1, "query_delay_seconds"),
        ("max_consecutive_query_errors", 0, "max_consecutive_query_errors"),
        ("target_per_class", 0, "target_per_class"),
        ("workers", 0, "workers"),
    ],
)
def test_collection_bounds_are_validated(
    tmp_path: Path,
    keyword: str,
    value: int,
    message: str,
) -> None:
    """Unsafe or nonsensical collection bounds must fail before network activity."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, [("433", "neo_candidate")])
    arguments: dict[str, Any] = {
        "labels_csv": manifest,
        "output_json": output,
        "max_objects": 1,
        "query_delay_seconds": 0,
    }
    arguments[keyword] = value

    with pytest.raises(ValueError, match=message):
        module.collect_sequence_dataset(**arguments)


def test_parallel_workers_produce_complete_dataset(tmp_path: Path) -> None:
    """Multiple workers must accept all designations and write a valid checkpoint."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(
        manifest,
        [
            ("neo-1", "neo_candidate"),
            ("neo-2", "neo_candidate"),
            ("mba-1", "main_belt_asteroid"),
            ("mba-2", "main_belt_asteroid"),
        ],
    )

    dataset = module.collect_sequence_dataset(
        manifest,
        output,
        4,
        query_delay_seconds=0,
        workers=4,
        fetcher=lambda designation, force_refresh=False: _observations(designation),
    )

    assert dataset["summary"]["accepted_objects"] == 4
    accepted = {entry["designation"] for entry in dataset["entries"]}
    assert accepted == {"neo-1", "neo-2", "mba-1", "mba-2"}
    assert dataset["safety"]["external_submission_enabled"] is False
    # checkpoint on disk must also reflect all four entries
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["summary"]["accepted_objects"] == 4


def test_parallel_mode_respects_target_per_class(tmp_path: Path) -> None:
    """Parallel workers must not exceed the accepted quota per class."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(
        manifest,
        [
            ("neo-1", "neo_candidate"),
            ("neo-2", "neo_candidate"),
            ("neo-3", "neo_candidate"),
            ("mba-1", "main_belt_asteroid"),
            ("mba-2", "main_belt_asteroid"),
            ("mba-3", "main_belt_asteroid"),
        ],
    )

    dataset = module.collect_sequence_dataset(
        manifest,
        output,
        6,
        query_delay_seconds=0,
        workers=4,
        target_per_class=1,
        fetcher=lambda designation, force_refresh=False: _observations(designation),
    )

    counts = dataset["summary"]["accepted_class_counts"]
    assert counts.get("neo_candidate", 0) <= 1
    assert counts.get("main_belt_asteroid", 0) <= 1


def test_parallel_circuit_breaker_trips_on_consecutive_errors(tmp_path: Path) -> None:
    """The circuit breaker must still stop acquisition when errors exceed the threshold."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(
        manifest,
        [
            ("neo-1", "neo_candidate"),
            ("neo-2", "neo_candidate"),
            ("mba-1", "main_belt_asteroid"),
        ],
    )

    def failing_fetcher(designation: str, force_refresh: bool = False) -> list[SimpleNamespace]:
        """Simulate an unavailable provider for all designations."""
        raise ConnectionError(f"provider down for {designation}")

    with pytest.raises(RuntimeError, match="consecutive provider errors"):
        module.collect_sequence_dataset(
            manifest,
            output,
            3,
            retries=0,
            query_delay_seconds=0,
            max_consecutive_query_errors=2,
            workers=2,
            fetcher=failing_fetcher,
        )

    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    assert checkpoint["schema_version"] == module.SCHEMA_VERSION
    assert all(item["status"] == "query_error" for item in checkpoint["query_log"])


def test_parallel_resume_skips_already_accepted(tmp_path: Path) -> None:
    """Resume mode must work correctly with workers > 1."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(manifest, [("433", "neo_candidate"), ("434", "neo_candidate")])
    calls: list[str] = []

    def fetcher(designation: str, force_refresh: bool = False) -> list[SimpleNamespace]:
        calls.append(designation)
        return _observations(designation)

    # First run: fetch both.
    module.collect_sequence_dataset(
        manifest, output, 2, query_delay_seconds=0, workers=2, fetcher=fetcher
    )
    first_calls = list(calls)
    calls.clear()

    # Second run with resume: no new fetches should occur.
    resumed = module.collect_sequence_dataset(
        manifest, output, 2, query_delay_seconds=0, workers=2, resume=True, fetcher=fetcher
    )

    assert set(first_calls) == {"433", "434"}
    assert calls == []
    assert resumed["summary"]["accepted_objects"] == 2


def test_parallel_circuit_breaker_threshold_scales_with_workers(tmp_path: Path) -> None:
    """With workers=4, base threshold 3 needs 3+(4-1)=6 consecutive errors to trip.

    With the old code, 3 errors from 3 concurrent workers would trip immediately
    because as_completed() returns errors before successes.  The fix adds
    (workers-1) to the threshold so the initial worker burst cannot false-trip.
    """
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    # 4 failing + 2 succeeding: errors should NOT trip (4 < effective threshold 6)
    _write_manifest(
        manifest,
        [
            ("fail-1", "neo_candidate"),
            ("fail-2", "neo_candidate"),
            ("fail-3", "main_belt_asteroid"),
            ("fail-4", "main_belt_asteroid"),
            ("ok-1", "neo_candidate"),
            ("ok-2", "main_belt_asteroid"),
        ],
    )

    def selective_fetcher(
        designation: str, force_refresh: bool = False
    ) -> list[SimpleNamespace]:
        if designation.startswith("fail-"):
            raise ConnectionError(f"provider down for {designation}")
        return _observations(designation)

    # With workers=4 and max_consecutive_query_errors=3, effective threshold = 6.
    # Four errors do not reach 6, so no RuntimeError should be raised.
    result = module.collect_sequence_dataset(
        manifest,
        output,
        6,
        retries=0,
        query_delay_seconds=0,
        max_consecutive_query_errors=3,
        workers=4,
        fetcher=selective_fetcher,
    )
    assert result["summary"]["accepted_objects"] == 2
    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    error_count = sum(
        1 for item in checkpoint["query_log"] if item["status"] == "query_error"
    )
    assert error_count == 4


def test_parallel_circuit_breaker_error_message_includes_diagnostics(
    tmp_path: Path,
) -> None:
    """The circuit-break error message must include failing designation and error type."""
    module = _load_skill()
    manifest = tmp_path / "labels.csv"
    output = tmp_path / "raw.json"
    _write_manifest(
        manifest,
        [("bad-1", "neo_candidate"), ("bad-2", "neo_candidate")],
    )

    def failing_fetcher(
        designation: str, force_refresh: bool = False
    ) -> list[SimpleNamespace]:
        raise ConnectionError("mpc down")

    with pytest.raises(RuntimeError, match=r"recent failures:.*bad-1.*ConnectionError"):
        module.collect_sequence_dataset(
            manifest,
            output,
            2,
            retries=0,
            query_delay_seconds=0,
            max_consecutive_query_errors=1,
            workers=1,
            fetcher=failing_fetcher,
        )
