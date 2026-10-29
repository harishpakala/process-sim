# F7 — Selective revalidation correctness (SC-01 reference slice)

**Status:** Conditional correctness argument and executable finite-state regression suite; not a general proof of SHACL/SPARQL incremental validation.

## Goal

For source revisions r and r+1 and correspondence set K, show:

`forall k in K: Selective(k,r+1) = Full(k,r+1)`

where equality concerns the SC-01 four-valued contract outcome, not execution time or publication authority.

## Assumptions

A1. The two snapshots contain the full relevant assigned-reference map, catalog identifier map, and trustworthy catalog-completeness flag. Change detection is exhaustive for those maps.

A2. SC-01 evaluation is deterministic and uses exactly: (i) assigned reference of the asset, (ii) completeness flag, (iii) cardinality of catalog identifiers equal to that reference. Any extra authority or rule inputs are tracked separately.

A3. Dependency capture includes the assignment token, the *entire identifier lookup scope*, including absent matches, and catalog completeness. Both old and new lookup scopes are considered.

A4. Contract policy, authority, and evaluator version are unchanged for reused outcomes; if not, full revalidation is required.

A5. Both snapshots are immutable, internally consistent and comparable. New/removed assignments are included in the comparison universe.

## Conditional correctness argument

For an asset not in the impact set, the assigned reference is unchanged; the catalog completeness flag is unchanged; and no catalog identifier equal to that reference was added, removed or changed (including previously absent and duplicate matches). Under A1–A3 the SC-01 evaluator reads an equivalent projection of its inputs at both revisions. Under A2 and A4 its outcome is identical. Therefore reusing the old outcome equals full re-evaluation. Every affected asset is evaluated at r+1, hence its outcome trivially equals full re-evaluation. If A1–A4 cannot be attested, the algorithm evaluates all assets, so equality follows by construction. This proves equality for the specified SC-01 snapshot evaluator *conditional on A1–A5*.

This argument does **not** prove that the current GraphDB adapter establishes A1 or A5; that must be demonstrated experimentally.

## Regression and measurement

`tests/test_selira_f7_selective_equivalence.py` compares all 1296 ordered pairs of 36 small snapshots (single asset, two catalog entries) and includes conservative fallback and unaffected-asset cases. The test suite is finite exploration, not a proof for arbitrary RDF graphs. `EquivalenceReport` exposes selective/full evaluation counts, impact set, fallback and equality.

## Limitations and next steps

- This module returns comparison reports; it does not yet persist or publish F6 state transitions.
- No general query-dependency extraction for SPARQL, SHACL paths, graph revisions, contract versions or authority revisions is implemented.
- No GraphDB-backed end-to-end experiment or timing baseline has been executed.
- Expand tests to multi-asset/property-based scenarios and independently verify complete source change feeds.
