# Ontology-aware GraphDB AI pipeline — prototype

This branch begins the DTwiSE workshop implementation: **dynamic, ontology-aware SPARQL generation with a fail-closed validation gate**. It does not yet provide a production-ready API or UI integration.

## Modules

- `process_sim.ai.graphdb.discover_schema(endpoint)`: read-only GraphDB named-graph/predicate sampling with provenance. It reports observed predicates, **not** full formal ontology constraints.
- `process_sim.ai.planner.plan(question, schema)`: local Ollama JSON planning, returning a candidate SPARQL SELECT query or `null`.
- `process_sim.ai.sparql_policy.validate_select(query)`: RDFLib grammar parsing, SELECT-only check, conservative rejection of federation/update keywords, and mandatory bounded LIMIT.
- `process_sim.ai.planner.query(question, graphdb_endpoint)`: combines schema discovery, Ollama planning, validation, IRI allowlisting, and read-only SELECT execution; returns raw bindings and the executed query, **not a verified natural-language answer**.

## Local checks

```bash
export PYTHONPATH=src
python -m pip install rdflib
python -m unittest discover -s tests -p 'test_ai_graph_pipeline.py'
ollama pull llama3.1:8b
ollama serve
```

With GraphDB available locally at `http://localhost:7200/repositories/AAS`, experiment from Python:

```python
from process_sim.ai.planner import query
result = query("List available equipment tags and their source graph", "http://localhost:7200/repositories/AAS")
print(result["status"], result.get("sparql"), result["bindings"][:5])
```

This prototype is intentionally conservative and may reject valid queries (for example, queries requiring prefix declarations, RDF type IRIs, or predicates absent from the sampled schema). **Do not loosen the gate without tests.** The next step is to replace lexical IRI handling with AST-based ontology/predicate resolution and graph-aware constraints.

## Known limitations and security

- **Not executed in the repository CI or against the owner's local GraphDB/Ollama.** Offline tests were committed but have not been run in the target environment.
- The existing `/api/kg/select` route is separate; the new planner is not yet exposed through `/api/ai/query` and the Vue AI Query panel remains disabled.
- The schema query is a bounded listing of observed named-graph predicates; its aggregate scan may be expensive on large graphs. Use caching and query budgets.
- The validator is a prototype policy gate, not a complete proof of SPARQL safety or ontology correctness. GraphDB **must** enforce read-only credentials, server-side timeouts, quotas and network restrictions.
- Local Ollama endpoint checks do not substitute for network egress controls.
- No temporal analysis planner, query repair loop, benchmark results, or answer-grounding verifier is implemented yet.
- Do not infer installed equipment from semantic correspondence, or causal relationships from temporal correlation.

## Next DTwiSE milestones

1. Test the parser and policy with real generated queries and adversarial cases.
2. Inspect GraphDB named graphs, classes, and temporal provenance to build a faithful schema catalog.
3. Implement a typed plan schema, structured validator feedback, and bounded query repair.
4. Add an authenticated, read-only Python API route and a Vue evidence/trace panel.
5. Evaluate against direct LLM-to-SPARQL and ontology-context baselines, including temporal questions.


## SHACL-aware registry milestone

`process_sim.ai.shacl_registry.build_shacl_registry()` invokes the **existing**
`semantic.template_lifting.build_template_graph` on each template registered in
`semantic.config.TARGETS`, then joins the instance-derived classes and
predicates from `semantic_registry`. The result includes SHACL property
paths, cardinalities, value classes, nested node shapes, and source paths.

```bash
export PYTHONPATH=src:.
python -m unittest discover -s tests -p 'test_ai_shacl_registry.py'
```

```python
from process_sim.ai.shacl_registry import build_shacl_registry, planner_shacl_context
registry = build_shacl_registry()
context = planner_shacl_context(registry, domains=["dexpi"])
print(context["domains"][0]["shaclPaths"][:3])
```

The schema registry is generated from source artifacts **without connecting to
GraphDB**. It is not yet used by the Ollama planner: the planner still uses the
earlier source-derived vocabulary catalog. The next milestone is a typed query
plan and semantic path validator that consumes this SHACL-aware registry.

Caveats: the extractor currently handles simple URI-valued `sh:path` and
`sh:node` links; complex SHACL paths are skipped. No runtime tests or
local GraphDB checks have been performed by the assistant.
