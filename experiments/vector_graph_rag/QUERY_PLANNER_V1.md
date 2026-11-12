# DTWise Constrained Query Planner v1

`08_constrained_query_planner.py` consumes a schema index and an existing hybrid retrieval evaluation result. It requires **an exact question, explicit intended domain scope, and an explicitly selected property URI**. It does not use provisional gold annotations to choose predicates.

The planner emits either:
- `ready`: one read-only `SELECT DISTINCT ?subject ?value` query using a single SHACL-supported property IRI; or
- `abstained`: an explanation without SPARQL.

It verifies the property is indexed in the selected domain, was retrieved for that question, and has a matching `sh:path` declaration with resolvable provenance. It **does not** assume `rdf:type` for the subject, verify instance data, execute queries, or synthesize cross-domain joins. A multi-domain declared intent always abstains. The caller must honestly specify the domain intent; the planner does not parse intent from natural language. For production use, a separately validated intent/selection stage is required.

## Run

```powershell
python -m unittest discover -s experiments/vector_graph_rag -p test_constrained_query_planner.py -v

python experiments/vector_graph_rag/08_constrained_query_planner.py `
  --retrieval experiments/vector_graph_rag/data/hybrid_evaluation_33_v3.json `
  --question "What is the manufacturer part number of a catalog product?" `
  --requested-domain productcatalog `
  --domain productcatalog `
  --concept https://example.org/productcatalog/hasManufacturerPartNumber `
  --output experiments/vector_graph_rag/data/query_plan_v1.json
```

If the selected property is not in the question's hybrid top-10 hits, the planner abstains. This is intentional. To test cross-domain abstention, pass both `--requested-domain ecad` and `--requested-domain dexpi` for the electrical-device/process-equipment question. Do not use a single-domain scope to disguise a multi-domain question.

This is a narrow executable baseline, **not** a general natural-language-to-SPARQL planner. Tests were added but not run in the GitHub editing environment.
