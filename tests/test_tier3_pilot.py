"""Offline tests for the approved five-class Tier 3 pilot workflow."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


def _load_skill(filename: str) -> Any:
    """Load a Skill module directly so its operator implementation is tested."""
    skill_path = Path(__file__).resolve().parents[1] / "Skills" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), skill_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mpc_line(
    designation: str,
    *,
    h_mag: float = 20.0,
    eccentricity: float = 0.1,
    semimajor_axis: float = 2.5,
) -> str:
    """Create one fixed-column MPC record for parser and policy tests."""
    characters = [" "] * 120
    characters[0:7] = f"{designation:<7}"[:7]
    characters[8:13] = f"{h_mag:5.1f}"
    characters[70:79] = f"{eccentricity:9.6f}"
    characters[92:103] = f"{semimajor_axis:11.7f}"
    return "".join(characters)


def _entry(class_name: str, index: int) -> dict[str, Any]:
    """Create a valid multi-night sequence for preparation tests."""
    label_map = {
        "neo_candidate": 0,
        "known_object": 1,
        "main_belt_asteroid": 2,
        "stellar_artifact": 3,
        "other_solar_system": 4,
    }
    return {
        "designation": f"{class_name}-{index}",
        "class_name": class_name,
        "label": label_map[class_name],
        "observations": [
            {
                "obs_id": f"{class_name}-{index}-{observation}",
                "ra_deg": 10.0 + observation,
                "dec_deg": 2.0,
                "jd": 2460000.0 + observation,
                "mag": 20.0,
                "mag_err": 0.1,
                "filter_band": "r",
                "mission": "MPC",
            }
            for observation in range(3)
        ],
    }


def test_unpack_designation_strips_leading_zeros() -> None:
    """Numbered packed designations need leading zeros removed for MPC.get_observations."""
    module = _load_skill("generate_training_labels.py")
    assert module._unpack_designation("00433") == "433"
    assert module._unpack_designation("00001") == "1"
    assert module._unpack_designation("12345") == "12345"


def test_unpack_designation_passes_through_provisional() -> None:
    """Provisional packed designations (letters+digits) must reach astroquery unchanged."""
    module = _load_skill("generate_training_labels.py")
    assert module._unpack_designation("K23A00A") == "K23A00A"
    assert module._unpack_designation("J99X99Y") == "J99X99Y"


def test_parse_mpc_80col_line_emits_unpacked_designation() -> None:
    """The parser must output the form MPC.get_observations accepts, not the packed form."""
    module = _load_skill("generate_training_labels.py")
    record = module.parse_mpc_80col_line(_mpc_line("00433"))
    assert record is not None
    assert record["designation"] == "433"


def test_tier3_nea_policy_separates_temporal_classes() -> None:
    """Numbered NEOs must use late windows and provisional NEOs early windows."""
    module = _load_skill("generate_training_labels.py")
    text = "\n".join(
        [
            _mpc_line("00433"),
            _mpc_line("K23A00A"),
            _mpc_line("00719"),
            _mpc_line("K24B00B"),
        ]
    )

    rows = module.build_tier3_nea_rows(text, 2)

    assert [row["neo_class"] for row in rows] == [
        "neo_candidate",
        "neo_candidate",
        "known_object",
        "known_object",
    ]
    assert {row["sequence_window"] for row in rows[:2]} == {"early"}
    assert {row["sequence_window"] for row in rows[2:]} == {"late"}


def test_tier3_manifest_fails_closed_when_a_class_is_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The approved pilot size is a hard gate for every MPC-backed class."""
    module = _load_skill("generate_training_labels.py")
    monkeypatch.setattr(
        module,
        "fetch_tier3_nea_rows",
        lambda limit: [
            {"neo_class": "neo_candidate"},
            {"neo_class": "known_object"},
        ],
    )
    monkeypatch.setattr(
        module,
        "fetch_tier3_mba_rows",
        lambda limit: [{"neo_class": "main_belt_asteroid"}],
    )
    monkeypatch.setattr(module, "fetch_other_solar_system_rows", lambda limit: [])

    with pytest.raises(RuntimeError, match="incomplete"):
        module.build_tier3_pilot_manifest(1)


def test_other_solar_system_fetch_overfetches_after_unusable_row() -> None:
    """Comet acquisition should retain the target after blank rows are filtered."""
    module = _load_skill("generate_training_labels.py")
    captured: dict[str, Any] = {}

    def query_objects(target_type: str, *, limit: int) -> list[dict[str, Any]]:
        """Return duplicate/blank rows followed by enough usable confirmed comets."""
        captured["target_type"] = target_type
        captured["limit"] = limit
        return [
            {"designation": ""},
            {"designation": "1P", "absolute_magnitude": 10.0},
            {"designation": "1P", "absolute_magnitude": 10.0},
            {"designation": "2P", "absolute_magnitude": 11.0},
        ]

    rows = module.fetch_other_solar_system_rows(2, query_objects=query_objects)

    assert captured == {"target_type": "comet", "limit": 52}
    assert [row["designation"] for row in rows] == ["1P", "2P"]


class _FakeAlerce:
    """Return deterministic public-broker shapes without network access."""

    def query_objects(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return one object that satisfies the configured bogus query."""
        assert kwargs["survey"] == "ztf"
        assert kwargs["classifier"] == "stamp_classifier"
        assert kwargs["page"] == 1
        return [{"oid": "ZTF-test-artifact"}]

    def query_detections(self, oid: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Return a valid multi-night ZTF detection history."""
        assert oid == "ZTF-test-artifact"
        assert kwargs["survey"] == "ztf"
        return [
            {
                "candid": index,
                "mjd": 60000.0 + index,
                "ra": 20.0 + index,
                "dec": -5.0,
                "magpsf": 19.5,
                "sigmapsf": 0.1,
                "fid": 1,
                "rb": 0.1,
                "drb": 0.05,
            }
            for index in range(3)
        ]


def test_alerce_artifact_collection_records_safe_provenance(tmp_path: Path) -> None:
    """Broker acquisition should produce the shared contract without secrets."""
    module = _load_skill("fetch_alerce_artifact_sequences.py")
    output = tmp_path / "artifacts.json"

    dataset = module.collect_artifact_sequences(
        output,
        1,
        query_delay_seconds=0,
        client_factory=_FakeAlerce,
    )

    assert dataset["summary"]["accepted_objects"] == 1
    assert dataset["entries"][0]["class_name"] == "stellar_artifact"
    assert dataset["entries"][0]["observations"][0]["mission"] == "ZTF"
    assert dataset["safety"]["external_submission_enabled"] is False
    assert "password" not in output.read_text(encoding="utf-8").lower()


class _FailingAlerce:
    """Raise a network-like error so bounded retry evidence can be inspected."""

    def query_objects(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Fail every candidate request without contacting the public broker."""
        raise TimeoutError("offline timeout")


def test_alerce_failure_is_bounded_and_checkpointed(tmp_path: Path) -> None:
    """An initial broker timeout should leave resumable, secret-free evidence."""
    module = _load_skill("fetch_alerce_artifact_sequences.py")
    output = tmp_path / "artifacts.json"
    sleeps: list[float] = []

    with pytest.raises(RuntimeError, match="after 2 attempts"):
        module.collect_artifact_sequences(
            output,
            1,
            query_delay_seconds=0.5,
            request_attempts=2,
            retry_delay_seconds=0.5,
            client_factory=_FailingAlerce,
            sleep_fn=sleeps.append,
        )

    checkpoint = json.loads(output.read_text(encoding="utf-8"))
    assert sleeps == [0.5]
    assert checkpoint["summary"]["accepted_objects"] == 0
    assert checkpoint["acquisition_errors"][0]["error_type"] == "TimeoutError"
    assert checkpoint["safety"]["secret_values_recorded"] is False


def test_alerce_uses_small_stable_candidate_pages(tmp_path: Path) -> None:
    """Candidate discovery should avoid the expensive detection-count sort."""
    module = _load_skill("fetch_alerce_artifact_sequences.py")
    output = tmp_path / "artifacts.json"
    calls: list[dict[str, Any]] = []

    class Client(_FakeAlerce):
        """Capture candidate-page arguments before returning one valid object."""

        def query_objects(self, **kwargs: Any) -> list[dict[str, Any]]:
            """Record the lightweight stable query contract."""
            calls.append(kwargs)
            return super().query_objects(**kwargs)

    module.collect_artifact_sequences(
        output,
        1,
        candidate_page_size=7,
        query_delay_seconds=0,
        client_factory=Client,
    )

    assert calls[0]["page_size"] == 7
    assert calls[0]["order_by"] == "oid"
    assert calls[0]["order_mode"] == "ASC"


def test_alerce_resume_retries_prior_detection_error(tmp_path: Path) -> None:
    """A transient object failure must remain eligible on the resumed run."""
    module = _load_skill("fetch_alerce_artifact_sequences.py")
    output = tmp_path / "artifacts.json"

    class FailingDetections(_FakeAlerce):
        """Return a candidate but fail its first detection-history request."""

        def query_detections(self, oid: str, **kwargs: Any) -> list[dict[str, Any]]:
            """Simulate one transient broker timeout."""
            raise TimeoutError("temporary timeout")

    with pytest.raises(RuntimeError, match="only 0 accepted"):
        module.collect_artifact_sequences(
            output,
            1,
            query_delay_seconds=0,
            request_attempts=1,
            max_candidate_pages=1,
            client_factory=FailingDetections,
        )

    resumed = module.collect_artifact_sequences(
        output,
        1,
        query_delay_seconds=0,
        request_attempts=1,
        max_candidate_pages=1,
        resume=True,
        client_factory=_FakeAlerce,
    )

    assert resumed["summary"]["accepted_objects"] == 1
    assert [item["status"] for item in resumed["query_log"]] == [
        "query_error",
        "accepted",
    ]


def test_alerce_client_network_configuration_normalizes_and_times_out() -> None:
    """The ALeRCE 2.3 legacy client should avoid redirects and bound requests."""
    module = _load_skill("fetch_alerce_artifact_sequences.py")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    class Session:
        """Capture delegated request arguments for timeout verification."""

        def request(self, method: str, url: str, **kwargs: Any) -> str:
            """Record one synthetic request and return a sentinel response."""
            calls.append((method, url, kwargs))
            return "ok"

    class LegacyClient:
        """Provide the ALeRCE attributes modified by the network hardener."""

        def __init__(self) -> None:
            """Create the slash-terminated URL shape shipped by ALeRCE 2.3."""
            self.config = {"ZTF_API_URL": "https://api.example/v1/"}
            self.session = Session()

    class Client:
        """Expose one legacy client through the public ALeRCE attribute."""

        def __init__(self) -> None:
            """Create the nested legacy client used by the compatibility API."""
            self.legacy_ztf_client = LegacyClient()

    client = Client()
    module._configure_client_network(client, 12.5)
    response = client.legacy_ztf_client.session.request(
        "GET",
        "https://api.example/v1/objects",
    )

    assert client.legacy_ztf_client.config["ZTF_API_URL"] == "https://api.example/v1"
    assert response == "ok"
    assert calls == [
        ("GET", "https://api.example/v1/objects", {"timeout": 12.5})
    ]


def test_prepare_sequence_splits_is_balanced_and_leak_free(tmp_path: Path) -> None:
    """Preparation should emit all three splits with no designation overlap."""
    module = _load_skill("build_sequence_dataset.py")
    classes = list(module.LABEL_MAP)
    entries = [_entry(class_name, index) for class_name in classes for index in range(10)]
    source = tmp_path / "raw.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "test-v1",
                "entries": entries,
                "source": {"provider": "offline-test"},
                "safety": {
                    "external_submission_enabled": False,
                    "impact_probability_generated": False,
                    "secret_values_recorded": False,
                },
            }
        ),
        encoding="utf-8",
    )

    report = module.prepare_sequence_splits(
        [source],
        tmp_path / "prepared",
        min_per_class=10,
    )

    assert report["validation"]["passed"] is True
    assert report["pilot_only"] is True
    assert report["production_promotion_allowed"] is False
    split_designations: list[set[str]] = []
    for split_name in ("train", "calibration", "test"):
        rows = list(csv_rows(tmp_path / "prepared" / f"{split_name}.csv"))
        split_designations.append({row["designation"] for row in rows})
        assert set(row["class_name"] for row in rows) == set(classes)
    assert split_designations[0].isdisjoint(split_designations[1])
    assert split_designations[0].isdisjoint(split_designations[2])
    assert split_designations[1].isdisjoint(split_designations[2])


def csv_rows(path: Path) -> list[dict[str, str]]:
    """Read generated CSV rows without introducing a pandas dependency."""
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_validation_rejects_missing_five_class_minimum() -> None:
    """Partial datasets must not reach tokenization or training."""
    module = _load_skill("build_sequence_dataset.py")

    with pytest.raises(ValueError, match="five-class minimum"):
        module.validate_entries([_entry("neo_candidate", 0)], min_per_class=1)


def _write_training_split(path: Path) -> None:
    """Write five balanced two-token examples for trainer evidence tests."""
    import csv

    token_columns = [
        f"tok_{time_index}_{feature_index}"
        for time_index in range(2)
        for feature_index in range(5)
    ]
    fieldnames = ["designation", "class_name", *token_columns, "label"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for label, class_name in enumerate(
            [
                "neo_candidate",
                "known_object",
                "main_belt_asteroid",
                "stellar_artifact",
                "other_solar_system",
            ]
        ):
            row = {column: "0.1" for column in token_columns}
            row.update(
                {
                    "designation": f"{class_name}-1",
                    "class_name": class_name,
                    "label": str(label),
                }
            )
            writer.writerow(row)


def test_tier3_training_emits_held_out_evidence(tmp_path: Path) -> None:
    """Training should save the best checkpoint and transparent pilot metrics."""
    import torch.nn as nn

    module = _load_skill("train_tier3_transformer.py")
    train_csv = tmp_path / "train.csv"
    validation_csv = tmp_path / "validation.csv"
    test_csv = tmp_path / "test.csv"
    for path in (train_csv, validation_csv, test_csv):
        _write_training_split(path)

    class TinySequenceModel(nn.Module):
        """Provide a fast trainable model with the production logits contract."""

        def __init__(self) -> None:
            """Create one mean-pooled linear five-class classifier."""
            super().__init__()
            self.linear = nn.Linear(5, 5)

        def forward(self, sequence: Any) -> Any:
            """Return logits for one variable-length sequence."""
            return self.linear(sequence.mean(dim=1))

    model_path = tmp_path / "tier3.pt"
    report_path = tmp_path / "training_report.json"
    report = module.train(
        train_csv,
        validation_csv,
        test_csv,
        epochs=1,
        out_path=model_path,
        report_path=report_path,
        model_factory=TinySequenceModel,
    )

    assert model_path.exists()
    assert report_path.exists()
    assert report["best_epoch"] == 1
    assert set(report["test"]) == {
        "accuracy",
        "loss",
        "macro_f1",
        "per_class_recall",
    }
    assert report["model_sha256"] == module._sha256_file(model_path)
    assert report["pilot_only"] is True
    assert report["production_promotion_allowed"] is False


class _MultiFakeAlerce(_FakeAlerce):
    """Return two OIDs so parallel workers have distinct tasks."""

    def query_objects(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return two objects only on page 1; empty thereafter."""
        if kwargs.get("page", 1) == 1:
            return [{"oid": "ZTF-obj-A"}, {"oid": "ZTF-obj-B"}]
        return []

    def query_detections(self, oid: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Return a valid multi-night history for any requested OID."""
        return [
            {
                "candid": index,
                "mjd": 60000.0 + index,
                "ra": 30.0 + index,
                "dec": -10.0,
                "magpsf": 19.5,
                "sigmapsf": 0.1,
                "fid": 1,
                "rb": 0.05,
                "drb": 0.02,
            }
            for index in range(3)
        ]


def test_alerce_parallel_workers_produce_complete_dataset(tmp_path: Path) -> None:
    """Multiple detection-fetch workers must accept all OIDs and checkpoint correctly."""
    module = _load_skill("fetch_alerce_artifact_sequences.py")
    output = tmp_path / "artifacts.json"

    dataset = module.collect_artifact_sequences(
        output,
        2,
        query_delay_seconds=0,
        workers=2,
        client_factory=_MultiFakeAlerce,
    )

    assert dataset["summary"]["accepted_objects"] == 2
    accepted_oids = {entry["designation"] for entry in dataset["entries"]}
    assert accepted_oids == {"ZTF-obj-A", "ZTF-obj-B"}
    assert dataset["safety"]["external_submission_enabled"] is False
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["summary"]["accepted_objects"] == 2


def test_alerce_workers_validation_rejects_zero(tmp_path: Path) -> None:
    """workers=0 must be rejected before any network activity."""
    module = _load_skill("fetch_alerce_artifact_sequences.py")
    output = tmp_path / "artifacts.json"

    with pytest.raises(ValueError, match="workers"):
        module.collect_artifact_sequences(
            output, 1, query_delay_seconds=0, workers=0, client_factory=_FakeAlerce
        )
