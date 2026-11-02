# TEP NEXUS paper evaluation (four reactor measurements)

Run from the repository root:

```bash
python scripts/tep_nexus_paper_evaluation.py
python -m unittest discover -s tests -p 'test_tep_nexus_paper_evaluation.py'
```

The default read-only run checks AssetInventory and ProductCatalog AAS instances for
pressure (PI-1101/XMEAS7), flow (FI-1101/XMEAS6), temperature
(TI-1101/XMEAS9), and level (LI-1101/XMEAS8), and writes
`reports/tep_nexus_paper_evaluation.json`.

To retrieve recorded fault-command and measurement evidence for an **existing,
operator-verified** simulation run:

```bash
export TEP_TIMESCALE_DSN='postgresql://...'
python scripts/tep_nexus_paper_evaluation.py --run-id VERIFIED_RUN_UUID
```

The run is not started and no fault is injected by this script. For each
signal the pre-fault sample is the latest sample strictly before the
recorded activation time; the post-fault sample is the earliest at or
after activation. All selections are restricted to the supplied run ID.
A recorded command does not establish causal influence.

## Coverage and remaining work

- Q4–Q5: AssetInventory/ProductCatalog evidence extracted directly from AAS
  instances; no natural-language answer grading.
- Q8–Q9: TimescaleDB evidence available only when a persisted activation
  event and corresponding run-specific samples exist.
- Q1–Q3, Q6–Q7, Q10: marked **UNVERIFIED_CROSS_DOMAIN_MAPPING** until explicit
  DEXPI–ECAD–BOM–AssetInventory relationships are verified in GraphDB.
  Similar equipment tags do not prove identity.
- The current script does not call Ollama, execute a simulation, inject a
  fault, or assert that the existing natural-language planner supports all
  ten paper queries. These require separate integration and live tests.

ECLASS verification is pending in the product records. QUDT attributes
refer to product-family specifications, not automatically to simulated
signal units. Product references are engineering candidates/selections,
not verified installed devices.
