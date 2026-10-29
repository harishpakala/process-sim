# TEP-C01 — Simulation contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_sim(k) = (B, S_k, T_k, Δt, R, Q)
\]

## Tuple elements

| Symbol | Meaning | Source |
| --- | --- | --- |
| `B` | Native simulation backend | TEPAdapter configuration |
| `S_k` | Native process state at step k | Native TEP simulator |
| `T_k` | Simulation time (hours) at step k | Native TEP simulator |
| `Δt` | Native simulation-time increment | Native simulator; test expectation |
| `R` | Random seed | TEPAdapter constructor |
| `Q` | Control mode | TEPAdapter constructor |

**Constraint:** T_0 = 0 after successful reset in tested fixture; T_1 ≈ 1/3600 h after one step. Native backend behavior determines whether T_(k+1) = T_k + Δt holds generally.

**Implementation boundary:** B, R and Q are adapter configuration; S_k and T_k are native state/time. Δt is observed from tests, not a guaranteed constant across all backends.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
