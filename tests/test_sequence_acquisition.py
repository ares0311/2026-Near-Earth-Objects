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
        ("retries", -1, "retries"),
        ("query_delay_seconds", -1, "query_delay_seconds"),
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
