# Gate Z3 — six-tab parallel alert-archive ingest batch results (2026-07-03)

## Summary

The operator ran `Skills/ztf_alert_archive_ingest.py` against 6 candidate
nights from the systematic MPC-history scan (30/53 real hits,
`docs/evidence/live/2026-07-02-gate-z3-full-mpc-scan-30-hits.md`), split
across parallel terminal tabs. All 6 runs completed on `main` @ v0.90.47
(before the git-relay auto-push code in v0.90.48 existed), so results were
relayed via pasted console output, then backfilled into the committed
manifest via `--sync` after upgrading to v0.90.48.

All values below are real, operator-observed, either from direct console
paste or from the `--sync` checkpoint backfill run (which read the same
on-disk checkpoint state written by each of the 6 runs). No values were
invented or inferred.

## Results

| Night | RA | Dec | Remote size | Scanned | Kept | Elapsed |
|---|---|---|---|---|---|---|
| 20220817 | 257.0809 | -10.7456 | 8.0GiB | 184,654 | **267** | 10m16s |
| 20220819 | 257.5497 | -10.9843 | 11.4GiB | 264,087 | **286** | 56m19s–56m27s |
| 20191005 | 35.0025 | 9.0289 | 5.8GiB | 129,972 | 0 | 35m32s |
| 20191008 | 34.4307 | 8.6509 | 7.2GiB | 165,058 | 0 | 41m58s |
| 20210106 | 116.1336 | 8.6041 | 13.9GiB | 323,581 | **272** | 60m38s |
| 20210111 | 114.9238 | 8.8044 | 13.4GiB | 309,952 | **177** | 61m11s |

`--sync` (run post-upgrade to v0.90.48/v0.90.49) independently confirmed
these `kept` counts by reading the on-disk checkpoints, plus 5 more nights
from earlier sessions already covered in prior evidence files
(20180809 kept=21, 20180810/20180812/20180902/20180903 kept=0).

## Key finding

**First time in this project that both nights of a candidate pair have
substantial real per-source detections.** The 20220817/20220819 pair
(2 real days apart) has 267 and 286 kept observations respectively — by
far the strongest real data this project has obtained for a Gate Z3
"known-object positive control" attempt. 20210106/20210111 (5 days apart)
is a secondary candidate pair with 272 and 177 kept.

20191005 and 20191008 are real negatives (0 kept on both) despite both
being real MPC-confirmed-coverage hits from the systematic scan — this
reconfirms the previously-diagnosed "a real sci exposure existing does not
guarantee a real alert fired at that exact sub-position" finding; not
re-investigated further since 20220817/20220819 already supersedes this
pair as the primary target.

## Process defect found and fixed (v0.90.49)

The first live exercise of the v0.90.48 git-relay `--sync` path failed to
push: `git add` on the manifest file (`Logs/reports/ztf_alert_archive_ingest_manifest.jsonl`)
was rejected with "The following paths are ignored by one of your
.gitignore files." Root cause: `.gitignore`'s `Logs/**` line ignores every
path under `Logs/` recursively; the existing `!Logs/reports/` negation only
un-ignores the directory entry itself, not files inside it, so any new file
under `Logs/reports/` other than the pre-existing explicit
`!Logs/reports/.gitkeep` exception remained ignored. Fixed by widening the
exception to `!Logs/reports/**`. This means the auto-commit-and-push code
path added in v0.90.48 was never actually exercised until this real run —
the manifest mechanism is now fixed and ready for the next invocation to
verify end-to-end.

## Next step

Run the Gate Z3 "known-object positive control"
(`Skills/run_archive_positive_control.py`) against nights 20220817 and
20220819 — the first pair in this project with substantial real detections
on both nights.
