# Gate Z3 — third candidate pair (20191030/20191101, same-station I41): one real negative, one strong positive

## Commands and real results

```bash
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20191030 --ra 29.6558 --dec 5.8706 --radius-deg 2.0 --min-rb 0.5
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20191101 --ra 29.2335 --dec 5.6456 --radius-deg 2.0 --min-rb 0.5
```

Real results (both real, non-mocked downloads via the git-relay-enabled
`ztf_alert_archive_ingest.py`, `main` @ v0.90.56):

| Night | Remote size | Scanned | Kept |
|---|---|---|---|
| 20191030 | 5.7GiB | 128,214 | **0** |
| 20191101 | 10.2GiB | 227,496 | **234** |

## Interpretation

Even with the improved same-station (`I41`, both nights) selection
criterion from
`docs/evidence/live/2026-07-04-gate-z3-observatory-filtered-scan-35-hits.md`,
night 20191030 still returned zero kept observations at `rb >= 0.5` in
the 2-degree search box. This is consistent with the previously
established finding that real sci-exposure/MPC-report coverage existing
does not guarantee a confident alert-level detection was generated at
that exact sub-position that night -- the same-station filter improves
confidence that both reports are genuine ZTF-associated detections, but
does not guarantee ZTF's difference-imaging pipeline produced an
`rb >= 0.5` alert there specifically.

Night 20191101's strong positive (234 kept) is itself a real, useful
result, but a positive control needs **both** nights to have data --
this specific pair cannot support one.

## Next step (NOT YET DONE)

Try the backup same-station candidate identified in the same scan:
**20210105/20210111** (both real `G96` reports, 6 days apart):

```bash
git checkout -- uv.lock
git pull origin main
export PYTHONPATH=src
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20210105 \
    --ra 116.3469 --dec 8.5736 --radius-deg 2.0 --min-rb 0.5
caffeinate -i uv run --python 3.14 python Skills/ztf_alert_archive_ingest.py \
    --nights 20210111 \
    --ra 114.9265 --dec 8.8038 --radius-deg 2.0 --min-rb 0.5
```

Note: 20210111 was already ingested earlier this session from a slightly
different reference position (114.9238/8.8044, kept=177) -- this new
attempt uses 20210111's *own* real MPC-report position (114.9265/8.8038)
from this same-station pairing, which differs by only a few arcsec, so
the existing checkpoint will very likely resume/match; only 20210105 is
a genuinely new ingest.
