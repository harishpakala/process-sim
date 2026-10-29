# TEP-C04 — Native disturbances contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_dist(i,k) = (I_i, A_(i,k), T_s, D, P)
\]

**Elements:** I_i: native IDV identity; A_(i,k): binary activation state; T_s: scheduled activation time; D: scheduled duration; P: source and fault provenance.

**Constraint:** i ∈ {1,…,20}; A_(i,k) ∈ {0,1}. Scheduled faults are synchronized at native step boundaries.

**Implementation boundary:** Native IDV state is exposed by the adapter; T_s, D and P belong to scenario/fault scheduling rather than the native IDV vector itself.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
