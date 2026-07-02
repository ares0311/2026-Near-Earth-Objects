#!/usr/bin/env python
"""Phase 0 source verification for the ZTF DR24 historical-replay pipeline.

Per docs/neo_discovery_agent_brief.md, no ingestion code may be written before
Phase 0 deliverables exist: data_sources_verified.md, auth_requirements.md.
This script probes ONLY the exact endpoints already cited in that brief's
"Concrete Starting API Calls" and "Operational Access, Download, and
Authentication Matrix" sections -- no invented URLs or schemas -- and records
the real HTTP status, headers, and a truncated response body for each.

Read-only: GET requests only, no submissions, no bulk downloads.

Usage:
    caffeinate -i uv run --python 3.14 python Skills/verify_ztf_dr24_sources.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Probe targets -- verbatim from docs/neo_discovery_agent_brief.md.
# Each entry documents which brief section it came from so results trace
# back to a specific claim, not an invented endpoint.
# ---------------------------------------------------------------------------

_PROBES: list[dict] = [
    {
        "id": "fink_schema",
        "brief_section": "Concrete Starting API Calls > Fink API Discovery",
        "url": "https://api.fink-portal.org/api/v1/schema",
        "method": "GET",
    },
    {
        "id": "fink_swagger",
        "brief_section": "Concrete Starting API Calls > Fink API Discovery",
        "url": "https://api.fink-portal.org/swagger.json",
        "method": "GET",
    },
    {
        "id": "jpl_sbdb_neo_query",
        "brief_section": "Concrete Starting API Calls > JPL SBDB Query: NEO-Only Current Catalog",
        "url": (
            "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
            "?fields=spkid,pdes,full_name,class,neo,pha,moid,H,epoch,e,a,q,i,om,w,ma"
            "&neo=Y&full-prec=true&limit=3"
        ),
        "method": "GET",
    },
    {
        "id": "mpc_get_obs",
        "brief_section": "Concrete Starting API Calls > MPC Observations API",
        "url": "https://data.minorplanetcenter.net/api/get-obs?desigs=433&output_format=XML",
        "method": "GET",
    },
    {
        "id": "irsa_ztf_sci_metadata",
        "brief_section": "Concrete Starting API Calls > IRSA ZTF Image Metadata Search",
        "url": "https://irsa.ipac.caltech.edu/ibe/search/ztf/products/sci?POS=358.3,25.6",
        "method": "GET",
    },
]

_CACHE_DIR = Path("Logs/pipeline_runs/phase0_source_verification")
_MAX_ATTEMPTS = 5
_BACKOFF_SECONDS = (2, 4, 8, 16, 32)
_BODY_PREVIEW_CHARS = 2000


def _checkpoint_path() -> Path:
    """Stable checkpoint path derived from the probe set, per the
    checkpoint/resume standing rule -- re-running the identical command
    resumes instead of re-querying already-probed endpoints."""
    key = hashlib.md5(
        json.dumps([p["id"] for p in _PROBES], sort_keys=True).encode()
    ).hexdigest()[:12]
    return _CACHE_DIR / f"checkpoint_{key}.json"


def _load_checkpoint() -> dict:
    path = _checkpoint_path()
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_checkpoint(results: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _checkpoint_path().write_text(json.dumps(results, indent=2))


def _probe_one(probe: dict) -> dict:
    """GET one endpoint with exponential-backoff retry. Returns a result dict
    with status, headers, and a truncated body -- never raises on HTTP-level
    errors (403/404/etc. are recorded as findings, not exceptions)."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(probe["url"], timeout=30)
            body_preview = resp.text[:_BODY_PREVIEW_CHARS]
            return {
                "id": probe["id"],
                "brief_section": probe["brief_section"],
                "url": probe["url"],
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body_preview": body_preview,
                "body_truncated": len(resp.text) > _BODY_PREVIEW_CHARS,
                "error": None,
            }
        except (ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc
            print(
                f"[verify] {probe['id']}: attempt {attempt}/{_MAX_ATTEMPTS} "
                f"failed ({type(exc).__name__}: {exc})",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS[attempt - 1])
    return {
        "id": probe["id"],
        "brief_section": probe["brief_section"],
        "url": probe["url"],
        "status_code": None,
        "headers": {},
        "body_preview": "",
        "body_truncated": False,
        "error": f"{type(last_exc).__name__}: {last_exc}" if last_exc else "unknown",
    }


def _fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def run_verification() -> dict:
    """Run all probes with checkpoint/resume, printing live progress and ETA.

    ETA is computed from a measurable quantity (probes completed / total),
    not an elapsed-only heartbeat, per the standing progress-output directive.
    """
    checkpoint = _load_checkpoint()
    results: dict = dict(checkpoint)
    total = len(_PROBES)
    t0 = time.monotonic()

    for i, probe in enumerate(_PROBES, start=1):
        if probe["id"] in results:
            print(
                f"[resume] ({i}/{total}) {probe['id']}: already probed, skipping",
                flush=True,
            )
            continue
        elapsed = time.monotonic() - t0
        per_probe = elapsed / max(i - 1, 1)
        eta = per_probe * (total - (i - 1))
        print(
            f"[verify] ({i}/{total}) Probing {probe['id']} -> {probe['url']}  "
            f"elapsed {_fmt_duration(elapsed)}  ETA {_fmt_duration(eta)}",
            flush=True,
        )
        result = _probe_one(probe)
        results[probe["id"]] = result
        _save_checkpoint(results)
        elapsed = time.monotonic() - t0
        per_probe = elapsed / i
        eta = per_probe * (total - i)
        status = result["status_code"] if result["status_code"] else f"ERROR: {result['error']}"
        print(
            f"[verify] ({i}/{total}) {probe['id']}: {status}  "
            f"elapsed {_fmt_duration(elapsed)}  ETA {_fmt_duration(eta)}",
            flush=True,
        )

    elapsed = time.monotonic() - t0
    print(f"[verify] Complete: {total} probe(s)  elapsed {_fmt_duration(elapsed)}", flush=True)
    return results


def _write_reports(results: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / "phase0_probe_results.json"
    raw_path.write_text(json.dumps(results, indent=2))

    sources_lines = [
        "# data_sources_verified.md",
        "",
        "Phase 0 source verification per docs/neo_discovery_agent_brief.md.",
        "Generated by Skills/verify_ztf_dr24_sources.py -- every row below is a",
        "real HTTP response observed at the timestamp this file was written,",
        "not an assumption from the brief text.",
        "",
        "| Probe | Brief section | URL | HTTP status | Notes |",
        "|---|---|---|---|---|",
    ]
    auth_lines = [
        "# auth_requirements.md",
        "",
        "Phase 0 auth verification per docs/neo_discovery_agent_brief.md.",
        "",
        "| Probe | Auth required? | Evidence |",
        "|---|---|---|",
    ]

    for probe in _PROBES:
        r = results.get(probe["id"], {})
        status = r.get("status_code")
        note = ""
        if status is None:
            note = f"probe failed: {r.get('error', 'unknown')}"
        elif status in (401, 403):
            note = "server rejected the request -- may require auth or block automated clients"
        elif status == 200:
            note = "reachable without credentials"
        else:
            note = f"HTTP {status} -- see phase0_probe_results.json for full body"

        sources_lines.append(
            f"| {probe['id']} | {probe['brief_section']} | {probe['url']} "
            f"| {status if status is not None else 'ERROR'} | {note} |"
        )

        auth_note = "unknown (probe failed)" if status is None else (
            "possibly required" if status in (401, 403) else "not required for this GET"
        )
        auth_lines.append(f"| {probe['id']} | {auth_note} | HTTP {status} observed |")

    (out_dir / "data_sources_verified.md").write_text("\n".join(sources_lines) + "\n")
    (out_dir / "auth_requirements.md").write_text("\n".join(auth_lines) + "\n")

    print(f"[verify] Wrote {out_dir / 'data_sources_verified.md'}", flush=True)
    print(f"[verify] Wrote {out_dir / 'auth_requirements.md'}", flush=True)
    print(f"[verify] Wrote {raw_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default="docs/evidence/phase0",
        metavar="DIR",
        help="Directory to write data_sources_verified.md and auth_requirements.md",
    )
    args = parser.parse_args()

    results = run_verification()
    _write_reports(results, Path(args.out_dir))


if __name__ == "__main__":
    main()
