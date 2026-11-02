# Semantic SHACL-SPARQL comparator (E1–E10)

## Research purpose

This experiment compares (A) SHACL Core structural completeness,
(B) structural plus engineering-aware SHACL-SPARQL constraints, and
(C) SELiRA's source qualification and consumer-specific decision logic.

The semantic profile is deliberately **stronger** than the original
structural comparator: it detects mismatched quantity kinds (E3),
incompatible pressure/temperature dimensions (E4), explicit
inapplicability (E6), missing task-matched revision evidence (E5),
and explicit consumer violations (E8). It also tests identity and
binding contradictions, though E1–E10 do not contain all such cases.

The semantic profile uses a small enumerated unit vocabulary and
selected input assertion predicates. It is not a complete industrial
SHACL model, does not authenticate evidence, and does not produce
three-valued or task-specific engineering authorization decisions.

## Reproduction (PowerShell)

```powershell
git switch docs/readme-startup-simplification
git pull origin docs/readme-startup-simplification
python -m pip install "rdflib>=7,<9" "pyshacl>=0.30,<1"
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_selira_semantic_shacl_baseline.py" -v
python scripts/run_selira_semantic_shacl_baseline.py `
  --focused selira-xmeas7-focused.json `
  --output selira-semantic-shacl-results.json
```

## Expected, not yet independently executed

| Case | Structural SHACL | Semantic SHACL | SELiRA source |
|---|---|---|---|
| E1 | Conforms | Conforms | V |
| E2 | Nonconforms | Nonconforms | U |
| E3 | Conforms | Nonconforms | F |
| E4 | Conforms | Nonconforms | F |
| E5 | Conforms | Nonconforms | U |
| E6 | Conforms | Nonconforms | F |
| E7 | Nonconforms | Nonconforms | U |
| E8 | Conforms | Nonconforms | V; CAC-01=F |
| E9 | Nonconforms | Nonconforms | V; CAC-02=U |
| E10 | Nonconforms | Nonconforms | U |

**Interpretation:** A semantic SHACL violation does not distinguish an
explicit engineering contradiction (SELiRA F) from insufficient evidence
(SELiRA U), nor source failure from task-specific consumer failure.
A conforming graph is not independently authenticated or authorized.
These are differences in the selected *decision models*, not evidence
that SHACL cannot be extended to implement a similar policy.

E1–E9 remain synthetic. E10 remains focused GraphDB discovery without
authenticated engineering contracts. Future work should compare against
an independently designed SHACL profile with provenance, authority and
task-scoped SPARQL constraints, plus independent reference labels.

Do not report the table as observed until tests and runner have been
executed. Preserve pySHACL version, RDF inputs, shapes and validation
reports for reproducibility.
