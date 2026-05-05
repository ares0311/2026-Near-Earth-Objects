"""Classify stage — three-tier ML pipeline: XGBoost, CNN, Transformer + ensemble."""

from __future__ import annotations

import base64
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
        labels = ["neo_candidate", "known_object", "main_belt_asteroid", "stellar_artifact", "other_solar_system"]
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
                f = torch.cat([self.branch_sci(sci), self.branch_ref(ref), self.branch_diff(diff)], dim=1)
                return self.head(f)

        return TripleCNN()
    except ImportError:
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
    if model is None:
        model = _load_cnn_model()
    if model is None:
        return None

    # Collect first observation with all three cutouts
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

    try:
        import torch

        def to_tensor(arr: np.ndarray) -> Any:
            return torch.from_numpy(arr).unsqueeze(0).unsqueeze(0)  # (1,1,63,63)

        with torch.no_grad():
            proba = model(to_tensor(triplet[0]), to_tensor(triplet[1]), to_tensor(triplet[2]))
            proba_np = proba.squeeze().numpy()

        labels = ["neo_candidate", "known_object", "main_belt_asteroid", "stellar_artifact", "other_solar_system"]
        return {k: float(v) for k, v in zip(labels, proba_np)}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tier 3 — Transformer on tracklet sequences
# ---------------------------------------------------------------------------


def _build_transformer_model() -> Any:
    """Build BERT-style encoder for tracklet sequence classification."""
    try:
        import torch
        import torch.nn as nn
        import math as _math

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
                return x + self.pe[:, : x.size(1)]

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
                    nn.Linear(d_model, 64), nn.ReLU(), nn.Linear(64, num_classes), nn.Softmax(dim=1)
                )

            def forward(self, x: Any) -> Any:
                b = x.size(0)
                cls = self.cls_token.expand(b, -1, -1)
                x = torch.cat([cls, self.input_proj(x)], dim=1)
                x = self.pos_enc(x)
                x = self.encoder(x)
                return self.head(x[:, 0])

        return TrackletTransformer()
    except ImportError:
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
            proba = model(x).squeeze().numpy()

        labels = ["neo_candidate", "known_object", "main_belt_asteroid", "stellar_artifact", "other_solar_system"]
        return {k: float(v) for k, v in zip(labels, proba)}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stacking ensemble
# ---------------------------------------------------------------------------


def _stack_predictions(
    t1: dict[str, OptScore],
    t2: dict[str, OptScore] | None,
    t3: dict[str, OptScore] | None,
) -> dict[str, float]:
    """Simple weighted average ensemble; weights reflect tier reliability."""
    labels = ["neo_candidate", "known_object", "main_belt_asteroid", "stellar_artifact", "other_solar_system"]
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
