# A7 grouped-split closure — 2026-07-10, fifth pass (PASSING, real data)

## Policy change (operator-approved 2026-07-10)

Per the decisive evidence in the four prior attempts in this directory
(single-night bug, object-conflict resolution bug, and a real 18-night
scale test showing simultaneous `object_id` + `night_key` + `sky_cell`
purity is structurally unachievable for ZTF's real training data),
`src/grouped_splits.py`'s `DEFAULT_HARD_GROUPS` changed from
`("object_id", "night_key", "sky_cell")` to `("object_id",)`. `night_key`
and `sky_cell` moved to a new `DEFAULT_MONITORED_GROUPS`: still computed
and reported (`monitored_leakage`, `monitored_leak_rates` in the report
JSON) but no longer block `passed`. `object_id` purity — the same physical
detection series never appearing in both train and validation/test — is
the one universal anti-leakage guarantee that remains a hard gate.

Code: `src/grouped_splits.py` (`leakage_report()` signature and logic),
tests updated in `tests/test_grouped_splits.py`
(`test_leakage_report_monitors_but_does_not_fail_night_overlap`,
`test_leakage_report_monitors_but_does_not_fail_sky_cell_overlap`
replace the old hard-fail-on-night-overlap test). Full suite: 1843 passed,
2 deselected, ruff/mypy clean.

## Real passing result

```bash
uv run --python 3.14 python Skills/train_tier2_cnn.py \
    --labels data/cutouts_v3/index.csv \
    --emit-split-csv data/cutouts_v3/grouped_split.csv
uv run --python 3.14 python Skills/validate_grouped_splits.py \
    data/cutouts_v3/grouped_split.csv > Logs/reports/tier2_cnn_v3_grouped_split_report.json
```

`Logs/reports/tier2_cnn_v3_grouped_split_report.json`:

```json
{
  "passed": true,
  "n_records": 90000,
  "split_counts": {"test": 13500, "train": 58500, "validation": 18000},
  "hard_leakage": {},
  "monitored_leak_rates": {
    "night_key": {"n_unique": 18, "n_leaking": 18, "leak_rate": 1.0},
    "sky_cell": {"n_unique": 4343, "n_leaking": 3967, "leak_rate": 0.9134}
  }
}
```

Data: 90,000 real ZTF alerts across 18 real distinct nights (2026-06-22
through 2026-07-09), 73,560 distinct real `object_id` values, ordinary
object-random splitting (the original `assign_grouped_split()`, not the
night-aware strategy — no longer needed for the sole hard gate, and gives
better per-split statistical diversity than whole-night blocks).

The disclosed `monitored_leak_rates` are the honest, expected numbers given
this session's evidence: essentially all nights and most sky cells are
revisited across splits, because that is how ZTF's survey actually behaves.
This is reported transparently in every future grouped-split report for
this project rather than hidden or gated on.

## Status

`grouped_split_report_missing` blocker: **CLOSED (real evidence, 2026-07-10)**.
This is the first genuinely passing grouped-split report for the Tier 2 CNN
on real ZTF training data. Next A7 blockers: `calibration_report_missing`
(needs an actual model retrain + `evaluate_calibration.py` run) and
`operator_signoff_missing` (inherently human-gated). The retrain step
requires PyTorch MPS/GPU acceleration per `docs/SYSTEM_PROFILE.md`'s local
compute standing rule; this sandboxed session found
`torch.backends.mps.is_available()` returns `False` here despite the
machine's Apple M4 Max GPU, so a feasibility check (small epoch-count
timing run) is needed before committing to the full 20-epoch training job.
