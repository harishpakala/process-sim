# TEP-C04 — Native disturbances contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_dist(i,k) = (I_i, A_(i,k), T_s, D, P)
\]

## Tuple elements

| Symbol | Meaning | Source |
| --- | --- | --- |
| `I_i` | IDV identifier, i = 1,…,20 | Native TEP IDV indexing |
| `A_(i,k)` | Binary activation state at step k | TEPAdapter.get_disturbances() |
| `T_s` | Scheduled activation time | Fault/scenario scheduler |
| `D` | Scheduled duration | Fault/scenario scheduler |
| `P` | Disturbance source and provenance | Fault/scenario metadata |

**Constraint:** i ∈ {1,…,20}; A_(i,k) ∈ {0,1}. Scheduled faults are synchronized at native step boundaries.

**Implementation boundary:** Native IDV state is exposed by the adapter; T_s, D and P belong to scenario/fault scheduling rather than the native IDV vector itself.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
