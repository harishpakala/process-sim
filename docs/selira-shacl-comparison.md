# E1–E10: actual SHACL Core comparator

This experiment executes the open-source **pySHACL** engine against a
published SHACL Core shape (`experiments/shacl/structural-baseline.ttl`).
It is **not** a claim that SHACL cannot express engineering semantics.

## Comparable input

E1–E9 use the same synthetic *input assertion records* as the SELiRA
evidence benchmark. `run_selira_shacl_baseline.py` converts these records
to RDF without copying SELiRA contract outcomes into the RDF graph.
The SHACL Core shape checks the presence and structure of identity links,
quantity-kind records, unit records, revision-applicability assertions,
binding assertions, and CAC check records.

E10 includes the actual focused GraphDB discovery observations as separate
RDF observation nodes. Those observations are not promoted to authenticated
assertions; the structural shape therefore reports missing contract evidence.
No claim of graph-wide absence follows from this result.

## Run in Windows PowerShell

```powershell
git switch docs/readme-startup-simplification
git pull origin docs/readme-startup-simplification
python -m pip install "rdflib>=7,<9" "pyshacl>=0.30,<1"
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_selira_shacl_baseline.py" -v
python scripts/run_selira_shacl_baseline.py `
  --focused selira-xmeas7-focused.json `
  --output selira-shacl-baseline-results.json
```

## Interpretation

A SHACL `conforms=true` means **only** that the RDF graph satisfies this
specific shape. A SHACL validation failure does **not** automatically mean
an engineering contradiction: for example, missing evidence is U for SELiRA
but violates the shape's `sh:minCount` constraint.

The shape deliberately checks structure, not semantic equivalence,
authentication, unit dimensions, or task-specific engineering authority.
A stronger comparison should add SHACL-SPARQL constraints for semantic
mismatches and explicit provenance/revision rules, or adapt an independently
developed industrial SHACL validation profile. Such stronger shapes may
detect E3/E4/E6. The research question is whether a source-qualification
and consumer-decision policy adds value *on top of* a validation engine.

**Do not call this baseline a complete SHACL approach or interpret its
nonconformance rate as a false-acceptance rate.** Report the shape,
engine/version, RDF translation, and validation report alongside SELiRA's
three-valued decisions. Synthetic E1–E9 are not authenticated field data.
All engineering authorization remains false.
