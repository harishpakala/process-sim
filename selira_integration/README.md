# SELiRA

**Contract-driven reference architecture for industrial life-cycle information**

The current TEP NEXUS experiment integrates four semantic contracts and two life-cycle policies. The earlier SC-01-only experiment remains available as a historical baseline.

## Architecture and realization

| Element | Implementation |
| --- | --- |
| D1 Semantic Representation | ONTO:NEXUS AAS-derived RDF/OWL |
| D2 Contract Processing and Compilation | Restricted SAFSL integrity fragment, semantic bindings, SHACL-SPARQL compiler and manifest |
| D2 Graph Validation | Local pySHACL |
| D2 Evidence-Aware Qualification | Caller attestations and structural validation |
| D2 Admission Control | Multi-contract coordinator and local versioned graph store |
| D2 Dependency Management | Graph projection and parsed SAFSL Boolean policy execution |
| D3 Information Services | Architectural responsibility, not independently evaluated |
| Automation Manager | Local multi-contract submission orchestration |

## Current specifications

| ID | Source | Realization |
| --- | --- | --- |
| SC-01 | [Asset–Product](contracts/safsl/SC-01.safsl) | SHACL |
| SC-02 | [DEXPI–Asset](contracts/safsl/SC-02.safsl) | SHACL |
| SC-03 | [Signal–Asset](contracts/safsl/SC-03.safsl) | SHACL |
| SC-04 | [BOM–Product](contracts/safsl/SC-04.safsl) | SHACL |
| LP-03 | [Change Impact Assessment](contracts/safsl/LP-03.safsl) | Restricted Boolean AST evaluator |
| LP-04 | [Selective Contract Revalidation](contracts/safsl/LP-04.safsl) | Restricted Boolean AST evaluator |

The SCs require exactly one distinct target for each predicate-selected focus resource using explicit RDF bindings and lexical identifier matching. Unassigned resources are outside that scope. See the [identity registry](contracts/identity_registry.json) for historical identifier collisions; it is descriptive, not a runtime resolver.

The multi-contract manager evaluates applicable contracts and admits atomically when at least one is validated and the remainder are validated or not applicable. Invalid dominates indeterminate; indeterminate blocks admission; all-not-applicable does not commit. Non-admitted submissions preserve the graph and version. Caller attestations are not independent engineering approvals.

LP-03 selects affected contract-focus pairs from the union of previous and candidate scopes. LP-04 selects reassessment or reuse. Python supplies projected Boolean inputs and computes reference outcomes; the restricted evaluator executes the parsed policy assignments. Unconfirmed coverage, policy stability or authority stability triggers full fallback. No process grammar extension was introduced for these policies. The evaluator is not a general SAFSL runtime. Policy files are located relative to the repository checkout.

## Reproduction

From the repository root with dependencies installed:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m selira_integration.evaluation.multi_contract_baseline
python -m selira_integration.evaluation.multi_contract_lifecycle
python -m pytest tests/selira (Get-ChildItem tests/test_safsl*.py).FullName -q
```

See the [evaluation guide](evaluation/README.md) for historical results and the [reported multi-contract verification](evaluation/results/multi_contract_reported_verification.txt) for current console evidence.

## Limitations

Local in-memory orchestration and controlled benchmark-derived RDF changes only. Full SHACL remains the validation gate. The comparison recomputes prior and full reference outcomes; logical counts are not measured runtime savings, persistent caching or native incremental SHACL. Independent evidence authentication, general entity resolution, distributed transactions and production deployment are outside scope. Historical contracts, adapters and policies remain available; see the [archive guide](archive/README.md) and [historical README](README.legacy.md).
