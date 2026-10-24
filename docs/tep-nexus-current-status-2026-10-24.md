# TEP NEXUS — Current Project Status

**Status date:** 24 October 2026  
**Working branch:** `feat/local-ollama-grounded-ai`  
**Purpose:** Evidence-aware project snapshot for engineering handoff and CAiSE 2027 planning. This document distinguishes repository implementation, previously reported local runs, and unverified integration. It is not a certification of production readiness.

## 1. Executive summary

TEP NEXUS is a research prototype for an industrial semantic digital twin built around the Tennessee Eastman Process (TEP). Its intended architecture combines the TEP simulation, OPC UA connectivity, operational history, MES and ERP, AAS-based engineering representations, semantic lifting to RDF/OWL, GraphDB, and local evidence-grounded Ollama question answering.

**Verified in the inspected branch:** repository documentation for TEP simulation, OPC UA, AAS lifting, and engineering-domain source checks; source code for a read-only GraphDB-to-Ollama Q&A prototype and RDF relationship audit scripts.  
**Previously reported local execution:** GraphDB graph inventory, entity-link audits, and Ollama test runs described below. These are historical observations from the development session, not freshly rerun by this documentation change.  
**Not yet verified as an end-to-end system:** TEP → OPC UA → TimescaleDB → semantic asset → GraphDB → AI, including MES/ERP data exchange. MES and ERP are reported as implemented by the project owner, but their concrete interfaces and runtime evidence still require a targeted repository/runtime audit.

## 2. Architecture inventory and evidence level

| Layer / capability | Current evidence | Outstanding validation |
|---|---|---|
| TEP reference simulation | Existing README documents adapter, deterministic simulation boundary, lifecycle and engineering measurements. | Capture a reproducible scenario with run ID, variable IDs and timestamps. |
| Faults and scenarios | README documents fault manager, native disturbances, controlled experiments and recording. | Confirm repeatable experiment outputs and provenance. |
| OPC UA | README documents simulation controls, XMEAS/XMV and fault-management methods. | Demonstrate live subscription/read with timestamps and stable asset identity. |
| TimescaleDB / historian | Project owner reports operational data infrastructure; older README still lists historian/TSDB as outstanding. | Inspect code, schema, deployment and live writes; resolve documentation discrepancy. |
| MES | Project owner reports implementation. | Inspect module, API, transaction boundaries and linkage to TEP/asset identifiers. |
| ERP | Project owner reports implementation. | Inspect module, API and linkage to MES, BOM and asset identifiers. |
| AAS semantic lifting | Repository documents configured DEXPI, ECAD, ProductCatalog and AssetInventory template/instance lifting; SHACL validation. | Repeat RDF completeness checks on current sources and pin versions. |
| AssetInventory | Historical source check: 62 assets. Previously reported GraphDB Q&A inventory: 62 assets, 38 ProductReferences, 5 candidate-only, 19 unmapped. | Verify exact mapping coverage and entity-level links to other domains. |
| ProductCatalog | Previously reported GraphDB Q&A inventory: 20 products; candidate status is distinct from installed/approved status. | Reconcile versioned JSON source and GraphDB contents. |
| Engineering BOM | Engineering review workflow and graph data exist; revision governance is explicitly deferred in README. | Verify approved physical membership separately from functional or candidate relationships. |
| ECAD and DEXPI | AAS models and semantic lifting exist; source-level cross-reference checks documented in README. | Establish and verify the intended current graph joins without reusing earlier paper results as new novelty. |
| OPC UA Connectivity AAS | Previously reported as present in GraphDB. | Verify asset-to-node references and live values. |
| GraphDB / RDF | Previously reported audit of 34,155 triples across multiple engineering domains. | Repeat against a pinned graph export; validate provenance, joins and query completeness. |
| Ollama grounded Q&A | `scripts/ask_graphdb_ollama.py` performs fixed SELECT-only GraphDB retrieval and local Ollama reasoning; no model-generated SPARQL or plant actions. | Run controlled benchmark and verify output correctness independently. |
| Frontend | README documents a Vue/Vite prototype and JSON-derived graph preview. | Do not claim that the preview is live GraphDB/SPARQL without verification. |

## 3. Semantic lifting and source checks

The README records earlier `Conforms: True` SHACL results for DEXPI, ECAD, ProductCatalog and AssetInventory. The historical ECAD result of **96 instance triples** predates restoration of a larger ECAD dataset and **must not be treated as the current ECAD size**.

Source-level checks previously documented in the README include:
- ECAD: 40 devices, 100 standard `EndPoint` collections, 40 PLC `PLCEndPoint` collections, 102 schematic relationships and 2 electrical nets.
- All 102 ECAD schematic relationship endpoints resolved to existing instance elements in that check.
- All 38 ECAD devices with manufacturer part numbers matched ProductCatalog part numbers in that check.
- All five checked AssetInventory `EngineeringReference` values matched DEXPI `AssetIdentifier` values.
- DEXPI source included five equipment, 22 instrumentation functions and 12 actuating functions.

**Interpretation:** source-level matches do not prove that corresponding RDF-level engineering relationships are materialized or that live operational/enterprise data is connected.

## 4. GraphDB audit — previously reported local run

`scripts/audit_graphdb_cross_domain.py` reported:

| Metric | Result |
|---|---:|
| RDF triples scanned | 34,155 |
| Distinct subjects | 5,388 |
| Subject namespaces | 25 |
| RDF classes | 34 |
| Predicates | 319 |
| Cross-namespace IRI relationship groups | 77 |
| Potential truncation | False |

**Caution:** cross-namespace IRI groups can include `rdf:type` and schema relationships. They do **not** imply 77 verified engineering-domain joins.

`scripts/audit_graphdb_entity_links.py` subsequently reported:

| Domain pair | Explicit entity RDF edges found | Exact identifier match groups | Conservative classification |
|---|---:|---:|---|
| AssetInventory ↔ ProductCatalog | 0 | 16 | Potential identifier join; verification required |
| AssetInventory ↔ Engineering BOM | 0 | 5 | Potential identifier join; verification required |
| Engineering BOM ↔ ECAD | 0 | 0 | Not established by this audit |
| AssetInventory ↔ OPC UA Connectivity | 0 | 0 | Not established by this audit |
| DEXPI ↔ AssetInventory | 0 | 0 | Not established by this audit |

This script uses selected domain and identifier heuristics. **A zero is not proof that a relationship is absent from the entire graph.** The next task is to inspect nested AAS references, encoded identities, engineering tags and actual RDF predicates before asserting or materializing joins.

## 5. Grounded engineering Q&A — previously reported local tests

Relevant implementation:
- `scripts/ask_graphdb_ollama.py` — read-only fixed GraphDB SELECT queries, evidence selection, local Ollama responses and fact guards.
- `scripts/test_graphdb_ollama_engineering.py` — five engineering review cases.

Previously reported results:
- Engineering suite: **5/5 EVIDENCE PASS**, zero automated failures.
- Separate earlier asset-oriented tests reported passing results, including coverage over 62 assets; these are historical test observations, not a fresh CI result.
- Guarded reactor case: `TEP_Reactor` remains `REQUIRES_ALTERNATIVE`; missing numerical pressure evidence must not be invented.
- Guarded unmapped measurement case: `TEP_XMEAS23` has no selected `ProductReference` or `CandidateProductReference`; a physical product must not be inferred.

**Limit:** evidence selection and guard checks do not establish general answer correctness. A controlled baseline comparison and independent review are still needed.

### Local reproduction commands

Run from the repository root with GraphDB and, where applicable, Ollama running:

```powershell
python scripts/audit_graphdb_cross_domain.py
python scripts/audit_graphdb_entity_links.py
python scripts/test_graphdb_ollama_engineering.py
python scripts/test_graphdb_ollama_assets.py
python scripts/test_graphdb_ollama_all_assets.py
```

The default GraphDB SPARQL endpoint in the Q&A script is `http://localhost:7200/repositories/AAS`; the default Ollama model is `llama3.1:8b`. Check script-specific `--help` and environment settings before execution. These commands do not establish TimescaleDB, MES or ERP integration.

## 6. Engineering governance and safety boundaries

The README explicitly defers full physical BOM revision supersession, comparison, withdrawal/correction and formal release. **Functional correspondence, candidate selection, engineering approval and physical installation are distinct states.** Do not infer installed hardware from a provisional ProductCatalog candidate. The Q&A prototype is read-only and must not be described as autonomous plant control.

## 7. Publication boundary and CAiSE 2027 research plan

Prior published foundation: *From Asset Administration Shells to Knowledge Graphs: Rule-Based Semantic Lifting for Cross-Domain Reasoning in Cyber-Physical Systems* (MODELS Companion 2026). It already introduces AAS-to-OWL/RDF semantic lifting, SHACL structural validation, ECAD–DEXPI integration and knowledge-graph-derived PLC bindings. **Do not claim these as newly invented by TEP NEXUS.**

Proposed **new** CAiSE contribution, contingent on evaluation:
1. Cross-layer industrial information architecture linking engineering, operational and enterprise information.
2. Verified asset-centered semantic integration and measurable cross-domain traceability.
3. Evidence-grounded engineering reasoning with explicit uncertainty handling.

Proposed experiments:
- **E1:** Trace representative TEP assets/variables across simulation, OPC UA, historian, AAS, graph and relevant MES/ERP references; report actual coverage and missing links.
- **E2:** Evaluate verified semantic joins versus identifier-only baselines; distinguish explicit, verified inferred, ambiguous and absent links.
- **E3:** Compare LLM-only, KG-grounded and KG-grounded-plus-guards on independently reviewed answerable/unanswerable questions; measure correctness, unsupported claims, abstention and latency.

**Publication deadlines discussed (verify against official call before submission):** CAiSE 2027 mandatory abstract 4 November 2026 AoE; full paper 15 November 2026 AoE. Use an anonymized artifact/repository if required by the call. Do not report planned experiments as completed results.

## 8. Immediate action list (priority order)

1. **Freeze paper scope and prior-work boundary.** Document novelty relative to MODELS Companion and the separate systems-engineering paper.
2. **Audit TimescaleDB, MES and ERP implementation.** Locate actual modules, schema, APIs, test fixtures and running interfaces; update this document with file paths and evidence.
3. **Capture one reproducible end-to-end trace.** Start with one TEP asset and its measurement; record identifiers, timestamps, data stores and query outputs.
4. **Verify AssetInventory-centered joins.** Inspect RDF predicates and nested AAS references; resolve candidate links only with defensible identity evidence.
5. **Build evaluation harness.** Pin data snapshot, test cases, baselines, metrics and reproducibility instructions.
6. **Draft CAiSE abstract and manuscript in parallel.** Separate prior work, implemented contribution, measured results and limitations.
7. **Synchronize README roadmap.** Update Phase 5/7/9 descriptions only after historian/enterprise/runtime audit; the README currently reflects an earlier milestone.

## 9. Status conventions

- **Implemented (source):** code or model present in repository; runtime integration may remain untested.
- **Reported (local):** developer-supplied execution output from an earlier local run.
- **Verified (end-to-end):** reproducible observed data flow with traceable identifiers and recorded evidence.
- **Planned / unverified:** proposed functionality or integration without sufficient evidence.

**Snapshot provenance:** branch source files inspected on 24 October 2026 (`README.md`, `scripts/ask_graphdb_ollama.py`, `scripts/audit_graphdb_entity_links.py`, `scripts/test_graphdb_ollama_engineering.py`) plus previously reported local GraphDB/test outputs. No fresh GraphDB, TimescaleDB, MES, ERP or Ollama runtime was executed as part of this documentation commit.
