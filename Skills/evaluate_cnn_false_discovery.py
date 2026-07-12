#!/usr/bin/env python
"""Real, model-specific CNN false-discovery evaluation.

Closes the gap found 2026-07-11/12: docs/evidence/promotion/*_false_discovery.json
was derived from Gate Z4's handcrafted-feature logistic-regression ranking
baseline (Skills/evaluate_ranking_baseline.py) evaluated against real
archived negative tracklets -- never any CNN's inference, for any candidate.

That real archived data cannot be reused here: its per-detection cutout
images (cutoutScience/cutoutTemplate/cutoutDifference) were never mapped
from the raw AVRO packets (see Skills/ztf_alert_archive_ingest.py's module
docstring -- "left None rather than guessed", a documented limitation, not
an oversight). Fabricating cutout pixels for real archived detections we
do not actually have would be data fabrication, not evidence. So this
script is explicitly synthetic-only and does NOT replace Gate Z4's real
false-link evidence -- it is additional, CNN-specific evidence answering a
narrower question the real-data evidence cannot: does a specific trained
CNN's *shape* discrimination correctly reject an artifact that the
shape-blind analytic real_bogus proxy (used by detect.py's pre-filter and
by injection_recovery.py's plain --image-level mode) would let through on
amplitude alone?

Method: synthesize tracklets using the exact same proven position/motion
generator as Skills/injection_recovery.py's inject_synthetic_neo_image_level
(guaranteed to satisfy link.py's motion-consistency requirement), but with
an artifact-shaped cutout -- an unresolved, single-pixel-scale spike (e.g.
a cosmic ray or hot pixel) instead of a seeing-limited Gaussian PSF. The
spike's peak-amplitude-over-background SNR is tuned to comfortably clear
detect.py's 0.65 threshold, exactly like a real detection would, so the
question the CNN actually faces at classify() time is real: "is this
astrophysical or not," not "is this even bright enough to look at."

A tracklet is a false discovery if it survives detect()+link() (an
artifact geometrically consistent with a real object -- Gate Z4's real
finding was that this genuinely happens: crowded-field static sources get
spuriously cross-night-paired) AND the ensemble's neo_candidate posterior
is the argmax across the five-hypothesis posterior despite being a known,
constructed artifact.

Usage:
    PYTHONPATH=src python Skills/evaluate_cnn_false_discovery.py \\
        --cnn-model models/tier2_cnn_v3.pt --n-artifacts 200 --seed 42 \\
        --json Logs/reports/cnn_false_discovery_tier2_cnn_v3.json
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from injection_recovery import _CUTOUT_SIZE, _SYNTHETIC_ZEROPOINT_MAG, _make_obs  # noqa: E402

from classify import (  # type: ignore[import]
    _load_cnn_model,
    _tier2_predict,
    classify,
    extract_features,
)
from detect import detect  # type: ignore[import]
from link import link  # type: ignore[import]
from schemas import Observation  # type: ignore[import]

# Spatial width (pixels) of the synthetic artifact spike -- far narrower
# than any real seeing-limited PSF (typical ZTF seeing ~1.0-2.5 arcsec /
# ~1-2.5 px at this harness's 1.01 arcsec/px scale, giving sigma_px roughly
# 0.4-1.1). 0.15 px is deliberately sub-resolution: a single hot pixel or
# cosmic-ray hit, not a defocused star.
_ARTIFACT_SPIKE_SIGMA_PX = 0.15


def _synthesize_artifact_cutout_arrays(
    rng: np.random.Generator,
    mag: float,
    background_level: float,
    sigma_px: float = _ARTIFACT_SPIKE_SIGMA_PX,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Build raw (63,63) float32 science/reference/difference arrays for a
    synthetic non-astrophysical artifact (unresolved spike) rather than a
    genuine seeing-limited point source. `sigma_px` defaults to this
    module's single extreme adversarial-test value but is exposed so
    callers (e.g. Skills/train_tier2_cnn.py's hard-negative augmentation)
    can generate a range of spike widths instead of one fixed case.
    Returns (science_arr, reference_arr, difference_arr, real_bogus_proxy)
    -- same amplitude/background SNR-to-real_bogus mapping as
    injection_recovery.py's _synthesize_cutout_triplet, so this passes
    detect.py's pre-filter on the same terms a genuine detection would."""
    total_flux = 10 ** (-0.4 * (mag - _SYNTHETIC_ZEROPOINT_MAG))
    sigma = sigma_px
    amplitude = total_flux / (2 * math.pi * sigma * sigma)

    size = _CUTOUT_SIZE
    y, x = np.indices((size, size))
    cx, cy = size / 2.0, size / 2.0
    source = amplitude * np.exp(-(((x - cx) ** 2) + ((y - cy) ** 2)) / (2 * sigma**2))

    reference_arr = rng.normal(0.0, background_level, size=(size, size)).astype(np.float32)
    diff_noise = rng.normal(0.0, background_level, size=(size, size)).astype(np.float32)
    difference_arr = (source + diff_noise).astype(np.float32)
    science_arr = reference_arr + difference_arr

    snr = amplitude / background_level
    real_bogus = float(min(1.0, max(0.0, (snr - 3.0) / 20.0)))

    return science_arr, reference_arr, difference_arr, real_bogus


def _synthesize_artifact_cutout_triplet(
    rng: np.random.Generator,
    mag: float,
    background_level: float,
    sigma_px: float = _ARTIFACT_SPIKE_SIGMA_PX,
) -> tuple[str, str, str, float]:
    """Base64-encoded wrapper around _synthesize_artifact_cutout_arrays for
    Observation cutout_* fields (science_b64, reference_b64, difference_b64,
    real_bogus_proxy)."""
    science_arr, reference_arr, difference_arr, real_bogus = _synthesize_artifact_cutout_arrays(
        rng, mag, background_level, sigma_px=sigma_px
    )
    reference_b64 = base64.b64encode(reference_arr.tobytes()).decode()
    science_b64 = base64.b64encode(science_arr.tobytes()).decode()
    difference_b64 = base64.b64encode(difference_arr.tobytes()).decode()
    return science_b64, reference_b64, difference_b64, real_bogus


def synthesize_artifact_tracklet(
    seed: int,
    n_nights: int = 3,
    ra0: float = 180.0,
    dec0: float = 0.0,
    motion_arcsec_per_hr: float = 1.0,
    mag: float = 19.5,
    background_level: float = 10.0,
    sigma_px: float = _ARTIFACT_SPIKE_SIGMA_PX,
) -> tuple[Observation, ...]:
    """Same cadence and linear-motion geometry as
    injection_recovery.inject_synthetic_neo_image_level (2 obs/night,
    guaranteed to satisfy link.py's motion-consistency chi2 test), but
    every cutout is a synthetic artifact spike, not a genuine point
    source. Tests whether the CNN's shape discrimination rejects an
    artifact that nonetheless passes the geometric linking test -- Gate
    Z4's real archived evidence showed this genuinely happens with real
    crowded-field static sources."""
    rng = np.random.default_rng(seed)
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    obs = []
    for night in range(n_nights):
        jd_base = 2460000.5 + night
        ra_base = ra0 + night * dra_per_hr * 24
        for label, dt_hr in (("a", 0.0), ("b", 1.0)):
            obs_mag = mag + rng.normal(0, 0.05)
            sci_b64, ref_b64, diff_b64, real_bogus = _synthesize_artifact_cutout_triplet(
                rng, obs_mag, background_level, sigma_px=sigma_px
            )
            obs.append(
                _make_obs(
                    f"art_{seed}_n{night}{label}",
                    jd_base + dt_hr / 24,
                    ra_base + dt_hr * dra_per_hr + rng.normal(0, 0.5 / 3600.0),
                    dec0 + rng.normal(0, 0.5 / 3600.0),
                    obs_mag,
                    real_bogus=real_bogus,
                    cutout_difference=diff_b64,
                    cutout_science=sci_b64,
                    cutout_reference=ref_b64,
                )
            )
    return tuple(obs)


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def run_false_discovery_eval(
    cnn_model_path: Path,
    n_artifacts: int = 200,
    seed: int = 42,
) -> dict:
    """Run the synthetic CNN false-discovery evaluation and return summary
    statistics. Fails closed (raises) if cnn_model_path cannot be loaded,
    same policy as injection_recovery.py --cnn-model."""
    print(f"Loading Tier 2 CNN for real inference: {cnn_model_path}", flush=True)
    model = _load_cnn_model(cnn_model_path)
    if model is None:
        raise ValueError(
            f"cnn_model_path={cnn_model_path} could not be loaded -- refusing to "
            "silently skip the false-discovery evaluation."
        )
    print("Tier 2 CNN loaded.", flush=True)

    rng = np.random.default_rng(seed)
    n_detected = 0
    n_linked = 0
    n_scored = 0
    n_false_discovery = 0
    n_tier2_false_discovery = 0
    records: list[dict] = []

    t0 = time.monotonic()
    for i in range(n_artifacts):
        elapsed = time.monotonic() - t0
        per_item = elapsed / max(i, 1)
        eta = per_item * (n_artifacts - i)
        print(
            f"[false-discovery] ({i + 1}/{n_artifacts})  "
            f"detected={n_detected} linked={n_linked} scored={n_scored} "
            f"false_discoveries={n_false_discovery}  "
            f"elapsed {_fmt_duration(elapsed)}  ETA {_fmt_duration(eta)}",
            flush=True,
        )
        motion = rng.uniform(0.1, 10.0)
        ra0 = rng.uniform(0.0, 359.0)
        dec0 = rng.uniform(-30.0, 30.0)
        mag = rng.uniform(18.0, 21.0)
        background = rng.uniform(2.0, 40.0)

        obs = synthesize_artifact_tracklet(
            seed=seed * 1000 + i,
            ra0=ra0,
            dec0=dec0,
            motion_arcsec_per_hr=float(motion),
            mag=float(mag),
            background_level=float(background),
        )

        detect_result = detect(obs, mpc_cross_match=False)
        detected = bool(detect_result.candidates)
        if detected:
            n_detected += 1

        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)
        linked = bool(link_result.tracklets)
        is_false_discovery = False
        is_tier2_false_discovery = None
        argmax_class = None
        tier2_argmax_class = None
        if linked:
            n_linked += 1
            t = link_result.tracklets[0]
            features = extract_features(t)
            _features_cls, posterior = classify(t, features, cnn_model=model)
            n_scored += 1
            posterior_dict = posterior.model_dump()
            argmax_class = max(posterior_dict, key=lambda k: posterior_dict[k])
            is_false_discovery = argmax_class == "neo_candidate"
            if is_false_discovery:
                n_false_discovery += 1

            # Isolated Tier 2 (CNN-only) posterior, bypassing the ensemble --
            # distinguishes "the whole pipeline flagged this" from "the CNN
            # itself flagged this," since Tier 1 (tabular, image-blind) sees
            # this tracklet's clean linear motion and high real_bogus
            # regardless of what the image actually shows.
            tier2_posterior = _tier2_predict(t, model)
            if tier2_posterior is not None:
                tier2_argmax_class = max(tier2_posterior, key=lambda k: tier2_posterior[k])
                is_tier2_false_discovery = tier2_argmax_class == "neo_candidate"
                if is_tier2_false_discovery:
                    n_tier2_false_discovery += 1

        records.append(
            {
                "index": i,
                "mag": float(mag),
                "background_level": float(background),
                "motion_arcsec_per_hr": float(motion),
                "detected": detected,
                "linked": linked,
                "scored": linked,
                "argmax_class": argmax_class,
                "false_discovery": is_false_discovery,
                "tier2_argmax_class": tier2_argmax_class,
                "tier2_false_discovery": is_tier2_false_discovery,
            }
        )

    print(
        f"[false-discovery] Complete: {n_artifacts} artifacts  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    return {
        "schema_version": "cnn-false-discovery-v1",
        "cnn_model_path": str(cnn_model_path),
        "n_artifacts": n_artifacts,
        "seed": seed,
        "n_detected": n_detected,
        "n_linked": n_linked,
        "n_scored": n_scored,
        "n_false_discovery": n_false_discovery,
        "false_discovery_rate": n_false_discovery / max(n_scored, 1),
        "n_tier2_false_discovery": n_tier2_false_discovery,
        "tier2_false_discovery_rate": n_tier2_false_discovery / max(n_scored, 1),
        "limitations": [
            "Synthetic-only: artifact cutouts are constructed (unresolved "
            "spike), not real archived detections. Does not replace Gate "
            "Z4's real-archived-data false-link evidence "
            "(docs/evidence/promotion/*_false_discovery.json, derived from "
            "Skills/evaluate_ranking_baseline.py). Provided as additional, "
            "genuinely model-specific evidence answering a narrower "
            "question the real-archived-data evidence cannot: does this "
            "specific CNN's shape discrimination reject an artifact the "
            "shape-blind analytic proxy would pass on amplitude alone.",
        ],
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Real, model-specific CNN false-discovery eval")
    parser.add_argument("--cnn-model", required=True, metavar="PATH", help="Tier 2 CNN checkpoint")
    parser.add_argument("--n-artifacts", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", metavar="PATH", help="Save results as JSON to this path")
    args = parser.parse_args()

    print(
        f"CNN false-discovery evaluation: {args.n_artifacts} synthetic artifacts "
        f"(seed={args.seed}, cnn_model={args.cnn_model})",
        flush=True,
    )
    print("-" * 50, flush=True)

    results = run_false_discovery_eval(
        cnn_model_path=Path(args.cnn_model),
        n_artifacts=args.n_artifacts,
        seed=args.seed,
    )

    n = results["n_artifacts"]
    print(f"Detected: {results['n_detected']}/{n}  Linked: {results['n_linked']}/{n}")
    print(f"Scored:   {results['n_scored']}/{n}")
    print(
        f"False discoveries (full ensemble): {results['n_false_discovery']}/{results['n_scored']} "
        f"({results['false_discovery_rate']:.1%} of scored artifacts)"
    )
    print(
        f"False discoveries (Tier 2 CNN alone): "
        f"{results['n_tier2_false_discovery']}/{results['n_scored']} "
        f"({results['tier2_false_discovery_rate']:.1%} of scored artifacts)"
    )
    print("-" * 50)
    print("Done.")

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"Results saved → {args.json}")


if __name__ == "__main__":
    main()
