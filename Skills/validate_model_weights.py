"""validate_model_weights.py — Verify committed model weights load and produce valid output.

Closes T2-D: loads each committed weight file (tier1_xgb.json, tier2_cnn.pt,
stacker_coef.json, tier3_transformer.pt) using the same loaders as classify.py,
runs a small synthetic inference pass, and asserts outputs are structurally valid.

Exit 0 only if all present model files pass. Missing files emit a warning and
are skipped (not a failure), because CI may run before all weights are committed.

Usage:
    PYTHONPATH=src uv run python Skills/validate_model_weights.py [--json]
"""

from __future__ import annotations

# Set thread-pool limits before any torch/numpy import to avoid CI deadlocks
# on single-core runners (macOS ATen thread-pool and MKL oversubscription).
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import base64
import json
import sys
from pathlib import Path

# Ensure src/ is on sys.path so classify/schemas can be imported when the
# script is run directly (not via PYTHONPATH env var alone).
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Expected class labels for all five-class models
# ---------------------------------------------------------------------------
_LABELS = [
    "neo_candidate",
    "known_object",
    "main_belt_asteroid",
    "stellar_artifact",
    "other_solar_system",
]

# ---------------------------------------------------------------------------
# Synthetic fixture builders
# ---------------------------------------------------------------------------


def _make_synthetic_observation(
    obs_id: str,
    jd_offset: float,
    with_cutouts: bool = False,
) -> Observation:  # type: ignore[name-defined]  # noqa: F821
    """Build a minimal synthetic Observation for testing model inference.

    When with_cutouts=True, generates a random 63×63 float32 base64 image
    triplet so the CNN path can be exercised.
    """
    import numpy as np

    from schemas import Observation  # imported here after sys.path is set

    kwargs: dict = {
        "obs_id": obs_id,
        "ra_deg": 90.0,
        "dec_deg": 15.0,
        "jd": 2460000.0 + jd_offset,
        "mag": 19.5,
        "mag_err": 0.05,
        "filter_band": "r",
        "mission": "ZTF",
        "real_bogus": 0.85,
        "deep_real_bogus": 0.88,
    }

    if with_cutouts:
        # Create a 63×63 random float32 cutout and base64-encode it.
        # The CNN expects (science, reference, difference) all present.
        rng = np.random.default_rng(42)
        def _cutout() -> str:
            arr = rng.random((63, 63), dtype=np.float32)
            return base64.b64encode(arr.tobytes()).decode()
        kwargs["cutout_science"] = _cutout()
        kwargs["cutout_reference"] = _cutout()
        kwargs["cutout_difference"] = _cutout()

    return Observation(**kwargs)


def _make_synthetic_tracklet(with_cutouts: bool = False) -> Tracklet:  # type: ignore[name-defined]  # noqa: F821
    """Build a minimal synthetic Tracklet with 3 observations across 3 nights."""
    from schemas import Tracklet  # imported here after sys.path is set

    obs = tuple(
        _make_synthetic_observation(f"obs_{i}", float(i), with_cutouts=with_cutouts)
        for i in range(3)
    )
    return Tracklet(
        object_id="synthetic_test_001",
        observations=obs,
        arc_days=2.0,
        motion_rate_arcsec_per_hour=30.0,
        motion_pa_degrees=45.0,
    )


def _make_synthetic_features() -> CandidateFeatures:  # type: ignore[name-defined]  # noqa: F821
    """Build a CandidateFeatures object with plausible non-None values."""
    from schemas import CandidateFeatures  # imported here after sys.path is set

    return CandidateFeatures(
        real_bogus_score=0.85,
        streak_score=0.1,
        psf_quality_score=0.9,
        motion_consistency_score=0.95,
        arc_coverage_score=0.5,
        nights_observed_score=0.33,
        brightness_score=0.6,
        color_score=0.5,
        lightcurve_variability_score=0.1,
        orbit_quality_score=None,
        moid_score=None,
        neo_class_confidence=None,
        pha_flag_confidence=None,
        known_object_score=0.0,
    )


# ---------------------------------------------------------------------------
# Per-model validation helpers
# ---------------------------------------------------------------------------


def _assert_five_class_proba(result: dict, model_name: str) -> None:
    """Assert that result is a 5-class probability dict summing to ~1.0.

    Raises AssertionError with a descriptive message on any violation.
    """
    assert isinstance(result, dict), f"{model_name}: output is not a dict (got {type(result)})"
    for label in _LABELS:
        assert label in result, f"{model_name}: missing key '{label}' in output"
        val = result[label]
        assert isinstance(val, float), f"{model_name}: '{label}' value is not float"
        assert 0.0 <= val <= 1.0, f"{model_name}: '{label}' = {val} outside [0,1]"
    total = sum(result[k] for k in _LABELS)
    assert abs(total - 1.0) < 1e-4, f"{model_name}: probabilities sum to {total:.6f}, expected ~1.0"


def validate_tier1(model_dir: Path) -> dict:
    """Load tier1_xgb.json and run _tier1_predict on a synthetic CandidateFeatures.

    Returns a result dict with keys: passed (bool), message (str),
    output (dict|None), skipped (bool).
    """
    model_path = model_dir / "tier1_xgb.json"

    # Skip gracefully when the file is not committed yet
    if not model_path.exists():
        return {
            "passed": True,
            "skipped": True,
            "message": f"SKIP tier1_xgb.json not found at {model_path}",
            "output": None,
        }

    try:
        from classify import _load_xgb_model, _tier1_predict  # type: ignore[import]

        model = _load_xgb_model()
        assert model is not None, "tier1: _load_xgb_model() returned None despite file existing"

        features = _make_synthetic_features()
        result = _tier1_predict(features, model=model)

        _assert_five_class_proba(result, "tier1")

        return {
            "passed": True,
            "skipped": False,
            "message": "PASS tier1_xgb.json loaded and produced valid 5-class output",
            "output": result,
        }
    except Exception as exc:
        return {
            "passed": False,
            "skipped": False,
            "message": f"FAIL tier1_xgb.json: {exc}",
            "output": None,
        }


def validate_tier2(model_dir: Path) -> dict:
    """Load tier2_cnn.pt and run _tier2_predict on a synthetic Tracklet with image cutouts.

    Returns a result dict with keys: passed (bool), message (str),
    output (dict|None), skipped (bool).
    """
    model_path = model_dir / "tier2_cnn.pt"

    # Skip gracefully when the file is not committed yet
    if not model_path.exists():
        return {
            "passed": True,
            "skipped": True,
            "message": f"SKIP tier2_cnn.pt not found at {model_path}",
            "output": None,
        }

    try:
        from classify import _load_cnn_model, _tier2_predict  # type: ignore[import]

        # Build a tracklet with synthetic cutouts so the CNN branch is taken
        tracklet = _make_synthetic_tracklet(with_cutouts=True)

        model = _load_cnn_model()
        assert model is not None, "tier2: _load_cnn_model() returned None despite file existing"

        result = _tier2_predict(tracklet, model=model)

        # _tier2_predict may return None if cutout decoding fails; treat as failure
        assert result is not None, "tier2: _tier2_predict returned None (cutouts not decoded?)"
        _assert_five_class_proba(result, "tier2")

        return {
            "passed": True,
            "skipped": False,
            "message": "PASS tier2_cnn.pt loaded and produced valid 5-class output",
            "output": result,
        }
    except Exception as exc:
        return {
            "passed": False,
            "skipped": False,
            "message": f"FAIL tier2_cnn.pt: {exc}",
            "output": None,
        }


def validate_stacker(model_dir: Path) -> dict:
    """Load stacker_coef.json and run ensemble_predict on synthetic tier1/tier2 dicts.

    ensemble_predict returns a plain dict; we reconstruct a NEOPosterior from it
    to verify all five fields are present and in [0, 1].

    Returns a result dict with keys: passed (bool), message (str),
    output (dict|None), skipped (bool).
    """
    model_path = model_dir / "stacker_coef.json"

    # Skip gracefully when the file is not committed yet
    if not model_path.exists():
        return {
            "passed": True,
            "skipped": True,
            "message": f"SKIP stacker_coef.json not found at {model_path}",
            "output": None,
        }

    try:
        from classify import _load_ensemble_stacker, ensemble_predict  # type: ignore[import]
        from schemas import NEOPosterior  # type: ignore[import]

        meta_model = _load_ensemble_stacker(model_path)
        assert meta_model is not None, (
            "stacker: _load_ensemble_stacker() returned None despite file existing"
        )

        # Build a uniform synthetic tier1 dict to feed ensemble_predict
        tier1 = {lbl: 1.0 / len(_LABELS) for lbl in _LABELS}

        # Call ensemble_predict; it returns a plain dict[str, float]
        result = ensemble_predict(tier1, meta_model=meta_model)

        assert isinstance(result, dict), (
            f"stacker: ensemble_predict returned {type(result)}, expected dict"
        )

        # Verify all five fields are present and in [0, 1]
        for label in _LABELS:
            assert label in result, f"stacker: missing key '{label}'"
            val = result[label]
            assert 0.0 <= float(val) <= 1.0, f"stacker: '{label}' = {val} outside [0,1]"

        total = sum(float(result[k]) for k in _LABELS)
        assert abs(total - 1.0) < 1e-4, f"stacker: probabilities sum to {total:.6f}, expected ~1.0"

        # Reconstruct NEOPosterior to confirm the schema is satisfied
        posterior = NEOPosterior(
            neo_candidate=float(result["neo_candidate"]),
            known_object=float(result["known_object"]),
            main_belt_asteroid=float(result["main_belt_asteroid"]),
            stellar_artifact=float(result["stellar_artifact"]),
            other_solar_system=float(result["other_solar_system"]),
        )
        # Verify all posterior fields are in [0, 1]
        for label in _LABELS:
            val = float(getattr(posterior, label))
            assert 0.0 <= val <= 1.0, f"stacker: NEOPosterior.{label} = {val} outside [0,1]"

        return {
            "passed": True,
            "skipped": False,
            "message": (
                "PASS stacker_coef.json loaded and ensemble_predict"
                " produced valid NEOPosterior"
            ),
            "output": result,
        }
    except Exception as exc:
        return {
            "passed": False,
            "skipped": False,
            "message": f"FAIL stacker_coef.json: {exc}",
            "output": None,
        }


def validate_tier3(model_dir: Path) -> dict:
    """Load tier3_transformer.pt and run _tier3_predict on a synthetic Tracklet.

    Returns a result dict with keys: passed (bool), message (str),
    output (dict|None), skipped (bool).
    """
    model_path = model_dir / "tier3_transformer.pt"

    # Skip gracefully when the file is not committed yet
    if not model_path.exists():
        return {
            "passed": True,
            "skipped": True,
            "message": f"SKIP tier3_transformer.pt not found at {model_path}",
            "output": None,
        }

    try:
        from classify import _load_transformer_model, _tier3_predict  # type: ignore[import]

        # Cutouts are not needed for the Transformer; tabular sequence is enough
        tracklet = _make_synthetic_tracklet(with_cutouts=False)

        model = _load_transformer_model()
        assert model is not None, (
            "tier3: _load_transformer_model() returned None despite file existing"
        )

        result = _tier3_predict(tracklet, model=model)

        assert result is not None, "tier3: _tier3_predict returned None"
        _assert_five_class_proba(result, "tier3")

        return {
            "passed": True,
            "skipped": False,
            "message": "PASS tier3_transformer.pt loaded and produced valid 5-class output",
            "output": result,
        }
    except Exception as exc:
        return {
            "passed": False,
            "skipped": False,
            "message": f"FAIL tier3_transformer.pt: {exc}",
            "output": None,
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all model weight validations and report results.

    Returns 0 if all present models pass, 1 if any fail.
    Missing model files are warned about but do not cause failure.
    """
    parser = argparse.ArgumentParser(
        description="Validate committed model weights (T2-D gate).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a structured JSON result dict to stdout instead of plain text.",
    )
    parser.add_argument(
        "--model-dir",
        default=str(_REPO_ROOT / "models"),
        help="Directory containing model weight files (default: <repo_root>/models).",
    )
    args = parser.parse_args()

    model_dir = Path(args.model_dir)

    # Constrain torch thread pool immediately if torch is about to be loaded.
    # OMP/MKL env vars above handle OpenMP; torch.set_num_threads handles ATen.
    try:
        import torch
        torch.set_num_threads(1)
    except ImportError:
        pass  # torch not installed; CNN/T3 paths will skip gracefully

    # Run validations in pipeline order: tier1 → tier2 → stacker → tier3
    results: dict[str, dict] = {
        "tier1": validate_tier1(model_dir),
        "tier2": validate_tier2(model_dir),
        "stacker": validate_stacker(model_dir),
        "tier3": validate_tier3(model_dir),
    }

    # Determine overall pass/fail (skipped models count as passing)
    all_passed = all(r["passed"] for r in results.values())

    if args.json:
        # Emit structured JSON result for CI parsing
        summary = {
            "all_passed": all_passed,
            "models": {
                name: {
                    "passed": r["passed"],
                    "skipped": r["skipped"],
                    "message": r["message"],
                }
                for name, r in results.items()
            },
        }
        print(json.dumps(summary, indent=2), flush=True)
    else:
        # Human-readable one-line-per-model output
        for name, r in results.items():
            print(r["message"], flush=True)
        status = "ALL PASSED" if all_passed else "SOME FAILED"
        print(f"\n{status}", flush=True)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
