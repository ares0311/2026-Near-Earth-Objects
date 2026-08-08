"""Shared interaction and presentation layer for the NEOHunter terminal.

This package implements ``docs/CLI_UX_SPEC.md`` (``HUNTER-CLI-UX-2026-07-30.3``)
for NEOHunter. It is deliberately a *presentation and interaction* layer only:
per specification section 12 it must not duplicate candidate selection,
scientific scoring, execution, persistence, provenance, or business validation
rules. Every command it exposes resolves to ``Skills/hunter_cli.py`` argument
vectors, which remain the one canonical production pipeline.

Module map:

* ``validation`` -- canonical parameter validators shared by the interactive and
  scriptable paths (UX-IN-04).
* ``registry``   -- the command and parameter catalogue driving the palette,
  guided entry, help, and argument construction (UX-CMD-02).
* ``theme``      -- terminal capability detection and colour handling
  (UX-START-04, specification section 11).
* ``animation``  -- NEO-domain startup identity and stage-aware execution
  progress (UX-START-01/02/03, UX-RUN-01/02).
* ``table``      -- width-aware result table and target detail view
  (UX-TABLE-01/02/03).
* ``preview``    -- resolved-action preview rendered before a search is frozen
  (specification section 8).
* ``palette``    -- the searchable slash-command palette and guided parameter
  editor (UX-CMD-01/03, UX-IN-01/02/03).
"""

from __future__ import annotations

__all__ = [
    "animation",
    "palette",
    "preview",
    "registry",
    "table",
    "theme",
    "validation",
]
