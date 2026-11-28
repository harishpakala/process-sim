# Benchmark correctness audit — candidate
Static inspection of the current manifest, reference metadata and recorded GraphDB bindings. No live rerun or independent semantic sign-off. All 46 scenarios remain pending review; no benchmark freeze.

## Findings
- 46 scenarios, 230 questions, 40 SELECT references and 6 rejection cases.
- SD11: recorded 4 rows but 3 distinct entities. Proposed entity-set semantics would require a reference/compiler or scoring contract change. SD12 has no recorded duplicate, but uses the same UNION pattern.
- SD05 and SD17: repeated projected literal values (31 and 7 duplicate rows respectively); decide whether value retrieval means per-entity bags or distinct values. Do not globally deduplicate.
- SD13/14 and CD15–18: inspect sort keys over unrestricted results and define tie behavior before scoring LIMIT.
- E45/E46: recorded empty results cannot establish correct structural interpretation.
- N39–44: define explicit negative policy and distinguish refusal, invalid plan, blocked query and accepted wrong SELECT. N41/42 ambiguity is a task contract, not universal SPARQL invalidity. N43 mapping governance and N44 write safety must be checked without oracle labels. Never execute writes.
- All positive cases: independent owner, projection, filter, mapping and graph review still required.

## Usage
Run from repository root:
```sh
python benchmarks/modelsward2027/validate_benchmark_contract.py
```
The script checks metadata and recorded bindings, not query semantics or live graph state. --require-freeze deliberately fails until a separate reviewed freeze gate is implemented. The JSON audit is a review ledger, not a correctness label. Preserve historical results and version any corrected references. No original benchmark files changed.
