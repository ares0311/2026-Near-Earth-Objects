# MPC Research Brief: WISE/NEOWISE Archival Astrometry Submission

Date checked: 2026-06-29  
Research constraint: official Minor Planet Center documentation/resources only, plus MPC-directly-linked ADES resources for format mechanics. No third-party summaries are used as authority.

## Question

For candidate astrometry derived by an independent data-analysis pipeline from public archival WISE/NEOWISE data, what MPC observatory/source code and submission pathway/format should be used?

## Executive conclusion

| Issue | Conclusion | Status |
|---|---|---|
| MPC observatory/source code for WISE/NEOWISE observations | MPC's official observatory-code list assigns `C51` to `WISE`. I found no MPC documentation assigning a separate `NEOWISE` observatory code. | Documented for WISE; separate NEOWISE code not documented |
| Whether an independent third-party archival remeasurement may submit using `C51` | MPC documentation documents `C51 = WISE`, program codes for different observers using the same telescope, and observing note `Z` for survey astrometry reported by a non-survey measurer/pipeline. However, I found no MPC page explicitly authorizing an independent researcher to submit reprocessed public WISE/NEOWISE archival astrometry under `C51`, nor a page saying they must use some other observatory/source code. | Requires MPC confirmation |
| Current submission format/pathway | MPC documents ADES as the current standard. The Astrometry Guide lists ADES PSV and ADES XML submission forms, cURL submission instructions, and says email is for `MPC1992 only`. WAMO is for checking processing status after submission, not the submission pathway. | Documented |
| Required observation-record fields for archival spacecraft/survey observations | MPC documents ADES field-value constraints and the observatory-code API fields, and the MPC-linked ADES standard defines the field model. MPC documentation found in this pass does not provide a WISE/NEOWISE-specific "required fields" recipe for third-party archival spacecraft remeasurements. The implementation should use ADES 2022-compatible records and validate with MPC tooling before submission, but authority and exact required-field policy should be confirmed with MPC. | Partly documented; WISE third-party recipe requires MPC confirmation |

## Official MPC sources checked

1. MPC Observations documentation hub  
   <https://docs.minorplanetcenter.net/mpc-ops-docs/observations/>

   Relevant quoted snippet:

   > "The ADES format is the current standard for submitting observations to the MPC."

2. MPC Guide to Minor Body Astrometry  
   <https://docs.minorplanetcenter.net/mpc-ops-docs/astrometry/>

   Relevant quoted snippets:

   > "Submission Methods"

   > "ADES PSV Submission Form"

   > "ADES XML Submission Form"

   > "E-mail submissions (MPC1992 only): obs@cfa.harvard.edu"

   > "Where Are My Observations (WAMO)"

3. MPC Valid ADES Field Values  
   <https://docs.minorplanetcenter.net/mpc-ops-docs/observations/valid-ades-values/>

   Relevant quoted snippets:

   > "The tables below list all values accepted by the MPC for key fields in ADES ... Use of an unlisted value in any of these fields will cause a batch to be rejected."

   > "`Z` | Astrometry from a survey reported by a non-survey measurer/pipeline"

   > "`A22` | ADES version 2022"

   > "`ICRF_KM` | Cartesian (km)"

4. MPC Observatory Codes API documentation  
   <https://docs.minorplanetcenter.net/mpc-ops-docs/apis/obscodes/>

   Relevant quoted snippets:

   > "The Observatory Codes API returns information about observatories registered with the MPC."

   > "`obscode` | String | Three-character observatory code"

   > "`uses_two_line_observations` | Boolean | Whether observatory uses two-line observations (most do not.)"

   > "`observations_type` | String | One of: `optical`, `occultation`, `satellite`, `radar`, `roving`"

5. MPC official observatory-code list  
   <https://minorplanetcenter.org/iau/lists/ObsCodesF.html>

   Relevant quoted snippet:

   > "`C51                              WISE`"

6. MPC Program Codes documentation  
   <https://docs.minorplanetcenter.net/mpc-ops-docs/observatory-and-program-codes/program-codes/>

   Relevant quoted snippets:

   > "The Minor Planet Center assigns program codes to identify different observers using the same telescope."

   > "These codes distinguish between multiple observation programs at individual facilities."

   > "Additional refinements regarding program code assignments for archival observations and non-historical stations are in development, with further details to be announced."

7. MPC Observations API documentation  
   <https://docs.minorplanetcenter.net/mpc-ops-docs/apis/get-obs/>

   Relevant quoted snippets:

   > "`output_format` ... `XML`, `ADES_DF`, `OBS_DF`, `OBS80`"

   > "`ades_version` ... `2017` or `2022` ... Default `2022`"

8. MPC Software page for ADES  
   <https://docs.minorplanetcenter.net/software/>

   Relevant quoted snippet:

   > "ADES defines both XML and PSV (pipe-separated value) formats for astrometric data exchange. It is jointly maintained by the MPC and the JPL Center for Near Earth Object Studies (CNEOS)."

9. MPC FAQ / Helpdesk pointer  
   <https://docs.minorplanetcenter.net/mpc-ops-docs/faqs/>

   Relevant quoted snippets:

   > "How do I submit observations? There are submission instructions here."

   > "After you submit your observations, you can confirm they were received using WAMO (Where Are My Observations)."

   > "Please submit a ticket under General Support."

10. MPC service desk portal, linked from official MPC material  
    <https://mpc-service.atlassian.net/servicedesk/customer/portals>

## Specific resolutions

### 1. Does MPC documentation assign WISE/NEOWISE observations to observatory code `C51`, or another code?

Conclusion: documented for WISE as `C51`; separate NEOWISE code not documented in the MPC sources found.

The official MPC observatory-code list contains:

> "`C51                              WISE`"

Nearby MPC-listed spacecraft codes include `C49 STEREO-A`, `C50 STEREO-B`, `C52 Swift`, `C53 NEOSSat`, `C55 Kepler`, `C57 TESS`, and `C58 NEO Surveyor`, but no separate `NEOWISE` code was found in the official MPC list excerpt or current MPC docs searched.

Coding-agent implication:

```text
stn = C51
```

only if MPC confirms that independently reprocessed WISE/NEOWISE archival observations should be submitted under the WISE station code.

### 2. May a third-party researcher reprocess public WISE/NEOWISE archival data and use the WISE/NEOWISE observatory code?

Conclusion: requires MPC confirmation.

What is documented:

- MPC documents `C51` as the WISE observatory code.
- MPC documents program codes as identifying "different observers using the same telescope."
- MPC documents ADES note `Z` as "Astrometry from a survey reported by a non-survey measurer/pipeline."
- MPC says program-code policy refinements for "archival observations and non-historical stations" are still "in development."

What is not documented in the official MPC material found:

- No explicit MPC rule was found saying an independent researcher may submit reprocessed public WISE/NEOWISE astrometry using `stn=C51`.
- No explicit MPC rule was found saying the independent researcher must not use `C51`.
- No explicit MPC rule was found assigning a separate code for third-party WISE/NEOWISE archival remeasurement.
- No explicit MPC recipe was found for "public archival WISE/NEOWISE data reprocessed by independent pipeline."

Best documented interpretation to confirm with MPC:

```text
Use station/observatory code C51 only as the physical/source observatory code for WISE data, but identify the reporting/remeasurement source separately through MPC-assigned submitter/program metadata and/or note Z, as instructed by MPC.
```

Do not ship a production submission workflow that silently submits under `C51` as though it were the WISE mission team without MPC confirmation.

### 3. What submission format/pathway is currently documented?

Conclusion: ADES PSV/XML submission is documented as current; email is documented only for MPC1992; WAMO is status checking, not submission.

Current MPC-documented submission options:

| Pathway | MPC-documented role |
|---|---|
| ADES PSV Submission Form | Documented submission method |
| ADES XML Submission Form | Documented submission method |
| cURL submission instructions | Documented submission method |
| Email to `obs@cfa.harvard.edu` | Documented as `MPC1992 only` |
| WAMO | Documented for checking whether submitted observations were received/processed |
| MPC1992 / 80-column | Still documented and retrievable, but not the current standard; email path is `MPC1992 only` |

Coding-agent implication:

Prefer ADES 2022 PSV or XML submission through the MPC submission form/API/cURL route. Use WAMO only after submission to monitor status.

### 4. What fields are required in the submitted observation record for archival spacecraft/survey observations?

Conclusion: partly documented, but not as a WISE/NEOWISE third-party archival checklist. Requires MPC confirmation for exact required field set and authorization.

MPC-documented ADES facts relevant to implementation:

- ADES is the current standard.
- ADES may be PSV or XML.
- ADES version `A22` is a valid submission-format value.
- Valid coordinate frame value includes `ICRF_KM`, described by MPC as `Cartesian (km)`.
- Observatory-code API describes whether an observatory uses two-line observations and whether its observation type is `satellite`.
- Valid note `Z` exists for "Astrometry from a survey reported by a non-survey measurer/pipeline."

Minimum implementation fields to prepare for a WISE/NEOWISE archival spacecraft ADES candidate, subject to MPC confirmation:

| Field | Purpose | Status for this use case |
|---|---|---|
| `permID` / `provID` / `trkSub` | Object identity or submitter-assigned tracklet identity | ADES field family; use according to object status |
| `mode` | Instrumentation type | MPC valid values required; WISE-specific value should be confirmed |
| `stn` | MPC station/observatory code | Likely `C51` for WISE source data, but third-party use requires MPC confirmation |
| `prog` | MPC program code identifying observing program/submitter where assigned | Program-code docs relevant; exact assignment requires MPC |
| `obsTime` | UTC observation time | Core astrometric field |
| `ra`, `dec` | Astrometric sky position | Core astrometric fields |
| `rmsRA`, `rmsDec` | Astrometric uncertainty | Important for MPC residual/rejection checks; exact requirement should be confirmed |
| `astCat` | Astrometric reference catalog | MPC valid values page applies |
| `mag`, `rmsMag`, `band`, `photCat` | Photometry and photometric metadata, if reported | MPC valid values page applies |
| `notes` including `Z` | Observation notes; `Z` specifically flags non-survey measurer/pipeline survey astrometry | Strongly relevant; exact use should be confirmed |
| `sys` | Coordinate frame for roving/space-based station coordinates | `ICRF_KM` is a documented valid value |
| `ctr` | Origin of coordinate frame | Needed for space-based coordinates per ADES model; exact value should be confirmed |
| `pos1`, `pos2`, `pos3` | Observer/spacecraft Cartesian position components | Needed for spacecraft/topocentric geometry |
| `vel1`, `vel2`, `vel3` | Observer/spacecraft velocity components where ADES 2022 supports/needs them | Use if required/accepted by MPC for spacecraft archival measurements |
| `remarks` / submission header contact fields | Provenance, pipeline, archival data release, remeasurement method, submitter contact | Include enough for MPC review; exact form policy requires MPC |

Important: the table above is an implementation preparation checklist, not a claim that MPC has published a WISE-specific required-field rule for third-party archival submissions.

### 5. If MPC does not explicitly answer third-party archival remeasurement/submission authority, where should confirmation be requested?

Conclusion: not documented; use MPC Helpdesk / General Support.

The MPC FAQ repeatedly directs users with unresolved processing, discovery-credit, rejection, and service issues to submit a ticket under "General Support." The official MPC-linked service desk portal is:

<https://mpc-service.atlassian.net/servicedesk/customer/portals>

Recommended confirmation request to MPC:

```text
We are preparing ADES submissions for candidate astrometry independently remeasured from public archival WISE/NEOWISE images by a non-WISE, non-NEOWISE data-analysis pipeline.

Please confirm:

1. Should the ADES station code be stn=C51 for the WISE/NEOWISE spacecraft source data?
2. Should these observations carry ADES note Z ("Astrometry from a survey reported by a non-survey measurer/pipeline")?
3. Should the submitter obtain/use a distinct MPC program code under C51, or another source identity?
4. Which ADES 2022 fields are mandatory for these archival spacecraft observations, especially sys/ctr/pos1/pos2/pos3 and vel1/vel2/vel3?
5. Should submission be via ADES PSV, ADES XML, cURL/API submission, or another MPC pathway?
```

## Final answer for coding-agent behavior

Implement the pipeline so it can emit ADES 2022 PSV/XML records, not only legacy 80-column MPC1992 records. Model WISE-origin observations with `stn=C51` only behind a configuration gate named something like `mpc_confirmed_wise_c51_submission = true`, because MPC documents `C51 = WISE` but does not explicitly document third-party archival WISE/NEOWISE remeasurement authority. Include support for ADES note `Z`, submitter/program-code metadata, spacecraft position fields, and WAMO status checking. Before live submission, require written MPC Helpdesk confirmation of the station/program-code authority and exact ADES field requirements.
