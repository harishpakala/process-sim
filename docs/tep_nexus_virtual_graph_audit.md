# TEP NEXUS — architecture and virtual-graph capability audit

Scope: code-level review of branch `refactor/repository-cleanup`, 2026-11-08. This is **not** a live GraphDB/TimescaleDB deployment audit. The status labels below refer to inspected code, not independently verified deployment behavior.

| Capability | Status | Code evidence | Gap / qualification |
|---|---|---|---|
| GraphDB engineering-function discovery | Implemented | `scripts/tep_nexus_mapping_discovery.py`: `SPARQL`, `classify_bindings` | Path-constrained AAS/DEXPI/AssetInventory matching is provisional, not physical identity verification |
| Run-scoped mapping eligibility | Implemented | `scripts/tep_nexus_function_registry.py`: `load_supported_functions` | Requires discovery and temporal coverage snapshots; run identity operator supplied |
| Live semantic mapping recheck | Implemented | `scripts/tep_nexus_function_registry.py`: `resolve_supported_mapping` | Checks snapshot equality, not cross-system provenance |
| Read-only historian retrieval | Implemented | `scripts/tep_nexus_semantic_temporal_live.py`: `retrieve_temporal_context`; `scripts/tep_nexus_fault_relative_query.py`: `retrieve_fault_relative_evidence` | Query paths differ; no common graph-oriented operation contract |
| Event-relative temporal classification | Implemented | `scripts/tep_nexus_fault_relative_query.py`; `src/process_sim/api/temporal_intervals.py` | Command-derived intervals do not establish physical fault states |
| Constrained natural-language planning | Implemented | `scripts/tep_nexus_ollama_query_planner.py`: `plan_question`, `validate_plan` | Plans are workflow-specific, not general virtual graph algebra |
| Deterministic analytics and provenance caveats | Implemented | `scripts/tep_nexus_fault_relative_analysis.py`; `scripts/tep_nexus_grounded_explanation.py` | Grounding screen is heuristic, not formal semantic verification |
| Stable virtual resource identifiers | Partial | Existing function, asset URI, run UUID, signal IDs and event IDs | No documented canonical URI contract for historian observations |
| Unified graph-shaped query results | Partial | Separate JSON evidence reports; `scripts/tep_nexus_virtual_graph.py` provides an initial **offline projection** | Not yet a runtime federated graph API |
| SPARQL access to virtual historian resources | Missing | No such execution path identified in inspected scripts | Must decide whether required; graph-shaped API alone is not SPARQL federation |
| Independently verified physical binding / shared run provenance | Not established | Explicit `NOT_VERIFIED` markers | Requires independent evidence beyond logical mapping |
| Storage/latency comparison against materialized RDF | Not established by this audit | — | Requires controlled benchmarks and explicit baselines |

## Architectural finding

The working integration currently follows **GraphDB semantic resolution → Python orchestration → TimescaleDB SQL → JSON evidence**. This is a valid cross-source demonstrator, but should not yet be described as a general-purpose virtual RDF/SPARQL knowledge graph. The immediate implementation increment is an **offline, deterministic graph projection** with explicit, namespaced virtual identifiers and source attribution, using already retrieved evidence. This separates graph representation from fault-specific query logic without moving measurements into GraphDB.

## Next implementation gates

1. Define stable URI/identity rules, including duplicate historian observations and timestamp precision; avoid treating timestamp alone as a guaranteed database primary key.
2. Implement a read-only, validated runtime virtual graph query interface over GraphDB and TimescaleDB (reuse existing resolvers, no model-generated SQL).
3. Add entity/observation/event query operators and cross-source provenance tests.
4. Decide whether SPARQL compatibility is a requirement, and evaluate RDF-star/R2RML/OBDA or a constrained graph API against that requirement.
5. Benchmark correctness, latency, freshness, storage overhead and query coverage against documented alternatives.

## Explicit limitations

A generated virtual graph is **not** evidence that observations have been materialized as RDF or that GraphDB supports querying them directly. A provisional semantic mapping is **not** a verified physical sensor binding. A recorded operator command is **not** proof of physical fault causation.
