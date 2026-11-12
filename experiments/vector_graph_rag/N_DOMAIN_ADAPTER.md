# Hybrid retrieval → existing DTWise N-domain planner

`09_retrieval_n_domain_adapter.py` is a narrow bridge, **not a replacement planner**.

It reads a saved hybrid/vector/lexical retrieval evaluation, matches the exact question, verifies that each explicitly requested domain has at least one indexed top-k concept hit, then invokes `semantic.dtwise_n_domain_planner.compile_n_domain` using the existing `semantic.dtwise_cross_domain._validate_path` validator.

**Safety:** Retrieval ranks candidate domains; it does not establish an identity join. Extra retrieved domains are not silently added. No catalog mappings are created, upgraded, or approved. The existing planner requires an exact domain-set catalog plan, grounded SHACL paths, and verified semantic approval by default. `--allow-candidate` is an explicit exploratory override, not verification. No SPARQL is executed.

## Commands (PowerShell, repository root)

```powershell
git pull origin feature/deterministic-nexus-baseline-20261110
python -m py_compile experiments/vector_graph_rag/09_retrieval_n_domain_adapter.py
python -m unittest discover -s experiments/vector_graph_rag -p test_retrieval_n_domain_adapter.py -v

python experiments/vector_graph_rag/09_retrieval_n_domain_adapter.py `
  --question "Which engineering components have inventory representations?" `
  --domain engineeringbom `
  --domain assetinventory `
  --retrieval experiments/vector_graph_rag/data/hybrid_evaluation_33_v3.json
```

The example should abstain: the catalog does not declare an approved exact EngineeringBOM + AssetInventory join. Other requests may abstain earlier if the hybrid top-10 lacks a selected domain. This is expected, not a failed integration.

For an existing **cataloged** two-domain pair, use a matching question in the retrieval results and explicitly specify both domains. Because current catalog mappings are `candidate_pending_semantic_approval`, default mode still abstains. Only for deliberate exploratory tests, pass `--allow-candidate`, which does not certify the mapping.

**Scope:** Domain selection is explicitly supplied by the caller; this adapter does not automatically determine the exact intended domain set from noisy retrieval rankings. A later intent-selection stage can supply it, but must be independently validated. No RelationshipElement processing or instance joins were added.

Tests were committed but not executed in the GitHub editing environment.
