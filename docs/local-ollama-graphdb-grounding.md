# Local Ollama + GraphDB grounded Q&A prototype

This is the first **read-only CLI integration**, not yet a frontend/API integration or a production industrial agent. It uses the existing RDF lifting convention (`assetinventory:hasProductReference` and `productcatalog:hasAssetIdentifier` as **literal** values). It does not permit the LLM to write or execute SPARQL.

## Prerequisites

- GraphDB running locally, with updated AssetInventory and ProductCatalog instance graphs available to the repository query endpoint.
- Ollama running locally and a downloaded chat model (default: `llama3.1:8b`).
- Python 3.10+; only Python standard-library modules are used.
- Ensure GraphDB's default query dataset includes the instance named graphs (e.g. GraphDB's default union dataset). The script does not query a specific named graph.

## Usage

```bash
# First verify retrieved GraphDB evidence without using Ollama:
python3 scripts/ask_graphdb_ollama.py "TEP_XMEAS7 pressure transmitter" --evidence-only

# Then ask the local model:
python3 scripts/ask_graphdb_ollama.py "Which product is associated with TEP_XMEAS7?"

# Override endpoints/model:
GRAPHDB_SPARQL_URL=http://localhost:7200/repositories/AAS \
OLLAMA_URL=http://localhost:11434 OLLAMA_MODEL=llama3.1:8b \
python3 scripts/ask_graphdb_ollama.py "Tell me about TEP_M_1301"
```

The output is JSON with `answer`, `evidence`, and `status`. Evidence contains the GraphDB bindings used to generate the answer. A query with no matching evidence returns `NO_EVIDENCE` rather than an invented answer.

## Design boundaries

1. Only fixed read-only SPARQL SELECT queries are sent to GraphDB; the user/model cannot inject SPARQL.
2. The bridge joins `ProductReference` and `AssetIdentifier` in memory using exact literal values. A missing match is not treated as an approved product.
3. The LLM is instructed to distinguish selected mappings, provisional candidates, and actual installed/approved equipment. This is a prompt-level guardrail, **not a formal guarantee**; review outputs before using them.
4. The script reads only AssetInventory and ProductCatalog. It cannot answer detailed DEXPI/ECAD/operating-data questions or make plant control recommendations.
5. Retrieval is a bounded simple keyword filter over the first 200 assets and products; it is **not** semantic retrieval or a general GraphRAG implementation.
6. No local GraphDB/Ollama execution was performed during implementation; run the commands above to verify actual endpoint behavior. If evidence is empty, confirm named-graph dataset visibility and loaded RDF predicate names first.

## Acceptance checks

- Evidence-only query for `TEP_XMEAS7` returns its inventory record and matched product.
- Query for `TEP_M_1301` identifies the ABB induction motor family without claiming verified installation.
- Query for `TEP_Reactor` preserves `REQUIRES_ALTERNATIVE` and does not promote the candidate to an approved selection.
- A nonexistent asset returns `NO_EVIDENCE`.
- Ollama unavailable: evidence-only still works; normal mode reports a connection failure rather than generating unsupported content.

See `docs/migrations/asset-product-graphdb-verification.md` for the underlying SPARQL checks and `docs/migrations/product-catalog-eclass-audit.md` for classification verification limits.
