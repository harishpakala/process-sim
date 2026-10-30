# SELiRA contract catalog alignment — research prototype

## Status

**UNRESOLVED**. Do not silently rename existing experimental contracts.
The experimental evaluator labels and the README's proposed contract catalog
are not interchangeable. This document records the difference rather than
claiming that it has been resolved.

| Experimental evaluator | Implemented experimental check | README proposal |
| --- | --- | --- |
| SC-01 | Cross-domain identity correspondence | Consult README for complete catalog |
| SC-02 | Quantity-kind compatibility | Engineering-to-Signal Meaning Consistency (broader) |
| SC-03 | Measurement-unit compatibility | Configuration and Revision Applicability (different) |
| SC-04 | Configuration and revision applicability | Not equivalent to README SC-03 by ID |
| SC-05 | Operational binding assertion | Experimental extension |
| CAC-01 | Operational Evidence Fitness | Operational Evidence Fitness |
| CAC-02 | Engineering Restriction Fitness | Engineering Restriction Fitness |

The README states its definitions are documentation proposals, not claims
about existing implementation specifications. Before publication, adopt one
versioned canonical catalog, map the experimental check identifiers into that
catalog, and update all result schemas, fixtures, and tables consistently.

## Evaluation layers

1. **Source qualification**: SC checks produce V, F, or U. Any F dominates,
   all V yields V, otherwise U.
2. **Consumer task fitness**: CAC-01 checks run/time interval, units,
   provenance and measurement coverage; CAC-02 checks engineering restriction
   approval, target property, units and configuration. Each may yield V, F,
   U or NA (explicitly outside scope).
3. **Consumer decision**: An in-scope V requires source V and CAC V;
   F dominates, U blocks use, and NA never authorizes.
4. **Authorization**: Always false in this prototype, even for synthetic V.

## Reproducibility

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_selira_integrated_contracts.py" -v
python -m unittest discover -s tests -p "test_selira_mixed_experiment.py" -v
python scripts/run_selira_integrated_experiment.py --focused selira-xmeas7-focused.json --output selira-integrated-results.json
python scripts/run_selira_mixed_experiment.py --output selira-mixed-results.json
```

The mixed-verdict experiment injects synthetic SC statuses **after**
individual SC evaluation. This isolates and tests aggregation semantics; it
is not an end-to-end contradictory engineering-evidence test. CAC task
controls are synthetic requirements and synthetic assertions, not actual
historian intervals or approved engineering restrictions.

The focused XMEAS7 RDF observations are discovery evidence, not independent
engineering authentication or a live OPC UA binding. Source-side real
qualification remains U; consumer task evidence is not supplied. No
engineering certification or authorization is issued.
