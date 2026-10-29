# TEP-C02 — Measurements (XMEAS)

**Status:** Draft contract specification scaffold. Formal requirements below are **to be defined and verified against the implementation**; no conformance or formal verification is claimed.

## Scope

41 XMEAS signal identities, measured values, engineering units, sample context.

## Formal contract definition (pending implementation audit)

| Element | Required specification | Status |
| --- | --- | --- |
| Typed interface | Operations, input/output types and admissible values | To be specified |
| Preconditions | Conditions for each operation to be accepted | To be specified |
| Postconditions | Observable results of success and failure | To be specified |
| Invariants | State and data properties that must always hold | To be specified |
| Temporal semantics | Simulation-time rules and operation ordering | To be specified |
| Failure semantics | Explicit behavior for invalid input and invalid state | To be specified |
| Provenance | Run, backend, time and source attribution as applicable | To be specified |
| Verification | Implementation mapping, tests and conformance status | To be established |

## Contract properties to formalize

1. Identifier domain.
2. value/unit consistency.
3. sampling-time association.
4. missing or invalid measurement behavior.

## Verification status

No implementation-level contract audit or machine-checkable conformance proof has been performed for this document. Each eventual requirement must be classified as **implemented and tested**, **implemented but unverified**, or **specified but not implemented**.
