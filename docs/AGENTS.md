# Documentation Directives

These rules apply to everything under `docs/` in addition to the repository root
directives.

- Canonical normative content belongs under `docs/harness/`.
- Every external factual claim must cite a `SOURCE_REGISTRY.csv` claim ID that
  has passed fresh independent adversarial validation, or be marked with an
  unresolved dependency ID that blocks affected work.
- Every formula must define symbols, units, domain, invalid-input behavior,
  numerical assumptions, and the source or derivation that justifies it.
- Every algorithm must define inputs, outputs, ordering, failure behavior,
  uncertainty propagation, and determinism requirements precisely enough that a
  coding agent need not choose among materially different interpretations.
- Every business rule must name its trigger, state transition, prohibited
  transition, reason code, and retained evidence.
- Do not replace missing decisions with plausible defaults. Record them as
  blockers in `HARNESS_STATUS.md` and `configs/harness/requirements.json`.
- Specify evidence prerequisites in the order the coding agent will need them.
  No step may depend on evidence scheduled to be discovered during implementation.
- Do not describe an external package as canonical merely because it was sealed
  or independently reviewed. Import it into the repository as reference material,
  reconcile it, and identify its accepted scope.
- Keep prose compact. Prefer one canonical definition over repeated restatements
  across packets or revision narratives.

## Reference subtree

Files under `docs/harness/reference/` are immutable evidence copies. Do not edit
their content. Corrections belong in the canonical specification with a provenance
record explaining the difference.
