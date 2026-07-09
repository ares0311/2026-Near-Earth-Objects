# Live Search Policy

Live-search data means any archival or current data path used to identify
candidate objects that could enter review or submission packaging.

Required controls:

- Use ZTF DR24 archival historical replay as the primary path unless
  `docs/MISSION.md` records a newer operator decision.
- Preserve historical time ordering: candidate scoring must not depend on
  catalog facts unavailable at the replay epoch except in explicit retrospective
  validation mode.
- Every live-search batch needs a documented selection rule before execution.
- Commands expected to exceed 3 minutes must evaluate bounded parallelism or
  sharding per `docs/SYSTEM_PROFILE.md` and the repository standing rules.
- External submission remains disabled until a real candidate survives
  automated adversarial review and operator review under
  `docs/MPC_SUBMISSION_POLICY.md`.
