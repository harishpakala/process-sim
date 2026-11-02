# TEP NEXUS — Final E4-E Question Registry

Status: FROZEN for the E4-E manually assessed paper evaluation. This file records the benchmark wording; it does not change the evaluation scripts.

## Questions

1. Which instruments are associated with the reactor?
2. What are their electrical references?
3. What are their asset IDs and signal references?
4. Which products and manufacturers are associated with these assets?
5. What are their ECLASS and QUDT attributes?
6. Which asset identifiers link the engineering representations?
7. What engineering information is available for PI-1101?
8. Which fault was activated, and when?
9. For the selected reactor-related TEP signals XMEAS6, XMEAS7, XMEAS8, and XMEAS9, what were their recorded values and simulation timestamps immediately before and at the paper-fault-01 operator injection command at simulation time 30 seconds in the selected simulation run?
10. For the reactor feed-flow instrument FI-1101, provide its canonical AAS AssetIdentifier, DEXPI reference, ECAD reference, associated product candidate, ECLASS class, and operational signal. Also report the recorded XMEAS6 values and simulation timestamps immediately before and at the paper-fault-01 operator injection command at simulation time 30 seconds in the selected simulation run.

## Scope and evaluation record

- Selected demonstration subset: XMEAS6, XMEAS7, XMEAS8, XMEAS9; not the full Tennessee Eastman Process measurement set.
- Simulation run: `53b37c4d-b8ba-4e37-8f49-6765a156dc17`.
- Recorded event: operator `inject` command for `paper-fault-01` at simulation time 30 seconds. This does not establish causal effects.
- Model: `llama3.1:8b`; answer prompt SHA-256: `d556b0fcc819698af316af8134ec96131f0212fd13b9d5b7eaf67bf371f6a40d`.
- Manually assessed E4-E result: 10 PASS, 0 PARTIAL, 0 FAIL for this single run. Not an automated correctness check or statistical reliability estimate.
- E4-E changes only Q9 and Q10 relative to E4-D; Q1–Q8 are unchanged. Cross-version comparisons are not identical-benchmark comparisons.
- Product associations are simulation candidates, not verified physical installations; ECLASS verification remains pending. No OPC UA-to-historian same-run provenance is claimed.
- Evidence report: `reports/tep_nexus_e4e_evidence.json`; response report: `reports/tep_nexus_e4e_queries.json` (local generated artifacts; not asserted committed).

## Change control

Keep this list unchanged for reporting the E4-E result. Any later changes to questions or scoring rules require a new evaluation version and preserved historical results.
