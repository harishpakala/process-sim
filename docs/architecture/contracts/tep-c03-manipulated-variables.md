# TEP-C03 — Manipulated variables contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_ctrl(i,k) = (I_i, V_(i,k), T_k, Q, P)
\]

**Elements:** I_i: XMV signal identity; V_(i,k): manipulated value; T_k: simulation time; Q: native/manual control mode; P: command or observation provenance.

**Constraint:** i ∈ {1,…,12}. The adapter rejects out-of-range XMV indices; OPC UA external control uses manual mode.

**Implementation boundary:** Control values are exposed by the adapter; provenance depends on the OPC UA/event or recording layer.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
