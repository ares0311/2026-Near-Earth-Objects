# ZTF DR24 Motion-Product Manifest — First Live Verification

Date: 2026-07-16

Scope: metadata-first replacement path for the completed ZTF alert-replay null results

External submission: none

## Result

The existing bounded IRSA science-metadata ingest now optionally emits a
source-native product acquisition plan. It derives, but does not download,
the documented URL for each exposure's:

- science-minus-reference difference image;
- science-image mask;
- single-exposure PSF-fit source catalog; and
- difference-image PSF.

Every planned product is marked `availability=unverified`. DR24 states that
difference products exist only for exposures that had a reference image when
originally processed, so filename construction alone is not accepted as proof
of availability.

## Primary-source contract

- DR24 is the latest public release dated 2026-01-22:
  `https://irsa.ipac.caltech.edu/Missions/ztf.html`
- DR24 includes single-exposure source catalogs, masks, difference images, and
  difference-image PSFs; it recommends `infobits < 33554432` for likely usable
  single-exposure products:
  `https://irsa.ipac.caltech.edu/data/ZTF/docs/releases/dr24/ztf_release_notes_dr24.pdf`
- IRSA documents the deterministic science-product path and filename suffixes:
  `https://irsa.ipac.caltech.edu/docs/program_interface/ztf_metadata.html`
- IRSA documents the metadata query and cutout API:
  `https://irsa.ipac.caltech.edu/docs/program_interface/ztf_api.html`

This product family is motion-oriented because detections can be extracted
independently from each exposure's difference pixels. It does not reinterpret
position-matched alert `prv_candidates` history as moving-object observations.

## Bounded live probe

The metadata-only query used:

```text
RA=232.6
Dec=-8.4
SIZE=0.01 deg
2458339.5 < obsjd < 2458340.5
infobits < 33554432
```

It returned one real exposure:

```text
pid=585152193615
obsjd=2458339.6521991
field=377
ccdid=10
qid=1
filtercode=zr
filefracday=20180809152095
infobits=0
```

The raw 2,197-byte IPAC response has SHA-256:
`5c73677d95601a509a52c1c53ce1ab19f2ae9abac346afe6cb00c92ca812a07e`.
The generated manifest and checkpoint occupy 16 KiB under ignored
`Logs/pipeline_runs/ztf_dr24_bounded_ingest/3d28311a660d/`.

Four bounded HTTP HEAD requests then verified that every planned product for
this exposure exists. No response body or image/catalog product was
downloaded.

| Product | HTTP | Content length |
|---|---:|---:|
| Difference image | 200 | 7,957,440 bytes |
| Science mask | 200 | 18,941,760 bytes |
| Science PSF catalog | 200 | 406,080 bytes |
| Difference PSF | 200 | 5,760 bytes |
| **Aggregate if later downloaded** |  | **27,311,040 bytes (~26.0 MiB)** |

## Decision boundary

This verification authorizes no pixel download, candidate claim, Gate Z3
resumption, MPC submission, or other external action. The next safe engineering
step is a bounded, checkpointed HEAD-preflight stage that records product
availability and byte estimates before a separately approved tiny extraction
pilot. Broad alert replay remains paused.
