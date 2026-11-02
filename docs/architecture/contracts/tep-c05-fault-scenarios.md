# TEP-C05 — Fault and scenarios contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_fault(f) = (I_f, F_f, X_f, M_f, T_s, D, P)
\]

## Tuple elements

| Symbol | Meaning | Source |
| --- | --- | --- |
| `I_f` | Fault identifier | Fault definition |
| `F_f` | Fault type | Fault definition |
| `X_f` | Target XMEAS, XMV or IDV signal | Fault definition |
| `M_f` | Magnitude or target value, when applicable | Fault definition |
| `T_s` | Scheduled start time | Fault definition |
| `D` | Scheduled duration | Fault definition |
| `P` | Scenario or operator provenance | Fault metadata/event layer |

**Constraint:** For a finite scheduled fault, intended active interval is T_s ≤ T < T_s + D, evaluated at native simulation-step boundaries.

**Implementation boundary:** Magnitude is not meaningful for every fault type; stuck faults use a target value and process disturbances use native binary IDV activation.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
