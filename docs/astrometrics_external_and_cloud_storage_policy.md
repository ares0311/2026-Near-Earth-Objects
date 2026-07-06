# Astrometrics External And Cloud Storage Policy

Date: 2026-07-05

Purpose: This file tells coding agents how to use a 4TB external SSD and optional cloud storage for the three Astrometrics projects while keeping the workflow reproducible and scientifically honest.

- `2026 Technosignatures`
- `2026 Exoplanet Research`
- `2026 Near Earth Objects`

This file complements:

- `docs/ASTROMETRICS_DETECTION_AGENT_GUIDE.md`
- `docs/ASTROMETRICS_DATA_SELECTION_POLICY.md`

## What The Agent Should Do With This File

1. Copy this file into each repo as `docs/ASTROMETRICS_EXTERNAL_AND_CLOUD_STORAGE_POLICY.md`.
2. Read this before adding external-drive paths, cloud sync, object storage, large download scripts, dataset mirrors, batch caches, or cloud compute jobs.
3. Treat the 4TB external SSD as the normal local Astrometrics workspace.
4. Treat cloud/object storage as optional infrastructure for overflow, durability, collaboration, and cloud compute.
5. Do not use Dropbox-style folder sync as the main scientific data layer.
6. Prefer manifest-driven copy/upload/download over automatic broad sync.
7. Preserve citations inline and in the bibliography. Do not move citations to a separate file.

## Core Decision

Use the **4TB external SSD** as the primary local workspace. Use cloud object storage only when it provides a clear benefit: overflow, off-laptop durability, collaboration, or running compute near cloud-hosted public archives.

Recommended architecture:

```text
public astronomy archives
  -> metadata and product manifests
  -> 4TB external SSD active workspace
  -> optional cloud object store for selected durable/overflow artifacts
  -> model/eval/candidate outputs
```

The project should not mirror entire public archives. For public raw data, store archive URIs, checksums, product metadata, and query manifests whenever possible. Pin raw copies only when the data is candidate evidence, frozen evaluation data, calibration data, expensive to reconstruct, user-approved offline working data, or at risk of changing/disappearing.

This follows industry storage best practice: inventory data first, segment by access pattern and value, manage lifecycle rules, minimize unnecessary transfer, optimize file formats, and delete or archive data that no longer needs hot access (Microsoft, "Architecture Strategies for Optimizing Data Costs").

## Local-First Recommendation

Default recommendation:

1. Use a 4TB external SSD as the primary workspace for the three repos.
2. Keep at least 500GB free for active downloads, temporary files, failed runs, and retries.
3. Store public raw archive data only as active batch cache unless it is promoted by policy.
4. Store manifests, ledgers, labels, reports, derived features, embeddings, candidate evidence, and frozen eval/calibration data on the external SSD.
5. Back up irreplaceable project state separately.
6. Add cloud/object storage later only if local-first work becomes painful.

Suggested local layout:

```text
/Volumes/Astrometrics/
  2026 Exoplanet Research/
  2026 Technosignatures/
  2026 Near Earth Objects/
  astrometrics-cache/
    exoplanets/
    technosignatures/
    near_earth_objects/
  candidate-evidence/
  frozen-eval/
  cloud-staging/
  backups-to-review/
```

The external SSD is a working drive, not a backup. It should be backed up separately if it holds anything not easily reconstructed.

## Cloud Provider Recommendation

Cloud is optional. Do not set it up until one of these is true:

1. The external SSD is running out of useful space despite eviction.
2. You need off-laptop durability for candidate evidence or frozen eval sets.
3. You need to share data between machines or collaborators.
4. You need cloud compute close to AWS-hosted MAST data.
5. You need a remote backup target for irreplaceable project state.

Default recommendation:

1. Use **AWS S3** when the project benefits from astronomy data already hosted in AWS.
2. Use **Cloudflare R2** or **Backblaze B2** when the priority is low-cost S3-compatible storage for laptop-first workflows.
3. Use Google Cloud Storage or Azure Blob Storage only if the user already has strong reasons to work inside those clouds.

| Provider | Recommended role | Why |
|---|---|---|
| AWS S3 | Primary cloud for TESS, Kepler, JWST-heavy work | MAST TESS, Kepler, and JWST public data are available through AWS Open Data S3 buckets (Registry of Open Data on AWS, "Transiting Exoplanet Survey Satellite"; Registry of Open Data on AWS, "Kepler Mission Data"; Registry of Open Data on AWS, "James Webb Space Telescope"). |
| Cloudflare R2 | Low-egress laptop cache/archive | R2 is S3-compatible, has lifecycle rules, and documents zero egress charges for both Standard and Infrequent Access classes (Cloudflare, "Pricing"; Cloudflare, "Object Lifecycles"). |
| Backblaze B2 | Low-cost durable object archive | B2 is S3-compatible object storage with lifecycle rules and API/CLI access (Backblaze, "About Backblaze B2 Cloud Storage"; Backblaze, "How to Set Lifecycle Rules on B2"). |
| Google Cloud Storage | Use if compute or accounts are already on GCP | Autoclass can automatically transition objects based on access patterns (Google Cloud, "Autoclass"). |
| Azure Blob Storage | Use if compute or accounts are already on Azure | Azure supports hot, cool, cold, archive, and smart tiering/lifecycle policies (Microsoft, "Access Tiers for Blob Data"). |

For these projects, AWS has a real scientific convenience advantage because MAST exposes TESS, Kepler, and JWST data in public S3 locations, and MAST/TIKE supports cloud-based analysis without downloading terabytes to a laptop (MAST, "TESS"; Registry of Open Data on AWS, "Transiting Exoplanet Survey Satellite"; Registry of Open Data on AWS, "Kepler Mission Data"; Registry of Open Data on AWS, "James Webb Space Telescope").

## Object Storage, Not Dropbox Sync

Do not use Dropbox, Google Drive, iCloud Drive, OneDrive, or generic sync folders as the authoritative dataset store.

Reasons:

1. Large scientific files should be addressed by immutable object keys, manifests, checksums, and roles.
2. Sync folders can accidentally download too much to the laptop.
3. Sync conflicts and hidden local state can compromise reproducibility.
4. Object storage supports lifecycle rules, access policies, checksums, versioning, and scripted batch transfer.

Dropbox-style sync may be used only for human-facing documents, notes, or exported reports under 1GB. It must not be used for raw archives, batch caches, model artifacts, or candidate evidence ledgers.

## Optional Bucket Layout

Use this section only if cloud/object storage is enabled. Use one bucket per project if possible. If using one shared bucket, use strict project prefixes.

```text
astrometrics/
  exoplanets/
    manifests/
    metadata/
    data_inventory/
    batch_manifests/
    raw_pinned/
    frozen_eval/
    calibration/
    features/
    embeddings/
    candidate_evidence/
    reports/
    models/
    logs/
  technosignatures/
    ...
  near_earth_objects/
    ...
```

Required object key pattern:

```text
{project}/{storage_class}/{role}/{dataset_id}/{version}/{filename}
```

Example:

```text
exoplanets/features/training/tess_lightcurve_features/v001/features.parquet
exoplanets/candidate_evidence/live_search/tic_123456789/v001/report.html
near_earth_objects/raw_pinned/followup_live_search/neocp_abc123/v001/cutout_001.fits
```

Do not upload files directly into a project root. Every object must live under a role-aware prefix.

## What To Store

| Artifact | Store in cloud? | Store locally? | Notes |
|---|---|---|---|
| Public archive metadata | optional cloud | yes | Keep local metadata for target queues. |
| Product manifests and query results | optional cloud | yes | These are the backbone of reproducibility. |
| Public raw archive files | usually no | active batch only | Store URI/checksum unless pinned. |
| Candidate evidence raw files | yes if cloud enabled | yes | Pin compact evidence packages. |
| Frozen eval and calibration data | yes if cloud enabled | yes | Never mutate without explicit versioning. |
| Derived features | optional cloud | yes | Prefer compressed parquet/zarr/HDF5. |
| Embeddings and ANN indexes | optional cloud | active/current versions | Store model/version metadata with them. |
| Model checkpoints | optional cloud | benchmark/released/best only | Evict scratch checkpoints. |
| Reports and ledgers | yes if cloud enabled | yes | Small and important. |
| Temporary batch files | no | yes, short-lived | Evict after processing. |

Default rule:

```text
External SSD stores active project state.
Cloud stores optional overflow/durable/shared state.
Public archive raw data is referenced, not duplicated, unless pinned by policy.
```

## Local Cache Rules

The 4TB external SSD is the active local workspace. Agents should keep at least 500GB free. If the external SSD is not mounted, agents must fall back to a conservative laptop cache and avoid large downloads.

The external SSD should contain:

1. Current batch raw files.
2. Current batch derived features.
3. Metadata inventories.
4. Current model checkpoint and frozen CNN benchmark.
5. Candidate evidence being reviewed.
6. Logs needed to reproduce the current run.

The external SSD should not contain:

1. Entire TESS sectors.
2. Broad Breakthrough Listen baseband mirrors.
3. Full survey-image mirrors for NEO work.
4. Duplicate raw files already available by URI and checksum.
5. Obsolete checkpoints or derived features.

Before starting a batch, agents must check local free space and projected download size. If projected free space after the batch is below 500GB on the 4TB SSD, abort the batch and reduce scope. If the external SSD is unavailable, use the conservative 100GB active-cache rules from the data-selection policy.

## Optional Cloud Lifecycle Policy

Use this section only if cloud/object storage is enabled. Use lifecycle rules by prefix.

Suggested lifecycle:

| Prefix | Tier | Lifecycle |
|---|---|---|
| `metadata/`, `manifests/`, `data_inventory/`, `batch_manifests/` | hot/standard | Keep current and historical versions. |
| `candidate_evidence/` | hot/standard for unresolved, cooler after resolution | Keep indefinitely unless user approves deletion. |
| `frozen_eval/`, `calibration/` | hot/standard or infrequent access | Keep indefinitely; version changes explicitly. |
| `features/`, `embeddings/` | standard then infrequent/cool | Keep current major versions; expire obsolete experimental versions after 90-180 days. |
| `models/` | standard then infrequent/cool | Keep benchmark, released, and best checkpoints; expire scratch checkpoints after 30-90 days. |
| `raw_pinned/` | standard then infrequent/cool/archive | Pin only justified raw data; archive after candidate/eval stability. |
| `logs/` | standard then expire | Keep important run logs; expire noisy debug logs after 30-90 days. |

Lifecycle rules must not delete:

1. Frozen eval data.
2. Calibration data.
3. Dataset manifests.
4. Candidate ledgers.
5. Accepted or unresolved candidate evidence.
6. Model cards and dataset cards.

Cloudflare R2, Backblaze B2, AWS S3, Google Cloud Storage, and Azure Blob Storage all support lifecycle or automatic tiering mechanisms in some form (Cloudflare, "Object Lifecycles"; Backblaze, "How to Set Lifecycle Rules on B2"; Amazon Web Services, "Managing Storage Costs with Amazon S3 Intelligent-Tiering"; Google Cloud, "Autoclass"; Microsoft, "Access Tiers for Blob Data").

## Versioning And Immutability

Enable object versioning where affordable and supported.

Rules:

1. Manifests, ledgers, frozen eval data, calibration data, candidate evidence, and model cards are versioned artifacts.
2. Never overwrite a released artifact in place. Write a new version prefix.
3. If a cloud provider keeps hidden old versions, lifecycle rules must control version buildup.
4. Every model report must cite the cloud object key/version for its data, features, embeddings, and checkpoints.

Version pattern:

```text
v001/
v002/
v003/
```

Do not use `final`, `latest`, or `new` as authoritative version names. A `latest` pointer file is allowed only if it points to an immutable version.

## Credentials And Security

Agents must not hard-code cloud credentials. If cloud is not enabled, skip cloud credentials entirely.

Required:

1. Use environment variables, local credential profiles, or secret managers.
2. Use least-privilege credentials scoped to the project bucket/prefix.
3. Use separate read-only credentials for analysis jobs that do not upload.
4. Enable server-side encryption when available.
5. Consider client-side encryption for private notes, unpublished candidate evidence, or sensitive collaboration data.
6. Do not commit `.env`, credential files, access keys, or generated signed URLs.

Suggested environment variables:

```text
ASTROMETRICS_CLOUD_PROVIDER=aws|r2|b2|gcs|azure
ASTROMETRICS_BUCKET=
ASTROMETRICS_PROJECT_PREFIX=
ASTROMETRICS_CACHE_DIR=
ASTROMETRICS_MAX_LOCAL_GB=100
ASTROMETRICS_MIN_FREE_GB=10
```

## Transfer Tooling

Agents should use normal filesystem operations for local external-drive work. Use a provider-neutral interface when cloud is enabled.

Recommended tools:

| Tool | Use |
|---|---|
| `rclone` | Provider-neutral sync/copy/check workflows across S3, B2, GCS, Azure, and many others. |
| `aws s3` / AWS SDK | Best when working directly with MAST public S3 data or AWS S3 buckets. |
| `s5cmd` | Fast S3-compatible batch copy/list workflows. |
| Provider SDK | Use only when lifecycle, inventory, or permissions require provider-specific APIs. |

Do not use automatic bidirectional sync for project data. Prefer explicit local copy or explicit cloud commands:

```text
copy metadata to/from the external SSD
copy selected batch to the external SSD
process locally
upload manifests/features/reports only if cloud is enabled
evict local raw files
```

## Public Archive Data Strategy

For TESS, Kepler, and JWST, prefer cloud-native archive access over local mirroring when possible.

| Archive data | Preferred strategy |
|---|---|
| TESS | Use MAST metadata, product lists, TIKE/cloud access, or AWS Open Data S3 paths before downloading. |
| Kepler | Use MAST/NASA archive metadata and AWS Open Data S3 paths where practical. |
| JWST | Query MAST metadata; use AWS public S3 or science-platform access for large products. |
| Breakthrough Listen | Use BL archive filters and small targeted batches; do not mirror raw/baseband broadly. |
| MPC/JPL NEO metadata | Store metadata locally/cloud; pull raw images/cutouts by target and time window. |

AWS Open Data exists specifically to reduce the burden of storing and transferring large public datasets before analysis (AWS, "Open Data on AWS"). MAST also documents TESS cloud access through TIKE and public cloud-hosted data (MAST, "TESS").

## Cloud Compute Rule

Use the laptop when:

1. The batch fits on the 4TB external SSD with at least 500GB free afterward.
2. The run can complete in reasonable time.
3. The data does not need cloud-proximate access.

Use cloud compute when:

1. The batch would require repeated downloads from public S3 archives.
2. The working set is larger than the laptop cache.
3. The job benefits from being near MAST AWS-hosted data.
4. The experiment needs GPU/large RAM.
5. The result can be reduced to compact features, embeddings, reports, or candidate evidence.

Cloud compute jobs must still write manifests and reports. A cloud notebook is not a provenance system.

## Agent Workflow

Before a large local or cloud transfer:

1. Read `ASTROMETRICS_DATA_SELECTION_POLICY.md`.
2. Confirm the dataset role.
3. Confirm acquisition mode: metadata-only, bulk, batch, stream/process/evict, or candidate evidence package.
4. Estimate download size.
5. Confirm local free space will remain above 500GB on the external SSD, or above the conservative laptop-cache threshold if the SSD is unavailable.
6. If cloud is enabled, check whether the object already exists in cloud storage.
7. Create or update the batch manifest.

After processing:

1. Save manifests, logs, derived features, candidate reports, and evidence packages to the external SSD.
2. Upload artifacts to cloud only if cloud is enabled or the artifact needs off-laptop durability.
3. Upload raw data only if it is pinned by this policy.
4. Write local paths and, if applicable, cloud object keys into the candidate ledger or model report.
5. Evict local raw files that are re-downloadable and not pinned.
6. Update `data_inventory.parquet`.

## Required Storage Artifacts

Each repo should add:

```text
storage/
  README.md
  external_drive_layout.md
  local_cache_policy.md
  cloud_bucket_layout.md
  cloud_lifecycle_policy.md
  transfer_policy.md
  example.env
  rclone.example.conf
  scripts/
    check_cache_budget.py
    inventory_cloud_prefix.py
    upload_batch_artifacts.py
    fetch_batch.py
```

`storage/README.md` must state:

1. External drive mount path.
2. Local cache directory.
3. Minimum free-space reserve.
4. Whether cloud is enabled.
5. Active cloud provider, if any.
6. Bucket name or placeholder, if any.
7. Project prefix.
8. Which prefixes are immutable.
9. Which prefixes are safe to expire.
10. How to run a dry-run transfer.

## Questions For The User

1. What exact mount path should agents expect for the 4TB external SSD?
2. Should candidate evidence and frozen eval/calibration sets be backed up to cloud immediately, or only to a separate local backup drive for now?
3. If cloud is enabled later, do you want AWS S3 because of MAST/TESS/Kepler/JWST proximity, or Cloudflare R2/Backblaze B2 because laptop downloads may be cheaper and simpler?
4. Should model checkpoints be backed up, or only benchmark/released checkpoints plus model cards?
5. Should candidate evidence be encrypted client-side before cloud upload?
6. Do you expect to run cloud compute jobs, or should cloud be storage-only if enabled?

## Bibliography

Amazon Web Services. "Managing Storage Costs with Amazon S3 Intelligent-Tiering." *Amazon Simple Storage Service User Guide*, AWS, https://docs.aws.amazon.com/AmazonS3/latest/userguide/intelligent-tiering.html. Accessed 5 July 2026.

Amazon Web Services. "Open Data on AWS." *AWS*, https://aws.amazon.com/opendata/. Accessed 5 July 2026.

Backblaze. "About Backblaze B2 Cloud Storage." *Backblaze Docs*, https://www.backblaze.com/docs/cloud-storage-about-backblaze-b2-cloud-storage. Accessed 5 July 2026.

Backblaze. "How to Set Lifecycle Rules on B2." *Backblaze Help*, https://help.backblaze.com/hc/en-us/articles/360039296494-How-to-set-Lifecycle-Rules-on-B2. Accessed 5 July 2026.

Cloudflare. "Object Lifecycles." *Cloudflare R2 Docs*, https://developers.cloudflare.com/r2/buckets/object-lifecycles/. Accessed 5 July 2026.

Cloudflare. "Pricing." *Cloudflare R2 Docs*, https://developers.cloudflare.com/r2/pricing/. Accessed 5 July 2026.

Cloudflare. "Storage Classes." *Cloudflare R2 Docs*, https://developers.cloudflare.com/r2/buckets/storage-classes/. Accessed 5 July 2026.

Google Cloud. "Autoclass." *Cloud Storage Documentation*, Google, https://docs.cloud.google.com/storage/docs/autoclass. Accessed 5 July 2026.

MAST. "TESS." *Mikulski Archive for Space Telescopes*, Space Telescope Science Institute, https://archive.stsci.edu/missions-and-data/tess. Accessed 5 July 2026.

Microsoft. "Access Tiers for Blob Data." *Azure Storage Documentation*, Microsoft Learn, https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview. Accessed 5 July 2026.

Microsoft. "Architecture Strategies for Optimizing Data Costs." *Microsoft Azure Well-Architected Framework*, Microsoft Learn, https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/optimize-data-costs. Accessed 5 July 2026.

Registry of Open Data on AWS. "James Webb Space Telescope (JWST)." *AWS Open Data Registry*, https://registry.opendata.aws/mast-jwst/. Accessed 5 July 2026.

Registry of Open Data on AWS. "Kepler Mission Data." *AWS Open Data Registry*, https://registry.opendata.aws/mast-kepler/. Accessed 5 July 2026.

Registry of Open Data on AWS. "Transiting Exoplanet Survey Satellite (TESS)." *AWS Open Data Registry*, https://registry.opendata.aws/mast-tess/. Accessed 5 July 2026.
