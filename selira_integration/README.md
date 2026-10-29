# SELiRA 12-contract GraphDB integration — experimental branch

This isolated prototype adds six semantic-contract specifications and SHACL-SPARQL shapes (SC-01–SC-06), six lifecycle-policy specifications (LP-01–LP-06), and a read-only GraphDB retrieval and SHACL runner. It does not alter existing AAS lifting code or GraphDB.

**Scope:** SC-01 uses the actual `ai:hasProductReference` and `pc:hasAssetIdentifier` RDF predicates. SC-02–SC-06 use proposed SELiRA evidence predicates and are **not mapped to authoritative engineering data**. Their shapes are scaffolds, not validated engineering rules. LP-01–LP-06 are specifications only, not implemented change listeners or selective revalidation.

Install dependencies: `pip install rdflib requests pyshacl`.

Example:

```bash
python -m selira_integration.runner \
  --endpoint http://localhost:7200/repositories/AAS \
  --graph 'ACTUAL_ASSET_INVENTORY_GRAPH_IRI' \
  --graph 'ACTUAL_PRODUCT_CATALOG_GRAPH_IRI' \
  --source-revisions revisions.json --ready SC-01
```

Supply `revisions.json` with real source revision identifiers. **Only pass `--ready SC-01` after verifying catalog completeness and engineering approval of the uniqueness rule.** Without readiness, the result is INDETERMINATE. A SHACL pass with no focus nodes does not establish validity. JSONL audit output is local, not RDF provenance.

Not yet verified: native pySHACL execution, live GraphDB access, all-domain source mapping, graph-change detection, dependency-based selective revalidation, and PROV-O history. Do not merge or use as production validation without review.

## Formal architecture roadmap (proposed; not yet implemented)

The research goal is an **evidence-aware, revision-sensitive semantic correspondence framework**, not merely a set of SHACL shapes. The following definitions are design targets, **not proven theorems or currently implemented guarantees**. Formal definitions, engineering authority, executable rules, and experiments must agree before claims are made.

### F1. Semantic correspondence model

Let `R` be the set of heterogeneous representations (DEXPI, ECAD, Asset Inventory AAS, Product Catalog AAS, TEP). A proposed correspondence is `k = (id, E, relation, context)`, where `E` contains participating engineering entities and `relation` is a proposed cross-representation claim. A proposal is **not** an accepted correspondence. Context includes identity, physical meaning, units, engineering authority, provenance, and revisions. Define explicit scope and identity for every correspondence; never infer equivalence from lexical similarity alone.

### F2. Engineering semantic contract semantics

A contract is `SC = (id, scope, preconditions, predicate, evidence requirements, dependencies, version)`. Evaluation is `Eval(SC, k, G_r, A_r) -> {VALIDATED, INVALID, INDETERMINATE, NOT_APPLICABLE}`, where `G_r` is a consistent source revision snapshot and `A_r` the approved engineering requirements. A contract must distinguish (a) out-of-scope, (b) insufficient evidence, (c) supported satisfaction, and (d) supported violation. Absence of evidence is not automatically a violation. SHACL conformance reports are implementation evidence, not automatically the final four-valued decision.

### F3. Contract composition (next definition milestone)

For a correspondence `k`, evaluate the applicable contract set `A(k,r)`. A conservative **proposed** composition policy is:

| Applicable results | Aggregate outcome |
| --- | --- |
| Any `INVALID` | `INVALID` |
| Otherwise any `INDETERMINATE` | `INDETERMINATE` |
| Otherwise all applicable results `VALIDATED` | `VALIDATED` |
| No applicable contracts | `NOT_APPLICABLE` |

`NOT_APPLICABLE` contracts are excluded from aggregation; an empty applicable set must **not** be treated as validated (no vacuous acceptance). This is a proposed **conjunctive** policy for mandatory requirements, not a universal engineering rule. Before implementation, define applicability, mandatory versus advisory contracts, contract conflict/overlap, required coverage, evidence sufficiency, and whether aggregate validity can be asserted while mandatory contract coverage is incomplete. Contract outcomes must be revision-bound; `PENDING_REVALIDATION` is a **separate lifecycle state**, never a fifth contract outcome.

### F4. Evidence and engineering authority

Define `Authority(source, claimType, context, revision)` and `Sufficient(evidence, contract, correspondence, revision)`. A manufacturer family specification is not automatically an installed-asset configuration. Cross-template constraints require documented engineering approval; do not invent missing ranges, units, references, or semantics. Track evidence provenance, applicability, and revision.

### F5. Dependency and change-impact model

Define dependencies `D(k, SC, r)` over entities, properties, queries, contract versions, completeness assertions, and approved requirements. Given a source/contract change `Delta`, compute `Impact(Delta,D)` at **contract–correspondence-pair** granularity. Dependencies must include possible *new* matches (e.g., a duplicate catalog identifier), not just previously observed triples. The target is sound impact recall; over-approximation is acceptable but missed impacts are not.

### F6. Lifecycle state machine

Model lifecycle status separately from the latest historical validation outcome. At minimum distinguish `CURRENT` and `PENDING_REVALIDATION`; an affected correspondence transitions to pending when source/contract dependencies change, then receives a new revision-bound evaluation. A pending result must not be represented as currently certified. Specify allowed transitions, source revision consistency, concurrent updates, and failure/retry behavior.

### F7. Selective revalidation correctness

Target property: `V_selective(r+1) = V_full(r+1)` for all in-scope correspondence–contract pairs, under explicit assumptions: correct initial state, complete relevant change detection, sound dependency coverage, identical evaluation semantics, and consistent source/contract revision snapshots. Prove the property under these assumptions or label it an unproven objective. Evaluate both affected-set recall and selective/full agreement; performance improvement must be measured, not assumed.

### F8. Validation provenance and history

A validation record minimally identifies correspondence, contract and its version, source revision(s), evidence, outcome, timestamp, and execution/report reference. Preserve append-only historical decisions while exposing a unique authoritative current result per evaluated pair and revision policy. JSONL is only a prototype; a dedicated RDF provenance graph and reproducible source revision identifiers remain future work.

### Paper contribution grouping

- **C1 — Engineering semantic contracts:** F1–F4 (formal semantics, composition, authority).
- **C2 — Dependency-aware lifecycle:** F5–F6 (change impact and state transitions).
- **C3 — Correctness and traceability:** F7–F8 (conditional guarantees and reproducible evaluation).

These are research **objectives**, not demonstrated novelty or established guarantees. A CAiSE claim requires related-work comparison, approved engineering ground truth, multi-contract execution, correctness evidence, and comparative experiments.

### Immediate composition-definition plan

1. Specify contract applicability independently of evaluation outcome.
2. Distinguish mandatory/advisory contracts and explicit completeness of the required contract set.
3. Define the four-valued composition operator with truth table and empty-set behavior.
4. Specify evidence sufficiency and conflict handling; test order independence and aggregation invariants.
5. Link aggregate results to revision-aware lifecycle state and provenance.
6. Validate the semantics with real SC-01–SC-06 engineering cases before treating them as implemented.

### Current implementation boundary

The read-only GraphDB snapshot adapter and SC-01 Python lifecycle prototype are described in [GRAPHDB_LIFECYCLE_EXPERIMENT.md](GRAPHDB_LIFECYCLE_EXPERIMENT.md). The adapter and tests are committed but have **not** been verified against live GraphDB in this work. Native selective SHACL, RDF provenance, general contract composition, and multi-contract lifecycle revalidation remain unimplemented.
