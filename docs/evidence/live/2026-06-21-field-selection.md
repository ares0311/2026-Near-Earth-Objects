# Field Selection for Live Recovery Run — 2026-06-21

## Command

```
uv run python Skills/select_survey_fields.py \
    --jd now \
    --mode recovery \
    --top-n 5 \
    --json
```

## Context

JD 2461213.44 (2026-06-21). Sun at RA=90.2° Dec=23.4°.
Observer lat: 33.36°N. 579 candidate fields scored; 122 observable.

## Results

| Rank | RA (°) | Dec (°) | Score | Elongation (°) | Ecl lat (°) | Hours vis |
|------|--------|---------|-------|----------------|-------------|-----------|
| 1 | 284.13 | -22.5 | 0.9527 | 167.2 | 0.3 | 4.7 |
| 2 | 251.66 | -22.5 | 0.9497 | 162.9 | -0.1 | 4.7 |
| 3 | 259.77 | -22.5 | 0.9429 | 170.3 | 0.6 | 4.7 |
| 4 | 276.01 | -22.5 | 0.9250 | 174.6 | 0.8 | 4.7 |
| 5 | 292.25 | -22.5 | 0.9237 | 159.7 | -0.6 | 4.7 |

All fields: Dec=-22.5° (within ZTF southern limit of ~-28°), near opposition,
on the ecliptic (ecl_lat < 1°), in the Sagittarius/Ophiuchus region.
Field radius: 3.5°.

## Selected Field for Next Run

**Rank 1: RA=284.13°, Dec=-22.5°**
- Known-object density score: 0.96 (highest in set)
- Geometry: 0.92 (optimal elongation 167.2°)
- JD window for run: 2461206.0 – 2461213.0 (7 days ending today)
