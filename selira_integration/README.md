# SELiRA

**Contract-driven reference architecture for industrial life-cycle information**

SELiRA integrates declarative integrity contracts, evidence-aware qualification, controlled admission and dependency-based reassessment. The experimental realization uses SC-01 (asset-to-product integrity) in TEP NEXUS.

## Architecture

| Element | Implementation and status |
| --- | --- |
| D1 — Semantic Representation | ONTO:NEXUS AAS-derived RDF/OWL |
| D2 — Contract Processing | Restricted SAFSL parser and semantic bindings |
| D2 — Constraint Compilation | SAFSL-to-SHACL compiler and manifest |
| D2 — Graph Validation | Local pySHACL validation |
| D2 — Evidence-Aware Qualification | Admission coordinator and caller attestations |
| D2 — Admission Control | Local versioned graph store |
| D2 — Dependency Management | SC-01 dependency tracker and reference evaluator |
| D3 — Information Services | Architectural responsibility, not independently evaluated |
| Automation Manager | Local SC-01 submission orchestration |

## Contract specification and compilation

[SC-01](contracts/safsl/SC-01.safsl) requires each applicable asset to match exactly one distinct product resource. [Semantic bindings](contracts/bindings/SC-01.json) resolve AAS template identifiers to RDF classes and properties. The current dataset uses ai:hasProductIdentifier and pc:hasProductIdentifier, predicate-based asset focus, class-based product selection and lexical equality. Compilation produces SHACL-SPARQL shapes and a manifest recording dependencies and required completeness scopes.

## Qualification and admission

The Automation Manager compiles the contract, projects candidate snapshots, checks expected versions and coordinates reassessment and admission. It assumes one nonempty lexical identifier per projected resource and checks that assigned focus nodes are typed assets.

| Outcome | Local decision |
| --- | --- |
| V — Validated | Commit subject to version check |
| F — Invalid | Reject |
| U — Indeterminate | Defer |
| NA — Not applicable | No commit for confirmed empty scope |

Non-admitted submissions preserve the admitted graph and version. Completeness, applicability and canonical identity are caller attestations, not independently authenticated evidence. Authority stability is supplied to reference reassessment; independent source authority qualification is not implemented. Full compiled SHACL remains the graph-validation gate when evidence and scope permit validation.

## Dependency-based reassessment

The SC-01 reference model tracks asset assignments, identifier-specific lookup scopes (including possible new matches), and completeness. Unconfirmed coverage, policy stability or authority stability triggers full reference reassessment. For successive submissions reaching the comparison stage, the manager compares selective and full reference outcomes; disagreement prevents admission. This is not a persistent outcome cache or native incremental SHACL engine.

## Repository organization

Paths relative to the repository root:

| Path | Responsibility |
| --- | --- |
| src/process_sim/safsl/shacl/ | Compiler, validation and admission |
| src/process_sim/selira/automation_manager.py | Local orchestration |
| selira_integration/contracts/safsl/ | Executable contract source |
| selira_integration/contracts/bindings/ | Semantic bindings |
| selira_integration/formal/ | Formal models and reference reassessment |
| selira_integration/lifecycle.py | SC-01 snapshot reference semantics |
| selira_integration/evaluation/ | Experiments and archived results |
| tests/selira/ and tests/test_safsl_*.py | Experimental and regression tests |
| semantic/ontology2/ | Engineering RDF inputs |

Earlier GraphDB adapters, handwritten shapes, SC-02–SC-06 and LP-01–LP-06 specifications remain in the repository but are not part of the current integrated SC-01 experiment. See the [archived README](README.legacy.md) for historical context.

## Reproduction

From the repository root with process_sim and its dependencies installed:

```powershell
python selira_integration/evaluation/characterize_dataset.py
python -m process_sim.safsl.shacl.compiler selira_integration/contracts/safsl/SC-01.safsl selira_integration/contracts/bindings/SC-01.json selira_integration/contracts/generated/SC-01
python -m selira_integration.evaluation.sc01_lifecycle
```

See the [evaluation guide](evaluation/README.md) for the focused regression command, recorded source revisions, results and environment caveats. The integrated experiment uses local RDF files without live GraphDB or TimescaleDB.

## Recorded engineering results

| Measure | Result |
| --- | ---: |
| RDF triples | 7,042 |
| Assets / products | 43 / 20 |
| Applicable assigned assets | 38 |
| Candidate submissions | 8 |
| Admissions / rejections / deferrals | 4 / 3 / 1 |
| Selective/full reference agreement | 7/7 |
| Full / selective logical evaluations | 266 / 96 |
| Logical evaluation reduction | 63.91% |
| Focused regression tests | 43 passed |

These are previously recorded results, not a new run after documentation changes. The broader suite has unresolved import/collection errors. Counts measure logical reference evaluations, not runtime savings.

## Scope and limitations

The current realization is restricted to SC-01, local in-memory orchestration and controlled perturbations of benchmark-derived RDF. Independent evidence authentication, general entity resolution, distributed transactions, persistent manager audit history and native incremental SHACL execution are outside its scope. D3 remains an architectural responsibility. Earlier experimental modules and policies are retained pending dependency audit. No production readiness or general compiler correctness is claimed.
