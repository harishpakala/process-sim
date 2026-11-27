# IC-10D — Configuration extensibility and regression verification

## Scope

The SELiRA integration core separates RDF schemas, SAFSL contracts, semantic bindings and comparison policies from integrity governance mechanisms. This is configuration extensibility within supported patterns, not empirical cross-industry validation.

## Changes

- Explicit impact and selection policy paths accepted by the manager and reassessment engine.
- Directory discovery accepts arbitrary SAFSL filenames paired with JSON bindings.
- Standalone field matching supports lexical_equality and normalized_asset_identifier.
- Existing TEP NEXUS contracts and bindings unchanged.

## Verification

Reported local execution on 2026-11-27:

- Combined manager, bounded runtime, SPARQL export and runtime extensibility tests: 41 passed in 81.38 seconds.
- SPARQL differential suite: 192 bounded graph configurations (128 referential, 32 normalized identifier, 32 lexical), across two namespaces.
- Synthetic runtime transfer: five submissions testing admission, unrelated change, rejection, missing evidence and full fallback.
- Regenerated baseline: exact SHACL/standalone SPARQL violation-set agreement for all four contracts; SC-01: 0, SC-02: 9, SC-03: 29, SC-04: 0.
- Integrated lifecycle: baseline F; 16 submissions, 7 admitted, 8 rejected, 1 deferred; 2444 full and 203 selective logical evaluations; 13/13 equivalent comparisons; 91.69394435351882% logical reduction.

Commands from repository root:

```sh
python -m pytest tests/selira/test_multi_contract_manager.py tests/selira/test_ic09_bounded_runtime.py tests/selira/test_ic10_sparql_export.py tests/selira/test_ic10_runtime_extensibility.py -v
python selira_integration/evaluation/regenerate_contracts.py
python selira_integration/evaluation/multi_contract_lifecycle_ic09.py
```

## Supported configuration and limitations

The runtime accepts one contract per specification file, predicate-based focus selection, lexical class-targeted referential lookup, and singleton nonempty referential identifier projections. Standalone field comparisons require singleton values; lexical equality compares string representations rather than RDF term or numerical equivalence. Normalized asset identifier comparison retains its HTTP(S) suffix convention and approved exception pairs.

Evidence attestations are caller supplied. Predicate selection assumes independent structural validation of required fields. Reassessment relies on coverage and context stability attestations and is logical reference reassessment, not incremental SHACL execution or measured runtime speedup.

Directory discovery skips unpaired SAFSL files; use explicit artifact lists when completeness of configuration must be controlled. Legacy default policy paths still depend on repository layout; supply explicit paths for independent use. Standalone packaging and formal evaluator synchronization remain pending. The synthetic transfer test covers one lexical consistency contract and is not an independent industrial dataset.

Verification results above are user-reported local executions, not independently executed by the documentation author. Full repository test suite was not rerun for this stage.
