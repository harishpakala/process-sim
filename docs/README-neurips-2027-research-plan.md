# TEP NEXUS: NeurIPS 2027 Research Plan

**Status:** Research proposal, not an established novelty claim or accepted submission.
**Target:** NeurIPS 2027 main conference (aspirational); workshop or alternative venue as fallback.
**Schedule:** Internal planning dates only. Verify official NeurIPS 2027 submission deadlines when announced.

## Executive summary

TEP NEXUS combines semantically lifted DEXPI, ECAD, ProductCatalog, and AssetInventory AAS domains; RDF/SHACL and GraphDB; simulation and temporal provenance; and a Python/Vue application. The proposed scientific contribution is **ontology-aware, validated, feedback-guided query planning for evidence-grounded reasoning over heterogeneous semantic-temporal knowledge graphs**.

Simply integrating local Ollama with GraphDB is systems engineering. A NeurIPS-level contribution would require a novel, generalizable method and rigorous experiments demonstrating gains over strong baselines.

## Research questions and hypotheses

**H1 — Constraint-guided planning:** Does ontology-aware query validation with structured feedback and bounded repair improve executable-query and answer accuracy compared with direct LLM-to-SPARQL and ontology-context-only baselines?

**H2 — Joint semantic-temporal reasoning:** Does a unified planner combining graph traversal, run-specific provenance, and time-series computation outperform disconnected graph and temporal pipelines on compositional questions?

**H3 — Evidence fidelity:** Can evidence-type and provenance checks reduce unsupported engineering assertions without excessive abstention?

Potential contributions (subject to literature review): a schema-aware planner; a parsed, policy-validated read-only SPARQL execution layer; structured validator feedback and query repair; a joint semantic/temporal tool protocol; and a reproducible benchmark.

## Existing repository foundation

- Four lifted semantic domains: DEXPI, ECAD, ProductCatalog, AssetInventory.
- GraphDB/SPARQL bridge in src/process_sim/api/server.py.
- Cross-domain asset-to-product query in src/process_sim/api/asset_specifications.py.
- Temporal RDF synchronization in src/process_sim/api/graph_sync.py and time-series/fault-event infrastructure.
- Vue AI Query placeholder in frontend/src/App.vue.
- Engineering review and physical BOM governance, with a critical distinction between semantic correspondence and verified physical installation.
- Draft PR #11 explores a local Ollama documentation-grounded prototype; it is **not** yet a GraphDB-first ontology-aware reasoning system.

The project owner reports that all four lifted datasets are loaded in local GraphDB. This has not been independently verified through live access. Local SHACL validation does not automatically establish cross-domain completeness or end-to-end temporal linkage.

## Proposed architecture

1. **Ontology discovery:** Inspect actual named graphs, classes, predicates, relationship paths, SHACL constraints, and available temporal provenance. Version/cache a compact schema context.
2. **Local Ollama planner:** Convert natural language into a typed plan: entity resolution, graph paths, temporal windows, joins, calculations, and dependencies.
3. **SPARQL compiler and validator:** Parse queries into an AST; enforce read-only operations, named-graph scope, allowed query features, complexity budgets, timeouts, and row limits. Do not rely on keyword checks alone.
4. **GraphDB executor:** Execute approved SPARQL with read-only database credentials, returning RDF bindings, graph IRIs, and provenance.
5. **Temporal executor:** Use TimescaleDB/Python for bounded signal windows, event ordering, and numerical metrics; preserve run IDs, timestamps, and units.
6. **Feedback and repair:** Return structured errors (unknown predicate, invalid join, unbounded query, incompatible run scope) to the planner for a limited number of revisions.
7. **Grounded answer generation:** Explain only supported findings, show evidence references, report uncertainty, and distinguish correlation from causation.
8. **Vue AI Query:** Display answer, generated/executed SPARQL, execution trace, source IRIs, temporal windows, and verification status.

**Design principle:** Restrict execution capabilities, not the range of questions the model may formulate. Parameterized templates remain useful as baselines or specialized tools but should not be the only reasoning mechanism.

## Example questions

- **Semantic:** Which instruments are associated with reactor R-001, and which RDF relationships support that association?
- **Cross-domain:** Which manufacturer specifications are referenced by an asset, and are they catalog claims or verified installed limits?
- **Temporal:** How did reactor pressure change following a fault event in a selected simulation run?
- **Joint:** Which semantically linked measurements deviated after a fault, and what controller actions occurred in the same interval?

Identifiers are illustrative; each must be resolved against actual graph data. Missing evidence should result in explicit abstention or clarification, not invented results.

## Experimental design

### Baselines

1. Fixed parameterized SPARQL templates.
2. Direct Ollama-to-SPARQL without schema context.
3. LLM-to-SPARQL with retrieved ontology context.
4. Ontology-aware validation without iterative repair.
5. Ontology-aware validation **with** feedback-guided repair (primary proposed method).
6. Separate graph and temporal analysis versus a joint semantic-temporal planner.

Control for model versions, prompts, query budgets, graph snapshots, and available tools. Include cost/latency comparisons to ensure gains are not simply due to more model calls.

### Benchmark

Build a versioned, independently checked benchmark with reference answers, queries/calculations, and evidence. Include single-hop and multi-hop graph questions, cross-domain joins, temporal ordering, before/after windows, cross-run comparisons, compositional graph-plus-time-series questions, ambiguous identifiers, and unanswerable cases.

Test generalization using held-out query compositions and ontology/schema perturbations rather than random paraphrase splits alone. Consider additional public graph datasets to avoid a single-testbed result.

### Metrics

- SPARQL parse/execution success and result-set correctness.
- Final-answer correctness, including temporal ordering and run consistency.
- Evidence-to-claim support and provenance fidelity.
- Unsupported-claim rate and appropriate abstention.
- Repair success rate and iterations.
- Latency, token usage, query cost, and robustness under schema shifts.

### Ablations

Remove ontology context, parser/policy validation, SHACL feedback, repair, temporal tools, and provenance checks separately. Report failure modes and statistical uncertainty.

### Reproducibility

Pin local model versions, software dependencies, graph snapshots, prompts, evaluation splits, and resource limits. Publish synthetic or redistributable RDF/time-series fixtures when real engineering data cannot be shared.

## Working schedule

| Period | Milestone | Exit criterion |
| --- | --- | --- |
| Oct–Nov 2026 | Literature review, novelty map, schema audit, benchmark design, baseline setup | Written research protocol and first baseline results |
| Dec 2026 | Ontology-aware planner and SPARQL validator | Parser/policy tests and valid GraphDB retrieval |
| Jan 2027 | Temporal planning and execution | End-to-end graph/time-series evidence traces |
| Feb 2027 | Benchmark and controlled experiments | Reproducible baseline comparisons |
| End Feb 2027 | **Go/no-go decision** | Demonstrable methodological gains and credible novelty |
| Mar 2027 | Ablations, robustness, manuscript draft | Complete experimental tables and failure analysis |
| Apr 2027 | Paper and artifact preparation | Internal submission-ready draft |

**Deadline caution:** The NeurIPS 2027 abstract and paper deadlines are not established here. Late April is an internal target only; verify official dates and track requirements.

## Research and implementation risks

- **Novelty:** Related work in text-to-SPARQL, GraphRAG, neuro-symbolic reasoning, constrained decoding, query repair, temporal KGQA, and tool agents may overlap. Conduct a systematic literature comparison before claiming novelty.
- **Graph completeness:** SHACL conformance does not prove all joins exist. Audit actual loaded graphs and label answerability.
- **Temporal correctness:** Never merge incompatible run IDs or timestamps; distinguish association from causation.
- **Safety:** Reject SPARQL UPDATE, SERVICE federation, and unbounded execution. Enforce least-privilege credentials and server-side policies.
- **Engineering validity:** Manufacturer catalog properties are not verified installed operating limits; semantic links are not physical installation proof.
- **Research scope:** Prioritize baselines, validation, and benchmark before UI polish.

## Immediate implementation milestones

1. Run a reproducible local GraphDB schema audit, including named graphs and temporal predicates.
2. Create representative RDF and temporal test fixtures without modifying canonical data.
3. Implement a typed plan schema and read-only SPARQL AST/policy validator.
4. Establish direct-generation and ontology-context baselines **before** adding feedback-guided repair.
5. Create gold-standard semantic and temporal questions with independently checked answers.
6. Integrate the validated executor into the Python API and expose execution/evidence traces in Vue.

## Publication positioning

Aim for NeurIPS 2027 if the work establishes a generalizable method with strong empirical evidence. A workshop or an alternative ML/knowledge-representation/industrial-AI venue remains a reasonable fallback. Acceptance is not guaranteed, and the scientific framing should be revisited after the literature review and February experiments.
