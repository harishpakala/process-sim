# DTWise hybrid retrieval: two missed questions (provisional audit)

Source: user-run `hybrid_evaluation_33.json` (33 questions, top_k=10). This report records observations, not expert validation of the proposed gold annotations.

## 1. EngineeringBOM / AssetInventory

**Question:** Which engineering components have inventory representations?

Proposed gold:
- `engineeringbom | https://example.org/engineeringbom/hasBOMItemRecord`
- `assetinventory | https://example.org/assetinventory/hasAsset`

Both gold URIs are present in the schema records (`missing_gold_in_records: []`), but **neither is in the top 10** for vector, lexical, or hybrid. All three methods have Recall@10 = 0.

Hybrid top-10 includes the AssetInventory root class (rank 1), EngineeringBOM `hasItemDescription` (rank 2), and EngineeringBOM root class (rank 6), but not the proposed gold properties. Domain recognition is therefore not equivalent to exact concept retrieval.

**Annotation review required:** The wording implies a cross-domain representation/link. The two proposed schema properties identify candidate domain concepts, but **do not prove a mapping or join**. Decide whether the intended task is (a) schema concept discovery across domains or (b) finding actual matched instances. Do not score a schema-only retriever as though an instance-level mapping were verified. Also check whether `hasBOMItemRecord` and `hasAsset` are the complete and most defensible gold concepts for this wording.

## 2. ProductCatalog technical characteristics

**Question:** What technical characteristics are recorded for a catalog product?

Proposed gold:
- `productcatalog | https://example.org/productcatalog/hasTechnicalProperty`
- `productcatalog | https://example.org/productcatalog/hasTechnicalProperties`

Both exist in the schema records. All three retrieval methods return `hasTechnicalProperty` at rank 1, but **none returns `hasTechnicalProperties` in the top 10**; Recall@10 = 0.5.

**Annotation review required:** Determine whether singular `hasTechnicalProperty` and plural `hasTechnicalProperties` denote genuinely distinct required concepts (for example, a field versus a collection). If one is merely a structural container, decide whether both are necessary to answer this question. Do not silently merge or remove either URI: they remain distinct schema concepts until reviewed.

## Recommended diagnostic follow-up (not yet implemented)

1. Capture full ranks and vector/lexical scores of the missing gold URIs (top 10 alone cannot show their positions).
2. Inspect the exact descriptions and SHACL owning shapes for those four concepts and their close competitors.
3. Obtain expert review of gold relevance and question scope **before** tuning the retriever.
4. Re-evaluate with unchanged baseline and reviewed labels; avoid using expected gold domains as inference-time reranking hints.

No RelationshipElement normalization, instance mapping, or cross-domain joins are implied by these findings.
