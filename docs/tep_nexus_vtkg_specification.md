# TEP NEXUS — Virtual Temporal Knowledge Graph (VTKG) Specification

**Status:** Version 0.1 — descriptive specification of the implemented prototype, not a claim of independent semantic validation.  
**Scope:** Ontology-guided, read-only semantic-temporal querying of Tennessee Eastman Process engineering and historian data.  
**Implementation references:** `scripts/tep_nexus_virtual_graph.py`, `scripts/tep_nexus_live_virtual_graph.py`, `scripts/tep_nexus_graph_operators.py`, `scripts/tep_nexus_function_registry.py`, `scripts/tep_nexus_unified_virtual_query.py`.

## 1. Research objective and boundary

TEP NEXUS provides a *logical* graph view joining engineering semantics in GraphDB to time-bounded process observations in TimescaleDB. Historian rows remain in TimescaleDB and are projected into graph-shaped results only on demand; they are **not bulk-materialized as RDF in GraphDB**. The current Python virtual graph is a query-result abstraction, **not** a general-purpose federated SPARQL endpoint or a persistent RDF graph.

The research question is whether this abstraction enables correct, provenance-aware semantic-temporal queries with acceptable overhead. Fault commands may be represented as recorded temporal events; fault diagnosis, causal inference, and physical fault-state claims are outside the research scope.

## 2. Source systems and trust boundaries

| Source | Role | Current verification |
|---|---|---|
| GraphDB AAS repository | Engineering function-to-signal mapping and associated engineering asset URI, resolved by constrained SPARQL | Live mapping is compared against a run-scoped discovery snapshot; mapping remains **provisional** |
| TimescaleDB `public.signal_samples` | Run-scoped historian observations, keyed by run UUID and signal ID | Read-only, parameterized SQL with bounded time interval and row limit |
| Run-scoped discovery and coverage JSON | Eligibility gate for supported functions and available historian signals | Snapshot checked for declared run and expected caveats; not independent ground truth |
| Caller | Run UUID, function, simulation-time interval, result limit | Syntactically validated; shared provenance is **not verified** |
| Ollama | Chooses from a fixed set of permitted graph operators | Output validated; no LLM-generated SQL/SPARQL or authoritative time bounds |

The system must not infer verified physical sensor identity, measurement units, shared simulation-run provenance, or causation from a provisional semantic match.

## 3. Formal virtual graph abstraction

For a validated request `q`, define the result graph:

`G_q = (V_q, E_q, A_q, P_q)`

where `V_q` is the set of virtual nodes, `E_q` the directed labeled edges, `A_q` the node attributes, and `P_q` the result-level provenance and execution metadata. `G_q` is created from the current GraphDB mapping and one bounded TimescaleDB retrieval. It is not persisted as an RDF dataset.

### 3.1 Node types

| Type | Identity | Core attributes | Source |
|---|---|---|---|
| `EngineeringFunction` | Virtual URI `function/{function_id}` | `localId`, provisional `mappingConfidence` | GraphDB mapping |
| `OperationalSignal` | Virtual URI `signal/{signal_id}` | `signalId`, `physicalSensorBinding=NOT_VERIFIED` | GraphDB mapping / TimescaleDB key |
| `EngineeringAsset` | Source asset URI | `physicalIdentity=NOT_VERIFIED` | GraphDB |
| `SimulationRun` | Virtual URI `run/{UUID}` | `runId`, `identitySource=operator_supplied`, `sharedRunProvenance=NOT_VERIFIED` | Caller |
| `VirtualObservation` | Virtual URI with content fingerprint, or fallback window ordinal | `simulationTimeHours`, `observedAt`, `value`, `identityScope`, `signalUnits=NOT_VERIFIED`, `windowIndex`, `truncatedWindow` | TimescaleDB |
| `RecordedFaultCommand` | Virtual URI `run/{UUID}/command/{event_id}` | `eventId`, `action`, `simulationTimeHours`, `observedAt`, `physicalFaultState=NOT_VERIFIED` | Supplied recorded fault evidence, if any |

URI fragments in this table are conceptual path suffixes; the implementation uses `https://example.org/tep-nexus/virtual/` and URL-escapes path segments. The asset retains its GraphDB source URI.

### 3.2 Edge predicates and direction

| Subject type | Predicate | Object type | Interpretation |
|---|---|---|---|
| `EngineeringFunction` | `mapsToSignal` | `OperationalSignal` | Provisional engineering-to-operational mapping |
| `EngineeringFunction` | `associatedWithAsset` | `EngineeringAsset` | Engineering asset associated with function |
| `SimulationRun` | `hasSignal` | `OperationalSignal` | Signal used in the requested run-scoped retrieval |
| `VirtualObservation` | `observesSignal` | `OperationalSignal` | Historian row's signal |
| `VirtualObservation` | `belongsToRun` | `SimulationRun` | Historian row selected by run UUID |
| `SimulationRun` | `hasRecordedCommand` | `RecordedFaultCommand` | Recorded command in supplied evidence; no causal implication |

These are **virtual projection predicates** implemented in Python. They must not be misrepresented as pre-existing RDF triples or formally established OWL properties in GraphDB. Temporal relation annotations, when supplied, are not automatically inferred causal relationships.

## 4. Query contract and temporal semantics

A live request contains `engineering_function`, `run_id` (valid UUID), `start_simulation_seconds`, `end_simulation_seconds`, and `limit` (integer 1–5000). Bounds must be finite, nonnegative, and ordered.

The historian selection is:

```sql
SELECT simulation_time_hours, value, observed_at
FROM public.signal_samples
WHERE run_id = %s::uuid AND signal_id = %s
  AND simulation_time_hours >= %s
  AND simulation_time_hours <= %s
ORDER BY simulation_time_hours, observed_at, value
LIMIT %s
```

The parameters are `run_id`, the **live-resolved signal ID**, `start_seconds/3600`, `end_seconds/3600`, and `limit+1` (to probe truncation). Both interval endpoints are **inclusive**. The result exposes at most `limit` observations and sets `truncated=true` if the probe finds more. SQL uses `simulation_time_hours` for selection; `observed_at` is a distinct timestamp attribute, not the simulation-time filter. Floating-point conversion and boundary precision need dedicated correctness tests.

### 4.1 Deterministic operators

- `resolve_function(G_q, function_id)`: returns the unique function node and its outgoing edges, otherwise errors.
- `get_observations(G_q, start_seconds, end_seconds)`: filters **already retrieved** virtual observations by simulation time; does not fetch additional database rows.
- `traverse_relationships(G_q, resource_id, predicate=None)`: returns outgoing edges from an existing virtual resource, optionally restricted by predicate.

The operators cannot execute arbitrary SQL/SPARQL or expand beyond the bounded graph snapshot.

### 4.2 Natural-language interface

Ollama selects an `engineering_function` and a subset of the permitted operator names. The contract requires the function explicitly mentioned in the question to match the caller's request, and exactly one explicit `between N [simulation] seconds and M` interval to match caller-supplied bounds. After validation, the implementation **always executes all three evidence-bearing operators**, regardless of which subset the model requested. The answer is deterministic and evidence-grounded. Arbitrary natural-language time expressions and unrestricted graph queries are not supported.

## 5. Identity, provenance, and uncertainty

Live observation IDs are derived from a SHA-256 fingerprint of canonical content: run UUID, signal ID, hexadecimal floating-point simulation hours and value, and normalized UTC `observed_at` (microsecond precision). This permits cross-window content matching but **is not a verified database primary key**. Two indistinguishable returned historian rows cause an error rather than silently merging their identities. Offline projections without fingerprints use query-window ordinal IDs and do not promise cross-query stability.

The live result declares:
- `observationIdentity.method=SHA256_CANONICAL_CONTENT_FINGERPRINT`, `databasePrimaryKeyVerified=false`;
- `provenance.semanticSource=GraphDB AAS repository`;
- `provenance.temporalSource=TimescaleDB public.signal_samples`;
- `provenance.runIdentitySource=operator_supplied`;
- `provenance.mappingConfidence=PROVISIONAL`;
- `provenance.physicalSensorBinding=NOT_VERIFIED`;
- `provenance.sharedRunProvenance=NOT_VERIFIED`;
- `materializedInGraphDB=false`.

These metadata describe the implementation and evidence sources; they do not establish independently verified real-world asset-to-sensor bindings.

## 6. Correctness properties and test obligations

| Property | Required condition | Current status |
|---|---|---|
| Mapping agreement | Live GraphDB mapping matches the eligible run-scoped registry entry | Implemented, structural tests |
| Request safety | UUID, function, finite ordered interval, and limit validated | Implemented |
| Retrieval equivalence | Same signal/run/window/limit yields identical historian observation content in virtual and direct paths | Initial 30/30 paired cases passed for TI_101 |
| Graph integrity | Every edge references existing nodes; required function/signal/asset edges exist | Implemented, structural checks |
| Temporal containment | Returned observation simulation times lie in the inclusive requested interval | Implemented filtering; independent boundary oracle pending |
| Observation identity | Fingerprints unique in a returned bounded retrieval and consistent across overlapping windows | Initial 102/102 overlap checks passed |
| Provenance honesty | Provisional mappings and unverified physical/shared-run claims remain explicit | Implemented, structural checks |
| No bulk RDF materialization | Historian observations retrieved from TimescaleDB and projected in memory | Architectural implementation; storage audit pending |
| Ground-truth correctness | Independent reference queries verify semantics and exact boundary behavior | **Pending** |
| Planner quality | Validated operator/function selection across diverse natural-language questions | **Pending systematic evaluation** |

The previously reported 102 semantic-temporal cases, 30 repeated TI_101 cases, and 30 paired TI_101 cases are **initial implementation evidence**, not a statistical proof of correctness or scalability.

## 7. Known limitations and proposed extensions

1. **Identity:** inspect the historian schema for a stable row primary key; do not assume one exists. If available, introduce a backward-compatible identity version and migration tests.
2. **Floating boundaries:** verify inclusive boundaries against independently executed SQL, including exact endpoints, empty intervals, and adjacent windows.
3. **Independent correctness oracle:** compare GraphDB source relationships and TimescaleDB rows to virtual results without reusing the same projection code as the oracle.
4. **Snapshot consistency:** GraphDB mapping and historian reads are not a single distributed transaction; paired baseline queries also run at different times.
5. **Ontology semantics:** document the actual GraphDB classes/properties and mapping SPARQL before claiming formal ontology entailment or a general-purpose federated graph.
6. **Query expressiveness:** current API is single-function and bounded-window; multiple functions, joins, aggregation, and richer temporal operators require explicit specification and tests.
7. **Performance and scale:** latency overhead is measured, but per-stage profiling, diverse workloads, freshness, and storage comparison remain open.
8. **Documentation consistency:** the offline projection's legacy limitations text describes ordinal IDs even when content fingerprints are used; align the message with the actual identity mode.

## 8. Reproducibility and next milestone

Run regression tests:

```powershell
python -m unittest discover -s tests -p "test_tep_nexus_*.py" -v
```

Then independently audit GraphDB mappings and TimescaleDB boundary results for selected functions and windows. Preserve the current validated interface while adding correctness tests and a machine-readable oracle report.

**Next milestone:** a *semantic-temporal correctness and provenance audit*, grounded in independent source queries, rather than further latency optimization.
