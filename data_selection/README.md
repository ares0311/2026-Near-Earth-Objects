# Data Selection Controls

This directory operationalizes
[`docs/astrometrics_data_selection_policy.md`](../docs/astrometrics_data_selection_policy.md)
for the NEO pipeline.

No agent should acquire, relabel, or promote data until the relevant role,
selection rule, leakage boundary, and decision-log entry are present here. Raw
bulk data does not belong in Git; durable summaries, manifests, queues, and
policy records do.

Current production posture:

- ZTF DR24 archival historical replay is the primary discovery path.
- WISE/DECam/TESS are preserved secondary historical paths.
- Gate Z3 candidate-pair gambling is paused unless the operator explicitly
  restarts it.
- Data roles must stay separated: training, validation, retrospective replay,
  live search, follow-up, positive control, negative control, and submission
  package evidence are not interchangeable.
