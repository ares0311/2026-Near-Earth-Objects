# Storage Controls

This directory operationalizes
[`docs/astrometrics_external_and_cloud_storage_policy.md`](../docs/astrometrics_external_and_cloud_storage_policy.md)
for this repository.

Default posture:

- Keep source code, lightweight manifests, policy files, and compact evidence in
  Git.
- Keep raw archive downloads, large caches, model-training scratch files, and
  generated packets out of Git.
- Do not treat Dropbox-style synchronized folders as the scientific data store.
- Use an external SSD or explicitly configured local cache for heavy datasets
  once the operator provides a path.
- Cloud storage is optional and must be configured deliberately; do not add
  implicit sync or upload behavior.

Current status: no external SSD path is committed for this machine. Future
operator commands that require bulk storage must either use an explicit
operator-provided path or fail closed with a clear message.
