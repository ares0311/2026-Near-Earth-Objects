"""Gate Z2 -- time-aware known-object exclusion.

Per docs/neo_discovery_agent_brief.md's `known_object_catalog_snapshots` /
`known_objects` schema (verbatim field names, not invented) and its
no-future-catalog-leakage rule: "MPC data should be used in a time-aware
way. If evaluating a historical date, do not use a future catalog state to
decide whether an object was already known."

The mechanism: JPL SBDB's Query API exposes a documented `first_obs` field
per object (confirmed via the official SBDB Query API docs and a live
astroquery example showing real output, e.g. `first_obs: '1983-09-10'` --
not guessed). A single current-day catalog snapshot can therefore still be
used correctly for an arbitrary historical replay cutoff: an object counts
as "known as of" a replay date D only if its own `first_obs` is on or
before D, regardless of when the snapshot itself was fetched. This avoids
needing true point-in-time historical catalog snapshots, which neither
JPL SBDB nor MPC's verified endpoints provide.

Fail-closed policy: an object with a missing or unparseable `first_obs`
is treated as *not confirmed known* as of any cutoff -- i.e. excluded from
the "known as of D" set -- per this project's conservative-by-default rule
(never assert a stronger conclusion than the evidence supports). Callers
that use this to suppress candidates as "already known" will therefore
under-suppress on missing data, not over-suppress; a human reviewer sees
the candidate rather than having it silently discarded.

LIVE-VERIFIED (2026-07-05): appending `first_obs` to the already-verified
`sb-group=neo` query's field list was confirmed live -- real populated
dates returned for all sampled NEOs. See
docs/evidence/live/2026-07-05-gate-z2-first-obs-verified.md.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Schema models -- field names and types copied verbatim from
# docs/neo_discovery_agent_brief.md's "known_object_catalog_snapshots" and
# "known_objects" tables, not invented.
# ---------------------------------------------------------------------------


class KnownObjectCatalogSnapshot(BaseModel):
    """A single fetch of a known-object catalog (e.g. JPL SBDB), recording
    when it was fetched and the latest replay date it may be used for
    without leaking future-catalog knowledge into a historical evaluation."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    source: str  # "jpl_sbdb", "mpc", etc.
    source_url: str
    fetched_at_utc: datetime
    valid_for_replay_before_utc: datetime | None = None
    signature_version: str | None = None
    raw_payload_uri: str
    record_count: int | None = None


class KnownObject(BaseModel):
    """One object record from a KnownObjectCatalogSnapshot."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    spkid: str | None = None
    pdes: str | None = None
    full_name: str | None = None
    kind: str | None = None
    orbit_class: str | None = None
    neo: bool | None = None
    pha: bool | None = None
    moid_au: float | None = None
    h_mag: float | None = None
    epoch: float | None = None
    a_au: float | None = None
    e: float | None = None
    q_au: float | None = None
    i_deg: float | None = None
    om_deg: float | None = None
    w_deg: float | None = None
    ma_deg: float | None = None
    first_obs: date | None = None
    last_obs: date | None = None
    n_obs_used: int | None = None
    data_arc_days: float | None = None


def known_as_of(known_objects: list[KnownObject], cutoff: date) -> list[KnownObject]:
    """Return only the objects that were already known (had at least one
    recorded observation) on or before `cutoff`.

    Fail-closed: an object with `first_obs is None` is NOT included here --
    it is treated as unconfirmed-known, so it will not be used to suppress
    a candidate as "already known." This is the safe direction of error for
    a discovery-paper pipeline: a missing catalog field can cause a
    candidate to be reviewed as potentially novel when it was actually
    known (a human/adversarial-review false positive to sort out), never
    the reverse (silently discarding a genuinely novel candidate because a
    data field happened to be blank).
    """
    return [obj for obj in known_objects if obj.first_obs is not None and obj.first_obs <= cutoff]


def validate_snapshot_usable_for_replay(
    snapshot: KnownObjectCatalogSnapshot, replay_cutoff: date
) -> tuple[bool, str]:
    """Fail-closed guard on the snapshot itself, independent of per-object
    first_obs filtering. Returns (usable, reason).

    A snapshot with an explicit `valid_for_replay_before_utc` earlier than
    the requested replay cutoff must not be used -- it does not claim to
    represent catalog state through that date. A snapshot with no
    `valid_for_replay_before_utc` set is treated as unusable until that
    field is populated, rather than silently assuming it is safe.
    """
    if snapshot.valid_for_replay_before_utc is None:
        return False, "snapshot has no valid_for_replay_before_utc -- refusing to assume it is safe"
    if snapshot.valid_for_replay_before_utc.date() < replay_cutoff:
        return (
            False,
            f"snapshot is only valid for replay before "
            f"{snapshot.valid_for_replay_before_utc.date()}, requested cutoff "
            f"is {replay_cutoff}",
        )
    return True, "snapshot valid_for_replay_before_utc covers the requested cutoff"
