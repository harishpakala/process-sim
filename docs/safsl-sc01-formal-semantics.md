# SAFSL SC-01: finite-model semantics and compiler proof obligations

**Status:** executable reference semantics and bounded differential tests;
not a mechanized proof of compiler correctness. This document describes the
implemented grammar subset, not the entire proposed SAFSL language.

## 1. Supported syntax and binding environment

The implemented grammar supports `Specification`, Base64-encoded AAS
`SubmodelTemplate` references, and contracts of the form:

```text
forall a in assets {
  existsExactlyOne p in products where matches(a.ref, p.identifier);
}
```

A binding environment B resolves template aliases to an RDF focus class,
catalog class, and property predicates. The compiler rejects unresolved
aliases, unsafe IRIs, and reversed field operands. The compiler does **not**
derive bindings, completeness, applicability, or canonical identity from
the AAS templates.

## 2. Denotational semantics

Let A be the finite set of *applicable* canonical focus entities and P the
finite set of canonical catalog entities in one authoritative snapshot G.
Let R(a) be the set of reference field values for a, and I(p) the set of
identifier field values for p. Under the explicitly chosen lexical equality
policy, define:

```text
match(a,p) := exists r in R(a), i in I(p): STR(r) = STR(i)
M(a) := { p in P | match(a,p) }
holds(G,A,P) := forall a in A: |M(a)| = 1
```

The cardinality is over **distinct canonical product resources**, not
reference triples or matching identifier literals. An asset with no reference
has |M(a)| = 0. Two different products with the same identifier yield
|M(a)| = 2. Several reference literals resolving to the same single product
still yield |M(a)| = 1; the current contract does not impose a single-value
constraint on the reference property.

This definition uses a closed, authoritative snapshot. RDF open-world
semantics alone cannot justify that missing triples imply missing entities.

## 3. Evidence-aware verdicts

For a confirmed applicability scope:

- **U** when completeness or canonical-identity normalization is not
  attested, or the declared focus population cannot be established.
- **NA** when the confirmed applicable focus population is empty.
- **V** when all applicable assets have exactly one matching product.
- **F** when at least one applicable asset has zero or more than one
  matching product, *provided the evidence preconditions hold*.

Applicability must be confirmed independently. An empty set of RDF
`hasProductReference` triples is not evidence of non-applicability.

The executable oracle is
`src/process_sim/safsl/shacl/reference_semantics.py`. The production
admission coordinator has additional transaction/version checks. The
standalone lifted evaluator currently treats missing focus-class triples as
NA; that result is justified only if the focus population is known complete.

## 4. Compilation correspondence

For each source focus entity a, the compiler emits a SHACL NodeShape with
`sh:targetClass` (or explicitly requested `sh:targetSubjectsOf`), and a
SPARQL violation query with two branches:

1. NOT EXISTS any matching product: |M(a)| = 0.
2. EXISTS two *distinct* matching product resources: |M(a)| >= 2.

Thus, assuming the focus targeting selects exactly A, the catalog pattern
selects exactly P, and RDF term/lexical equality agrees with the source
equality policy, the query reports a violation iff |M(a)| != 1.

**Important binding caveat:** `match_by_predicate=True` selects all
subjects with the identifier predicate, regardless of RDF catalog class.
It is sound only when that predicate is exclusive to the authoritative
catalog population. `target_by_predicate=True` selects only subjects
already carrying the reference predicate and cannot detect missing
references; it must not be used for an all-assets obligation.

## 5. Proof obligations and present evidence

- **Parsing/binding soundness:** malformed input and unresolved semantic
  bindings must be rejected; existing unit tests cover selected cases.
- **Focus coverage:** compiled targets must equal the intended applicable
  population, including assets missing the reference field.
- **Catalog coverage:** catalog bindings must select only canonical catalog
  products and include all such products in the snapshot.
- **Predicate equivalence:** emitted SPARQL equality must implement the
  declared identity/value policy.
- **Cardinality equivalence:** for every focus a, a SHACL violation must
  occur iff |M(a)| != 1.
- **Admission soundness:** V may commit only after independent evidence
  attestations and successful validation against the same snapshot/version.

`tests/test_safsl_semantics_differential.py` compares the independent
finite-model oracle to generated SHACL on **81 exhaustively enumerated**
two-asset/two-product snapshots (each field absent, A, or B). It also checks
U/NA preconditions and duplicate-product cardinality. This is bounded
evidence, **not** a proof for arbitrary graphs, mappings, SPARQL engines,
or distributed transactions.

## 6. Research evaluation still required

Add randomized/property-based larger models; multiple identifiers and
references per entity; RDF datatype and language-tag comparisons; adversarial
class/predicate mappings; sameAs/canonicalization tests; malformed SAFSL
rejection; cross-engine SHACL comparison; and mutation testing. Define and
validate the TEP NEXUS applicability scope independently of SC-01.
Record tool versions, seeds, runtimes, and counterexamples for reproducibility.
