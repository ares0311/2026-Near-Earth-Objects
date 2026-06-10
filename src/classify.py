"""Classify stage — three-tier ML pipeline: XGBoost, CNN, Transformer + ensemble."""

from __future__ import annotations

__all__ = [
    "extract_features",
    "classify",
    "classify_batch",
    "explain_classification",
    "batch_explain",
    "get_tier1_feature_importances",
    "ensemble_predict",
    "_build_ensemble",
    "retrain_tier1",
    "retrain_stacker",
    "posterior_entropy",
    "dominant_hypothesis",
    "classify_morphology",
    "batch_morphology",
    "summarize_classifications",
    "calibrate_posterior", "compute_classification_table",
    "get_posterior_vector",
    "compute_neo_probability",
    "compute_artifact_probability",
    "compute_artifact_features_summary",
    "compute_confusion_matrix",
    "compute_calibration_gain",
    "batch_classify_morphology",
    "compute_class_entropy_stats",
    "compute_tier1_score_distribution",
    "compute_class_entropy_summary",
    "compute_neo_class_distribution",
    "compute_tier1_feature_vector",
    "batch_dominant_hypothesis",
    "filter_by_neo_probability",
    "count_by_dominant_hypothesis",
    "compute_mean_neo_probability",
    "compute_posterior_update",
    "compute_tier1_confidence",
    "compute_posterior_stability",
    "compute_class_probability_range",
    "compute_ensemble_agreement",
    "compute_real_bogus_histogram",
    "compute_neo_class_prior",
    "compute_main_belt_probability",
    "compute_comet_probability",
    "compute_known_object_probability",
    "compute_stellar_artifact_score_from_features",
    "compute_posterior_from_scores",
    "compute_classification_confidence",
    "compute_entropy_weighted_score",
    "compute_tier1_neo_score",
    "compute_class_balance",
    "compute_real_bogus_summary",
    "compute_class_agreement",
    "compute_neo_class_distribution",
    "compute_composite_neo_score",
    "get_highest_confidence_neo",
    "compute_classification_entropy_summary",
]

import base64
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from schemas import (
    CandidateFeatures,
    NEOPosterior,
    OptScore,
    Tracklet,
)

_MODEL_DIR = Path("models")
_MODEL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Feature extraction (shared by all tiers)
# ---------------------------------------------------------------------------


def _nights_observed(tracklet: Tracklet) -> int:
    return len({int(o.jd) for o in tracklet.observations})


def _mean_real_bogus(tracklet: Tracklet) -> OptScore:
    scores = [
        o.deep_real_bogus if o.deep_real_bogus is not None else o.real_bogus
        for o in tracklet.observations
        if (o.deep_real_bogus is not None or o.real_bogus is not None)
    ]
    if not scores:
        return None
    return float(np.mean(scores))


def _color_index(tracklet: Tracklet) -> OptScore:
    """Compute g-r color index if both bands present, else None."""
    g_mags = [o.mag for o in tracklet.observations if o.filter_band == "g"]
    r_mags = [o.mag for o in tracklet.observations if o.filter_band == "r"]
    if g_mags and r_mags:
        gr = float(np.mean(g_mags)) - float(np.mean(r_mags))
        # Normalize: typical NEO g-r ~ 0.4–0.7; clip and rescale to [0,1]
        return float(min(1.0, max(0.0, (gr + 0.5) / 2.0)))
    return None


def _lightcurve_variability(tracklet: Tracklet) -> OptScore:
    mags = [o.mag for o in tracklet.observations]
    if len(mags) < 3:
        return None
    std = float(np.std(mags))
    return float(min(1.0, std / 0.5))


def _arc_coverage(tracklet: Tracklet) -> OptScore:
    """Arc length normalized to [0,1]; 30 days → 1."""
    return float(min(1.0, tracklet.arc_days / 30.0))


def _nights_score(tracklet: Tracklet) -> OptScore:
    n = _nights_observed(tracklet)
    return float(min(1.0, (n - 1) / 6.0))


def _motion_consistency(tracklet: Tracklet) -> OptScore:
    """Score motion consistency: 1 = perfectly linear, 0 = highly scattered."""
    if len(tracklet.observations) < 3:
        return None
    obs = sorted(tracklet.observations, key=lambda o: o.jd)
    t0 = obs[0].jd
    cos_dec = math.cos(math.radians(np.mean([o.dec_deg for o in obs])))
    ts = np.array([(o.jd - t0) * 24.0 for o in obs])
    ras = np.array([o.ra_deg * 3600.0 * cos_dec for o in obs])
    decs = np.array([o.dec_deg * 3600.0 for o in obs])
    # Linear fit residuals
    coeffs_ra = np.polyfit(ts, ras, 1)
    coeffs_dec = np.polyfit(ts, decs, 1)
    res = np.sqrt(
        (ras - np.polyval(coeffs_ra, ts)) ** 2 + (decs - np.polyval(coeffs_dec, ts)) ** 2
    )
    rms = float(np.sqrt(np.mean(res**2)))
    return float(max(0.0, 1.0 - rms / 30.0))  # 30 arcsec scatter → 0


def _brightness_score(tracklet: Tracklet) -> OptScore:
    mags = [o.mag for o in tracklet.observations if o.mag < 99]
    if not mags:
        return None
    mean_mag = float(np.mean(mags))
    # Brighter (lower mag) → higher score; scale around mag 20
    return float(min(1.0, max(0.0, (25.0 - mean_mag) / 10.0)))


def extract_features(tracklet: Tracklet) -> CandidateFeatures:
    """Extract all tabular features from a tracklet."""
    return CandidateFeatures(
        real_bogus_score=_mean_real_bogus(tracklet),
        streak_score=None,  # populated by detect stage if applicable
        psf_quality_score=None,
        motion_consistency_score=_motion_consistency(tracklet),
        arc_coverage_score=_arc_coverage(tracklet),
        nights_observed_score=_nights_score(tracklet),
        brightness_score=_brightness_score(tracklet),
        color_score=_color_index(tracklet),
        lightcurve_variability_score=_lightcurve_variability(tracklet),
        orbit_quality_score=None,  # set after orbit.py
        moid_score=None,
        neo_class_confidence=None,
        pha_flag_confidence=None,
        known_object_score=None,
    )


# ---------------------------------------------------------------------------
# Tier 1 — XGBoost on tabular features
# ---------------------------------------------------------------------------


def _features_to_array(features: CandidateFeatures) -> np.ndarray:
    vals = [
        features.real_bogus_score,
        features.motion_consistency_score,
        features.arc_coverage_score,
        features.nights_observed_score,
        features.brightness_score,
        features.color_score,
        features.lightcurve_variability_score,
        features.streak_score,
        features.psf_quality_score,
        features.known_object_score,
    ]
    return np.array([v if v is not None else 0.0 for v in vals], dtype=np.float32)


def _load_xgb_model() -> Any:
    model_path = _MODEL_DIR / "tier1_xgb.json"
    if not model_path.exists():
        return None
    try:
        import xgboost as xgb  # type: ignore[import]

        clf = xgb.XGBClassifier()
        clf.load_model(str(model_path))
        return clf
    except Exception:
        return None


def _tier1_predict(
    features: CandidateFeatures,
    model: Any = None,
) -> dict[str, OptScore]:
    """Return Tier 1 class probabilities."""
    if model is None:
        model = _load_xgb_model()

    if model is not None:
        x = _features_to_array(features).reshape(1, -1)
        proba = model.predict_proba(x)[0]
        # Assume classes: [neo_candidate, known_object, main_belt, artifact, other]
        labels = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        return {k: float(v) for k, v in zip(labels, proba)}

    # Heuristic fallback when no model is trained yet
    rb = features.real_bogus_score or 0.5
    motion = features.motion_consistency_score or 0.5
    neo_score = rb * 0.5 + motion * 0.3 + (features.nights_observed_score or 0.0) * 0.2
    neo_score = float(min(1.0, neo_score))
    artifact = float(max(0.0, 1.0 - rb))
    known = float(features.known_object_score or 0.1)
    residual = max(0.0, 1.0 - neo_score - artifact - known)
    mba = residual * 0.7
    other = residual * 0.3
    total = neo_score + known + mba + artifact + other
    if total > 0:
        neo_score /= total
        known /= total
        mba /= total
        artifact /= total
        other /= total
    return {
        "neo_candidate": neo_score,
        "known_object": known,
        "main_belt_asteroid": mba,
        "stellar_artifact": artifact,
        "other_solar_system": other,
    }


# ---------------------------------------------------------------------------
# Tier 2 — CNN on image triplets
# ---------------------------------------------------------------------------


def _decode_cutout_f32(b64: str, size: int = 63) -> np.ndarray | None:
    try:
        raw = base64.b64decode(b64)
        arr = np.frombuffer(raw, dtype=np.float32)
        if arr.size != size * size:
            return None
        return arr.reshape(size, size)
    except Exception:
        return None


def _build_cnn_model() -> Any:
    """Build the Duev et al. (2019)-style three-branch CNN."""
    try:
        import torch
        import torch.nn as nn

        class ConvBranch(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.net = nn.Sequential(
                    nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(),
                    nn.MaxPool2d(2),
                    nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(),
                    nn.AdaptiveAvgPool2d(4),
                    nn.Flatten(),
                )

            def forward(self, x: Any) -> Any:
                return self.net(x)

        class TripleCNN(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.branch_sci = ConvBranch()
                self.branch_ref = ConvBranch()
                self.branch_diff = ConvBranch()
                self.head = nn.Sequential(
                    nn.Linear(128 * 3 * 16, 256), nn.ReLU(),
                    nn.Dropout(0.3),
                    nn.Linear(256, 5),  # 5 classes
                    nn.Softmax(dim=1),
                )

            def forward(self, sci: Any, ref: Any, diff: Any) -> Any:
                f = torch.cat(
                    [self.branch_sci(sci), self.branch_ref(ref), self.branch_diff(diff)], dim=1
                )
                return self.head(f)

        return TripleCNN()
    except ImportError:  # pragma: no cover
        return None


def _load_cnn_model() -> Any:
    model_path = _MODEL_DIR / "tier2_cnn.pt"
    if not model_path.exists():
        return None
    try:
        import torch

        model = _build_cnn_model()
        if model is None:
            return None
        model.load_state_dict(torch.load(str(model_path), map_location="cpu"))
        model.eval()
        return model
    except Exception:
        return None


def _tier2_predict(
    tracklet: Tracklet,
    model: Any = None,
) -> dict[str, OptScore] | None:
    """Return Tier 2 CNN probabilities, or None if cutouts unavailable."""
    # Collect first observation with all three cutouts before loading Torch/CNN.
    # This keeps summary/CLI paths lightweight when fixtures have no image triplets.
    triplet = None
    for obs in tracklet.observations:
        if obs.cutout_science and obs.cutout_reference and obs.cutout_difference:
            sci = _decode_cutout_f32(obs.cutout_science)
            ref = _decode_cutout_f32(obs.cutout_reference)
            diff = _decode_cutout_f32(obs.cutout_difference)
            if sci is not None and ref is not None and diff is not None:
                triplet = (sci, ref, diff)
                break

    if triplet is None:
        return None

    if model is None:
        model = _load_cnn_model()
    if model is None:
        return None

    try:
        import torch

        def to_tensor(arr: np.ndarray) -> Any:
            return torch.from_numpy(arr).unsqueeze(0).unsqueeze(0)  # (1,1,63,63)

        with torch.no_grad():
            proba = model(to_tensor(triplet[0]), to_tensor(triplet[1]), to_tensor(triplet[2]))
            proba_np = proba.squeeze().numpy()

        labels = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        return {k: float(v) for k, v in zip(labels, proba_np)}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tier 3 — Transformer on tracklet sequences
# ---------------------------------------------------------------------------


def _build_transformer_model() -> Any:
    """Build BERT-style encoder for tracklet sequence classification."""
    try:
        import math as _math

        import torch
        import torch.nn as nn

        class PositionalEncoding(nn.Module):
            def __init__(self, d_model: int, max_len: int = 512) -> None:
                super().__init__()
                pe = torch.zeros(max_len, d_model)
                position = torch.arange(0, max_len).unsqueeze(1).float()
                div_term = torch.exp(
                    torch.arange(0, d_model, 2).float() * (-_math.log(10000.0) / d_model)
                )
                pe[:, 0::2] = torch.sin(position * div_term)
                pe[:, 1::2] = torch.cos(position * div_term)
                self.register_buffer("pe", pe.unsqueeze(0))

            def forward(self, x: Any) -> Any:
                return x + self.pe[:, : x.size(1)]  # type: ignore[index]

        class TrackletTransformer(nn.Module):
            def __init__(
                self,
                input_dim: int = 5,  # RA, Dec, mag, time, filter_id
                d_model: int = 128,
                nhead: int = 4,
                num_layers: int = 3,
                num_classes: int = 5,
            ) -> None:
                super().__init__()
                self.input_proj = nn.Linear(input_dim, d_model)
                self.pos_enc = PositionalEncoding(d_model)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=nhead, batch_first=True
                )
                self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
                self.cls_token = nn.Parameter(torch.randn(1, 1, d_model))
                self.head = nn.Sequential(
                    nn.Linear(d_model, 64),
                    nn.ReLU(),
                    nn.Linear(64, num_classes),
                )

            def forward(self, x: Any) -> Any:
                b = x.size(0)
                cls = self.cls_token.expand(b, -1, -1)
                x = torch.cat([cls, self.input_proj(x)], dim=1)
                x = self.pos_enc(x)
                x = self.encoder(x)
                return self.head(x[:, 0])

        return TrackletTransformer()
    except ImportError:  # pragma: no cover
        return None


def _tracklet_to_sequence(tracklet: Tracklet) -> np.ndarray | None:
    """Convert tracklet observations to a (T, 5) feature matrix."""
    _filter_map = {"g": 0, "r": 1, "i": 2, "o": 3, "c": 4, "V": 5}
    obs_sorted = sorted(tracklet.observations, key=lambda o: o.jd)
    if len(obs_sorted) < 2:
        return None
    t0 = obs_sorted[0].jd
    rows = []
    for obs in obs_sorted:
        rows.append([
            obs.ra_deg / 360.0,
            (obs.dec_deg + 90.0) / 180.0,
            obs.mag / 30.0,
            (obs.jd - t0) / 30.0,
            _filter_map.get(obs.filter_band, 0) / 5.0,
        ])
    return np.array(rows, dtype=np.float32)


def _load_transformer_model() -> Any:
    model_path = _MODEL_DIR / "tier3_transformer.pt"
    if not model_path.exists():
        return None
    try:
        import torch

        model = _build_transformer_model()
        if model is None:
            return None
        model.load_state_dict(torch.load(str(model_path), map_location="cpu"))
        model.eval()
        return model
    except Exception:
        return None


def _tier3_predict(
    tracklet: Tracklet,
    model: Any = None,
) -> dict[str, OptScore] | None:
    if model is None:
        model = _load_transformer_model()
    if model is None:
        return None

    seq = _tracklet_to_sequence(tracklet)
    if seq is None:
        return None

    try:
        import torch

        x = torch.from_numpy(seq).unsqueeze(0)  # (1, T, 5)
        with torch.no_grad():
            proba = torch.softmax(model(x), dim=1).squeeze().numpy()

        labels = [
            "neo_candidate", "known_object", "main_belt_asteroid",
            "stellar_artifact", "other_solar_system",
        ]
        return {k: float(v) for k, v in zip(labels, proba)}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stacking ensemble — logistic regression meta-learner
# ---------------------------------------------------------------------------

_LABELS = [
    "neo_candidate", "known_object", "main_belt_asteroid",
    "stellar_artifact", "other_solar_system",
]


def _build_ensemble(tier1_outputs: list[dict[str, float]], labels: list[dict[str, float]]) -> Any:
    """Train a logistic regression meta-learner on stacked tier outputs.

    tier1_outputs: list of tier1 probability dicts (one per training example)
    labels: list of one-hot or integer label dicts with key 'label' (int 0-4)

    Returns a fitted sklearn LogisticRegression, or None on failure.
    """
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression  # type: ignore[import]

        X = np.array([[d[lbl] for lbl in _LABELS] for d in tier1_outputs], dtype=np.float32)
        y = np.array([int(d["label"]) for d in labels], dtype=np.int32)
        if len(np.unique(y)) < 2:
            return None
        clf = LogisticRegression(max_iter=500, solver="lbfgs")
        clf.fit(X, y)
        return clf
    except Exception:
        return None


def ensemble_predict(
    tier1: dict[str, float],
    tier2: dict[str, float] | None = None,
    tier3: dict[str, float] | None = None,
    meta_model: Any = None,
) -> dict[str, float]:
    """Produce final ensemble probabilities.

    If meta_model is provided, it is used to re-weight tier1 outputs (logistic
    regression meta-learner). Falls back to weighted average when no meta_model.
    """
    if meta_model is not None:
        try:
            import numpy as np

            x = np.array([[tier1[lbl] for lbl in _LABELS]], dtype=np.float32)
            proba = meta_model.predict_proba(x)[0]
            meta_out = {lbl: float(p) for lbl, p in zip(_LABELS, proba)}
            return _stack_predictions(meta_out, tier2, tier3)
        except Exception:
            pass
    return _stack_predictions(tier1, tier2, tier3)


def _stack_predictions(
    t1: dict[str, OptScore],
    t2: dict[str, OptScore] | None,
    t3: dict[str, OptScore] | None,
) -> dict[str, float]:
    """Simple weighted average ensemble; weights reflect tier reliability."""
    labels = [
        "neo_candidate", "known_object", "main_belt_asteroid",
        "stellar_artifact", "other_solar_system",
    ]
    weights: list[float] = []
    preds: list[dict[str, OptScore]] = []

    weights.append(1.0)
    preds.append(t1)
    if t2 is not None:
        weights.append(1.5)
        preds.append(t2)
    if t3 is not None:
        weights.append(2.0)
        preds.append(t3)

    total_w = sum(weights)
    result: dict[str, float] = {}
    for label in labels:
        val = sum(
            w * (p.get(label) or 0.0) for w, p in zip(weights, preds)
        ) / total_w
        result[label] = float(val)

    # Renormalize
    s = sum(result.values())
    if s > 0:
        result = {k: v / s for k, v in result.items()}
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def retrain_tier1(
    csv_path: Path | str,
    model_path: Path | str | None = None,
) -> dict[str, Any]:
    """Retrain the Tier 1 XGBoost classifier from a labelled CSV file.

    The CSV must contain columns matching the 10 feature names in
    ``_features_to_array`` plus a ``label`` column (integer 0–4 mapping
    to the five hypotheses).

    Returns a training report dict with keys ``n_samples``, ``n_classes``,
    ``auc``, ``model_path``.  The trained model is saved as JSON to
    ``model_path`` (defaults to ``models/tier1_xgb.json``).
    """
    import csv

    import numpy as np

    feature_cols = [
        "real_bogus_score", "motion_consistency_score", "arc_coverage_score",
        "nights_observed_score", "brightness_score", "color_score",
        "lightcurve_variability_score", "streak_score", "psf_quality_score",
        "known_object_score",
    ]

    rows: list[list[float]] = []
    labels_list: list[int] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vals = [float(row.get(c) or 0.0) for c in feature_cols]
            rows.append(vals)
            labels_list.append(int(row["label"]))

    X = np.array(rows, dtype=np.float32)
    y = np.array(labels_list, dtype=np.int32)
    n_samples = len(y)
    n_classes = len(set(y))

    try:
        import xgboost as xgb  # type: ignore[import]
        from sklearn.metrics import roc_auc_score  # type: ignore[import]
        from sklearn.preprocessing import label_binarize  # type: ignore[import]

        clf = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            use_label_encoder=False,
            eval_metric="mlogloss",
        )
        clf.fit(X, y)

        proba = clf.predict_proba(X)
        classes = sorted(set(y))
        auc: float | None
        if n_classes == 2:
            auc = float(roc_auc_score(y, proba[:, 1]))
        elif n_classes > 2:
            y_bin = label_binarize(y, classes=classes)
            auc = float(roc_auc_score(y_bin, proba, multi_class="ovr", average="macro"))
        else:
            auc = None  # pragma: no cover — n_classes < 2 only for single-class datasets

        out_path = Path(model_path) if model_path else _MODEL_DIR / "tier1_xgb.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        clf.save_model(str(out_path))

        return {
            "n_samples": n_samples,
            "n_classes": n_classes,
            "auc": auc,
            "model_path": str(out_path),
        }
    except ImportError as exc:
        return {
            "n_samples": n_samples,
            "n_classes": n_classes,
            "auc": None,
            "model_path": None,
            "error": f"xgboost/sklearn not available: {exc}",
        }


def retrain_stacker(
    tier1_outputs: list[dict[str, float]],
    labels: list[dict[str, float]],
    model_path: Path | str | None = None,
) -> dict[str, Any]:
    """Retrain the stacking meta-learner from tier-1 probability outputs.

    ``tier1_outputs`` is a list of probability dicts (one per training example).
    ``labels`` is a list of dicts each with key ``"label"`` (int 0–4).

    Serialises the fitted coefficients to a JSON sidecar at ``model_path``
    (defaults to ``models/stacker_coef.json``).

    Returns a training report with keys ``n_samples``, ``n_classes``,
    ``auc``, ``model_path``, ``coef_path``.
    """
    model = _build_ensemble(tier1_outputs, labels)
    n_samples = len(labels)
    n_classes = len({int(d["label"]) for d in labels})

    out_path = Path(model_path) if model_path else _MODEL_DIR / "stacker_coef.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    auc: float | None = None
    coef_path: str | None = None

    if model is not None:
        try:
            import numpy as np
            from sklearn.metrics import roc_auc_score  # type: ignore[import]
            from sklearn.preprocessing import label_binarize  # type: ignore[import]

            X = np.array([[d[lbl] for lbl in _LABELS] for d in tier1_outputs], dtype=np.float32)
            y = np.array([int(d["label"]) for d in labels], dtype=np.int32)
            proba = model.predict_proba(X)
            classes = sorted(set(y))
            if n_classes == 2:
                auc = float(roc_auc_score(y, proba[:, 1]))
            elif n_classes > 2:
                y_bin = label_binarize(y, classes=classes)
                auc = float(roc_auc_score(y_bin, proba, multi_class="ovr", average="macro"))

            coef_data = {
                "classes": model.classes_.tolist(),
                "coef": model.coef_.tolist(),
                "intercept": model.intercept_.tolist(),
                "labels": _LABELS,
            }
            with out_path.open("w") as f:
                json.dump(coef_data, f, indent=2)
            coef_path = str(out_path)
        except Exception:
            pass

    return {
        "n_samples": n_samples,
        "n_classes": n_classes,
        "auc": auc,
        "model_path": coef_path,
        "coef_path": coef_path,
    }


def classify(
    tracklet: Tracklet,
    features: CandidateFeatures | None = None,
    xgb_model: Any = None,
    cnn_model: Any = None,
    transformer_model: Any = None,
) -> tuple[CandidateFeatures, NEOPosterior]:
    """Run the three-tier classification pipeline on a single tracklet.

    Returns updated CandidateFeatures (with tier scores) and NEOPosterior.
    """
    if features is None:
        features = extract_features(tracklet)

    # Tier 1
    t1 = _tier1_predict(features, xgb_model)

    # Tier 2 (CNN)
    t2 = _tier2_predict(tracklet, cnn_model)

    # Tier 3 (Transformer)
    t3 = _tier3_predict(tracklet, transformer_model)

    # Ensemble
    ensemble = _stack_predictions(t1, t2, t3)

    posterior = NEOPosterior(
        neo_candidate=ensemble["neo_candidate"],
        known_object=ensemble["known_object"],
        main_belt_asteroid=ensemble["main_belt_asteroid"],
        stellar_artifact=ensemble["stellar_artifact"],
        other_solar_system=ensemble["other_solar_system"],
    )

    updated_features = features.model_copy(
        update={
            "real_bogus_score": features.real_bogus_score or _mean_real_bogus(tracklet),
            "stellar_artifact_score": ensemble["stellar_artifact"],
            "main_belt_consistency_score": ensemble["main_belt_asteroid"],
        }
    )

    return updated_features, posterior


def classify_batch(
    tracklets: list[Tracklet],
    xgb_model: Any = None,
    cnn_model: Any = None,
    transformer_model: Any = None,
) -> list[tuple[CandidateFeatures, NEOPosterior]]:
    """Run the three-tier classification pipeline on a list of tracklets.

    Loads each model at most once, then applies it to every tracklet.
    Returns a list of (CandidateFeatures, NEOPosterior) in the same order
    as the input list.
    """
    loaded_xgb = xgb_model if xgb_model is not None else _load_xgb_model()
    loaded_cnn = cnn_model if cnn_model is not None else _load_cnn_model()
    loaded_t3 = transformer_model if transformer_model is not None else _load_transformer_model()
    return [
        classify(t, xgb_model=loaded_xgb, cnn_model=loaded_cnn, transformer_model=loaded_t3)
        for t in tracklets
    ]


def get_tier1_feature_importances(model_path: Path | str | None = None) -> dict[str, float] | None:
    """Return feature importances from the saved Tier 1 XGBoost model.

    Returns a dict mapping feature name → importance (gain-based), or None
    if the model file does not exist or cannot be loaded.
    """
    path = Path(model_path) if model_path else _MODEL_DIR / "tier1_xgb.json"
    if not path.exists():
        return None
    try:
        import xgboost as xgb  # type: ignore[import]

        clf = xgb.XGBClassifier()
        clf.load_model(str(path))
        scores = clf.get_booster().get_fscore()
        feature_names = [
            "real_bogus_score", "motion_consistency_score", "arc_coverage_score",
            "nights_observed_score", "brightness_score", "color_score",
            "lightcurve_variability_score", "streak_score", "psf_quality_score",
            "known_object_score",
        ]
        # Map f0, f1, … back to feature names; fill missing with 0.0
        named: dict[str, float] = {name: 0.0 for name in feature_names}
        for fkey, imp in scores.items():
            idx = int(fkey.lstrip("f"))
            if idx < len(feature_names):
                val = imp[0] if isinstance(imp, list) else imp
                named[feature_names[idx]] = float(val)
        total = sum(named.values()) or 1.0
        return {k: v / total for k, v in named.items()}
    except Exception:
        return None


def explain_classification(tracklet: Tracklet) -> dict:
    """Return a structured breakdown of the classification for a tracklet.

    Runs the full three-tier classifier and returns:
      ``features``            — dict of feature name → score
      ``posterior``           — dict of hypothesis → probability
      ``tier1_importances``   — normalised XGBoost gain importances (or ``None``)
      ``dominant_hypothesis`` — name of the highest-probability hypothesis
      ``confidence``          — probability of the dominant hypothesis
    """
    features, posterior = classify(tracklet)
    feat_dict = {k: getattr(features, k) for k in type(features).model_fields}
    post_dict = {
        "neo_candidate": round(posterior.neo_candidate, 4),
        "known_object": round(posterior.known_object, 4),
        "main_belt_asteroid": round(posterior.main_belt_asteroid, 4),
        "stellar_artifact": round(posterior.stellar_artifact, 4),
        "other_solar_system": round(posterior.other_solar_system, 4),
    }
    dominant = max(post_dict, key=lambda k: post_dict[k])
    importances = get_tier1_feature_importances(Path("models/tier1_xgb.json"))
    return {
        "features": feat_dict,
        "posterior": post_dict,
        "tier1_importances": importances,
        "dominant_hypothesis": dominant,
        "confidence": post_dict[dominant],
    }


def batch_explain(tracklets: list[Tracklet]) -> list[dict]:
    """Run :func:`explain_classification` on a list of tracklets.

    Returns one explanation dict per tracklet in input order.
    Each dict has keys ``features``, ``posterior``, ``tier1_importances``,
    ``dominant_hypothesis``, and ``confidence``.
    """
    return [explain_classification(t) for t in tracklets]


def posterior_entropy(posterior: NEOPosterior) -> float:  # type: ignore[name-defined]
    """Compute Shannon entropy of the classification posterior in bits.

    H = -sum(p * log2(p)) over the five hypotheses.
    Range: [0, log2(5)] ≈ [0, 2.322].  High entropy means high uncertainty.
    Zero entropy means one hypothesis has probability 1.
    """
    probs = [
        posterior.neo_candidate,
        posterior.known_object,
        posterior.main_belt_asteroid,
        posterior.stellar_artifact,
        posterior.other_solar_system,
    ]
    h = 0.0
    for p in probs:
        if p > 0.0:
            h -= p * math.log2(p)
    return h


def dominant_hypothesis(posterior: NEOPosterior) -> tuple[str, float]:
    """Return the hypothesis name and probability for the highest-probability class.

    Returns a tuple ``(name, probability)`` where *name* is one of
    ``"neo_candidate"``, ``"known_object"``, ``"main_belt_asteroid"``,
    ``"stellar_artifact"``, or ``"other_solar_system"``.

    Returns ``("unknown", 0.0)`` when all probabilities are zero.
    """
    candidates = {
        "neo_candidate": posterior.neo_candidate,
        "known_object": posterior.known_object,
        "main_belt_asteroid": posterior.main_belt_asteroid,
        "stellar_artifact": posterior.stellar_artifact,
        "other_solar_system": posterior.other_solar_system,
    }
    best = max(candidates, key=lambda k: candidates[k])
    prob = candidates[best]
    if prob == 0.0:
        return ("unknown", 0.0)
    return (best, float(prob))


def classify_morphology(obs) -> str:
    """Classify source morphology as 'point_source', 'extended', or 'streak'.

    Uses image second-moment elongation from the difference-image cutout.
    Elongation ≥ 5 → 'streak'; elongation ≥ 1.5 → 'extended'; otherwise
    'point_source'.  Falls back to 'point_source' if no cutout is available.
    """
    if obs.cutout_difference is None:
        return "point_source"
    try:
        import base64
        import math as _math

        import numpy as np

        raw = base64.b64decode(obs.cutout_difference)
        arr = np.frombuffer(raw, dtype=np.float32)
        size = int(_math.isqrt(len(arr)))
        if size * size != len(arr) or size < 3:
            return "point_source"
        arr = arr.reshape(size, size).astype(np.float64)
        arr = np.clip(arr, 0.0, None)
        total = float(arr.sum())
        if total <= 0:
            return "point_source"
        y, x = np.indices(arr.shape)
        cx = float((x * arr).sum()) / total
        cy = float((y * arr).sum()) / total
        dx, dy = x - cx, y - cy
        mxx = float((dx**2 * arr).sum()) / total
        myy = float((dy**2 * arr).sum()) / total
        mxy = float((dx * dy * arr).sum()) / total
        trace = mxx + myy
        if trace <= 0:
            return "point_source"
        det = mxx * myy - mxy**2
        disc = max(0.0, (trace / 2) ** 2 - det)
        lam1 = trace / 2 + _math.sqrt(disc)
        lam2 = trace / 2 - _math.sqrt(disc)
        if lam2 <= 1e-12 * lam1:
            return "streak"
        elongation = lam1 / lam2
        if elongation >= 5.0:
            return "streak"
        if elongation >= 1.5:
            return "extended"
        return "point_source"
    except Exception:
        return "point_source"


def batch_morphology(tracklet: object) -> dict:
    """Classify the morphology of every observation in a tracklet.

    Returns a dict with:
    - ``modal_class``: most common morphology string across all observations
    - ``class_counts``: mapping from morphology label to count
    - ``streak_fraction``: fraction of observations classified as "streak"
    """
    obs_list = list(getattr(tracklet, "observations", []))
    if not obs_list:
        return {"modal_class": "point_source", "class_counts": {}, "streak_fraction": 0.0}

    labels = [classify_morphology(o) for o in obs_list]
    counts: dict[str, int] = {}
    for lbl in labels:
        counts[lbl] = counts.get(lbl, 0) + 1

    modal = max(counts, key=lambda k: counts[k])
    streak_frac = round(counts.get("streak", 0) / len(labels), 4)
    return {"modal_class": modal, "class_counts": counts, "streak_fraction": streak_frac}


def summarize_classifications(neos: list) -> dict:
    """Aggregate classification summary across a list of ScoredNEO objects.

    Returns a dict with:
    - ``total``: number of NEOs
    - ``dominant_hypothesis_counts``: mapping from hypothesis name → count
    - ``mean_entropy_bits``: mean Shannon entropy of posteriors
    - ``mean_real_bogus_score``: mean real_bogus_score (None scores excluded)
    - ``pha_candidate_count``: number with hazard_flag == 'pha_candidate'
    """
    if not neos:
        return {
            "total": 0,
            "dominant_hypothesis_counts": {},
            "mean_entropy_bits": 0.0,
            "mean_real_bogus_score": None,
            "pha_candidate_count": 0,
        }

    hyp_counts: dict[str, int] = {}
    entropies: list[float] = []
    rb_scores: list[float] = []
    pha_count = 0

    for neo in neos:
        name, _ = dominant_hypothesis(neo.posterior)
        hyp_counts[name] = hyp_counts.get(name, 0) + 1
        entropies.append(posterior_entropy(neo.posterior))
        rb = neo.features.real_bogus_score
        if rb is not None:
            rb_scores.append(rb)
        if getattr(neo.hazard, "hazard_flag", None) == "pha_candidate":
            pha_count += 1

    mean_ent = round(float(sum(entropies) / len(entropies)), 6)
    mean_rb = round(float(sum(rb_scores) / len(rb_scores)), 6) if rb_scores else None

    return {
        "total": len(neos),
        "dominant_hypothesis_counts": hyp_counts,
        "mean_entropy_bits": mean_ent,
        "mean_real_bogus_score": mean_rb,
        "pha_candidate_count": pha_count,
    }


def calibrate_posterior(
    posterior: NEOPosterior,
    calibrator: object | None = None,
) -> NEOPosterior:
    """Re-calibrate a NEOPosterior using an optional probability calibrator.

    If ``calibrator`` is None, applies a simple Laplace smoothing step to
    bring very sharp posteriors slightly toward the uniform prior (avoids
    overconfident 0/1 probabilities in downstream alert logic).

    The returned posterior is always normalised to sum to 1.0.

    Args:
        posterior: The raw NEOPosterior to calibrate.
        calibrator: Optional calibrator object with a ``predict_proba`` method.
            When None, soft Laplace smoothing (alpha=0.05) is applied.

    Returns:
        A new NEOPosterior with calibrated, normalised probabilities.
    """
    import numpy as np

    from schemas import NEOPosterior

    raw = np.array([
        posterior.neo_candidate,
        posterior.known_object,
        posterior.main_belt_asteroid,
        posterior.stellar_artifact,
        posterior.other_solar_system,
    ], dtype=float)

    if calibrator is not None and hasattr(calibrator, "predict_proba"):
        try:
            cal = np.asarray(calibrator.predict_proba(raw.reshape(1, -1))[0], dtype=float)
            raw = cal
        except Exception:
            pass

    # Laplace smoothing: alpha / (1 + n_classes * alpha)
    alpha = 0.05
    raw = raw + alpha
    total = raw.sum()
    if total > 0:
        raw = raw / total

    return NEOPosterior(
        neo_candidate=round(float(raw[0]), 6),
        known_object=round(float(raw[1]), 6),
        main_belt_asteroid=round(float(raw[2]), 6),
        stellar_artifact=round(float(raw[3]), 6),
        other_solar_system=round(float(raw[4]), 6),
    )


def compute_classification_table(neos: list) -> list[dict]:
    """Build a per-NEO classification summary table.

    For each scored NEO, returns the object ID, dominant hypothesis name and
    probability, and posterior entropy.  Useful for quick review of a batch
    classification run.

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.

    Returns:
        List of dicts, each with keys:
          - ``"object_id"``: tracklet object identifier.
          - ``"dominant_hypothesis"``: name of the highest-probability class.
          - ``"probability"``: probability of the dominant class (rounded to 4 dp).
          - ``"entropy_bits"``: Shannon entropy of the posterior (rounded to 4 dp).
    """
    rows = []
    for neo in neos:
        hyp, prob = dominant_hypothesis(neo.posterior)
        ent = posterior_entropy(neo.posterior)
        rows.append({
            "object_id": neo.tracklet.object_id,
            "dominant_hypothesis": hyp,
            "probability": round(prob, 4),
            "entropy_bits": round(ent, 4),
        })
    return rows


def get_posterior_vector(posterior: NEOPosterior) -> np.ndarray:
    """Return the posterior probability distribution as a 5-element numpy array.

    The element order is fixed:
    [neo_candidate, known_object, main_belt_asteroid, stellar_artifact, other_solar_system]

    This provides a convenient vector representation for downstream numerical
    processing such as ensemble stacking or distance computations.

    Args:
        posterior: A :class:`~schemas.NEOPosterior` object.

    Returns:
        1-D numpy array of shape ``(5,)`` with probabilities in [0, 1].
    """
    import numpy as np  # already imported at module level but explicit for safety
    return np.array([
        posterior.neo_candidate,
        posterior.known_object,
        posterior.main_belt_asteroid,
        posterior.stellar_artifact,
        posterior.other_solar_system,
    ], dtype=float)


def compute_neo_probability(features: CandidateFeatures) -> float:
    """Compute a scalar NEO probability directly from a CandidateFeatures object.

    Applies the Tier-1 log-score model from the scoring model spec without
    running the full classify pipeline.  Useful for quick screening.

    Args:
        features: A :class:`~schemas.CandidateFeatures` object.

    Returns:
        Scalar probability in [0, 1] that the candidate is a genuine new NEO.
    """
    import math as _math

    log_prior_neo = _math.log(0.05)
    log_prior_other = _math.log(0.95)

    weights = {
        "real_bogus_score": 2.0,
        "arc_coverage_score": 1.5,
        "nights_observed_score": 1.5,
        "motion_consistency_score": 1.2,
        "orbit_quality_score": 1.0,
        "known_object_score": -2.5,
        "stellar_artifact_score": -2.0,
        "main_belt_consistency_score": -1.5,
    }

    log_score = log_prior_neo
    for attr, w in weights.items():
        val = getattr(features, attr, None)
        if val is not None:
            log_score += w * float(val)

    # Two-class softmax: neo vs other
    log_other = log_prior_other
    log_max = max(log_score, log_other)
    exp_neo = _math.exp(log_score - log_max)
    exp_other = _math.exp(log_other - log_max)
    prob = exp_neo / (exp_neo + exp_other)
    return round(float(prob), 6)


def compute_artifact_probability(features: CandidateFeatures) -> float:
    """Compute a scalar artifact (non-astronomical source) probability.

    Applies a log-score model using features indicative of instrumental
    artifacts — the complement framing to :func:`compute_neo_probability`.
    A high score means the candidate is likely an artifact rather than a
    real astronomical source.

    Feature weights used:

    - ``stellar_artifact_score``: +2.5 (strong artifact indicator)
    - ``psf_quality_score``: -2.0 (good PSF → less likely artifact)
    - ``real_bogus_score``: -2.0 (high rb → less likely artifact)
    - ``streak_score``: +1.5 (streaks are often satellites/cosmic rays)
    - ``motion_consistency_score``: -1.0 (consistent motion → less likely artifact)

    Args:
        features: A :class:`~schemas.CandidateFeatures` object.

    Returns:
        Scalar probability in [0, 1] that the candidate is an artifact.
    """
    import math as _math

    log_prior_art = _math.log(0.25)
    log_prior_other = _math.log(0.75)

    weights = {
        "stellar_artifact_score": 2.5,
        "psf_quality_score": -2.0,
        "real_bogus_score": -2.0,
        "streak_score": 1.5,
        "motion_consistency_score": -1.0,
    }

    log_score = log_prior_art
    for attr, w in weights.items():
        val = getattr(features, attr, None)
        if val is not None:
            log_score += w * float(val)

    log_other = log_prior_other
    log_max = max(log_score, log_other)
    exp_art = _math.exp(log_score - log_max)
    exp_other = _math.exp(log_other - log_max)
    prob = exp_art / (exp_art + exp_other)
    return round(float(prob), 6)


def compute_confusion_matrix(
    predicted_labels: list | tuple,
    true_labels: list | tuple,
) -> dict:
    """Compute a confusion matrix from predicted and true string labels.

    Args:
        predicted_labels: Sequence of predicted class label strings.
        true_labels: Sequence of true (ground-truth) class label strings.

    Returns:
        Dict with keys:

        - ``"labels"``: Sorted list of unique labels (union of predicted and
          true).
        - ``"matrix"``: List of lists of counts where rows correspond to true
          labels and columns correspond to predicted labels.
        - ``"accuracy"``: Fraction of correct predictions in [0, 1]; 0.0 for
          empty input.
    """
    pred = list(predicted_labels)
    true = list(true_labels)

    if not pred and not true:
        return {"labels": [], "matrix": [], "accuracy": 0.0}

    all_labels = sorted(set(pred) | set(true))
    label_idx = {lbl: i for i, lbl in enumerate(all_labels)}
    n = len(all_labels)

    matrix = [[0] * n for _ in range(n)]
    correct = 0
    total = min(len(pred), len(true))
    for p, t in zip(pred, true):
        row = label_idx.get(t, 0)
        col = label_idx.get(p, 0)
        matrix[row][col] += 1
        if p == t:
            correct += 1

    accuracy = correct / total if total > 0 else 0.0
    return {"labels": all_labels, "matrix": matrix, "accuracy": round(accuracy, 6)}


def compute_calibration_gain(
    posterior_before: NEOPosterior,
    posterior_after: NEOPosterior,
) -> float:
    """Compute KL divergence from posterior_before to posterior_after.

    Measures the information gain (in nats) from applying a calibration step.
    A value of 0 means the two posteriors are identical; higher values indicate
    greater change.

    Args:
        posterior_before: :class:`~schemas.NEOPosterior` before calibration.
        posterior_after: :class:`~schemas.NEOPosterior` after calibration.

    Returns:
        KL divergence D_KL(after ‖ before) in nats, rounded to 6 decimal places.
        Returns 0.0 if either posterior is degenerate (all zeros).
    """
    import numpy as np

    fields = [
        "neo_candidate", "known_object", "main_belt_asteroid",
        "stellar_artifact", "other_solar_system",
    ]
    q = np.array([float(getattr(posterior_before, f, 0.0)) for f in fields], dtype=float)
    p = np.array([float(getattr(posterior_after, f, 0.0)) for f in fields], dtype=float)

    q_sum = q.sum()
    p_sum = p.sum()
    if q_sum <= 0.0 or p_sum <= 0.0:
        return 0.0

    q = q / q_sum
    p = p / p_sum

    eps = 1e-12
    kl = float(np.sum(p * np.log((p + eps) / (q + eps))))
    return round(kl, 6)


def batch_classify_morphology(tracklets: list[Tracklet]) -> list[dict[str, Any]]:
    """Batch morphology summary across multiple tracklets.

    For each tracklet calls :func:`batch_morphology` and returns a flat dict
    with keys: ``object_id``, ``modal_class``, ``streak_fraction``, and
    ``n_observations``.

    Args:
        tracklets: List of :class:`~schemas.Tracklet` objects.

    Returns:
        List of dicts, one per tracklet.  Empty list for empty input.
    """
    results: list[dict[str, Any]] = []
    for tracklet in tracklets:
        morph = batch_morphology(tracklet)
        results.append({
            "object_id": tracklet.object_id,
            "modal_class": morph.get("modal_class", "unknown"),
            "streak_fraction": morph.get("streak_fraction", 0.0),
            "n_observations": len(tracklet.observations),
        })
    return results


def compute_class_entropy_stats(neos: list) -> dict[str, Any]:
    """Aggregate entropy statistics across a list of scored NEO posteriors.

    Computes mean, max, and min Shannon entropy (bits) from each NEO's
    :class:`~schemas.NEOPosterior`, plus a count of high-entropy candidates
    (entropy ≥ 2.0 bits).

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.

    Returns:
        Dict with keys ``mean_entropy``, ``max_entropy``, ``min_entropy``,
        ``n_high_entropy``, and ``n_total``.  All zeros for empty input.
    """
    if not neos:
        return {
            "mean_entropy": 0.0,
            "max_entropy": 0.0,
            "min_entropy": 0.0,
            "n_high_entropy": 0,
            "n_total": 0,
        }
    entropies = [posterior_entropy(neo.posterior) for neo in neos]
    return {
        "mean_entropy": round(sum(entropies) / len(entropies), 4),
        "max_entropy": round(max(entropies), 4),
        "min_entropy": round(min(entropies), 4),
        "n_high_entropy": sum(1 for e in entropies if e >= 2.0),
        "n_total": len(neos),
    }


def compute_tier1_score_distribution(neos: list) -> dict[str, Any]:
    """Compute descriptive statistics of Tier-1 real/bogus scores across a NEO list.

    Extracts ``features.real_bogus_score`` from each :class:`~schemas.ScoredNEO`
    and returns summary statistics over valid (non-None) values.

    Args:
        neos: List of :class:`~schemas.ScoredNEO` objects.

    Returns:
        Dict with keys ``mean``, ``std``, ``p10``, ``p50``, ``p90``,
        ``n_valid``, ``n_total``.  All float stats are 0.0 when no valid
        scores are present.
    """
    import numpy as np

    scores: list[float] = []
    for neo in neos:
        rb = getattr(getattr(neo, "features", None), "real_bogus_score", None)
        if rb is not None:
            scores.append(float(rb))

    n_total = len(neos)
    n_valid = len(scores)
    if not scores:
        return {
            "mean": 0.0, "std": 0.0,
            "p10": 0.0, "p50": 0.0, "p90": 0.0,
            "n_valid": 0, "n_total": n_total,
        }

    arr = np.array(scores, dtype=float)
    return {
        "mean": round(float(arr.mean()), 4),
        "std": round(float(arr.std()), 4),
        "p10": round(float(np.percentile(arr, 10)), 4),
        "p50": round(float(np.percentile(arr, 50)), 4),
        "p90": round(float(np.percentile(arr, 90)), 4),
        "n_valid": n_valid,
        "n_total": n_total,
    }


def compute_class_entropy_summary(neos: list) -> dict[str, float | int]:
    """Return entropy statistics across a list of *ScoredNEO* objects.

    Computes :func:`posterior_entropy` for each NEO and returns a summary
    dict with ``mean_entropy``, ``std_entropy``, ``max_entropy``,
    ``min_entropy``, and ``n_neos``.  Entropy is in bits (log base-2).

    An empty list returns zeros for all float fields and 0 for ``n_neos``.
    """
    entropies: list[float] = []
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        if posterior is not None:
            try:
                entropies.append(posterior_entropy(posterior))
            except Exception:
                pass
    n = len(entropies)
    if n == 0:
        return {"mean_entropy": 0.0, "std_entropy": 0.0,
                "max_entropy": 0.0, "min_entropy": 0.0, "n_neos": 0}
    arr = np.array(entropies, dtype=float)
    return {
        "mean_entropy": round(float(arr.mean()), 6),
        "std_entropy": round(float(arr.std()), 6),
        "max_entropy": round(float(arr.max()), 6),
        "min_entropy": round(float(arr.min()), 6),
        "n_neos": n,
    }


def compute_neo_class_distribution(neos: list) -> dict[str, dict[str, float | int]]:
    """Return the distribution of NEO dynamical classes across scored candidates.

    For each distinct ``neo_class`` found in the hazard assessments of the
    supplied *neos*, returns a dict with ``"count"`` (int) and
    ``"fraction"`` (float, rounded to 4 d.p.).  An empty list returns an
    empty dict.
    """
    counts: dict[str, int] = {}
    for neo in neos:
        cls = getattr(getattr(neo, "hazard", None), "neo_class", "unknown") or "unknown"
        counts[cls] = counts.get(cls, 0) + 1
    total = len(neos)
    if total == 0:
        return {}
    return {
        cls: {"count": cnt, "fraction": round(cnt / total, 4)}
        for cls, cnt in counts.items()
    }


def compute_posterior_update(
    prior: NEOPosterior,  # type: ignore[name-defined]
    likelihood_weights: dict[str, float],
) -> NEOPosterior:  # type: ignore[name-defined]
    """Update a NEOPosterior with log-likelihood weights from new evidence.

    Each key in *likelihood_weights* must match a hypothesis name in the
    posterior (``neo_candidate``, ``known_object``, ``main_belt_asteroid``,
    ``stellar_artifact``, ``other_solar_system``).  Unknown keys are ignored.
    The update follows the log-score model:

    .. code-block:: text

        log p_i ∝ log prior_i + weight_i

    The result is normalised so all five probabilities sum to 1.0.
    Missing hypothesis keys in *likelihood_weights* keep their prior unchanged.
    Returns a new frozen ``NEOPosterior``; the original is not modified.
    """
    _KEYS = [
        "neo_candidate",
        "known_object",
        "main_belt_asteroid",
        "stellar_artifact",
        "other_solar_system",
    ]
    import math

    log_scores: dict[str, float] = {}
    for key in _KEYS:
        prior_val = float(getattr(prior, key, 0.0))
        prior_val = max(prior_val, 1e-12)
        log_scores[key] = math.log(prior_val) + float(likelihood_weights.get(key, 0.0))

    log_max = max(log_scores.values())
    exp_scores = {k: math.exp(v - log_max) for k, v in log_scores.items()}
    total = sum(exp_scores.values())

    return NEOPosterior(
        neo_candidate=round(exp_scores["neo_candidate"] / total, 8),
        known_object=round(exp_scores["known_object"] / total, 8),
        main_belt_asteroid=round(exp_scores["main_belt_asteroid"] / total, 8),
        stellar_artifact=round(exp_scores["stellar_artifact"] / total, 8),
        other_solar_system=round(exp_scores["other_solar_system"] / total, 8),
    )


def compute_tier1_confidence(features: object) -> float:
    """Return the fraction of Tier-1 feature scores that are not None.

    A value of 1.0 means all tabular features are populated; 0.0 means
    none are.  Uses the 14 ``CandidateFeatures`` fields defined in
    ``schemas.py``.
    """
    _FEATURE_FIELDS = [
        "real_bogus_score",
        "streak_score",
        "psf_quality_score",
        "motion_consistency_score",
        "arc_coverage_score",
        "nights_observed_score",
        "brightness_score",
        "color_score",
        "lightcurve_variability_score",
        "orbit_quality_score",
        "moid_score",
        "neo_class_confidence",
        "pha_flag_confidence",
        "known_object_score",
    ]
    present = sum(1 for f in _FEATURE_FIELDS if getattr(features, f, None) is not None)
    return round(present / len(_FEATURE_FIELDS), 6)


def compute_posterior_stability(posteriors: list) -> float:
    """Return the mean pairwise L1 distance across a list of NEOPosterior objects.

    0.0 = all posteriors identical; higher = more variable.  Returns 0.0
    when fewer than 2 posteriors are supplied.
    """
    _KEYS = ["neo_candidate", "known_object", "main_belt_asteroid",
             "stellar_artifact", "other_solar_system"]
    if len(posteriors) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(posteriors)):
        for j in range(i + 1, len(posteriors)):
            p = posteriors[i]
            q = posteriors[j]
            l1 = sum(abs(float(getattr(p, k, 0.0)) - float(getattr(q, k, 0.0)))
                     for k in _KEYS)
            total += l1
            count += 1
    return round(total / count, 6) if count > 0 else 0.0


def compute_class_probability_range(neos: list) -> dict:
    """Return the min/max posterior probability for each hypothesis across all ScoredNEOs.

    Returns a dict mapping each of the 5 hypothesis names to
    ``{"min": float, "max": float}``.  Empty input yields all zeros.

    Args:
        neos: List of ScoredNEO objects (or any objects with a ``posterior`` attribute).

    Returns:
        Dict with keys ``neo_candidate``, ``known_object``, ``main_belt_asteroid``,
        ``stellar_artifact``, ``other_solar_system``, each mapping to
        ``{"min": float, "max": float}``.
    """
    _KEYS = [
        "neo_candidate",
        "known_object",
        "main_belt_asteroid",
        "stellar_artifact",
        "other_solar_system",
    ]
    result: dict = {k: {"min": 0.0, "max": 0.0} for k in _KEYS}
    if not neos:
        return result
    mins: dict[str, float] = {k: float("inf") for k in _KEYS}
    maxs: dict[str, float] = {k: float("-inf") for k in _KEYS}
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        if posterior is None:
            continue
        for k in _KEYS:
            v = float(getattr(posterior, k, 0.0))
            if v < mins[k]:
                mins[k] = v
            if v > maxs[k]:
                maxs[k] = v
    for k in _KEYS:
        if mins[k] == float("inf"):
            result[k] = {"min": 0.0, "max": 0.0}
        else:
            result[k] = {"min": round(mins[k], 6), "max": round(maxs[k], 6)}
    return result


def compute_ensemble_agreement(posterior_list: list) -> float:
    """Compute mean pairwise agreement across a list of NEOPosterior-like objects.

    Agreement for a pair is defined as 1 - L1_distance/2, where L1_distance is
    the sum of absolute differences across the five hypothesis keys.  Returns a
    float in [0, 1], rounded to 6 decimal places.  Returns 0.0 if fewer than
    two posteriors are supplied.
    """
    _KEYS = [
        "neo_candidate",
        "known_object",
        "main_belt_asteroid",
        "stellar_artifact",
        "other_solar_system",
    ]
    if len(posterior_list) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(posterior_list)):
        for j in range(i + 1, len(posterior_list)):
            p = posterior_list[i]
            q = posterior_list[j]
            l1 = sum(
                abs(float(getattr(p, k, 0.0)) - float(getattr(q, k, 0.0)))
                for k in _KEYS
            )
            total += 1.0 - l1 / 2.0
            count += 1
    return round(total / count, 6) if count > 0 else 0.0


def compute_real_bogus_histogram(tracklet: object, n_bins: int = 5) -> dict:
    """Compute a histogram of real/bogus scores across a tracklet's observations.

    Returns a dict with keys ``"bins"`` (left edges, length n_bins),
    ``"counts"`` (integer counts per bin), and ``"mean"`` (mean RB score).
    Uses the deep_real_bogus score when available, falling back to real_bogus.
    Returns an empty histogram dict if no valid scores are found.
    """
    observations = getattr(tracklet, "observations", ()) or ()
    scores: list[float] = []
    for obs in observations:
        rb = getattr(obs, "deep_real_bogus", None)
        if rb is None:
            rb = getattr(obs, "real_bogus", None)
        if rb is not None:
            scores.append(float(rb))
    if not scores:
        return {"bins": [], "counts": [], "mean": None}
    import numpy as np
    counts_arr, edges = np.histogram(scores, bins=n_bins, range=(0.0, 1.0))
    return {
        "bins": [round(float(e), 4) for e in edges[:-1]],
        "counts": [int(c) for c in counts_arr],
        "mean": round(float(np.mean(scores)), 6),
    }


_NEO_CLASS_PRIORS: dict[str, float] = {
    "amor": 0.35,
    "apollo": 0.50,
    "aten": 0.12,
    "ieo": 0.03,
}


def compute_neo_class_prior(neo_class: str) -> float | None:
    """Return the fractional prior for a NEO dynamical class.

    Priors reflect approximate survey-completeness-corrected population fractions
    (Apollo dominant, followed by Amor, Aten, and IEO/Atira).
    Returns ``None`` for unknown class labels.
    """
    return _NEO_CLASS_PRIORS.get(neo_class.lower() if neo_class else "")


def compute_main_belt_probability(features: object) -> float:
    """Compute the log-score probability for the main-belt asteroid hypothesis.

    Uses the prior of 0.35 (CLAUDE.md) with feature weights that reward
    evidence consistent with a main-belt asteroid and penalise NEO-like
    motion.  The result is normalised against the neo_candidate hypothesis
    score so values are comparable.

    Returns a value in ``[0, 1]``; ``0.0`` if ``features`` is ``None``.
    """
    import math

    if features is None:
        return 0.0

    def _f(name: str) -> float:
        v = getattr(features, name, None)
        return float(v) if v is not None else 0.0

    log_mba = (
        math.log(0.35)
        + 1.5 * _f("main_belt_consistency_score")
        + 1.0 * _f("known_object_score")
        + 0.5 * _f("real_bogus_score")
        - 2.0 * _f("motion_consistency_score")
        - 1.0 * _f("orbit_quality_score")
        - 1.5 * _f("arc_coverage_score")
    )
    log_neo = (
        math.log(0.05)
        + 2.0 * _f("real_bogus_score")
        + 1.5 * _f("arc_coverage_score")
        + 1.5 * _f("nights_observed_score")
        + 1.2 * _f("motion_consistency_score")
        + 1.0 * _f("orbit_quality_score")
        - 2.5 * _f("known_object_score")
    )
    max_log = max(log_mba, log_neo)
    exp_mba = math.exp(log_mba - max_log)
    exp_neo = math.exp(log_neo - max_log)
    denom = exp_mba + exp_neo
    return float(max(0.0, min(1.0, exp_mba / denom)))


def compute_comet_probability(features: CandidateFeatures) -> float:
    """Compute log-score comet probability from candidate features.

    Uses a low prior (0.02) for comets and rewards erratic motion, poor orbit
    quality, and uncertain detection scores.  Missing features contribute 0
    (neutral).

    Args:
        features: :class:`~schemas.CandidateFeatures` object.

    Returns:
        Comet probability in [0, 1].
    """

    def _f(name: str) -> float:
        v = getattr(features, name, None)
        return float(v) if v is not None else 0.0

    log_comet = (
        math.log(0.02)
        + 1.5 * (1.0 - _f("motion_consistency_score"))
        + 1.0 * (1.0 - _f("orbit_quality_score"))
        + 0.5 * (1.0 - _f("real_bogus_score"))
    )
    log_non_comet = math.log(0.98)
    max_log = max(log_comet, log_non_comet)
    exp_comet = math.exp(log_comet - max_log)
    exp_non = math.exp(log_non_comet - max_log)
    denom = exp_comet + exp_non
    return float(max(0.0, min(1.0, exp_comet / denom)))


def compute_known_object_probability(features: CandidateFeatures) -> float:
    """Compute log-score probability that a candidate is a known MPC object.

    Log-score model::

        log_ko  = log(0.30)
                  + 2.0 × known_object_score
                  + 1.0 × real_bogus_score
                  + 0.5 × motion_consistency_score

        log_neo = log(0.70)

    Normalizes against ``log_neo`` (prior for not-known-object).  Missing
    features contribute 0 (neutral).

    Args:
        features: :class:`~schemas.CandidateFeatures` object.

    Returns:
        Known-object probability in [0, 1].
    """

    def _f(name: str) -> float:
        v = getattr(features, name, None)
        return float(v) if v is not None else 0.0

    log_ko = (
        math.log(0.30)
        + 2.0 * _f("known_object_score")
        + 1.0 * _f("real_bogus_score")
        + 0.5 * _f("motion_consistency_score")
    )
    log_neo = math.log(0.70)
    max_log = max(log_ko, log_neo)
    exp_ko = math.exp(log_ko - max_log)
    exp_neo = math.exp(log_neo - max_log)
    denom = exp_ko + exp_neo
    return float(max(0.0, min(1.0, exp_ko / denom)))


def compute_stellar_artifact_score_from_features(features: CandidateFeatures) -> float:
    """Extract the stellar artifact score from a :class:`~schemas.CandidateFeatures` object.

    Returns ``features.stellar_artifact_score`` as a float.  If the value is
    ``None`` or the attribute is missing (e.g. due to a duck-typed input),
    returns ``0.0``.

    Args:
        features: :class:`~schemas.CandidateFeatures` object (or any object
            with an optional ``stellar_artifact_score`` attribute).

    Returns:
        Stellar artifact score in [0, 1], or ``0.0`` if unavailable.
    """
    v = getattr(features, "stellar_artifact_score", None)
    if v is None:
        return 0.0
    return float(v)


def compute_posterior_from_scores(
    real_bogus: float | None,
    neo_prob: float | None,
    known_obj_prob: float | None,
) -> NEOPosterior:
    """Construct a :class:`~schemas.NEOPosterior` from three scalar scores.

    Uses hypothesis priors when inputs are ``None``:

    - ``neo_candidate``:      0.05
    - ``known_object``:       0.30
    - ``main_belt_asteroid``: 0.35
    - ``stellar_artifact``:   0.25
    - ``other_solar_system``: 0.05

    When ``real_bogus`` is provided, the artifact weight is scaled by
    ``(1 - real_bogus)`` and the neo / known-object / main-belt weights are
    scaled up proportionally to preserve normalisation.  When ``neo_prob``
    is provided it replaces the neo prior weight (before normalisation).
    When ``known_obj_prob`` is provided it replaces the known-object prior
    weight (before normalisation).  The resulting weights are always
    normalised to sum to 1.0.

    Args:
        real_bogus: Real/bogus score in [0, 1], or ``None``.
        neo_prob:  NEO candidate probability in [0, 1], or ``None``.
        known_obj_prob: Known-object probability in [0, 1], or ``None``.

    Returns:
        :class:`~schemas.NEOPosterior` with all five fields summing to 1.0.
    """
    # Start from priors
    w_neo = 0.05
    w_ko = 0.30
    w_mba = 0.35
    w_art = 0.25
    w_other = 0.05

    # Apply provided scores
    if neo_prob is not None:
        w_neo = float(neo_prob)
    if known_obj_prob is not None:
        w_ko = float(known_obj_prob)

    if real_bogus is not None:
        rb = float(real_bogus)
        # Scale artifact down by (1 - rb)
        w_art = w_art * (1.0 - rb)
        # Scale the real-source hypotheses up by (1 + rb) proportionally
        real_total = w_neo + w_ko + w_mba
        if real_total > 0.0:
            scale = real_total + real_total * rb
            if real_total > 0.0:
                factor = scale / real_total
                w_neo *= factor
                w_ko *= factor
                w_mba *= factor

    # Normalise — total is always > 0 since w_other = 0.05 (fixed prior)
    total = w_neo + w_ko + w_mba + w_art + w_other
    return NEOPosterior(
        neo_candidate=round(w_neo / total, 8),
        known_object=round(w_ko / total, 8),
        main_belt_asteroid=round(w_mba / total, 8),
        stellar_artifact=round(w_art / total, 8),
        other_solar_system=round(w_other / total, 8),
    )


def compute_classification_confidence(posterior: object) -> float:
    """Return the margin between the top-1 and top-2 posterior probabilities.

    Extracts the five class probabilities from a :class:`~schemas.NEOPosterior`
    (``neo_candidate``, ``known_object``, ``main_belt_asteroid``,
    ``stellar_artifact``, ``other_solar_system``), sorts them in descending
    order, and returns the difference between the highest and second-highest
    probability.  Returns ``0.0`` when all probabilities are equal or when
    fewer than two distinct values exist.

    Args:
        posterior: :class:`~schemas.NEOPosterior` or any object with the five
            class-probability attributes.

    Returns:
        Confidence margin in [0, 1].
    """
    fields = [
        "neo_candidate",
        "known_object",
        "main_belt_asteroid",
        "stellar_artifact",
        "other_solar_system",
    ]
    probs = sorted(
        [float(getattr(posterior, f, 0.0) or 0.0) for f in fields], reverse=True
    )
    return round(float(max(0.0, probs[0] - probs[1])), 6)


def compute_entropy_weighted_score(posterior: object, features: object) -> float:
    """Compute entropy-weighted NEO candidate score.

    Combines the NEO posterior probability with a confidence weight derived
    from posterior entropy: ``neo_prob * (1 - H / H_max)`` where ``H`` is the
    Shannon entropy of the posterior in bits and ``H_max = log2(5)``
    (maximum entropy for 5 hypotheses).  The result is clamped to [0, 1].

    Args:
        posterior: A :class:`~schemas.NEOPosterior`-like object.
        features: A :class:`~schemas.CandidateFeatures`-like object (unused
            directly but kept for API consistency).

    Returns:
        Entropy-weighted score in [0, 1].
    """
    from classify import posterior_entropy

    H = posterior_entropy(posterior)
    H_max = math.log2(5)
    neo_prob = float(getattr(posterior, "neo_candidate", 0.0) or 0.0)
    confidence = 1.0 - (H / H_max) if H_max > 0.0 else 0.0
    result = neo_prob * confidence
    return float(min(1.0, max(0.0, result)))


def compute_tier1_neo_score(features: object) -> float:
    """Compute a Tier 1 NEO score as a log-likelihood ratio rescaled to [0, 1].

    Calls :func:`compute_neo_probability` to obtain the NEO hypothesis
    probability ``p_neo``, computes the log-odds (log-likelihood ratio), clamps
    the LLR to [−10, 10], and applies the logistic function to map the result
    back to [0, 1].

    Args:
        features: A :class:`~schemas.CandidateFeatures`-like object.

    Returns:
        Tier 1 NEO score in [0, 1] (float).
    """
    p_neo = compute_neo_probability(features)
    llr = math.log(p_neo / (1.0 - p_neo))
    llr = max(-10.0, min(10.0, llr))
    return float(1.0 / (1.0 + math.exp(-llr)))


def compute_artifact_features_summary(features: object) -> dict:
    """Return a dict of artifact-relevant feature scores from a CandidateFeatures object.

    Each value is a float in [0, 1] or None if the feature is absent.
    """
    names = [
        "stellar_artifact_score",
        "psf_quality_score",
        "real_bogus_score",
        "streak_score",
    ]
    return {name: getattr(features, name, None) for name in names}


def compute_class_balance(neos: list) -> dict[str, int]:
    """Return a count of each dominant hypothesis across a list of ScoredNEO objects.

    The dominant hypothesis is the highest-probability class in each object's
    NEOPosterior. Returns a dict mapping hypothesis name to count.
    """
    counts: dict[str, int] = {}
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        if posterior is None:
            counts["unknown"] = counts.get("unknown", 0) + 1
            continue
        name, _ = dominant_hypothesis(posterior)
        counts[name] = counts.get(name, 0) + 1
    return counts


def compute_real_bogus_summary(neos: list) -> dict:
    """Return mean, min, and max real_bogus_score across a list of ScoredNEO objects.

    Only considers scores that are not None. Returns None for each stat if no
    valid scores exist.
    """
    scores = []
    for neo in neos:
        features = getattr(neo, "features", None)
        rb = getattr(features, "real_bogus_score", None) if features else None
        if rb is not None:
            scores.append(float(rb))
    if not scores:
        return {"mean": None, "min": None, "max": None, "n": 0}
    return {
        "mean": float(sum(scores) / len(scores)),
        "min": float(min(scores)),
        "max": float(max(scores)),
        "n": len(scores),
    }


def compute_class_agreement(neos: list) -> float:
    """Return the fraction of candidates that share the single most common dominant hypothesis.

    Agreement = count(most_common_hypothesis) / total_valid_candidates.
    Returns 0.0 if the list is empty or no posteriors are valid.
    """
    counts: dict[str, int] = {}
    total = 0
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        if posterior is None:
            continue
        name, _ = dominant_hypothesis(posterior)
        if name == "unknown":
            continue
        counts[name] = counts.get(name, 0) + 1
        total += 1
    if total == 0:
        return 0.0
    return float(max(counts.values()) / total)


def compute_tier1_feature_vector(tracklet: object) -> dict:
    """Extract the tabular feature dict used for Tier 1 XGBoost classification.

    Computes features purely from the tracklet's observations without requiring
    a trained model.  Returns a dict with the following keys (all float or None):

      - ``motion_rate_arcsec_hr``: tracklet motion rate
      - ``arc_days``: total arc length in days
      - ``n_nights``: number of distinct integer-JD nights observed
      - ``mean_mag``: mean magnitude of valid observations (mag < 90)
      - ``mean_real_bogus``: mean real/bogus score of valid observations
      - ``streak_fraction``: fraction of observations flagged as streaks
      - ``mag_range``: max − min magnitude across valid observations

    Missing or unavailable values are returned as ``None``.
    """
    motion_rate = getattr(tracklet, "motion_rate_arcsec_per_hour", None)
    arc_days = getattr(tracklet, "arc_days", None)
    obs_seq = getattr(tracklet, "observations", None) or ()

    nights = {
        int(float(getattr(o, "jd", 0)))
        for o in obs_seq
        if getattr(o, "jd", None) is not None
    }
    n_nights = len(nights) if nights else None

    mags = [
        float(getattr(o, "mag", 99))
        for o in obs_seq
        if getattr(o, "mag", None) is not None and float(getattr(o, "mag", 99)) < 90.0
    ]
    mean_mag = float(sum(mags) / len(mags)) if mags else None
    mag_range = float(max(mags) - min(mags)) if len(mags) >= 2 else None

    rbs = [
        float(getattr(o, "real_bogus_score", None))
        for o in obs_seq
        if getattr(o, "real_bogus_score", None) is not None
    ]
    mean_rb = float(sum(rbs) / len(rbs)) if rbs else None

    n_obs = len(obs_seq)
    streak_count = sum(1 for o in obs_seq if getattr(o, "is_streak", False))
    streak_fraction = float(streak_count / n_obs) if n_obs > 0 else None

    return {
        "motion_rate_arcsec_hr": float(motion_rate) if motion_rate is not None else None,
        "arc_days": float(arc_days) if arc_days is not None else None,
        "n_nights": n_nights,
        "mean_mag": mean_mag,
        "mean_real_bogus": mean_rb,
        "streak_fraction": streak_fraction,
        "mag_range": mag_range,
    }


def batch_dominant_hypothesis(neos: list) -> list:
    """Return a list of dominant-hypothesis dicts for each scored NEO.

    For each NEO in *neos*, calls :func:`dominant_hypothesis` on its posterior
    and returns a dict with keys:

      - ``"object_id"``: tracklet object ID (str) or ``"unknown"`` if unavailable
      - ``"hypothesis"``: dominant hypothesis name (str)
      - ``"probability"``: probability of the dominant hypothesis (float)

    NEOs with a missing or invalid posterior contribute
    ``{"object_id": ..., "hypothesis": "unknown", "probability": 0.0}``.
    """
    results = []
    for neo in neos:
        obj_id = getattr(getattr(neo, "tracklet", None), "object_id", "unknown") or "unknown"
        posterior = getattr(neo, "posterior", None)
        if posterior is None:
            results.append({"object_id": obj_id, "hypothesis": "unknown", "probability": 0.0})
            continue
        hyp, prob = dominant_hypothesis(posterior)
        results.append({"object_id": obj_id, "hypothesis": hyp, "probability": float(prob)})
    return results


def filter_by_neo_probability(neos: list, min_prob: float = 0.5) -> list:
    """Return scored NEOs whose posterior neo_candidate probability ≥ min_prob.

    Reads ``neo.posterior.neo_candidate``.  NEOs with a missing or None
    posterior are excluded.  Returns an empty list if no candidates qualify.
    """
    result = []
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        prob = getattr(posterior, "neo_candidate", None) if posterior else None
        if prob is not None and float(prob) >= min_prob:
            result.append(neo)
    return result


def count_by_dominant_hypothesis(neos: list) -> dict:
    """Return a count of scored NEOs by their dominant posterior hypothesis.

    For each NEO in *neos*, calls :func:`dominant_hypothesis` on its
    posterior and tallies the result.  NEOs with missing posteriors
    contribute to the ``"unknown"`` key.  Returns an empty dict for
    empty input.
    """
    counts: dict = {}
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        if posterior is None:
            hyp = "unknown"
        else:
            hyp, _ = dominant_hypothesis(posterior)
        counts[hyp] = counts.get(hyp, 0) + 1
    return counts


def compute_mean_neo_probability(neos: list) -> float | None:
    """Return the mean posterior neo_candidate probability across all NEOs.

    Reads ``neo.posterior.neo_candidate`` for each NEO.  NEOs with a missing
    or None posterior are excluded.  Returns ``None`` for an empty list or if
    no NEO has a valid posterior.
    """
    probs = []
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        prob = getattr(posterior, "neo_candidate", None) if posterior else None
        if prob is not None:
            probs.append(float(prob))
    return float(sum(probs) / len(probs)) if probs else None


def compute_composite_neo_score(features: object) -> float:
    """Weighted composite NEO score from candidate features.

    Combines four detection-quality signals into a single [0, 1] score:

    - real_bogus_score × 0.35
    - arc_coverage_score × 0.25
    - nights_observed_score × 0.25
    - orbit_quality_score × 0.15

    Missing (None) features contribute 0.  The result is clamped to [0, 1].
    """

    def _get(name: str) -> float:
        v = getattr(features, name, None)
        return float(v) if v is not None else 0.0

    score = (
        _get("real_bogus_score") * 0.35
        + _get("arc_coverage_score") * 0.25
        + _get("nights_observed_score") * 0.25
        + _get("orbit_quality_score") * 0.15
    )
    return float(min(1.0, max(0.0, score)))


def get_highest_confidence_neo(neos: list) -> object | None:
    """Return the ScoredNEO with the highest posterior neo_candidate probability.

    Ignores NEOs with missing or None posteriors.  Returns ``None`` if the
    list is empty or no valid posteriors exist.
    """
    best = None
    best_prob = -1.0
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        prob = getattr(posterior, "neo_candidate", None) if posterior else None
        if prob is not None and float(prob) > best_prob:
            best_prob = float(prob)
            best = neo
    return best


def compute_classification_entropy_summary(neos: list) -> dict:
    """Summary statistics of Shannon entropy across scored NEOs.

    Returns a dict with keys: ``mean_entropy``, ``std_entropy``,
    ``min_entropy``, ``max_entropy``.  Returns an empty dict if no
    NEOs have a valid posterior.
    """
    import math

    entropies = []
    for neo in neos:
        posterior = getattr(neo, "posterior", None)
        if posterior is None:
            continue
        ent = posterior_entropy(posterior)
        entropies.append(float(ent))

    if not entropies:
        return {}

    n = len(entropies)
    mean = sum(entropies) / n
    variance = sum((e - mean) ** 2 for e in entropies) / n
    return {
        "mean_entropy": mean,
        "std_entropy": math.sqrt(variance),
        "min_entropy": min(entropies),
        "max_entropy": max(entropies),
    }
