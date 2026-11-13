# DTWise vector retrieval experiment (isolated)

No production DTWise modules are modified. The scripts use the existing **schema** JSON index, not instance data. No join or asset identity is inferred.

## Prerequisites

- Python 3.10+
- Existing `semantic/ontology/dtwise/dtwise-schema-index.json` generated using `python -m semantic.dtwise_schema_index` (requires the DTWise concepts/relationships TTL catalogs).
- Local Ollama service and an embedding model: `ollama pull nomic-embed-text`

Run from the **repository root**:

```bash
python experiments/vector_graph_rag/01_prepare_schema_records.py
python experiments/vector_graph_rag/02_build_vector_index.py --model nomic-embed-text
python experiments/vector_graph_rag/03_evaluate_retrieval.py --top-k 10
```

The outputs go to `experiments/vector_graph_rag/data/` and should remain untracked. The vector index is a simple JSONL embedding store with exact cosine similarity, intentionally **not** a production vector database. The question file is an **illustrative smoke-test set**, not a gold benchmark. Expected domains need independent expert review before claiming retrieval accuracy. The lexical baseline here is plain token overlap, **not** the full `dtwise_concept_resolver.resolve` ranking; do not claim a direct head-to-head with the production resolver.

Next steps, only after inspecting outputs: curate gold concept/relationship IRIs, measure recall@k, test retrieval with/without domain words, and implement graph expansion using SHACL evidence. Vector retrieval candidates are never proof of a valid cross-domain join.

## Phase 2: evidence-constrained graph expansion and evaluation

The following additions **do not modify** production DTWise modules:

```bash
python experiments/vector_graph_rag/04_expand_graph_context.py --max-hops 2
python experiments/vector_graph_rag/05_evaluate_grounding.py
```

`04_expand_graph_context.py` uses the existing JSON schema index and retrieval output. It traverses only explicit, **same-source-domain** OWL/RDFS and SHACL declarations, with configurable hop and edge caps. It reports associated SHACL paths as declarations, not asserted instance relationships. A missing EngineeringBOM domain can only be recovered if explicit evidence is reachable from a seed; this script never creates a cross-domain mapping based on name similarity.

`05_evaluate_grounding.py` adds domain precision/recall/F1 and, **if independently reviewed concept gold labels are supplied**, concept precision/recall/F1 and reciprocal rank. Without concept gold labels those metrics remain `null` rather than implying success. To provide gold labels, create a JSON list like:

```json
[
  {
    "question": "Which electrical devices correspond to process equipment?",
    "expected_domains": ["ecad", "dexpi"],
    "gold_concepts": [
      {"domain": "ecad", "uri": "https://example.org/ecad/hasDevice"},
      {"domain": "dexpi", "uri": "https://example.org/dexpi/hasEquipment"}
    ]
  }
]
```

These concept labels are **examples only**, not adjudicated ground truth. Invoke with `--gold path/to/reviewed_gold.json`. The report does not claim relationship accuracy, SHACL path completeness, instance validation, or cross-domain join correctness. Future work should add expert-reviewed gold relationship/path annotations and test retrieval on held-out questions.
