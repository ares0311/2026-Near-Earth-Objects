#!/usr/bin/env python
"""Run each pipeline stage with synthetic data and report timing and status.

Provides a quick sanity check that every stage imports cleanly and returns
the expected output type, without requiring network access or real data.

Usage:
    PYTHONPATH=src python Skills/diagnose_pipeline.py
    PYTHONPATH=src python Skills/diagnose_pipeline.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _make_obs(obs_id: str = "diag_001", jd: float = 2460000.5) -> Any:
    from schemas import Observation

    return Observation(
        obs_id=obs_id,
        ra_deg=180.0,
        dec_deg=10.0,
        jd=jd,
        mag=19.5,
        mag_err=0.05,
        filter_band="r",
        mission="ZTF",
        real_bogus=0.9,
    )


def _make_tracklet(n_obs: int = 4, arc_days: float = 3.0) -> Any:
    from schemas import Tracklet

    obs = tuple(
        _make_obs(obs_id=f"d_{i}", jd=2460000.5 + i * arc_days / max(n_obs - 1, 1))
        for i in range(n_obs)
    )
    return Tracklet(
        object_id="DIAG001",
        observations=obs,
        arc_days=arc_days,
        motion_rate_arcsec_per_hour=1.2,
        motion_pa_degrees=90.0,
    )


def _run_stage(name: str, fn: Any, *args: Any, **kwargs: Any) -> dict:
    t0 = time.perf_counter()
    error: str | None = None
    result: Any = None
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "stage": name,
        "pass": error is None,
        "elapsed_ms": round(elapsed_ms, 2),
        "error": error,
        "result_type": type(result).__name__ if result is not None else None,
    }


def run_diagnostics() -> list[dict]:
    results: list[dict] = []

    # ---- preprocess ----
    def _diag_preprocess() -> Any:
        from preprocess import preprocess

        obs = tuple(_make_obs(f"p_{i}", 2460000.5 + i * 0.04) for i in range(3))
        return preprocess(obs, apply_astrometry=False)

    results.append(_run_stage("preprocess", _diag_preprocess))

    # ---- detect ----
    def _diag_detect() -> Any:
        from detect import detect
        from schemas import PreprocessProvenance, PreprocessResult

        obs = tuple(_make_obs(f"det_{i}", 2460000.5 + i * 0.04) for i in range(3))
        prep = PreprocessResult(
            observations=obs,
            provenance=PreprocessProvenance(
                n_sources_in=3,
                n_sources_out=3,
                astrometric_reference="none",
            ),
        )
        return detect(prep)

    results.append(_run_stage("detect", _diag_detect))

    # ---- link ----
    def _diag_link() -> Any:
        from link import link
        from schemas import RawCandidate

        obs_night1 = tuple(
            _make_obs(f"n1_{i}", 2460000.5 + i * 0.01)
            for i in range(3)
        )
        obs_night2 = tuple(
            _make_obs(f"n2_{i}", 2460001.5 + i * 0.01)
            for i in range(3)
        )
        obs_night3 = tuple(
            _make_obs(f"n3_{i}", 2460002.5 + i * 0.01)
            for i in range(3)
        )
        cands = tuple(
            RawCandidate(
                object_id=f"c{n}",
                observations=obs,
                detection_jd=obs[0].jd,
                survey="ZTF",
            )
            for n, obs in enumerate([obs_night1, obs_night2, obs_night3])
        )
        return link(cands)

    results.append(_run_stage("link", _diag_link))

    # ---- classify ----
    def _diag_classify() -> Any:
        from classify import classify

        return classify(_make_tracklet())

    results.append(_run_stage("classify", _diag_classify))

    # ---- classify_batch ----
    def _diag_classify_batch() -> Any:
        from classify import classify_batch

        return classify_batch([_make_tracklet(), _make_tracklet(n_obs=5)])

    results.append(_run_stage("classify_batch", _diag_classify_batch))

    # ---- orbit ----
    def _diag_orbit() -> Any:
        from orbit import arc_quality_report, fit_orbit

        t = _make_tracklet(n_obs=5, arc_days=5.0)
        report = arc_quality_report(t)
        elements = fit_orbit(t)
        return (report, elements)

    results.append(_run_stage("orbit", _diag_orbit))

    # ---- score ----
    def _diag_score() -> Any:
        from classify import classify
        from orbit import fit_orbit
        from score import score

        t = _make_tracklet()
        features, posterior = classify(t)
        orbital = fit_orbit(t)
        return score(t, features, posterior, orbital)

    results.append(_run_stage("score", _diag_score))

    # ---- score_batch ----
    def _diag_score_batch() -> Any:
        from classify import classify
        from orbit import fit_orbit
        from score import score_batch

        items = []
        for _ in range(3):
            t = _make_tracklet()
            f, p = classify(t)
            o = fit_orbit(t)
            items.append((t, f, p, o))
        return score_batch(items)

    results.append(_run_stage("score_batch", _diag_score_batch))

    # ---- alert (format_mpc_report) ----
    def _diag_alert() -> Any:
        from alert import format_mpc_json, format_mpc_report
        from classify import classify
        from orbit import fit_orbit
        from score import score

        t = _make_tracklet()
        f, p = classify(t)
        o = fit_orbit(t)
        s = score(t, f, p, o)
        return format_mpc_report(s), format_mpc_json(s)

    results.append(_run_stage("alert", _diag_alert))

    # ---- validate_mpc_report (self-test via export) ----
    def _diag_validate() -> Any:
        import tempfile

        from alert import format_mpc_report
        from classify import classify
        from orbit import fit_orbit
        from score import score
        from Skills.validate_mpc_report import validate_report  # type: ignore[import]

        t = _make_tracklet()
        f, p = classify(t)
        o = fit_orbit(t)
        s = score(t, f, p, o)
        report_text = format_mpc_report(s)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(report_text)
            tmp_path = Path(tmp.name)
        try:
            return validate_report(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    results.append(_run_stage("validate_mpc_report", _diag_validate))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose pipeline stages with synthetic data")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    stages = run_diagnostics()

    if args.json:
        print(json.dumps(stages, indent=2))
        sys.exit(0 if all(s["pass"] for s in stages) else 1)

    n_pass = sum(1 for s in stages if s["pass"])
    n_total = len(stages)
    print(f"\nPipeline Diagnostics — {n_pass}/{n_total} stages passed\n")
    print(f"{'Stage':<28} {'Status':<8} {'Time (ms)':<12} {'Result type'}")
    print("-" * 70)
    for s in stages:
        status = "PASS" if s["pass"] else "FAIL"
        rtype = s["result_type"] or "—"
        print(f"  {s['stage']:<26} {status:<8} {s['elapsed_ms']:<12.1f} {rtype}")
        if not s["pass"]:
            print(f"    ERROR: {s['error']}")
    print()
    sys.exit(0 if n_pass == n_total else 1)


if __name__ == "__main__":
    main()
