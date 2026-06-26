# Near Earth Objects: Satellite, AI, and Literature Brief for Coding Agents

Last updated: 2026-06-26

## Mission Objective

Build software that can ingest public survey data, detect or recover moving objects, prioritize near-Earth object (NEO) candidates, link observations into tracklets/orbits, and support planetary-defense research. Treat space assets as one part of the pipeline: most operational NEO discovery still depends on ground surveys plus orbit linking, while space telescopes add infrared sensitivity, solar-elongation access, and unbiased physical characterization.

## Ranked Space Assets and Satellites

Ranking criteria: direct NEO relevance, discovery power, characterization value, data access, algorithmic value, and current/future operational importance.

| Rank | Asset | Status | Best Use | Why It Ranks Here | Data / Access |
|---:|---|---|---|---|---|
| 1 | NASA NEO Surveyor | Future, launch no earlier than 2027 | Dedicated infrared discovery of hazardous NEOs | First space telescope designed specifically to discover and characterize potentially hazardous asteroids and comets. It will operate near Sun-Earth L1 and survey closer to the Sun than ground surveys can usually handle. Expected discovery yield is roughly 200,000-300,000 new NEOs down to small sizes, with a primary requirement focused on objects larger than 140 m. | Mission page and papers now; science archive/data products after launch. |
| 2 | WISE / NEOWISE | Ended; archival | Infrared asteroid diameters, albedos, population studies, historical detections | The most important existing public space-IR asteroid survey archive. NEOWISE produced infrared detections for more than 158,000 minor planets and tens of thousands of discoveries. Essential for thermal modeling and debiasing. | IRSA WISE/NEOWISE catalogs, images, coadds, time-series tools. |
| 3 | ESA Gaia | Science operations ended 2025; archive continuing | Precision astrometry, orbit improvement, asteroid reflectance spectra | Gaia DR3 contains astrometry/photometry for more than 150,000 Solar System objects and spectra for more than 60,000 small bodies. It is not optimized for NEO discovery but is extremely valuable for orbit refinement and population science. | ESA Gaia Archive via TAP/ADQL and `astroquery.gaia`; anonymous and registered use. |
| 4 | ESA Euclid | Active | Serendipitous asteroid streaks; multiband photometry/spectra | Not a planetary-defense mission, but simulations suggest up to roughly 150,000 asteroid detections in Euclid images. Valuable for deep-learning streak detection and faint-object pipelines. | Euclid data releases through ESA archive; some proprietary periods may apply. |
| 5 | Hubble Space Telescope | Active/legacy | Archival asteroid trails, high-resolution characterization | Not a survey instrument, but archival HST images contain asteroid trails useful for ML detection and characterization. Hubble Asteroid Hunter style data are useful for training. | MAST public archive; proprietary windows for new observations. |
| 6 | JWST | Active | Physical characterization of selected small bodies | Not suitable for wide NEO survey, but powerful for spectroscopy/thermal characterization of selected targets. High proposal burden and sparse cadence. | MAST archive; GO proposal required for new data. |
| 7 | ESA Hera | En route / active mission | Planetary-defense validation at Didymos/Dimorphos | Not a survey satellite. Important for impact-physics validation after DART, shape modeling, surface properties, and deflection science. | Mission data via ESA archives after release. |
| 8 | NASA DART / LICIACube | Completed | Deflection experiment data, ejecta/impact modeling | Not a detector, but foundational for planetary-defense modeling and validation of kinetic impactor effects. | NASA/ASI mission archives and published datasets. |
| 9 | OSIRIS-REx / OSIRIS-APEX | Active extended mission | Detailed asteroid characterization | Not a surveyor. Crucial for physical priors on rubble piles, regolith, Bennu/Apophis science, and hazard modeling. | NASA PDS. |
| 10 | Hayabusa2 | Completed / extended operations | Sample-return and asteroid physical priors | Not a surveyor, but Ryugu data are important for interpreting dark rubble-pile NEOs. | JAXA/DARTS and PDS mirrors where available. |

Not ranked as satellites but mandatory context: ATLAS, Pan-STARRS, Catalina, ZTF, Vera C. Rubin Observatory/LSST, and radar assets are central to real NEO discovery and follow-up. A coding agent should not ignore them.

## Credentials and Access Requirements

| Task | Credentials Needed | Notes |
|---|---|---|
| Query WISE/NEOWISE catalogs/images | Usually none | Use IRSA web tools, TAP-style services, or `astroquery.ipac.irsa`. Bulk downloads may require bandwidth planning, not special credentials. |
| Query Gaia DR3/DR4-era products | None for basic archive access; optional ESA account | Anonymous TAP/ADQL works for many queries. Registered accounts help with persistent uploads, async jobs, and collaboration tables. |
| Query MAST HST/JWST/TESS-like archival products | None for public data; MAST account useful | New JWST/HST observations require successful proposals. Public archive downloads can be automated. |
| Submit astrometry to Minor Planet Center | MPC observatory code and accepted observation batches | For real discovery/follow-up reporting, you need an observatory code. MPC supports ADES and legacy formats. |
| Access Rubin/LSST data | Data-rights access may be required for prompt products; public releases later | Rubin moving-object products will be transformative, but access depends on release phase and data-rights policy. |
| Use NEO Surveyor data | TBD until archive operations mature | Plan for NASA archive conventions, likely public releases with calibrated products after mission start. |
| Propose new space-telescope observations | PI/co-I credentials, proposal cycle, institutional support | HST/JWST/ESA missions require peer-reviewed observing proposals. |

## Frontier AI and Computational Methods

| Method | Implementation Target | Why It Is Used | Key Sources |
|---|---|---|---|
| CNN streak detection | ZTF, Euclid, HST, wide-field image cutouts | Fast-moving close NEOs appear as faint streaks. CNNs can recover faint/high-motion objects missed by humans or classical thresholding. | DeepStreaks: https://academic.oup.com/mnras/article/486/3/4158/5472913; Wang et al. 2022: https://arxiv.org/abs/2208.09098; Irureta-Goyena et al. 2025: https://arxiv.org/abs/2504.11918 |
| Synthetic-data augmentation | Streak classifiers and object detectors | Real labeled asteroid streaks are rare. Synthetic streaks let models learn faint, fast, unusual cases and measure completeness. | Wang et al. 2022: https://arxiv.org/abs/2208.09098; Irureta-Goyena et al. 2025: https://arxiv.org/abs/2504.11918 |
| Multi-stage CNN + RNN + gradient boosting | Euclid asteroid streaks | CNN detects snippets, RNN merges long streak pieces, XGBoost links detections between exposures to reduce false positives. | Pöntinen et al. 2023: https://arxiv.org/abs/2310.03845 |
| Tracklet-less heliocentric orbit recovery | Archival surveys with irregular cadence | Traditional methods need same-night tracklets. THOR can link sparse detections across arbitrary cadence by searching plausible heliocentric orbits. | THOR overview: https://b612.ai/opensource/thor/; Moeyens et al. AJ reference via B612 fact sheet: https://b612foundation.org/thor-on-adam-fact-sheet/ |
| HelioLinC / HelioLinC3D | LSST/Rubin-style moving-object linking | Scales asteroid linking by transforming detections/tracklets into heliocentric coordinates and clustering consistent motion. Critical for Rubin-scale alert streams. | Rubin announcement: https://rubinobservatory.org/news/new-algorithm-asteroid; NOIRLab: https://noirlab.edu/public/announcements/ann23023/ |
| Classical image differencing + shift-and-stack | Faint slow/fast moving objects | Still a baseline. AI models should be compared against classical pipelines because astronomy discovery claims require quantified completeness and false positives. | National Academies NEO survey context: https://www.nationalacademies.org/read/12842/chapter/5 |
| Probabilistic orbit fitting and impact monitoring | Candidate validation | Detection is not enough; the pipeline must fit orbits, propagate uncertainty, and interface with MPC/JPL systems. | JPL/CNEOS and MPC workflows; NEO Surveyor simulation paper: https://arxiv.org/pdf/2310.12919 |

## Influential and Innovative arXiv Papers

| Paper | Why It Matters | Coding-Agent Takeaway |
|---|---|---|
| Granvik et al., “Debiased orbit and absolute-magnitude distributions for near-Earth objects” https://arxiv.org/abs/1804.10265 | Highly cited modern NEO population model. Establishes debiased orbital/H distributions and source regions. | Use for priors, simulation populations, survey completeness tests, and synthetic training distributions. |
| Mainzer et al., “The Near-Earth Object Surveyor Mission” https://arxiv.org/abs/2310.12918 | Mission-defining paper for the future dedicated NEO IR survey. | Encode NEO Surveyor as the future top-ranked space discovery asset. Use its cadence/objective language for pipeline assumptions. |
| Masiero et al., NEO Surveyor simulation/yardstick paper https://arxiv.org/pdf/2310.12919 | Describes simulation methods for measuring progress toward discovery requirements. | Build evaluation harnesses around survey completeness, object classes, and survey cadence. |
| Cheng et al., “Momentum Transfer from the DART Mission Kinetic Impact” https://arxiv.org/abs/2303.03464 | Foundational planetary-defense result: kinetic impact momentum transfer included ejecta enhancement. | If modeling mitigation, include material/ejecta parameters and uncertainty; do not treat impacts as simple billiards. |
| Raducan et al., “Physical properties of asteroid Dimorphos as derived from the DART impact” https://arxiv.org/abs/2403.00667 | Shows Dimorphos is weak/rubble-pile-like and may have globally deformed. | Use rubble-pile priors for small-body physical models. |
| Pöntinen et al., “Euclid: Identification of asteroid streaks in simulated images using deep learning” https://arxiv.org/abs/2310.03845 | Good example of a modern mixed ML pipeline for space-image asteroid streaks. | Pattern: detect, merge, link; do not rely on a single classifier. |
| Wang et al., “Discovering Faint and High Apparent Motion Rate Near-Earth Asteroids Using A Deep Learning Program” https://arxiv.org/abs/2208.09098 | Demonstrates simulated streak training can discover real faint fast asteroids. | Synthetic data can be scientifically productive if validated on real survey images. |
| Irureta-Goyena et al., “Deep learning to improve the discovery of near-Earth asteroids in ZTF” https://arxiv.org/abs/2504.11918 | Modern operationally relevant CNN pipeline that found additional valid streaks beyond human scanners. | Evaluate against human scanner labels and count newly verified positives, not just benchmark metrics. |

## Citizen Candidate Vetting and Submission Best Practices

Goal: produce astrometry good enough that the Minor Planet Center (MPC), NEOCP follow-up observers, and orbit-computation systems can use it. For NEOs, community follow-up is time-sensitive: a fast-moving object can be lost quickly, and delayed submission is a known contributor to unconfirmed NEO candidates.

### Best Submission Path

| Scenario | Best Path | Practical Notes |
|---|---|---|
| You have an MPC observatory code and measured a moving object | Submit ADES-formatted astrometry to MPC; if likely NEO, it may appear on NEOCP | ADES is the modern data-exchange format for observers, MPC, and orbit centers. |
| You do not have an MPC code | First submit calibration observations to obtain a code, or coordinate with an experienced MPC-coded observer | MPC can assign a code after accepted observations; do not expect a single unvetted image to be useful. |
| You are following an object already on NEOCP | Prioritize rapid follow-up, multiple images, accurate timing, and prompt submission | NEOCP objects are provisional and can be lost without timely astrometry. |
| You found a candidate in archival survey data | Check MPC/JPL known-object services first, then package detections and seek collaboration with an observer/survey team | Archival candidates need tracklet/orbit linkage, not just a single detection. |
| You suspect an impactor | Submit to MPC immediately and coordinate with established NEO observers; monitor JPL Scout/CNEOS after MPC ingestion | Do not publicize alarming claims before orbit uncertainty is assessed. |

### Minimum Evidence Package

| Item | Required Practice |
|---|---|
| Images | At least 3-4 calibrated exposures showing consistent motion; more is better, especially for fast movers. |
| Timing | Mid-exposure UTC timestamps, synchronized clock, exposure duration, time-standard clarity. |
| Astrometry | RA/Dec with uncertainties, WCS solution, residuals against Gaia reference stars, plate scale, field center. |
| Photometry | Approximate magnitude and filter/bandpass if available; useful but secondary to astrometry. |
| Motion | Sky-plane rate and position angle; make sure motion is consistent across frames. |
| Known-object checks | Query MPC, JPL SBDB/CNEOS, SkyBoT/MPChecker-style services before claiming novelty. |
| Artifact rejection | Rule out hot pixels, cosmic rays, aircraft/satellite trails, diffraction spikes, bad columns, ghosts, and stacking artifacts. |
| Observatory metadata | Observatory code, telescope/aperture, detector, site coordinates, software used, astrometric catalog. |

### Citizen Workflow

1. Plan observations using MPC NEOCP, JPL Scout, CNEOS close-approach tables, and ephemeris tools.
2. Capture a sequence long enough to establish motion and short enough that trailing does not destroy centroid quality.
3. Calibrate images with bias/dark/flat corrections.
4. Solve WCS against Gaia DR3 or a current astrometric reference.
5. Measure centroids with asteroid-aware software such as Tycho Tracker, Astrometrica, find_orb/Project Pluto tools, or equivalent reproducible pipelines.
6. Cross-check against known minor planets and artificial satellites.
7. Format observations in ADES where possible.
8. Submit promptly to MPC or coordinate with an MPC-coded observer.
9. If the object appears on NEOCP, watch for follow-up requests and avoid duplicate low-value reports.
10. Archive raw frames, calibrated frames, reduction logs, and submission files.

### Quality Bar Before Asking for Community Follow-up

| Green Flag | Red Flag |
|---|---|
| Same moving source appears in multiple frames with plausible inertial motion | Single-frame detection only |
| Astrometric residuals are small and consistent | Large WCS residuals or distorted field edge |
| Object is absent from known-object query | Known main-belt asteroid or satellite track matches |
| Motion vector is coherent over time | Motion jumps frame to frame |
| Timing is traceable to UTC | Camera clock or FITS time is uncertain |
| Raw/calibrated data can be shared | Only screenshots or cropped images exist |

### What Not To Do

- Do not announce an impact risk from your own preliminary orbit.
- Do not submit stacked-only positions unless the moving-object timing is properly handled.
- Do not report single isolated points as discoveries.
- Do not hide non-detections or ambiguous frames; they matter for follow-up.
- Do not overfit an orbit from a short arc and treat it as authoritative.

### Source Pointers

- MPC ADES documentation: https://www.minorplanetcenter.net/mpcops/documentation/ades/
- MPC technical submission information: https://www.minorplanetcenter.net/iau/info/TechInfo.html
- MPC NEO Confirmation Page: https://www.minorplanetcenter.net/iau/NEO_dev/toconfirm_tabular.html
- MPC observatory code request: https://minorplanetcenter.net/new_obscode_request
- JPL CNEOS: https://cneos.jpl.nasa.gov/
- NASA NEO Observations Program: https://www.nasa.gov/solar-system/near-earth-object-observations-program/
- Vereš et al., unconfirmed NEOs and the cost of delayed follow-up: https://arxiv.org/abs/1805.02804

## Coding-Agent Guidance

1. Build adapters first: IRSA WISE/NEOWISE, Gaia TAP/ADQL, MAST, MPCORB/MPC observation formats, JPL SBDB/CNEOS where allowed.
2. Separate image detection from orbit linking. These are different error regimes.
3. Track provenance aggressively: image ID, time system, observatory/spacecraft ephemeris, WCS, photometric band, and detection confidence.
4. Use synthetic injections to measure completeness as a function of magnitude, rate, streak length, background density, and trailing loss.
5. Never claim a NEO discovery from ML alone. Require astrometric validation, orbit fit, and MPC-compatible reporting.

## Source URLs

- NASA NEO Surveyor: https://science.nasa.gov/mission/neo-surveyor/
- JPL NEO Surveyor: https://www.jpl.nasa.gov/missions/near-earth-object-surveyor/
- NASA NEOWISE: https://science.nasa.gov/mission/neowise/
- NEOWISE/IPAC: https://neowise.ipac.caltech.edu/
- IRSA WISE/NEOWISE: https://irsa.ipac.caltech.edu/Missions/wise.html
- ESA Gaia: https://www.esa.int/Science_Exploration/Space_Science/Gaia
- Gaia DR3 Solar System: https://www.cosmos.esa.int/web/gaia/dr3-solar-system-objects
- Gaia programmatic access: https://www.cosmos.esa.int/web/gaia-users/archive/programmatic-access
- MPC observatory codes: https://minorplanetcenter.net/new_obscode_request
