# TEP-C05 — Fault and scenarios contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_fault(f) = (I_f, F_f, X_f, M_f, T_s, D, P)
\]

**Elements:** I_f: fault identifier; F_f: fault type; X_f: XMEAS/XMV/IDV target; M_f: magnitude or value where applicable; T_s: start time; D: duration; P: scenario/operator provenance.

**Constraint:** For a finite scheduled fault, intended active interval is T_s ≤ T < T_s + D, evaluated at native simulation-step boundaries.

**Implementation boundary:** Magnitude is not meaningful for every fault type; stuck faults use a target value and process disturbances use native binary IDV activation.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
