# Schema description and SHACL containment experiment

This iteration makes two schema-only changes:

1. `01_prepare_schema_records.py` reads the already-authored English description for EngineeringBOM `BOMItemRecord` from `semantic/templates/engineeringbom_v2_template.json` **only if** the schema index has no description for `https://example.org/engineeringbom/hasBOMItemRecord`. The source template already describes it as a source-recorded engineering BOM item or component with identification, metadata, provenance and structural associations. No invented description is introduced. Other concepts are unchanged.
2. `07_expand_shacl_containment.py` uses same-domain `sh:node` declarations plus matching `shape_paths` to attach parent/child schema paths to top-k hits. It retains provenance and leaves retrieval rankings unchanged. In ProductCatalog, the declared `hasTechnicalProperties` collection can be surfaced when `hasTechnicalProperty` is retrieved.

**Caveat:** This is not a change to gold labels, not evidence of a cross-domain identity mapping, and not an instance relationship. Do not treat schema-context coverage as Recall@10 improvement.

Run from the repository root with Ollama running:

```bash
git pull origin feature/deterministic-nexus-baseline-20261110
python experiments/vector_graph_rag/01_prepare_schema_records.py
python experiments/vector_graph_rag/02_build_vector_index.py --model nomic-embed-text
python experiments/vector_graph_rag/06_evaluate_hybrid_retrieval.py \
  --gold experiments/vector_graph_rag/gold/dtwise_gold_concepts_review_draft.json \
  --output experiments/vector_graph_rag/data/hybrid_evaluation_33_v3.json
python experiments/vector_graph_rag/07_expand_shacl_containment.py \
  --evaluation experiments/vector_graph_rag/data/hybrid_evaluation_33_v3.json \
  --output experiments/vector_graph_rag/data/hybrid_shacl_context.json
```

Compare v3 with the archived v2 results using unchanged annotations and top-k. The description fallback modifies one record's embedding and requires rebuilding vectors. The SHACL context step is separate and does not rerank. Runtime tests were not executed during the GitHub update.
