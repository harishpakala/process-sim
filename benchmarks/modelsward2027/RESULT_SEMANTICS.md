# Candidate result semantics v1
Entity and entity-pair retrieval use set agreement; literal property retrieval uses bag agreement. Report both set and bag agreement and duplicate counts for transparency. This is a proposed task-level scoring policy, not a change to SPARQL bag semantics. SD11 overlap (four recorded rows, three entities) is scored as a set; SD12 also uses set agreement. SD05/SD17 retain multiplicity. Do not normalize before LIMIT or claim ordered correctness: six ordered scenarios remain blocked pending tie review. Negative cases require separate policy evaluation. All cases require structural review, especially empty results. Explicit projection-role alignment must be supplied independently; positional inference is not accepted. Blank nodes are unsupported pending a scoped identity policy. Literal lexical form, datatype and language are preserved (plain strings normalized to xsd:string). No production compiler or historical references changed.

Run from repository root:
```sh
python benchmarks/modelsward2027/test_result_semantics.py
```
The tests are synthetic scoring regressions, not live SPARQL execution. The module is not yet wired into the benchmark runner. Independent approval and live reference validation remain pending.
