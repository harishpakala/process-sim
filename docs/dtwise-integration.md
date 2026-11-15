# DTwise integration checkpoint (frozen external checkout)

This branch is based on `feature/deterministic-nexus-baseline-20261110`.
The initial integration is **read-only and CLI-only**. It does not alter
TEP NEXUS, the process simulator, TimescaleDB, the Vue UI, or DTwise planner
source. It is not yet a combined semantic-temporal query interface.

## Source of truth

Use the uploaded frozen `Vectorized_Retr.zip`, extracted to a local directory.
The active planner entry point in that archive is
`dtwise.semantic_planner.plan_question_semantic`; SPARQL compilation is
`dtwise.sparql_generator.compile_sparql`; GraphDB execution and formatting
are in `dtwise.rdf_executor`. The adapter imports these **from the external
checkout**, not from a copied or rewritten planner.

Do not use `typed_query_planner.py` or `typed_intent_adapter.py`; those are
abandoned experiments. Do not execute `dtwise/integrate.py`; it is a source
patching utility, not the runtime entry point. The archive's README mentions
`main.py`, but that file is absent from this uploaded ZIP. This integration
therefore uses the verified module entry points directly.

The schema index is located in the archive at
`semantic/ontology/dtwise/dtwise-schema-index.json`.
The adapter does not rebuild embeddings or modify Qdrant storage.

## PowerShell smoke test

From the `process-sim` checkout on this integration branch:

```powershell
$dtwise = "C:\Users\haris\eclipse-workspace\Vectorized_Retr"
$schema = Join-Path $dtwise "semantic\ontology\dtwise\dtwise-schema-index.json"
$env:GRAPHDB_SPARQL_ENDPOINT = "http://pakala:7200/repositories/AAS"

# Plan + compile only (no GraphDB query):
python scripts\dtwise_bridge.py `
  --dtwise-root $dtwise --schema $schema `
  --question "List OPCUA SignalNames." `
  --output reports\dtwise_bridge_smoke.json

# Once reviewed, execute a read-only SELECT:
python scripts\dtwise_bridge.py `
  --dtwise-root $dtwise --schema $schema `
  --question "List OPCUA SignalNames." --execute `
  --output reports\dtwise_bridge_live.json
```

Requires the frozen DTwise Python dependencies and a reachable Ollama model
when a question follows an LLM-backed planner path. GraphDB access is only
required with `--execute`. The bridge compiles with
`graph_mode="all_named"`, matching the DTwise benchmark environment.

## Next validation gates

1. Record the exact SHA-256 of the frozen ZIP and the selected schema index.
2. Compare bridge SPARQL and results against the same questions run directly
   in the frozen DTwise checkout; run the existing regression suite.
3. Verify the original TEP NEXUS tests remain unchanged and passing.
4. Only then expose a constrained API endpoint and connect the existing Vue UI.
5. For combined queries, reuse the existing run-scoped function registry and
   read-only virtual graph execution; do not infer equipment-to-signal mappings
   from string resemblance or copy historian samples into GraphDB.

No live GraphDB/TimescaleDB/Ollama execution is claimed by this commit.
