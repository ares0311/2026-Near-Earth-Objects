#!/usr/bin/env python
"""Injection-recovery test for the NEO detection pipeline.

Injects synthetic moving objects into a background of real observations and
measures how many are successfully detected, linked, classified, and scored.

By default (and with --image-level alone), the real_bogus score used
throughout is an analytic SNR-based proxy (see _analytic_real_bogus) --
this exercises pipeline mechanics (detect.py's threshold, link.py,
score.py) but never runs any trained CNN's real inference, since
classify.py's _tier2_predict requires a full science/reference/difference
cutout triplet that this mode never synthesizes. Found and documented
2026-07-11 while investigating whether a promoted model's injection-
recovery evidence actually reflected its own behavior (it didn't, for any
CNN candidate to date).

Pass --image-level --cnn-model <path> to synthesize full triplets and run
real inference through a specific Tier 2 CNN checkpoint (e.g.
models/tier2_cnn_v3.pt), so recovery curves and hazard-flag outcomes
reflect that model's actual classification behavior.

Usage:
    PYTHONPATH=src python Skills/injection_recovery.py [--n-inject 50] [--seed 42]
    PYTHONPATH=src python Skills/injection_recovery.py --image-level \\
        --cnn-model models/tier2_cnn_v3.pt
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np

from classify import classify, extract_features
from detect import detect
from link import link
from orbit import fit_orbit
from recovery_curves import DEFAULT_BINS, IMAGE_LEVEL_BINS, recovery_curve_report
from schemas import Observation
from score import score

# ---------------------------------------------------------------------------
# Image-level cutout synthesis (A6: seeing/background/trail-length curves)
# ---------------------------------------------------------------------------

# Pixel scale and FWHM conversion match detect.py's compute_psf_fwhm exactly,
# so a real run of that function against a synthesized cutout recovers close
# to the seeing_arcsec used to generate it.
_PIXEL_SCALE_ARCSEC_PER_PX = 1.01
_FWHM_FACTOR = 2.3548  # 2 * sqrt(2 * ln 2)
_CUTOUT_SIZE = 63

# Synthetic-harness flux zeropoint. This is NOT a calibrated ZTF zeropoint --
# it only fixes an arbitrary flux scale so that the existing 18-21 mag
# injection range and the background_level/seeing/trail ranges below produce
# a real_bogus spread that actually crosses the detect.py 0.65 threshold
# (verified empirically; see docs/PRODUCTION_READINESS.md A6 note).
_SYNTHETIC_ZEROPOINT_MAG = 26.0


def _analytic_real_bogus(
    mag: float,
    seeing_arcsec: float,
    background_level: float,
    trail_length_arcsec: float,
) -> float:
    """Derive a real_bogus proxy from the analytic peak SNR of a synthetic source.

    Models a point source of the given magnitude spread over a 2D Gaussian PSF
    (sigma from seeing_arcsec) and, if trail_length_arcsec > 0, further
    elongated along one axis to represent per-exposure trailing loss. Peak
    amplitude divided by background_level gives an SNR; SNR is mapped to
    [0, 1] with the same 5-sigma->0.5, 20-sigma->~1 formula preprocess.py's
    (private) _psf_quality helper uses, so this proxy is consistent with the
    pipeline's own real image-quality-to-score convention rather than an
    unrelated invented scale. Using the *analytic* (noise-free) amplitude
    keeps the curve a function of the swept parameters, not per-injection RNG
    noise from a single pixel draw.
    """
    if background_level <= 0:
        return 1.0
    total_flux = 10 ** (-0.4 * (mag - _SYNTHETIC_ZEROPOINT_MAG))
    sigma_px = seeing_arcsec / _PIXEL_SCALE_ARCSEC_PER_PX / _FWHM_FACTOR
    trail_px = trail_length_arcsec / _PIXEL_SCALE_ARCSEC_PER_PX
    sigma_x = math.sqrt(sigma_px**2 + (trail_px / _FWHM_FACTOR) ** 2)
    sigma_y = sigma_px
    amplitude = total_flux / (2 * math.pi * sigma_x * sigma_y)
    snr = amplitude / background_level
    return float(min(1.0, max(0.0, (snr - 3.0) / 20.0)))


def _synthesize_difference_cutout(
    rng: np.random.Generator,
    mag: float,
    seeing_arcsec: float,
    background_level: float,
    trail_length_arcsec: float,
) -> tuple[str, float]:
    """Build a synthetic 63x63 difference-image cutout and its real_bogus proxy.

    Returns (base64_encoded_cutout, real_bogus). The cutout itself carries
    genuine Gaussian pixel noise at background_level so detect.py's
    compute_psf_fwhm/compute_streak_metric measure something real; real_bogus
    is computed separately from the noise-free analytic SNR (see
    _analytic_real_bogus) so the recovery curve reflects the swept parameter,
    not single-draw noise variance.
    """
    total_flux = 10 ** (-0.4 * (mag - _SYNTHETIC_ZEROPOINT_MAG))
    sigma_px = seeing_arcsec / _PIXEL_SCALE_ARCSEC_PER_PX / _FWHM_FACTOR
    trail_px = trail_length_arcsec / _PIXEL_SCALE_ARCSEC_PER_PX
    sigma_x = math.sqrt(sigma_px**2 + (trail_px / _FWHM_FACTOR) ** 2)
    sigma_y = sigma_px
    amplitude = total_flux / (2 * math.pi * sigma_x * sigma_y)

    size = _CUTOUT_SIZE
    y, x = np.indices((size, size))
    cx, cy = size / 2.0, size / 2.0
    source = amplitude * np.exp(
        -(((x - cx) ** 2) / (2 * sigma_x**2) + ((y - cy) ** 2) / (2 * sigma_y**2))
    )
    noise = rng.normal(0.0, background_level, size=(size, size))
    arr = (source + noise).astype(np.float32)

    cutout_b64 = base64.b64encode(arr.tobytes()).decode()
    real_bogus = _analytic_real_bogus(mag, seeing_arcsec, background_level, trail_length_arcsec)
    return cutout_b64, real_bogus


def _synthesize_cutout_triplet(
    rng: np.random.Generator,
    mag: float,
    seeing_arcsec: float,
    background_level: float,
    trail_length_arcsec: float,
) -> tuple[str, str, str, float]:
    """Build science/reference/difference cutouts for real Tier 2 CNN
    inference (classify.py's _tier2_predict requires all three).

    The existing image-level harness only ever produced a difference cutout
    and derived real_bogus analytically (_synthesize_difference_cutout),
    because that was sufficient for testing detect.py's threshold and
    pipeline mechanics. It was never sufficient to exercise the trained
    CNN's own inference, since _tier2_predict returns None unless
    cutout_science, cutout_reference, and cutout_difference are all present.

    Convention (not claimed to be photometrically exact -- this is a
    synthetic harness with an arbitrary flux zeropoint, same caveat as
    _synthesize_difference_cutout): reference = pure background noise, no
    source. difference = EXACTLY what _synthesize_difference_cutout already
    produces (source + independent noise at background_level), unchanged,
    so existing analytic-real_bogus recovery curves and committed baselines
    stay reproducible. science = reference + difference, which makes
    science - reference == difference hold exactly by construction, giving
    the CNN a structurally consistent triplet even though per-pixel noise
    isn't independently drawn for science vs. difference.

    Returns (science_b64, reference_b64, difference_b64, real_bogus_proxy).
    The proxy is still computed and returned for detect.py's pre-filter
    (matching real ZTF pipelines, where detect() gates on the survey's own
    native real/bogus score, separate from this project's own CNN, which
    only runs inside classify()).
    """
    diff_b64, real_bogus = _synthesize_difference_cutout(
        rng, mag, seeing_arcsec, background_level, trail_length_arcsec
    )
    diff_arr = np.frombuffer(base64.b64decode(diff_b64), dtype=np.float32).reshape(
        _CUTOUT_SIZE, _CUTOUT_SIZE
    )
    reference_arr = rng.normal(0.0, background_level, size=(_CUTOUT_SIZE, _CUTOUT_SIZE)).astype(
        np.float32
    )
    science_arr = reference_arr + diff_arr

    reference_b64 = base64.b64encode(reference_arr.tobytes()).decode()
    science_b64 = base64.b64encode(science_arr.tobytes()).decode()
    return science_b64, reference_b64, diff_b64, real_bogus


def _make_obs(
    obs_id: str,
    jd: float,
    ra_deg: float,
    dec_deg: float,
    mag: float,
    mission: str = "ZTF",
    filter_band: str = "r",
    mag_err: float = 0.05,
    real_bogus: float | None = 0.92,
    cutout_difference: str | None = None,
    cutout_science: str | None = None,
    cutout_reference: str | None = None,
) -> Observation:
    return Observation(
        obs_id=obs_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        jd=jd,
        mag=mag,
        mag_err=mag_err,
        filter_band=filter_band,
        mission=mission,
        real_bogus=real_bogus,
        cutout_difference=cutout_difference,
        cutout_science=cutout_science,
        cutout_reference=cutout_reference,
    )


def inject_synthetic_neo(
    seed: int,
    n_nights: int = 3,
    ra0: float = 180.0,
    dec0: float = 0.0,
    motion_arcsec_per_hr: float = 1.0,
    mag: float = 19.5,
) -> tuple[Observation, ...]:
    """Generate a synthetic ZTF-cadence NEO tracklet as a sequence of observations."""
    rng = np.random.default_rng(seed)
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    obs = []
    for night in range(n_nights):
        jd_base = 2460000.5 + night
        ra_base = ra0 + night * dra_per_hr * 24
        # Two observations per night separated by 1 hr
        obs.append(
            _make_obs(
                f"inj_{seed}_n{night}a",
                jd_base,
                ra_base + rng.normal(0, 0.5 / 3600.0),
                dec0 + rng.normal(0, 0.5 / 3600.0),
                mag + rng.normal(0, 0.05),
            )
        )
        obs.append(
            _make_obs(
                f"inj_{seed}_n{night}b",
                jd_base + 1 / 24,
                ra_base + dra_per_hr + rng.normal(0, 0.5 / 3600.0),
                dec0 + rng.normal(0, 0.5 / 3600.0),
                mag + rng.normal(0, 0.05),
            )
        )
    return tuple(obs)


def inject_synthetic_neo_image_level(
    seed: int,
    n_nights: int = 3,
    ra0: float = 180.0,
    dec0: float = 0.0,
    motion_arcsec_per_hr: float = 1.0,
    mag: float = 19.5,
    seeing_arcsec: float = 1.5,
    background_level: float = 10.0,
    trail_length_arcsec: float = 0.0,
    cnn_scoring: bool = False,
) -> tuple[Observation, ...]:
    """Generate a ZTF-cadence NEO tracklet with synthesized difference cutouts.

    Same cadence as inject_synthetic_neo (2 obs/night), but each observation
    carries a real synthetic cutout_difference (see
    _synthesize_difference_cutout) built from the given seeing/background/
    trail-length, and real_bogus is derived from that cutout instead of a
    fixed constant -- so detect()'s real/bogus threshold, and detect.py's own
    compute_psf_fwhm/compute_streak_metric measurements, respond to these
    image-level parameters for A6 recovery curves.

    cnn_scoring=True additionally synthesizes cutout_science/cutout_reference
    (see _synthesize_cutout_triplet) so classify.py's _tier2_predict has the
    full triplet it requires to run real CNN inference, rather than the
    default (cnn_scoring=False) behavior of only ever populating
    cutout_difference, which _tier2_predict cannot act on. Default is False
    to keep existing committed baselines exactly reproducible.
    """
    rng = np.random.default_rng(seed)
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    obs = []
    for night in range(n_nights):
        jd_base = 2460000.5 + night
        ra_base = ra0 + night * dra_per_hr * 24
        for label, dt_hr in (("a", 0.0), ("b", 1.0)):
            obs_mag = mag + rng.normal(0, 0.05)
            if cnn_scoring:
                sci_b64, ref_b64, diff_b64, real_bogus = _synthesize_cutout_triplet(
                    rng, obs_mag, seeing_arcsec, background_level, trail_length_arcsec
                )
            else:
                diff_b64, real_bogus = _synthesize_difference_cutout(
                    rng, obs_mag, seeing_arcsec, background_level, trail_length_arcsec
                )
                sci_b64 = ref_b64 = None
            obs.append(
                _make_obs(
                    f"inj_img_{seed}_n{night}{label}",
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


def inject_synthetic_neo_wise(
    seed: int,
    ra0: float = 180.0,
    dec0: float = 0.0,
    motion_arcsec_per_hr: float = 1.0,
    mag: float = 12.0,
    n_exposures: int = 6,
    visit_span_hours: float = 54.0,
) -> tuple[Observation, ...]:
    """Generate a synthetic WISE/NEOWISE-cadence NEO tracklet.

    Source-specific cadence assumption (see docs/PRODUCTION_READINESS.md Gate
    P1 and Mainzer et al. 2014): a single NEOWISE "visit" consists of several
    single-epoch W1 exposures as the spacecraft's overlapping orbit tracks
    re-cross the same sky patch, not a paired same-night detection like ZTF.
    Visit duration depends on ecliptic latitude: near the ecliptic poles,
    continuous orbit-track overlap gives multi-day (~2-3 UTC calendar day)
    visit coverage rather than the ~1-day baseline at low ecliptic latitude
    (Mainzer et al. 2014). link.py buckets nights by `int(obs.jd)`, and a
    single seed pair can only extend to a tracklet if a third night's
    observation falls within its predicted position — so a >=3-distinct-night
    visit is used here to satisfy link.py's >=3-observation, >=2-night
    structural requirement without inventing an unphysical inter-visit (~6
    month) linear-motion assumption. Unlike ZTF, NEOWISE single-epoch
    photometry (`neowiser_p1bs_psd`) carries no real/bogus score, so
    `real_bogus` is left `None` — the pipeline's scoring model treats a
    missing score as neutral (contributes 0), not as a fabricated ZTF-style
    confidence. W1 photometric uncertainty
    (`w1sigmpro`) is typically 0.03-0.2 mag at the depths NEOs are detected;
    astrometric scatter reflects the ~1 arcsec position-fit sky in
    Mainzer et al. (2014).
    """
    rng = np.random.default_rng(seed)
    dra_per_hr = motion_arcsec_per_hr / 3600.0
    obs = []
    exposure_hours = np.linspace(0.0, visit_span_hours, n_exposures)
    # Start mid-day (2460000.6) so the multi-day visit crosses integer-JD
    # night boundaries link.py uses for night bucketing (int(obs.jd)); a
    # visit starting at midnight would shift bucket boundaries unnecessarily.
    for idx, dt_hr in enumerate(exposure_hours):
        jd = 2460000.6 + dt_hr / 24.0
        ra = ra0 + dt_hr * dra_per_hr + rng.normal(0, 1.0 / 3600.0)
        dec = dec0 + rng.normal(0, 1.0 / 3600.0)
        obs.append(
            _make_obs(
                f"inj_wise_{seed}_e{idx}",
                jd,
                ra,
                dec,
                mag + rng.normal(0, 0.08),
                mission="WISE",
                filter_band="W1",
                mag_err=0.08,
                real_bogus=None,
            )
        )
    return tuple(obs)


def _fmt_duration(seconds: float) -> str:
    """Format elapsed seconds as Mm SSs, per the standing progress-output rule."""
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


_CHECKPOINT_ROOT = Path("Logs/pipeline_runs/injection_recovery")
_CHECKPOINT_SCHEMA_VERSION = 2


def _checkpoint_key(
    n_inject: int,
    seed: int,
    mission: str,
    *,
    image_level: bool = False,
    cnn_model_path: str | None = None,
) -> str:
    """Stable checkpoint key from the exact run parameters, so re-running the
    identical command finds and resumes the existing checkpoint instead of
    starting over (checkpoint/resume standing rule).

    cnn_model_path is included deliberately: a real bug found 2026-07-11 in
    Skills/ztf_alert_archive_ingest.py showed that a checkpoint keyed
    without one of its defining parameters can silently resume with a
    *different* run's cached results under the new request's label. Two
    runs that differ only in which CNN model was scored must never share a
    checkpoint.
    """
    payload = json.dumps(
        {
            "checkpoint_schema_version": _CHECKPOINT_SCHEMA_VERSION,
            "n_inject": n_inject,
            "seed": seed,
            "mission": mission,
            "image_level": image_level,
            "cnn_model_path": cnn_model_path,
        },
        sort_keys=True,
    )
    return hashlib.md5(payload.encode()).hexdigest()[:12]


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write a checkpoint atomically (write-then-rename) so a kill mid-write
    never leaves a corrupt/unparseable checkpoint file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


def run_injection_recovery(
    n_inject: int = 20,
    seed: int = 0,
    mission: str = "ZTF",
    review_packet_out: Path | None = None,
    checkpoint_root: Path | None = None,
    image_level: bool = False,
    cnn_model_path: Path | None = None,
) -> dict:
    """Run the injection-recovery test and return summary statistics.

    ``mission="ZTF"`` uses the original two-obs-per-night ZTF cadence.
    ``mission="WISE"`` uses the single-visit, multi-exposure NEOWISE cadence
    (Gate P1 discovery-source positive control) with no native real/bogus
    score, routed through detect.py's discovery-archive singleton path.

    ``image_level=True`` (ZTF only) additionally sweeps seeing_arcsec,
    background_level, and trail_length_arcsec per injection, synthesizing a
    real difference-image cutout for each observation (see
    inject_synthetic_neo_image_level) so the A6 recovery curves cover those
    three image-level dimensions, not just mag/motion/n_observations/n_nights.

    ``cnn_model_path`` (requires image_level=True) loads that specific Tier 2
    CNN checkpoint and passes it into every classify() call, and synthesizes
    full science/reference/difference cutout triplets (not just difference)
    so classify.py's _tier2_predict actually runs real inference through
    this model rather than returning None. Without this, injection-recovery
    never exercised any CNN's live weights at all -- verified 2026-07-11 by
    reading _tier2_predict's triplet requirement and
    _analytic_real_bogus's docstring. Recovery curves and hazard-flag
    outcomes with cnn_model_path set reflect this specific model's actual
    classification behavior, not just pipeline mechanics.

    If ``review_packet_out`` is given, every recovered candidate's full
    ``ScoredNEO`` packet is written to that path as a JSON list — the same
    format ``Skills/run_pipeline.py --review-packet-out`` produces, so the
    output can feed ``Skills/adversarial_review.py`` and
    ``Skills/export_ades_report.py`` for the Gate P3 no-submission drill.

    Checkpoints after every item to ``<checkpoint_root>/<key>/checkpoint.json``
    (key derived from n_inject/seed/mission/image_level/cnn_model_path),
    including the RNG's own serializable bit-generator state, so a kill/sleep
    mid-run and re-running the identical command resumes from the next
    un-completed item instead of losing prior work or silently diverging
    from a from-scratch run. cnn_model_path is part of the key so two runs
    scoring different models never share a checkpoint.
    """
    if image_level and mission != "ZTF":
        raise ValueError("image_level=True is only supported for mission='ZTF'")
    if cnn_model_path is not None and not image_level:
        raise ValueError("cnn_model_path requires image_level=True")

    root = checkpoint_root if checkpoint_root is not None else _CHECKPOINT_ROOT
    key = _checkpoint_key(
        n_inject,
        seed,
        mission,
        image_level=image_level,
        cnn_model_path=str(cnn_model_path) if cnn_model_path else None,
    )
    checkpoint_path = root / key / "checkpoint.json"

    loaded_cnn = None
    cnn_model_sha256 = None
    if cnn_model_path is not None:
        # Import lazily -- keeps the non-CNN-scoring path free of a torch
        # dependency, matching classify.py's own lazy-import convention.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from classify import _load_cnn_model

        print(f"Loading Tier 2 CNN for real inference: {cnn_model_path}", flush=True)
        loaded_cnn = _load_cnn_model(cnn_model_path)
        if loaded_cnn is None:
            raise ValueError(
                f"cnn_model_path={cnn_model_path} could not be loaded "
                "(file missing, torch unavailable, or weights failed to load) "
                "-- refusing to silently fall back to analytic-only scoring."
            )
        digest = hashlib.sha256()
        with cnn_model_path.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest.update(chunk)
        cnn_model_sha256 = digest.hexdigest()
        print(
            "Tier 2 CNN loaded — recovery curves will reflect this model's real inference.",
            flush=True,
        )

    rng = np.random.default_rng(seed)

    n_detected = 0
    n_linked = 0
    n_scored = 0
    hazard_flags: list[str] = []
    review_packets: list[dict] = []
    injection_records: list[dict] = []
    start_i = 0

    if checkpoint_path.exists():
        state = json.loads(checkpoint_path.read_text())
        start_i = state["completed"]
        n_detected = state["n_detected"]
        n_linked = state["n_linked"]
        n_scored = state["n_scored"]
        hazard_flags = state["hazard_flags"]
        review_packets = state["review_packets"]
        injection_records = state.get("injection_records", [])
        rng.bit_generator.state = state["rng_state"]
        print(
            f"[resume] loaded checkpoint: {start_i}/{n_inject} items already "
            f"completed, continuing from item {start_i + 1}",
            flush=True,
        )

    t0 = time.monotonic()

    for i in range(start_i, n_inject):
        elapsed = time.monotonic() - t0
        # Use items completed in THIS run (not the absolute index) for the
        # rate estimate -- after a resume, i starts far above 0 while
        # elapsed restarts at 0, so dividing by i would produce a wildly
        # wrong near-zero ETA immediately after resuming.
        items_done_this_run = i - start_i
        per_item = elapsed / max(items_done_this_run, 1)
        eta = per_item * (n_inject - i)
        print(
            f"[injection] ({i + 1}/{n_inject}) mission={mission}  "
            f"detected={n_detected} linked={n_linked} scored={n_scored}  "
            f"elapsed {_fmt_duration(elapsed)}  ETA {_fmt_duration(eta)}",
            flush=True,
        )
        motion = rng.uniform(0.1, 10.0)
        ra0 = rng.uniform(0.0, 359.0)
        dec0 = rng.uniform(-30.0, 30.0)
        seeing = background = trail = None

        if mission == "WISE":
            mag = rng.uniform(10.0, 14.0)
            obs = inject_synthetic_neo_wise(
                seed=seed * 1000 + i,
                ra0=ra0,
                dec0=dec0,
                motion_arcsec_per_hr=float(motion),
                mag=float(mag),
            )
        elif image_level:
            mag = rng.uniform(18.0, 21.0)
            seeing = rng.uniform(0.8, 3.5)
            background = rng.uniform(2.0, 40.0)
            trail = rng.uniform(0.0, 8.0)
            obs = inject_synthetic_neo_image_level(
                seed=seed * 1000 + i,
                ra0=ra0,
                dec0=dec0,
                motion_arcsec_per_hr=float(motion),
                mag=float(mag),
                seeing_arcsec=float(seeing),
                background_level=float(background),
                trail_length_arcsec=float(trail),
                cnn_scoring=cnn_model_path is not None,
            )
        else:
            mag = rng.uniform(18.0, 21.0)
            obs = inject_synthetic_neo(
                seed=seed * 1000 + i,
                ra0=ra0,
                dec0=dec0,
                motion_arcsec_per_hr=float(motion),
                mag=float(mag),
            )

        detect_result = detect(obs, mpc_cross_match=False)
        detected = bool(detect_result.candidates)
        if detected:
            n_detected += 1

        link_result = link(tuple(detect_result.candidates), min_nights=2, min_observations=3)
        linked = bool(link_result.tracklets)
        scored_packet = False
        posterior_payload = None
        if linked:
            n_linked += 1

            t = link_result.tracklets[0]
            features = extract_features(t)
            orbital = fit_orbit(t)
            features_cls, posterior = classify(t, features, cnn_model=loaded_cnn)
            scored = score(t, features_cls, posterior, orbital)
            posterior_payload = posterior.model_dump(mode="json")
            n_scored += 1
            scored_packet = True
            hazard_flags.append(scored.hazard.hazard_flag)
            # Always accumulate internally (not gated on review_packet_out)
            # so a checkpoint saved on a run without --review-packet-out can
            # still be resumed correctly by a later run that requests it.
            review_packets.append(scored.model_dump(mode="json"))

        record = {
            "index": i,
            "mission": mission,
            "seed": seed * 1000 + i,
            "mag": float(mag),
            "motion_arcsec_per_hr": float(motion),
            "n_observations": len(obs),
            "n_nights": len({int(ob.jd) for ob in obs}),
            "detected": detected,
            "linked": linked,
            "scored": scored_packet,
        }
        if image_level:
            record["seeing_arcsec"] = float(seeing)
            record["background_level"] = float(background)
            record["trail_length_arcsec"] = float(trail)
        if posterior_payload is not None:
            record["posterior"] = posterior_payload
        injection_records.append(record)

        _atomic_write_json(
            checkpoint_path,
            {
                "checkpoint_schema_version": _CHECKPOINT_SCHEMA_VERSION,
                "n_inject": n_inject,
                "seed": seed,
                "mission": mission,
                "image_level": image_level,
                "cnn_model_path": str(cnn_model_path) if cnn_model_path else None,
                "completed": i + 1,
                "n_detected": n_detected,
                "n_linked": n_linked,
                "n_scored": n_scored,
                "hazard_flags": hazard_flags,
                "review_packets": review_packets,
                "injection_records": injection_records,
                "rng_state": rng.bit_generator.state,
            },
        )

    print(
        f"[injection] Complete: {n_inject} injected  "
        f"elapsed {_fmt_duration(time.monotonic() - t0)}",
        flush=True,
    )

    if review_packet_out is not None:
        review_packet_out.parent.mkdir(parents=True, exist_ok=True)
        review_packet_out.write_text(json.dumps(review_packets, indent=2))
        print(
            f"Review packets written to {review_packet_out} "
            f"({len(review_packets)} packet(s))"
        )

    recovery_curves = recovery_curve_report(
        injection_records,
        bins={**DEFAULT_BINS, **IMAGE_LEVEL_BINS} if image_level else None,
    )
    if cnn_model_path is not None:
        model_records = [
            {
                "index": record["index"],
                "posterior": record["posterior"],
                "argmax_class": max(record["posterior"], key=record["posterior"].get),
            }
            for record in injection_records
            if isinstance(record.get("posterior"), dict)
        ]
        argmax_counts = {
            label: sum(row["argmax_class"] == label for row in model_records)
            for label in (
                "neo_candidate",
                "known_object",
                "main_belt_asteroid",
                "stellar_artifact",
                "other_solar_system",
            )
        }
        recovery_curves["model_behavior"] = {
            "cnn_model_path": str(cnn_model_path),
            "cnn_model_sha256": cnn_model_sha256,
            "n_scored_posteriors": len(model_records),
            "posterior_argmax_counts": argmax_counts,
            "records": model_records,
        }

    return {
        "n_injected": n_inject,
        "mission": mission,
        "n_detected": n_detected,
        "n_linked": n_linked,
        "n_scored": n_scored,
        "cnn_model_path": str(cnn_model_path) if cnn_model_path else None,
        "cnn_scoring": cnn_model_path is not None,
        "detection_rate": n_detected / max(n_inject, 1),
        "link_rate": n_linked / max(n_inject, 1),
        "score_rate": n_scored / max(n_inject, 1),
        "hazard_flag_counts": {
            flag: hazard_flags.count(flag)
            for flag in {"pha_candidate", "close_approach", "nominal", "unknown"}
        },
        "image_level": image_level,
        "injection_records": injection_records,
        "recovery_curves": recovery_curves,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="NEO injection-recovery test")
    parser.add_argument("--n-inject", type=int, default=20, help="Number of NEOs to inject")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--survey",
        choices=["ZTF", "WISE"],
        default="ZTF",
        help="Source-native cadence to simulate. WISE uses the single-visit "
        "NEOWISE cadence for Gate P1 discovery-source positive control.",
    )
    parser.add_argument("--json", metavar="PATH", help="Save results as JSON to this path")
    parser.add_argument(
        "--review-packet-out",
        metavar="PATH",
        help="Write full ScoredNEO review packets (JSON list) to this path, "
        "consumable by Skills/adversarial_review.py and "
        "Skills/export_ades_report.py for a Gate P3 no-submission drill.",
    )
    parser.add_argument(
        "--curve-json",
        metavar="PATH",
        help="Write parameterized injection-recovery curves to this JSON path.",
    )
    parser.add_argument(
        "--checkpoint-root",
        metavar="PATH",
        help="Override checkpoint root for tests or isolated operator runs.",
    )
    parser.add_argument(
        "--image-level",
        action="store_true",
        help=(
            "Sweep seeing_arcsec/background_level/trail_length_arcsec per injection "
            "with synthesized difference-image cutouts, for A6 image-level recovery "
            "curves. Only supported with --survey ZTF."
        ),
    )
    parser.add_argument(
        "--cnn-model",
        metavar="PATH",
        help=(
            "Path to a specific Tier 2 CNN checkpoint (e.g. models/tier2_cnn_v3.pt). "
            "Requires --image-level. Synthesizes full science/reference/difference "
            "cutout triplets and loads this model for real inference inside "
            "classify(), so recovery curves and hazard-flag outcomes reflect this "
            "model's actual classification behavior -- not the analytic real_bogus "
            "proxy used by --image-level alone, which never exercises any CNN's "
            "live weights."
        ),
    )
    args = parser.parse_args()

    if args.image_level and args.survey != "ZTF":
        print(f"ERROR: --image-level is only supported with --survey ZTF, got {args.survey}")
        sys.exit(1)
    if args.cnn_model and not args.image_level:
        print("ERROR: --cnn-model requires --image-level")
        sys.exit(1)

    print(
        f"Injection-recovery test: {args.n_inject} synthetic {args.survey} NEOs "
        f"(seed={args.seed}, image_level={args.image_level}, "
        f"cnn_model={args.cnn_model or 'none (analytic proxy only)'})"
    )
    print("-" * 50)

    results = run_injection_recovery(
        n_inject=args.n_inject,
        seed=args.seed,
        mission=args.survey,
        review_packet_out=Path(args.review_packet_out) if args.review_packet_out else None,
        checkpoint_root=Path(args.checkpoint_root) if args.checkpoint_root else None,
        image_level=args.image_level,
        cnn_model_path=Path(args.cnn_model) if args.cnn_model else None,
    )

    n = results["n_injected"]
    print(f"Detection rate:  {results['detection_rate']:.1%}  ({results['n_detected']}/{n})")
    print(f"Link rate:       {results['link_rate']:.1%}  ({results['n_linked']}/{n})")
    print(f"Score rate:      {results['score_rate']:.1%}  ({results['n_scored']}/{n})")
    print()
    print("Hazard flag distribution (scored objects):")
    for flag, count in sorted(results["hazard_flag_counts"].items()):
        if count > 0:
            print(f"  {flag}: {count}")

    print("-" * 50)
    print("Done.")

    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved → {args.json}")

    if args.curve_json:
        curve_path = Path(args.curve_json)
        curve_path.parent.mkdir(parents=True, exist_ok=True)
        curve_path.write_text(json.dumps(results["recovery_curves"], indent=2))
        print(f"Recovery curves saved → {args.curve_json}")


if __name__ == "__main__":
    main()
