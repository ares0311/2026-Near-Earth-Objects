"""Offline tests for the sharded ZTF field/night metadata inventory."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "Skills"
sys.path.insert(0, str(SKILLS))
SPEC = importlib.util.spec_from_file_location(
    "inventory_ztf_field_night_coverage",
    SKILLS / "inventory_ztf_field_night_coverage.py",
)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)


def _manifest(tmp_path: Path, field_count: int = 6) -> Path:
    path = tmp_path / "coverage_batch.json"
    path.write_text(
        json.dumps(
            {
                "batch_id": "coverage_batch_v1",
                "data_role": "metadata_only_coverage_preflight",
                "start_jd_exclusive": 2460209.5,
                "end_jd_exclusive": 2460574.5,
                "size_deg": 2.0,
                "min_distinct_nights": 3,
                "fields": [
                    {
                        "field_id": f"field_{index}",
                        "role": "live_search",
                        "ra_deg": 10.0 + index,
                        "dec_deg": -20.0 + index,
                    }
                    for index in range(field_count)
                ],
                "safety": {
                    "metadata_only": True,
                    "raw_alert_archives_downloaded": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _load(tmp_path: Path, monkeypatch, field_count: int = 6):
    monkeypatch.setattr(inventory, "REPO_ROOT", tmp_path)
    return inventory.load_batch_manifest(_manifest(tmp_path, field_count))


def _fake_field_result(field, batch, _out_dir):
    nights = ["20240910", "20240911", "20240919"]
    return {
        "field_id": field.field_id,
        "role": field.role,
        "ra_deg": field.ra_deg,
        "dec_deg": field.dec_deg,
        "n_rows": 12,
        "n_distinct_nights": len(nights),
        "distinct_nights_yyyymmdd": nights,
        "passes_min_distinct_nights": len(nights) >= batch.min_distinct_nights,
        "raw_response_sha256": "a" * 64,
        "raw_response_path": f"raw/{field.field_id}.ipac",
    }


def test_load_manifest_and_assign_disjoint_fields(tmp_path: Path, monkeypatch) -> None:
    batch = _load(tmp_path, monkeypatch)
    assert [field.field_id for field in inventory.assigned_fields(batch.fields, 0, 2)] == [
        "field_0",
        "field_2",
        "field_4",
    ]
    assert [field.field_id for field in inventory.assigned_fields(batch.fields, 1, 2)] == [
        "field_1",
        "field_3",
        "field_5",
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(data_role="live_search"), "data_role"),
        (lambda data: data.update(end_jd_exclusive=2461000.0), "bounded ingest cap"),
        (lambda data: data.update(size_deg=3.0), "size_deg"),
        (lambda data: data.update(min_distinct_nights=2), "at least 3"),
        (
            lambda data: data["safety"].update(raw_alert_archives_downloaded=True),
            "raw_alert_archives_downloaded",
        ),
    ],
)
def test_manifest_validation_fails_closed(
    tmp_path: Path, monkeypatch, mutation, message: str
) -> None:
    monkeypatch.setattr(inventory, "REPO_ROOT", tmp_path)
    path = _manifest(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        inventory.load_batch_manifest(path)


def test_inventory_field_delegates_to_bounded_metadata_ingest(
    tmp_path: Path, monkeypatch
) -> None:
    batch = _load(tmp_path, monkeypatch, field_count=1)
    seen: dict[str, object] = {}

    def fake_ingest(**kwargs):
        seen.update(kwargs)
        return {
            "n_rows": 20,
            "distinct_nights_yyyymmdd": ["20240910", "20240911", "20240919"],
            "raw_response_sha256": "b" * 64,
            "raw_response_path": "raw.ipac",
        }

    monkeypatch.setattr(inventory.bounded_ingest, "run_bounded_ingest", fake_ingest)
    result = inventory.inventory_field(batch.fields[0], batch, tmp_path / "out")
    assert seen["size_deg"] == 2.0
    assert seen["start_jd"] == 2460209.5
    assert result["passes_min_distinct_nights"] is True


def test_run_shard_writes_only_owned_field(tmp_path: Path, monkeypatch) -> None:
    batch = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(inventory, "inventory_field", _fake_field_result)
    summary = inventory.run_shard(batch, tmp_path / "out", 2, 6, 1)
    assert summary["field_ids"] == ["field_2"]
    assert summary["field_results"][0]["field_id"] == "field_2"
    assert inventory._shard_summary_path(batch, tmp_path / "out", 2).is_file()


def test_run_shard_rejects_unverified_aggregate_concurrency(
    tmp_path: Path, monkeypatch
) -> None:
    batch = _load(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="verified ceiling"):
        inventory.run_shard(batch, tmp_path / "out", 0, 6, 6)


def test_status_is_safe_when_incomplete_and_merge_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    batch = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(inventory, "inventory_field", _fake_field_result)
    inventory.run_shard(batch, tmp_path / "out", 0, 6, 1)
    status = inventory.report_status(batch, tmp_path / "out", 6)
    assert status["complete"] is False
    assert status["missing_shards"] == [1, 2, 3, 4, 5]
    with pytest.raises(RuntimeError, match="missing shard"):
        inventory.merge_shards(batch, tmp_path / "out", 6)


def test_six_shards_merge_complete_inventory(tmp_path: Path, monkeypatch) -> None:
    batch = _load(tmp_path, monkeypatch)
    monkeypatch.setattr(inventory, "inventory_field", _fake_field_result)
    for index in range(6):
        inventory.run_shard(batch, tmp_path / "out", index, 6, 1)
    report = inventory.merge_shards(batch, tmp_path / "out", 6)
    assert report["metadata_only"] is True
    assert report["n_fields"] == 6
    assert report["n_fields_passing"] == 6
    assert report["all_fields_pass"] is True
    assert report["night_field_counts"] == {
        "20240910": 6,
        "20240911": 6,
        "20240919": 6,
    }


def test_output_dir_must_remain_inside_repository(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(inventory, "REPO_ROOT", repo)
    assert inventory.resolve_output_dir(repo / "Logs") == repo / "Logs"
    with pytest.raises(ValueError, match="inside the repository"):
        inventory.resolve_output_dir(tmp_path / "outside")
