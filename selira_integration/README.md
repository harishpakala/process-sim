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
