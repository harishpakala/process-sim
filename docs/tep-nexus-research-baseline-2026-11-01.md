# TEP NEXUS — semantic-temporal research baseline (2026-11-01)

> **Status:** Experimental, operator-reported local executions. This document records what was demonstrated, not an independently audited CI or physical-plant validation. The local scripts described below were not present on the GitHub default branch when this documentation was drafted; commit and review their actual source separately.

## Research objective

TEP NEXUS investigates **cross-domain engineering knowledge integration and temporal operational-data access through a knowledge-graph-oriented interface**, with a natural-language user interface. The Tennessee Eastman Process (TEP) is an experimental data source, **not** a claim of a high-fidelity validated physical plant. Success is measured by traceable semantic-temporal retrieval and interoperability, not perfect OPC UA/TimescaleDB sample alignment.

## Architecture and data sources

- **GraphDB** repository: `http://localhost:7200/repositories/AAS`. Semantic relationships across DEXPI-style engineering function identifiers, AAS references, and AssetInventory operational references.
- **TimescaleDB**: `public.signal_samples(run_id, simulation_time_hours, signal_id, value, observed_at)`. Read-only, operator-selected run; DSN supplied by `TEP_TIMESCALE_DSN` (never commit credentials).
- **OPC UA** simulated source: `opc.tcp://127.0.0.1:4841/process-sim/`; `TEP.Measurements.XMEAS9` and simulation clock are exposed. Shared OPC UA/database run identity **not verified**.
- **Local Ollama**: `llama3.1:8b` at `http://localhost:11434`, for explanation and, in the later prototype, constrained JSON query planning.
- **RDF adapter**: local Turtle serialization using SOSA, PROV-O, OWL-Time, and project-specific `tep:` predicates. This is an exported/query-time RDF representation, **not** continuously synchronized or materialized in GraphDB.

### Demonstration semantic path

`TI_101` (engineering function) → `https://aas.example.com/TI_101` (AAS function reference) → `XMEAS9` (operational signal) → AssetInventory asset URI `http://org.example.com/aHR0cHM6Ly9leGFtcGxlLm9yZy9zbS90ZXAtYXNzZXQtaW52ZW50b3J5/QXNzZXRzLlRFUF9YTUVBUzk`.

The GraphDB resolution uses a **path-constrained** SPARQL join through DEXPI, AAS element paths, and AssetInventory operational reference, not a free-form identifier guess. Mapping status: **`PROVISIONAL_ENGINEERING_MATCH`**. This does **not** establish engineering approval, physical sensor binding, or source authenticity.

## Local implementation artifacts

These paths describe locally executed prototypes; **presence in the GitHub branch must be checked independently**.

| Local script / artifact | Purpose |
| --- | --- |
| `scripts/tep_nexus_ollama_integration.py` | Earlier graph-resolution + time-series + Ollama proof of concept |
| `scripts/tep_nexus_cross_store_validator.py`, `scripts/tep_nexus_cross_store_validator_v2.py` | Read-only OPC UA / TimescaleDB sampling checks; timing alignment is not the main research target |
| `scripts/tep_nexus_semantic_temporal_live.py` | Graph-resolved latest/history query; optional periodic watch |
| `scripts/tep_nexus_virtual_temporal_kg.py` | Query-time property graph JSON from GraphDB context and TimescaleDB samples |
| `scripts/tep_nexus_rdf_temporal_adapter.py` | Local SOSA/PROV-O/OWL-Time Turtle export, parse round-trip, local SPARQL |
| `scripts/tep_nexus_nl_query.py` | Rule-based question interpretation, federated retrieval, Ollama answer |
| `scripts/tep_nexus_ollama_query_planner.py` | Ollama-generated constrained JSON plan, deterministic plan validation, federated retrieval, Ollama answer |
| `reports/tep_nexus_semantic_temporal_live.json` | Example retrieval report |
| `reports/tep_nexus_virtual_temporal_kg.json` | Virtual property-graph snapshot |
| `reports/tep_nexus_temporal_graph.ttl` | Local RDF export |
| `reports/tep_nexus_nl_query.json` | Natural-language query evidence and answer |
| `reports/tep_nexus_ollama_planned_query.json` | Raw plan, validated plan, evidence, answer, execution status |

**Do not commit** database credentials, tokens, private host configuration, or unreviewed raw operational datasets. Reports may contain environment-specific identifiers and should be sanitized or replaced with minimal curated fixtures for publication.

## Demonstrated local results

All results below were supplied from local PowerShell execution on 2026-11-01; they are **individual observations**, not repeated benchmark statistics.

1. **Semantic-temporal query:** `TI_101` resolved to `XMEAS9` and the associated AssetInventory URI. A ten-simulation-minute window returned **206 samples** in one run. Five periodic watch iterations showed advancing persisted simulation times **2503, 2509, 2515, 2521, 2523 seconds**.
2. **Virtual temporal property graph:** **205 temporal observations**, **210 nodes**, **413 edges**. Five context nodes plus 205 observation nodes; three context edges and two edges per observation. The observation IDs were **query-local**, not persistent RDF identifiers.
3. **RDF temporal export:** latest **20 SOSA observations**, **239 RDF triples**, Turtle serialization/parse round-trip **PASS**, local SPARQL query **PASS**. Example latest exported observation: simulation time **2650 seconds**, value approximately **120.408796**, recorded at `2026-11-01T23:16:46.978620+01:00`. Local SPARQL is **not** a live GraphDB temporal SPARQL endpoint.
4. **Natural-language explanation:** rule-based parser interpreted a question about `TI_101`, the associated asset, and the last ten simulation minutes. Retrieved **205 samples**, latest value **120.39089576343358** at **2868 simulation seconds**, range **120.3699346804799–120.42360688151687**. Ollama answer agreed with checked values and included provisional mapping / unverified provenance caveats. Answer validation was explicitly **`NOT_AUTOMATICALLY_VERIFIED`**.
5. **Constrained Ollama planner:** `llama3.1:8b` produced `{intent: latest_and_history, engineering_function: TI_101, history_window_minutes: 10, include_asset: true, include_provenance: true}`; deterministic validation accepted the plan. Retrieval returned **201 samples**, latest **120.40902468910848** at **3043 simulation seconds**, range **120.3699346804799–120.42168665286619**, record age approximately **4.758 seconds** at query time. Status **`COMPLETED`**. The answer reproduced values and caveats, but answered a request for a *trend* using only min/max/sample count, not a computed slope or defensible trend characterization.

### Interpretation of the evidence

- **Demonstrated:** engineering-function-driven semantic resolution; read-only temporal history retrieval; query-time property graph assembly; standards-vocabulary RDF export and local SPARQL; constrained LLM JSON plan generation with deterministic validation for one supported function; evidence-grounded answer generation in the tested examples.
- **Not demonstrated:** independent physical correctness of the `TI_101`–`XMEAS9` match; engineering approval; authenticated provenance; shared OPC UA/database run identity; persistent synchronized temporal RDF in GraphDB; arbitrary natural-language-to-SPARQL execution; robust performance or accuracy across a benchmark corpus.
- **Timestamp caution:** `simulation_time_hours` is the simulator clock; `observed_at` is a database-recorded timestamp. The RDF prototype maps recorded time to `sosa:resultTime`, but an independently verified physical observation time has not been established.
- **Graph semantics caution:** application-defined virtual edges can represent derived paths rather than asserted GraphDB triples. `prov:wasDerivedFrom` and `tep:` terms in the prototype are modeling choices, not proof of authenticated provenance.
- **LLM safety boundary:** the planner returns a restricted JSON plan; Python validates it; no LLM-authored SQL or SPARQL is executed. Validating a plan does not validate the factual accuracy or completeness of its natural-language answer.

## Reproduction (Windows PowerShell)

Prerequisites: running local GraphDB, TimescaleDB and Ollama services; the local scripts above available in the working tree; `TEP_TIMESCALE_DSN` set in the session; Python packages used by the scripts (including `requests`, `psycopg`, `asyncua` where relevant, and `rdflib`). The following run ID is **an example from the operator's session** and may not be available in another environment.

```powershell
$run = "10cfb1d1-2984-4932-8207-dc430ed60c2b"
python scripts\tep_nexus_semantic_temporal_live.py --run-id $run --window-minutes 10
python scripts\tep_nexus_virtual_temporal_kg.py --function TI_101 --run-id $run --window-minutes 10
python scripts\tep_nexus_rdf_temporal_adapter.py --limit 20
python scripts\tep_nexus_ollama_query_planner.py --question "For engineering function TI_101, show the latest measurement and the trend over the last 10 simulation minutes, including the associated asset and provenance." --run-id $run
```

These commands operate on changing persisted observations; exact counts, timestamps and values **will vary**. RDF conversion uses the prior virtual graph JSON snapshot, not a new database read. Before publishing reproducible results, pin dependencies, commit the scripts, add redacted fixtures, and test from a clean checkout.

## Research roadmap — explicitly NOT implemented at this checkpoint

| Next work | Status | Acceptance criterion |
| --- | --- | --- |
| Quantitative temporal trend analysis | **Not implemented** | Compute slope, endpoint delta, mean, standard deviation and coverage from actual returned samples; distinguish trend from range |
| Automated factual answer validation | **Not implemented** | Compare LLM claims with structured evidence; flag unsupported values, timestamps, relationships and omissions; include adversarial tests |
| Generalized multi-function query planning | **Not implemented** | Resolve multiple curated engineering identifiers through graph evidence; reject ambiguity/unsupported mappings; no hardcoded single-function shortcut |
| Query-plan evaluation suite | **Not implemented** | Test intent, function and window accuracy, invalid requests and prompt-injection resistance |
| Engineering-centric RDF SPARQL traversal | **Not yet tested** | One query starting from engineering function reaches asset, signal and temporal observations |
| Live/persistent RDF graph integration | **Not implemented** | Clearly specified refresh/provenance policy, query semantics and freshness tests |
| Independent provenance / correspondence qualification | **Not verified** | Reviewed engineering evidence and source/run traceability, not simply graph co-occurrence |

## Suggested DTwiSE 2027 claim

> An experimental prototype demonstrated a federated engineering-to-temporal retrieval path, query-time temporal graph construction, local standards-vocabulary RDF export with SPARQL retrieval, and a constrained local-LLM interface that produced and validated a structured query plan before executing read-only semantic and time-series retrieval. These demonstrations do not establish physical sensor equivalence, authoritative correspondence, continuous RDF synchronization, or generalized planner accuracy.

**Research focus:** semantic interoperability, explicit evidence/provenance boundaries, temporal access, and testable natural-language interaction—not fidelity of the TEP simulator.
