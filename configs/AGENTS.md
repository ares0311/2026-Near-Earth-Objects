# Configuration Directives

These rules apply to everything under `configs/` in addition to the repository
root directives.

- Configuration must be machine-readable, strictly parseable, and free of
  duplicate keys and non-finite numeric constants.
- Stable identifiers are normative. Do not silently rename, reorder when order is
  meaningful, or reuse an identifier for a different concept.
- Represent unresolved values explicitly with a status and dependency ID. Do not
  encode placeholders as executable defaults.
- Schemas must reject undeclared fields where ambiguity would change scientific,
  operational, or authority behavior.
- Units, coordinate frames, time scales, null semantics, allowed enumerations,
  and failure reason codes must be explicit.
- No configuration file may authorize implementation, data acquisition, runtime
  execution, submission, authority contact, or scientific claims while the parent
  charter status is `HARNESS_CONSOLIDATION_INCOMPLETE`.
- Keep configuration synchronized with the canonical documentation. A mismatch is
  a blocking defect, not a documentation-only issue.
