"""Stable read-only cross-project Hunter history interchange (IDENT-01/02).

This is NEOHunter's half of the shared interoperability contract already
implemented by EXOHunter in ``src/exo_toolkit/hunter_cross_project.py``. The
schema, verification rules, validity vocabulary, and returned payload shape are
deliberately identical; only the identity normalizer differs, because each
Hunter's targets are named in its own domain.

Why history is *copied* rather than read across repositories
------------------------------------------------------------
Contract WS-03 forbids runtime imports from sibling repositories, cross-repository
symlinks, and undocumented filesystem dependencies. So a sibling exports a
manifest, the manifest is committed **inside this repository**, and
:func:`require_repo_local_history_path` refuses any path outside it. There is no
live cross-repo dependency at runtime.

Copies could go stale, which IDENT-04 explicitly rejects as authoritative
("periodic unverified JSON copies are not authoritative novelty evidence"). That
is what the SHA-256 verification is for: when the sibling checkout is reachable,
every source artifact named in the manifest is re-hashed and compared. All
sources verified means ``valid``; otherwise ``stale-but-usable`` -- and IDENT-03
forbids ``stale-but-usable`` from justifying a known-incomplete novelty decision.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Shared across all three Hunters. Bump only alongside the siblings.
CROSS_PROJECT_SCHEMA_VERSION = 1

# The shared manifest_id every Hunter stamps on its own published export.
CROSS_PROJECT_HISTORY_MANIFEST_ID = "hunter-prior-search-history-v1"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_COPIED_HISTORY = (
    REPOSITORY_ROOT
    / "data_selection"
    / "cross_project_imports"
    / "exo_hunter_history_v1.json"
)

# Deliverable A: the single path this repository publishes its OWN history to.
# Identical relative path in all three Hunters, so a consumer resolving a
# sibling needs no per-project special casing.
DEFAULT_PUBLISH_PATH = (
    REPOSITORY_ROOT / "data_selection" / "hunter_prior_search_history_v1.json"
)

# The committed artifact that is NEOHunter's real target search history. Per
# CLAUDE.md this file -- not a table in hunter_state.sqlite -- is the system of
# record for "which sky fields has this project already searched"; the durable
# search_runs tables record individual executions, not the cumulative history.
DEFAULT_TARGET_QUEUE = REPOSITORY_ROOT / "data_selection" / "target_priority_queue.csv"

CROSS_PROJECT_HISTORY_DISCLAIMER = (
    "Cross-project Hunter search-history exports are local scheduling aids "
    "shared between independently sandboxed Astrometrics search projects. "
    "They do not constitute a detection, discovery, expert review, external "
    "validation, or authorization for external submission."
)

# Maps NEOHunter's native target_priority_queue statuses onto the shared
# cross-project status vocabulary the siblings already validate against.
#
# The native status is never discarded -- it is preserved verbatim on each entry
# as ``native_status`` -- but a sibling cannot be expected to know what
# ``insufficient_retained_coverage`` means. The mapped value is what a sibling's
# validity stamper reads:
#   * ``no_signal``  is a COMPLETED status: a real search ran over real data and
#     found nothing, which is genuine evidence the field was searched.
#   * ``no_data``    is an INVALID status: coverage was too thin to search at
#     all. Marking these invalid is the fail-closed-correct direction -- they
#     must NOT count as prior search, because no search actually happened.
_QUEUE_STATUS_TO_SHARED = {
    "null_result": "no_signal",
    "insufficient_coverage": "no_data",
    "insufficient_retained_coverage": "no_data",
}

# Rows in this state have never been searched and carry no history to publish.
_UNSEARCHED_QUEUE_STATUS = "not_searched"

# Real RA/Dec of a queue row, recorded in its free-text notes column.
_QUEUE_RA = re.compile(r"\bra_deg=(-?\d+(?:\.\d+)?)")
_QUEUE_DEC = re.compile(r"\bdec_deg=(-?\d+(?:\.\d+)?)")

# An ISO calendar date appearing in a row's notes or evidence path. This repo
# dates every piece of run evidence (docs/evidence/live/YYYY-MM-DD-*.md), so the
# date a field was searched is recoverable from committed provenance rather than
# guessed. The queue itself has no timestamp column.
_QUEUE_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")

# A provisional minor-planet designation: year, half-month letter, order letter,
# optional cycle count -- "2019 AB", "2019 AB1", "1998 QE2".
_PROVISIONAL = re.compile(r"^(\d{4})\s*([A-Z])([A-Z])(\d*)$")

# A permanent number, written bare or parenthesised: "433", "(433)".
_NUMBERED = re.compile(r"^\((\d+)\)$|^(\d+)$")


def require_repo_local_history_path(path: Path) -> Path:
    """Resolve a copied history manifest and reject every cross-repo path.

    The interchange is a committed artifact of *this* repository. A path outside
    it would reintroduce exactly the runtime cross-repository coupling WS-03
    prohibits, so it is refused rather than followed.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise ValueError(
            "cross-project history must be copied inside the active repository: "
            f"{resolved}"
        ) from exc
    if not resolved.is_file():
        raise ValueError(f"cross-project history export does not exist: {resolved}")
    return resolved


def normalize_neo_identity(value: object) -> str | None:
    """Normalize an interoperable minor-planet identity, or return ``None``.

    NEOHunter's domain counterpart to EXOHunter's TIC/HIP/KIC normalizer. Two
    spellings of the same object must collapse to one string, or novelty
    exclusion silently misses prior work: ``1998 QE2``, ``1998QE2``, and
    ``1998 qe2`` are the same object, as are ``433`` and ``(433)``.

    Returns ``None`` for anything not recognisably a minor-planet identity --
    including this repository's internal RA/Dec-derived ``target_id``, which is a
    sky position rather than an object and is meaningless to a sibling.
    """
    text = " ".join(str(value or "").strip().upper().replace("_", " ").split())
    if not text:
        return None

    numbered = _NUMBERED.match(text)
    if numbered:
        return f"({int(numbered.group(1) or numbered.group(2))})"

    compact = text.replace(" ", "")
    provisional = _PROVISIONAL.match(compact)
    if provisional:
        year, half_month, order, cycle = provisional.groups()
        # Drop a leading zero cycle so "2019 AB0" and "2019 AB" agree.
        suffix = str(int(cycle)) if cycle and int(cycle) else ""
        return f"{year} {half_month}{order}{suffix}"

    return None


# --- Federated novelty: this project plus both siblings --------------------
#
# Mirrors TechnoHunter's hunter_search.py. Novelty is a claim about every
# Astrometrics Hunter, so consulting only this repository's own export would
# establish "not searched by NEOHunter" and then report it as novelty -- the
# narrower form of the defect recorded as EXO-FIELD-01.

#: Sibling repositories, by directory name. Never includes this project.
CROSS_PROJECT_ROOT_NAMES = {
    "exo_hunter": "2026 Exoplanet Research",
    "techno_hunter": "2026 Technosignatures",
}

#: Only these two states can justify a novelty decision (IDENT-03).
CROSS_PROJECT_DECISION_STATES = frozenset({"valid", "stale-but-usable"})

#: This project's key in the federation map.
OWN_PROJECT_KEY = "neo_hunter"

#: Ranked weakest-first. Ordering decides only which state is *reported* as
#: blocking; any single non-decision-grade project closes the gate.
_HISTORY_STATE_RANK = (
    "invalid",
    "refresh-required",
    "unknown",
    "stale-but-usable",
    "valid",
)


class CrossProjectHistoryError(RuntimeError):
    """Raised when history cannot justify a novelty decision (IDENT-03)."""


def sibling_history_export_path(project: str) -> Path:
    """Resolve a sibling Hunter's live export path, relative to this repo.

    Computed from this repository's own location -- never a hardcoded absolute
    path, a symlink, a copy pulled inward, or a runtime import from a sibling
    (WS-03). A sibling that is not checked out simply yields a path that does
    not exist, which the caller resolves to ``unknown`` rather than treating as
    evidence of novelty.

    Derived from :data:`REPOSITORY_ROOT` rather than a fixed ``parents[N]``
    index, because this module sits one directory deeper than TechnoHunter's
    equivalent and a copied index would silently resolve to the wrong level.
    """
    root_name = CROSS_PROJECT_ROOT_NAMES.get(project)
    if root_name is None:
        allowed = ", ".join(sorted(CROSS_PROJECT_ROOT_NAMES))
        raise ValueError(f"unknown sibling project {project!r}; allowed: {allowed}")
    return (
        REPOSITORY_ROOT.parent / root_name / "data_selection"
        / "hunter_prior_search_history_v1.json"
    )


def load_cross_project_history_export(path: Path) -> dict[str, Any]:
    """Structural load of a published export, stamping validity **per source**.

    There is deliberately no top-level validity field: an export is only as
    trustworthy as its weakest source, and a single unverifiable source must not
    be averaged away by the others.

    A source whose artifact is present is re-hashed and is ``valid`` on match and
    ``invalid`` on mismatch. A source whose artifact is absent -- the normal case
    for an operator-copied export -- is ``stale-but-usable``: its entries stay
    visible but are never represented as freshly verified.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"cross-project history export must be a JSON object: {path}")
    if payload.get("schema_version") != CROSS_PROJECT_SCHEMA_VERSION:
        raise ValueError(
            "cross-project history export must use schema_version="
            f"{CROSS_PROJECT_SCHEMA_VERSION}: {path}"
        )
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(
            f"cross-project history export sources must be a non-empty list: {path}"
        )

    # The exporting repository's root: <repo>/data_selection/<export>.json
    export_root = path.resolve().parents[1]
    stamped: list[dict[str, Any]] = []
    for index, source in enumerate(sources, 1):
        if not isinstance(source, Mapping):
            raise ValueError(f"cross-project source {index} must be an object: {path}")
        source_path = str(source.get("source_path", "")).strip()
        source_sha256 = str(source.get("source_sha256", "")).strip()
        if not str(source.get("source_project", "")).strip() or not source_path:
            raise ValueError(f"cross-project source {index} lacks provenance: {path}")

        artifact = (export_root / source_path).resolve()
        try:
            artifact.relative_to(export_root)
        except ValueError:
            state = "invalid"
        else:
            if not artifact.is_file():
                state = "stale-but-usable"
            elif len(source_sha256) != 64:
                state = "invalid"
            elif hashlib.sha256(artifact.read_bytes()).hexdigest() != source_sha256:
                state = "invalid"
            else:
                state = "valid"
        stamped.append({**dict(source), "validity_state": state})

    return {**payload, "sources": stamped}


def cross_project_history_validity(
    history_path: Path | None = None,
) -> tuple[str, str, dict[str, Any] | None]:
    """Resolve one export's validity, degraded to its weakest source."""
    path = history_path or DEFAULT_PUBLISH_PATH
    if not path.is_file():
        return "unknown", f"absent: {path}", None
    try:
        payload = load_cross_project_history_export(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return "invalid", f"{path}: {exc}", None

    sources = payload.get("sources") or []
    states = [str(source.get("validity_state", "unknown")) for source in sources]
    if not states:
        return "unknown", f"{path}: no sources", payload
    degraded = [state for state in states if state not in CROSS_PROJECT_DECISION_STATES]
    if degraded:
        return degraded[0], f"{path}: {degraded[0]} source(s)", payload
    state = "stale-but-usable" if "stale-but-usable" in states else "valid"
    return state, f"{path}: {state} across {len(states)} source(s)", payload


def cross_project_history_federation_validity(
    history_path: Path | None = None,
) -> tuple[str, str, dict[str, tuple[str, str]]]:
    """Resolve history validity across this project **and both siblings**.

    A sibling that is not checked out, has never published, or published
    something malformed resolves to ``unknown`` -- never silently skipped, and
    never read as evidence of novelty. Absence of a label is not evidence.

    Returns ``(weakest_state, detail, per_project)``.
    """
    per_project: dict[str, tuple[str, str]] = {}
    own_state, own_detail, _ = cross_project_history_validity(history_path)
    per_project[OWN_PROJECT_KEY] = (own_state, own_detail)

    for project in sorted(CROSS_PROJECT_ROOT_NAMES):
        try:
            sibling_path = sibling_history_export_path(project)
        except ValueError as exc:  # unknown project name -- never assume novelty
            per_project[project] = ("unknown", f"unresolvable sibling: {exc}")
            continue
        # Validated by exactly the same rules as our own export: a sibling is
        # trusted neither more nor less for being remote.
        state, detail, _ = cross_project_history_validity(sibling_path)
        per_project[project] = (state, detail)

    weakest = min(
        (state for state, _ in per_project.values()),
        key=lambda state: (
            _HISTORY_STATE_RANK.index(state) if state in _HISTORY_STATE_RANK else 0
        ),
    )
    detail = "; ".join(
        f"{project}={state} ({project_detail})"
        for project, (state, project_detail) in sorted(per_project.items())
    )
    return weakest, detail, per_project


def require_decision_grade_history(
    history_path: Path | None = None,
) -> tuple[str, str]:
    """Fail closed unless cross-project history can justify a novelty decision.

    Raises before any durable state is written. Selecting targets first and
    validating afterwards would leave a frozen manifest whose novelty claim was
    never established -- the failure IDENT-03 exists to prevent.
    """
    state, detail, per_project = cross_project_history_federation_validity(history_path)
    if state not in CROSS_PROJECT_DECISION_STATES:
        blocking = sorted(
            project
            for project, (project_state, _) in per_project.items()
            if project_state not in CROSS_PROJECT_DECISION_STATES
        )
        raise CrossProjectHistoryError(
            "New eligibility requires decision-grade cross-project history from "
            f"all {len(per_project)} Astrometrics Hunter projects; weakest "
            f"validity is {state!r} from {', '.join(blocking)}. {detail}. "
            "Publish or refresh the blocking project's export "
            "(data_selection hunter_prior_search_history_v1.json), or run a "
            "follow-up search instead. New selection fails closed rather than "
            "assuming novelty (IDENT-03)."
        )
    return state, detail


def load_cross_project_history(
    path: Path | Mapping[str, Any],
    *,
    source_root: Path | None,
) -> dict[str, Any]:
    """Load and independently verify a sibling history manifest.

    ``source_root`` is the sibling checkout, when it is reachable. Given one,
    every source artifact is re-hashed and compared against the manifest's
    recorded SHA-256, and any mismatch raises rather than degrading quietly.
    Given ``None`` the entries are still usable, but the result is marked
    ``stale-but-usable`` because nothing was independently confirmed.

    Every failure path raises. A malformed or unverifiable history must not
    return a partial set that silently understates what siblings have searched --
    that would make targets look novel when they are not.
    """
    if isinstance(path, Mapping):
        payload = dict(path)
        raw = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
        manifest_path = f"inline:{payload.get('manifest_id', 'cross-project-history')}"
    else:
        if not path.is_file():
            raise ValueError(f"cross-project history export does not exist: {path}")
        raw = path.read_bytes()
        payload = json.loads(raw)
        manifest_path = str(path)

    if not isinstance(payload, Mapping) or payload.get("schema_version") != (
        CROSS_PROJECT_SCHEMA_VERSION
    ):
        raise ValueError(
            f"cross-project history must be a schema_version="
            f"{CROSS_PROJECT_SCHEMA_VERSION} object"
        )
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("cross-project history requires a non-empty sources list")

    source_hashes_verified = 0
    raw_entry_count = 0
    normalized_entries: list[dict[str, Any]] = []

    for source_index, source in enumerate(sources, 1):
        if not isinstance(source, Mapping):
            raise ValueError(f"cross-project source {source_index} must be an object")
        source_project = str(source.get("source_project", "")).strip()
        source_path = str(source.get("source_path", "")).strip()
        source_sha256 = str(source.get("source_sha256", "")).strip()
        if not source_project or not source_path:
            raise ValueError(f"cross-project source {source_index} lacks provenance")
        if len(source_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in source_sha256
        ):
            raise ValueError(f"cross-project source {source_index} has invalid SHA-256")

        if source_root is not None:
            resolved = (source_root / source_path).resolve()
            try:
                resolved.relative_to(source_root.resolve())
            except ValueError as exc:
                raise ValueError(
                    f"cross-project source escapes source root: {source_path}"
                ) from exc
            if not resolved.is_file():
                raise ValueError(f"cross-project source artifact is missing: {resolved}")
            actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
            if actual != source_sha256:
                raise ValueError(
                    f"cross-project source hash mismatch: {resolved}; "
                    f"expected={source_sha256} actual={actual}"
                )
            source_hashes_verified += 1

        entries = source.get("entries")
        if not isinstance(entries, list):
            raise ValueError(f"cross-project source {source_index} entries must be a list")
        # A source claiming to be search history with no entries at all is
        # structurally wrong, and is rejected. That is different from a source
        # whose entries simply name no target in *this* project's domain, which
        # is handled below and is legitimate.
        if not entries:
            raise ValueError(f"cross-project source {source_index} has no entries")
        raw_entry_count += len(entries)

        for entry_index, entry in enumerate(entries, 1):
            if not isinstance(entry, Mapping):
                raise ValueError(
                    f"cross-project source {source_index} entry {entry_index} "
                    "must be an object"
                )
            identities = {
                identity
                for raw_identity in (
                    entry.get("target_id"),
                    entry.get("canonical_id"),
                    *(entry.get("aliases") or ()),
                )
                if (identity := normalize_neo_identity(raw_identity)) is not None
            }
            # An entry naming no interoperable identity is skipped rather than
            # rejected: siblings legitimately search targets in domains this
            # Hunter cannot name.
            if not identities:
                continue
            searched_at = str(entry.get("searched_at", "")).strip()
            status = str(entry.get("status", "")).strip()
            if not searched_at or not status:
                raise ValueError(
                    f"cross-project source {source_index} entry {entry_index} "
                    "lacks searched_at/status"
                )
            normalized_entries.append(
                {
                    "source_project": source_project,
                    "source_search_id": str(source.get("search_id", "")),
                    "source_path": source_path,
                    "source_sha256": source_sha256,
                    "identities": sorted(identities),
                    "searched_at": searched_at,
                    "status": status,
                    "source_entry": dict(entry),
                }
            )

    # A structurally sound export whose entries name nothing in this project's
    # identity domain is NOT a failure, and must not be treated as one.
    #
    # This previously raised, which was wrong in a way that only shows up in
    # production: NEOHunter searches sky fields while both siblings search stars
    # (TIC/HIP/KIC), so neither side can EVER normalize the other's identities.
    # Raising made every sibling export permanently 'invalid', and a New-search
    # gate that fails closed on validity would therefore have deadlocked New
    # searches forever rather than transiently.
    #
    # Trustworthiness and domain overlap are different questions. This export is
    # verified; it simply reports "I have searched nothing you can name", which is
    # real, decision-grade evidence of non-overlap. Absence of a *match* is not
    # absence of *evidence* -- the export is present, hashed, and schema-checked.
    # Genuine failure modes (absent, malformed, wrong schema, unhashable source,
    # empty source) all still raise above.
    domain_disjoint = not normalized_entries

    return {
        "schema_version": CROSS_PROJECT_SCHEMA_VERSION,
        "manifest_path": manifest_path,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        # Unverified copies are usable but explicitly not authoritative (IDENT-04).
        "validity_state": (
            "valid" if source_hashes_verified == len(sources) else "stale-but-usable"
        ),
        "source_hashes_verified": source_hashes_verified,
        "source_count": len(sources),
        "entries": normalized_entries,
        # Lets a caller distinguish "sibling searched nothing I can name" from
        # "sibling searched nothing", and disclose which it was.
        "raw_entry_count": raw_entry_count,
        "interoperable_entry_count": len(normalized_entries),
        "domain_disjoint": domain_disjoint,
    }


# --------------------------------------------------------------------------
# Deliverable A: publishing THIS repository's own search history.
#
# Everything above consumes what a sibling published. Everything below produces
# what this repository publishes, so the other two Hunters can answer "has
# NEOHunter already searched this?" from evidence instead of assumption.
#
# WS-01: this half writes exactly one file, always inside this repository.
# Nothing here resolves, opens, or writes a sibling path.
# --------------------------------------------------------------------------


def _queue_searched_at(row: Mapping[str, Any]) -> str:
    """Recover the real UTC date a queue row was searched, or fail loudly.

    The queue has no timestamp column, so the date comes from the row's own
    committed provenance: the dated evidence file it cites, or a date written
    into its notes. A row that records a completed search but names no date is a
    provenance gap, not something to paper over with ``now()`` -- an invented
    timestamp would make stale history look freshly verified.
    """
    text = f"{row.get('notes', '')} {row.get('evidence_path', '')}"
    dates = sorted(set(_QUEUE_DATE.findall(text)))
    if not dates:
        raise ValueError(
            f"target queue row rank={row.get('rank')!r} status={row.get('status')!r} "
            "records a completed search but names no date in its notes or "
            "evidence_path; cannot publish it without inventing a timestamp"
        )
    # Earliest cited date is when the search happened; later dates in a row's
    # notes are follow-on analysis of that same search.
    return f"{dates[0]}T00:00:00+00:00"


def _queue_row_to_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one real, already-searched queue row into an export entry.

    Raises rather than skipping on malformed input: a silently dropped row would
    understate what this project has searched, which is the direction that makes
    an already-searched field look novel to a sibling.
    """
    native_status = str(row.get("status", "")).strip()
    shared_status = _QUEUE_STATUS_TO_SHARED.get(native_status)
    if shared_status is None:
        raise ValueError(
            f"target queue row rank={row.get('rank')!r} has status "
            f"{native_status!r}, which has no mapping onto the shared "
            f"cross-project status vocabulary {sorted(_QUEUE_STATUS_TO_SHARED)}. "
            "Add an explicit mapping rather than publishing an unlabelled status "
            "-- absence of a label is not evidence."
        )

    notes = str(row.get("notes", ""))
    ra_match = _QUEUE_RA.search(notes)
    dec_match = _QUEUE_DEC.search(notes)
    if ra_match is None or dec_match is None:
        raise ValueError(
            f"target queue row rank={row.get('rank')!r} records a completed "
            "search but its notes carry no ra_deg/dec_deg; cannot publish a "
            "target with no position"
        )
    ra_deg = float(ra_match.group(1))
    dec_deg = float(dec_match.group(1))

    # Reuse the repo's own canonical target key so a published entry and this
    # project's internal durable records name the same target identically.
    target_id = f"radec_{round(ra_deg, 2):.2f}_{round(dec_deg, 2):.2f}"

    return {
        "target_id": target_id,
        # NEOHunter searches sky fields, not catalogued objects. The field key
        # IS the canonical id here; see the module-level interoperability note.
        "canonical_id": target_id,
        "target_kind": "sky_field",
        "status": shared_status,
        "native_status": native_status,
        "searched_at": _queue_searched_at(row),
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
        "survey": str(row.get("source", "")).strip(),
        "evidence_path": str(row.get("evidence_path", "")).strip(),
    }


def build_own_history_export(
    *,
    target_queue_path: Path = DEFAULT_TARGET_QUEUE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build NEOHunter's own portable, schema_version=1 history export.

    Reads only the committed target priority queue -- this project's real system
    of record for which sky fields it has already searched -- and emits the same
    shape TechnoHunter and EXOHunter publish, so no sibling needs NEO-specific
    parsing.

    Only rows recording an actual search attempt are published. ``not_searched``
    rows are planning intent, not history, and publishing them would falsely tell
    a sibling this project had already covered ground it has not.
    """
    if not target_queue_path.is_file():
        raise ValueError(f"target priority queue not found: {target_queue_path}")

    with target_queue_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    searched = [
        row
        for row in rows
        if str(row.get("status", "")).strip()
        not in {"", _UNSEARCHED_QUEUE_STATUS}
    ]
    entries = [_queue_row_to_entry(row) for row in searched]
    if not entries:
        raise ValueError(
            f"no searched rows in {target_queue_path}; there is no real history "
            "to publish. Run a search before publishing an export -- an empty "
            "export is not decision-grade for any consumer."
        )

    # Hash the exact bytes the entries were derived from, so a consumer that can
    # reach this checkout re-hashes the same file and gets 'valid'.
    source_sha256 = hashlib.sha256(target_queue_path.read_bytes()).hexdigest()
    # Repo-root-relative, because a consumer resolves it as
    # <export_dir>/../<source_path>. An absolute path would be both unresolvable
    # for the consumer and a WS-03 violation.
    source_path = target_queue_path.resolve().relative_to(REPOSITORY_ROOT).as_posix()

    generated_at = generated_at_utc or datetime.now(UTC).isoformat()
    searched_timestamps = sorted(entry["searched_at"] for entry in entries)
    started_at = searched_timestamps[0]
    # Consumers require every entry to fall at or before completed_at. Taking the
    # max keeps that true even when an explicit generated_at is supplied for a
    # reproducible build.
    completed_at = max(generated_at, searched_timestamps[-1])

    return {
        "schema_version": CROSS_PROJECT_SCHEMA_VERSION,
        "manifest_id": CROSS_PROJECT_HISTORY_MANIFEST_ID,
        "description": (
            "NEOHunter (2026 Near Earth Objects) real prior search history, "
            "derived from the committed target priority queue. Targets are SKY "
            "FIELDS identified by rounded RA/Dec, not catalogued minor planets: "
            "this project's discovery path searches archival survey fields. A "
            "sibling matching on object identity will correctly find no overlap "
            "with these entries -- that is honest disjointness, not missing data."
        ),
        "disclaimer": CROSS_PROJECT_HISTORY_DISCLAIMER,
        "sources": [
            {
                "search_id": f"neo-hunter-target-queue-export-{generated_at}",
                "mode": "new",
                "started_at": started_at,
                "completed_at": completed_at,
                "searched_by": "NEO-Hunter",
                "source_project": "2026 Near Earth Objects",
                "method_or_data": (
                    "ZTF DR24 archival historical replay and WISE/NEOWISE "
                    "archival field sweeps; bounded pixel extraction, multi-night "
                    "tracklet linking, and adversarial candidate review"
                ),
                "source_path": source_path,
                "source_sha256": source_sha256,
                "provenance_uri": f"local-artifact:{source_path}#sha256={source_sha256}",
                "entries": entries,
            }
        ],
    }


def write_own_history_export(
    output_path: Path = DEFAULT_PUBLISH_PATH,
    *,
    target_queue_path: Path = DEFAULT_TARGET_QUEUE,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Publish this repository's own export and return a summary.

    WS-01: refuses to write anywhere outside this repository, so a mistyped or
    injected path can never turn publishing into a write into a sibling.
    """
    resolved = output_path.resolve()
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise ValueError(
            "refusing to publish outside the active repository (WS-01: a repo "
            f"never writes into a sibling): {resolved}"
        ) from exc

    payload = build_own_history_export(
        target_queue_path=target_queue_path,
        generated_at_utc=generated_at_utc,
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    entries = payload["sources"][0]["entries"]
    return {
        "ok": True,
        "schema_version": CROSS_PROJECT_SCHEMA_VERSION,
        "disclaimer": CROSS_PROJECT_HISTORY_DISCLAIMER,
        "output_path": str(resolved),
        "entry_count": len(entries),
        "unique_target_count": len({entry["target_id"] for entry in entries}),
        "source_sha256": payload["sources"][0]["source_sha256"],
    }
