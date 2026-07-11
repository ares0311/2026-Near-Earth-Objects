"""Classify stage — three-tier ML pipeline: XGBoost, CNN, Transformer + ensemble."""

from __future__ import annotations

__all__ = [
    "extract_features",
    "features_to_vector",
    "classify",
    "classify_batch",
    "ensemble_predict",
    "_build_ensemble",
    "_load_ensemble_stacker",
    "retrain_tier1",
    "retrain_stacker",
    "compute_calibration_gain",
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


def features_to_vector(features: CandidateFeatures) -> np.ndarray:
    """Public wrapper for the handcrafted Tier 1 feature vector.

    Exposes the same ordered array `_tier1_predict` feeds to the XGBoost
    model, for use by evaluators (e.g. Gate Z4's ranking-baseline drill)
    that need the raw handcrafted features rather than a tier prediction.
    """
    return _features_to_array(features)


def _read_file_with_heartbeat(path: Any, label: str, interval: float = 5.0) -> bytes:
    """Read a file into memory in 64 KB chunks, printing a heartbeat every
    `interval` seconds if the read is slow.

    A bare path-based load (xgboost's ``load_model(str(path))``, or
    ``torch.load(str(path))`` which mmaps and defers reads) can block
    silently and indefinitely if `path` lives on a cloud-synced directory
    (e.g. Dropbox) that has not finished downloading the file locally --
    the OS read() call blocks on the network fetch with zero visible
    progress, indistinguishable from a true hang. This was diagnosed and
    fixed for the CNN loader (BytesIO pre-read); this shared helper applies
    the identical fix to every other model loader in this module.
    """
    import threading
    import time as _time

    stop = threading.Event()

    def _heartbeat() -> None:
        t0 = _time.monotonic()
        while not stop.wait(interval):
            elapsed = int(_time.monotonic() - t0)
            m, s = divmod(elapsed, 60)
            print(f"  reading {label} … still working ({m}m{s:02d}s elapsed)", flush=True)

    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()
    try:
        buf = bytearray()
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)
        return bytes(buf)
    finally:
        stop.set()
        hb.join(timeout=1.0)


def _load_xgb_model() -> Any:
    model_path = _MODEL_DIR / "tier1_xgb.json"
    if not model_path.exists():
        return None
    try:
        import xgboost as xgb  # type: ignore[import]

        # Pre-read with a heartbeat -- see _read_file_with_heartbeat. This
        # is the model loaded FIRST inside classify() (Tier 1 runs before
        # Tier 2/3), so an unprotected read here blocks before any other
        # tier's deadlock mitigation is ever reached.
        raw = _read_file_with_heartbeat(model_path, "Tier 1 XGBoost model")

        clf = xgb.XGBClassifier()
        clf.load_model(bytearray(raw))
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
                # Layer list and order are unchanged from the original
                # single nn.Sequential so state_dict keys (net.0, net.1, ...)
                # stay identical -- the frozen benchmark_cnn_v1 checkpoint
                # (models/tier2_cnn.pt) must keep loading via this same
                # module structure. forward() below iterates self.net's
                # children manually (instead of calling self.net(x)
                # directly) only to route the AdaptiveAvgPool2d step through
                # CPU on MPS; this does not change parameter registration.
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
                # PyTorch's MPS backend does not implement adaptive_avg_pool2d
                # for non-divisible input/output sizes (this branch's conv
                # stack produces a 15x15 feature map, and 15 is not evenly
                # divisible by the AdaptiveAvgPool2d(4) target): RuntimeError
                # "Adaptive pool MPS: input sizes must be divisible by output
                # sizes. Non-divisible input sizes are not implemented on MPS
                # device yet." -- https://github.com/pytorch/pytorch/issues/96056.
                # Per that issue's own suggested workaround, only this one op
                # is moved to CPU when running on MPS; every other layer runs
                # on its original device.
                for layer in self.net:
                    if isinstance(layer, nn.AdaptiveAvgPool2d) and x.device.type == "mps":
                        x = layer(x.to("cpu")).to(x.device)
                    else:
                        x = layer(x)
                return x

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


def _cnn_heartbeat(label: str, stop_event: Any, interval: float = 5.0) -> None:
    """Print an elapsed-time line every `interval` seconds until `stop_event`
    is set. Run on a plain Python thread -- unrelated to and does not
    interact with ATen's internal thread pool, so it cannot itself
    contribute to the deadlock it exists to make visible.

    Mirrors Skills/evaluate_calibration.py's `_heartbeat`: a blocking torch
    call on a Dropbox-backed path or a lazy CNN-kernel compile can stall for
    minutes with zero output, indistinguishable from a true hang, without
    this.
    """
    import time as _time

    t0 = _time.monotonic()
    while not stop_event.wait(interval):
        elapsed = int(_time.monotonic() - t0)
        m, s = divmod(elapsed, 60)
        print(f"  {label} … still working ({m}m{s:02d}s elapsed)", flush=True)


def _load_cnn_model() -> Any:
    model_path = _MODEL_DIR / "tier2_cnn.pt"
    if not model_path.exists():
        return None
    try:
        import io
        import os
        import threading

        # Set thread limits before importing torch to prevent ATen thread-pool
        # deadlock on macOS (same fix as evaluate_calibration.py v0.87.7).
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")

        import torch

        torch.set_num_threads(1)

        # Pre-read the model file into BytesIO in 64 KB chunks.
        # torch.load on a file-path string uses mmap, which defers byte reads
        # until load_state_dict — that deferred I/O triggers the ATen
        # thread-pool deadlock on Dropbox-backed paths on macOS.
        buf = io.BytesIO()
        with open(model_path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                buf.write(chunk)
        buf.seek(0)

        model = _build_cnn_model()
        if model is None:
            return None

        # Warm up PyTorch's Accelerate/BLAS/thread-pool lazy initialisation
        # with a dummy matmul BEFORE load_state_dict. On macOS (Apple Silicon
        # + Accelerate), the first tensor compute in a new process triggers
        # this init and can take 15-30s+; if it happens inside
        # load_state_dict instead, the caller sees a silent hang. This exact
        # mitigation already existed in Skills/evaluate_calibration.py
        # (PR #93) but was never ported into this shared module, which is
        # why every other caller of classify() -- including
        # Skills/injection_recovery.py -- remained exposed to the deadlock.
        stop = threading.Event()
        hb = threading.Thread(
            target=_cnn_heartbeat, args=("PyTorch matmul warmup", stop), daemon=True
        )
        hb.start()
        try:
            _w = torch.zeros(256, 256)
            _ = _w @ _w  # forces ATen dispatch into Accelerate
            del _w, _
        finally:
            stop.set()
            hb.join(timeout=1.0)

        model.load_state_dict(torch.load(buf, map_location="cpu"))
        model.eval()

        # Force conv2d kernel initialisation with a dummy forward pass before
        # any real inference. The matmul warmup above only activates ATen's
        # BLAS paths; the first torch.nn.Conv2d call goes through a separate
        # dispatch route (FBGEMM/oneDNN/nnpack on macOS CPU) that can take
        # many minutes to lazily compile on first use (PR #94, also never
        # previously ported here).
        stop = threading.Event()
        hb = threading.Thread(
            target=_cnn_heartbeat, args=("CNN conv warmup", stop), daemon=True
        )
        hb.start()
        try:
            with torch.no_grad():
                _dummy = torch.zeros(1, 1, 63, 63)
                model(_dummy, _dummy, _dummy)
                del _dummy
        finally:
            stop.set()
            hb.join(timeout=1.0)

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
        import io
        import os
        import threading

        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("MKL_NUM_THREADS", "1")

        import torch

        torch.set_num_threads(1)

        # Pre-read with a heartbeat -- see _read_file_with_heartbeat. If no
        # image cutouts are present, Tier 2's CNN never loads and this is
        # the FIRST torch model load in the process, so it needs the same
        # protection independently rather than relying on Tier 2 having
        # already warmed things up.
        raw = _read_file_with_heartbeat(model_path, "Tier 3 Transformer model")
        buf = io.BytesIO(raw)

        model = _build_transformer_model()
        if model is None:
            return None

        # Warm up ATen/Accelerate lazy init with a dummy matmul before the
        # real load_state_dict, same rationale as the CNN loader.
        stop = threading.Event()
        hb = threading.Thread(
            target=_cnn_heartbeat, args=("PyTorch matmul warmup (Tier 3)", stop), daemon=True
        )
        hb.start()
        try:
            _w = torch.zeros(256, 256)
            _ = _w @ _w
            del _w, _
        finally:
            stop.set()
            hb.join(timeout=1.0)

        model.load_state_dict(torch.load(buf, map_location="cpu"))
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


class _StackerProxy:
    """Reconstruct stacker from JSON coefficients; provides predict_proba and coef_ attributes."""

    def __init__(self, coef: list, intercept: list, classes: list) -> None:
        import numpy as np
        # coef shape: (n_classes, n_features); intercept shape: (n_classes,)
        self.coef_ = np.array(coef, dtype=np.float64)
        self.intercept_ = np.array(intercept, dtype=np.float64)
        self.classes_ = np.array(classes)

    def predict_proba(self, X: Any) -> Any:
        """Apply softmax over linear decision function; matches sklearn LogReg output."""
        import numpy as np
        X_arr = np.asarray(X, dtype=np.float64)
        # decision function: (n_samples, n_classes)
        z = X_arr @ self.coef_.T + self.intercept_
        # numerically stable softmax
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)


def _load_ensemble_stacker(model_path: Path | str | None = None) -> Any:
    """Load ensemble stacker coefficients from JSON; returns _StackerProxy or None."""
    path = Path(model_path) if model_path else _MODEL_DIR / "stacker_coef.json"
    if not path.exists():
        return None
    try:
        with path.open() as f:
            data = json.load(f)
        return _StackerProxy(data["coef"], data["intercept"], data["classes"])
    except Exception:
        return None


def _build_ensemble(
    tier1_outputs: list[dict[str, float]],
    labels: list[dict[str, float]],
    tier2_outputs: list[dict[str, float]] | None = None,
    tier3_outputs: list[dict[str, float]] | None = None,
) -> Any:
    """Train a logistic regression meta-learner on stacked tier outputs.

    Supports 5-feature (T1 only), 10-feature (T1+T2), or 15-feature (T1+T2+T3)
    input depending on which tier outputs are supplied.

    tier1_outputs: list of 5-class probability dicts (one per example)
    labels: list of dicts with key 'label' (int 0-4)
    tier2_outputs: optional list of 5-class T2 probability dicts (same length)
    tier3_outputs: optional list of 5-class T3 probability dicts (same length)

    Returns a fitted sklearn LogisticRegression, or None on failure.
    """
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression  # type: ignore[import]

        rows = []
        for i, t1 in enumerate(tier1_outputs):
            row = [t1[lbl] for lbl in _LABELS]
            if tier2_outputs is not None and i < len(tier2_outputs):
                row += [tier2_outputs[i][lbl] for lbl in _LABELS]
            if tier3_outputs is not None and i < len(tier3_outputs):
                row += [tier3_outputs[i][lbl] for lbl in _LABELS]
            rows.append(row)

        X = np.array(rows, dtype=np.float32)
        y = np.array([int(d["label"]) for d in labels], dtype=np.int32)
        if len(np.unique(y)) < 2:
            return None
        clf = LogisticRegression(max_iter=500, solver="lbfgs", C=1.0)
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

    If meta_model is provided it is used as the stacking meta-learner.
    Feature dimension is inferred from meta_model.coef_.shape[1]:
      5  = T1 only
      10 = T1 + T2 (tier2 must be non-None; otherwise falls back)
      15 = T1 + T2 + T3 (both tier2 and tier3 must be non-None; otherwise falls back)

    When the stacker was trained on a subset of the 5 classes, missing-class
    probabilities are backfilled using T1 proportions and the output is
    renormalized to sum to 1.

    Falls back to weighted average when meta_model is absent, a required tier is
    missing, or any exception occurs.
    """
    if meta_model is not None:
        try:
            import numpy as np

            n_features = int(meta_model.coef_.shape[1])
            row: list[float] = [tier1[lbl] for lbl in _LABELS]
            if n_features >= 10:
                # 10-feature stacker needs T2; fall back gracefully if absent
                if tier2 is None:
                    return _stack_predictions(tier1, tier2, tier3)
                row += [tier2[lbl] for lbl in _LABELS]
            if n_features >= 15:
                # 15-feature stacker needs T3; fall back gracefully if absent
                if tier3 is None:
                    return _stack_predictions(tier1, tier2, tier3)
                row += [tier3[lbl] for lbl in _LABELS]

            x = np.array([row[:n_features]], dtype=np.float32)
            proba = meta_model.predict_proba(x)[0]

            # Handle partial-class stackers (trained on subset of 5 classes)
            trained_classes = list(meta_model.classes_)
            if len(trained_classes) < len(_LABELS):
                # Map stacker probas to their respective labels
                meta_out: dict[str, float] = {lbl: 0.0 for lbl in _LABELS}
                assigned = 0.0
                for cls_idx, p in zip(trained_classes, proba):
                    if 0 <= int(cls_idx) < len(_LABELS):
                        meta_out[_LABELS[int(cls_idx)]] = float(p)
                        assigned += float(p)
                # Backfill missing classes using T1 relative proportions
                gap = max(0.0, 1.0 - assigned)
                t1_missing = sum(
                    tier1.get(lbl, 0.0) for lbl in _LABELS if meta_out[lbl] == 0.0
                )
                for lbl in _LABELS:
                    if meta_out[lbl] == 0.0 and t1_missing > 0:
                        meta_out[lbl] = gap * tier1.get(lbl, 0.0) / t1_missing
            else:
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
    tier2_outputs: list[dict[str, float]] | None = None,
    tier3_outputs: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Retrain the stacking meta-learner from tier probability outputs.

    ``tier1_outputs`` is a list of 5-class probability dicts (one per example).
    ``labels`` is a list of dicts each with key ``"label"`` (int 0–4).
    ``tier2_outputs`` / ``tier3_outputs`` extend the feature vector to 10 / 15
    features when provided.

    Serialises the fitted coefficients to a JSON sidecar at ``model_path``
    (defaults to ``models/stacker_coef.json``).  ``n_features`` is stored in
    the JSON so ``_load_ensemble_stacker`` can reconstruct the correct proxy.

    Returns a training report with keys ``n_samples``, ``n_classes``,
    ``auc``, ``model_path``, ``coef_path``.
    """
    model = _build_ensemble(tier1_outputs, labels, tier2_outputs, tier3_outputs)
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

            # Rebuild feature matrix matching the training input (T1 + optional T2 + T3)
            rows_eval = []
            for i_e, t1_e in enumerate(tier1_outputs):
                row_e = [t1_e[lbl] for lbl in _LABELS]
                if tier2_outputs is not None and i_e < len(tier2_outputs):
                    row_e += [tier2_outputs[i_e][lbl] for lbl in _LABELS]
                if tier3_outputs is not None and i_e < len(tier3_outputs):
                    row_e += [tier3_outputs[i_e][lbl] for lbl in _LABELS]
                rows_eval.append(row_e)
            X = np.array(rows_eval, dtype=np.float32)
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
                "n_features": int(model.coef_.shape[1]),
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
































































