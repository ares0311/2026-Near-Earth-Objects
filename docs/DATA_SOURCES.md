# Data Sources

This document describes the external data sources used by the NEO Detection & Ranking Pipeline, including access methods, cadence, data formats, and known limitations.

---

## ZTF (Zwicky Transient Facility)

| Property | Value |
|---|---|
| Access | IRSA TAP endpoint or `ztfquery` Python package |
| Coverage | Northern sky (dec > −31°) |
| Cadence | ~3 nights over full footprint |
| Bands | g, r, i |
| Depth | ~20.5 mag (r-band, 30 s) |
| Real/bogus | Native `rb` score (CNN-based, Duev et al. 2019) |

**How to access:**
```python
pip install ztfquery
from ztfquery import query as zq
```
Or via IRSA TAP:
```
https://irsa.ipac.caltech.edu/TAP/sync
```
ZTF alert packets include science, reference, and difference image cutouts (63×63 pixels) in base64-encoded FITS format.

**Key fields per alert:** `candid`, `ra`, `dec`, `jd`, `magpsf`, `sigmapsf`, `fid` (filter id: 1=g, 2=r, 3=i), `rb`, `drb` (deep real/bogus), `ssdistnr` (nearest known solar system object distance).

**Limitations:**
- IRSA account required (free registration)
- Alert stream has a ~30-day latency for full history; real-time stream requires a broker (e.g., Lasair, ALeRCE)
- Southern hemisphere not covered

---

## ATLAS (Asteroid Terrestrial-impact Last Alert System)

| Property | Value |
|---|---|
| Access | Forced Photometry Server REST API |
| Coverage | Full sky (two telescopes: Hawaii + South Africa) |
| Cadence | 2–3 nights |
| Bands | o (orange, 560–820 nm), c (cyan, 420–650 nm) |
| Depth | ~19.5 mag |
| API | `https://fallingstar-data.com/forcedphot/` |

**How to access:**
```bash
curl -X POST https://fallingstar-data.com/forcedphot/queue/ \
  -H "Authorization: Token <your_token>" \
  -d '{"ra": 180.0, "dec": 10.0, "mjd_min": 60000, "mjd_max": 60030}'
```
Free API tokens are available upon registration. The server queues photometry jobs; poll the returned URL for completion.

**Limitations:**
- No difference imaging — forced photometry at user-specified positions only
- API is asynchronous (poll-based, typically 5–30 min)
- Real/bogus score not provided

---

## MPC (Minor Planet Center)

| Property | Value |
|---|---|
| Access | `astroquery.mpc` or direct HTTP API |
| Catalog | ~1.3 million known objects (MPCs + provisional) |
| NEOs | ~35,000 known (as of 2026) |

**How to access:**
```python
from astroquery.mpc import MPC
# Query known objects in a sky region
result = MPC.query_objects_in_region(center, radius)
# Submit new observations
MPC.submit_observations(mpc_format_string)
```
The **NEO Confirmation Page (NEOCP)** lists unconfirmed candidates requiring follow-up; poll with:
```
https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html
```

**Output format:** MPC 80-column format or newer MPC JSON format. The pipeline formats all submissions with `alert.py`.

---

## JPL Horizons / CNEOS

| Property | Value |
|---|---|
| Access | `astroquery.jplhorizons` or Horizons web API |
| Purpose | Ephemerides for known objects; close-approach tables |

```python
from astroquery.jplhorizons import Horizons
obj = Horizons(id="Apophis", location="500@399",
               epochs={"start": "2029-04-13", "stop": "2029-04-14", "step": "1h"})
eph = obj.ephemerides()
```

**CNEOS Scout/Sentry:** Read-only monitoring output for impact probabilities. The pipeline does not replicate these calculations; it only flags candidates for human review and defers all impact probability assessment to CNEOS.

---

## Gaia DR3 (Astrometric Reference)

| Property | Value |
|---|---|
| Access | `astroquery.gaia` |
| Purpose | Sub-milliarcsecond astrometry for calibration |
| Release | Gaia DR3 (2022); GaiaDR4 expected ~2026 |

```python
from astroquery.gaia import Gaia
results = Gaia.query_object_async(
    coordinate=sky_coord, radius=0.1 * u.deg
)
```

Used in `preprocess.py` for astrometric correction of ZTF source positions relative to Gaia reference stars.

---

## Credential And Live Dry-Run Policy

Automated live dry-run planning is offline by default. Before any network query
is allowed, `Skills/background.py automation-readiness` checks:

| Source | Default dry-run auth |
|---|---|
| ZTF / IRSA public | no credential |
| ZTF / IRSA proprietary | optional `ZTF_IRSA_USERNAME` + `ZTF_IRSA_PASSWORD` |
| ATLAS forced photometry | required `ATLAS_TOKEN` when ATLAS is included |
| Pan-STARRS public | no credential |
| MAST authenticated access | optional `MAST_API_TOKEN` |

Use `Skills/background.py live-credential-inventory` to review required
credential names, provider mappings, local presence booleans, and storage
guidance without printing token values. The inventory checks environment
variables first and macOS Keychain service names such as
`neo-detection:ATLAS_TOKEN` second. Tokens and passwords must stay outside git.

The review contract lives in:

```text
background/live_review_policy.example.json
background/live_review_policy.schema.json
```

As of 2026-06-18, the committed policy records Jerome W. Lindsey III's bounded
live dry-run approval. It must keep `no_external_submission_confirmed` and
`no_impact_probability_claims` true and define allowed surveys, a dry-run
sky/time scope, and per-run rate limits. The readiness command validates this
policy contract and the policy schema without contacting external services. A
policy may be contract-valid and signed while live execution remains blocked by
missing credentials or provider readiness.

No live dry-run planning, readiness check, or mock provider execution contacts
external services. Use `Skills/background.py live-dry-run-plan` to inspect
planned queries, `Skills/background.py record-live-dry-run-plan` to persist the
plan to SQLite, and `Skills/background.py live-dry-run-execute` to record a
mock-only execution attempt. Injected dry-run providers must report
`network_access_performed=false` and `external_submission_enabled=false`; any
provider result that violates those fields is rejected. None of these commands
submit observations, notify external parties, or assert impact probabilities.

Provider readiness is reported per survey before any live attempt. Public ZTF
uses `fetch_ztf_alerts` without a default credential; proprietary ZTF can use
`ZTF_IRSA_USERNAME` and `ZTF_IRSA_PASSWORD`; ATLAS uses `ATLAS_TOKEN` and
`fetch_atlas_forced`; public Pan-STARRS uses `fetch_panstarrs_catalog` without a
default credential, with `MAST_API_TOKEN` treated as optional. These mappings
are readiness metadata only; they do not trigger live data retrieval.

---

## Local Cache

All fetch results are cached to disk under `.neo_cache/` to avoid repeated network requests. Cache keys are MD5 hashes of the query parameters. Cache files are plain JSON and can be inspected or deleted manually.

```
.neo_cache/
  <md5_hash>.json   # one file per unique (survey, position, time range) query
```

To clear all cached data:
```bash
rm -rf .neo_cache/
```
