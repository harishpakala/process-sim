# SELiRA CAiSE evaluation — E1–E10 evidence benchmark

## Purpose

This is a reproducible *prototype* comparison, not a field validation.
E1–E9 perturb synthetic evidence records **before** invoking SC-01 through
SC-05 and CAC-01/CAC-02. No source statuses are injected. E10 uses the
existing focused XMEAS7 GraphDB discovery report.

| Case | Perturbation | Expected source | Consumer effect |
| --- | --- | --- | --- |
| E1 | Complete synthetic assertions | V | Both evaluator-level V |
| E2 | Remove DEXPI→ECAD correspondence | U | Both U |
| E3 | Operational quantity pressure→temperature | F | Both F |
| E4 | Operational unit kPa→degC | F | Both F |
| E5 | Applicability assertion revision differs from task | U | Both U |
| E6 | Exact-scope applicability marked INAPPLICABLE | F | Both F |
| E7 | Remove authenticated operational binding assertion | U | Both U |
| E8 | CAC-01 measurementCoverage marked VIOLATED | V | CAC-01 F, CAC-02 V |
| E9 | Remove CAC-02 approval check | V | CAC-01 V, CAC-02 U |
| E10 | Real focused XMEAS7 discovery | U | Both U |

**E7 caveat:** The synthetic target contains a declared NodeId; removing
the binding assertion tests absence of authenticated binding, not an actual
OPC UA connectivity probe.

## Comparator definitions

- **B1_identifier_presence**: accepts when the five source-domain identifier
  strings are populated. For E10, the fixed focused report contains the
  relevant declared identifiers. It does not verify equivalence.
- **B2_structural_presence**: accepts when required assertion arrays are
  present (and the SC-01 link count is four). For E10, the focused report
  contains declared structural relationships. It does not execute SHACL.
- **SELiRA_evaluator**: source conjunction of the five actual SC evaluator
  outputs, followed by task-specific CAC evaluation. All engineering
  authorization flags remain false.

B1/B2 are deliberately naive experimental comparators, **not** published
baselines or representations of GraphDB, SHACL, or any existing tool.

Reference labels are scenario expectations and must not be presented as
independent engineering ground truth. The reported unsupported-acceptance
count measures *permissive comparator outputs on synthetic U/F cases*,
not field-measured false acceptance rates. No inferential statistical
claim is supported by these ten cases.

## Run (Windows PowerShell)

```powershell
git switch docs/readme-startup-simplification
git pull origin docs/readme-startup-simplification
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_selira_e1_e10_benchmark.py" -v
python scripts/run_selira_e1_e10_benchmark.py `
  --focused selira-xmeas7-focused.json `
  --output selira-e1-e10-results.json
```

## Publication readiness

Still needed: canonical versioned contract catalog, independent reference
label adjudication, stronger realistic evidence fixtures, actual external
baselines with controlled equivalent inputs, and runtime measurements.
The real XMEAS7 case is discovery only and remains U. No certification
or engineering use is authorized.
