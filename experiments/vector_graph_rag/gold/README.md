# DTWise concept retrieval annotation set — REVIEW DRAFT

This is **not yet a gold standard**. All proposed concept annotations were selected from the uploaded `schema_records.jsonl` and require independent domain-expert review before reporting gold-standard metrics.

- `dtwise_gold_existing_3_review_draft.json`: 3 questions with exact text matching the uploaded retrieval results. Compatible with `05_evaluate_grounding.py --gold` now, but results are provisional.
- `dtwise_gold_concepts_review_draft.json`: 33 questions, spanning all six domains. To evaluate all 33, add their exact question text to the retrieval question input and rerun steps 03–05.

Review each question and the complete set of relevant (domain, URI) pairs. Add/remove concepts as needed, flag ambiguous or unanswerable questions, and separately annotate whether any claimed cross-domain identity mapping has independent evidence. The first three questions include potentially cross-domain language; labels are **retrieval targets only**, not verified joins.

Do not score RelationshipElement semantics or instance links in this phase. The annotation file uses the JSON format expected by the current `05_evaluate_grounding.py` script; the script does not itself verify that labels have been reviewed.

Example command (from repository root, after copying file into `experiments/vector_graph_rag/data/`):

```bash
python experiments/vector_graph_rag/05_evaluate_grounding.py \
  --gold experiments/vector_graph_rag/data/dtwise_gold_existing_3_review_draft.json \
  --output experiments/vector_graph_rag/data/grounding_evaluation_provisional.json
```