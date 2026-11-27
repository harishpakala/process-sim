# SELiRA artifact restructuring audit

Baseline: 20cb091239cc6cbf888100826416abbaeff79241 (merged PR #32). This is a restructuring baseline, not an independently established experiment revision.

## Inspected dependency closure

- Language: process_sim/safsl/{ast,parser,grammar}; Lark; importlib.resources package paths.
- Compiler: process_sim/safsl/shacl/compiler.py; Lark, RDFLib; contracts.lark resource.
- Runtime: shacl/admission.py (RDFLib, pySHACL), selira/multi_contract_manager.py, reassessment/{multi_contract,policy}.py. Policy evaluator imports SAFSL AST and parser. Multi-contract evaluator resolves LP files through a repository-relative path. Manager.from_directory expects safsl/ and bindings/ siblings.
- Reference semantics: shacl/reference_semantics.py.
- Bounded SC01 reassessment: reassessment/{snapshot,dependency,sc01_dependencies,selective_sc01}.py; selira_integration/lifecycle.py and formal/selective_sc01.py compatibility imports used by tests.
- Evaluation: multi_contract_baseline.py and multi_contract_lifecycle.py depend on repository-relative contract, binding, dataset and output paths. Five instance graphs under semantic/ontology2: assetinventory, productcatalog, dexpi, opcuaconnectivity, engineeringbom.
- Verification: tests/test_safsl_semantics_differential.py, tests/test_safsl_admission.py, tests/selira/test_lifecycle_policy_safsl.py, test_multi_contract_manager.py, test_selira_f7_selective_equivalence.py. Further test and fixture closure audit required.
- Direct core dependencies observed: lark, rdflib, pyshacl; pytest for tests. Exact environment lock not established.

## Migration plan

Create an isolated artifact package with language, compiler, runtime and formal modules; separate contracts, bindings, policies, datasets, tests and evaluation. Preserve existing process_sim imports and integration until compatibility is verified. Resolve grammar resources and policy paths explicitly; update experiment paths and preserve archived result files unchanged. Do not change algorithms or evidence semantics during relocation.

## Acceptance

Reproduce 81 SC01 graph configurations, 80 policy configurations, 1296 SC01 transitions, integrated 11 submissions (5 admitted, 5 rejected, 1 deferred), 9 equivalent comparisons and 195/1638 logical evaluations. Run existing regression suite. These are reported targets, not new test results. Full SHACL remains the gate; logical reduction is not runtime improvement.

## Open items

Complete transitive import and fixture audit, inspect package initializers, verify dataset redistribution and licensing, establish citation metadata, pin dependencies from a verified environment, and run tests locally. No source relocation or algorithm changes in this audit commit.
