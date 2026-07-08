# Acquisition Policy

Data acquisition must be reproducible, bounded, and role-aware.

Required controls:

- Prefer source-native APIs and documented archive formats over scraped or
  inferred schemas.
- Before handing an operator a command, verify URLs, parameters, schemas, and
  authentication requirements from committed code, official documentation, or
  a live probe.
- Network-bound batches must checkpoint, resume, print progress with ETA, and
  write a manifest or compact evidence artifact visible to future agents.
- Raw downloads, large caches, and generated packets must remain outside Git
  unless a repository policy explicitly allowlists a compact summary.
- External-disk and cloud behavior must follow
  `docs/astrometrics_external_and_cloud_storage_policy.md`.
