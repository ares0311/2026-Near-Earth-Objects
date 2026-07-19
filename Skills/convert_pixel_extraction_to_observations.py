#!/usr/bin/env python
"""Convert a Skills/ztf_dr24_bounded_ingest.py --pixel-extraction-pilot
checkpoint into the per-night Observation checkpoint format that
Skills/run_archive_positive_control.py already consumes
(<out-dir>/<night>.json, `{"observations": [...], "kept_count": N}`).

This is glue between two already-real, already-tested pipeline stages: the
source-native pixel extractor (this session's motion-product-pivot work)
and the existing preprocess -> detect -> link chain that
run_archive_positive_control.py already exercises against real archived
alert data. It does not reimplement linking -- it only reshapes data so the
existing tool can be reused unmodified.

Photometry caveat, stated plainly rather than overclaimed: this pixel
extractor has no calibrated zeropoint. The `mag` field is a rough
uncalibrated proxy (`_PLACEHOLDER_ZEROPOINT - 2.5*log10(peak_value)`) so the
required Observation schema field is populated with *something*
real-derived rather than a fabricated placeholder, but it must not be
treated as real calibrated ZTF photometry. The zeropoint constant is an
arbitrary, disclosed placeholder chosen only to land typical peak values in
a physically plausible ZTF magnitude range (~15-22) -- `preprocess()`
itself hard-rejects any observation with `mag <= 0` or `mag > 35`
(src/preprocess.py's basic quality cuts), which a raw zeropoint-free
`-2.5*log10(peak_value)` fails for every realistic peak value (root-caused,
not guessed: the first real run of this converter produced 0/471 passing
observations for exactly this reason). `real_bogus`/`deep_real_bogus` are
left None (no such score exists for these candidates) -- detect.py's own
`_passes_real_bogus()` already handles a None score by passing it through
conservatively rather than rejecting it, matching the project's existing
policy for non-native sources. The source-native Pearson PSF correlation is
preserved separately as `psf_shape_correlation`; it is not copied into an rb
field because no calibration currently justifies treating it as a probability.

Usage:
    uv run --python 3.14 python Skills/convert_pixel_extraction_to_observations.py \\
        --pilot-checkpoint Logs/pipeline_runs/ztf_dr24_bounded_ingest/<run>/\\
pixel_extraction_pilot.json \\
        --manifest Logs/pipeline_runs/ztf_dr24_bounded_ingest/<run>/\\
motion_product_manifest.json \\
        --night 20180809 \\
        --out-dir Logs/pipeline_runs/ztf_dr24_pixel_extraction_positive_control
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

# No real calibration exists for the pixel extractor's raw peak values;
# this fixed magnitude-error placeholder is disclosed, not fabricated
# precision -- it must never be read as a measured uncertainty.
_PLACEHOLDER_MAG_ERR = 0.5

# Arbitrary, disclosed placeholder zeropoint (not a real ZTF calibration)
# chosen only so realistic difference-image peak values (tens to low
# thousands, ADU-like units) map to physically plausible ZTF magnitudes
# (~15-22), landing inside preprocess()'s hard 0 < mag <= 35 gate.
_PLACEHOLDER_ZEROPOINT = 25.0


def convert(pilot_path: Path, manifest_path: Path) -> dict:
    """Return {"observations": [...], "kept_count": N} built from one
    pixel-extraction-pilot checkpoint and its sibling motion-product
    manifest (for the real obsjd/filtercode this pilot checkpoint itself
    does not store)."""
    pilot = json.loads(pilot_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    exposure = manifest["exposures"][0]
    obsjd = float(exposure["obsjd"])
    filtercode = str(exposure["filtercode"])
    # ZTF filtercodes are "z" + band letter (zg/zr/zi); Observation.filter_band
    # elsewhere in this project uses the bare band letter.
    filter_band = filtercode[-1] if filtercode else "r"

    observations = []
    for source in pilot["sources"]:
        peak = max(float(source["peak_value"]), 1e-6)
        mag_proxy = _PLACEHOLDER_ZEROPOINT - 2.5 * math.log10(peak)
        observations.append(
            {
                "obs_id": f"pixel_{pilot['pid']}_{source['x']}_{source['y']}",
                "ra_deg": source["ra_deg"],
                "dec_deg": source["dec_deg"],
                "jd": obsjd,
                "mag": mag_proxy,
                "mag_err": _PLACEHOLDER_MAG_ERR,
                "filter_band": filter_band,
                "mission": "ZTF",
                "psf_shape_correlation": source.get("psf_correlation"),
            }
        )
    return {"observations": observations, "kept_count": len(observations)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pilot-checkpoint", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--night", required=True, help="YYYYMMDD; names the output checkpoint file."
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    result = convert(args.pilot_checkpoint, args.manifest)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.night}.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(
        f"[convert] {args.night}: wrote {result['kept_count']} observation(s) to {out_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
