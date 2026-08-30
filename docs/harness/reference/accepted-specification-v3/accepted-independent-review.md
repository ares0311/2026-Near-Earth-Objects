# NEO Harness Specification Revision 3 — Independent Adversarial Revalidation

## Verdict

`SPECIFICATION_ACCEPTED_AFTER_INDEPENDENT_REVIEW`

Every required gate passed for the exact frozen Revision 3 identity. This acceptance is bound only to complete-manifest SHA-256 `6825a1cce0c649ae7151f9dcda4a6725bc82ff7235a97f89f3212cff90d902fb` and digest-record SHA-256 `9ac8fa3c7e55ffc6f6364cb8a673de2a119be01880b3ad676e8920aa6c02570b`.

It does not establish scientific effectiveness, operational fitness, implementation readiness, benchmark performance, production authority, deployment authority, search authority, submission authority, permission to contact authorities, or any impact claim.

## Gate 1 — identity and preservation preflight

- The fresh output root was absent before work.
- Revision 3, Revision 2 and its controlling review, Revision 1 and its controlling review, and the initiation checkpoint all match the supplied SHA-256 anchors.
- All five complete manifests replay exactly against complete recursive no-follow `lstat` inventories; the checkpoint's six declared files replay exactly.
- Strict JSON/JSONL/CSV parsing, duplicate-key/header/width checks, safe-path checks, and entry-type checks pass.
- All ten accepted dependency roots and the continuity-only root match their pinned manifest SHA-256, complete inventory SHA-256, and entry counts.
- The independent before-state covers 17 roots and 532 entries: 16 protected source roots with 512 entries plus the 20-entry Revision 3 target.

## Gate 2 — exact Revision 2 to Revision 3 surface

The only normative field changes are: `revision_header.title, revision_header.revision_basis, section_10_1.implicated_paragraph, section_13.reviewer_handoff_contract, section_19.handoff_wording, REQ-044.normative_requirement`. All 47 non-REQ-044 requirement rows are unchanged; only `REQ-044.normative_requirement` changed within REQ-044. The OQ and IR files are byte-identical to Revision 2. No unauthorized normative change was found in the specification, reports, ledgers, or handoff.

## Gate 3 — four controlling findings

- Revision 1 `CE-G0-verdict-bypass.json`: `PASS_RETAINED_RESOLVED` across exactly seven cases. Only the exact accepting verdict from a fresh role-separated review bound to the exact bytes advances, and only to G1.
- Revision 1 `CE-IR016-G10-deadlock.json`: `PASS_RETAINED_RESOLVED` across exactly ten cases. IR-016 remains `INTENTIONALLY_DEFERRED` at `post-G10`, blocks only final production selection, and does not deadlock a separately authorized bounded G9/G10 evidence path.
- `CE-R2-SCOPE-10.1-NORMATIVE-EXPANSION`: `PASS_REMEDIATED`. The paragraph exactly equals Revision 1 after changing only `v1` to `v3`.
- `CE-REQ044-SECTION13-HANDOFF-CONTRADICTION`: `PASS_REMEDIATED_IDENTICAL`. REQ-044 and Section 13 contain the same exact four-item initial-review and five-item remediation-revalidation contract, including the pinned Revision 2 review identity and `REVISIONS_REQUIRED` verdict.

## Gates 4 and 5 — registers, ceilings, and prohibitions

- Requirements: 48 unique sequential IDs; 34 `SPECIFIED_COMPLETE`, 14 `SPECIFIED_INCOMPLETE`.
- Open questions: 16 unique sequential IDs; OQ-01 through OQ-15 `UNRESOLVED`, OQ-16 `UNRESOLVED_HISTORICAL_PROVENANCE_LIMITATION`.
- Incomplete requirements: 16 unique sequential IDs; IR-001 through IR-015 `INCOMPLETE`, IR-016 `INTENTIONALLY_DEFERRED` at `post-G10`.
- The eight objectives, ten excluded objectives, seven method branches and baselines, accepted NEO-001/002/003 ceilings, all required regime separations, honest gap states, and scientific/authority prohibitions are retained.

## Gate 6 — fresh semantic attacks and controls

Exactly 34 fresh attack/control pairs ran on disposable complete-root copies: the exact 30 controlling Revision 2 families plus four targeted Revision 3 pairs. Every unsafe case was rejected for its intended semantic invariant; every matched control retained only its legitimate bounded status or next-gate scope. Semantic bypasses: 0. Matched-control regressions: 0.

## Gate 7 — final preservation

The independent after-state is byte-identical to the before-state: 17 roots, 532 entries, inventory SHA-256 `b1c2e92d1aea64ef2b6cae8d27a67907e55ae38432b4ec60e3263c4797d0b240`, with no missing, extra, changed, redirected, ambiguous, symlinked, or other non-regular entry.

No source repair, implementation, dry run, benchmark, production or live search, data acquisition, submission, public alert, authority contact, impact analysis or claim, commit, push, publication, or downstream initiation occurred.
