# NEO Detection & Ranking Pipeline

![CI](https://github.com/ares0311/2026-Near-Earth-Objects/actions/workflows/ci.yml/badge.svg)

Automated pipeline for detecting, linking, classifying, and ranking Near-Earth Object (NEO) candidates from publicly available survey photometry, with MPC-compatible reporting and a NASA alert pathway for high-confidence hazard signals.

## Quick Start

```bash
pip install -e ".[dev]"
PYTHONPATH=src python Skills/smoke_test.py
PYTHONPATH=src python -m pytest -q
```

## Architecture

```
Fetch → Preprocess → Detect → Link → Classify → Score → Alert
```

| Module | Description |
|---|---|
| `fetch.py` | ZTF/ATLAS/MPC data retrieval with on-disk caching |
| `preprocess.py` | Difference image handling, source extraction, Gaia astrometry |
| `detect.py` | Moving object detection; real/bogus filtering |
| `link.py` | Multi-night tracklet linking (THOR-inspired) |
| `classify.py` | XGBoost + CNN + Transformer ensemble |
| `orbit.py` | Gauss IOD, differential correction, MOID computation |
| `score.py` | Hazard ranking, PHA flag, discovery priority |
| `alert.py` | MPC 80-column report formatting; NASA PDCO alert protocol |
| `calibration.py` | Platt scaling and isotonic PAVA probability calibration |

Each stage produces a typed, immutable result object (Pydantic, `frozen=True`). No shared mutable state.

## Alert Protocol

The pipeline **never autonomously asserts a probability of Earth impact**. All hazard signals follow a mandatory three-step confirmation process (MPC submission → NEOCP independent confirmation → CNEOS Scout/Sentry) before any NASA PDCO notification. See `CLAUDE.md` for the full protocol.

## Development

```bash
ruff check .          # lint
python -m mypy src    # type-check
PYTHONPATH=src python -m pytest -q  # tests
```

Scientific context, design decisions, and module specifications are documented in [CLAUDE.md](CLAUDE.md).
