from __future__ import annotations

import base64
from pathlib import Path

import numpy as np

from benchmarks.benchmark_cnn_v1 import model, preprocess, score


def _encoded_plane(value: float) -> str:
    """Create one deterministic base64 float32 cutout plane for tests."""
    arr = np.full((preprocess.CUTOUT_SIZE, preprocess.CUTOUT_SIZE), value, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def test_benchmark_metadata_freezes_current_artifact() -> None:
    """The benchmark metadata must identify the committed model artifact."""
    metadata = model.benchmark_metadata()
    assert metadata["benchmark_id"] == "benchmark_cnn_v1"
    assert metadata["model_artifact"] == "models/tier2_cnn.pt"
    assert metadata["artifact_sha256"] == (
        "981a59f6935c51ec66321cd171a4e74d8ac58eaf6fd73ca0e84f79c0ea3218ec"
    )
    assert metadata["input_shape"] == [3, 63, 63]
    assert metadata["production_status"] == "benchmark_only_not_production_promoted"
    assert metadata["labels"] == list(model.LABELS)


def test_locked_config_and_model_card_record_limitations() -> None:
    """The frozen config and card must preserve promotion blockers."""
    root = Path("benchmarks/benchmark_cnn_v1")
    config = (root / "locked_config.yaml").read_text()
    card = (root / "MODEL_CARD.md").read_text()
    assert "model_artifact: models/tier2_cnn.pt" in config
    assert "split_policy: random_split_historical_diagnostic_only" in config
    assert "grouped_object_field_night_source_splits" in config
    assert "not production-promoted" in card
    assert "Random-split accuracy" in card
    assert "not authorize production promotion" in card


def test_decode_base64_triplet_uses_locked_shape() -> None:
    """Valid encoded triplets decode to three 63x63 float32 planes."""
    triplet = preprocess.decode_base64_triplet(
        _encoded_plane(1.0),
        _encoded_plane(2.0),
        _encoded_plane(3.0),
    )
    assert triplet is not None
    science, reference, difference = triplet
    assert science.shape == (63, 63)
    assert reference.dtype == np.float32
    assert float(difference[0, 0]) == 3.0


def test_decode_base64_triplet_rejects_bad_payload() -> None:
    """Invalid payloads fail closed instead of silently resizing arrays."""
    assert preprocess.decode_base64_triplet("bad", _encoded_plane(2.0), _encoded_plane(3.0)) is None


def test_load_npz_triplet_zero_fills_non_finite_pixels(tmp_path: Path) -> None:
    """Persisted cutouts use the same zero-fill policy as training."""
    science = np.zeros((63, 63), dtype=np.float32)
    reference = np.zeros((63, 63), dtype=np.float32)
    difference = np.zeros((63, 63), dtype=np.float32)
    science[0, 0] = np.nan
    reference[0, 0] = np.inf
    difference[0, 0] = -np.inf
    path = tmp_path / "triplet.npz"
    np.savez(path, science=science, reference=reference, difference=difference)

    loaded = preprocess.load_npz_triplet(path)

    assert all(plane.dtype == np.float32 for plane in loaded)
    assert [float(plane[0, 0]) for plane in loaded] == [0.0, 0.0, 0.0]


def test_load_npz_triplet_rejects_wrong_shape(tmp_path: Path) -> None:
    """Wrong-size cutouts fail with a clear shape error."""
    path = tmp_path / "bad.npz"
    np.savez(
        path,
        science=np.zeros((62, 63), dtype=np.float32),
        reference=np.zeros((63, 63), dtype=np.float32),
        difference=np.zeros((63, 63), dtype=np.float32),
    )

    try:
        preprocess.load_npz_triplet(path)
    except ValueError as exc:
        assert "expected (63, 63)" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("load_npz_triplet accepted a wrong-shaped cutout")


def test_score_tracklet_delegates_to_injected_predictor() -> None:
    """The score wrapper remains testable without loading torch weights."""

    class StubTracklet:
        """Minimal object used because the injected predictor ignores content."""

    def fake_predictor(tracklet, loaded_model):  # type: ignore[no-untyped-def]
        """Return a deterministic posterior from an injected predictor."""
        assert isinstance(tracklet, StubTracklet)
        assert loaded_model == "loaded"
        return {"neo_candidate": 0.1, "stellar_artifact": 0.9}

    result = score.score_tracklet(StubTracklet(), model="loaded", predict_fn=fake_predictor)  # type: ignore[arg-type]

    assert result == {"neo_candidate": 0.1, "stellar_artifact": 0.9}
