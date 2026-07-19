"""Tests for src/known_object_exclusion.py (Gate Z2 time-aware exclusion).

These tests are the safety net for the project's "no future-catalog
leakage" claim -- getting the direction of any comparison backwards here
would silently break the discovery-paper's defensibility, so every
boundary case (missing first_obs, exact-cutoff equality, snapshot validity)
is exercised explicitly rather than assumed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from known_object_exclusion import (
    KnownObject,
    KnownObjectCatalogSnapshot,
    known_as_of,
    known_at_observation_jd,
    validate_snapshot_usable_for_replay,
)


@pytest.mark.parametrize(
    ("first_jd", "observation_jd", "expected"),
    [
        (2459000.5, 2459000.5, True),
        (2459000.6, 2459000.5, False),
        (None, 2459000.5, False),
        (float("nan"), 2459000.5, False),
        (2459000.4, float("inf"), False),
    ],
)
def test_known_at_observation_jd_exact_boundaries(first_jd, observation_jd, expected):
    assert known_at_observation_jd(first_jd, observation_jd) is expected


def _known_object(pdes: str, first_obs: date | None) -> KnownObject:
    return KnownObject(snapshot_id="snap-1", pdes=pdes, first_obs=first_obs)


def test_known_as_of_includes_objects_first_observed_on_or_before_cutoff():
    cutoff = date(2020, 6, 1)
    objs = [
        _known_object("before", date(2020, 1, 1)),
        _known_object("on_cutoff", date(2020, 6, 1)),
        _known_object("after", date(2020, 12, 1)),
    ]
    result = {obj.pdes for obj in known_as_of(objs, cutoff)}
    assert result == {"before", "on_cutoff"}


def test_known_as_of_excludes_objects_with_missing_first_obs_fail_closed():
    """A missing first_obs must NOT be treated as 'known' -- the safe
    direction of error is under-suppression, not over-suppression."""
    cutoff = date(2020, 6, 1)
    objs = [_known_object("unknown_date", None)]
    assert known_as_of(objs, cutoff) == []


def test_known_as_of_empty_input_returns_empty():
    assert known_as_of([], date(2020, 1, 1)) == []


def test_known_as_of_does_not_mutate_input_order_or_length_incorrectly():
    cutoff = date(2020, 6, 1)
    objs = [_known_object(f"obj{i}", date(2020, 1, 1) if i % 2 == 0 else None) for i in range(10)]
    result = known_as_of(objs, cutoff)
    assert len(result) == 5
    assert all(obj.first_obs is not None and obj.first_obs <= cutoff for obj in result)


def _snapshot(valid_before: datetime | None) -> KnownObjectCatalogSnapshot:
    return KnownObjectCatalogSnapshot(
        snapshot_id="snap-1",
        source="jpl_sbdb",
        source_url="https://ssd-api.jpl.nasa.gov/sbdb_query.api?sb-group=neo",
        fetched_at_utc=datetime(2026, 7, 2, tzinfo=UTC),
        valid_for_replay_before_utc=valid_before,
        raw_payload_uri="/tmp/snapshot.json",
        record_count=42153,
    )


def test_validate_snapshot_usable_for_replay_accepts_covering_cutoff():
    snapshot = _snapshot(datetime(2026, 12, 31, tzinfo=UTC))
    ok, reason = validate_snapshot_usable_for_replay(snapshot, replay_cutoff=date(2020, 6, 1))
    assert ok is True
    assert "covers" in reason


def test_validate_snapshot_usable_for_replay_rejects_cutoff_beyond_validity():
    snapshot = _snapshot(datetime(2019, 1, 1, tzinfo=UTC))
    ok, reason = validate_snapshot_usable_for_replay(snapshot, replay_cutoff=date(2020, 6, 1))
    assert ok is False
    assert "only valid for replay before" in reason


def test_validate_snapshot_usable_for_replay_fails_closed_on_missing_validity():
    """A snapshot with no stated validity window must not be assumed safe."""
    snapshot = _snapshot(None)
    ok, reason = validate_snapshot_usable_for_replay(snapshot, replay_cutoff=date(2020, 6, 1))
    assert ok is False
    assert "no valid_for_replay_before_utc" in reason


def test_known_object_model_is_frozen():
    obj = _known_object("x", date(2020, 1, 1))
    with pytest.raises(Exception):  # noqa: B017 -- pydantic ValidationError, immutability check only
        obj.pdes = "y"  # type: ignore[misc]
