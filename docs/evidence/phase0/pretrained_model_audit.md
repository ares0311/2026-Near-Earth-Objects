# Phase 0 pretrained model audit

Date: 2026-07-02

Scope: Phase 0 of the ZTF DR24 historical-replay pipeline required by
`docs/neo_discovery_agent_brief.md`.

No third-party pretrained model is approved for production scoring at this
stage. The first Phase 1 implementation must use auditable rule-based features,
a simple linear/logistic baseline, and then LightGBM/XGBoost trained from
historical replay features. Pretrained/deep models may be reconsidered only
after a baseline exists and a later audit records exact model identifiers,
licenses, download sizes, preprocessing, and leakage controls.

| Candidate | Exact identifier | Source URL | License | Download size | Local cache path | Required package/version | Input schema / preprocessing | Use mode | Synthetic pretraining noted? | Known limitations | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Generic ConvNeXt via timm | Not selected | Not fetched | Unknown until selected | Not downloaded | None | `timm` version not selected | Requires image tensors with model-specific normalization; not yet mapped to ZTF DR24 alert/image products | None | Unknown until exact model card is selected | Generic vision embeddings are not a candidate ranker and may introduce non-auditable preprocessing assumptions | Defer |
| DINOv2 small | `facebook/dinov2-small` mentioned by brief, not fetched | https://huggingface.co/facebook/dinov2-small | Not audited here | Not downloaded | None | `transformers` version not selected | Requires image preprocessing not yet tied to ZTF DR24 cutout availability | None | Unknown until full model card audit | General image embeddings do not provide survey-native moving-object confidence by themselves | Defer |
| AstroM3-CLIP | `AstroMLCore/AstroM3-CLIP` mentioned by brief, not fetched | https://huggingface.co/AstroMLCore/AstroM3-CLIP | Not audited here | Not downloaded | None | Package/workflow not selected | Requires photometry/spectra/metadata preprocessing that is not yet verified for ZTF DR24 historical replay | None | Unknown until full model card audit | May not match ZTF alert fields without fragile transformations | Defer |
| Chronos / Chronos-Bolt style time-series models | Not selected | Not fetched | Unknown until selected | Not downloaded | None | Package/version not selected | Requires time-series tokenization not yet defined for candidate tracklets | None | Unknown until exact model card is selected | General time-series model, not astronomy-specific NEO detection; use only after handcrafted light-curve features exist | Defer |
| Fink-FAT / SNAPS methods | Papers only; no weights selected | See `docs/neo_discovery_agent_brief.md` | Not applicable to weights in this audit | Not downloaded | None | Not applicable | Method references for linking/features, not production weights | Method reference only | Not applicable | Must not be treated as a pretrained scoring artifact unless public code/data are separately verified | Reject as pretrained model; keep as methodology reference |

## Decision

Phase 1 may proceed without pretrained models. Any future use of a pretrained
model requires a new versioned audit entry before the model contributes to
training, evaluation, candidate ranking, or benchmark claims.
